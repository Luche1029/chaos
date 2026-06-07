import requests
import time

def call_local_router(query, ollama_base_url, ollama_model_name):
    start = time.time()
    payload = {
        "model": ollama_model_name,
        "prompt": f"Classifica in una parola (DOMOTICA o GENERALE): {query}",
        "stream": False,
        "keep_alive": -1,
        "options": {"temperature": 0}
    }
    try:
        res = requests.post(f"{ollama_base_url}/api/generate", json=payload, timeout=10)
        res.raise_for_status()
        
        latency = (time.time() - start) * 1000
        ans = res.json().get('response', '').strip().upper()
        decision = "DOMOTICA" if "DOMOTICA" in ans else "GENERALE"
        return decision, latency
    except Exception as e:
        # Questo ci dirà esattamente cosa non va (es. ConnectionError o 404)
        print(f"DEBUG Errore Locale su '{query}': {e}")
        return "ERROR", 0

