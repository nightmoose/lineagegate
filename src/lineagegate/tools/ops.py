"""Day-2 graph tools: failed-job triage, incident memory, critical assets.

All read paths are pure Cypher over FalkorDB. Incident memory is persisted as
``Incident`` nodes linked into the lineage graph, so anything recorded in one
session is recalled by ``similar_incidents`` in the next.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from lineagegate.graph.client import PATH_NODES, PATH_RELS, graph, make_path, resolve_node, ro

_WORD = re.compile(r"[a-z0-9_]{3,}")
_STOP = {"the", "and", "for", "with", "after", "was", "not", "from", "into", "this", "that", "failed", "values"}


def _words(text: str | None) -> set[str]:
    return {w for w in _WORD.findall((text or "").lower()) if w not in _STOP}


def _resolve(ref: str, label: str) -> dict | None:
    for cand in (ref if ":" in ref else f"{label.lower()}:{ref}", ref):
        hits = [h for h in resolve_node(cand) if h["label"] == label]
        if hits:
            return hits[0]
    return None


# --------------------------------------------------------------------------
# triage_failed_job
# --------------------------------------------------------------------------
def triage_failed_job(job: str | None = None) -> dict:
    """Explain a failed job: failing tests, upstream suspects, violated contracts,
    downstream dashboards, owners and matching past incidents."""
    if not job:
        rows = ro("MATCH (j:Job {status:'failed'}) RETURN j.id ORDER BY j.last_run_at DESC LIMIT 1")
        if not rows:
            return {"found": False, "error": "no failed jobs in the graph"}
        job = rows[0][0]
    j = _resolve(job, "Job")
    if j is None:
        return {"found": False, "error": f"job {job!r} not found",
                "failed_jobs": [r[0] for r in ro("MATCH (j:Job {status:'failed'}) RETURN j.id ORDER BY j.id")]}
    jid = j["id"]
    info = ro("MATCH (j:Job {id:$id}) RETURN j.status, j.last_error, j.last_run_at, j.kind", {"id": jid})[0]

    models = [r[0] for r in ro(
        "MATCH (:Job {id:$id})-[:REFRESHES]->(m:Model) RETURN m.id ORDER BY m.id", {"id": jid})]

    failing = [{"id": r[0], "name": r[1], "on": r[2], "last_run_at": r[3]} for r in ro(
        """MATCH (:Job {id:$id})-[:REFRESHES]->(m:Model)
           MATCH (t:Test)-[:READS_FROM]->(x) WHERE x = m OR (m)-[:HAS_COLUMN]->(x)
           WITH DISTINCT t, x WHERE t.status = 'fail'
           RETURN t.id, t.name, x.id, t.last_run_at ORDER BY t.id""", {"id": jid})]

    # Upstream models (and the jobs that feed them) are the suspects.
    upstream = [{"id": r[0], "hops": r[1], "refreshed_by": r[2]} for r in ro(
        """MATCH (:Job {id:$id})-[:REFRESHES]->(m:Model)
           MATCH p = (m)-[:DEPENDS_ON*1..8]->(u:Model)
           WITH u, min(length(p)) AS hops
           OPTIONAL MATCH (uj:Job)-[:REFRESHES]->(u)
           RETURN u.id, hops, collect(DISTINCT uj.id) ORDER BY hops, u.id""", {"id": jid})]
    best: dict[str, dict] = {}
    for uid, status, pn, pr in ro(
            f"""MATCH p = (:Job {{id:$id}})-[:REFRESHES]->(:Model)-[:DEPENDS_ON*0..8]->(:Model)
                          -[:READS_FROM]->(:Table)<-[:WRITES_TO]-(uj:Job)
                RETURN uj.id, uj.status, {PATH_NODES}, {PATH_RELS}""", {"id": jid}):
        path = make_path(pn, pr)
        if uid not in best or path["hops"] < best[uid]["hops"]:
            best[uid] = {"id": uid, "status": status, "hops": path["hops"], "path": path["text"]}
    upstream_jobs = [best[k] for k in sorted(best)]

    contracts = [{"id": r[0], "spec": r[1], "on": r[2]} for r in ro(
        """MATCH (:Job {id:$id})-[:REFRESHES]->(m:Model)
           OPTIONAL MATCH (m)-[:DEPENDS_ON*0..8]->(u:Model)
           WITH collect(DISTINCT m) + collect(DISTINCT u) AS ms
           UNWIND ms AS x
           MATCH (x)-[:GOVERNED_BY]->(c:Contract)
           RETURN DISTINCT c.id, c.spec, x.id ORDER BY c.id""", {"id": jid})]

    dashboards = [r[0] for r in ro(
        """MATCH (:Job {id:$id})-[:REFRESHES]->(m:Model)<-[:DEPENDS_ON*0..8]-(d:Model)<-[:DISPLAYS]-(dash:Dashboard)
           RETURN DISTINCT dash.id ORDER BY dash.id""", {"id": jid})]

    owners = [{"team": r[0], "on_call": r[1]} for r in ro(
        """MATCH (:Job {id:$id})-[:OWNED_BY]->(t:Team)
           OPTIONAL MATCH (p:Person {on_call:true})-[:MEMBER_OF]->(t)
           RETURN t.name, collect(p.name)""", {"id": jid})]

    query_text = " ".join(filter(None, [info[1], *(f["name"] for f in failing)]))
    past = similar_incidents(node=jid, text=query_text, k=3)["incidents"]

    return {"found": True, "job": {"id": jid, "status": info[0], "last_error": info[1],
                                    "last_run_at": info[2], "kind": info[3]},
            "refreshes": models, "failing_tests": failing, "upstream_models": upstream,
            "upstream_ingestion_jobs": upstream_jobs, "contracts": contracts,
            "downstream_dashboards": dashboards, "owners": owners, "similar_incidents": past}


# --------------------------------------------------------------------------
# similar_incidents (graph + keyword) and record_incident (memory write)
# --------------------------------------------------------------------------
_LINEAGE_RELS = ("DEPENDS_ON|READS_FROM|WRITES_TO|REFRESHES|HAS_COLUMN|GOVERNED_BY|"
                 "TRIGGERED_BY|VIOLATED|RELATED_TO|DISPLAYS")


def similar_incidents(node: str | None = None, text: str | None = None, k: int = 5) -> dict:
    """Rank stored incidents by graph proximity to ``node`` (shared job,
    contract, or lineage neighbourhood) plus keyword overlap with ``text``."""
    anchor = None
    graph_score: dict[str, tuple[float, str]] = {}
    if node:
        hits = resolve_node(node)
        if hits:
            anchor = hits[0]["id"]
            rows = ro(
                f"""MATCH (a {{id:$id}}), (i:Incident) WHERE i <> a
                    WITH i, shortestPath((a)-[:{_LINEAGE_RELS}*1..6]-(i)) AS p
                    WHERE p IS NOT NULL
                    RETURN i.id, length(p), {PATH_NODES}, {PATH_RELS}""", {"id": anchor})
            for iid, hops, pn, pr in rows:
                graph_score[iid] = (1.0 / hops, make_path(pn, pr)["text"])
    qwords = _words(text)
    out = []
    for iid, title, root, sev, opened, res, related in ro(
            """MATCH (i:Incident) OPTIONAL MATCH (i)-[:RELATED_TO]-(r:Incident)
               RETURN i.id, i.title, i.root_cause, i.severity, i.opened_at, i.resolution,
                      collect(DISTINCT r.id)"""):
        g, path = graph_score.get(iid, (0.0, None))
        kw = len(qwords & _words(f"{title} {root}")) / max(len(qwords), 1) if qwords else 0.0
        score = round(g + kw, 4)
        if score > 0:
            out.append({"id": iid, "title": title, "severity": sev, "opened_at": opened,
                        "root_cause": root, "resolution": res, "related": related,
                        "score": score, "graph_path": path})
    out.sort(key=lambda x: (-x["score"], x["id"]))
    return {"found": bool(out), "anchor": anchor, "incidents": out[:k]}


def record_incident(title: str, root_cause: str = "", severity: str = "SEV3",
                    job: str | None = None, contracts: list[str] | None = None,
                    resolution: str = "", key: str | None = None) -> dict:
    """Persist an incident into FalkorDB, linking it to its job/contracts and to
    the most similar prior incidents (RELATED_TO). This is cross-session memory."""
    now = datetime.now(timezone.utc)
    key = key or f"INC-{now:%m%d%H%M%S}"
    iid = f"incident:{key}"
    g = graph()
    g.query("""MERGE (i:Incident {id:$id})
               SET i.name=$key, i.title=$title, i.root_cause=$rc, i.severity=$sev,
                   i.status='open', i.opened_at=$ts, i.resolution=$res""",
            {"id": iid, "key": key, "title": title, "rc": root_cause, "sev": severity,
             "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "res": resolution})
    links = []
    if job and (j := _resolve(job, "Job")):
        g.query("MATCH (i:Incident {id:$i}),(j:Job {id:$j}) MERGE (i)-[:TRIGGERED_BY]->(j)",
                {"i": iid, "j": j["id"]})
        links.append(f"TRIGGERED_BY {j['id']}")
    for c in contracts or []:
        if cn := _resolve(c, "Contract"):
            g.query("MATCH (i:Incident {id:$i}),(c:Contract {id:$c}) MERGE (i)-[:VIOLATED]->(c)",
                    {"i": iid, "c": cn["id"]})
            links.append(f"VIOLATED {cn['id']}")
    sims = [s for s in similar_incidents(node=iid, text=f"{title} {root_cause}", k=4)["incidents"]
            if s["id"] != iid][:2]
    for s in sims:
        g.query("MATCH (a:Incident {id:$a}),(b:Incident {id:$b}) MERGE (a)-[:RELATED_TO]->(b)",
                {"a": iid, "b": s["id"]})
        links.append(f"RELATED_TO {s['id']}")
    return {"found": True, "id": iid, "links": links}


# --------------------------------------------------------------------------
# critical_assets
# --------------------------------------------------------------------------
def critical_assets(algorithm: str = "pagerank", k: int = 5) -> dict:
    """Rank models by structural importance in the DEPENDS_ON lineage using
    FalkorDB's built-in algorithms (algo.pageRank or algo.betweenness), and
    attach downstream dashboard reach + owner for each."""
    algorithm = algorithm.lower()
    if algorithm == "betweenness":
        q = ("CALL algo.betweenness({nodeLabels:['Model'], relationshipTypes:['DEPENDS_ON']}) "
             "YIELD node, score")
    else:
        algorithm = "pagerank"
        q = "CALL algo.pageRank('Model','DEPENDS_ON') YIELD node, score"
    rows = ro(q + """
        WITH node, score ORDER BY score DESC, node.id LIMIT $k
        OPTIONAL MATCH (node)<-[:DEPENDS_ON*0..8]-(:Model)<-[:DISPLAYS]-(d:Dashboard)
        WITH node, score, count(DISTINCT d) AS dashboards
        OPTIONAL MATCH (node)<-[:DEPENDS_ON*1..8]-(down:Model)
        WITH node, score, dashboards, count(DISTINCT down) AS downstream
        OPTIONAL MATCH (node)-[:OWNED_BY]->(t:Team)
        RETURN node.id, score, downstream, dashboards, t.name
        ORDER BY score DESC, node.id""", {"k": int(k)})
    return {"found": bool(rows), "algorithm": algorithm,
            "assets": [{"id": r[0], "score": round(float(r[1]), 4), "downstream_models": r[2],
                        "dashboards": r[3], "owner_team": r[4]} for r in rows]}


TOOLS = {"triage_failed_job": triage_failed_job, "similar_incidents": similar_incidents,
         "record_incident": record_incident, "critical_assets": critical_assets}

TOOL_SPECS = [
    {"type": "function", "function": {
        "name": "triage_failed_job",
        "description": "Triage a failed pipeline job: error, failing tests, upstream models/ingestion jobs "
                       "(with graph paths), contracts involved, downstream dashboards at risk, owners/on-call, "
                       "and similar past incidents. Omit job to triage the most recent failure.",
        "parameters": {"type": "object", "properties": {
            "job": {"type": "string", "description": "Job name or id, e.g. dbt_mart_customers_daily"}}}}},
    {"type": "function", "function": {
        "name": "similar_incidents",
        "description": "Recall past incidents (persistent memory in the graph) similar to a node and/or a "
                       "description. Ranked by graph distance plus keyword overlap; returns root cause, "
                       "resolution and the connecting graph path.",
        "parameters": {"type": "object", "properties": {
            "node": {"type": "string", "description": "Any node ref: job, model, contract, column fqn"},
            "text": {"type": "string", "description": "Symptom / error description"},
            "k": {"type": "integer", "default": 5}}}}},
    {"type": "function", "function": {
        "name": "record_incident",
        "description": "Persist a new incident into graph memory, linked to its job, violated contracts and "
                       "similar past incidents. Only call when the user explicitly asks to record/log one.",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string"}, "root_cause": {"type": "string"},
            "severity": {"type": "string", "enum": ["SEV1", "SEV2", "SEV3", "SEV4"]},
            "job": {"type": "string"}, "contracts": {"type": "array", "items": {"type": "string"}},
            "resolution": {"type": "string"}}, "required": ["title"]}}},
    {"type": "function", "function": {
        "name": "critical_assets",
        "description": "Most critical models in the lineage by FalkorDB graph algorithm (pagerank or "
                       "betweenness), with downstream model/dashboard reach and owner team.",
        "parameters": {"type": "object", "properties": {
            "algorithm": {"type": "string", "enum": ["pagerank", "betweenness"], "default": "pagerank"},
            "k": {"type": "integer", "default": 5}}}}},
]
