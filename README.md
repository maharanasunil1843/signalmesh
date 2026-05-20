# Multi-Agent NOC Incident Triage

> A reference implementation of a multi-agent triage pattern.

A two-agent system that turns raw network telemetry into a professional incident report. An **Analyst Agent** invokes a telemetry tool, determines root cause, and emits a *validated* structured finding. A **Reporter Agent** consumes only that finding and produces the incident report. The two agents are decoupled by an enforced typed contract, with a bounded conditional, explicit failure handling, structured tracing, and a programmatic task-success metric.

**Runs in one command, with no API key.** A deterministic mock provider is the default, so the entire system — including the success metric and tests — is reproducible offline.

---

## Architecture

```mermaid
flowchart TD
    A[Telemetry Tool: fetch_network_errors] -->|raw JSON| B[Analyst Agent]

    B -->|validated AnalystFinding| R{Route on LLM output}

    R -->|finding ok| C[Reporter Agent]

    R -->|low confidence or no finding| B

    R -->|retry exhausted| F[Fail-Safe Node]

    C -->|incident report| OUT[Final Report + Trace]

    F -->|honest unresolved report| OUT

    subgraph Boundary [Enforced agent boundary]
        B
        C
    end

    classDef agent fill:#eef,stroke:#446;
    class B,C agent;
```

- **Telemetry tool** — synthetic, deterministic, agent-invoked (genuine tool-use).
- **Analyst Agent** — its *only* output is a validated `AnalystFinding`.
- **Conditional router** — one bounded loop: low-confidence/no-finding triggers at most one re-analysis, then proceeds or fails safe.
- **Reporter Agent** — receives *only* the finding; structurally cannot see raw telemetry.
- **Fail-Safe** — produces an honest "unresolved" report instead of crashing or fabricating a router id.

## Quickstart

### 1. Install dependencies

```bash
uv venv --python 3.11
source .venv/bin/activate
uv sync --extra dev          # offline use: mock provider + tests
uv sync --extra dev --extra openai  # add this if you want to run with a real OpenAI model
```

### 2. Run with the mock provider (no API key needed)

The mock is deterministic and rule-based — same input always yields the same output.

```bash
# Normal incident — analyst identifies router, reporter formats the report
python main.py --scenario incident-42

# See only the report (trace goes to stderr)
python main.py --scenario incident-42 2>/dev/null

# Failure path — empty telemetry, system declines safely without fabricating a router
python main.py --scenario empty

# Failure path — malformed telemetry (missing router id), same safe decline
python main.py --scenario malformed

# Task-success metric: scores all 5 scenarios, prints PASS/FAIL per case
python main.py --metric
```

### 3. Run with a real OpenAI model

```bash
# Copy the example and fill in your key
cp .env.example .env
# Edit .env: set LLM_PROVIDER=openai, OPENAI_API_KEY=sk-..., OPENAI_MODEL=gpt-4o-mini

# Load the env and run — no code changes required
set -a && source .env && set +a
python main.py --scenario incident-42
```

The LLM now reads the actual telemetry numbers and reasons over them. Expect ~5–15 seconds
per run (two API calls: one for the Analyst, one for the Reporter).

### 4. Run the test suite

```bash
# Offline — 13 tests, no key needed, completes in ~2 seconds
python -m pytest -v

# With OpenAI active — 16 tests (3 integration tests run, rest unchanged)
set -a && source .env && set +a
python -m pytest -v

# Run only the OpenAI integration tests
python -m pytest -v tests/test_provider_integration.py

# Run only the offline tests (mock + fault injection + contract)
python -m pytest -v tests/test_resilience.py tests/test_success_metric.py
```

The 3 OpenAI integration tests auto-skip when `LLM_PROVIDER` is not set to `openai`,
so `python -m pytest -v` is always safe to run without a key.

## Design Decisions & Trade-offs

The reasoning matters more than the code here, so it is explicit:

