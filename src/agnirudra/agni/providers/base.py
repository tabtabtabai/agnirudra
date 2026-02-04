"""Abstract base class for model providers."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass
class ProviderToolCall:
    """Normalized tool call returned by any provider."""

    id: str
    name: str  # "computer", "bash", or "str_replace_based_edit_tool"
    input: dict


@dataclass
class ProviderResponse:
    """Normalized response from any provider."""

    text_blocks: list[str] = field(default_factory=list)
    tool_calls: list[ProviderToolCall] = field(default_factory=list)
    stop_reason: str = ""


class BaseProvider(abc.ABC):
    """Interface every model provider must implement."""

    @abc.abstractmethod
    def __init__(
        self, api_key: str, model: str, display_width: int, display_height: int
    ) -> None: ...

    @abc.abstractmethod
    def create_message(
        self,
        system: str,
        messages: list[dict],
    ) -> ProviderResponse:
        """Send messages to the model and return a normalized response."""
        ...

    @abc.abstractmethod
    def format_assistant_content(self, response: ProviderResponse) -> list[dict]:
        """Build the assistant message content list for conversation history."""
        ...

    @abc.abstractmethod
    def format_tool_results(self, results: list[dict]) -> list[dict]:
        """Format tool execution results into user message content.

        Each item in *results* has keys:
          - tool_call_id: str (echoes ProviderToolCall.id)
          - content: dict | list[dict] (from _handle_tool_call)
        """
        ...

    def needs_image_forwarding(self) -> bool:
        """If True, screenshots in tool results must be sent as separate user messages.

        Override to return True for providers without native computer-use
        (e.g. OpenAI-compatible function-calling APIs).
        """
        return False

    def system_prompt_addendum(self) -> str:
        """Extra text appended to the system prompt.

        Non-native-CU providers use this to document the available function tools.
        """
        return ""
