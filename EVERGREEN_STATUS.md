# Evergreen — Complete Project Description & Build Record

> The single, self-contained source of truth for Evergreen: what it is, why it's built
> this way, the hard-won Band SDK facts, the full company definition, everything built
> and verified, the decisions behind each piece, and how to run it. Self-contained —
> you do not need any other file to understand or operate the project. (Other
> `EVERGREEN_*.md` files remain as historical design briefs; this doc supersedes them
> as the canonical description.) Last updated 2026-06-19.

---

## 1. What Evergreen is

Assign an AI **room** to an **outcome**, and it owns that outcome for its whole
lifetime — watching continuously, waking on real-world events, convening the right
specialists and humans, recording every decision and the reasoning behind it, then
going back to watching.

Most agent systems are vending machines: request → burst of work → output → off.
Evergreen inverts that: you don't give it a task, you give it an outcome to **own**.

**Three non-negotiable pillars (what make it "Evergreen"):**
1. **Persistent** — a room stays alive over weeks/months; state survives restarts.
2. **Event-driven** — it reacts the moment something happens, not on prompt.
3. **Institutional memory** — it remembers every signal, decision, and rationale, and
   can answer "why did we decide X?" months later.

**Litmus test:** if the system would still work after deleting the simulated clock and
the memory, it has degraded into a one-shot pipeline — that's failure. Both are
load-bearing here.

**Use case (locked):** a *Startup Operating System* / "chief-of-staff." The room owns
one outcome — *keep the company healthy and growing*.

**The differentiator — dynamic convening:** per event, the orchestrator assembles a
situation-specific task force (specialists + the right humans) via Band's
add/remove-participant primitives, then stands it down. The room persists and
remembers; only the roster flexes.

### Prime directive & working principles (every change obeys these)
- **A genuinely usable real-world product, NOT a hackathon demo.** When a demo
  shortcut and a real-product choice diverge, take the real one.
- **Respect the funnel; never blur the tiers** (detect / triage / analyze — see §3).
- **Never bluff Band** — fetch the docs or read the SDK source; never invent an API.
- **`band_send_message` is the only delivery path** (§4); grounded specialists
  **pre-fetch-and-inject** (no choose-able data tools); recipient is **forced in code**.
- **Detection never judges** — a watcher emits a raw observation only; materiality is
  the orchestrator's job, meaning is the specialist's.
- **One room; connect specialists before convening** (no offline mention queue).
- **Env-driven config; never commit secrets. Verify via logs + memory + the Band UI**
  (the agent REST `messages` endpoint is a work queue, not a transcript).
- Small reviewable changes; keep the room transcript short and human-readable (it is
  both the UX and the audit trail).

---

## 2. The company — Quillo (fictional)

All tiers reason about a concrete company. Identity lives in
`core/company_profile.py`; the financial numbers (the day-0 seed the fake source
evolves) live in `core/company_data.py`.

- **Identity:** **Quillo**, a SaaS **form & survey builder** for SMB teams and
  non-technical operators. Plans: Free / Starter / Pro / Business.
- **Watchlist (the keystone for relevance + materiality):** major/direct competitor
  **Typeform**; minor competitors **FormFly, Jotform, Google Forms, Tally**; category
  keywords "form builder", "survey tool", "AI form", "lead capture".
- **Watch thresholds (env-overridable):** MRR drop ≥ 10% vs trailing mean, z ≥ 3.0.
- **Book of business (day-0 seed):** Free 3,200 ($0) · Starter 1,150 @ $19 = $21,850 ·
  Pro 380 @ $49 = $18,620 · Business 52 @ $149 = $7,748 → **MRR $48,218** (~1,582
  paying), ARR ~$578k. Trailing 6-mo MRR 39,800 → 48,218.
- **Unit economics:** CAC $180, LTV $720 (LTV:CAC 4:1), gross margin 82%, payback 7mo.
- **Cash:** burn $62k/mo, cash $740k → ~12mo runway.
- **Retention slice:** 3.2% monthly logo / 2.8% gross-rev churn; NRR 102%, GRR 96%;
  per-plan churn Starter 4.5% / Pro 1.6% / Business 0.8% (Starter is the at-risk
  cohort); at-risk accounts Northwind Co (Pro), Acme Forms (Business).
- **Hiring slice:** 18 actual vs 21 plan; attrition 2.1%/mo; time-to-fill 48 days; 3
  open reqs (Sr Backend Eng, Product Designer, CS Lead).

