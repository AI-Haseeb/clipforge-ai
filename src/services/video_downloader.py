from pathlib import Path  # provides object-oriented file paths
from yt_dlp import YoutubeDL  # downloads media from supported websites


def download_video_from_url(video_url: str, output_dir: str = "data/link_uploads") -> Path:  # downloads a supported video URL into the local link upload folder
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        "outtmpl": str(out_dir / "%(title).80s.%(ext)s"),
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": False,
        "no_warnings": False,
        "retries": 3,
        "fragment_retries": 3,
        "windowsfilenames": True,
        "restrictfilenames": True,
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        downloaded_path = Path(ydl.prepare_filename(info))
        if downloaded_path.suffix.lower() != ".mp4":
            merged_path = downloaded_path.with_suffix(".mp4")
            if merged_path.exists():
                downloaded_path = merged_path

    if not downloaded_path.exists():
        raise FileNotFoundError(f"Downloaded video was not found: {downloaded_path}")

    return downloaded_path
