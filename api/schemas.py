"""Modelos de resposta Pydantic da API.

As descrições dos campos aparecem no Swagger (/docs) e seguem
transform/models/activation/schema.yml.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

SegmentLabel = Literal[
    "Champions", "Loyal", "Promising", "At Risk", "Hibernating", "Lost", "no_purchase"
]
Tier = Literal["Gold", "Silver", "Bronze"]
CampaignReason = Literal[
    "propensity_model", "segment_affinity", "overall_affinity", "most_recent_fallback"
]
ShowcaseReason = Literal["item_similarity", "basket_affinity", "favorite_category_fallback"]


class ErrorResponse(BaseModel):
    detail: str = Field(examples=["Cliente não encontrado"])


class CustomerSummary(BaseModel):
    customer_id: str = Field(
        description="Id do cliente (= `identity.cdpId` da API de dados sintéticos).",
        examples=["00065b8f-e8a2-54b6-adb8-6f7c9af82bd6"],
    )
    full_name: Optional[str] = Field(default=None, examples=["Beatriz Alves"])


class SegmentResponse(BaseModel):
    customer_id: str = Field(examples=["00065b8f-e8a2-54b6-adb8-6f7c9af82bd6"])
    cluster_id: Optional[int] = Field(
        default=None,
        description="Cluster cru do K-Means; nulo para clientes sem histórico de compra.",
        examples=[1],
    )
    segment_label: Optional[SegmentLabel] = Field(
        default=None,
        description="Rótulo de negócio do cluster, ou `no_purchase` para quem nunca comprou.",
    )
    tier: Optional[Tier] = Field(
        default=None,
        description="Faixa por percentil de receita líquida entre quem já comprou; nulo para `no_purchase`.",
    )
    segmented_at: Optional[str] = Field(
        default=None,
        description="Momento em que a segmentação foi calculada.",
        examples=["2026-10-13 18:44:22-03:00"],
    )


class SegmentSummary(BaseModel):
    segment_label: SegmentLabel
    customer_count: int = Field(description="Quantidade de clientes no segmento.", examples=[783])


class CampaignResponse(BaseModel):
    customer_id: str = Field(examples=["00065b8f-e8a2-54b6-adb8-6f7c9af82bd6"])
    promotion_id: Optional[str] = Field(
        default=None,
        description="Campanha recomendada (= `utmiCampaign` em `/promotions` da API de dados sintéticos).",
        examples=["inverno-calcados-40off"],
    )
    promotion_name: Optional[str] = Field(default=None, examples=["Colecao Inverno - Ate 40% OFF Calcados"])
    score: Optional[float] = Field(
        default=None,
        description="Pontuação da camada que decidiu a campanha; a escala depende de `reason`, "
        "então só é comparável entre clientes com o mesmo `reason`.",
    )
    reason: Optional[CampaignReason] = Field(
        default=None,
        description="Camada que decidiu a campanha: `propensity_model` (modelo de propensão do cliente) | "
        "`segment_affinity` (conversão histórica do segmento) | `overall_affinity` (conversão "
        "histórica geral) | `most_recent_fallback` (nenhuma conversão histórica ainda).",
    )
    scored_at: Optional[str] = Field(default=None, examples=["2026-10-13 18:44:23-03:00"])


class ShowcaseItem(BaseModel):
    rank: int = Field(description="Posição na vitrine (1 = mais relevante).", examples=[1])
    product_id: str = Field(examples=["2003546"])
    sku_id: Optional[str] = Field(default=None, examples=["5010637"])
    product_name: Optional[str] = Field(default=None, examples=["Body Manga Longa 26 PP Azul"])
    price: Optional[float] = Field(default=None, description="Preço de venda do SKU.", examples=[226.26])
    image_url: Optional[str] = None
    reason: ShowcaseReason = Field(
        description="Sinal que colocou o produto na vitrine: `item_similarity` (similaridade com "
        "produtos já comprados) | `basket_affinity` (quem comprou X também comprou Y) | "
        "`favorite_category_fallback` (categoria/marca favorita)."
    )
    score: float = Field(description="Relevância do item para o cliente.", examples=[0.5])


class ShowcaseResponse(BaseModel):
    customer_id: str = Field(examples=["00065b8f-e8a2-54b6-adb8-6f7c9af82bd6"])
    items: list[ShowcaseItem] = Field(
        description="Produtos ordenados por `rank`; lista vazia se o cliente não tiver vitrine."
    )
