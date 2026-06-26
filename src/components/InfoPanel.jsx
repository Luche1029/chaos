import { useEffect, useState } from "react";
import { getHistory } from "../services/vickyApi";

export default function InfoPanel() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    getHistory()
      .then(setItems)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const fmt = (iso) =>
    new Date(iso).toLocaleString("it-IT",
      { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

  return (
    <div className="info-panel">
      <h3 className="info-title">Cronologia interventi</h3>
      {loading && <p className="info-empty">Carico…</p>}
      {error && <p className="info-empty">Errore: {error}</p>}
      {!loading && !error && items.length === 0 && <p className="info-empty">Nessun intervento ancora.</p>}
      <ul className="info-list">
        {items.map((it, i) => (
          <li key={i} className="info-item">
            <span className="info-time">{fmt(it.time)}</span>
            <span className="info-action">{it.command} · {it.device} <em>({it.area})</em></span>
            {it.text && <span className="info-text">“{it.text}”</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}