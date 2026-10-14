"""Generate the synthetic "Acme Analytics" lineage + contracts dataset.

Everything here is fictional: company, people, systems, and incidents.
Output is deterministic CSV/JSON under ``data/`` so the graph can be
re-created from scratch with ``lineagegate seed``.

Node ids are prefixed by kind (``column:stg_orders.amount``,
``model:stg_orders``, ``dashboard:finance.revenue_daily`` ...) so they are
unique across labels and readable in paths.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[3] / "data"

# --------------------------------------------------------------------------
# Org: teams + people (fictional, @acme.example)
# --------------------------------------------------------------------------
TEAMS = {
    "finance_analytics": "Finance Analytics",
    "data_platform": "Data Platform",
    "customer_analytics": "Customer Analytics",
    "growth_analytics": "Growth Analytics",
}

PEOPLE = [
    # handle, display name, team, role, on_call
    ("priya.raman", "Priya Raman", "finance_analytics", "Analytics Engineering Lead", True),
    ("marcus.lee", "Marcus Lee", "finance_analytics", "Analytics Engineer", False),
    ("dana.okafor", "Dana Okafor", "data_platform", "Data Platform Lead", False),
    ("sam.rivera", "Sam Rivera", "data_platform", "Data Engineer", True),
    ("jules.chen", "Jules Chen", "customer_analytics", "Customer Analytics Lead", True),
    ("ana.petrova", "Ana Petrova", "customer_analytics", "Analytics Engineer", False),
    ("tom.becker", "Tom Becker", "growth_analytics", "Growth Analytics Lead", True),
    ("lena.ortiz", "Lena Ortiz", "growth_analytics", "Data Analyst", False),
]

# --------------------------------------------------------------------------
# Sources, raw tables, ingestion jobs
# --------------------------------------------------------------------------
SOURCES = {
    "shopify": ("Shopify storefront", "saas"),
    "stripe": ("Stripe payments", "saas"),
    "hubspot": ("HubSpot CRM", "saas"),
    "zendesk": ("Zendesk support", "saas"),
    "google_ads": ("Google Ads", "saas"),
}

# raw table -> (source, columns {name: type})
RAW_TABLES = {
    "raw.shopify_orders": ("shopify", {"order_id": "string", "customer_id": "string", "total_price_cents": "integer"}),
    "raw.shopify_order_items": ("shopify", {"discount_cents": "integer"}),
    "raw.stripe_payments": ("stripe", {"amount_cents": "integer"}),
    "raw.crm_customers": ("hubspot", {"customer_id": "string", "segment": "string"}),
    "raw.zendesk_tickets": ("zendesk", {"requester_id": "string"}),
    "raw.ad_spend": ("google_ads", {"spend_cents": "integer"}),
}

INGEST_JOBS = {
    # job: (source, [tables written], schedule)
    "ingest_shopify": ("shopify", ["raw.shopify_orders", "raw.shopify_order_items"], "*/30 * * * *"),
    "ingest_stripe": ("stripe", ["raw.stripe_payments"], "0 * * * *"),
    "ingest_crm": ("hubspot", ["raw.crm_customers"], "0 */4 * * *"),
    "ingest_zendesk": ("zendesk", ["raw.zendesk_tickets"], "0 * * * *"),
    "ingest_ads": ("google_ads", ["raw.ad_spend"], "0 5 * * *"),
}

# --------------------------------------------------------------------------
# dbt models: name -> (layer, team owner, {column: type})
# --------------------------------------------------------------------------
MODELS = {
    "stg_orders": ("staging", "finance_analytics", {"order_id": "string", "customer_id": "string", "amount": "decimal(18,2)"}),
    "stg_order_items": ("staging", "finance_analytics", {"discount": "decimal(18,2)"}),
    "stg_payments": ("staging", "finance_analytics", {"amount": "decimal(18,2)"}),
    "stg_customers": ("staging", "customer_analytics", {"customer_id": "string", "segment": "string"}),
    "stg_tickets": ("staging", "customer_analytics", {"customer_id": "string"}),
    "stg_ad_spend": ("staging", "growth_analytics", {"spend": "decimal(18,2)"}),
    "int_order_revenue": ("intermediate", "finance_analytics", {"gross_revenue": "decimal(18,2)", "net_revenue": "decimal(18,2)"}),
    "int_customer_orders": ("intermediate", "customer_analytics", {"customer_id": "string", "lifetime_spend": "decimal(18,2)"}),
    "int_payments_reconciled": ("intermediate", "finance_analytics", {"paid_amount": "decimal(18,2)", "expected_amount": "decimal(18,2)", "variance": "decimal(18,2)"}),
    "dim_customer": ("mart", "customer_analytics", {"customer_id": "string", "segment": "string", "lifetime_value": "decimal(18,2)"}),
    "fct_orders": ("mart", "finance_analytics", {"order_id": "string", "order_amount": "decimal(18,2)"}),
    "fct_revenue_daily": ("mart", "finance_analytics", {"revenue": "decimal(18,2)"}),
    "mart_finance_revenue": ("mart", "finance_analytics", {"revenue_usd": "decimal(18,2)"}),
    "mart_cash_reconciliation": ("mart", "finance_analytics", {"variance_usd": "decimal(18,2)"}),
    "mart_customers": ("mart", "customer_analytics", {"customer_id": "string", "lifetime_value": "decimal(18,2)"}),
    "mart_customer_ltv": ("mart", "customer_analytics", {"ltv": "decimal(18,2)"}),
    "mart_support_health": ("mart", "customer_analytics", {"tickets_per_customer": "float"}),
    "mart_marketing_roi": ("mart", "growth_analytics", {"roas": "float"}),
    "mart_churn_features": ("mart", "customer_analytics", {"churn_score_input": "float"}),
}

# Column-level lineage: downstream column -> [upstream columns]
COLUMN_LINEAGE = {
    "stg_orders.order_id": ["raw.shopify_orders.order_id"],
    "stg_orders.customer_id": ["raw.shopify_orders.customer_id"],
    "stg_orders.amount": ["raw.shopify_orders.total_price_cents"],
    "stg_order_items.discount": ["raw.shopify_order_items.discount_cents"],
    "stg_payments.amount": ["raw.stripe_payments.amount_cents"],
    "stg_customers.customer_id": ["raw.crm_customers.customer_id"],
    "stg_customers.segment": ["raw.crm_customers.segment"],
    "stg_tickets.customer_id": ["raw.zendesk_tickets.requester_id"],
    "stg_ad_spend.spend": ["raw.ad_spend.spend_cents"],
    "int_order_revenue.gross_revenue": ["stg_orders.amount"],
    "int_order_revenue.net_revenue": ["int_order_revenue.gross_revenue", "stg_order_items.discount"],
    "int_customer_orders.customer_id": ["stg_orders.customer_id"],
    "int_customer_orders.lifetime_spend": ["int_order_revenue.net_revenue"],
    "int_payments_reconciled.paid_amount": ["stg_payments.amount"],
    "int_payments_reconciled.expected_amount": ["int_order_revenue.gross_revenue"],
    "int_payments_reconciled.variance": ["int_payments_reconciled.paid_amount", "int_payments_reconciled.expected_amount"],
    "dim_customer.customer_id": ["stg_customers.customer_id"],
    "dim_customer.segment": ["stg_customers.segment"],
    "dim_customer.lifetime_value": ["int_customer_orders.lifetime_spend"],
    "fct_orders.order_id": ["stg_orders.order_id"],
    "fct_orders.order_amount": ["int_order_revenue.gross_revenue"],
    "fct_revenue_daily.revenue": ["fct_orders.order_amount"],
    "mart_finance_revenue.revenue_usd": ["fct_revenue_daily.revenue"],
    "mart_cash_reconciliation.variance_usd": ["int_payments_reconciled.variance"],
    "mart_customers.customer_id": ["dim_customer.customer_id"],
    "mart_customers.lifetime_value": ["dim_customer.lifetime_value"],
    "mart_customer_ltv.ltv": ["dim_customer.lifetime_value"],
    "mart_support_health.tickets_per_customer": ["stg_tickets.customer_id", "dim_customer.customer_id"],
    "mart_marketing_roi.roas": ["stg_ad_spend.spend", "fct_revenue_daily.revenue"],
    "mart_churn_features.churn_score_input": ["dim_customer.segment", "stg_tickets.customer_id"],
}

# Extra model->model refs not implied by column lineage (joins on keys).
# These make dim_customer the hub of the customer domain (scenario 3).
EXTRA_MODEL_REFS = [
    ("fct_orders", "dim_customer"),
    ("mart_marketing_roi", "dim_customer"),
    ("mart_customer_ltv", "mart_customers"),
    ("int_customer_orders", "stg_customers"),
]

DBT_JOBS = {
    # job: (team owner, schedule, status, last_run_at, models refreshed, extra props)
    "dbt_hourly_core": ("data_platform", "15 * * * *", "success", "2026-10-14T13:15:00Z",
                        ["stg_orders", "stg_order_items", "stg_payments", "stg_customers", "stg_tickets",
                         "stg_ad_spend", "int_order_revenue", "int_customer_orders", "fct_orders", "dim_customer"], {}),
    "dbt_finance_daily": ("finance_analytics", "0 6 * * *", "success", "2026-10-14T10:00:00Z",
                          ["int_payments_reconciled", "fct_revenue_daily", "mart_finance_revenue", "mart_cash_reconciliation"], {}),
    # Scenario 2: today's failure
    "dbt_mart_customers_daily": ("customer_analytics", "0 7 * * *", "failed", "2026-10-14T11:00:00Z",
                                 ["mart_customers", "mart_customer_ltv", "mart_churn_features",
                                  "mart_support_health", "mart_marketing_roi"],
                                 {"last_error": "dbt test unique_mart_customers_customer_id failed: 37 duplicate customer_id values"}),
}

DASHBOARDS = {
    # name: (title, team owner, person owner or None, [models displayed])
    "finance.revenue_daily": ("Daily Revenue", "finance_analytics", "priya.raman", ["mart_finance_revenue"]),
    "finance.cash_reconciliation": ("Cash Reconciliation", "finance_analytics", "marcus.lee", ["mart_cash_reconciliation"]),
    "exec.kpi_overview": ("Executive KPI Overview", "finance_analytics", None, ["fct_revenue_daily", "mart_customers"]),
    "cx.support_health": ("Support Health", "customer_analytics", "ana.petrova", ["mart_support_health"]),
    "growth.marketing_roi": ("Marketing ROI", "growth_analytics", "lena.ortiz", ["mart_marketing_roi"]),
    "crm.customer_360": ("Customer 360", "customer_analytics", "jules.chen", ["mart_customers", "mart_customer_ltv"]),
}

CONTRACTS = {
    # name: (title, team owner, version, spec, governs [column fqns or model names])
    "orders_amount": ("Orders amount contract", "finance_analytics", "2.1",
                      "amount is decimal(18,2) in USD dollars (not cents); not null; >= 0",
                      ["column:stg_orders.amount", "model:stg_orders"]),
    "payments_amount": ("Payments amount contract", "finance_analytics", "1.3",
                        "amount is decimal(18,2) in USD dollars; not null",
                        ["column:stg_payments.amount"]),
    "customers_identity": ("Customer identity contract", "customer_analytics", "1.0",
                           "customer_id is unique and not null; sourced from CRM",
                           ["column:stg_customers.customer_id", "column:raw.crm_customers.customer_id"]),
    "dim_customer_grain": ("dim_customer grain contract", "customer_analytics", "1.2",
                           "exactly one row per customer_id in dim_customer and mart_customers",
                           ["model:dim_customer", "column:mart_customers.customer_id"]),
    "finance_revenue_freshness": ("Finance revenue freshness SLA", "finance_analytics", "1.0",
                                  "mart_finance_revenue refreshed by 07:00 ET daily (24h max staleness)",
                                  ["model:mart_finance_revenue"]),
}

TESTS = {
    # name: (target node id, contract, status, last_run_at)
    "not_null_stg_orders_amount": ("column:stg_orders.amount", "orders_amount", "pass", "2026-10-14T13:15:00Z"),
    "accepted_range_stg_orders_amount": ("column:stg_orders.amount", "orders_amount", "pass", "2026-10-14T13:15:00Z"),
    "not_null_stg_payments_amount": ("column:stg_payments.amount", "payments_amount", "pass", "2026-10-14T13:15:00Z"),
    "unique_stg_customers_customer_id": ("column:stg_customers.customer_id", "customers_identity", "pass", "2026-10-14T13:15:00Z"),
    "unique_mart_customers_customer_id": ("column:mart_customers.customer_id", "dim_customer_grain", "fail", "2026-10-14T11:00:00Z"),
    "freshness_mart_finance_revenue": ("model:mart_finance_revenue", "finance_revenue_freshness", "pass", "2026-10-14T10:05:00Z"),
}

INCIDENTS = [
    {
        "key": "INC-0802", "title": "Revenue dashboard showed 100x values after Shopify cents/dollars change",
        "opened_at": "2026-08-02T14:10:00Z", "resolved_at": "2026-08-02T19:40:00Z", "severity": "SEV2", "status": "resolved",
        "root_cause": "Upstream Shopify export switched total_price to cents; stg_orders.amount was not divided by 100.",
        "resolution": "Added accepted_range test on stg_orders.amount; contract orders_amount bumped to v2.",
        "triggered_by": "ingest_shopify", "violated": ["orders_amount"], "owner": "priya.raman", "related": [],
    },
    {
        "key": "INC-0916", "title": "Duplicate customer_id rows after CRM backfill",
        "opened_at": "2026-09-16T09:05:00Z", "resolved_at": "2026-09-16T16:30:00Z", "severity": "SEV3", "status": "resolved",
        "root_cause": "CRM backfill re-inserted merged contacts, producing duplicate customer_id values in raw.crm_customers.",
        "resolution": "Dedup step added to stg_customers; CRM team notified.",
        "triggered_by": "ingest_crm", "violated": ["customers_identity"], "owner": "sam.rivera", "related": [],
    },
    {
        "key": "INC-0917", "title": "dbt_mart_customers_daily failed on unique test (customer grain)",
        "opened_at": "2026-09-17T11:20:00Z", "resolved_at": "2026-09-17T15:00:00Z", "severity": "SEV2", "status": "resolved",
        "root_cause": "Duplicates from INC-0916 propagated through dim_customer into mart_customers.",
        "resolution": "Re-ran ingest_crm after dedup fix, then dbt_mart_customers_daily.",
        "triggered_by": "dbt_mart_customers_daily", "violated": ["dim_customer_grain"], "owner": "jules.chen",
        "related": ["INC-0916"],
    },
    {
        "key": "INC-0930", "title": "Daily Revenue dashboard stale for 30 hours",
        "opened_at": "2026-09-30T12:00:00Z", "resolved_at": "2026-09-30T14:45:00Z", "severity": "SEV3", "status": "resolved",
        "root_cause": "dbt_finance_daily was paused during a warehouse maintenance window and not resumed.",
        "resolution": "Resumed schedule; added freshness alert.",
        "triggered_by": "dbt_finance_daily", "violated": ["finance_revenue_freshness"], "owner": "marcus.lee", "related": [],
    },
]

INFRA_OWNED = ["source", "table", "ingest_job"]  # owned by Data Platform


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------
def build():
    nodes: dict[str, list[dict]] = defaultdict(list)
    edges: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    label_of: dict[str, str] = {}

    def node(label: str, nid: str, **props):
        assert nid not in label_of, f"duplicate node id {nid}"
        label_of[nid] = label
        nodes[label].append({"id": nid, **props})

    def edge(rel: str, src: str, dst: str, **props):
        assert src in label_of, f"unknown src {src} ({rel})"
        assert dst in label_of, f"unknown dst {dst} ({rel})"
        edges[(rel, label_of[src], label_of[dst])].append({"src": src, "dst": dst, **props})

    # org
    for key, name in TEAMS.items():
        node("Team", f"team:{key}", name=name)
    for handle, name, team, role, on_call in PEOPLE:
        node("Person", f"person:{handle}", name=name, email=f"{handle}@acme.example",
             slack=f"@{handle.split('.')[0]}", role=role, on_call=str(on_call).lower())
        edge("MEMBER_OF", f"person:{handle}", f"team:{team}")

    # sources + raw tables + columns
    for key, (name, kind) in SOURCES.items():
        node("Source", f"source:{key}", name=name, kind=kind)
        edge("OWNED_BY", f"source:{key}", "team:data_platform")
    for tname, (src, cols) in RAW_TABLES.items():
        node("Table", f"table:{tname}", name=tname, layer="raw", source=src)
        edge("OWNED_BY", f"table:{tname}", "team:data_platform")
        for c, ctype in cols.items():
            node("Column", f"column:{tname}.{c}", name=c, table=tname, fqn=f"{tname}.{c}", data_type=ctype)
            edge("HAS_COLUMN", f"table:{tname}", f"column:{tname}.{c}")

    # models + columns
    for m, (layer, team, cols) in MODELS.items():
        node("Model", f"model:{m}", name=m, layer=layer, materialized="view" if layer == "staging" else "table")
        edge("OWNED_BY", f"model:{m}", f"team:{team}")
        for c, ctype in cols.items():
            node("Column", f"column:{m}.{c}", name=c, table=m, fqn=f"{m}.{c}", data_type=ctype)
            edge("HAS_COLUMN", f"model:{m}", f"column:{m}.{c}")
    # person-level owners on a few key models
    edge("OWNED_BY", "model:stg_orders", "person:priya.raman")
    edge("OWNED_BY", "model:mart_finance_revenue", "person:marcus.lee")
    edge("OWNED_BY", "model:dim_customer", "person:jules.chen")

    # column lineage + derived model-level lineage
    model_refs: set[tuple[str, str]] = set()
    reads_raw: set[tuple[str, str]] = set()
    for down, ups in COLUMN_LINEAGE.items():
        for up in ups:
            edge("DEPENDS_ON", f"column:{down}", f"column:{up}", level="column")
            down_parent = down.rsplit(".", 1)[0]
            up_parent = up.rsplit(".", 1)[0]
            if down_parent == up_parent:
                continue
            if up_parent in RAW_TABLES:
                reads_raw.add((down_parent, up_parent))
            else:
                model_refs.add((down_parent, up_parent))
    model_refs.update(EXTRA_MODEL_REFS)
    for down, up in sorted(model_refs):
        edge("DEPENDS_ON", f"model:{down}", f"model:{up}", level="model")
    for m, t in sorted(reads_raw):
        edge("READS_FROM", f"model:{m}", f"table:{t}")

    # ingestion jobs
    for j, (src, tables, sched) in INGEST_JOBS.items():
        node("Job", f"job:{j}", name=j, kind="ingestion", schedule=sched, status="success",
             last_run_at="2026-10-14T13:00:00Z")
        edge("OWNED_BY", f"job:{j}", "team:data_platform")
        edge("READS_FROM", f"job:{j}", f"source:{src}")
        for t in tables:
            edge("WRITES_TO", f"job:{j}", f"table:{t}")

    # dbt jobs
    for j, (team, sched, status, last_run, models, extra) in DBT_JOBS.items():
        node("Job", f"job:{j}", name=j, kind="dbt", schedule=sched, status=status, last_run_at=last_run, **extra)
        edge("OWNED_BY", f"job:{j}", f"team:{team}")
        for m in models:
            edge("REFRESHES", f"job:{j}", f"model:{m}")

    # dashboards + BI refresh job
    node("Job", "job:refresh_bi_dashboards", name="refresh_bi_dashboards", kind="bi_refresh",
         schedule="30 7 * * *", status="success", last_run_at="2026-10-14T11:30:00Z")
    edge("OWNED_BY", "job:refresh_bi_dashboards", "team:data_platform")
    for d, (title, team, person, models) in DASHBOARDS.items():
        node("Dashboard", f"dashboard:{d}", name=d, title=title, tool="BI")
        edge("OWNED_BY", f"dashboard:{d}", f"team:{team}")
        if person:
            edge("OWNED_BY", f"dashboard:{d}", f"person:{person}")
        for m in models:
            edge("DISPLAYS", f"dashboard:{d}", f"model:{m}")
        edge("REFRESHES", "job:refresh_bi_dashboards", f"dashboard:{d}")

    # contracts + tests
    for k, (title, team, version, spec, governs) in CONTRACTS.items():
        node("Contract", f"contract:{k}", name=k, title=title, version=version, spec=spec, status="active")
        edge("OWNED_BY", f"contract:{k}", f"team:{team}")
        for target in governs:
            edge("GOVERNED_BY", target, f"contract:{k}")
    for t, (target, contract, status, last_run) in TESTS.items():
        node("Test", f"test:{t}", name=t, status=status, last_run_at=last_run)
        edge("READS_FROM", f"test:{t}", target)
        edge("GOVERNED_BY", f"test:{t}", f"contract:{contract}")

    # incidents (past episodes; Track 02 memory builds on these)
    for inc in INCIDENTS:
        nid = f"incident:{inc['key']}"
        node("Incident", nid, name=inc["key"], title=inc["title"], opened_at=inc["opened_at"],
             resolved_at=inc["resolved_at"], severity=inc["severity"], status=inc["status"],
             root_cause=inc["root_cause"], resolution=inc["resolution"])
        edge("TRIGGERED_BY", nid, f"job:{inc['triggered_by']}")
        for k in inc["violated"]:
            edge("VIOLATED", nid, f"contract:{k}")
        edge("OWNED_BY", nid, f"person:{inc['owner']}")
        for r in inc["related"]:
            edge("RELATED_TO", nid, f"incident:{r}")

    return nodes, edges


def write(out_dir: Path = DATA_DIR) -> tuple[int, int]:
    nodes, edges = build()
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in list(out_dir.glob("nodes_*.csv")) + list(out_dir.glob("edges_*.csv")):
        old.unlink()
    for label, rows in sorted(nodes.items()):
        cols = sorted({k for r in rows for k in r}, key=lambda k: (k != "id", k != "name", k))
        with open(out_dir / f"nodes_{label}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
    by_rel: dict[str, list[dict]] = defaultdict(list)
    for (rel, sl, dl), rows in edges.items():
        for r in rows:
            by_rel[rel].append({"src_label": sl, "dst_label": dl, **r})
    for rel, rows in sorted(by_rel.items()):
        cols = sorted({k for r in rows for k in r},
                      key=lambda k: (["src_label", "src", "dst_label", "dst"] + [k]).index(k))
        with open(out_dir / f"edges_{rel}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
    with open(out_dir / "incidents.json", "w") as f:
        json.dump(INCIDENTS, f, indent=2)
    n = sum(len(v) for v in nodes.values())
    e = sum(len(v) for v in by_rel.values())
    return n, e


if __name__ == "__main__":
    n, e = write()
    print(f"wrote {n} nodes, {e} edges to {DATA_DIR}")
