import os
import glob
import pandas as pd
from logger import get_logger
from dotenv import load_dotenv
from agents.drive_service import DriveService

load_dotenv()
log = get_logger(__name__)

INPUT_FOLDER = os.environ.get("INPUT_FOLDER", "data/input")
GOOGLE_DRIVE_DAILY_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_DAILY_FOLDER_ID", "")
SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "credentials.json")


def _download_latest_from_drive():
    """Fetch the most recent data from Drive (either .xlsx file or Google Sheet)."""
    if not GOOGLE_DRIVE_DAILY_FOLDER_ID:
        return None

    if not os.path.isfile(SERVICE_ACCOUNT_FILE):
        log.warning("Service account file '%s' not found — skipping Drive download.", SERVICE_ACCOUNT_FILE)
        return None

    try:
        log.info("Checking Google Drive folder %s for latest files", GOOGLE_DRIVE_DAILY_FOLDER_ID)
        drive = DriveService(SERVICE_ACCOUNT_FILE)
        files = drive.list_files_in_folder(GOOGLE_DRIVE_DAILY_FOLDER_ID)
        
        if not files:
            log.warning("No files found in Drive folder %s", GOOGLE_DRIVE_DAILY_FOLDER_ID)
            return None

        latest_file = files[0]
        mime_type = latest_file['mimeType']

        # Option A: It's an Excel file
        if mime_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
            dest_path = os.path.join(INPUT_FOLDER, latest_file['name'])
            drive.download_file(latest_file['id'], dest_path)
            return pd.read_excel(dest_path, engine="openpyxl")
        
        # Option B: It's a Google Sheet
        elif mime_type == 'application/vnd.google-apps.spreadsheet':
            log.info("Reading Google Sheet: %s", latest_file['name'])
            import gspread
            from google.oauth2.service_account import Credentials
            scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
            creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
            gc = gspread.authorize(creds)
            worksheet = gc.open_by_key(latest_file['id']).get_worksheet(0)
            return pd.DataFrame(worksheet.get_all_records())
        
        else:
            log.warning("Latest file '%s' is not a supported spreadsheet type.", latest_file['name'])
            return None

    except Exception as e:
        log.error("Failed to fetch from Drive: %s", e)
        return None


def run() -> pd.DataFrame:
    """Ingest the most recent data, preferring Drive if configured."""
    # Try to fetch latest from Drive first
    df = _download_latest_from_drive()

    if df is not None:
        log.info("Data loaded successfully from Google Drive")
    else:
        log.info("Ingestion started — scanning local folder %s", INPUT_FOLDER)
        pattern = os.path.join(INPUT_FOLDER, "*.xlsx")
        files = glob.glob(pattern)

        if not files:
            raise FileNotFoundError(f"No .xlsx files found in {INPUT_FOLDER} and no Drive data available.")

        latest = max(files, key=os.path.getmtime)
        log.info("Selected local file: %s", latest)
        df = pd.read_excel(latest, engine="openpyxl")

    log.info("Raw rows loaded: %d", len(df))

    # Standardise column names: lowercase, strip, underscores
    df.columns = (
        df.columns.str.strip()
        .str.lower()
        .str.replace(r"\s+", "_", regex=True)
    )
    log.debug("Columns after standardisation: %s", list(df.columns))

    # Deduplicate on card_id
    before = len(df)
    df = df.drop_duplicates(subset="card_id", keep="first").reset_index(drop=True)
    dupes_removed = before - len(df)
    log.info("Deduplication: %d duplicates removed, %d rows remain", dupes_removed, len(df))

    return df
