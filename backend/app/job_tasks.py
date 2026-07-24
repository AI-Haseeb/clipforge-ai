from __future__ import annotations  # allows modern type hints to work safely

import json  # reads and writes JSON data
import re  # works with text patterns
import threading  # controls safe work between threads
import time  # works with delays and elapsed time
import traceback  # creates detailed error reports
import uuid  # creates unique IDs
from datetime import datetime  # works with dates and times
from pathlib import Path  # works with file and folder paths
from typing import Any, Optional  # provides flexible type hints

try:
    from rq import get_current_job  # gives access to the currently running queue job
except Exception:
    get_current_job = None

from src.services.pipeline_runner import PipelineRequest, run_clipforge_pipeline  # runs the main ClipForge pipeline


DATA_DIR = Path("data").resolve()
JOB_REGISTRY_PATH = DATA_DIR / "job_registry.json"
ERROR_LOG_DIR = DATA_DIR / "job_errors"
_REGISTRY_LOCK = threading.Lock()

PROCESSING_STAGES = [
    "Upload / Link Submitted",
    "Job Queued",
    "Transcribing Audio",
    "Detecting Highlights",
    "Rendering Shorts",
    "Creating Captions",
    "Generating Thumbnails",
    "Writing Metadata",
    "Building ZIP Package",
    "Complete",
]


def _now_iso() -> str:  # creates a clean timestamp for saved job state
    return datetime.now().isoformat(timespec="seconds")


