from pathlib import Path  # provides object-oriented file paths
from typing import Literal, List, Optional  # adds type hint helpers
from datetime import datetime  # works with dates and timestamps
from urllib.parse import urlparse  # validates submitted public web URLs
import math  # validates finite numeric timestamp values
import json  # handles JSON encode and decode
import uuid  # creates unique identifiers
import zipfile  # creates and reads ZIP archives
import threading  # runs and coordinates threads
import time  # measures time, delays, and elapsed seconds
import re  # matches and cleans text with regular expressions
import html  # escapes OAuth callback messages
from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException  # builds Python web APIs
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse, HTMLResponse  # builds Python web APIs
from src.services.pipeline_runner import PipelineRequest, run_clipforge_pipeline  # project pipeline runner
from src.services.music_engine import pick_music_track  # project music selector
from src.services.video_downloader import download_video_from_url  # project video downloader
from fastapi.staticfiles import StaticFiles  # builds Python web APIs
from src.services.font_manager import get_available_fonts  # project font manager
from backend.app.queue import enqueue_clipforge_job, is_queue_job_active, queue_job_info, redis_health  # Redis/RQ job queue helpers
from backend.app.auth_store import (  # project auth helpers
    authenticate_user,
    create_session,
    create_user,
    delete_session,
    get_user_by_token,
    init_auth_db,
)
from fastapi.middleware.cors import CORSMiddleware  # builds Python web APIs

app = FastAPI(title="ClipForge AI Online Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/data", StaticFiles(directory="data"), name="data")
init_auth_db()

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
INPUT_DIR = Path("data/input")
INPUT_DIR.mkdir(parents=True, exist_ok=True)
BATCH_DIR = Path("data/batches")
BATCH_DIR.mkdir(parents=True, exist_ok=True)
YOUTUBE_TOKEN_DIR = Path("data/youtube_tokens")
YOUTUBE_TOKEN_DIR.mkdir(parents=True, exist_ok=True)
YOUTUBE_CLIENT_SECRET = Path("config/youtube_client_secret.json")
YOUTUBE_REDIRECT_URI = "http://localhost:8000/youtube/auth/callback"
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_AUTH_STATE = {}

JOBS = {}

DATA_DIR = Path("data").resolve()
JOB_REGISTRY_PATH = DATA_DIR / "job_registry.json"
_JOBS_REGISTRY_LOCK = threading.Lock()

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
def _safe_job_slug(value: str) -> str:  # converts a video name into a filesystem/API safe job slug
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "").strip())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:90] or "clipforge_job"

def _new_single_job_id(video_stem: str) -> str:  # creates a unique job id for each single-video run
    base = _safe_job_slug(video_stem)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:6]
    return f"{base}_{stamp}_{suffix}"

def _resolve_registered_job_id(job_id: str) -> str:  # maps an older filename-based id to the real unique job id
    if job_id in JOBS:
        return job_id

    requested_slug = _safe_job_slug(job_id)
    matches = []
    for registered_id, job in JOBS.items():
        input_video = str(job.get("input_video") or "").strip()
        input_slug = _safe_job_slug(Path(input_video).stem) if input_video else ""
        id_matches = registered_id.startswith(f"{requested_slug}_")
        input_matches = bool(input_slug) and (
            input_slug == requested_slug
            or input_slug.startswith(requested_slug)
            or requested_slug.startswith(input_slug)
        )
        if id_matches or input_matches:
            active_rank = 1 if job.get("status") in {"queued", "processing"} else 0
            updated_at = str(job.get("updated_at") or job.get("started_at") or job.get("created_at") or "")
            matches.append((active_rank, updated_at, registered_id))

    if not matches:
        return job_id

    matches.sort(reverse=True)
    return matches[0][2]

def file_to_public_url(file_path: Path) -> str:  # converts a generated file path into a frontend-accessible URL
    """
    Convert local file path inside data/ into browser-accessible URL.
    Example:
    C:/project/data/jobs/job123/shorts/a.mp4
    -> /data/jobs/job123/shorts/a.mp4
    """
    resolved = file_path.resolve()

    try:
        rel_path = resolved.relative_to(DATA_DIR)
        return "/data/" + rel_path.as_posix()
    except ValueError:
        # File is outside data folder, so do not expose unsafe path
        return ""
def _save_jobs_registry():  # saves generated state or output files
    """Save job registry safely on Windows while the frontend polls often."""
    JOB_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(JOBS, indent=2)
    last_error = None
    with _JOBS_REGISTRY_LOCK:
        for attempt in range(8):
            temp_path = JOB_REGISTRY_PATH.with_name(
                f"{JOB_REGISTRY_PATH.stem}.{uuid.uuid4().hex}.tmp"
            )
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
        print(f"[WARN] Could not save job registry after retries: {last_error}", flush=True)
def _load_jobs_registry():  # loads required data/settings into memory
    if not JOB_REGISTRY_PATH.exists():
        return

    try:
        saved_jobs = json.loads(JOB_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    if isinstance(saved_jobs, dict):
        JOBS.clear()
        JOBS.update(saved_jobs)

def _refresh_jobs_registry():  # reloads worker-written queue progress from disk before status/result reads
    _load_jobs_registry()

def _recover_orphaned_active_jobs():  # marks interrupted legacy active jobs while preserving queued RQ jobs
    changed = False
    for job_id, job in JOBS.items():
        if job.get("status") not in {"queued", "processing"}:
            continue
        if job.get("rq_job_id"):
            info = queue_job_info(job_id, job.get("queue_name"))
            job.update({key: value for key, value in info.items() if value is not None})
            if info.get("queue_status") in {"failed", "stopped", "canceled"}:
                job["status"] = "failed"
                job["progress_failed"] = True
                job["progress_label"] = "Failed"
                job["error"] = "Queued job stopped before completion. Resume this job to enqueue it again."
            changed = True
            continue
        if job.get("status") == "processing":
            job["status"] = "failed"
            job["progress_failed"] = True
            job["progress_label"] = "Interrupted"
            job["error"] = (
                "Backend was stopped before this job finished. "
                "Start the job again, or resume it from the saved input video."
            )
            changed = True
    if changed:
        _save_jobs_registry()
def _request_payload(request: PipelineRequest) -> dict:  # extracts the original request payload from a stored job record
    if hasattr(request, "model_dump"):
        return request.model_dump()
    if hasattr(request, "dict"):
        return request.dict()
    return dict(getattr(request, "__dict__", {}) or {})
def _request_from_job(job: dict) -> Optional[PipelineRequest]:  # rebuilds a pipeline request object from saved job data
    payload = job.get("request_payload") or {}
    if isinstance(payload, dict) and payload.get("input_video"):
        return PipelineRequest(**payload)
    input_video = job.get("input_video")
    if input_video:
        return PipelineRequest(input_video=str(input_video))
    return None
def _is_output_dir_complete(output_dir: Path) -> bool:  # checks whether an output folder already contains finished result files
    if not output_dir.exists():
        return False
    reports = list((output_dir / "reports").glob("*.json"))
    if not reports:
        return False
    try:
        for report in reports:
            shorts = json.loads(report.read_text(encoding="utf-8")).get("shorts", [])
            if not shorts or not all(Path(item).is_file() and Path(item).stat().st_size > 0 for item in shorts):
                return False
        return True
    except (OSError, ValueError, TypeError):
        return False
def _find_latest_output_dir(job_id: str) -> Optional[Path]:  # finds the newest output folder for a job after reload/resume
    jobs_dir = DATA_DIR / "jobs"
    if not jobs_dir.exists():
        return None

    lookup_ids = [job_id]
    safe_job_id = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in job_id)
    if safe_job_id and safe_job_id != job_id:
        lookup_ids.append(safe_job_id)

    candidates = []
    seen = set()
    for lookup_id in lookup_ids:
        exact_dir = jobs_dir / lookup_id
        if exact_dir.is_dir() and exact_dir not in seen:
            candidates.append(exact_dir)
            seen.add(exact_dir)
        for path in jobs_dir.glob(f"{lookup_id}_*"):
            if path.is_dir() and path not in seen:
                candidates.append(path)
                seen.add(path)

    candidates = [path for path in candidates if _is_output_dir_complete(path)]

    if not candidates:
        return None

    return max(candidates, key=lambda path: path.stat().st_mtime)
