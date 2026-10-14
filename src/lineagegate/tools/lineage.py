"""Cypher-backed graph tools the agent can call.

Each tool returns plain JSON-serialisable dicts, always including the graph
paths that justify the answer (``paths[*].text``) and the Cypher used, so the
agent can cite evidence instead of guessing.
"""
from __future__ import annotations

import difflib

from lineagegate.graph.client import PATH_NODES, PATH_RELS, make_path, requires_graph, resolve_node, ro, suggest

MAX_HOPS = 8

# --------------------------------------------------------------------------
# impact_from_column
# --------------------------------------------------------------------------
# Column-precise blast radius: follow column-level DEPENDS_ON edges downstream
# (incoming direction), then hop to the owning model/table, then to the
# dashboards that display it and the jobs that refresh it.
IMPACT_MODELS = f"""
MATCH (c:Column {{fqn: $fqn}})
MATCH p = (c)<-[:DEPENDS_ON*0..{MAX_HOPS}]-(dc:Column)<-[:HAS_COLUMN]-(m:Model)
RETURN m.id, labels(m)[0], m.name, length(p) AS hops, {PATH_NODES} AS pnodes, {PATH_RELS} AS prels
ORDER BY hops
"""

IMPACT_DASHBOARDS = f"""
MATCH (c:Column {{fqn: $fqn}})
MATCH p = (c)<-[:DEPENDS_ON*0..{MAX_HOPS}]-(:Column)<-[:HAS_COLUMN]-(:Model)<-[:DISPLAYS]-(d:Dashboard)
RETURN d.id, labels(d)[0], d.name, length(p) AS hops, {PATH_NODES} AS pnodes, {PATH_RELS} AS prels
ORDER BY hops
"""

IMPACT_JOBS = f"""
MATCH (c:Column {{fqn: $fqn}})
MATCH p = (c)<-[:DEPENDS_ON*0..{MAX_HOPS}]-(:Column)<-[:HAS_COLUMN]-(:Model)<-[:REFRESHES]-(j:Job)
RETURN j.id, labels(j)[0], j.name, length(p) AS hops, {PATH_NODES} AS pnodes, {PATH_RELS} AS prels
ORDER BY hops
"""

IMPACT_COLUMNS = f"""
MATCH (c:Column {{fqn: $fqn}})
MATCH (c)<-[:DEPENDS_ON*1..{MAX_HOPS}]-(dc:Column)
RETURN DISTINCT dc.id, dc.fqn, dc.data_type ORDER BY dc.fqn
"""

IMPACT_CONTRACTS = f"""
MATCH (c:Column {{fqn: $fqn}})
MATCH (c)<-[:DEPENDS_ON*0..{MAX_HOPS}]-(dc:Column)
OPTIONAL MATCH (m:Model)-[:HAS_COLUMN]->(dc)
WITH collect(DISTINCT dc) + collect(DISTINCT m) AS assets
UNWIND assets AS a
MATCH (a)-[:GOVERNED_BY]->(k:Contract)
OPTIONAL MATCH (k)-[:OWNED_BY]->(t:Team)
RETURN k.id, k.name, k.version, k.spec, collect(DISTINCT a.id) AS governs, t.name ORDER BY k.id
"""

IMPACT_TESTS = f"""
MATCH (c:Column {{fqn: $fqn}})
MATCH (c)<-[:DEPENDS_ON*0..{MAX_HOPS}]-(dc:Column)
OPTIONAL MATCH (m:Model)-[:HAS_COLUMN]->(dc)
WITH collect(DISTINCT dc) + collect(DISTINCT m) AS assets
UNWIND assets AS a
MATCH (t:Test)-[:READS_FROM]->(a)
RETURN DISTINCT t.id, t.name, t.status, a.id ORDER BY t.id
"""

