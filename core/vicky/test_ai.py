import os
import requests
from typing import Annotated, Literal, TypedDict, List
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel

# Carica le variabili dal file .env (SERVER_IP, HA_TOKEN, OPENAI_API_KEY)
load_dotenv()

def test_connessione():
    print(f"--- DIAGNOSTICA NEOCITY ---")
    print(f"IP Server: {os.getenv('SERVER_IP')}")
    
    url = f"http://{os.getenv('SERVER_IP')}:8123/api/states"
    headers = {"Authorization": f"Bearer {os.getenv('HA_TOKEN')}"}
    
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            print("✅ Connessione a Home Assistant: OK!")
            # Cerchiamo la luce ingresso
            stati = r.json()
            luce = next((s for s in stati if s['entity_id'] == 'light.l_ing'), None)
            if luce:
                print(f"✅ Entità 'light.l_ing' trovata! Stato attuale: {luce['state']}")
            else:
                print("❌ Errore: Entità 'light.l_ing' non trovata. Controlla lo YAML.")
        else:
            print(f"❌ Errore HA: Status Code {r.status_code}")
    except Exception as e:
        print(f"❌ Errore di rete: {e}")

# --- 1. DEFINIZIONE DELLO STATO ---
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], "Il registro della conversazione"]
    destination: str

# --- 2. TOOL PER LA REGGIA ---
@tool
def gestisci_casa(azioni: List[dict]):
    """
    Esegue azioni sui dispositivi (luci, switch, tapparelle, elettrodomestici).
    Ogni azione nel formato: {'entita': 'domain.entity_id', 'comando': 'service_name'}
    Esempio: [{'entita': 'light.cucina_luce', 'comando': 'turn_on'}]
    """
    risultati = []
    headers = {
        "Authorization": f"Bearer {os.getenv('HA_TOKEN')}",
        "Content-Type": "application/json"
    }
    
    for azione in azioni:
        entita = azione['entita']
        cmd = azione['comando']
        dominio = entita.split(".")[0]
        
        # Correzione automatica per le tapparelle
        if dominio == "cover":
            if "on" in cmd or "open" in cmd: cmd = "open_cover"
            elif "off" in cmd or "close" in cmd: cmd = "close_cover"
            
        url = f"http://{os.getenv('SERVER_IP')}:8123/api/services/{dominio}/{cmd}"
        try:
            r = requests.post(url, headers=headers, json={"entity_id": entita}, timeout=5)
            risultati.append(f"{entita}: {r.status_code} OK")
        except Exception as e:
            risultati.append(f"{entita}: ERRORE ({str(e)})")
            
    return "\n".join(risultati)

@tool
def stato_casa(stanza: str = None):
    """
    Legge lo stato di sensori (temperatura, luce, presenza) e attuatori.
    Filtra per stanza se specificato (ingresso, soggiorno, cucina, camera, bagno).
    """
    headers = {"Authorization": f"Bearer {os.getenv('HA_TOKEN')}"}
    try:
        r = requests.get(f"http://{os.getenv('SERVER_IP')}:8123/api/states", headers=headers, timeout=5)
        all_states = r.json()
        
        stanze_valide = ["ingresso", "soggiorno", "cucina", "camera", "bagno"]
        report = []
        
        for s in all_states:
            e_id = s['entity_id']
            # Filtriamo solo le entità della nostra configurazione MQTT
            if any(stanza_nome in e_id for stanza_nome in stanze_valide):
                if not stanza or stanza.lower() in e_id:
                    name = s['attributes'].get('friendly_name', e_id)
                    stato = s['state']
                    unit = s['attributes'].get('unit_of_measurement', '')
                    report.append(f"- {name}: {stato} {unit}")
        
        return "\n".join(report) if report else "Nessun dispositivo trovato."
    except Exception as e:
        return f"Errore lettura stati: {e}"

tools = [gestisci_casa, stato_casa]
tool_node = ToolNode(tools)

# --- 3. MODELLI (Cloud & Locale) ---
llm_cloud = ChatOpenAI(model="gpt-4o-mini", temperature=0)
llm_local = ChatOllama(
    model="llama3.1", 
    base_url=f"http://{os.getenv('SERVER_IP')}:11434",
    temperature=0
).bind_tools(tools)

