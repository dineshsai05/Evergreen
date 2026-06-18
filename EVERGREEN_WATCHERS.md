# Evergreen — Real Watchers & the Detection Layer (Step 4+) — Design

> **Status: design only. Nothing here is built yet.** This is the thinking and the
> feature plan for turning the detection tier from stubs into real, production-grade
> watchers — and the features that real detection unlocks. It starts from Step 4 of
> `EVERGREEN_NEXT.md`. Read `EVERGREEN_CONTEXT.md` for the current architecture.
>
> Deliberately NOT a hackathon task — `EVERGREEN_NEXT.md` defers real watchers. This
> doc exists so the design is ready when we choose to build it, and so we agree on
> scope and principles first.

---

## 0. Why this matters

Today, every tier below detection is **real**: the orchestrator genuinely triages, it
genuinely convenes specialists through Band, specialists genuinely reason over grounded
data, and decisions are genuinely recorded and recalled. The one remaining mock is the
**Market Watcher's hardcoded feed**. So the watcher layer is the last boundary between
"impressive demo" and "product you'd actually run."

The good news, and the whole point of the funnel design: **the watcher → orchestrator
interface is just a posted event.** Swapping a hardcoded feed for a live source changes
*nothing* downstream. That means real watchers are an additive, low-blast-radius upgrade
— if we get the event contract right.

---

## 1. What a watcher IS — and the one line we must never cross

A watcher is a **sensor**. Its entire job: *"did something happen in our world?"* — broad,
continuous, cheap, shallow. It surfaces a raw signal and stops.

**The crucial design line (the spine of this whole doc):**

> A watcher may **FILTER** ("is this signal in our world at all?"). A watcher must never
> **JUDGE** ("is this important?", "how bad?", "what should we do?"). Materiality is the
> orchestrator's job; meaning is the specialist's job.

This line is subtle because relevance filtering can *look* like judgment. The test:

- ✅ Allowed (filtering / gating): "Is this news about a competitor or our category?"
  "Did this metric move beyond its normal range?" "Is this ticket about us?"
- ❌ Forbidden (judgment / analysis): "This price cut is a serious threat." "This churn
  spike is bad and we should respond." "Recommend we match the price."

A watcher may attach a **raw magnitude** ("MRR −15% WoW", "42 new tickets vs. ~12 typical")
because that's an observation, not a verdict. It must not attach severity, threat level,
or a recommendation. If a watcher starts ranking importance, it has become a (bad,
context-starved) orchestrator.

Why so strict? Three reasons: (1) it keeps each tier cheap and replaceable; (2) the
orchestrator triages with the *full* company picture a single watcher never has; (3) it's
the property that makes the funnel auditable — every escalation traces to a raw signal.

---

## 2. Anatomy of a real watcher (the pipeline every watcher shares)

A real watcher is a small, repeating pipeline:

```
  ┌─────────┐   ┌───────────┐   ┌──────────────────┐   ┌──────────────┐   ┌────────────┐
  │connector│──▶│ normalize │──▶│ change-detection │──▶│  relevance   │──▶│   emit     │
  │ (pull/  │   │ (to a     │   │ + dedup          │   │  filter      │   │ structured │
  │  push)  │   │  raw obs) │   │ (fire only NEW)  │   │ (in our      │   │  event ──▶ │
  └─────────┘   └───────────┘   └────────┬─────────┘   │  world?)     │   │ Orchestr.  │
                                          │              └──────────────┘   └────────────┘
                                          ▼
                                  ┌────────────────┐
                                  │ persisted state│  baselines, cursors, seen-set —
                                  │ (survives      │  so restarts don't replay and
                                  │  restart)      │  steady-state doesn't re-fire
                                  └────────────────┘
```

Stage by stage:

1. **Connector** — pull from a source (REST/GraphQL/DB/RSS) on a timer, or receive a push
   (webhook). The only tier-specific code most of the time.
2. **Normalize** — map the source's shape into a uniform *raw observation* (value, text,
   id, timestamp). Decouples detection logic from any one vendor.
