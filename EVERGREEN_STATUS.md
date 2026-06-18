# Evergreen — Status (done / remaining)

> Single at-a-glance tracker. Detailed source of truth per area:
> `EVERGREEN_CONTEXT.md` (state + Band facts), `EVERGREEN_NEXT.md` (Steps 1–3),
> `EVERGREEN_FAKE_COMPANY.md` + `EVERGREEN_NEXT_STEPS_2.md` (Fake Company A–G),
> `EVERGREEN_WATCHERS.md` (real-watchers / Step-4 design). Last updated 2026-06-19.

The three pillars (persistent · event-driven · institutional memory) are all proven
end-to-end live against the litmus test. The MVP is complete; remaining work is
breadth/polish and the real-watcher upgrade.

---

## ✅ Done (built + verified live)

**Core coordination & cascade**
- Orchestrator (LangGraph, gpt-4o): materiality triage, dynamic convening, stand-down,
  one founder brief per event, `record_decision`.
- Fan-out: one event → multiple specialists (e.g. churn → Finance + Retention),
  wait-for-all, then a single synthesized brief.
- Specialists on a shared base (`agents/specialists/_base.py`): **recipient forced to
  the orchestrator in code**, Band's conflicting prompt instructions suppressed,
  company-identity + as-of data injected per convene.
  - Competitive Analysis (persona), Finance / Retention / Hiring (grounded, pre-fetch).
- Hardening: the founder brief goes ONLY to the human; never a watcher/specialist; if
  no human is present, record silently.

**Pillar 1 — Persistent**
- Wall-time-anchored simulated clock (`clock/sim_clock.py`), shared across processes;
  full kill/restart resumes the sim-day and preserves memory with **no event replay**.

**Pillar 2 — Event-driven (real detection)**
- Fake Company workstream **A–G** done: company profile + watchlist; in-process
  `as_of` fake Stripe (deterministic, planted day-12 churn); **real Metrics watcher**
  that derives MRR itself and fires `mrr_drop` only on a genuine breach (no judgment);
  event contract (`core/events.py`); clock-as-driver; specialist as-of coherence.
- Market watcher (scripted external feed) remains for competitor events.
- Two distinct watcher identities on Band (Market = external, Metrics = internal).

**Pillar 3 — Institutional memory**
- `record_decision` + `recall_decisions` (keyword overlap + recency, relevance-gated);
  decisions stamped with `sim_day` + event provenance (`source`/`signal_type`);
  recall answers "why did we flag X?" cross-process after a restart, no convening.

**Project infra**
- Env-driven config; secrets gitignored (`.env`, `agent_config.yaml`) with `.example`
  templates; git repo + push-after-every-commit; README; this status doc.

---

## 🔜 Remaining

**ACTIVE NEXT — Real watchers** (design: `EVERGREEN_WATCHERS.md`)
- **Market watcher on REAL external sources** — the one that maps cleanly to a fictional
  company, because the *competitors are real* (Typeform, Jotform, Google Forms, Tally).
  Build: connector (news API / RSS / competitor page-diff) → change-detection/dedup →
  relevance gate (keyword/watchlist or LLM) → emit the existing event contract. Decisions
  pending: which source first, and deterministic vs LLM relevance gate.
- (Metrics is already "real" via its source — real Stripe is a one-line backing swap if
  ever there's a real account. People & Voice needs real customer data a fictional
  company lacks — deferred.)

**Soon / when a 2nd real watcher exists**
- **Watcher framework** (a `_base` for watchers) — scheduling, state, dedup, relevance,
  emit, logging — so new watchers are cheap (like `_base.py` did for specialists).

**Deferred (out of current scope)**
- Push/webhook ingestion (Stripe/Slack), real wall-clock scheduler for production.
- Scheduled beats (weekly review / renewal / month-end — "a watcher whose source is the calendar").
- Persistent LangGraph checkpointer (SQLite) so in-flight investigations also survive restart.
- Embedding-based `recall_decisions` (the `_score` seam is already isolated).
- Alerting channels (email/Slack/SMS) in addition to the room.

**Admin / cleanup**
- Partner-prize submission writeup (AI/ML API is visibly in use).
- Delete the stale generic `COMPANY` dict in `core/company_data.py` (unused; identity
  is canonical in `company_profile.py`).
- Reset runtime state before a clean demo: `rm evergreen_memory.jsonl
  clock/clock_state.json metrics_watcher_state.json`.
- Delete stale Band test rooms; keep one.