def _restore_job_from_disk(job_id: str) -> Optional[dict]:  # restores job status from saved request/progress/output files
    output_dir = _find_latest_output_dir(job_id)
    if not output_dir:
        return None

    reports_dir = output_dir / "reports"
    report_files = sorted(reports_dir.rglob("*.json")) if reports_dir.exists() else []
    shorts_dir = output_dir / "shorts"
    shorts = [str(path) for path in sorted(shorts_dir.rglob("*.mp4"))] if shorts_dir.exists() else []

    job = {
        "status": "completed",
        "input_video": "",
        "progress_stage": 10,
        "progress_label": "Complete",
        "progress_failed": False,
        "restored_from_disk": True,
        "result": {
            "job_id": output_dir.name,
            "output_dir": str(output_dir),
            "shorts": shorts,
            "report_path": str(report_files[0]) if report_files else "",
        },
    }
    JOBS[job_id] = job
    _save_jobs_registry()
    return job
def _get_or_restore_job(job_id: str) -> Optional[dict]:  # returns a saved job, or restores completed output from disk when registry state is stale
    _refresh_jobs_registry()
    job = JOBS.get(job_id)
    if not job:
        return _restore_job_from_disk(job_id)
    if job.get("status") not in {"queued", "processing", "completed"} or (job.get("status") == "completed" and not job.get("result")):
        restored = _restore_job_from_disk(job_id)
        if restored:
            return restored
    return job


_load_jobs_registry()
_recover_orphaned_active_jobs()
PlatformOption = Literal["youtube", "instagram", "tiktok"]
AspectRatioOption = Literal["9:16", "16:9", "1:1", "4:5"]
SegmentModeOption = Literal["semantic_ai", "fixed_duration", "manual", "raw_footage"]
OutputResolutionOption = Literal["1080p", "720p", "480p"]

FilterPresetOption = Literal[
    "Natural Enhance (Recommended)",
    "Punchy + Clear",
    "Cool Modern",
    "Warm Cinematic",
    "Black & White (Mono)",
    "None (No Filter)",
]

ReframeOption = Literal["off", "on"]
FontPresetOption = Literal[
    "clean_white",
    "bold_yellow",
    "podcast_blue",
    "gaming_neon",
    "horror_red",
    "meme_big",
    "viral_dynamic",
    "creator_pop",
    "scroll_stopper",
    "soft_glow",
]
CaptionPositionOption = Literal[
    "bottom_center",
    "center",
    "top_center",
]

CaptionSizeOption = Literal[
    "extra_small",
    "small",
    "medium",
    "large",
    "extra_large",
]

FontFamilyOption = Literal[
    "preset",
    "Montserrat",
    "Poppins",
    "Raleway",
    "Anton",
    "Bebas Neue",
    "Oswald",
    "Archivo Black",
    "Luckiest Guy",
    "Fredoka",
]

CaptionCaseOption = Literal[
    "preset",
    "normal",
    "uppercase",
    "lowercase",
]

EditingStyleOption = Literal[
    "none",
    "podcast",
    "educational",
    "tutorial",
    "motivational",
    "romantic",
    "sad",
    "love",
    "business",
    "marketing",
    "gaming",
    "funny",
    "meme",
    "horror",
    "cinematic",
    "documentary",
    "news",
    "lifestyle",
    "fitness",
]
MusicCategoryOption = Literal[
    "none",
    "auto",
    "podcast",
    "educational",
    "tutorial",
    "motivational",
    "romantic",
    "sad",
    "love",
    "business",
    "marketing",
    "gaming",
    "funny",
    "meme",
    "horror",
    "cinematic",
    "documentary",
    "news",
    "lifestyle",
    "fitness",
    "calm",
    "energetic",
]

MUSIC_ROOT = Path("assets/music").resolve()
MUSIC_MEDIA_TYPES = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
}
def _safe_music_category(category: str) -> str:  # sanitizes a music category before using it in a path
    return "".join(ch for ch in (category or "none").lower() if ch.isalnum() or ch in {"_", "-"}) or "none"
def _safe_music_filename(filename: str) -> str:  # sanitizes a music filename before previewing or mixing it
    clean = str(filename or "").replace("\\", "/").strip("/")
    parts = [part for part in clean.split("/") if part]
    if not parts or any(part in {".", ".."} for part in parts):
        return ""
    return "/".join(parts)
def _music_track_path(category: str, filename: str) -> Optional[Path]:  # builds the filesystem path for a selected music track
    safe_category = _safe_music_category(category)
    safe_filename = _safe_music_filename(filename)
    if not safe_filename:
        return None
    category_dir = (MUSIC_ROOT / safe_category).resolve()
    track_path = (category_dir / Path(*safe_filename.split("/"))).resolve()
    try:
        track_path.relative_to(category_dir)
    except ValueError:
        return None
    if not track_path.is_file() or track_path.suffix.lower() not in MUSIC_MEDIA_TYPES:
        return None
    return track_path
def _validated_music_track(category: str, filename: str) -> str:  # validates that a requested music track is safe to pass to the pipeline
    if not filename or _safe_music_category(category) == "none":
        return ""
    clean = str(filename).replace("\\", "/").strip("/")
    parts = [part for part in clean.split("/") if part]
    if not parts or any(part in {".", ".."} for part in parts):
        return ""
    if Path(parts[-1]).suffix.lower() not in MUSIC_MEDIA_TYPES:
        return ""
    # Preserve a safe missing filename so the music engine can report any substitution.
    return "/".join(parts)
def _music_tracks_for_category(category: str) -> List[Path]:  # returns available audio tracks for one music category
    safe_category = _safe_music_category(category)
    category_dir = (MUSIC_ROOT / safe_category).resolve()
    try:
        category_dir.relative_to(MUSIC_ROOT)
    except ValueError:
        return []
    if not category_dir.exists():
        return []
    return sorted(
        [p for p in category_dir.rglob("*") if p.is_file() and p.suffix.lower() in MUSIC_MEDIA_TYPES],
        key=lambda p: p.relative_to(category_dir).as_posix().lower(),
    )


@app.get("/music/tracks/{category}")
def list_music_tracks(category: str):  # returns the backend API response listing music tracks in a category
    safe_category = _safe_music_category(category)
    category_dir = (MUSIC_ROOT / safe_category).resolve()
    tracks = _music_tracks_for_category(safe_category)
    return {
        "category": safe_category,
        "tracks": [
            {
                "name": track.relative_to(category_dir).as_posix(),
                "label": track.relative_to(category_dir).as_posix().replace("/", " / ").replace("_", " ").replace("-", " ").rsplit(".", 1)[0].title(),
                "url": f"/music/preview/{safe_category}/{track.relative_to(category_dir).as_posix()}",
            }
            for track in tracks
        ],
    }


@app.get("/music/preview/{category}/{filename:path}")
def preview_named_music_track(category: str, filename: str):  # streams a specific music preview file from the backend
    track_path = _music_track_path(category, filename)
    if not track_path:
        return JSONResponse({"error": "No preview track found for this category."}, status_code=404)
    return FileResponse(
        track_path,
        media_type=MUSIC_MEDIA_TYPES.get(track_path.suffix.lower(), "application/octet-stream"),
        filename=track_path.name,
    )

@app.get("/music/preview/{category}")
def preview_music_track(category: str):  # streams the first available preview track for a category
    safe_category = _safe_music_category(category)
    track = pick_music_track(safe_category, base_dir="assets/music")
    if not track:
        return JSONResponse({"error": "No preview track found for this category."}, status_code=404)

    track_path = Path(track).resolve()
    try:
        track_path.relative_to(MUSIC_ROOT)
    except ValueError:
        return JSONResponse({"error": "Unsafe music path."}, status_code=400)

    return FileResponse(
        track_path,
        media_type=MUSIC_MEDIA_TYPES.get(track_path.suffix.lower(), "application/octet-stream"),
        filename=track_path.name,
    )
@app.get("/")
def home():  # returns the backend health/home response
    return {"message": "ClipForge AI backend is running"}
def _extract_bearer_token(authorization: Optional[str]) -> str:  # pulls audio, text, frames, or metadata from source media
    if not authorization:
        return ""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return ""
    return token.strip()


@app.post("/auth/signup")
def auth_signup(  # creates a local test user from the signup form payload
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):
    try:
        user = create_user(name, email, password)
        session = create_session(user["id"])
        return {"user": user, **session}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/auth/login")
def auth_login(  # authenticates a local test user and returns a session token
    email: str = Form(...),
    password: str = Form(...),
):
    user = authenticate_user(email, password)
    if not user:
        return JSONResponse({"error": "Invalid email or password."}, status_code=401)
    session = create_session(user["id"])
    return {"user": user, **session}


