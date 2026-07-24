from __future__ import annotations  # enables future Python language features
import json  # handles JSON encode and decode
import os  # works with environment variables and OS paths
import time  # measures time, delays, and elapsed seconds
from pathlib import Path  # provides object-oriented file paths
def set_progress(stage: int, label: str) -> None:  # updates runtime state or UI/backend state
    """Write pipeline progress for the FastAPI parent process.

    This is intentionally tiny and best-effort: the video pipeline should never
    fail only because progress reporting failed.
    """
    target = os.getenv("CLIPFORGE_PROGRESS_FILE")
    if not target:
        return

    try:
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "stage": int(stage),
            "label": str(label),
            "updated_at": time.time(),
        }
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(path)
    except Exception:
        return
