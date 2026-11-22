import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from app.pipeline_engine import _model_factory, simulate
from contracts import StudentProfile
from model_errors import ModelRequestError


class ModelErrorTests(unittest.TestCase):
    def test_http_code_is_visible_without_provider_body(self):
        with patch("app.pipeline_engine.build_opener") as factory:
            factory.return_value.open.side_effect = HTTPError("https://example.test/chat/completions", 401,
                                                             "key=secret-value", {}, None)
            model, _ = _model_factory({"LLM_ENDPOINT": "https://example.test/chat/completions",
                                      "LLM_MODEL": "test", "LLM_API_KEY": "secret-value"})
            with self.assertRaises(ModelRequestError) as caught:
                model("JSON", {})
            self.assertIn("HTTP 401", str(caught.exception))
            self.assertNotIn("secret-value", str(caught.exception))

    def test_planning_error_is_forwarded_to_frontend(self):
        def failed(*args):
            raise ModelRequestError(402)
        result = simulate("test question", StudentProfile("", "", 0), model=failed)
        self.assertEqual(result.status, "failed")
        self.assertIn("HTTP 402", result.text)
        self.assertIn("余额不足", result.text)


if __name__ == "__main__":
    unittest.main()