---

## 3. Architecture — the funnel

Three tiers of agents, plus humans and infrastructure. Each tier is deeper and more
expensive than the last:

1. **Watchers = detection.** "Did something happen in our world?" Broad, continuous,
   cheap, shallow — a *sensor*. Organized **by data source** (Market/External,
   Metrics, People & Voice). NEVER analyzes, recommends, or self-escalates. It may
   *filter* ("is this in our world / did it move beyond normal?") but never *judge*.
2. **Orchestrator = triage.** "Does this matter to us right now, and who should look?"
   The only coordinator/router. Judges materiality, routes to specialist(s), never
   analyzes a domain question itself.
3. **Specialists = analysis.** "What does it mean, how bad, what do we do?" Deep,
   narrow, on-demand. Organized **by expertise**. Never watch, never self-trigger; sit
   dormant until convened; report only to the orchestrator.

Watchers and specialists do **not** map 1:1 — the orchestrator is the router, and one
signal can fan out to several specialists (e.g. a priced competitor move → Competitive
Analysis *and* Finance). Company knowledge lives in a shared profile all three tiers
read (`company_profile.py` + `company_data.py`).

**Cross-framework (a hackathon criterion, met):** Orchestrator on **LangGraph** (model
`gpt-4o`); Specialists on **CrewAI** (model `gpt-4o-mini`). **Band** is the
coordination spine (remove it and the system collapses — by design). All reasoning via
the **AI/ML API**. Humans (founder) and infra (memory, clock) are not agents.

---

## 4. Band SDK / platform facts (hard-won; not obvious from the code)

Distribution **`band-sdk` 1.0.0**; import `band` (docs also say `thenvoi`; code tries
both). Extras `[crewai]`, `[langgraph]`. Python 3.13, uv.

- **Agent lifecycle:** `Agent.create(adapter, agent_id, api_key, ws_url=, rest_url=)`
  then `await agent.run()` (connects WebSocket, runs forever). Creds per agent in
  `agent_config.yaml` via `load_agent_config("name")`.
- **Agents are REACTIVE** — they only process messages that **@mention** them. There is
  **no offline queue**: a mention sent while an agent is disconnected is missed (start
  agents and let them connect *before* events — this caused a "watcher stopped working"
  red herring once).
- **`auto_subscribe_existing_rooms=True`** by default → an agent subscribes to ALL
  rooms it's in at startup. Accumulated test rooms cause history bloat and noise
  ("room churn") — keep ONE room. Heavy room history once caused the orchestrator to
  skip recording a decision; a clean room fixed it.
- **Platform tools (auto-injected):** `band_send_message(content, mentions)`,
  `band_send_event`, `band_add_participant`, `band_remove_participant`,
  `band_get_participants`, `band_lookup_peers`, `band_create_chatroom`. Sibling agents
  under one account auto-discover via `band_lookup_peers`.
- **⚠️ Plain LLM/agent output is NOT delivered — the agent MUST call
  `band_send_message`.** For CrewAI specifically, the adapter (band/adapters/crewai.py)
  appends the agent's final answer (`result.raw`) only to internal history and
  **discards it for the room** — the only path to the room is the `band_send_message`
  *tool* called *during* the run. (This is the root of the original Finance bug — §6.)
- **⚠️ Recipient routing is model-chosen, and Band biases it wrong.** `send_message`
  routes by the `mentions` the model produces. Band injects a fixed block into every
  agent's prompt (`band/runtime/prompts.py :: BASE_INSTRUCTIONS`):
  `## Relaying` ("deliver to the original requester" → made specialists answer the
  founder), `## Activation`, `## Delegation` ("don't remove added agents" → fights
  stand-down). Out-prompting these is unreliable; Evergreen **suppresses the block**
  (`include_base_instructions=False`) and **forces the recipient in code** (§5.2).
- **Adapters:** `LangGraphAdapter(llm, checkpointer, additional_tools, custom_section)`;
  `CrewAIAdapter(model, role, goal, backstory, custom_section, additional_tools=[(PydanticModel, handler)], ...)`.
  For CrewAI custom tools, the model class name is the tool name, its docstring the
  description, the handler takes the model and returns a string.
