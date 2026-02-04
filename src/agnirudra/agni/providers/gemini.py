"""Google Gemini 2.5 Computer Use provider — native computer-use."""

from __future__ import annotations

import base64
import logging
import uuid

from google import genai
from google.genai import types

from agnirudra.agni.providers.base import BaseProvider, ProviderResponse, ProviderToolCall

logger = logging.getLogger(__name__)


def _grid_to_pixel(gx: int, gy: int, width: int, height: int) -> tuple[int, int]:
    """Convert Gemini's 0-999 grid to pixel coordinates."""
    return int(gx * width / 1000), int(gy * height / 1000)


def _gemini_to_canonical(
    name: str, args: dict, width: int, height: int
) -> dict:
    """Map a Gemini function_call to the canonical tool format."""
    if name == "click_at":
        x, y = _grid_to_pixel(args.get("x", 0), args.get("y", 0), width, height)
        return {"name": "computer", "input": {"action": "left_click", "coordinate": [x, y]}}
    elif name == "double_click_at":
        x, y = _grid_to_pixel(args.get("x", 0), args.get("y", 0), width, height)
        return {"name": "computer", "input": {"action": "double_click", "coordinate": [x, y]}}
    elif name == "right_click_at":
        x, y = _grid_to_pixel(args.get("x", 0), args.get("y", 0), width, height)
        return {"name": "computer", "input": {"action": "right_click", "coordinate": [x, y]}}
    elif name == "type_text":
        text = args.get("text", "")
        result = {"name": "computer", "input": {"action": "type", "text": text}}
        if args.get("press_enter"):
            # Will be handled as a two-step action in agent_loop
            result["input"]["press_enter"] = True
        return result
    elif name == "press_key":
        return {"name": "computer", "input": {"action": "key", "text": args.get("key", "")}}
    elif name == "scroll":
        x, y = _grid_to_pixel(args.get("x", 500), args.get("y", 500), width, height)
        direction = args.get("direction", "down")
        amount = args.get("amount", 3)
        return {"name": "computer", "input": {
            "action": "scroll",
            "coordinate": [x, y],
            "direction": direction,
            "amount": amount,
        }}
    elif name == "navigate":
        url = args.get("url", "")
        return {"name": "bash", "input": {"command": f"browser {url}"}}
    elif name == "wait":
        secs = args.get("seconds", 2)
        return {"name": "bash", "input": {"command": f"sleep {secs}"}}
    elif name == "screenshot":
        return {"name": "computer", "input": {"action": "screenshot"}}
    elif name == "bash":
        return {"name": "bash", "input": {"command": args.get("command", "")}}
    return {"name": name, "input": args}


class GeminiProvider(BaseProvider):

    def __init__(
        self, api_key: str, model: str, display_width: int, display_height: int
    ) -> None:
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.display_width = display_width
        self.display_height = display_height

    def create_message(
        self, system: str, messages: list[dict]
    ) -> ProviderResponse:
        gemini_contents = self._convert_messages(messages)

        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=[
                types.Tool(
                    computer_use=types.ComputerUse(
                        environment=types.Environment.ENVIRONMENT_BROWSER,
                    )
                )
            ],
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=gemini_contents,
            config=config,
        )

        text_blocks: list[str] = []
        tool_calls: list[ProviderToolCall] = []

        if response.candidates:
            candidate = response.candidates[0]
            for part in candidate.content.parts:
                if part.text:
                    text_blocks.append(part.text)
                elif part.function_call:
                    fc = part.function_call
                    args = dict(fc.args) if fc.args else {}
                    canonical = _gemini_to_canonical(
                        fc.name, args, self.display_width, self.display_height
                    )
                    tool_calls.append(ProviderToolCall(
                        id=f"gemini_{uuid.uuid4().hex[:8]}",
                        name=canonical["name"],
                        input=canonical["input"],
                    ))

        finish = ""
        if response.candidates:
            fr = response.candidates[0].finish_reason
            if fr and str(fr) == "STOP":
                finish = "end_turn"

        return ProviderResponse(
            text_blocks=text_blocks,
            tool_calls=tool_calls,
            stop_reason=finish,
        )

    def format_assistant_content(self, response: ProviderResponse) -> list[dict]:
        content: list[dict] = [{"type": "text", "text": t} for t in response.text_blocks]
        for tc in response.tool_calls:
            content.append({
                "type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.input,
            })
        return content

    def format_tool_results(self, results: list[dict]) -> list[dict]:
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

    # ------------------------------------------------------------------
    # Internal conversion
    # ------------------------------------------------------------------

    def _convert_messages(self, messages: list[dict]) -> list[types.Content]:
        """Convert internal message format to Gemini Content objects."""
        contents: list[types.Content] = []

        for msg in messages:
            role = msg["role"]
            gemini_role = "model" if role == "assistant" else "user"
            raw_content = msg.get("content", "")

            if not isinstance(raw_content, list):
                contents.append(types.Content(
                    role=gemini_role,
                    parts=[types.Part(text=str(raw_content))],
                ))
                continue

            parts: list[types.Part] = []
            for block in raw_content:
                if not isinstance(block, dict):
                    continue

                btype = block.get("type", "")

                if btype == "text":
                    parts.append(types.Part(text=block["text"]))

                elif btype == "image":
                    src = block.get("source", {})
                    img_bytes = base64.b64decode(src.get("data", ""))
                    parts.append(types.Part.from_bytes(
                        data=img_bytes,
                        mime_type=src.get("media_type", "image/png"),
                    ))

                elif btype == "tool_use" and gemini_role == "model":
                    # Reconstruct a function_call Part
                    parts.append(types.Part(
                        function_call=types.FunctionCall(
                            name=block.get("name", ""),
                            args=block.get("input", {}),
                        )
                    ))

                elif btype == "tool_result" and gemini_role == "user":
                    # Convert tool result to function_response
                    result_text = self._extract_text_from_content(block.get("content", []))
                    # Also extract screenshot if present
                    screenshot_bytes = self._extract_image_from_content(block.get("content", []))

                    fr_parts = []
                    if screenshot_bytes:
                        fr_parts.append(types.Part.from_bytes(
                            data=screenshot_bytes,
                            mime_type="image/png",
                        ))

                    parts.append(types.Part(
                        function_response=types.FunctionResponse(
                            name="computer_use",
                            response={"output": result_text},
                        )
                    ))
                    # Append screenshot as a separate part
                    if screenshot_bytes:
                        parts.append(types.Part.from_bytes(
                            data=screenshot_bytes,
                            mime_type="image/png",
                        ))

            if parts:
                contents.append(types.Content(role=gemini_role, parts=parts))

        return contents

    @staticmethod
    def _extract_text_from_content(content: list | dict) -> str:
        if isinstance(content, dict):
            content = [content]
        texts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block["text"])
        return "\n".join(texts) if texts else "(action completed)"

    @staticmethod
    def _extract_image_from_content(content: list | dict) -> bytes | None:
        if isinstance(content, dict):
            content = [content]
        for block in content:
            if isinstance(block, dict) and block.get("type") == "image":
                data = block.get("source", {}).get("data", "")
                if data:
                    return base64.b64decode(data)
        return None
