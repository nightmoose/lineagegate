# AI assistance disclosure

LineageGate was built during the WeMakeDevs **Graph Hacks: Context for AI Agents** hackathon
(Oct 14–18, 2026) with help from AI coding assistants (Grok-based agents) for scaffolding,
Cypher drafting, tests, and documentation. Design decisions, data model, and review are the author's.

- All FalkorDB-related application code in this repository was written during the event window
  (hacking opened Oct 14, 2026, 2:31 PM ET).
- The demo dataset ("Acme Analytics") is entirely synthetic: no real people, companies, customers,
  or production systems.
- Runtime LLM use is optional; the `ask` command calls an OpenAI-compatible API only if a key is configured.
