#!/usr/bin/env python3
"""Free public-web game-signal watcher. No X API, no paid services, stdlib only."""
from __future__ import annotations
import datetime as dt
import email.utils
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "data" / "state.json"
REPORT = ROOT / "data" / "latest.md"
UTC = dt.timezone.utc
NOW = dt.datetime.now(UTC)
USER_AGENT = "GameSignalWatch/1.0 (public feed monitor; no API keys)"
REQUEST_TIMEOUT = 12

# Queries rotate. Latest and top are both sampled to spot early and large spikes.
BSKY_TERMS = [
    "game prototype", "indie game", "I made a game", "game mechanic",
    "physics game", "gameplay prototype", "making a game", "game dev",
    "game concept", "horror game", "roblox game", "fortnite creative",
    "ゲーム開発", "ゲーム制作", "ゲーム試作", "自作ゲーム", "ゲーム アイデア", "新作ゲーム",
]
BING_TERMS = [
    'site:x.com/status "game prototype"', 'site:x.com/status "indie game"',
    'site:x.com/status "gameplay" "made"', 'site:x.com/status "game mechanic"',
    'site:x.com/status "ゲーム開発"', 'site:x.com/status "ゲーム作った"',
    'site:twitter.com/status "indie game"', 'site:x.com/status "new game" video',
]
NEWS_TERMS = [
    '"indie game" "viral" when:3d', '"game prototype" "viral" when:7d',
    '"game dev" "twitter" when:7d', '"インディーゲーム" "話題" when:3d',
    '"new game" "X post" viral when:7d', '"Roblox" "viral" "game" when:3d',
]
MASTODON_FEEDS = [
    "https://mastodon.gamedev.place/tags/indiedev.rss",
    "https://mastodon.gamedev.place/tags/gamedev.rss",
]
KEYS = ["game", "play", "prototype", "indie", "devlog", "mechanic", "made", "physics", "roblox", "fortnite", "steam", "pixel", "horror", "ゲーム", "ロブロックス", "フォートナイト", "試作", "開発", "自作"]
EXCLUDE = ["job hiring", "game developer salary", "stock market", "game of thrones", "nba game", "football game"]
XPOST = re.compile(r"https?://(?:www\.)?(?:x|twitter)\.com/[^\s/]+/status/\d+", re.I)
URLS = re.compile(r"https?://[^\s<>\"']+", re.I)


def iso(t=None):
    return (t or NOW).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_state():
    if not STATE.exists():
        return {"version": 1, "runs": [], "posts": {}, "notified": []}
    return json.loads(STATE.read_text(encoding="utf-8"))


