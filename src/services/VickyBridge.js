// Helper React <-> Unity per Vicky.
// Presuppone di avere il riferimento a `unityInstance` (dal loader Unity WebGL).

const VICKY_GO = "Vicky"; // deve combaciare col nome del GameObject in Unity

/**
 * Registra i callback di stato emessi da Unity (window.vickyOnEvent).
 * handlers es: { ready, speaking_started, speaking_ended }
 */
export function setupVickyEvents(handlers = {}) {
  window.vickyOnEvent = (evt) => {
    if (typeof handlers[evt] === "function") handlers[evt]();
  };
}

/**
 * Fa parlare Vicky.
 * ttsResponse: { audioUrl?: string, audioBlob?: Blob, cues: object }
 *   - cues = JSON Rhubarb con { mouthCues: [...] }
 */
export function vickySpeak(unityInstance, ttsResponse) {
  if (!unityInstance) return;

  let audioUrl = ttsResponse.audioUrl;
  if (!audioUrl && ttsResponse.audioBlob) {
    audioUrl = URL.createObjectURL(ttsResponse.audioBlob); // blob: url risolvibile dalla webview
  }

  const payload = JSON.stringify({
    audioUrl,
    cues: JSON.stringify(ttsResponse.cues || { mouthCues: [] }),
  });

  unityInstance.SendMessage(VICKY_GO, "Speak", payload);
}

/**
 * Flusso completo: chiede al backend /tts e fa parlare Vicky.
 * Il backend /tts dovrebbe restituire audio (wav) + cues (timeline Rhubarb).
 */
export async function speakText(unityInstance, text, apiBase = "http://vicky.chaos.home") {
  const res = await fetch(`${apiBase}/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify({ text }),
  });

  const ct = res.headers.get("content-type") || "";

  if (ct.includes("application/json")) {
    // Contratto ideale: { audio_base64 | audio_url, cues: {mouthCues:[...]} }
    const data = await res.json();
    let audioUrl = data.audio_url;
    if (!audioUrl && data.audio_base64) {
      audioUrl = URL.createObjectURL(b64ToBlob(data.audio_base64, "audio/wav"));
    }
    vickySpeak(unityInstance, { audioUrl, cues: data.cues });
  } else {
    // Fallback: il backend ha restituito solo il wav (niente visemi)
    const blob = await res.blob();
    vickySpeak(unityInstance, { audioBlob: blob, cues: { mouthCues: [] } });
  }
}

function b64ToBlob(b64, mime) {
  const bytes = atob(b64);
  const arr = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
  return new Blob([arr], { type: mime });
}