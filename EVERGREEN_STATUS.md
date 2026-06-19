# Evergreen — Project Status & Detailed Build Record

> The comprehensive record of everything built and verified. Companion docs:
> `EVERGREEN_CONTEXT.md` (architecture + hard-won Band SDK facts), `EVERGREEN_NEXT.md`
> (Steps 1–3 + working principles §A), `EVERGREEN_FAKE_COMPANY.md` +
> `EVERGREEN_NEXT_STEPS_2.md` (Fake Company A–G), `EVERGREEN_WATCHERS.md` +
> `EVERGREEN_MARKET_WATCHER.md` (real-watcher design). Last updated 2026-06-19.

## 0. Standing

Evergreen assigns an AI **room** to an **outcome** and has it own that outcome over
time — watching, waking on real events, convening specialists + humans, recording
decisions, then returning to watch. Use case: **Startup Operating System** for a
fictional SaaS form/survey builder, **Quillo**.

**All three pillars are built and proven end-to-end, live on Band:**
1. **Persistent** — survives restart (memory + sim-day resume, no event replay).
2. **Event-driven** — real detection: a watcher genuinely *derives and detects* a
   change (internal metrics + real external competitor pages), not a script.
3. **Institutional memory** — every decision recorded with rationale + provenance and
   recalled later ("why did we flag the MRR drop?"), cross-process after a restart.

Litmus test held: delete the clock or the memory and it degrades to a one-shot
pipeline — both are load-bearing. Remaining work is optional breadth/polish + the
submission writeup.

## 1. Architecture at a glance

- **Funnel (3 tiers):** Watchers (detect, by source) → Orchestrator (triage, the only
  router) → Specialists (analyze, by expertise, convened on demand, report only to the
  orchestrator). Humans (founder) and infra (memory, clock) are not agents.
- **Cross-framework:** Orchestrator on **LangGraph** (`gpt-4o`); Specialists on
  **CrewAI** (`gpt-4o-mini`). Coordination spine: **Band**. Reasoning: **AI/ML API**
  (OpenAI-compatible). Everything env-driven.
