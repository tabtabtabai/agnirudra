"""Anthropic Claude provider — native computer-use."""

from __future__ import annotations

import anthropic

from agnirudra.agni.providers.base import BaseProvider, ProviderResponse, ProviderToolCall

COMPUTER_USE_BETA = "computer-use-2025-01-24"


class AnthropicProvider(BaseProvider):

    def __init__(
        self, api_key: str, model: str, display_width: int, display_height: int
    ) -> None:
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.tools = [
            {
                "type": "computer_20250124",
                "name": "computer",
                "display_width_px": display_width,
                "display_height_px": display_height,
                "display_number": 1,
            },
            {
                "type": "bash_20250124",
                "name": "bash",
            },
            {
                "type": "text_editor_20250728",
                "name": "str_replace_based_edit_tool",
            },
        ]

    def create_message(
        self, system: str, messages: list[dict]
    ) -> ProviderResponse:
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            tools=self.tools,
            messages=messages,
            betas=[COMPUTER_USE_BETA],
        )

        text_blocks: list[str] = []
        tool_calls: list[ProviderToolCall] = []

        for block in response.content:
            if block.type == "text":
                text_blocks.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ProviderToolCall(
                        id=block.id,
                        name=block.name,
                        input=block.input,
                    )
                )

        return ProviderResponse(
            text_blocks=text_blocks,
            tool_calls=tool_calls,
            stop_reason=response.stop_reason or "",
        )

    def format_assistant_content(self, response: ProviderResponse) -> list[dict]:
        content: list[dict] = [
            {"type": "text", "text": t} for t in response.text_blocks
        ]
        for tc in response.tool_calls:
            content.append(
                {
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.input,
                }
            )
        return content

    def format_tool_results(self, results: list[dict]) -> list[dict]:
        out: list[dict] = []
        for r in results:
            content = r["content"]
            if isinstance(content, dict):
                content = [content]
            out.append(
                {
                    "type": "tool_result",
                    "tool_use_id": r["tool_call_id"],
                    "content": content,
                }
            )
        return out
