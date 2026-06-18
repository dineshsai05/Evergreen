# Evergreen — Full Project Context & Build Log

> Single-file context primer. Read this top to bottom to understand what Evergreen is,
> why it's built the way it is, what's done, what's broken, and the hard-won Band SDK
> facts that aren't obvious from the code. The actual source lives in the repo; this
> file is the *reasoning and state* around it.

---

## 0. Prime directive

**We are building a genuinely usable real-world product, NOT a hackathon demo.**
Favor real-world practicality over demo shortcuts in every design decision.

Working principles that have been enforced throughout:
- Direct, opinionated recommendations; the human makes the final architecture call.
- No premature code during conceptual discussions — answer the question asked first.
- Flag assumptions and unknowns *before* writing code. Never bluff. If a Band API
  detail is unknown, fetch the real docs or read the SDK source — do not invent it.
- Small, reviewable changes; say exactly what to run to verify each one.
- Keep the room transcript human-readable — it's both the UX and the audit trail.

---

## 1. What Evergreen is

Assign an AI **room** to an **outcome**, and it owns that outcome for its whole
lifetime — watching continuously, waking on real-world events, convening the right
specialists and humans, recording every decision, then going back to watching.

Most agent systems are vending machines: request → burst of work → output → off.
Evergreen inverts that: you don't give it a task, you give it an outcome to *own*.

**Three non-negotiable properties** (these are what make it "Evergreen"):
1. **Persistent** — a room stays alive over weeks/months; state survives restarts.
2. **Event-driven** — it reacts to things the moment they happen, not on prompt.
3. **Institutional memory** — it remembers every signal, decision, and rationale,
   and can answer "why did we decide X?" months later.

**Litmus test:** if the system would still work after deleting the simulated clock
and the memory, it has degraded into a one-shot pipeline. That's failure.

**Locked use case:** *Startup Operating System* ("chief-of-staff"). The room owns
"keep the company healthy and growing."

**The differentiator:** *dynamic convening*. The orchestrator assembles a
situation-specific task force (specialist agents + the right humans) per event via
Band's add/remove-participant primitives, then stands it down. The room persists and
remembers; only the roster flexes.

---

## 2. Architecture

Three tiers of agents, plus humans and infrastructure.

### The mental model (settled after a long discussion — this is the core)

Think of a funnel, each layer deeper and more expensive than the last:

1. **Watcher = detection.** "Did something happen in our world?" Broad, continuous,
   cheap, shallow. A *sensor*, not an analyst. Surfaces a raw signal ("MRR down 15%",
   "Raspberry Pi 6 announced") after a light relevance filter. NEVER says what it
   means or recommends anything. If a watcher recommends, it's overstepping.
2. **Orchestrator = triage.** "Does this matter to us right now, and who should
   look?" Judges materiality, routes to a specialist. Routing, not analysis.
3. **Specialist = analysis.** "What does this mean, how bad, what do we do?" Deep,
   narrow, on-demand. The ONLY layer that does "the study."

Key consequences:
- **Watchers are organized by source** (Market/External, Metrics, People & Voice).
  **Specialists are organized by expertise** (Competitive, Finance, Retention,
  Hiring...). They do NOT map 1:1 — the orchestrator is the router. One signal can
  fan out to several specialists (e.g. a competitor price cut → Competitive *and*
  Finance).
- **Specialists never watch anything and never self-trigger.** They are consultants
  that sit dormant until the orchestrator convenes them. The trigger always
  originates from a watcher (or a human, or a scheduled beat) → orchestrator →
  specialist.
- **Company-specific knowledge lives in a shared company profile** that all three
  tiers read (the watcher filters against it, the orchestrator triages against it,
  the specialist analyzes against it). This is the same institutional-memory pillar.
  Today this is `core/company_data.py` (mock).

### Tier 1 — Orchestrator (Chief of Staff)
- The only coordinator. Framework: **LangGraph**. Model: **gpt-4o** (via AI/ML API).
- Loop: judge materiality → convene the right specialist → on reply, stand the
  specialist down → decide (low-risk = record & stay quiet; high-risk = one founder
  brief) → record to memory.
- Two memory tools (LangChain `@tool`): `record_decision` appends JSON lines to
  `evergreen_memory.jsonl` (write path); `recall_decisions(query)` reads them back to
  answer a founder's "why did we decide X?" (read path — keyword-overlap + recency,
  with a relevance gate; scoring isolated in `_score()` for a future embedding swap).
  A founder *question* is handled as a direct query (recall + reply, no convene), not
  an event — see the prompt's "ANSWERING THE FOUNDER ABOUT THE PAST" branch.

