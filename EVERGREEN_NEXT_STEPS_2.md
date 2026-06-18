# Evergreen — Next Steps v2: The Fake Company Workstream (build plan for Claude Code)

> **Read order:** `EVERGREEN_CONTEXT.md` (current state + Band facts) →
> `EVERGREEN_NEXT_STEPS.md` **§A (how to work)** → `EVERGREEN_FAKE_COMPANY.md` (the
> component designs + the proposed company identity) → this file (the **ordered,
> implementable build sequence**, including the changes to already-built steps).
>
> `EVERGREEN_FAKE_COMPANY.md` is the canonical *design*. This file is the canonical
> *build order + verification gates + prior-step changes*. Where they overlap, the
> design doc wins on shape; this file wins on sequence.
>
> **Assumed current state:** Steps 1–3 of `EVERGREEN_NEXT_STEPS.md` are DONE (memory
> recall, simulated clock + persistence, Retention & Hiring). The cascade, memory, and
> clock all work; the watcher is still a scripted stub.

---

## 0. The point of this workstream (one paragraph)

The company was never actually defined, so the watcher doesn't know what to watch, the
orchestrator judges from generic priors, and only Finance is grounded (on a financial
slice). This workstream makes the company a **real, queryable, time-varying thing**: a
**company profile** (identity + watchlist) every tier reads, and an **in-process
API-shaped fake data source** (fake Stripe) whose data changes over sim-time, so a
**real Metrics watcher** genuinely *derives and detects* a change instead of being
spoon-fed. It doubles as the clock's real payload. This is the step where Evergreen
stops being a demo.

---

## 1. CHANGES TO ALREADY-BUILT STEPS (do these as part of the sequence below)

This is the direct answer to "do the previous steps need changes?" — yes, these.
Each is cross-referenced to the build step where it's actually done.

| Built step | Change needed | Severity | Done in |
|---|---|---|---|
| **Step 2 — clock** | Clock becomes the *driver* the fake source + Metrics watcher key off (`as_of = current_day`); it no longer just fires scripts. | **Real** | Build Step D |
| **Step 2 — persistence** | Persisted state now includes the Metrics watcher's dedup/last-fired markers; restart demo must show the timeline re-derive identically from seed. | **Real** | Build Step D |
| **Orchestrator** (foundational) | (a) inject a short profile/watchlist summary into `CHIEF_OF_STAFF_PROMPT` so materiality is grounded; (b) accept structured events **without breaking** the existing plain-string path; (c) confirm/extend routing so `mrr_drop` → Finance + Retention. | **Real** | Build Steps A, C, E |
| **Step 1 — memory** | Optional: capture event provenance (`source`/`signal_type`/`sim_day`) in `record_decision` so recall can ground "why did we flag X". Recall still works without it if the rationale names the event. | **Optional enhancement** | Build Step F |
| **Step 3 — Retention/Hiring** | Read the profile for identity context; and (real nuance) analyze the **source as-of the event's sim-day**, not a static slice, or their numbers contradict the watcher. | **Coherence** | Build Step E |
| **`core/company_data.py`** | Refactor into the **day-0 seed** for the timeline; identity moves to the new profile module; define ONE source of truth so they don't drift. | **Refactor** | Build Steps A, B |
| **Market watcher** (stub) | Stays as-is functionally. Optional: migrate it to the same structured event contract for consistency. | **Optional** | Build Step C (note) |

**No hard breakage** if the orchestrator's structured-event handling stays backward
compatible (a human-readable line is always present) and the specialists' as-of switch
is done deliberately. The two genuine risks to manage: (1) the orchestrator must still
parse the old plain-string events from the Market watcher; (2) specialists reading
static day-0 data while the event reflects a churn spike will state contradictory
numbers — decide Phase 1 vs Phase 2 (Build Step E) consciously.

---

## 2. Ideology recap (the invariants that bite in THIS work)

