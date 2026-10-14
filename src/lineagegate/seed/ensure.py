"""Seed the configured graph only if it is missing or empty (used at container start)."""
from lineagegate import config
from lineagegate.graph.client import db
from lineagegate.seed.load import load


def main() -> None:
    name = config.GRAPH_NAME
    if name in db().list_graphs():
        n = db().select_graph(name).ro_query("MATCH (n) RETURN count(n)").result_set[0][0]
        if n:
            print(f"graph '{name}' present with {n} nodes; skipping seed")
            return
    s = load(name)
    print(f"seeded graph '{name}': {s['node_count']} nodes, {s['edge_count']} edges")


if __name__ == "__main__":
    main()
