# Game Signal Watch (free, X-centered discovery)

A **no-payment** detector for game prototypes, visual game mechanics and indie-game virality. Requests a twice-hourly schedule via **standard GitHub Actions on a public repository** (actual execution can be delayed or skipped by GitHub) and uses only no-key public endpoints. It never calls the paid X API.

## Data collection

- **X leads:** Free FxEmbed X profile-media RSS feeds for a small curated list of accounts, plus Bing-indexed URLs where they exist. These are incomplete and may fail. In production, Bing `site:x.com` sometimes returns generic websites rather than X status posts; this is labelled **limited**, not success. X view/like/repost counts remain unavailable.
- **Bluesky:** public unauthenticated AppView search (`api.bsky.app`) with rotation of 18 English/Japanese queries, using both latest/top sorting. Reads public likes and reposts for platform-specific alerts, not X metrics. The service may rate-limit or reject requests; failures are logged.
- **Google News:** search RSS with viral-game and Japanese topic keywords; lead discovery only.
- **Mastodon:** two public hashtag RSS feeds; optional and may be blocked.
- **Hacker News:** Algolia public stories search; upvotes can trigger high-interest alerts.
- **Reddit:** indexed Reddit-related pages via public Google News RSS queries only. This is not a comprehensive subreddit feed. No paid Reddit API is used.

## Alert thresholds (initial heuristics)

A Bluesky post qualifies at **600 likes AND 100 reposts**, or **250 reposts**, or high growth (**300 likes/hour AND 35 reposts/hour** within six hours). A Hacker News story qualifies at 175 points. These are configurable thresholds in `monitor.py`, not proven predictors of future Roblox/Fortnite success. Each qualifying post opens **one GitHub Issue**, with its own original URL, actual platform counts, discovered time, and any X links found. The Issue is assigned to the repository owner when allowed by the API. GitHub notification delivery depends on your notification settings.

Each execution writes a timestamped, source-by-source audit trail to `data/state.json`, plus a readable `data/latest.md` of the last run and `data/health.json` with route-level acquisition health and the X coverage limitation. Failed sources are shown as **error**. Historical posts have only the platform's counts (never fabricated X views). Posts are deduplicated by canonical URL. History keeps 28 runs, 4 snapshots per post and at most 650 recent posts to keep `state.json` below GitHub's ~1 MiB normal file API inline-content limit. Closed and open issues provide longer-term notification deduplication.

## Quick links

- [Live scan report](data/latest.md)
- [Machine-readable data](data/state.json)
- [Acquisition health](data/health.json)
- [Scheduled job](../.github/workflows/game-signal-watch.yml)

## Operating and costs

The workflow executes only on the standard GitHub-hosted runner for a **public repository**, for which GitHub currently provides free execution minutes. It uses Python standard library and public, no-key endpoints; no cloud subscription or payment card is required. If the repository is made private, free monthly minutes are limited and other account usage can consume the quota. Do not move it to private without reviewing account billing.

GitHub scheduled runs may be delayed and may be disabled by GitHub after inactivity. The source terms and availability can change. Update search terms to cover new genres and search variants. This cannot provide exhaustiveness or guaranteed coverage of all X posts. If absolutely complete X coverage and numeric X view spikes are required, this architecture cannot deliver that for free.

## Local tests

```bash
python -m unittest discover -s game-watch -p 'test_*.py' -v
python game-watch/monitor.py
```

The first command works offline. The second requires public internet; it will record source errors separately if some endpoints are unavailable. You can run it manually from the Actions tab using `Run workflow`.
