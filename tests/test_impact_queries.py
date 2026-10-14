"""Cypher tool tests against the synthetic seed (no LLM involved)."""
from lineagegate.agent.loop import route
from lineagegate.tools.lineage import impact_from_column, owners_for_node, paths_explain


def test_seed_counts(seeded_graph):
    assert 80 <= seeded_graph["node_count"] <= 120
    assert 150 <= seeded_graph["edge_count"] <= 250
    assert set(seeded_graph["nodes_by_label"]) == {
        "Source", "Table", "Column", "Model", "Contract", "Test", "Job", "Dashboard", "Person", "Team", "Incident"}


def test_impact_stg_orders_amount_reaches_revenue_dashboard():
    r = impact_from_column("stg_orders", "amount")
    assert r["found"]
    dashes = {d["name"] for d in r["impacted"]["dashboards"]}
    assert "finance.revenue_daily" in dashes
    assert "cx.support_health" not in dashes  # does not use amount
    path = next(p for p in r["paths"] if p["target"] == "dashboard:finance.revenue_daily")
    assert path["nodes"][0]["id"] == "column:stg_orders.amount"
    assert path["nodes"][-1]["id"] == "dashboard:finance.revenue_daily"
    assert "model:mart_finance_revenue" in [n["id"] for n in path["nodes"]]
    assert {c["name"] for c in r["impacted"]["contracts"]} >= {"orders_amount"}
    assert r["owners"][0]["team"] == "Finance Analytics"


def test_impact_unknown_column_suggests():
    r = impact_from_column("stg_orders.amt")
    assert not r["found"]
    assert "stg_orders.amount" in r["did_you_mean"]


def test_owners_inherited_for_column():
    r = owners_for_node("stg_orders.amount")
    assert r["found"]
    names = {o["name"] for o in r["owners"]}
    assert "Finance Analytics" in names
    assert all(o["inherited"] == 1 for o in r["owners"])
    assert "Priya Raman" in r["on_call"]


def test_paths_failed_job_to_violated_contract():
    r = paths_explain("job:dbt_mart_customers_daily", "contract:customers_identity")
    assert r["found"]
    ids = [n["id"] for n in r["paths"][0]["nodes"]]
    assert ids[0] == "job:dbt_mart_customers_daily" and ids[-1] == "contract:customers_identity"


def test_dim_customer_is_hub():
    from lineagegate.graph.client import ro
    rows = ro("MATCH (m:Model)<-[:DEPENDS_ON]-(d:Model) RETURN m.name, count(d) AS c ORDER BY c DESC LIMIT 1")
    assert rows[0][0] == "dim_customer"


def test_offline_router():
    assert route("What breaks if stg_orders.amount changes?") == (
        "impact_from_column", {"table": "stg_orders", "column": "amount"})
    assert route("who owns model:dim_customer")[0] == "owners_for_node"
