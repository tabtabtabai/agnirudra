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
        default="moonshotai/kimi-k2.5",
        description="Model ID — provider auto-detected from prefix (claude-*, moonshotai/*, gemini-*)",
    )

    # Azure - identity
    azure_subscription_id: str = Field(description="Azure subscription ID")
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

    # GitHub
    github_token: str = Field(description="GitHub token for API access")
    github_repository: str = Field(
        description="GitHub repository in owner/repo format"
    )
    pr_number: int = Field(description="Pull request number to test")

    # Docker image
    docker_image: str = Field(
        default="ghcr.io/tabtabtabai/agnirudra:latest",
        description="Docker image for the test VM",
    )

    # Pre-baked VM image (optional, speeds up boot by ~1.5-2 min)
    azure_vm_image: str = Field(
        default="",
        description="Azure managed image resource ID (from build-vm-image.sh)",
    )

    # Agent
    max_agent_iterations: int = Field(
        default=30, description="Max computer-use loop iterations"
    )
    vm_timeout_seconds: int = Field(
        default=900, description="Max seconds to wait for VM completion"
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
