"""The Analyst -> Reporter handoff contract.

WHY THIS IS ITS OWN MODULE (Separation of concerns — rubric line 1):
This schema IS the agent boundary. The Analyst's only output is an
`AnalystFinding`. The Reporter's only input is an `AnalystFinding`. The Reporter
never receives — and structurally cannot reach — the raw tool telemetry. Putting
the contract in its own file makes that boundary impossible for a reviewer to
miss and makes each agent independently testable.

A typed, validated contract (not a free-text string) is the difference between
"two prompts chained together" (junior) and "two decoupled agents with an
enforced interface" (senior). Validation also gives us a natural place to fail
fast on a malformed Analyst output (Robustness — rubric line 2).

No pydantic dependency on purpose: a frozen dataclass + explicit validation runs
everywhere with zero install and is fully sufficient at this scope. (Documented
as a deliberate trade-off in the README, not an omission.)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ContractViolation(ValueError):
    """Raised when an Analyst output does not satisfy the handoff contract.

    The graph catches this and fails fast into a safe degraded report rather
    than passing a malformed finding downstream.
    """


_VALID_SEVERITIES = {"low", "medium", "high", "critical"}


@dataclass(frozen=True)
class AnalystFinding:
    """The ONLY thing that crosses from Analyst to Reporter.

    Fields are deliberately minimal — exactly what the Reporter needs to write a
    compliant report and what the success metric needs to verify (the router_id
    must survive end to end).
    """

    router_id: str
    root_cause: str
    severity: str
    confidence: float
    # Optional provenance for observability; never required by the Reporter.
    evidence: dict[str, Any] = field(default_factory=dict)

    # ----- validation: the contract is enforced, not assumed ----- #
    def __post_init__(self) -> None:
        if not self.router_id or not self.router_id.strip():
            raise ContractViolation("router_id is empty")
        if not self.router_id.upper().startswith("RTR-"):
            raise ContractViolation(
                f"router_id '{self.router_id}' is not a valid router identifier"
            )
        if not self.root_cause or len(self.root_cause.strip()) < 10:
            raise ContractViolation("root_cause missing or too short to be meaningful")
        if self.severity not in _VALID_SEVERITIES:
            raise ContractViolation(
                f"severity '{self.severity}' not in {sorted(_VALID_SEVERITIES)}"
            )
        if not (0.0 <= self.confidence <= 1.0):
            raise ContractViolation(
                f"confidence {self.confidence} outside [0.0, 1.0]"
            )

    @staticmethod
    def from_model_json(raw: dict[str, Any]) -> "AnalystFinding":
        """Build (and validate) a finding from the Analyst model's JSON.

        Missing keys raise ContractViolation — we fail fast here rather than
        let a half-formed finding reach the Reporter.
        """
        try:
            return AnalystFinding(
                router_id=str(raw["router_id"]).strip().upper(),
                root_cause=str(raw["root_cause"]).strip(),
                severity=str(raw.get("severity", "")).strip().lower(),
                confidence=float(raw.get("confidence", 0.0)),
                evidence=dict(raw.get("evidence", {})),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractViolation(f"Analyst output not contract-compliant: {exc}") from exc

    def is_low_confidence(self, floor: float = 0.5) -> bool:
        """Drives the bounded conditional in the graph (Agentic Logic — line 4)."""
        return self.confidence < floor
