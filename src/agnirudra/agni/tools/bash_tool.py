"""Bash tool: execute shell commands and return output."""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger(__name__)

TIMEOUT = 120  # seconds


def run(command: str, timeout: int = TIMEOUT) -> tuple[int, str]:
    """Run a shell command and return (return_code, combined_output).

    Stdout and stderr are merged. The command runs in a bash shell.
    """
    logger.debug("Running: %s", command)
    try:
        result = subprocess.run(
            ["bash", "-c", command],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={"DISPLAY": ":1", "HOME": "/root", "PATH": "/usr/local/bin:/usr/bin:/bin"},
        )
        output = result.stdout + result.stderr
        # Truncate very long output to avoid context blowout
        if len(output) > 30000:
            output = output[:15000] + "\n... [truncated] ...\n" + output[-15000:]
        return result.returncode, output
    except subprocess.TimeoutExpired:
        return 1, f"Command timed out after {timeout}s"
    except Exception as exc:
        return 1, f"Error running command: {exc}"
