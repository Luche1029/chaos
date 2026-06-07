import os
import requests
import csv
import time
from router_local import call_local_router

# CONFIGURAZIONE
N8N_PROD_URL = os.getenv('N8N_PROD_URL')
OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL')
OLLAMA_MODEL_NAME = os.getenv('OLLAMA_MODEL_NAME')
queries = [
    "Accendi la luce in corridoio",
    "Chi è il presidente della repubblica?",
    "Hanno suonato al citofono?",
    "Qual è la capitale della Francia?",
    "Imposta la temperatura a 22 gradi",
    "Raccontami una barzelletta"
]

results = []

print(f"🚀 Avvio Benchmark su {len(queries)} query...")

for q in queries:
    print(f"Testing: {q}")
    
    # 1. Test n8n (Latenza misurata internamente dal workflow)
    try:
        res_n8n = requests.post(N8N_PROD_URL, json={"query": q}, timeout=15)
        data_n8n = res_n8n.json()
        dec_n8n = data_n8n.get('decision', 'ERR')
        lat_n8n = data_n8n.get('latency_router_ms', 0)
    except:
        dec_n8n, lat_n8n = "TIMEOUT", 0

    # 2. Test Python Locale (Latenza misurata dallo script)
    dec_loc, lat_loc = call_local_router(q, OLLAMA_BASE_URL, OLLAMA_MODEL_NAME)

    results.append([q, dec_n8n, lat_n8n, dec_loc, round(lat_loc, 2)])
    time.sleep(0.5) # Pausa per non saturare la VRAM

# Salvataggio CSV
with open('risultati_benchmark.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(["Query", "n8n_Dec", "n8n_Lat_ms", "Local_Dec", "Local_Lat_ms"])
    writer.writerows(results)

print("\n✅ Benchmark completato! File 'risultati_benchmark.csv' generato.")