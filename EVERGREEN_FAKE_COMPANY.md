# Evergreen — The Fake Company & the In-Process Data Source (build brief for Claude Code)

> Read `EVERGREEN_CONTEXT.md` (state + Band facts) and `EVERGREEN_NEXT_STEPS.md`
> (esp. **§A — how to work**) FIRST. This file is a **new workstream** that fills the
> one gap underneath everything else: **the company itself was never defined.**
>
> Current state assumed: Steps 1–3 of `EVERGREEN_NEXT_STEPS.md` are done (memory
> recall, simulated clock + persistence, Retention & Hiring specialists). The cascade,
> memory, and clock all work.

---

## A. Why this exists (the gap we're closing)

Today nothing in the system defines **what the company is**:
- The **watcher** is a hardcoded feed — it doesn't know what to watch for; we hand it
  pre-written events.
- The **orchestrator** judges materiality from generic LLM priors + the event's own
  self-describing text. It has no model of the business.
- Only the **Finance** specialist is grounded, and only on a *financial* slice
  (`core/company_data.py`); Competitive Analysis invents its figures. The company's
  **identity** (what it sells, to whom, who it competes with) is written nowhere.

The system *looks* coherent because events are self-labeling and the LLM fills gaps
with plausible startup reasoning. Strip those crutches and the upstream tiers have
nothing to reason from.

**The fix:** make the company a real, queryable, **time-varying** thing the agents
actually read. Concretely: (1) a **company profile** (identity + watchlist) every tier
reads, and (2) an **in-process, API-shaped fake data source** (a fake Stripe) whose
data **changes over sim-time**, so a real **Metrics watcher** can *derive* metrics and
*detect* a genuine change — instead of being spoon-fed.

**This is not extra scope on top of the clock — it IS the clock's missing payload.**
The clock already advances sim-days (Step 2). Today it fires scripts. Backed by this
source, the clock advances *time*, the data genuinely evolves, and the watcher
genuinely catches it. That's the line between "we scripted an event" and "the system
noticed something."

---

## B. The decision (locked) — and the invariants that bite here

**Locked:** an **in-process, API-shaped layer** (NOT a real HTTP server). Accessors
shaped like a real SDK (e.g. `fake_stripe.subscriptions.list(as_of=day)`) returning
Stripe-shaped objects over a generated timeline. Swappable for real Stripe later by
replacing the backing layer, not the watcher.

Invariants from `EVERGREEN_NEXT_STEPS.md §A` that specifically apply:
- **Funnel discipline (the one most at risk here):** the watcher **detects/filters,
  never judges**. It may emit a raw magnitude ("MRR −12% WoW, z=−3.1") because that's
  an observation; it must NEVER attach severity, threat level, or a recommendation.
  Materiality is the orchestrator's job; meaning is the specialist's.
- **Swap the backing layer, not the agent.** The watcher's connector/derivation code
  is real production code; only the data behind the accessor is fake. Going live later
  = swap the backing layer.
- **Env-driven** (no hardcoded paths/seeds/thresholds in logic).
- **Don't break the working Finance specialist** (see Part 4).
- **Fire-once / dedup discipline persists across restart** (same rule as the clock):
  a given condition fires once; a restart resumes, it does not replay.
- **Verify via logs + `evergreen_memory.jsonl` + Band UI**, never `GET …/messages`.

---

## Part 0 — Proposed company identity (PROPOSED — edit freely; this is your call)

You said you'd define the company. Here's a concrete, internally-consistent starting
point so Claude Code isn't blocked — **rename / adjust anything**. It is deliberately
consistent with the existing numbers in `core/company_data.py` so Finance keeps working.

- **Name:** *Quillo* (placeholder — rename).
- **What it is:** a SaaS form & survey builder (the fictional product the existing mock
  already implies).
- **ICP / who it sells to:** SMB teams and non-technical operators building forms,
  surveys, and lead-capture pages.
- **Monetization (reuse existing figures):** the existing `PLANS` from
  `core/company_data.py` — Free / Starter ($19) / Pro ($49) / Business ($149) — and the
  existing MRR / unit-economics / cash figures as the **day-0 baseline**. Do NOT invent
  new numbers; anchor on what's already there (Starter ≈ 45% of MRR, etc.).
