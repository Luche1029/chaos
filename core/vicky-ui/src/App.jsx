import { useState, useRef, useEffect } from "react"

const VICKY_URL = "http://vicky.chaos.home"

const styles = {
  app: {
    display: "flex", flexDirection: "column", height: "100vh",
    background: "#0A0A1A", color: "#E8E8FF",
    fontFamily: "'Segoe UI', sans-serif", overflow: "hidden",
  },
  header: {
    padding: "16px 20px", borderBottom: "1px solid #1E1E4A",
    display: "flex", alignItems: "center", gap: "12px", background: "#080818",
  },
  avatar: {
    width: 40, height: 40, borderRadius: "50%",
    background: "linear-gradient(135deg, #00B4D8, #7B2FBE)",
    display: "flex", alignItems: "center", justifyContent: "center",
    fontSize: 20, flexShrink: 0,
  },
  headerTitle: { fontWeight: 600, fontSize: 16, color: "#E8E8FF", margin: 0 },
  headerStatus: (active) => ({
    fontSize: 12, color: active ? "#FF4B6E" : "#00E5A0", margin: 0
  }),
  messages: {
    flex: 1, overflowY: "auto", padding: "20px",
    display: "flex", flexDirection: "column", gap: "12px",
  },
  bubbleWrap: (isUser) => ({
    alignSelf: isUser ? "flex-end" : "flex-start", maxWidth: "80%"
  }),
  bubble: (isUser) => ({
    background: isUser ? "linear-gradient(135deg, #00B4D8, #0090B0)" : "#12122A",
    border: isUser ? "none" : "1px solid #1E1E4A",
    borderRadius: isUser ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
    padding: "10px 16px", fontSize: 14, lineHeight: 1.5, color: "#E8E8FF",
  }),
  time: { fontSize: 11, color: "#666699", marginTop: 4, textAlign: "right" },
  badge: (ok) => ({
    display: "inline-block", fontSize: 11, padding: "2px 8px",
    borderRadius: 10, marginTop: 6,
    background: ok ? "rgba(0,229,160,0.15)" : "rgba(255,75,110,0.15)",
    color: ok ? "#00E5A0" : "#FF4B6E",
  }),
  typing: {
    alignSelf: "flex-start", background: "#12122A",
    border: "1px solid #1E1E4A", borderRadius: "18px 18px 18px 4px",
    padding: "12px 16px", display: "flex", gap: 6, alignItems: "center",
  },
  inputArea: {
    padding: "16px 20px", borderTop: "1px solid #1E1E4A",
    background: "#080818", display: "flex", gap: "10px", alignItems: "flex-end",
  },
  input: {
    flex: 1, background: "#12122A", border: "1px solid #1E1E4A",
    borderRadius: 24, padding: "10px 18px", color: "#E8E8FF",
    fontSize: 14, outline: "none", resize: "none",
    fontFamily: "inherit", lineHeight: 1.5, maxHeight: 120, overflowY: "auto",
  },
  btn: (color, disabled) => ({
    width: 42, height: 42, borderRadius: "50%",
    background: disabled ? "#1A1A3E" : color,
    border: disabled ? "1px solid #333355" : "none",
    cursor: disabled ? "not-allowed" : "pointer",
    display: "flex", alignItems: "center", justifyContent: "center",
    flexShrink: 0, fontSize: 18, transition: "all 0.2s",
    opacity: disabled ? 0.4 : 1,
  }),
}

function formatTime(d) {
  return d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })
}

// ── Abilita/disabilita bottoni wake word ───────────────────────────────────────
const SERVER_WAKE_ENABLED = false  // ← true quando modello custom è pronto
const BROWSER_WAKE_ENABLED = true

