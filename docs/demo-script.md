# Demo script (one take, ~80 seconds)

**Setup before recording:** open https://lineagegate.fly.dev/ in a fresh tab and reload once so the
machine is awake (first wake takes a few seconds). Browser at ~1440×900, zoom 100%. Have
https://github.com/nightmoose/lineagegate open in a second tab. Each answer takes ~5–10 s; keep talking
over the wait.

| Time | Do exactly this | Say |
|---|---|---|
| 0:00–0:10 | Show the LineageGate page, empty chat. | "This is LineageGate, an agent that answers data-reliability questions from a lineage and contracts graph in FalkorDB. Every answer comes with the graph path behind it." |
| 0:10–0:28 | Click sample 1: **"What breaks if stg_orders.amount changes from dollars to cents?"** When it answers, point at the 🔧 `impact_from_column` card, then the highlighted graph. | "Grok picked the impact tool by itself. FalkorDB walks column-level lineage: five dashboards at risk, the orders_amount contract that says dollars not cents, and Finance Analytics to notify. Here's the exact path from the column to the revenue dashboard." |
| 0:28–0:46 | Click sample 2: **"Why did dbt_mart_customers_daily fail, and who should I page?"** Click the path row ending in `Job ingest_crm`. | "A job failed last night. Triage follows refresh, dependency and ingestion edges upstream: duplicate customer IDs, the dim_customer grain contract, and Jules Chen on call. Click any path to highlight it." |
| 0:46–1:02 | Click sample 3: **"Have we seen an incident like this stg_orders.amount problem before?"** Point at the `VIOLATED` path to INC-0802. | "This is the memory part. Incidents live in the graph, so a new session recalls INC-0802, the same cents-versus-dollars bug from August, with its fix. It's linked through the contract it violated." |
| 1:02–1:14 | Click sample 4: **"Which model is the most critical in the lineage?"** | "FalkorDB's built-in PageRank ranks dim_customer as the hub, and the evidence shows every dashboard that depends on it." |
| 1:14–1:22 | Type **"What breaks if stg_orders.amount_eur changes?"** and press Enter. | "And when the graph has no evidence, it says so and suggests close matches instead of guessing." |
| 1:22–1:30 | Switch to the GitHub tab. | "Track 01, with incident memory for Track 02. Open source, synthetic data, live on Fly.io. Powered by FalkorDB." |

**If an answer is slow:** keep narrating the previous evidence panel; don't cut.
**Fallback:** if the LLM is unavailable, answers still come back in `offline-router` mode with the same tools and paths.
