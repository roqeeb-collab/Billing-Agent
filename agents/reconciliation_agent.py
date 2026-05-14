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


def _find_mastersheet_on_drive():
    """Find the latest .xlsx or Google Sheet mastersheet in the configured Drive folder."""
    if not GOOGLE_DRIVE_MASTERSHEET_FOLDER_ID:
        return None

    if not os.path.isfile(SERVICE_ACCOUNT_FILE):
        log.warning("Service account file '%s' not found.", SERVICE_ACCOUNT_FILE)
        return None

    try:
        log.info("Checking Google Drive folder %s for mastersheet", GOOGLE_DRIVE_MASTERSHEET_FOLDER_ID)
        drive = DriveService(SERVICE_ACCOUNT_FILE)
        files = drive.list_files_in_folder(GOOGLE_DRIVE_MASTERSHEET_FOLDER_ID)
        
        # Filter for .xlsx files or Google Sheets
        valid_files = [
            f for f in files 
            if f['name'].lower().endswith('.xlsx') or 
               f['mimeType'] == 'application/vnd.google-apps.spreadsheet'
        ]
        
        if not valid_files:
            log.warning("No mastersheet (Excel or Google Sheet) found in Drive folder %s", GOOGLE_DRIVE_MASTERSHEET_FOLDER_ID)
            return None

        # Return the latest one
        return valid_files[0]
    except Exception as e:
        log.error("Failed to scan Drive for mastersheet: %s", e)
        return None


def _fetch_sheet_card_ids(sheet_id: str, tab_name: str = "Sheet1") -> set[str]:
    """Authenticate and pull card_id column from a specific Google Sheet."""
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    gc = gspread.authorize(creds)
    worksheet = gc.open_by_key(sheet_id).worksheet(tab_name)

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
    """Compare billing card_ids with Mastersheet (either from Drive Excel/Sheet or Live Google Sheet)."""
    log.info("Reconciliation started")

    sheet_ids = set()

    # Priority 1: Check for Reference Mastersheet on Google Drive (Folder 1dJr...)
    ref_file = _find_mastersheet_on_drive()
    if ref_file:
        mime_type = ref_file['mimeType']
        log.info("Found reference mastersheet on Drive: %s (%s)", ref_file['name'], mime_type)
        
        try:
            if mime_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
                # It's an Excel file
                drive = DriveService(SERVICE_ACCOUNT_FILE)
                dest_path = os.path.join(INPUT_FOLDER, "mastersheet_" + ref_file['name'])
                drive.download_file(ref_file['id'], dest_path)
                sheet_ids = _fetch_excel_card_ids(dest_path)
            elif mime_type == 'application/vnd.google-apps.spreadsheet':
                # It's a Google Sheet
                sheet_ids = _fetch_sheet_card_ids(ref_file['id'], GOOGLE_SHEET_TAB)
        except Exception as e:
            log.error("Failed to process reference mastersheet: %s", e)
    
    # Priority 2: Fall back to Live Google Sheet if no reference was found
    if not sheet_ids and GOOGLE_SHEET_ID:
        log.info("No reference file found. Using Live Google Sheet ID: %s", GOOGLE_SHEET_ID)
        try:
            sheet_ids = _fetch_sheet_card_ids(GOOGLE_SHEET_ID, GOOGLE_SHEET_TAB)
        except Exception as exc:
            log.warning("Live Google Sheets API error: %s", exc)
    
    if not sheet_ids:
        log.warning("No mastersheet data found — skipping reconciliation")
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
