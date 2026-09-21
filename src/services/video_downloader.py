import os  # reads optional downloader settings from environment variables
from pathlib import Path  # provides object-oriented file paths

from yt_dlp import YoutubeDL  # downloads media from supported websites
from yt_dlp.utils import DownloadError  # exposes downloader failures for clear error handling


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COOKIE_FILE = PROJECT_ROOT / "config" / "youtube_cookies.txt"


class VideoDownloadError(RuntimeError):
    """Reports a safe, user-readable link download failure."""


def _youtube_cookie_file() -> Path | None:
    """Returns the configured YouTube cookie file only when it exists and is not empty."""
    configured_path = os.getenv("CLIPFORGE_YOUTUBE_COOKIE_FILE", "").strip()
    cookie_path = Path(configured_path).expanduser() if configured_path else DEFAULT_COOKIE_FILE
    if cookie_path.is_file() and cookie_path.stat().st_size > 0:
        return cookie_path.resolve()
    return None


def _download_error_message(error: Exception, cookie_file: Path | None) -> str:
    """Converts yt-dlp errors into concise instructions suitable for the frontend."""
    message = str(error)
    normalized = message.lower()
    blocked = (
        "429" in normalized
        or "too many requests" in normalized
        or "confirm you’re not a bot" in normalized
        or "confirm you're not a bot" in normalized
        or "sign in to confirm" in normalized
    )
    if blocked:
        cookie_hint = (
            f"The configured cookie file was rejected or expired: {cookie_file}."
            if cookie_file
            else
            "Export fresh youtube.com cookies in Netscape format to "
            f"{DEFAULT_COOKIE_FILE}."
        )
        return (
            "YouTube blocked this link download with a rate-limit or bot check. "
            f"{cookie_hint} Keep this private file out of Git, restart the worker, "
            "and retry the job."
        )
    return f"The video link could not be downloaded: {message}"


def download_video_from_url(video_url: str, output_dir: str = "data/link_uploads") -> Path:  # downloads a supported video URL into the local link upload folder
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cookie_file = _youtube_cookie_file()

    ydl_opts = {
        "outtmpl": str(out_dir / "%(title).80s.%(ext)s"),
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": False,
        "no_warnings": False,
        "retries": 3,
        "fragment_retries": 3,
        "extractor_retries": 2,
        "sleep_interval_requests": 1,
        "sleep_interval": 5,
        "max_sleep_interval": 10,
        "windowsfilenames": True,
        "restrictfilenames": True,
    }
    if cookie_file:
        ydl_opts["cookiefile"] = str(cookie_file)

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            downloaded_path = Path(ydl.prepare_filename(info))
            if downloaded_path.suffix.lower() != ".mp4":
                merged_path = downloaded_path.with_suffix(".mp4")
                if merged_path.exists():
                    downloaded_path = merged_path
    except DownloadError as exc:
        raise VideoDownloadError(_download_error_message(exc, cookie_file)) from exc

    if not downloaded_path.exists():
        raise FileNotFoundError(f"Downloaded video was not found: {downloaded_path}")

    return downloaded_path
