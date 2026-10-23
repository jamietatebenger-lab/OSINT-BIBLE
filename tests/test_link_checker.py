"""Regression tests for link_checker HTTP classification; no network requests."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from link_checker import classify  # noqa: E402


class FakeResponse:
    def __init__(self, status_code, url="https://example.org/report.pdf"):
        self.status_code = status_code
        self.url = url

    def close(self):
        pass


class LinkCheckerTests(unittest.TestCase):
    URL = "https://example.org/report.pdf"

    @patch("link_checker.requests.request")
    def test_success_200(self, request):
        request.return_value = FakeResponse(200)
        self.assertEqual(classify(self.URL)[1], "OK")

    @patch("link_checker.requests.request")
    def test_server_503_is_not_ok(self, request):
        request.return_value = FakeResponse(503)
        row = classify(self.URL)
        self.assertEqual(row[1], "SERVER_ERROR")
        self.assertEqual(row[2], 503)

    @patch("link_checker.requests.request")
    def test_server_500_is_not_ok(self, request):
        request.return_value = FakeResponse(500)
        self.assertEqual(classify(self.URL)[1], "SERVER_ERROR")

    @patch("link_checker.requests.request")
    def test_blocked_remains_blocked(self, request):
        request.return_value = FakeResponse(403)
        self.assertEqual(classify(self.URL)[1], "BLOCKED")

    @patch("link_checker.requests.request")
    def test_absent_document_remains_dead(self, request):
        request.return_value = FakeResponse(404)
        self.assertEqual(classify(self.URL)[1], "DEAD")

    @patch("link_checker.requests.request")
    def test_head_503_get_200_recovers(self, request):
        request.side_effect = [FakeResponse(503), FakeResponse(200)]
        self.assertEqual(classify(self.URL, method="head")[1], "OK")
        self.assertEqual([c.args[0] for c in request.call_args_list], ["head", "get"])

    @patch("link_checker.requests.request")
    def test_head_503_get_503_server_error(self, request):
        request.side_effect = [FakeResponse(503), FakeResponse(503)]
        self.assertEqual(classify(self.URL, method="head")[1], "SERVER_ERROR")

    @patch("link_checker.requests.request")
    def test_redirect_is_not_deleted(self, request):
        request.return_value = FakeResponse(200, "https://example.org/new.pdf")
        self.assertEqual(classify(self.URL)[1], "REDIRECT")


if __name__ == "__main__":
    unittest.main()
