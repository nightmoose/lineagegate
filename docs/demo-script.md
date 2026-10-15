# Demo script: one take, ~80 seconds

Dry-run against https://lineagegate.fly.dev on Oct 15, 2026 (headless Chrome, 1440×900):

- **Cold start:** the first request takes about 4 s while the Fly machine wakes up. After that, requests take about 0.6 s.
- **Answer times:** impact 6–15 s (the 15 s was an outlier), triage 7 s, memory 6–8 s, critical 4–5 s, unknown column 5–6 s.
- **While waiting:** the chat shows a live seconds counter. After 3 s it switches to "Querying FalkorDB and writing the answer". Narrate over the wait; never cut.

## Before recording (checklist)

1. **Wake the machine:** open https://lineagegate.fly.dev/health and wait for `"status":"ok"` with `"nodes":111`.
   If it was idle, the first load takes about 4 s.
2. **Open the app:** go to https://lineagegate.fly.dev/ in a **fresh** tab, so the chat is empty and the header has no `agent:` tag yet.
3. **Window:** browser window at **1440×900** (or full screen at 1080p), zoom **100%**, bookmarks bar hidden,
   no other tabs visible except the GitHub repo (https://github.com/nightmoose/lineagegate) to the right.
4. **Mouse:** after each click, move the mouse off the sample buttons so the hover outline doesn't linger.
5. **Optional warm-up:** if Grok seems slow today, ask one question in another tab first. Each tab has its own chat, so the recording tab stays clean.
6. Start the recording on the empty LineageGate page.

## Script

| Time | Click / type exactly | Say exactly |
|---|---|---|
| 0:00–0:08 | Nothing. Empty page. | "This is LineageGate: an AI agent that answers data-reliability questions from a lineage graph in FalkorDB, and shows the graph path behind every answer." |
| 0:08–0:26 | Click sample **"What breaks if stg_orders.amount changes from dollars to cents?"** While it loads, keep talking. When the answer lands, point at the 🔧 `impact_from_column` card, then the orange path in the graph. | "Someone wants to switch order amounts from dollars to cents. Grok picks the impact tool on its own, and FalkorDB walks column-level lineage. It breaks the orders-amount contract and hits five dashboards, including daily revenue. Here's the exact path." |
| 0:26–0:44 | Click sample **"Why did dbt_mart_customers_daily fail, and who should I page?"** When it lands, click the second path row (ends in **Job ingest_crm**). | "A job failed overnight. Triage walks upstream from the failed job: 37 duplicate customer IDs, the customer-grain contract, and Jules Chen is on call. Click any path to highlight it." |
| 0:44–1:00 | Click sample **"Have we seen an incident like this stg_orders.amount problem before?"** Point at the first path (ends in **Incident INC-0802**). | "Incidents are stored in the graph, so memory carries across sessions. It finds INC-0802, the same cents-versus-dollars bug from August, with its fix, linked through the contract it violated." |
| 1:00–1:12 | Click sample **"Which model is the most critical in the lineage?"** | "FalkorDB's built-in PageRank finds the hub, dim_customer, and the graph shows every dashboard that depends on it." |
| 1:12–1:22 | Click the input, type **`What breaks if stg_orders.amount_eur changes?`**, press **Enter**. Point at "⚠ No graph evidence". | "And when the graph has no evidence, it says so and suggests real columns. No guessing." |
| 1:22–1:30 | Click **Data model** tab for two seconds, then switch to the GitHub tab. | "Eleven node types, twelve relationships, all live from FalkorDB. Open source on GitHub, running on Fly.io." |

## If something goes wrong

- **An answer takes more than 10 s:** keep describing the previous evidence panel, and don't cut.
- **Error or `agent: offline router` in the header:** the LLM was unreachable, but answers still come from the same graph tools with
  the same paths. Keep going and mention "offline mode" once.
- **A path row isn't where the script says:** click whichever row ends in the named node.
