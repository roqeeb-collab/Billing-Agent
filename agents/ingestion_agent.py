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
    # 1. Monthly/Full Load Mode: Just read the Master Sheet
    if force_full_load and GOOGLE_SHEET_ID:
        log.info("Monthly Mode: Loading full data from Master Google Sheet.")
        df = _fetch_from_google_sheet(GOOGLE_SHEET_ID)
        if df is not None:
            df.columns = (
                df.columns.str.strip()
                .str.lower()
                .str.replace(r"\s+", "_", regex=True)
            )
            return df.drop_duplicates(subset="card_id", keep="first").reset_index(drop=True)

    # 2. Daily Mode: Try to fetch latest from Drive folder to append
    df_new = None
    if GOOGLE_DRIVE_DAILY_FOLDER_ID:
        try:
            log.info("Scanning Google Drive folder %s for latest file to append", GOOGLE_DRIVE_DAILY_FOLDER_ID)
            drive = DriveService(SERVICE_ACCOUNT_FILE)
            files = drive.list_files_in_folder(GOOGLE_DRIVE_DAILY_FOLDER_ID)
            
            if files:
                latest_file = files[0]
                mime_type = latest_file['mimeType']
                log.info("Found latest file: %s", latest_file['name'])

                # Option A: It's an Excel file
                if mime_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
                    dest_path = os.path.join(INPUT_FOLDER, latest_file['name'])
                    drive.download_file(latest_file['id'], dest_path)
                    df_new = pd.read_excel(dest_path, engine="openpyxl")
                
                # Option B: It's a Google Sheet (different from the Master)
                elif mime_type == 'application/vnd.google-apps.spreadsheet':
                    df_new = _fetch_from_google_sheet(latest_file['id'])
            else:
                log.info("No files found in Drive folder.")

        except Exception as e:
            log.error("Failed to fetch from Drive folder: %s", e)

    # If we found new data, append it to the Master Sheet
    if df_new is not None and not df_new.empty:
        # Standardise new data columns before appending
        df_new.columns = (
            df_new.columns.str.strip()
            .str.lower()
            .str.replace(r"\s+", "_", regex=True)
        )
        
        # Append to Master if configured
        if GOOGLE_SHEET_ID:
            _append_to_google_sheet(GOOGLE_SHEET_ID, df_new)
        
        log.info("Data appended. Reloading full Master Sheet for live reporting.")

    # Always return the full Master Sheet data (Live Data)
    if GOOGLE_SHEET_ID:
        log.info("Fetching full live data from Master Google Sheet.")
        df = _fetch_from_google_sheet(GOOGLE_SHEET_ID)
    else:
        # Fallback to local if no Sheet ID is configured
        log.info("No Master Sheet ID. Scanning local folder.")
        pattern = os.path.join(INPUT_FOLDER, "*.xlsx")
        files = glob.glob(pattern)
        if not files:
            raise FileNotFoundError("No data source available.")
        latest = max(files, key=os.path.getmtime)
        df = pd.read_excel(latest, engine="openpyxl")

    # Standardise column names
    df.columns = (
        df.columns.str.strip()
        .str.lower()
        .str.replace(r"\s+", "_", regex=True)
    )
    
    # Deduplicate to ensure clean reporting of the Master Sheet
    df = df.drop_duplicates(subset="card_id", keep="first").reset_index(drop=True)
    
    return df
