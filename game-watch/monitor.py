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
HEALTH = ROOT / "data" / "health.json"
UTC = dt.timezone.utc
NOW = dt.datetime.now(UTC)
USER_AGENT = "GameSignalWatch/1.0 (public feed monitor; no API keys)"
REQUEST_TIMEOUT = 12

# Queries rotate. Latest and top are both sampled to spot early and large spikes.
BSKY_TERMS = [
    "game prototype", "indie game", "I made a game", "game mechanic",
    "physics game", "gameplay prototype", "making a game", "game dev",
    "game concept", "horror game", "roblox game", "fortnite creative",
    "game demo", "indie dev", "physics sandbox", "viral indie game",
    "ゲーム開発", "ゲーム制作", "ゲーム試作", "自作ゲーム", "ゲーム アイデア", "新作ゲーム",
]
BING_TERMS = [
    'site:x.com "game prototype" video', 'site:x.com "indie game" "gameplay"',
    'site:twitter.com "I made a game"', '"x.com" "game mechanic" gameplay',
    'site:x.com "ゲーム開発" 動画', 'site:x.com "ゲーム作った"',
    'site:twitter.com "indie game" prototype', '"x.com" "new game" video',
]
REDDIT_INDEX_TERMS = [
    'site:reddit.com/r/IndieDev "game" when:7d',
    'site:reddit.com/r/indiegames "prototype" when:7d',
    'site:reddit.com/r/gamedev "gameplay" when:7d',
]
NEWS_TERMS = [
    '"indie game" "viral" when:3d', '"game prototype" "viral" when:7d',
    '"game dev" "twitter" when:7d', '"インディーゲーム" "話題" when:3d',
    '"new game" "X post" viral when:7d', '"Roblox" "viral" "game" when:3d',
]
# Free, public profile-media feeds documented by FxEmbed. These cover only
# selected X accounts, NOT a global keyword search of X.
FX_X_SEARCH_TERMS = ["game prototype", "ゲーム開発"]
FX_X_MEDIA_HANDLES = [
    "ID_XBOX", "Steam", "pandorioltd", "IGN",
    "Roblox", "FortniteGame", "UnrealEngine", "itchio",
]
MASTODON_FEEDS = [
    "https://mastodon.gamedev.place/tags/indiedev.rss",
    "https://mastodon.gamedev.place/tags/gamedev.rss",
]
KEYS = ["game", "play", "prototype", "indie", "devlog", "mechanic", "made", "physics", "roblox", "fortnite", "steam", "pixel", "horror", "ゲーム", "ロブロックス", "フォートナイト", "試作", "開発", "自作"]
EXCLUDE = ["job hiring", "game developer salary", "stock market", "game of thrones", "nba game", "football game"]
# Game industry politics and awards are NOT playable mechanics.
NEWS_ONLY = [
    "igf", "juror", "jury", "award judges", "judging committee", "union", "labor action",
    "声明", "審査員", "投票しない", "ゲーム開発カンファレンス", "ゲーム開発者の労働", "インディーゲーム大賞",
]
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
    """Exclude generic game-industry commentary; require actual gameplay evidence.

    Precision filter for automatic alerts, not a complete discovery filter.
    """
    text = (text or "").lower()
    if any(s in text for s in EXCLUDE):
        return False
    if any(s in text for s in NEWS_ONLY):
        return False
    game_words = ("game", "gameplay", "prototype", "gamedev", "indiedev", "roblox", "fortnite", "ゲーム", "ロブロックス", "フォートナイト")
    if not any(word in text for word in game_words):
        return False
    cues = [
        r"\b(?:i|we|our team|my studio)\s+(?:just\s+)?(?:made|built|developed|created|am making|are making|am working on)\b",
        r"\b(?:game prototype|gameplay prototype|gameplay reveal|gameplay trailer|first gameplay|game mechanic|game concept|game jam|devlog|physics game|playable demo)\b",
        r"\b(?:game where|game that lets|play my game|working on my game|working on our game|new game i made)\b",
        r"(?:自作ゲーム|ゲームの試作|試作ゲーム|ゲームを作|ゲームを開発|開発中のゲーム|ゲーム制作中|ゲーム開発中|ゲーム作りました|ゲームを制作|ゲームプレイ映像)",
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


def rss_item_count(content):
    """Distinguish valid but empty index search results from game leads."""
    return len(ET.fromstring(content).findall(".//item"))


def fx_x_search_signal(p):
    """A public FxEmbed proxy search result, NOT a direct X API response."""
    if not isinstance(p, dict) or p.get("type", "status") != "status":
        return None
    author = p.get("author") or {}
    handle = author.get("screen_name") or author.get("username") or ""
    raw_url = p.get("url") or (f"https://x.com/{handle}/status/{p.get('id')}" if handle and p.get("id") else "")
    url = normalized_url(raw_url)
    if not XPOST.fullmatch(url):
        return None
    text = p.get("text") or ""
    media = p.get("media") or {}
    signal = {"url": url, "title": text[:180].replace("\n", " "), "text": text[:600],
              "published": date_iso(p.get("created_at")), "source": "fx-x-search",
              "author": handle, "likes": int(p["likes"]) if isinstance(p.get("likes"), (int, float)) else None,
              "reposts": int(p["reposts"]) if isinstance(p.get("reposts"), (int, float)) else None,
              "replies": int(p["replies"]) if isinstance(p.get("replies"), (int, float)) else None,
              "video": bool(media.get("videos") or media.get("external")),
              "image": bool(media.get("photos")), "x_posts": [url],
              "counts_source": "FxEmbed public X proxy, not X official API"}
    return classify(signal)


def fx_x_media_signals(content, handle):
    """Convert a public, per-account FxEmbed RSS feed into X post leads.

    FxEmbed is a third-party relay; X engagement metrics are deliberately None.
    """
    posts = []
    for item in ET.fromstring(content).findall(".//item"):
        urls = (item.findtext("link", default="") or "") + " " + (item.findtext("guid", default="") or "")
        found = XPOST.findall(urls)
        if not found:
            found = re.findall(r"https?://(?:www\.)?(?:fxtwitter|fixupx)\.com/[^/\s<>\"']+/status/\d+", urls, re.I)
        if not found:
            continue
        original = normalized_url(found[0])
        original = re.sub(r"^https://(?:fxtwitter|fixupx)\.com/", "https://x.com/", original, flags=re.I)
        title = " ".join((item.findtext("title", default="") or "").split())
        raw = item.findtext("description", default="") or ""
        desc = re.sub(r"<[^>]+>", " ", raw)
        pub = date_iso(item.findtext("pubDate", default=""))
        # General entertainment feeds include movies and TV. Keep gaming
        # context only; specialized developer feeds remain broad.
        if handle.lower() in {"ign", "steam", "id_xbox"}:
            combined = (title + " " + desc).lower()
            if not any(word in combined for word in
                       ("game", "play", "indie", "steam", "demo", "trailer", "devlog",
                        "prototype", "roblox", "fortnite", "ゲーム", "switch", "xbox")):
                continue
        posts.append({"url": original, "title": title[:180], "text": desc[:600],
                      "published": pub, "source": "fx-x-media", "author": handle,
                      "likes": None, "reposts": None, "replies": None, "video": True,
                      "image": False, "x_posts": [original]})
    return posts


def rss_raw_examples(content, limit=3):
    items = ET.fromstring(content).findall(".//item")
    return [{"title": " ".join((i.findtext("title", default="") or "").split())[:130],
             "url": normalized_url(i.findtext("link", default=""))} for i in items[:limit]]


def indexed_x_candidates(content):
    """Keep actual X post URLs as unverified discovery leads.

    Bing dates are indexing dates, never claimed to be original X publication dates.
    No X engagement numbers can be inferred from the RSS results.
    """
    out, seen = [], set()
    for item in ET.fromstring(content).findall(".//item"):
        title = " ".join((item.findtext("title", default="") or "").split())
        link = item.findtext("link", default="") or ""
        desc = item.findtext("description", default="") or ""
        for found in XPOST.findall(link + " " + desc):
            status = normalized_url(found)
            if status not in seen:
                seen.add(status)
                out.append({"status_url": status, "title": title[:130], "indexed_source": normalized_url(link)})
    return out


def collect():
    results = []
    stats = []
    h = NOW.hour
    # Always sample BOTH English and Japanese, even if some scheduled runs are skipped.
    en_count = len(BSKY_TERMS) - 6
    indices = sorted({(h * 5 + i) % en_count for i in range(5)} | {en_count + ((h + i) % 6) for i in range(2)})
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
    # Pilot FxEmbed public X SEARCH: test code/availability independently of
    # the broken Bing search index. X metrics are proxied, not official.
    for term in FX_X_SEARCH_TERMS:
        url = "https://api.fxtwitter.com/2/search?" + urllib.parse.urlencode({"q": term, "feed": "latest", "count": 30})
        try:
            data = json.loads(request(url))
            if data.get("code") != 200:
                raise ValueError("FxEmbed search code=" + str(data.get("code")))
            raw = data.get("results") or []
            posts = [fx_x_search_signal(p) for p in raw]
            posts = [p for p in posts if p]
            results.extend(posts)
            stats.append({"source": "fx-x-search", "query": term, "status": "ok" if posts else "limited",
                          "count": len(posts), "raw_count": len(raw),
                          "samples": [p.get("text", "")[:75] for p in raw[:2] if isinstance(p, dict)]})
        except Exception as e:
            stats.append({"source": "fx-x-search", "query": term, "status": "error", "error": str(e)[:180]})
    # X profile media feeds are free but limited to watched accounts. No view
    # counts and no claim of comprehensive keyword coverage.
    for handle in FX_X_MEDIA_HANDLES:
        # Both hosts are documented by FxEmbed. One may have intermittent
        # upstream 404s while the other succeeds.
        payload, used_host, failures = None, None, []
        for host in ("fxtwitter.com", "fixupx.com"):
            url = f"https://{host}/{handle}/media.xml?count=15"
            try:
                payload = request(url)
                used_host = host
                break
            except Exception as e:
                failures.append(f"{host}: {str(e)[:70]}")
        if payload is None:
            stats.append({"source": "fx-x-media", "query": handle, "status": "error", "error": "; ".join(failures)[:200]})
            continue
        try:
            posts = fx_x_media_signals(payload, handle)
            results.extend(posts)
            stats.append({"source": "fx-x-media", "query": handle, "status": "ok" if posts else "limited",
                          "count": len(posts), "raw_count": rss_item_count(payload), "host": used_host})
        except Exception as e:
            stats.append({"source": "fx-x-media", "query": handle, "status": "error", "error": str(e)[:140]})
    # Search engine feeds have uneven indexing of X; this is discovery, NOT all-X collection.
    for i in range(4):
        term = BING_TERMS[(h * 2 + i) % len(BING_TERMS)]
        url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": term, "format": "rss"})
        try:
            payload = request(url)
            raw_count = rss_item_count(payload)
            candidates = indexed_x_candidates(payload)
            posts = parse_rss(payload, "bing-x-index")
            results.extend(posts)
            status = "ok" if posts else "candidate_only" if candidates else "limited"
            stats.append({"source": "bing-x-index", "query": term, "status": status, "count": len(posts), "raw_count": raw_count, "x_post_candidates": len(candidates), "examples": candidates[:5], "raw_examples": rss_raw_examples(payload, 2)})
        except Exception as e:
            stats.append({"source": "bing-x-index", "query": term, "status": "error", "error": str(e)[:140]})
    for i in range(3):
        term = NEWS_TERMS[(h + i) % len(NEWS_TERMS)]
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": term, "hl": "en-US", "gl": "US", "ceid": "US:en"})
        try:
            payload = request(url)
            posts = parse_rss(payload, "google-news")
            results.extend(posts)
            stats.append({"source": "google-news", "query": term, "status": "ok" if posts else "limited", "count": len(posts), "raw_count": rss_item_count(payload)})
        except Exception as e:
            stats.append({"source": "google-news", "query": term, "status": "error", "error": str(e)[:140]})
    # Reddit's old direct RSS is unavailable: use searchable public article indexes.
    for i in range(2):
        term = REDDIT_INDEX_TERMS[(h + i) % len(REDDIT_INDEX_TERMS)]
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": term, "hl": "en-US", "gl": "US", "ceid": "US:en"})
        try:
            payload = request(url)
            posts = parse_rss(payload, "reddit-index")
            results.extend(posts)
            stats.append({"source": "reddit-index", "query": term, "status": "ok" if posts else "limited", "count": len(posts), "raw_count": rss_item_count(payload)})
        except Exception as e:
            stats.append({"source": "reddit-index", "query": term, "status": "error", "error": str(e)[:140]})
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
        fresh["history"] = ((old or {}).get("history", []) + [{"at": iso(), "likes": p.get("likes"), "reposts": p.get("reposts")}])[-4:]
        fresh["alerted"] = (old or {}).get("alerted", False)
        if criterion and not fresh["alerted"]:
            fresh["alerted"] = True
            fresh["alert_reason"] = criterion
            alerts.append(fresh)
        posts[key] = fresh
    # Keep state below GitHub Contents API's ~1 MiB inline content limit.
    # Long-term alert dedup also checks existing GitHub Issues.
    if len(posts) > 650:
        kept = sorted(posts.items(), key=lambda kv: kv[1].get("last_seen", ""), reverse=True)[:650]
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
    x_media = sorted((p for p in state["posts"].values() if p.get("source") == "fx-x-media" and relevant(p.get("title", "") + " " + p.get("text", ""))),
                     key=lambda x: x.get("published") or "", reverse=True)[:20]
    lines += ["", "## X media leads from watched accounts (no X metrics)", "",
              "| X post URL | Account | Published from feed | Post title |", "|---|---|---|---|"]
    for p in x_media:
        lines.append(f"| {p['url']} | {p.get('author','')} | {p.get('published') or 'unknown'} | {p.get('title','').replace('|','/')[:110]} |")
    lines += ["", "## Search route status", "", "| Source | Query | Status | Qualified | Raw RSS items |", "|---|---|---|---:|---:|"]
    for s in run["routes"]:
        lines.append(f"| {s['source']} | {s['query'].replace('|','/')} | {s['status']} | {s.get('count', '—')} | {s.get('raw_count', '—')} |")
    lines += ["", "## Raw search results from X discovery routes (unverified)", "", "Raw search results help diagnose search providers returning unrelated pages.", "", "| Query | Result title | Result URL |", "|---|---|---|"]
    for r in run["routes"]:
        if r["source"] == "bing-x-index":
            for item in r.get("raw_examples", []):
                lines.append(f"| {r['query'].replace('|','/')} | {item['title'].replace('|','/')} | {item['url']} |")
    x_indexed = {}
    for r in run["routes"]:
        for c in r.get("examples", []):
            x_indexed[c["status_url"]] = c
    lines += ["", "## X-indexed status links (unverified candidates)", "", "Links below are indexed leads, not verified games or X engagement metrics.", "", "| X status URL | Search title |", "|---|---|"]
    for c in list(x_indexed.values())[:12]:
        lines.append(f"| {c['status_url']} | {c['title'].replace('|','/')} |")
    if not x_indexed:
        lines.append("| — | No actual X status URL extracted; degraded route rather than a clean scan |")
    lines += ["", "**Limited** means the source responded but yielded no qualifying game post. This is NOT evidence that X had no viral games.", "", "X metadata is **not** available without X access. A failure or missing indexed post is **not** a zero-viral claim. Reddit RSS was retired 2026-11-13 and is deliberately excluded. All sources are best effort; absence of a hit is not evidence that no viral game exists.", ""]
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
    state["runs"] = state["runs"][-28:]
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    x_routes = [s for s in stats if s["source"] == "bing-x-index"]
    prior = state["runs"][-2]["at"] if len(state["runs"]) > 1 else None
    gap_hours = None
    if prior:
        try:
            gap_hours = round((NOW - dt.datetime.fromisoformat(prior.replace("Z", "+00:00"))).total_seconds() / 3600, 2)
        except (ValueError, TypeError):
            pass
    fx_routes = [s for s in stats if s["source"] == "fx-x-media"]
    x_feed_count = sum(s.get("count", 0) for s in fx_routes)
    health = {"at": iso(), "status": "partial_x_feeds" if x_feed_count > 0 else "degraded_x",
              "x_index": {"attempts": len(x_routes), "hits": sum(s.get("count", 0) for s in x_routes),
                          "raw_hits": sum(s.get("raw_count", 0) for s in x_routes),
                          "errors": sum(s["status"] == "error" for s in x_routes),
                          "indexed_candidate_status_urls": sum(s.get("x_post_candidates", 0) for s in x_routes),
                          "note": "No X metrics or complete X search API; zero indexed hits does not prove no virality"},
              "source_attempts": len(stats), "source_ok": run["source_ok"], "source_errors": sum(s["status"] == "error" for s in stats),
              "unique_results": count, "alert_attempts": len(sent), "hours_since_previous_run": gap_hours,
              "state_bytes": STATE.stat().st_size}
    x_search_routes = [s for s in stats if s["source"] == "fx-x-search"]
    health["fx_x_search"] = {"attempts": len(x_search_routes),
                             "qualified_posts": sum(s.get("count", 0) for s in x_search_routes),
                             "raw_posts": sum(s.get("raw_count", 0) for s in x_search_routes),
                             "errors": sum(s["status"] == "error" for s in x_search_routes),
                             "note": "Free FxEmbed proxy search pilot, not an official X API contract"}
    if health["fx_x_search"]["qualified_posts"]:
        health["status"] = "partial_x_search"
    health["fx_x_media"] = {"accounts_attempted": len(fx_routes), "posts": x_feed_count,
                            "errors": sum(s["status"] == "error" for s in fx_routes),
                            "limitation": "Only curated profile media feeds, not search across all X posts"}
    HEALTH.write_text(json.dumps(health, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report(state, run, alerts)
    print(json.dumps({"at": run["at"], "ok": run["source_ok"], "attempted": run["source_attempts"], "unique": count, "alerts": sent}, ensure_ascii=False))
    if run["source_ok"] == 0:
        sys.exit(2)


if __name__ == "__main__":
    main()
