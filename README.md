# ecommerce-machine-learning

Camada de ML do CDP: resolve 3 casos de uso -- clusterização dinâmica de
clientes, próxima campanha sugerida e vitrine inteligente personalizada.

Projeto irmão de `ecommerce-data-pipeline`, independente: não sobe ClickHouse próprio,
mas tem seu próprio venv, seu próprio projeto dbt (`transform/`, models de
`feature/` e `activation/`) e seu próprio `stack.sh` -- `./stack.sh ml` roda
o pipeline inteiro (treino + dbt build + export) sem precisar de nenhum
passo manual no `ecommerce-data-pipeline`. A única dependência real é de dado: os
schemas `staging` e `marts`, materializados fisicamente pelo dbt do
`ecommerce-data-pipeline` (`../ecommerce-data-pipeline/transform`) no ClickHouse compartilhado, que
`transform/` aqui lê via `source()` do dbt (não `ref()` -- `ref()` só
resolve dentro do mesmo projeto dbt; por isso `staging` lá é `view`, não
`ephemeral`). Nenhum arquivo é copiado entre os dois projetos -- é tudo
schema físico no mesmo warehouse.

## Estrutura

- `stack.sh` -- `ml` (dbt build de `feature/*` → treino → dbt build
  completo → export, tudo num comando só) e `export` (só o passo de export,
  pra reexportar sem retreinar) como comandos separados, além de `ml-api` e
  `ml-web`.
- `transform/` -- projeto dbt próprio (`dbt-clickhouse`), profile
  `ecomm_ml`:
  - `models/feature/` -- feature views lidas pelos scripts de treino
    (`feat_rfm_features`, `feat_promotion_engagement`,
    `feat_campaign_training_data`, `feat_customer_product_interactions`,
    `feat_customer_segment_labels`).
  - `models/activation/` -- resultado final combinando SQL + saída dos
    scripts de treino (`customer_profile`, `segment_campaign_affinity`,
    `product_affinity`, `customer_showcase`).
  - `models/sources.yml` -- declara `staging`/`marts` (materializados pelo
    ecommerce-data-pipeline, lidos via `source()`) e `raw` (landing zone compartilhada,
    onde `training/` grava e de onde `feature/`/`activation/` leem).
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

- **Python 3.11** -- mesma versão que o `ecommerce-data-pipeline` usa (`dbt-clickhouse`
  quebra em Python 3.14). `.venv-py` (treino/API/export) e `.venv-dbt`
  (`transform/`) são criadas e populadas automaticamente na primeira
  execução de `./stack.sh` -- não precisa rodar `pip install` à mão.
- **Node.js** -- só pro painel web (`web/`), instalado automaticamente por
  `./stack.sh ml-web` (`npm install` se `web/node_modules` não existir).
- **[ecommerce-data-pipeline](../ecommerce-data-pipeline)** no ar, com `./stack.sh up` +
  `./stack.sh data` já rodados (ClickHouse + `staging`/`marts` em pé) antes
  do primeiro `./stack.sh ml` aqui -- única dependência entre os dois
  projetos, e só de dado (ver acima).

`cp .env.example .env` e ajuste `CLICKHOUSE_*` (mesmos valores do `.env` do
`ecommerce-data-pipeline` -- os dois projetos apontam pro mesmo ClickHouse) e
`SERVING_STORE_PATH` (absoluto) antes do primeiro run.

## Ordem de execução do pipeline batch

`customer_profile.sql` lê a saída do Python (`raw.customer_clusters`,
`raw.campaign_propensity`), e o Python lê as feature views. Isso exige
rodar o `dbt build` em duas passagens -- a segunda só depois que os scripts
de treino já escreveram em `raw.*`. `./stack.sh ml` encadeia tudo isso:

```bash
(cd ../ecommerce-data-pipeline && ./stack.sh up && ./stack.sh data)  # pré-requisito: staging/marts em pé
./stack.sh ml       # dbt build (feature) -> treino -> dbt build (completo) -> export
./stack.sh ml-api   # sobe a ml-api (lê só output/serving_store.sqlite, nunca o ClickHouse)
./stack.sh ml-web   # sobe o painel web (:5173)
```

Por baixo dos panos, `./stack.sh ml` roda, na ordem:

```bash
# 1. dbt build de feature/*, exceto feat_customer_segment_labels (depende de
#    raw.customer_clusters, que só existe depois do passo 2 abaixo). As
#    outras 4 feature views leem staging/marts do ecommerce-data-pipeline via source().
(cd transform && dbt build --exclude path:models/activation feat_customer_segment_labels)

# 2. os 3 scripts de treino (cada um só lê a feature view e grava
#    UMA tabela crua em raw.*)
python training/segmentation/train_kmeans.py
python training/campaigns/train_propensity.py
python training/recommendations/train_item_similarity.py

# 3. dbt build completo -- agora feat_customer_segment_labels,
#    customer_profile.sql, customer_showcase.sql etc. conseguem ler
#    raw.customer_clusters/campaign_propensity/product_similarity.
(cd transform && dbt build)

# 4. publica os resultados finais num SQLite de leitura pra API consumir
python export_to_serving_store.py
```

## Por que Python só treina

Cada script em `training/<caso_de_uso>/train_*.py` faz uma única coisa: ler
uma feature view, rodar o algoritmo de ML, e escrever uma tabela crua em
`raw.*` (mesmo padrão de `ecommerce-data-pipeline/scripts/load_ga4_customer_behavior.py`).
Toda rotulagem de negócio, ranking, fallback e combinação com outras tabelas
fica em SQL/dbt -- mais fácil de auditar e testar (`dbt test`).

| Caso de uso | Algoritmo | Script | Saída crua |
|---|---|---|---|
| Clusterização dinâmica | K-Means (k via silhouette) | `training/segmentation/train_kmeans.py` | `raw.customer_clusters` |
| Próxima campanha | Regressão Logística por campanha | `training/campaigns/train_propensity.py` | `raw.campaign_propensity` |
| Vitrine personalizada | Cosine similarity produto x produto | `training/recommendations/train_item_similarity.py` | `raw.product_similarity` |

## Licença

Distribuído sob a licença [MIT](../ecommerce-data-pipeline/LICENSE).
