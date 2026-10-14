"""FastAPI service: /health, /impact, /chat (+ /triage, /incidents, /critical).

Run: uvicorn lineagegate.api.app:app --reload
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from lineagegate import config
from lineagegate.agent.loop import ask
from lineagegate.graph.client import db
from lineagegate.tools.lineage import impact_from_column
from lineagegate.tools.ops import critical_assets, similar_incidents, triage_failed_job

app = FastAPI(title="LineageGate", version="0.2.0",
              description="Explainable agent over a data lineage + contracts graph in FalkorDB")


class ChatIn(BaseModel):
    question: str
    offline: bool = False


@app.get("/health")
def health() -> dict:
    try:
        db().connection.ping()
        n = db().select_graph(config.GRAPH_NAME).ro_query("MATCH (n) RETURN count(n)").result_set[0][0]
        return {"status": "ok", "falkordb": "up", "graph": config.GRAPH_NAME, "nodes": n}
    except Exception as exc:
        return {"status": "degraded", "falkordb": f"down: {type(exc).__name__}", "graph": config.GRAPH_NAME}


@app.get("/impact")
def impact(column: str) -> dict:
    """Blast radius for `table.column`, e.g. /impact?column=stg_orders.amount"""
    r = impact_from_column(column)
    if not r.get("found"):
        raise HTTPException(404, detail=r)
    return r


@app.post("/chat")
def chat(body: ChatIn) -> dict:
    res = ask(body.question, offline=body.offline)
    return {"answer": res.answer, "mode": res.mode,
            "tool_calls": [{"tool": c["tool"], "args": c["args"], "result": c["result"]} for c in res.tool_calls]}


@app.get("/triage")
def triage(job: str | None = None) -> dict:
    return triage_failed_job(job)


@app.get("/incidents")
def incidents(node: str | None = None, text: str | None = None, k: int = 5) -> dict:
    return similar_incidents(node=node, text=text, k=k)


@app.get("/critical")
def critical(algorithm: str = "pagerank", k: int = 5) -> dict:
    return critical_assets(algorithm, k)


STATIC = Path(__file__).parent / "static"


@app.get("/", include_in_schema=False)
def ui() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/schema")
def schema() -> dict:
    """Live schema from FalkorDB: labels, relationship types, and label-[type]->label pairs with counts."""
    from lineagegate.graph.client import ro
    labels = {r[0]: 0 for r in ro("CALL db.labels() YIELD label RETURN label")}
    for lbl, n in ro("MATCH (n) RETURN labels(n)[0], count(n)"):
        labels[lbl] = n
    rel_types = [r[0] for r in ro("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType")]
    pairs = [{"from": a, "type": t, "to": b, "count": c} for a, t, b, c in ro(
        "MATCH (a)-[r]->(b) RETURN labels(a)[0], type(r), labels(b)[0], count(r) ORDER BY type(r), labels(a)[0]")]
    return {"labels": [{"label": k, "count": v} for k, v in sorted(labels.items())],
            "relationship_types": sorted(rel_types), "pairs": pairs}
