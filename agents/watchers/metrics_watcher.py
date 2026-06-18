"""
Metrics Watcher — Evergreen (the first REAL watcher)
====================================================

A standing, LLM-free detector for internal numeric signals. Unlike the Market
watcher (which posts a scripted external feed), this one is *real*: each sim-day it
pulls raw subscriptions from the data source, **derives MRR itself**, holds a rolling
baseline, and fires only when the number genuinely moves beyond its normal range. It
is deterministic, so a restart re-derives the same timeline.

Funnel discipline (the line that must not be crossed): it **detects/filters, never
judges**. It emits a raw magnitude ("MRR fell 11% vs trailing mean, z=-22") — never a
severity, threat level, or recommendation. Materiality is the orchestrator's job.

Swap the backing layer, not the watcher: the source is injected (defaults to the
in-process fake Stripe); pointing it at real Stripe later is a one-line swap.

Run from the project root (after the orchestrator + specialists are connected):
    uv run python -m agents.watchers.metrics_watcher

Env:
    METRICS_WATCHER_API_KEY   (falls back to MARKET_WATCHER_API_KEY) — Band agent key
    EVERGREEN_ROOM_ID, ORCHESTRATOR_NAME
    SIM_SECONDS_PER_DAY, SIM_START_DAY   (clock)
    METRICS_BASELINE_DAYS=7              (rolling window; < planted day so it's full)
    METRICS_MIN_STDDEV_PCT=0.005         (min-stddev floor as a fraction of the mean)
    METRICS_STATE_FILE=metrics_watcher_state.json  (persisted fired/dedup set)
    MRR_DROP_PCT / MRR_Z  (detection thresholds, from the company profile)
"""

import json
import logging
import os
import statistics
import sys
from collections import Counter
from pathlib import Path

import httpx

from clock.sim_clock import SimClock
from core.company_profile import WATCH_THRESHOLDS
from core.events import Event
from core.sources.fake_stripe import subscriptions as default_source

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("evergreen.metrics_watcher")


# --------------------------------------------------------------------------- #
# Config (env-driven)
# --------------------------------------------------------------------------- #
def _load_env() -> None:
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
WATCHER_API_KEY = os.getenv("METRICS_WATCHER_API_KEY") or os.getenv("MARKET_WATCHER_API_KEY")
ROOM_ID = os.getenv("EVERGREEN_ROOM_ID")
ORCH_NAME = os.getenv("ORCHESTRATOR_NAME", "Orchestrator")
BASELINE_DAYS = int(os.getenv("METRICS_BASELINE_DAYS", "7"))
MIN_STDDEV_PCT = float(os.getenv("METRICS_MIN_STDDEV_PCT", "0.005"))
STATE_FILE = os.getenv("METRICS_STATE_FILE", "metrics_watcher_state.json")


# --------------------------------------------------------------------------- #
# Detection core (transport-free, unit-testable)
# --------------------------------------------------------------------------- #
class MetricsWatcher:
    """Derives MRR from the source, baselines it, and detects genuine moves."""

    def __init__(
        self,
        source=default_source,
        baseline_days: int = BASELINE_DAYS,
        min_stddev_pct: float = MIN_STDDEV_PCT,
        drop_pct: float = WATCH_THRESHOLDS["mrr_drop_pct"],
        z_thresh: float = WATCH_THRESHOLDS["mrr_z"],
        state_file: str = STATE_FILE,
    ):
        self.source = source
        self.window = baseline_days
        self.min_stddev_pct = min_stddev_pct
        self.drop_pct = drop_pct          # fraction, e.g. 0.10
        self.z_thresh = z_thresh
        self.state_path = Path(state_file)
        self._fired: set[str] = self._load_fired()

    # --- derivation (real: the watcher computes MRR, never handed it) ---
    def _derive(self, as_of: int) -> dict:
        subs = [s for s in self.source.list(as_of=as_of) if s["status"] == "active"]
        mrr = sum(s["amount"] for s in subs)
        return {"mrr": mrr, "active": len(subs), "by_plan": dict(Counter(s["plan"] for s in subs))}

    def _baseline_mrrs(self, as_of: int) -> list[float]:
        days = [d for d in range(as_of - self.window, as_of) if d >= 0]
        return [self._derive(d)["mrr"] for d in days]

    # --- fire-once state ---
    def _load_fired(self) -> set[str]:
        try:
            return set(json.loads(self.state_path.read_text()).get("fired", []))
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            return set()

    def _persist_fired(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps({"fired": sorted(self._fired)}))

    # --- the detector ---
    def evaluate(self, sim_day: int) -> Event | None:
        """Return an Event if `sim_day` is a genuine, not-yet-fired breach, else None."""
        baseline = self._baseline_mrrs(sim_day)
        if len(baseline) < self.window:
            return None  # baseline not full yet — never fire on a partial window

        cur = self._derive(sim_day)
        now = cur["mrr"]
        mean = statistics.mean(baseline)
        if mean <= 0:
            return None
        sd = statistics.pstdev(baseline)
        floor = max(sd, mean * self.min_stddev_pct)  # min-stddev floor: no infinite z
        pct = (now - mean) / mean              # signed fraction
        z = (now - mean) / floor

        # %Δ-vs-trailing-mean is primary; z-score confirms.
        if abs(pct) < self.drop_pct or abs(z) < self.z_thresh:
            return None

        dedup_key = f"mrr_drop:day-{sim_day}"
        if dedup_key in self._fired:
            return None
        self._fired.add(dedup_key)
        self._persist_fired()

        verb = "fell" if pct < 0 else "rose"
        observation = (
            f"MRR {verb} {abs(pct) * 100:.0f}% vs its {self.window}-day trailing "
            f"average (z={z:.1f}): ${mean:,.0f} → ${now:,.0f}."
        )
        return Event(
            source="stripe",
            signal_type="mrr_drop" if pct < 0 else "mrr_spike",
            observation=observation,
            magnitude={
                "metric": "mrr",
                "prev": round(mean),
                "now": now,
                "pct": round(pct * 100, 1),
                "z": round(z, 1),
                "by_plan_active": cur["by_plan"],
            },
            dedup_key=dedup_key,
            sim_day=sim_day,
            watcher="metrics",
        )