IMPACT_OWNERS = f"""
MATCH (c:Column {{fqn: $fqn}})
MATCH (c)<-[:DEPENDS_ON*0..{MAX_HOPS}]-(:Column)<-[:HAS_COLUMN]-(m:Model)
OPTIONAL MATCH (d:Dashboard)-[:DISPLAYS]->(m)
WITH collect(DISTINCT m) + collect(DISTINCT d) AS assets
UNWIND assets AS a
MATCH (a)-[:OWNED_BY]->(t:Team)
RETURN t.id, t.name, collect(DISTINCT a.name) AS assets ORDER BY size(assets) DESC
"""


def _shortest_per_target(rows) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for tid, label, name, hops, pnodes, prels in rows:
        if tid not in out or hops < out[tid]["hops"]:
            out[tid] = {"id": tid, "label": label, "name": name, "hops": hops,
                        "path": make_path(pnodes, prels)}
    return out


@requires_graph
def impact_from_column(table: str, column: str | None = None) -> dict:
    """Downstream blast radius of changing ``table.column``.

    Returns impacted columns, models, dashboards, jobs, contracts, tests,
    owning teams, and one shortest evidence path per impacted asset.
    """
    fqn = table if column is None else f"{table}.{column}"
    fqn = fqn.removeprefix("column:")
    found = ro("MATCH (c:Column {fqn: $fqn}) RETURN c.id, c.data_type", {"fqn": fqn})
    if not found:
        table_part = fqn.rsplit(".", 1)[0]
        candidates = [{"id": r[0]} for r in ro(
            "MATCH (c:Column) WHERE c.table = $t OR c.name = $n RETURN c.id ORDER BY c.id LIMIT 10",
            {"t": table_part, "n": fqn.rsplit(".", 1)[-1]})]
        did = [c["id"].removeprefix("column:") for c in candidates]
        did = list(dict.fromkeys(did + suggest(fqn, "Column")))
        did.sort(key=lambda x: -difflib.SequenceMatcher(None, fqn.lower(), x.lower()).ratio())
        table_known = bool(ro("MATCH (n) WHERE (n:Model OR n:Table) AND n.name = $t RETURN n.id LIMIT 1",
                              {"t": table_part}))
        err = (f"Table/model '{table_part}' exists but has no column '{fqn.rsplit('.', 1)[-1]}'."
               if table_known else f"No Column with fqn '{fqn}' in the graph.")
        return {"found": False, "column": fqn, "error": err, "did_you_mean": did[:8]}

    p = {"fqn": fqn}
    models = _shortest_per_target(ro(IMPACT_MODELS, p))
    dashboards = _shortest_per_target(ro(IMPACT_DASHBOARDS, p))
    jobs = _shortest_per_target(ro(IMPACT_JOBS, p))
    origin_model = next((m for m in models.values() if m["hops"] == 1), None)

    def summarise(d: dict[str, dict]) -> list[dict]:
        return [{k: v[k] for k in ("id", "name", "hops")} | {"path": v["path"]["text"]}
                for v in sorted(d.values(), key=lambda v: (v["hops"], v["id"]))]

    paths = [dict(target=v["id"], **v["path"]) for v in
             sorted(dashboards.values(), key=lambda v: (v["hops"], v["id"]))]

    return {
        "found": True,
        "column": fqn,
        "data_type": found[0][1],
        "origin_model": origin_model["name"] if origin_model else None,
        "impacted": {
            "columns": [{"fqn": r[1], "data_type": r[2]} for r in ro(IMPACT_COLUMNS, p)],
            "models": summarise({k: v for k, v in models.items() if v is not origin_model}),
            "dashboards": summarise(dashboards),
            "jobs": summarise(jobs),
            "contracts": [{"id": r[0], "name": r[1], "version": r[2], "spec": r[3], "governs": r[4], "owner_team": r[5]}
                          for r in ro(IMPACT_CONTRACTS, p)],
            "tests": [{"id": r[0], "name": r[1], "status": r[2], "checks": r[3]} for r in ro(IMPACT_TESTS, p)],
        },
        "owners": [{"team": r[1], "id": r[0], "assets": r[2]} for r in ro(IMPACT_OWNERS, p)],
        "paths": paths,
        "cypher": {"models": IMPACT_MODELS.strip(), "dashboards": IMPACT_DASHBOARDS.strip()},
    }


