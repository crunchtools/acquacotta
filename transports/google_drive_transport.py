"""Google Drive transport — thin adapter for JSON file operations on Drive."""

import io

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload

ACQUACOTTA_FOLDER_NAME = "Acquacotta"


class GoogleDriveTransport:
    def __init__(self, drive_service, folder_id):
        self._service = drive_service
        self._folder_id = folder_id
        self._file_id_cache = {}

    def _find_file(self, filename):
        """Find a file by name in the Acquacotta folder. Returns file ID or None."""
        cached = self._file_id_cache.get(filename)
        if cached:
            return cached
        resp = (
            self._service.files()
            .list(
                q=f"name='{filename}' and '{self._folder_id}' in parents and trashed=false",
                fields="files(id)",
                spaces="drive",
            )
            .execute()
        )
        files = resp.get("files", [])
        if files:
            self._file_id_cache[filename] = files[0]["id"]
            return files[0]["id"]
        return None

    def download_file(self, filename):
        """Download a file's content as a string. Returns None if not found."""
        file_id = self._find_file(filename)
        if not file_id:
            return None
        content = self._service.files().get_media(fileId=file_id).execute()
        if isinstance(content, bytes):
            return content.decode("utf-8")
        return str(content)

    def upload_file(self, filename, content):
        """Upload/overwrite a file in the Acquacotta folder."""
        media = MediaIoBaseUpload(
            io.BytesIO(content.encode("utf-8")),
            mimetype="application/json",
            resumable=False,
        )
        file_id = self._find_file(filename)
        if file_id:
            self._service.files().update(
                fileId=file_id,
                media_body=media,
            ).execute()
        else:
            self._service.files().create(
                body={
                    "name": filename,
                    "parents": [self._folder_id],
                    "mimeType": "application/json",
                },
                media_body=media,
                fields="id",
            ).execute()

    def ensure_directory(self):
        """Ensure the Acquacotta folder exists. Returns folder_id.

        If self._folder_id is already set and valid, returns it.
        Otherwise searches for or creates the folder.
        """
        if self._folder_id:
            try:
                self._service.files().get(fileId=self._folder_id, fields="id,trashed").execute()
                return self._folder_id
            except HttpError:
                pass

        resp = (
            self._service.files()
            .list(
                q=f"name='{ACQUACOTTA_FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
                fields="files(id)",
                spaces="drive",
            )
            .execute()
        )
        folders = resp.get("files", [])
        if folders:
            self._folder_id = folders[0]["id"]
            return self._folder_id

        folder = (
            self._service.files()
            .create(
                body={
                    "name": ACQUACOTTA_FOLDER_NAME,
                    "mimeType": "application/vnd.google-apps.folder",
                },
                fields="id",
            )
            .execute()
        )
        self._folder_id = folder["id"]
        return self._folder_id

    def file_exists(self, filename):
        """Check if a file exists in the folder."""
        return self._find_file(filename) is not None
