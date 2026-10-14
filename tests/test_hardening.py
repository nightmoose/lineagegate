"""Edge cases: unknown names, ambiguity, empty graph, no-path, LLM abstention."""
import os

import pytest

from lineagegate import config
from lineagegate.graph.client import db
from lineagegate.tools.lineage import impact_from_column, owners_for_node, paths_explain
from lineagegate.tools.ops import critical_assets, similar_incidents, triage_failed_job


def test_unknown_column_typo_suggests_best_match_first():
    r = impact_from_column("stg_ordr.amount")
    assert not r["found"] and r["did_you_mean"][0] == "stg_orders.amount"


def test_known_table_unknown_column():
    r = impact_from_column("stg_orders", "amt")
    assert not r["found"]
    assert "exists but has no column 'amt'" in r["error"]
    assert r["did_you_mean"][0] == "stg_orders.amount"


def test_totally_unknown_column_has_no_fake_suggestions():
    r = impact_from_column("foo.bar")
    assert not r["found"] and r["did_you_mean"] == []


def test_unknown_node_suggests_via_graph():
    r = owners_for_node("dim_custmer")
    assert not r["found"] and r["candidates"][0] == "model:dim_customer"


def test_ambiguous_reference_lists_candidates():
    r = owners_for_node("customer_id")
    assert not r["found"] and "Ambiguous" in r["error"]
    assert {"column:stg_customers.customer_id", "column:mart_customers.customer_id"} <= set(r["candidates"])


def test_unknown_job_suggests():
    r = triage_failed_job("dbt_mart_custmers")
    assert not r["found"] and r["did_you_mean"] == ["job:dbt_mart_customers_daily"]


def test_no_path_reports_not_found():
    # People only connect through ownership edges, which are excluded by default.
    r = paths_explain("person:priya.raman", "dashboard:cx.support_health")
    assert not r["found"]


def test_critical_assets_returns_evidence_paths():
    r = critical_assets("pagerank", 3)
    paths = r["top_asset_paths"]
    assert paths and all(p["text"].endswith("(Model dim_customer)") for p in paths)
    assert all(p["text"].startswith("(Dashboard ") for p in paths)


@pytest.fixture
def empty_graph():
    name = config.GRAPH_NAME
    config.GRAPH_NAME = "acme_empty_test"
    yield
    if "acme_empty_test" in db().list_graphs():
        db().select_graph("acme_empty_test").delete()
    config.GRAPH_NAME = name


def test_empty_graph_is_reported(empty_graph):
    for r in (impact_from_column("stg_orders.amount"), owners_for_node("x"), triage_failed_job(),
              similar_incidents(text="x"), critical_assets(), paths_explain("a", "b")):
        assert r == {"found": False, "error": "The lineage graph is empty. Run `lineagegate seed` first.",
                     "empty_graph": True}


@pytest.mark.skipif(not (os.getenv("XAI_API_KEY") and os.getenv("RUN_LLM_TESTS")),
                    reason="live LLM test; set XAI_API_KEY and RUN_LLM_TESTS=1")
def test_llm_abstains_on_unknown_column():
    from lineagegate.agent.loop import ask
    res = ask("What breaks if stg_orders.amount_eur changes to a string?")
    assert res.mode.startswith("llm:")
    assert res.tool_calls and all(not c["result"].get("found", True) for c in res.tool_calls
                                  if c["tool"] == "impact_from_column")
    assert "-[:" not in res.answer  # no fabricated path
