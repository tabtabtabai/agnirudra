"""Tests for the trigger / test plan generation module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from agnirudra.agni.trigger import TestPlan, generate_test_plan


def _make_settings(**overrides):
    defaults = {
        "anthropic_api_key": "sk-test",
        "github_token": "ghp-test",
        "github_repository": "tabtabtabai/test-repo",
        "pr_number": 42,
        "model": "claude-sonnet-4-5-20250929",
        "azure_subscription_id": "sub-123",
    }
    defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


@patch("agnirudra.agni.trigger.anthropic.Anthropic")
@patch("agnirudra.agni.trigger.fetch_pr_context")
def test_generate_test_plan_ui_changes(mock_fetch, mock_anthropic_cls):
    """Test that a UI-visible change produces a non-skip test plan."""
    mock_fetch.return_value = ("--- src/App.tsx\n+<button>Login</button>", "Add login button")

    plan_data = {
        "description": "Adds a login button to the homepage",
        "start_url": "http://localhost:3000",
        "steps": ["Navigate to homepage", "Look for the login button", "Click it"],
        "pass_criteria": "Login button is visible and clickable",
        "fail_criteria": "Login button is missing or broken",
        "skip": False,
        "skip_reason": "",
    }

    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(plan_data))]
    mock_client.messages.create.return_value = mock_response

    settings = _make_settings()
    result = generate_test_plan(settings)

    assert isinstance(result, TestPlan)
    assert result.skip is False
    assert result.start_url == "http://localhost:3000"
    assert len(result.steps) == 3


@patch("agnirudra.agni.trigger.anthropic.Anthropic")
@patch("agnirudra.agni.trigger.fetch_pr_context")
def test_generate_test_plan_skip(mock_fetch, mock_anthropic_cls):
    """Test that a non-UI change produces a skip test plan."""
    mock_fetch.return_value = ("--- .github/ci.yml\n+timeout: 30", "Update CI timeout")

    plan_data = {
        "description": "Updates CI configuration",
        "start_url": "",
        "steps": [],
        "pass_criteria": "",
        "fail_criteria": "",
        "skip": True,
        "skip_reason": "CI config change, no UI impact",
    }

    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(plan_data))]
    mock_client.messages.create.return_value = mock_response

    settings = _make_settings()
    result = generate_test_plan(settings)

    assert result.skip is True
    assert "CI" in result.skip_reason


@patch("agnirudra.agni.trigger.anthropic.Anthropic")
@patch("agnirudra.agni.trigger.fetch_pr_context")
def test_generate_test_plan_markdown_fences(mock_fetch, mock_anthropic_cls):
    """Test that JSON wrapped in markdown code fences is parsed correctly."""
    mock_fetch.return_value = ("--- index.html\n+<h1>Hello</h1>", "Add heading")

    plan_data = {
        "description": "Adds heading",
        "start_url": "http://localhost:3000",
        "steps": ["Check heading"],
        "pass_criteria": "Heading visible",
        "fail_criteria": "No heading",
        "skip": False,
        "skip_reason": "",
    }
    fenced = f"```json\n{json.dumps(plan_data)}\n```"

    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=fenced)]
    mock_client.messages.create.return_value = mock_response

    settings = _make_settings()
    result = generate_test_plan(settings)

    assert result.skip is False
    assert result.description == "Adds heading"