### Tier 2 — Watchers (sensors)
- Mostly idle, by data source: **Market**, **Metrics**, **People & Voice**.
- Detection only (rule/threshold/relevance-filter), emit structured events, never
  analyze.
- **Built so far:** Market Watcher only, as a stub (hardcoded feed). It's a
  standalone REST script (no LLM, no adapter) — see §5.
- Real watcher = connector + change-detection (only fire on new) + relevance filter.
  Swapping the stub's feed for that changes NOTHING downstream. (Deferred — hardcoded
  feeds are fine for now.)

### Tier 3 — Specialists (analysts)
- Convened on demand by the orchestrator. Framework: **CrewAI**. Model: gpt-4o-mini
  (cheaper) for the persona-style ones.
- **Built & working (all four):** Competitive Analysis (persona), Finance, Retention,
  and Hiring (the latter three grounded/pre-fetched), all on the shared
  `agents/specialists/_base.py` (forced recipient + prompt fix, §7). Fan-out across
  the four verified live.

### Humans & infrastructure
- Founder (and function heads) are **participants, not agents**. The founder is the
  escalation target / approver.
- Memory layer (`evergreen_memory.jsonl`) and the simulated clock are
  **infrastructure, not agents**.

### Hard requirement (hackathon)
≥3 agents collaborating *through Band during the workflow*. Currently satisfied:
Orchestrator + Competitive Analysis + Market Watcher.

---

## 3. Current state (what works, what doesn't)

**Working, verified end-to-end in a Band room (2026-06-18 live run, room
`ea9b566e…`, logs + memory captured):**
- Orchestrator connects, judges materiality correctly — a minor FormFly UI-refresh
  event was recorded "not material" with `actors:['orchestrator']` only (no convene,
  no founder ping).
- Full **fan-out** cascade on a material competitor price cut: watcher posts event →
  orchestrator convenes BOTH Competitive Analysis AND Finance → each returns a
  structured assessment **addressed to the orchestrator** → orchestrator stands each
  one down (removes it) as it replies → after both report, orchestrator records ONE
  synthesized decision and escalates to the founder with exactly ONE brief.
- **Dynamic re-convening** verified: after a first cascade removed both specialists,
  a second material event re-added them from scratch.
- Event-driven over SIM TIME: the Market Watcher is driven by `clock/sim_clock.py` —
  it stays quiet for "days" and fires scheduled events on their sim-day (no hand-posting).
- Founder gets exactly one message per material event (the final brief) — noise,
  intermediate steps, and "still working" status no longer ping the founder.
- Memory READ path: a founder "why did we decide X?" is answered from
  `evergreen_memory.jsonl` via `recall_decisions`, with no specialist convened (§Step 1).
- Persistence across restart: a full kill/restart preserved memory + resumed the
  sim-day from `clock_state.json` with NO event replay (§Step 2). Caveat: the
  LangGraph `InMemorySaver` (in-flight graph state) does not persist.

**Finance specialist — FIXED (was BLOCKED, see §8):**
- Now delivers its grounded answer to the orchestrator reliably. Two changes did it:
  (a) the four data tools were replaced by a plain-Python **pre-fetch** of the same
  figures injected into context, so the only action left is `band_send_message`;
  (b) both specialists now run on a shared base (`agents/specialists/_base.py`) that
  **forces the reply recipient to the orchestrator** in code and **suppresses Band's
  conflicting prompt instructions**. See §7, §8.

**Known operational mess to clean up:**
- Multiple test rooms have accumulated (the orchestrator auto-subscribes to all
  existing rooms). Keep ONE room; delete the stale ones. Reconnections during a test
  replay messages and make logs non-reproducible — don't trust a test taken across a
  reconnect.

---

## 4. Tech stack & provider config

