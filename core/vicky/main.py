"""
main.py
Entry point di Vicky AI — API FastAPI
"""

import os
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from neo4j import GraphDatabase

from router_local import call_local_router
from nlp_engine import NLPEngine
from query_engine import QueryEngine
from feedback_engine import FeedbackEngine



app = FastAPI(title="Vicky AI", version="1.0.0")

# ── Configurazione ─────────────────────────────────────────────────────────────
NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://neo4j:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "chaospassword")
HA_URL         = os.getenv("HA_URL",         "http://homeassistant:8123")
HA_TOKEN       = os.getenv("HA_TOKEN",       "")
OLLAMA_URL     = os.getenv("OLLAMA_URL",     "http://ollama:11434")
OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL",   "llama3.2")

# ── Wrapper Neo4jManager minimale ──────────────────────────────────────────────
class Neo4jManager:
    """Wrapper minimale compatibile con NLPEngine e QueryEngine."""
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

# ── Inizializzazione engines ───────────────────────────────────────────────────
db           = Neo4jManager(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
query_engine = QueryEngine(db)
nlp_engine   = NLPEngine(db, common_yaml_path="_common.yaml")

feedback_engine = FeedbackEngine(
    neo4j_uri=NEO4J_URI,
    neo4j_user=NEO4J_USER,
    neo4j_password=NEO4J_PASSWORD,
    influx_url=os.getenv("INFLUXDB_URL", "http://influxdb:8086"),
    influx_token=os.getenv("INFLUXDB_TOKEN", ""),
    influx_org=os.getenv("INFLUXDB_ORG", "chaos"),
    influx_bucket=os.getenv("INFLUXDB_BUCKET", "casa")
)

# ── Precaricamento indice al boot ─────────────────────────────────────────────
@app.on_event("startup")
def startup_event():
    print("[Vicky] Precariamento indice NLP...")
    nlp_engine.ensure_index()
    print("[Vicky] Indice pronto.")

# ── Modelli request/response ───────────────────────────────────────────────────
class CommandRequest(BaseModel):
    text:       str
    session_id: Optional[str] = "default"

class CommandResponse(BaseModel):
    input:     str
    type:      str
    level:     Optional[int] = None
    calls:     Optional[list] = None
    response:  str
    success:   bool

# ── Health check ───────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "service": "vicky-ai"}

class FeedbackRequest(BaseModel):
    original_text:   str
    correct_area:    Optional[str] = None
    correct_device:  Optional[str] = None
    correct_command: Optional[str] = None
    session_id:      Optional[str] = "default"

# ── feedback endpoint ──────────────────────────────────────────────────────────
@app.post("/feedback")
def process_feedback(req: FeedbackRequest):
    result = feedback_engine.process(
        original_text=req.original_text,
        correct_area=req.correct_area,
        correct_device=req.correct_device,
        correct_command=req.correct_command,
        session_id=req.session_id
    )
    nlp_engine.build_index()
    return result

@app.post("/rebuild-index")
def rebuild_index():
    """Forza la ricostruzione dell'indice NLP."""
    nlp_engine.build_index()
    return {"status": "ok", "message": "Indice ricostruito."}

# ── Endpoint principale ────────────────────────────────────────────────────────
@app.post("/command", response_model=CommandResponse)
def process_command(req: CommandRequest):
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Testo vuoto")

    # Step 1 — NLP Engine estrae slot
    extraction = nlp_engine.extract(text)
    print(f"[DEBUG] extraction: {extraction.to_dict()}")
    print(f"[DEBUG] confident: {extraction.confident}")

    if extraction.confident:
        # L'NLP restituisce node_id (es. "luce_semplice", "toggle", "Sala")
        # Il QueryEngine cerca per alias — usiamo una query diretta per id
        area_id    = extraction.area
        device_id  = extraction.device
        command_id = extraction.command

        print(f"[DEBUG] node_ids: area={area_id}, device={device_id}, command={command_id}")

        # Risolvi direttamente tramite id archetipo
        qr = _resolve_by_ids(area_id, device_id, command_id)
        print(f"[DEBUG] query_result: status={qr['status']}")

        if qr['status'] == "ok":
            executed = []
            for call in qr['calls']:
                ok = _execute_ha(call['entity_id'], call['service'], call.get('service_data', {}))
                executed.append({"entity_id": call['entity_id'],
                                "service": call['service'],
                                "success": ok})
            all_ok = all(c["success"] for c in executed)
            return CommandResponse(
                input=text,
                type="domotica",
                level=1,
                calls=executed,
                response="Fatto." if all_ok else "Eseguito parzialmente.",
                success=all_ok
            )
        if qr['status'] == "ambiguous":
            return CommandResponse(
                input=text,
                type="domotica",
                level=1,
                response=qr['message'],
                success=False
            )

    # Step 2 — NLP non sicuro → Ollama decide
    decision, _ = call_local_router(text, OLLAMA_URL, OLLAMA_MODEL)

    if decision == "DOMOTICA":
        # Livello 3 — fallback LLM domotica
        return CommandResponse(
            input=text,
            type="domotica",
            level=3,
            response=_llm_domotica_fallback(text),
            success=False
        )

    # Generica
    return CommandResponse(
        input=text,
        type="generica",
        response=_llm_generica(text),
        success=True
    )

# ── Helpers ────────────────────────────────────────────────────────────────────
def _execute_ha(entity_id: str, service: str, service_data: dict = {}) -> bool:
    try:
        domain, svc = service.split(".", 1)
        url     = f"{HA_URL}/api/services/{domain}/{svc}"
        headers = {"Authorization": f"Bearer {HA_TOKEN}",
                   "Content-Type": "application/json"}
        payload = {"entity_id": entity_id, **service_data}
        r = requests.post(url, json=payload, headers=headers, timeout=5)
        return r.status_code in (200, 201)
    except Exception as e:
        print(f"[Vicky] Errore HA: {e}")
        return False

def _llm_generica(text: str) -> str:
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": text, "stream": False},
            timeout=30
        )
        return r.json().get("response", "Non ho capito.").strip()
    except Exception as e:
        return f"Errore LLM: {e}"