@app.get("/auth/me")
def auth_me(authorization: Optional[str] = Header(None)):  # returns the current authenticated local test user
    token = _extract_bearer_token(authorization)
    user = get_user_by_token(token)
    if not user:
        return JSONResponse({"error": "Not authenticated."}, status_code=401)
    return {"user": user}


@app.post("/auth/logout")
def auth_logout(authorization: Optional[str] = Header(None)):  # deletes the current local test auth session
    token = _extract_bearer_token(authorization)
    delete_session(token)
    return {"message": "Logged out."}


@app.get("/auth/oauth-status")
def auth_oauth_status():  # reports that production OAuth is not configured yet
    return {
        "google": "Configure Google OAuth client ID/secret on hosting to enable this.",
        "github": "Configure GitHub OAuth client ID/secret on hosting to enable this.",
        "facebook": "Configure Meta/Facebook app credentials on hosting to enable this.",
    }
def _optional_auth_user(authorization: Optional[str]) -> Optional[dict]:  # reads the optional auth token without blocking guest usage
    token = _extract_bearer_token(authorization)
    return get_user_by_token(token) if token else None
def _stage_label(stage: int) -> str:  # maps backend progress stage numbers into readable labels
    if stage >= 10:
        return "Complete"
    if 0 <= stage < len(PROCESSING_STAGES):
        return PROCESSING_STAGES[stage]
    return "Processing"
def _set_job_stage(job_id: str, stage: int, label: Optional[str] = None, percent: Optional[float] = None):  # updates runtime state or UI/backend state
    job = JOBS.get(job_id)
    if not job:
        return
    clean_stage = max(0, min(10, int(stage)))
    job["progress_stage"] = clean_stage
    job["progress_label"] = label or _stage_label(clean_stage)
    stage_percent = max(0.0, min(100.0, float(clean_stage) * 10.0))
    if percent is not None:
        stage_percent = max(stage_percent, max(0.0, min(100.0, float(percent))))
    previous_percent = float(job.get("progress_percent", 0) or 0)
    job["progress_percent"] = round(max(previous_percent, stage_percent), 2)
    _save_jobs_registry()
def _append_job_event(job_id: str, line: str, stage: Optional[int] = None, percent: Optional[float] = None):  # adds a timestamped progress/log event to a job record
    job = JOBS.get(job_id)
    if not job:
        return
    clean = str(line or "").strip()
    if not clean:
        return
    events = job.setdefault("progress_events", [])
    event = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "message": clean,
    }
    if stage is not None:
        event["stage"] = int(stage)
    if percent is not None:
        event["percent"] = round(float(percent), 2)
    events.append(event)
    del events[:-30]
    job["latest_log"] = clean
def _parse_log_percent(line: str, stage: Optional[int]) -> Optional[float]:  # turns raw text/API data into structured values
    text = str(line or "")
    if not text:
        return None
    # tqdm can look like: Transcribing: 90%|...| 90/100 [23:27<03:35, 21.58s/%]
    if "Transcribing" in text or "Translating" in text:
        values = [float(match.group(1)) for match in re.finditer(r"(?:Transcribing|Translating):\s*(\d+(?:\.\d+)?)(?:%|/100)", text, re.IGNORECASE)]
        values.extend(float(match.group(1)) for match in re.finditer(r"(\d+(?:\.\d+)?)/100", text))
        if values:
            local_pct = max(0.0, min(100.0, values[-1]))
            return 20.0 + (local_pct * 0.10) if stage == 2 else local_pct
    return None
def _detect_stage_from_log(line: str) -> Optional[int]:  # finds highlights, faces, language, timing, or visual signals
    text = line.lower().strip()

    # Ignore setup/config summary lines. They mention captions/package, but no work has started yet.
    ignored_summary_tokens = (
        "run summary",
        "clip mode:",
        "meta style:",
        "plan:",
        "captions:",
        "input videos:",
        "canvas:",
        "filters:",
        "ffmpeg quality:",
    )
    if any(token in text for token in ignored_summary_tokens):
        return None

    if "audio extracting" in text or "audio: extracting" in text or "whisper transcribing" in text or "whisper: transcribing" in text or text.startswith("transcribing:"):
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
def _make_job_log_callback(job_id: str):  # creates a callback that stores pipeline log lines on the job
    structured = False
    def on_log(line: str):  # stores one pipeline log line and updates the related job event list
        nonlocal structured
        clean_line = line.strip()
        if clean_line.startswith("[progress-json] "):
            JOBS[job_id].update(json.loads(clean_line[len("[progress-json] "):]))
            structured = True
            _save_jobs_registry()
            return
        if structured:
            return
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
            label = None
            if percent is not None and ("transcribing" in clean_line.lower() or "translating" in clean_line.lower()):
                local_pct = max(0.0, min(100.0, (percent - 20.0) * 10.0 if stage == 2 else percent))
                label = "Transcribing Audio"
            _set_job_stage(job_id, stage, label=label, percent=percent)
            _append_job_event(job_id, clean_line, stage=stage, percent=percent)
        elif clean_line:
            _append_job_event(job_id, clean_line)

    return on_log
def process_job(job_id: str, request: PipelineRequest):  # runs one backend processing job and updates job status until completion
    try:
        JOBS[job_id]["status"] = "processing"
        _set_job_stage(job_id, 2, "Processing started")
        result = run_clipforge_pipeline(request, on_log=_make_job_log_callback(job_id))

        JOBS[job_id]["status"] = "completed"
        _set_job_stage(job_id, 10, "Complete", percent=100)
        JOBS[job_id]["result"] = {
            "job_id": result.job_id,
            "output_dir": result.output_dir,
            "shorts": result.shorts,
            "report_path": result.report_path,
        }
        _save_jobs_registry()

    except Exception as e:
        restored = _restore_job_from_disk(job_id)
        if restored:
            _set_job_stage(job_id, 10, "Complete", percent=100)
            _save_jobs_registry()
            return
        JOBS[job_id]["status"] = "failed"
        JOBS[job_id]["progress_failed"] = True
        JOBS[job_id]["error"] = str(e)
        _save_jobs_registry()
def _new_batch_id() -> str:  # creates a unique ID for a multi-file batch upload
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"batch_{stamp}_{uuid.uuid4().hex[:6]}"
def _copy_request_for_video(base_request: PipelineRequest, input_video: str, output_base_dir: str) -> PipelineRequest:  # copies base request settings for one video in a batch
    data = base_request.__dict__.copy()
    data["input_video"] = input_video
    data["output_base_dir"] = output_base_dir
    return PipelineRequest(**data)
def process_batch_job(batch_id: str, base_request: PipelineRequest, video_paths: List[Path]):  # runs each uploaded batch video through the pipeline job runner
    batch = JOBS[batch_id]
    batch["status"] = "processing"
    _set_job_stage(batch_id, 2, "Processing batch")
    batch["total"] = len(video_paths)
    batch["completed"] = 0
    batch["failed"] = 0
    batch["items"] = []
    _save_jobs_registry()
    output_base_dir = str(BATCH_DIR / batch_id / "jobs")

    for index, video_path in enumerate(video_paths, start=1):
        item = {
            "index": index,
            "input_video": str(video_path),
            "status": "processing",
        }
        batch["items"].append(item)
        request = _copy_request_for_video(base_request, str(video_path), output_base_dir)

        try:
            batch["current_video"] = index
            _set_job_stage(batch_id, 2, f"Processing video {index} of {len(video_paths)}")
            result = run_clipforge_pipeline(request, on_log=_make_job_log_callback(batch_id))
            item.update({
                "status": "completed",
                "job_id": result.job_id,
                "output_dir": result.output_dir,
                "shorts": result.shorts,
                "report_path": result.report_path,
            })
            batch["completed"] += 1
            _save_jobs_registry()
        except Exception as e:
            item.update({"status": "failed", "error": str(e)})
            batch["failed"] += 1
            _save_jobs_registry()

    output_dirs = [item.get("output_dir") for item in batch["items"] if item.get("output_dir")]
    batch["result"] = {
        "batch_id": batch_id,
        "output_dirs": output_dirs,
        "items": batch["items"],
    }

    if output_dirs:
        batch["status"] = "completed"
        _set_job_stage(batch_id, 10, "Complete")
    else:
        batch["status"] = "failed"
        batch["progress_failed"] = True
        batch["error"] = "All videos failed during batch processing."
    _save_jobs_registry()

