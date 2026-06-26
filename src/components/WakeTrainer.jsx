import { useEffect, useRef, useState } from "react";
import { sendWakeSample, getWakeVocab } from "../services/vickyApi";

const TARGET = 40;       // obiettivo campioni
const CLIP_MS = 1400;    // durata finestra di registrazione

export default function WakeTrainer({ label = "vicky" }) {
  const [busy, setBusy]   = useState(false);
  const [last, setLast]   = useState(null);
  const [vocab, setVocab] = useState({ total: 0, vocab: [] });
  const [error, setError] = useState(null);
  const streamRef = useRef(null);

  useEffect(() => {
    getWakeVocab().then(setVocab).catch(() => {});
    return () => streamRef.current?.getTracks().forEach(t => t.stop());
  }, []);

  async function getStream() {
    if (!streamRef.current) {
      streamRef.current = await navigator.mediaDevices.getUserMedia({ audio: true });
    }
    return streamRef.current;
  }

  async function recordOne() {
    setError(null); setBusy(true);
    try {
      const stream = await getStream();
      const rec = new MediaRecorder(stream);
      const chunks = [];
      rec.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
      const stopped = new Promise((res) => { rec.onstop = res; });
      rec.start();
      await new Promise(r => setTimeout(r, CLIP_MS));
      rec.stop();
      await stopped;
      const blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
      const result = await sendWakeSample(blob, label);
      setLast(result);
      setVocab(await getWakeVocab());
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  const pct = Math.min(100, Math.round((vocab.total / TARGET) * 100));

  return (
    <div style={{
      background: "#0b1220", border: "1px solid #1e3a5f", borderRadius: 12,
      padding: 16, color: "#cfe8ff", fontFamily: "system-ui, sans-serif", maxWidth: 420
    }}>
      <div style={{ fontWeight: 600, color: "#5ad1ff", marginBottom: 8 }}>
        Addestramento wake word · “{label}”
      </div>

      <div style={{ height: 8, background: "#13243d", borderRadius: 6, overflow: "hidden", marginBottom: 6 }}>
        <div style={{ height: "100%", width: `${pct}%`, background: "#2aa9e0", transition: "width .2s" }} />
      </div>
      <div style={{ fontSize: 13, opacity: .8, marginBottom: 12 }}>
        {vocab.total} / {TARGET} campioni
      </div>

      <button
        onClick={recordOne}
        disabled={busy}
        style={{
          width: "100%", padding: "10px 14px", borderRadius: 8, border: "none",
          background: busy ? "#244" : "#2aa9e0", color: "#001018",
          fontWeight: 600, cursor: busy ? "default" : "pointer"
        }}>
        {busy ? "Registrazione…" : `Registra campione (${(CLIP_MS/1000).toFixed(1)}s)`}
      </button>

      {error && <div style={{ color: "#ff7a7a", marginTop: 8, fontSize: 13 }}>Errore: {error}</div>}

      {last && (
        <div style={{ marginTop: 12, fontSize: 13 }}>
          Ultimo: <b>{last.file}</b><br />
          STT (en) → <i>{last.transcription || "(vuoto)"}</i> → <code>{last.norm || "—"}</code>
        </div>
      )}

      {vocab.vocab.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <div style={{ fontSize: 12, opacity: .7, marginBottom: 4 }}>Grafie raccolte</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: "2px 12px", fontSize: 13 }}>
            {vocab.vocab.map((v) => (
              <>
                <span key={`g-${v.grafia}`} style={{ fontFamily: "monospace" }}>{v.grafia || "(vuoto)"}</span>
                <span key={`c-${v.grafia}`} style={{ opacity: .7 }}>{v.count}</span>
              </>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}