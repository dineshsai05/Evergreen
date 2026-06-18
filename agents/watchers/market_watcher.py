"""
Market Watcher  --  Evergreen
=============================

A standing, LLM-free detector. It is the autonomous event source that replaces
you hand-posting events into the room.

On each simulated-day tick it pulls the next signal from its feed and posts it
into the Evergreen room, @mentioning the Orchestrator. The Orchestrator then
judges materiality (noise -> ignored; material -> convene a specialist, etc.).

Design notes
------------
* Watchers are dumb: detection only, no reasoning. Materiality lives in the
  Orchestrator, so the watcher just reports what it "sees".
* Send-only: Band's docs confirm a REST-only integration can SEND commands but
  cannot RECEIVE. A watcher never needs to listen, so it needs no WebSocket,
  no SDK, and no model -- just the Agent REST API.
* Env-driven, like the other agents, so nothing is hardcoded.

Run it (from the project root, with the orchestrator + specialist already up in
their own terminals):

    uv run python agents/watchers/market_watcher.py

Requires these in .env:

    EVERGREEN_ROOM_ID=<the chat room's uuid>
    MARKET_WATCHER_API_KEY=<the Market Watcher agent's api key>
    ORCHESTRATOR_NAME=Orchestrator        # display name of the orchestrator in the room
    WATCHER_TICK_SECONDS=20               # 1 simulated "day" = 20 real seconds

The Market Watcher must be created on Band (a sibling agent under your account)
and added to the room as a participant before running this.
"""

import os
import sys
import time
from pathlib import Path

import httpx


# --------------------------------------------------------------------------- #
# Config (env-driven). Mirrors the THENVOI_/BAND_ fallback the other agents use.
# --------------------------------------------------------------------------- #
def _load_env() -> None:
    """Load .env without forcing a python-dotenv dependency."""
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv()
        return
    except Exception:
        pass
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_env()

REST_URL = os.getenv(
    "THENVOI_REST_URL", os.getenv("BAND_REST_URL", "https://app.band.ai")
).rstrip("/")
API = f"{REST_URL}/api/v1/agent"

WATCHER_API_KEY = os.getenv("MARKET_WATCHER_API_KEY")
ROOM_ID = os.getenv("EVERGREEN_ROOM_ID")
ORCH_NAME = os.getenv("ORCHESTRATOR_NAME", "Orchestrator")
TICK_SECONDS = int(os.getenv("WATCHER_TICK_SECONDS", "20"))


# --------------------------------------------------------------------------- #
# The watcher's scripted feed.
# Edit freely. The Orchestrator decides which of these matter -- the first is
# deliberately minor (to show the materiality gate ignore it), the second is the
# real competitor move (to trigger the convene -> assess -> escalate cascade).
# --------------------------------------------------------------------------- #
FEED: list[tuple[str, str]] = [
    (
        "market",
        "A minor competitor, FormFly, pushed a small UI refresh and some "
        "marketing copy changes this week.",
    ),
    (
        "market",
        "Competitor Typeform just announced a 30% price cut on their Starter "
        "plan plus a new AI form-building feature.",
    ),
]


# --------------------------------------------------------------------------- #
# Band Agent REST helpers
# --------------------------------------------------------------------------- #
def _headers() -> dict[str, str]:
    return {"X-API-Key": WATCHER_API_KEY, "Content-Type": "application/json"}


def _data(payload):
    """Tolerate both {'data': ...} envelopes and bare bodies."""
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def whoami(client: httpx.Client) -> str:
    try:
        r = client.get(f"{API}/me", headers=_headers())
        if r.status_code == 200:
            return _data(r.json()).get("name", "?")
        return f"(status {r.status_code})"
    except Exception as exc:  # noqa: BLE001
        return f"(error: {exc})"


def resolve_orchestrator(client: httpx.Client) -> dict | None:
    """Find the orchestrator in the room's participant list by display name."""
    r = client.get(f"{API}/chats/{ROOM_ID}/participants", headers=_headers())
    r.raise_for_status()
    participants = _data(r.json())
    if isinstance(participants, dict):  # in case it's {'data': [...]} nested oddly
        participants = participants.get("data", [])
    for p in participants:
        if str(p.get("name", "")).lower() == ORCH_NAME.lower():
            return {
                k: v
                for k, v in {
                    "id": p.get("id"),
                    "handle": p.get("handle"),
                    "name": p.get("name"),
                }.items()
                if v
            }
    return None


def post_signal(client: httpx.Client, orchestrator: dict, text: str) -> None:
    content = f"@{orchestrator['name']} [event from market-watcher] {text}"
    body = {"message": {"content": content, "mentions": [orchestrator]}}
    r = client.post(f"{API}/chats/{ROOM_ID}/messages", headers=_headers(), json=body)
    r.raise_for_status()


# --------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------- #
def main() -> None:
    missing = [
        name
        for name, val in [
            ("MARKET_WATCHER_API_KEY", WATCHER_API_KEY),
            ("EVERGREEN_ROOM_ID", ROOM_ID),
        ]
        if not val
    ]
    if missing:
        sys.exit(f"[watcher] missing required env: {', '.join(missing)}")

    with httpx.Client(timeout=30) as client:
        print(f"[watcher] connected as: {whoami(client)}")

        orchestrator = resolve_orchestrator(client)
        if not orchestrator:
            sys.exit(
                f"[watcher] could not find '{ORCH_NAME}' among room participants. "
                "Make sure both the Market Watcher and the Orchestrator are added "
                "to the room."
            )
        print(
            f"[watcher] reporting to {orchestrator['name']} "
            f"({orchestrator['id']}); 1 day = {TICK_SECONDS}s"
        )

        day = 0
        for label, text in FEED:
            day += 1
            print(f"[watcher] --- simulated day {day}: waiting {TICK_SECONDS}s ---")
            time.sleep(TICK_SECONDS)
            print(f"[watcher] day {day}: emitting '{label}' signal -> {ORCH_NAME}")
            try:
                post_signal(client, orchestrator, text)
                print("[watcher] posted.")
            except httpx.HTTPStatusError as exc:
                print(
                    f"[watcher] POST failed: {exc.response.status_code} "
                    f"{exc.response.text}"
                )

        print("[watcher] feed exhausted; standing by (Ctrl-C to stop).")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n[watcher] stopped.")


if __name__ == "__main__":
    main()