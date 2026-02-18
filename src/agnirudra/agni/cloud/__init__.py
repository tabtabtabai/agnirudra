"""Cloud provider factory — supports Azure and Hetzner."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agnirudra.agni.cloud.base import CloudProvider

if TYPE_CHECKING:
    from agnirudra.config import AgniSettings


def create_cloud_provider(settings: AgniSettings) -> CloudProvider:
    """Create a cloud provider instance based on settings.

    The provider is determined by the `cloud_provider` setting:
      - "azure" (default): Azure VMs + Blob Storage
      - "hetzner": Hetzner Cloud VMs + S3-compatible Object Storage
    """
    provider_name = settings.cloud_provider.lower()

    if provider_name == "azure":
        from agnirudra.agni.cloud.azure import AzureProvider
        return AzureProvider(settings)

    if provider_name == "hetzner":
        from agnirudra.agni.cloud.hetzner import HetznerProvider
        return HetznerProvider(settings)

    raise ValueError(
        f"Unknown cloud provider: {provider_name!r}. "
        f"Supported providers: azure, hetzner"
    )


__all__ = ["CloudProvider", "create_cloud_provider"]
