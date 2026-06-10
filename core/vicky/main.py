"""
main.py
Entry point di Vicky AI — API FastAPI
"""

import os
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from neo4j import GraphDatabase

from router_local import call_local_router
from nlp_engine import NLPEngine
from query_engine import QueryEngine
from feedback_engine import FeedbackEngine
from pattern_engine import PatternEngine

import io
import wave
from fastapi import UploadFile, File
from fastapi.responses import StreamingResponse

app = FastAPI(title="Vicky AI", version="1.0.0")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Configurazione ─────────────────────────────────────────────────────────────
NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://neo4j:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "chaospassword")
HA_URL         = os.getenv("HA_URL",         "http://homeassistant:8123")
HA_TOKEN       = os.getenv("HA_TOKEN",       "")
OLLAMA_URL     = os.getenv("OLLAMA_URL",     "http://ollama:11434")
OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL",   "llama3.2")
WHISPER_URL    = os.getenv("WHISPER_URL", "http://whisper:9000")
OWWW_URL       = os.getenv("OWWW_URL", "http://openwakeword:10400")

# ── Wrapper Neo4jManager minimale ──────────────────────────────────────────────
class Neo4jManager:
    """Wrapper minimale compatibile con NLPEngine e QueryEngine."""
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

# ── Inizializzazione engines ───────────────────────────────────────────────────
db           = Neo4jManager(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
query_engine = QueryEngine(db)
nlp_engine   = NLPEngine(db, common_yaml_path="_common.yaml")

feedback_engine = FeedbackEngine(
    neo4j_uri=NEO4J_URI,
    neo4j_user=NEO4J_USER,
    neo4j_password=NEO4J_PASSWORD,
    influx_url=os.getenv("INFLUXDB_URL", "http://influxdb:8086"),
    influx_token=os.getenv("INFLUXDB_TOKEN", ""),
    influx_org=os.getenv("INFLUXDB_ORG", "chaos"),
    influx_bucket=os.getenv("INFLUXDB_BUCKET", "casa")
)

pattern_engine = PatternEngine(
    influx_url=os.getenv("INFLUXDB_URL",    "http://influxdb:8086"),
    influx_token=os.getenv("INFLUXDB_TOKEN", ""),
    influx_org=os.getenv("INFLUXDB_ORG",    "chaos"),
    source_bucket="casa",
    rules_bucket="vicky_rules"
)

# ── Precaricamento indice al boot ─────────────────────────────────────────────
@app.on_event("startup")
def startup_event():
    print("[Vicky] Precariamento indice NLP...")
    nlp_engine.ensure_index()
    print("[Vicky] Indice pronto.")

# ── Modelli request/response ───────────────────────────────────────────────────
class CommandRequest(BaseModel):
    text:       str
    session_id: Optional[str] = "default"

class CommandResponse(BaseModel):
    input:     str
    type:      str
    level:     Optional[int] = None
    calls:     Optional[list] = None
    response:  str
    success:   bool

# ── Health check ───────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "service": "vicky-ai"}

class FeedbackRequest(BaseModel):
    original_text:   str
    correct_area:    Optional[str] = None
    correct_device:  Optional[str] = None
    correct_command: Optional[str] = None
    session_id:      Optional[str] = "default"

# ── feedback endpoint ──────────────────────────────────────────────────────────
@app.post("/feedback")
def process_feedback(req: FeedbackRequest):
    result = feedback_engine.process(
        original_text=req.original_text,
        correct_area=req.correct_area,
        correct_device=req.correct_device,
        correct_command=req.correct_command,
        session_id=req.session_id
    )
    nlp_engine.build_index()
    return result

# ── pattern endpoint ──────────────────────────────────────────────────────────
@app.post("/analyze-patterns")
def analyze_patterns(days: int = 7):
    result = pattern_engine.analyze(days=days)
    return result

@app.get("/rules")
def get_rules(min_confidence: float = 0.5, active_only: bool = True):
    """Restituisce le regole apprese da Vicky dal bucket vicky_rules."""
    try:
        from influxdb_client import InfluxDBClient
        client = InfluxDBClient(
            url=os.getenv("INFLUXDB_URL", "http://influxdb:8086"),
            token=os.getenv("INFLUXDB_TOKEN", ""),
            org=os.getenv("INFLUXDB_ORG", "chaos")
        )
        query_api = client.query_api()

        query = f'''
        from(bucket: "vicky_rules")
          |> range(start: -30d)
          |> filter(fn: (r) => r._measurement == "vicky_rules")
          |> filter(fn: (r) => r._field == "rule_json")
          |> last()
        '''

        tables = query_api.query(query, org=os.getenv("INFLUXDB_ORG", "chaos"))
        rules = []
        for table in tables:
            for record in table.records:
                try:
                    import json
                    rule = json.loads(record.get_value())
                    if rule.get("confidenza", 0) >= min_confidence:
                        if not active_only or rule.get("attiva", False):
                            rules.append(rule)
                except:
                    pass

        client.close()

        # Ordina per confidenza
        rules.sort(key=lambda x: x.get("confidenza", 0), reverse=True)
        return {"rules": rules, "total": len(rules)}

    except Exception as e:
        return {"rules": [], "total": 0, "error": str(e)}

@app.post("/rebuild-index")
def rebuild_index():
    """Forza la ricostruzione dell'indice NLP."""
    nlp_engine.build_index()
    return {"status": "ok", "message": "Indice ricostruito."}

# ── STT — Speech to Text ───────────────────────────────────────────────────────
@app.post("/stt")
async def speech_to_text(audio_file: UploadFile = File(...)):
    import tempfile, subprocess, os
    try:
        audio_bytes = await audio_file.read()
        print(f"[STT] Ricevuto: {len(audio_bytes)} bytes, type: {audio_file.content_type}")
        
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp_in:
            tmp_in.write(audio_bytes)
            tmp_in_path = tmp_in.name
        
        tmp_out_path = tmp_in_path.replace(".webm", ".wav")
        result = subprocess.run([
            "ffmpeg", "-i", tmp_in_path,
            "-ar", "16000", "-ac", "1", "-f", "wav",
            tmp_out_path, "-y"
        ], capture_output=True, timeout=15)
        
        os.unlink(tmp_in_path)
        print(f"[STT] ffmpeg returncode: {result.returncode}")
        print(f"[STT] ffmpeg stderr: {result.stderr.decode()[-200:]}")
        
        if result.returncode != 0:
            return {"text": "", "success": False, "error": "Conversione audio fallita"}
        
        with open(tmp_out_path, "rb") as f:
            wav_bytes = f.read()
        os.unlink(tmp_out_path)
        print(f"[STT] WAV generato: {len(wav_bytes)} bytes")
        
        files = {"audio_file": ("audio.wav", wav_bytes, "audio/wav")}
        params = {"language": "it", "task": "transcribe"}
        r = requests.post(f"{WHISPER_URL}/asr", files=files, params=params, timeout=60)
        print(f"[STT] Whisper status: {r.status_code}, body: {r.text[:200]}")
        r.raise_for_status()
        data = r.json()
        text = data.get("text", "").strip()
        return {"text": text, "success": bool(text)}
        
    except Exception as e:
        import traceback
        print(f"[STT] Whisper status: {r.status_code}, body: {r.text[:200]}")
        r.raise_for_status()

        # Whisper può rispondere con testo plain o JSON
        try:
            data = r.json()
            text = data.get("text", "").strip()
        except Exception:
            # Risposta testo plain
            text = r.text.strip()

        return {"text": text, "success": bool(text)}

# ── TTS — Text to Speech ───────────────────────────────────────────────────────
@app.post("/tts")
def text_to_speech(req: dict):
    """Genera audio WAV da testo usando Piper locale."""
    import subprocess
    import tempfile
    import os

    text = req.get("text", "")
    if not text:
        return {"error": "Testo vuoto"}

    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        result = subprocess.run(
            ["piper", "--model", "/app/piper-voices/it_IT-paola-medium.onnx",
            "--output_file", tmp_path],
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=30
        )

        if result.returncode != 0:
            return {"error": result.stderr.decode()}

        with open(tmp_path, "rb") as f:
            audio_data = f.read()

        os.unlink(tmp_path)

        return StreamingResponse(
            io.BytesIO(audio_data),
            media_type="audio/wav",
            headers={"Content-Disposition": "inline; filename=response.wav"}
        )
    except Exception as e:
        return {"error": str(e)}

# ── Trigger Word ────────────────────────────────────────────────────────
@app.post("/wake-detect")
async def wake_detect(audio_file: UploadFile = File(...)):
    """Rileva wake word usando Whisper — cerca 'vicky' nel testo trascritto."""
    import tempfile, subprocess, os
    try:
        audio_bytes = await audio_file.read()

        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp_in:
            tmp_in.write(audio_bytes)
            tmp_in_path = tmp_in.name

        tmp_out_path = tmp_in_path.replace(".webm", ".wav")
        result = subprocess.run([
            "ffmpeg", "-i", tmp_in_path,
            "-ar", "16000", "-ac", "1", "-f", "wav",
            tmp_out_path, "-y"
        ], capture_output=True, timeout=10)

        os.unlink(tmp_in_path)

        if result.returncode != 0:
            return {"detected": False}

        with open(tmp_out_path, "rb") as f:
            wav_bytes = f.read()
        os.unlink(tmp_out_path)

        # Usa Whisper per trascrivere
        files = {"audio_file": ("audio.wav", wav_bytes, "audio/wav")}
        params = {"language": "it", "task": "transcribe"}
        r = requests.post(f"{WHISPER_URL}/asr", files=files, params=params, timeout=30)

        if r.status_code != 200:
            return {"detected": False}

        try:
            data = r.json()
            text = data.get("text", "").strip().lower()
        except Exception:
            text = r.text.strip().lower()

        print(f"[WakeDetect] Trascritto: '{text}'")

        # Cerca wake word
        wake_words = ["vicky", "ehi vicky", "hey vicky", "ok vicky", "ciao vicky"]
        detected = any(w in text for w in wake_words)

        return {"detected": detected, "text": text}

    except Exception as e:
        print(f"[WakeDetect] Errore: {e}")
        return {"detected": False, "error": str(e)}

# ── Endpoint principale ────────────────────────────────────────────────────────
@app.post("/command", response_model=CommandResponse)
def process_command(req: CommandRequest):
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Testo vuoto")

    # Step 1 — NLP Engine estrae slot
    extraction = nlp_engine.extract(text)
    print(f"[DEBUG] extraction: {extraction.to_dict()}")
    print(f"[DEBUG] confident: {extraction.confident}")

    if extraction.confident:
        # L'NLP restituisce node_id (es. "luce_semplice", "toggle", "Sala")
        # Il QueryEngine cerca per alias — usiamo una query diretta per id
        area_id    = extraction.area
        device_id  = extraction.device
        command_id = extraction.command

        print(f"[DEBUG] node_ids: area={area_id}, device={device_id}, command={command_id}")

        # Risolvi direttamente tramite id archetipo
        qr = _resolve_by_ids(area_id, device_id, command_id)
        print(f"[DEBUG] query_result: status={qr['status']}")

        if qr['status'] == "ok":
            executed = []
            for call in qr['calls']:
                ok = _execute_ha(call['entity_id'], call['service'], call.get('service_data', {}))
                executed.append({"entity_id": call['entity_id'],
                                "service": call['service'],
                                "success": ok})
            all_ok = all(c["success"] for c in executed)
            return CommandResponse(
                input=text,
                type="domotica",
                level=1,
                calls=executed,
                response="Fatto." if all_ok else "Eseguito parzialmente.",
                success=all_ok
            )
        if qr['status'] == "ambiguous":
            return CommandResponse(
                input=text,
                type="domotica",
                level=1,
                response=qr['message'],
                success=False
            )

    # Step 2 — NLP non sicuro → Ollama decide
    decision, _ = call_local_router(text, OLLAMA_URL, OLLAMA_MODEL)

    if decision == "DOMOTICA":
        # Livello 3 — fallback LLM domotica
        return CommandResponse(
            input=text,
            type="domotica",
            level=3,
            response=_llm_domotica_fallback(text),
            success=False
        )

    # Generica
    return CommandResponse(
        input=text,
        type="generica",
        response=_llm_generica(text),
        success=True
    )

# ── Helpers ────────────────────────────────────────────────────────────────────
def _execute_ha(entity_id: str, service: str, service_data: dict = {}) -> bool:
    try:
        domain, svc = service.split(".", 1)
        url     = f"{HA_URL}/api/services/{domain}/{svc}"
        headers = {"Authorization": f"Bearer {HA_TOKEN}",
                   "Content-Type": "application/json"}
        payload = {"entity_id": entity_id, **service_data}
        r = requests.post(url, json=payload, headers=headers, timeout=5)
        return r.status_code in (200, 201)
    except Exception as e:
        print(f"[Vicky] Errore HA: {e}")
        return False

def _llm_generica(text: str) -> str:
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": text, "stream": False},
            timeout=30
        )
        return r.json().get("response", "Non ho capito.").strip()
    except Exception as e:
        return f"Errore LLM: {e}"

