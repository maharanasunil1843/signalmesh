"""Integration test — verifies the OpenAI provider actually reaches the API.

Skipped automatically when LLM_PROVIDER != openai or OPENAI_API_KEY is unset,
so it is safe to run in CI without a key (it simply reports 'skipped').

Run explicitly with a live key:
    LLM_PROVIDER=openai OPENAI_API_KEY=sk-... pytest -v tests/test_provider_integration.py
Or with a sourced .env:
    set -a && source .env && set +a && pytest -v tests/test_provider_integration.py
"""
from __future__ import annotations

import os
import time

import pytest

_OPENAI_AVAILABLE = (
    os.environ.get("LLM_PROVIDER", "mock").lower() == "openai"
    and bool(os.environ.get("OPENAI_API_KEY", ""))
)

openai_only = pytest.mark.skipif(
    not _OPENAI_AVAILABLE,
    reason="OpenAI provider not configured (set LLM_PROVIDER=openai and OPENAI_API_KEY)",
)

# The mock always returns this for unrecognised prompts — a real model won't.
_MOCK_FALLBACK = "ACK"
# The mock's hardcoded analyst root-cause phrase.
_MOCK_ANALYST_PHRASE = "upstream link saturation"


@openai_only
def test_provider_reaches_api():
    """A direct call to the provider returns a real response, not the mock fallback."""
    from src.provider import OpenAIProvider

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    provider = OpenAIProvider(model)

    t0 = time.perf_counter()
    resp = provider.complete(
        system="You are a test assistant.",
        user="Reply with exactly the word: OPENAI_CONFIRMED",
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert resp.text.strip(), "empty response — API call may have failed silently"
    assert resp.text.strip() != _MOCK_FALLBACK, "got mock fallback, not a real API response"
    assert elapsed_ms > 200, (
        f"response in {elapsed_ms:.0f}ms — suspiciously fast for a real network call; "
        "mock provider returns in <10ms"
    )
    assert resp.model == model
    assert resp.latency_ms > 0


@openai_only
def test_full_triage_uses_openai_not_mock():
    """End-to-end triage with the OpenAI provider produces non-mock output.

    The mock analyst always emits 'upstream link saturation' as the root cause.
    A real LLM reasons over the actual telemetry numbers and produces different prose.
    """
    from src.graph import triage
    from src.provider import OpenAIProvider

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    provider = OpenAIProvider(model)

    state = triage(provider, "incident-42")

    report = state.get("report") or ""
    assert report, "no report produced"
    assert state.get("finding") is not None, "no finding — triage failed entirely"

    # The mock reporter always outputs plain-text with this exact phrase.
    # A real LLM will describe what it actually sees in the telemetry.
    assert _MOCK_ANALYST_PHRASE not in report.lower(), (
        "report contains the mock's hardcoded phrase — likely fell back to MockProvider"
    )


@openai_only
def test_provider_error_on_bad_key():
    """A wrong key raises ProviderError (not a raw OpenAI SDK exception)."""
    from src.provider import OpenAIProvider, ProviderError

    bad = OpenAIProvider.__new__(OpenAIProvider)
    bad._model = "gpt-4o-mini"
    bad._key = "sk-bad-key"

    with pytest.raises(ProviderError):
        bad.complete("system", "user")
