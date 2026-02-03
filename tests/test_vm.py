"""Tests for the Azure VM lifecycle module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agnirudra.agni.trigger import TestPlan


def _make_settings(**overrides):
    defaults = {
        "anthropic_api_key": "sk-test",
        "github_token": "ghp-test",
        "github_repository": "tabtabtabai/test-repo",
        "pr_number": 42,
        "model": "claude-opus-4-5-20251101",
        "azure_subscription_id": "sub-123",
        "azure_tenant_id": "tenant-123",
        "azure_client_id": "client-123",
        "azure_client_secret": "secret-123",
        "azure_resource_group": "agnirudra-rg",
        "azure_location": "eastus",
        "azure_vm_size": "Standard_D4s_v3",
        "azure_storage_account": "agnirudrarecordings",
        "azure_storage_container": "recordings",
        "docker_image": "ghcr.io/tabtabtabai/agnirudra:latest",
        "vm_timeout_seconds": 600,
        "run_attempt": 1,
        "app_secrets": "{}",
    }
    defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _make_test_plan():
    return TestPlan(
        description="Test login button",
        start_url="http://localhost:3000",
        steps=["Navigate to /", "Click login"],
        pass_criteria="Redirect to dashboard",
        fail_criteria="Error or no redirect",
    )


@patch("agnirudra.agni.vm._get_credential")
@patch("agnirudra.agni.vm.ComputeManagementClient")
@patch("agnirudra.agni.vm.NetworkManagementClient")
def test_create_vm(mock_net_cls, mock_compute_cls, mock_cred):
    """Test that create_vm calls Azure APIs to create NIC and VM."""
    from agnirudra.agni.vm import create_vm

    mock_cred.return_value = MagicMock()

    # Mock network client
    mock_net = MagicMock()
    mock_net_cls.return_value = mock_net
    mock_net.public_ip_addresses.begin_create_or_update.return_value.result.return_value = MagicMock(id="/ip/1")
    mock_net.virtual_networks.begin_create_or_update.return_value.result.return_value = None
    mock_net.subnets.get.return_value = MagicMock(id="/subnet/1")
    mock_net.network_interfaces.begin_create_or_update.return_value.result.return_value = MagicMock(id="/nic/1")

    # Mock compute client
    mock_compute = MagicMock()
    mock_compute_cls.return_value = mock_compute
    mock_compute.virtual_machines.begin_create_or_update.return_value.result.return_value = None

    settings = _make_settings()
    test_plan = _make_test_plan()
    vm_name = create_vm(settings, test_plan, "abc12345def")

    assert vm_name == "agni-42-abc12345-r1"
    mock_compute.virtual_machines.begin_create_or_update.assert_called_once()


@patch("agnirudra.agni.vm._get_credential")
@patch("agnirudra.agni.vm.ComputeManagementClient")
@patch("agnirudra.agni.vm.NetworkManagementClient")
def test_teardown_vm(mock_net_cls, mock_compute_cls, mock_cred):
    """Test that teardown_vm deletes VM, NIC, and public IP."""
    from agnirudra.agni.vm import teardown_vm

    mock_cred.return_value = MagicMock()
    mock_compute = MagicMock()
    mock_compute_cls.return_value = mock_compute
    mock_net = MagicMock()
    mock_net_cls.return_value = mock_net

    settings = _make_settings()
    teardown_vm(settings, "abc12345def")

    mock_compute.virtual_machines.begin_delete.assert_called_once()
    mock_net.network_interfaces.begin_delete.assert_called_once()
    mock_net.public_ip_addresses.begin_delete.assert_called_once()
