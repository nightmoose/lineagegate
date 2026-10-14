"""FalkorDB connection + helpers shared by seed and tools."""
from __future__ import annotations

import difflib
import functools
from functools import lru_cache
from typing import Any

from falkordb import FalkorDB

from lineagegate import config

# Cypher fragments that project a path into plain maps so callers never depend
# on client-side Path decoding. Use as: RETURN {PATH_NODES} AS pnodes, {PATH_RELS} AS prels
PATH_NODES = "[n IN nodes(p) | {id: n.id, label: labels(n)[0], name: coalesce(n.fqn, n.name)}]"
PATH_RELS = "[r IN relationships(p) | {type: type(r), src: startNode(r).id, dst: endNode(r).id}]"


@lru_cache(maxsize=1)
def db() -> FalkorDB:
    return FalkorDB(
        host=config.FALKORDB_HOST,
        port=config.FALKORDB_PORT,
        username=config.FALKORDB_USERNAME,
        password=config.FALKORDB_PASSWORD,
    )


def graph(name: str | None = None):
    return db().select_graph(name or config.GRAPH_NAME)


def ro(query: str, params: dict | None = None, graph_name: str | None = None) -> list[list[Any]]:
    """Run a read-only query and return the raw result rows."""
    return graph(graph_name).ro_query(query, params or {}).result_set


def _to_dict(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: _to_dict(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_to_dict(v) for v in x]
    return x


def make_path(pnodes: list, prels: list) -> dict:
    """Normalise a projected path and render it as an arrow string."""
    pnodes = _to_dict(pnodes)
    prels = _to_dict(prels)
    parts = [node_str(pnodes[0])]
    for i, rel in enumerate(prels):
        here, nxt = pnodes[i], pnodes[i + 1]
        if rel["src"] == here["id"] and rel["dst"] == nxt["id"]:
            parts.append(f"-[:{rel['type']}]->")
        else:
            parts.append(f"<-[:{rel['type']}]-")
        parts.append(node_str(nxt))
    return {"hops": len(prels), "nodes": pnodes, "rels": prels, "text": " ".join(parts)}


def node_str(n: dict) -> str:
    return f"({n['label']} {n['name']})"


def resolve_node(ref: str) -> list[dict]:
    """Resolve a user-supplied reference to node(s).

    Accepts an exact id (``model:stg_orders``), a column fqn
    (``stg_orders.amount``), or a node name (case-insensitive). Returns the
    best matches (exact id/fqn first)."""
    ref = ref.strip()
    rows = ro(
        """
        MATCH (n)
        WHERE n.id = $ref OR n.fqn = $ref OR toLower(n.name) = toLower($ref)
        RETURN n.id, labels(n)[0], n.name,
               CASE WHEN n.id = $ref OR n.fqn = $ref THEN 0 ELSE 1 END AS rank
        ORDER BY rank, n.id
        LIMIT 10
        """,
        {"ref": ref},
    )
    if not rows:
        rows = ro(
            """
            MATCH (n) WHERE toLower(n.id) CONTAINS toLower($ref)
            RETURN n.id, labels(n)[0], n.name, 2 AS rank ORDER BY n.id LIMIT 10
            """,
            {"ref": ref},
        )
    if rows and rows[0][3] == 0:
        rows = [r for r in rows if r[3] == 0]
    return [{"id": r[0], "label": r[1], "name": r[2]} for r in rows]


def node_count(graph_name: str | None = None) -> int:
    try:
        return ro("MATCH (n) RETURN count(n)", graph_name=graph_name)[0][0]
    except Exception:  # graph key does not exist yet
        return 0


EMPTY_GRAPH = {"found": False, "error": "The lineage graph is empty. Run `lineagegate seed` first.",
               "empty_graph": True}


def requires_graph(fn):
    """Tool decorator: return a clear error instead of misleading empty results on an empty graph."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if node_count() == 0:
            return dict(EMPTY_GRAPH)
        return fn(*args, **kwargs)
    return wrapper


def suggest(ref: str, label: str | None = None, n: int = 5) -> list[str]:
    """Close matches for a misspelled reference, drawn from ids/fqns/names in the graph."""
    where = f"WHERE n:{label}" if label else ""
    keys: dict[str, str] = {}
    for nid, fqn, name in ro(f"MATCH (n) {where} RETURN n.id, n.fqn, n.name"):
        for k in (nid, fqn, name, nid.split(":", 1)[-1] if nid else None):
            if k:
                keys.setdefault(k.lower(), fqn or nid)
    ref_l = ref.lower().strip()
    hits = difflib.get_close_matches(ref_l, keys, n=n * 3, cutoff=0.6)
    out: list[str] = []
    for h in hits:
        if keys[h] not in out:
            out.append(keys[h])
    return out[:n]