Full version in `EVERGREEN_NEXT_STEPS.md §A`. The ones that matter here:
- **Funnel discipline:** the watcher **detects/filters, never judges**. It may emit a
  raw magnitude ("MRR −12% WoW, z=−3.1"); it must NEVER attach severity, threat level,
  or a recommendation. Materiality = orchestrator; meaning = specialist.
- **Swap the backing layer, not the agent.** The watcher's connector + derivation is
  real production code; only the data behind the accessor is fake.
- **`band_send_message` is the only delivery path**; grounded analysis via
  **pre-fetch-and-inject** (no choose-able data tools); specialists go through
  `agents/specialists/_base.py`; recipient forced in code.
- **Fire-once / dedup persists across restart**; **verify via logs +
  `evergreen_memory.jsonl` + Band UI**, never `GET …/messages`; **one room**;
  **connect-before-convene**; **env-driven** config; **don't bluff** Band APIs (fetch
  docs / read SDK source); small reviewable changes; keep the transcript human-readable.

---

## 3. BUILD ORDER

Seven steps. Each has a verification gate — don't start the next until the current one
passes. Steps A–C are pure additions; D–F fold in the prior-step changes; G is the
end-to-end proof.

---

### Build Step A — Company profile (keystone) + orchestrator grounding

**Goal:** the missing first-class object — a company identity + watchlist every tier
reads — and the orchestrator actually using it to judge materiality.

**Design / decisions:**
- Create `core/company_profile.py` holding the **static identity + watchlist** from
  `EVERGREEN_FAKE_COMPANY.md` Part 0 (name, what it sells, ICP, segments, tiered
  competitors, category keywords, optional key accounts, and the thresholds that define
  "a move worth noticing"). **The identity in Part 0 is a proposed default — confirm or
  edit the name/details with the human before hardcoding.**
- Keep the **financial constants** (`PLANS`, `UNIT_ECONOMICS`, `CASH`) in
  `core/company_data.py`. Profile = identity (slow-changing); company_data = the numbers
  (the day-0 seed). One source of truth each; no overlap.
- **Orchestrator grounding (recommended approach):** inject a **short** profile +
  watchlist summary string into `CHIEF_OF_STAFF_PROMPT` at load (not the whole object —
  keep the prompt lean). A `get_company_profile()` tool is an alternative but
  unnecessary now; the static summary is enough for materiality.

**Implementation sketch:**
```python
# core/company_profile.py  (shape — adapt)
COMPANY = {
  "name": "Quillo",                      # PROPOSED — confirm with human
  "what": "SaaS form & survey builder",
  "icp": "SMB teams / non-technical operators",
  "segments": ["Free", "Starter", "Pro", "Business"],
  "competitors": {"major": ["Typeform"],
                  "minor": ["FormFly", "Jotform", "Google Forms", "Tally"]},
  "category_keywords": ["form builder", "survey tool", "AI form", "lead capture"],
  "watch_thresholds": {"mrr_drop_pct": 0.10, "mrr_z": 3.0},  # tunable, env-overridable
}
def profile_summary() -> str: ...   # short string injected into the orchestrator prompt
```

**Consistency:** the tiered watchlist should *ground* the materiality calls already
observed — Typeform (major) = material, FormFly (minor) = not material. The orchestrator
should now reach those verdicts from the watchlist, not generic priors.

**Verify:** restart the orchestrator; post the existing Typeform and FormFly test events
(plain string, as today). Materiality verdicts unchanged, but the orchestrator log/
rationale should reflect watchlist grounding. **Nothing else should regress.**

**Pitfalls:** prompt bloat (keep the summary short); don't duplicate financial numbers
into the profile.

**Done when:** the profile exists, all three tiers can read it, the orchestrator prompt
carries a lean summary, and existing cascades still behave.

---

### Build Step B — In-process API-shaped fake Stripe source

