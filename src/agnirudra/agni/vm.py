"""Azure VM lifecycle: create, poll for completion, teardown."""

from __future__ import annotations

import base64
import json
import logging
import time

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
from azure.storage.blob import BlobServiceClient

from agnirudra.agni.trigger import TestPlan
from agnirudra.config import AgniSettings

logger = logging.getLogger(__name__)

CLOUD_INIT_TEMPLATE = """\
#!/bin/bash
set -euo pipefail

# Install Docker
curl -fsSL https://get.docker.com | sh

# Build docker run command with env vars
ENV_ARGS=""
ENV_ARGS="$ENV_ARGS -e AGNI_ANTHROPIC_API_KEY='{anthropic_api_key}'"
ENV_ARGS="$ENV_ARGS -e AGNI_GITHUB_TOKEN='{github_token}'"
ENV_ARGS="$ENV_ARGS -e AGNI_GITHUB_REPOSITORY='{github_repository}'"
ENV_ARGS="$ENV_ARGS -e AGNI_PR_NUMBER='{pr_number}'"
ENV_ARGS="$ENV_ARGS -e AGNI_AZURE_STORAGE_ACCOUNT='{storage_account}'"
ENV_ARGS="$ENV_ARGS -e AGNI_AZURE_STORAGE_CONTAINER='{storage_container}'"
ENV_ARGS="$ENV_ARGS -e AGNI_AZURE_SUBSCRIPTION_ID='{subscription_id}'"
ENV_ARGS="$ENV_ARGS -e AGNI_AZURE_TENANT_ID='{tenant_id}'"
ENV_ARGS="$ENV_ARGS -e AGNI_AZURE_CLIENT_ID='{client_id}'"
ENV_ARGS="$ENV_ARGS -e AGNI_AZURE_CLIENT_SECRET='{client_secret}'"
ENV_ARGS="$ENV_ARGS -e AGNI_MODEL='{model}'"
ENV_ARGS="$ENV_ARGS -e TEST_PLAN='{test_plan_json}'"

# Inject consumer app secrets (DB URLs, API keys, etc.)
{app_secrets_env_lines}

# Pull and run the Agni container
docker pull {docker_image}
eval docker run --rm $ENV_ARGS {docker_image}
"""


def _get_credential(settings: AgniSettings) -> ClientSecretCredential:
    return ClientSecretCredential(
        tenant_id=settings.azure_tenant_id,
        client_id=settings.azure_client_id,
        client_secret=settings.azure_client_secret,
    )


def _vm_name(settings: AgniSettings, short_hash: str) -> str:
    return f"agni-{settings.pr_number}-{short_hash[:8]}"


def create_vm(
    settings: AgniSettings, test_plan: TestPlan, commit_hash: str
) -> str:
    """Create an Azure VM that runs the Agni Docker container.

    Returns the VM name.
    """
    credential = _get_credential(settings)
    compute_client = ComputeManagementClient(
        credential, settings.azure_subscription_id
    )
    network_client = NetworkManagementClient(
        credential, settings.azure_subscription_id
    )

    vm_name = _vm_name(settings, commit_hash)
    rg = settings.azure_resource_group
    location = settings.azure_location

    # --- Public IP ---
    ip_name = f"{vm_name}-ip"
    ip_poller = network_client.public_ip_addresses.begin_create_or_update(
        rg,
        ip_name,
        {
            "location": location,
            "sku": {"name": "Basic"},
            "public_ip_allocation_method": "Dynamic",
        },
    )
    ip_result = ip_poller.result()

    # --- NIC ---
    nic_name = f"{vm_name}-nic"
    # Assumes a VNet/subnet already exists or uses the default
    # For simplicity, create a minimal VNet + subnet inline
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

    # Build app secrets env lines for the consumer app's own secrets
    app_secrets_env_lines = ""
    try:
        app_secrets = json.loads(settings.app_secrets)
        for key, value in app_secrets.items():
            safe_val = str(value).replace("'", "'\\''")
            app_secrets_env_lines += (
                f"ENV_ARGS=\"$ENV_ARGS -e {key}='{safe_val}'\"\n"
            )
    except (json.JSONDecodeError, AttributeError):
        pass

    cloud_init = CLOUD_INIT_TEMPLATE.format(
        docker_image=settings.docker_image,
        anthropic_api_key=settings.anthropic_api_key,
        github_token=settings.github_token,
        github_repository=settings.github_repository,
        pr_number=settings.pr_number,
        storage_account=settings.azure_storage_account,
        storage_container=settings.azure_storage_container,
        subscription_id=settings.azure_subscription_id,
        tenant_id=settings.azure_tenant_id,
        client_id=settings.azure_client_id,
        client_secret=settings.azure_client_secret,
        model=settings.model,
        test_plan_json=test_plan_json.replace("'", "'\\''"),
        app_secrets_env_lines=app_secrets_env_lines,
    )
    custom_data = base64.b64encode(cloud_init.encode()).decode()

    # --- VM ---
    vm_poller = compute_client.virtual_machines.begin_create_or_update(
        rg,
        vm_name,
        VirtualMachine(
            location=location,
            hardware_profile=HardwareProfile(
                vm_size=VirtualMachineSizeTypes(settings.azure_vm_size)
            ),
            storage_profile=StorageProfile(
                image_reference=ImageReference(
                    publisher="Canonical",
                    offer="0001-com-ubuntu-server-jammy",
                    sku="22_04-lts",
                    version="latest",
                ),
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
                linux_configuration=LinuxConfiguration(
                    disable_password_authentication=True,
                    ssh=None,
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
                "pr": str(settings.pr_number),
                "commit": commit_hash[:8],
            },
        ),
    )
    vm_poller.result()
    logger.info("VM %s created in %s", vm_name, rg)
    return vm_name


def poll_for_completion(
    settings: AgniSettings, commit_hash: str, timeout: int | None = None
) -> bool:
    """Poll Azure Blob Storage for the done marker. Returns True if found."""
    credential = _get_credential(settings)
    blob_service = BlobServiceClient(
        account_url=f"https://{settings.azure_storage_account}.blob.core.windows.net",
        credential=credential,
    )
    container_client = blob_service.get_container_client(
        settings.azure_storage_container
    )
    marker_blob = f"pr-{settings.pr_number}/{commit_hash[:8]}/done.marker"

    timeout = timeout or settings.vm_timeout_seconds
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            container_client.get_blob_client(marker_blob).get_blob_properties()
            logger.info("Completion marker found: %s", marker_blob)
            return True
        except Exception:
            time.sleep(15)

    logger.warning("Timed out waiting for completion marker")
    return False


def teardown_vm(settings: AgniSettings, commit_hash: str) -> None:
    """Delete the VM and associated resources."""
    credential = _get_credential(settings)
    compute_client = ComputeManagementClient(
        credential, settings.azure_subscription_id
    )
    network_client = NetworkManagementClient(
        credential, settings.azure_subscription_id
    )

    vm_name = _vm_name(settings, commit_hash)
    rg = settings.azure_resource_group

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
