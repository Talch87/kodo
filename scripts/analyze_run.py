#!/usr/bin/env python3
"""Analyze kodo JSONL run logs - extract model exchanges, costs, and outcomes.

Usage: python analyze_run.py <logfile.jsonl> [<logfile2.jsonl> ...]
"""

import json
import sys
from collections import defaultdict


def _infer_bucket(agent_name: str) -> str:
    """Infer cost bucket from agent name for older logs without cost_bucket field.

    Claude-backed agents (worker_smart, architect) -> claude_subscription
    Cursor-backed agents (worker_fast, tester, tester_browser) -> cursor_subscription
    """
    name = agent_name.lower()
    if any(k in name for k in ("smart", "architect")):
        return "claude_subscription"
    if any(k in name for k in ("fast", "tester", "browser")):
        return "cursor_subscription"
    return "unknown"


def analyze_log(path: str) -> dict:
    events = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    info = {
        "file": path,
        "num_events": len(events),
        "run_init": None,
        "cli_args": None,
        "run_start": None,
        "cycles": [],
        "exchanges": [],  # agent_run_end events
        "orchestrator_calls": [],  # orchestrator_tool_call events
        "orchestrator_response": None,
        "orchestrator_done": None,
        "errors": [],
        "total_time_s": 0,
        "total_cost_usd": 0,
        "agent_stats": defaultdict(
            lambda: {
                "count": 0,
                "cost": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_time": 0,
                "errors": 0,
                "context_resets": 0,
                "cost_bucket": None,
            }
        ),
        "cost_by_bucket": defaultdict(
            float
        ),  # api / claude_subscription / cursor_subscription
    }

    for e in events:
        ev = e.get("event")
        if ev == "run_init":
            info["run_init"] = e
        elif ev == "cli_args":
            info["cli_args"] = e
        elif ev == "run_start":
            info["run_start"] = e
        elif ev in ("run_cycle", "cycle_start"):
            info["cycles"].append(e)
        elif ev == "orchestrator_tool_call":
            info["orchestrator_calls"].append(e)
        elif ev == "agent_run_end":
            info["exchanges"].append(e)
            agent = e.get("agent", "unknown")
            s = info["agent_stats"][agent]
            s["count"] += 1
            s["cost"] += e.get("cost_usd") or 0
            s["input_tokens"] += e.get("input_tokens") or 0
            s["output_tokens"] += e.get("output_tokens") or 0
            s["total_time"] += e.get("elapsed_s") or 0
            if e.get("is_error"):
                s["errors"] += 1
                info["errors"].append(e)
            if e.get("context_reset"):
                s["context_resets"] += 1
            bucket = e.get("cost_bucket") or _infer_bucket(agent)
            s["cost_bucket"] = bucket
            info["cost_by_bucket"][bucket] += e.get("cost_usd") or 0
            info["total_cost_usd"] += e.get("cost_usd") or 0
        elif ev == "cycle_end":
            bucket = e.get("cost_bucket", "api")
            info["cost_by_bucket"][bucket] += e.get("cost_usd") or 0
        elif ev == "orchestrator_response":
            info["orchestrator_response"] = e
            info["total_cost_usd"] += e.get("cost_usd") or 0
        elif ev == "orchestrator_done":
            info["orchestrator_done"] = e

    if events:
        info["total_time_s"] = events[-1].get("t", 0)

    return info


