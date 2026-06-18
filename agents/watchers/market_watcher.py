"""
Market Watcher  --  Evergreen
=============================

Detects competitor moves and posts them to the room @mentioning the Orchestrator.
Two modes (env MARKET_WATCHER_MODE), both posting as the same "Market Watcher"
Band identity, send-only over REST (no SDK, no model):

* MODE=real (default) — the REAL connector. Polls curated competitor update sources
  on WALL-CLOCK time and fires on a genuine change. Relevance is inherent: the
  curated sources ARE the watchlist. It still only DETECTS — raw observation +
  evidence URL, never severity/recommendation. Materiality is the Orchestrator's job
  (judged against the watchlist: Typeform major -> likely material; Jotform minor ->
  likely not).
    - Typeform "What's New" (major) — page-diff of the dated release region.
    - Jotform product blog (minor) — RSS seen-set, filtered to the Product category.
  Events are stamped with the current sim_day (for memory-timeline coherence) but
  POLLED on real time. Seeds silently on first run; persists seen-set/hashes so it
  fires once and survives restart with no replay.

* MODE=scripted — the original sim-clock-driven scripted feed, kept as the on-cue
  DEMO beat (you can't make a real competitor publish during a 2-minute demo). Run it
  ALONGSIDE the real one.

Run (from project root):
    uv run python -m agents.watchers.market_watcher                      # real
    MARKET_WATCHER_MODE=scripted uv run python -m agents.watchers.market_watcher

Env: EVERGREEN_ROOM_ID, MARKET_WATCHER_API_KEY, ORCHESTRATOR_NAME;
     real mode: MARKET_POLL_SECONDS (900), MARKET_USER_AGENT, MARKET_STATE_FILE,
                TYPEFORM_WHATSNEW_URL, JOTFORM_FEED_URL;
     scripted mode: SIM_SECONDS_PER_DAY, SIM_START_DAY.
The Market Watcher and the Orchestrator must both be participants in the room.
"""

import hashlib
import json
import os
import re
import sys
import time
import urllib.robotparser
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from clock.sim_clock import SimClock, read_current_day
from core.events import Event


def _load_env() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv()
        return
    except Exception:
        pass
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_env()

REST_URL = os.getenv("THENVOI_REST_URL", os.getenv("BAND_REST_URL", "https://app.band.ai")).rstrip("/")
API = f"{REST_URL}/api/v1/agent"
WATCHER_API_KEY = os.getenv("MARKET_WATCHER_API_KEY")
ROOM_ID = os.getenv("EVERGREEN_ROOM_ID")
ORCH_NAME = os.getenv("ORCHESTRATOR_NAME", "Orchestrator")

MODE = os.getenv("MARKET_WATCHER_MODE", "real").lower()
POLL_SECONDS = int(os.getenv("MARKET_POLL_SECONDS", "900"))  # real-time cadence
USER_AGENT = os.getenv(
    "MARKET_USER_AGENT",
    "EvergreenMarketWatcher/1.0 (+https://github.com/dineshsai05/Evergreen)",
)
STATE_FILE = os.getenv("MARKET_STATE_FILE", "market_watcher_state.json")


# --------------------------------------------------------------------------- #
# Band Agent REST helpers (shared by both modes)
# --------------------------------------------------------------------------- #
def _headers() -> dict[str, str]:
    return {"X-API-Key": WATCHER_API_KEY, "Content-Type": "application/json"}


def _data(payload):
    return payload["data"] if isinstance(payload, dict) and "data" in payload else payload


def whoami(client: httpx.Client) -> str:
    try:
        r = client.get(f"{API}/me", headers=_headers())
        return _data(r.json()).get("name", "?") if r.status_code == 200 else f"(status {r.status_code})"
    except Exception as exc:  # noqa: BLE001
        return f"(error: {exc})"


def resolve_orchestrator(client: httpx.Client) -> dict | None:
    r = client.get(f"{API}/chats/{ROOM_ID}/participants", headers=_headers())
    r.raise_for_status()
    participants = _data(r.json())
    if isinstance(participants, dict):
        participants = participants.get("data", [])
    for p in participants:
        if str(p.get("name", "")).lower() == ORCH_NAME.lower():
            return {k: v for k, v in {"id": p.get("id"), "handle": p.get("handle"),
                                      "name": p.get("name")}.items() if v}
    return None


