"""NVIDIA Build / Kimi K2.5 provider — OpenAI-compatible, function calling."""

from __future__ import annotations

import json
import logging
import uuid

from openai import OpenAI

from agnirudra.agni.providers.base import BaseProvider, ProviderResponse, ProviderToolCall

logger = logging.getLogger(__name__)

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

# OpenAI function-calling tool definitions
KIMI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "screenshot",
            "description": "Take a screenshot of the current screen.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "Click at pixel coordinates (x, y) on the screen. The display is 1280x720.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X pixel coordinate"},
                    "y": {"type": "integer", "description": "Y pixel coordinate"},
                    "button": {
                        "type": "string",
                        "enum": ["left", "right", "middle"],
                        "default": "left",
                    },
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type text using the keyboard.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "key",
            "description": "Press a key or key combination (e.g. 'Return', 'ctrl+a', 'ctrl+l').",
            "parameters": {
                "type": "object",
                "properties": {"keys": {"type": "string"}},
                "required": ["keys"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll",
            "description": "Scroll at a position on the screen.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "direction": {"type": "string", "enum": ["up", "down"]},
                    "amount": {"type": "integer", "default": 3},
                },
                "required": ["x", "y", "direction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a bash command and return the output.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
]


def _kimi_to_canonical(name: str, args: dict) -> dict:
    """Convert a Kimi function call to the canonical tool format used by _handle_tool_call."""
    if name == "screenshot":
        return {"name": "computer", "input": {"action": "screenshot"}}
    elif name == "click":
        button_map = {"left": "left_click", "right": "right_click", "middle": "middle_click"}
        action = button_map.get(args.get("button", "left"), "left_click")
        return {"name": "computer", "input": {"action": action, "coordinate": [args["x"], args["y"]]}}
    elif name == "type_text":
        return {"name": "computer", "input": {"action": "type", "text": args["text"]}}
    elif name == "key":
        return {"name": "computer", "input": {"action": "key", "text": args["keys"]}}
    elif name == "scroll":
        return {"name": "computer", "input": {
            "action": "scroll",
            "coordinate": [args["x"], args["y"]],
            "direction": args["direction"],
            "amount": args.get("amount", 3),
        }}
    elif name == "bash":
        return {"name": "bash", "input": {"command": args["command"]}}
    return {"name": name, "input": args}


class NvidiaKimiProvider(BaseProvider):

    def __init__(
        self, api_key: str, model: str, display_width: int, display_height: int
    ) -> None:
        self.client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key)
        self.model = model
        self.display_width = display_width
        self.display_height = display_height

    # ------------------------------------------------------------------
    # BaseProvider interface
    # ------------------------------------------------------------------

    def create_message(
        self, system: str, messages: list[dict]
    ) -> ProviderResponse:
        oai_messages = self._convert_messages(system, messages)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=oai_messages,
            tools=KIMI_TOOLS,
            max_tokens=4096,
        )

        choice = response.choices[0]
        text_blocks: list[str] = []
        tool_calls: list[ProviderToolCall] = []

        if choice.message.content:
            text_blocks.append(choice.message.content)

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                args = json.loads(tc.function.arguments)
                canonical = _kimi_to_canonical(tc.function.name, args)
                tool_calls.append(ProviderToolCall(
                    id=tc.id,
                    name=canonical["name"],
                    input=canonical["input"],
                ))

        return ProviderResponse(
            text_blocks=text_blocks,
            tool_calls=tool_calls,
            stop_reason="end_turn" if choice.finish_reason == "stop" else (choice.finish_reason or ""),
        )

    def format_assistant_content(self, response: ProviderResponse) -> list[dict]:
        # Store in canonical internal format (same as Anthropic)
        content: list[dict] = [{"type": "text", "text": t} for t in response.text_blocks]
        for tc in response.tool_calls:
            content.append({
                "type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.input,
            })
        return content

    def format_tool_results(self, results: list[dict]) -> list[dict]:
        # Store in canonical internal format
        out: list[dict] = []
        for r in results:
            content = r["content"]
            if isinstance(content, dict):
                content = [content]
            out.append({
                "type": "tool_result",
                "tool_use_id": r["tool_call_id"],
                "content": content,
            })
        return out

    def needs_image_forwarding(self) -> bool:
        return True

    def system_prompt_addendum(self) -> str:
        return (
            "\nAVAILABLE TOOLS:\n"
            "- screenshot() — Take a screenshot to see the current screen\n"
            "- click(x, y) — Click at pixel coordinates\n"
            "- type_text(text) — Type text using keyboard\n"
            "- key(keys) — Press key combination (e.g. 'Return', 'ctrl+l')\n"
            "- scroll(x, y, direction, amount) — Scroll at position\n"
            "- bash(command) — Run a bash command\n"
            f"\nThe screen resolution is {self.display_width}x{self.display_height} pixels. "
            "Coordinates are absolute pixel values.\n"
            "After each action, a screenshot will be provided so you can see the result.\n"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _convert_messages(self, system: str, messages: list[dict]) -> list[dict]:
        """Convert internal (Anthropic-style) messages to OpenAI chat format."""
        oai: list[dict] = [{"role": "system", "content": system}]

        for msg in messages:
            role = msg["role"]
            content = msg.get("content", "")

            if role == "assistant":
                oai.extend(self._convert_assistant_msg(content))
            elif role == "user":
                oai.extend(self._convert_user_msg(content))

        return oai

    def _convert_assistant_msg(self, content: str | list) -> list[dict]:
        """Convert an assistant message to OpenAI format."""
        if not isinstance(content, list):
            return [{"role": "assistant", "content": str(content)}]

        text_parts: list[str] = []
        tc_list: list[dict] = []

        for block in content:
            if block.get("type") == "text":
                text_parts.append(block["text"])
            elif block.get("type") == "tool_use":
                # Reverse-map canonical name back to Kimi function name
                fn_name, fn_args = self._canonical_to_kimi(block["name"], block["input"])
                tc_list.append({
                    "id": block["id"],
                    "type": "function",
                    "function": {"name": fn_name, "arguments": json.dumps(fn_args)},
                })

        oai_msg: dict = {"role": "assistant"}
        oai_msg["content"] = "\n".join(text_parts) if text_parts else None
        if tc_list:
            oai_msg["tool_calls"] = tc_list
        return [oai_msg]

    def _convert_user_msg(self, content: str | list) -> list[dict]:
        """Convert a user message to OpenAI format."""
        if not isinstance(content, list):
            return [{"role": "user", "content": str(content)}]

        # Check if these are tool_results
        has_tool_results = any(b.get("type") == "tool_result" for b in content if isinstance(b, dict))

        if has_tool_results:
            msgs: list[dict] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_result":
                    result_text = self._tool_result_to_text(block.get("content", []))
                    msgs.append({
                        "role": "tool",
                        "tool_call_id": block["tool_use_id"],
                        "content": result_text,
                    })
                elif block.get("type") == "text":
                    msgs.append({"role": "user", "content": block["text"]})
            return msgs

        # Mixed content — convert images to data URLs
        parts: list[dict] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                parts.append({"type": "text", "text": block["text"]})
            elif block.get("type") == "image":
                src = block.get("source", {})
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{src['media_type']};base64,{src['data']}"},
                })
        return [{"role": "user", "content": parts}] if parts else []

    def _tool_result_to_text(self, content: list | dict) -> str:
        """Flatten tool result content to text (images become placeholders)."""
        if isinstance(content, dict):
            content = [content]
        parts: list[str] = []
        for block in content:
            if block.get("type") == "text":
                parts.append(block["text"])
            elif block.get("type") == "image":
                parts.append("[screenshot taken — see next message]")
        return "\n".join(parts) if parts else "(no output)"

    @staticmethod
    def _canonical_to_kimi(name: str, input_data: dict) -> tuple[str, dict]:
        """Reverse-map canonical tool call back to Kimi function name + args."""
        if name == "computer":
            action = input_data.get("action", "")
            if action == "screenshot":
                return "screenshot", {}
            elif action in ("left_click", "right_click", "middle_click"):
                btn = {"left_click": "left", "right_click": "right", "middle_click": "middle"}
                coords = input_data.get("coordinate", [0, 0])
                return "click", {"x": coords[0], "y": coords[1], "button": btn.get(action, "left")}
            elif action == "type":
                return "type_text", {"text": input_data.get("text", "")}
            elif action == "key":
                return "key", {"keys": input_data.get("text", "")}
            elif action == "scroll":
                coords = input_data.get("coordinate", [640, 360])
                return "scroll", {
                    "x": coords[0], "y": coords[1],
                    "direction": input_data.get("direction", "down"),
                    "amount": input_data.get("amount", 3),
                }
        elif name == "bash":
            return "bash", {"command": input_data.get("command", "")}
        return name, input_data
