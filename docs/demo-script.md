# Demo script (60–90s) — draft

| Time | Visual | Voice |
|---|---|---|
| 0–10s | Title: LineageGate + FalkorDB | "An agent that reasons over data lineage and contracts in FalkorDB." |
| 10–25s | `lineagegate ask "What breaks if stg_orders.amount changes?"` | Lists models, dashboards, contracts, owners; shows the path to `finance.revenue_daily`. |
| 25–45s | Triage: `dbt_mart_customers_daily` failed (Day 2 tool) | Finds upstream contract violation + owner; shows path. |
| 45–65s | New session: "Seen this before?" (Day 2 memory) | Recalls INC-0916 / INC-0917 via `RELATED_TO`. |
| 65–80s | FalkorDB Browser (localhost:3000) + `algo.SPpaths` | "Graph queries are the agent's tools, not a sidebar." |
| 80–90s | Repo + run command | "Track 01. Public repo, one-command Docker." |
