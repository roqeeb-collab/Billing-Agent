"""
Stage 3 — Billing Agent

Calculate months_active and apply tiered fee:
  • ≤ 3 months  →  $3.00
  • > 3 months  →  $1.00

Returns the enriched DataFrame and a billing summary dict.
"""

from datetime import datetime
import pandas as pd
from logger import get_logger

log = get_logger(__name__)

FEE_HIGH = 3.00  # ≤ 3 months
FEE_LOW = 1.00   # > 3 months
DAYS_PER_MONTH = 30.44


def run(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Enrich DataFrame with billing columns and produce a summary."""
    log.info("Billing started — %d rows", len(df))

    today = datetime.today()

    df = df.copy()
    df["created_at"] = pd.to_datetime(df["created_at"])
    df["days_active"] = (today - df["created_at"]).dt.days
    df["months_active"] = (df["days_active"] / DAYS_PER_MONTH).round(2)
    df["fee"] = df["months_active"].apply(lambda m: FEE_HIGH if m <= 3 else FEE_LOW)

    tier_3_count = int((df["fee"] == FEE_HIGH).sum())
    tier_1_count = int((df["fee"] == FEE_LOW).sum())
    total_revenue = float(df["fee"].sum())

    # Daily card creation stats
    today_date = today.date()
    new_today = int((df["created_at"].dt.date == today_date).sum())
    new_this_week = int((df["days_active"] <= 7).sum())
    new_this_month = int((df["days_active"] <= 30).sum())

    summary = {
        "total_cards": len(df),
        "total_revenue": total_revenue,
        "avg_months": round(float(df["months_active"].mean()), 2),
        "breakdown": {
            "tier_3_dollar": tier_3_count,
            "tier_1_dollar": tier_1_count,
        },
        "daily": {
            "new_today": new_today,
            "new_this_week": new_this_week,
            "new_this_month": new_this_month,
        },
    }

    log.info(
        "Billing complete — %d cards, $%.2f revenue (tier $3: %d, tier $1: %d)",
        summary["total_cards"],
        summary["total_revenue"],
        tier_3_count,
        tier_1_count,
    )
    return df, summary
