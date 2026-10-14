"""Thin tool-calling agent loop.

* With an LLM key (OpenAI-compatible API: xAI, OpenAI, or any LLM_BASE_URL),
  the model chooses among the graph tools and must cite the returned paths.
* Without a key, a deterministic offline router picks the tool from the
  question and renders a templated answer from the tool result, so the demo
  still runs end-to-end against FalkorDB.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from lineagegate.tools import lineage, ops

TOOLS = {**lineage.TOOLS, **ops.TOOLS}
TOOL_SPECS = lineage.TOOL_SPECS + ops.TOOL_SPECS
DEFAULT_XAI_MODEL = "grok-4.3"  # tool-calling capable; override with LLM_MODEL

SYSTEM_PROMPT = """You are LineageGate, a data-reliability assistant for the Acme Analytics warehouse.
You answer ONLY from the lineage + contracts graph stored in FalkorDB, using the tools provided.
Rules:
- Always call a tool before answering questions about impact, ownership, connections, failed jobs,
  past incidents, or which assets are most critical. Prefer triage_failed_job for failures and
  similar_incidents to recall prior incidents (graph memory persists across sessions).
- Only call record_incident when the user explicitly asks to record or log an incident.
- Cite at least one graph path verbatim (the `text` / `path` fields) as evidence.
- Name impacted dashboards, contracts at risk, failing tests, and the owner team / on-call person.
- If a tool returns found=false, an empty result, or no path, say plainly that the graph has no
  evidence for it, offer any did_you_mean / candidates, and STOP. Never invent tables, columns,
  dashboards, owners, or paths that no tool returned.
