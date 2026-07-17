from pathlib import Path  # provides object-oriented file paths
from yt_dlp import YoutubeDL  # downloads media from supported websites
def download_video_from_url(video_url: str, output_dir: str = "data/link_uploads") -> Path:  # downloads or returns a generated file
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        "outtmpl": str(out_dir / "%(title).80s.%(ext)s"),
        "format": "mp4/best[ext=mp4]/best",
        "noplaylist": True,
        "quiet": False,
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        downloaded_path = Path(ydl.prepare_filename(info))

    return downloaded_path
