# Evergreen — Real Market Watcher (build brief for Claude Code)

> Read order: `EVERGREEN_CONTEXT.md` (state + Band facts) → `EVERGREEN_NEXT.md` **§A
> (how to work)** → `EVERGREEN_WATCHERS.md` (the detection-layer design; this implements
> its **§5.2 Market Watcher** as the curated/deterministic P2 slice). This is the
> ACTIVE NEXT from the status doc.
>
> The Metrics watcher is already "real" via its source. This makes the **external** side
> real too — and it's the family that maps cleanly to a fictional company *because the
> competitors are real* (Typeform, Jotform, Google Forms, Tally).

---

## 0. Goal & the one non-obvious constraint

**Goal:** a watcher that detects *genuine* competitor moves from real public sources and
emits the existing event contract — replacing the *role* of the scripted feed, not the
script itself.

**The constraint to internalize first — this runs on WALL-CLOCK, not the sim-clock.**
The Metrics watcher works on sim-time only because its source (fake Stripe) is
`as_of`-parameterized. A real external page changes in real time — you can't
fast-forward Typeform's real changelog to sim-day 12. Consequences:
- **Keep the scripted Market watcher for the on-cue demo beat.** You cannot summon a
  real competitor change during a 2-minute compressed demo, so do NOT rely on this one
  for a live scripted beat. Run it **alongside** the scripted one as continuous proof
  ("it's genuinely watching real Typeform — here's a real change it caught").
- **Stamp emitted events with the current `sim_day`** so the memory timeline stays
  coherent, but its *polling cadence is real wall-clock* (e.g. every few minutes).
- Replacing the scripted watcher entirely is correct only once you're in continuous
  real-product operation, not demoing.

---

## 1. Locked decisions

