# devmetrics

Development metrics for every project on this machine — collected passively,
never with tokens.

All LLM calls route through omniroute, which already records every request
(model, token categories, price, success) in `request_cost_ledger`. devmetrics
joins that with harness session logs and a one-tap end-of-session label to
answer: what did this project cost, which model earns its price, where is the
rework — and it renders the story for a retro.

Design: [docs/specs/2026-10-25-devmetrics.md](docs/specs/2026-10-25-devmetrics.md).
 Construction starts there: `devmetrics sync` first, CLI after.