def _llm_domotica_fallback(text: str) -> str:
    prompt = (
        f"Sei Vicky, assistente domotico CHAOS. "
        f"Non ho trovato il dispositivo per: '{text}'. "
        f"Rispondi brevemente in italiano."
    )
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=30
        )
        return r.json().get("response", "Dispositivo non trovato.").strip()
    except Exception as e:
        return f"Errore LLM: {e}"

def _resolve_by_ids(area_id: str | None, device_id: str | None, command_id: str | None) -> dict:
    """Risolve device+command direttamente per node_id nel grafo."""
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            if device_id and command_id and area_id:
                rows = list(s.run("""
                    MATCH (d:Device)-[:INSTANCE_OF]->(:Archetype {id: $arch})
                    MATCH (d)-[:BELONGS]->(:Area {id: $area})
                    MATCH (d)-[:HAS_COMMAND]->(c:Command)
                    MATCH (c)-[:HAS_ALIAS]->(a:Alias {value: $cmd})
                    WHERE c.ha_service_key STARTS WITH split(d.ha_entity_id, '.')[0]
                    RETURN d.ha_entity_id as eid, c.ha_service_key as svc
                    LIMIT 1
                """, arch=device_id, area=area_id, cmd=command_id))
            elif device_id and command_id:
                rows = list(s.run("""
                    MATCH (d:Device)-[:INSTANCE_OF]->(:Archetype {id: $arch})
                    MATCH (d)-[:HAS_COMMAND]->(c:Command)
                    MATCH (c)-[:HAS_ALIAS]->(a:Alias {value: $cmd})
                    WHERE c.ha_service_key STARTS WITH split(d.ha_entity_id, '.')[0]
                    RETURN d.ha_entity_id as eid, c.ha_service_key as svc
                    LIMIT 1
                """, arch=device_id, cmd=command_id))
            elif device_id:
                rows = list(s.run("""
                    MATCH (arch:Archetype {id: $arch})
                    MATCH (d:Device)-[:INSTANCE_OF]->(arch)
                    MATCH (d)-[:HAS_COMMAND]->(c:Command {id: arch.default_command})
                    RETURN d.ha_entity_id as eid, c.ha_service_key as svc
                """, arch=device_id))
            else:
                return {"status": "ambiguous", "message": "Slot insufficienti.", "calls": []}

        if not rows:
            return {"status": "not_found", "message": "Nessun device trovato.", "calls": []}

        if len(rows) > 1:
            return {
                "status": "ambiguous",
                "message": f"Trovati {len(rows)} dispositivi. Specifica la stanza.",
                "calls": []
            }

        row = rows[0]
        parts = row["svc"].split(".")
        service = f"{parts[0]}.{parts[1]}"
        return {
            "status": "ok",
            "calls": [{"entity_id": row["eid"], "service": service, "service_data": {}}]
        }
    finally:
        driver.close()