- **Agent REST API** (used by the send-only watchers): base `…/api/v1/agent`, auth
  header **`X-API-Key`** (not Bearer).
  - `POST /chats/{id}/messages` body `{"message": {"content": "@Name …", "mentions": [{"id": uuid}]}}` — the @Name is display; the `id` routes; ≥1 mention required.
  - `GET /chats/{id}/participants`; `POST /chats/{id}/participants` body
    `{"participant": {"participant_id": uuid, "role": "member"}}`;
    `DELETE /chats/{id}/participants/{participant_id}`.
  - `POST /chats` body `{"chat": {}}` creates a room **with the calling agent as owner**.
  - **`GET /chats/{id}/messages` is a WORK QUEUE, not a transcript** — returns only
    pending messages, reads empty once processed; listing a room you're not in → 404.
    Verify runs via agent logs + `evergreen_memory.jsonl` + the Band UI.
- **Good-citizen web hygiene (real Market watcher):** respect `robots.txt`
  (`urllib.robotparser`), identifiable User-Agent, conditional GET, sane interval,
  prefer official feeds. Some pages (Typeform help-center) WAF-block automated GETs
  (403) — don't circumvent; use a legitimate fetchable source.

---

## 5. Components in detail (everything built)

### 5.1 Orchestrator — `agents/orchestrator.py` (LangGraph, gpt-4o)
Reacts only to @mentions; every event ends in a tool call (never silent). Loop: judge
materiality → convene specialist(s) → stand each down on reply → decide → record.
- **Materiality grounded in the profile:** a lean Quillo identity + watchlist summary
  is prepended to `CHIEF_OF_STAFF_PROMPT`, so a **major** competitor move is material
  and a **minor** one is not — judged against the watchlist, not generic priors.
- **Fan-out + wait-for-all:** convene every fitting specialist, wait for all, then one
  synthesized founder brief.
- **The Founder Rule + hardening:** at most one founder message per event, and it goes
  **only to the human** participant — never a watcher/specialist; if no human is in the
  room, record silently instead of mis-addressing an agent.
- **No status spam; stay silent while waiting** (even when re-pinged).
- **Answering the founder about the past:** a founder question is a direct query →
  `recall_decisions` + a reply via `band_send_message`, no convene.
- Tools: `record_decision`, `recall_decisions`.

### 5.2 Shared specialist base — `agents/specialists/_base.py`
The robustness layer every specialist runs through (`run_specialist(...)`), encoding
guarantees in **code, not prompts**:
- **Deterministic recipient:** a tools proxy rewrites every `band_send_message` to the
  orchestrator (resolved from the live participant list, cached), regardless of the
  model's `mentions`.
- **Suppress Band's conflicting instructions:** module-global patch of
  `render_system_prompt` to `include_base_instructions=False`, dropping
  Relaying/Activation/Delegation; supplies a minimal conflict-free platform note.
- **Identity grounding:** injects the Quillo profile summary into every specialist.
- **As-of context injection:** an optional `context_provider` recomputed per convene and
  injected into the incoming message (`PlatformMessage` is a frozen dataclass →
  `dataclasses.replace`), so time-varying specialists reflect current reality.
- Sets `logging.basicConfig` (no silent specialists).

### 5.3 Specialists
- **Competitive Analysis** (`competitive_analysis.py`) — persona; competitor threat
  assessment; no data tools.
- **Finance** (`finance.py`) — grounded. **Was the original blocked bug** (its answer
  never reached the room — see §4 CrewAI discard + the choose-able-tools second exit).
  Fixed by pre-fetching figures and injecting them. Now reads **as-of-sim-day** figures
  from the fake source so its numbers match what the watcher reported.
- **Retention** (`retention.py`) — grounded; churn / NRR / GRR / at-risk revenue;
  as-of Starter cohort.
- **Hiring** (`hiring.py`) — grounded (static slice); pipeline / attrition / headcount.
- All: pre-fetch-and-inject, **no choose-able data tools**, recipient forced in code.

### 5.4 Simulated clock — `clock/sim_clock.py` (Pillar 1)
- **Wall-time-anchored:** `clock_state.json` is a write-once anchor
  `{anchor_epoch, anchor_day, seconds_per_day}`;
  `current_day = anchor_day + floor((now − anchor_epoch)/seconds_per_day)`. Any number
  of processes share ONE sim-day with no write races; the persisted `seconds_per_day`
  means they agree even if their env rates differ (a real bug found + fixed).
