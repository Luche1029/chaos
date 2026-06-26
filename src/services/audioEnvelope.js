let ctx;
const getCtx = () => (ctx ||= new (window.AudioContext || window.webkitAudioContext)());
const FPS = 60;

export async function decodeAndEnvelope(arrayBuffer) {
  const audioCtx = getCtx();
  const buf = await audioCtx.decodeAudioData(arrayBuffer.slice(0)); // copia: decode consuma il buffer
  const ch = buf.getChannelData(0);
  const frame = Math.floor(buf.sampleRate / FPS);
  const env = [];
  for (let i = 0; i < ch.length; i += frame) {
    const end = Math.min(i + frame, ch.length);
    let sum = 0;
    for (let j = i; j < end; j++) sum += ch[j] * ch[j];
    env.push(Math.sqrt(sum / (end - i)));
  }
  let max = 1e-6;
  for (const v of env) if (v > max) max = v;
  return { audioBuffer: buf, envelope: env.map((v) => Math.min(1, v / max)), fps: FPS };
}

export function playBuffer(audioBuffer, onended) {
  const audioCtx = getCtx();
  if (audioCtx.state === "suspended") audioCtx.resume(); // serve un gesto utente (il click)
  const src = audioCtx.createBufferSource();
  src.buffer = audioBuffer;
  src.connect(audioCtx.destination);
  src.onended = onended;
  src.start();
  return src;
}