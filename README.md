# CHAOS - Cognitive Home Adaptive Operating System

## Architettura
- OS Base: Debian 13 Trixie minimal
- Container runtime: Docker + Compose v2
- Core services: Home Assistant, MQTT, InfluxDB
- AI Layer: n8n, Python, Ollama
- UI: Dashboard web + App mobile

## Struttura
/opt/chaos/
  core/     → docker compose files
  data/     → volumi persistenti
  config/   → configurazioni servizi
  scripts/  → automazioni bash
  logs/     → log di sistema

## Fase attuale
Fase 1 - OS Base completata