def request(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json, application/rss+xml, application/xml, text/xml, */*"})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
        return response.read(3_000_000)


def date_iso(raw):
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            return dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        return dt.datetime.fromisoformat(raw).astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    except Exception:
        try:
            return email.utils.parsedate_to_datetime(raw).astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        except Exception:
            return None


def normalized_url(url):
    url = (url or "").strip().rstrip("),.;]}")
    if not url:
        return ""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        return ""
    host = parsed.netloc.lower().removeprefix("www.")
    if host in {"twitter.com", "x.com", "mobile.twitter.com"}:
        host = "x.com"
    return urllib.parse.urlunsplit(("https", host, parsed.path.rstrip("/"), "", ""))


def relevant(text):
    """Only flag an actual game concept, developer demonstration, or prototype.

    This is intentionally conservative; the separate ChatGPT discovery task covers
    broad low-information X videos and can manually promote strong exceptions.
    """
    text = (text or "").lower()
    if any(s in text for s in EXCLUDE):
        return False
    if not any(s in text for s in ["game", "gameplay", "prototype", "gamedev", "indiedev", "roblox", "fortnite", "ゲーム", "ロブロックス", "フォートナイト"]):
        return False
    cues = [
        r"\b(?:i|we|our team|my studio)\s+(?:just\s+)?(?:made|built|developed|created|am making|are making|am working on)\b",
        r"\b(?:game prototype|gameplay prototype|gameplay reveal|gameplay trailer|first gameplay|game mechanic|game concept|game jam|devlog|physics game)\b",
        r"\b(?:game where|game that lets|play my game|playable demo|working on my game|working on our game|new game i made)\b",
        r"(?:自作ゲーム|ゲーム開発|ゲーム制作|ゲームの試作|試作ゲーム|ゲームを作|ゲームを開発|作っているゲーム)",
    ]
    return any(re.search(pattern, text) for pattern in cues)


def classify(post):
    """Accept a signal only with positive gaming context. No made-up X metrics."""
    title = post.get("title", "") or ""
    desc = post.get("text", "") or ""
    if not relevant(title + " " + desc):
        return None
    return post


def bsky_to_signal(p):
    record = p.get("record") or {}
    text = record.get("text", "") or ""
    created = date_iso(record.get("createdAt") or p.get("indexedAt"))
    author = p.get("author") or {}
    handle = author.get("handle", "")
    uri = p.get("uri", "")
    rkey = uri.rsplit("/", 1)[-1] if uri else ""
    primary = f"https://bsky.app/profile/{handle}/post/{rkey}" if handle and rkey else ""
    media = p.get("embed") or record.get("embed") or {}
    has_video = "video" in json.dumps(media, ensure_ascii=False).lower()
    has_image = "image" in json.dumps(media, ensure_ascii=False).lower()
    refs = [normalized_url(u) for u in XPOST.findall(text)]
    if isinstance(media, dict) and isinstance(media.get("external"), dict):
        refs += [normalized_url(u) for u in XPOST.findall(media["external"].get("uri", ""))]
    signal = {"url": primary, "title": text[:180].strip().replace("\n", " "), "text": text[:600], "published": created, "source": "bluesky", "author": handle, "likes": int(p.get("likeCount") or 0), "reposts": int(p.get("repostCount") or 0), "replies": int(p.get("replyCount") or 0), "video": has_video, "image": has_image, "x_posts": sorted(set(filter(None, refs)))}
    return classify(signal)


def parse_rss(content, source):
    root = ET.fromstring(content)
    posts = []
    entries = root.findall(".//item")
    for item in entries:
        title = " ".join("".join(item.findtext("title", default="")).split())
        link = item.findtext("link", default="")
        raw = item.findtext("description", default="")
        clean = re.sub(r"<[^>]+>", " ", raw)
        pub = date_iso(item.findtext("pubDate", default=""))
        refs = [normalized_url(u) for u in XPOST.findall(link + " " + clean)]
        signal = {"url": normalized_url(link), "title": title[:180], "text": clean[:500], "published": pub, "source": source, "author": "", "likes": None, "reposts": None, "replies": None, "video": False, "image": False, "x_posts": sorted(set(filter(None, refs)))}
        signal = classify(signal)
        if signal:
            posts.append(signal)
    return posts


def collect():
    results = []
    stats = []
    h = NOW.hour
    # One high-coverage and one emerging query each run, with rotating language/phrases.
    indices = sorted({(h * 3 + i) % len(BSKY_TERMS) for i in range(6)})
    for index in indices:
        term = BSKY_TERMS[index]
        for sort in ("latest", "top"):
            url = "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts?" + urllib.parse.urlencode({"q": term, "sort": sort, "limit": 100})
            try:
                data = json.loads(request(url))
                signals = [bsky_to_signal(p) for p in data.get("posts", [])]
                signals = [p for p in signals if p]
                results.extend(signals)
                stats.append({"source": "bluesky", "query": term + "/" + sort, "status": "ok", "count": len(signals)})
            except Exception as e:
                stats.append({"source": "bluesky", "query": term + "/" + sort, "status": "error", "error": str(e)[:140]})
    # Search engine feeds have uneven indexing of X; this is discovery, NOT all-X collection.
    for i in range(4):
        term = BING_TERMS[(h * 2 + i) % len(BING_TERMS)]
        url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": term, "format": "rss"})
        try:
            posts = parse_rss(request(url), "bing-x-index")
            results.extend(posts)
            stats.append({"source": "bing-x-index", "query": term, "status": "ok", "count": len(posts)})
        except Exception as e:
            stats.append({"source": "bing-x-index", "query": term, "status": "error", "error": str(e)[:140]})
    for i in range(3):
        term = NEWS_TERMS[(h + i) % len(NEWS_TERMS)]
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": term, "hl": "en-US", "gl": "US", "ceid": "US:en"})
        try:
            posts = parse_rss(request(url), "google-news")
            results.extend(posts)
            stats.append({"source": "google-news", "query": term, "status": "ok", "count": len(posts)})
        except Exception as e:
            stats.append({"source": "google-news", "query": term, "status": "error", "error": str(e)[:140]})
    for feed in MASTODON_FEEDS:
        try:
            posts = parse_rss(request(feed), "mastodon")
            results.extend(posts)
            stats.append({"source": "mastodon", "query": feed, "status": "ok", "count": len(posts)})
        except Exception as e:
            stats.append({"source": "mastodon", "query": feed, "status": "error", "error": str(e)[:140]})
    for term in ("game prototype", "indie game", "roblox"):
        url = "https://hn.algolia.com/api/v1/search_by_date?" + urllib.parse.urlencode({"query": term, "tags": "story", "hitsPerPage": 30})
        try:
            hits = json.loads(request(url)).get("hits", [])
            posts = []
            for p in hits:
                title = p.get("title") or ""
                link = p.get("url") or ("https://news.ycombinator.com/item?id=" + str(p.get("objectID", "")))
                signal = {"url": normalized_url(link), "title": title, "text": title, "published": date_iso(p.get("created_at")), "source": "hacker-news", "author": p.get("author", ""), "likes": p.get("points") or 0, "reposts": None, "replies": p.get("num_comments") or 0, "video": False, "image": False, "x_posts": [normalized_url(u) for u in XPOST.findall(link + title)]}
                if classify(signal):
                    posts.append(signal)
            results.extend(posts)
            stats.append({"source": "hacker-news", "query": term, "status": "ok", "count": len(posts)})
        except Exception as e:
            stats.append({"source": "hacker-news", "query": term, "status": "error", "error": str(e)[:140]})
    return results, stats


def eligible(post, old):
    """Only numeric evidence from its ORIGINAL public platform qualifies for alert."""
    # Do not alert on old posts rediscovered by a top-ranked search.
    if not post.get("published"):
        return None
    try:
        age_hours = (NOW - dt.datetime.fromisoformat(post["published"].replace("Z", "+00:00"))).total_seconds() / 3600
        if age_hours < -1 or age_hours > 24 * 7:
            return None
    except (ValueError, TypeError):
        return None
    if post["source"] == "bluesky":
        likes, rts = post.get("likes") or 0, post.get("reposts") or 0
        if (likes >= 600 and rts >= 100) or rts >= 250:
            return "large_reposts_or_likes"
        if old and old.get("likes") is not None and old.get("prev_at"):
            try:
                hours = max(0.05, (NOW - dt.datetime.fromisoformat(old["prev_at"].replace("Z", "+00:00"))).total_seconds() / 3600)
                if hours <= 6 and (likes - old["likes"]) / hours >= 300 and (rts - (old.get("reposts") or 0)) / hours >= 35:
                    return "rapid_engagement_growth"
            except Exception:
                pass
    elif post["source"] == "hacker-news" and (post.get("likes") or 0) >= 175:
        return "hacker_news_points"
    return None


def update(state, signals):
    alerts = []
    posts = state.setdefault("posts", {})
    unique = {}
    for p in signals:
        if p.get("url"):
            key = normalized_url(p["url"])
            if key not in unique or (p.get("likes") or 0) > (unique[key].get("likes") or 0):
                unique[key] = p
    for key, p in unique.items():
        old = posts.get(key)
        criterion = eligible(p, old)
        fresh = dict(p)
        fresh["first_seen"] = old["first_seen"] if old else iso()
        fresh["last_seen"] = iso()
        fresh["prev_at"] = iso()
        fresh["history"] = ((old or {}).get("history", []) + [{"at": iso(), "likes": p.get("likes"), "reposts": p.get("reposts")}])[-12:]
        fresh["alerted"] = (old or {}).get("alerted", False)
        if criterion and not fresh["alerted"]:
            fresh["alerted"] = True
            fresh["alert_reason"] = criterion
            alerts.append(fresh)
        posts[key] = fresh
    # Bounded state; alerted items retained longer where possible.
    if len(posts) > 3500:
        kept = sorted(posts.items(), key=lambda kv: kv[1].get("last_seen", ""), reverse=True)[:3500]
        state["posts"] = dict(kept)
    return alerts, len(unique)


def issue_title(p):
    return "[GameSignal] " + (p.get("title", "")[:78] or p.get("url", ""))


def create_github_issue(p):
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPOSITORY")
    if not token or not repo:
        return {"status": "not_created", "reason": "No GitHub token/repository; local audit only"}
    body = (f"## 無料監視で検出したゲーム関連の急拡散候補\n\n"
            f"- 出典: {p['source']}（X上の拡散確認を意味しません）\n"
            f"- 一次投稿: {p['url']}\n"
            f"- 公開日時: {p.get('published') or '未確認'}\n"
            f"- 発信者: {p.get('author') or '未確認'}\n"
            f"- いいね/評価: {p.get('likes') if p.get('likes') is not None else '未取得'}\n"
            f"- 再投稿: {p.get('reposts') if p.get('reposts') is not None else '未取得'}\n"
            f"- 検知理由: {p.get('alert_reason')}\n"
            f"- X関連リンク: {', '.join(p.get('x_posts') or []) or '未確認'}\n\n"
            f"内容: {p.get('text', '')[:500]}\n\n"
            "**注意:** 取得できた数字は記載元サービスの数字のみ。Xの表示回数・X最古投稿・リーク真偽は別途検証が必要です。\n")
    owner = repo.split("/")[0]
    url = f"https://api.github.com/repos/{repo}/issues"
    # Check all recent issues including closed ones. A failed data push must not
    # produce duplicate notifications on the next run.
    for page in (1, 2, 3):
        check = f"{url}?state=all&per_page=100&page={page}"
        req = urllib.request.Request(check, headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                existing = json.load(resp)
            for old_issue in existing:
                if ("- 一次投稿: " + p["url"]) in (old_issue.get("body") or ""):
                    return {"status": "already_exists", "issue_url": old_issue.get("html_url")}
            if len(existing) < 100:
                break
        except Exception as e:
            # Safer to skip this alert than create duplicates when issue search fails.
            return {"status": "error", "error": "Issue dedup check failed: " + str(e)}
    payload = {"title": issue_title(p), "body": body, "assignees": [owner]}
    for attempt in range(2):
        req = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "Content-Type": "application/json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": USER_AGENT}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.load(resp)
            return {"status": "created", "issue_url": data.get("html_url")}
        except urllib.error.HTTPError as e:
            if e.code == 422 and attempt == 0:
                payload.pop("assignees", None)  # Avoid silently losing alert because repo forbids assignment.
                continue
            return {"status": "error", "code": e.code, "error": e.read(300).decode("utf-8", "replace")}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    return {"status": "error", "error": "unexpected"}


def report(state, run, alerts):
    top = sorted((p for p in state["posts"].values() if classify(p)), key=lambda x: ((x.get("reposts") or 0) * 3 + (x.get("likes") or 0)), reverse=True)[:30]
    lines = ["# Game Signal Watch — Latest", "", f"Last run (UTC): **{iso()}**", "", f"Sources OK: **{run['source_ok']}** / **{run['source_attempts']}**", f"Unique posts found this run: **{run['unique_results']}**", f"Alerts this run: **{len(alerts)}**", "", "## Top public-platform signals (not X views)", "", "| Source | Original link | Likes/points | Reposts | First seen |", "|---|---|---:|---:|---|" ]
    for p in top:
        safe = p.get("source", "").replace("|", "")
        lines.append(f"| {safe} | {p['url']} | {p.get('likes') if p.get('likes') is not None else '—'} | {p.get('reposts') if p.get('reposts') is not None else '—'} | {p.get('first_seen','')} |")
    lines += ["", "## Search route status", "", "| Source | Query | Status | Posts |", "|---|---|---|---:|"]
    for s in run["routes"]:
        lines.append(f"| {s['source']} | {s['query'].replace('|','/')} | {s['status']} | {s.get('count', '—')} |")
    lines += ["", "X metadata is **not** available without X access. A failure or missing indexed post is **not** a zero-viral claim. Reddit RSS was retired 2026-11-13 and is deliberately excluded. All sources are best effort; absence of a hit is not evidence that no viral game exists.", ""]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main():
    state = read_state()
    signals, stats = collect()
    alerts, count = update(state, signals)
    sent = []
    # Mark as alerted only if an Issue can be opened or we're in a local test.
    for p in alerts[:10]:
        result = create_github_issue(p)
        if result["status"] in ("error", "not_created"):
            state["posts"][normalized_url(p["url"])]["alerted"] = False
        sent.append({"url": p["url"], **result})
    for p in alerts[10:]:
        state["posts"][normalized_url(p["url"])]["alerted"] = False
    run = {"at": iso(), "source_attempts": len(stats), "source_ok": sum(s["status"] == "ok" for s in stats), "unique_results": count, "alerts": sent, "routes": stats}
    state.setdefault("runs", []).append(run)
    state["runs"] = state["runs"][-180:]
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report(state, run, alerts)
    print(json.dumps({"at": run["at"], "ok": run["source_ok"], "attempted": run["source_attempts"], "unique": count, "alerts": sent}, ensure_ascii=False))
    if run["source_ok"] == 0:
        sys.exit(2)


if __name__ == "__main__":
    main()