def _post(client: httpx.Client, orchestrator: dict, content: str) -> None:
    body = {"message": {"content": content, "mentions": [orchestrator]}}
    r = client.post(f"{API}/chats/{ROOM_ID}/messages", headers=_headers(), json=body)
    r.raise_for_status()


# =========================================================================== #
# SCRIPTED MODE — the on-cue demo beat (sim-clock driven). Unchanged behaviour.
# =========================================================================== #
SCHEDULE: dict[int, tuple[str, str]] = {
    3: ("market", "A minor competitor, FormFly, pushed a small UI refresh and some "
                  "marketing copy changes this week."),
    12: ("market", "Competitor Typeform just announced a 30% price cut on their Starter "
                   "plan plus a new AI form-building feature."),
}


def run_scripted(client: httpx.Client, orchestrator: dict) -> None:
    clock = SimClock()
    print(f"[market/scripted] reporting to {orchestrator['name']}; "
          f"{clock.seconds_per_day:g}s = 1 sim-day; resuming at day {clock.current_day()}; "
          f"scheduled days: {sorted(SCHEDULE)}")
    for day in clock.tick():
        scheduled = SCHEDULE.get(day)
        if not scheduled:
            print(f"[market/scripted] sim-day {day}: all quiet")
            continue
        _, text = scheduled
        content = f"@{orchestrator['name']} [event from market-watcher · sim-day {day}] {text}"
        print(f"[market/scripted] sim-day {day}: emitting -> {ORCH_NAME}")
        try:
            _post(client, orchestrator, content)
            print("[market/scripted] posted.")
        except httpx.HTTPStatusError as exc:
            print(f"[market/scripted] POST failed: {exc.response.status_code} {exc.response.text}")


# =========================================================================== #
# REAL MODE — wall-clock connector over curated competitor sources.
# =========================================================================== #
def _sources() -> list[dict]:
    """Curated competitor sources (the watchlist). URLs env-overridable. The
    help-center Typeform changelog is WAF-blocked (403); we use the main-domain
    What's New page, which is fetchable and robots-allowed."""
    return [
        {
            "key": "competitor:typeform", "name": "Typeform", "tier": "major", "type": "page",
            "url": os.getenv("TYPEFORM_WHATSNEW_URL", "https://www.typeform.com/whats-new"),
            # isolate the dated release headings; ignores nav/footer/blurb-wording noise
            "pattern": r"(?:Winter|Spring|Summer|Fall)\s+20\d{2}",
        },
        {
            "key": "competitor:jotform", "name": "Jotform", "tier": "minor", "type": "rss",
            "url": os.getenv("JOTFORM_FEED_URL", "https://www.jotform.com/blog/feed/"),
            "category": "Product",
        },
        {
            # Google Workspace Updates Blogger Atom feed, label-filtered to Google Forms
            # (inherent relevance — the label feed is Forms-only, so no category filter).
            "key": "competitor:googleforms", "name": "Google Forms", "tier": "minor", "type": "rss",
            "url": os.getenv(
                "GOOGLE_FORMS_FEED_URL",
                "https://workspaceupdates.googleblog.com/feeds/posts/default/-/Google%20Forms",
            ),
        },
        {
            "key": "competitor:tally", "name": "Tally", "tier": "minor", "type": "page",
            "url": os.getenv("TALLY_CHANGELOG_URL", "https://tally.so/changelog"),
            # dated entry headings ("June 10, 2026 — …") are the change key
            "pattern": r"(?:January|February|March|April|May|June|July|August|September|"
                       r"October|November|December)\s+\d{1,2},\s+20\d{2}",
        },
    ]


def http_fetch(url: str, etag: str | None = None, last_modified: str | None = None) -> dict:
    """Default fetcher: conditional GET with an identifiable UA. Returns a dict the
    connector understands. (Injectable so tests can supply fixtures.)"""
    headers = {"User-Agent": USER_AGENT}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    r = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)
    return {"status": r.status_code, "text": r.text,
            "etag": r.headers.get("ETag"), "last_modified": r.headers.get("Last-Modified")}


_robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}


def robots_allows(url: str, fetcher=http_fetch) -> bool:
    """Respect robots.txt for the curated path (good-citizen). Fail-open if robots
    can't be read (standard practice), logging the reason."""
    host = urlparse(url)
    base = f"{host.scheme}://{host.netloc}"
    rp = _robots_cache.get(base)
    if rp is None:
        rp = urllib.robotparser.RobotFileParser()
        try:
            res = fetcher(f"{base}/robots.txt")
            if res["status"] == 200:
                rp.parse(res["text"].splitlines())
            else:
                rp.allow_all = True
        except Exception as exc:  # noqa: BLE001
            print(f"[market/real] robots.txt unreadable for {base} ({exc}); allowing")
            rp.allow_all = True
        _robots_cache[base] = rp
    return rp.can_fetch(USER_AGENT, url)


def _clean_text(html: str) -> str:
    """Extract human-readable text, dropping nav/footer/script/style so layout/cookie
    noise can't trigger a false diff."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "form", "button"]):
        tag.decompose()
    return re.sub(r"\n{2,}", "\n", soup.get_text("\n")).strip()


def _page_extract(src: dict, html: str) -> dict:
    """The 'meaningful update region' for a page source as {key: detail}. With a
    pattern, each dated release HEADING maps to the BLURB that follows it: the heading
    set is the stable change key (robust to wording/layout noise — a blurb edit on an
    existing release won't false-fire), while the blurb is surfaced in the observation
    so the orchestrator sees release detail (e.g. a price cut). Without a pattern
    (e.g. a controlled test page), the whole cleaned text under one key."""
    text = _clean_text(html)
    pat = src.get("pattern")
    if not pat:
        return {"_page": text}
    matches = list(re.finditer(pat, text))
    out: dict[str, str] = {}
    for i, mt in enumerate(matches):
        nxt = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        blurb = " ".join(s.strip() for s in text[mt.end():nxt].splitlines() if s.strip())
        out[mt.group(0)] = blurb[:200]
    return out


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]  # strip any XML namespace


def parse_feed(xml_text: str) -> list[dict]:
    """Parse RSS 2.0 (<item>) OR Atom (<entry>), namespace-agnostic, with stdlib
    ElementTree (no feedparser/lxml). Handles RSS <link>text + <guid> and Atom
    <link rel=alternate href> + <id> + <category term>."""
    root = ET.fromstring(xml_text)
    items = []
    for el in root.iter():
        if _localname(el.tag) not in ("item", "entry"):
            continue
        title = link = guid = ""
        cats = []
        for ch in el:
            ln = _localname(ch.tag)
            if ln == "title":
                title = (ch.text or "").strip()
            elif ln == "link":
                href = ch.get("href")  # Atom
                if href:
                    if ch.get("rel", "alternate") == "alternate" or not link:
                        link = href
                elif ch.text:  # RSS
                    link = ch.text.strip()
            elif ln == "guid":
                guid = (ch.text or "").strip()
            elif ln == "id" and not guid:  # Atom id
                guid = (ch.text or "").strip()
            elif ln == "category":
                cats.append((ch.get("term") or ch.text or "").strip())
        items.append({"id": guid or link, "title": title, "link": link,
                      "categories": [c for c in cats if c]})
    return items


def _make_event(src: dict, observation: str, dedup_suffix: str, evidence: list[str]) -> Event:
    return Event(
        source=src["key"],
        signal_type="competitor_update",
        observation=observation,
        dedup_key=f"{src['key']}:{dedup_suffix}",
        sim_day=read_current_day(default=0),
        evidence=evidence,
        watcher="market",
    )


def process_source(src: dict, prev: dict, fetcher=http_fetch) -> tuple[list[Event], dict]:
    """Fetch one source, detect genuine change, return (events, new_state). Pure of
    transport — `fetcher` is injectable for tests. Seeds silently (no events) on first
    sight; fires only on subsequent change; returns updated per-source state."""
    prev = prev or {}
    res = fetcher(src["url"], prev.get("etag"), prev.get("last_modified"))
    if res["status"] == 304:  # unchanged since last poll
        return [], prev
    if res["status"] != 200:
        raise RuntimeError(f"HTTP {res['status']} for {src['url']}")

    meta = {"etag": res.get("etag"), "last_modified": res.get("last_modified")}
    events: list[Event] = []

    if src["type"] == "page":
        cur = _page_extract(src, res["text"])
        prev_entries = prev.get("entries")
        new_state = {**prev, **meta, "entries": cur}
        if prev_entries is None:
            return [], new_state  # seed silently on first sight
        if src.get("pattern"):
            prev_keys = set(prev_entries)  # tolerates old list-format state
            added = [h for h in cur if h not in prev_keys]
            changed = set(cur) != prev_keys  # fire on a NEW (or removed) release heading
        else:
            added, changed = [], (cur != prev_entries)  # whole-text diff (test pages)
        if changed:
            digest = hashlib.sha256(json.dumps(sorted(cur), sort_keys=True).encode()).hexdigest()[:8]
            if added:
                detail = "; ".join(f"{h} — {cur[h]}" if cur.get(h) else h for h in added)
                obs = f"{src['name']}'s update page added: {detail}"
            else:
                obs = f"{src['name']}'s update page changed"
            events.append(_make_event(src, obs, digest, [src["url"]]))
        return events, new_state

    # RSS
    items = parse_feed(res["text"])
    cat = src.get("category")
    if cat:
        items = [it for it in items if any(cat.lower() == c.lower() for c in it["categories"])]
    seeded = prev.get("seen") is not None
    seen = set(prev.get("seen", []))
    new_state = {**prev, **meta, "seen": list({*seen, *(it["id"] for it in items)})[-500:]}
    if seeded:
        for it in items:
            if it["id"] in seen:
                continue
            events.append(_make_event(src, f'{src["name"]} published: "{it["title"]}"',
                                      it["id"], [it["link"]] if it["link"] else []))
    return events, new_state


def _load_state() -> dict:
    try:
        return json.loads(Path(STATE_FILE).read_text())
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        return {}


def _save_state(state: dict) -> None:
    Path(STATE_FILE).write_text(json.dumps(state))


def run_real(client: httpx.Client, orchestrator: dict, fetcher=http_fetch) -> None:
    sources = [s for s in _sources() if robots_allows(s["url"], fetcher)]
    print(f"[market/real] reporting to {orchestrator['name']}; polling every {POLL_SECONDS}s; "
          f"sources: {[s['key'] for s in sources]}")
    while True:
        state = _load_state()
        for src in sources:
            try:
                events, new_state = process_source(src, state.get(src["key"], {}), fetcher)
            except Exception as exc:  # noqa: BLE001 — a source failing must not crash the room
                print(f"[market/real] {src['key']}: fetch/parse failed ({exc}); backing off")
                continue
            for ev in events:
                print(f"[market/real] {src['key']}: FIRING competitor_update — {ev.observation}")
                try:
                    _post(client, orchestrator, ev.render(orchestrator["name"]))
                except httpx.HTTPStatusError as exc:
                    print(f"[market/real] POST failed: {exc.response.status_code} {exc.response.text}")
            if not events:
                print(f"[market/real] {src['key']}: no change")
            state[src["key"]] = new_state
            _save_state(state)
        time.sleep(POLL_SECONDS)


# --------------------------------------------------------------------------- #
def main() -> None:
    missing = [n for n, v in [("MARKET_WATCHER_API_KEY", WATCHER_API_KEY),
                              ("EVERGREEN_ROOM_ID", ROOM_ID)] if not v]
    if missing:
        sys.exit(f"[market] missing required env: {', '.join(missing)}")

    with httpx.Client(timeout=30) as client:
        print(f"[market] mode={MODE}; connected as: {whoami(client)}")
        orchestrator = resolve_orchestrator(client)
        if not orchestrator:
            sys.exit(f"[market] could not find '{ORCH_NAME}' among room participants.")
        (run_scripted if MODE == "scripted" else run_real)(client, orchestrator)


if __name__ == "__main__":
    main()
