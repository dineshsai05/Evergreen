"""
Simulated clock — Evergreen
===========================

Real scheduling infrastructure, not a demo prop. It maps real seconds to
"sim-days" so the room's long-running, time-driven behavior is visible in a short
run, and it PERSISTS the current sim-day so a restart resumes instead of resetting
to zero. The same seam later drives real scheduled beats (weekly review, renewal
day, month-end) — so it stays a day counter, not a generic cron.

Config (env):
    SIM_SECONDS_PER_DAY    real seconds per sim-day (default 5)
    SIM_START_DAY          first sim-day to enter (default 1)
    SIM_CLOCK_STATE_FILE   where the sim-day is persisted (default clock/clock_state.json)

Persistence model: `clock_state.json` stores the LAST sim-day reached. A fresh
start begins at SIM_START_DAY-1, so the first day yielded by tick() is
SIM_START_DAY. A restart loads the persisted day and yields only days AFTER it —
so a scheduled event that already fired on, say, day 12 is never replayed (this is
the watcher's fire-once / change-detection discipline). No secrets are written.

This module is intentionally sync (stdlib only): the Market Watcher that consumes
it is a dependency-light, send-only REST script. The advance/persist logic is
transport-agnostic, so an async consumer can wrap `current_day()` later.
"""

import json
import os
import time
from collections.abc import Iterator
from pathlib import Path

DEFAULT_STATE_FILE = "clock/clock_state.json"


def _default_state_path() -> Path:
    return Path(os.getenv("SIM_CLOCK_STATE_FILE", DEFAULT_STATE_FILE))


def read_current_day(default=0):
    """Best-effort read of the persisted sim-day for processes that only need to
    stamp the current day (e.g. the orchestrator) without running the clock.
    Returns `default` if the state file is missing or unreadable."""
    try:
        return int(json.loads(_default_state_path().read_text())["current_day"])
    except (FileNotFoundError, KeyError, ValueError, TypeError, json.JSONDecodeError):
        return default


class SimClock:
    """Advances sim-days in real time and persists the current day across restarts."""

    def __init__(self, seconds_per_day=None, start_day=None, state_path=None):
        self.seconds_per_day = float(
            seconds_per_day
            if seconds_per_day is not None
            else os.getenv("SIM_SECONDS_PER_DAY", "5")
        )
        self.start_day = int(
            start_day if start_day is not None else os.getenv("SIM_START_DAY", "1")
        )
        self.state_path = Path(state_path) if state_path else _default_state_path()
        self._day = self._load()

    def _load(self) -> int:
        try:
            return int(json.loads(self.state_path.read_text())["current_day"])
        except (FileNotFoundError, KeyError, ValueError, TypeError, json.JSONDecodeError):
            # No prior state: start one BELOW start_day so the first tick yields it.
            return self.start_day - 1

    def _persist(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps({"current_day": self._day}))

    def current_day(self) -> int:
        """The last sim-day reached (resumed from disk on restart)."""
        return self._day

    def tick(self) -> Iterator[int]:
        """Yield each new sim-day as real time advances, forever. Sleeps one
        sim-day, advances, persists, then yields. Resumes from the persisted day
        after a restart, so already-passed days are not re-yielded (no replay)."""
        while True:
            time.sleep(self.seconds_per_day)
            self._day += 1
            self._persist()
            yield self._day
