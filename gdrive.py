"""
gdrive.py – Google Drive upload module for Hotstar/MX Player Leech Bot.

Uploads local video files directly to Google Drive folder:
https://drive.google.com/drive/folders/1SQXO4uP3EWdhaAc8D907g1P3YgEhCVqR

Supports:
  - Service Account JSON (service_account.json)
  - OAuth token (token.json / credentials.json)
  - Live upload progress callback
"""
import logging
from pathlib import Path
from typing import Callable, Optional

import config

log = logging.getLogger("LeechBot.GDrive")

_service = None


def _get_gdrive_service():
    """Build Google Drive API service client."""
    global _service
    if _service is not None:
        return _service

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        sa_file = config.GDRIVE_SA_FILE
        if sa_file.exists():
            scopes = ["https://www.googleapis.com/auth/drive"]
            creds = service_account.Credentials.from_service_account_file(
                str(sa_file), scopes=scopes
            )
            _service = build("drive", "v3", credentials=creds)
            log.info("Google Drive service initialized using Service Account (%s)", sa_file)
            return _service
    except Exception as e:
        log.warning("Could not initialize Service Account GDrive client: %s", e)

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        token_file = Path("token.json")
        if token_file.exists():
            scopes = ["https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_authorized_user_file(str(token_file), scopes)
            _service = build("drive", "v3", credentials=creds)
            log.info("Google Drive service initialized using token.json")
            return _service
    except Exception as e:
        log.warning("Could not initialize token.json GDrive client: %s", e)

    return None


def upload_to_gdrive(
    file_path: Path,
    folder_id: Optional[str] = None,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> Optional[str]:
    """
    Upload *file_path* to Google Drive folder *folder_id* with optional live progress callback.
    Returns direct Google Drive view URL, or None if GDrive is not configured.
    """
    service = _get_gdrive_service()
    if service is None:
        log.info("Google Drive API is not configured (no service_account.json or token.json found).")
        return None

    target_folder = folder_id or config.GDRIVE_FOLDER_ID
    file_name = file_path.name
    total_size = file_path.stat().st_size

    file_metadata = {
        "name": file_name,
        "parents": [target_folder] if target_folder else [],
    }

    try:
        from googleapiclient.http import MediaFileUpload

        media = MediaFileUpload(
            str(file_path),
            mimetype="video/mp4" if file_path.suffix == ".mp4" else "video/x-matroska",
            resumable=True,
            chunksize=10 * 1024 * 1024,  # 10 MB chunks
        )

        request = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, webViewLink",
        )

        log.info("Uploading %s to Google Drive folder %s...", file_name, target_folder)

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status and progress_cb:
                try:
                    progress_cb(status.resumable_progress, total_size)
                except Exception:
                    pass

        file_id = response.get("id")
        web_link = response.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"
        log.info("Uploaded to Google Drive successfully: %s", web_link)
        return web_link
    except Exception as e:
        log.exception("Google Drive upload failed for %s: %s", file_path, e)
        return None
