"""Provider registry and factory."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agnirudra.agni.providers.base import BaseProvider

# Model prefix → (module path, class name, env var for API key)
_PROVIDER_MAP: dict[str, tuple[str, str, str]] = {
    "claude-": (
        "agnirudra.agni.providers.anthropic_provider",
        "AnthropicProvider",
        "AGNI_ANTHROPIC_API_KEY",
    ),
    "moonshotai/": (
        "agnirudra.agni.providers.nvidia_kimi",
        "NvidiaKimiProvider",
        "AGNI_NVIDIA_API_KEY",
    ),
    "gemini-": (
        "agnirudra.agni.providers.gemini",
        "GeminiProvider",
        "AGNI_GOOGLE_API_KEY",
    ),
}


def detect_provider_prefix(model: str) -> str:
    """Return the matching prefix key for *model*."""
    for prefix in _PROVIDER_MAP:
        if model.startswith(prefix):
            return prefix
    raise ValueError(
        f"Unknown model: {model!r}. "
        f"Supported prefixes: {list(_PROVIDER_MAP.keys())}"
    )


def get_api_key_env_var(model: str) -> str:
    """Return the env var name that holds the API key for *model*."""
    prefix = detect_provider_prefix(model)
    return _PROVIDER_MAP[prefix][2]


def create_provider(
    model: str,
    api_key: str,
    display_width: int = 1280,
    display_height: int = 720,
) -> BaseProvider:
    """Instantiate the provider matching *model*."""
    prefix = detect_provider_prefix(model)
    module_path, class_name, _ = _PROVIDER_MAP[prefix]
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls(
        api_key=api_key,
        model=model,
        display_width=display_width,
        display_height=display_height,
    )
