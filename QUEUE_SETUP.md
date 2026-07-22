# ClipForge AI Queue Setup

ClipForge AI now uses Redis + RQ for heavy video jobs. FastAPI accepts the request, saves the job state, and enqueues work. The separate worker process runs the existing pipeline.

## 1. Install Dependencies

```powershell
pip install -r requirements.txt
```

## 2. Start Redis

Docker option:

```powershell
docker run --name clipforge-redis -p 6379:6379 redis:7
```

If the container already exists:

```powershell
docker start clipforge-redis
```

## 3. Start FastAPI

```powershell
python -m uvicorn backend.app.main:app --reload
```

## 4. Start The Worker

Use a second terminal from the project root:

```powershell
python -m backend.app.worker high default low
```

For your current PC, start with one worker process. The existing renderer already limits short workers, FFmpeg workers, and thumbnail AI workers through `config/settings.yaml`.

## Environment Variables

Defaults:

```powershell
$env:REDIS_URL="redis://localhost:6379/0"
$env:RQ_DEFAULT_QUEUE="default"
$env:RQ_JOB_TIMEOUT="7200"
$env:RQ_RESULT_TTL="86400"
$env:RQ_FAILURE_TTL="604800"
$env:RQ_MAX_RETRIES="2"
```

## Health Check

Open:

```text
http://127.0.0.1:8000/queue/health
```

If Redis is unavailable, new submissions return HTTP 503 instead of running heavy work inside FastAPI.

## Expected Flow

1. Frontend submits upload, local video, batch upload, or pasted link.
2. FastAPI creates the same job record as before.
3. FastAPI enqueues the job in Redis/RQ.
4. Worker runs the existing `run_clipforge_pipeline`.
5. Worker writes progress/results into `data/job_registry.json`.
6. Frontend keeps polling `/jobs/{job_id}` and opens `/jobs/{job_id}/result` when complete.

## Retry Behavior

RQ retries failed jobs up to `RQ_MAX_RETRIES` times with delays of 30 seconds and 120 seconds. A failed attempt writes a safe frontend error and a full traceback under `data/job_errors`.
