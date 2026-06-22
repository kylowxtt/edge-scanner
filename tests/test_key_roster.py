from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from key_roster import ApiKeyRoster, KeyRosterError


class ApiKeyRosterTests(unittest.TestCase):
    def test_loads_and_selects_active_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "api_keys.json"
            path.write_text(
                json.dumps(
                    {
                        "reset": {"day": 1, "hour": 0, "timezone": "UTC"},
                        "keys": [
                            {"id": "first", "key": "one", "enabled": True, "remaining": 2},
                            {"id": "second", "key": "two", "enabled": True, "remaining": 9},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            roster = ApiKeyRoster.load(path)

            self.assertIsNotNone(roster)
            assert roster is not None
            self.assertEqual(roster.get_key(), "two")
            self.assertEqual(roster.metadata()["active_key_id"], "second")

    def test_invalid_json_raises_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "api_keys.json"
            path.write_text("{not-json", encoding="utf-8")

            with self.assertRaises(KeyRosterError):
                ApiKeyRoster.load(path)

    def test_mark_response_persists_quota_headers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "api_keys.json"
            path.write_text(
                json.dumps({"keys": [{"id": "primary", "key": "abc", "enabled": True}]}),
                encoding="utf-8",
            )
            roster = ApiKeyRoster.load(path)
            assert roster is not None

            self.assertEqual(roster.get_key(), "abc")
            roster.mark_response(
                {
                    "x-requests-remaining": "42",
                    "x-requests-used": "8",
                    "x-requests-last": "3",
                }
            )

            saved = json.loads(path.read_text(encoding="utf-8"))
            saved_key = saved["keys"][0]
            self.assertEqual(saved_key["remaining"], 42)
            self.assertEqual(saved_key["used"], 8)
            self.assertEqual(saved_key["last_cost"], 3)
            self.assertIsNone(saved_key["exhausted_at"])

    def test_monthly_reset_reactivates_exhausted_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "api_keys.json"
            path.write_text(
                json.dumps(
                    {
                        "reset": {"day": 1, "hour": 0, "timezone": "UTC"},
                        "keys": [
                            {
                                "id": "primary",
                                "key": "abc",
                                "enabled": True,
                                "status": "exhausted",
                                "remaining": 0,
                                "exhausted_at": "2026-05-20T12:00:00Z",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            roster = ApiKeyRoster.load(path)
            assert roster is not None

            roster.reactivate_reset_keys(dt.datetime(2026, 6, 2, tzinfo=dt.timezone.utc))

            self.assertEqual(roster.get_key(), "abc")
            self.assertEqual(roster.metadata()["keys_exhausted"], 0)


if __name__ == "__main__":
    unittest.main()
