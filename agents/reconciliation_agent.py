import os
import pandas as pd
from logger import get_logger
from dotenv import load_dotenv
from agents.drive_service import DriveService

load_dotenv()
log = get_logger(__name__)

GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")
GOOGLE_SHEET_TAB = os.environ.get("GOOGLE_SHEET_TAB_NAME", "Sheet1")
SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "credentials.json")
GOOGLE_DRIVE_MASTERSHEET_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_MASTERSHEET_FOLDER_ID", "")
INPUT_FOLDER = os.environ.get("INPUT_FOLDER", "data/input")


def _download_mastersheet_from_drive():
    """Download the latest .xlsx mastersheet from the configured Google Drive folder."""
    if not GOOGLE_DRIVE_MASTERSHEET_FOLDER_ID:
        return None

    if not os.path.isfile(SERVICE_ACCOUNT_FILE):
        log.warning("Service account file '%s' not found — skipping mastersheet download.", SERVICE_ACCOUNT_FILE)
        return None

    try:
        log.info("Checking Google Drive folder %s for mastersheet", GOOGLE_DRIVE_MASTERSHEET_FOLDER_ID)
        drive = DriveService(SERVICE_ACCOUNT_FILE)
        files = drive.list_files_in_folder(GOOGLE_DRIVE_MASTERSHEET_FOLDER_ID)
        
        # Filter for .xlsx files
        xlsx_files = [f for f in files if f['name'].lower().endswith('.xlsx')]
        
        if not xlsx_files:
            log.warning("No .xlsx mastersheet found in Drive folder %s", GOOGLE_DRIVE_MASTERSHEET_FOLDER_ID)
            return None

        latest_file = xlsx_files[0]
        dest_path = os.path.join(INPUT_FOLDER, "mastersheet_" + latest_file['name'])
        drive.download_file(latest_file['id'], dest_path)
        return dest_path
    except Exception as e:
        log.error("Failed to download mastersheet from Drive: %s", e)
        return None


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


def _fetch_excel_card_ids(file_path: str) -> set[str]:
    """Read card_id column from a local Excel mastersheet."""
    try:
        df = pd.read_excel(file_path, engine="openpyxl")
        # Standardise columns for comparison
        df.columns = df.columns.str.strip().str.lower().str.replace(r"\s+", "_", regex=True)
        if "card_id" not in df.columns:
            log.error("Column 'card_id' not found in mastersheet %s", file_path)
            return set()
        return {str(val).strip() for val in df["card_id"].dropna() if str(val).strip()}
    except Exception as e:
        log.error("Error reading mastersheet Excel: %s", e)
        return set()


def run(df: pd.DataFrame) -> dict:
    """Compare billing card_ids with Mastersheet (either from Drive Excel or Google Sheet)."""
    log.info("Reconciliation started")

    sheet_ids = set()

    # Priority 1: Check for Excel mastersheet on Google Drive
    excel_path = _download_mastersheet_from_drive()
    if excel_path:
        log.info("Using Excel mastersheet from Drive: %s", excel_path)
        sheet_ids = _fetch_excel_card_ids(excel_path)
    
    # Priority 2: Fall back to Google Sheet if no Excel was found but ID is set
    elif GOOGLE_SHEET_ID:
        log.info("Using Google Sheet ID: %s", GOOGLE_SHEET_ID)
        try:
            sheet_ids = _fetch_sheet_card_ids()
        except Exception as exc:
            log.warning("Google Sheets API error: %s", exc)
    
    if not sheet_ids:
        log.warning("No mastersheet data found (Drive Excel or Google Sheet) — skipping reconciliation")
        return {"deleted": [], "missing": [], "matched": 0, "skipped": True}

    billing_ids = set(df["card_id"].astype(str).str.strip())

    deleted = sorted(sheet_ids - billing_ids)   # in mastersheet, not in billing
    missing = sorted(billing_ids - sheet_ids)   # in billing, not in mastersheet
    matched = len(billing_ids & sheet_ids)

    log.info(
        "Reconciliation complete — matched: %d, deleted: %d, missing: %d",
        matched, len(deleted), len(missing),
    )
    return {"deleted": deleted, "missing": missing, "matched": matched, "skipped": False}
