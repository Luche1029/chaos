import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import RulesPanel from './RulesPanel'

const path = window.location.pathname

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {path === '/rules-ui' ? <RulesPanel /> : <App />}
  </React.StrictMode>
)