3. **Change-detection + dedup** — the discipline that makes a watcher trustworthy: fire
   *only on genuinely new or changed* signals. Three mechanisms by data type:
   - **Cursor / seen-set** (streams of items: news, tickets, reviews) — track the
     last-seen id/timestamp or a hash set; emit only unseen items.
   - **Value baseline** (metrics) — compare the current value to a stored baseline; emit
     only on a breach.
   - **Content diff** (pages: a competitor's pricing/changelog page) — hash/diff the
     content; emit only on change.
   This is the same fire-once discipline as the sim-clock: state persists, so a restart
   resumes instead of replaying. **It also keeps the orchestrator's "trust every event"
   contract honest** — the orchestrator is told dedup is the watcher's job (gotcha #7).
4. **Relevance filter** — the gate from §1. Deterministic for metrics (threshold/z-score
   IS the relevance test). Fuzzy for text (an embedding/LLM gate against the company
   profile + watchlist). Tunable for precision vs. recall.
5. **Emit** — post a *structured* event to the orchestrator (the room). Same interface as
   today's stub, but richer metadata (see §3).
6. **Persisted state** — baselines, cursors, seen-sets, content hashes — written to disk
   (like `clock_state.json`), so the watcher is stateful across restarts.

A real watcher is **connector + a detect-rule + a relevance gate** on top of this shared
pipeline — which is exactly why §7 proposes a watcher framework so new watchers are a few
dozen lines, the way `_base.py` made new specialists trivial.

---

## 3. The event contract (formalize it now)

Today the stub posts a plain string: `@Orchestrator [event from market-watcher] <text>`.
For real watchers we want a **structured event** so the orchestrator can triage
consistently and memory can record provenance. The event should carry observation +
provenance, and **deliberately omit any verdict**:

| Field | Example | Notes |
|-------|---------|-------|
| `source` | `"stripe"`, `"g2"`, `"competitor:typeform"` | where it came from |
| `watcher` | `"metrics"`, `"market"`, `"voice"` | which family detected it |
| `signal_type` | `"mrr_drop"`, `"competitor_pricing_change"`, `"ticket_spike"` | a stable enum the orchestrator can route on |
| `observation` | `"MRR fell 15% week-over-week"` | human-readable, raw |
| `magnitude` | `{"metric":"mrr","prev":48218,"now":41000,"pct":-15.0,"z":-3.1}` | raw numbers, **not** a judgment |
| `dedup_key` | `"mrr_drop:2026-W25"` | so the same condition doesn't re-fire |
| `evidence` | `["https://typeform.com/pricing", "ticket #4821"]` | links/ids the specialist can cite |
| `confidence` | `0.0–1.0` | relevance/extraction confidence (for fuzzy sources) |
| `observed_at` / `sim_day` | ISO ts + sim-day | ties detection to the clock/memory timeline |

How it reaches the orchestrator: keep posting into the **room** (the transcript is the
audit trail and the UX — a pillar), but put the human-readable line in the message content
and the structured fields in message metadata (or a compact JSON tail). The orchestrator
triages from this; `record_decision` can capture `source`/`evidence` for provenance.

**Recommendation:** define this contract as a small typed object (e.g. `core/events.py`,
which already exists as an empty scaffold) and have *both* the stub and real watchers emit
it. Migrating the stub to the contract first is a safe, downstream-visible-but-compatible
step we could even do during the hackathon if desired.

---

## 4. Detection methods — deterministic vs. fuzzy

The watcher families split cleanly by how they decide "is this real and ours?":

### Deterministic (numbers) — preferred, build first
- **Threshold:** value crosses an absolute line (runway < 6 months).
- **% change vs. prior period:** WoW / MoM deltas.
- **Z-score vs. rolling baseline:** `z = (value − mean) / stddev` over a trailing window;
  fire when `|z| > k`. Robust, self-calibrating, no hardcoded thresholds.
- **Streaks:** "flat/declining for N periods" (catches slow bleeds a single delta misses).

> **Seasonality is the deterministic gotcha.** Naive z-scores false-fire on weekly cycles
> (weekend DAU dips), paydays, holidays. Mitigations: compare same-day-of-week, use a long
> enough window, or hold a per-weekday baseline. Worth designing in from day one — a
> watcher that cries wolf every Saturday trains the orchestrator (and the founder) to
> ignore it, which defeats the whole point.

### Fuzzy (text) — needs intelligence, build after the framework is proven
- **Relevance gate:** embedding similarity (or a cheap LLM yes/no) between an item and the
  company profile + watchlist. This is the borderline-but-allowed use of an LLM in a
  watcher — a *binary gate*, not an assessment.
- **Sentiment / classification:** negative vs. neutral vs. positive; topic tagging.
- **Volume / topic anomaly:** a *spike* in items about one topic (z-score on counts, per
  topic cluster) — e.g. "tickets about CSV export up 3×".
- **Clustering:** group similar items so one event = "a cluster of complaints about X",
  not 40 separate pings (noise control).

**Cost note for fuzzy:** an LLM relevance gate on every news item gets expensive and slow.
Mitigations: cheap pre-filter by keyword/embedding first, batch, cache by content hash,
and run the gate only on items that pass change-detection.

---

## 5. The three watcher families (in detail)

Watchers are organized **by data source** (the orchestrator is the router that maps source
→ expertise). Three families, in recommended build order.

### 5.1 Metrics Watcher — **build this first** (deterministic, highest signal)

The cleanest first real watcher: no fuzzy relevance, pure numbers, and the events it
produces (revenue/usage/churn moves) are exactly what the Finance/Retention specialists
are built to analyze.

- **Sources:** Stripe (MRR, new/churned subscriptions, failed payments), product analytics
  (PostHog/Amplitude/Mixpanel: DAU/WAU, activation, feature usage, funnel conversion), the
  product DB / data warehouse (anything queryable), bank/accounting (cash, runway).
- **Signals:** MRR drop/spike, churn-rate move, DAU/WAU drop, activation-rate decline,
  conversion drop, runway threshold, signup stall (streak), expansion/contraction.
- **Method:** on each tick, query each tracked metric → compute z-score (or %Δ, or
  threshold) vs. a persisted rolling baseline → if breached and not already fired this
  period, emit. Update the baseline.
- **State:** rolling window of recent values per metric (baseline) + last-fired markers.
- **Config:** which metrics, query cadence, per-metric method + sensitivity (`k`),
  seasonality mode.
- **Examples:** "MRR −15% WoW (z=−3.1)", "Starter churn 5% vs. ~2.5% baseline", "DAU −22%".
- **Why first:** deterministic (no NLP), self-calibrating baselines, and it closes the
  loop with specialists we've already verified. It's also the most *defensible* in a demo
  ("this fired because the number genuinely moved 3σ").

### 5.2 Market / External Watcher (fuzzy — relevance filtering)

Detects moves in the outside world (the family the current stub fakes).

- **Sources:** news APIs (NewsAPI, GDELT), RSS/Atom feeds, competitor **page diffing**
  (pricing, changelog, blog — scrape + content hash), Product Hunt / Hacker News launches,
  Crunchbase / funding feeds, Google Alerts, social (X/Reddit) mentions.
- **Method:** pull items → dedup (seen-ids / url+content hashes) → **relevance gate**
  against a **watchlist** (named competitors, our category keywords, our product area) via
  embedding similarity or a cheap LLM yes/no → emit the relevant ones. Competitor pages
  use content-diff (fire only when the page actually changed).
- **State:** per-source cursors, seen-set, per-page content hashes.
- **Examples:** "Typeform shipped an AI form builder", "competitor X raised a Series B",
  "new entrant launched on Product Hunt in our category".
- **Challenges (be honest):** noisy sources; relevance precision/recall tuning; scraping is
  fragile and has ToS/legal limits; API rate limits and cost; the LLM gate's latency/$$.
  This is *real* engineering, not a weekend — hence it's after the framework.

### 5.3 People & Voice Watcher (fuzzy — sentiment / volume anomaly)

Detects internal signals and the customer's voice — the qualitative early-warning system.

- **Sources:** support tickets (Zendesk/Intercom), NPS/CSAT surveys, product reviews (G2,
  Capterra, App/Play stores), community (Discord/Slack), social mentions, churn-risk
  product signals (usage drop on a key account), optionally internal team sentiment.
- **Method:** pull → dedup → classify (sentiment + topic) → detect **anomalies**: a spike
  in volume per topic (z-score on counts), an NPS/CSAT drop (numeric, deterministic), a
  cluster of negative reviews on one theme. Cluster so one event = one theme, not N pings.
- **State:** cursors per source, per-topic volume baselines, last NPS/CSAT values.
- **Examples:** "Support tickets about exports up 3× this week", "NPS dropped 45→30",
  "cluster of 1-star reviews citing the new pricing".
- **Challenges:** PII handling, sentiment-model accuracy, signal-vs-noise, topic drift.

---

## 6. Scheduling & ingestion — poll vs. push (and the clock question)

- **Poll loop** (today's model): a timer (real cron or the sim-clock) drives queries. Simple,
  works for everything, but introduces detection latency and wastes calls on quiet sources.
- **Push / webhooks:** sources like Stripe events and Slack events can *push* to us in real
  time. This needs a small **always-on listener service** (an HTTP endpoint) that receives
  the webhook, runs the same detect→filter→emit pipeline, and posts to the room. Lower
  latency, fewer wasted calls, but more infra (a public endpoint, signature verification).

**The clock question:** the sim-clock is the right driver for a *demo* (compresses weeks
into minutes, visibly idle). In **production**, watchers run on real wall-clock time (real
cron / real webhooks). The design should let the scheduling source be swappable —
sim-clock for demo, real scheduler for prod — without touching detection logic. The
`SimClock` seam (`current_day()` + a tick generator) was built with this in mind; a real
clock is the same interface backed by wall time.

**Recommendation:** start poll-only (uniform, simple); add webhook ingestion for Stripe and
one chat source once the poll model is proven. Don't build the listener service until a
source clearly justifies the latency win.

---

## 7. The Watcher Framework (a `_base` for watchers) — the real unlock

The single highest-leverage thing to build. Just as `agents/specialists/_base.py` turned a
new specialist into "backstory + instructions + `run_specialist(...)`", a watcher base
should turn a new watcher into **"connector + detect-rule + relevance gate"**.

What the base owns (so no watcher re-implements it):
- the scheduling loop (poll via clock, or webhook entrypoint),
- normalize → change-detection → dedup → relevance-gate → emit pipeline,
- **persisted state** helper (baselines / cursors / seen-sets / hashes — one small
  store, like `clock_state.json` but per-watcher),
- the **event contract** emission (§3) to the room,
- structured logging (what it saw / filtered / fired — so a silent watcher is debuggable,
  the lesson from the specialist logging gap),
- failure handling (source down → log + back off, **never crash the room**),
- rate-limit / backoff helpers.

A new watcher then declares: its source connector, its detect-rule (a z-score config, or a
relevance gate), and its `signal_type`s. This is the pattern that makes families 5.2 and
5.3 affordable instead of bespoke.

---

## 8. The live company profile (relevance's reference) — make it real

Relevance filtering needs something to filter *against*. Today `core/company_data.py` is a
mock profile that specialists read. For real watchers it must grow into the shared
**company profile + watchlist** that all three tiers read (the institutional-memory pillar):

- **Live metrics** (replacing the mock numbers) — the same module, but values fetched from
  Stripe/analytics instead of hardcoded. Specialists need zero changes (the brief's whole
  point: swap the data source, not the agents).
- **Watchlist** — named competitors, category keywords, product areas, key accounts,
  metric thresholds. This is what the Market/Voice relevance gates score against.
- **Profile facts** — what we sell, to whom, our segments — so "is this in our world?" has
  a reference.

**Recommendation:** formalize the profile/watchlist as config now (even while values stay
mock); wiring live sources is then a connector swap.

---

## 9. Cross-cutting concerns (none optional for "real")

- **Reliability:** a source outage must degrade gracefully — log, back off, keep the room
  alive. A watcher crash must not take down detection for other signals (isolate per
  watcher process, like today).
- **Cost & rate limits:** API quotas (Stripe/news), and especially **LLM relevance cost** —
  pre-filter cheaply, batch, cache by content hash, gate only post-dedup items.
- **Observability:** every watcher logs saw/filtered/fired counts; a "quiet day" is visible,
  not silent. Optionally a heartbeat so we know a watcher is alive vs. hung.
- **Secrets & security:** source API keys via `.env` (never committed); webhook signature
  verification; least-privilege source credentials.
- **PII / compliance:** People & Voice touches customer data — minimize, avoid storing raw
  PII in the event/memory, respect retention rules.
- **Tuning (precision vs. recall):** the watcher's real product value is *protecting the
  orchestrator's (and founder's) attention*. Too sensitive → noise → everyone ignores it.
  Too dull → misses the thing that mattered. Thresholds and the relevance gate need a
  feedback loop (e.g. learn from which events the orchestrator judged "not material").

---

## 10. Feature set & recommended priority

| # | Feature | Type | Effort | Priority | Why |
|---|---------|------|--------|----------|-----|
| 1 | **Event contract** (`core/events.py`) + migrate stub to it | foundation | S | **P0** | unlocks everything; safe, downstream-compatible |
| 2 | **Watcher framework** (`_base` for watchers) | foundation | M | **P0** | makes every later watcher cheap |
| 3 | **Metrics Watcher** (z-score vs. baseline, persisted) | watcher | M | **P1** | deterministic, highest signal, closes loop with Finance/Retention |
| 4 | **Live company profile + watchlist** | data | M | **P1** | relevance reference; live metrics for specialists |
| 5 | **Market Watcher** (news/RSS + competitor page-diff + relevance gate) | watcher | L | **P2** | replaces the faked family; fuzzy, real engineering |
| 6 | **People & Voice Watcher** (tickets/reviews/NPS + anomaly) | watcher | L | **P2** | qualitative early-warning |
| 7 | **Webhook ingestion service** (Stripe/Slack push) | infra | M | **P3** | latency/efficiency once poll is proven |
| 8 | **Real (wall-clock) scheduler** swap | infra | S | **P3** | production driver; sim-clock stays for demos |
| 9 | **Relevance-tuning feedback loop** (learn from orchestrator's "not material" verdicts) | quality | M | **P4** | closes the precision/recall loop; advanced |

### Beyond watchers (features real detection enables)
- **Scheduled beats** (proactive cadence): weekly review, renewal day, month-end close —
  the orchestrator wakes on a *scheduled* sim-day with no external event. The `SimClock`
  seam already supports this; it's "a watcher whose source is the calendar."
- **Persistent orchestrator checkpointer** (SQLite vs. `InMemorySaver`) — so an in-flight
  investigation also survives restart (today only the durable record does). Deferred in
  Step 2; pairs naturally with always-on watchers.
- **Embedding-based memory recall** — upgrade `recall_decisions` `_score()` from keyword to
  embeddings (the seam is already isolated). More important as memory grows.
- **Alerting channels** — the founder brief could also go to email/Slack/SMS, not just the
  room. (The room stays the system of record.)
- **More specialists** — once detection is rich (e.g. a Product/Roadmap or Security
  specialist), since `_base.py` makes them cheap.

---

## 11. My recommendation (the opinionated take)

1. **Do the two foundations first (P0): the event contract and the watcher framework.**
   They're modest effort and they're what make real watchers cheap instead of three
   bespoke scripts. Skipping them = three divergent watchers and a refactor later (the
   exact thing `_base.py` saved us from on specialists).
2. **Then build the Metrics Watcher (P1) and only it, end-to-end.** Prove the whole real
   pipeline — connector → baseline → z-score → dedup → event → existing cascade — on the
   *easy, deterministic* case. This is the moment Evergreen stops being a demo.
3. **Make the company profile real alongside it (P1)** — live metrics flow into the same
   `company_data` interface specialists already read; relevance gets a watchlist.
4. **Treat Market and Voice (P2) as genuine projects, not a weekend.** They're fuzzy,
   noisy, and fragile (scraping/ToS/PII/LLM cost). Worth it, but only after the framework
   de-risks them. The current stub is *fine* until then — the interface guarantees no
   downstream rework.
5. **Defer webhooks, real scheduler, and the tuning loop (P3–P4)** until a real source
   demands them. Don't build infra ahead of need.
6. **Hold the line from §1 relentlessly.** Every time a watcher feature tempts us to let it
   "just decide if it's important," push that into the orchestrator. The funnel's value is
   that boundary.

What I would **not** do: build all three families at once; add an LLM relevance gate before
the deterministic metrics path works; build the webhook service before poll is proven; or
let watchers grow severity/recommendation logic.

---

## 12. Open questions for you (decisions before any build)

1. **Which real source first?** Stripe (revenue) and a product-analytics tool (usage) are
   the obvious Metrics candidates — which do we actually have access to?
2. **Demo vs. prod clock:** keep sim-clock for the demo and add a real scheduler later, or
   go straight to wall-clock? (I'd keep sim-clock for now.)
3. **How much LLM in relevance gates?** Embeddings (cheap, needs a vector step) vs. an LLM
   yes/no (simpler, pricier)? Affects the Market/Voice cost profile.
4. **Webhooks now or later?** Are any sources push-capable and latency-sensitive enough to
   justify the listener service early?
5. **How real should the company profile get?** Live metrics end-to-end, or keep mock
   values and just add the watchlist config for relevance?
6. **Event contract scope:** minimal (source/type/observation/dedup_key) or the full
   table in §3 including `magnitude`/`evidence`/`confidence`? (I lean full — it's cheap now
   and provenance strengthens the memory pillar.)
