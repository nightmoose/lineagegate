"""Deterministic tests for Day-2 Cypher tools against the seed graph."""
from lineagegate.agent.loop import route
from lineagegate.tools.ops import critical_assets, record_incident, similar_incidents, triage_failed_job


def test_triage_defaults_to_failed_job():
    r = triage_failed_job()
    assert r["found"] and r["job"]["id"] == "job:dbt_mart_customers_daily"
    assert r["job"]["status"] == "failed"


def test_triage_mart_customers_evidence():
    r = triage_failed_job("dbt_mart_customers_daily")
    assert [t["id"] for t in r["failing_tests"]] == ["test:unique_mart_customers_customer_id"]
    assert "contract:dim_customer_grain" in {c["id"] for c in r["contracts"]}
    assert any(u["id"] == "model:dim_customer" and u["hops"] == 1 for u in r["upstream_models"])
    crm = next(u for u in r["upstream_ingestion_jobs"] if u["id"] == "job:ingest_crm")
    assert "raw.crm_customers" in crm["path"] and "dim_customer" in crm["path"]
    assert "dashboard:crm.customer_360" in r["downstream_dashboards"]
    assert r["owners"][0]["team"] == "Customer Analytics"
    assert [i["id"] for i in r["similar_incidents"][:2]] == ["incident:INC-0917", "incident:INC-0916"]


def test_triage_unknown_job():
    r = triage_failed_job("nope_job")
    assert not r["found"] and r["failed_jobs"] == ["job:dbt_mart_customers_daily"]


def test_similar_incidents_graph_path_for_amount():
    r = similar_incidents(node="stg_orders.amount")
    top = r["incidents"][0]
    assert top["id"] == "incident:INC-0802"
    assert "VIOLATED" in top["graph_path"] and "orders_amount" in top["graph_path"]


def test_similar_incidents_keyword_only():
    r = similar_incidents(text="duplicate customer_id after backfill")
    assert r["incidents"][0]["id"] == "incident:INC-0916"


def test_critical_assets_pagerank_and_betweenness():
    pr = critical_assets("pagerank", 3)
    assert pr["assets"][0]["id"] == "model:dim_customer"
    assert pr["assets"][0]["owner_team"] == "Customer Analytics"
    assert pr["assets"][0]["dashboards"] >= 5
    bt = critical_assets("betweenness", 3)
    assert [a["id"] for a in bt["assets"]] == ["model:dim_customer", "model:fct_orders", "model:int_order_revenue"]


def test_record_incident_persists_and_is_recalled():
    rec = record_incident("mart_customers duplicate customer_id again", "CRM backfill duplicates",
                          "SEV2", job="dbt_mart_customers_daily", contracts=["dim_customer_grain"],
                          key="INC-TEST1")
    assert rec["id"] == "incident:INC-TEST1"
    assert "TRIGGERED_BY job:dbt_mart_customers_daily" in rec["links"]
    assert any(l.startswith("RELATED_TO incident:INC-091") for l in rec["links"])
    # a fresh lookup (new "session") finds it via the graph
    r = similar_incidents(node="contract:dim_customer_grain", k=10)
    assert "incident:INC-TEST1" in {i["id"] for i in r["incidents"]}


def test_offline_routes_day2():
    assert route("Why did dbt_mart_customers_daily fail?") == ("triage_failed_job", {"job": "dbt_mart_customers_daily"})
    assert route("Which models are most critical?")[0] == "critical_assets"
    assert route("Any similar incidents for stg_orders.amount?") == ("similar_incidents", {"node": "stg_orders.amount"})