1. **Source = targeted, curated competitor update pages; mechanism = content-diff.**
   Not a broad news API first. Prefer a real RSS/Atom feed **only where you verify one
   genuinely exists** (cleaner than scraping); otherwise diff the page.
   - **Verified real targets (June 2026 — confirm the live URL + check for a feed first):**
     - Typeform product Changelog (Help Center): `https://help.typeform.com/hc/en-us/articles/29035269414036-Changelog` — dated monthly entries, clean diff target.
     - Jotform product updates: `https://www.jotform.com/blog/product/`.
     - Google Forms / Tally: curate their public "what's new"/changelog pages at build
       time (verify before hardcoding — don't assume a feed).
   - Optionally also diff each competitor's **pricing page** for the specific
     `competitor_pricing_change` signal (the on-narrative one).
2. **Relevance gate = inherent / deterministic. No LLM gate now.** Curated competitor
   sources *are* the watchlist — every item from them is relevant by construction; a
   content-hash diff is itself the relevance test. Add a cheap keyword filter only if a
   source is broad; reserve an LLM gate for if/when you add a news firehose (its
   cost/latency/failure surface isn't worth it here).
3. **Clock = real wall-clock** (see §0). Scripted watcher stays for the demo beat.

Still the human's call (small, confirm before hardcoding): the exact competitor source
list and the poll cadence.

---

## 2. Pipeline (reuse `EVERGREEN_WATCHERS.md` §2 anatomy)

```
connector → normalize → change-detection/dedup → relevance(inherent) → emit → [persist]
```
- **Connector:** on a real-time interval, fetch each curated source (RSS via feedparser
  where it exists; else HTTP GET the page HTML).
- **Normalize:** map to a raw observation (title/text, link, source, timestamp).
- **Change-detection / dedup:**
  - RSS: a **seen-set** of entry ids/links — emit only unseen entries.
  - Page-diff: a **content hash** of the *meaningful region* (extract the changelog/
    update text, not the whole HTML — nav/footer/cookie banners must not trigger it).
    Emit only when the meaningful content changes.
  - **Seed silently on first run** (record what's already there; do NOT fire on
    everything you see initially) — fire only on subsequent change.
- **Emit** the existing event contract (`core/events.py`): `source`
  (e.g. `competitor:typeform`), `watcher="market"`, `signal_type`
  (`competitor_update` / `competitor_pricing_change`), `observation` (human-readable,
  raw), `evidence` (the URL), `dedup_key`, `observed_at` + current `sim_day`. Post to
  `@Orchestrator` via the existing REST send path (`X-API-Key`, ≥1 mention, resolve the
  orchestrator id from participants; must be a room participant).
- **Persist** the seen-set / content hashes to disk (e.g. `market_watcher_state.json`)
  so it **fires once and survives restart with no replay** — same discipline as the
  Metrics watcher and the clock.

---

## 3. Funnel discipline (the line not to cross)

The watcher emits a **raw observation + evidence only** — e.g. "Typeform's changelog
added an entry: '<text>'" with the URL. It must NOT attach severity, threat level, or a
recommendation. **Materiality is the orchestrator's job**, judged against the
watchlist: Typeform (major) → likely material; FormFly (minor) → likely not. The
watcher's "relevance" is just "is this a competitor we track"; "how much it matters"
stays upstream. If the watcher starts ranking importance, it's overstepping.

---

## 4. Build shape

It's the **existing Market watcher with the scripted feed swapped for a real
connector** — same REST send-only structure (no LLM, no adapter needed for a sender).
Keep the scripted feed as a separate mode/flag (`--scripted` or env switch) so the demo
beat still works and the real connector runs alongside. Everything env-driven: source
list, poll cadence, any feed/API keys, state-file path.

**ToS / hygiene (these are public update pages, but be a good citizen):**
- Respect `robots.txt`; set a clear, identifiable `User-Agent`.
- Sane poll interval (minutes, not seconds); cache; conditional GET (ETag/Last-Modified)
  where supported.
- Prefer an official feed over scraping where one genuinely exists.
- A source being down must **log + back off, never crash the room**; isolate per-source
  failures.

---

## 5. Verify (what to run)

- **Standalone, first run:** point it at a real changelog page → it seeds the
  hash/seen-set and **fires nothing**. Run again with no change → still nothing.
- **Standalone, on change:** because you can't make a real competitor publish on cue,
  test the diff by temporarily pointing it at a page you control (or a saved copy you
  edit) → it emits exactly **one** structured event with the evidence URL. Restart →
  **no replay** (state persisted).
- **With agents (cascade):** feed it a detected change (the controlled page, or a
  captured real diff) → orchestrator judges materiality **against the watchlist** →
  convenes Competitive Analysis (+ Finance if pricing) → grounded reply → stand-down →
  one founder brief → recorded. The materiality verdict should now be **grounded in the
  watchlist**, not generic priors.

---

## 6. Pitfalls

- **First-run flood** — seed silently; don't fire on the existing backlog.
- **Page-diff noise** — diff the extracted update text, not raw HTML, or layout/footer/
  cookie changes will false-fire (the "cries wolf every Saturday" failure from
  `EVERGREEN_WATCHERS.md` §4).
- **Assuming RSS** — verify per source; default to page-diff. Don't hardcode a feed URL
  you haven't confirmed (no bluffing).
- **Wall-clock vs sim-clock** — run real cadence, stamp `sim_day`; don't expect a live
  fire during the compressed demo.
- **Re-firing on restart** — persist the seen-set/hash.
- **Scraping fragility** — prefer feeds; isolate failures; back off.

---

## 7. Do-NOT

- No LLM relevance gate now; no broad news API as the first source.
- Don't replace the scripted Market watcher — **run both** (scripted = demo beat, real =
  proof).
- The watcher never judges — raw observation + evidence only.
- Respect ToS/robots; env-driven (sources, cadence, keys, state path).
- Don't build the generic watcher `_base` yet — this is the *second* real watcher, so
  if a shared base now pays off, extract it from Metrics + Market together; otherwise
  keep it inline (YAGNI until the third).