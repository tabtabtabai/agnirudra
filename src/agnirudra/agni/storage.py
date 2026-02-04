"""Upload recordings to Azure Blob Storage and generate SAS URLs."""

from __future__ import annotations

import datetime
import logging
from pathlib import Path

from azure.identity import ClientSecretCredential
from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    ContentSettings,
    generate_blob_sas,
)

from agnirudra.config import AgniSettings

logger = logging.getLogger(__name__)


def _get_blob_service(settings: AgniSettings) -> BlobServiceClient:
    credential = ClientSecretCredential(
        tenant_id=settings.azure_tenant_id,
        client_id=settings.azure_client_id,
        client_secret=settings.azure_client_secret,
    )
    return BlobServiceClient(
        account_url=f"https://{settings.azure_storage_account}.blob.core.windows.net",
        credential=credential,
    )


def upload_recording(
    settings: AgniSettings,
    local_path: Path,
    commit_hash: str,
) -> str:
    """Upload a recording file and return the blob path."""
    blob_path = f"pr-{settings.pr_number}/{commit_hash[:8]}/recording.mp4"
    blob_service = _get_blob_service(settings)
    container = blob_service.get_container_client(settings.azure_storage_container)
    blob_client = container.get_blob_client(blob_path)

    with open(local_path, "rb") as f:
        blob_client.upload_blob(
            f,
            overwrite=True,
            content_settings=ContentSettings(content_type="video/mp4"),
        )

    logger.info("Uploaded recording to %s", blob_path)
    return blob_path


def generate_sas_url(
    settings: AgniSettings,
    blob_path: str,
    expiry_days: int = 30,
) -> str:
    """Generate a SAS URL for a blob, valid for expiry_days."""
    credential = ClientSecretCredential(
        tenant_id=settings.azure_tenant_id,
        client_id=settings.azure_client_id,
        client_secret=settings.azure_client_secret,
    )

    # We need the account key for SAS generation; fall back to user delegation key
    blob_service = BlobServiceClient(
        account_url=f"https://{settings.azure_storage_account}.blob.core.windows.net",
        credential=credential,
    )

    start_time = datetime.datetime.now(datetime.timezone.utc)
    # User delegation keys are limited to 7 days; SAS cannot outlive the key
    capped_days = min(expiry_days, 7)
    expiry_time = start_time + datetime.timedelta(days=capped_days)

    user_delegation_key = blob_service.get_user_delegation_key(
        key_start_time=start_time,
        key_expiry_time=expiry_time,
    )

    sas_token = generate_blob_sas(
        account_name=settings.azure_storage_account,
        container_name=settings.azure_storage_container,
        blob_name=blob_path,
        user_delegation_key=user_delegation_key,
        permission=BlobSasPermissions(read=True),
        expiry=expiry_time,
        start=start_time,
    )

    url = (
        f"https://{settings.azure_storage_account}.blob.core.windows.net/"
        f"{settings.azure_storage_container}/{blob_path}?{sas_token}"
    )
    logger.info("Generated SAS URL (expires in %d days)", expiry_days)
    return url


def upload_thumbnail(
    settings: AgniSettings,
    local_path: Path,
    commit_hash: str,
) -> str:
    """Upload a thumbnail image and return the blob path."""
    blob_path = f"pr-{settings.pr_number}/{commit_hash[:8]}/thumbnail.jpg"
    blob_service = _get_blob_service(settings)
    container = blob_service.get_container_client(settings.azure_storage_container)
    blob_client = container.get_blob_client(blob_path)

    with open(local_path, "rb") as f:
        blob_client.upload_blob(
            f,
            overwrite=True,
            content_settings=ContentSettings(content_type="image/jpeg"),
        )

    logger.info("Uploaded thumbnail to %s", blob_path)
    return blob_path


def upload_player_page(
    settings: AgniSettings,
    recording_sas_url: str,
    commit_hash: str,
) -> str:
    """Upload an HTML video player page and return the blob path."""
    blob_path = f"pr-{settings.pr_number}/{commit_hash[:8]}/player.html"
    html = _build_player_html(recording_sas_url)
    blob_service = _get_blob_service(settings)
    container = blob_service.get_container_client(settings.azure_storage_container)
    blob_client = container.get_blob_client(blob_path)
    blob_client.upload_blob(
        html.encode(),
        overwrite=True,
        content_settings=ContentSettings(content_type="text/html"),
    )
    logger.info("Uploaded player page to %s", blob_path)
    return blob_path


def _build_player_html(recording_url: str) -> str:
    """Build a minimal HTML page with a video player."""
    from html import escape

    safe_url = escape(recording_url, quote=True)
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agni Test Recording</title>
<style>
  body {{ margin:0; background:#111; display:flex; align-items:center;
         justify-content:center; min-height:100vh; font-family:system-ui }}
  video {{ max-width:100%; max-height:100vh; border-radius:8px;
           box-shadow:0 4px 24px rgba(0,0,0,.5) }}
</style>
</head>
<body>
<video controls autoplay>
  <source src="{safe_url}" type="video/mp4">
  <a href="{safe_url}">Download recording</a>
</video>
</body>
</html>"""


def delete_done_marker(settings: AgniSettings, commit_hash: str) -> None:
    """Delete any existing done.marker so stale results aren't picked up."""
    blob_path = f"pr-{settings.pr_number}/{commit_hash[:8]}/done.marker"
    blob_service = _get_blob_service(settings)
    container = blob_service.get_container_client(settings.azure_storage_container)
    blob_client = container.get_blob_client(blob_path)
    try:
        blob_client.delete_blob()
        logger.info("Deleted stale done marker: %s", blob_path)
    except Exception:
        pass  # Marker didn't exist, nothing to clean up


def write_done_marker(
    settings: AgniSettings, commit_hash: str, verdict_json: str = "done"
) -> None:
    """Write a done.marker blob so the orchestrator knows we finished.

    The marker content is the verdict JSON so the orchestrator can
    read the pass/fail result without a separate blob.
    """
    blob_path = f"pr-{settings.pr_number}/{commit_hash[:8]}/done.marker"
    blob_service = _get_blob_service(settings)
    container = blob_service.get_container_client(settings.azure_storage_container)
    blob_client = container.get_blob_client(blob_path)
    blob_client.upload_blob(verdict_json.encode(), overwrite=True)
    logger.info("Wrote completion marker: %s", blob_path)
