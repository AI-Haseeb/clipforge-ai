from __future__ import annotations  # enables future Python language features
def set_progress(stage: int, label: str, **kwargs) -> None:  # updates runtime state or UI/backend state
    """Write pipeline progress for the FastAPI parent process.

    This is intentionally tiny and best-effort: the video pipeline should never
    fail only because progress reporting failed.
    """
    from src.services.progress_state import publish_progress
    publish_progress(stage, label, **kwargs)
