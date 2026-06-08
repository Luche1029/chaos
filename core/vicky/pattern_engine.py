"""
pattern_engine.py
Analizza i dati storici in InfluxDB e genera regole di abitudine.
Due categorie:
  - Eventi: correlazioni condizione → azione
  - Abitudini: pattern temporali ricorrenti
"""

from __future__ import annotations
import os
import json
from datetime import datetime, timezone
from collections import defaultdict
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS


class PatternEngine:

    def __init__(self,
                 influx_url: str, influx_token: str,
                 influx_org: str,
                 source_bucket: str = "casa",
                 rules_bucket:  str = "vicky_rules"):

        self.client      = InfluxDBClient(url=influx_url, token=influx_token, org=influx_org)
        self.query_api   = self.client.query_api()
        self.write_api   = self.client.write_api(write_options=SYNCHRONOUS)
        self.org         = influx_org
        self.src_bucket  = source_bucket
        self.rules_bucket= rules_bucket

    # ── Entry point ────────────────────────────────────────────────────────────
    def analyze(self, days: int = 7) -> dict:
        """
        Analizza gli ultimi N giorni di dati e genera regole.
        Restituisce un dict con le regole trovate.
        """
        print(f"[Pattern] Analisi ultimi {days} giorni...")

        events = self._load_events(days)
        print(f"[Pattern] Eventi caricati: {len(events)}")

        if not events:
            return {"status": "no_data", "rules": []}

        habits  = self._find_habits(events)
        correlations = self._find_correlations(events)

        all_rules = habits + correlations
        print(f"[Pattern] Regole trovate: {len(all_rules)} "
              f"({len(habits)} abitudini, {len(correlations)} eventi)")

        # Salva le regole in InfluxDB
        saved = self._save_rules(all_rules)
        print(f"[Pattern] Regole salvate: {saved}")

        return {
            "status":       "ok",
            "analyzed_days": days,
            "total_events": len(events),
            "rules": all_rules,
            "summary": {
                "habits":       len(habits),
                "correlations": len(correlations),
                "saved":        saved
            }
        }

    # ── Carica eventi da InfluxDB ──────────────────────────────────────────────
    def _load_events(self, days: int) -> list[dict]:
        query = f'''
        from(bucket: "{self.src_bucket}")
        |> range(start: -{days}d)
        |> filter(fn: (r) => r._measurement == "casa_virtuale")
        |> filter(fn: (r) => r._field == "state" or r._field == "measurement")
        '''
        try:
            tables = self.query_api.query(query, org=self.org)
            events = []
            for table in tables:
                for record in table.records:
                    dt = record.get_time()
                    events.append({
                        "time":    dt,
                        "hour":    dt.hour,
                        "weekday": dt.weekday(),
                        "device":  record.values.get("device", ""),
                        "area":    record.values.get("area", ""),
                        "scene":   record.values.get("scene", ""),
                        "state":   str(record.get_value() or ""),
                        "domain":  record.values.get("domain", ""),
                    })
            return events
        except Exception as e:
            print(f"[Pattern] Errore lettura InfluxDB: {e}")
            return []

    # ── Trova abitudini temporali ──────────────────────────────────────────────
    def _find_habits(self, events: list[dict],
                     min_occurrences: int = 2) -> list[dict]:
        """
        Trova pattern temporali ricorrenti.
        Un'abitudine è: stesso device + stesso stato + stessa fascia oraria
        che si ripete almeno min_occurrences volte.
        """
        # Raggruppa per device + state + fascia oraria (arrotondata a 30min)
        buckets: dict[str, list] = defaultdict(list)

        for e in events:
            hour_slot = (e["hour"] // 1) * 1  # slot di 1 ora
            key = f"{e['device']}|{e['state']}|{hour_slot}|{e['weekday']}"
            buckets[key].append(e)

        habits = []
        for key, occurrences in buckets.items():
            if len(occurrences) < min_occurrences:
                continue

            parts    = key.split("|")
            device   = parts[0]
            state    = parts[1]
            hour     = int(parts[2])
            weekday  = int(parts[3])

            # Calcola confidenza
            confidence = min(1.0, len(occurrences) / 7)

            # Mappa weekday a nome
            days_map = {0:"lun", 1:"mar", 2:"mer", 3:"gio",
                        4:"ven", 5:"sab", 6:"dom"}

            habits.append({
                "id":           f"habit_{device.replace('.','_')}_{state}_{hour}h_{weekday}",
                "tipo":         "abitudine",
                "trigger":      f"orario:{hour:02d}:00, giorno:{days_map[weekday]}",
                "azione": f"{'on' if state in ('on','morning','evening') else 'off'} {device}",
                "device":       device,
                "stato":        state,
                "ora":          hour,
                "giorno":       days_map[weekday],
                "confidenza":   round(confidence, 2),
                "osservazioni": len(occurrences),
                "attiva":       confidence >= 0.5,
                "generata_il":  datetime.now(timezone.utc).isoformat(),
            })

        # Ordina per confidenza
        return sorted(habits, key=lambda x: x["confidenza"], reverse=True)

    # ── Trova correlazioni evento → azione ────────────────────────────────────
    def _find_correlations(self, events: list[dict],
                           min_occurrences: int = 2) -> list[dict]:
        """
        Trova correlazioni tra scene e stati dispositivi.
        Una correlazione è: scena X → device Y sempre in stato Z.
        """
        # Raggruppa per scena + device + state
        buckets: dict[str, int] = defaultdict(int)
        scene_counts: dict[str, int] = defaultdict(int)

        for e in events:
            if e["scene"]:
                scene_counts[e["scene"]] += 1
                key = f"{e['scene']}|{e['device']}|{e['state']}"
                buckets[key] += 1

        correlations = []
        for key, count in buckets.items():
            if count < min_occurrences:
                continue

            parts  = key.split("|")
            scene  = parts[0]
            device = parts[1]
            state  = parts[2]

            total_scene = scene_counts.get(scene, 1)
            confidence  = min(1.0, count / max(total_scene, 1))

            if confidence < 0.3:
                continue

            correlations.append({
                "id":           f"event_{scene}_{device.replace('.','_')}_{state}",
                "tipo":         "evento",
                "trigger":      f"scena:{scene}",
                "azione":       f"{state} {device}",
                "device":       device,
                "stato":        state,
                "scena":        scene,
                "confidenza":   round(confidence, 2),
                "osservazioni": count,
                "attiva":       confidence >= 0.5,
                "generata_il":  datetime.now(timezone.utc).isoformat(),
            })

        return sorted(correlations, key=lambda x: x["confidenza"], reverse=True)

    # ── Salva regole in InfluxDB ───────────────────────────────────────────────
    def _save_rules(self, rules: list[dict]) -> int:
        """Salva le regole nel bucket vicky_rules."""
        saved = 0
        for rule in rules:
            try:
                point = (
                    Point("vicky_rules")
                    .tag("tipo",    rule["tipo"])
                    .tag("device",  rule["device"])
                    .tag("attiva",  str(rule["attiva"]))
                    .field("rule_id",      rule["id"])
                    .field("trigger",      rule["trigger"])
                    .field("azione",       rule["azione"])
                    .field("confidenza",   rule["confidenza"])
                    .field("osservazioni", rule["osservazioni"])
                    .field("rule_json",    json.dumps(rule, ensure_ascii=False))
                )
                self.write_api.write(
                    bucket=self.rules_bucket,
                    org=self.org,
                    record=point
                )
                saved += 1
            except Exception as e:
                print(f"[Pattern] Errore salvataggio regola {rule['id']}: {e}")
        return saved

    def close(self):
        self.client.close()


# ── CLI per test standalone ────────────────────────────────────────────────────
if __name__ == "__main__":
    engine = PatternEngine(
        influx_url=os.getenv("INFLUXDB_URL",   "http://influxdb:8086"),
        influx_token=os.getenv("INFLUXDB_TOKEN", ""),
        influx_org=os.getenv("INFLUXDB_ORG",   "chaos"),
        source_bucket="casa",
        rules_bucket="vicky_rules"
    )
    result = engine.analyze(days=7)
    print(f"\nStatus: {result['status']}")
    print(f"Regole trovate: {len(result['rules'])}")
    for r in result['rules'][:10]:
        print(f"  [{r['tipo']:10}] conf={r['confidenza']:.2f} | {r['trigger']} → {r['azione']}")
    engine.close()