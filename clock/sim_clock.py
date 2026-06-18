"""
Simulated clock — Evergreen (wall-time-anchored)
================================================

Real scheduling infrastructure: it maps real seconds to "sim-days" so the room's
long-running, time-driven behavior is visible in a short run, and it survives a
restart. It is **wall-time-anchored** so that ANY number of processes (the Market
watcher, the Metrics watcher, future scheduled beats) share ONE consistent sim-day
with no write races: the sim-day is *computed from elapsed wall time against a shared
anchor*, never from a mutable counter each process increments.

State (`clock_state.json`) holds a write-once anchor:
`{anchor_epoch, anchor_day, seconds_per_day}`.
- The first process to start (when the file is absent) creates it:
  `anchor_day = SIM_START_DAY - 1`, `anchor_epoch = now`, `seconds_per_day` from env.
- Every later process — and every restart — READS that anchor (including its
  `seconds_per_day`) and computes the same current day. So concurrent processes
  always agree even if their own `SIM_SECONDS_PER_DAY` env differs, and a restart
  resumes (it does not reset to 0). The persisted rate is the single source of truth.

  current_day = anchor_day + floor((now - anchor_epoch) / seconds_per_day)

Semantics to know: sim-time *flows with wall-time*, so downtime advances sim-days (a
quick restart resumes at ≈ the same day). To start a fresh demo at SIM_START_DAY,
delete `clock_state.json`. Legacy `{current_day: N}` files are migrated to an anchor
that resumes at day N.

Config (env): SIM_SECONDS_PER_DAY (default 5), SIM_START_DAY (default 1),
SIM_CLOCK_STATE_FILE (default clock/clock_state.json). No secrets are written.
"""

import json
import os
import time
from collections.abc import Iterator
from pathlib import Path

DEFAULT_STATE_FILE = "clock/clock_state.json"


def _default_state_path() -> Path:
    return Path(os.getenv("SIM_CLOCK_STATE_FILE", DEFAULT_STATE_FILE))


def _seconds_per_day() -> float:
    return float(os.getenv("SIM_SECONDS_PER_DAY", "5"))


def _compute_day(anchor_epoch: float, anchor_day: int, seconds_per_day: float) -> int:
    elapsed = max(0.0, time.time() - anchor_epoch)
    return int(anchor_day + elapsed // seconds_per_day)


def read_current_day(default=0):
    """Best-effort current sim-day for processes that only need to stamp it (e.g. the
    orchestrator) without running the clock. Reads the shared anchor — including its
    persisted `seconds_per_day` — and computes the day from wall time, so it agrees
    with the clock owner regardless of this process's own env. Returns `default` if
    no valid anchor exists."""
    try:
        d = json.loads(_default_state_path().read_text())
        spd = float(d.get("seconds_per_day", _seconds_per_day()))
        return _compute_day(float(d["anchor_epoch"]), int(d["anchor_day"]), spd)
    except (FileNotFoundError, KeyError, ValueError, TypeError, json.JSONDecodeError):
        return default


class SimClock:
    """Advances sim-days in real time against a shared, persisted anchor."""

    def __init__(self, seconds_per_day=None, start_day=None, state_path=None):
        self.seconds_per_day = (
            float(seconds_per_day) if seconds_per_day is not None else _seconds_per_day()
        )
        self.start_day = (
            int(start_day) if start_day is not None else int(os.getenv("SIM_START_DAY", "1"))
        )
        self.state_path = Path(state_path) if state_path else _default_state_path()
        # The persisted anchor (incl. its seconds_per_day) wins, so all processes agree.
        self.anchor_epoch, self.anchor_day, self.seconds_per_day = self._load_or_create_anchor()

    def _load_or_create_anchor(self) -> tuple[float, int, float]:
        try:
            d = json.loads(self.state_path.read_text())
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            d = None
        if d and "anchor_epoch" in d and "anchor_day" in d:  # shared anchor — read it (rate too)
            spd = float(d.get("seconds_per_day", self.seconds_per_day))
            return float(d["anchor_epoch"]), int(d["anchor_day"]), spd
        if d and "current_day" in d:  # legacy format — migrate, resuming at that day
            epoch, day, spd = time.time(), int(d["current_day"]), self.seconds_per_day
            self._persist(epoch, day, spd)
            return epoch, day, spd
        # fresh: first process creates the shared, write-once anchor
        epoch, day, spd = time.time(), self.start_day - 1, self.seconds_per_day
        self._persist(epoch, day, spd)
        return epoch, day, spd

    def _persist(self, epoch: float, day: int, seconds_per_day: float) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps({"anchor_epoch": epoch, "anchor_day": day, "seconds_per_day": seconds_per_day})
        )

    def current_day(self) -> int:
        """The current sim-day, computed from elapsed wall time (shared by all readers)."""
        return _compute_day(self.anchor_epoch, self.anchor_day, self.seconds_per_day)

    def tick(self) -> Iterator[int]:
        """Yield each NEW sim-day as wall-time crosses it, forever. Starts from the
        current day (already-passed days are not replayed — so a restart resumes
        without re-firing), and catches up if several days elapse between polls."""
        last = self.current_day()
        poll = min(self.seconds_per_day, 1.0)
        while True:
            time.sleep(poll)
            cur = self.current_day()
            while last < cur:
                last += 1
                yield last
