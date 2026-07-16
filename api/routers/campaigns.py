from fastapi import APIRouter, HTTPException

from api.db import get_connection
from api.schemas import CampaignResponse

router = APIRouter()


@router.get("/customers/{customer_id}/next-best-campaign", response_model=CampaignResponse)
def get_next_best_campaign(customer_id: str) -> CampaignResponse:
    with get_connection() as con:
        row = con.execute(
            """
            SELECT
                customer_id,
                next_best_promotion_id AS promotion_id,
                next_best_promotion_name AS promotion_name,
                next_best_campaign_score AS score,
                next_best_campaign_reason AS reason,
                campaign_scored_at AS scored_at
            FROM customer_profile
            WHERE customer_id = ?
            """,
            (customer_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    return CampaignResponse(**dict(row))
