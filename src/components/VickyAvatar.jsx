// src/components/VickyAvatar.jsx
import { useEffect } from "react";

const isElectron = import.meta.env.VITE_MODE === 'electron'

// Importa Unity solo in modalità browser
let Unity, useUnityContext
if (!isElectron) {
  const unityWebgl = await import("react-unity-webgl")
  Unity = unityWebgl.Unity
  useUnityContext = unityWebgl.useUnityContext
}

export default function VickyAvatar({ onUnityReady }) {
  // In modalità Electron, Unity gira come processo nativo separato
  if (isElectron) {
    return <div className="vicky-avatar vicky-native" />
  }

  return <VickyAvatarWebGL onUnityReady={onUnityReady} />
}

function VickyAvatarWebGL({ onUnityReady }) {
  const {
    unityProvider,
    isLoaded,
    loadingProgression,
    sendMessage,
    addEventListener,
    removeEventListener,
  } = useUnityContext({
    loaderUrl: "/unity/Build/_build_webgl.loader.js",
    dataUrl: "/unity/Build/_build_webgl.data",
    frameworkUrl: "/unity/Build/_build_webgl.framework.js",
    codeUrl: "/unity/Build/_build_webgl.wasm",
  });

  useEffect(() => {
    if (isLoaded && onUnityReady) {
      onUnityReady({ sendMessage, addEventListener, removeEventListener });
    }
  }, [isLoaded]);

  return (
    <div className="vicky-avatar">
      {!isLoaded && (
        <div className="vicky-loading">
          <div className="vicky-loading-bar">
            <div
              className="vicky-loading-fill"
              style={{ width: `${Math.round(loadingProgression * 100)}%` }}
            />
          </div>
          <span>Caricamento Vicky… {Math.round(loadingProgression * 100)}%</span>
        </div>
      )}
      <Unity
        unityProvider={unityProvider}
        className="vicky-canvas"
        style={{ visibility: isLoaded ? "visible" : "hidden" }}
      />
    </div>
  );
}