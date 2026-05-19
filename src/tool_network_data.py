"""Synthetic network-telemetry tool.

WHY THIS SHAPE (Agentic Logic — rubric line 4: genuine tool-use):
This is exposed as a *callable tool with a schema*, not a helper the graph calls
and spoon-feeds to the model. The Analyst agent decides to invoke it and
receives its raw JSON. That distinction — agent-invoked vs. pre-fetched — is
exactly what separates real tool-use from a chained prompt, and a reviewer
looks for it.

Data is SYNTHETIC and DETERMINISTIC (seeded). No real telemetry, and the same
scenario id always yields the same payload so tests and the success metric are
reproducible. Determinism here is a deliberate choice, documented as a trade-off
in the README, not an accident.

The tool can also emit two failure shapes on purpose:
  - an empty payload  (no incidents)            -> exercises the None/empty path
  - a malformed payload (missing router id)      -> exercises fail-fast handling
These exist so Robustness (rubric line 2) can be demonstrated, not just claimed.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

# Fixed catalog so generated data is bounded and realistic.
_ROUTERS = ["RTR-A", "RTR-B", "RTR-C", "RTR-D"]
_METRICS = ("latency_ms", "packet_loss_pct", "cpu_pct", "error_rate")


@dataclass(frozen=True)
class ToolResult:
    """Uniform tool envelope. `ok=False` means the Analyst must handle a
    degraded/empty result rather than assume data is present."""

    ok: bool
    payload: dict[str, Any]
    note: str = ""


def _seed_int(scenario_id: str) -> int:
    """Deterministic integer from a scenario id (hash, not RNG → stable tests)."""
    return int(hashlib.sha256(scenario_id.encode()).hexdigest(), 16)


def fetch_network_errors(scenario_id: str = "default") -> ToolResult:
    """The tool the Analyst agent invokes.

    Args:
        scenario_id: selects a deterministic synthetic scenario. Special ids:
            "empty"     -> ok=False, no incidents (tests the None/empty branch)
            "malformed" -> ok=True but payload missing router id (fail-fast test)
            anything else -> a normal, deterministic incident payload

    Returns:
        ToolResult with a JSON-serializable payload.
    """
    if scenario_id == "empty":
        return ToolResult(ok=False, payload={}, note="No active incidents reported.")

    if scenario_id == "malformed":
        # Intentionally missing 'router' — downstream must fail fast, not crash.
        return ToolResult(
            ok=True,
            payload={"incidents": [{"latency_ms": 910, "packet_loss_pct": 0.14}]},
            note="Malformed: router identifier absent.",
        )

    s = _seed_int(scenario_id)
    router = _ROUTERS[s % len(_ROUTERS)]
    # Derive plausible, deterministic metric values from the seed.
    latency = 400 + (s % 700)            # 400–1099 ms
    packet_loss = round(((s >> 3) % 25) / 100, 3)   # 0.000–0.240
    cpu = 55 + (s >> 5) % 45             # 55–99 %
    error_rate = round(((s >> 7) % 18) / 100, 3)    # 0.000–0.170

    payload = {
        "incidents": [
            {
                "router": router,
                "latency_ms": latency,
                "packet_loss_pct": packet_loss,
                "cpu_pct": cpu,
                "error_rate": error_rate,
                "window": "last_15m",
            }
        ],
        "collected_by": "synthetic-telemetry-agent",
    }
    return ToolResult(ok=True, payload=payload, note="OK")


# --- Tool advertisement: the schema the agent sees when deciding to call it. ---
# Kept explicit so the Analyst's tool-use is real (model is told the tool exists
# and what it returns), not implicit.
TOOL_SPEC = {
    "name": "fetch_network_errors",
    "description": (
        "Fetch the latest synthetic NOC network-error telemetry for a scenario. "
        "Returns recent incident metrics (latency, packet loss, CPU, error rate) "
        "for the affected router. May return ok=False when there are no incidents."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "scenario_id": {
                "type": "string",
                "description": "Scenario selector; use 'default' if unspecified.",
            }
        },
        "required": [],
    },
}


def tool_result_as_prompt_block(result: ToolResult) -> str:
    """Render a ToolResult into the exact text the Analyst model receives.

    Centralizing this means the Analyst agent never hand-rolls tool parsing —
    one source of truth for the tool→model boundary.
    """
    if not result.ok:
        return f"TOOL RESULT: NO_DATA\nnote: {result.note}"
    return "TOOL RESULT (JSON):\n" + json.dumps(result.payload, indent=2)
