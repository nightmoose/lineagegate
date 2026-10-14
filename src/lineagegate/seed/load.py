"""Load data/*.csv into a fresh FalkorDB graph (drops the graph first)."""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from lineagegate import config
from lineagegate.graph.client import db
from lineagegate.seed.generate import DATA_DIR

INDEXED_LABELS = ["Source", "Table", "Column", "Model", "Contract", "Test", "Job",
                  "Dashboard", "Person", "Team", "Incident"]


def _coerce(v: str):
    if v == "":
        return None
    if v in ("true", "false"):
        return v == "true"
    return v


def _rows(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return [{k: _coerce(v) for k, v in r.items() if _coerce(v) is not None} for r in csv.DictReader(f)]


def load(graph_name: str | None = None, data_dir: Path = DATA_DIR) -> dict:
    name = graph_name or config.GRAPH_NAME
    client = db()
    if name in client.list_graphs():
        client.select_graph(name).delete()
    g = client.select_graph(name)

    n_nodes = 0
    for path in sorted(data_dir.glob("nodes_*.csv")):
        label = path.stem.removeprefix("nodes_")
        rows = _rows(path)
        g.query(f"UNWIND $rows AS row CREATE (n:{label}) SET n = row", {"rows": rows})
        n_nodes += len(rows)

    for label in INDEXED_LABELS:
        g.query(f"CREATE INDEX FOR (n:{label}) ON (n.id)")
    g.query("CREATE INDEX FOR (n:Column) ON (n.fqn)")

    n_edges = 0
    for path in sorted(data_dir.glob("edges_*.csv")):
        rel = path.stem.removeprefix("edges_")
        groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for r in _rows(path):
            sl, dl = r.pop("src_label"), r.pop("dst_label")
            src, dst = r.pop("src"), r.pop("dst")
            groups[(sl, dl)].append({"src": src, "dst": dst, "props": r})
        for (sl, dl), rows in groups.items():
            res = g.query(
                f"UNWIND $rows AS row "
                f"MATCH (a:{sl} {{id: row.src}}), (b:{dl} {{id: row.dst}}) "
                f"CREATE (a)-[r:{rel}]->(b) SET r = row.props",
                {"rows": rows},
            )
            created = res.relationships_created
            if created != len(rows):
                raise RuntimeError(f"{rel} {sl}->{dl}: created {created} of {len(rows)} edges")
            n_edges += created

    return {"graph": name, "nodes": n_nodes, "edges": n_edges, **stats(name)}


def stats(graph_name: str | None = None) -> dict:
    g = db().select_graph(graph_name or config.GRAPH_NAME)
    labels = g.ro_query("MATCH (n) RETURN labels(n)[0] AS l, count(*) ORDER BY l").result_set
    rels = g.ro_query("MATCH ()-[r]->() RETURN type(r) AS t, count(*) ORDER BY t").result_set
    return {
        "node_count": sum(c for _, c in labels),
        "edge_count": sum(c for _, c in rels),
        "nodes_by_label": dict(labels),
        "edges_by_type": dict(rels),
    }
