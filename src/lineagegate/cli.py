"""LineageGate CLI.

  lineagegate generate            # rebuild data/*.csv from the synthetic spec
  lineagegate seed                # drop + load the graph from data/
  lineagegate stats               # node / edge counts by label / type
  lineagegate impact stg_orders.amount
  lineagegate owners stg_orders.amount
  lineagegate path stg_orders.amount dashboard:finance.revenue_daily
  lineagegate ask "What breaks if stg_orders.amount changes?"
"""
from __future__ import annotations

import argparse
import json
import sys

from lineagegate import config


def _print_json(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lineagegate", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--graph", default=None, help=f"graph name (default {config.GRAPH_NAME})")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("generate")
    sub.add_parser("seed")
    sub.add_parser("stats")
    p = sub.add_parser("impact"); p.add_argument("column", help="table.column, e.g. stg_orders.amount")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("owners"); p.add_argument("node"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("path"); p.add_argument("source"); p.add_argument("target")
    p.add_argument("-k", type=int, default=3); p.add_argument("--json", action="store_true")
    p = sub.add_parser("ask"); p.add_argument("question", nargs="+")
    p.add_argument("--offline", action="store_true", help="skip the LLM even if a key is set")
    p.add_argument("--show-tools", action="store_true", help="print tool calls + args")
    args = ap.parse_args(argv)

    if args.graph:
        config.GRAPH_NAME = args.graph

    if args.cmd == "generate":
        from lineagegate.seed.generate import DATA_DIR, write
        n, e = write()
        print(f"wrote {n} nodes, {e} edges to {DATA_DIR}")
        return 0
    if args.cmd == "seed":
        from lineagegate.seed.load import load
        s = load()
        print(f"seeded graph '{s['graph']}': {s['node_count']} nodes, {s['edge_count']} edges")
        print("  nodes:", ", ".join(f"{k}={v}" for k, v in s["nodes_by_label"].items()))
        print("  edges:", ", ".join(f"{k}={v}" for k, v in s["edges_by_type"].items()))
        return 0
    if args.cmd == "stats":
        from lineagegate.seed.load import stats
        _print_json(stats())
        return 0

    from lineagegate.agent.loop import ask, render_impact, render_owners, render_paths
    from lineagegate.tools.lineage import impact_from_column, owners_for_node, paths_explain

    if args.cmd == "impact":
        r = impact_from_column(args.column)
        _print_json(r) if args.json else print(render_impact(r))
        return 0 if r.get("found") else 1
    if args.cmd == "owners":
        r = owners_for_node(args.node)
        _print_json(r) if args.json else print(render_owners(r))
        return 0 if r.get("found") else 1
    if args.cmd == "path":
        r = paths_explain(args.source, args.target, k=args.k)
        _print_json(r) if args.json else print(render_paths(r))
        return 0 if r.get("found") else 1
    if args.cmd == "ask":
        res = ask(" ".join(args.question), offline=args.offline)
        print(f"[mode: {res.mode}]")
        if args.show_tools:
            for c in res.tool_calls:
                print(f"[tool] {c['tool']}({json.dumps(c['args'])})")
        print(res.answer)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
