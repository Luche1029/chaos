import { useState, useCallback, useRef, useLayoutEffect } from "react";
import VickyAvatar from "./components/VickyAvatar";
import ChatOverlay from "./components/ChatOverlay";
import LovelacePanel from "./components/LovelacePanel";
import InfoPanel from "./components/InfoPanel";
import { attachUnity } from "./services/unityBridge";
import "./App.css";

const DURATION = 260;
const EASING = "cubic-bezier(0.4, 0, 0.2, 1)";
const isElectron = import.meta.env.VITE_MODE === 'electron';

export default function App() {
  const [expanded, setExpanded] = useState(false);
  const infoRef = useRef(null);
  const firstRect = useRef(null);

  const handleUnityReady = useCallback((unityApi) => { attachUnity(unityApi); }, []);

  const expand = () => {
    firstRect.current = infoRef.current.getBoundingClientRect();
    setExpanded(true);
  };

  const collapse = (e) => {
    e?.stopPropagation?.();
    const el = infoRef.current;
    if (!el) { setExpanded(false); return; }
    const last = el.getBoundingClientRect();
    const f = firstRect.current;
    el.style.transformOrigin = "top left";
    const anim = el.animate(
      [{ transform: "none" },
       { transform: `translate(${f.left - last.left}px, ${f.top - last.top}px) scale(${f.width / last.width}, ${f.height / last.height})` }],
      { duration: DURATION, easing: EASING }
    );
    anim.onfinish = () => setExpanded(false);
  };

  useLayoutEffect(() => {
    if (!expanded) return;
    const el = infoRef.current;
    const f = firstRect.current;
    const last = el.getBoundingClientRect();
    el.style.transformOrigin = "top left";
    el.animate(
      [{ transform: `translate(${f.left - last.left}px, ${f.top - last.top}px) scale(${f.width / last.width}, ${f.height / last.height})` },
       { transform: "none" }],
      { duration: DURATION, easing: EASING }
    );
  }, [expanded]);

  return (
    <div className={`layout-chaos${isElectron ? ' electron-mode' : ''}`}>
      <section className="zone-lovelace-main">
        <LovelacePanel />
      </section>

      {!isElectron && (
        <section className="zone-vicky-chat">
          <VickyAvatar onUnityReady={handleUnityReady} />
          <ChatOverlay />
        </section>
      )}

      <section
        ref={infoRef}
        className={`zone-info panel ${expanded ? "panel-expanded" : ""}`}
        onClick={expanded ? undefined : expand}
      >
        {expanded && <button className="panel-close" onClick={collapse}>✕</button>}
        <InfoPanel />
      </section>

      {expanded && <div className="modal-backdrop" onClick={collapse} />}
    </div>
  );
}