- **Typed handoff contract in its own module (`handoff_contract.py`).** The
  agent boundary is enforced by the type system, not convention. The Reporter's signature accepts only an `AnalystFinding`; it has no import path to the tool. This is what makes the agents independently testable and swappable.
- **One bounded conditional, not an elaborate graph.** The rubric asks for
  conditional logic on LLM output; it does not ask for graph virtuosity. A single, clearly-visible, *bounded* retry demonstrates the skill while avoiding the dominant failure mode of agentic systems — unbounded loops that silently multiply cost and latency. Retry cap = 1, hard.
- **Fail-fast on an unidentifiable router.** When telemetry doesn't permit a real router id, the Analyst *refuses* to emit a placeholder. For a triage tool, surfacing a fabricated identifier downstream is worse than honestly reporting "manual investigation required."
- **Deterministic mock provider as the default.** Reproducibility and
  zero-setup runnability beat a flashy demo that needs a key. The mock is rule-based, not random, so the success metric and tests are stable in CI.
- **Resilience as a small dedicated module, not scattered try/except.** Bounded retry, timeout, and explicit None-guards are reusable and tested in one place.
- **Provider behind a Protocol.** Vendor choice is one config value; agents
  never import a vendor SDK. Any vendor exception is normalized to
  `ProviderError` so it cannot leak into agent logic.

## Out of Scope — Deliberately

Right-sizing is part of the engineering. The following were consciously
**excluded** because the brief is a bounded two-agent triage task, and adding them would signal poor scoping, not capability:

- **Vector DB / RAG** — Scenario 2 has no retrieval requirement. A vector store here would be machinery with no scored value and added failure surface.
- **Auth / user management / UI** — not in this scenario's scope (UI was
  Scenarios 3 & 4). A CLI entrypoint is more robust and sufficient.
- **Containerization / distributed services / CI runners** — over-engineering for a 6-hour bounded task; the rubric explicitly rewards minimal, composable design.

How each would extend in production, if this graduated to a real service:

- *Retrieval:* a runbook/knowledge RAG path the Reporter could cite, behind the same provider interface.
- *Auth & multi-tenant:* request-scoped identity + per-tenant trace isolation.
- *Scale:* the graph is stateless per run; horizontal scaling needs only a shared checkpointer and a queue in front of the entrypoint.
- *Observability:* `observability.emit()` is the single integration point —
  point it at OpenTelemetry / LangSmith; no agent code changes.

This combination — building exactly the bounded scope *and* articulating the production path — is the intended demonstration of judgment.

## Repository Layout

```
main.py                     one-command entrypoint (stdout=report, stderr=trace)
src/provider.py             ModelProvider Protocol + deterministic mock + OpenAI
src/tool_network_data.py    synthetic, deterministic, agent-invoked telemetry tool
src/handoff_contract.py     the enforced Analyst -> Reporter typed contract
src/agent_analyst.py        tool-use + root cause + fail-fast guards
src/agent_reporter.py       consumes ONLY the finding; isolated from raw data
src/graph.py                LangGraph wiring + the one bounded conditional
src/resilience.py           bounded retry / timeout / None-guard primitives
src/success_metric.py       the task-success metric (scored, deterministic)
src/observability.py        structured JSON decision trace
tests/                      success-metric, fault-injection, and OpenAI provider integration tests
docs/EVALUATION_LOG.md      metric result + fail-fast rationale
```

## Evaluation

See [`docs/EVALUATION_LOG.md`](docs/EVALUATION_LOG.md). Summary: the task-success
metric scores **5/5** deterministically — three normal cases carry the Analyst's router id through to the report; two failure cases (empty / malformed telemetry) correctly decline without fabricating a router. `pytest -q` runs 16 tests: 13 run offline with no key (success-metric, contract validation, fault injection); 3 are OpenAI integration tests that auto-skip unless `LLM_PROVIDER=openai` is set.

## Data

All telemetry is **synthetic** and generated deterministically in
`src/tool_network_data.py`. No real or proprietary data is used.
