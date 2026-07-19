#!/usr/bin/env bash
# Orquestra o stack nativo (sem Docker) do ecommerce-machine-learning: treino de ML, o dbt
# build próprio (transform/, feature+activation) e o export pro serving
# store, além de ml-api e do painel web. As venvs (.venv-py, .venv-dbt) e o
# node_modules (web/) são criados automaticamente na primeira execução --
# projeto roda sozinho, só precisa de Python 3.11 (mesma versão que o
# ecommerce-data-pipeline usa -- dbt-clickhouse quebra em Python 3.14) e Node.js
# instalados na máquina.
#
# O ecommerce-data-pipeline roda separado (../ecommerce-data-pipeline/stack.sh up/data) -- não é
# gerenciado daqui, só precisa estar no ar (ClickHouse + staging/marts já
# construídos, staging como `view`) antes de `./stack.sh ml`. transform/ aqui
# é um projeto dbt próprio (feature/activation) que lê staging/marts de lá
# via source() -- não copia nenhum arquivo entre os dois projetos, só lê o
# schema físico no ClickHouse compartilhado.
#
# Uso:
#   ./stack.sh ml         # dbt build (feature) -> treino -> dbt build (completo) -> export
#   ./stack.sh export     # só publica activation/* no serving store (sem retreinar)
#   ./stack.sh ml-api     # sobe a ml-api em background (:8000)
#   ./stack.sh ml-web     # sobe o painel web da ml-api em background (:5173)
#   ./stack.sh down       # para ml-api e ml-web
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
AGENTIC_CDP="$ROOT/../ecommerce-data-pipeline"

set -a
source .env
set +a

log() { echo "[ecommerce-machine-learning] $*"; }

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

ensure_venv() {
  if [ ! -d ".venv-py" ]; then
    log "venv: .venv-py não existe, criando e instalando requirements.txt..."
    python3.11 -m venv .venv-py
    .venv-py/bin/pip install -q --upgrade pip
    .venv-py/bin/pip install -q -r requirements.txt
  fi
}

ensure_dbt_venv() {
  if [ ! -d ".venv-dbt" ]; then
    log "venv: .venv-dbt não existe, criando e instalando transform/requirements.txt..."
    python3.11 -m venv .venv-dbt
    .venv-dbt/bin/pip install -q --upgrade pip
    .venv-dbt/bin/pip install -q -r transform/requirements.txt
  fi
}

dbt_build() {
  ensure_dbt_venv
  source .venv-dbt/bin/activate
  (cd transform && dbt build "$@")
  deactivate
}

cmd_ml() {
  require_clickhouse

  log "dbt build (feature/*, exceto feat_customer_segment_labels -- depende de raw.customer_clusters, que só existe depois do treino)"
  dbt_build --exclude path:models/activation feat_customer_segment_labels

  log "ml: treino (segmentação, campanhas, recomendações, receita)"
  ensure_venv
  source .venv-py/bin/activate
  python training/segmentation/train_kmeans.py
  python training/campaigns/train_propensity.py
  python training/recommendations/train_item_similarity.py
  python training/revenue/train_revenue_trend.py
  python training/orders/train_order_volume_trend.py
  deactivate

  log "dbt build completo (feat_customer_segment_labels + activation/*)"
  dbt_build

  log "ml: export para serving store"
  source .venv-py/bin/activate
  python export_to_serving_store.py
  deactivate

  log "pipeline de ML completo."
}

cmd_export() {
  require_clickhouse
  ensure_venv

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
  ensure_venv
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
