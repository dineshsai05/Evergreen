"""
Fake Stripe — Evergreen (in-process, API-shaped data source)
============================================================

An **in-process, SDK-shaped** stand-in for Stripe — NOT a real HTTP server. It
exposes accessors shaped like the real SDK, parameterized by sim-day (`as_of`), and
returns raw Stripe-ish subscription objects over a generated timeline:

    from core.sources.fake_stripe import subscriptions
    subscriptions.list(as_of=12) -> [ {id, plan, amount, currency, status}, ... ]

Design rules (see EVERGREEN_FAKE_COMPANY.md Part 2):
- **Raw objects only.** It exposes active subscriptions with their plan/amount; it
  does NOT expose a precomputed MRR — the *watcher* derives MRR by summing amounts.
  That's what keeps the watcher's detection logic real.
- **Deterministic from (seed, as_of).** Same `FAKE_DATA_SEED` + same sim-day → the
  same objects. This is what makes a restart consistent *without persisting the
  timeline* — it is re-derived. No wall-clock, no unseeded randomness.
- **Anchored on the day-0 seed.** At `as_of=0` the active book reproduces the
  existing `core/company_data.py` figures (Starter 1150 @ $19, Pro 380 @ $49,
  Business 52 @ $149 → MRR $48,218). Free is not a Stripe subscription (no payment).
- **Mild daily variation** (slight growth + small noise) on the quiet days so the
  derived-MRR baseline has real variance — a flat baseline would make the watcher's
  z-score divide by ~0.
- **A planted churn cluster** on `PLANTED_CHURN_DAY` (default 12): ~300 Starter
  subscriptions drop out, cutting MRR ~12% — a genuine change for the watcher to catch.
- **No judgment, no thresholds here.** It returns what's true on a day; the watcher
  decides whether that's a change worth firing.

Swappable for real Stripe later by replacing this backing layer — not the watcher.
`amount` is in whole dollars (matching `company_data.py`), not Stripe cents.
"""

import os
import random

from core.company_data import PLANS

_SEED = int(os.getenv("FAKE_DATA_SEED", "42"))
_PLANTED_CHURN_DAY = int(os.getenv("PLANTED_CHURN_DAY", "12"))
_PLANTED_STARTER_CHURN = int(os.getenv("PLANTED_STARTER_CHURN", "300"))


def _rng(*parts) -> random.Random:
    """A fresh RNG seeded deterministically by (global seed, *parts)."""
    return random.Random("|".join(str(p) for p in (_SEED, *parts)))


def _daily_delta(plan_name: str, base: int, day: int) -> int:
    """Mild per-day change in a plan's active count: small noise with a slight
    positive bias (gentle growth), scaled to the plan's size. Deterministic per
    (seed, plan, day) so the timeline re-derives identically."""
    r = _rng("delta", plan_name, day)
    low = -(base // 500 + 1)
    high = base // 250 + 1   # high magnitude > low ⇒ slight net growth + variance
    return r.randint(low, high)


def _planted_churn(plan_name: str, day: int) -> int:
    """The one-time planted churn cluster: ~300 Starter cancellations on the
    planted day. Zero on every other day / plan."""
    if plan_name == "Starter" and day == _PLANTED_CHURN_DAY:
        return _PLANTED_STARTER_CHURN
    return 0


def _active_count(plan_name: str, base: int, as_of: int) -> int:
    """Active subscriptions for a plan as of a sim-day: the day-0 base, plus the
    accumulated mild daily drift, minus any planted churn that has occurred."""
    count = base
    for day in range(1, as_of + 1):
        count += _daily_delta(plan_name, base, day)
        count -= _planted_churn(plan_name, day)
    return max(count, 0)


class _Subscriptions:
    """Stripe-shaped `subscriptions` accessor."""

    def list(self, as_of: int, status: str = "active") -> list[dict]:
        """Return the active subscription book as of sim-day `as_of`. Only paying
        plans are subscriptions (Free is not). Each item is a raw, Stripe-ish dict;
        the caller derives MRR by summing `amount` over active items."""
        if status != "active":
            return []  # only the active book is modeled for now
        subs: list[dict] = []
        for plan in PLANS:
            if plan["mrr"] <= 0:
                continue  # Free is not a paid Stripe subscription
            n = _active_count(plan["name"], plan["customers"], as_of)
            for i in range(n):
                subs.append(
                    {
                        "id": f"sub_{plan['name'].lower()}_{i}",
                        "plan": plan["name"],
                        "amount": plan["price"],   # whole dollars (matches company_data)
                        "currency": "usd",
                        "status": "active",
                    }
                )
        return subs


# Module-level singleton, used like the real SDK: fake_stripe.subscriptions.list(...)
subscriptions = _Subscriptions()
