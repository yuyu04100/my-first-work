# Game Signal Watch (free, X-centered discovery)

A **no-payment** detector for game prototypes, visual game mechanics and indie-game virality. Runs twice an hour with **standard GitHub Actions on a public repository** and uses only no-key public endpoints. It never calls the paid X API.

## Data collection

- **X leads:** indexed `x.com/status/...` posts from Bing RSS-style search and Google News queries. X search indexing is incomplete, and X view/like/repost counts are unavailable. Do not interpret an empty result as "no new game went viral on X."
- **Bluesky:** public unauthenticated AppView search (`api.bsky.app`) with rotation of 18 English/Japanese queries, using both latest/top sorting. Reads public likes and reposts for platform-specific alerts, not X metrics. The service may rate-limit or reject requests; failures are logged.
- **Google News:** search RSS with viral-game and Japanese topic keywords; lead discovery only.
- **Mastodon:** two public hashtag RSS feeds; optional and may be blocked.
- **Hacker News:** Algolia public stories search; upvotes can trigger high-interest alerts.
- **Reddit:** excluded, because Reddit shut down its own RSS service on 2026-11-13; no paid Reddit API is used.

## Alert thresholds (initial heuristics)

A Bluesky post qualifies at **600 likes AND 100 reposts**, or **250 reposts**, or high growth (**300 likes/hour AND 35 reposts/hour** within six hours). A Hacker News story qualifies at 175 points. These are configurable thresholds in `monitor.py`, not proven predictors of future Roblox/Fortnite success. Each qualifying post opens **one GitHub Issue**, with its own original URL, actual platform counts, discovered time, and any X links found. The Issue is assigned to the repository owner when allowed by the API. GitHub notification delivery depends on your notification settings.

Each execution writes a timestamped, source-by-source audit trail to `data/state.json`, plus a readable `data/latest.md` of the last run. Failed sources are shown as **error**. Historical posts have only the platform's counts (never fabricated X views). Posts are deduplicated by canonical URL. History keeps 180 runs, 12 snapshots per post and at most 3,500 posts.

## Quick links

- [Live scan report](data/latest.md)
- [Machine-readable data](data/state.json)
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
