"""Hetzner cloud provider: VMs and S3-compatible Object Storage."""

from __future__ import annotations

import json
import logging
import secrets
import time
from pathlib import Path
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config as BotoConfig
from hcloud import Client as HetznerClient
from hcloud.images import Image
from hcloud.locations import Location
from hcloud.server_types import ServerType
from hcloud.servers import Server

from agnirudra.agni.cloud.base import CloudProvider

if TYPE_CHECKING:
    from agnirudra.agni.trigger import TestPlan
    from agnirudra.config import AgniSettings

logger = logging.getLogger(__name__)

CLOUD_INIT_TEMPLATE = """\
#!/bin/bash
set -euo pipefail

# Install Docker
curl -fsSL https://get.docker.com | sh

# Write env vars to file (avoids shell quoting issues)
cat > /tmp/agni.env <<'ENVEOF'
{env_file_contents}
ENVEOF

# Pull and run the Agni container
docker pull {docker_image}
docker run --rm --env-file /tmp/agni.env {docker_image}
"""


class HetznerProvider(CloudProvider):
    """Hetzner cloud provider using Cloud VMs and S3-compatible Object Storage."""

    def __init__(self, settings: AgniSettings) -> None:
        super().__init__(settings)
        self._hcloud = HetznerClient(token=settings.hetzner_api_token)
        self._s3 = boto3.client(
            "s3",
            endpoint_url=settings.hetzner_s3_endpoint,
            aws_access_key_id=settings.hetzner_s3_access_key,
            aws_secret_access_key=settings.hetzner_s3_secret_key,
            config=BotoConfig(signature_version="s3v4"),
            region_name=settings.hetzner_s3_region,
        )

    def _server_name(self, short_hash: str) -> str:
        return f"agni-{self.settings.pr_number}-{short_hash[:8]}-r{self.settings.run_attempt}"

    # ─────────────────────────────────────────────────────────────
    # VM lifecycle
    # ─────────────────────────────────────────────────────────────

    def create_vm(self, test_plan: TestPlan, commit_hash: str) -> str:
        """Create a Hetzner Cloud server that runs the Agni Docker container."""
        server_name = self._server_name(commit_hash)

        # Build cloud-init user_data
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
            "AGNI_CLOUD_PROVIDER": "hetzner",
            "AGNI_HETZNER_S3_ENDPOINT": self.settings.hetzner_s3_endpoint,
            "AGNI_HETZNER_S3_ACCESS_KEY": self.settings.hetzner_s3_access_key,
            "AGNI_HETZNER_S3_SECRET_KEY": self.settings.hetzner_s3_secret_key,
            "AGNI_HETZNER_S3_BUCKET": self.settings.hetzner_s3_bucket,
            "AGNI_HETZNER_S3_REGION": self.settings.hetzner_s3_region,
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

        # Create the server
        # Use ubuntu-22.04 image and a reasonable server type (cpx31 = 4 vCPU, 8GB RAM)
        response = self._hcloud.servers.create(
            name=server_name,
            server_type=ServerType(name=self.settings.hetzner_server_type),
            image=Image(name=self.settings.hetzner_image),
            location=Location(name=self.settings.hetzner_location),
            user_data=cloud_init,
            labels={
                "project": "agnirudra",
                "pr": str(self.settings.pr_number),
                "commit": commit_hash[:8],
            },
        )

        # Wait for server to be created
        response.action.wait_until_finished()
        logger.info(
            "Server %s created (ID: %d, IP: %s)",
            server_name,
            response.server.id,
            response.server.public_net.ipv4.ip if response.server.public_net.ipv4 else "N/A",
        )
        return server_name

    def poll_for_completion(
        self, commit_hash: str, timeout: int | None = None
    ) -> dict | None:
        """Poll Hetzner Object Storage for the done marker."""
        marker_key = f"{self._object_prefix(commit_hash)}/done.marker"

        timeout = timeout or self.settings.vm_timeout_seconds
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                response = self._s3.get_object(
                    Bucket=self.settings.hetzner_s3_bucket,
                    Key=marker_key,
                )
                data = response["Body"].read().decode()
                logger.info("Completion marker found: %s", marker_key)
                try:
                    return json.loads(data)
                except (json.JSONDecodeError, ValueError):
                    return {"passed": True, "summary": data}
            except self._s3.exceptions.NoSuchKey:
                time.sleep(15)
            except Exception:
                time.sleep(15)

        logger.warning("Timed out waiting for completion marker")
        return None

    def teardown_vm(self, commit_hash: str) -> None:
        """Delete the Hetzner server."""
        server_name = self._server_name(commit_hash)

        # Find the server by name
        servers = self._hcloud.servers.get_all(name=server_name)
        if not servers:
            logger.warning("Server %s not found for teardown", server_name)
            return

        for server in servers:
            logger.info("Deleting server %s (ID: %d)", server.name, server.id)
            try:
                server.delete()
            except Exception as exc:
                logger.warning("Failed to delete server %s: %s", server.name, exc)

        logger.info("Teardown complete for %s", server_name)

    # ─────────────────────────────────────────────────────────────
    # Object storage
    # ─────────────────────────────────────────────────────────────

    def upload_recording(self, local_path: Path, commit_hash: str) -> str:
        """Upload a recording file and return the object key."""
        object_key = f"{self._object_prefix(commit_hash)}/recording.mp4"
        self._s3.upload_file(
            str(local_path),
            self.settings.hetzner_s3_bucket,
            object_key,
            ExtraArgs={"ContentType": "video/mp4"},
        )
        logger.info("Uploaded recording to %s", object_key)
        return object_key

    def upload_thumbnail(self, local_path: Path, commit_hash: str) -> str:
        """Upload a thumbnail image and return the object key."""
        object_key = f"{self._object_prefix(commit_hash)}/thumbnail.jpg"
        self._s3.upload_file(
            str(local_path),
            self.settings.hetzner_s3_bucket,
            object_key,
            ExtraArgs={"ContentType": "image/jpeg"},
        )
        logger.info("Uploaded thumbnail to %s", object_key)
        return object_key

    def upload_player_page(self, recording_url: str, commit_hash: str) -> str:
        """Upload an HTML video player page and return the object key."""
        object_key = f"{self._object_prefix(commit_hash)}/player.html"
        html = self._build_player_html(recording_url)
        self._s3.put_object(
            Bucket=self.settings.hetzner_s3_bucket,
            Key=object_key,
            Body=html.encode(),
            ContentType="text/html",
        )
        logger.info("Uploaded player page to %s", object_key)
        return object_key

    def upload_trace(self, local_path: Path, commit_hash: str) -> str:
        """Upload the agent trace log and return the object key."""
        object_key = f"{self._object_prefix(commit_hash)}/trace.log"
        self._s3.upload_file(
            str(local_path),
            self.settings.hetzner_s3_bucket,
            object_key,
            ExtraArgs={"ContentType": "text/plain"},
        )
        logger.info("Uploaded trace to %s", object_key)
        return object_key

    def generate_public_url(self, object_path: str, expiry_days: int = 7) -> str:
        """Generate a presigned URL for an object."""
        # Hetzner Object Storage supports presigned URLs via S3 API
        url = self._s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.settings.hetzner_s3_bucket,
                "Key": object_path,
            },
            ExpiresIn=expiry_days * 24 * 60 * 60,  # Convert days to seconds
        )
        logger.info("Generated presigned URL (expires in %d days)", expiry_days)
        return url

    def delete_done_marker(self, commit_hash: str) -> None:
        """Delete any existing done marker."""
        object_key = f"{self._object_prefix(commit_hash)}/done.marker"
        try:
            self._s3.delete_object(
                Bucket=self.settings.hetzner_s3_bucket,
                Key=object_key,
            )
            logger.info("Deleted stale done marker: %s", object_key)
        except Exception:
            pass  # Marker didn't exist

    def write_done_marker(
        self, commit_hash: str, verdict_json: str = "done"
    ) -> None:
        """Write a done marker object."""
        object_key = f"{self._object_prefix(commit_hash)}/done.marker"
        self._s3.put_object(
            Bucket=self.settings.hetzner_s3_bucket,
            Key=object_key,
            Body=verdict_json.encode(),
        )
        logger.info("Wrote completion marker: %s", object_key)
