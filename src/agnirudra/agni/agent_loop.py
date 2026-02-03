"""Opus 4.5 computer-use agent loop.

Runs inside the Azure VM Docker container. Drives a browser through the
test plan using Anthropic's computer-use beta API.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import anthropic

from agnirudra.agni.tools import computer, bash_tool

logger = logging.getLogger(__name__)

MAX_SCREENSHOTS_IN_CONTEXT = 10

SYSTEM_PROMPT = """\
You are Agni, an automated QA testing agent. You have a browser and a
Linux desktop. Your job: visually verify that a PR's changes work.

{auth_section}TEST PLAN:
{test_plan}

INSTRUCTIONS:
1. Open Chromium and navigate to the start URL.
2. If the app shows a login or sign-in page, log in using the credentials above.
3. Follow the test steps one by one.
4. After each step, observe the result on screen.
5. When done, write your verdict to /tmp/verdict.json:
   {{"passed": true/false, "summary": "what happened"}}
6. If you cannot complete a step, note what went wrong and still write verdict.json.
"""


@dataclass
class Verdict:
    passed: bool
    summary: str


def _build_test_plan_text(test_plan: dict) -> str:
    lines = [f"Description: {test_plan.get('description', '')}"]
    lines.append(f"Start URL: {test_plan.get('start_url', 'http://localhost:3000')}")
    lines.append(f"Pass criteria: {test_plan.get('pass_criteria', '')}")
    lines.append(f"Fail criteria: {test_plan.get('fail_criteria', '')}")
    lines.append("Steps:")
    for i, step in enumerate(test_plan.get("steps", []), 1):
        lines.append(f"  {i}. {step}")
    return "\n".join(lines)


def _make_tools(width: int, height: int) -> list[dict]:
    return [
        {
            "type": "computer_20250124",
            "name": "computer",
            "display_width_px": width,
            "display_height_px": height,
            "display_number": 1,
        },
        {
            "type": "bash_20250124",
            "name": "bash",
        },
        {
            "type": "text_editor_20250728",
            "name": "text_editor",
        },
    ]


def _handle_tool_call(tool_use: dict) -> dict:
    """Execute a tool call and return the tool_result content."""
    name = tool_use.get("name", "")
    input_data = tool_use.get("input", {})

    if name == "computer":
        return _handle_computer_tool(input_data)
    elif name == "bash":
        return _handle_bash_tool(input_data)
    elif name == "text_editor":
        return _handle_text_editor(input_data)
    else:
        return {"type": "text", "text": f"Unknown tool: {name}"}


def _handle_computer_tool(input_data: dict) -> dict | list:
    """Handle computer tool actions and return result content."""
    action = input_data.get("action", "")

    if action == "screenshot":
        img_b64 = computer.screenshot()
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": img_b64},
        }
    elif action == "left_click":
        coords = input_data.get("coordinate", [0, 0])
        computer.click(coords[0], coords[1], button=1)
    elif action == "right_click":
        coords = input_data.get("coordinate", [0, 0])
        computer.click(coords[0], coords[1], button=3)
    elif action == "double_click":
        coords = input_data.get("coordinate", [0, 0])
        computer.double_click(coords[0], coords[1])
    elif action == "middle_click":
        coords = input_data.get("coordinate", [0, 0])
        computer.click(coords[0], coords[1], button=2)
    elif action == "mouse_move":
        coords = input_data.get("coordinate", [0, 0])
        computer.mouse_move(coords[0], coords[1])
    elif action == "type":
        text = input_data.get("text", "")
        computer.type_text(text)
    elif action == "key":
        keys = input_data.get("text", "")
        computer.key(keys)
    elif action == "scroll":
        coords = input_data.get("coordinate", [640, 360])
        direction = input_data.get("direction", "down")
        amount = input_data.get("amount", 3)
        computer.scroll(coords[0], coords[1], direction, amount)
    elif action == "drag":
        start = input_data.get("start_coordinate", [0, 0])
        end = input_data.get("end_coordinate", [0, 0])
        computer.drag(start[0], start[1], end[0], end[1])
    else:
        return {"type": "text", "text": f"Unknown computer action: {action}"}

    # For non-screenshot actions, take a follow-up screenshot
    img_b64 = computer.screenshot()
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": img_b64},
    }


def _handle_bash_tool(input_data: dict) -> dict:
    command = input_data.get("command", "")
    restart = input_data.get("restart", False)
    if restart:
        return {"type": "text", "text": "Shell restarted."}
    returncode, output = bash_tool.run(command)
    return {"type": "text", "text": output or "(no output)"}


def _handle_text_editor(input_data: dict) -> dict:
    """Handle the text editor tool via shell commands."""
    command = input_data.get("command", "")
    path = input_data.get("path", "")
    if command == "view":
        _, output = bash_tool.run(f"cat -n '{path}'")
        return {"type": "text", "text": output or "(empty file)"}
    elif command == "write":
        content = input_data.get("file_text", "")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content)
        return {"type": "text", "text": f"Wrote {len(content)} chars to {path}"}
    elif command == "str_replace":
        old = input_data.get("old_str", "")
        new = input_data.get("new_str", "")
        text = Path(path).read_text()
        if old not in text:
            return {"type": "text", "text": f"old_str not found in {path}"}
        text = text.replace(old, new, 1)
        Path(path).write_text(text)
        return {"type": "text", "text": f"Replaced in {path}"}
    elif command == "insert":
        line = input_data.get("insert_line", 0)
        new_str = input_data.get("new_str", "")
        lines = Path(path).read_text().splitlines(keepends=True)
        lines.insert(line, new_str + "\n")
        Path(path).write_text("".join(lines))
        return {"type": "text", "text": f"Inserted at line {line} in {path}"}
    elif command == "undo_edit":
        return {"type": "text", "text": "Undo not supported in this environment"}
    return {"type": "text", "text": f"Unknown editor command: {command}"}


def _truncate_old_screenshots(messages: list[dict]) -> list[dict]:
    """Replace old screenshot images with placeholder text to control context size."""
    screenshot_count = 0
    # Walk backwards to count screenshots
    for msg in reversed(messages):
        if msg["role"] != "user":
            continue
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "image":
                screenshot_count += 1

    if screenshot_count <= MAX_SCREENSHOTS_IN_CONTEXT:
        return messages

    # Truncate oldest screenshots
    to_remove = screenshot_count - MAX_SCREENSHOTS_IN_CONTEXT
    removed = 0
    for msg in messages:
        if msg["role"] != "user":
            continue
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        for i, block in enumerate(content):
            if isinstance(block, dict) and block.get("type") == "image" and removed < to_remove:
                content[i] = {"type": "text", "text": "[screenshot truncated]"}
                removed += 1

    return messages


def _build_auth_section(test_email: str, test_password: str) -> str:
    """Build the authentication section for the system prompt."""
    if test_email and test_password:
        return (
            "AUTHENTICATION:\n"
            "If the app shows a login/sign-in page, log in with:\n"
            f"  Email: {test_email}\n"
            f"  Password: {test_password}\n"
            "Then continue with the test steps.\n\n"
        )
    return ""


def run_agent_loop(
    api_key: str,
    model: str,
    test_plan: dict,
    max_iterations: int = 30,
    display_width: int = 1280,
    display_height: int = 720,
    test_email: str = "",
    test_password: str = "",
) -> Verdict:
    """Run the computer-use agent loop. Returns a Verdict."""
    client = anthropic.Anthropic(api_key=api_key)

    plan_text = _build_test_plan_text(test_plan)
    auth_section = _build_auth_section(test_email, test_password)
    system = SYSTEM_PROMPT.format(test_plan=plan_text, auth_section=auth_section)
    tools = _make_tools(display_width, display_height)

    messages: list[dict] = [
        {
            "role": "user",
            "content": "Begin the test. Start by taking a screenshot to see the current state of the desktop.",
        }
    ]

    for iteration in range(max_iterations):
        logger.info("Agent iteration %d/%d", iteration + 1, max_iterations)

        messages = _truncate_old_screenshots(messages)

        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system,
            tools=tools,
            messages=messages,
        )

        # Collect assistant content blocks
        assistant_content = []
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
                logger.info("Agent: %s", block.text[:200])
            elif block.type == "tool_use":
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })
                tool_calls.append(block)

        messages.append({"role": "assistant", "content": assistant_content})

        # If no tool calls, the agent is done
        if not tool_calls:
            logger.info("Agent stopped requesting tools")
            break

        # Execute tool calls and build tool_result messages
        tool_results = []
        for tc in tool_calls:
            result_content = _handle_tool_call({
                "name": tc.name,
                "input": tc.input,
            })
            # Wrap in a list if it's a single dict
            if isinstance(result_content, dict):
                result_content = [result_content]
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": result_content,
            })

        messages.append({"role": "user", "content": tool_results})

        # Check stop reason
        if response.stop_reason == "end_turn":
            logger.info("Agent ended turn")
            break

    # Read verdict
    verdict_path = Path("/tmp/verdict.json")
    if verdict_path.exists():
        try:
            data = json.loads(verdict_path.read_text())
            return Verdict(passed=data.get("passed", False), summary=data.get("summary", ""))
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Failed to parse verdict: %s", exc)

    return Verdict(passed=False, summary="Agent did not write a verdict file.")


def main() -> None:
    """Entry point when run inside the Docker container."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    api_key = os.environ.get("AGNI_ANTHROPIC_API_KEY", "")
    model = os.environ.get("AGNI_MODEL", "claude-opus-4-5-20251101")
    test_plan_raw = os.environ.get("TEST_PLAN", "{}")
    max_iter = int(os.environ.get("AGNI_MAX_AGENT_ITERATIONS", "30"))

    if not api_key:
        logger.error("AGNI_ANTHROPIC_API_KEY is required")
        sys.exit(1)

    test_email = os.environ.get("AGNI_TEST_EMAIL", "")
    test_password = os.environ.get("AGNI_TEST_PASSWORD", "")

    test_plan = json.loads(test_plan_raw)
    verdict = run_agent_loop(
        api_key, model, test_plan,
        max_iterations=max_iter,
        test_email=test_email,
        test_password=test_password,
    )

    # Write verdict for entrypoint.sh to pick up
    Path("/tmp/verdict.json").write_text(json.dumps({
        "passed": verdict.passed,
        "summary": verdict.summary,
    }))
    logger.info("Verdict: passed=%s summary=%s", verdict.passed, verdict.summary)


if __name__ == "__main__":
    main()
