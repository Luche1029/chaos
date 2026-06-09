import { useState, useRef, useEffect } from "react"

const VICKY_URL = "http://vicky.chaos.home/command"

const styles = {
  app: {
    display: "flex",
    flexDirection: "column",
    height: "100vh",
    background: "#0A0A1A",
    color: "#E8E8FF",
    fontFamily: "'Segoe UI', sans-serif",
    overflow: "hidden",
  },
  header: {
    padding: "16px 20px",
    borderBottom: "1px solid #1E1E4A",
    display: "flex",
    alignItems: "center",
    gap: "12px",
    background: "#080818",
  },
  avatar: {
    width: 40,
    height: 40,
    borderRadius: "50%",
    background: "linear-gradient(135deg, #00B4D8, #7B2FBE)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 20,
    flexShrink: 0,
  },
  headerText: {
    flex: 1,
  },
  headerTitle: {
    fontWeight: 600,
    fontSize: 16,
    color: "#E8E8FF",
    margin: 0,
  },
  headerStatus: {
    fontSize: 12,
    color: "#00E5A0",
    margin: 0,
  },
  messages: {
    flex: 1,
    overflowY: "auto",
    padding: "20px",
    display: "flex",
    flexDirection: "column",
    gap: "12px",
  },
  messageBubble: (isUser) => ({
    maxWidth: "80%",
    alignSelf: isUser ? "flex-end" : "flex-start",
    background: isUser
      ? "linear-gradient(135deg, #00B4D8, #0090B0)"
      : "#12122A",
    border: isUser ? "none" : "1px solid #1E1E4A",
    borderRadius: isUser ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
    padding: "10px 16px",
    fontSize: 14,
    lineHeight: 1.5,
    color: "#E8E8FF",
  }),
  messageTime: {
    fontSize: 11,
    color: "#666699",
    marginTop: 4,
    textAlign: "right",
  },
  typingIndicator: {
    alignSelf: "flex-start",
    background: "#12122A",
    border: "1px solid #1E1E4A",
    borderRadius: "18px 18px 18px 4px",
    padding: "12px 16px",
    display: "flex",
    gap: 6,
    alignItems: "center",
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: "50%",
    background: "#00B4D8",
  },
  inputArea: {
    padding: "16px 20px",
    borderTop: "1px solid #1E1E4A",
    background: "#080818",
    display: "flex",
    gap: "10px",
    alignItems: "flex-end",
  },
  input: {
    flex: 1,
    background: "#12122A",
    border: "1px solid #1E1E4A",
    borderRadius: 24,
    padding: "10px 18px",
    color: "#E8E8FF",
    fontSize: 14,
    outline: "none",
    resize: "none",
    fontFamily: "inherit",
    lineHeight: 1.5,
    maxHeight: 120,
    overflowY: "auto",
  },
  sendBtn: (disabled) => ({
    width: 42,
    height: 42,
    borderRadius: "50%",
    background: disabled
      ? "#333355"
      : "linear-gradient(135deg, #00B4D8, #7B2FBE)",
    border: "none",
    cursor: disabled ? "not-allowed" : "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
    fontSize: 18,
    transition: "all 0.2s",
  }),
  resultBadge: (success) => ({
    display: "inline-block",
    fontSize: 11,
    padding: "2px 8px",
    borderRadius: 10,
    background: success ? "rgba(0,229,160,0.15)" : "rgba(255,75,110,0.15)",
    color: success ? "#00E5A0" : "#FF4B6E",
    marginTop: 6,
  }),
}

function formatTime(date) {
  return date.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })
}

export default function App() {
  const [messages, setMessages] = useState([
    {
      id: 1,
      role: "vicky",
      text: "Ciao! Sono Vicky, l'assistente di CHAOS. Come posso aiutarti?",
      time: new Date(),
    },
  ])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, loading])

  async function sendMessage() {
    const text = input.trim()
    if (!text || loading) return

    const userMsg = { id: Date.now(), role: "user", text, time: new Date() }
    setMessages((prev) => [...prev, userMsg])
    setInput("")
    setLoading(true)

    try {
      const res = await fetch(VICKY_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      })
      const data = await res.json()

      let responseText = data.response || "Non ho capito."
      let badge = null

      if (data.type === "domotica" && data.calls?.length > 0) {
        const devices = data.calls.map((c) => c.entity_id).join(", ")
        badge = { success: data.success, text: data.success ? `✓ ${devices}` : `✗ Errore` }
      }

      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          role: "vicky",
          text: responseText,
          time: new Date(),
          badge,
          level: data.level,
          type: data.type,
        },
      ])
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          role: "vicky",
          text: "Errore di connessione con Vicky.",
          time: new Date(),
        },
      ])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  function handleKey(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div style={styles.app}>
      <div style={styles.header}>
        <div style={styles.avatar}>🤖</div>
        <div style={styles.headerText}>
          <p style={styles.headerTitle}>Vicky</p>
          <p style={styles.headerStatus}>● Online</p>
        </div>
      </div>

      <div style={styles.messages}>
        {messages.map((msg) => (
          <div key={msg.id} style={{ alignSelf: msg.role === "user" ? "flex-end" : "flex-start", maxWidth: "80%" }}>
            <div style={styles.messageBubble(msg.role === "user")}>
              {msg.text}
              {msg.badge && (
                <div style={styles.resultBadge(msg.badge.success)}>
                  {msg.badge.text}
                </div>
              )}
            </div>
            <div style={styles.messageTime}>{formatTime(msg.time)}</div>
          </div>
        ))}

        {loading && (
          <div style={styles.typingIndicator}>
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                style={{
                  ...styles.dot,
                  animation: `bounce 1.2s ${i * 0.2}s infinite`,
                }}
              />
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
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Scrivi a Vicky..."
          rows={1}
        />
        <button
          style={styles.sendBtn(!input.trim() || loading)}
          onClick={sendMessage}
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