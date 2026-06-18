# Evergreen — Next Steps (build brief for Claude Code)

> Read `EVERGREEN_CONTEXT.md` FIRST — it is the current state, architecture, and the
> hard-won Band SDK facts. This file is the **forward plan**: what to build next, in
> what order, and — most importantly — **the ideology and process to build it with**,
> so there is zero drift between the two of us.
>
> Section references like "§5", "§8" point into `EVERGREEN_CONTEXT.md`.

---

## A. How to work on this (non-negotiable — read before touching code)

These are the principles every change must obey. They are not style preferences; each
one was paid for with a real failure (see §9 of the context doc).

1. **Prime directive: this is a genuinely usable real-world product, NOT a demo.**
   When a demo shortcut and a real-product choice diverge, take the real-product one
   and say so. (e.g. grounded specialists over persona ones; deterministic delivery
   over "prompt it harder".)

2. **The litmus test governs everything.** If a change would still work after deleting
   the simulated clock and the memory, it has drifted into a one-shot pipeline — stop
   and flag it. The three pillars (persistent, event-driven, institutional memory) are
   the product. Protect them.

3. **Respect the funnel. Never blur the tiers.**
   - **Watcher = detection** ("did something happen?"). A sensor. NEVER analyzes,
     NEVER recommends, NEVER self-escalates. Organized **by source**.
   - **Orchestrator = triage** ("does it matter, who should look?"). Routes. NEVER
     analyzes a domain question itself.
   - **Specialist = analysis** ("what does it mean, how bad, what do we do?"). Deep,
     on-demand. NEVER watches, NEVER self-triggers — only the orchestrator convenes it.
     Organized **by expertise**. Reports ONLY to the orchestrator.
   Any new agent that violates this layering is wrong even if it "works".

4. **Never bluff about Band.** If a Band primitive or behavior is unknown, fetch the
   real docs (§12 list) or read the SDK source — do not invent an API. State the
   assumption explicitly if you must proceed on one.

