"""Check that the CLI link audit reports inconclusive and non-OK results."""

import contextlib
import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import osint_bible


class FakeResponse:
    def __init__(self, status_code, url):
        self.status_code = status_code
        self.url = url

    def close(self):
        pass


class OSINTBibleCheckTests(unittest.TestCase):
    def run_check(self, responses, strict=False):
        urls = [f"https://example.org/{i}" for i in range(len(responses))]
        tools = [{"url": url} for url in urls]
        output = io.StringIO()
        with patch.object(osint_bible, "_load", return_value={"tools": tools}), \
                patch("requests.get", side_effect=responses), \
                contextlib.redirect_stdout(output):
            result = osint_bible.cmd_check(SimpleNamespace(
                limit=None, workers=1, strict=strict
            ))
        return result, output.getvalue()

    def test_check_reports_each_classification(self):
        responses = [
            FakeResponse(200, "https://example.org/0"),
            FakeResponse(200, "https://example.org/new"),
            FakeResponse(403, "https://example.org/2"),
            FakeResponse(503, "https://example.org/3"),
            requests.ConnectionError("offline"),
            FakeResponse(404, "https://example.org/5"),
        ]
        result, output = self.run_check(responses)
        self.assertEqual(result, 0)
        for status in ("OK", "REDIRECT", "BLOCKED", "SERVER_ERROR",
                       "NO_RESPONSE", "DEAD"):
            self.assertIn(status, output)
        self.assertIn("ConnectionError", output)
        self.assertIn("https://example.org/new", output)

    def test_strict_mode_fails_on_dead_link(self):
        result, _ = self.run_check(
            [FakeResponse(404, "https://example.org/0")], strict=True
        )
        self.assertEqual(result, 1)

    def test_strict_mode_does_not_fail_on_no_response(self):
        result, _ = self.run_check(
            [requests.ConnectionError("offline")], strict=True
        )
        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
