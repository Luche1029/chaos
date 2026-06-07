import os
import requests
import json

# --- CONFIGURAZIONE ---
# Sostituisci con i tuoi URL reali di n8n
WEBHOOK_INFERENCE = f"{os.getenv('N8N_BASE_URL')}{os.getenv('WEBHOOK_INFERENCE')}"
WEBHOOK_FEEDBACK = f"{os.getenv('N8N_BASE_URL')}{os.getenv('WEBHOOK_FEEDBACK')}"

def test_query(query):
    try:
        # 1. Chiamata al motore di Inferenza
        response = requests.get(WEBHOOK_INFERENCE, params={'q': query})
        response.raise_for_status()
        data = response.json()
        
        print(f"\n--- RISULTATO ---")
        print(f"Query: {query}")
        print(f"Predizione: {data.get('prediction')}")
        print(f"Confidenza: {data.get('confidence')}")
        print(f"Score Finale: {data.get('result_data', {}).get('final_score')}")
        
        return data.get('prediction')
    
    except Exception as e:
        print(f"Errore durante l'inferenza: {e}")
        return None

def send_feedback(query, correct_category):
    try:
        # 2. Invio della correzione al motore di Feedback
        payload = {
            "query": query,
            "correct_category": correct_category
        }
        response = requests.post(WEBHOOK_FEEDBACK, json=payload)
        response.raise_for_status()
        
        print(f"✅ Sistema aggiornato! La parola ora è associata a: {correct_category}")
        
    except Exception as e:
        print(f"Errore durante l'invio del feedback: {e}")

def main():
    print("🤖 AI Router Console - Operativa")
    print("Digita 'exit' per uscire.")
    
    while True:
        query = input("\nInserisci una query: ").strip()
        
        if query.lower() == 'exit':
            break
        
        if not query:
            continue
            
        # Esegui test
        prediction = test_query(query)
        
        if prediction:
            # Chiedi feedback all'utente
            feedback = input("La classificazione è corretta? (s/n): ").lower()
            
            if feedback == 'n':
                print("1. DOMOTICA")
                print("2. GENERALE")
                scelta = input("Qual è la categoria corretta? (1 o 2): ")
                
                correct_cat = "DOMOTICA" if scelta == '1' else "GENERALE"
                send_feedback(query, correct_cat)
            else:
                print("Ottimo! Il modello sta imparando bene.")

if __name__ == "__main__":
    main()