from fastapi import APIRouter, HTTPException

from api.db import get_connection
from api.schemas import SegmentResponse, SegmentSummary

router = APIRouter()


@router.get("/customers/{customer_id}/segment", response_model=SegmentResponse)
def get_customer_segment(customer_id: str) -> SegmentResponse:
    with get_connection() as con:
        row = con.execute(
            """
            SELECT customer_id, cluster_id, segment_label, tier, segmented_at
            FROM customer_profile
            WHERE customer_id = ?
            """,
            (customer_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    return SegmentResponse(**dict(row))


@router.get("/segments", response_model=list[SegmentSummary])
def list_segments() -> list[SegmentSummary]:
    with get_connection() as con:
        rows = con.execute(
            """
            SELECT segment_label, count(*) as customer_count
            FROM customer_profile
            GROUP BY segment_label
            ORDER BY customer_count DESC
            """
        ).fetchall()

    return [SegmentSummary(**dict(row)) for row in rows]
