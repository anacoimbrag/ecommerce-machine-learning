"""API REST que expõe os 3 casos de uso de ML do CDP (segmentação, próxima
campanha, vitrine personalizada). Lê só de output/serving_store.sqlite,
gravado por export_to_serving_store.py — nunca do ClickHouse diretamente.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import campaigns, customers, segments, showcase

TAGS_METADATA = [
    {"name": "customers", "description": "Clientes disponíveis no serving store."},
    {"name": "segments", "description": "Caso de uso 1 — clusterização dinâmica de clientes (K-Means + RFM)."},
    {"name": "campaigns", "description": "Caso de uso 2 — próxima campanha sugerida por cliente."},
    {"name": "showcase", "description": "Caso de uso 3 — vitrine inteligente personalizada."},
    {"name": "infra", "description": "Saúde do serviço."},
]

app = FastAPI(
    title="ecommerce-data-pipeline ML API",
    version="1.0.0",
    description=(
        "Segmentação dinâmica, próxima campanha sugerida e vitrine personalizada.\n\n"
        "Somente leitura: os dados vêm de `output/serving_store.sqlite`, publicado por "
        "`export_to_serving_store.py` após o treino/dbt — rode `./stack.sh ml` para atualizá-los.\n\n"
        "`customer_id` é o mesmo `identity.cdpId` da API de dados sintéticos; use `GET /customers` "
        "para obter ids de exemplo."
    ),
    openapi_tags=TAGS_METADATA,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(customers.router, tags=["customers"])
app.include_router(segments.router, tags=["segments"])
app.include_router(campaigns.router, tags=["campaigns"])
app.include_router(showcase.router, tags=["showcase"])


@app.get("/health", tags=["infra"], summary="Health check")
def health() -> dict:
    return {"status": "ok"}
