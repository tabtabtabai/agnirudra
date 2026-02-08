"""Analyze a PR diff and generate a TestPlan."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import anthropic
from github import Github

from agnirudra.config import AgniSettings

# Planning always uses Claude — it's a text-only task.
PLANNING_MODEL = "claude-sonnet-4-5-20250929"

SYSTEM_PROMPT = """\
You are a QA analyst. Given a pull request diff and commit messages, determine:
1. What changed
2. Whether the changes are UI-visible (would a user see something different in a browser?)
3. If UI-visible, produce a step-by-step test plan for a browser-based QA agent.

Respond with JSON only. Schema:
{
  "description": "string - what the PR does",
  "start_url": "string - e.g. http://localhost:3000/login",
  "steps": ["string - step 1", "string - step 2", ...],
  "pass_criteria": "string - what success looks like",
  "fail_criteria": "string - what failure looks like",
  "skip": false,
  "skip_reason": ""
}

If the changes are NOT UI-visible (e.g. backend-only, CI config, docs), set skip=true
and skip_reason to a short explanation. Leave steps empty and start_url empty.
"""


@dataclass
class TestPlan:
    """What to test and how."""

    description: str
    start_url: str = ""
    steps: list[str] = field(default_factory=list)
    pass_criteria: str = ""
    fail_criteria: str = ""
    skip: bool = False
    skip_reason: str = ""


def fetch_pr_context(settings: AgniSettings) -> tuple[str, str]:
    """Return (diff_text, commit_messages) for the PR."""
    gh = Github(settings.github_token)
    repo = gh.get_repo(settings.github_repository)
    pr = repo.get_pull(settings.pr_number)

    diff: str = pr.get_diff() if hasattr(pr, "get_diff") else ""
    # PyGithub doesn't expose raw diff easily; use the files list instead
    if not diff:
        parts: list[str] = []
        for f in pr.get_files():
            parts.append(f"--- {f.filename}\n{f.patch or ''}")
        diff = "\n".join(parts)

    commits_text = "\n".join(c.commit.message for c in pr.get_commits())
    return diff, commits_text


def generate_test_plan(settings: AgniSettings) -> TestPlan:
    """Fetch PR context and ask Claude to produce a TestPlan.

    Always uses Claude for planning (text-only task), regardless of which
    model is configured for the computer-use agent loop.
    """
    diff, commits = fetch_pr_context(settings)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    user_msg = f"## Commit messages\n{commits}\n\n## Diff\n{diff}"

    response = client.messages.create(
        model=PLANNING_MODEL,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    text = response.content[0].text
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]

    data = json.loads(text)
    return TestPlan(**data)