5. **Match the patterns that already shipped. Do not reinvent.** Specifically:
   - **`band_send_message` is the ONLY delivery path.** Plain agent/LLM output is
     discarded by the adapter (§5, §8). Every reply must go through it.
   - **Grounded specialists use PRE-FETCH-AND-INJECT, never choose-able data tools.**
     Choose-able tools give the model a second, non-delivering exit (this was the
     Finance bug, §8). Compute the numbers in plain Python, inject into context, leave
     `band_send_message` as the only action.
   - **All specialists go through `agents/specialists/_base.py` (`run_specialist`).**
     It forces the reply recipient to the orchestrator in code and suppresses Band's
     conflicting injected instructions (Relaying/Activation/Delegation). Do NOT
     re-introduce the old "report only to the orchestrator" prompt paragraph — it's
     obsolete; the base handles it.
   - **Recipient is forced in code, not prompted.** Prompt overrides lost to Band's
     injected `## Relaying` instruction in practice (§5, gotcha #12).
   - **Orchestrator: every event ends in a tool call** (`record_decision` for noise,
     convene path for material). Silent inaction is the bug. Dedup is the watcher's
     job, not the orchestrator's (gotcha #7).
   - **The Founder Rule:** at most one founder @mention per event, only the final
     brief (gotcha #8). (Exception: a direct founder *question* — see Step 1 — is
     answered as a reply; that's not an unsolicited escalation.)

6. **Verify runs the right way.** Read **agent logs + `evergreen_memory.jsonl` + the
   Band UI**. Do NOT use `GET …/chats/{id}/messages` to check a transcript — it's a
   work queue and reads empty once processed (§5, gotcha #14).

7. **Operational discipline.** ONE room (delete stale ones — the orchestrator
   auto-subscribes to all rooms it's in). Start specialist processes and let them
   CONNECT before convening — there is no offline mention queue (gotcha #13).

8. **Config stays env-driven.** No hardcoded keys, models, URLs, or room IDs in code.
   Everything swappable via `.env` (§4).

9. **Process:** flag assumptions/unknowns *before* writing code; make small reviewable
   changes; after each one, say exactly what to run to verify it; keep every room
   message short and human-readable (the transcript is the audit trail and the UX).

10. **Fragility watch:** `_base.py` patches SDK internals (a module-global override of
    `render_system_prompt` + an `on_message` wrapper). Re-verify it after ANY
    `band-sdk` upgrade. It degrades gracefully, but a major version could move the
    seams.

---

## B. Priority order (and why)

Deadline is tight (hackathon, June 19). Build in this order. **Steps 1 and 2 are the
ones that matter most** — they finish the two pillars that are currently incomplete and
are what the litmus test is about. Steps 3–5 are breadth/polish/admin.

| # | Step | Why it's here | Pillar / requirement it closes |
|---|------|---------------|--------------------------------|
| 1 | **Memory recall** (`recall_decisions`) | Institutional memory is currently **write-only** — we record decisions but nothing reads them back. This is the signature "why did we decide X?" capability. | Pillar 3 (institutional memory); DoD "memory answers a why query" |
| 2 | **Simulated clock + persistence-across-restart** | Makes the long-running / time dimension **visible**, and proves state survives a restart. The most convincing proof depends on Step 1 (recall a pre-restart decision), so it goes second. | Pillars 1 & 2 (persistent, event-driven over time); DoD "clock makes long-running behavior visible" + "room persists across restart" |
| 3 | **Retention & Hiring specialists** | Breadth — strengthens the *dynamic convening* differentiator (richer fan-out across expertises). Now trivial via `_base.py`. | Strengthens the differentiator; not a pillar gap |
| 4 | **Real watchers** | The real-product upgrade for detection. **Deferred — do NOT build during the hackathon** unless explicitly asked. | Real-product polish; out of hackathon scope |
| 5 | **Partner-prize claim** | AI/ML API is already in use — make it visible and claim it. Submission task, not code. | Partner prize |

If time runs out, having 1 and 2 done + the existing cascade is a complete, coherent
Evergreen. 3–5 are bonus.

---

## STEP 1 — Memory recall (`recall_decisions`) — ✅ DONE (2026-06-18)

> Shipped in `agents/orchestrator.py`: `recall_decisions(query)` (keyword-overlap +
> recency, relevance-gated, `_score()` isolated for an embedding swap) + the
> "ANSWERING THE FOUNDER ABOUT THE PAST" prompt branch (recall + reply via
> band_send_message, no convene). Verified live in the Band room: positive query →
> grounded answer; unknown → graceful no-record; 0 specialist convenes. Write-path
> schema confirmed sufficient (`summary` + `rationale` present); no `record_decision`
> change needed (a `sim_day` field is deferred to Step 2). Known v1 limit: keyword
> polysemy (e.g. "hiring plan") — accepted; the model handled it correctly in testing.

**Goal:** the room can answer a founder's "why did we decide X?" (and "why *didn't* we
act on Y?") months later, grounded in what `record_decision` logged. This completes the
institutional-memory pillar.

### 1A. FIRST verify the write path (do this before building anything)
Do not build the read side against a guessed schema.
- Read the actual `record_decision` `@tool` in `agents/orchestrator.py` and note the
  **exact field names** it writes.
- `cat evergreen_memory.jsonl | tail -n 20` and confirm cascades are actually
  producing entries (both "not material" notes and material decisions). Note the real
  shape of a line.
- If the file is empty or entries are missing, the bug is upstream — fix
  `record_decision` firing first (it should fire on every event per the ACT ON EVERY
  EVENT rule). Report what you find before proceeding.
- **Build recall against the schema you actually observe**, not against the PRD's
  suggested shape. If the current schema is thin (e.g. only a summary, no rationale),
  flag it — recall needs both a `summary` and a `rationale` to answer "why", so
  `record_decision` may need a `rationale` field added. State the change before making
  it.

### 1B. Build the `recall_decisions` tool
- A LangChain `@tool` added to the orchestrator's `additional_tools` list, alongside
  `record_decision`. Same file, same style.
- Signature: `recall_decisions(query: str) -> str`.
- Behavior:
  1. Read every line of `evergreen_memory.jsonl` (the file is small — read per call;
     handle blank/malformed lines gracefully).
  2. Score each entry against `query` and return the top ~3–5, formatted as compact,
     human-readable lines: `sim-day/date — summary — rationale — actors`.
  3. If nothing matches, return an explicit `"No recorded decision matches that."` so
     the model says so instead of inventing an answer.
- **Design decision — search method (flagged):** use **keyword overlap + recency** for
  v1. Lowercase, strip stopwords, score by token overlap on `summary + rationale`,
  break ties by recency. Rationale: the store is tiny, it's deterministic, needs no new
  dependency, and ships in minutes.
  - **Honest limitation:** keyword matching misses paraphrase ("why didn't we match the
    price cut" vs an entry that says "declined to match Typeform discount"). Mitigate
    by (a) instructing the orchestrator to pass keyword-rich queries, and (b) generous
    token overlap.
  - **Real-product upgrade path (only if there's spare time):** embed `summary +
    rationale` at write time via the AI/ML API embeddings endpoint, store the vector on
    the entry, and cosine-match the query embedding. Keep the scoring isolated in one
    helper (e.g. `_score(entry, query)`) so swapping keyword→embedding is a one-function
    change. Do NOT build this if it risks Steps 2–3; the keyword version is acceptable
    for the hackathon and the seam makes the upgrade cheap later.

### 1C. Teach the orchestrator a new branch (founder query ≠ watcher event)
The orchestrator currently only reacts to watcher *events*. A founder asking about the
past is a **direct query**, not an event. Add a branch to `CHIEF_OF_STAFF_PROMPT`
(insert near the top, after ACT ON EVERY EVENT). Match the existing prompt's plain,
imperative voice. Suggested text (adapt wording, keep intent):

```
ANSWERING THE FOUNDER ABOUT THE PAST. If a human (the founder) @mentions you asking
about past reasoning or decisions — e.g. "why did we decide X?", "what did we decide
about Y?", "why didn't we act on Z?", "have we dealt with this before?" — this is a
DIRECT QUESTION, not a new event. Do NOT convene a specialist and do NOT treat it as
something to escalate. Call recall_decisions with the key terms from their question,
then reply to the founder in 1-3 plain sentences using ONLY what it returns. If it
returns nothing, tell them you have no record of that decision. Answering a direct
question is a reply, so the once-per-event Founder Rule does not apply here.
(If the founder instead raises a genuinely NEW development, handle it as an event
through the normal loop below.)
```

Also upgrade the existing closing line of the prompt ("If asked why a past decision was
made, answer from what was recorded.") to explicitly route through the tool: "…call
recall_decisions and answer from what it returns."

### Verify Step 1 (what to run)
1. Run a clean cascade so a material decision is recorded; confirm the entry in
   `evergreen_memory.jsonl`.
2. As the founder, in the room: `@Orchestrator why did we decide not to match
   Typeform's price cut?` → expect a grounded 1–3 sentence answer drawn from the
   logged rationale. Check the orchestrator log shows `recall_decisions` was called and
   **no** `add_participant`/convene happened.
3. Negative case: ask about something never decided → expect a graceful "no record".

### Pitfalls (Step 1)
- The orchestrator must answer from `recall_decisions`, not from chat history it
  happens to still see. Grounding is the point.
- `record_decision` and `recall_decisions` must agree on the file path and schema.
- Don't let the recall answer trip the Founder Rule into staying silent — it's a reply.

**Done when:** a founder "why…?" returns an answer sourced from `evergreen_memory.jsonl`
with no specialist convened, matching a real recorded rationale; the negative case is
handled.

---

## STEP 2 — Simulated clock + persistence-across-restart — ✅ DONE (2026-06-18)

> Shipped: `clock/sim_clock.py` (`SimClock` real-secs→sim-days, persisted to
> `clock/clock_state.json`, fire-once via persisted last-day; `read_current_day()`
> for stamping). Market Watcher refactored to clock-driven (SCHEDULE by sim-day,
> quiet days log-only, sim-day stamped on events; run via `-m`). `record_decision`
> stamps `sim_day`; `recall_decisions` shows "sim-day N · date". Verified live:
> quiet days → minor (not material) day 3 → material cascade day 12 → full restart
> preserved memory + resumed sim-day with NO replay. Built sync (stdlib) to fit the
> send-only REST watcher. Honest boundary: LangGraph `InMemorySaver` (in-flight
> graph state) does NOT survive restart — durable record does; SQLite checkpointer
> deferred. Note: at a fast clock the decision's `sim_day` can trail the event's day
> (cascade spans sim-days) — use a slower clock for a same-day demo.

**Goal:** make the time dimension visible (room idle for "days", then wakes on a
scheduled day) and prove the room's state survives a full restart. This is the pillar
the litmus test is named after.

### 2A. Simulated clock (`clock/sim_clock.py`)
Build it as **real scheduling infrastructure**, not a demo prop — the same seam later
drives scheduled beats (weekly review, renewal day, month-end), which are real product
features.
- A `SimClock` mapping real seconds → sim-days. Config from env:
  `SIM_SECONDS_PER_DAY` (e.g. 5), `SIM_START_DAY` (default 1).
- **Persist `current_day`** to `clock/clock_state.json` so a restart resumes the
  sim-day instead of resetting to 0. (This is also half of the persistence demo.)
- API: `current_day() -> int`, and an async loop/generator that yields each new sim-day
  as real time advances. Keep it minimal — a day counter, not a generic cron.
- **Do not persist secrets** in `clock_state.json`.

### 2B. Drive the Market Watcher off the clock
Refactor `agents/watchers/market_watcher.py` (currently a bare tick loop) to use the
`SimClock`:
- Hold a `SCHEDULE = {sim_day: event_payload}` (a couple of entries: one not-material
  on an early day, the material competitor event on a later day, e.g. day 12 to match
  the demo narrative).
- On each new sim-day, if there's a scheduled event, POST it via the existing REST path
  (§5), stamping the message/metadata with `sim_day`. On days with nothing scheduled,
  stay quiet (you may log "day N — all quiet" to the watcher's own console, but NEVER
  post idle chatter into the room — watchers don't chatter).
- **Fire-once discipline (important):** an event for day N fires only when the clock
  first crosses into day N. After a restart, resume at the persisted day so already-fired
  days are NOT replayed. This is the watcher's change-detection discipline (only fire on
  genuinely new) and it keeps the orchestrator's "trust every event" contract honest.

### 2C. Persistence-across-restart
- **What already persists:** the Band room + its history (server-side),
  `evergreen_memory.jsonl` (disk), and now `clock/clock_state.json` (sim-day).
- **What does NOT persist — flag honestly:** the orchestrator's LangGraph
  `InMemorySaver()` checkpointer. In-flight graph state (a half-finished investigation)
  is lost on restart. For the hackathon the durable record (memory + room + sim-day) is
  enough to demonstrate the pillar — do not over-build.
  - **Real-product upgrade (optional, only if time):** swap `InMemorySaver` for a
    persistent LangGraph checkpointer (SQLite) so in-flight investigations also survive.
    Pointer only; mark optional and confirm the exact class against the installed
    LangGraph version before using it (no bluffing).

### Verify Step 2 (what to run)
1. Start orchestrator + both specialists + watcher in one room. Watch the watcher log
   show sim-days advancing, quiet days, then the scheduled event firing on its day →
   full cascade → room resumes quiet.
2. Run a cascade so a decision is recorded; note the sim-day.
3. **Kill all processes. Restart them.** Confirm: (a) `evergreen_memory.jsonl` intact;
   (b) sim-day resumed from `clock_state.json` (not reset); (c) Band room history present
   in the UI; (d) the watcher does NOT replay already-fired days.
4. The clincher (depends on Step 1): as the founder, ask "why did we decide X?" about
   the **pre-restart** decision → `recall_decisions` answers it. That is the persistence
   pillar, proven.

### Pitfalls (Step 2)
- Don't replay past scheduled events after a restart (2B fire-once).
- One room only; connect specialists before the scheduled event fires (gotcha #13).
- Keep the clock minimal — resist building a general scheduler.

**Done when:** the sim-clock visibly advances with quiet days and a scheduled wake; a
full restart preserves memory + sim-day + room history with no event replay; and a
pre-restart decision is still recallable.

---

## STEP 3 — Retention & Hiring specialists

**Goal:** broaden the specialist pool so the orchestrator's *dynamic convening* shows
across more expertises (and richer fan-out). Not a pillar gap, but high value for low
effort now that `_base.py` exists.

### Pattern (locked — do not deviate)
Each specialist module = **backstory + analysis instructions + `run_specialist(...)`**
on `agents/specialists/_base.py`. Both new ones should be **grounded** (pre-fetch +
inject), like Finance — the prime directive favors real numbers over persona estimates.
- Add a data slice to `core/company_data.py`, internally consistent with the existing
  form-builder company.
- Write a `build_*_snapshot()` that renders that slice into a `COMPANY … DATA
  (authoritative)` block, injected via `custom_section`.
- **No choose-able data tools** (adapter discards the final answer — §8).
- **Do not** re-add the "report only to the orchestrator" paragraph — `_base.py`
  forces the recipient in code.
- Output format: the same four-part, decision-ready shape — what's happening / severity
  / who's exposed / one recommended action.

### 3A. Retention specialist (`agents/specialists/retention.py`)
- Domain: churn, customer health, retention plays, at-risk revenue, NRR/GRR, cohort
  retention.
- New `company_data.py` slice (suggested): monthly logo + revenue churn (trailing),
  NRR/GRR, at-risk segment(s) (e.g. the Starter cohort), optionally a few at-risk
  accounts. `build_retention_snapshot()`.

### 3B. Hiring specialist (`agents/specialists/hiring.py`)
- Domain: hiring pipeline, key open roles, attrition, time-to-fill, headcount plan vs
  actual.
- New slice (suggested): open reqs by function, pipeline counts/stages, attrition rate,
  time-to-fill, plan-vs-actual headcount. `build_hiring_snapshot()`.

### 3C. Wire them into routing
- Extend the orchestrator's CONVENE step: add **Retention** (churn / customer-health /
  retention) and **Hiring** (hiring / attrition / org-capacity) to the routing rules,
  and add fan-out examples (e.g. a churn spike → Retention AND Finance; a key
  departure → Hiring AND the People & Voice signal).
- Routing is by **peer description** — create both agents on Band under the same
  account with clear descriptions; add them to `agent_config.yaml`; keep their
  processes running and connected before convening.

### Verify Step 3 (what to run)
- Retention route: `@Orchestrator [event] Monthly churn jumped from 2% to 5%, mostly on
  the Starter plan.` → orchestrator convenes Retention (and possibly Finance) → grounded
  reply addressed to the orchestrator → stand-down → one founder brief.
- Hiring route: a key-departure or stalled-pipeline event → convenes Hiring similarly.
- Confirm fan-out across four specialists still stands each down and sends exactly one
  founder brief.

**Done when:** the orchestrator convenes Retention and Hiring on the right events, both
reply grounded to the orchestrator, and stand-down + single-brief behavior holds across
the larger pool.

---

## STEP 4 — Real watchers (DEFERRED — do not build during the hackathon)

Stubs are fine; the watcher→orchestrator interface is just a posted event, so swapping
the feed for a real source changes nothing downstream. **Do not build real integrations
now** — it's scope creep against a tight deadline (gotcha: scope discipline). Documented
here only so the design is ready.

When it's time: **connector + change-detection (fire only on NEW) + light relevance
filter** against the company profile. The **Metrics watcher is the cleanest first real
one** (deterministic, no fuzzy relevance): query Stripe/PostHog/DB on a timer, z-score
against a stored baseline, fire on threshold breach. Market and People & Voice are
fuzzier (need relevance filtering / NLP). The watcher still only **detects** — never
analyzes or recommends.

---

## STEP 5 — Partner-prize claim (submission task, not code)

- **AI/ML API** already powers all reasoning agents — make that visible in the
  submission and claim "Best Use of AI/ML API". Nothing to build.
- **Featherless** (optional, only if time): run ONE specialist on an open-source model
  via Featherless — an env-driven model/base-url swap for that specialist, eligible for
  "Best Use of Featherless AI". Nice-to-have, not core; don't let it block 1–3.

---

## C. Consistency contract (the short version to keep open while coding)

- Build in order 1 → 2 → 3; treat 4 as deferred and 5 as admin.
- Match shipped patterns; don't invent Band APIs (fetch §12 docs or read SDK source).
- Every specialist: through `_base.py`, pre-fetch + inject, no choose-able data tools.
- `band_send_message` is the only delivery path; recipient forced in code.
- Orchestrator: every event ends in a tool call; one founder mention per event (a
  recall reply is exempt).
- Verify via logs + `evergreen_memory.jsonl` + Band UI — never `GET …/messages`.
- One room; connect specialists before convening; config stays env-driven.
- Re-verify `_base.py` after any `band-sdk` upgrade.
- Flag assumptions before coding; small reviewable changes; say what to run to verify;
  keep the transcript human-readable.
- Don't expand scope (especially real watchers / real integrations) without asking
  first and stating the trade-off.