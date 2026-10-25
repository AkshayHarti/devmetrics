# devmetrics

Development metrics for every project on this machine — collected passively,
never with tokens.

All LLM calls route through omniroute, which already records every request
(model, token categories, price, success) in `request_cost_ledger`. devmetrics
joins that with harness session logs and a one-tap end-of-session label to
answer: what did this project cost, which model earns its price, where is the
rework — and it renders the story for a retro.

Design: [docs/specs/2026-10-25-devmetrics.md](docs/specs/2026-10-25-devmetrics.md).

## Implemented (v1)

```bash
uv sync && uv run devmetrics sync                 # ledger + attribution
uv run devmetrics cost [--since 3d|YYYY-MM-DD]    # money view, by project
uv run devmetrics models                          # volume, success rate, $ per model
uv run devmetrics sessions [--since ...]          # session table with labels
uv run devmetrics label            # evidence-based proposal, one tap confirm
uv run devmetrics label latest --yes        # accept the proposal
uv run devmetrics label latest rework       # override (wins over evidence)
```

Data sources: omniroute's `request_cost_ledger` (read-only), OpenCode's
session database for project attribution (±120 s activity window, exactly-one
project rule — otherwise the row stays `unattributed` rather than guessed).
Warehouse lives at `~/.local/share/devmetrics/ledger.sqlite`.

Construction continues from the spec: `report` (retro renderer, family 4) and
`forecast` (family 5) next, then the web dashboard on the same SQLite.
