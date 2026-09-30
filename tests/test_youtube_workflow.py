import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from backend.app import main as api


class YoutubeWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for folder in ("shorts", "thumbnails", "meta"):
            (self.root / folder).mkdir()
        for n in (1, 2, 3):
            (self.root / "shorts" / f"short_{n:02}.mp4").write_bytes(b"mock video")
            (self.root / "meta" / f"short_{n:02}.txt").write_text(
                "TITLE:\nGenerated title\nHOOK OPTIONS:\nHook\nDESCRIPTION:\nGenerated description\nHASHTAGS:\n#one\nHASHTAGS COMMA:\none,two\nMETA:\nOther", encoding="utf-8")
        for filename in ("thumbnail_01.jpg", "thumbnail_01_v2.png", "thumbnail_01_v3.jpeg"):
            (self.root / "thumbnails" / filename).write_bytes(b"mock image")
        self.youtube = MagicMock()
        self.youtube.videos.return_value.insert.return_value.execute.return_value = {"id": "mock-video"}
        self.youtube.thumbnails.return_value.set.return_value.execute.return_value = {"items": [{"default": {"url": "mock"}}]}
        self.build = MagicMock(return_value=self.youtube)
        self.media = MagicMock(side_effect=lambda path, **kw: {"path": path, **kw})
        self.libraries = (MagicMock(), MagicMock(), self.build, self.media)

    def publish(self, items=None, **extra):
        with patch.object(api, "_youtube_output_dirs", return_value=[self.root]), patch.object(api, "_youtube_credentials"), patch.object(api, "_youtube_libraries", return_value=self.libraries):
            return api.youtube_publish({"job_id": "test", "items": items or [{"short": "short_01.mp4", "thumbnail": 1}], **extra})

    def test_selected_thumbnail_variations_and_mime(self):
        for variation, filename, mime in ((1, "thumbnail_01.jpg", "image/jpeg"), (2, "thumbnail_01_v2.png", "image/png"), (3, "thumbnail_01_v3.jpeg", "image/jpeg")):
            with self.subTest(variation=variation):
                result = self.publish([{"short": "short_01.mp4", "thumbnail": variation}])
                media = self.youtube.thumbnails.return_value.set.call_args.kwargs["media_body"]
                self.assertEqual(Path(media["path"]).name, filename)
                self.assertEqual(media["mimetype"], mime)
                self.assertTrue(result["items"][0]["thumbnail_applied"])

    def test_visibility_metadata_and_existing_schedule_payload(self):
        for visibility in ("private", "unlisted", "public"):
            self.publish(visibility=visibility)
            body = self.youtube.videos.return_value.insert.call_args.kwargs["body"]
            self.assertEqual(body["status"]["privacyStatus"], visibility)
            self.assertEqual(body["snippet"]["title"], "Generated title")
            self.assertEqual(body["snippet"]["description"], "Generated description")
            self.assertEqual(body["snippet"]["tags"], ["one", "two"])
        self.publish(publish_mode="schedule", publish_at="2030-01-01T12:00:00Z", visibility="public")
        body = self.youtube.videos.return_value.insert.call_args.kwargs["body"]
        self.assertEqual(body["status"]["privacyStatus"], "private")
        self.assertEqual(body["status"]["publishAt"], "2030-01-01T12:00:00Z")

    def test_one_upload_failure_does_not_discard_success_or_stop_remaining(self):
        self.youtube.videos.return_value.insert.return_value.execute.side_effect = [{"id": "first"}, RuntimeError("secret must not leak"), {"id": "third"}]
        result = self.publish([{"short": f"short_{n:02}.mp4"} for n in (1, 2, 3)])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["items"][0]["video_id"], "first")
        self.assertIn("error", result["items"][1])
        self.assertNotIn("secret must not leak", json.dumps(result))
        self.assertEqual(result["items"][2]["video_id"], "third")

    def test_thumbnail_failure_keeps_uploaded_video(self):
        self.youtube.thumbnails.return_value.set.return_value.execute.side_effect = RuntimeError("private detail")
        item = self.publish()["items"][0]
        self.assertEqual(item["video_id"], "mock-video")
        self.assertNotIn("error", item)
        self.assertIn("warning", item)
        self.assertFalse(item["thumbnail_applied"])

    def test_empty_thumbnail_response_is_not_success(self):
        self.youtube.thumbnails.return_value.set.return_value.execute.return_value = {}
        self.assertFalse(self.publish()["items"][0]["thumbnail_applied"])

    def test_invalid_selection_rejected_before_any_upload(self):
        with self.assertRaises(api.HTTPException):
            self.publish([{"short": "short_01.mp4"}, {"short": "missing.mp4"}])
        self.build.assert_not_called()

    def test_duplicate_publish_blocked(self):
        with api._YOUTUBE_PUBLISH_LOCK:
            with self.assertRaises(api.HTTPException) as error:
                api.youtube_publish({})
        self.assertEqual(error.exception.status_code, 409)

    def test_auth_valid_refresh_and_invalid(self):
        token = self.root / "token.json"
        token.write_text("{}")
        credentials = MagicMock(valid=True)
        self.libraries[1].from_authorized_user_file.return_value = credentials
        with patch.object(api, "_youtube_token_path", return_value=token), patch.object(api, "_youtube_libraries", return_value=self.libraries):
            self.assertTrue(api.youtube_auth_status()["connected"])
            credentials.valid = False
            credentials.refresh_token = "mock refresh token"
            credentials.to_json.return_value = '{"token":"mock refreshed"}'
            credentials.refresh.side_effect = lambda request: setattr(credentials, "valid", True)
            self.assertTrue(api.youtube_auth_status()["connected"])
            self.assertEqual(json.loads(token.read_text())["token"], "mock refreshed")
            credentials.valid = False
            credentials.refresh.side_effect = RuntimeError("secret")
            result = api.youtube_auth_status()
            self.assertFalse(result["connected"])
            self.assertNotIn("secret", result["detail"])
            self.libraries[1].from_authorized_user_file.side_effect = ValueError("corrupt")
            self.assertFalse(api.youtube_auth_status()["connected"])

    def test_oauth_flow_reused_state_single_use_and_expiry(self):
        flow = MagicMock()
        flow.authorization_url.return_value = ("https://accounts.google.com/mock", "unused")
        with patch.dict(api.YOUTUBE_AUTH_STATE, {}, clear=True), patch.object(api, "_youtube_flow", return_value=flow), patch.object(api, "_save_youtube_credentials") as save:
            api.youtube_auth_start("job", "http://localhost:5500")
            state = next(iter(api.YOUTUBE_AUTH_STATE))
            response = api.youtube_auth_callback("code", state)
            self.assertEqual(response.status_code, 200)
            flow.fetch_token.assert_called_once_with(code="code")
            save.assert_called_once()
            self.assertIn(b'"http://localhost:5500"', response.body)
            self.assertNotIn(b"'*'", response.body)
            self.assertEqual(api.youtube_auth_callback("code", state).status_code, 400)
            api.YOUTUBE_AUTH_STATE["old"] = {"created": time.time() - 601}
            self.assertEqual(api.youtube_auth_callback("code", "old").status_code, 400)

    def test_oauth_cancel_notifies_original_tab(self):
        with patch.dict(api.YOUTUBE_AUTH_STATE, {"cancel": {"created": time.time(), "origin": "http://localhost:5500"}}, clear=True):
            result = api.youtube_auth_callback(state="cancel", error="access_denied")
            self.assertEqual(result.status_code, 400)
            self.assertIn(b"clipforge-youtube-error", result.body)

    def test_private_files_and_untrusted_origins_blocked(self):
        client = TestClient(api.app, base_url="http://localhost:8000")
        for url in ("/data/youtube_tokens/default.json", "/data/youtube_tokens/default.tmp", "/data/clipforge_auth.sqlite3", "/config/youtube_client_secret.json"):
            self.assertEqual(client.get(url).status_code, 404)
        for origin in ("https://evil.example", "null", "http://localhost.evil.example:5500"):
            self.assertEqual(client.post("/youtube/publish", json={}, headers={"Origin": origin}).status_code, 403)
        self.assertEqual(client.get("/youtube/auth/start?job_id=test", headers={"Sec-Fetch-Site": "cross-site"}).status_code, 403)
        with patch.object(api, "_youtube_credentials"):
            self.assertTrue(client.get("/youtube/auth/status", headers={"Origin": "http://localhost:5500"}).json()["connected"])


if __name__ == "__main__":
    unittest.main()
