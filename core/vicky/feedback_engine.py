"""
feedback_engine.py
Gestisce il ciclo di feedback utente → aggiornamento grafo → rebuild indice.
Ogni correzione arricchisce il vocabolario di Vicky.
"""

from __future__ import annotations
import os
from datetime import datetime
from neo4j import GraphDatabase
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS


class FeedbackEngine:

    def __init__(self,
                 neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                 influx_url: str, influx_token: str,
                 influx_org: str, influx_bucket: str):

        self.driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        self.influx = InfluxDBClient(url=influx_url, token=influx_token, org=influx_org)
        self.write_api = self.influx.write_api(write_options=SYNCHRONOUS)
        self.influx_org = influx_org
        self.influx_bucket = influx_bucket

    def process(self,
                original_text: str,
                correct_area: str | None,
                correct_device: str | None,
                correct_command: str | None,
                session_id: str = "default") -> dict:
        """
        Processa un feedback utente.
        Aggiunge alias al grafo e registra l'evento su InfluxDB.
        """
        results = []

        # Normalizza il testo originale
        text = original_text.strip().lower()

        # Aggiungi alias area
        if correct_area:
            added = self._add_alias_if_new(correct_area, text, "area")
            if added:
                results.append(f"Alias area '{text}' → '{correct_area}'")

        # Aggiungi alias device (archetipo)
        if correct_device:
            added = self._add_alias_if_new(correct_device, text, "archetype")
            if added:
                results.append(f"Alias device '{text}' → '{correct_device}'")

        # Aggiungi alias command
        if correct_command:
            added = self._add_alias_if_new(correct_command, text, "command")
            if added:
                results.append(f"Alias command '{text}' → '{correct_command}'")

        # Registra su InfluxDB
        self._log_to_influx(
            original_text=original_text,
            correct_area=correct_area,
            correct_device=correct_device,
            correct_command=correct_command,
            session_id=session_id
        )

        return {
            "status": "ok",
            "aliases_added": results,
            "message": f"{len(results)} alias aggiornati. Ricostruisci l'indice per applicare le modifiche."
        }

    def _add_alias_if_new(self, node_id: str, alias_value: str, alias_type: str) -> bool:
        """Aggiunge un alias al nodo se non esiste già. Restituisce True se aggiunto."""
        with self.driver.session() as s:
            # Verifica se esiste già
            existing = list(s.run("""
                MATCH (n {id: $nid})-[:HAS_ALIAS]->(a:Alias {value: $val})
                RETURN a
            """, nid=node_id, val=alias_value))

            if existing:
                return False

            # Aggiunge il nuovo alias
            s.run("""
                MATCH (n {id: $nid})
                MERGE (a:Alias {value: $val, type: $type, owner: $nid})
                MERGE (n)-[:HAS_ALIAS]->(a)
            """, nid=node_id, val=alias_value, type=alias_type)
            return True

    def _log_to_influx(self, original_text: str,
                       correct_area: str | None,
                       correct_device: str | None,
                       correct_command: str | None,
                       session_id: str):
        """Registra il feedback su InfluxDB per tracciabilità e analisi."""
        try:
            point = (
                Point("vicky_feedback")
                .tag("session_id", session_id)
                .tag("area", correct_area or "unknown")
                .tag("device", correct_device or "unknown")
                .tag("command", correct_command or "unknown")
                .field("original_text", original_text)
                .field("timestamp", datetime.utcnow().isoformat())
            )
            self.write_api.write(bucket=self.influx_bucket, org=self.influx_org, record=point)
        except Exception as e:
            print(f"[Feedback] Errore InfluxDB: {e}")

    def close(self):
        self.driver.close()
        self.influx.close()