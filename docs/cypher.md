# Cypher the agent depends on

All tools live in `src/lineagegate/tools/lineage.py` and `src/lineagegate/tools/ops.py` and are parameterised (no string-built Cypher
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

## triage_failed_job(job)

```cypher
MATCH (:Job {id:$id})-[:REFRESHES]->(m:Model)
MATCH (t:Test)-[:READS_FROM]->(x) WHERE x = m OR (m)-[:HAS_COLUMN]->(x)   // failing tests
MATCH p = (:Job {id:$id})-[:REFRESHES]->(:Model)-[:DEPENDS_ON*0..8]->(:Model)
          -[:READS_FROM]->(:Table)<-[:WRITES_TO]-(uj:Job)                 // upstream ingestion paths
```
Plus upstream contracts (`GOVERNED_BY`), downstream dashboards (`<-[:DEPENDS_ON*0..8]-()<-[:DISPLAYS]-`),
owner/on-call, and `similar_incidents` anchored on the job.

## similar_incidents(node, text)

```cypher
MATCH (a {id:$id}), (i:Incident) WHERE i <> a
WITH i, shortestPath((a)-[:DEPENDS_ON|READS_FROM|WRITES_TO|REFRESHES|HAS_COLUMN|GOVERNED_BY|
                          TRIGGERED_BY|VIOLATED|RELATED_TO|DISPLAYS*1..6]-(i)) AS p
WHERE p IS NOT NULL RETURN i.id, length(p), ...
```
Score = 1/hops + keyword overlap with `text`. Ownership edges are excluded so team membership does not
make everything look related. `record_incident` `MERGE`s new `Incident` nodes with `TRIGGERED_BY`,
`VIOLATED`, and `RELATED_TO` edges, so memory persists in FalkorDB across sessions.

## critical_assets(algorithm)

```cypher
CALL algo.pageRank('Model','DEPENDS_ON') YIELD node, score
// or: CALL algo.betweenness({nodeLabels:['Model'], relationshipTypes:['DEPENDS_ON']}) YIELD node, score
```
On the seed both rank `dim_customer` first (the planted hub). Evidence for the top asset: the shortest
path from each dashboard down to it, so the UI can draw *why* it is critical:

```cypher
MATCH p = (d:Dashboard)-[:DISPLAYS]->(:Model)-[:DEPENDS_ON*0..8]->(m:Model {id:$id})
RETURN d.id, pnodes, prels      // shortest kept per dashboard
```

## Guards and suggestions

- **Empty graph:** every tool first runs `MATCH (n) RETURN count(n)`. On 0 it returns
  `{found:false, empty_graph:true}` instead of misleading empty results.
- **Unknown names:** close matches come from the graph itself (all `id` / `fqn` / `name` values, fuzzy
  ranked), plus same-table columns. For example, `stg_ordr.amount` suggests `stg_orders.amount`.
- **Ambiguous names:** `resolve_node` returns every exact name match. Tools return `candidates`, and the
  agent is instructed to ask instead of picking one.
- **No path:** tools return `found:false`. The system prompt forbids inventing nodes or paths, and a
  live test checks that the agent abstains on an unknown column.
