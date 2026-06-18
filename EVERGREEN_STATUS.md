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
- **Real Market watcher** (`MODE=real`, wall-clock): polls curated REAL competitor
  sources — Typeform "What's New" (page-diff, bs4) + Jotform product feed (RSS,
  Product category) — fires once on genuine change, robots-respecting, fail-soft,
  emits the event contract with an evidence URL; detection-only (no verdict). The
  scripted feed (`MODE=scripted`) stays as the on-cue demo beat; both run alongside.
  Verified: unit + live seed against the real pages (HTTP 200, robots-allowed).
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

**Real Market watcher — DONE & cascade-verified** (Typeform page-diff + Jotform RSS;
design: `EVERGREEN_MARKET_WATCHER.md`). Unit + live-seed + **live controlled-change
cascade** all pass: a real Typeform-tier change → judged **material** → convene
Competitive Analysis → brief; a real Jotform-tier change → **not material** → recorded
silently, no convene — opposite verdicts grounded in the watchlist, with provenance.
Remaining bits:
- **Refinement:** page-diff extracts only the dated heading; extract heading + blurb so
  the orchestrator sees release detail (e.g. a price cut → also convene Finance).
- **Deferred more sources:** Google Forms & Tally "what's-new" pages (verify each first);
  pricing-page diffing for the `competitor_pricing_change` signal (JS-rendered/noisy).
- (Metrics is already "real" via its source — real Stripe is a one-line backing swap if
  ever there's a real account. People & Voice needs real customer data a fictional
  company lacks — deferred.)

**Soon / when a 3rd real watcher exists**
- **Watcher framework** (a `_base` for watchers) — scheduling, state, dedup, emit,
  logging — extract from Metrics + Market once a third would pay off (YAGNI until then).

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
