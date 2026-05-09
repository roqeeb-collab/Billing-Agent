"""Generate synthetic test data matching the real data schema for smoke testing."""

import os
import pandas as pd

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data", "input")
os.makedirs(OUTPUT_DIR, exist_ok=True)

data = {
    "card_id": [
        "0002ffeb7a414ccdab0e54b0b1ea53e2",
        "00040d7525a74c069afb4083b2614d82",
        "00156eab1a2d40dd9b471d626ccafeba",
        "0002ffeb7a414ccdab0e54b0b1ea53e2",  # duplicate of row 1
    ],
    "created_at": [
        "2026-04-28",
        "2025-09-10",
        "2025-12-15",
        "2026-04-28",  # duplicate
    ],
    "card_limit": [1000000, 1000000, 1000000, 1000000],
    "is_real_ten_thousand_card": [False, False, False, False],
    "card_name": [
        "Aly SARE",
        "EricCodjo TOSSOU",
        "ArielMakpo SOSSOULOKO",
        "Aly SARE",  # duplicate
    ],
    "merchant_name": [
        "Axa Zara LLC",
        "Axa Zara LLC",
        "Axa Zara LLC",
        "Axa Zara LLC",
    ],
}

df = pd.DataFrame(data)
path = os.path.join(OUTPUT_DIR, "test_accounts.xlsx")
df.to_excel(path, index=False, engine="openpyxl")
print(f"Created {path} with {len(df)} rows (including 1 duplicate card_id)")
