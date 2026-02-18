"""Azure cloud provider: VMs and Blob Storage."""

from __future__ import annotations

import base64
import datetime
import json
import logging
import secrets
import time
from pathlib import Path
from typing import TYPE_CHECKING

from azure.identity import ClientSecretCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.compute.models import (
    DiskCreateOptionTypes,
    HardwareProfile,
    ImageReference,
    LinuxConfiguration,
    ManagedDiskParameters,
    NetworkInterfaceReference,
    NetworkProfile,
    OSDisk,
    OSProfile,
    StorageAccountTypes,
    StorageProfile,
    VirtualMachine,
    VirtualMachineSizeTypes,
)
from azure.mgmt.network import NetworkManagementClient
from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    ContentSettings,
    generate_blob_sas,
)

from agnirudra.agni.cloud.base import CloudProvider

if TYPE_CHECKING:
    from agnirudra.agni.trigger import TestPlan
    from agnirudra.config import AgniSettings

logger = logging.getLogger(__name__)

CLOUD_INIT_TEMPLATE = """\
#!/bin/bash
set -euo pipefail

# Install Docker only if not pre-cached in VM image
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi

# Write env vars to file (avoids shell quoting issues)
cat > /tmp/agni.env <<'ENVEOF'
{env_file_contents}
ENVEOF

# Pull (fast if layers are pre-cached) and run the Agni container
docker pull {docker_image}
docker run --rm --env-file /tmp/agni.env {docker_image}
"""