def _queue_unavailable_response(job_id: str, queue_result: dict) -> JSONResponse:  # returns a clear queue setup error instead of running heavy work inside FastAPI
    error = queue_result.get("error") or "Redis/RQ queue is unavailable. Start Redis and the ClipForge worker, then try again."
    if job_id in JOBS:
        JOBS[job_id].update({
            "status": "failed",
            "queue_status": "unavailable",
            "progress_failed": True,
            "progress_label": "Queue unavailable",
            "error": error,
        })
        _save_jobs_registry()
    return JSONResponse(
        {
            "error": "Queue unavailable",
            "details": error,
            "job_id": job_id,
            "redis_url": queue_result.get("redis_url"),
            "queue_name": queue_result.get("queue_name"),
        },
        status_code=503,
    )

def _enqueue_saved_job(job_id: str, request: PipelineRequest, message: str):  # sends a saved single-video job to Redis/RQ while preserving API response shape
    request_payload = _request_payload(request)
    queue_result = enqueue_clipforge_job(job_id, request_payload)
    if not queue_result.get("ok"):
        JOBS[job_id].update({
            "status": "queued",
            "queue_status": "local_thread",
            "queue_name": "local",
            "queue_position": None,
            "progress_stage": 1,
            "progress_label": "Processing locally",
            "progress_failed": False,
            "request_payload": request_payload,
            "queue_fallback_reason": queue_result.get("error") or "Redis/RQ queue unavailable",
        })
        _save_jobs_registry()
        _start_local_pipeline_job(job_id, request_payload)
        return {
            "message": f"{message} Running locally because Redis queue is unavailable.",
            "job_id": job_id,
            "status_url": f"/jobs/{job_id}",
            "queue_status": JOBS[job_id].get("queue_status"),
            "queue_position": None,
        }
    JOBS[job_id].update({
        "status": "queued",
        "queue_status": queue_result.get("queue_status", "queued"),
        "queue_name": queue_result.get("queue_name"),
        "queue_position": queue_result.get("queue_position"),
        "rq_job_id": queue_result.get("rq_job_id"),
        "progress_stage": 1,
        "progress_label": "Job Queued",
        "progress_failed": False,
        "request_payload": request_payload,
    })
    _save_jobs_registry()
    return {
        "message": message,
        "job_id": job_id,
        "status_url": f"/jobs/{job_id}",
        "queue_status": JOBS[job_id].get("queue_status"),
        "queue_position": JOBS[job_id].get("queue_position"),
    }

def _start_local_pipeline_job(job_id: str, request_payload: dict) -> None:  # starts an upload/local-input job in a local background thread when Redis is unavailable
    def _runner() -> None:
        try:
            from backend.app.job_tasks import run_clipforge_job  # runs the same single-video task used by the RQ worker

            run_clipforge_job(job_id, request_payload)
        except Exception as exc:
            _refresh_jobs_registry()
            if job_id in JOBS:
                JOBS[job_id].update({
                    "status": "failed",
                    "queue_status": "local_failed",
                    "progress_failed": True,
                    "progress_label": "Failed",
                    "error": f"Local processing job failed: {exc}",
                })
                _save_jobs_registry()

    thread = threading.Thread(target=_runner, name=f"clipforge-local-{job_id[:24]}", daemon=True)
    thread.start()


def _start_local_link_job(job_id: str, request_payload: dict, video_url: str) -> None:  # starts a pasted-link job in a local background thread when Redis is unavailable
    def _runner() -> None:
        try:
            from backend.app.job_tasks import run_clipforge_link_job  # runs the same link task used by the RQ worker

            run_clipforge_link_job(job_id, request_payload, video_url)
        except Exception as exc:
            _refresh_jobs_registry()
            if job_id in JOBS:
                JOBS[job_id].update({
                    "status": "failed",
                    "queue_status": "local_failed",
                    "progress_failed": True,
                    "progress_label": "Failed",
                    "error": f"Local link job failed: {exc}",
                })
                _save_jobs_registry()

    thread = threading.Thread(target=_runner, name=f"clipforge-link-{job_id[:24]}", daemon=True)
    thread.start()


def _start_local_batch_job(batch_id: str, request_payload: dict, video_paths: List[Path]) -> None:  # starts a batch upload job locally when Redis is unavailable
    def _runner() -> None:
        try:
            from backend.app.job_tasks import run_clipforge_batch_job  # runs the same batch task used by the RQ worker

            run_clipforge_batch_job(batch_id, request_payload, [str(path) for path in video_paths])
        except Exception as exc:
            _refresh_jobs_registry()
            if batch_id in JOBS:
                JOBS[batch_id].update({
                    "status": "failed",
                    "queue_status": "local_failed",
                    "progress_failed": True,
                    "progress_label": "Failed",
                    "error": f"Local batch job failed: {exc}",
                })
                _save_jobs_registry()

    thread = threading.Thread(target=_runner, name=f"clipforge-batch-{batch_id[:24]}", daemon=True)
    thread.start()


def _enqueue_saved_batch_job(batch_id: str, base_request: PipelineRequest, video_paths: List[Path], message: str):  # sends a saved batch job to Redis/RQ while preserving API response shape
    request_payload = _request_payload(base_request)
    queue_result = enqueue_clipforge_job(
        batch_id,
        request_payload,
        task_name="backend.app.job_tasks.run_clipforge_batch_job",
        extra_args=[[str(path) for path in video_paths]],
    )
    if not queue_result.get("ok"):
        JOBS[batch_id].update({
            "status": "queued",
            "queue_status": "local_thread",
            "queue_name": "local",
            "queue_position": None,
            "progress_stage": 1,
            "progress_label": "Processing locally",
            "progress_failed": False,
            "request_payload": request_payload,
            "queue_fallback_reason": queue_result.get("error") or "Redis/RQ queue unavailable",
        })
        _save_jobs_registry()
        _start_local_batch_job(batch_id, request_payload, video_paths)
        return {
            "message": f"{message} Running locally because Redis queue is unavailable.",
            "job_id": batch_id,
            "batch_id": batch_id,
            "type": "batch",
            "total": len(video_paths),
            "status_url": f"/jobs/{batch_id}",
            "queue_status": JOBS[batch_id].get("queue_status"),
            "queue_position": None,
        }
    JOBS[batch_id].update({
        "status": "queued",
        "queue_status": queue_result.get("queue_status", "queued"),
        "queue_name": queue_result.get("queue_name"),
        "queue_position": queue_result.get("queue_position"),
        "rq_job_id": queue_result.get("rq_job_id"),
        "progress_stage": 1,
        "progress_label": "Job Queued",
        "progress_failed": False,
        "request_payload": request_payload,
    })
    _save_jobs_registry()
    return {
        "message": message,
        "job_id": batch_id,
        "batch_id": batch_id,
        "type": "batch",
        "total": len(video_paths),
        "status_url": f"/jobs/{batch_id}",
        "queue_status": JOBS[batch_id].get("queue_status"),
        "queue_position": JOBS[batch_id].get("queue_position"),
    }
VIDEO_INPUT_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mpeg", ".mpg", ".ogv"}
UPLOAD_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v"}

def _parse_manual_time(value: str) -> float:  # parses seconds, MM:SS, or HH:MM:SS timestamps
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("timestamp is empty")
    parts = raw.split(":")
    if len(parts) == 1:
        seconds = float(parts[0])
    elif len(parts) == 2:
        seconds = float(parts[0]) * 60 + float(parts[1])
    elif len(parts) == 3:
        seconds = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    else:
        raise ValueError("timestamp must be seconds, MM:SS, or HH:MM:SS")
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("timestamp must be a finite non-negative number")
    return seconds

def _validate_manual_ranges(segment_mode: str, manual_ranges: str) -> str:  # rejects malformed manual clip ranges before job creation
    clean = str(manual_ranges or "").strip()
    if segment_mode != "manual":
        return clean
    raw_ranges = [item.strip() for item in re.split(r"[;,]", clean) if item.strip()]
    if not raw_ranges:
        raise HTTPException(status_code=422, detail="Manual mode requires at least one start-end range.")
    for index, raw_range in enumerate(raw_ranges, start=1):
        if "-" not in raw_range:
            raise HTTPException(status_code=422, detail=f"Manual range {index} must use start-end format.")
        start_raw, end_raw = [part.strip() for part in raw_range.split("-", 1)]
        try:
            start_time = _parse_manual_time(start_raw)
            end_time = _parse_manual_time(end_raw)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"Manual range {index} is invalid: {exc}.") from exc
        if end_time <= start_time:
            raise HTTPException(status_code=422, detail=f"Manual range {index} must have end_time greater than start_time.")
    return ";".join(raw_ranges)