def fmt_time(s):
    if s < 60:
        return f"{s:.1f}s"
    m = int(s // 60)
    sec = s % 60
    if m < 60:
        return f"{m}m {sec:.0f}s"
    h = m // 60
    rm = m % 60
    return f"{h}h {rm}m"


def fmt_tokens(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def print_report(info):
    print("=" * 80)
    print(f"LOG FILE: {info['file']}")
    print("=" * 80)

    # Run config
    start = info["run_start"]
    if start:
        print(f"\nOrchestrator: {start.get('orchestrator', '?')}")
        print(f"Model:        {start.get('model', '?')}")
        print(f"Max exchanges: {start.get('max_exchanges', '?')}")
        print(f"Max cycles:    {start.get('max_cycles', '?')}")
        if start.get("team"):
            print("Team:")
            team = start["team"]
            if isinstance(team, dict):
                for name, cfg in team.items():
                    model = cfg.get("model", "?") if isinstance(cfg, dict) else "?"
                    print(f"  {name}: {model}")
            elif isinstance(team, list):
                for entry in team:
                    if isinstance(entry, dict):
                        print(f"  {entry.get('name', '?')}: {entry.get('model', '?')}")
                    else:
                        print(f"  {entry}")

    args = info["cli_args"]
    if args:
        goal = args.get("goal_text", "")
        if len(goal) > 200:
            goal = goal[:200] + "..."
        print(f"\nGoal: {goal}")

    init = info["run_init"]
    if init:
        print(f"Project: {init.get('project_dir', '?')}")
        print(f"Version: {init.get('version', '?')}")

    # Summary stats
    print("\n--- SUMMARY ---")
    print(f"Total time:        {fmt_time(info['total_time_s'])}")
    print(f"Total cost:        ${info['total_cost_usd']:.4f}")
    print(f"Total exchanges:   {len(info['exchanges'])}")
    print(f"Orchestrator calls: {len(info['orchestrator_calls'])}")
    print(f"Cycles:            {len(info['cycles'])}")
    print(f"Errors:            {len(info['errors'])}")
    print(f"Raw events:        {info['num_events']}")

    total_in = sum(s["input_tokens"] for s in info["agent_stats"].values())
    total_out = sum(s["output_tokens"] for s in info["agent_stats"].values())
    print(f"Total tokens:      in:{fmt_tokens(total_in)}  out:{fmt_tokens(total_out)}")

    # Cost by billing bucket
    buckets = info["cost_by_bucket"]
    if buckets:
        print("\n--- COST BY BILLING BUCKET ---")
        for bucket, cost in sorted(buckets.items()):
            label = bucket.replace("_", " ").title()
            print(f"  {label:<25} ${cost:.4f}")
        api_cost = buckets.get("api", 0)
        sub_cost = sum(v for k, v in buckets.items() if k != "api")
        print(f"  {'':25} -------")
        print(f"  {'Real API spend':<25} ${api_cost:.4f}")
        print(f"  {'Subscription (flat rate)':<25} ${sub_cost:.4f}")

    # Per-agent breakdown
    print("\n--- AGENT BREAKDOWN ---")
    print(
        f"{'Agent':<25} {'Bucket':<18} {'Calls':>5} {'Cost':>10} {'In Tok':>10} {'Out Tok':>10} {'Time':>10} {'Err':>4} {'CtxRst':>6}"
    )
    print("-" * 105)
    for agent, s in sorted(info["agent_stats"].items()):
        bucket = (s.get("cost_bucket") or "?").replace("_", " ")
        print(
            f"{agent:<25} {bucket:<18} {s['count']:>5} ${s['cost']:>9.4f} {fmt_tokens(s['input_tokens']):>10} {fmt_tokens(s['output_tokens']):>10} {fmt_time(s['total_time']):>10} {s['errors']:>4} {s['context_resets']:>6}"
        )

    # Orchestrator cost
    orch = info["orchestrator_response"]
    if orch:
        print(f"\nOrchestrator cost:   ${orch.get('cost_usd', 0):.4f}")
        print(f"Orchestrator turns:  {orch.get('num_turns', '?')}")

    # Exchange timeline (condensed)
    print("\n--- EXCHANGE TIMELINE ---")
    for i, call in enumerate(info["orchestrator_calls"]):
        agent = call.get("agent", "?")
        task = call.get("task", "")
        if len(task) > 120:
            task = task[:120] + "..."
        t = call.get("t", 0)
        print(f"\n[{fmt_time(t)}] Orchestrator -> {agent}")
        print(f"  Task: {task}")

        # Find matching agent_run_end
        matching = [
            e
            for e in info["exchanges"]
            if e.get("agent") == agent and e.get("t", 0) >= t
        ]
        if matching:
            resp = matching[0]
            resp_text = resp.get("response_text", "")
            if len(resp_text) > 200:
                resp_text = resp_text[:200] + "..."
            cost = resp.get("cost_usd") or 0
            elapsed = resp.get("elapsed_s") or 0
            print(
                f"  [{fmt_time(resp.get('t') or 0)}] {agent} responded"
                f" (${cost:.4f},"
                f" {resp.get('turns', '?')} turns,"
                f" {fmt_time(elapsed)})"
            )
            if resp.get("is_error"):
                print("  ** ERROR **")
            if resp_text:
                print(f"  Response: {resp_text}")

    # Final outcome
    done = info["orchestrator_done"]
    if done:
        print("\n--- OUTCOME ---")
        print(f"Success: {done.get('success', '?')}")
        summary = done.get("summary", "")
        if len(summary) > 500:
            summary = summary[:500] + "..."
        print(f"Summary: {summary}")

    if orch:
        result = orch.get("result_text", "")
        if result:
            if len(result) > 1000:
                result = result[:1000] + "..."
            print("\n--- FINAL RESULT ---")
            print(result)

    print()


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <logfile.jsonl> [<logfile2.jsonl> ...]")
        sys.exit(1)

    for path in sys.argv[1:]:
        info = analyze_log(path)
        print_report(info)


if __name__ == "__main__":
    main()