- `tick()` yields only new days (restart resumes, no replay); legacy `{current_day}`
  migrates; `read_current_day()` lets other processes stamp the day; public interface
  unchanged. Sim-time flows with wall-time (downtime advances days; `rm` resets).

### 5.5 The Fake Company workstream (A–G) — real internal detection (Pillar 2)
- **A — Profile** (`core/company_profile.py`): identity + watchlist + thresholds;
  `profile_summary()` injected into the orchestrator. (§2.)
- **B — In-process fake Stripe** (`core/sources/fake_stripe.py`): SDK-shaped
  `subscriptions.list(as_of=day)` returning raw subscription dicts (no precomputed MRR
  — the watcher derives it). Deterministic from `(FAKE_DATA_SEED, as_of)` so restart
  re-derives the timeline without persisting it; anchored on day-0 ($48,218); mild
  seeded daily variation; **planted ~300 Starter churn on day 12 (≈ −12% MRR)**.
- **C — Event contract + Metrics watcher** (`core/events.py`,
  `agents/watchers/metrics_watcher.py`): `Event`
  (source/signal_type/observation/magnitude/dedup_key/sim_day/evidence/watcher),
  rendered as a readable line + `<event>{json}</event>` tail. The watcher pulls
  subscriptions, **derives MRR**, baselines it (window rebuilt from the deterministic
  source), detects via **%Δ-vs-trailing-mean (primary) + z-score (confirmation) with a
  min-stddev floor**, seeds silently, dedups (fire-once, persisted), emits raw
  magnitude only.
- **D — Clock-as-driver + persistence:** the watcher reads the wall-anchored clock;
  restart resumes with no replay.
- **E — Specialist coherence:** identity grounding for all; Finance/Retention pre-fetch
  **as-of the event's sim-day** so their numbers match the watcher (no contradiction).
- **F — Memory provenance:** `record_decision` stamps `source`/`signal_type`;
  `recall_decisions` searches + shows it (`[event: stripe/mrr_drop]`).
- **G — End-to-end proof** (room `078d8912`): quiet sim-days → day-12 churn → derive &
  fire `mrr_drop` → convene Finance + Retention → as-of grounded replies → one founder
  brief to the human → decision recorded with provenance (sim_day 12) → full restart
  resumes (no replay, memory intact) → a fresh orchestrator recalled the pre-restart
  decision from memory, no convene.

### 5.6 Real Market watcher — `agents/watchers/market_watcher.py` (Pillar 2)
Detection over **real external competitor sources** (the family that maps to a fictional
company, because the competitors are real).
- **Two modes:** `MODE=real` (default; wall-clock; real sources) and `MODE=scripted`
  (original sim-clock feed, kept as the on-cue demo beat). Both post as the Market
  Watcher; run alongside.
- **Curated sources = the watchlist (inherent relevance, no LLM gate):**
  - **Typeform** (major) — `typeform.com/whats-new` **page-diff** (the help-center
    changelog is WAF-blocked/403; swapped to the fetchable main-domain page).
  - **Jotform** (minor) — product blog **RSS** (Product category).
  - **Google Forms** (minor) — Workspace Updates Blogger **Atom** label feed.
  - **Tally** (minor) — `tally.so/changelog` **page-diff** (date headings).
