from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import scanner
from key_roster import EXHAUSTED_MESSAGE, ApiKeyRoster


class FakeResponse:
    def __init__(self, status_code: int, payload: object, headers: dict[str, str] | None = None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = json.dumps(payload)

    def json(self) -> object:
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]):
        self.responses = responses
        self.params_seen: list[dict[str, str]] = []

    def get(self, url: str, params: dict[str, str], timeout: int) -> FakeResponse:
        self.params_seen.append(dict(params))
        return self.responses.pop(0)


def make_roster(path: Path, keys: list[dict[str, object]]) -> ApiKeyRoster:
    path.write_text(
        json.dumps({"reset": {"day": 1, "hour": 0, "timezone": "UTC"}, "keys": keys}),
        encoding="utf-8",
    )
    roster = ApiKeyRoster.load(path)
    assert roster is not None
    return roster


class ScannerKeyRotationTests(unittest.TestCase):
    def setUp(self) -> None:
        scanner._SPORTS_CACHE = None
        scanner._SPORTS_CACHE_EXPIRES_AT = 0.0

    def test_exhausted_key_retries_same_call_with_next_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "api_keys.json"
            roster = make_roster(
                path,
                [
                    {"id": "first", "key": "one", "enabled": True},
                    {"id": "second", "key": "two", "enabled": True},
                ],
            )
            fake_session = FakeSession(
                [
                    FakeResponse(429, {"message": "OUT_OF_USAGE_CREDITS"}),
                    FakeResponse(
                        200,
                        [{"id": "event-1"}],
                        {
                            "x-requests-remaining": "20",
                            "x-requests-used": "5",
                            "x-requests-last": "2",
                        },
                    ),
                ]
            )

            with mock.patch.object(scanner, "_SESSION", fake_session):
                data, cost = scanner.fetch_odds_for_sport(roster, "basketball_nba", ["h2h"], regions=["us"])

            self.assertEqual(data, [{"id": "event-1"}])
            self.assertEqual(cost, 2)
            self.assertEqual([params["apiKey"] for params in fake_session.params_seen], ["one", "two"])
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["keys"][0]["status"], "exhausted")
            self.assertEqual(saved["keys"][1]["remaining"], 20)

    def test_all_keys_exhausted_returns_clear_scan_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "api_keys.json"
            roster = make_roster(
                path,
                [
                    {"id": "first", "key": "one", "enabled": True},
                    {"id": "second", "key": "two", "enabled": True},
                ],
            )
            fake_session = FakeSession(
                [
                    FakeResponse(429, {"message": "OUT_OF_USAGE_CREDITS"}),
                    FakeResponse(429, {"message": "OUT_OF_USAGE_CREDITS"}),
                ]
            )

            with mock.patch.object(scanner, "_SESSION", fake_session):
                result = scanner.run_scan("", key_roster=roster)

            self.assertFalse(result["success"])
            self.assertEqual(result["error"], EXHAUSTED_MESSAGE)
            self.assertEqual(result["error_code"], 429)
            self.assertEqual(result["api_keys"]["keys_exhausted"], 2)

    def test_env_style_key_still_works_without_roster(self) -> None:
        with mock.patch.object(scanner, "fetch_sports", return_value=[]):
            result = scanner.run_scan("env-key", sports=[])

        self.assertTrue(result["success"])
        self.assertIsNone(result["api_keys"])


if __name__ == "__main__":
    unittest.main()
