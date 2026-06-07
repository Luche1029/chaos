"""
query_engine.py
Risolve slot NLP in service call Home Assistant tramite query Cypher.

Uso:
    from query_engine import QueryEngine
    engine = QueryEngine(db)  # db = Neo4jManager
    result = engine.resolve(area="soggiorno", device="luce", command="accendi")
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vicky_world_builder import Neo4jManager


# ══════════════════════════════════════════════════════════════════════════════
# Strutture dati risultato
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ServiceCall:
    """Un singolo service call HA pronto all'esecuzione."""
    entity_id:    str
    service:      str                    # es. "light.turn_on"
    service_data: dict = field(default_factory=dict)
    device_id:    str  = ""
    area_id:      str  = ""
    command_id:   str  = ""

    def to_dict(self) -> dict:
        return {
            "entity_id":    self.entity_id,
            "service":      self.service,
            "service_data": self.service_data,
            "device_id":    self.device_id,
            "area_id":      self.area_id,
            "command_id":   self.command_id,
        }


@dataclass
class QueryResult:
    """Risultato completo della risoluzione slot."""
    status:   str           # "ok" | "ambiguous" | "not_found" | "error"
    results:  list[ServiceCall] = field(default_factory=list)
    message:  str = ""
    candidates: list[dict] = field(default_factory=list)  # per ambiguous

    def to_dict(self) -> dict:
        return {
            "status":     self.status,
            "results":    [r.to_dict() for r in self.results],
            "message":    self.message,
            "candidates": self.candidates,
        }


# ══════════════════════════════════════════════════════════════════════════════
# Query Engine
# ══════════════════════════════════════════════════════════════════════════════

