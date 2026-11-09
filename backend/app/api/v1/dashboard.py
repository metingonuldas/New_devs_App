from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List
from sqlalchemy import text
from app.core.database_pool import db_pool
from app.services.cache import get_revenue_summary
from app.services.reservations import calculate_monthly_revenue, to_money
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()


def _tenant_of(current_user) -> str:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        # Never fall back to a shared "default" tenant: that mixes clients' data.
        raise HTTPException(status_code=403, detail="No tenant assigned to this user")
    return tenant_id


@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: dict = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Only the properties that belong to the logged-in client."""
    tenant_id = _tenant_of(current_user)
    await db_pool.initialize()
    async with db_pool.get_session() as session:
        result = await session.execute(
            text("SELECT id, name, timezone FROM properties WHERE tenant_id = :tenant_id ORDER BY id"),
            {"tenant_id": tenant_id},
        )
        return [dict(row._mapping) for row in result]


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:

    tenant_id = _tenant_of(current_user)

    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id)
    except Exception:
        raise HTTPException(status_code=503, detail="Revenue data is temporarily unavailable")

    return {
        "property_id": revenue_data['property_id'],
        # Already rounded to cents from the exact Decimal sum.
        "total_revenue": float(revenue_data['total']),
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }


@router.get("/dashboard/monthly")
async def get_monthly_revenue(
    property_id: str,
    month: int,
    year: int,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    if not 1 <= month <= 12:
        raise HTTPException(status_code=422, detail="month must be between 1 and 12")

    tenant_id = _tenant_of(current_user)
    total = await calculate_monthly_revenue(property_id, tenant_id, month, year)
    return {
        "property_id": property_id,
        "month": month,
        "year": year,
        "total_revenue": float(to_money(total)),
        "currency": "USD",
    }
