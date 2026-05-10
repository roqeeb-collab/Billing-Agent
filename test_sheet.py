import os
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file(
    os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE"),
    scopes=SCOPES
)

client = gspread.authorize(creds)

sheet = client.open_by_key(
    os.getenv("GOOGLE_SHEET_ID")
)

worksheet = sheet.worksheet(
    os.getenv("GOOGLE_SHEET_TAB_NAME")
)

print(worksheet.get_all_records())
