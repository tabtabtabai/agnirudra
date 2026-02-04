"""Upload recordings to Azure Blob Storage and generate SAS URLs."""

from __future__ import annotations

import datetime
import logging
from pathlib import Path

from azure.identity import ClientSecretCredential
from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
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
        blob_client.upload_blob(f, overwrite=True, content_settings=None)

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
    expiry_time = start_time + datetime.timedelta(days=expiry_days)

    # Azure user delegation keys are limited to 7 days max
    delegation_expiry = start_time + datetime.timedelta(days=min(expiry_days, 7))

    user_delegation_key = blob_service.get_user_delegation_key(
        key_start_time=start_time,
        key_expiry_time=delegation_expiry,
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
        blob_client.upload_blob(f, overwrite=True)

    logger.info("Uploaded thumbnail to %s", blob_path)
    return blob_path


def write_done_marker(settings: AgniSettings, commit_hash: str) -> None:
    """Write a done.marker blob so the orchestrator knows we finished."""
    blob_path = f"pr-{settings.pr_number}/{commit_hash[:8]}/done.marker"
    blob_service = _get_blob_service(settings)
    container = blob_service.get_container_client(settings.azure_storage_container)
    blob_client = container.get_blob_client(blob_path)
    blob_client.upload_blob(b"done", overwrite=True)
    logger.info("Wrote completion marker: %s", blob_path)
