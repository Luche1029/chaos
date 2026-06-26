import { useState, useRef, useEffect } from "react";
import { speak, setupVickyEvents  } from "../services/unityBridge";
import { sendCommand, synthesize, transcribe } from "../services/vickyApi";
import { decodeAndEnvelope, playBuffer } from "../services/audioEnvelope";
import { startRecording } from "../services/recorder";

export default function ChatOverlay() {
  const [text, setText] = useState("");
  const [subtitle, setSubtitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const recorderRef = useRef(null);

  const pendingSubtitle = useRef("");
  useEffect(() => {
    setupVickyEvents({
      speaking_started: () => setSubtitle(pendingSubtitle.current),
      speaking_ended:   () => setSubtitle(""),
    });
  }, []);

  // pipeline condivisa (niente guardia: la gestiscono i chiamanti)
  async function respond(userText) {
    const { response } = await sendCommand(userText);    
    const { blob, cues } = await synthesize(response);   
    const audioUrl = URL.createObjectURL(blob);

    pendingSubtitle.current = response;   
    speak(audioUrl, cues);                                
  }

  async function submitText() {
    const t = text.trim();
    if (!t || busy) return;
    setText("");
    setBusy(true);
    try { await respond(t); }
    catch (e) { console.error(e); setSubtitle("Errore: " + e.message); }
    finally { setBusy(false); }
  }

  async function toggleMic() {
    if (busy) return;
    if (!recording) {                         // inizia ad ascoltare
      recorderRef.current = await startRecording();
      setRecording(true);
      return;
    }
    setRecording(false);                      // ferma → trascrivi → rispondi
    setBusy(true);
    try {
      const blob = await recorderRef.current.stop();
      recorderRef.current = null;
      const userText = await transcribe(blob);
      setSubtitle("Tu: " + userText);
      await respond(userText);
    } catch (e) { console.error(e); setSubtitle("Errore: " + e.message);  }
    finally { setBusy(false); }
  }

  const stop = (e) => e.stopPropagation();

  return (
    <div className="chat">
      <div className="chat-log">
        {subtitle && <div className="chat-subtitle">{subtitle}</div>}
      </div>
      <div className="chat-input" onClick={stop}>
        <button
          className={recording ? "mic recording" : "mic"}
          onClick={(e) => { stop(e); toggleMic(); }}
          disabled={busy}
        >
          {recording ? "● Stop" : "Parla"}
        </button>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onClick={stop}
          onKeyDown={(e) => e.key === "Enter" && submitText()}
          placeholder="Scrivi a Vicky…"
          disabled={busy || recording}
        />
        <button onClick={(e) => { stop(e); submitText(); }} disabled={busy || recording}>Invia</button>
      </div>
    </div>
  );
}