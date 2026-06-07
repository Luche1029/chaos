"""
io_manager.py
Export e import della struttura domotica in/da JSON.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from archetypes import ARCHETYPES

if TYPE_CHECKING:
    from vicky_world_builder import Neo4jManager

FORMAT_VERSION = "1.0"


# ══════════════════════════════════════════════════════════════════════════════
# Export
# ══════════════════════════════════════════════════════════════════════════════

def export_json(db: "Neo4jManager", path: str | Path, description: str = "") -> dict:
    """
    Legge il grafo e scrive il JSON sul path indicato.
    Restituisce il dict esportato (utile per test).
    """
    path = Path(path)

    with db.driver.session() as s:
        # ── Tutti i nodi Area e Device ────────────────────────────────────────
        all_areas = {r["id"]: r for r in s.run(
            "MATCH (n:Area) RETURN n.id as id"
        )}
        all_devices = {r["id"]: {
            "archetype":   r["arch"],
            "ha_entity_id": r["eid"] or "",
        } for r in s.run(
            "MATCH (d:Device) RETURN d.id as id, d.archetype as arch, "
            "d.ha_entity_id as eid"
        )}

        # ── Relazioni CONTAINS tra aree ───────────────────────────────────────
        contains = {}      # parent_id -> [child_id]
        for r in s.run("MATCH (p:Area)-[:CONTAINS]->(c:Area) "
                        "RETURN p.id as p, c.id as c"):
            contains.setdefault(r["p"], []).append(r["c"])

        # ── Relazioni BELONGS device->area ────────────────────────────────────
        belongs = {}       # area_id -> [device_id]
        for r in s.run("MATCH (d:Device)-[:BELONGS]->(a:Area) "
                        "RETURN a.id as area, d.id as dev"):
            belongs.setdefault(r["area"], []).append(r["dev"])

        # ── Alias per ogni nodo (Area e Device istanza) ───────────────────────
        aliases_map: dict[str, list[str]] = {}
        for r in s.run(
            "MATCH (n)-[:HAS_ALIAS]->(a:Alias) "
            "WHERE n:Area OR n:Device "
            "RETURN n.id as nid, a.value as v ORDER BY v"
        ):
            aliases_map.setdefault(r["nid"], []).append(r["v"])

        # ── Alias comandi ─────────────────────────────────────────────────────
        commands_aliases: dict[str, list[str]] = {}
        for r in s.run(
            "MATCH (c:Command)-[:HAS_ALIAS]->(a:Alias) "
            "RETURN c.id as cid, a.value as v ORDER BY v"
        ):
            commands_aliases.setdefault(r["cid"], []).append(r["v"])

    # ── Costruzione albero aree ────────────────────────────────────────────────
    area_children = set()
    for children in contains.values():
        area_children.update(children)

    # Device che appartengono ad almeno un'area
    device_children = set()
    for devs in belongs.values():
        device_children.update(devs)

    def build_area(area_id: str) -> dict:
        return {
            "aliases":  aliases_map.get(area_id, []),
            "contains": {
                cid: build_area(cid)
                for cid in contains.get(area_id, [])
            },
            "devices": {
                did: {
                    "archetype":    all_devices[did]["archetype"],
                    "ha_entity_id": all_devices[did]["ha_entity_id"],
                    "aliases":      aliases_map.get(did, []),
                }
                for did in belongs.get(area_id, [])
                if did in all_devices
            },
        }

    root_areas = {aid for aid in all_areas if aid not in area_children}
    areas_dict = {aid: build_area(aid) for aid in sorted(root_areas)}

    unassigned = {
        did: {
            "archetype":    all_devices[did]["archetype"],
            "ha_entity_id": all_devices[did]["ha_entity_id"],
            "aliases":      aliases_map.get(did, []),
        }
        for did in sorted(all_devices)
        if did not in device_children
    }

    doc = {
        "metadata": {
            "version":     FORMAT_VERSION,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "description": description,
        },
        "areas":            areas_dict,
        "unassigned":       unassigned,
        "commands_aliases": commands_aliases,
    }

    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return doc


# ══════════════════════════════════════════════════════════════════════════════
# Validazione
# ══════════════════════════════════════════════════════════════════════════════

class ImportReport:
    def __init__(self):
        self.created:  list[str] = []
        self.skipped:  list[str] = []
        self.warnings: list[str] = []
        self.errors:   list[str] = []

    def ok(self, msg: str):  self.created.append(msg)
    def skip(self, msg: str): self.skipped.append(msg)
    def warn(self, msg: str): self.warnings.append(msg)
    def err(self, msg: str):  self.errors.append(msg)

    def summary(self) -> str:
        lines = []
        if self.created:
            lines.append(f"✓ Creati ({len(self.created)}):\n  " +
                         "\n  ".join(self.created))
        if self.skipped:
            lines.append(f"⏭ Saltati ({len(self.skipped)}):\n  " +
                         "\n  ".join(self.skipped))
        if self.warnings:
            lines.append(f"⚠ Warning ({len(self.warnings)}):\n  " +
                         "\n  ".join(self.warnings))
        if self.errors:
            lines.append(f"✗ Errori ({len(self.errors)}):\n  " +
                         "\n  ".join(self.errors))
        if not lines:
            lines.append("Nessuna modifica effettuata.")
        return "\n\n".join(lines)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


def _validate_device(dev_id: str, dev_data: dict, report: ImportReport) -> bool:
    """Valida un nodo device. Restituisce True se importabile."""
    if not isinstance(dev_data, dict):
        report.err(f"Device '{dev_id}': formato non valido"); return False
    arch = dev_data.get("archetype")
    if not arch:
        report.err(f"Device '{dev_id}': campo 'archetype' mancante"); return False
    if arch not in ARCHETYPES:
        report.err(f"Device '{dev_id}': archetipo '{arch}' non presente in archetypes.py")
        return False
    if not isinstance(dev_data.get("aliases", []), list):
        report.err(f"Device '{dev_id}': 'aliases' deve essere una lista"); return False
    if not dev_data.get("ha_entity_id"):
        report.warn(f"Device '{dev_id}': ha_entity_id vuoto")
    return True


def _validate_area(area_id: str, area_data: dict, report: ImportReport) -> bool:
    if not isinstance(area_data, dict):
        report.err(f"Area '{area_id}': formato non valido"); return False
    for field in ("aliases", "contains", "devices"):
        if field not in area_data:
            report.err(f"Area '{area_id}': campo '{field}' mancante"); return False
    if not isinstance(area_data["aliases"], list):
        report.err(f"Area '{area_id}': 'aliases' deve essere una lista"); return False
    return True


def validate_json(doc: dict) -> tuple[bool, list[str]]:
    """
    Validazione strutturale veloce.
    Restituisce (ok, lista_errori_bloccanti).
    """
    errors = []
    meta = doc.get("metadata", {})
    version = meta.get("version")
    if not version:
        errors.append("Campo 'metadata.version' mancante")
    elif version != FORMAT_VERSION:
        errors.append(f"Versione '{version}' non compatibile (attesa: {FORMAT_VERSION})")
    if "areas" not in doc:
        errors.append("Sezione 'areas' mancante")
    if "unassigned" not in doc:
        errors.append("Sezione 'unassigned' mancante")
    return (len(errors) == 0), errors


# ══════════════════════════════════════════════════════════════════════════════
# Import
# ══════════════════════════════════════════════════════════════════════════════

def import_json(db: "Neo4jManager", path: str | Path,
                on_conflict: str = "skip") -> ImportReport:
    """
    Legge il JSON e popola il grafo.

    on_conflict: 'skip' (default) = non sovrascrive nodi esistenti
                 'merge' = aggiorna ha_entity_id e alias dei nodi esistenti
    """
    path = Path(path)
    report = ImportReport()

    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        report.err(f"Impossibile leggere il file: {e}")
        return report

    ok, errors = validate_json(doc)
    if not ok:
        for e in errors:
            report.err(e)
        return report

    # Nodi già presenti nel grafo
    with db.driver.session() as s:
        existing_ids = {r["id"] for r in s.run(
            "MATCH (n) WHERE n:Area OR n:Device RETURN n.id as id"
        )}

    def _import_area(area_id: str, area_data: dict, parent_id: str | None = None):
        if not _validate_area(area_id, area_data, report):
            return

        if area_id in existing_ids:
            if on_conflict == "skip":
                report.skip(f"Area '{area_id}' già presente — saltata")
            else:
                # merge: aggiorna alias
                _sync_aliases(db, area_id, area_data.get("aliases", []), "area", report)
                report.ok(f"Area '{area_id}' aggiornata (merge)")
        else:
            try:
                db.save_area(area_id)
                if parent_id:
                    db.move_area(area_id, parent_id)
                _sync_aliases(db, area_id, area_data.get("aliases", []), "area", report)
                report.ok(f"Area '{area_id}'" + (f" in '{parent_id}'" if parent_id else ""))
                existing_ids.add(area_id)
            except Exception as e:
                report.err(f"Area '{area_id}': {e}")
                return

        # Sotto-aree ricorsive
        for sub_id, sub_data in area_data.get("contains", {}).items():
            _import_area(sub_id, sub_data, parent_id=area_id)

        # Device di questa area
        for dev_id, dev_data in area_data.get("devices", {}).items():
            _import_device(dev_id, dev_data, area_id=area_id)

    def _import_device(dev_id: str, dev_data: dict, area_id: str | None = None):
        if not _validate_device(dev_id, dev_data, report):
            return

        if dev_id in existing_ids:
            if on_conflict == "skip":
                report.skip(f"Device '{dev_id}' già presente — saltato")
            else:
                eid = dev_data.get("ha_entity_id", "")
                if eid:
                    db.set_ha_entity_id(dev_id, eid)
                _sync_aliases(db, dev_id, dev_data.get("aliases", []), "device", report)
                report.ok(f"Device '{dev_id}' aggiornato (merge)")
            return

        try:
            db.save_device(dev_id, dev_data["archetype"])
            eid = dev_data.get("ha_entity_id", "")
            if eid:
                db.set_ha_entity_id(dev_id, eid)
            if area_id:
                db.move_device(dev_id, area_id)
            _sync_aliases(db, dev_id, dev_data.get("aliases", []), "device", report)
            report.ok(f"Device '{dev_id}' [{dev_data['archetype']}]"
                      + (f" in '{area_id}'" if area_id else ""))
            existing_ids.add(dev_id)
        except Exception as e:
            report.err(f"Device '{dev_id}': {e}")

    # ── Aree root ─────────────────────────────────────────────────────────────
    for area_id, area_data in doc.get("areas", {}).items():
        _import_area(area_id, area_data, parent_id=None)

    # ── Device non assegnati ──────────────────────────────────────────────────
    for dev_id, dev_data in doc.get("unassigned", {}).items():
        _import_device(dev_id, dev_data, area_id=None)

    # ── Alias comandi ─────────────────────────────────────────────────────────
    for cmd_id, aliases in doc.get("commands_aliases", {}).items():
        for alias in aliases:
            try:
                db.add_alias(cmd_id, alias, "command")
            except Exception as e:
                report.warn(f"Alias comando '{alias}' su '{cmd_id}': {e}")

    return report


def _sync_aliases(db: "Neo4jManager", node_id: str, aliases: list[str],
                  alias_type: str, report: ImportReport):
    """Aggiunge gli alias mancanti sul nodo (non rimuove quelli esistenti)."""
    existing = set(db.get_aliases(node_id))
    for alias in aliases:
        alias = alias.strip().lower()
        if not alias:
            continue
        if alias in existing:
            continue
        try:
            db.add_alias(node_id, alias, alias_type)
        except Exception as e:
            report.warn(f"Alias '{alias}' su '{node_id}': {e}")