**Goal:** time-varying company data behind an SDK-shaped accessor, deterministic from a
seed, anchored on the day-0 figures, with the planted churn event.

**Design / decisions** (full detail: `EVERGREEN_FAKE_COMPANY.md` Part 2):
- Create `core/sources/fake_stripe.py` (leave room for `fake_posthog.py` later — build
  only Stripe now).
- **SDK-shaped, `as_of`-parameterized accessors** returning Stripe-shaped raw objects:
```python
fake_stripe.subscriptions.list(as_of: int) -> list[dict]   # plan, amount, status, ...
fake_stripe.charges.list(as_of: int, since: int|None=None) -> list[dict]
# do NOT expose a precomputed "mrr" — the watcher derives it
```
- **Deterministic from (seed, as_of):** same seed + day → same objects. Seed via env
  (`FAKE_DATA_SEED`). This is what makes restarts consistent **without persisting the
  timeline** — re-derive it.
- **Timeline:** at `as_of=0`, active subscriptions reproduce the existing
  `company_data.py` figures. Baseline (flat/gentle) for quiet days; on the planted
  sim-day, flip a coherent batch of Starter subscriptions to `canceled` (e.g. ~300 →
  ≈ −$5.7k MRR ≈ −12%, tunable to breach the Step-A threshold).
- **No judgment / no thresholds in the source.** It returns what's true on that day.

**Verify (standalone, no agents):** a tiny script that calls
`subscriptions.list(as_of=d)` for `d` in a range, derives MRR, and prints the curve —
confirm it's flat then drops on the planted day, and that two runs with the same seed
are identical.

**Pitfalls:** incoherent magnitudes (Starter cancellations must reduce Starter MRR by
the right amount); accidental nondeterminism (no `random` without the seeded RNG; no
wall-clock).

**Done when:** the accessor returns coherent, deterministic, day-varying objects whose
derived MRR matches day-0 at day 0 and drops through the threshold on the planted day.

---

### Build Step C — Event contract + Metrics watcher (real detection)

**Goal:** a real watcher that derives MRR from the source, detects a genuine change, and
emits a structured event — never judging.

**C1. Minimal event contract** (`core/events.py`, currently an empty scaffold). Use the
minimal subset of `EVERGREEN_FAKE_COMPANY`/Step-4-design §3:
`source`, `signal_type`, `observation` (human-readable), `magnitude` (raw:
`{metric, prev, now, pct, z}`), `dedup_key`, `sim_day`. **No severity / recommendation.**