- If a name is ambiguous, list the candidates and ask which one; do not pick silently.
Keep answers short: a 1-2 sentence verdict, then bullets."""


@dataclass
class AgentResult:
    answer: str
    mode: str
    tool_calls: list[dict] = field(default_factory=list)


def _llm_client():
    """Return (client, model, provider) for the first configured provider, else None."""
    try:
        from openai import OpenAI
    except ImportError:
        return None
    if os.getenv("LLM_API_KEY") and os.getenv("LLM_BASE_URL"):
        return (OpenAI(api_key=os.environ["LLM_API_KEY"], base_url=os.environ["LLM_BASE_URL"]),
                os.getenv("LLM_MODEL", "gpt-4o-mini"), "custom")
    if os.getenv("XAI_API_KEY"):
        return (OpenAI(api_key=os.environ["XAI_API_KEY"], base_url="https://api.x.ai/v1"),
                os.getenv("LLM_MODEL", DEFAULT_XAI_MODEL), "xai")
    if os.getenv("OPENAI_API_KEY"):
        return OpenAI(), os.getenv("LLM_MODEL", "gpt-4o-mini"), "openai"
    if os.getenv("ANTHROPIC_API_KEY"):  # Anthropic's OpenAI-compatible endpoint
        return (OpenAI(api_key=os.environ["ANTHROPIC_API_KEY"], base_url="https://api.anthropic.com/v1/"),
                os.getenv("LLM_MODEL", "claude-sonnet-4-5"), "anthropic")
    return None


def _call_tool(name: str, args: dict) -> dict:
    fn = TOOLS.get(name)
    if fn is None:
        return {"found": False, "error": f"unknown tool {name}"}
    try:
        return fn(**args)
    except Exception as exc:  # surface errors to the model instead of crashing
        return {"found": False, "error": f"{type(exc).__name__}: {exc}"}


def _compact(result: dict) -> dict:
    """Drop bulky fields before sending tool output back to the LLM."""
    out = {k: v for k, v in result.items() if k != "cypher"}
    for p in out.get("paths", []) or []:
        p.pop("nodes", None)
        p.pop("rels", None)
    return out


def run_llm(question: str, max_turns: int = 6) -> AgentResult | None:
    cfg = _llm_client()
    if cfg is None:
        return None
    client, model, provider = cfg
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": question}]
    calls: list[dict] = []
    for _ in range(max_turns):
        try:
            resp = client.chat.completions.create(model=model, messages=messages, tools=TOOL_SPECS,
                                                  timeout=float(os.getenv("LLM_TIMEOUT", "90")))
        except Exception as exc:  # network/auth/model error -> caller falls back offline
            print(f"[llm error: {type(exc).__name__}; falling back to offline router]")
            return None
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return AgentResult(answer=msg.content or "", mode=f"llm:{provider}:{model}", tool_calls=calls)
        messages.append(msg.model_dump(exclude_none=True))
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            result = _call_tool(tc.function.name, args)
            calls.append({"tool": tc.function.name, "args": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": json.dumps(_compact(result), default=str)})
    return AgentResult(answer="(stopped: too many tool turns)", mode=f"llm:{provider}:{model}", tool_calls=calls)


# --------------------------------------------------------------------------
# Offline router (no LLM key): deterministic tool selection + templated answer
# --------------------------------------------------------------------------
_FQN = re.compile(r"\b([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+)\b", re.I)
_ID = re.compile(r"\b((?:column|model|table|dashboard|job|contract|test|person|team|incident|source):[\w.\-]+)", re.I)


def route(question: str) -> tuple[str, dict] | None:
    q = question.lower()
    refs = _ID.findall(question) or _FQN.findall(question)
    if any(w in q for w in ("critical", "pagerank", "central", "most important", "hub", "riskiest")):
        return "critical_assets", {"algorithm": "betweenness" if "betweenness" in q else "pagerank"}
    if any(w in q for w in ("fail", "triage", "broke")):
        m = re.search(r"\b((?:dbt|ingest|refresh)_[a-z0-9_]+)", q)
        return "triage_failed_job", {"job": m.group(1)} if m else {}
    if any(w in q for w in ("incident", "happened before", "seen this", "similar")):
        return "similar_incidents", {"node": refs[0]} if refs else {"text": question}
    if any(w in q for w in ("path", "connected", "connect", "between", "how does", "lead to", "reach")) and len(refs) >= 2:
        return "paths_explain", {"source": refs[0], "target": refs[1]}
    if any(w in q for w in ("who owns", "owner", "own ", "on-call", "on call", "contact")) and refs:
        return "owners_for_node", {"node": refs[0]}
    if refs:
        ref = refs[0].removeprefix("column:")
        if "." in ref:
            table, column = ref.rsplit(".", 1)
            return "impact_from_column", {"table": table, "column": column}
    return None


def render_impact(r: dict) -> str:
    if not r.get("found"):
        if r.get("empty_graph"):
            return r["error"]
        hint = f" Did you mean: {', '.join(r['did_you_mean'])}?" if r.get("did_you_mean") else ""
        return f"I could not find column `{r['column']}` in the lineage graph. {r.get('error', '')}{hint}"
    imp = r["impacted"]
    dashes = imp["dashboards"]
    lines = [
        f"Changing `{r['column']}` ({r['data_type']}, model {r['origin_model']}) reaches "
        f"{len(imp['columns'])} downstream columns, {len(imp['models'])} models and "
        f"{len(dashes)} dashboards.",
        "",
        "Dashboards at risk: " + (", ".join(d["name"] for d in dashes) or "none"),
        "Models: " + ", ".join(m["name"] for m in imp["models"]),
        "Jobs that would carry the change: " + ", ".join(j["name"] for j in imp["jobs"]),
    ]
    if imp["contracts"]:
        lines.append("Contracts at risk: " + "; ".join(
            f"{c['name']} v{c['version']} ({c['spec']}) on {', '.join(c['governs'])}, owner {c['owner_team']}"
            for c in imp["contracts"]))
    if imp["tests"]:
        lines.append("Tests covering impacted assets: " + ", ".join(
            f"{t['name']} [{t['status']}]" for t in imp["tests"]))
    if r["owners"]:
        lines.append("Owner teams to notify: " + "; ".join(
            f"{o['team']} ({len(o['assets'])} assets)" for o in r["owners"]))
    if r["paths"]:
        lines += ["", "Evidence (shortest graph path per dashboard):"]
        lines += [f"  [{p['hops']} hops] {p['text']}" for p in r["paths"]]
    return "\n".join(lines)


def render_owners(r: dict) -> str:
    if not r.get("found"):
        extra = f" Candidates: {', '.join(r['candidates'])}" if r.get("candidates") else ""
        return r.get("error", "not found") + extra
    lines = [f"Owners of {r['node']['id']}:"]
    for o in r["owners"]:
        how = "direct" if o["inherited"] == 0 else "inherited"
        lines.append(f"  - {o['label']} {o['name']} ({how}) evidence: {o['path']}")
        for m in o.get("members", []):
            lines.append(f"      member: {m['name']} - {m['role']} {m['slack']}{' [on-call]' if m.get('on_call') else ''}")
    if r["on_call"]:
        lines.append("On-call now: " + ", ".join(r["on_call"]))
    return "\n".join(lines)


def render_paths(r: dict) -> str:
    if not r.get("found"):
        return r.get("error", "no path") + (f" Candidates: {', '.join(r['candidates'])}" if r.get("candidates") else "")
    lines = [f"{len(r['paths'])} path(s) from {r['source']['id']} to {r['target']['id']} via {r['method']}:"]
    lines += [f"  [{p['hops']} hops] {p['text']}" for p in r["paths"]]
    return "\n".join(lines)


def render_triage(r: dict) -> str:
    if not r.get("found"):
        dym = f" Did you mean: {', '.join(r['did_you_mean'])}?" if r.get("did_you_mean") else ""
        return r.get("error", "not found") + dym + (f" Failed jobs: {', '.join(r['failed_jobs'])}" if r.get("failed_jobs") else "")
    j = r["job"]
    lines = [f"{j['id']} is {j['status']} (last run {j['last_run_at']}): {j.get('last_error') or 'no error text'}"]
    if r["failing_tests"]:
        lines.append("Failing tests: " + ", ".join(f"{t['name']} on {t['on']}" for t in r["failing_tests"]))
    if r["contracts"]:
        lines.append("Contracts in the upstream lineage: " + "; ".join(f"{c['id']} ({c['spec']})" for c in r["contracts"]))
    lines.append("Dashboards at risk: " + (", ".join(r["downstream_dashboards"]) or "none"))
    for o in r["owners"]:
        lines.append(f"Owner: {o['team']} (on-call: {', '.join(o['on_call']) or 'n/a'})")
    if r["similar_incidents"]:
        lines += ["", "Similar past incidents:"]
        for i in r["similar_incidents"]:
            lines.append(f"  {i['id']} [{i['severity']}] {i['title']} -> fix: {i['resolution']}")
            if i.get("graph_path"):
                lines.append(f"      via {i['graph_path']}")
    if r["upstream_ingestion_jobs"]:
        lines += ["", "Upstream ingestion paths:"]
        lines += [f"  [{u['hops']} hops] {u['path']}" for u in r["upstream_ingestion_jobs"]]
    return "\n".join(lines)


def render_incidents(r: dict) -> str:
    if not r.get("found"):
        return r.get("error") or "No similar incidents in graph memory."
    lines = ["Similar incidents:"]
    for i in r["incidents"]:
        lines.append(f"  {i['id']} [{i['severity']}] score {i['score']}: {i['title']}")
        lines.append(f"      root cause: {i['root_cause']}  fix: {i['resolution']}")
        if i.get("graph_path"):
            lines.append(f"      via {i['graph_path']}")
    return "\n".join(lines)


def render_critical(r: dict) -> str:
    if not r.get("found"):
        return r.get("error", "no assets")
    lines = [f"Most critical models by {r['algorithm']} over DEPENDS_ON:"]
    lines += [f"  {i+1}. {a['id']} score {a['score']} - {a['downstream_models']} downstream models, "
              f"{a['dashboards']} dashboards, owner {a['owner_team']}" for i, a in enumerate(r["assets"])]
    if r.get("top_asset_paths"):
        lines += ["", f"Why {r['assets'][0]['id']} matters (dashboards that depend on it):"]
        lines += [f"  [{p['hops']} hops] {p['text']}" for p in r["top_asset_paths"]]
    return "\n".join(lines)


RENDER = {"triage_failed_job": render_triage, "similar_incidents": render_incidents,
          "critical_assets": render_critical, "impact_from_column": render_impact, "owners_for_node": render_owners, "paths_explain": render_paths}


def run_offline(question: str) -> AgentResult:
    picked = route(question)
    if picked is None:
        return AgentResult(
            answer="Offline mode understands: impact of `table.column`, `who owns <node>`, "
                   "`path between <a> and <b>`, failed-job triage, similar incidents, critical assets. Set an LLM key for free-form questions.",
            mode="offline-router")
    name, args = picked
    result = _call_tool(name, args)
    return AgentResult(answer=RENDER[name](result), mode="offline-router",
                       tool_calls=[{"tool": name, "args": args, "result": result}])


def ask(question: str, offline: bool = False) -> AgentResult:
    if not offline:
        res = run_llm(question)
        if res is not None:
            return res
    return run_offline(question)
