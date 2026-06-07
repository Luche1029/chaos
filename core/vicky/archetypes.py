ARCHETYPES = {

    # ── ILLUMINAZIONE ──────────────────────────────────────────────────────────
    "luce_semplice": {
        "label":           "Luce semplice",
        "category":        "illuminazione",
        "default_aliases": ["luce", "lampada", "punto luce"],
        "default_command": "toggle",
        "default_item":    None,
        "commands": {
            "accendi": {
                "label":          "Accendi",
                "ha_service_key": "light.turn_on",
                "params": []
            },
            "spegni": {
                "label":          "Spegni",
                "ha_service_key": "light.turn_off",
                "params": []
            },
            "toggle": {
                "label":          "Toggle",
                "ha_service_key": "light.toggle",
                "params": []
            },
        }
    },

    "luce_dimmer": {
        "label":           "Luce dimmerabile",
        "category":        "illuminazione",
        "inherits":        "luce_semplice",
        "default_aliases": ["luce", "lampada", "dimmer"],
        "default_command": "toggle",
        "default_item":    None,
        "commands": {
            "imposta_luminosita": {
                "label":          "Imposta luminosità",
                "ha_service_key": "light.turn_on.brightness",
                "params": [
                    {"id": "brightness_pct", "type": "int", "min": 0, "max": 100, "unit": "%"}
                ]
            },
        }
    },

    "luce_rgb": {
        "label":           "Luce RGB",
        "category":        "illuminazione",
        "inherits":        "luce_dimmer",
        "default_aliases": ["luce", "lampada", "luce colorata", "rgb"],
        "default_command": "toggle",
        "default_item":    None,
        "commands": {
            "imposta_colore": {
                "label":          "Imposta colore",
                "ha_service_key": "light.turn_on.rgb_color",
                "params": [
                    {"id": "r", "type": "int", "min": 0, "max": 255},
                    {"id": "g", "type": "int", "min": 0, "max": 255},
                    {"id": "b", "type": "int", "min": 0, "max": 255},
                ]
            },
            "imposta_temperatura_colore": {
                "label":          "Imposta temperatura colore",
                "ha_service_key": "light.turn_on.color_temp",
                "params": [
                    {"id": "color_temp_kelvin", "type": "int", "min": 2700, "max": 6500, "unit": "K"}
                ]
            },
        }
    },

    # ── COPERTURE ──────────────────────────────────────────────────────────────
    "tapparella": {
        "label":           "Tapparella",
        "category":        "coperture",
        "default_aliases": ["tapparella", "veneziana", "persiana"],
        "default_command": "apri",
        "default_item":    None,
        "commands": {
            "apri": {
                "label":          "Apri",
                "ha_service_key": "cover.open_cover",
                "params": []
            },
            "chiudi": {
                "label":          "Chiudi",
                "ha_service_key": "cover.close_cover",
                "params": []
            },
            "stop": {
                "label":          "Stop",
                "ha_service_key": "cover.stop_cover",
                "params": []
            },
            "imposta_posizione": {
                "label":          "Imposta posizione",
                "ha_service_key": "cover.set_cover_position",
                "params": [
                    {"id": "position", "type": "int", "min": 0, "max": 100, "unit": "%"}
                ]
            },
        }
    },

    "tenda_da_sole": {
        "label":           "Tenda da sole",
        "category":        "coperture",
        "inherits":        "tapparella",
        "default_aliases": ["tenda", "tenda da sole", "tendalino"],
        "default_command": "apri",
        "default_item":    None,
        "commands": {}
    },

    "vetro_oscurabile": {
        "label":           "Vetro oscurabile",
        "category":        "coperture",
        "inherits":        "tapparella",
        "default_aliases": ["vetro", "vetro elettrocromatico", "vetro oscurabile"],
        "default_command": "apri",
        "default_item":    None,
        "commands": {
            "imposta_opacita": {
                "label":          "Imposta opacità",
                "ha_service_key": "cover.set_cover_position",
                "params": [
                    {"id": "position", "type": "int", "min": 0, "max": 100, "unit": "%"}
                ]
            },
        }
    },

    # ── CLIMA ──────────────────────────────────────────────────────────────────
    "termostato": {
        "label":           "Termostato",
        "category":        "clima",
        "default_aliases": ["termostato", "riscaldamento", "temperatura"],
        "default_command": "imposta_temperatura",
        "default_item":    "ALL",
        "commands": {
            "accendi": {
                "label":          "Accendi",
                "ha_service_key": "climate.turn_on",
                "params": []
            },
            "spegni": {
                "label":          "Spegni",
                "ha_service_key": "climate.turn_off",
                "params": []
            },
            "imposta_temperatura": {
                "label":          "Imposta temperatura",
                "ha_service_key": "climate.set_temperature",
                "params": [
                    {"id": "temperature", "type": "float", "min": 10.0, "max": 35.0, "unit": "°C"}
                ]
            },
            "imposta_modalita": {
                "label":          "Imposta modalità",
                "ha_service_key": "climate.set_hvac_mode",
                "params": [
                    {"id": "hvac_mode", "type": "enum",
                     "values": ["heat", "cool", "auto", "off"]}
                ]
            },
        }
    },

    "condizionatore": {
        "label":           "Condizionatore",
        "category":        "clima",
        "inherits":        "termostato",
        "default_aliases": ["condizionatore", "climatizzatore", "aria condizionata", "split"],
        "default_command": "imposta_temperatura",
        "default_item":    None,
        "commands": {
            "imposta_fan_speed": {
                "label":          "Imposta velocità ventola",
                "ha_service_key": "climate.set_fan_mode",
                "params": [
                    {"id": "fan_mode", "type": "enum",
                     "values": ["auto", "low", "medium", "high"]}
                ]
            },
            "imposta_swing": {
                "label":          "Imposta orientamento",
                "ha_service_key": "climate.set_swing_mode",
                "params": [
                    {"id": "swing_mode", "type": "enum",
                     "values": ["off", "vertical", "horizontal", "both"]}
                ]
            },
        }
    },

    # ── PRESE E INTERRUTTORI ───────────────────────────────────────────────────
    "presa": {
        "label":           "Presa",
        "category":        "interruttori",
        "default_aliases": ["presa", "presa elettrica", "spina"],
        "default_command": "toggle",
        "default_item":    None,
        "commands": {
            "accendi": {
                "label":          "Accendi",
                "ha_service_key": "switch.turn_on",
                "params": []
            },
            "spegni": {
                "label":          "Spegni",
                "ha_service_key": "switch.turn_off",
                "params": []
            },
            "toggle": {
                "label":          "Toggle",
                "ha_service_key": "switch.toggle",
                "params": []
            },
        }
    },

    "interruttore": {
        "label":           "Interruttore",
        "category":        "interruttori",
        "inherits":        "presa",
        "default_aliases": ["interruttore", "switch"],
        "default_command": "toggle",
        "default_item":    None,
        "commands": {}
    },

    # ── SICUREZZA ──────────────────────────────────────────────────────────────
    "sensore_binario": {
        "label":           "Sensore binario",
        "category":        "sicurezza",
        "default_aliases": ["sensore"],
        "default_command": None,
        "default_item":    None,
        "commands": {}
    },

    "sensore_movimento": {
        "label":           "Sensore movimento",
        "category":        "sicurezza",
        "inherits":        "sensore_binario",
        "default_aliases": ["sensore movimento", "pir", "rilevatore"],
        "default_command": None,
        "default_item":    None,
        "commands": {}
    },

    "allarme": {
        "label":           "Allarme",
        "category":        "sicurezza",
        "default_aliases": ["allarme", "antifurto", "sirena"],
        "default_command": "attiva",
        "default_item":    None,
        "commands": {
            "attiva": {
                "label":          "Attiva",
                "ha_service_key": "alarm_control_panel.alarm_arm_away",
                "params": []
            },
            "attiva_notturno": {
                "label":          "Attiva modalità notte",
                "ha_service_key": "alarm_control_panel.alarm_arm_night",
                "params": []
            },
            "disattiva": {
                "label":          "Disattiva",
                "ha_service_key": "alarm_control_panel.alarm_disarm",
                "params": []
            },
        }
    },

    # ── SENSORI AMBIENTALI ─────────────────────────────────────────────────────
    "sensore_temperatura": {
        "label":           "Sensore temperatura",
        "category":        "sensori",
        "default_aliases": ["sensore temperatura", "termometro"],
        "default_command": None,
        "default_item":    None,
        "commands": {}
    },

    "sensore_umidita": {
        "label":           "Sensore umidità",
        "category":        "sensori",
        "default_aliases": ["sensore umidità", "igrometro"],
        "default_command": None,
        "default_item":    None,
        "commands": {}
    },

    "sensore_qualita_aria": {
        "label":           "Sensore qualità aria",
        "category":        "sensori",
        "default_aliases": ["sensore aria", "qualità aria", "co2"],
        "default_command": None,
        "default_item":    None,
        "commands": {}
    },

    # ── MULTIMEDIA ─────────────────────────────────────────────────────────────
    "tv": {
        "label":           "TV",
        "category":        "multimedia",
        "default_aliases": ["tv", "televisore", "televisione", "schermo"],
        "default_command": "toggle",
        "default_item":    None,
        "commands": {
            "accendi": {
                "label":          "Accendi",
                "ha_service_key": "media_player.turn_on",
                "params": []
            },
            "spegni": {
                "label":          "Spegni",
                "ha_service_key": "media_player.turn_off",
                "params": []
            },
            "toggle": {
                "label":          "Toggle",
                "ha_service_key": "media_player.toggle",
                "params": []
            },
            "volume_su": {
                "label":          "Volume su",
                "ha_service_key": "media_player.volume_up",
                "params": []
            },
            "volume_giu": {
                "label":          "Volume giù",
                "ha_service_key": "media_player.volume_down",
                "params": []
            },
            "muto": {
                "label":          "Muto",
                "ha_service_key": "media_player.volume_mute",
                "params": [
                    {"id": "is_volume_muted", "type": "bool"}
                ]
            },
            "cambia_sorgente": {
                "label":          "Cambia sorgente",
                "ha_service_key": "media_player.select_source",
                "params": [
                    {"id": "source", "type": "str"}
                ]
            },
        }
    },

    "diffusore": {
        "label":           "Diffusore audio",
        "category":        "multimedia",
        "inherits":        "tv",
        "default_aliases": ["diffusore", "cassa", "altoparlante", "speaker"],
        "default_command": "play",
        "default_item":    None,
        "commands": {
            "play": {
                "label":          "Play",
                "ha_service_key": "media_player.media_play",
                "params": []
            },
            "pausa": {
                "label":          "Pausa",
                "ha_service_key": "media_player.media_pause",
                "params": []
            },
            "prossimo": {
                "label":          "Prossimo brano",
                "ha_service_key": "media_player.media_next_track",
                "params": []
            },
        }
    },

    # ── VENTILAZIONE ───────────────────────────────────────────────────────────
    "ventilazione": {
        "label":           "Ventilazione",
        "category":        "clima",
        "default_aliases": ["ventilazione", "fan", "ventola", "estrattore"],
        "default_command": "toggle",
        "default_item":    None,
        "commands": {
            "accendi": {
                "label":          "Accendi",
                "ha_service_key": "fan.turn_on",
                "params": []
            },
            "spegni": {
                "label":          "Spegni",
                "ha_service_key": "fan.turn_off",
                "params": []
            },
            "toggle": {
                "label":          "Toggle",
                "ha_service_key": "fan.toggle",
                "params": []
            },
            "imposta_velocita": {
                "label":          "Imposta velocità",
                "ha_service_key": "fan.set_percentage",
                "params": [
                    {"id": "percentage", "type": "int", "min": 0, "max": 100, "unit": "%"}
                ]
            },
        }
    },
}


def resolve_archetype(archetype_id: str) -> dict:
    """Restituisce label, category, defaults e comandi flat (ereditarietà risolta)."""
    archetype = ARCHETYPES[archetype_id]
    commands = {}
    if "inherits" in archetype:
        parent = resolve_archetype(archetype["inherits"])
        commands.update(parent["commands"])
    commands.update(archetype["commands"])
    return {
        "label":           archetype["label"],
        "category":        archetype["category"],
        "default_aliases": archetype.get("default_aliases", []),
        "default_command": archetype.get("default_command"),
        "default_item":    archetype.get("default_item"),
        "commands":        commands,
    }


def archetypes_by_category() -> dict:
    result = {}
    for aid, data in ARCHETYPES.items():
        result.setdefault(data["category"], []).append((aid, data["label"]))
    return result