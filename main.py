"""Entrypoint — the command a reviewer runs first.

    python main.py                 # default scenario, mock provider, no key
    python main.py --scenario empty
    python main.py --metric        # run the task-success metric

DESIGN INTENT:
First impressions decide take-homes. This must run with zero setup (mock
provider default), print a clean incident report on stdout, and the structured
decision trace on stderr — so `python main.py` "just works" and `python main.py
2>/dev/null` shows only the report.
"""
from __future__ import annotations

import argparse
import sys

from src.graph import triage
from src.observability import Trace
from src.provider import get_provider


def run_once(scenario_id: str) -> int:
    provider = get_provider()
    tr = Trace(run_id=f"triage:{scenario_id}")

    state = triage(provider, scenario_id)

    # Reconstruct structured events from the graph's recorded path.
    for step in state.get("path", []):
        tr.event(step)
    tr.event(
        "result",
        degraded=state.get("degraded", False),
        has_finding=state.get("finding") is not None,
        error=state.get("analyst_error"),
    )

    # Human output -> stdout. Structured trace -> stderr.
    report = state.get("report") or "(no report produced)"
    print(report)
    tr.emit(sys.stderr)

    # Non-zero exit if we could not resolve, so this is CI/script friendly.
    return 0 if state.get("finding") is not None else 2


def run_metric() -> int:
    from src.success_metric import score

    report = score()
    print(report.render())
    return 0 if report.score == 1.0 else 1


def main() -> None:
    ap = argparse.ArgumentParser(description="Multi-agent NOC incident triage")
    ap.add_argument("--scenario", default="default",
                    help="scenario id (try: default, empty, malformed)")
    ap.add_argument("--metric", action="store_true",
                    help="run the task-success metric instead of one triage")
    args = ap.parse_args()

    code = run_metric() if args.metric else run_once(args.scenario)
    sys.exit(code)


if __name__ == "__main__":
    main()
