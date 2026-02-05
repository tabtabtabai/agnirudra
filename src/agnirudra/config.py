"""Pydantic settings loaded from environment variables."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class AgniSettings(BaseSettings):
    """All configuration for an Agni test run."""

    model_config = {"env_prefix": "AGNI_"}

    # API keys — Anthropic is always required (used for planning).
    # The vision model key is only needed if model != claude-*.
    anthropic_api_key: str = Field(
        description="Anthropic API key (always required for test plan generation)"
    )
    nvidia_api_key: str = Field(
        default="", description="NVIDIA Build API key (for Kimi K2.5)"
    )
    google_api_key: str = Field(
        default="", description="Google AI API key (for Gemini models)"
    )
    model: str = Field(
        default="claude-opus-4-5-20251101",
        description="Model ID — provider auto-detected from prefix (claude-*, moonshotai/*, gemini-*)",
    )

    # Cloud provider selection
    cloud_provider: str = Field(
        default="azure",
        description="Cloud provider for VMs and storage: 'azure' or 'hetzner'",
    )

    # Azure - identity (required when cloud_provider=azure)
    azure_subscription_id: str = Field(
        default="", description="Azure subscription ID"
    )
    azure_tenant_id: str = Field(default="", description="Azure tenant ID")
    azure_client_id: str = Field(default="", description="Azure SP client ID")
    azure_client_secret: str = Field(default="", description="Azure SP client secret")

    # Azure - resources
    azure_resource_group: str = Field(
        default="agnirudra-rg", description="Azure resource group"
    )
    azure_location: str = Field(default="eastus", description="Azure region")
    azure_vm_size: str = Field(
        default="Standard_D4s_v3", description="Azure VM size"
    )
    azure_storage_account: str = Field(
        default="agnirudrarecordings", description="Azure storage account name"
    )
    azure_storage_container: str = Field(
        default="recordings", description="Azure blob container name"
    )

    # Hetzner - API (required when cloud_provider=hetzner)
    hetzner_api_token: str = Field(
        default="", description="Hetzner Cloud API token"
    )
    hetzner_location: str = Field(
        default="fsn1", description="Hetzner datacenter location (fsn1, nbg1, hel1, ash, hil)"
    )
    hetzner_server_type: str = Field(
        default="cpx31", description="Hetzner server type (cpx31 = 4 vCPU, 8GB RAM)"
    )
    hetzner_image: str = Field(
        default="ubuntu-22.04", description="Hetzner OS image"
    )

    # Hetzner - S3-compatible Object Storage
    hetzner_s3_endpoint: str = Field(
        default="https://fsn1.your-objectstorage.com",
        description="Hetzner Object Storage endpoint URL",
    )
    hetzner_s3_region: str = Field(
        default="fsn1", description="Hetzner Object Storage region"
    )
    hetzner_s3_access_key: str = Field(
        default="", description="Hetzner Object Storage access key"
    )
    hetzner_s3_secret_key: str = Field(
        default="", description="Hetzner Object Storage secret key"
    )
    hetzner_s3_bucket: str = Field(
        default="agnirudra-recordings", description="Hetzner Object Storage bucket name"
    )

    # GitHub
    github_token: str = Field(description="GitHub token for API access")
    github_repository: str = Field(
        description="GitHub repository in owner/repo format"
    )
    pr_number: int = Field(description="Pull request number to test")

    # Docker image (set to your organization's image registry)
    docker_image: str = Field(
        default="",
        description="Docker image for the test VM (e.g., ghcr.io/your-org/agnirudra:latest)",
    )

    # Pre-baked VM image (optional, speeds up boot by ~1.5-2 min)
    azure_vm_image: str = Field(
        default="",
        description="Azure managed image resource ID (from build-vm-image.sh)",
    )

    # Agent
    max_agent_iterations: int = Field(
        default=50, description="Max computer-use loop iterations"
    )
    vm_timeout_seconds: int = Field(
        default=2400, description="Max seconds to wait for VM completion"
    )

    # Force run (skip the "no UI changes" check)
    force_run: bool = Field(
        default=False, description="Skip the skip-check and always run the test"
    )

    # Branch filter
    branch_filter: str = Field(
        default="claude/", description="Only test PRs from branches with this prefix"
    )

    # GitHub Actions run attempt (for unique VM names across retries)
    run_attempt: int = Field(
        default=1, description="GitHub Actions run attempt number"
    )

    # App secrets — JSON-encoded dict of env vars the consumer app needs
    app_secrets: str = Field(
        default="{}",
        description="JSON-encoded dict of env vars to inject into the test VM for the app",
    )

    # Display
    display_width: int = Field(default=1280, description="Virtual display width")
    display_height: int = Field(default=720, description="Virtual display height")
