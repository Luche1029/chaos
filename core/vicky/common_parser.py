"""
common_parser.py
Legge _common.yaml di Home Assistant Assist e produce:
  - dizionario expansion_rules espanso (regex → lista termini concreti)
  - mapping domain → alias device
  - mapping intent → command_id grafo
  - skip_words da aggiungere alle stopword

Uso:
    from common_parser import CommonParser
    parser = CommonParser("path/to/_common.yaml")
    parser.parse()
    terms = parser.get_device_terms("light")
    # ["luce", "luci", "lampada", "lampadine", ...]
"""

from __future__ import annotations

import re
import yaml
from pathlib import Path
from itertools import product


# ── Mapping domain HA → archetipi del grafo ────────────────────────────────────
DOMAIN_TO_ARCHETYPES: dict[str, list[str]] = {
    "light":        ["luce_semplice", "luce_dimmer", "luce_rgb"],
    "cover":        ["tapparella", "tenda_da_sole", "vetro_oscurabile"],
    "climate":      ["termostato", "condizionatore"],
    "fan":          ["ventilazione"],
    "switch":       ["presa", "interruttore"],
    "media_player": ["tv", "diffusore"],
    "alarm_control_panel": ["allarme"],
}

# ── Mapping expansion_rule → command_id del grafo ──────────────────────────────
RULE_TO_COMMAND: dict[str, str] = {
    "turn_on":    "accendi",
    "turn_off":   "spegni",
    "open":       "apri",
    "close":      "chiudi",
    "set":        "imposta_luminosita",   # generico, affinato dal domain
    "to_lock":    "chiudi",
    "unlock":     "apri",
    "clean":      "accendi",              # vacuum → start
    "start":      "accendi",
}

# ── Mapping intent HA → command_id del grafo ───────────────────────────────────
INTENT_TO_COMMAND: dict[str, str] = {
    "HassTurnOn":                   "accendi",
    "HassTurnOff":                  "spegni",
    "HassLightSet":                 "imposta_luminosita",
    "HassSetPosition":              "imposta_posizione",
    "HassClimateSetTemperature":    "imposta_temperatura",
    "HassClimateGetTemperature":    "imposta_temperatura",
    "HassTurnOnHvacMode":           "imposta_modalita",
    "HassMediaNext":                "prossimo",
    "HassMediaPause":               "pausa",
    "HassMediaUnpause":             "play",
    "HassSetVolume":                "volume_su",
    "HassVacuumStart":              "accendi",
    "HassVacuumReturnToBase":       "spegni",
    "HassCoverOpen":                "apri",
    "HassCoverClose":               "chiudi",
    "HassCoverSetPosition":         "imposta_posizione",
}