- **The one rule under all watcher work:** a watcher *filters* ("is this in our
  world?") but never *judges* ("is it important / what does it mean?"). Materiality is
  the orchestrator's; meaning is the specialist's.

---

## 2. DONE — detailed, by area

### 2.1 Orchestrator (Chief of Staff) — `agents/orchestrator.py`
- LangGraph + `gpt-4o`. Reacts only to @mentions; on each event ends with a tool call
  (never silent). Loop: judge materiality → convene specialist(s) → on reply stand each
  down → decide → record.
- **Materiality grounded in the company profile** (not generic priors): the prompt
  carries a lean Quillo identity + watchlist summary, so a **major** competitor move
  (Typeform) is material and a **minor** one (FormFly/Jotform/Google Forms/Tally) is
  not — graded against the watchlist.
- **Fan-out + wait-for-all:** an event spanning expertises convenes several specialists
  (churn → Finance + Retention; priced competitor move → Competitive Analysis +
  Finance), waits for all, then one synthesized founder brief.
- **Founder Rule + hardening:** at most one founder message per event, and it goes
  **only to the human** participant — never a watcher/specialist; if no human is in the
  room, it records silently instead of mis-addressing an agent.
- **No status spam:** never narrates ("analyzing now") and stays silent while waiting,
  even when re-pinged.
- Tools: `record_decision`, `recall_decisions` (LangChain `@tool`s).

### 2.2 Shared specialist base — `agents/specialists/_base.py`
The robustness layer every specialist runs through (so they can't drift), encoding
guarantees in **code, not prompts**:
- **Deterministic recipient:** a tools proxy rewrites every `band_send_message` to the
  orchestrator (resolved from the live participant list), regardless of what the model
  put in `mentions`. Fixes specialists addressing the founder.
- **Conflicting Band instructions suppressed:** renders the system prompt with
  `include_base_instructions=False` (module-global patch), dropping Band's
  Relaying/Activation/Delegation blocks; supplies a minimal conflict-free platform note.
- **Identity grounding:** injects the Quillo profile summary into every specialist.
- **As-of context injection:** an optional `context_provider` is recomputed per convene
  and injected into the incoming message (`PlatformMessage` is a frozen dataclass →
  `dataclasses.replace`), so time-varying specialists reflect current reality.
- `logging.basicConfig` so a specialist is never silent/undebuggable.

### 2.3 Specialists
- **Competitive Analysis** (`competitive_analysis.py`) — persona; threat assessment of
  competitor moves. No data tools.
- **Finance** (`finance.py`) — grounded. Originally tooled and **BLOCKED** (its answer
  never reached the room: Band's CrewAI adapter discards the agent's final answer; only
  `band_send_message` delivers, and the choose-able data tools gave the model a second,
  non-delivering exit). **Fixed** by pre-fetching the figures in plain Python and
  injecting them (only action left is reason + `band_send_message`). Now also reads
  **as-of** figures from the fake source for the current sim-day, so it matches what
  the watcher reported (no contradictory brief).
- **Retention** (`retention.py`) — grounded; churn/NRR/GRR/at-risk revenue; as-of
  Starter cohort from the fake source.
- **Hiring** (`hiring.py`) — grounded (static slice); pipeline/attrition/headcount.
- All four: pre-fetch-and-inject, **no choose-able data tools**, recipient forced in code.

### 2.4 Pillar 1 — Simulated clock + persistence — `clock/sim_clock.py`
- **Wall-time-anchored:** `clock_state.json` is a write-once anchor
  `{anchor_epoch, anchor_day, seconds_per_day}`; `current_day = anchor_day +
  floor((now − anchor_epoch)/seconds_per_day)`. Any number of processes share ONE
  consistent sim-day with no write races (the earlier blind-increment design broke when
  two watchers ran). The persisted `seconds_per_day` means processes agree even if
  their env rates differ (a real bug found + fixed: a decision was mis-stamped because
  the orchestrator used its own env rate).
- `tick()` yields only new days (restart resumes, no replay); legacy `{current_day}`
  migrates; public interface unchanged so watchers/`record_decision` needed no changes.
- Sim-time flows with wall-time (downtime advances days; `rm clock_state.json` resets).

### 2.5 Pillar 2 — Real detection (the Fake Company workstream, A–G)
Turned detection from a stub into something real. The company is now a queryable,
time-varying thing.
- **A — Company profile** (`core/company_profile.py`): Quillo identity + tiered
  watchlist + env-overridable `WATCH_THRESHOLDS`; `profile_summary()` injected into the
  orchestrator. Identity here; numbers stay in `company_data.py`.
- **B — In-process fake Stripe** (`core/sources/fake_stripe.py`): SDK-shaped
  `subscriptions.list(as_of=day)` returning raw subscription dicts (no precomputed MRR
  — the watcher derives it). Deterministic from `(FAKE_DATA_SEED, as_of)` so a restart
  re-derives the timeline without persisting it; anchored on the day-0 figures (MRR
  $48,218); mild seeded daily variation (so the baseline has variance); a planted ~300
  Starter churn on day 12 (≈ −12% MRR).
- **C — Event contract + Metrics watcher** (`core/events.py`,
  `agents/watchers/metrics_watcher.py`): `Event` (source/signal_type/observation/
  magnitude/dedup_key/sim_day/evidence/watcher), rendered as a readable line + a
  `<event>{json}</event>` tail (backward-compatible). The watcher pulls subscriptions,
  **derives MRR**, baselines it (rolling window rebuilt from the deterministic source),
  detects via **%Δ-vs-trailing-mean (primary) + z-score confirmation with a
  min-stddev floor**, seeds silently, dedups (fire-once, persisted), emits raw
  magnitude only.
- **D — Clock-as-driver + extended persistence:** the watcher reads the sim-day from
  the wall-anchored clock; restart resumes with no replay (see 2.4).
- **E — Specialist coherence:** identity grounding for all; Finance/Retention pre-fetch
  **as-of the event's sim-day** so their numbers match the watcher (no contradiction).
- **F — Memory provenance:** `record_decision` stamps `source`/`signal_type`;
  `recall_decisions` searches + shows provenance (`[event: stripe/mrr_drop]`).
- **G — End-to-end proof** (room `078d8912`): quiet sim-days → day-12 churn → watcher
  derives & fires `mrr_drop` → orchestrator convenes Finance + Retention → as-of
  grounded replies → one founder brief to the human → decision recorded with provenance
  (sim_day 12) → full restart resumes (no replay, memory intact) → a fresh orchestrator
  answered "why did we flag the MRR drop?" from durable memory, no convene.

### 2.6 Pillar 2 — Real Market watcher — `agents/watchers/market_watcher.py`
Detection over **real external competitor sources** (the family that maps to a fictional
company, because the competitors are real).
- **Two modes:** `MODE=real` (default, wall-clock, real sources) and `MODE=scripted`
  (the original sim-clock feed, kept as the on-cue demo beat). Both post as the Market
  Watcher; run alongside.
- **Curated sources = the watchlist (inherent relevance, no LLM gate):**
  - **Typeform** (major) — `typeform.com/whats-new` **page-diff**. (The originally
    specified help-center changelog is WAF-blocked/403; swapped to the fetchable,
    robots-allowed main-domain page — env-overridable.)
  - **Jotform** (minor) — product blog **RSS**, filtered to the Product category.
  - **Google Forms** (minor) — Workspace Updates Blogger **Atom** label feed
    (Forms-filtered → inherent relevance).
  - **Tally** (minor) — `tally.so/changelog` **page-diff** (date headings).
- **Mechanics:** identifiable User-Agent, conditional GET (ETag/Last-Modified),
  **robots.txt respected** (`urllib.robotparser`), per-source fail-soft (log + back off,
  never crash). bs4 strips nav/footer for page text; a **format-agnostic feed parser**
  handles RSS `<item>` AND Atom `<entry>` (stdlib ElementTree, no feedparser/lxml).
- **Page-diff = heading + blurb:** the dated release **heading** is the stable change
  key (blurb edits don't false-fire), but the **blurb** is surfaced in the observation
  so a pricing line routes to Finance, not just Competitive Analysis.
- **Discipline:** seeds silently (no backlog flood); persists seen-set/hashes to
  `market_watcher_state.json` (fire-once, restart-safe); emits the event contract with
  an evidence URL; raw observation only (no verdict); stamped with `sim_day` but polled
  on real time (`MARKET_POLL_SECONDS`, default 900).

### 2.7 Pillar 3 — Institutional memory
- `record_decision` appends JSON lines to `evergreen_memory.jsonl`
  (entry_id/kind/summary/rationale/actors/source/signal_type/sim_day/timestamp).
- `recall_decisions(query)` — keyword-overlap + recency, document-frequency relevance
  gate (a lone common word can't false-match), provenance included; scoring isolated in
  `_score()` for a future embedding swap; graceful "no record" message.
- A founder question is a direct query (recall + reply via `band_send_message`, no
  convene), distinct from an event — handled by a dedicated prompt branch.

### 2.8 Watchers — identities & the scripted vs real split
- Two Band agent identities: **Market Watcher** (external) and **Metrics Watcher**
  (internal). The Metrics watcher reads `METRICS_WATCHER_API_KEY` (falls back to the
  Market key).
- Market Watcher runs scripted (demo beat) or real (continuous proof) — both supported.

### 2.9 Project infrastructure
- Env-driven throughout (`.env`); **secrets gitignored** (`.env`, `agent_config.yaml`)
  with `.example` templates so the repo is usable without exposing keys.
- Git repo **github.com/dineshsai05/Evergreen** (private), push after every change.
- `README.md`; full doc set (this file + the companions above).
- Runtime state gitignored (regenerated): `evergreen_memory.jsonl`,
  `clock/clock_state.json`, `metrics_watcher_state.json`, `market_watcher_state.json`.

---

## 3. Key decisions & gotchas resolved (the hard-won learnings)
- **Providers:** Groq OUT (rejects Band's `band_send_event` schema); Gemini free tier
  OUT (20/day cap); **AI/ML API IN** ($20 min top-up).
- **CrewAI adapter discards the final answer** → the only delivery path is the
  `band_send_message` tool. Grounded specialists therefore **pre-fetch-and-inject**, no
  choose-able data tools (the root of the original Finance bug).
- **Band injects conflicting prompt blocks** (Relaying/Activation/Delegation) → out-
  prompting them is unreliable; **suppress them in code** + force the recipient in code.
- **Room churn (gotcha #10) is real:** accumulated room history caused a decision-skip
  once; verified that a clean room records correctly. Use one clean room per run.
- **Wall-clock vs sim-clock:** real external pages can't be fast-forwarded → the Market
  watcher polls real time and stamps `sim_day`; the clock anchor must persist
  `seconds_per_day` so all processes agree.
- **Founder = the human only** — never brief an agent.
- **WAF walls** (Typeform help-center 403) — don't circumvent; find a legitimate
  fetchable source.
- **Page-diff noise** — diff extracted text (not raw HTML); use the heading as the
  change key + surface the blurb.
- **Determinism** lets restart re-derive the fake timeline without persisting it; only
  fire-once/dedup state needs disk.

## 4. Verification ledger (proven live, with rooms)
- `ea9b566e` — early full cascade (Typeform fan-out), materiality gate, recall, Step 2
  persistence, Step 3 Retention/Hiring, Step A grounding.
- `4b3567f9` — cross-room recall of a prior decision.
- `078d8912` — Step G end-to-end (metrics churn cascade → restart → recall).
- `ea531147` — real Market watcher cascade v1 (Typeform material / Jotform not-material).
- `aff3e3cf` — real Market watcher cascade v2 (heading+blurb → Typeform priced release
  fanned out to Competitive Analysis + Finance).
- Standalone/unit: clock, fake_stripe curve + determinism, metrics detection,
  market change-detection (RSS + Atom + page), live-seed of all four real sources.

---

## 5. Remaining (all optional / deferred)
- **Submission writeup** (`SUBMISSION.md`) — next up; lead with AI/ML API usage.
- **Watcher track extras:** competitor **pricing-page diffing** (`competitor_pricing_change`,
  JS-rendered/noisy); a generic watcher `_base` (only once a 3rd real watcher pays off);
  Metrics→real Stripe (one-line backing swap) and People & Voice (needs real customer
  data) — deferred.
- **Infra:** push/webhook ingestion; real wall-clock scheduler; scheduled beats
  (calendar-sourced); persistent LangGraph checkpointer (SQLite) for in-flight state;
  embedding-based `recall_decisions`; alerting channels (email/Slack/SMS).
- **Cleanup:** delete the stale generic `COMPANY` dict in `core/company_data.py`
  (unused; identity is canonical in `company_profile.py`); delete stale Band test rooms
  (keep one); `rm` the gitignored runtime-state files before a clean demo.

## 6. Repo map & how to run
```
agents/
  orchestrator.py                  # LangGraph; record_decision + recall_decisions
  specialists/
    _base.py                       # forced recipient, prompt-fix, identity + as-of injection
    competitive_analysis.py finance.py retention.py hiring.py
  watchers/
    market_watcher.py              # MODE=real (curated competitor sources) | MODE=scripted
    metrics_watcher.py             # derives MRR from the source; real detection
core/
  company_profile.py               # Quillo identity + watchlist (read by all tiers)
  company_data.py                  # day-0 financial seed (numbers)
  events.py                        # Event contract
  sources/fake_stripe.py           # in-process, as_of, deterministic
clock/sim_clock.py                 # wall-time-anchored sim-days (shared anchor)
```
Run (project root; orchestrator + specialists first, let them connect):
```
uv run python -m agents.orchestrator
uv run python -m agents.specialists.{competitive_analysis,finance,retention,hiring}
uv run python -m agents.watchers.metrics_watcher
uv run python -m agents.watchers.market_watcher                      # real
MARKET_WATCHER_MODE=scripted uv run python -m agents.watchers.market_watcher  # demo beat
```
Verify via agent logs + `evergreen_memory.jsonl` + the Band UI (the agent REST
`messages` endpoint is a work queue, not a transcript).
