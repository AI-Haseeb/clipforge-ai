from __future__ import annotations

import sys

from backend.app.queue import default_queue_name, get_queue, get_redis_connection, redis_health


def main() -> int:
    health = redis_health()
    if not health.get("queue_available"):
        print("[clipforge-worker] Redis/RQ queue is unavailable.", flush=True)
        print(f"[clipforge-worker] {health.get('error', 'Unknown queue error')}", flush=True)
        return 1

    try:
        from rq import SimpleWorker
    except Exception as exc:
        print(f"[clipforge-worker] RQ is not installed: {exc}", flush=True)
        return 1

    queue_names = sys.argv[1:] or ["high", default_queue_name(), "low"]
    connection = get_redis_connection()
    queues = [get_queue(name) for name in queue_names]
    print(f"[clipforge-worker] Listening on queues: {', '.join(queue_names)}", flush=True)
    worker = SimpleWorker(queues, connection=connection)
    try:
        worker.work(with_scheduler=True)
    except TypeError:
        worker.work()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
