"""Check that the catalogue validator never labels HTTP 5xx as OK."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_data import _check_links


class FakeResponse:
    def __init__(self, status):
        self.status_code = status
        self.url = "https://example.org/source"

    def close(self):
        pass


class LinkValidationTests(unittest.TestCase):
    def verify_status(self, http_code, classification):
        with patch("requests.get", return_value=FakeResponse(http_code)):
            results = _check_links(["https://example.org/source"], workers=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["http"], http_code)
        self.assertEqual(results[0]["status"], classification)

    def test_ok(self):
        self.verify_status(200, "OK")

    def test_server_error_500(self):
        self.verify_status(500, "SERVER_ERROR")

    def test_server_error_503(self):
        self.verify_status(503, "SERVER_ERROR")

    def test_dead_404(self):
        self.verify_status(404, "DEAD")

    def test_blocked_403(self):
        self.verify_status(403, "BLOCKED")


if __name__ == "__main__":
    unittest.main()
