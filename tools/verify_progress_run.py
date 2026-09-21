"""Run one real speech clip through the same task used by local/queue processing."""
import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from backend.app.job_tasks import run_clipforge_job, _load_registry
from src.services.pipeline_runner import PipelineRequest, _valid_video


def main():
    source = next(Path("data/uploads").glob("How To Market*.mp4"))
    sample = Path("data/input/progress_speech_12s.mp4")
    if not sample.exists():
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "30", "-i", str(source),
                        "-t", "12", "-vf", "scale=-2:480", "-c:v", "libx264", "-preset", "fast",
                        "-c:a", "aac", str(sample)], check=True)
    request = PipelineRequest(input_video=str(sample), segment_mode="manual", manual_ranges="0-10",
                              output_resolution="720p", captions=True, reframe="off", editing_style="none",
                              music_enabled=True, music_category="educational")
    job_id = "progress_verification_" + __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
    result = run_clipforge_job(job_id, asdict(request))
    job = _load_registry()[job_id]
    output = Path(result["output_dir"])
    assert job["status"] == "completed", job
    assert len(result["shorts"]) == 1
    assert _valid_video(Path(result["shorts"][0]))
    assert list((output / "captions").rglob("*.ass"))
    assert len(list((output / "thumbnails").rglob("*.png"))) == 3
    assert (output / "zip/client_output.zip").is_file()
    import zipfile
    with zipfile.ZipFile(output / "zip/client_output.zip") as archive:
        assert archive.testzip() is None
    stages = {event["stage"] for event in job["progress_events"]}
    assert {2, 3, 4, 5, 6, 7, 8} <= stages, stages
    summary = {"job_id": job_id, "output_dir": str(output), "shorts": result["shorts"],
               "status": job["status"], "stages": sorted(stages)}
    Path("tmp/progress_verification.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
