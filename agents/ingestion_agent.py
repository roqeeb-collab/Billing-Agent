import os
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

# Supported MIME types for Drive files
SUPPORTED_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",  # .xlsx
    "application/vnd.ms-excel.sheet.macroEnabled.12": "xlsm",                    # .xlsm
    "text/csv": "csv",                                                             # .csv
    "application/vnd.google-apps.spreadsheet": "gsheet",                          # Google Sheet
}


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


def _read_drive_file(drive, file_meta):
    """Download and read a Drive file into a DataFrame. Supports xlsx, xlsm, csv, gsheet."""
    mime_type = file_meta["mimeType"]
    file_format = SUPPORTED_MIME_TYPES.get(mime_type)

    if file_format == "gsheet":
        return _fetch_from_google_sheet(file_meta["id"])

    if file_format in ("xlsx", "xlsm", "csv"):
        os.makedirs(INPUT_FOLDER, exist_ok=True)
        dest_path = os.path.join(INPUT_FOLDER, file_meta["name"])
        drive.download_file(file_meta["id"], dest_path)

        if file_format in ("xlsx", "xlsm"):
            return pd.read_excel(dest_path, engine="openpyxl")
        elif file_format == "csv":
            return pd.read_csv(dest_path)

    log.warning("Unsupported file type '%s' for file '%s' — skipping.", mime_type, file_meta["name"])
    return None


def _standardise_columns(df):
    """Normalise column names to lowercase snake_case."""
    df.columns = (
        df.columns.str.strip()
        .str.lower()
        .str.replace(r"\s+", "_", regex=True)
    )
    return df


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

        rows = df.values.tolist()
        # Convert timestamps/NaNs to strings to avoid serialisation issues
        rows = [[str(item) if pd.notnull(item) else "" for item in row] for row in rows]

        worksheet.append_rows(rows, value_input_option="USER_ENTERED")
        log.info("Successfully appended to Google Sheet")
    except Exception as e:
        log.error("Failed to append to Google Sheet %s: %s", sheet_id, e)


def run(force_full_load: bool = False):
    """
    Ingestion workflow:

    - force_full_load=True (Monthly mode):
        Loads the entire Master Sheet and returns a single DataFrame.

    - force_full_load=False (Daily mode):
        Scans ALL files in the Drive folder (xlsx, xlsm, csv, gsheet).
        Deduplicates each file against the Master Sheet AND against other
        files processed in the same batch (by card_id).
        Appends each file's new rows to the Master Sheet individually.
        Returns a list of dicts: [{"filename": str, "df": DataFrame}, ...]
        — one entry per file that had genuinely new records.
    """
    # ── 1. Fetch Master Sheet for deduplication ────────────────────────────
    df_master = None
    if GOOGLE_SHEET_ID:
        df_master = _fetch_from_google_sheet(GOOGLE_SHEET_ID)
        if df_master is not None and not df_master.empty:
            df_master = _standardise_columns(df_master)
            df_master = df_master.drop_duplicates(subset="card_id", keep="first").reset_index(drop=True)

    # ── 2. Monthly mode ────────────────────────────────────────────────────
    if force_full_load:
        log.info("Monthly Mode: Returning full Master Sheet data.")
        return df_master if df_master is not None else pd.DataFrame()

    # ── 3. Daily mode — process ALL files in the Drive folder ──────────────
    if not GOOGLE_DRIVE_DAILY_FOLDER_ID:
        log.warning("GOOGLE_DRIVE_DAILY_FOLDER_ID not set — skipping Drive ingestion.")
        return []

    if not os.path.isfile(SERVICE_ACCOUNT_FILE):
        log.warning("Service account file '%s' not found — skipping Drive ingestion.", SERVICE_ACCOUNT_FILE)
        return []

    try:
        log.info("Scanning Google Drive folder %s for all files", GOOGLE_DRIVE_DAILY_FOLDER_ID)
        drive = DriveService(SERVICE_ACCOUNT_FILE)
        files = drive.list_files_in_folder(GOOGLE_DRIVE_DAILY_FOLDER_ID)
    except Exception as e:
        log.error("Failed to list Drive folder: %s", e)
        return []

    if not files:
        log.info("No files found in Drive folder.")
        return []

    # Keep only supported file types
    supported_files = [f for f in files if f["mimeType"] in SUPPORTED_MIME_TYPES]
    log.info(
        "Found %d supported file(s) in folder (out of %d total).",
        len(supported_files), len(files)
    )

    if not supported_files:
        return []

    # Running set of card_ids already committed this batch (starts from master)
    seen_in_batch = (
        set(df_master["card_id"].tolist())
        if df_master is not None and not df_master.empty
        else set()
    )

    results = []

    for file_meta in supported_files:
        filename = file_meta["name"]
        log.info("Processing file: %s", filename)

        try:
            df_new = _read_drive_file(drive, file_meta)
        except Exception as e:
            log.error("Failed to read file '%s': %s — skipping.", filename, e)
            continue

        if df_new is None or df_new.empty:
            log.info("File '%s' is empty or unreadable — skipping.", filename)
            continue

        df_new = _standardise_columns(df_new)

        if "card_id" not in df_new.columns:
            log.warning("File '%s' has no 'card_id' column — skipping.", filename)
            continue

        # Deduplicate: exclude any card_id we have already seen (master + this batch)
        df_delta = df_new[~df_new["card_id"].isin(seen_in_batch)].copy()
        log.info(
            "File '%s': %d total rows → %d new (deduplicated against %d known IDs).",
            filename, len(df_new), len(df_delta), len(seen_in_batch)
        )

        if df_delta.empty:
            log.info("File '%s': no new records — all card_ids already exist.", filename)
            continue

        # Align columns to match the Master Sheet before appending
        if df_master is not None and not df_master.empty:
            # Ensure all master columns exist in delta
            for col in df_master.columns:
                if col not in df_delta.columns:
                    df_delta[col] = ""
            # Reorder delta columns to match master exactly
            df_delta = df_delta[df_master.columns]

        # Append this file's new rows to the Master Sheet
        if GOOGLE_SHEET_ID:
            _append_to_google_sheet(GOOGLE_SHEET_ID, df_delta)

        # Register these IDs so subsequent files in the batch don't duplicate them
        seen_in_batch.update(df_delta["card_id"].tolist())

        results.append({
            "filename": filename,
            "df": df_delta.reset_index(drop=True),
        })

    log.info("Daily ingestion complete: %d file(s) had new data.", len(results))
    return results
