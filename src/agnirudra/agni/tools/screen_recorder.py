"""FFmpeg screen recorder: start/stop recording of the virtual display."""

from __future__ import annotations

import logging
import signal
import subprocess

logger = logging.getLogger(__name__)

_process: subprocess.Popen | None = None

DEFAULT_OUTPUT = "/tmp/recording.mp4"
DISPLAY = ":1"
RESOLUTION = "1280x720"
FPS = "15"


def start(output_path: str = DEFAULT_OUTPUT) -> None:
    """Start FFmpeg screen recording in the background."""
    global _process
    if _process is not None:
        logger.warning("Recording already in progress")
        return

    cmd = [
        "ffmpeg",
        "-y",
        "-f", "x11grab",
        "-video_size", RESOLUTION,
        "-framerate", FPS,
        "-i", DISPLAY,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "28",
        "-pix_fmt", "yuv420p",
        output_path,
    ]
    _process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    logger.info("Started screen recording -> %s (pid=%d)", output_path, _process.pid)


def stop() -> None:
    """Stop the FFmpeg recording gracefully with SIGINT for clean MP4 finalization."""
    global _process
    if _process is None:
        logger.warning("No recording in progress")
        return

    logger.info("Stopping screen recording (pid=%d)", _process.pid)
    _process.send_signal(signal.SIGINT)
    try:
        _process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        _process.kill()
        _process.wait()
    _process = None
    logger.info("Screen recording stopped")


def is_recording() -> bool:
    """Check if recording is currently active."""
    return _process is not None and _process.poll() is None
