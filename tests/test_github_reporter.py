"""Tests for the GitHub reporter module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_settings():
    mock = MagicMock()
    mock.github_token = "ghp-test"
    mock.github_repository = "tabtabtabai/test-repo"
    mock.pr_number = 42
    return mock


@patch("agnirudra.agni.github_reporter.Github")
def test_post_result_pass(mock_github_cls):
    """Test posting a PASS result."""
    from agnirudra.agni.github_reporter import post_result

    mock_gh = MagicMock()
    mock_github_cls.return_value = mock_gh
    mock_pr = MagicMock()
    mock_gh.get_repo.return_value.get_pull.return_value = mock_pr

    settings = _make_settings()
    post_result(
        settings,
        passed=True,
        summary="Login button works correctly",
        recording_url="https://example.com/recording.mp4",
        commit_hash="abc12345",
        commit_message="Add login button",
    )

    mock_pr.create_issue_comment.assert_called_once()
    body = mock_pr.create_issue_comment.call_args[0][0]
    assert "PASS" in body
    assert "abc12345" in body
    assert "Login button works correctly" in body
    assert "recording.mp4" in body


@patch("agnirudra.agni.github_reporter.Github")
def test_post_result_fail(mock_github_cls):
    """Test posting a FAIL result."""
    from agnirudra.agni.github_reporter import post_result

    mock_gh = MagicMock()
    mock_github_cls.return_value = mock_gh
    mock_pr = MagicMock()
    mock_gh.get_repo.return_value.get_pull.return_value = mock_pr

    settings = _make_settings()
    post_result(
        settings,
        passed=False,
        summary="Button not found on page",
        recording_url="https://example.com/recording.mp4",
        commit_hash="def67890",
        commit_message="Add button",
    )

    body = mock_pr.create_issue_comment.call_args[0][0]
    assert "FAIL" in body
    assert "def67890" in body


@patch("agnirudra.agni.github_reporter.Github")
def test_post_result_with_thumbnail(mock_github_cls):
    """Test that thumbnail URL is embedded as a clickable image."""
    from agnirudra.agni.github_reporter import post_result

    mock_gh = MagicMock()
    mock_github_cls.return_value = mock_gh
    mock_pr = MagicMock()
    mock_gh.get_repo.return_value.get_pull.return_value = mock_pr

    settings = _make_settings()
    post_result(
        settings,
        passed=True,
        summary="All good",
        recording_url="https://example.com/recording.mp4",
        commit_hash="abc12345",
        commit_message="Test PR",
        thumbnail_url="https://example.com/thumbnail.jpg",
    )

    body = mock_pr.create_issue_comment.call_args[0][0]
    assert "[![Watch test session](https://example.com/thumbnail.jpg)](https://example.com/recording.mp4)" in body


@patch("agnirudra.agni.github_reporter.Github")
def test_post_skip(mock_github_cls):
    """Test posting a SKIPPED comment."""
    from agnirudra.agni.github_reporter import post_skip

    mock_gh = MagicMock()
    mock_github_cls.return_value = mock_gh
    mock_pr = MagicMock()
    mock_gh.get_repo.return_value.get_pull.return_value = mock_pr

    settings = _make_settings()
    post_skip(settings, "No UI changes detected")

    body = mock_pr.create_issue_comment.call_args[0][0]
    assert "SKIPPED" in body
    assert "No UI changes detected" in body


@patch("agnirudra.agni.github_reporter.Github")
def test_post_error(mock_github_cls):
    """Test posting an ERROR comment."""
    from agnirudra.agni.github_reporter import post_error

    mock_gh = MagicMock()
    mock_github_cls.return_value = mock_gh
    mock_pr = MagicMock()
    mock_gh.get_repo.return_value.get_pull.return_value = mock_pr

    settings = _make_settings()
    post_error(settings, "App failed to start", recording_url="https://example.com/r.mp4")

    body = mock_pr.create_issue_comment.call_args[0][0]
    assert "ERROR" in body
    assert "App failed to start" in body
    assert "r.mp4" in body
