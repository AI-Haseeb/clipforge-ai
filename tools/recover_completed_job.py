"""Recover a failed registry entry only after validating its committed report/videos."""
import argparse
import json
from datetime import datetime
from pathlib import Path

from backend.app.job_tasks import _load_registry, _update_job
from src.services.pipeline_runner import _valid_video, build_output_zip


def recover(job_id, output_dir):
    output = Path(output_dir).resolve()
    job = _load_registry().get(job_id)
    if not job or job.get("status") in {"queued", "processing"}:
        raise ValueError("Recovery requires an existing inactive job")
    reports = list((output / "reports").glob("*.json"))
    if not reports:
        raise ValueError("No final report")
    shorts = []
    for report in reports:
        data = json.loads(report.read_text(encoding="utf-8"))
        shorts.extend(data.get("shorts", []))
    if not shorts or not all(Path(item).resolve().is_relative_to(output) and _valid_video(Path(item)) for item in shorts):
        raise ValueError("Missing or invalid video outputs")
    if "[stage] DONE" not in (output / "run.log").read_text(encoding="utf-8"):
        raise ValueError("Pipeline did not reach completion")
    archive = build_output_zip(output)
    _update_job(job_id, {"status": "completed", "queue_status": "finished", "progress_failed": False,
        "error": "", "progress_stage": 10, "progress_percent": 100, "progress_label": "Complete",
        "active_stages": [], "finished_at": datetime.now().astimezone().isoformat(),
        "recovered_from_validated_outputs": True,
        "result": {"job_id": output.name, "output_dir": str(output), "shorts": shorts,
                   "report_path": str(reports[0])}})
    print(json.dumps({"job_id": job_id, "shorts": len(shorts), "zip": str(archive)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("job_id")
    parser.add_argument("output_dir")
    args = parser.parse_args()
    recover(args.job_id, args.output_dir)
