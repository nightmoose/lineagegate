# Cypher the agent depends on

All tools live in `src/lineagegate/tools/lineage.py` and are parameterised (no string-built Cypher
from the LLM). Paths are projected server-side into plain maps:

```cypher
[n IN nodes(p) | {id: n.id, label: labels(n)[0], name: coalesce(n.fqn, n.name)}] AS pnodes,
[r IN relationships(p) | {type: type(r), src: startNode(r).id, dst: endNode(r).id}] AS prels
```

## impact_from_column(table, column)

Column-precise blast radius: walk column lineage downstream (incoming `DEPENDS_ON`, 0..8 hops), then
one `HAS_COLUMN` hop to the owning model, then `DISPLAYS` (dashboards) / `REFRESHES` (jobs).
The shortest path per impacted asset is kept as evidence.

```cypher
MATCH (c:Column {fqn: $fqn})
MATCH p = (c)<-[:DEPENDS_ON*0..8]-(:Column)<-[:HAS_COLUMN]-(:Model)<-[:DISPLAYS]-(d:Dashboard)
RETURN d.id, d.name, length(p) AS hops, pnodes, prels
ORDER BY hops
```

Also: impacted columns, contracts (`GOVERNED_BY` on impacted columns/models), tests (`READS_FROM`
impacted assets), and owner teams (`OWNED_BY` on impacted models/dashboards).

## owners_for_node(node)

Direct owners first; columns inherit from their table/model; tests inherit from what they check.

```cypher
MATCH (n {id: $id})
MATCH p = (n)<-[:HAS_COLUMN*0..1]-()-[:OWNED_BY]->(o)
RETURN o.id, labels(o)[0], o.name, length(p) - 1 AS inherited, pnodes, prels
```

Then `(:Person)-[:MEMBER_OF]->(team)` for members / on-call.

## paths_explain(source, target)

FalkorDB built-in pathfinding, k shortest paths, either direction, lineage relationship types only
(ownership edges optional so paths stay meaningful):

```cypher
MATCH (a {id: $src}), (b {id: $dst})
CALL algo.SPpaths({sourceNode: a, targetNode: b, relTypes: $rel_types, relDirection: 'both',
                   maxLen: $max_hops, pathCount: $k})
YIELD path, pathWeight
WITH path AS p, pathWeight
RETURN length(p) AS hops, pnodes, prels ORDER BY hops
```

Fallback: `RETURN shortestPath((a)-[*..8]-(b))`.

## Planned (Day 2+)

- `triage_failed_job(job)`: failed job → refreshed models → upstream contracts/tests → related incidents.
- `similar_incidents(...)`: incidents sharing violated contracts / triggering jobs (`RELATED_TO` memory).
- `critical_assets()`: `algo.pageRank` / betweenness over lineage edges.
