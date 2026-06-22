from __future__ import annotations

import argparse
import os
import socket
import threading
import webbrowser
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from config import (
    DEFAULT_BANKROLL,
    DEFAULT_COMMISSION,
    DEFAULT_KELLY_FRACTION,
    DEFAULT_REGION_KEYS,
    DEFAULT_SHARP_BOOK,
    DEFAULT_SPORT_OPTIONS,
    KELLY_OPTIONS,
    MIN_EDGE_PERCENT,
    REGION_OPTIONS,
    SHARP_BOOKS,
)
from key_roster import ApiKeyRoster, DEFAULT_ROSTER_PATH, KeyRosterError
from scanner import run_scan

load_dotenv()

app = Flask(__name__)
ENV_API_KEY = os.getenv("ODDS_API_KEY") or os.getenv("THEODDSAPI_API_KEY")


def load_key_roster() -> Optional[ApiKeyRoster]:
    roster = ApiKeyRoster.load(DEFAULT_ROSTER_PATH)
    if roster and roster.has_enabled_keys():
        return roster
    return None


@app.route("/")
def index() -> str:
    has_key_roster = False
    try:
        has_key_roster = bool(load_key_roster())
    except KeyRosterError:
        has_key_roster = False
    return render_template(
        "index.html",
        default_sports=DEFAULT_SPORT_OPTIONS,
        region_options=REGION_OPTIONS,
        default_commission_percent=int(DEFAULT_COMMISSION * 100),
        has_env_key=has_key_roster or bool(ENV_API_KEY),
        api_key_source_label="API key roster" if has_key_roster else ".env",
        sharp_books=SHARP_BOOKS,
        default_sharp_book=DEFAULT_SHARP_BOOK,
        default_min_edge_percent=MIN_EDGE_PERCENT,
        default_bankroll=DEFAULT_BANKROLL,
        default_kelly_fraction=DEFAULT_KELLY_FRACTION,
        kelly_options=KELLY_OPTIONS,
    )


@app.route("/scan", methods=["POST"])
def scan() -> tuple:
    payload = request.get_json(force=True, silent=True) or {}
    try:
        key_roster = load_key_roster()
    except KeyRosterError as exc:
        return jsonify({"success": False, "error": str(exc), "error_code": 500}), 500
    api_key = "" if key_roster else ENV_API_KEY or (payload.get("apiKey") or "").strip()
    sports = payload.get("sports") or []
    all_sports = bool(payload.get("allSports"))
    stake = payload.get("stake")
    regions = payload.get("regions")
    commission = payload.get("commission")
    sharp_book = (payload.get("sharpBook") or DEFAULT_SHARP_BOOK).strip().lower()
    try:
        min_edge_percent = (
            float(payload.get("minEdgePercent")) if payload.get("minEdgePercent") is not None else MIN_EDGE_PERCENT
        )
    except (TypeError, ValueError):
        min_edge_percent = MIN_EDGE_PERCENT
    min_edge_percent = max(0.0, min_edge_percent)
    try:
        bankroll_value = float(payload.get("bankroll")) if payload.get("bankroll") is not None else DEFAULT_BANKROLL
    except (TypeError, ValueError):
        bankroll_value = DEFAULT_BANKROLL
    bankroll_value = max(0.0, bankroll_value)
    try:
        kelly_fraction = (
            float(payload.get("kellyFraction"))
            if payload.get("kellyFraction") is not None
            else DEFAULT_KELLY_FRACTION
        )
    except (TypeError, ValueError):
        kelly_fraction = DEFAULT_KELLY_FRACTION
    kelly_fraction = max(0.0, min(kelly_fraction, 1.0))
    try:
        stake_value = float(stake) if stake is not None else 100.0
    except (TypeError, ValueError):
        stake_value = 100.0
    if isinstance(regions, list):
        regions_value = [str(region) for region in regions if isinstance(region, str)]
    else:
        regions_value = None
    try:
        commission_percent = float(commission) if commission is not None else None
    except (TypeError, ValueError):
        commission_percent = None
    commission_rate = (
        commission_percent / 100.0 if commission_percent is not None else DEFAULT_COMMISSION
    )
    result = run_scan(
        api_key,
        sports,
        all_sports,
        stake_value,
        regions_value or DEFAULT_REGION_KEYS,
        commission_rate,
        sharp_book=sharp_book,
        min_edge_percent=min_edge_percent,
        bankroll=bankroll_value,
        kelly_fraction=kelly_fraction,
        key_roster=key_roster,
    )
    status = 200 if result.get("success") else result.get("error_code", 500)
    return jsonify(result), status


def _port_available(port: int) -> bool:
    if port <= 0:
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(0.5)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _choose_port(preferred: Optional[int]) -> int:
    candidates = []
    if preferred:
        candidates.append(preferred)
    candidates.extend([5000, 5050, 8000])
    seen = set()
    for port in candidates:
        if port in seen:
            continue
        seen.add(port)
        if _port_available(port):
            return port
    return 0  # fall back to OS-chosen port


def open_browser(port: int) -> None:
    webbrowser.open_new(f"http://localhost:{port}/")


def ensure_data_dir() -> None:
    Path("data").mkdir(exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sports Arbitrage Scanner server")
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to run the local server on (default 5000, auto-fallback if busy)",
    )
    args = parser.parse_args()

    ensure_data_dir()
    port = _choose_port(args.port)
    if port > 0:
        timer = threading.Timer(1.0, open_browser, args=(port,))
        timer.start()
    else:
        timer = None
    try:
        app.run(port=port or 0, debug=False)
    finally:
        if timer:
            timer.cancel()


if __name__ == "__main__":
    main()
