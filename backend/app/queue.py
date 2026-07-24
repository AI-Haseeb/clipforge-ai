from __future__ import annotations  # allows modern type hints to work safely

import os  # reads environment variables
from functools import lru_cache  # caches repeated function results
from typing import Any, Optional  # provides flexible type hints

try:
    from redis import Redis  # connects Python code to Redis
    from rq import Queue, Retry  # creates job queues and retry rules
    from rq.job import Job  # reads saved queue job records
except Exception as exc:  # keeps FastAPI importable before queue deps are installed
    Redis = None
    Queue = None
    Retry = None
    Job = None
    QUEUE_IMPORT_ERROR = exc
else:
    QUEUE_IMPORT_ERROR = None


ACTIVE_QUEUE_STATUSES = {"queued", "started", "deferred", "scheduled"}


def redis_url() -> str:  # returns the Redis connection URL
    return os.getenv("REDIS_URL", "redis://localhost:6379/0")


def default_queue_name() -> str:  # returns the default RQ queue name
    return os.getenv("RQ_DEFAULT_QUEUE", "default")


def _env_int(name: str, default: int) -> int:  # reads an integer setting from environment variables
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def rq_job_timeout() -> int:  # returns the maximum runtime for one queued job
    return _env_int("RQ_JOB_TIMEOUT", 7200)


def rq_result_ttl() -> int:  # returns how long successful queue results stay saved
    return _env_int("RQ_RESULT_TTL", 86400)


def rq_failure_ttl() -> int:  # returns how long failed queue results stay saved
    return _env_int("RQ_FAILURE_TTL", 604800)


def rq_max_retries() -> int:  # returns how many times a failed job can retry
    return _env_int("RQ_MAX_RETRIES", 2)


@lru_cache(maxsize=1)
def get_redis_connection():  # creates or returns the Redis connection
    if QUEUE_IMPORT_ERROR:
        raise RuntimeError(f"Redis/RQ packages are not installed: {QUEUE_IMPORT_ERROR}")
    return Redis.from_url(redis_url())


@lru_cache(maxsize=8)
def get_queue(name: Optional[str] = None):  # returns an RQ queue object
    queue_name = name or default_queue_name()
    return Queue(queue_name, connection=get_redis_connection(), default_timeout=rq_job_timeout())


def rq_job_key(job_id: str) -> str:  # creates a stable RQ job key from a ClipForge job id
    return f"clipforge:{job_id}"


def redis_health() -> dict[str, Any]:  # checks whether Redis and RQ are ready
    if QUEUE_IMPORT_ERROR:
        return {
            "redis_connected": False,
            "queue_available": False,
            "redis_url": redis_url(),
            "queue_name": default_queue_name(),
            "error": f"Redis/RQ packages are not installed: {QUEUE_IMPORT_ERROR}",
        }

    try:
        connection = get_redis_connection()
        connection.ping()
        return {
            "redis_connected": True,
            "queue_available": True,
            "redis_url": redis_url(),
            "queue_name": default_queue_name(),
        }
    except Exception as exc:
        return {
            "redis_connected": False,
            "queue_available": False,
            "redis_url": redis_url(),
            "queue_name": default_queue_name(),
            "error": str(exc),
        }


def fetch_rq_job(job_id: str):  # finds a queued job by ClipForge job id
    if QUEUE_IMPORT_ERROR:
        return None
    try:
        return Job.fetch(rq_job_key(job_id), connection=get_redis_connection())
    except Exception:
        return None


def queue_job_info(job_id: str, queue_name: Optional[str] = None) -> dict[str, Any]:  # returns queue status details for a job
    info: dict[str, Any] = {
        "rq_job_id": rq_job_key(job_id),
        "queue_name": queue_name or default_queue_name(),
        "queue_status": "unknown",
        "queue_position": None,
    }
    if QUEUE_IMPORT_ERROR:
        info["queue_status"] = "unavailable"
        info["queue_error"] = f"Redis/RQ packages are not installed: {QUEUE_IMPORT_ERROR}"
        return info

    job = fetch_rq_job(job_id)
    if job:
        try:
            info["queue_status"] = job.get_status(refresh=True)
        except Exception:
            info["queue_status"] = "unknown"
        retries_left = getattr(job, "retries_left", None)
        info["retries_left"] = retries_left
        if isinstance(retries_left, int):
            info["retry_count"] = max(0, rq_max_retries() - retries_left)
        else:
            info["retry_count"] = None
        info["enqueued_at"] = job.enqueued_at.isoformat() if job.enqueued_at else None
        info["started_at"] = job.started_at.isoformat() if job.started_at else None
        info["ended_at"] = job.ended_at.isoformat() if job.ended_at else None

    try:
        queue = get_queue(info["queue_name"])
        queued_ids = queue.job_ids
        key = rq_job_key(job_id)
        if key in queued_ids:
            info["queue_position"] = queued_ids.index(key) + 1
    except Exception:
        pass
    return info


def is_queue_job_active(job_id: str, queue_name: Optional[str] = None) -> bool:  # checks if a job is still waiting or running
    return queue_job_info(job_id, queue_name).get("queue_status") in ACTIVE_QUEUE_STATUSES


def enqueue_clipforge_job(job_id: str, request_payload: dict[str, Any], queue_name: Optional[str] = None, task_name: str = "backend.app.job_tasks.run_clipforge_job", extra_args: Optional[list[Any]] = None) -> dict[str, Any]:  # adds a ClipForge job to Redis/RQ
    health = redis_health()
    if not health.get("queue_available"):
        return {"ok": False, **health}

    try:
        target_queue_name = queue_name or default_queue_name()
        queue = get_queue(target_queue_name)
        existing = fetch_rq_job(job_id)
        if existing:
            try:
                existing_status = existing.get_status(refresh=True)
            except Exception:
                existing_status = "unknown"
            if existing_status in ACTIVE_QUEUE_STATUSES:
                return {"ok": True, "duplicate": True, **queue_job_info(job_id, target_queue_name)}
            try:
                existing.delete()
            except Exception:
                pass

        retry = Retry(max=rq_max_retries(), interval=[30, 120]) if Retry else None
        task_args = [job_id, dict(request_payload)]
        if extra_args:
            task_args.extend(extra_args)
        rq_job = queue.enqueue(
            task_name,
            *task_args,
            job_id=rq_job_key(job_id),
            timeout=rq_job_timeout(),
            result_ttl=rq_result_ttl(),
            failure_ttl=rq_failure_ttl(),
            retry=retry,
        )
        return {
            "ok": True,
            "rq_job_id": rq_job.id,
            "queue_name": target_queue_name,
            "queue_status": rq_job.get_status(refresh=True),
            "queue_position": queue_job_info(job_id, target_queue_name).get("queue_position"),
        }
    except Exception as exc:
        return {
            "ok": False,
            "redis_connected": False,
            "queue_available": False,
            "redis_url": redis_url(),
            "queue_name": queue_name or default_queue_name(),
            "error": str(exc),
        }


