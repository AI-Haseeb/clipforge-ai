from __future__ import annotations  # enables future Python language features
from pathlib import Path  # provides object-oriented file paths
import json  # handles JSON encode and decode
from typing import Optional, Dict, Any  # adds type hint helpers
def detect_main_face_timeline(  # finds highlights, faces, language, timing, or visual signals
    video_path: Path,
    out_json: Path,
    sample_fps: float = 10.0,
    min_score: float = 0.35,
    hold_seconds: float = 0.9,
    **kwargs,
) -> None:
    """
    SAFE STUB — FACE DETECTION DISABLED

    This function intentionally does NOT perform any face / pose detection.
    It only writes a valid empty timeline JSON so the rest of the pipeline
    continues to work without smart-crop or face-follow logic.

    Output format (unchanged):
      {
        "timeline": [
          { "t": 0.0, "face": null }
        ]
      }
    """

    out_json = Path(out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)

    # Minimal valid timeline
    data = {
        "timeline": [
            {
                "t": 0.0,
                "face": None
            }
        ]
    }

    out_json.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