# --------------------------------------------------------------------------
# owners_for_node
# --------------------------------------------------------------------------
# Direct owners first (0 inherited hops), then owners inherited from the
# parent table/model (for columns) or from the asset a test checks.
OWNERS = f"""
MATCH (n {{id: $id}})
MATCH p = (n)<-[:HAS_COLUMN*0..1]-()-[:OWNED_BY]->(o)
RETURN o.id, labels(o)[0], o.name, o.email, o.slack, o.on_call, length(p) - 1 AS inherited,
       {PATH_NODES} AS pnodes, {PATH_RELS} AS prels
UNION
MATCH (n:Test {{id: $id}})
MATCH p = (n)-[:READS_FROM]->()<-[:HAS_COLUMN*0..1]-()-[:OWNED_BY]->(o)
RETURN o.id, labels(o)[0], o.name, o.email, o.slack, o.on_call, length(p) - 1 AS inherited,
       {PATH_NODES} AS pnodes, {PATH_RELS} AS prels
"""

TEAM_MEMBERS = """
MATCH (p:Person)-[:MEMBER_OF]->(t:Team {id: $id})
RETURN p.id, p.name, p.role, p.email, p.slack, p.on_call ORDER BY p.on_call DESC, p.name
"""

PERSON_TEAMS = """
MATCH (p:Person {id: $id})-[:MEMBER_OF]->(t:Team) RETURN t.id, t.name
"""


@requires_graph
def owners_for_node(node: str) -> dict:
    """Who owns a node: Team/Person via OWNED_BY (inherited through
    HAS_COLUMN for columns), plus team members (MEMBER_OF) and on-call."""
    matches = resolve_node(node)
    if not matches:
        return {"found": False, "node": node, "error": f"No node matches '{node}'.",
                "candidates": suggest(node)}
    if len(matches) > 1 and matches[0]["id"] != node:
        return {"found": False, "node": node, "error": "Ambiguous reference; pick one id.",
                "candidates": [m["id"] for m in matches]}
    target = matches[0]
    rows = ro(OWNERS, {"id": target["id"]})
    owners: dict[str, dict] = {}
    for oid, label, name, email, slack, on_call, inherited, pnodes, prels in rows:
        if oid in owners and owners[oid]["inherited"] <= inherited:
            continue
        owners[oid] = {"id": oid, "label": label, "name": name, "email": email, "slack": slack,
                       "on_call": on_call, "inherited": inherited, "path": make_path(pnodes, prels)["text"]}
    if owners:  # keep only the closest ownership level
        best = min(o["inherited"] for o in owners.values())
        owners = {k: v for k, v in owners.items() if v["inherited"] == best}
    result = []
    for o in sorted(owners.values(), key=lambda o: (o["label"] != "Team", o["name"])):
        if o["label"] == "Team":
            o["members"] = [{"id": r[0], "name": r[1], "role": r[2], "email": r[3], "slack": r[4], "on_call": r[5]}
                            for r in ro(TEAM_MEMBERS, {"id": o["id"]})]
        elif o["label"] == "Person":
            o["teams"] = [r[1] for r in ro(PERSON_TEAMS, {"id": o["id"]})]
        result.append({k: v for k, v in o.items() if v is not None})
    return {"found": True, "node": target, "owners": result,
            "on_call": sorted({m["name"] for o in result for m in o.get("members", []) if m.get("on_call")}),
            "cypher": OWNERS.strip()}


# --------------------------------------------------------------------------
# paths_explain
# --------------------------------------------------------------------------
LINEAGE_RELS = ["READS_FROM", "WRITES_TO", "HAS_COLUMN", "DEPENDS_ON", "DISPLAYS", "REFRESHES",
                "GOVERNED_BY", "TRIGGERED_BY", "VIOLATED", "RELATED_TO"]
OWNERSHIP_RELS = ["OWNED_BY", "MEMBER_OF"]

