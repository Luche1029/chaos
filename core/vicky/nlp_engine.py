"""
nlp_engine.py
Estrae slot (area, device, command) da una frase in linguaggio naturale
usando un sistema n-gram pesato (m1×1, m2×10, m3×100).

Fonti dell'indice:
  1. Alias nel grafo Neo4j (inseriti manualmente nel VWB)
  2. Termini espansi da _common.yaml di HA (automatici)

Fallback: embedding sentence-transformers per termini non in indice.

Uso:
    from nlp_engine import NLPEngine
    engine = NLPEngine(db, common_yaml_path="_common.yaml")
    engine.build_index()
    result = engine.extract("accendi la luce in soggiorno")
    print(result.to_dict())
"""

from __future__ import annotations

import json
import pickle
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vicky_world_builder import Neo4jManager

# ── Configurazione ─────────────────────────────────────────────────────────────
INDEX_PATH       = Path("vicky_ngram_index.pkl")
STOPWORDS_PATH   = Path("stopwords_it.txt")
COMMON_YAML_PATH = Path("_common.yaml")

# Pesi n-gram (speculare al tuo script JS)
WEIGHTS = {"m1": 1, "m2": 10, "m3": 100}

# Soglia minima di score per accettare un match
MIN_SCORE = 5.0

# Soglia sotto cui si usa il fallback embedding
EMBEDDING_FALLBACK_THRESHOLD = 2.0

MAX_NGRAM = 3


# ══════════════════════════════════════════════════════════════════════════════
# Strutture dati
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class SlotMatch:
    node_id:  str    # id del nodo nel grafo (area_id, archetype_id, command_id)
    score:    float
    ngram:    str    # porzione di frase che ha matchato
    term:     str    # termine nell'indice che ha matchato
    source:   str    # "graph_alias" | "common_yaml" | "embedding"

    def __repr__(self):
        return (f"SlotMatch(node={self.node_id!r}, "
                f"ngram={self.ngram!r}, score={self.score:.1f}, "
                f"src={self.source})")


@dataclass
class ExtractionResult:
    area:    str | None = None
    device:  str | None = None
    command: str | None = None

    area_match:    SlotMatch | None = None
    device_match:  SlotMatch | None = None
    command_match: SlotMatch | None = None

    all_scores: dict = field(default_factory=dict)  # per debug

    @property
    def confident(self) -> bool:
        return any([self.area, self.device, self.command])

    def to_dict(self) -> dict:
        return {
            "area":      self.area,
            "device":    self.device,
            "command":   self.command,
            "confident": self.confident,
            "scores": {
                "area":    round(self.area_match.score, 2)    if self.area_match    else None,
                "device":  round(self.device_match.score, 2)  if self.device_match  else None,
                "command": round(self.command_match.score, 2) if self.command_match else None,
            },
            "matched_ngrams": {
                "area":    self.area_match.ngram    if self.area_match    else None,
                "device":  self.device_match.ngram  if self.device_match  else None,
                "command": self.command_match.ngram if self.command_match else None,
            },
            "sources": {
                "area":    self.area_match.source    if self.area_match    else None,
                "device":  self.device_match.source  if self.device_match  else None,
                "command": self.command_match.source if self.command_match else None,
            },
        }