export default function App() {
  const [messages, setMessages] = useState([{
    id: 1, role: "vicky",
    text: "Ciao! Sono Vicky, l'assistente di CHAOS. Come posso aiutarti?",
    time: new Date(),
  }])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [listening, setListening] = useState(false)
  const [recording, setRecording] = useState(false)
  const [wakeActive, setWakeActive] = useState(false)
  const [wakeMode, setWakeMode] = useState(null) // 'server' | 'browser' | null
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const chunksRef = useRef([])
  const wakeRecorderRef = useRef(null)
  const wakeStreamRef = useRef(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, loading])

  useEffect(() => {
    return () => {
      stopWake()
    }
  }, [])

  function stopWake() {
    if (wakeRecorderRef.current) {
      try { wakeRecorderRef.current.stop() } catch {}
      wakeRecorderRef.current = null
    }
    wakeStreamRef.current?.getTracks().forEach(t => t.stop())
    wakeStreamRef.current = null
    setWakeActive(false)
    setWakeMode(null)
  }

  async function sendText(text) {
    if (!text.trim() || loading) return
    const userMsg = { id: Date.now(), role: "user", text, time: new Date() }
    setMessages(prev => [...prev, userMsg])
    setInput("")
    setLoading(true)
    try {
      const res = await fetch(`${VICKY_URL}/command`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      })
      const data = await res.json()
      const responseText = data.response || "Non ho capito."
      const badge = data.type === "domotica" && data.calls?.length > 0
        ? { success: data.success, text: data.success ? `✓ ${data.calls[0].entity_id}` : "✗ Errore" }
        : null
      setMessages(prev => [...prev, {
        id: Date.now() + 1, role: "vicky",
        text: responseText, time: new Date(), badge,
      }])
      playTTS(responseText)
    } catch {
      setMessages(prev => [...prev, {
        id: Date.now() + 1, role: "vicky",
        text: "Errore di connessione.", time: new Date(),
      }])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  async function playTTS(text) {
    try {
      const res = await fetch(`${VICKY_URL}/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      })
      if (!res.ok) return
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      audio.play()
      audio.onended = () => URL.revokeObjectURL(url)
    } catch (e) {
      console.error("TTS error:", e)
    }
  }

  async function toggleMic() {
    if (recording) {
      if (mediaRecorderRef.current?._silenceDetector) {
        clearInterval(mediaRecorderRef.current._silenceDetector)
      }
      if (mediaRecorderRef.current?._audioContext) {
        const ctx = mediaRecorderRef.current._audioContext
        if (ctx.state !== "closed") ctx.close()
      }
      mediaRecorderRef.current?.stop()
      setRecording(false)
      setListening(false)
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mediaRecorder = new MediaRecorder(stream)
      mediaRecorderRef.current = mediaRecorder
      chunksRef.current = []

      mediaRecorder.ondataavailable = e => chunksRef.current.push(e.data)
      mediaRecorder.onstop = async () => {
        if (mediaRecorderRef.current?._silenceDetector) {
          clearInterval(mediaRecorderRef.current._silenceDetector)
        }
        if (mediaRecorderRef.current?._audioContext) {
          const ctx = mediaRecorderRef.current._audioContext
          if (ctx.state !== "closed") ctx.close()
        }
        const blob = new Blob(chunksRef.current, { type: "audio/webm" })
        stream.getTracks().forEach(t => t.stop())
        await transcribeAudio(blob)
      }

      mediaRecorder.start()
      setRecording(true)
      setListening(true)

      // Rilevamento silenzio automatico
      const audioContext = new AudioContext()
      const source = audioContext.createMediaStreamSource(stream)
      const analyser = audioContext.createAnalyser()
      analyser.fftSize = 2048
      source.connect(analyser)

      const bufferLength = analyser.frequencyBinCount
      const dataArray = new Uint8Array(bufferLength)
      let silenceStart = null
      const SILENCE_THRESHOLD = 10
      const SILENCE_DURATION = 2000 // 2 secondi di silenzio → stop automatico

      const silenceDetector = setInterval(() => {
        if (!mediaRecorderRef.current) {
          clearInterval(silenceDetector)
          return
        }
        analyser.getByteFrequencyData(dataArray)
        const avg = dataArray.reduce((a, b) => a + b, 0) / bufferLength

        if (avg < SILENCE_THRESHOLD) {
          if (!silenceStart) silenceStart = Date.now()
          else if (Date.now() - silenceStart > SILENCE_DURATION) {
            clearInterval(silenceDetector)
            audioContext.close()
            if (mediaRecorder.state === "recording") {
              mediaRecorder.stop()
              setRecording(false)
              setListening(false)
            }
          }
        } else {
          silenceStart = null
        }
      }, 100)

      mediaRecorderRef.current._silenceDetector = silenceDetector
      mediaRecorderRef.current._audioContext = audioContext

    } catch (e) {
      console.error("Mic error:", e)
    }
  }

  async function transcribeAudio(blob) {
    setLoading(true)
    try {
      const formData = new FormData()
      formData.append("audio_file", blob, "recording.wav")
      const res = await fetch(`${VICKY_URL}/stt`, { method: "POST", body: formData })
      const data = await res.json()
      if (data.text) await sendText(data.text)
    } catch (e) {
      console.error("STT error:", e)
    } finally {
      setLoading(false)
    }
  }

  // ── Wake word SERVER (modello custom openWakeWord) ─────────────────────────
async function onWakeDetected(commandAfterWake = "") {
  stopWake()

  if (commandAfterWake.length > 3) {
    // Comando nella stessa frase — esegui direttamente
    setMessages(prev => [...prev, {
      id: Date.now(), role: "user",
      text: commandAfterWake, time: new Date(),
    }])
    await sendText(commandAfterWake)
    return
  }

  // Solo wake word — avvia microfono e aspetta 800ms
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  const mediaRecorder = new MediaRecorder(stream)
  mediaRecorderRef.current = mediaRecorder
  chunksRef.current = []

  mediaRecorder.ondataavailable = e => chunksRef.current.push(e.data)
  mediaRecorder.onstop = async () => {
    if (mediaRecorderRef.current?._silenceDetector) {
      clearInterval(mediaRecorderRef.current._silenceDetector)
    }
    if (mediaRecorderRef.current?._audioContext) {
      const ctx = mediaRecorderRef.current._audioContext
      if (ctx.state !== "closed") ctx.close()
    }
    const blob = new Blob(chunksRef.current, { type: "audio/webm" })
    stream.getTracks().forEach(t => t.stop())
    await transcribeAudio(blob)
  }

  mediaRecorder.start()
  setRecording(true)
  setListening(true)

  // Aspetta 800ms — controlla se c'è audio
  const audioContext = new AudioContext()
  const source = audioContext.createMediaStreamSource(stream)
  const analyser = audioContext.createAnalyser()
  analyser.fftSize = 2048
  source.connect(analyser)
  const bufferLength = analyser.frequencyBinCount
  const dataArray = new Uint8Array(bufferLength)
  mediaRecorderRef.current._audioContext = audioContext

  await new Promise(r => setTimeout(r, 800))

  // Controlla se c'è audio dopo 800ms
  analyser.getByteFrequencyData(dataArray)
  const avg = dataArray.reduce((a, b) => a + b, 0) / bufferLength
  const hasAudio = avg > 10

  if (hasAudio) {
    // C'è audio — continua ad ascoltare fino al silenzio
    let silenceStart = null
    const silenceDetector = setInterval(() => {
      analyser.getByteFrequencyData(dataArray)
      const avg = dataArray.reduce((a, b) => a + b, 0) / bufferLength
      if (avg < 10) {
        if (!silenceStart) silenceStart = Date.now()
        else if (Date.now() - silenceStart > 2000) {
          clearInterval(silenceDetector)
          if (audioContext.state !== "closed") audioContext.close()
          if (mediaRecorder.state === "recording") {
            mediaRecorder.stop()
            setRecording(false)
            setListening(false)
          }
        }
      } else {
        silenceStart = null
      }
    }, 100)
    mediaRecorderRef.current._silenceDetector = silenceDetector

  } else {
    // Nessun audio — spegni microfono, parla, poi riascolta
    if (mediaRecorder.state === "recording") mediaRecorder.stop()
    if (audioContext.state !== "closed") audioContext.close()
    setRecording(false)
    setListening(false)

    // Vicky parla
    setMessages(prev => [...prev, {
      id: Date.now(), role: "vicky",
      text: "Sì? Ti ascolto...", time: new Date(),
    }])

    await new Promise((resolve) => {
      fetch(`${VICKY_URL}/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: "Sì, ti ascolto" }),
      })
      .then(res => res.blob())
      .then(blob => {
        const url = URL.createObjectURL(blob)
        const audio = new Audio(url)
        audio.onended = () => { URL.revokeObjectURL(url); resolve() }
        audio.onerror = () => resolve()
        audio.play()
      })
      .catch(() => resolve())
    })

    // Dopo 500ms riavvia microfono
    await new Promise(r => setTimeout(r, 500))
    await toggleMic()
  }
}

