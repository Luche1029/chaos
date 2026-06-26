const BASE = "http://vicky.chaos.home";

export async function sendCommand(text) {
  const res = await fetch(`${BASE}/command`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error(`/command ${res.status}`);
  return res.json();            // { response: "Fatto, luce accesa", ... }
}

export async function synthesize(text) {
  const res = await fetch(`${BASE}/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error(`/tts ${res.status}`);

  const data = await res.json();              // { audio: base64, cues: {mouthCues:[...]} }
  // base64 → Blob wav
  const bytes = atob(data.audio);
  const arr = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
  const blob = new Blob([arr], { type: "audio/wav" });

  return { blob, cues: data.cues || { mouthCues: [] } };
}

export async function transcribe(blob) {
  const form = new FormData();
  form.append("audio_file", blob, "speech.webm");
  const res = await fetch(`${BASE}/stt`, { method: "POST", body: form });
  if (!res.ok) {
    const detail = await res.text();          // FastAPI dice quale campo manca/è sbagliato
    throw new Error(`/stt ${res.status}: ${detail}`);
  }
  const data = await res.json();
  return data.text;
}

export async function getHistory(limit = 50, days = 7) {
  const res = await fetch(`${BASE}/history?limit=${limit}&days=${days}`);
  if (!res.ok) throw new Error(`/history ${res.status}`);
  const data = await res.json();
  return data.items;
}

export async function sendWakeSample(blob, label = "vicky") {
  const fd = new FormData();
  fd.append("audio_file", blob, "sample.webm");   // il campo DEVE chiamarsi audio_file
  const r = await fetch(`${BASE}/wakeword/sample?label=${encodeURIComponent(label)}`, {
    method: "POST",
    body: fd,
  });
  if (!r.ok) throw new Error(`sample ${r.status}`);
  return r.json();
}

export async function getWakeVocab() {
  const r = await fetch(`${BASE}/wakeword/vocab`);
  if (!r.ok) throw new Error(`vocab ${r.status}`);
  return r.json();
}