**Delivery shape (avoid bluffing about Band metadata):** post via the existing REST send
path with a **human-readable line in `content` PLUS a compact JSON tail** the
orchestrator can parse, e.g.:
```
@Orchestrator [metrics] MRR fell 12% week-over-week (z=-3.1), driven by Starter churn.
<event>{"source":"stripe","signal_type":"mrr_drop","magnitude":{"metric":"mrr","prev":48218,"now":42500,"pct":-11.9,"z":-3.1},"dedup_key":"mrr_drop:day-12","sim_day":12}</event>
```
If Band's REST message supports structured metadata, prefer that — **confirm against the
docs first** (don't assume). The readable line guarantees backward compatibility with
the orchestrator's existing plain-string handling.

**C2. Metrics watcher** (`agents/watchers/metrics_watcher.py`) — pipeline:
1. **Pull** `fake_stripe.subscriptions.list(as_of=current_sim_day)`.
2. **Derive** MRR (sum active amounts), active-sub count, churn count — real derivation.
3. **Baseline** — a rolling window of recent values. **Reconstruct it on startup by
   querying the source for the last N sim-days** (the source is deterministic, so no
   need to persist the window). 
4. **Detect** — z-score or %Δ vs baseline; fire only on threshold breach (threshold
   from profile/env).
5. **Dedup / fire-once** — by `dedup_key`; **persist a small last-fired/seen set** so a
   restart does not re-fire an already-fired condition.
6. **Emit** the structured event to `@Orchestrator` via REST (`X-API-Key`, ≥1 mention,
   resolve orchestrator id from participants). Must be a room participant to post.

Transport mirrors the Market watcher. Reuse its REST helpers if practical.

**Funnel check:** the watcher outputs raw magnitude only. If it ever emits "this is
serious" or "we should…", it's overstepping — strip it.

**Verify (with agents):** see Build Step G (end-to-end). Standalone: run the watcher
against the source across the planted day and confirm it fires exactly once, with raw
magnitude, on the right day, and nothing on quiet days.

**Pitfalls:** firing on every tick (baseline/threshold wrong); re-firing after restart
(persist last-fired); the watcher starting *after* the orchestrator and missing nothing
because it only *sends* (fine) — but the orchestrator/specialists must be connected
before the event (connect-before-convene).

**Done when:** the watcher derives MRR itself, fires one structured `mrr_drop` on the
planted day, stays quiet otherwise, and doesn't re-fire on restart.

---

### Build Step D — Clock integration + extended persistence (Step-2 changes)

**Goal:** make the clock the driver, and make the whole thing survive a restart
deterministically. **This modifies the already-built Step 2.**

**Changes:**
- The Metrics watcher reads the **sim-day from the existing clock** each tick and polls
  the source `as_of` that day. The clock no longer needs to "fire scripts" for the
  metrics path (the Market watcher's scripted feed can remain for external events).
- **Reconcile the two watchers:** both Market (scripted external) and Metrics (real
  internal) run off the same clock into the **one room**. Confirm no double-room churn
  (gotcha #10).
- **Extend persisted state:** sim-day (already persisted) + the Metrics watcher's
  last-fired/dedup set. The source timeline and the watcher baseline are **re-derived**
  from the seed, not persisted.

**Verify (the persistence demo, upgraded):**
1. Run clock + Metrics watcher + orchestrator + Finance + Retention, one room, all
   connected before the planted day.
2. Let it run to (or past) the planted day; confirm the real cascade fires.
3. **Kill everything, restart.** Confirm: sim-day resumes; the source re-derives the
   identical timeline; the watcher rebuilds its baseline and does **not** re-fire the
   planted event; `evergreen_memory.jsonl` and room history intact.

**Pitfalls:** re-firing the planted event after restart (the #1 risk — persist
last-fired); clock and source disagreeing on sim-day (single source of sim-day = the
clock).

**Done when:** the clock drives real detection, and a full restart resumes cleanly with
no replay and identical timeline.

---

### Build Step E — Specialist coherence (Step-3 changes)

**Goal:** specialists analyzing a time-varying event must agree with what the watcher
reported, and should know the company identity. **This modifies the already-built
Finance/Retention.**

**Changes / decision (Phase 1 vs Phase 2 — choose consciously):**
- **Profile context:** Finance, Retention (and Competitive, Hiring) inject the profile
  summary for identity grounding — same pre-fetch-and-inject pattern, via `_base.py`.
- **As-of consistency (the real nuance):** for an event about a time-varying metric
  (the `mrr_drop`), the analyzing specialist should pre-fetch from the **fake source
  as-of the event's sim-day**, NOT the static day-0 `company_data.py`. Otherwise the
  founder brief says "MRR −12%" (watcher) while Finance cites the pre-churn number —
  contradictory.
  - **Phase 1 (fastest, acceptable for a first pass):** leave specialists on day-0
    `company_data.py`; accept that their numbers lag the event. Flag this in the demo.
  - **Phase 2 (recommended for coherence):** point the pre-fetch for the **metric the
    event is about** at `fake_stripe`/derived values `as_of` the event sim-day. Keep
    pre-fetch-and-inject (no choose-able tools). This makes Finance's "MRR now $42.5k,
    Starter churn cluster" match the watcher exactly.
- Routing: confirm `mrr_drop` convenes **Finance + Retention** (churn → both). Adjust
  the orchestrator CONVENE rules only if it doesn't.

**Verify:** on the planted-day cascade, Finance's and Retention's cited numbers **match**
the watcher's reported magnitude (Phase 2), and the founder brief is internally
consistent.

**Pitfalls:** reintroducing choose-able data tools (don't — adapter discards the final
answer); two sources of truth drifting (the source as-of-now should derive from the same
seed/day-0 as `company_data.py`).

**Done when:** specialists ground in identity + the correct as-of numbers, and the brief
has no contradictory figures.

---

### Build Step F — Memory provenance (Step-1 enhancement, optional)

**Goal:** recall can answer "why did we flag the MRR drop?" with grounding.

**Change:** extend `record_decision` to capture event provenance when present —
`source`, `signal_type`, `sim_day`, and the `magnitude` — alongside the existing
summary/rationale. `recall_decisions` keyword search then matches on these too. If the
orchestrator already writes the event's facts into the rationale, basic recall works
without this; the enhancement makes provenance queries robust.

**Verify:** trigger the planted cascade; ask the founder "why did we flag the MRR
drop?" → `recall_decisions` returns the decision with the metrics provenance, no
specialist convened.

**Done when:** a metrics-driven decision is recallable with its provenance.

---

### Build Step G — End-to-end verification (the proof)

Run the whole thing, one room, everything connected before the planted day:
clock + Metrics watcher + Market watcher (optional) + orchestrator + Finance + Retention
(+ Competitive, Hiring running).

1. Quiet days: watcher pulls subscriptions, derives MRR, holds baseline, **fires
   nothing**; orchestrator silent; founder un-pinged.
2. Planted day: churn cluster lands → watcher **derives the drop and fires a real
   `mrr_drop`** → orchestrator (grounded by the profile) judges it material → convenes
   **Finance + Retention** → grounded replies addressed to the orchestrator → stand-down
   → **one** founder brief → `record_decision`.
3. **Restart:** sim-day resumes, timeline re-derives identically, no replay, memory +
   room intact.
4. **Recall:** "why did we flag the MRR drop?" → answered from memory.

If all four hold, the detection layer is real, the company is defined, every tier is
grounded, and the three pillars (persistent / event-driven / memory) are intact against
the litmus test.

---

## 4. Scope discipline (do NOT)

- **No real HTTP server**; in-process API-shaped accessors only.
- **Don't clone all of Stripe** — only subscriptions (+ maybe charges).
- **One source only** (fake Stripe). Fake PostHog / support are later, same pattern.
- **The watcher never judges** — raw magnitude only.
- **Don't break Finance / the existing cascade**; don't reintroduce choose-able data
  tools; keep `_base.py` intact (re-verify it after any `band-sdk` bump).
- **Env-driven** seed / threshold / cadence; **keep numbers coherent** with the day-0
  seed.
- **Deadline:** the MVP (cascade + memory + clock) already ships. This workstream is the
  real-product leap. If time is short, Build Steps A–D are the spine (real detection +
  grounding + restart); E (Phase 2) and F are coherence/polish.

---

## 5. Consistency contract (keep open while coding)

- Build order A → B → C → D → E → F → G; gate each on its verify.
- Profile = identity; `company_data.py` = day-0 seed; fake source = timeline derived
  from the seed. One source of truth each; specialists read the source **as-of** for
  time-varying events.
- Watcher detects/filters, never judges. Structured event = readable line + JSON tail
  (or confirmed Band metadata). Orchestrator stays backward compatible with plain
  strings.
- `band_send_message` only; pre-fetch-and-inject; `_base.py` for specialists; recipient
  forced in code; fire-once persists across restart; determinism via seed.
- Verify via logs + memory + Band UI; one room; connect-before-convene; env-driven;
  don't bluff Band APIs; small reviewable changes; human-readable transcript.