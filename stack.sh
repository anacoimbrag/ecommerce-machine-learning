#!/usr/bin/env bash
# Orquestra o stack nativo (sem Docker) do ecomm-ml: treino de ML, export pro
# serving store, ml-api e o painel web. Ver README.md para o setup inicial da
# venv (.venv-py) e do node_modules (web/).
#
# O agentic-cdp roda separado (../agentic-cdp/stack.sh up/data) -- não é
# gerenciado daqui, só precisa estar no ar (ClickHouse + staging/marts já
# construídos) antes de `./stack.sh ml`. Este script NÃO chama o `dbt build`
# de `../agentic-cdp/transform` -- entre `ml` (treino) e `export`, rode esse
# outro fluxo manualmente (ver mensagem de erro do `./stack.sh ml`); não há
# nenhum arquivo pra copiar entre os dois projetos, dbt e treino conversam só
# via tabelas do ClickHouse compartilhado.
#
# Uso:
#   ./stack.sh ml         # treino de ML (segmentação, campanhas, recomendações)
#   ./stack.sh export     # publica activation/* (dbt) no serving store -- rode depois do dbt build
#   ./stack.sh ml-api     # sobe a ml-api em background (:8000)
#   ./stack.sh ml-web     # sobe o painel web da ml-api em background (:5173)
#   ./stack.sh down       # para ml-api e ml-web
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
AGENTIC_CDP="$ROOT/../agentic-cdp"

set -a
source .env
set +a

log() { echo "[ecomm-ml] $*"; }

wait_for() {
  local desc="$1" check="$2" tries=30
  for ((i = 0; i < tries; i++)); do
    eval "$check" >/dev/null 2>&1 && { log "$desc: no ar"; return 0; }
    sleep 1
  done
  log "$desc: não respondeu em ${tries}s"
  return 1
}

require_clickhouse() {
  if ! curl -sf -m 2 "http://${CLICKHOUSE_HOST}:${CLICKHOUSE_PORT}/ping" >/dev/null 2>&1; then
    log "clickhouse não está respondendo em ${CLICKHOUSE_HOST}:${CLICKHOUSE_PORT}"
    log "suba com: (cd $AGENTIC_CDP && ./stack.sh up) e rode ./stack.sh data lá antes"
    exit 1
  fi
}

cmd_ml() {
  require_clickhouse

  log "ml: treino (segmentação, campanhas, recomendações)"
  source .venv-py/bin/activate
  python training/segmentation/train_kmeans.py
  python training/campaigns/train_propensity.py
  python training/recommendations/train_item_similarity.py
  deactivate

  log "treino completo. Falta rodar o dbt build no agentic-cdp antes do export:"
  log "  (cd $AGENTIC_CDP/transform && source ../.venv-dbt/bin/activate && dbt build)"
  log "Depois rode: ./stack.sh export"
  exit 1
}

cmd_export() {
  require_clickhouse

  log "ml: export para serving store"
  source .venv-py/bin/activate
  python export_to_serving_store.py
  deactivate
}

cmd_ml_api() {
  if curl -sf -m 2 "http://localhost:8000/health" >/dev/null 2>&1; then
    log "ml-api: já rodando"
    return
  fi
  log "ml-api: iniciando..."
  source .venv-py/bin/activate
  nohup uvicorn api.main:app --host 0.0.0.0 --port 8000 \
    >"$ROOT/.stack-ml-api.log" 2>&1 & disown
  deactivate
  wait_for "ml-api" "curl -sf -m 2 http://localhost:8000/health"
}

cmd_ml_web() {
  if curl -sf -m 2 "http://localhost:5173" >/dev/null 2>&1; then
    log "ml-web: já rodando"
    return
  fi
  if [ ! -d "web/node_modules" ]; then
    log "ml-web: instalando dependências..."
    (cd web && npm install)
  fi
  log "ml-web: iniciando..."
  (cd web && nohup npm run dev -- --host \
    >"$ROOT/.stack-ml-web.log" 2>&1 & disown)
  wait_for "ml-web" "curl -sf -m 2 http://localhost:5173"
}

cmd_down() {
  for port_desc in "8000:ml-api" "5173:ml-web"; do
    port="${port_desc%%:*}"; desc="${port_desc##*:}"
    pid=$(lsof -ti "tcp:$port" 2>/dev/null || true)
    if [ -n "$pid" ]; then
      kill $pid 2>/dev/null && log "$desc: parado (porta $port)"
    else
      log "$desc: não estava rodando"
    fi
  done
}

case "${1:-}" in
  ml) cmd_ml ;;
  export) cmd_export ;;
  ml-api) cmd_ml_api ;;
  ml-web) cmd_ml_web ;;
  down) cmd_down ;;
  *)
    echo "Uso: $0 {ml|export|ml-api|ml-web|down}" >&2
    exit 1
    ;;
esac
