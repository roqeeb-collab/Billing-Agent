"""
Stage 2 — Validation Agent

Validate that card_id and created_at are non-null and parseable.
Write error rows to logs/validation_errors.csv.
Halt the pipeline if > 10 % of rows are invalid.
"""

import os
import pandas as pd
from logger import get_logger

log = get_logger(__name__)

VALIDATION_ERRORS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "logs", "validation_errors.csv"
)


def run(df: pd.DataFrame) -> pd.DataFrame:
    """Return only valid rows; raise if error rate exceeds 10 %."""
    log.info("Validation started — %d rows to check", len(df))

    errors = []

    for idx, row in df.iterrows():
        reasons = []

        # card_id must be non-null and non-empty
        if pd.isna(row.get("card_id")) or str(row.get("card_id")).strip() == "":
            reasons.append("card_id is null or empty")

        # created_at must be non-null and parseable as a date
        raw_date = row.get("created_at")
        if pd.isna(raw_date):
            reasons.append("created_at is null")
        else:
            try:
                pd.to_datetime(raw_date)
            except (ValueError, TypeError):
                reasons.append(f"created_at not parseable: {raw_date!r}")

        if reasons:
            errors.append({"row_index": idx, **row.to_dict(), "error": "; ".join(reasons)})

    # Write error rows
    if errors:
        error_df = pd.DataFrame(errors)
        os.makedirs(os.path.dirname(VALIDATION_ERRORS_PATH), exist_ok=True)
        error_df.to_csv(VALIDATION_ERRORS_PATH, index=False)
        log.warning("Wrote %d validation errors to %s", len(errors), VALIDATION_ERRORS_PATH)
    else:
        log.info("No validation errors found")

    # Threshold check
    error_rate = len(errors) / len(df) if len(df) > 0 else 0
    if error_rate > 0.10:
        msg = (
            f"Validation threshold breached: {len(errors)}/{len(df)} rows "
            f"({error_rate:.1%}) are invalid — halting pipeline"
        )
        log.error(msg)
        raise ValueError(msg)

    # Drop bad rows
    bad_indices = {e["row_index"] for e in errors}
    valid_df = df.drop(index=bad_indices).reset_index(drop=True)
    log.info("Validation passed — %d valid rows", len(valid_df))
    return valid_df
