# ecomm-ml

Camada de ML do CDP: resolve 3 casos de uso a partir de
`activation.customer_profile` e `marts.fct_order_line` (ambos no ClickHouse
do [`agentic-cdp`](../agentic-cdp)) -- clusterização dinâmica de clientes,
próxima campanha sugerida e vitrine inteligente personalizada.

Projeto irmão de `agentic-cdp`: não sobe ClickHouse próprio nem roda dbt --
lê/escreve as tabelas do warehouse do `agentic-cdp` (`../agentic-cdp`), mas
não chama o `dbt build` de lá -- esse passo é manual, entre `./stack.sh ml`
e `./stack.sh export` (ver [Ordem de execução](#ordem-de-execução-do-pipeline-batch)
abaixo). A lógica de negócio (rotulagem, ranking, combinação com outras
tabelas) mora em SQL
nos models de `../agentic-cdp/transform/models/activation/`
(`customer_profile.sql`, `segment_campaign_affinity.sql`,
`customer_showcase.sql`) -- os scripts aqui em `training/` só rodam o
algoritmo de ML e gravam o resultado cru em `raw.*` do ClickHouse
compartilhado.

## Estrutura

- `stack.sh` -- `ml` (treino) e `export` (serving store) como comandos
  separados, com o `dbt build` de `../agentic-cdp/transform` rodando
  manualmente entre os dois, além de `ml-api` e `ml-web`.
- `training/<caso_de_uso>/train_*.py` -- um script por caso de uso, cada um
  lê uma feature view do ClickHouse e grava uma tabela crua em `raw.*`.
- `export_to_serving_store.py` -- publica os resultados finais (já
  materializados pelo dbt em `activation.*`) num SQLite de leitura em
  `output/serving_store.sqlite`, pra API consumir sem disputar o ClickHouse
  com o dbt/treino.
- `api/` -- API REST (FastAPI) que expõe os 3 casos de uso lendo só do
  SQLite acima, nunca do ClickHouse diretamente.
- `web/` -- painel web (React + Vite) que consome a API.
- `common/db.py` -- conexão ClickHouse e helpers compartilhados pelos
  scripts de treino.

## Dependências

- **Python 3.11** -- venv `.venv-py` (não commitada; ver `.gitignore`).
  `python3 -m venv .venv-py && source .venv-py/bin/activate && pip install -r requirements.txt`
- **Node.js** -- só pro painel web (`web/`), instalado automaticamente por
  `./stack.sh ml-web` (`npm install` se `web/node_modules` não existir).
- **[agentic-cdp](../agentic-cdp)** no ar, com `./stack.sh up` +
  `./stack.sh data` já rodados (ClickHouse + staging/marts + as 4 feature
  views base em pé) antes do primeiro `./stack.sh ml` aqui.

`cp .env.example .env` e ajuste `CLICKHOUSE_*` (mesmos valores do `.env` do
`agentic-cdp` -- os dois projetos apontam pro mesmo ClickHouse) e
`SERVING_STORE_PATH` (absoluto) antes do primeiro run.

## Ordem de execução do pipeline batch

`customer_profile.sql` (em `agentic-cdp/transform/models/activation/`) lê a
saída do Python (`raw.customer_clusters`, `raw.campaign_propensity`), e o
Python lê as views de `agentic-cdp/transform/models/feature/`. Isso exige
rodar o `dbt build` em duas passagens -- a segunda só depois que os scripts
de treino já escreveram em `raw.*`. `./stack.sh ml` só treina e para: falta
rodar o `dbt build` manualmente antes do `./stack.sh export`.

```bash
(cd ../agentic-cdp && ./stack.sh up && ./stack.sh data)  # pré-requisito: staging/marts + as 4 feature views base já em raw/feature
./stack.sh ml       # treino (segmentation, campaigns, recommendations) -- para com erro pedindo o passo abaixo
(cd ../agentic-cdp/transform && source ../.venv-dbt/bin/activate && dbt build)  # completo: feat_customer_segment_labels + activation/*
./stack.sh export   # publica activation/* (dbt) no serving store
./stack.sh ml-api   # sobe a ml-api (lê só output/serving_store.sqlite, nunca o ClickHouse)
./stack.sh ml-web   # sobe o painel web (:5173)
```

Passo a passo do que cada comando faz:

```bash
# 1. (feito por ../agentic-cdp/stack.sh data) as 4 feature views que os
#    scripts de treino consomem já foram materializadas -- NÃO inclui
#    feat_customer_segment_labels, que depende de raw.customer_clusters (só
#    existe depois do passo 2 abaixo).

# 2. `./stack.sh ml` -- os 3 scripts de treino (cada um só lê a feature view
#    e grava UMA tabela crua em raw.*)
python training/segmentation/train_kmeans.py
python training/campaigns/train_propensity.py
python training/recommendations/train_item_similarity.py

# 3. manual, no projeto agentic-cdp -- agora customer_profile.sql,
#    customer_showcase.sql etc. conseguem ler raw.customer_clusters/
#    campaign_propensity/product_similarity. Não há nenhum arquivo pra
#    transferir entre os dois projetos -- dbt e treino só conversam via
#    tabelas do ClickHouse compartilhado; `ecomm-ml/stack.sh` não chama esse
#    cmd, só avisa que ele precisa rodar.
(cd ../agentic-cdp/transform && dbt build)

# 4. `./stack.sh export` -- publica os resultados finais num SQLite de
#    leitura pra API consumir
python export_to_serving_store.py
```

## Por que Python só treina

Cada script em `training/<caso_de_uso>/train_*.py` faz uma única coisa: ler
uma feature view, rodar o algoritmo de ML, e escrever uma tabela crua em
`raw.*` (mesmo padrão de `agentic-cdp/scripts/load_ga4_customer_behavior.py`).
Toda rotulagem de negócio, ranking, fallback e combinação com outras tabelas
fica em SQL/dbt -- mais fácil de auditar e testar (`dbt test`).

| Caso de uso | Algoritmo | Script | Saída crua |
|---|---|---|---|
| Clusterização dinâmica | K-Means (k via silhouette) | `training/segmentation/train_kmeans.py` | `raw.customer_clusters` |
| Próxima campanha | Regressão Logística por campanha | `training/campaigns/train_propensity.py` | `raw.campaign_propensity` |
| Vitrine personalizada | Cosine similarity produto x produto | `training/recommendations/train_item_similarity.py` | `raw.product_similarity` |

## Licença

Distribuído sob a licença [MIT](../agentic-cdp/LICENSE).