def _load_registry() -> dict[str, Any]:  # loads all saved job records from disk
    if not JOB_REGISTRY_PATH.exists():
        return {}
    try:
        data = json.loads(JOB_REGISTRY_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_registry(jobs: dict[str, Any]) -> None:  # saves all job records safely to disk
    JOB_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(jobs, indent=2, ensure_ascii=False)
    last_error = None
    with _REGISTRY_LOCK:
        for attempt in range(8):
            temp_path = JOB_REGISTRY_PATH.with_name(f"{JOB_REGISTRY_PATH.stem}.{uuid.uuid4().hex}.tmp")
            try:
                temp_path.write_text(payload, encoding="utf-8")
                temp_path.replace(JOB_REGISTRY_PATH)
                return
            except OSError as exc:
                last_error = exc
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
                time.sleep(0.08 * (attempt + 1))
    if last_error:
        print(f"[WARN] Could not save job registry from worker: {last_error}", flush=True)


def _update_job(job_id: str, updates: dict[str, Any]) -> dict[str, Any]:  # updates one job record with new values
    jobs = _load_registry()
    job = jobs.setdefault(job_id, {})
    job.update(updates)
    _save_registry(jobs)
    return job


def _stage_label(stage: int, fallback: Optional[str] = None) -> str:  # returns the readable name for a progress stage
    if fallback:
        return fallback
    if 1 <= stage <= len(PROCESSING_STAGES):
        return PROCESSING_STAGES[stage - 1]
    return "Processing"


def _set_job_stage(job_id: str, stage: int, label: Optional[str] = None, percent: Optional[float] = None) -> None:  # saves the current progress stage for a job
    updates: dict[str, Any] = {
        "progress_stage": stage,
        "progress_label": _stage_label(stage, label),
        "updated_at": _now_iso(),
    }
    if percent is not None:
        updates["progress_percent"] = max(0.0, min(100.0, float(percent)))
    _update_job(job_id, updates)


def _append_job_event(job_id: str, line: str, stage: Optional[int] = None, percent: Optional[float] = None) -> None:  # adds one progress event to a job
    if not line:
        return
    jobs = _load_registry()
    job = jobs.setdefault(job_id, {})
    events = job.setdefault("progress_events", [])
    event = {
        "message": line[:500],
        "time": _now_iso(),
    }
    if stage is not None:
        event["stage"] = stage
    if percent is not None:
        event["percent"] = max(0.0, min(100.0, float(percent)))
    events.append(event)
    job["progress_events"] = events[-30:]
    job["updated_at"] = _now_iso()
    _save_registry(jobs)


def _parse_log_percent(clean_line: str, stage: Optional[int]) -> Optional[float]:  # finds a progress percentage from a log line
    text = clean_line.lower()
    if stage == 2 and (text.startswith("transcribing:") or text.startswith("translating:")):
        match = re.search(r"(\d+(?:\.\d+)?)\s*/\s*100", clean_line)
        if match:
            raw = float(match.group(1))
            return 20.0 + (raw / 100.0) * 10.0
        match = re.search(r"(\d+(?:\.\d+)?)\s*%", clean_line)
        if match:
            return 20.0 + (float(match.group(1)) / 100.0) * 10.0
    return None


def _detect_stage_from_log(line: str) -> Optional[int]:  # detects the progress stage from a pipeline log line
    text = line.strip().lower()
    if not text:
        return None
    ignored_summary_tokens = (
        "plan:",
        "captions:",
        "input videos:",
        "canvas:",
        "filters:",
        "ffmpeg quality:",
    )
    if any(token in text for token in ignored_summary_tokens):
        return None

    if "audio extracting" in text or "audio: extracting" in text or "whisper transcribing" in text or "whisper: transcribing" in text or text.startswith("transcribing:") or text.startswith("translating:"):
        return 2
    if "language detected" in text or "meta: using source track" in text or "meta: urdu/hindi" in text:
        return 2
    if "highlights selecting segments" in text or "highlights: selecting segments" in text or "segments selected" in text or text.startswith("[semantic-ai]"):
        return 3
    if "start short" in text or "reframe" in text or "direct crop" in text or "applying color filter" in text:
        return 4
    if "building captions track" in text or "burning subtitles" in text or "captions enabled but no segments" in text:
        return 5
    if "thumbnail created" in text or "thumbnail creation failed" in text:
        return 6
    if "romanizing meta" in text or "report saved" in text or text.startswith("[meta-"):
        return 7
    if "completed short" in text:
        return 6
    return None


def _make_job_log_callback(job_id: str):  # creates a logger that sends pipeline updates into job progress
    def on_log(line: str) -> None:  # handles one pipeline log message
        clean_line = line.strip()
        if clean_line.lower().startswith("[progress-stage]"):
            parts = clean_line.split(" ", 2)
            if len(parts) >= 2:
                try:
                    stage = int(parts[1])
                    label = parts[2].strip() if len(parts) > 2 else None
                    _set_job_stage(job_id, stage, label)
                    return
                except ValueError:
                    pass

        stage = _detect_stage_from_log(line)
        percent = _parse_log_percent(clean_line, stage)
        if stage is not None:
            label = "Transcribing Audio" if percent is not None else None
            _set_job_stage(job_id, stage, label=label, percent=percent)
            _append_job_event(job_id, clean_line, stage=stage, percent=percent)
        elif clean_line:
            _append_job_event(job_id, clean_line)

    return on_log


def _write_error_log(job_id: str, error_text: str) -> str:  # writes a detailed error log for a failed job
    ERROR_LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = ERROR_LOG_DIR / f"{job_id}.log"
    path.write_text(error_text, encoding="utf-8")
    return str(path)


def run_clipforge_job(job_id: str, request_payload: dict[str, Any]) -> dict[str, Any]:  # runs one queued ClipForge video job
    rq_job = get_current_job() if get_current_job else None
    worker_name = getattr(rq_job, "worker_name", None) if rq_job else None
    retry_count = None
    if rq_job is not None:
        retry_count = getattr(rq_job, "retries_left", None)

    _update_job(job_id, {
        "status": "processing",
        "queue_status": "started",
        "worker_name": worker_name,
        "retry_count": retry_count,
        "started_at": _now_iso(),
        "progress_failed": False,
        "error": "",
    })
    _set_job_stage(job_id, 2, "Processing started")

    try:
        request = PipelineRequest(**request_payload)
        result = run_clipforge_pipeline(request, on_log=_make_job_log_callback(job_id))
        payload = {
            "status": "completed",
            "queue_status": "finished",
            "finished_at": _now_iso(),
            "progress_failed": False,
            "error": "",
            "result": {
                "job_id": result.job_id,
                "output_dir": result.output_dir,
                "shorts": result.shorts,
                "report_path": result.report_path,
            },
        }
        _update_job(job_id, payload)
        _set_job_stage(job_id, 10, "Complete", percent=100)
        return payload["result"]
    except Exception as exc:
        error_log = _write_error_log(job_id, traceback.format_exc())
        _update_job(job_id, {
            "status": "failed",
            "queue_status": "failed",
            "finished_at": _now_iso(),
            "progress_failed": True,
            "progress_label": "Failed",
            "error": "Pipeline failed. Check backend worker logs for details.",
            "error_detail_log": error_log,
            "error_type": type(exc).__name__,
        })
        raise


def _copy_request_for_video(base_request: PipelineRequest, input_video: str, output_base_dir: str) -> PipelineRequest:  # creates a separate request for one batch video
    data = base_request.__dict__.copy()
    data["input_video"] = input_video
    data["output_base_dir"] = output_base_dir
    return PipelineRequest(**data)


def run_clipforge_batch_job(batch_id: str, base_request_payload: dict[str, Any], video_paths: list[str]) -> dict[str, Any]:  # runs a queued batch of videos
    _update_job(batch_id, {
        "status": "processing",
        "queue_status": "started",
        "started_at": _now_iso(),
        "total": len(video_paths),
        "completed": 0,
        "failed": 0,
        "items": [],
        "progress_failed": False,
        "error": "",
    })
    _set_job_stage(batch_id, 2, "Processing batch")

    output_base_dir = str(Path("data/batches") / batch_id / "jobs")
    base_request = PipelineRequest(**base_request_payload)
    items = []
    completed = 0
    failed = 0

    for index, video_path in enumerate(video_paths, start=1):
        item = {
            "index": index,
            "input_video": str(video_path),
            "status": "processing",
        }
        items.append(item)
        _update_job(batch_id, {
            "items": items,
            "current_video": index,
            "completed": completed,
            "failed": failed,
        })
        _set_job_stage(batch_id, 2, f"Processing video {index} of {len(video_paths)}")
        request = _copy_request_for_video(base_request, str(video_path), output_base_dir)

        try:
            result = run_clipforge_pipeline(request, on_log=_make_job_log_callback(batch_id))
            item.update({
                "status": "completed",
                "job_id": result.job_id,
                "output_dir": result.output_dir,
                "shorts": result.shorts,
                "report_path": result.report_path,
            })
            completed += 1
        except Exception as exc:
            item.update({"status": "failed", "error": str(exc)})
            failed += 1
        _update_job(batch_id, {
            "items": items,
            "completed": completed,
            "failed": failed,
        })

    output_dirs = [item.get("output_dir") for item in items if item.get("output_dir")]
    final_payload = {
        "result": {
            "batch_id": batch_id,
            "output_dirs": output_dirs,
            "items": items,
        },
        "finished_at": _now_iso(),
    }

    if output_dirs:
        final_payload.update({
            "status": "completed",
            "queue_status": "finished",
            "progress_failed": False,
            "error": "",
        })
        _update_job(batch_id, final_payload)
        _set_job_stage(batch_id, 10, "Complete", percent=100)
    else:
        final_payload.update({
            "status": "failed",
            "queue_status": "failed",
            "progress_failed": True,
            "error": "All videos failed during batch processing.",
        })
        _update_job(batch_id, final_payload)
        raise RuntimeError("All videos failed during batch processing.")

    return final_payload["result"]


def run_clipforge_link_job(job_id: str, request_payload: dict[str, Any], video_url: str) -> dict[str, Any]:  # downloads a link and runs it as a queued job
    from src.services.video_downloader import download_video_from_url  # downloads videos from supported URLs

    _update_job(job_id, {
        "status": "processing",
        "queue_status": "started",
        "started_at": _now_iso(),
        "progress_failed": False,
        "error": "",
    })
    _set_job_stage(job_id, 1, "Downloading video")
    try:
        downloaded_video = download_video_from_url(video_url)
        request_payload = dict(request_payload)
        request_payload["input_video"] = str(downloaded_video)
        _update_job(job_id, {
            "input_video": str(downloaded_video),
            "request_payload": request_payload,
            "source_url": video_url,
        })
        return run_clipforge_job(job_id, request_payload)
    except Exception as exc:
        error_log = _write_error_log(job_id, traceback.format_exc())
        _update_job(job_id, {
            "status": "failed",
            "queue_status": "failed",
            "finished_at": _now_iso(),
            "progress_failed": True,
            "progress_label": "Failed",
            "error": "Link download or pipeline failed. Check backend worker logs for details.",
            "error_detail_log": error_log,
            "error_type": type(exc).__name__,
        })
        raise