# ══════════════════════════════════════════════════════════════════════════════
# Indice n-gram
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class NgramIndex:
    """
    Struttura indice:
    {
      "area":    {"m1": {"soggiorno": {"Sala": 1.0}, ...}, "m2": {...}, "m3": {...}},
      "device":  {"m1": {"luce": {"luce_semplice": 0.5, "luce_rgb": 0.5}, ...}},
      "command": {"m1": {"accendi": {"accendi": 1.0}, ...}}
    }
    Ogni foglia è {node_id: probabilità}.
    """
    data: dict = field(default_factory=lambda: {
        "area":      {"m1": {}, "m2": {}, "m3": {}},
        "device":    {"m1": {}, "m2": {}, "m3": {}},
        "command":   {"m1": {}, "m2": {}, "m3": {}},
        "archetype": {"m1": {}, "m2": {}, "m3": {}},
    })
    built_at: float = 0.0

    def add(self, slot_type: str, ngram: str, node_id: str, prob: float = 1.0):
        """Aggiunge un termine all'indice per il livello corretto."""
        n_words = len(ngram.split())
        level   = f"m{min(n_words, 3)}"
        bucket  = self.data[slot_type][level]
        if ngram not in bucket:
            bucket[ngram] = {}
        bucket[ngram][node_id] = bucket[ngram].get(node_id, 0) + prob

    def normalize(self):
        """Normalizza le probabilità in ogni entry dell'indice."""
        for slot_type in self.data:
            for level in self.data[slot_type]:
                for ngram, nodes in self.data[slot_type][level].items():
                    total = sum(nodes.values())
                    if total > 0:
                        for nid in nodes:
                            nodes[nid] /= total

    def score(self, slot_type: str, tokens: list[str]) -> dict[str, float]:
        """
        Calcola score ponderato per tutti i candidati dato un set di token.
        Restituisce {node_id: score_totale}.
        """
        scores: dict[str, float] = {}
        ngrams_by_level = build_ngrams(tokens, MAX_NGRAM)

        for level, ngrams in ngrams_by_level.items():
            weight = WEIGHTS.get(level, 1)
            bucket = self.data[slot_type].get(level, {})
            for ngram in ngrams:
                if ngram in bucket:
                    entry = bucket[ngram]
                    for node_id, prob in entry.items():
                        scores[node_id] = scores.get(node_id, 0) + prob * weight

        return scores

    def best_match(self, slot_type: str,
                   tokens: list[str],
                   original_tokens: list[str]) -> SlotMatch | None:
        """
        Trova il miglior match per uno slot dato i token della frase.
        Restituisce None se sotto MIN_SCORE.
        """
        scores = self.score(slot_type, tokens)
        if not scores:
            return None

        best_id    = max(scores, key=lambda k: scores[k])
        best_score = scores[best_id]

        if best_score < MIN_SCORE:
            return None

        # Trova l'n-gram che ha contribuito di più
        best_ngram = _find_best_ngram(self, slot_type, tokens, best_id)

        return SlotMatch(
            node_id=best_id,
            score=best_score,
            ngram=best_ngram,
            term=best_ngram,
            source="graph_alias",
        )


def _find_best_ngram(index: NgramIndex, slot_type: str,
                     tokens: list[str], winner_id: str) -> str:
    """Trova l'n-gram che ha dato il contributo maggiore al winner."""
    best_ngram = ""
    best_contrib = 0.0
    ngrams_by_level = build_ngrams(tokens, MAX_NGRAM)
    for level, ngrams in ngrams_by_level.items():
        weight = WEIGHTS.get(level, 1)
        bucket = index.data[slot_type].get(level, {})
        for ngram in ngrams:
            if ngram in bucket and winner_id in bucket[ngram]:
                contrib = bucket[ngram][winner_id] * weight
                if contrib > best_contrib:
                    best_contrib = contrib
                    best_ngram   = ngram
    return best_ngram


# ══════════════════════════════════════════════════════════════════════════════
# Helpers tokenizzazione
# ══════════════════════════════════════════════════════════════════════════════

def load_stopwords(path: Path = STOPWORDS_PATH) -> set[str]:
    if not path.exists():
        print(f"[NLP] ⚠ Stopwords non trovate: {path}")
        return set()
    words = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            words.add(line.lower())
    print(f"[NLP] Stopwords: {len(words)} voci")
    return words


def tokenize(text: str, stopwords: set[str]) -> list[str]:
    """Tokenizza rimuovendo punteggiatura e stopword."""
    text   = text.strip().lower()
    text   = re.sub(r"[^\w\s]", " ", text)
    tokens = text.split()
    return [t for t in tokens if t not in stopwords and len(t) > 1]