- **Band** (a.k.a. thenvoi) — the coordination spine. Remove Band and the system
  collapses (that's the design goal).
- **AI/ML API** (aimlapi.com) — powers all reasoning agents. Pay-as-you-go,
  **$20 minimum** top-up (not $10), non-refundable, OpenAI-compatible. Also a partner
  prize target ("Best Use of AI/ML API") — so use it visibly.
- **Cross-framework** criterion met via **LangGraph** (orchestrator) + **CrewAI**
  (specialists).
- **Featherless AI** (other partner prize) — deferred, not used.

### Provider journey (so nobody re-treads it)
- **Groq: OUT.** Its strict JSON-Schema validator rejects Band's built-in
  `band_send_event` tool schema (`'required' present but 'properties' is missing`).
  Every Band agent gets that tool, so Groq can't run any Band agent.
- **Gemini free tier: OUT.** Worked for tool calling but hit a 20-requests/day cap.
- **AI/ML API: IN.** $20 added. Everything env-driven so swaps need no code change.

### Model routing
- Orchestrator: `gpt-4o` (needs strong tool-calling for the convening loop).
- Specialists: `aiml/gpt-4o-mini` (cheaper). NOTE: the model is NOT the cause of the
  Finance delivery bug — see §8.

### `.env` template
```
# Orchestrator (LangGraph + ChatOpenAI → AI/ML API, OpenAI-compatible)
LLM_BASE_URL=https://api.aimlapi.com/v1
LLM_API_KEY=<aiml key>
ORCHESTRATOR_MODEL=gpt-4o

# Specialists (CrewAI → LiteLLM → AI/ML API, provider route "aiml/")
AIML_API_KEY=<aiml key>
SPECIALIST_MODEL=aiml/gpt-4o-mini
# AIML_API_BASE=https://api.aimlapi.com/v2   # only if a CrewAI call 400s on the endpoint

# Band platform
THENVOI_WS_URL=wss://app.band.ai/api/v1/socket/websocket
THENVOI_REST_URL=https://app.band.ai

# Market Watcher (REST, send-only)
EVERGREEN_ROOM_ID=<room uuid>
MARKET_WATCHER_API_KEY=<watcher agent key>
ORCHESTRATOR_NAME=Orchestrator

# Simulated clock (clock/sim_clock.py — drives the watcher; read by record_decision)
SIM_SECONDS_PER_DAY=5
SIM_START_DAY=1
# SIM_CLOCK_STATE_FILE=clock/clock_state.json   # default; persisted sim-day
```
LiteLLM's AI/ML provider reads `AIML_API_KEY`; model string is `aiml/<model>`
(e.g. `aiml/gpt-4o-mini`, `aiml/gpt-4o`). Their chat examples use api_base
`https://api.aimlapi.com/v2`; the orchestrator's direct OpenAI-compatible path uses
`/v1`.

---

## 5. Band SDK / platform facts (the hard-won knowledge)

Distribution: **`band-sdk`** (currently **1.0.0**). Import is `thenvoi` OR `band`
(docs are inconsistent; code uses `try: import thenvoi / except ImportError: import band`).
Extras: `band-sdk[langgraph]`, `band-sdk[crewai]`. Requires Python 3.10+, uv.

### Agent lifecycle
- `Agent.create(adapter, agent_id, api_key, ws_url=..., rest_url=...)`, then
  `await agent.run()` (connects WebSocket, runs forever).
- URLs default to production: ws `wss://app.band.ai/api/v1/socket/websocket`,
  rest `https://app.band.ai`. Env: `THENVOI_*` or `BAND_*`.
- Creds per agent in `agent_config.yaml`; `load_agent_config("name")` →
  `(agent_id, api_key)`.
- Agents are **REACTIVE**: they only process messages that **@mention** them.
- `auto_subscribe_existing_rooms=True` by default → an agent subscribes to ALL rooms
  it's in. This is why stale test rooms keep getting polled. Keep one room.

### Platform tools (auto-injected; CrewAI names)
`band_send_message(content, mentions)`, `band_send_event(content, message_type,
metadata)`, `band_add_participant(name)`, `band_remove_participant(name)`,
`band_get_participants()`, `band_lookup_peers()`, `band_create_chatroom()`.
- **Plain LLM/agent output is NOT delivered. The agent MUST call `band_send_message`
  to reply.** (This is central to the Finance bug — §8.)
- Sibling agents under the same account **auto-discover via `band_lookup_peers`** — no
  contact handshake needed. So a convened specialist just needs to be running under
  the same account; the orchestrator finds it.

### Adapters
- `LangGraphAdapter(llm=ChatOpenAI(...), checkpointer=InMemorySaver(),
  additional_tools=[<LangChain @tool>], custom_section=...)`.
- `CrewAIAdapter(model, role, goal, backstory, custom_section,
  additional_tools=[(PydanticModel, handler)], enable_execution_reporting=...,
  allow_delegation=False)`.
- **Custom tools (CrewAI):** a tuple `(PydanticModel, handler)`. The model **class
  name becomes the tool name**, the model **docstring becomes the tool description**,
  and the **handler takes the validated model and returns a string** (sync or async).
  No-arg tools (empty model + docstring) are fine on AI/ML's OpenAI-compatible endpoint.

### Band auto-injects platform instructions into each CrewAI agent's backstory
(visible by dumping the agent at startup). These have bitten us:
- **"## Activation: respond to the mentioning participant."**
- **"## Relaying: always deliver the answer to the original requester."** ← caused
  Competitive Analysis to address the **founder** (who posted the original event)
  instead of the **orchestrator** (who convened it). Override explicitly in each
  specialist's `custom_section` (see §7).
- **"Do NOT remove added agents automatically; they stay silent unless mentioned."**
  ← fights our stand-down design. The orchestrator prompt must explicitly override it
  to remove specialists after they report.

### Agent REST API (used by the watcher; send-only integrations)
- Base `…/api/v1/agent`. Auth header **`X-API-Key: <agent key>`** (NOT Bearer).
- `POST /agent/chats/{chat_id}/messages` with body:
  ```json
  { "message": { "content": "@Orchestrator …", "mentions": [ { "id": "<uuid>" } ] } }
  ```
  The `@Name` in `content` is for display; the `id` in `mentions` does the routing;
  at least one mention is required.
- `GET /agent/chats/{chat_id}/participants` → list (to resolve the orchestrator's id).
- A REST-only integration can **send but not receive** (no WebSocket). Perfect for a
  watcher, which only ever posts. The posting agent must be a participant in the room.

### Deprecation (harmless)
`enable_execution_reporting=True` / `enable_memory_tools=True` are deprecated →
`features=AdapterFeatures(emit={Emit.EXECUTION}, capabilities={Capability.MEMORY})`.
The old flags still work; the warning changes nothing. Cosmetic cleanup only.

### ⚠️ CRITICAL adapter finding (band-sdk 1.0.0, `band/adapters/crewai.py`)
After a CrewAI agent runs, the adapter does ONLY this with the result:
```python
result = await self._crewai_agent.kickoff_async(messages)
if result and result.raw:
    self._message_history[room_id].append({"role": "assistant", "content": result.raw})
logger.info("Room %s: CrewAI agent completed (output_length=%s)", room_id, ...)
```
**There is NO code that delivers `result.raw` (the CrewAI "final answer") to the
room.** The only path to the room is the `band_send_message` *tool* being called
*during* the run. The adapter's except block even documents the intent: an empty
final answer after a reply is "benign noise — the user already got their response."
So the final answer is throwaway by design; the reply MUST go through
`band_send_message`. This is the root of the Finance bug (§8).

### ⚠️ Recipient routing is model-chosen — and Band biases it the wrong way
`band_send_message(content, mentions)` routes purely by the `mentions` the LLM
produces; `send_message` accepts handle strings (`@<user>/<agent>`) or `{"id":…}`
dicts. Band injects a fixed instruction block into EVERY agent's system prompt
(`band/runtime/prompts.py :: BASE_INSTRUCTIONS`), including:
- **`## Relaying` — "always deliver the answer to the original requester."** This
  made Finance (and intermittently CA) answer the **founder** — the human who first
  raised the event — even when the **orchestrator** convened it. Confirmed in a live
  log: orchestrator @Finance → Finance @founder.
- `## Activation` ("respond to the mentioning participant") and `## Delegation`
  ("do NOT remove added agents") — the latter fights the orchestrator's stand-down.

Out-prompting these is model-dependent and unreliable (it lost in practice). The
robust fix lives in `agents/specialists/_base.py` and does TWO things, both
process-local and gracefully degrading:
1. **Suppress the conflicting block.** `render_system_prompt(...)` is called by the
   adapter with `include_base_instructions=True` and exposes no off-switch. We patch
   that module-global (`sys.modules[CrewAIAdapter.__module__].render_system_prompt`)
   to force `include_base_instructions=False`, then supply a minimal, conflict-free
   platform note (how to use `band_send_message`; treat messages as input). The
   Relaying/Activation/Delegation lines are simply gone.
2. **Force the recipient deterministically.** `SpecialistAdapter` overrides
   `on_message(msg, tools, *args, **kwargs)` to wrap `tools` in a proxy whose
   `send_message` rewrites `mentions` to the orchestrator (resolved once from
   `get_participants()`, matched by name/handle, then cached). The `EmitExecution`
   reporter has no `execute_send_message`, so every send falls through to
   `tools.send_message` → the proxy catches 100% of them. If the orchestrator can't
   be resolved it falls back to the model's own mention rather than crashing.

### Agent REST API — two more facts
- **Add a participant:** `POST …/chats/{id}/participants` with body
  `{"participant": {"participant_id": "<uuid>", "role": "member"}}` (the
  `participant` wrapper is required; a bare `participant_id` 422s). `DELETE
  …/participants/{participant_id}` removes one. The orchestrator does both during
  convene/stand-down.
- **`GET …/chats/{id}/messages` is a WORK QUEUE, not a transcript.** It returns only
  pending/processing messages for that agent (`?status=processing`, `/messages/next`)
  and reads empty once everything is processed. To verify a run, read the agent logs
  and the memory file, or the Band UI — not this endpoint. Also: listing a room you
  are not a member of returns **404** (used this to detect agents missing from a new
  room).

### Operational: an agent only receives mentions sent WHILE it is connected
There is no offline queue for @mentions. If the orchestrator @mentions a specialist
whose process started a moment later, that mention is simply missed (this looked
like "CA stopped working" in one test — it had started ~1 min after being convened).
Start all specialist processes and let them connect BEFORE driving events. Specialist
modules now call `logging.basicConfig` (via `_base`) so a silent/dead agent is
visible in its log instead of failing invisibly.

---

## 6. The orchestrator prompt (current, consolidated)

`CHIEF_OF_STAFF_PROMPT` in `agents/orchestrator.py`. This has been through many
iterations; this is the current full text:

```
You are the Chief of Staff for a startup. This room owns ONE outcome: keep the
company healthy and growing. You stay quiet and act only when something material
happens. You are a COORDINATOR, not a soloist — your value is convening the right
specialist. You must NEVER analyze a domain question yourself, even if you think
you know the answer.

THE FOUNDER RULE (most important): You @mention the founder AT MOST ONCE per
event, and only when a strategic, costly, or irreversible decision needs their
approval — a single final brief with your recommendation. NEVER @mention the
founder for noise, to acknowledge that you saw an event, to say what you are
about to do, or for low-risk actions you can take yourself.

ACT ON EVERY EVENT. Every signal a watcher sends you is a genuine new
development — watchers have already filtered out anything stale or routine.
NEVER skip an event or stay silent because it resembles something earlier in
this room's history; that de-duplication is the watcher's job, not yours. On
every event you MUST end your turn with a tool call: record_decision if you
judge it not material, or the convene path if it is material. Ending your turn
with no tool call — silent inaction — is never correct.

When a watcher @mentions you with an event, run this loop:

1. JUDGE MATERIALITY — silently. Do NOT message the founder about this.
   - If the event is noise or routine: call record_decision to log a one-line
     "not material" note, then STOP. Convene no one; do not message the founder.
   - If it is material: go straight to step 2 without announcing it to anyone.

2. CONVENE THE RIGHT SPECIALIST(S). Get specialist assessments first — never
   analyze it yourself, and do not escalate yet.
   - Competitive Analysis for competitor positioning/product/feature moves and
     threat; Finance for revenue, pricing, margin, churn-cost, burn, or runway.
   - MANY EVENTS NEED BOTH. A competitor price change where we are weighing whether
     to match is a competitive threat AND a pricing/financial decision → convene
     BOTH. (This fan-out is the §2 design, finally enforced in the prompt.)
   - Add each chosen specialist if not in the room; if already in, just @mention.
   @mention each convened specialist with a specific question, then end your turn
   and wait. Do not message the founder at this stage.

3. WHEN A SPECIALIST REPLIES, do these in order:
   a. STAND DOWN that specialist (remove-participant). Do it for EACH as it
      replies; REQUIRED even if other guidance says keep agents in the room.
   b. IF YOU CONVENED MORE THAN ONE and others have not replied, end your turn and
      WAIT. Do NOT decide or brief the founder until every convened specialist has
      reported.
   c. DECIDE (when in doubt, brief the founder — escalation is the default for
      anything touching strategy, money, or direction):
      - Strategic / costly / irreversible (incl. ANY pricing change, competitive
        response, material revenue/MRR/margin/runway impact, hiring, partnerships;
        and a decision NOT to act is still strategic) → @mention the founder ONCE
        with a SHORT brief, then record_decision. This is the ONLY founder message.
      - Genuinely small, reversible, no strategic/financial weight → record_decision
        and stay quiet.

COMMUNICATION DISCIPLINE:
- Send a message ONLY when it carries new substance: a question to a specialist,
  or the single final brief to the founder.
- NEVER send progress or status updates ("analyzing now", "I will convene a
  specialist", "done"). Go straight to the action instead.
- WHILE WAITING for a specialist you convened, stay silent. If the same event
  arrives again, or someone asks for a status ("any update?", "why didn't you…?"),
  do NOT status-update and do NOT message the founder — wait, or convene a clearly
  needed specialist that was missed. Never narrate. (Fixes the "I've already
  requested an analysis…" founder spam seen when re-pinged mid-wait.)
- Write every message as plain, short sentences. Do NOT paste a specialist's
  message verbatim, do NOT use bullet blocks, and never write literal "\n"
  characters — synthesize into 1-3 sentences in your own words.
- Keep every message short and human-readable — the transcript is the audit trail.

Rely only on what watchers and specialists report; never invent facts. If asked
why a past decision was made, answer from what was recorded.
```

Each clause exists because of a specific failure — see §9.

---

## 7. The specialists

### Shared base (`agents/specialists/_base.py`) — the robustness layer
BOTH specialists run through `run_specialist(...)` here, so they can't drift apart.
It owns the two guarantees detailed in §5: (1) suppress Band's conflicting prompt
block (`include_base_instructions=False` + a minimal platform note); (2) force every
`band_send_message` to the orchestrator via a tools proxy in `SpecialistAdapter`.
It also sets `logging.basicConfig` (so specialists aren't silent) and reads
`SPECIALIST_MODEL` (default `aiml/gpt-4o-mini`). A specialist module is now just:
backstory + analysis instructions + `run_specialist(...)`.

Because the recipient is enforced in code, the per-specialist prompts no longer
contain the brittle "always @mention the Orchestrator, never the founder, disregard
the 'original requester' guidance" paragraph — that whole class of instruction is
obsolete.

### Competitive Analysis (`agents/specialists/competitive_analysis.py`) — WORKS
Persona specialist, **no data tools**: reasons from the signal text, so its figures
(e.g. "~15% exposure") are estimates, not data-grounded — the reason Finance is
pre-fed real numbers. Instructions ask for the four-part decision-ready assessment
(what/who, threat level, our exposure, one recommended response).

### Finance (`agents/specialists/finance.py`) — WORKS (was BLOCKED, see §8)
CrewAI, **no choose-able tools**. The four figures are computed in plain Python at
startup (`revenue_snapshot`, `revenue_by_plan`, `unit_economics`, `burn_and_runway`)
and folded into the prompt as a `COMPANY FINANCIAL DATA` block via
`build_data_snapshot()`; ratios derived in code so they can't drift. Data still comes
ONLY from `core/company_data.py`. Verified live: it sent the orchestrator a grounded
brief ("MRR drop … ~$15,295 … lose ~$6,555/mo", Starter = 45% of MRR). Trade-off vs.
the old tooled version: no per-tool audit events and no dynamic tool selection — for
four cheap internal slices, worth it for guaranteed delivery.

### Retention (`agents/specialists/retention.py`) — WORKS
Same grounded pattern as Finance. `build_retention_snapshot()` pre-fetches the
`RETENTION` slice (logo/revenue churn, NRR/GRR, per-plan churn, trailing trend,
at-risk accounts; Starter is the at-risk cohort, ~$983/mo at risk derived from
PLANS). Four-part output: what's happening / severity / who's exposed / one play.
Verified live (churn-spike → grounded "1,150 Starter / $21,850 MRR at risk" reply).

### Hiring (`agents/specialists/hiring.py`) — WORKS
Same pattern. `build_hiring_snapshot()` pre-fetches the `HIRING` slice (headcount
plan vs actual, attrition, time-to-fill, open reqs with pipeline). Four-part output.
Verified live (departure → grounded "role open 52d, pipeline 40→1, Eng gap" reply).

> Fan-out across the 4-specialist pool verified live (churn → Retention+Finance;
> departure → Hiring+Finance); each stood down, one founder brief per event. Nuance:
> Finance's slice is revenue-only, so on a pure departure its reply is tangential —
> candidate refinement: Hiring-only routing for departures, or a payroll slice.

### Shared mock data (`core/company_data.py`)
The "company profile" all specialists read. A fictional SaaS form-builder, internally
consistent: `PLANS` (Free/Starter/Pro/Business with customers + MRR),
`MRR_TRAILING_6MO`, `UNIT_ECONOMICS` (CAC 180, LTV 720, GM 82%, payback 7mo),
`CASH` (net burn 62k/mo, cash 740k → ~12mo runway). Swap these values (or replace
with live API calls) without touching any agent.

---

## 8. RESOLVED — Finance now delivers (was: never delivers its answer)

**Original symptom:** Finance was convened, pulled the right data, produced an
analysis, but no message reached the orchestrator (`CrewAI agent completed` then
silence; no `band_send_message`). A follow-on symptom appeared once delivery worked:
Finance addressed the **founder** instead of the orchestrator.

**Two root causes (both confirmed from SDK source — §5):**
1. *No delivery.* The CrewAI adapter discards the agent's final answer; the ONLY
   path to the room is the `band_send_message` tool. Finance's data tools gave the
   model a second exit (do tool work → emit a final answer the adapter throws away).
   Not the model, not fixable by prompting harder.
2. *Wrong recipient.* Even after delivery worked, Band's injected `## Relaying`
   instruction ("deliver to the original requester") pulled the reply to the founder.

**The fix that shipped (both in code, not prompts):**
1. *Guaranteed delivery* — removed the choose-able data tools; the four figures are
   pre-fetched in plain Python and injected into context, so the only remaining
   action is reason + `band_send_message`. Grounding preserved (numbers are in
   context, nothing else to cite). Exactly as reliable as Competitive Analysis.
2. *Deterministic recipient* — `agents/specialists/_base.py` suppresses the conflicting
   Relaying/Activation/Delegation block and forces every send to the orchestrator via
   a tools proxy (resolved from the participant list, cached). See §5 for mechanics.

**Verified live (2026-06-18):** orchestrator convened Finance → Finance replied to
the orchestrator with a grounded brief → orchestrator stood it down and recorded a
synthesized decision. The earlier "Finance → founder" misroute no longer occurs even
when the model tries it (unit-tested: a model mention of the founder is overwritten
to the orchestrator).

**Residual caveat:** the recipient proxy and the prompt-block suppression touch SDK
internals (a module-global patch + an `on_message` wrapper). They degrade gracefully
(fall back to model-chosen mention; only the base-instruction toggle is at risk on a
major SDK bump). Re-verify both after any `band-sdk` upgrade.

---

## 9. Gotchas & learnings (running list)

1. **Groq is incompatible** with Band (strict tool-schema validator rejects Band's
   native `band_send_event` schema).
2. **Gemini free tier** hit a 20 req/day cap; abandoned for AI/ML API.
3. **AI/ML API minimum top-up is $20**, not $10. Pay-as-you-go, non-refundable.
4. **Plain agent output is never delivered** — must call `band_send_message`.
5. **CrewAI adapter discards the final answer** — tooled CrewAI agents need a
   guaranteed `band_send_message` call (see §8).
6. **Band auto-injects backstory instructions** (Activation/Delegation/Relaying +
   "don't remove agents"). The Relaying one made specialists address the founder;
   the don't-remove one fights stand-down. *Prompt overrides proved unreliable* —
   specialists now **suppress** the whole block (`include_base_instructions=False`)
   and the recipient is forced in code (§5, §8). The orchestrator (LangGraph) still
   overrides the don't-remove line in its prompt.
7. **Orchestrator silent no-ops** were caused by (a) it de-duplicating against the
   room's chat history ("already handled, do nothing") and (b) a prompt escape hatch
   allowing total inaction. Fixed with the ACT ON EVERY EVENT block: dedup is the
   watcher's job; every event must end in a tool call. This also removed the need for
   a "fresh room" each test.
8. **Founder spam** (3 messages: noise verdict + "I'll convene" + the real brief) was
   cut to ONE via THE FOUNDER RULE. "Act on every event" ≠ "message on every event":
   noise → silent `record_decision`; only material → one founder brief.
9. **Literal `\n` in messages** — gpt-4o was relaying a specialist's multi-line text
   verbatim/escaped. Fixed by instructing plain short sentences, synthesize don't
   relay, never emit literal "\n".
10. **Room churn** — every test spun up a new room; the orchestrator auto-subscribes
    to all of them and reconnections replay messages. Use ONE room; delete stale ones;
    don't trust a test taken across a reconnect.
11. **No-arg custom tools** are fine on AI/ML's OpenAI-compatible endpoint (the empty-
    schema problem was Groq-specific). Add a dummy field only if one ever 400s.
12. **Specialist recipient must be forced in code, not prompted.** "Always @mention
    the Orchestrator" lost to Band's Relaying instruction in practice. The tools-proxy
    in `_base.py` overwrites the mention regardless of what the model picks (§5/§8).
13. **An agent only gets @mentions sent while it's connected** — no offline queue.
    Start specialist processes and let them connect BEFORE convening, or a too-fast
    mention is silently missed (looked like "CA stopped working"). `_base` now sets
    `logging.basicConfig` so a dead/slow specialist is visible instead of silent.
14. **`GET .../messages` is a work queue, not a transcript** — empty once processed.
    Verify runs via agent logs + `evergreen_memory.jsonl` + the Band UI (§5).
15. **Driving a self-test without the human:** add the Market Watcher to the room via
    `POST .../participants` body `{"participant":{"participant_id":…,"role":"member"}}`
    (the `participant` wrapper is required), then run `market_watcher.py` against that
    room. Its feed posts a minor event (not-material) then the material one.

---

## 10. File structure & how to run

```
evergreen/
  agents/
    orchestrator.py                     # LangGraph, gpt-4o, record_decision tool
    specialists/
      _base.py                          # shared base: forced recipient + prompt fix (§5/§7)
      competitive_analysis.py           # CrewAI persona on _base (works)
      finance.py                        # CrewAI pre-fetched data on _base (works — §8)
    watchers/
      market_watcher.py                 # REST, send-only; clock-driven SCHEDULE (§Step 2)
  core/
    company_data.py                     # shared mock "company profile"
    (llm.py / memory.py / events.py)    # scaffolding, mostly empty
  clock/
    sim_clock.py                        # SimClock: real secs -> sim-days, persisted
    clock_state.json                    # persisted sim-day (gitignored, runtime state)
  .env                                  # see §4
  agent_config.yaml                     # per-agent {agent_id, api_key}
  evergreen_memory.jsonl                # memory store (written by record_decision)
  Evergreen_PRD.md                      # original spec / source of truth
```

`agent_config.yaml` shape:
```yaml
orchestrator:
  agent_id: "<uuid>"
  api_key: "<key>"
competitive_analysis:
  agent_id: "<uuid>"
  api_key: "<key>"
finance:
  agent_id: "<uuid>"
  api_key: "<key>"
```
(The Market Watcher authenticates via REST using `MARKET_WATCHER_API_KEY` from `.env`;
it does not load through the SDK.)

**Run each in its own terminal, from the project root:**
```
uv run python -m agents.orchestrator
uv run python -m agents.specialists.competitive_analysis
uv run python -m agents.specialists.finance
uv run python -m agents.watchers.market_watcher   # now -m (imports clock.sim_clock)
```
Clock config via env (§4): `SIM_SECONDS_PER_DAY` (default 5), `SIM_START_DAY`
(default 1). Use a slower clock for a demo (e.g. 15-20s/day) so a material event
and its decision land on the same sim-day — at a fast clock the multi-LLM cascade
spans several sim-days, so a decision's `sim_day` (when finalized) can trail the
event's day. Delete `clock/clock_state.json` to reset the sim-day to the start.
Specialists are convened on demand — they do NOT need to be pre-added to the room;
just keep their processes running (siblings auto-discover via lookup_peers) and let
them CONNECT before any event is posted (gotcha #13). The Orchestrator and the Market
Watcher DO need to be participants in the room (orchestrator to receive events,
watcher to post). Each Band agent must exist on the platform under the same account,
with a clear **description** (the orchestrator routes by peer description).

**Manual test event (paste in the room, @mentioning the orchestrator):**
- Competitive route: `@Orchestrator [event from market-watcher] Competitor Typeform
  just announced a 30% price cut on their Starter plan plus a new AI form-building
  feature.`
- Finance route: `@Orchestrator [event from market-watcher] Typeform cut their Starter
  plan price 30%. We're weighing whether to match it.`

---

## 11. Roadmap / next steps

1. ~~**Fix Finance delivery** (§8)~~ — DONE (2026-06-18): pre-fetch data + drop tools,
   plus the shared `_base.py` forced-recipient/prompt-suppression layer. Verified live.
2. ~~**Retention & Hiring specialists**~~ — DONE (2026-06-18): both built grounded on
   `_base.py` with `core/company_data.py` slices + routing/fan-out (§7). Verified live
   (churn → Retention+Finance; departure → Hiring+Finance; each stood down, one brief).
3. ~~**Memory recall tool**~~ — DONE (2026-06-18): `recall_decisions` added to the
   orchestrator; founder "why did we decide X?" answered from `evergreen_memory.jsonl`
   with no specialist convened. Verified live (positive + graceful no-record).
4. ~~**Simulated clock / event injector**~~ — DONE (2026-06-18): `clock/sim_clock.py`
   (`SimClock`, persisted sim-day); the Market Watcher is clock-driven (SCHEDULE by
   sim-day, quiet days, fire-once). Verified live.
5. ~~**Persistence-across-restart demo**~~ — DONE (2026-06-18): full restart preserved
   `evergreen_memory.jsonl` + resumed the sim-day from `clock_state.json` with NO
   event replay. Caveat: LangGraph `InMemorySaver` (in-flight graph state) does NOT
   persist — durable record does; SQLite checkpointer deferred.
6. **Real watchers** (later) — swap hardcoded feeds for connector + change-detection
   + relevance filter. Metrics watcher is the cleanest first real one (deterministic,
   no fuzzy relevance): query Stripe/PostHog/DB on a timer, z-score vs a stored
   baseline, fire on threshold.
7. **Partner prizes** — AI/ML API is in use (claim it). Featherless optional.

---

## 12. Band docs quick-reference (verified pages)

- Overview / welcome: https://docs.band.ai/welcome
- SDK setup: https://docs.band.ai/integrations/sdks/tutorials/setup
- SDK reference (classes/adapters/tools): https://docs.band.ai/integrations/sdks/reference
- CrewAI adapter tutorial (custom tools): https://docs.band.ai/integrations/sdks/tutorials/crewai
- LangGraph adapter tutorial: https://docs.band.ai/integrations/sdks/tutorials/langgraph
- Agent REST API intro (auth, perspectives): https://docs.band.ai/api/introduction
- Send a message as the agent: https://docs.band.ai/api/agent-api/agent-api-messages/create-agent-chat-message
- LiteLLM AI/ML provider: https://docs.litellm.ai/docs/providers/aiml
- Append `/llms.txt` to any docs URL for a page index, or `.md` for markdown.
```
```