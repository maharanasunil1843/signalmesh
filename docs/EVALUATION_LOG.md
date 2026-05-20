# Evaluation Log

## Task-Success Metric

The brief asks: *did the Reporter's final output include the specific Router ID the Analyst identified?* This is implemented programmatically in `src/success_metric.py` and run via `python main.py --metric`.

```
TASK-SUCCESS METRIC
===================
[PASS] incident-1     router RTR-C present in report      path: analyst#1 -> reporter
[PASS] incident-42    router RTR-A present in report      path: analyst#1 -> reporter
[PASS] incident-777   router RTR-D present in report      path: analyst#1 -> reporter
[PASS] empty          declined safely, no fabricated router  path: analyst#1 -> analyst#2 -> fail_safe
[PASS] malformed      declined safely, no fabricated router  path: analyst#1 -> analyst#2 -> fail_safe
-------------------
SCORE: 5/5 (100%)
```

The metric is **deterministic** under the mock provider, so this result is
reproducible in CI and by a reviewer with no API key.

Note the scoring design: for normal scenarios, success = the Analyst's router id survives end-to-end into the report. For failure scenarios (empty / malformed telemetry), success = the system **declines safely without fabricating a router id**. A triage system that fails honestly is succeeding at the task; the metric reflects that rather than naively demanding a router id in every case.

## Test Suite

`pytest -q` — **16 tests total**.

- **13 run offline** (no API key required): success-metric determinism and per-case structure; handoff-contract rejection of malformed / out-of-range findings; fault injection (total model failure → safe degrade; empty / malformed telemetry → fail-safe with no fabricated router; bounded-retry cap honored; timeout guard fires; `ProviderError` normalization).
- **3 OpenAI integration tests** (`tests/test_provider_integration.py`): verify the live provider actually reaches the API, that an end-to-end triage with OpenAI produces non-mock output, and that a bad key raises `ProviderError`. These auto-skip when `LLM_PROVIDER` is not set to `openai`.

## The "Fail-Fast" Mindset — How This Design Satisfies It

The brief explicitly asks for a design that reflects a fail-fast mindset. This system applies it at every boundary rather than as an afterthought:

1. **Fail fast on bad input, not late on a symptom.** The handoff contract
   validates the Analyst's output at the boundary. A malformed finding raises `ContractViolation` immediately — it never reaches the Reporter to cause an opaque downstream error.

2. **Refuse rather than fabricate.** When telemetry does not permit a real
   router id, the Analyst returns an explicit error instead of a placeholder. In a NOC context, a fabricated identifier propagated into an incident report is a more dangerous failure than an honest "could not determine."

3. **Bounded recovery, never unbounded.** The one conditional re-analysis is hard-capped at a single retry. Unbounded agentic loops are the dominant cost/latency failure mode; the cap fails fast into a safe path instead of retrying indefinitely.

4. **Degrade, don't crash.** Every external call (model, tool) has an explicit failure branch. Total model failure still yields a complete, useful report built from the validated finding — or, when there is no finding, an honest "unresolved — manual investigation required" report. The system never raises to the user.

5. **Failures are observable.** Every decision step emits a structured trace event, so a fail-fast path is visible and debuggable, not silent.

The guiding principle: **detect the failure at the earliest boundary where its meaning is known, convert it into an explicit, typed signal, and degrade to the safest still-useful behavior.**