def build_ngrams(tokens: list[str], max_n: int) -> dict[str, list[str]]:
    """
    Genera n-gram per livello.
    Restituisce {"m1": [...], "m2": [...], "m3": [...]}.
    """
    result = {}
    for n in range(1, max_n + 1):
        level  = f"m{n}"
        ngrams = []
        for i in range(len(tokens) - n + 1):
            ngrams.append(" ".join(tokens[i:i+n]))
        result[level] = ngrams
    return result


# ══════════════════════════════════════════════════════════════════════════════
# NLP Engine
# ══════════════════════════════════════════════════════════════════════════════

class NLPEngine:

    def __init__(self, db: "Neo4jManager",
                 common_yaml_path: Path | str = COMMON_YAML_PATH,
                 index_path: Path = INDEX_PATH,
                 stopwords_path: Path = STOPWORDS_PATH):
        self.db               = db
        self.common_yaml_path = Path(common_yaml_path)
        self.index_path       = index_path
        self.stopwords        = load_stopwords(stopwords_path)
        self._index: NgramIndex | None = None
        self._embedding_engine = None  # lazy init per fallback

    # ── Build indice ───────────────────────────────────────────────────────────
    def build_index(self, save: bool = True) -> NgramIndex:
        """
        Costruisce l'indice n-gram da:
        1. Alias nel grafo (area, archetype, command)
        2. Termini espansi da _common.yaml
        """
        print("[NLP] Costruzione indice n-gram...")
        index = NgramIndex(built_at=time.time())

        # ── 1. Alias dal grafo ────────────────────────────────────────────────
        print("[NLP] Lettura alias dal grafo...")
        graph_aliases = self._fetch_graph_aliases()
        print(f"[NLP] Alias letti: { {k: len(v) for k,v in graph_aliases.items()} }")
        for slot_type, entries in graph_aliases.items():
            for entry in entries:
                alias   = entry["value"]
                node_id = entry["node_id"]
                tokens  = tokenize(alias, self.stopwords)
                if not tokens:
                    continue
                # Aggiunge tutti gli n-gram dell'alias
                ngrams_by_level = build_ngrams(tokens, MAX_NGRAM)
                for level, ngrams in ngrams_by_level.items():
                    for ngram in ngrams:
                        index.add(slot_type, ngram, node_id, prob=1.0)

        print(f"[NLP]   Alias grafo: "
              f"area={len(graph_aliases.get('area', []))}, "
              f"device={len(graph_aliases.get('archetype', []))}, "
              f"command={len(graph_aliases.get('command', []))}")

        # ── 2. Termini da _common.yaml ────────────────────────────────────────
        print(f"[NLP] Cerco _common.yaml in: {self.common_yaml_path.resolve()}")
        print(f"[NLP] Esiste: {self.common_yaml_path.exists()}")
        if self.common_yaml_path.exists():
            common_counts = self._add_common_yaml_terms(index)
            print(f"[NLP]   Common YAML: {common_counts}")
        else:
            print(f"[NLP] ⚠ _common.yaml non trovato: {self.common_yaml_path}")

        # Normalizza probabilità
        print("[NLP] Normalizzazione indice...")
        index.normalize()
        self._index = index

        if save:
            self.index_path.write_bytes(pickle.dumps(index))
            print(f"[NLP] Indice salvato: {self.index_path}")

        return index

    def _fetch_graph_aliases(self) -> dict[str, list[dict]]:
        """
        Legge alias dal grafo divisi per tipo.
        Mappa 'archetype' e 'device' entrambi al bucket 'archetype'
        dell'indice — gli alias custom delle istanze contribuiscono
        allo stesso pool degli alias di tipo.
        """
        result: dict[str, list[dict]] = {
            "area": [], "archetype": [], "command": []}

        # Mappa tipo nel grafo → bucket indice
        type_map = {
            "area":      "area",
            "archetype": "archetype",
            "device":    "archetype",   # alias custom istanza → stesso bucket
            "command":   "command",
        }

        with self.db.driver.session() as s:
            rows = s.run("""
                MATCH (n)-[:HAS_ALIAS]->(a:Alias)
                WHERE a.type IN ['area', 'archetype', 'device', 'command']
                RETURN a.value as value, a.type as type, n.id as node_id
            """)
            for r in rows:
                bucket = type_map.get(r["type"])
                if bucket:
                    result[bucket].append({"value":   r["value"],
                                           "node_id": r["node_id"]})
        return result

    def _add_common_yaml_terms(self, index: NgramIndex) -> dict:
        """Aggiunge termini da _common.yaml all'indice."""
        from common_parser import CommonParser, DOMAIN_TO_ARCHETYPES

        print("[NLP] Parsing _common.yaml...")
        parser = CommonParser(self.common_yaml_path).parse()
        print("[NLP] Parsing completato")

        # Aggiorna stopword con skip_words di HA
        for w in parser.get_skip_words():
            self.stopwords.add(w.lower())

        counts = {"device": 0, "command": 0}

        # ── Device terms ──────────────────────────────────────────────────────
        print("[NLP] Espansione device terms...")
        device_terms = parser.get_all_device_terms()
        print(f"[NLP] Device terms: {len(device_terms)} archetipi")
        for arch_id, terms in device_terms.items():
            for term in terms:
                tokens = tokenize(term, self.stopwords)
                if not tokens:
                    continue
                ngrams_by_level = build_ngrams(tokens, MAX_NGRAM)
                for level, ngrams in ngrams_by_level.items():
                    for ngram in ngrams:
                        index.add("archetype", ngram, arch_id, prob=0.8)
                        counts["device"] += 1

        # ── Command terms ─────────────────────────────────────────────────────
        print("[NLP] Espansione command terms...")
        command_terms = parser.get_all_command_terms()
        print(f"[NLP] Command terms: {len(command_terms)} comandi")
        for cmd_id, terms in command_terms.items():
            for term in terms:
                tokens = tokenize(term, self.stopwords)
                if not tokens:
                    continue
                ngrams_by_level = build_ngrams(tokens, MAX_NGRAM)
                for level, ngrams in ngrams_by_level.items():
                    for ngram in ngrams:
                        index.add("command", ngram, cmd_id, prob=0.8)
                        counts["command"] += 1

        return counts

    # ── Carica indice ──────────────────────────────────────────────────────────
    def load_index(self) -> bool:
        if not self.index_path.exists():
            return False
        try:
            self._index = pickle.loads(self.index_path.read_bytes())
            t = time.strftime("%Y-%m-%d %H:%M",
                              time.localtime(self._index.built_at))
            print(f"[NLP] Indice caricato (costruito: {t})")
            return True
        except Exception as e:
            print(f"[NLP] ⚠ Indice corrotto: {e}")
            return False

    def ensure_index(self):
        if self._index is None:
            if not self.load_index():
                self.build_index()

    # ── Estrazione slot ────────────────────────────────────────────────────────
    def extract(self, sentence: str) -> ExtractionResult:
        """
        Estrae (area, device, command) da una frase libera.
        """
        self.ensure_index()

        tokens = tokenize(sentence, self.stopwords)
        if not tokens:
            return ExtractionResult()

        result = ExtractionResult()

        # Cerca match per ogni slot
        for slot_type, attr in [("area", "area"),
                                  ("archetype", "device"),
                                  ("command", "command")]:
            match = self._index.best_match(slot_type, tokens, tokens)

            # Fallback embedding se score troppo basso
            if match is None or match.score < EMBEDDING_FALLBACK_THRESHOLD:
                emb_match = self._embedding_fallback(slot_type, tokens)
                if emb_match and (match is None or
                                  emb_match.score > match.score):
                    match = emb_match

            if match:
                setattr(result, attr, match.node_id)
                setattr(result, f"{attr}_match", match)

        # Debug scores
        result.all_scores = {
            "area":    self._index.score("area",      tokens),
            "device":  self._index.score("archetype", tokens),
            "command": self._index.score("command",   tokens),
        }

        return result

    # ── Fallback embedding ─────────────────────────────────────────────────────
    def _embedding_fallback(self, slot_type: str,
                            tokens: list[str]) -> SlotMatch | None:
        """
        Usa sentence-transformers come fallback quando l'indice n-gram
        non trova match sufficienti.
        """
        try:
            if self._embedding_engine is None:
                self._embedding_engine = _EmbeddingFallback(self.db)
            return self._embedding_engine.find(slot_type, " ".join(tokens))
        except Exception as e:
            print(f"[NLP] Embedding fallback error: {e}")
            return None

    # ── Debug ──────────────────────────────────────────────────────────────────
    def explain(self, sentence: str) -> str:
        """Versione verbose dell'estrazione per debug."""
        self.ensure_index()
        tokens = tokenize(sentence, self.stopwords)
        lines  = [f"Frase:  '{sentence}'",
                  f"Token:  {tokens}", ""]

        for slot_type, label in [("area", "AREA"),
                                   ("archetype", "DEVICE"),
                                   ("command", "COMMAND")]:
            scores = self._index.score(slot_type, tokens)
            sorted_scores = sorted(scores.items(),
                                   key=lambda x: x[1], reverse=True)[:5]
            lines.append(f"── {label} ──")
            if sorted_scores:
                for nid, sc in sorted_scores:
                    lines.append(f"  {nid:30s} score={sc:.2f}")
            else:
                lines.append("  (nessun match)")
            lines.append("")

        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# Fallback embedding (lazy, solo se sentence-transformers disponibile)