class QueryEngine:

    def __init__(self, db: "Neo4jManager"):
        self.db = db

    # ── Entry point principale ─────────────────────────────────────────────────
    def resolve(self,
                area:    str | None = None,
                device:  str | None = None,
                command: str | None = None,
                params:  dict | None = None) -> QueryResult:
        """
        Risolve slot NLP in una lista di ServiceCall.

        Tutti gli slot sono alias (stringhe in linguaggio naturale).
        params: valori opzionali per i comandi con parametri
                es. {"temperature": 21.0} per imposta_temperatura
        """
        params = params or {}

        # Normalizza
        area    = area.strip().lower()    if area    else None
        device  = device.strip().lower()  if device  else None
        command = command.strip().lower() if command else None

        # ── Caso 1: area + device + comando (completo) ─────────────────────
        if area and device and command:
            return self._resolve_full(area, device, command, params)

        # ── Caso 2: device + comando, senza area ──────────────────────────
        if device and command and not area:
            return self._resolve_no_area(device, command, params)

        # ── Caso 3: area + device, senza comando (usa default_command) ────
        if area and device and not command:
            return self._resolve_default_command(area, device, params)

        # ── Caso 4: area + comando, senza device ──────────────────────────
        if area and command and not device:
            return QueryResult(
                status="ambiguous",
                message=f"Non so a quale dispositivo applicare '{command}' "
                        f"in '{area}'. Specifica il tipo di dispositivo.")

        # ── Caso 5: solo device (usa default_command + default_item) ──────
        if device and not area and not command:
            return self._resolve_device_only(device, params)

        # ── Caso 6: tutto mancante o solo area ────────────────────────────
        return QueryResult(
            status="ambiguous",
            message="Slot insufficienti per risolvere il comando. "
                    "Specifica almeno dispositivo e comando.")

    # ── Caso 1: completo ───────────────────────────────────────────────────────
    def _resolve_full(self, area: str, device: str,
                      command: str, params: dict) -> QueryResult:
        with self.db.driver.session() as s:
            # Cerca prima tramite alias area + alias device (via Archetype) + alias comando
            rows = list(s.run("""
                MATCH (a:Area)-[:HAS_ALIAS]->(aa:Alias {value: $area})
                MATCH (d:Device)-[:BELONGS]->(a)
                MATCH (d)-[:INSTANCE_OF]->(:Archetype)-[:HAS_ALIAS]->(da:Alias {value: $device})
                MATCH (d)-[:HAS_COMMAND]->(c:Command)
                MATCH (c)-[:HAS_ALIAS]->(ca:Alias {value: $command})
                RETURN d.id as did, d.ha_entity_id as eid,
                       a.id as aid, c.id as cid, c.ha_service_key as svc
            """, area=area, device=device, command=command))

            # Fallback: cerca anche alias custom sull'istanza device
            if not rows:
                rows = list(s.run("""
                    MATCH (a:Area)-[:HAS_ALIAS]->(aa:Alias {value: $area})
                    MATCH (d:Device)-[:BELONGS]->(a)
                    MATCH (d)-[:HAS_ALIAS]->(da:Alias {value: $device})
                    MATCH (d)-[:HAS_COMMAND]->(c:Command)
                    MATCH (c)-[:HAS_ALIAS]->(ca:Alias {value: $command})
                    RETURN d.id as did, d.ha_entity_id as eid,
                           a.id as aid, c.id as cid, c.ha_service_key as svc
                """, area=area, device=device, command=command))

        if not rows:
            return QueryResult(
                status="not_found",
                message=f"Nessun dispositivo trovato per "
                        f"area='{area}', device='{device}', command='{command}'.")

        calls = [self._make_call(r, params) for r in rows if r["eid"]]
        missing_eid = [r["did"] for r in rows if not r["eid"]]

        if not calls:
            return QueryResult(
                status="error",
                message=f"Dispositivi trovati ma senza ha_entity_id: "
                        f"{missing_eid}")

        msg = ""
        if missing_eid:
            msg = f"⚠ Alcuni device senza entity_id ignorati: {missing_eid}"

        return QueryResult(status="ok", results=calls, message=msg)

    # ── Caso 2: device + comando, senza area ──────────────────────────────────
    def _resolve_no_area(self, device: str, command: str,
                         params: dict) -> QueryResult:
        with self.db.driver.session() as s:
            # Trova l'archetipo corrispondente all'alias device
            arch_rows = list(s.run("""
                MATCH (arch:Archetype)-[:HAS_ALIAS]->(da:Alias {value: $device})
                RETURN arch.id as arch_id,
                       arch.default_item as default_item
            """, device=device))

        if not arch_rows:
            return QueryResult(
                status="not_found",
                message=f"Nessun archetipo trovato per device='{device}'.")

        arch_id      = arch_rows[0]["arch_id"]
        default_item = arch_rows[0]["default_item"]

        # Risolvi quali device usare in base a default_item
        if default_item and default_item != "ALL":
            # ID specifico — usa solo quel device
            target_devices = [default_item]
        elif default_item == "ALL":
            # Tutti i device di quell'archetipo
            with self.db.driver.session() as s:
                target_devices = [r["did"] for r in s.run("""
                    MATCH (d:Device)-[:INSTANCE_OF]->(:Archetype {id: $arch})
                    RETURN d.id as did
                """, arch=arch_id)]
        else:
            # Ambiguo — restituisci i candidati
            with self.db.driver.session() as s:
                candidates = [{"id": r["did"], "area": r["area"]} for r in s.run("""
                    MATCH (d:Device)-[:INSTANCE_OF]->(:Archetype {id: $arch})
                    OPTIONAL MATCH (d)-[:BELONGS]->(a:Area)
                    RETURN d.id as did, a.id as area
                """, arch=arch_id)]
            return QueryResult(
                status="ambiguous",
                message=f"Più dispositivi di tipo '{device}' trovati. "
                        f"Specifica l'area o imposta un default_item sull'archetipo.",
                candidates=candidates)

        return self._resolve_devices_command(target_devices, command, params)

    # ── Caso 3: area + device, senza comando (default_command) ────────────────
    def _resolve_default_command(self, area: str, device: str,
                                 params: dict) -> QueryResult:
        with self.db.driver.session() as s:
            arch_rows = list(s.run("""
                MATCH (arch:Archetype)-[:HAS_ALIAS]->(da:Alias {value: $device})
                RETURN arch.id as arch_id, arch.default_command as default_cmd
            """, device=device))

        if not arch_rows:
            return QueryResult(
                status="not_found",
                message=f"Nessun archetipo trovato per device='{device}'.")

        default_cmd = arch_rows[0]["default_cmd"]
        if not default_cmd:
            return QueryResult(
                status="ambiguous",
                message=f"Nessun comando di default per '{device}'. "
                        f"Specifica il comando.")

        # Ora risolvi come caso completo usando il comando di default
        return self._resolve_full(area, device, default_cmd, params)

    # ── Caso 5: solo device ────────────────────────────────────────────────────
    def _resolve_device_only(self, device: str, params: dict) -> QueryResult:
        with self.db.driver.session() as s:
            arch_rows = list(s.run("""
                MATCH (arch:Archetype)-[:HAS_ALIAS]->(da:Alias {value: $device})
                RETURN arch.id as arch_id,
                       arch.default_item as default_item,
                       arch.default_command as default_cmd
            """, device=device))

        if not arch_rows:
            return QueryResult(
                status="not_found",
                message=f"Nessun archetipo trovato per device='{device}'.")

        default_cmd  = arch_rows[0]["default_cmd"]
        default_item = arch_rows[0]["default_item"]

        if not default_cmd:
            return QueryResult(
                status="ambiguous",
                message=f"Nessun comando di default per '{device}'. "
                        f"Specifica il comando.")

        # Risolvi il comando di default
        return self._resolve_no_area(device, default_cmd, params)

    # ── Helper: esegui comando su lista di device id ───────────────────────────
    def _resolve_devices_command(self, device_ids: list[str],
                                 command: str, params: dict) -> QueryResult:
        if not device_ids:
            return QueryResult(status="not_found",
                               message="Nessun device da comandare.")

        calls = []
        missing = []
        not_found_cmd = []

        for did in device_ids:
            with self.db.driver.session() as s:
                rows = list(s.run("""
                    MATCH (d:Device {id: $did})-[:HAS_COMMAND]->(c:Command)
                    MATCH (c)-[:HAS_ALIAS]->(ca:Alias {value: $command})
                    OPTIONAL MATCH (d)-[:BELONGS]->(a:Area)
                    RETURN d.ha_entity_id as eid, a.id as aid,
                           c.id as cid, c.ha_service_key as svc
                """, did=did, command=command))

            if not rows:
                not_found_cmd.append(did)
                continue

            for r in rows:
                if r["eid"]:
                    calls.append(ServiceCall(
                        entity_id=r["eid"],
                        service=self._parse_service(r["svc"]),
                        service_data=self._build_service_data(r["svc"], params),
                        device_id=did,
                        area_id=r["aid"] or "",
                        command_id=r["cid"],
                    ))
                else:
                    missing.append(did)

        if not calls:
            msgs = []
            if not_found_cmd:
                msgs.append(f"Comando '{command}' non trovato su: {not_found_cmd}")
            if missing:
                msgs.append(f"Entity id mancante su: {missing}")
            return QueryResult(status="not_found", message=" | ".join(msgs))

        msg_parts = []
        if not_found_cmd:
            msg_parts.append(f"⚠ Comando non trovato su: {not_found_cmd}")
        if missing:
            msg_parts.append(f"⚠ Entity id mancante su: {missing}")

        return QueryResult(status="ok", results=calls,
                           message=" | ".join(msg_parts))

    # ── Helper: costruisce ServiceCall da una row Cypher ──────────────────────
    def _make_call(self, row, params: dict) -> ServiceCall:
        svc_key = row["svc"]
        return ServiceCall(
            entity_id=row["eid"],
            service=self._parse_service(svc_key),
            service_data=self._build_service_data(svc_key, params),
            device_id=row["did"],
            area_id=row["aid"] or "",
            command_id=row["cid"],
        )

    @staticmethod
    def _parse_service(ha_service_key: str) -> str:
        """
        Estrae domain.service da ha_service_key.
        es. "light.turn_on.brightness" -> "light.turn_on"
            "light.turn_on"            -> "light.turn_on"
        """
        parts = ha_service_key.split(".")
        return f"{parts[0]}.{parts[1]}"

    @staticmethod
    def _build_service_data(ha_service_key: str, params: dict) -> dict:
        """
        Costruisce service_data unendo i parametri forniti
        con eventuali chiavi implicite dal service key.
        es. "light.turn_on.brightness" con params={"brightness_pct":50}
            -> {"brightness_pct": 50}
        """
        if not params:
            return {}
        # Filtra solo i params forniti, il chiamante è responsabile
        # di passare le chiavi corrette per quel comando
        return dict(params)