# FalkorDB built-in pathfinding: k shortest paths between two nodes.
PATHS_ALGO = f"""
MATCH (a {{id: $src}}), (b {{id: $dst}})
CALL algo.SPpaths({{sourceNode: a, targetNode: b, relTypes: $rel_types, relDirection: 'both',
                   maxLen: $max_hops, pathCount: $k}})
YIELD path, pathWeight
WITH path AS p, pathWeight
RETURN length(p) AS hops, {PATH_NODES} AS pnodes, {PATH_RELS} AS prels
ORDER BY hops
"""

# Fallback (plain Cypher): undirected shortestPath.
PATHS_SHORTEST = f"""
MATCH (a {{id: $src}}), (b {{id: $dst}})
WITH shortestPath((a)-[*..{MAX_HOPS}]-(b)) AS p
WHERE p IS NOT NULL
RETURN length(p) AS hops, {PATH_NODES} AS pnodes, {PATH_RELS} AS prels
"""


@requires_graph
def paths_explain(source: str, target: str, k: int = 3, include_ownership: bool = False,
                  max_hops: int = MAX_HOPS) -> dict:
    """Explain how two nodes are connected: up to ``k`` shortest paths
    (FalkorDB ``algo.SPpaths``), each rendered with edge directions."""
    ends = []
    for ref in (source, target):
        m = resolve_node(ref)
        if not m:
            return {"found": False, "error": f"No node matches '{ref}'.", "candidates": suggest(ref)}
        if len(m) > 1 and m[0]["id"] != ref:
            return {"found": False, "error": f"'{ref}' is ambiguous.", "candidates": [x["id"] for x in m]}
        ends.append(m[0])
    rel_types = LINEAGE_RELS + (OWNERSHIP_RELS if include_ownership else [])
    params = {"src": ends[0]["id"], "dst": ends[1]["id"], "rel_types": rel_types, "max_hops": max_hops, "k": k}
    method = "algo.SPpaths"
    try:
        rows = ro(PATHS_ALGO, params)
    except Exception as exc:  # older server without algo.SPpaths
        method = f"shortestPath (algo.SPpaths unavailable: {exc})"
        rows = ro(PATHS_SHORTEST, params)
    paths = [make_path(pn, pr) for _, pn, pr in rows]
    return {"found": bool(paths), "source": ends[0], "target": ends[1], "method": method,
            "paths": paths, "cypher": PATHS_ALGO.strip(),
            **({} if paths else {"error": "No path within max_hops using lineage relationships."})}


# --------------------------------------------------------------------------
# Tool registry (OpenAI-style function specs)
# --------------------------------------------------------------------------
TOOLS = {
    "impact_from_column": impact_from_column,
    "owners_for_node": owners_for_node,
    "paths_explain": paths_explain,
}

TOOL_SPECS = [
    {"type": "function", "function": {
        "name": "impact_from_column",
        "description": "Downstream blast radius if a column changes (type, unit, semantics, rename, drop). "
                       "Returns impacted columns, models, dashboards, jobs, contracts, tests, owner teams, "
                       "and graph paths as evidence.",
        "parameters": {"type": "object", "properties": {
            "table": {"type": "string", "description": "Table or dbt model name, e.g. stg_orders"},
            "column": {"type": "string", "description": "Column name, e.g. amount"}},
            "required": ["table", "column"]}}},
    {"type": "function", "function": {
        "name": "owners_for_node",
        "description": "Owning team/person for any node (model, table, column, dashboard, job, contract, test, "
                       "incident), with team members and on-call. Accepts an id like model:stg_orders, a column "
                       "fqn like stg_orders.amount, or a name.",
        "parameters": {"type": "object", "properties": {
            "node": {"type": "string"}}, "required": ["node"]}}},
    {"type": "function", "function": {
        "name": "paths_explain",
        "description": "Explain how two nodes are connected in the lineage graph: up to k shortest paths with "
                       "edge directions.",
        "parameters": {"type": "object", "properties": {
            "source": {"type": "string"}, "target": {"type": "string"},
            "k": {"type": "integer", "default": 3},
            "include_ownership": {"type": "boolean", "default": False}},
            "required": ["source", "target"]}}},
]
