let api = null;
export function attachUnity(unityApi) { api = unityApi; }
export function isReady() { return !!api; }

export function speak(audioUrl, cues) {
  if (!api) { console.warn("Unity non pronto"); return; }
  const payload = JSON.stringify({
    audioUrl,
    cues: JSON.stringify(cues || { mouthCues: [] }),
  });
  api.sendMessage("Vicky", "Speak", payload);
}

let _handlers = {};

export function setupVickyEvents(handlers = {}) {
  _handlers = { ..._handlers, ...handlers };   // unisce, non sovrascrive
  window.vickyOnEvent = (evt) => {
    _handlers[evt]?.();                          // chiama l'handler giusto se esiste
  };
}