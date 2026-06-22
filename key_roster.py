from __future__ import annotations

import calendar
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_ROSTER_PATH = Path("data/api_keys.json")
EXHAUSTED_MESSAGE = "All configured API keys are exhausted until the next reset."


class KeyRosterError(Exception):
    """Raised when the API key roster cannot be loaded or used."""


class ApiKeyRoster:
    def __init__(self, path: Path, data: Dict[str, Any]):
        self.path = path
        self.data = data
        self._active_key_id: Optional[str] = None
        self._last_key_id: Optional[str] = None
        self._changed = False
        self._normalize()
        self.reactivate_reset_keys()
        if self._changed:
            self.save()

    @classmethod
    def load(cls, path: Path | str = DEFAULT_ROSTER_PATH) -> Optional["ApiKeyRoster"]:
        roster_path = Path(path)
        if not roster_path.exists():
            return None
        try:
            with roster_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise KeyRosterError(f"Invalid API key roster JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise KeyRosterError("API key roster must be a JSON object.")
        return cls(roster_path, data)

    def has_enabled_keys(self) -> bool:
        return bool(self._enabled_keys())

    def get_key(self) -> str:
        candidates = self._active_keys()
        if not candidates:
            raise KeyRosterError(EXHAUSTED_MESSAGE)

        if self._active_key_id:
            for item in candidates:
                if item["id"] == self._active_key_id:
                    self._last_key_id = item["id"]
                    return item["key"]

        selected = min(candidates, key=lambda item: (self._remaining_rank(item), item.get("last_used_at") or ""))
        self._active_key_id = selected["id"]
        self._last_key_id = selected["id"]
        return selected["key"]

    def mark_response(self, headers: Dict[str, str]) -> None:
        key = self._last_key()
        if not key:
            return
        key["status"] = "active"
        key["remaining"] = _header_int(headers, "x-requests-remaining")
        key["used"] = _header_int(headers, "x-requests-used")
        key["last_cost"] = _header_int(headers, "x-requests-last")
        key["last_used_at"] = _utc_now()
        key["exhausted_at"] = None
        self._changed = True
        self.save()

    def mark_exhausted(self) -> None:
        key = self._last_key()
        if not key:
            return
        key["status"] = "exhausted"
        key["remaining"] = 0
        key["exhausted_at"] = _utc_now()
        self._active_key_id = None
        self._changed = True
        self.save()

    def metadata(self) -> Dict[str, Any]:
        keys = self._enabled_keys()
        exhausted = [item for item in keys if item.get("status") == "exhausted"]
        return {
            "active_key_id": self._active_key_id,
            "keys_available": len(keys),
            "keys_exhausted": len(exhausted),
        }

    def reactivate_reset_keys(self, now: Optional[dt.datetime] = None) -> None:
        now = now or dt.datetime.now(dt.timezone.utc)
        for key in self._enabled_keys():
            exhausted_at = _parse_datetime(key.get("exhausted_at"))
            if key.get("status") != "exhausted" or exhausted_at is None:
                continue
            if _next_reset_after(exhausted_at, self.data["reset"]) <= now:
                key["status"] = "active"
                key["remaining"] = None
                key["exhausted_at"] = None
                self._changed = True

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=2)
            fh.write("\n")
        os.replace(tmp_path, self.path)
        self._changed = False

    def _normalize(self) -> None:
        reset = self.data.get("reset")
        if not isinstance(reset, dict):
            reset = {}
            self.data["reset"] = reset
            self._changed = True
        reset.setdefault("day", 1)
        reset.setdefault("hour", 0)
        reset.setdefault("timezone", "UTC")

        keys = self.data.get("keys")
        if not isinstance(keys, list):
            raise KeyRosterError("API key roster must include a keys array.")
        for index, key in enumerate(keys, start=1):
            if not isinstance(key, dict):
                raise KeyRosterError("Each API key roster entry must be an object.")
            if key.get("enabled", True) and not str(key.get("key") or "").strip():
                raise KeyRosterError("Each enabled API key roster entry must include a key value.")
            key.setdefault("id", f"key-{index}")
            key.setdefault("enabled", True)
            key.setdefault("status", "active")
            key.setdefault("remaining", None)
            key.setdefault("used", None)
            key.setdefault("last_cost", None)
            key.setdefault("last_used_at", None)
            key.setdefault("exhausted_at", None)

    def _enabled_keys(self) -> List[Dict[str, Any]]:
        return [
            key
            for key in self.data.get("keys", [])
            if key.get("enabled", True) and str(key.get("key") or "").strip()
        ]

    def _active_keys(self) -> List[Dict[str, Any]]:
        self.reactivate_reset_keys()
        return [key for key in self._enabled_keys() if key.get("status") != "exhausted"]

    def _last_key(self) -> Optional[Dict[str, Any]]:
        if not self._last_key_id:
            return None
        for key in self._enabled_keys():
            if key.get("id") == self._last_key_id:
                return key
        return None

    @staticmethod
    def _remaining_rank(key: Dict[str, Any]) -> int:
        remaining = key.get("remaining")
        if remaining is None:
            return 0
        try:
            return -int(remaining)
        except (TypeError, ValueError):
            return 0


def _header_int(headers: Dict[str, str], name: str) -> Optional[int]:
    value = None
    for header_name, header_value in headers.items():
        if header_name.lower() == name:
            value = header_value
            break
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> Optional[dt.datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _next_reset_after(start: dt.datetime, reset: Dict[str, Any]) -> dt.datetime:
    try:
        tz = ZoneInfo(str(reset.get("timezone") or "UTC"))
    except ZoneInfoNotFoundError:
        tz = dt.timezone.utc

    local_start = start.astimezone(tz)
    day = _safe_int(reset.get("day"), 1)
    hour = max(0, min(_safe_int(reset.get("hour"), 0), 23))
    year = local_start.year
    month = local_start.month

    candidate = _reset_datetime(year, month, day, hour, tz)
    if candidate <= local_start:
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
        candidate = _reset_datetime(year, month, day, hour, tz)
    return candidate.astimezone(dt.timezone.utc)


def _reset_datetime(year: int, month: int, day: int, hour: int, tz: dt.tzinfo) -> dt.datetime:
    last_day = calendar.monthrange(year, month)[1]
    safe_day = max(1, min(day, last_day))
    return dt.datetime(year, month, safe_day, hour, tzinfo=tz)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
