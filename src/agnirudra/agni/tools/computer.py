"""Computer-use tool: screenshots, mouse clicks, keyboard input via xdotool/scrot."""

from __future__ import annotations

import base64
import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

DISPLAY = ":1"


def screenshot() -> str:
    """Take a screenshot and return it as a base64-encoded PNG string."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name

    subprocess.run(
        ["scrot", "-o", path],
        env={"DISPLAY": DISPLAY},
        check=True,
        capture_output=True,
    )
    data = Path(path).read_bytes()
    Path(path).unlink(missing_ok=True)
    return base64.standard_b64encode(data).decode()


def click(x: int, y: int, button: int = 1) -> None:
    """Click at (x, y) with the given mouse button (1=left, 2=middle, 3=right)."""
    subprocess.run(
        ["xdotool", "mousemove", str(x), str(y), "click", str(button)],
        env={"DISPLAY": DISPLAY},
        check=True,
        capture_output=True,
    )
    logger.debug("Clicked at (%d, %d) button=%d", x, y, button)


def double_click(x: int, y: int) -> None:
    """Double-click at (x, y)."""
    subprocess.run(
        [
            "xdotool",
            "mousemove",
            str(x),
            str(y),
            "click",
            "--repeat",
            "2",
            "1",
        ],
        env={"DISPLAY": DISPLAY},
        check=True,
        capture_output=True,
    )


def type_text(text: str) -> None:
    """Type text using xdotool."""
    subprocess.run(
        ["xdotool", "type", "--clearmodifiers", "--delay", "50", text],
        env={"DISPLAY": DISPLAY},
        check=True,
        capture_output=True,
    )


def key(keys: str) -> None:
    """Press key combination, e.g. 'Return', 'ctrl+l', 'ctrl+a'."""
    subprocess.run(
        ["xdotool", "key", "--clearmodifiers", keys],
        env={"DISPLAY": DISPLAY},
        check=True,
        capture_output=True,
    )


def scroll(x: int, y: int, direction: str, amount: int = 3) -> None:
    """Scroll at position. direction is 'up' or 'down'."""
    button = "4" if direction == "up" else "5"
    subprocess.run(
        ["xdotool", "mousemove", str(x), str(y)],
        env={"DISPLAY": DISPLAY},
        check=True,
        capture_output=True,
    )
    for _ in range(amount):
        subprocess.run(
            ["xdotool", "click", button],
            env={"DISPLAY": DISPLAY},
            check=True,
            capture_output=True,
        )


def mouse_move(x: int, y: int) -> None:
    """Move mouse to (x, y) without clicking."""
    subprocess.run(
        ["xdotool", "mousemove", str(x), str(y)],
        env={"DISPLAY": DISPLAY},
        check=True,
        capture_output=True,
    )


def drag(start_x: int, start_y: int, end_x: int, end_y: int) -> None:
    """Click-and-drag from start to end coordinates."""
    subprocess.run(
        [
            "xdotool",
            "mousemove",
            str(start_x),
            str(start_y),
            "mousedown",
            "1",
            "mousemove",
            str(end_x),
            str(end_y),
            "mouseup",
            "1",
        ],
        env={"DISPLAY": DISPLAY},
        check=True,
        capture_output=True,
    )
