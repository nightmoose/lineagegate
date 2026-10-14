from fastapi.testclient import TestClient

from lineagegate.api.app import app

client = TestClient(app)


def test_health():
    r = client.get("/health").json()
    assert r["status"] == "ok" and r["nodes"] > 80


def test_impact_endpoint():
    r = client.get("/impact", params={"column": "stg_orders.amount"})
    assert r.status_code == 200
    assert "finance.revenue_daily" in {d["name"] for d in r.json()["impacted"]["dashboards"]}
    assert client.get("/impact", params={"column": "stg_orders.nope"}).status_code == 404


def test_chat_offline():
    r = client.post("/chat", json={"question": "What breaks if stg_orders.amount changes?", "offline": True}).json()
    assert r["mode"] == "offline-router"
    assert r["tool_calls"][0]["tool"] == "impact_from_column"
    assert "finance.revenue_daily" in r["answer"]


def test_schema_endpoint():
    j = client.get("/schema").json()
    assert {l["label"] for l in j["labels"]} >= {"Column", "Model", "Dashboard", "Incident"}
    assert "DEPENDS_ON" in j["relationship_types"]
    assert {"from": "Dashboard", "type": "DISPLAYS", "to": "Model", "count": 8} in j["pairs"]
    assert sum(p["count"] for p in j["pairs"]) == 248
