"""
generate_training_data.py
Genera training_data.csv combinando:
1. Frasi manuali (training_data_manual.csv)
2. Frasi generate da _common.yaml via CommonParser
"""

import csv
import random
from pathlib import Path
from itertools import product
from common_parser import CommonParser

OUTPUT_CSV = Path("training_data.csv")
MANUAL_CSV = Path("training_data_manual.csv")
COMMON_YAML = Path("_common.yaml")

# Struttura casa — aree e device
CASA = {
    "Cucina":    [("luce_semplice", "light"), ("termostato", "climate")],
    "Sala":      [("luce_rgb", "light"), ("tapparella", "cover"), ("termostato", "climate")],
    "Camera":    [("luce_rgb", "light"), ("termostato", "climate")],
    "Cameretta": [("luce_rgb", "light"), ("tapparella", "cover"), ("termostato", "climate")],
    "Bagno":     [("luce_semplice", "light"), ("tapparella", "cover"), ("condizionatore", "fan")],
    "Balcone":   [("luce_semplice", "light")],
    "Ingresso":  [("luce_semplice", "light")],
}

# Mapping domain → command_id
DOMAIN_TO_COMMANDS = {
    "light":   ["accendi", "spegni"],
    "cover":   ["apri", "chiudi"],
    "climate": ["accendi", "spegni", "imposta_temperatura"],
    "fan":     ["accendi", "spegni"],
}

def generate_from_yaml(parser: CommonParser) -> list[dict]:
    """Genera frasi da _common.yaml combinando termini espansi."""
    rows = []

    # Termini per ogni slot
    turn_on_terms  = parser.get_command_terms("turn_on")[:8]
    turn_off_terms = parser.get_command_terms("turn_off")[:8]
    open_terms     = parser.get_command_terms("open")[:5]
    close_terms    = parser.get_command_terms("close")[:5]
    light_terms    = parser.get_device_terms("light")[:6]
    cover_terms    = parser.get_device_terms("cover")[:4]
    climate_terms  = parser.get_device_terms("climate")[:4]

    prepositions = ["in", "del", "della", "nel", "nella", "in"]

    for area, devices in CASA.items():
        area_lower = area.lower()

        for archetype, domain in devices:
            # Seleziona termini giusti per dominio
            if domain == "light":
                device_terms = light_terms
                on_terms  = turn_on_terms
                off_terms = turn_off_terms
                on_cmd    = "accendi"
                off_cmd   = "spegni"
            elif domain == "cover":
                device_terms = cover_terms
                on_terms  = open_terms
                off_terms = close_terms
                on_cmd    = "apri"
                off_cmd   = "chiudi"
            elif domain in ("climate", "fan"):
                device_terms = climate_terms
                on_terms  = turn_on_terms
                off_terms = turn_off_terms
                on_cmd    = "accendi"
                off_cmd   = "spegni"
            else:
                continue

            # Genera frasi ON
            for cmd_term, dev_term, prep in product(
                on_terms[:4], device_terms[:3], prepositions[:2]
            ):
                frase = f"{cmd_term} {dev_term} {prep} {area_lower}"
                rows.append({
                    "frase":   frase,
                    "area":    area,
                    "device":  archetype,
                    "command": on_cmd
                })

            # Genera frasi OFF
            for cmd_term, dev_term, prep in product(
                off_terms[:4], device_terms[:3], prepositions[:2]
            ):
                frase = f"{cmd_term} {dev_term} {prep} {area_lower}"
                rows.append({
                    "frase":   frase,
                    "area":    area,
                    "device":  archetype,
                    "command": off_cmd
                })

    return rows

def load_manual(path: Path) -> list[dict]:
    """Carica frasi manuali dal CSV."""
    if not path.exists():
        return []
    return list(csv.DictReader(path.open(encoding="utf-8")))

def deduplicate(rows: list[dict]) -> list[dict]:
    """Rimuove frasi duplicate."""
    seen = set()
    result = []
    for row in rows:
        key = row["frase"].strip().lower()
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result

def main():
    print("Caricamento _common.yaml...")
    parser = CommonParser(COMMON_YAML).parse()

    print("Generazione frasi da YAML...")
    yaml_rows = generate_from_yaml(parser)
    print(f"  Generate: {len(yaml_rows)} frasi")

    print("Caricamento frasi manuali...")
    # Rinomina il CSV manuale esistente
    if Path("training_data.csv").exists() and not MANUAL_CSV.exists():
        import shutil
        shutil.copy("training_data.csv", MANUAL_CSV)
    manual_rows = load_manual(MANUAL_CSV)
    print(f"  Manuali: {len(manual_rows)} frasi")

    # Unisci e deduplica
    all_rows = manual_rows + yaml_rows
    all_rows = deduplicate(all_rows)
    random.shuffle(all_rows)

    # Salva
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["frase", "area", "device", "command"])
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\nCSV generato: {OUTPUT_CSV}")
    print(f"Totale frasi: {len(all_rows)}")
    print("\nEsempi:")
    for row in all_rows[:5]:
        print(f"  {row['frase'][:50]:50} | {row['area']:12} | {row['device']:15} | {row['command']}")

if __name__ == "__main__":
    main()