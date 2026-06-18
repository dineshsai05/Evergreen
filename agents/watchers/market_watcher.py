"""
Market Watcher  --  Evergreen
=============================

A standing, LLM-free detector and the autonomous event source for the room. It is
driven by the simulated clock (`clock/sim_clock.py`): on each new sim-day it checks
its SCHEDULE and, if a signal is due that day, POSTs it into the Evergreen room
@mentioning the Orchestrator. On days with nothing scheduled it stays silent
(watchers don't chatter). The Orchestrator then judges materiality.

Design notes
------------
* Watchers are dumb: detection only, no reasoning. Materiality lives in the
  Orchestrator, so the watcher just reports what it "sees".
* Send-only over REST: a REST-only integration can SEND but not RECEIVE; a watcher
  never needs to listen, so no WebSocket, no SDK, no model.
* Clock-driven + fire-once: an event for sim-day N fires only when the clock first
  crosses into day N. The clock persists the current day, so after a restart it
  resumes at the persisted day and already-fired days are NOT replayed — the
  watcher's change-detection discipline (only fire on genuinely new).
* Env-driven, like the other agents; nothing hardcoded.

Run it (from the project root, AFTER the orchestrator + specialists are up and
connected — there is no offline mention queue):

    uv run python -m agents.watchers.market_watcher

Requires in .env:
    EVERGREEN_ROOM_ID=<the chat room's uuid>
    MARKET_WATCHER_API_KEY=<the Market Watcher agent's api key>
    ORCHESTRATOR_NAME=Orchestrator        # display name of the orchestrator in the room
    SIM_SECONDS_PER_DAY=5                  # real seconds per sim-day (clock config)
    SIM_START_DAY=1                        # first sim-day (clock config)

The Market Watcher and the Orchestrator must both be participants in the room.
"""

import os
import sys
from pathlib import Path

import httpx

from clock.sim_clock import SimClock


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


# --------------------------------------------------------------------------- #
# The watcher's scheduled feed, keyed by sim-day. Edit freely.
# Day 3 is a deliberately minor signal (to show the materiality gate ignore it);
# day 12 is the real competitor move (to trigger convene -> assess -> escalate).
# --------------------------------------------------------------------------- #
SCHEDULE: dict[int, tuple[str, str]] = {
    3: (
        "market",
        "A minor competitor, FormFly, pushed a small UI refresh and some "
        "marketing copy changes this week.",
    ),
    12: (
        "market",
        "Competitor Typeform just announced a 30% price cut on their Starter "
        "plan plus a new AI form-building feature.",
    ),
}


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
    if isinstance(participants, dict):
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


def post_signal(client: httpx.Client, orchestrator: dict, text: str, sim_day: int) -> None:
    # Stamp the sim-day into the (human-readable) content so it's visible in the
    # transcript / audit trail without relying on message-metadata API specifics.
    content = f"@{orchestrator['name']} [event from market-watcher · sim-day {sim_day}] {text}"
    body = {"message": {"content": content, "mentions": [orchestrator]}}
    r = client.post(f"{API}/chats/{ROOM_ID}/messages", headers=_headers(), json=body)
    r.raise_for_status()


# --------------------------------------------------------------------------- #
# Main loop — clock-driven
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

    clock = SimClock()

    with httpx.Client(timeout=30) as client:
        print(f"[watcher] connected as: {whoami(client)}")

        orchestrator = resolve_orchestrator(client)
        if not orchestrator:
            sys.exit(
                f"[watcher] could not find '{ORCH_NAME}' among room participants. "
                "Make sure both the Market Watcher and the Orchestrator are in the room."
            )
        print(
            f"[watcher] reporting to {orchestrator['name']} ({orchestrator['id']}); "
            f"{clock.seconds_per_day:g}s = 1 sim-day; resuming at day {clock.current_day()}; "
            f"scheduled days: {sorted(SCHEDULE)}"
        )

        # tick() resumes after the persisted day, so already-fired days never replay.
        for day in clock.tick():
            scheduled = SCHEDULE.get(day)
            if not scheduled:
                print(f"[watcher] sim-day {day}: all quiet")
                continue
            label, text = scheduled
            print(f"[watcher] sim-day {day}: emitting '{label}' signal -> {ORCH_NAME}")
            try:
                post_signal(client, orchestrator, text, day)
                print("[watcher] posted.")
            except httpx.HTTPStatusError as exc:
                print(
                    f"[watcher] POST failed: {exc.response.status_code} "
                    f"{exc.response.text}"
                )


if __name__ == "__main__":
    main()
