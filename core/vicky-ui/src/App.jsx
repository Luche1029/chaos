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
  headerStatus: (listening) => ({
    fontSize: 12, color: listening ? "#FF4B6E" : "#00E5A0", margin: 0
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
    background: disabled ? "#333355" : color,
    border: "none", cursor: disabled ? "not-allowed" : "pointer",
    display: "flex", alignItems: "center", justifyContent: "center",
    flexShrink: 0, fontSize: 18, transition: "all 0.2s",
  }),
}

function formatTime(d) {
  return d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })
}

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
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const chunksRef = useRef([])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, loading])

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

      // TTS — riproduci risposta vocale
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
      // Stop registrazione
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
        const blob = new Blob(chunksRef.current, { type: "audio/webm" })
        stream.getTracks().forEach(t => t.stop())
        await transcribeAudio(blob)
      }

      mediaRecorder.start()
      setRecording(true)
      setListening(true)
    } catch (e) {
      console.error("Mic error:", e)
    }
  }

async function transcribeAudio(blob) {
    console.log("Audio blob:", blob.size, "bytes", blob.type)

    setLoading(true)
    try {
      const formData = new FormData()
      // Forza content type wav anche se il blob è webm
      formData.append("audio_file", blob, "recording.wav")
      
      const res = await fetch(`${VICKY_URL}/stt`, {
        method: "POST",
        body: formData,
      })
      const data = await res.json()
      console.log("STT response:", data)
      if (data.text) {
        await sendText(data.text)
      } else {
        console.warn("STT: testo vuoto", data)
      }
    } catch (e) {
      console.error("STT error:", e)
    } finally {
      setLoading(false)
    }
  }

  function handleKey(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      sendText(input)
    }
  }

  return (
    <div style={styles.app}>
      <div style={styles.header}>
        <div style={styles.avatar}>🤖</div>
        <div style={{ flex: 1 }}>
          <p style={styles.headerTitle}>Vicky</p>
          <p style={styles.headerStatus(listening)}>
            {listening ? "● In ascolto..." : "● Online"}
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