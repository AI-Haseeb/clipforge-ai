from __future__ import annotations  # enables future Python language features
import json  # handles JSON encode and decode
import os  # works with environment variables and OS paths
import subprocess  # runs external system commands
import sys  # accesses Python runtime and CLI state
import threading  # runs and coordinates threads
import time  # measures time, delays, and elapsed seconds
import uuid  # creates unique identifiers
from dataclasses import dataclass, asdict  # creates lightweight data classes
from datetime import datetime  # works with dates and timestamps
from pathlib import Path  # provides object-oriented file paths
from typing import Optional, Literal, Callable  # adds type hint helpers
from click import command  # builds command-line interfaces
from src.services.style_presets import apply_editing_style_defaults  # project style preset definitions

SegmentMode = Literal["semantic_ai", "fixed_duration", "manual", "raw_footage"]
Platform = Literal["youtube", "instagram", "tiktok"]


@dataclass
class PipelineRequest:  # stores validated data and related behavior for Pipeline Request
    input_video: str
    platform: Platform = "youtube"
    aspect_ratio: str = "9:16"
    segment_mode: SegmentMode = "semantic_ai"
    clip_duration_seconds: float = 45.0
    output_resolution: str = "1080p"
    manual_ranges: Optional[str] = None
    filter_preset: str = "Natural Enhance (Recommended)"
    captions: bool = True
    plan: str = "free"
    output_base_dir: str = "data/jobs"
    reframe: str = "off"
    font_preset: str = "clean_white"
    caption_position: str = "bottom_center"
    caption_size: str = "medium"
    editing_style: str = "podcast"
    openai_api_key: Optional[str] = None
    font_family: str = "preset"
    caption_case: str = "preset"
    music_enabled: bool = False
    music_category: str = "none"
    music_volume: float = 0.20
    music_track: Optional[str] = None

@dataclass
class PipelineResult:  # stores validated data and related behavior for Pipeline Result
    job_id: str
    status: str
    output_dir: str
    report_path: Optional[str]
    shorts: list[str]
    request: dict
def run_clipforge_pipeline(req: PipelineRequest, on_log: Optional[Callable[[str], None]] = None) -> PipelineResult:  # executes a pipeline step, command, or test
    req = apply_editing_style_defaults(req)
    input_path = Path(req.input_video).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"Input video not found: {input_path}")

    video_name = input_path.stem
    safe_name = "".join(
        c if c.isalnum() or c in ("_", "-") else "_"
        for c in video_name
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:4]

    job_id = f"{safe_name}_{timestamp}_{short_id}"

    output_base = Path(req.output_base_dir).resolve()
    job_output_dir = output_base / job_id
    job_output_dir.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "src.main",
        "--silent",
        "--yes",
        "--input",
        str(input_path),
        "--out-dir",
        str(job_output_dir),
        "--platform",
        req.platform,
        "--aspect",
        req.aspect_ratio,
        "--output-resolution",
        req.output_resolution,
        "--filter-preset",
        req.filter_preset,
        "--plan",
        req.plan,
        "--reframe",
        req.reframe,
        "--font-preset",
        req.font_preset,
        "--caption-position",
        req.caption_position,
        "--caption-size",
        req.caption_size,
        "--font-family",
        req.font_family,
        "--caption-case",
        req.caption_case,
        "--music-enabled",
        "on" if req.music_enabled else "off",
        "--music-category",
        req.music_category,
        "--editing-style",
        req.editing_style,
        "--music-volume",
        str(req.music_volume),
    ]

    if req.music_track:
        command.extend(["--music-track", req.music_track])

    if req.segment_mode == "semantic_ai":
        command.extend(["--segment-mode", "semantic_ai"])

    elif req.segment_mode == "fixed_duration":
        command.extend(["--segment-mode", "rule_chunks"])
        command.extend(["--simple-auto-mode", "uniform"])
        command.extend(["--simple-auto-chunk-len", str(req.clip_duration_seconds)])

    elif req.segment_mode == "manual":
        command.extend(["--segment-mode", "manual"])
        if req.manual_ranges:
            command.extend(["--manual-ranges", req.manual_ranges])
    elif req.segment_mode == "raw_footage":
        command.extend(["--segment-mode", "rule_chunks"])
        command.extend(["--simple-auto-mode", "silence"])
        command.extend(["--simple-auto-gap-thr", "0.60"])            

    if req.captions:
        command.append("--captions")
    else:
        command.append("--no-captions")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

    progress_json = job_output_dir / "progress.json"
    progress_json.unlink(missing_ok=True)
    env["CLIPFORGE_PROGRESS_FILE"] = str(progress_json)

    if req.openai_api_key:
        env["CLIPFORGE_OPENAI_API_KEY"] = req.openai_api_key
        env["OPENAI_API_KEY"] = req.openai_api_key

    request_json = job_output_dir / "request.json"
    request_json.write_text(
        json.dumps(asdict(req), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    process = subprocess.Popen(
        command,
        cwd=Path.cwd(),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )

    all_logs = []
    stop_progress_monitor = threading.Event()
    def emit_progress_line(payload: dict):# emits progress line to the caller/UI
        stage = payload.get("stage")
        label = payload.get("label") or "Processing"
        try:
            stage_int = int(stage)
        except (TypeError, ValueError):
            return
        line = f"[progress-stage] {stage_int} {label}\n"
        all_logs.append(line)
        if on_log:
            on_log(line)
    def monitor_progress_file():# monitors progress file for updates
        last_payload = ""
        while not stop_progress_monitor.is_set():
            try:
                if progress_json.exists():
                    raw = progress_json.read_text(encoding="utf-8")
                    if raw and raw != last_payload:
                        last_payload = raw
                        emit_progress_line(json.loads(raw))
            except Exception:
                pass
            stop_progress_monitor.wait(0.5)

    progress_thread = threading.Thread(target=monitor_progress_file, daemon=True)
    progress_thread.start()

    try:
        if process.stdout is not None:
            for line in process.stdout:
                print(line, end="")
                all_logs.append(line)
                if on_log:
                    on_log(line)

        process.wait()
    finally:
        stop_progress_monitor.set()
        progress_thread.join(timeout=2)

    stdout_text = "".join(all_logs)

    log_path = job_output_dir / "run.log"
    log_path.write_text(
        "COMMAND:\n"
        + " ".join(command)
        + "\n\nOUTPUT:\n"
        + stdout_text,
        encoding="utf-8",
    )

    if process.returncode != 0:
        raise RuntimeError(
            f"Pipeline failed. Check log file: {log_path}\n\n{stdout_text}"
        )

    shorts_dir = job_output_dir / "shorts"
    shorts = [str(p) for p in shorts_dir.rglob("*.mp4")] if shorts_dir.exists() else []

    reports_dir = job_output_dir / "reports"
    reports = list(reports_dir.rglob("*.json")) if reports_dir.exists() else []
    report_path = str(reports[0]) if reports else None

    return PipelineResult(
        job_id=job_id,
        status="completed",
        output_dir=str(job_output_dir),
        report_path=report_path,
        shorts=shorts,
        request=asdict(req),
    )


if __name__ == "__main__":
    request = PipelineRequest(
        input_video="data/input/test.mp4",
        platform="youtube",
        aspect_ratio="9:16",
        segment_mode="fixed_duration",
        clip_duration_seconds=45.0,
        captions=True,
        plan="free",
    )

    result = run_clipforge_pipeline(request)
    print(json.dumps(asdict(result), indent=2, ensure_ascii=False))