- **Watchlist — competitors, tiered (this is the keystone for relevance + materiality):**
  - *Major / direct:* **Typeform**.
  - *Minor:* **FormFly**, Jotform, Google Forms, Tally.
  - *Category keywords:* "form builder", "survey tool", "AI form", "lead capture".
  - **Nice consistency win:** this retroactively *grounds* the materiality calls we
    already saw — the **Typeform** price cut was material (major competitor) and the
    **FormFly** UI refresh was *not* material (minor competitor). Today that judgment
    came from generic priors; with the watchlist it becomes grounded.
- **The planted timeline event (what the Metrics watcher should genuinely catch):** a
  **churn cluster** on a chosen sim-day — e.g. ~300 Starter cancellations on sim-day 12
  — dropping total MRR ~10–15% through the watcher's threshold. Size it to breach
  whatever threshold the watcher uses (tunable). This drives a **metrics** event
  (`mrr_drop`), distinct from the existing competitor (market) events.

---

## Part 1 — Company profile module (the keystone all tiers read)

Create `core/company_profile.py` (or grow `company_data.py` to include it — your call,
but keep identity separate from the financial numbers conceptually).

- Holds the **static identity + watchlist** from Part 0: name, what it sells, ICP,
  segments, competitor tiers, category keywords, key accounts (optional), and the
  thresholds that define "a move worth noticing".