class AzureProvider(CloudProvider):
    """Azure cloud provider using VMs and Blob Storage."""

    def __init__(self, settings: AgniSettings) -> None:
        super().__init__(settings)
        self._credential = ClientSecretCredential(
            tenant_id=settings.azure_tenant_id,
            client_id=settings.azure_client_id,
            client_secret=settings.azure_client_secret,
        )

    def _vm_name(self, short_hash: str) -> str:
        return f"agni-{self.settings.pr_number}-{short_hash[:8]}-r{self.settings.run_attempt}"

    def _get_blob_service(self) -> BlobServiceClient:
        return BlobServiceClient(
            account_url=f"https://{self.settings.azure_storage_account}.blob.core.windows.net",
            credential=self._credential,
        )

    # ─────────────────────────────────────────────────────────────
    # VM lifecycle
    # ─────────────────────────────────────────────────────────────

    def create_vm(self, test_plan: TestPlan, commit_hash: str) -> str:
        """Create an Azure VM that runs the Agni Docker container."""
        compute_client = ComputeManagementClient(
            self._credential, self.settings.azure_subscription_id
        )
        network_client = NetworkManagementClient(
            self._credential, self.settings.azure_subscription_id
        )

        vm_name = self._vm_name(commit_hash)
        rg = self.settings.azure_resource_group
        location = self.settings.azure_location

        # --- Public IP ---
        ip_name = f"{vm_name}-ip"
        ip_poller = network_client.public_ip_addresses.begin_create_or_update(
            rg,
            ip_name,
            {
                "location": location,
                "sku": {"name": "Standard"},
                "public_ip_allocation_method": "Static",
            },
        )
        ip_result = ip_poller.result()

        # --- NIC ---
        nic_name = f"{vm_name}-nic"
        vnet_name = "agnirudra-vnet"
        subnet_name = "default"
        try:
            network_client.virtual_networks.begin_create_or_update(
                rg,
                vnet_name,
                {
                    "location": location,
                    "address_space": {"address_prefixes": ["10.0.0.0/16"]},
                    "subnets": [
                        {"name": subnet_name, "address_prefix": "10.0.0.0/24"}
                    ],
                },
            ).result()
        except Exception:
            pass  # VNet may already exist

        subnet = network_client.subnets.get(rg, vnet_name, subnet_name)

        nic_poller = network_client.network_interfaces.begin_create_or_update(
            rg,
            nic_name,
            {
                "location": location,
                "ip_configurations": [
                    {
                        "name": "ipconfig1",
                        "subnet": {"id": subnet.id},
                        "public_ip_address": {"id": ip_result.id},
                    }
                ],
            },
        )
        nic_result = nic_poller.result()

        # --- Cloud-init ---
        test_plan_json = json.dumps(
            {
                "description": test_plan.description,
                "start_url": test_plan.start_url,
                "steps": test_plan.steps,
                "pass_criteria": test_plan.pass_criteria,
                "fail_criteria": test_plan.fail_criteria,
            }
        )

        env_vars: dict[str, str] = {
            "AGNI_GITHUB_TOKEN": self.settings.github_token,
            "AGNI_GITHUB_REPOSITORY": self.settings.github_repository,
            "AGNI_PR_NUMBER": str(self.settings.pr_number),
            "AGNI_CLOUD_PROVIDER": "azure",
            "AGNI_AZURE_STORAGE_ACCOUNT": self.settings.azure_storage_account,
            "AGNI_AZURE_STORAGE_CONTAINER": self.settings.azure_storage_container,
            "AGNI_AZURE_SUBSCRIPTION_ID": self.settings.azure_subscription_id,
            "AGNI_AZURE_TENANT_ID": self.settings.azure_tenant_id,
            "AGNI_AZURE_CLIENT_ID": self.settings.azure_client_id,
            "AGNI_AZURE_CLIENT_SECRET": self.settings.azure_client_secret,
            "AGNI_MODEL": self.settings.model,
            "TEST_PLAN": test_plan_json,
        }

        # Pass provider API keys (only the ones that are set)
        if self.settings.anthropic_api_key:
            env_vars["AGNI_ANTHROPIC_API_KEY"] = self.settings.anthropic_api_key
        if self.settings.nvidia_api_key:
            env_vars["AGNI_NVIDIA_API_KEY"] = self.settings.nvidia_api_key
        if self.settings.google_api_key:
            env_vars["AGNI_GOOGLE_API_KEY"] = self.settings.google_api_key

        # Add consumer app secrets
        if self.settings.app_secrets and self.settings.app_secrets.strip() != "{}":
            app_secrets = json.loads(self.settings.app_secrets)
            for key, value in app_secrets.items():
                env_vars[key] = str(value)
            logger.info("Loaded %d app secrets", len(app_secrets))

        env_file_contents = "\n".join(f"{k}={v}" for k, v in env_vars.items())

        cloud_init = CLOUD_INIT_TEMPLATE.format(
            docker_image=self.settings.docker_image,
            env_file_contents=env_file_contents,
        )
        custom_data = base64.b64encode(cloud_init.encode()).decode()

        # --- VM ---
        if self.settings.azure_vm_image:
            image_ref = ImageReference(id=self.settings.azure_vm_image)
            logger.info("Using pre-baked VM image: %s", self.settings.azure_vm_image)
        else:
            image_ref = ImageReference(
                publisher="Canonical",
                offer="0001-com-ubuntu-server-jammy",
                sku="22_04-lts",
                version="latest",
            )

        vm_poller = compute_client.virtual_machines.begin_create_or_update(
            rg,
            vm_name,
            VirtualMachine(
                location=location,
                hardware_profile=HardwareProfile(
                    vm_size=VirtualMachineSizeTypes(self.settings.azure_vm_size)
                ),
                storage_profile=StorageProfile(
                    image_reference=image_ref,
                    os_disk=OSDisk(
                        create_option=DiskCreateOptionTypes.FROM_IMAGE,
                        managed_disk=ManagedDiskParameters(
                            storage_account_type=StorageAccountTypes.STANDARD_LRS
                        ),
                        disk_size_gb=30,
                        delete_option="Delete",
                    ),
                ),
                os_profile=OSProfile(
                    computer_name=vm_name,
                    admin_username="agni",
                    admin_password=secrets.token_urlsafe(32),
                    linux_configuration=LinuxConfiguration(
                        disable_password_authentication=False,
                    ),
                    custom_data=custom_data,
                ),
                network_profile=NetworkProfile(
                    network_interfaces=[
                        NetworkInterfaceReference(id=nic_result.id, primary=True)
                    ]
                ),
                tags={
                    "project": "agnirudra",
                    "pr": str(self.settings.pr_number),
                    "commit": commit_hash[:8],
                },
            ),
        )
        vm_poller.result()
        logger.info("VM %s created in %s", vm_name, rg)
        return vm_name

    def poll_for_completion(
        self, commit_hash: str, timeout: int | None = None
    ) -> dict | None:
        """Poll Azure Blob Storage for the done marker."""
        blob_service = self._get_blob_service()
        container_client = blob_service.get_container_client(
            self.settings.azure_storage_container
        )
        marker_blob = f"{self._object_prefix(commit_hash)}/done.marker"

        timeout = timeout or self.settings.vm_timeout_seconds
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                blob_client = container_client.get_blob_client(marker_blob)
                data = blob_client.download_blob().readall().decode()
                logger.info("Completion marker found: %s", marker_blob)
                try:
                    return json.loads(data)
                except (json.JSONDecodeError, ValueError):
                    return {"passed": True, "summary": data}
            except Exception:
                time.sleep(15)

        logger.warning("Timed out waiting for completion marker")
        return None

    def teardown_vm(self, commit_hash: str) -> None:
        """Delete the VM and associated resources."""
        compute_client = ComputeManagementClient(
            self._credential, self.settings.azure_subscription_id
        )
        network_client = NetworkManagementClient(
            self._credential, self.settings.azure_subscription_id
        )

        vm_name = self._vm_name(commit_hash)
        rg = self.settings.azure_resource_group

        # Delete VM (os disk auto-deletes due to delete_option=Delete)
        logger.info("Deleting VM %s", vm_name)
        try:
            compute_client.virtual_machines.begin_delete(rg, vm_name).result()
        except Exception as exc:
            logger.warning("Failed to delete VM %s: %s", vm_name, exc)

        # Delete NIC
        try:
            network_client.network_interfaces.begin_delete(
                rg, f"{vm_name}-nic"
            ).result()
        except Exception as exc:
            logger.warning("Failed to delete NIC: %s", exc)

        # Delete public IP
        try:
            network_client.public_ip_addresses.begin_delete(
                rg, f"{vm_name}-ip"
            ).result()
        except Exception as exc:
            logger.warning("Failed to delete public IP: %s", exc)

        logger.info("Teardown complete for %s", vm_name)

    # ─────────────────────────────────────────────────────────────
    # Object storage
    # ─────────────────────────────────────────────────────────────

    def upload_recording(self, local_path: Path, commit_hash: str) -> str:
        """Upload a recording file and return the blob path."""
        blob_path = f"{self._object_prefix(commit_hash)}/recording.mp4"
        blob_service = self._get_blob_service()
        container = blob_service.get_container_client(
            self.settings.azure_storage_container
        )
        blob_client = container.get_blob_client(blob_path)

        with open(local_path, "rb") as f:
            blob_client.upload_blob(
                f,
                overwrite=True,
                content_settings=ContentSettings(content_type="video/mp4"),
            )

        logger.info("Uploaded recording to %s", blob_path)
        return blob_path

    def upload_thumbnail(self, local_path: Path, commit_hash: str) -> str:
        """Upload a thumbnail image and return the blob path."""
        blob_path = f"{self._object_prefix(commit_hash)}/thumbnail.jpg"
        blob_service = self._get_blob_service()
        container = blob_service.get_container_client(
            self.settings.azure_storage_container
        )
        blob_client = container.get_blob_client(blob_path)

        with open(local_path, "rb") as f:
            blob_client.upload_blob(
                f,
                overwrite=True,
                content_settings=ContentSettings(content_type="image/jpeg"),
            )

        logger.info("Uploaded thumbnail to %s", blob_path)
        return blob_path

    def upload_player_page(self, recording_url: str, commit_hash: str) -> str:
        """Upload an HTML video player page and return the blob path."""
        blob_path = f"{self._object_prefix(commit_hash)}/player.html"
        html = self._build_player_html(recording_url)
        blob_service = self._get_blob_service()
        container = blob_service.get_container_client(
            self.settings.azure_storage_container
        )
        blob_client = container.get_blob_client(blob_path)
        blob_client.upload_blob(
            html.encode(),
            overwrite=True,
            content_settings=ContentSettings(content_type="text/html"),
        )
        logger.info("Uploaded player page to %s", blob_path)
        return blob_path

    def upload_trace(self, local_path: Path, commit_hash: str) -> str:
        """Upload the agent trace log and return the blob path."""
        blob_path = f"{self._object_prefix(commit_hash)}/trace.log"
        blob_service = self._get_blob_service()
        container = blob_service.get_container_client(
            self.settings.azure_storage_container
        )
        blob_client = container.get_blob_client(blob_path)

        with open(local_path, "rb") as f:
            blob_client.upload_blob(
                f,
                overwrite=True,
                content_settings=ContentSettings(content_type="text/plain"),
            )

        logger.info("Uploaded trace to %s", blob_path)
        return blob_path

    def generate_public_url(self, object_path: str, expiry_days: int = 7) -> str:
        """Generate a SAS URL for a blob."""
        blob_service = self._get_blob_service()

        start_time = datetime.datetime.now(datetime.timezone.utc)
        # User delegation keys are limited to 7 days
        capped_days = min(expiry_days, 7)
        expiry_time = start_time + datetime.timedelta(days=capped_days)

        user_delegation_key = blob_service.get_user_delegation_key(
            key_start_time=start_time,
            key_expiry_time=expiry_time,
        )

        sas_token = generate_blob_sas(
            account_name=self.settings.azure_storage_account,
            container_name=self.settings.azure_storage_container,
            blob_name=object_path,
            user_delegation_key=user_delegation_key,
            permission=BlobSasPermissions(read=True),
            expiry=expiry_time,
            start=start_time,
        )

        url = (
            f"https://{self.settings.azure_storage_account}.blob.core.windows.net/"
            f"{self.settings.azure_storage_container}/{object_path}?{sas_token}"
        )
        logger.info("Generated SAS URL (expires in %d days)", capped_days)
        return url

    def delete_done_marker(self, commit_hash: str) -> None:
        """Delete any existing done marker."""
        blob_path = f"{self._object_prefix(commit_hash)}/done.marker"
        blob_service = self._get_blob_service()
        container = blob_service.get_container_client(
            self.settings.azure_storage_container
        )
        blob_client = container.get_blob_client(blob_path)
        try:
            blob_client.delete_blob()
            logger.info("Deleted stale done marker: %s", blob_path)
        except Exception:
            pass  # Marker didn't exist

    def write_done_marker(
        self, commit_hash: str, verdict_json: str = "done"
    ) -> None:
        """Write a done marker blob."""
        blob_path = f"{self._object_prefix(commit_hash)}/done.marker"
        blob_service = self._get_blob_service()
        container = blob_service.get_container_client(
            self.settings.azure_storage_container
        )
        blob_client = container.get_blob_client(blob_path)
        blob_client.upload_blob(verdict_json.encode(), overwrite=True)
        logger.info("Wrote completion marker: %s", blob_path)
