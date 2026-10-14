# LineageGate

**An explainable agent that answers "what breaks if this changes?" from a data lineage + contracts graph in [FalkorDB](https://www.falkordb.com/).**

Built for the WeMakeDevs **Graph Hacks: Context for AI Agents** hackathon, Track 01: Connected Data for AI Agents.

Data teams get asked the same questions over and over. What breaks if this column changes? Who owns this
dashboard? Why did this job fail, and have we seen it before? The answers live in *relationships*:
column → model → dashboard, asset → contract, asset → team → on-call person. LineageGate stores those
relationships in FalkorDB and gives an agent a few **Cypher-backed tools**. Every answer comes with the
**graph path** that justifies it. Without the graph, the agent has nothing to say.

> Inspired by common data-contract and lineage practices. Standalone demo on a fully synthetic
> dataset ("Acme Analytics"). No external services required.

## Example

```text
$ lineagegate ask --show-tools "What breaks if stg_orders.amount changes from dollars to cents?"
[mode: offline-router]
[tool] impact_from_column({"table": "stg_orders", "column": "amount"})
Changing `stg_orders.amount` (decimal(18,2), model stg_orders) reaches 13 downstream columns, 11 models and 5 dashboards.

Dashboards at risk: exec.kpi_overview, finance.cash_reconciliation, finance.revenue_daily, growth.marketing_roi, crm.customer_360
Contracts at risk: orders_amount v2.1 (amount is decimal(18,2) in USD dollars (not cents); not null; >= 0) ...
Owner teams to notify: Finance Analytics (10 assets); Customer Analytics (5 assets); Growth Analytics (2 assets)

Evidence (shortest graph path per dashboard):
  [6 hops] (Column stg_orders.amount) <-[:DEPENDS_ON]- (Column int_order_revenue.gross_revenue)
           <-[:DEPENDS_ON]- (Column fct_orders.order_amount) <-[:DEPENDS_ON]- (Column fct_revenue_daily.revenue)
           <-[:DEPENDS_ON]- (Column mart_finance_revenue.revenue_usd) <-[:HAS_COLUMN]- (Model mart_finance_revenue)
           <-[:DISPLAYS]- (Dashboard finance.revenue_daily)
  ...
```

## Quick start

Requirements: Docker, Python 3.11+.

```bash
git clone https://github.com/nightmoose/lineagegate && cd lineagegate
docker compose up -d                      # FalkorDB on :6379, Browser on http://localhost:3000
python3 -m venv .venv && .venv/bin/pip install -e '.[llm,dev]'
.venv/bin/lineagegate seed                # drop + load graph "acme" (111 nodes, 248 edges)
.venv/bin/lineagegate ask --show-tools "What breaks if stg_orders.amount changes?"
```

Other commands:

```bash
lineagegate impact stg_orders.amount            # pretty blast radius (add --json for raw output)
lineagegate owners stg_orders.amount            # owners (inherited from model), members, on-call
lineagegate path job:dbt_mart_customers_daily contract:customers_identity   # k shortest paths (algo.SPpaths)
lineagegate stats                               # counts by label / relationship type
pytest -q                                       # tool tests against a throwaway graph
```

### LLM mode

`lineagegate ask` runs a small tool-calling loop when an OpenAI-compatible key is configured
(`XAI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `LLM_BASE_URL` + `LLM_API_KEY`; see
`.env.example`). The model picks among the graph tools and is instructed to cite the returned paths.
With no key, a deterministic offline router chooses the tool from the question and renders a templated
answer, so the demo always runs end to end against FalkorDB.

## How it works

```
question ─► agent loop ─► tool (Cypher template) ─► FalkorDB graph "acme"
                │                                         │
                └──── answer + evidence paths ◄───────────┘
```

| Tool | What it does | Graph feature |
|---|---|---|
| `impact_from_column(table, column)` | Column-level downstream blast radius: models, dashboards, jobs, contracts, tests, owner teams, plus the shortest path to each impacted asset | variable-length `DEPENDS_ON*0..8` + fixed hops, path projection |
| `owners_for_node(node)` | Owning team/person (inherited through `HAS_COLUMN`), members, on-call | multi-hop `OWNED_BY` / `MEMBER_OF` |
| `paths_explain(source, target)` | k shortest connections between any two nodes, with edge directions | `algo.SPpaths` (fallback `shortestPath`) |

* Data model and scenarios: [`docs/data-model.md`](docs/data-model.md)
* Cypher used by each tool: [`docs/cypher.md`](docs/cypher.md)
* Demo script: [`docs/demo-script.md`](docs/demo-script.md)

## Repo layout

```
docker-compose.yml        FalkorDB (server + Browser)
data/                     synthetic seed as CSV (nodes_*.csv, edges_*.csv, incidents.json)
src/lineagegate/
  seed/generate.py        dataset spec -> data/*.csv  (lineagegate generate)
  seed/load.py            data/*.csv -> FalkorDB graph (lineagegate seed)
  graph/client.py         connection, node resolution, path rendering
  tools/lineage.py        Cypher-backed agent tools + tool specs
  agent/loop.py           LLM tool-calling loop + offline router
  cli.py                  command line
tests/                    tool tests against the seed
docs/                     data model, Cypher, demo script
```

## Status

- [x] Day 1: FalkorDB + seed + 3 tools + CLI impact answer with paths
- [ ] Failed-job triage, similar incidents (cross-session memory), critical assets (PageRank)
- [ ] HTTP API + minimal UI with evidence panel
- [ ] Hosted demo + video

## License

MIT. See [LICENSE](LICENSE). AI assistance is disclosed in [DISCLOSURE.md](DISCLOSURE.md).