def _llm_domotica_fallback(text: str) -> str:
    prompt = (
        f"Sei Vicky, assistente domotico CHAOS. "
        f"Non ho trovato il dispositivo per: '{text}'. "
        f"Rispondi brevemente in italiano."
    )
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=30
        )
        return r.json().get("response", "Dispositivo non trovato.").strip()
    except Exception as e:
        return f"Errore LLM: {e}"

def _resolve_by_ids(area_id: str | None, device_id: str | None, command_id: str | None) -> dict:
    """Risolve device+command direttamente per node_id nel grafo."""
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            if device_id and command_id and area_id:
                rows = list(s.run("""
                    MATCH (d:Device)-[:INSTANCE_OF]->(:Archetype {id: $arch})
                    MATCH (d)-[:BELONGS]->(:Area {id: $area})
                    MATCH (d)-[:HAS_COMMAND]->(c:Command)
                    MATCH (c)-[:HAS_ALIAS]->(a:Alias {value: $cmd})
                    WHERE c.ha_service_key STARTS WITH split(d.ha_entity_id, '.')[0]
                    RETURN d.ha_entity_id as eid, c.ha_service_key as svc
                    LIMIT 1
                """, arch=device_id, area=area_id, cmd=command_id))
            elif device_id and command_id:
                rows = list(s.run("""
                    MATCH (d:Device)-[:INSTANCE_OF]->(:Archetype {id: $arch})
                    MATCH (d)-[:HAS_COMMAND]->(c:Command)
                    MATCH (c)-[:HAS_ALIAS]->(a:Alias {value: $cmd})
                    WHERE c.ha_service_key STARTS WITH split(d.ha_entity_id, '.')[0]
                    RETURN d.ha_entity_id as eid, c.ha_service_key as svc
                    LIMIT 1
                """, arch=device_id, cmd=command_id))
            elif device_id:
                rows = list(s.run("""
                    MATCH (arch:Archetype {id: $arch})
                    MATCH (d:Device)-[:INSTANCE_OF]->(arch)
                    MATCH (d)-[:HAS_COMMAND]->(c:Command {id: arch.default_command})
                    RETURN d.ha_entity_id as eid, c.ha_service_key as svc
                """, arch=device_id))
            else:
                return {"status": "ambiguous", "message": "Slot insufficienti.", "calls": []}

        if not rows:
            return {"status": "not_found", "message": "Nessun device trovato.", "calls": []}

        if len(rows) > 1:
            return {
                "status": "ambiguous",
                "message": f"Trovati {len(rows)} dispositivi. Specifica la stanza.",
                "calls": []
            }

        row = rows[0]
        parts = row["svc"].split(".")
        service = f"{parts[0]}.{parts[1]}"
        return {
            "status": "ok",
            "calls": [{"entity_id": row["eid"], "service": service, "service_data": {}}]
        }
    finally:
        driver.close()