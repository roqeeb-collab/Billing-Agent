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
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")
GOOGLE_SHEET_TAB_NAME = os.environ.get("GOOGLE_SHEET_TAB_NAME", "Sheet1")
SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "credentials.json")


def _fetch_from_google_sheet(sheet_id):
    """Fetch data from a specific Google Sheet ID."""
    try:
        log.info("Fetching data from Google Sheet ID: %s", sheet_id)
        import gspread
        from google.oauth2.service_account import Credentials
        scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
        gc = gspread.authorize(creds)
        
        spreadsheet = gc.open_by_key(sheet_id)
        worksheet = spreadsheet.worksheet(GOOGLE_SHEET_TAB_NAME)
        data = worksheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        log.error("Failed to fetch from Google Sheet %s: %s", sheet_id, e)
        return None


def _download_latest_from_drive():
    """Fetch the most recent data from Drive (Sheet ID priority, then folder scanning)."""
    if not os.path.isfile(SERVICE_ACCOUNT_FILE):
        log.warning("Service account file '%s' not found — skipping Drive ingestion.", SERVICE_ACCOUNT_FILE)
        return None

    # Priority 1: Specific Google Sheet ID
    if GOOGLE_SHEET_ID:
        df = _fetch_from_google_sheet(GOOGLE_SHEET_ID)
        if df is not None and not df.empty:
            log.info("Successfully fetched %d rows from Google Sheet ID: %s", len(df), GOOGLE_SHEET_ID)
            return df

    # Priority 2: Scan folder for latest file
    if not GOOGLE_DRIVE_DAILY_FOLDER_ID:
        return None

    try:
        log.info("Scanning Google Drive folder %s for latest files", GOOGLE_DRIVE_DAILY_FOLDER_ID)
        drive = DriveService(SERVICE_ACCOUNT_FILE)
        files = drive.list_files_in_folder(GOOGLE_DRIVE_DAILY_FOLDER_ID)
        
        if not files:
            log.warning("No files found in Drive folder %s", GOOGLE_DRIVE_DAILY_FOLDER_ID)
            return None

        latest_file = files[0]
        mime_type = latest_file['mimeType']

        # Option A: It's an Excel file
        if mime_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
            os.makedirs(INPUT_FOLDER, exist_ok=True)
            dest_path = os.path.join(INPUT_FOLDER, latest_file['name'])
            drive.download_file(latest_file['id'], dest_path)
            return pd.read_excel(dest_path, engine="openpyxl")
        
        # Option B: It's a Google Sheet
        elif mime_type == 'application/vnd.google-apps.spreadsheet':
            return _fetch_from_google_sheet(latest_file['id'])
        
        else:
            log.warning("Latest file '%s' is not a supported spreadsheet type.", latest_file['name'])
            return None

    except Exception as e:
        log.error("Failed to scan Drive folder: %s", e)
        return None


def _append_to_google_sheet(sheet_id, df):
    """Append a DataFrame to the bottom of a specific Google Sheet."""
    if df.empty:
        return
    try:
        log.info("Appending %d rows to Master Google Sheet: %s", len(df), sheet_id)
        import gspread
        from google.oauth2.service_account import Credentials
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
        gc = gspread.authorize(creds)
        
        spreadsheet = gc.open_by_key(sheet_id)
        worksheet = spreadsheet.worksheet(GOOGLE_SHEET_TAB_NAME)
        
        # Prepare data for append (convert all values to strings to avoid serialisation issues)
        # Note: gspread.append_rows expects a list of lists.
        # We include the header only if the sheet is empty, but usually it's not.
        rows = df.values.tolist()
        
        # Convert timestamps/NaNs to strings
        rows = [[str(item) if pd.notnull(item) else "" for item in row] for row in rows]
        
        worksheet.append_rows(rows, value_input_option="USER_ENTERED")
        log.info("Successfully appended to Google Sheet")
    except Exception as e:
        log.error("Failed to append to Google Sheet %s: %s", sheet_id, e)


def run(force_full_load: bool = False) -> pd.DataFrame:
    """
    Ingestion workflow:
    - If force_full_load is True: Loads the entire Master Sheet (for Monthly reports).
    - If False (Daily): Scans for new files to append and returns the delta.
    """
    # 1. Fetch Master Sheet (always needed for deduplication or full load)
    df_master = None
    if GOOGLE_SHEET_ID:
        df_master = _fetch_from_google_sheet(GOOGLE_SHEET_ID)
        if df_master is not None and not df_master.empty:
            df_master.columns = (
                df_master.columns.str.strip()
                .str.lower()
                .str.replace(r"\s+", "_", regex=True)
            )
            df_master = df_master.drop_duplicates(subset="card_id", keep="first").reset_index(drop=True)

    if force_full_load:
        log.info("Monthly Mode: Returning full Master Sheet data.")
        return df_master if df_master is not None else pd.DataFrame()

    # 2. Daily Mode: Try to fetch latest from Drive folder to append
    df_new = None
    if GOOGLE_DRIVE_DAILY_FOLDER_ID:
        try:
            log.info("Scanning Google Drive folder %s for latest file", GOOGLE_DRIVE_DAILY_FOLDER_ID)
            drive = DriveService(SERVICE_ACCOUNT_FILE)
            files = drive.list_files_in_folder(GOOGLE_DRIVE_DAILY_FOLDER_ID)
            
            if files:
                latest_file = files[0]
                mime_type = latest_file['mimeType']
                log.info("Found latest file: %s", latest_file['name'])

                if mime_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
                    dest_path = os.path.join(INPUT_FOLDER, latest_file['name'])
                    drive.download_file(latest_file['id'], dest_path)
                    df_new = pd.read_excel(dest_path, engine="openpyxl")
                elif mime_type == 'application/vnd.google-apps.spreadsheet':
                    df_new = _fetch_from_google_sheet(latest_file['id'])
            else:
                log.info("No files found in Drive folder.")

        except Exception as e:
            log.error("Failed to fetch from Drive folder: %s", e)

    # Process and Return Delta
    if df_new is not None and not df_new.empty:
        # Standardise new data columns
        df_new.columns = (
            df_new.columns.str.strip()
            .str.lower()
            .str.replace(r"\s+", "_", regex=True)
        )
        
        # Deduplicate against Master
        if df_master is not None and not df_master.empty:
            df_delta = df_new[~df_new['card_id'].isin(df_master['card_id'])].copy()
            log.info("Filtered %d new rows against %d existing Master records.", len(df_delta), len(df_master))
        else:
            df_delta = df_new.copy()

        if not df_delta.empty:
            if GOOGLE_SHEET_ID:
                _append_to_google_sheet(GOOGLE_SHEET_ID, df_delta)
            return df_delta.reset_index(drop=True)
        else:
            log.info("No actually new records (all exists in Master).")
            return pd.DataFrame()

    log.info("No new data file found for daily run.")
    return pd.DataFrame()
