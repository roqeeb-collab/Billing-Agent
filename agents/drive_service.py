import io
import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.service_account import Credentials
from logger import get_logger

log = get_logger(__name__)

class DriveService:
    def __init__(self, credentials_file, scopes=None):
        if scopes is None:
            scopes = ["https://www.googleapis.com/auth/drive.readonly"]
        self.creds = Credentials.from_service_account_file(credentials_file, scopes=scopes)
        self.service = build("drive", "v3", credentials=self.creds)

    def list_files_in_folder(self, folder_id):
        """List files in a specific Google Drive folder, sorted by modification time."""
        query = f"'{folder_id}' in parents and trashed = false"
        results = self.service.files().list(
            q=query,
            fields="files(id, name, modifiedTime, mimeType)",
            orderBy="modifiedTime desc"
        ).execute()
        return results.get("files", [])

    def download_file(self, file_id, destination_path):
        """Download a file from Google Drive."""
        request = self.service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            log.debug("Download %d%%.", int(status.progress() * 100))

        # Ensure the destination directory exists
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        
        with open(destination_path, "wb") as f:
            f.write(fh.getvalue())
        log.info("Downloaded file from Drive to %s", destination_path)