# ══════════════════════════════════════════════════════════════════════════════

class _EmbeddingFallback:
    MODEL_NAME = "paraphrase-multilingual-mpnet-base-v2"

    def __init__(self, db: "Neo4jManager"):
        import numpy as np
        from sentence_transformers import SentenceTransformer
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[NLP Embedding] Caricamento modello su {device}...")
        self.model = SentenceTransformer(self.MODEL_NAME, device=device)
        self.db    = db
        self._cache: dict[str, tuple] = {}  # slot_type → (aliases, node_ids, vecs)
        self.np    = np

    def _get_index(self, slot_type: str):
        if slot_type in self._cache:
            return self._cache[slot_type]
        with self.db.driver.session() as s:
            rows = list(s.run("""
                MATCH (n)-[:HAS_ALIAS]->(a:Alias {type: $t})
                RETURN a.value as v, n.id as nid
            """, t=slot_type if slot_type != "archetype" else "archetype"))
        aliases  = [r["v"] for r in rows]
        node_ids = [r["nid"] for r in rows]
        if not aliases:
            return None, None, None
        vecs = self.model.encode(aliases, normalize_embeddings=True,
                                 show_progress_bar=False)
        self._cache[slot_type] = (aliases, node_ids, vecs)
        return aliases, node_ids, vecs

    def find(self, slot_type: str, text: str) -> SlotMatch | None:
        aliases, node_ids, vecs = self._get_index(slot_type)
        if vecs is None:
            return None
        query_vec = self.model.encode([text], normalize_embeddings=True)[0]
        sims      = vecs @ query_vec
        best_idx  = int(self.np.argmax(sims))
        best_sim  = float(sims[best_idx])
        if best_sim < 0.5:
            return None
        return SlotMatch(
            node_id=node_ids[best_idx],
            score=best_sim * 10,   # scala comparabile con n-gram
            ngram=text,
            term=aliases[best_idx],
            source="embedding",
        )


# ══════════════════════════════════════════════════════════════════════════════
# CLI per test standalone
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from vicky_world_builder import Neo4jManager

    db     = Neo4jManager()
    engine = NLPEngine(db)

    if "--rebuild" in sys.argv:
        engine.build_index()
    else:
        engine.ensure_index()

    print("\nNLP Engine pronto. Digita una frase (--explain per dettagli):\n")
    explain_mode = "--explain" in sys.argv

    while True:
        try:
            frase = input("→ ").strip()
            if not frase:
                continue
            if explain_mode or frase.startswith("?"):
                frase = frase.lstrip("?").strip()
                print(engine.explain(frase))
            else:
                result = engine.extract(frase)
                print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            print()
        except KeyboardInterrupt:
            print("\nUscita.")
            break