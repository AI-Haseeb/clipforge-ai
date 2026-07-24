from __future__ import annotations  # enables future Python language features
from pathlib import Path  # provides object-oriented file paths
from typing import Optional  # adds type hint helpers

# Use the single source of truth in utils
from src.utils.ffmpeg import extract_audio as _extract_audio  # project FFmpeg helper
def extract(  # pulls audio, text, frames, or metadata from source media
    input_video: Path,
    out_wav: Path,
    *,
    ffmpeg_path: str = "ffmpeg",
    sample_rate: int = 16000,
) -> None:
    """
    Extract mono WAV for Whisper.
    Keeps backward compatibility with main.py and supports ffmpeg_path.
    """
    _extract_audio(
        input_video=Path(input_video),
        out_wav=Path(out_wav),
        ffmpeg_path=str(ffmpeg_path),
        sample_rate=int(sample_rate),
    )
