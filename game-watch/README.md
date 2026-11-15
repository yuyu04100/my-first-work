# Game Signal Watch (free, X-centered discovery)

A **no-payment** detector for game prototypes, visual game mechanics and indie-game virality. X is accessed through a **third-party free public proxy** (FxEmbed), never X's paid official API. Requests a twice-hourly schedule via **standard GitHub Actions on a public repository** (actual execution can be delayed or skipped by GitHub) and uses only no-key public endpoints. It never calls the paid X API.

## Data collection

- **X leads:** The free FxEmbed public API `/2/search` scans rotating queries in English/Japanese/other languages over 24-hour, 3-day and 7-day windows using latest/media/top feeds. Also tracks selected X profiles via FxEmbed RSS with a fallback host. FxEmbed supplies X post IDs and proxy-captured likes/reposts, **not X official API metrics**. View/impression numbers are never inferred. Search is partial, subject to free proxy availability and its changing coverage. Bing site-index RSS is retained as a degraded diagnostic because it has returned unrelated generic websites.
- **Bluesky:** public unauthenticated AppView search (`api.bsky.app`) with rotation of 18 English/Japanese queries, using both latest/top sorting. Reads public likes and reposts for platform-specific alerts, not X metrics. The service may rate-limit or reject requests; failures are logged.
- **Google News:** search RSS with viral-game and Japanese topic keywords; lead discovery only.
- **Mastodon:** two public hashtag RSS feeds; optional and may be blocked.
- **Hacker News:** Algolia public stories search; upvotes can trigger high-interest alerts.
- **Reddit:** indexed Reddit-related pages via public Google News RSS queries only. This is not a comprehensive subreddit feed. No paid Reddit API is used.

## Alert thresholds (initial heuristics)

An X search hit with verifiable FxEmbed proxy values qualifies at **3,000 likes AND 120 reposts**, or **750 reposts**, or strong recent growth. These are heuristic thresholds and not X view counts. A Bluesky post qualifies at **600 likes AND 100 reposts**, or **250 reposts**, or high growth (**300 likes/hour AND 35 reposts/hour** within six hours). A Hacker News story qualifies at 175 points. These are configurable thresholds in `monitor.py`, not proven predictors of future Roblox/Fortnite success. Each qualifying post opens **one GitHub Issue**, with its own original URL, actual platform counts, discovered time, and any X links found. The Issue is assigned to the repository owner when allowed by the API. GitHub notification delivery depends on your notification settings.

Each execution writes a timestamped, source-by-source audit trail to `data/state.json`, plus a readable `data/latest.md` of the last run and `data/health.json` with route-level acquisition health and the X coverage limitation. Failed sources are shown as **error**. Historical posts have only the platform's counts (never fabricated X views). Posts are deduplicated by canonical URL. History keeps 28 runs, 4 snapshots per post and at most 520 recent posts to keep `state.json` below GitHub's ~1 MiB normal file API inline-content limit. Closed and open issues provide longer-term notification deduplication.

## Quick links

- [Live scan report](data/latest.md)
- [Machine-readable data](data/state.json)
- [Acquisition health](data/health.json)
- [Scheduled job](../.github/workflows/game-signal-watch.yml)

## Operating and costs

The workflow executes only on the standard GitHub-hosted runner for a **public repository**, for which GitHub currently provides free execution minutes. It uses Python standard library and public, no-key endpoints; no cloud subscription or payment card is required. If the repository is made private, free monthly minutes are limited and other account usage can consume the quota. Do not move it to private without reviewing account billing.

GitHub scheduled runs may be delayed and may be disabled by GitHub after inactivity. The third-party FxEmbed search API may become unavailable or change behavior, and its reported metrics are not guaranteed to match the X interface. Source-specific errors are logged instead of being treated as zero activity. The source terms and availability can change. Update search terms to cover new genres and search variants. This cannot provide exhaustiveness or guaranteed coverage of all X posts. If absolutely complete X coverage and numeric X view spikes are required, this architecture cannot deliver that for free.

## Local tests

```bash
python -m unittest discover -s game-watch -p 'test_*.py' -v
python game-watch/monitor.py
```

The first command works offline. The second requires public internet; it will record source errors separately if some endpoints are unavailable. You can run it manually from the Actions tab using `Run workflow`.
