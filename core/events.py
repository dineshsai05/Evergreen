"""
Event contract — Evergreen
==========================

The structured signal a watcher emits to the orchestrator. It carries an
**observation + provenance** and deliberately **no verdict** — no severity, no
threat level, no recommendation. Materiality is the orchestrator's job; meaning is
the specialist's (funnel discipline, EVERGREEN_NEXT.md §A).

Delivery is backward-compatible: `render()` produces a human-readable line (which the
orchestrator's existing plain-string handling already understands) plus a compact
`<event>{…json…}</event>` tail carrying the structured fields for any consumer that
wants provenance. (If Band's REST message gains first-class structured metadata,
prefer that — but only after confirming it in the docs; the readable line + tail
needs no such assumption.)
"""

import json
from dataclasses import asdict, dataclass, field


@dataclass
class Event:
    source: str                 # where the data came from, e.g. "stripe", "competitor:typeform"
    signal_type: str            # stable enum the orchestrator routes on, e.g. "mrr_drop"
    observation: str            # human-readable, FACTUAL only (no severity/recommendation)
    dedup_key: str              # so the same condition isn't re-fired (e.g. "mrr_drop:day-12")
    sim_day: int                # ties the event to the clock/memory timeline
    magnitude: dict = field(default_factory=dict)   # raw numbers (metrics); empty for qualitative
    evidence: list = field(default_factory=list)     # links/ids a specialist can cite, e.g. [url]
    watcher: str = "metrics"    # which watcher family detected it

    def to_dict(self) -> dict:
        return asdict(self)

    def render(self, orchestrator_name: str = "Orchestrator") -> str:
        """The room post: a readable line (backward-compatible) + a parseable JSON
        tail. Contains observation + raw magnitude/evidence only — never a judgment."""
        tail = json.dumps(self.to_dict(), separators=(",", ":"))
        ev = f" ({'; '.join(self.evidence)})" if self.evidence else ""
        return (
            f"@{orchestrator_name} [{self.watcher} · sim-day {self.sim_day}] "
            f"{self.observation}{ev}\n<event>{tail}</event>"
        )