def _validate_public_url(value: str) -> str:  # rejects empty or malformed public links before yt-dlp runs
    clean = str(value or "").strip()
    parsed = urlparse(clean)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or any(char.isspace() for char in clean):
        raise HTTPException(status_code=400, detail="Enter a valid public URL starting with http:// or https://.")
    return clean

def _validate_uploaded_video(upload: UploadFile) -> None:  # allows only supported video filename extensions
    filename = str(upload.filename or "").strip()
    if not filename or Path(filename).suffix.lower() not in UPLOAD_VIDEO_EXTS:
        allowed = ", ".join(sorted(UPLOAD_VIDEO_EXTS))
        raise HTTPException(status_code=400, detail=f"Unsupported upload type. Allowed video extensions: {allowed}.")
def _safe_input_relative_path(value: str) -> str:  # validates a project input-library relative path
    clean = str(value or "").replace("\\", "/").strip("/")
    parts = [part for part in clean.split("/") if part]
    if not parts or any(part in {".", ".."} for part in parts):
        return ""
    return "/".join(parts)
def _resolve_input_video(relative_path: str) -> Optional[Path]:  # converts settings/input into a concrete path or option
    safe_path = _safe_input_relative_path(relative_path)
    if not safe_path:
        return None
    root = INPUT_DIR.resolve()
    candidate = (root / Path(*safe_path.split("/"))).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if not candidate.is_file() or candidate.suffix.lower() not in VIDEO_INPUT_EXTS:
        return None
    return candidate


@app.get("/input-library")
def list_input_library():  # returns videos found in the local input library folder
    root = INPUT_DIR.resolve()
    videos = []
    if root.exists():
        for file in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix().lower()):
            if file.is_file() and file.suffix.lower() in VIDEO_INPUT_EXTS:
                rel = file.relative_to(root).as_posix()
                videos.append({
                    "name": file.name,
                    "relative_path": rel,
                    "folder": str(Path(rel).parent).replace("\\", "/") if str(Path(rel).parent) != "." else "data/input",
                    "url": "/data/input/" + rel,
                    "size_bytes": file.stat().st_size,
                })
    return {"root": str(root), "videos": videos}

@app.post("/process-local-input")
async def process_local_input(  # starts a job from a selected local input-library video
    local_input_path: str = Form(...),

    platform: PlatformOption = Form("youtube"),
    aspect_ratio: AspectRatioOption = Form("9:16"),
    segment_mode: SegmentModeOption = Form("semantic_ai"),
    clip_duration_seconds: float = Form(45.0),
    output_resolution: OutputResolutionOption = Form("1080p"),
    manual_ranges: str = Form(""),
    captions: bool = Form(True),
    filter_preset: FilterPresetOption = Form("Natural Enhance (Recommended)"),
    reframe: ReframeOption = Form("off"),
    font_preset: FontPresetOption = Form("clean_white"),
    caption_position: CaptionPositionOption = Form("bottom_center"),
    caption_size: CaptionSizeOption = Form("medium"),
    font_family: FontFamilyOption = Form("preset"),
    caption_case: CaptionCaseOption = Form("preset"),
    editing_style: EditingStyleOption = Form("none"),
    music_enabled: bool = Form(False),
    music_category: MusicCategoryOption = Form("none"),
    music_volume: float = Form(0.20),
    music_track: str = Form(""),
):
    manual_ranges = _validate_manual_ranges(segment_mode, manual_ranges)
    input_path = _resolve_input_video(local_input_path)
    if not input_path:
        return JSONResponse(
            {"error": "Selected project input video was not found in this app's data/input folder."},
            status_code=400,
        )

    request = PipelineRequest(
        input_video=str(input_path),
        platform=platform,
        aspect_ratio=aspect_ratio,
        segment_mode=segment_mode,
        clip_duration_seconds=clip_duration_seconds,
        output_resolution=output_resolution,
        manual_ranges=manual_ranges or None,
        captions=captions,
        filter_preset=filter_preset,
        reframe=reframe,
        font_preset=font_preset,
        caption_position=caption_position,
        caption_size=caption_size,
        font_family=font_family,
        caption_case=caption_case,
        editing_style=editing_style,
        music_enabled=music_enabled,
        music_category=music_category,
        music_volume=music_volume,
        music_track=_validated_music_track(music_category, music_track),
    )

    temp_job_id = _new_single_job_id(input_path.stem)
    JOBS[temp_job_id] = {
        "status": "queued",
        "input_video": str(input_path),
        "source": "project_input",
        "progress_stage": 1,
        "progress_label": "Job Queued",
        "progress_failed": False,
        "request_payload": _request_payload(request),
    }
    _save_jobs_registry()
    return _enqueue_saved_job(temp_job_id, request, "Project input video selected. Job queued.")

@app.post("/process-upload")
async def process_upload(  # accepts one uploaded video and starts its pipeline job
    video: UploadFile = File(...),

    platform: PlatformOption = Form("youtube"),
    aspect_ratio: AspectRatioOption = Form("9:16"),

    segment_mode: SegmentModeOption = Form(
        "semantic_ai",
        description="semantic_ai = AI finds best moments, fixed_duration = equal length clips, manual = custom time ranges, raw_footage = speech/silence based clips for unedited recordings."
    ),

    clip_duration_seconds: float = Form(
        45.0,
        description="Used only for fixed_duration mode. Examples: 45 = 45 sec, 60 = 1 min, 90 = 1 min 30 sec, 120 = 2 min."
    ),

    output_resolution: OutputResolutionOption = Form(
        "1080p",
        description="Output video quality/resolution: 1080p, 720p, or 480p."
    ),

    manual_ranges: str = Form(
        "",
        description="Used only for manual mode. Format: 00:10-00:45;01:20-02:00 or 10-45;80-120."
    ),

    captions: bool = Form(True),
    filter_preset: FilterPresetOption = Form("Natural Enhance (Recommended)"),
    reframe: ReframeOption = Form("off"),
    font_preset: FontPresetOption = Form(
    "clean_white",
    description="Caption font preset: clean_white, bold_yellow, podcast_blue, gaming_neon, horror_red, meme_big, viral_dynamic, creator_pop, scroll_stopper, soft_glow."),

    caption_position: CaptionPositionOption = Form(
        "bottom_center",
        description="Caption position: bottom_center, center, top_center."
    ),
    caption_size: CaptionSizeOption = Form(
        "medium",
        description="Caption size: extra_small, small, medium, large, extra_large."
    ),
    font_family: FontFamilyOption = Form(
        "preset",
        description="Caption font family."
    ),
    caption_case: CaptionCaseOption = Form(
        "preset",
        description="Caption letter case: preset, normal, uppercase, lowercase."
    ),
    editing_style: EditingStyleOption = Form(
        "none",
        description="Editing style preset."
    ),
    music_enabled: bool = Form(
        False,
        description="Enable or disable background music."
    ),
    music_category: MusicCategoryOption = Form(
        "none",
        description="Background music category."
    ),
    music_volume: float = Form(
        0.20,
        description="Background music volume. Example: 0.20 = 20 percent."
    ),
    music_track: str = Form(
        "",
        description="Optional preferred background music filename from the selected category."
    ),


):
    _validate_uploaded_video(video)
    manual_ranges = _validate_manual_ranges(segment_mode, manual_ranges)
    input_path = UPLOAD_DIR / Path(video.filename or "video.mp4").name

    with input_path.open("wb") as f:
        f.write(await video.read())

    request = PipelineRequest(
        input_video=str(input_path),
        platform=platform,
        aspect_ratio=aspect_ratio,
        segment_mode=segment_mode,
        clip_duration_seconds=clip_duration_seconds,
        output_resolution=output_resolution,
        manual_ranges=manual_ranges or None,
        captions=captions,
        filter_preset=filter_preset,
        reframe=reframe,
        font_preset=font_preset,
        caption_position=caption_position,
        caption_size=caption_size,
        font_family=font_family,
        caption_case=caption_case,
        editing_style=editing_style,
        music_enabled=music_enabled,
        music_category=music_category,
        music_volume=music_volume,
        music_track=_validated_music_track(music_category, music_track),

    )

    temp_job_id = _new_single_job_id(input_path.stem)

    JOBS[temp_job_id] = {
        "status": "queued",
        "input_video": str(input_path),
        "progress_stage": 1,
        "progress_label": "Job Queued",
        "progress_failed": False,
        "request_payload": _request_payload(request),
    }

    _save_jobs_registry()
    return _enqueue_saved_job(temp_job_id, request, "Video uploaded successfully. Job queued.")



