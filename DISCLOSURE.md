# AI assistance disclosure

LineageGate was built during the WeMakeDevs **Graph Hacks: Context for AI Agents** hackathon
(Oct 14–18, 2026).

## AI coding assistants used

- **Grok (xAI), via Grok-based coding agents:** scaffolding, Cypher drafting, tool and agent code,
  tests, UI, deployment config, and documentation drafts. All output was run, tested against the
  seed graph, and reviewed before commit.

Design decisions (problem choice, graph data model, tool set, evidence-first answers) and final
review are the author's.

## Runtime AI use

- The deployed agent calls **xAI Grok (`grok-4.3`)** through its OpenAI-compatible API for tool
  selection and answer wording. All facts come from FalkorDB tool results.
- Without an API key, a deterministic offline router answers instead (no LLM involved).

## Other notes

- All FalkorDB-related application code in this repository was written during the event window
  (hacking opened Oct 14, 2026, 2:31 PM ET).
- The demo dataset ("Acme Analytics") is entirely synthetic: no real people, companies, customers,
  or production systems.
