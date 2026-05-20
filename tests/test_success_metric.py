"""Test: the task-success metric and the handoff contract.

These lock the two things a reviewer most wants reproducible:
  1. the success metric scores 5/5 deterministically (Evaluation — line 5)
  2. the handoff contract actually rejects malformed findings (line 1/2)

Run:  pytest -q
"""
from __future__ import annotations

import pytest

from src.handoff_contract import AnalystFinding, ContractViolation
from src.provider import MockProvider
from src.success_metric import score

# All metric tests must use MockProvider explicitly so they remain deterministic
# regardless of which LLM_PROVIDER is configured in the environment.
_MOCK = MockProvider()


def test_success_metric_is_perfect_and_deterministic():
    """The metric must be 5/5 and identical across runs (mock provider)."""
    r1 = score(_MOCK)
    r2 = score(_MOCK)
    assert r1.score == 1.0, r1.render()
    assert [c.passed for c in r1.results] == [c.passed for c in r2.results]
    assert r1.total == 5


def test_normal_cases_carry_router_id_through():
    """Every 'normal' case must end analyst -> reporter with the router id.

    Assert on path *structure* (a list), not a joined string, so the test
    cannot break on a cosmetic separator change in rendering.
    """
    r = score(_MOCK)
    normals = [c for c in r.results if c.path == ["analyst#1", "reporter"]]
    assert len(normals) == 3, (
        f"expected 3 normal analyst->reporter cases, got {len(normals)}; "
        f"paths were: {[c.path for c in r.results]}"
    )
    assert all(c.passed for c in normals)


def test_failure_cases_decline_without_fabrication():
    """empty/malformed must reach fail_safe and pass (declined safely)."""
    r = score(_MOCK)
    failers = [c for c in r.results if "fail_safe" in c.path]
    assert len(failers) == 2
    assert all(c.passed for c in failers)


def test_contract_rejects_bad_router():
    with pytest.raises(ContractViolation):
        AnalystFinding(router_id="BADID", root_cause="x" * 20,
                       severity="high", confidence=0.9)


def test_contract_rejects_out_of_range_confidence():
    with pytest.raises(ContractViolation):
        AnalystFinding(router_id="RTR-A", root_cause="x" * 20,
                       severity="high", confidence=1.7)


def test_contract_accepts_valid_finding():
    f = AnalystFinding(router_id="RTR-A",
                        root_cause="Upstream saturation causing latency.",
                        severity="high", confidence=0.8)
    assert f.router_id == "RTR-A"
    assert not f.is_low_confidence()