- **Mechanics:** identifiable User-Agent, conditional GET, **robots.txt respected**,
  per-source fail-soft (never crash the room). bs4 strips nav/footer; a
  **format-agnostic parser** handles RSS `<item>` AND Atom `<entry>` (stdlib
  ElementTree). **Page-diff = heading + blurb**: the dated heading is the stable change
  key (blurb edits don't false-fire), the blurb is surfaced so a pricing line routes to
  Finance. Seeds silently; persists seen-set/hashes (`market_watcher_state.json`,
  fire-once, restart-safe); emits the event contract + evidence URL; raw observation
  only; stamped with `sim_day` but polled on real time (`MARKET_POLL_SECONDS`, 900).

### 5.7 Institutional memory (Pillar 3)
- `record_decision` appends JSON lines to `evergreen_memory.jsonl`
  (entry_id/kind/summary/rationale/actors/source/signal_type/sim_day/timestamp).
- `recall_decisions(query)` — keyword-overlap + recency with a document-frequency
  relevance gate (a lone common word can't false-match); provenance included; scoring
  isolated in `_score()` for a future embedding swap; graceful "no record" message.

### 5.8 Watchers — identities & scripted/real split
- Two Band identities: **Market Watcher** (external) and **Metrics Watcher** (internal;
  reads `METRICS_WATCHER_API_KEY`, falls back to the Market key). Market Watcher runs
  scripted (demo beat) or real (continuous proof).

### 5.9 Project infrastructure
- Env-driven (`.env`); **secrets gitignored** (`.env`, `agent_config.yaml`) with
  `.example` templates. Git repo **github.com/dineshsai05/Evergreen** (private),
  push after every change. `README.md`. Runtime state gitignored (regenerated):
  `evergreen_memory.jsonl`, `clock/clock_state.json`, `metrics_watcher_state.json`,
  `market_watcher_state.json`.

---

## 6. Build history / milestones (chronological)

1. **Foundation (pre-existing):** orchestrator + Competitive Analysis + Market Watcher
   stub working through Band; the materiality gate and a single founder brief.
2. **Finance unblocked:** root-caused the "Finance never delivers" bug to the CrewAI
   adapter discarding `result.raw` (only `band_send_message` delivers) — its data tools
   gave the model a non-delivering second exit. Fixed by pre-fetch-and-inject.
3. **Shared `_base` robustness layer:** forced recipient + suppressed Band's
   Relaying/Activation/Delegation blocks (specialists were addressing the founder).
4. **Step 1 — Memory recall:** `recall_decisions` + the "answer the founder about the
   past" prompt branch; fixed a delivery bug (recall replies must go via
   `band_send_message`).
5. **Step 2 — Simulated clock + persistence:** clock-driven watcher; restart resumes,
   no replay. (Clock later upgraded to wall-anchored in the Fake Company Step D.)
6. **Step 3 — Retention & Hiring specialists** on `_base` (grounded).
7. **Fake Company workstream A–G** (§5.5): defined Quillo; in-process fake Stripe;
   real Metrics watcher; wall-anchored clock + shared-rate fix; as-of specialist
   coherence; memory provenance; end-to-end proof.
8. **Orchestrator hardening:** founder brief to the human only; silent record if none.
9. **Real Market watcher** (§5.6): wall-clock connector over real competitor pages;
   page-diff + RSS + Atom; heading+blurb; full watchlist; cascade-verified.
10. **Docs + repo hygiene** throughout; this consolidated description.

---

## 7. Tech stack, providers & config

- **Coordination:** Band. **Orchestrator:** LangGraph + `gpt-4o`. **Specialists:**
  CrewAI + `aiml/gpt-4o-mini`. **Reasoning provider:** AI/ML API (OpenAI-compatible,
  $20 min top-up, pay-as-you-go; a partner-prize target — used visibly).
- **Provider journey (so nobody re-treads it):** Groq **OUT** (its strict JSON-schema
  validator rejects Band's `band_send_event` tool schema); Gemini free tier **OUT**
  (20 requests/day cap); **AI/ML API IN**. Everything env-driven, so swaps need no code.
- **`.env` shape:**
  ```
  LLM_BASE_URL=https://api.aimlapi.com/v1   LLM_API_KEY=<aiml>   ORCHESTRATOR_MODEL=gpt-4o
  AIML_API_KEY=<aiml>   SPECIALIST_MODEL=aiml/gpt-4o-mini
  THENVOI_WS_URL=wss://app.band.ai/api/v1/socket/websocket   THENVOI_REST_URL=https://app.band.ai
  EVERGREEN_ROOM_ID=<uuid>   ORCHESTRATOR_NAME=Orchestrator
  MARKET_WATCHER_API_KEY=<key>   METRICS_WATCHER_API_KEY=<key>
  SIM_SECONDS_PER_DAY=5   SIM_START_DAY=1
  FAKE_DATA_SEED=42   PLANTED_CHURN_DAY=12   MARKET_POLL_SECONDS=900
  ```
- **`agent_config.yaml`:** per-agent `{agent_id, api_key}` for orchestrator,
  competitive_analysis, finance, retention, hiring (gitignored; `.example` provided).
  The watchers authenticate via REST keys in `.env`, not `load_agent_config`.

---

## 8. Key decisions & gotchas resolved
- Providers: Groq/Gemini out, AI/ML in (above).
- CrewAI adapter discards the final answer → `band_send_message` only → grounded
  specialists pre-fetch-and-inject, no choose-able data tools.
- Band injects conflicting prompt blocks → suppress in code + force recipient in code.
- Room churn (auto-subscribe + history bloat) caused a decision-skip once → use one
  clean room; reset runtime state for clean demos.
- Wall-clock vs sim-clock: real pages can't be fast-forwarded → Market watcher polls
  real time, stamps `sim_day`; the clock anchor must persist `seconds_per_day`.
- Founder = the human only — never brief an agent.
- WAF walls (Typeform help-center 403) — don't circumvent; use a legitimate source.
- Page-diff noise — diff extracted text (not raw HTML); heading is the change key,
  surface the blurb.
- Determinism (seeded fake source) lets restart re-derive the timeline without
  persisting it; only fire-once/dedup state needs disk.
- Literal `\n` / verbatim relaying in messages → instruct plain short sentences.

## 9. Verification ledger (proven live, by room)
- `ea9b566e` — early full cascade (Typeform fan-out), materiality gate, recall, Step 2
  persistence, Step 3 Retention/Hiring, Step A grounding.
- `4b3567f9` — cross-room recall of a prior decision.
- `078d8912` — Fake Company Step G end-to-end (churn cascade → restart → recall).
- `ea531147` — real Market watcher cascade v1 (Typeform material / Jotform not-material).
- `aff3e3cf` — real Market watcher cascade v2 (heading+blurb → priced Typeform release
  fanned out to Competitive Analysis + Finance).
- Standalone/unit: clock (race-free/resume/no-replay), fake_stripe (curve +
  determinism), metrics detection (seed/fire-once/restart), market change-detection
  (RSS + Atom + page; noise-robustness), live-seed of all four real sources.

---

## 10. Remaining (all optional / deferred)
- **Submission writeup** (`SUBMISSION.md`) — next; lead with AI/ML API usage.
- **Watcher extras:** competitor pricing-page diffing (`competitor_pricing_change`);
  a generic watcher `_base` (only once a 3rd real watcher pays off); Metrics→real
  Stripe (one-line backing swap); People & Voice (needs real customer data) — deferred.
- **Infra:** push/webhook ingestion; real wall-clock scheduler; scheduled beats
  (calendar-sourced); persistent LangGraph checkpointer (SQLite) for in-flight state;
  embedding-based recall; alerting channels.
- **Cleanup:** delete the stale generic `COMPANY` dict in `core/company_data.py`
  (unused; identity is canonical in `company_profile.py`); delete stale Band test rooms.

---

## 11. Repo map & how to run

```
agents/
  orchestrator.py                  # LangGraph; record_decision + recall_decisions
  specialists/
    _base.py                       # forced recipient, prompt-fix, identity + as-of injection
    competitive_analysis.py  finance.py  retention.py  hiring.py
  watchers/
    market_watcher.py              # MODE=real (curated competitor sources) | MODE=scripted
    metrics_watcher.py             # derives MRR from the source; real detection
core/
  company_profile.py               # Quillo identity + watchlist (read by all tiers)
  company_data.py                  # day-0 financial seed (numbers)
  events.py                        # Event contract
  sources/fake_stripe.py           # in-process, as_of, deterministic
clock/sim_clock.py                 # wall-time-anchored sim-days (shared anchor)
evergreen_memory.jsonl             # decision log (gitignored runtime state)
.env / agent_config.yaml           # secrets (gitignored; *.example templates committed)
```

**Setup:** create the agents on Band (Orchestrator, Competitive Analysis, Finance,
Retention, Hiring, Market Watcher, Metrics Watcher) under one account with clear
descriptions; create a room; add the Orchestrator + the watcher(s) (+ yourself as the
founder). `uv sync`; copy `.env.example`→`.env` and `agent_config.example.yaml`→
`agent_config.yaml` and fill in keys.

**Run** (project root; orchestrator + specialists first, let them connect):
```
uv run python -m agents.orchestrator
uv run python -m agents.specialists.{competitive_analysis,finance,retention,hiring}
uv run python -m agents.watchers.metrics_watcher
uv run python -m agents.watchers.market_watcher                      # real
MARKET_WATCHER_MODE=scripted uv run python -m agents.watchers.market_watcher  # demo beat
```

**Verify** via agent logs + `evergreen_memory.jsonl` + the Band UI — never the agent
REST `messages` endpoint (work queue). Reset runtime state for a clean demo:
`rm evergreen_memory.jsonl clock/clock_state.json metrics_watcher_state.json market_watcher_state.json`.