# --------------------------------------------------------------------------- #
# Band REST transport (mirrors the Market watcher; send-only)
# --------------------------------------------------------------------------- #
def _headers() -> dict[str, str]:
    return {"X-API-Key": WATCHER_API_KEY, "Content-Type": "application/json"}


def _data(payload):
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def resolve_orchestrator(client: httpx.Client) -> dict | None:
    r = client.get(f"{API}/chats/{ROOM_ID}/participants", headers=_headers())
    r.raise_for_status()
    participants = _data(r.json())
    if isinstance(participants, dict):
        participants = participants.get("data", [])
    for p in participants:
        if str(p.get("name", "")).lower() == ORCH_NAME.lower():
            return {k: v for k, v in {"id": p.get("id"), "handle": p.get("handle"),
                                      "name": p.get("name")}.items() if v}
    return None


def post_event(client: httpx.Client, orchestrator: dict, event: Event) -> None:
    body = {"message": {"content": event.render(orchestrator["name"]),
                        "mentions": [orchestrator]}}
    r = client.post(f"{API}/chats/{ROOM_ID}/messages", headers=_headers(), json=body)
    r.raise_for_status()


# --------------------------------------------------------------------------- #
# Main loop — clock-driven (fully wired in Step D; transport exercised in Step G)
# --------------------------------------------------------------------------- #
def main() -> None:
    missing = [n for n, v in [("METRICS_WATCHER_API_KEY/MARKET_WATCHER_API_KEY", WATCHER_API_KEY),
                              ("EVERGREEN_ROOM_ID", ROOM_ID)] if not v]
    if missing:
        sys.exit(f"[metrics] missing required env: {', '.join(missing)}")

    clock = SimClock()
    watcher = MetricsWatcher()

    with httpx.Client(timeout=30) as client:
        orchestrator = resolve_orchestrator(client)
        if not orchestrator:
            sys.exit(f"[metrics] could not find '{ORCH_NAME}' in the room participants.")
        logger.info(
            "Metrics watcher up; reporting to %s; %gs/sim-day; resuming at day %d; "
            "baseline=%d days; thresholds pct=%.0f%% z=%.1f",
            orchestrator["name"], clock.seconds_per_day, clock.current_day(),
            watcher.window, watcher.drop_pct * 100, watcher.z_thresh,
        )
        for day in clock.tick():
            event = watcher.evaluate(day)
            if event is None:
                logger.info("sim-day %d: no metrics signal", day)
                continue
            logger.info("sim-day %d: FIRING %s — %s", day, event.signal_type, event.observation)
            try:
                post_event(client, orchestrator, event)
                logger.info("sim-day %d: posted.", day)
            except httpx.HTTPStatusError as exc:
                logger.error("post failed: %s %s", exc.response.status_code, exc.response.text)


if __name__ == "__main__":
    main()
