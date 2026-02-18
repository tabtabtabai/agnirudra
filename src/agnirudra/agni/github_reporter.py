"""Post test results as PR comments on GitHub."""

from __future__ import annotations

import logging

from github import Github

from agnirudra.config import AgniSettings

logger = logging.getLogger(__name__)

REPORT_TEMPLATE = """\
## Agni Visual Test Report

**Status**: {status}

**Commit**: `{commit_hash}` -- {commit_message}

**Summary**: {summary}

**Recording**: [![Watch test session]({thumbnail_url})]({recording_url})
{trace_line}
---
*Tested by [Agni](https://github.com/anthropics/agnirudra)*\
"""

SKIP_TEMPLATE = """\
## Agni Visual Test Report

**Status**: SKIPPED -- {reason}

---
*Tested by [Agni](https://github.com/anthropics/agnirudra)*\
"""

ERROR_TEMPLATE = """\
## Agni Visual Test Report

**Status**: ERROR -- {reason}

{recording_line}

---
*Tested by [Agni](https://github.com/anthropics/agnirudra)*\
"""


def post_result(
    settings: AgniSettings,
    passed: bool,
    summary: str,
    recording_url: str,
    commit_hash: str,
    commit_message: str,
    thumbnail_url: str = "",
    trace_url: str = "",
) -> None:
    """Post a pass/fail result as a PR comment."""
    status = "PASS" if passed else "FAIL"
    trace_line = f"\n**Agent Trace**: [View reasoning log]({trace_url})\n" if trace_url else ""
    body = REPORT_TEMPLATE.format(
        status=status,
        commit_hash=commit_hash[:8],
        commit_message=commit_message,
        summary=summary,
        recording_url=recording_url,
        thumbnail_url=thumbnail_url or recording_url,
        trace_line=trace_line,
    )
    _post_comment(settings, body)


def post_skip(settings: AgniSettings, reason: str) -> None:
    """Post a skip comment when there are no UI changes to test."""
    body = SKIP_TEMPLATE.format(reason=reason)
    _post_comment(settings, body)


def post_error(
    settings: AgniSettings, reason: str, recording_url: str = ""
) -> None:
    """Post an error comment when something went wrong."""
    recording_line = (
        f"**Recording**: [Watch attempt]({recording_url})"
        if recording_url
        else ""
    )
    body = ERROR_TEMPLATE.format(reason=reason, recording_line=recording_line)
    _post_comment(settings, body)


def _post_comment(settings: AgniSettings, body: str) -> None:
    gh = Github(settings.github_token)
    repo = gh.get_repo(settings.github_repository)
    pr = repo.get_pull(settings.pr_number)
    pr.create_issue_comment(body)
    logger.info("Posted PR comment on #%d", settings.pr_number)