@app.post("/process-batch-upload")
async def process_batch_upload(  # accepts multiple uploaded videos and starts a batch job
    videos: List[UploadFile] = File(...),

    platform: PlatformOption = Form("youtube"),
    aspect_ratio: AspectRatioOption = Form("9:16"),
    segment_mode: SegmentModeOption = Form("semantic_ai"),
    clip_duration_seconds: float = Form(45.0),
    output_resolution: OutputResolutionOption = Form("1080p"),
    manual_ranges: str = Form(""),
    captions: bool = Form(True),
    filter_preset: FilterPresetOption = Form("Natural Enhance (Recommended)"),
    reframe: ReframeOption = Form("off"),
    font_preset: FontPresetOption = Form("clean_white"),
    caption_position: CaptionPositionOption = Form("bottom_center"),
    caption_size: CaptionSizeOption = Form("medium"),
    font_family: FontFamilyOption = Form("preset"),
    caption_case: CaptionCaseOption = Form("preset"),
    editing_style: EditingStyleOption = Form("none"),
    music_enabled: bool = Form(False),
    music_category: MusicCategoryOption = Form("none"),
    music_volume: float = Form(0.20),
    music_track: str = Form(""),
):
    if not videos:
        return JSONResponse({"error": "No videos uploaded"}, status_code=400)

    manual_ranges = _validate_manual_ranges(segment_mode, manual_ranges)
    for video in videos:
        _validate_uploaded_video(video)

    batch_id = _new_batch_id()
    upload_dir = BATCH_DIR / batch_id / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: List[Path] = []
    for index, video in enumerate(videos, start=1):
        safe_name = Path(video.filename or f"video_{index}.mp4").name
        target = upload_dir / f"{index:02d}_{safe_name}"
        with target.open("wb") as f:
            f.write(await video.read())
        saved_paths.append(target)

    base_request = PipelineRequest(
        input_video=str(saved_paths[0]),
        platform=platform,
        aspect_ratio=aspect_ratio,
        segment_mode=segment_mode,
        clip_duration_seconds=clip_duration_seconds,
        output_resolution=output_resolution,
        manual_ranges=manual_ranges or None,
        captions=captions,
        filter_preset=filter_preset,
        reframe=reframe,
        font_preset=font_preset,
        caption_position=caption_position,
        caption_size=caption_size,
        font_family=font_family,
        caption_case=caption_case,
        editing_style=editing_style,
        music_enabled=music_enabled,
        music_category=music_category,
        music_volume=music_volume,
        music_track=_validated_music_track(music_category, music_track),
    )

    JOBS[batch_id] = {
        "status": "queued",
        "type": "batch",
        "batch_id": batch_id,
        "total": len(saved_paths),
        "completed": 0,
        "uploads": [str(p) for p in saved_paths],
        "progress_stage": 1,
        "progress_label": "Job Queued",
        "progress_failed": False,
        "request_payload": _request_payload(base_request),
    }

    _save_jobs_registry()
    return _enqueue_saved_batch_job(batch_id, base_request, saved_paths, "Videos uploaded successfully. Batch job queued.")


@app.post("/process-link")
async def process_link(  # downloads a pasted link and starts a pipeline job from it
    video_url: str = Form(...),

    platform: PlatformOption = Form("youtube"),
    aspect_ratio: AspectRatioOption = Form("9:16"),

    segment_mode: SegmentModeOption = Form(
        "semantic_ai",
        description="semantic_ai = AI finds best moments, fixed_duration = equal length clips, manual = custom time ranges."
    ),

    clip_duration_seconds: float = Form(
        45.0,
        description="Used only for fixed_duration mode. Examples: 45 = 45 sec, 60 = 1 min, 90 = 1 min 30 sec, 120 = 2 min."
    ),

    output_resolution: OutputResolutionOption = Form(
        "1080p",
        description="Output video quality/resolution: 1080p, 720p, or 480p."
    ),

    manual_ranges: str = Form(
        "",
        description="Used only for manual mode. Format: 00:10-00:45;01:20-02:00 or 10-45;80-120."
    ),

    captions: bool = Form(True),
    filter_preset: FilterPresetOption = Form("Natural Enhance (Recommended)"),
    reframe: ReframeOption = Form("off"),
    font_preset: FontPresetOption = Form(
    "clean_white",
    description="Caption font preset: clean_white, bold_yellow, podcast_blue, gaming_neon, horror_red, meme_big, viral_dynamic, creator_pop, scroll_stopper, soft_glow."),
    caption_position: CaptionPositionOption = Form(
        "bottom_center",
        description="Caption position: bottom_center, center, top_center."
    ),
    caption_size: CaptionSizeOption = Form(
        "medium",
        description="Caption size: extra_small, small, medium, large, extra_large."
    ),
    font_family: FontFamilyOption = Form(
        "preset",
        description="Caption font family."
    ),
    caption_case: CaptionCaseOption = Form(
        "preset",
        description="Caption letter case: preset, normal, uppercase, lowercase."
    ),
    editing_style: EditingStyleOption = Form(
        "none",
        description="Editing style preset."
    ),   
    music_enabled: bool = Form(
        False,
        description="Enable or disable background music."
    ),
    music_category: MusicCategoryOption = Form(
        "none",
        description="Background music category."
    ),
    music_volume: float = Form(
        0.20,
        description="Background music volume. Example: 0.20 = 20 percent."
    ),
    music_track: str = Form(
        "",
        description="Optional preferred background music filename from the selected category."
    ),

):
    video_url = _validate_public_url(video_url)
    manual_ranges = _validate_manual_ranges(segment_mode, manual_ranges)
    request = PipelineRequest(
        input_video="",
        platform=platform,
        aspect_ratio=aspect_ratio,
        segment_mode=segment_mode,
        clip_duration_seconds=clip_duration_seconds,
        output_resolution=output_resolution,
        manual_ranges=manual_ranges or None,
        captions=captions,
        filter_preset=filter_preset,
        reframe=reframe,
        font_preset=font_preset,
        caption_position=caption_position,
        caption_size=caption_size,
        font_family=font_family,
        caption_case=caption_case,
        editing_style=editing_style,
        music_enabled=music_enabled,
        music_category=music_category,
        music_volume=music_volume,
        music_track=_validated_music_track(music_category, music_track),
    )

    temp_job_id = _new_single_job_id("linked_video")

    JOBS[temp_job_id] = {
        "status": "queued",
        "input_video": "",
        "source_url": video_url,
        "progress_stage": 1,
        "progress_label": "Job Queued",
        "progress_failed": False,
        "request_payload": _request_payload(request),
    }

    request_payload = _request_payload(request)
    _save_jobs_registry()
    queue_result = enqueue_clipforge_job(
        temp_job_id,
        request_payload,
        task_name="backend.app.job_tasks.run_clipforge_link_job",
        extra_args=[video_url],
    )
    if not queue_result.get("ok"):
        JOBS[temp_job_id].update({
            "status": "queued",
            "queue_status": "local_thread",
            "queue_name": "local",
            "queue_position": None,
            "progress_stage": 1,
            "progress_label": "Downloading video",
            "progress_failed": False,
            "queue_fallback_reason": queue_result.get("error") or "Redis/RQ queue unavailable",
        })
        _save_jobs_registry()
        _start_local_link_job(temp_job_id, request_payload, video_url)
        return {
            "message": "Video link submitted. Running locally because Redis queue is unavailable.",
            "job_id": temp_job_id,
            "status_url": f"/jobs/{temp_job_id}",
            "queue_status": JOBS[temp_job_id].get("queue_status"),
            "queue_position": None,
        }
    JOBS[temp_job_id].update({
        "status": "queued",
        "queue_status": queue_result.get("queue_status", "queued"),
        "queue_name": queue_result.get("queue_name"),
        "queue_position": queue_result.get("queue_position"),
        "rq_job_id": queue_result.get("rq_job_id"),
    })
    _save_jobs_registry()
    return {
        "message": "Video link submitted. Job queued.",
        "job_id": temp_job_id,
        "status_url": f"/jobs/{temp_job_id}",
        "queue_status": JOBS[temp_job_id].get("queue_status"),
        "queue_position": JOBS[temp_job_id].get("queue_position"),
    }