class CommonParser:

    def __init__(self, path: str | Path):
        self.path       = Path(path)
        self._raw: dict = {}
        self._rules: dict[str, str]       = {}   # nome → pattern grezzo
        self._expanded: dict[str, list[str]] = {} # nome → lista termini
        self.skip_words: list[str]         = []

    # ── Parse ──────────────────────────────────────────────────────────────────
    def parse(self) -> "CommonParser":
        """Carica il YAML e espande tutte le expansion_rules."""
        self._raw = yaml.safe_load(self.path.read_text(encoding="utf-8"))

        self._rules    = self._raw.get("expansion_rules", {})
        self.skip_words = self._raw.get("skip_words", [])

        # Espandi ogni regola
        for name in self._rules:
            self._expanded[name] = self._expand_rule(name, depth=0)

        print(f"[Parser] Caricate {len(self._rules)} expansion_rules")
        print(f"[Parser] skip_words: {len(self.skip_words)} voci")
        return self

    # ── Espansione regole ──────────────────────────────────────────────────────
    def _expand_rule(self, name: str, depth: int = 0,
                     _stack: frozenset | None = None) -> list[str]:
        """Espande ricorsivamente una regola in lista di termini concreti."""
        if _stack is None:
            _stack = frozenset()

        # Anti-loop: se la regola è già nello stack corrente, fermati
        if name in _stack:
            return []

        # Profondità massima di sicurezza
        if depth > 12:
            return []

        # Cache: già espansa
        if name in self._expanded:
            return self._expanded[name]

        # Marca come "in espansione" nello stack
        _stack = _stack | {name}

        pattern = self._rules.get(name, "")
        result = self._expand_pattern(pattern, depth, _stack)

        # Salva in cache solo se non è un risultato parziale da ciclo
        self._expanded[name] = result
        return result

    def _expand_pattern(self, pattern: str, depth: int,
                        _stack: frozenset | None = None) -> list[str]:
        if _stack is None:
            _stack = frozenset()
        """
        Espande un pattern HA in lista di stringhe concrete.
        Gestisce:
          - <rule_ref>       → espansione ricorsiva
          - (a|b|c)          → alternativa
          - [optional]       → con e senza
          - {slot}           → wildcard, ignorato
          - testo letterale
        """
        # Rimuovi spazi eccessivi
        pattern = pattern.strip()

        # Sostituisci riferimenti <rule> con un placeholder numerato
        # (per non confonderli con le parentesi tonde dell'alternativa)
        refs: dict[str, list[str]] = {}
        ref_idx = [0]

        def replace_ref(m):
            rule_name = m.group(1)
            key = f"__REF{ref_idx[0]}__"
            refs[key] = self._expand_rule(rule_name, depth + 1, _stack)
            ref_idx[0] += 1
            return key

        pattern = re.sub(r"<([^>]+)>", replace_ref, pattern)

        # Rimuovi slot {name} — sono wildcard runtime, li ignoriamo
        pattern = re.sub(r"\{[^}]+\}", "", pattern)

        # Espandi il pattern
        terms = self._expand_groups(pattern, _stack)

        # Reintegra i riferimenti espansi
        final = []
        for term in terms:
            expanded = self._reintegrate_refs(term, refs)
            final.extend(expanded)

        # Pulisci e deduplicazione
        result = []
        seen = set()
        for t in final:
            t = self._clean(t)
            if t and t not in seen:
                seen.add(t)
                result.append(t)

        return result

    def _expand_groups(self, pattern: str,
                       _stack: frozenset | None = None) -> list[str]:
        """
        Espande (a|b|c) e [optional] ricorsivamente.
        Restituisce lista di varianti.
        """
        if _stack is None:
            _stack = frozenset()
        # Trova il primo gruppo non annidato
        # Prova prima con parentesi tonde (obbligatorio), poi quadre (opzionale)
        for open_c, close_c, optional in [("(", ")", False), ("[", "]", True)]:
            idx = self._find_first_group(pattern, open_c, close_c)
            if idx is None:
                continue

            start, end = idx
            before  = pattern[:start]
            group   = pattern[start+1:end]
            after   = pattern[end+1:]

            # Espandi le alternative dentro il gruppo
            alternatives = self._split_alternatives(group)
            alt_expanded = []
            for alt in alternatives:
                alt_expanded.extend(self._expand_groups(alt, _stack))

            if optional:
                alt_expanded.append("")   # versione senza il gruppo

            # Ricombina con prima e dopo
            result = []
            for alt in alt_expanded:
                sub = before + alt + after
                result.extend(self._expand_groups(sub, _stack))
            return result

        # Nessun gruppo trovato — ritorna il pattern così com'è
        return [pattern]

    def _find_first_group(self, s: str, open_c: str,
                          close_c: str) -> tuple[int, int] | None:
        """Trova start e end del primo gruppo bilanciato."""
        depth = 0
        start = None
        for i, c in enumerate(s):
            if c == open_c:
                if depth == 0:
                    start = i
                depth += 1
            elif c == close_c:
                depth -= 1
                if depth == 0 and start is not None:
                    return start, i
        return None

    def _split_alternatives(self, group: str) -> list[str]:
        """Divide 'a|b|c' rispettando i gruppi annidati."""
        parts = []
        depth = 0
        current = []
        for c in group:
            if c in ("(", "["):
                depth += 1
                current.append(c)
            elif c in (")", "]"):
                depth -= 1
                current.append(c)
            elif c == "|" and depth == 0:
                parts.append("".join(current))
                current = []
            else:
                current.append(c)
        if current:
            parts.append("".join(current))
        return parts

    def _reintegrate_refs(self, term: str,
                          refs: dict[str, list[str]]) -> list[str]:
        """Sostituisce i placeholder __REFn__ con le espansioni reali."""
        # Trova tutti i placeholder nel termine
        placeholders = re.findall(r"__REF\d+__", term)
        if not placeholders:
            return [term]

        # Costruisci lista di espansioni per ogni placeholder
        options = []
        for ph in placeholders:
            options.append(refs.get(ph, [""]))

        # Prodotto cartesiano
        result = []
        for combo in product(*options):
            t = term
            for ph, val in zip(placeholders, combo):
                t = t.replace(ph, val, 1)
            result.append(t)
        return result

    @staticmethod
    def _clean(text: str) -> str:
        """Normalizza spazi e rimuove caratteri residui."""
        text = re.sub(r"[\[\](){}|]", " ", text)
        text = re.sub(r"\s+", " ", text).strip().lower()
        # Filtra stringhe troppo corte o solo simboli
        if len(text) < 2:
            return ""
        return text

    # ── API pubblica ───────────────────────────────────────────────────────────
    def get_device_terms(self, domain: str) -> list[str]:
        """
        Restituisce i termini italiani per un domain HA.
        es. get_device_terms("light") → ["luce", "luci", "lampada", ...]
        """
        # Mappa domain → nome regola
        domain_rule_map = {
            "light":   "light",
            "cover":   "cover",
            "climate": "climate",
            "fan":     "fan",
            "switch":  "on_off_domains",
            "lock":    "lock",
        }
        rule = domain_rule_map.get(domain)
        if not rule:
            return []
        return self._expanded.get(rule, [])

    def get_command_terms(self, rule_name: str) -> list[str]:
        """
        Restituisce i termini italiani per un comando.
        es. get_command_terms("turn_on") → ["accendi", "attiva", ...]
        """
        return self._expanded.get(rule_name, [])

    def get_all_command_terms(self) -> dict[str, list[str]]:
        """
        Restituisce tutti i termini per ogni regola mappata a un command_id.
        Restituisce {command_id: [termini]}
        """
        result: dict[str, list[str]] = {}
        for rule_name, command_id in RULE_TO_COMMAND.items():
            terms = self._expanded.get(rule_name, [])
            if command_id not in result:
                result[command_id] = []
            for t in terms:
                if t not in result[command_id]:
                    result[command_id].append(t)
        return result

    def get_all_device_terms(self) -> dict[str, list[str]]:
        """
        Restituisce {archetype_id: [termini]} per tutti i domain mappati.
        """
        result: dict[str, list[str]] = {}
        for domain, archetypes in DOMAIN_TO_ARCHETYPES.items():
            terms = self.get_device_terms(domain)
            for arch in archetypes:
                if arch not in result:
                    result[arch] = []
                for t in terms:
                    if t not in result[arch]:
                        result[arch].append(t)
        return result

    def get_skip_words(self) -> list[str]:
        """Restituisce le skip_words da aggiungere alle stopword."""
        cleaned = []
        for w in self.skip_words:
            w = w.strip().lower()
            if w:
                cleaned.append(w)
        return cleaned

    def summary(self) -> str:
        """Stampa un sommario delle espansioni per debug."""
        lines = [f"CommonParser — {self.path.name}",
                 f"  Regole totali: {len(self._rules)}",
                 f"  Skip words:    {len(self.skip_words)}",
                 ""]
        for name in ["light", "cover", "climate", "fan",
                     "turn_on", "turn_off", "open", "close", "set"]:
            terms = self._expanded.get(name, [])
            lines.append(f"  <{name}>: {terms[:5]}"
                         + (f" ... (+{len(terms)-5})" if len(terms) > 5 else ""))
        return "\n".join(lines)


# ── CLI per test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "_common.yaml"
    parser = CommonParser(path).parse()
    print(parser.summary())
    print("\nDevice terms per domain:")
    for domain in ["light", "cover", "climate", "fan"]:
        print(f"  {domain}: {parser.get_device_terms(domain)}")
    print("\nCommand terms:")
    for cmd, terms in parser.get_all_command_terms().items():
        print(f"  {cmd}: {terms[:6]}")