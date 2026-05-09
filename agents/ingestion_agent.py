"""
Stage 1 — Ingestion Agent

Scan data/input/ for the latest .xlsx file, standardise column names,
and deduplicate on card_id.
"""

import os
import glob
import pandas as pd
from logger import get_logger
from dotenv import load_dotenv

load_dotenv()
log = get_logger(__name__)

INPUT_FOLDER = os.environ.get("INPUT_FOLDER", "data/input")


def run() -> pd.DataFrame:
    """Ingest the most recent .xlsx from the input folder."""
    log.info("Ingestion started — scanning %s", INPUT_FOLDER)

    pattern = os.path.join(INPUT_FOLDER, "*.xlsx")
    files = glob.glob(pattern)

    if not files:
        raise FileNotFoundError(f"No .xlsx files found in {INPUT_FOLDER}")

    # Pick the most recently modified file
    latest = max(files, key=os.path.getmtime)
    log.info("Selected file: %s", latest)

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
