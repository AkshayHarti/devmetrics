# devmetrics — development metrics for every project

Status: approved through brainstorming, 2026-10-25. Owner: Akshay Harti.

## Why

Agent development burns tokens every day, and none of it is visible: what a
project cost so far, what V1 cost, which model earns its price, where the
rework is. devmetrics is a passive collector + query layer that answers those
questions from data that already exists. It is generic — any project on this
machine gets the same numbers — and it never costs tokens to collect.

## Metric families (all approved)

1. **Cost control** — total tokens and $ over a project's life, cost of V1,
   per day/week/model. "What did this project cost, and is it still moving?"
2. **Model choice** — most-used and most-expensive models, failure and
   fallback rates, and (after labels) cost-per-good-outcome per model.
3. **Process quality** — wasted-work ratio (tokens after the first "it
   works" claim), failure taxonomy (tool errors vs. test failures vs. user
   corrections), PR round-trips (later), user-turn density (later).
4. **Storytelling** — a dated retro per project: tokens, cost, sessions,
   models, labels; pasteable into README, blog, brain.
5. **Forecasting** — rolling averages per feature type feed "a feature like
   this should cost about N".

## Sources of truth (decided)

- **`~/.omniroute/storage.sqlite`** — `request_cost_ledger` (one row per
  request: model, input/output/cache-read/cache-write/reasoning tokens,
  unit prices, `amount_usd`, success, timestamp) plus
  `daily_usage_summary`/`hourly_usage_summary`. Because every LLM call on
  this machine routes through omniroute, this is the single choke point and
  works retroactively for the whole project.
- **`~/.omniroute/call_logs/<date>/*.json`** — per-request detail:
  requested vs. routed model (fallbacks), duration, api key name.
- **Harness session logs** (OpenCode et al.) — joined by timestamp and model
  to give each request a project (session cwd) and session title.
- **End-of-session taste labels** — one tap, good|meh|rework, recorded by the
  user; the quality dimension that harnesses cannot know.
- **Git/PR metadata** — later, for round-trip counts.

## Attribution (decided)

- Project = session working directory via a timestamp-join with harness
  session logs (no per-project keys, no manual keys to maintain).
- V1 / "this stretch of work" = session-title markers: a lightweight
  convention on session names, not a separate bookkeeping tool.
- Precision is ~a minute; good enough for every metric above.

## Interface (decided)

- A `devmetrics` CLI on top of its own SQLite warehouse:
  - `devmetrics sync` — refresh the warehouse from the sources above.
  - `devmetrics cost [--project P] [--since WHEN]` — the money view.
  - `devmetrics models` — volume, cost, failures, fallbacks per model.
  - `devmetrics sessions [--project P]` — session table with tokens + labels.
  - `devmetrics label <session|latest> good|meh|rework` — the one manual act.
  - `devmetrics report <project>` — the retrospective (markdown, family 4).
  - `devmetrics forecast <project>` — per-feature-type estimates (family 5).
- Everything queries the warehouse; the raw omniroute DB is read-only, never
  written. No tokens, no network, no keys for collection.

## Later (known next steps)

- Web dashboard (same SQLite; Extras-style split like ntfsmnt).
- PR round-trip and review-cycle metrics once a project has PR volume.
- Per-project default pricing overrides for models omniroute bills at 0.

## Non-goals

- Real-time harness hooks (add later only if sync latency hurts).
- Judging sessions by merges: label 3 was chosen deliberately; "merged PR"
  is not the marker of a successful session (research/Q&A sessions are
  legitimate work).
- Any UI before the CLI is credible.
