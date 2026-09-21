import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.services.progress_state import ProgressTracker
from src.services.pipeline_runner import build_output_zip, _valid_video
from backend.app import job_tasks


class ProgressTests(unittest.TestCase):
    def test_parallel_stages_remain_active(self):
        tracker = ProgressTracker()
        tracker.update(4, "Rendering short 1/2", clip=1, total=2)
        tracker.update(4, "Rendering short 2/2", clip=2, total=2)
        snapshot = tracker.update(6, "Generating thumbnails 1/2", clip=1, total=2)
        self.assertEqual(snapshot["active_stages"], [4, 6])
        self.assertIn("Rendering short 2/2", snapshot["progress_label"])
        self.assertNotIn(4, snapshot["completed_stages"])
        self.assertNotIn("ended_at", snapshot["progress_events"][1])

    def test_repeated_stages_have_distinct_events_and_monotonic_percent(self):
        tracker = ProgressTracker()
        first = tracker.update(7, "Writing metadata 1/1", clip=1, total=1)
        second = tracker.update(4, "Adding music 1/1", clip=1, total=1)
        self.assertGreaterEqual(second["progress_percent"], first["progress_percent"])
        self.assertEqual(second["active_stages"], [4])
        self.assertIn("ended_at", second["progress_events"][0])
        self.assertNotEqual(second["progress_events"][0]["id"], second["progress_events"][1]["id"])

    def test_worker_uses_snapshot_without_one_based_shift_or_raw_log_override(self):
        callback = job_tasks._make_job_log_callback("test")
        payload = ProgressTracker().update(6, "Generating thumbnails")
        with patch.object(job_tasks, "_update_job") as update:
            callback("[progress-json] " + json.dumps(payload))
            callback("[meta-openai] fallback")
            update.assert_called_once_with("test", payload)

    def test_zip_contains_outputs_not_temporary_video(self):
        import zipfile
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "shorts").mkdir()
            (root / "shorts/short_01.mp4").write_bytes(b"test")
            (root / "shorts/_raw_short_01.mp4").write_bytes(b"temporary")
            with zipfile.ZipFile(build_output_zip(root)) as archive:
                self.assertEqual(archive.namelist(), ["shorts/short_01.mp4"])

    def test_invalid_video_not_recovered(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.mp4"
            path.write_bytes(b"invalid")
            self.assertFalse(_valid_video(path))


if __name__ == "__main__":
    unittest.main()