# --- 4. LOGICA DEL ROUTER ---
class RouteQuery(BaseModel):
    destination: Literal["domotica", "generica"]

router_llm = llm_cloud.with_structured_output(RouteQuery)

def router_node(state: AgentState):
    prompt = [
        SystemMessage(content="Se la richiesta riguarda la casa, i sensori, le stanze o i dispositivi, rispondi 'domotica'. Per tutto il resto rispondi 'generica'."),
        state['messages'][-1]
    ]
    decision = router_llm.invoke(prompt)
    return {"destination": decision.destination}

# --- 5. NODI AGENTI ---
# --- FORZIAMO L'USO DEI TOOL ---
# bind_tools con tool_choice="required" obbliga il modello a generare una chiamata a un tool
llm_local = ChatOllama(
    model="llama3.1", 
    base_url=f"http://{os.getenv('SERVER_IP')}:11434",
    temperature=0
).bind_tools(tools) # Alcune versioni di Ollama supportano tool_choice="required"

def domotica_agent(state: AgentState):
    # Creiamo un contesto con la lista esatta delle entità per non farlo sbagliare
    elenco_entita = """
    LUCI: light.l_ing (Ingresso), light.l_sog1, light.l_sog2, light.l_cuc, light.l_cam_sof
    TAPPARELLE: cover.cov_sog, cover.cov_cuc, cover.cov_cam, cover.cov_bag
    SENSORI: sensor.sn_sog_temp (Temp Soggiorno), sensor.sn_cuc_temp
    """
    
    sys_msg = SystemMessage(content=(
        f"Sei il sistema operativo Neocity. Elenco entità reali: {elenco_entita}\n"
        "REGOLE RIGIDE:\n"
        "1. Ogni richiesta dell'utente deve trasformarsi in una chiamata a 'gestisci_casa' o 'stato_casa'.\n"
        "2. NON rispondere con testo libero se non hai prima eseguito un tool.\n"
        "3. Se l'utente dice 'Spegni luce ingresso', chiama gestisci_casa con entita='light.l_ing' e comando='turn_off'."
    ))
    
    # Prendiamo solo l'ULTIMO messaggio dell'utente per evitare che i fallimenti passati lo confondano
    ultimo_messaggio = [m for m in state['messages'] if isinstance(m, HumanMessage)][-1:]
    
    response = llm_local.invoke([sys_msg] + ultimo_messaggio)
    return {"messages": [response]}

def generica_agent(state: AgentState):
    sys_msg = SystemMessage(content="Sei un assistente utile e simpatico. Rispondi a domande generali.")
    response = llm_cloud.invoke([sys_msg] + state['messages'])
    return {"messages": [response]}

# --- 6. COSTRUZIONE DEL GRAFO ---
workflow = StateGraph(AgentState)

workflow.add_node("router", router_node)
workflow.add_node("domotica", domotica_agent)
workflow.add_node("generica", generica_agent)
workflow.add_node("action", tool_node)

workflow.set_entry_point("router")

workflow.add_conditional_edges(
    "router",
    lambda x: x["destination"],
    {"domotica": "domotica", "generica": "generica"}
)

workflow.add_conditional_edges(
    "domotica",
    lambda x: "action" if x["messages"][-1].tool_calls else END
)

workflow.add_edge("action", "domotica")
workflow.add_edge("generica", END)

app = workflow.compile()

# --- 7. ESECUZIONE INTERATTIVA CON MEMORIA ---
if __name__ == "__main__":
    test_connessione()
    print("\n🏰 Benvenuto nella Reggia Neocity! (Scrivi 'esci' per chiudere)")
    session_history = []
    
    while True:
        print(f"DEBUG - Storia inviata all'AI: {[m.content for m in session_history]}")
        user_input = input("\nTu: ")
        if user_input.lower() in ["esci", "quit", "exit"]:
            break
            
        session_history.append(HumanMessage(content=user_input))
        
        # Invochiamo il grafo
        final_state = app.invoke({"messages": session_history})
        
        # Recuperiamo l'ultima risposta
        ai_msg = final_state['messages'][-1]
        session_history.append(ai_msg)
        
        print(f"\nAI: {ai_msg.content}")