async function toggleWakeWordBrowser() {
  if (wakeActive && wakeMode === "browser") { stopWake(); return }

  if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
    alert("Web Speech API non supportata. Usa Chrome.")
    return
  }

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
  const recognition = new SpeechRecognition()
  recognition.lang = "it-IT"
  recognition.continuous = true
  recognition.interimResults = false  // solo risultati finali
  recognition.maxAlternatives = 1

  let triggered = false

  recognition.onresult = async (event) => {
    if (triggered) return

    for (let i = event.resultIndex; i < event.results.length; i++) {
      if (!event.results[i].isFinal) continue  // ignora risultati intermedi
      
      const transcript = event.results[i][0].transcript.toLowerCase().trim()
      console.log("[Wake Browser] Finale:", transcript)

      const wakeWords = [
        "vicky", "ehi vicky", "hey vicky", "ok vicky", "ciao vicky",
        "wiki", "wicky", "bicky", "vickie", "viki",
        "picchi", "bichi", "biki", "ricky", "picki",
        "ehi picchi", "ehi bichi", "ehi biki", "ehi ricky"
      ]

      const wakeFound = wakeWords.find(w => transcript.includes(w))

      if (wakeFound) {
        triggered = true
        recognition.stop()
        wakeRecorderRef.current = null

        // Estrai comando dopo la wake word
        const afterWake = transcript.split(wakeFound).pop().trim()
        console.log("[Wake Browser] Comando:", afterWake)
        await onWakeDetected(afterWake)
        return
      }
    }
  }

  recognition.onerror = (e) => {
    if (e.error === "no-speech") return  // normale, ignora
    console.error("[Wake Browser] Errore:", e.error)
    stopWake()
  }

  recognition.onend = () => {
    if (wakeRecorderRef.current && !triggered) {
      try { recognition.start() } catch(e) {}
    }
  }

  recognition.start()
  wakeRecorderRef.current = recognition
  setWakeActive(true)
  setWakeMode("browser")
}

  // ── Wake word BROWSER (Web Speech API) ────────────────────────────────────