- This is **read by all three tiers**:
  - **Watcher** — relevance/threshold reference ("is this in our world? did it move
    beyond normal?").
  - **Orchestrator** — inject a short profile/watchlist summary into
    `CHIEF_OF_STAFF_PROMPT` (or as a tool it can read) so materiality is judged against
    *this* business, not generic priors. (Small, high-signal summary — not the whole
    object. Keep the prompt lean.)
  - **Specialists** — identity context so analysis is grounded in who the company *is*,
    not just its numbers.
- **Scope rule:** a fact belongs here only if a watcher needs it to filter or a
  specialist/orchestrator needs it to ground. Don't model the whole company — keep it
  lean so it stays high-signal.

> Keep the **financial constants** (`PLANS`, `UNIT_ECONOMICS`, `CASH`, etc.) where they
> are in `core/company_data.py`; they become the **day-0 seed** for the timeline in
> Part 2. Profile = identity (slow-changing). Company_data = the numbers (the seed).

---

## Part 2 — In-process API-shaped fake source (the fake Stripe)

Create `core/sources/fake_stripe.py` (leave room for `fake_posthog.py` etc. later —
but build ONLY Stripe now).

**Shape it like a real SDK, with an `as_of` (sim-day) dimension:**
```python
# sketch — adapt names to taste
fake_stripe.subscriptions.list(as_of: int) -> list[Subscription]   # Stripe-shaped dicts
fake_stripe.charges.list(as_of: int, since: int|None=None) -> list[Charge]
# (expose RAW-ish objects; do NOT expose a precomputed "mrr" field)
```

Requirements:
- **Expose raw-ish objects** (subscriptions with plan/amount/status, charges), and let
  the **watcher derive MRR** from them. This is what keeps the watcher's logic real. A
  source that just returns `{"mrr": 41000}` defeats the point.
- **Timeline anchored on the day-0 seed** (`company_data.py`): at `as_of = 0` the
  active subscriptions reproduce the existing plan/MRR figures. A baseline trajectory
  (flat or gentle growth) for the quiet days, then the **planted churn cluster** on the
  chosen sim-day (Part 0) flips a batch of Starter subscriptions to `canceled`.
- **Deterministic from (seed, as_of).** Given the same seed and sim-day, it returns the
  same objects. This is what makes a **restart consistent** without persisting the
  whole timeline — re-derive it. Seed via env (e.g. `FAKE_DATA_SEED`).
- **No judgment, no thresholds here.** It's a data source. It returns what's true on
  that day; the watcher decides if that's a change worth firing.

---

## Part 3 — The Metrics watcher (real detection, finally)

Create `agents/watchers/metrics_watcher.py`. This is a **real** watcher — the Market
watcher stub stays as-is (different family: external/news). The Metrics watcher is the
clean first real one because it's deterministic numbers, and it closes the loop with the
Finance/Retention specialists already built.

Pipeline (each clock tick = each new sim-day):
1. **Pull** `fake_stripe.subscriptions.list(as_of=current_sim_day)`.
2. **Derive** the metric(s) — MRR (sum of active subscription amounts), active-sub
   count, churn count. (Real derivation, not handed to it.)
3. **Baseline** — maintain a rolling window of recent values, **persisted to disk**
   (like `clock_state.json`) so it survives restart.
4. **Detect** — z-score (or %Δ) vs baseline; fire only when it breaches the threshold
   (threshold from the profile / env, tunable so the planted cluster breaches it).
5. **Dedup / fire-once** — by period (e.g. `dedup_key="mrr_drop:sim-day-12"`); after a
   restart, resume — do NOT re-fire an already-fired condition.
6. **Emit** a **structured event** to the orchestrator (post into the room via the
   existing REST send path, @mentioning the Orchestrator). Use the minimal event
   contract from the Step-4 design doc §3 — `source`, `signal_type`, `observation`
   (human-readable), `magnitude` (raw numbers: prev/now/pct/z), `dedup_key`,
   `sim_day`. **No severity, no recommendation** (funnel §1).

Transport reuses what the Market watcher already does (REST, `X-API-Key`, ≥1 mention,
resolve the orchestrator id from participants). It must be a room participant to post.

---

## Part 4 — Wiring & consistency (don't break what works)

- **Clock drives the tick.** The Metrics watcher reads the sim-day from the existing
  clock (Step 2) and polls the source per new sim-day. Quiet days produce no event;
  the planted day fires one. This is the clock finally having a *real* payload.
- **Routing already exists.** The orchestrator routes by peer description; an
  `mrr_drop` event should convene **Finance** (and likely **Retention**, since churn is
  the cause) → grounded replies → stand-down → one founder brief → `record_decision`.
  Confirm the routing picks them up; only adjust the CONVENE rules if it doesn't.
- **Finance grounding — do NOT break it.**
  - *Phase 1 (now):* leave Finance reading `core/company_data.py` as today. The day-0
    seed equals those figures, so the cascade stays coherent.
  - *Phase 2 (optional, only if time):* point Finance's pre-fetch at the fake source
    `as_of` the current sim-day, so Finance's numbers match exactly what the watcher
    saw post-churn. Keep the pre-fetch-and-inject pattern (no choose-able tools).
- **Market watcher stays as-is** (still scripted external events). We are adding the
  Metrics family, not replacing Market.

---

## Part 5 — Verify (what to run)

1. Start the clock, the Metrics watcher, the orchestrator, Finance, Retention — one
   room, all connected before the planted day (connect-before-convene).
2. Watch the watcher log each sim-day: it pulls subscriptions, derives MRR, holds a
   baseline, and on the quiet days **fires nothing**.
3. On the planted day: the churn cluster lands → watcher derives the drop → **fires a
   real `mrr_drop` event** with raw magnitude → orchestrator convenes Finance (+
   Retention) → grounded replies → stand-down → one founder brief → decision recorded.
4. **Determinism / restart:** kill everything, restart. The timeline re-derives
   identically (same seed), the baseline + last-fired state resume from disk, the
   sim-day resumes — and the planted event is **not replayed**.
5. **Recall:** ask the founder "why did we flag the MRR drop?" → `recall_decisions`
   answers from memory (ties the new real-detection loop back to the memory pillar).

---

## Part 6 — Scope discipline (do NOT)

- **No real HTTP server.** In-process API-shaped accessors only.
- **Don't clone all of Stripe** — only the slice the watcher needs (subscriptions,
  maybe charges).
- **One source only** (fake Stripe / financial). Fake PostHog / support / etc. are
  later, same pattern.
- **The watcher never judges.** It computes and thresholds; it emits raw magnitude. No
  severity, no recommendation. If it starts ranking importance, it's become a bad
  orchestrator.
- **Keep numbers coherent** with the day-0 seed; the planted churn must be internally
  consistent (Starter cancellations reduce Starter MRR by the right amount).
- **Env-driven** seed/threshold/cadence; **don't break Finance**.

---

## How this relates to the existing plan (so there's no drift)

- It **supersedes the scripted payload** behind the already-built clock
  (`EVERGREEN_NEXT_STEPS.md` Step 2): the clock stays, but its events now come from a
  real time-varying source instead of a script.
- It **pulls forward a scoped, in-process slice of Step 4** (the Metrics watcher from
  `EVERGREEN_NEXT_*` real-watchers design) — but **fake/in-process**, not real HTTP.
  The rest of Step 4 (real HTTP sources, Market/Voice watchers, webhooks) stays
  **deferred**.
- It introduces the **Company Profile** as the first-class object the whole system was
  missing — read by all three tiers.