@app.post("/jobs/{job_id}/resume")
def resume_job(job_id: str):  # reloads saved job progress/results after page refresh or backend restart
    _refresh_jobs_registry()
    job_id = _resolve_registered_job_id(job_id)
    job = _get_or_restore_job(job_id)
    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)

    if job.get("status") == "completed":
        return {"message": "Job already completed.", "job_id": job_id, "status": "completed", "job": job}

    if job.get("type") == "batch":
        if is_queue_job_active(job_id, job.get("queue_name")):
            return {
                "message": "Batch job is already queued or processing.",
                "job_id": job_id,
                "batch_id": job_id,
                "type": "batch",
                "status": job.get("status", "queued"),
                "queue_status": job.get("queue_status"),
            }
        payload = job.get("request_payload") or {}
        uploads = [Path(path) for path in job.get("uploads", []) if path]
        if not isinstance(payload, dict) or not payload:
            return JSONResponse({"error": "No saved batch settings found for this job."}, status_code=400)
        if not uploads:
            return JSONResponse({"error": "No saved batch input videos found for this job."}, status_code=400)
        missing = [str(path) for path in uploads if not path.exists()]
        if missing:
            return JSONResponse({"error": "Batch input video not found", "missing": missing[:5]}, status_code=404)
        base_request = PipelineRequest(**payload)
        JOBS[job_id].update({
            "status": "queued",
            "progress_stage": 1,
            "progress_label": "Job Queued",
            "progress_failed": False,
            "error": "",
            "request_payload": _request_payload(base_request),
        })
        _save_jobs_registry()
        response = _enqueue_saved_batch_job(job_id, base_request, uploads, "Batch job resumed and queued.")
        if isinstance(response, JSONResponse):
            return response
        response["status"] = "queued"
        return response
    request = _request_from_job(job)
    if not request and job.get("source_url") and isinstance(job.get("request_payload"), dict):
        if is_queue_job_active(job_id, job.get("queue_name")):
            return {"message": "Job is already queued or processing.", "job_id": job_id, "status": job.get("status", "queued"), "queue_status": job.get("queue_status")}
        JOBS[job_id].update({
            "status": "queued",
            "progress_stage": 1,
            "progress_label": "Job Queued",
            "progress_failed": False,
            "error": "",
        })
        _save_jobs_registry()
        queue_result = enqueue_clipforge_job(
            job_id,
            job.get("request_payload", {}),
            task_name="backend.app.job_tasks.run_clipforge_link_job",
            extra_args=[job.get("source_url")],
        )
        if not queue_result.get("ok"):
            return _queue_unavailable_response(job_id, queue_result)
        JOBS[job_id].update({
            "queue_status": queue_result.get("queue_status", "queued"),
            "queue_name": queue_result.get("queue_name"),
            "queue_position": queue_result.get("queue_position"),
            "rq_job_id": queue_result.get("rq_job_id"),
        })
        _save_jobs_registry()
        return {"message": "Link job resumed and queued.", "job_id": job_id, "status": "queued", "queue_status": JOBS[job_id].get("queue_status")}
    if not request:
        return JSONResponse({"error": "No input video saved for this job."}, status_code=400)

    input_path = Path(request.input_video)
    if not input_path.exists():
        return JSONResponse({"error": f"Input video not found: {input_path}"}, status_code=404)

    if is_queue_job_active(job_id, job.get("queue_name")):
        return {"message": "Job is already queued or processing.", "job_id": job_id, "status": job.get("status", "queued"), "queue_status": job.get("queue_status")}

    JOBS[job_id].update({
        "status": "queued",
        "progress_stage": 1,
        "progress_label": "Job Queued",
        "progress_failed": False,
        "error": "",
        "request_payload": _request_payload(request),
    })
    _save_jobs_registry()
    response = _enqueue_saved_job(job_id, request, "Job resumed and queued.")
    if isinstance(response, JSONResponse):
        return response
    response["status"] = "queued"
    return response

@app.get("/jobs/{job_id}")
def get_job_status(job_id: str):  # returns a resolved value used by later code
    _refresh_jobs_registry()
    job_id = _resolve_registered_job_id(job_id)
    job = _get_or_restore_job(job_id)

    if not job:
        return JSONResponse(
            {
                "error": "Job not found",
                "details": "This job was not in memory or the disk registry. If the backend was stopped before completion, start the upload again.",
            },
            status_code=404,
        )

    response = dict(job)
    response["job_id"] = job_id
    if job.get("rq_job_id"):
        response.update(queue_job_info(job_id, job.get("queue_name")))
    return response

@app.get("/queue/health")
def get_queue_health():  # reports Redis/RQ availability for local setup checks
    return redis_health()

def _collect_result_files_from_output_dirs(output_dirs: List[Path]):  # collects shorts, thumbnails, metadata, reports, and ZIP paths for results UI
    shorts = []
    metadata = []
    thumbnails = []

    for output_dir in output_dirs:
        shorts_dir = output_dir / "shorts"
        if shorts_dir.exists():
            for file in sorted(shorts_dir.rglob("*.mp4")):
                url = file_to_public_url(file)
                if url:
                    shorts.append({"name": file.name, "path": str(file), "url": url})

        meta_dir = output_dir / "meta"
        if meta_dir.exists():
            for file in sorted(meta_dir.rglob("*")):
                if file.is_file() and file.suffix.lower() in [".txt", ".json", ".md"]:
                    url = file_to_public_url(file)
                    if url:
                        metadata.append({"name": file.name, "path": str(file), "url": url})

        thumb_dir = output_dir / "thumbnails"
        if thumb_dir.exists():
            for file in sorted(thumb_dir.rglob("*")):
                if file.is_file() and file.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
                    url = file_to_public_url(file)
                    if url:
                        thumbnails.append({"name": file.name, "path": str(file), "url": url})

    return shorts, metadata, thumbnails

def _read_result_manifest(report_path: str) -> dict:  # reads the completed pipeline report used by the results dashboard
    if not report_path:
        return {}
    try:
        path = Path(report_path)
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        pass
    return {}

def _youtube_libraries():
    try:
        from google_auth_oauthlib.flow import Flow
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        return Flow, Credentials, build, MediaFileUpload
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="YouTube support is not installed. Run: pip install -r requirements.txt") from exc

def _youtube_token_path():
    return YOUTUBE_TOKEN_DIR / "default.json"

def _youtube_flow(state: Optional[str] = None):
    Flow, _, _, _ = _youtube_libraries()
    if not YOUTUBE_CLIENT_SECRET.is_file():
        raise HTTPException(status_code=400, detail="Add Google OAuth client JSON at config/youtube_client_secret.json first.")
    flow = Flow.from_client_secrets_file(str(YOUTUBE_CLIENT_SECRET), scopes=YOUTUBE_SCOPES, state=state)
    flow.redirect_uri = YOUTUBE_REDIRECT_URI
    return flow