async function toggleWakeWordBrowser() {
    if (wakeActive && wakeMode === "browser") { stopWake(); return }

    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
      alert("Web Speech API non supportata. Usa Chrome.")
      return
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    const recognition = new SpeechRecognition()
    recognition.lang = "it-IT"
    recognition.continuous = true
    recognition.interimResults = true
    recognition.maxAlternatives = 3

    let triggered = false  // evita trigger multipli

    recognition.onresult = async (event) => {
      if (triggered) return  // già triggerato, ignora

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript.toLowerCase().trim()
        console.log("[Wake Browser] Sentito:", transcript)

        const wakeWords = [
          "vicky", "ehi vicky", "hey vicky", "ok vicky", "ciao vicky",
          "wiki", "wicky", "bicky", "vickie", "viki",
          "picchi", "bichi", "biki", "ricky", "picki",
          "ehi picchi", "ehi bichi", "ehi biki", "ehi ricky"
        ]

        const wakeFound = wakeWords.find(w => transcript.includes(w))

        if (wakeFound) {
          triggered = true
          recognition.stop()
          wakeRecorderRef.current = null

          // Estrai eventuale comando dopo la wake word
          const afterWake = transcript.split(wakeFound).pop().trim()
          console.log("[Wake Browser] Comando dopo wake word:", afterWake)

          await onWakeDetected()

          // Se c'è già un comando nella stessa frase, eseguilo direttamente
          if (afterWake.length > 3) {
            setTimeout(() => {
              setRecording(false)
              setListening(false)
              sendText(afterWake)
            }, 500)
          }
          return
        }
      }
    }

    recognition.onerror = (e) => {
      console.error("[Wake Browser] Errore:", e.error)
      if (e.error !== "no-speech") stopWake()
    }

    recognition.onend = () => {
      if (wakeRecorderRef.current && !triggered) recognition.start()
    }

    recognition.start()
    wakeRecorderRef.current = recognition
    setWakeActive(true)
    setWakeMode("browser")
  }

  function handleKey(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      sendText(input)
    }
  }

  const isWakeServer = wakeActive && wakeMode === "server"
  const isWakeBrowser = wakeActive && wakeMode === "browser"

  return (
    <div style={styles.app}>
      <div style={styles.header}>
        <div style={styles.avatar}>🤖</div>
        <div style={{ flex: 1 }}>
          <p style={styles.headerTitle}>Vicky</p>
          <p style={styles.headerStatus(listening || wakeActive || recording)}>
            {recording ? "● In ascolto comando..."
              : isWakeServer ? "● Wake word server attivo..."
              : isWakeBrowser ? "● In attesa: 'Ehi Vicky'..."
              : "● Online"}
          </p>
        </div>
      </div>

      <div style={styles.messages}>
        {messages.map(msg => (
          <div key={msg.id} style={styles.bubbleWrap(msg.role === "user")}>
            <div style={styles.bubble(msg.role === "user")}>
              {msg.text}
              {msg.badge && <div style={styles.badge(msg.badge.success)}>{msg.badge.text}</div>}
            </div>
            <div style={styles.time}>{formatTime(msg.time)}</div>
          </div>
        ))}
        {loading && (
          <div style={styles.typing}>
            {[0,1,2].map(i => (
              <div key={i} style={{
                width: 8, height: 8, borderRadius: "50%", background: "#00B4D8",
                animation: `bounce 1.2s ${i*0.2}s infinite`
              }} />
            ))}
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div style={styles.inputArea}>
        <textarea
          ref={inputRef}
          style={styles.input}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Scrivi a Vicky..."
          rows={1}
        />

        {/* Wake word SERVER — disabilitato finché modello non è pronto */}
        <button
          style={styles.btn(
            isWakeServer ? "linear-gradient(135deg, #FF6B35, #CC4400)" : "linear-gradient(135deg, #333355, #222244)",
            !SERVER_WAKE_ENABLED
          )}
          onClick={SERVER_WAKE_ENABLED ? toggleWakeWordServer : undefined}
          disabled={!SERVER_WAKE_ENABLED}
          title={SERVER_WAKE_ENABLED ? "Wake word server (modello custom)" : "Wake word server — modello non ancora addestrato"}
        >
          🧠
        </button>

        {/* Wake word BROWSER — Web Speech API */}
        <button
          style={styles.btn(
            isWakeBrowser ? "linear-gradient(135deg, #00E5A0, #009966)" : "linear-gradient(135deg, #333355, #222244)",
            !BROWSER_WAKE_ENABLED
          )}
          onClick={BROWSER_WAKE_ENABLED ? toggleWakeWordBrowser : undefined}
          disabled={!BROWSER_WAKE_ENABLED}
          title="Wake word browser (Web Speech API) — dì 'Ehi Vicky'"
        >
          {isWakeBrowser ? "👂" : "🔇"}
        </button>

        {/* Microfono manuale */}
        <button
          style={styles.btn(
            recording ? "linear-gradient(135deg, #FF4B6E, #CC0033)" : "linear-gradient(135deg, #7B2FBE, #5A1F9E)",
            loading
          )}
          onClick={toggleMic}
          disabled={loading}
          title={recording ? "Ferma registrazione" : "Parla con Vicky"}
        >
          {recording ? "⏹" : "🎤"}
        </button>

        {/* Invia testo */}
        <button
          style={styles.btn("linear-gradient(135deg, #00B4D8, #7B2FBE)", !input.trim() || loading)}
          onClick={() => sendText(input)}
          disabled={!input.trim() || loading}
        >
          ➤
        </button>
      </div>

      <style>{`
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: #0A0A1A; }
        ::-webkit-scrollbar-thumb { background: #1E1E4A; border-radius: 2px; }
        @keyframes bounce {
          0%, 60%, 100% { transform: translateY(0); }
          30% { transform: translateY(-8px); }
        }
      `}</style>
    </div>
  )
}