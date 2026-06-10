import { useState, useEffect } from "react"

const VICKY_URL = "http://vicky.chaos.home"

export default function RulesPanel() {
  const [rules, setRules] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchRules()
    const interval = setInterval(fetchRules, 60000) // aggiorna ogni minuto
    return () => clearInterval(interval)
  }, [])

  async function fetchRules() {
    try {
      const res = await fetch(`${VICKY_URL}/rules`)
      const data = await res.json()
      setRules(data.rules || [])
      setError(null)
    } catch (e) {
      setError("Errore connessione Vicky")
    } finally {
      setLoading(false)
    }
  }

  function confidenceColor(c) {
    if (c >= 0.8) return "#00E5A0"
    if (c >= 0.5) return "#FFB347"
    return "#FF4B6E"
  }

  function confidenceLabel(c) {
    if (c >= 0.8) return "Alta"
    if (c >= 0.5) return "Media"
    return "Bassa"
  }

  return (
    <div style={{
      background: "#0A0A1A", color: "#E8E8FF",
      fontFamily: "'Segoe UI', sans-serif",
      padding: "12px", minHeight: "100vh",
    }}>
      <div style={{
        display: "flex", alignItems: "center",
        gap: 8, marginBottom: 12,
        borderBottom: "1px solid #1E1E4A", paddingBottom: 10
      }}>
        <span style={{ fontSize: 18 }}>🧠</span>
        <span style={{ fontWeight: 600, fontSize: 14, color: "#00B4D8" }}>
          Abitudini di Vicky
        </span>
        <span style={{
          marginLeft: "auto", fontSize: 11,
          color: "#666699", cursor: "pointer"
        }} onClick={fetchRules}>↻ Aggiorna</span>
      </div>

      {loading && (
        <div style={{ color: "#666699", fontSize: 13, textAlign: "center", padding: 20 }}>
          Caricamento...
        </div>
      )}

      {error && (
        <div style={{ color: "#FF4B6E", fontSize: 12, padding: 8 }}>
          {error}
        </div>
      )}

      {!loading && !error && rules.length === 0 && (
        <div style={{ color: "#666699", fontSize: 13, textAlign: "center", padding: 20 }}>
          Nessuna regola appresa ancora.
          <br />
          <span style={{ fontSize: 11 }}>Vicky impara dalle tue abitudini nel tempo.</span>
        </div>
      )}

      {rules.map(rule => (
        <div key={rule.id} style={{
          background: "#12122A", border: "1px solid #1E1E4A",
          borderRadius: 8, padding: "10px 12px", marginBottom: 8,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 12, color: "#9999CC" }}>
              {rule.tipo === "abitudine" ? "⏰" : "⚡"} {rule.trigger}
            </span>
            <span style={{
              fontSize: 11, padding: "2px 8px", borderRadius: 10,
              background: `${confidenceColor(rule.confidenza)}22`,
              color: confidenceColor(rule.confidenza),
            }}>
              {confidenceLabel(rule.confidenza)} {Math.round(rule.confidenza * 100)}%
            </span>
          </div>
          <div style={{ fontSize: 13, color: "#E8E8FF", marginTop: 4 }}>
            → {rule.azione}
          </div>
          <div style={{ fontSize: 11, color: "#666699", marginTop: 4 }}>
            {rule.osservazioni} osservazioni · {rule.attiva ? "✓ Attiva" : "✗ Inattiva"}
          </div>
        </div>
      ))}

      <style>{`
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: #0A0A1A; }
        ::-webkit-scrollbar-thumb { background: #1E1E4A; border-radius: 2px; }
      `}</style>
    </div>
  )
}