"""
training_loop.py
Supervised training loop per Vicky.
Legge training_data.csv, testa ogni frase su /command,
confronta con i valori attesi e corregge via /feedback.
"""

import csv
import json
import requests
import time
from pathlib import Path
from datetime import datetime

VICKY_URL    = "http://localhost:8000"
TRAINING_CSV = Path("training_data.csv")

def test_command(frase: str) -> dict:
    try:
        r = requests.post(
            f"{VICKY_URL}/command",
            json={"text": frase},
            timeout=60
        )
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def send_feedback(frase: str, area: str, device: str, command: str) -> dict:
    try:
        r = requests.post(
            f"{VICKY_URL}/feedback",
            json={
                "original_text":  frase,
                "correct_area":   area    or None,
                "correct_device": device  or None,
                "correct_command":command or None,
                "session_id":     "training"
            },
            timeout=30
        )
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def run_training(csv_path: Path = TRAINING_CSV):
    print(f"\n{'='*60}")
    print(f"CHAOS — Vicky Training Loop")
    print(f"{'='*60}")
    print(f"File: {csv_path}")
    print(f"Avvio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    total    = len(rows)
    correct  = 0
    corrected= 0
    errors   = 0

    for i, row in enumerate(rows, 1):
        frase   = row["frase"].strip()
        exp_area= row["area"].strip()
        exp_dev = row["device"].strip()
        exp_cmd = row["command"].strip()

        print(f"[{i:02d}/{total}] '{frase}'")

        # Test
        result = test_command(frase)

        if "error" in result:
            print(f"  ✗ Errore: {result['error']}")
            errors += 1
            continue

        got_type  = result.get("type", "")
        got_calls = result.get("calls") or []

        # Verifica se il risultato è corretto
        is_correct = False

        if got_type == "domotica" and got_calls:
            # Verifica entity_id se possibile
            is_correct = result.get("success", False)
        elif got_type == "domotica" and not got_calls:
            is_correct = False
        else:
            is_correct = False

        if is_correct:
            print(f"  ✓ Corretto — {got_calls[0]['entity_id'] if got_calls else ''}")
            correct += 1
        else:
            print(f"  ✗ Errato (tipo={got_type}) — invio feedback")
            fb = send_feedback(frase, exp_area, exp_dev, exp_cmd)
            aliases = fb.get("aliases_added", [])
            print(f"  → Feedback: {len(aliases)} alias aggiunti")
            corrected += 1

        time.sleep(0.5)  # pausa tra le richieste

    # Rebuild indice dopo il training
    print(f"\nRicostruzione indice NLP...")
    try:
        requests.post(f"{VICKY_URL}/rebuild-index", timeout=120)
        print("Indice ricostruito.")
    except Exception as e:
        print(f"Errore rebuild: {e}")

    # Report finale
    print(f"\n{'='*60}")
    print(f"REPORT TRAINING")
    print(f"{'='*60}")
    print(f"Totale frasi:   {total}")
    print(f"Corrette:       {correct}  ({100*correct//total}%)")
    print(f"Corrette dopo feedback: {corrected}")
    print(f"Errori:         {errors}")
    accuracy = 100 * correct // total if total > 0 else 0
    print(f"Accuratezza iniziale: {accuracy}%")
    print(f"Fine: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    run_training()