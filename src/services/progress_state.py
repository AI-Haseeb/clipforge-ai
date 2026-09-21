"""Authoritative progress snapshots with independent concurrent clip lifecycles."""
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path


class ProgressTracker:
    def __init__(self):
        self.events = []
        self.active = {}
        self.percent = 0.0
        self.sequence = 0
        self.total = 0

    def update(self, stage, label, *, clip=None, total=None, done=False):
        if total:
            self.total = total
        now = datetime.now(timezone.utc).isoformat()
        slot = str(clip) if clip is not None else "pipeline"
        if clip is not None and "pipeline" in self.active:
            self.active.pop("pipeline")["ended_at"] = now
        previous = self.active.pop(slot, None)
        if previous:
            previous["ended_at"] = now
        self.sequence += 1
        event = {"id": self.sequence, "message": label, "stage": stage,
                 "time": now, "clip": clip}
        if done:
            event["ended_at"] = now
        else:
            self.active[slot] = event
        self.events.append(event)
        self.events = self.events[-100:]
        active = list(self.active.values())
        active_stages = sorted({item["stage"] for item in active})
        estimate = {2: 20, 3: 30, 4: 40, 5: 40, 6: 65, 7: 60, 8: 90}.get(stage, 0)
        if clip is not None:
            finished = sum(1 for item in self.events if item.get("clip") is not None
                           and item["message"].startswith("Completed short"))
            estimate = 40 + 45 * finished / max(1, total or 1)
        self.percent = max(self.percent, estimate)
        labels = list(dict.fromkeys(item["message"] for item in active))
        completed = set(range(4 if clip is not None else min(stage, 4)))
        if self.total:
            for candidate in (4, 5, 6, 7):
                finished_clips = {item["clip"] for item in self.events
                                  if item.get("clip") is not None and item["stage"] == candidate
                                  and item.get("ended_at")}
                if len(finished_clips) == self.total and candidate not in active_stages:
                    completed.add(candidate)
        return {"progress_schema": 2, "progress_stage": active_stages[0] if active_stages else stage,
                "progress_label": " | ".join(labels) or label,
                "active_stages": active_stages,
                "completed_stages": sorted(completed),
                "progress_percent": self.percent, "progress_events": self.events,
                "updated_at": now}


_tracker = ProgressTracker()
_lock = threading.Lock()


def publish_progress(stage, label, **kwargs):
    target = os.getenv("CLIPFORGE_PROGRESS_FILE")
    if not target:
        return
    with _lock:
        payload = _tracker.update(int(stage), str(label), **kwargs)
        # The pipe preserves transitions shorter than a polling interval.
        print("[progress-json] " + json.dumps(payload, ensure_ascii=True), flush=True)
        try:
            path = Path(target)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_suffix(path.suffix + ".tmp")
            tmp_path.write_text(json.dumps(payload), encoding="utf-8")
            tmp_path.replace(path)
        except OSError:
            pass
