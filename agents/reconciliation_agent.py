"""
Stage 4 — Reconciliation Agent

Pull card_id values from a Google Sheet (via gspread + service account)
and compare with the billing DataFrame to find deleted and missing accounts.

Degrades gracefully when credentials are unavailable (smoke-test safe).
"""

import os
import pandas as pd
from logger import get_logger
from dotenv import load_dotenv

load_dotenv()
log = get_logger(__name__)

GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")
GOOGLE_SHEET_TAB = os.environ.get("GOOGLE_SHEET_TAB_NAME", "Sheet1")
SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "credentials.json")


def _fetch_sheet_card_ids() -> set[str]:
    """Authenticate and pull card_id column from Google Sheets."""
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    gc = gspread.authorize(creds)
    worksheet = gc.open_by_key(GOOGLE_SHEET_ID).worksheet(GOOGLE_SHEET_TAB)

    records = worksheet.get_all_records()
    return {str(r.get("card_id", "")).strip() for r in records if r.get("card_id")}


def run(df: pd.DataFrame) -> dict:
    """Compare billing card_ids with Google Sheet; return reconciliation results."""
    log.info("Reconciliation started")

    # Graceful degradation when credentials are missing
    if not GOOGLE_SHEET_ID:
        log.warning(
            "GOOGLE_SHEET_ID is empty — skipping reconciliation (no real credentials)"
        )
        return {"deleted": [], "missing": [], "matched": 0, "skipped": True}

    if not os.path.isfile(SERVICE_ACCOUNT_FILE):
        log.warning(
            "Service account file '%s' not found — skipping reconciliation",
            SERVICE_ACCOUNT_FILE,
        )
        return {"deleted": [], "missing": [], "matched": 0, "skipped": True}

    try:
        sheet_ids = _fetch_sheet_card_ids()
    except Exception as exc:
        log.warning("Google Sheets API error — skipping reconciliation: %s", exc)
        return {"deleted": [], "missing": [], "matched": 0, "skipped": True}

    billing_ids = set(df["card_id"].astype(str).str.strip())

    deleted = sorted(sheet_ids - billing_ids)   # in sheet, not in billing
    missing = sorted(billing_ids - sheet_ids)   # in billing, not in sheet
    matched = len(billing_ids & sheet_ids)

    log.info(
        "Reconciliation complete — matched: %d, deleted: %d, missing: %d",
        matched, len(deleted), len(missing),
    )
    return {"deleted": deleted, "missing": missing, "matched": matched, "skipped": False}