def _parse_youtube_metadata(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    def block(label, next_labels):
        pattern = rf"(?is)^{re.escape(label)}:\s*(.*?)(?=^({'|'.join(re.escape(x) for x in next_labels)}):|\Z)"
        match = re.search(pattern, text, re.MULTILINE)
        return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""
    title = block("TITLE", ["HOOK OPTIONS", "DESCRIPTION", "HASHTAGS"])
    description = block("DESCRIPTION", ["HASHTAGS", "HASHTAGS COMMA", "META", "CLIP RANGE"])
    tags = block("HASHTAGS COMMA", ["META", "CLIP RANGE", "KEYWORDS HIT"])
    return {"title": title or path.stem, "description": description, "tags": [x.strip() for x in tags.split(",") if x.strip()]}

def _youtube_output_dir(job_id: str) -> Path:
    job = _get_or_restore_job(job_id)
    if not job or job.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Job is not completed or was not found.")
    result = job.get("result", {})
    dirs = result.get("output_dirs") if job.get("type") == "batch" else [result.get("output_dir")]
    for raw in dirs or []:
        path = Path(raw or "")
        if path.is_dir(): return path
    raise HTTPException(status_code=404, detail="Generated output folder not found.")

@app.get("/youtube/auth/start")
def youtube_auth_start(job_id: str):
    flow = _youtube_flow()
    state = uuid.uuid4().hex
    YOUTUBE_AUTH_STATE[state] = {"job_id": job_id, "created": time.time()}
    url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent", state=state)
    return {"authorize_url": url}

@app.get("/youtube/auth/callback")
def youtube_auth_callback(code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    if error: return HTMLResponse(f"YouTube authorization cancelled: {html.escape(error)}", status_code=400)
    if not code or state not in YOUTUBE_AUTH_STATE: return HTMLResponse("Invalid or expired YouTube authorization state.", status_code=400)
    flow = _youtube_flow(state)
    flow.fetch_token(code=code)
    _youtube_token_path().write_text(flow.credentials.to_json(), encoding="utf-8")
    YOUTUBE_AUTH_STATE.pop(state, None)
    return HTMLResponse("""<!doctype html><html><body style='font-family:system-ui;padding:32px'><h2>YouTube connected</h2><p>Return to ClipForge to publish your selected shorts.</p><script>if (window.opener) { window.opener.postMessage({type:'clipforge-youtube-connected'}, '*'); setTimeout(() => window.close(), 700); }</script></body></html>""")

@app.get("/youtube/auth/status")
def youtube_auth_status():
    return {"connected": _youtube_token_path().is_file()}

@app.post("/youtube/publish")
def youtube_publish(payload: dict):
    _, Credentials, build, MediaFileUpload = _youtube_libraries()
    token_path = _youtube_token_path()
    if not token_path.is_file(): raise HTTPException(status_code=401, detail="Connect YouTube first.")
    creds = Credentials.from_authorized_user_file(str(token_path), YOUTUBE_SCOPES)
    if not creds.valid and creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        creds.refresh(Request()); token_path.write_text(creds.to_json(), encoding="utf-8")
    if not creds.valid: raise HTTPException(status_code=401, detail="YouTube connection expired. Connect again.")
    output_dir = _youtube_output_dir(str(payload.get("job_id") or ""))
    shorts = list((output_dir / "shorts").rglob("*.mp4")); thumbs = list((output_dir / "thumbnails").rglob("*")); metas = list((output_dir / "meta").rglob("*.txt"))
    selected = payload.get("items") or []
    if not selected: raise HTTPException(status_code=400, detail="Select at least one short.")
    youtube = build("youtube", "v3", credentials=creds)
    visibility = str(payload.get("visibility") or "private")
    mode = str(payload.get("publish_mode") or "now")
    results = []
    for item in selected:
        short_name = Path(str(item.get("short") or "")).name
        short = next((p for p in shorts if p.name == short_name), None)
        if not short: raise HTTPException(status_code=400, detail=f"Short not found: {short_name}")
        stem = short.stem
        meta = next((p for p in metas if p.stem == stem), None)
        data = _parse_youtube_metadata(meta) if meta else {"title": stem, "description": "", "tags": []}
        privacy = "private" if mode == "schedule" else visibility
        status = {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}
        if mode == "schedule": status["publishAt"] = str(payload.get("publish_at") or "")
        response = youtube.videos().insert(part="snippet,status", body={"snippet": {"title": data["title"][:100], "description": data["description"], "tags": data["tags"][:500], "categoryId": "22"}, "status": status}, media_body=MediaFileUpload(str(short), mimetype="video/mp4", resumable=True)).execute()
        variation = int(item.get("thumbnail") or 1)
        short_number = int(re.search(r"(\d+)$", stem).group(1)) if re.search(r"(\d+)$", stem) else 1
        thumb = next((p for p in thumbs if re.fullmatch(rf"thumbnail_0?{short_number}(?:_v{variation if variation > 1 else 1})?\.(?:jpg|jpeg|png)", p.name, re.I)), None)
        thumbnail_applied = False
        if thumb:
            thumb_mime = "image/png" if thumb.suffix.lower() == ".png" else "image/jpeg"
            youtube.thumbnails().set(videoId=response["id"], media_body=MediaFileUpload(str(thumb), mimetype=thumb_mime)).execute()
            thumbnail_applied = True
        results.append({"short": short_name, "video_id": response["id"], "url": f"https://youtu.be/{response['id']}", "thumbnail_applied": thumbnail_applied})
    return {"status": "published", "items": results}


@app.get("/download-job/{job_id}")
def download_job(job_id: str):  # returns the ZIP/download file for a completed job
    job = _get_or_restore_job(job_id)

    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)

    if job.get("status") != "completed":
        return JSONResponse(
            {"error": "Job is not completed yet", "status": job.get("status")},
            status_code=400,
        )

    result = job.get("result", {})

    if job.get("type") == "batch":
        batch_root = BATCH_DIR / job_id
        zip_dir = batch_root / "zip"
        zip_dir.mkdir(parents=True, exist_ok=True)
        zip_path = zip_dir / f"{job_id}_client_output.zip"
        output_dirs = [Path(p) for p in result.get("output_dirs", []) if p]
        if not output_dirs:
            return JSONResponse({"error": "Batch output folders not found"}, status_code=404)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for output_dir in output_dirs:
                if not output_dir.exists():
                    continue
                job_folder = output_dir.name
                for file in output_dir.rglob("*"):
                    if file.is_file() and file.name != f"{job_id}_client_output.zip":
                        zipf.write(file, Path(job_folder) / file.relative_to(output_dir))
        return FileResponse(zip_path, media_type="application/zip", filename=f"{job_id}_client_output.zip")

    output_dir = Path(result.get("output_dir", ""))

    if not output_dir.exists():
        return JSONResponse({"error": "Output folder not found"}, status_code=404)

    zip_dir = output_dir / "zip"
    zip_dir.mkdir(parents=True, exist_ok=True)
    zip_path = zip_dir / f"{job_id}_client_output.zip"

    prepared_zip = zip_dir / "client_output.zip"
    if prepared_zip.is_file():
        return FileResponse(prepared_zip, media_type="application/zip", filename=f"{job_id}_client_output.zip")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        shorts_dir = output_dir / "shorts"
        meta_dir = output_dir / "meta"

        if shorts_dir.exists():
            for file in shorts_dir.rglob("*"):
                if file.is_file():
                    zipf.write(file, file.relative_to(output_dir))

        if meta_dir.exists():
            for file in meta_dir.rglob("*"):
                if file.is_file():
                    zipf.write(file, Path("metadata") / file.relative_to(meta_dir))

        thumb_dir = output_dir / "thumbnails"

        if thumb_dir.exists():
            for file in thumb_dir.rglob("*"):
                if file.is_file():
                    zipf.write(file, Path("thumbnails") / file.relative_to(thumb_dir))

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"{job_id}_client_output.zip",
    )

@app.get("/jobs/{job_id}/result")
def get_job_result(job_id: str):  # returns a resolved value used by later code
    job = _get_or_restore_job(job_id)

    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)

    if job.get("status") != "completed":
        return JSONResponse(
            {
                "error": "Job is not completed yet",
                "status": job.get("status"),
            },
            status_code=400,
        )

    result = job.get("result", {})

    if job.get("type") == "batch":
        output_dirs = [Path(p) for p in result.get("output_dirs", []) if p]
        shorts, metadata, thumbnails = _collect_result_files_from_output_dirs(output_dirs)
        manifests = [_read_result_manifest(item.get("report_path", "")) for item in result.get("items", [])]
        return {
            "job_id": job_id,
            "batch_id": job_id,
            "type": "batch",
            "status": "completed",
            "total": job.get("total", len(output_dirs)),
            "completed": job.get("completed", len(output_dirs)),
            "items": result.get("items", []),
            "output_dirs": [str(p) for p in output_dirs],
            "shorts": shorts,
            "metadata": metadata,
            "thumbnails": thumbnails,
            "manifests": [manifest for manifest in manifests if manifest],
            "download_zip": f"/download-job/{job_id}",
        }

    output_dir = Path(result.get("output_dir", ""))

    if not output_dir.exists():
        return JSONResponse({"error": "Output folder not found"}, status_code=404)

    shorts, metadata, thumbnails = _collect_result_files_from_output_dirs([output_dir])

    manifest = _read_result_manifest(result.get("report_path", ""))
    return {
        "job_id": job_id,
        "pipeline_job_id": result.get("job_id"),
        "status": "completed",
        "output_dir": str(output_dir),
        "shorts": shorts,
        "metadata": metadata,
        "thumbnails": thumbnails,
        "manifest": manifest,
        "download_zip": f"/download-job/{job_id}",
    }

@app.get("/fonts")
def list_fonts():  # returns local caption fonts available to the frontend
    return {
        "fonts": get_available_fonts()
    }
