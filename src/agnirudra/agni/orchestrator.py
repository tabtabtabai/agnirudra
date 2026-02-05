"""Orchestrator: the main flow that runs on the GitHub Actions runner.

1. Fetch PR diff + commit messages
2. Generate a TestPlan via Claude
3. If no UI changes, post skip comment and exit
4. Create VM (Azure or Hetzner) that runs the Docker container with the agent
5. Poll for completion
6. Teardown VM
"""

from __future__ import annotations

import logging
import signal
import sys
from typing import TYPE_CHECKING

from github import Github

from agnirudra.agni import github_reporter, trigger
from agnirudra.agni.cloud import create_cloud_provider
from agnirudra.config import AgniSettings

if TYPE_CHECKING:
    from agnirudra.agni.cloud.base import CloudProvider

logger = logging.getLogger(__name__)

# Module-level variable to hold the cloud provider for signal handlers
_cloud_provider: CloudProvider | None = None
_commit_hash: str | None = None


def _teardown_on_signal(signum: int, _frame: object) -> None:
    """Signal handler that tears down VM on job cancellation."""
    sig_name = signal.Signals(signum).name
    logger.warning("Received %s — tearing down VM before exit", sig_name)
    if _cloud_provider and _commit_hash:
        try:
            _cloud_provider.teardown_vm(_commit_hash)
        except Exception as exc:
            logger.warning("Teardown on signal failed: %s", exc)
    sys.exit(1)


def _get_head_commit(settings: AgniSettings) -> tuple[str, str]:
    """Return (sha, message) of the PR's head commit."""
    gh = Github(settings.github_token)
    repo = gh.get_repo(settings.github_repository)
    pr = repo.get_pull(settings.pr_number)
    commits = list(pr.get_commits())
    head = commits[-1]
    return head.sha, head.commit.message


def run() -> None:
    """Main orchestrator entry point."""
    global _cloud_provider, _commit_hash

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    logger.info("Starting Agni orchestrator")

    try:
        settings = AgniSettings()  # type: ignore[call-arg]
    except Exception as exc:
        logger.error("Failed to load settings: %s", exc)
        sys.exit(1)

    commit_hash, commit_message = _get_head_commit(settings)
    _commit_hash = commit_hash
    logger.info("PR #%d, head commit: %s", settings.pr_number, commit_hash[:8])

    # Step 1: Generate test plan
    logger.info("Generating test plan...")
    try:
        test_plan = trigger.generate_test_plan(settings)
    except Exception as exc:
        logger.error("Failed to generate test plan: %s", exc)
        github_reporter.post_error(settings, f"Failed to generate test plan: {exc}")
        sys.exit(1)

    # Step 2: Skip if no UI changes (unless force_run is set, e.g. label trigger)
    if test_plan.skip and not settings.force_run:
        logger.info("Skipping: %s", test_plan.skip_reason)
        github_reporter.post_skip(settings, test_plan.skip_reason)
        return
    elif test_plan.skip and settings.force_run:
        logger.info("Would skip (%s) but force_run is set — continuing", test_plan.skip_reason)

    logger.info("Test plan: %s", test_plan.description)
    logger.info("Steps: %s", test_plan.steps)

    # Step 3: Create cloud provider and clean up stale markers
    logger.info("Using cloud provider: %s", settings.cloud_provider)
    cloud = create_cloud_provider(settings)
    _cloud_provider = cloud
    cloud.delete_done_marker(commit_hash)

    # Step 4: Create VM
    logger.info("Creating VM...")
    try:
        vm_name = cloud.create_vm(test_plan, commit_hash)
    except Exception as exc:
        logger.error("Failed to create VM: %s", exc)
        github_reporter.post_error(settings, f"Failed to create test VM: {exc}")
        sys.exit(1)

    logger.info("VM created: %s", vm_name)

    # Register signal handlers so teardown runs on job cancellation
    signal.signal(signal.SIGTERM, _teardown_on_signal)
    signal.signal(signal.SIGINT, _teardown_on_signal)

    # Step 5: Poll for completion
    logger.info("Waiting for test completion (timeout=%ds)...", settings.vm_timeout_seconds)
    verdict = cloud.poll_for_completion(commit_hash)

    # Step 6: Teardown
    logger.info("Tearing down VM...")
    try:
        cloud.teardown_vm(commit_hash)
    except Exception as exc:
        logger.warning("VM teardown error (non-fatal): %s", exc)

    if verdict is None:
        github_reporter.post_error(
            settings,
            "Test timed out. The VM was running for too long.",
        )
        sys.exit(1)

    passed = verdict.get("passed", False)
    summary = verdict.get("summary", "")
    logger.info("Orchestrator complete. Passed: %s — %s", passed, summary)

    if not passed:
        sys.exit(1)


if __name__ == "__main__":
    run()
