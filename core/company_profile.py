"""
Company profile — Evergreen
===========================

The company's IDENTITY and WATCHLIST — the first-class object the whole system was
missing. This is the keystone all three tiers read so they reason about *this*
business rather than from generic LLM priors:

- the **watcher** filters against it ("is this signal in our world?"),
- the **orchestrator** triages against it ("does a move by THIS competitor / a breach
  of THESE thresholds matter?"),
- the **specialists** ground their analysis in who the company is.

Separation of concerns (one source of truth each, no overlap):
- `core/company_profile.py` (this file) = IDENTITY (slow-changing: who we are, who we
  compete with, what counts as "a move worth noticing").
- `core/company_data.py` = the NUMBERS (the day-0 financial seed the specialists read,
  and later the anchor for the time-varying source).

Scope rule: a fact belongs here only if a watcher needs it to filter or the
orchestrator/specialists need it to ground. Keep it lean so it stays high-signal.

Thresholds are env-overridable so detection sensitivity can be tuned without code.
"""

import os

COMPANY = {
    "name": "Quillo",
    "what": "SaaS form & survey builder",
    "icp": "SMB teams and non-technical operators building forms, surveys, and lead-capture pages",
    "segments": ["Free", "Starter", "Pro", "Business"],
    # Tiered watchlist — the keystone for relevance + materiality. A move by a MAJOR
    # competitor is far more likely material than one by a MINOR competitor.
    "competitors": {
        "major": ["Typeform"],
        "minor": ["FormFly", "Jotform", "Google Forms", "Tally"],
    },
    "category_keywords": ["form builder", "survey tool", "AI form", "lead capture"],
}

# "A move worth noticing" — env-overridable so watchers can be tuned without code.
WATCH_THRESHOLDS = {
    "mrr_drop_pct": float(os.getenv("MRR_DROP_PCT", "0.10")),  # |%Δ| vs trailing mean
    "mrr_z": float(os.getenv("MRR_Z", "3.0")),                 # z-score confirmation
}


def profile_summary() -> str:
    """A short, high-signal identity + watchlist string for injection into agent
    prompts. Deliberately names no financial figures (those live in company_data,
    the single source of truth for numbers) to avoid drift."""
    c = COMPANY
    major = ", ".join(c["competitors"]["major"])
    minor = ", ".join(c["competitors"]["minor"])
    return (
        f"{c['name']} is a {c['what']} for {c['icp']} "
        f"(plans: {', '.join(c['segments'])}). "
        f"Major/direct competitor: {major}. Minor competitors: {minor}. "
        f"Category: {', '.join(c['category_keywords'])}."
    )
