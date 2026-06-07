"""
import_graph.py
Importa vicky_structure.json nel grafo Neo4j.
Eseguire una volta sola al primo avvio.
"""
import os
from neo4j import GraphDatabase
from io_manager import import_json

class Neo4jManager:
    def __init__(self):
        uri      = os.getenv("NEO4J_URI",      "bolt://neo4j:7687")
        user     = os.getenv("NEO4J_USER",     "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "chaospassword")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def save_area(self, area_id: str):
        with self.driver.session() as s:
            s.run("MERGE (a:Area {id: $id, name: $id})", id=area_id)

    def move_area(self, child_id: str, parent_id: str):
        with self.driver.session() as s:
            s.run("""
                MATCH (p:Area {id: $pid}), (c:Area {id: $cid})
                MERGE (p)-[:CONTAINS]->(c)
            """, pid=parent_id, cid=child_id)

    def save_device(self, device_id: str, archetype: str):
        with self.driver.session() as s:
            s.run("""
                MERGE (d:Device {id: $id})
                SET d.name = $id, d.archetype = $arch
                WITH d
                MATCH (a:Archetype {id: $arch})
                MERGE (d)-[:INSTANCE_OF]->(a)
            """, id=device_id, arch=archetype)

    def move_device(self, device_id: str, area_id: str):
        with self.driver.session() as s:
            s.run("""
                MATCH (d:Device {id: $did}), (a:Area {id: $aid})
                MERGE (d)-[:BELONGS]->(a)
            """, did=device_id, aid=area_id)

    def set_ha_entity_id(self, device_id: str, entity_id: str):
        with self.driver.session() as s:
            s.run("MATCH (d:Device {id: $id}) SET d.ha_entity_id = $eid",
                  id=device_id, eid=entity_id)

    def add_alias(self, node_id: str, value: str, alias_type: str):
        with self.driver.session() as s:
            s.run("""
                MATCH (n {id: $nid})
                MERGE (a:Alias {value: $val, type: $type, owner: $nid})
                MERGE (n)-[:HAS_ALIAS]->(a)
            """, nid=node_id, val=value, type=alias_type)

    def get_aliases(self, node_id: str) -> list:
        with self.driver.session() as s:
            rows = s.run("""
                MATCH (n {id: $nid})-[:HAS_ALIAS]->(a:Alias)
                RETURN a.value as v
            """, nid=node_id)
            return [r["v"] for r in rows]

if __name__ == "__main__":
    print("Connessione a Neo4j...")
    db = Neo4jManager()

    print("Importazione archetipi...")
    with db.driver.session() as s:
        archetypes = [
            {"id": "luce_semplice",    "label": "Luce semplice",    "category": "illuminazione", "default_command": "toggle"},
            {"id": "luce_rgb",         "label": "Luce RGB",         "category": "illuminazione", "default_command": "toggle",  "default_item": "ALL"},
            {"id": "tapparella",       "label": "Tapparella",       "category": "coperture",     "default_command": "apri"},
            {"id": "termostato",       "label": "Termostato",       "category": "clima",         "default_command": "imposta_temperatura", "default_item": "ALL"},
            {"id": "condizionatore",   "label": "Condizionatore",   "category": "clima",         "default_command": "imposta_temperatura"},
            {"id": "sensore_movimento","label": "Sensore movimento", "category": "sicurezza"},
        ]
        for a in archetypes:
            s.run("MERGE (n:Archetype {id: $id}) SET n += $props",
                  id=a["id"], props=a)

    print("Importazione comandi...")
    with db.driver.session() as s:
        commands = [
            {"id": "toggle",                   "label": "Toggle",                    "ha_service_key": "light.toggle"},
            {"id": "accendi",                  "label": "Accendi",                   "ha_service_key": "climate.turn_on"},
            {"id": "spegni",                   "label": "Spegni",                    "ha_service_key": "climate.turn_off"},
            {"id": "apri",                     "label": "Apri",                      "ha_service_key": "cover.open_cover"},
            {"id": "chiudi",                   "label": "Chiudi",                    "ha_service_key": "cover.close_cover"},
            {"id": "stop",                     "label": "Stop",                      "ha_service_key": "cover.stop_cover"},
            {"id": "imposta_temperatura",      "label": "Imposta temperatura",       "ha_service_key": "climate.set_temperature"},
            {"id": "imposta_modalita",         "label": "Imposta modalità",          "ha_service_key": "climate.set_hvac_mode"},
            {"id": "imposta_luminosita",       "label": "Imposta luminosità",        "ha_service_key": "light.turn_on.brightness"},
            {"id": "imposta_colore",           "label": "Imposta colore",            "ha_service_key": "light.turn_on.rgb_color"},
            {"id": "imposta_temperatura_colore","label": "Imposta temperatura colore","ha_service_key": "light.turn_on.color_temp"},
            {"id": "imposta_posizione",        "label": "Imposta posizione",         "ha_service_key": "cover.set_cover_position"},
            {"id": "imposta_fan_speed",        "label": "Imposta velocità ventola",  "ha_service_key": "climate.set_fan_mode"},
            {"id": "imposta_swing",            "label": "Imposta orientamento",      "ha_service_key": "climate.set_swing_mode"},
        ]
        for c in commands:
            s.run("MERGE (n:Command {id: $id}) SET n += $props",
                  id=c["id"], props=c)

    print("Importazione struttura da vicky_structure.json...")
    report = import_json(db, "vicky_structure.json")
    print(report.summary())

    print("Importazione alias archetipi...")
    archetype_aliases = [
        ("luce_semplice",    ["luce", "lampada", "punto luce"]),
        ("luce_rgb",         ["luce", "lampada", "luce colorata", "rgb"]),
        ("tapparella",       ["tapparella", "veneziana", "persiana"]),
        ("termostato",       ["termostato", "riscaldamento", "temperatura"]),
        ("condizionatore",   ["condizionatore", "clima", "ventilazione"]),
        ("sensore_movimento",["sensore movimento", "pir", "rilevatore"]),
    ]
    for arch_id, aliases in archetype_aliases:
        for alias in aliases:
            db.add_alias(arch_id, alias, "archetype")

    print("Importazione alias comandi...")
    command_aliases = [
        ("toggle",              ["accendi", "spegni", "toggla"]),
        ("accendi",             ["accendi", "attiva", "metti su", "apri"]),
        ("spegni",              ["spegni", "disattiva", "metti giù", "spegni"]),
        ("apri",                ["apri", "alza", "solleva"]),
        ("chiudi",              ["chiudi", "abbassa", "chiudi"]),
        ("imposta_temperatura", ["imposta temperatura", "metti", "porta a", "imposta"]),
        ("imposta_luminosita",  ["imposta luminosità", "dimmer", "luminosità"]),
        ("imposta_colore",      ["imposta colore", "colore", "cambia colore"]),
    ]
    for cmd_id, aliases in command_aliases:
        for alias in aliases:
            db.add_alias(cmd_id, alias, "command")

    db.close()
    print("\nImportazione completata.")