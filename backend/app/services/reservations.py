from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any

from sqlalchemy import text

from app.core.database_pool import db_pool

CENTS = Decimal("0.01")


def to_money(value) -> str:
    """Round an exact Decimal sum to cents once, at the end (never via float)."""
    return str(Decimal(str(value or 0)).quantize(CENTS, rounding=ROUND_HALF_UP))


async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Decimal:
    """
    Calculates revenue for a specific month in the property's own time zone.

    A booking that checks in at 2024-02-29 23:30 UTC is 1 March 00:30 in Paris,
    so it belongs to March for a Paris property.
    """
    start_date = datetime(year, month, 1)
    if month < 12:
        end_date = datetime(year, month + 1, 1)
    else:
        end_date = datetime(year + 1, 1, 1)

    query = text("""
        SELECT COALESCE(SUM(r.total_amount), 0) AS total
        FROM reservations r
        JOIN properties p
          ON p.id = r.property_id AND p.tenant_id = r.tenant_id
        WHERE r.property_id = :property_id
          AND r.tenant_id = :tenant_id
          AND (r.check_in_date AT TIME ZONE p.timezone) >= :start_date
          AND (r.check_in_date AT TIME ZONE p.timezone) < :end_date
    """)

    await db_pool.initialize()
    async with db_pool.get_session() as session:
        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_date": start_date,
            "end_date": end_date,
        })
        return Decimal(str(result.scalar() or 0))


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.

    Errors are raised instead of returning hard-coded mock numbers: the old
    fallback was not tenant-aware and showed made-up totals to real clients.
    """
    await db_pool.initialize()
    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available")

    query = text("""
        SELECT
            COALESCE(SUM(total_amount), 0) AS total_revenue,
            COUNT(*) AS reservation_count
        FROM reservations
        WHERE property_id = :property_id AND tenant_id = :tenant_id
    """)

    async with db_pool.get_session() as session:
        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id
        })
        row = result.fetchone()

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": to_money(row.total_revenue),
        "currency": "USD",
        "count": row.reservation_count,
    }
