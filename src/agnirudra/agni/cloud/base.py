"""Abstract base class for cloud providers (VMs and object storage)."""

from __future__ import annotations

import abc
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agnirudra.agni.trigger import TestPlan
    from agnirudra.config import AgniSettings


class CloudProvider(abc.ABC):
    """Abstract interface for cloud infrastructure providers.

    A provider must implement:
      - VM lifecycle: create, poll, teardown
      - Object storage: upload files, generate URLs, markers
    """

    def __init__(self, settings: AgniSettings) -> None:
        self.settings = settings

    # ─────────────────────────────────────────────────────────────
    # VM lifecycle
    # ─────────────────────────────────────────────────────────────

    @abc.abstractmethod
    def create_vm(self, test_plan: TestPlan, commit_hash: str) -> str:
        """Create a VM that runs the Agni Docker container.

        Returns the VM name/ID.
        """
        ...

    @abc.abstractmethod
    def poll_for_completion(
        self, commit_hash: str, timeout: int | None = None
    ) -> dict | None:
        """Poll object storage for the done marker.

        Returns the verdict dict if found, or None on timeout.
        """
        ...

    @abc.abstractmethod
    def teardown_vm(self, commit_hash: str) -> None:
        """Delete the VM and associated resources."""
        ...

    # ─────────────────────────────────────────────────────────────
    # Object storage
    # ─────────────────────────────────────────────────────────────

    @abc.abstractmethod
    def upload_recording(self, local_path: Path, commit_hash: str) -> str:
        """Upload a recording file and return the blob/object path."""
        ...

    @abc.abstractmethod
    def upload_thumbnail(self, local_path: Path, commit_hash: str) -> str:
        """Upload a thumbnail image and return the blob/object path."""
        ...

    @abc.abstractmethod
    def upload_player_page(
        self, recording_url: str, commit_hash: str
    ) -> str:
        """Upload an HTML video player page and return the blob/object path."""
        ...

    @abc.abstractmethod
    def upload_trace(self, local_path: Path, commit_hash: str) -> str:
        """Upload the agent trace log and return the blob/object path."""
        ...

    @abc.abstractmethod
    def generate_public_url(
        self, object_path: str, expiry_days: int = 7
    ) -> str:
        """Generate a public/signed URL for an object."""
        ...

    @abc.abstractmethod
    def delete_done_marker(self, commit_hash: str) -> None:
        """Delete any existing done marker (cleanup before new run)."""
        ...

    @abc.abstractmethod
    def write_done_marker(
        self, commit_hash: str, verdict_json: str = "done"
    ) -> None:
        """Write a done marker so the orchestrator knows we finished."""
        ...

    # ─────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────

    def _object_prefix(self, commit_hash: str) -> str:
        """Return the object storage prefix for this PR/commit."""
        return f"pr-{self.settings.pr_number}/{commit_hash[:8]}"

    def _build_player_html(self, recording_url: str) -> str:
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
