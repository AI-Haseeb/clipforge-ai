import json
import unittest
from unittest.mock import patch

from src.pipeline.cut_shorts import ai_cleanup_roman_captions, openai_romanize_segments


class _Response:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        return False
    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class RomanOpenAITests(unittest.TestCase):
    def settings(self):
        return {"ai_features": {"enabled": False, "openai_roman_captions": {
            "enabled": True, "api_key_env": "TEST_ROMAN_KEY", "model": "gpt-4o-mini"
        }}}

    @patch.dict("os.environ", {"TEST_ROMAN_KEY": "test-key"})
    @patch("urllib.request.urlopen")
    def test_batch_romanization_preserves_timing_and_english(self, urlopen):
        urlopen.return_value = _Response({"choices": [{"message": {"content": json.dumps({
            "segments": ["Aap apna YouTube channel shuru karein", "Yeh three practical tips hain"]
        })}}]})
        source = [{"start": 1, "end": 2, "text": "आप अपना YouTube चैनल शुरू करें"},
                  {"start": 2, "end": 3, "text": "یہ three practical tips ہیں"}]
        output = openai_romanize_segments(source, self.settings())
        self.assertEqual([item["text"] for item in output], [
            "Aap apna YouTube channel shuru karein", "Yeh three practical tips hain"])
        self.assertEqual([(item["start"], item["end"]) for item in output], [(1, 2), (2, 3)])
        request = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(request["temperature"], 0)
        self.assertEqual(request["response_format"], {"type": "json_object"})

    @patch.dict("os.environ", {"TEST_ROMAN_KEY": "test-key"})
    @patch("urllib.request.urlopen")
    def test_master_ai_plan_flag_does_not_disable_roman_mode(self, urlopen):
        urlopen.return_value = _Response({"choices": [{"message": {"content": "Aap kaise hain"}}]})
        self.assertEqual(ai_cleanup_roman_captions("آپ کیسے ہیں", self.settings()), "Aap kaise hain")

    @patch.dict("os.environ", {"TEST_ROMAN_KEY": "test-key"})
    @patch("urllib.request.urlopen")
    def test_invalid_batch_response_uses_fallback(self, urlopen):
        urlopen.return_value = _Response({"choices": [{"message": {"content": '{"segments":["sirf aik"]}'}}]})
        source = [{"text": "पहला"}, {"text": "दूसरा"}]
        self.assertIsNone(openai_romanize_segments(source, self.settings()))


if __name__ == "__main__":
    unittest.main()
