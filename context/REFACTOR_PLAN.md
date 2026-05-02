# Refactor Plan: From CLI Library to Agent System

Status: **Plan / not yet implemented**
Branch: `claude/plan-agent-refactor-SCEdC`

## 1. Goal

Transform the repo from a YAML-config CLI tool into an **agent-driven cost
analysis system**. The user's primary interface becomes a chat with Claude.
Claude:

1. Surveys the user's situation/goals via a **questionnaire tool**.
2. Fetches **market data** (rate curve, inflation expectations, typical
   maintenance/insurance reference values) via tools.
3. Assembles `CondoParams` / `HouseParams` / `SimulationParams` /
   `EconomicParams` from those inputs.
4. Runs the existing `compute_deterministic` and `run_monte_carlo` engines as
   tools.
5. Produces a tailored narrative + numbers, with the option to drill into
   sensitivities and what-ifs.

The compute core (`pv.py`, `deterministic.py`, `monte_carlo.py`, `models.py`)
stays as-is. The agent layer wraps it.

## 2. Target User Flow

```
User: "I'm comparing a $480k condo with $520/mo HOA against a $620k house
       in the Boston suburbs. Help me think through 25-year cost."

Claude (intake tool): asks for missing facts — horizon, time-on-property
                      assumption, whether HOA includes insurance, age of
                      house, special assessments history, risk tolerance,
                      etc. Stops when it has enough.

Claude (market tools): fetches current 10y/30y Treasury, 30y mortgage rate,
                       headline + core CPI, 5y/10y breakevens, regional
                       maintenance benchmarks.

Claude (param assembly): builds a CondoParams/HouseParams set, with
                         provenance comments per field ("discount_rate=
                         0.041 from 10y Treasury 2026-05-02").

Claude (run_simulation tool): runs deterministic + Monte Carlo.

Claude (response): narrative + headline numbers + a follow-up offer
                   ("Want me to stress the HOA escalation rate?").
```

## 3. Architecture After Refactor

```
src/cvh_cost/
├── core/                         # (renamed) pure compute layer, untouched logic
│   ├── __init__.py
│   ├── models.py                 # moved from cvh_cost/models.py
│   ├── pv.py
│   ├── deterministic.py
│   ├── monte_carlo.py
│   └── reporting.py              # text/plot helpers stay here
│
├── config/                       # (renamed) YAML loader, kept as power-user path
│   ├── __init__.py
│   └── yaml_config.py            # was cvh_cost/config.py
│
├── agent/                        # NEW
│   ├── __init__.py
│   ├── system_prompt.py          # the orchestrator persona
│   ├── runner.py                 # entrypoint: launches the agent loop
│   ├── intake.py                 # questionnaire tool + schema
│   ├── market.py                 # market-data tools
│   ├── analysis.py               # wraps compute_deterministic / run_monte_carlo
│   ├── assemble.py               # builds dataclasses from intake + market state
│   ├── session.py                # in-memory state shared across tool calls
│   └── tools.py                  # MCP/SDK tool registration table
│
├── cli.py                        # back-compat: old YAML CLI still runs
└── chat.py                       # NEW: `python -m cvh_cost.chat` agent CLI
```

Notes:
- The `cvh_cost/` import path stays; we re-export the public surface from
  `cvh_cost/__init__.py` so existing notebooks and tests keep working.
- The split of `core/` vs `agent/` makes the boundary explicit: anything in
  `core/` is deterministic Python; anything in `agent/` may call out to LLMs,
  the network, or the user.

## 4. Tools to Expose

These are the tools Claude will see. Each is registered through the Claude
Agent SDK tool surface.

### 4.1 Intake / Questionnaire

| Tool | Input | Output | Purpose |
|---|---|---|---|
| `ask_user_questions` | `questions: list[Question]` (id, prompt, type, choices?, required?) | `answers: dict[id, value]` | Batch-ask the user one or more structured questions. The agent must batch — round-tripping single questions is wasteful. |
| `read_intake_state` | — | full intake dict | Lets Claude inspect what it already knows before deciding what else to ask. |
| `set_intake_field` | `key, value, source` | ack | Lets Claude record a fact derived from free-form chat (not just from tool answers). |

`Question` schema covers: `text`, `numeric`, `currency`, `percent`, `single_choice`, `multi_choice`, `year`, `boolean`. Validation lives in `agent/intake.py`.

Initial canonical question bank (Claude can pick subsets):

- Horizon (years), expected length of stay
- Discount-rate preference: market rate vs. user opportunity cost
- Condo: price, monthly HOA, what HOA covers, fee history, reserve study summary, special assessment history
- House: price, year built, recent inspection findings, lot size, region (for benchmarks)
- Insurance, taxes (treated as `RecurringOtherCost`)
- Risk tolerance / which percentile the user cares about (drives MC reporting)

### 4.2 Market Data

| Tool | Input | Output | Source |
|---|---|---|---|
| `fetch_rate_curve` | `as_of?: date` | `{tenor: yield}` for 1m–30y | Treasury par yield curve (Treasury.gov daily CSV). |
| `fetch_mortgage_rate` | `term: 15\|30, as_of?` | rate | Freddie Mac PMMS or FRED (`MORTGAGE30US`). |
| `fetch_inflation_expectations` | `as_of?` | `{cpi_yoy, core_cpi_yoy, breakeven_5y, breakeven_10y}` | FRED (`CPIAUCSL`, `CPILFESL`, `T5YIE`, `T10YIE`). |
| `fetch_regional_benchmarks` | `region, property_type` | `{maintenance_pct, insurance_annual, ...}` | Static seed table to start; can later pull from external data. |
| `recommend_discount_rate` | intake snapshot | `{rate, rationale}` | Pure helper that turns curve + horizon + mode into a rate suggestion. |

All market tools cache to `~/.cache/cvh_cost/<source>-<date>.json` to keep
latencies down inside a session and to give us deterministic replays.

### 4.3 Analysis

| Tool | Input | Output | Purpose |
|---|---|---|---|
| `assemble_params` | — | `{condo, house, sim, econ}` JSON | Snapshot the dataclasses that would be used for simulation. Lets Claude review before committing. |
| `run_deterministic` | optional override patches | `DeterministicResult` JSON | Wraps `compute_deterministic`. |
| `run_monte_carlo` | optional override patches + `num_sims?` | `MonteCarloResult` summary JSON (no full arrays) + a result handle | Wraps `run_monte_carlo`. Full arrays kept server-side. |
| `summarize_results` | result handle | text report | Wraps `format_text_report`. |
| `plot_results` | result handle, plot_kind | path to PNG | Wraps the `plot_*` functions. |
| `run_sensitivity` | param_path, values | sweep results | Reruns MC across a 1-D sweep of one parameter. |

The "result handle" pattern keeps large numpy arrays out of the LLM's context
window. The session stores them, the LLM only sees summaries.

## 5. Session State

`agent/session.py` holds a single object across the run:

```python
@dataclass
class AgentSession:
    intake: dict[str, Any]                       # raw answers, keyed by question id
    market: dict[str, Any]                       # cached fetches, keyed by source
    params: AssembledParams | None               # built dataclasses
    last_results: dict[str, AnalysisArtifact]    # result handles
    transcript: list[dict]                       # for audit / replay
```

Tools read/write this object. The agent loop is constructed around it. Result
artifacts include the params snapshot they were computed from so the user can
always trace a number back to its inputs.

## 6. SDK Integration

- Use the **Claude Agent SDK for Python** (`claude-agent-sdk`).
- Default model: `claude-sonnet-4-6` for cost; allow overriding to
  `claude-opus-4-7` via env var for hard cases.
- Tools are registered as in-process Python callables (no separate MCP server
  for v1).
- System prompt lives in `agent/system_prompt.py`. Key rules in the prompt:
  1. Never fabricate market numbers — always use a fetch tool.
  2. Always show the user the assembled params before running a heavy MC.
  3. Cite the source for every numeric assumption in the final report.
  4. Prefer batched `ask_user_questions` over chatty back-and-forth.

## 7. Migration Phases

### Phase 1 — Reorganize without behavior change
- Move `models.py`, `pv.py`, `deterministic.py`, `monte_carlo.py`,
  `reporting.py` into `cvh_cost/core/`.
- Move `config.py` into `cvh_cost/config/yaml_config.py`.
- Update `cvh_cost/__init__.py` to re-export the same names from the new
  paths so external imports don't break.
- Run `pytest` — should be green with zero test edits.

### Phase 2 — Build the session + analysis tools
- `agent/session.py` and `agent/analysis.py`.
- Wrap `compute_deterministic` / `run_monte_carlo` / `format_text_report`
  with JSON-friendly signatures and result handles.
- Unit tests: confirm wrapping preserves outputs vs. the underlying engines.

### Phase 3 — Intake tool + assembly
- `agent/intake.py` with the question schema and validators.
- `agent/assemble.py` that maps intake answers → dataclasses, with a
  `set_intake_field` path for facts pulled from free-form chat.
- Tests: feed canned answer dicts, assert dataclasses match expected.

### Phase 4 — Market tools
- `agent/market.py`: Treasury curve, FRED rates/inflation, mortgage rate,
  static regional benchmarks.
- All fetches go through a thin caching wrapper keyed by `(source, as_of)`.
- Add a `--offline` mode that uses only fixtures (for tests + CI).
- Tests: mock HTTP layer, verify cache hits don't re-fetch.

### Phase 5 — Wire the agent
- `agent/runner.py` builds the SDK client, registers tools, holds the loop.
- `cvh_cost/chat.py` is the new top-level CLI: `python -m cvh_cost.chat`.
- System prompt + an integration test that runs a scripted intake → MC end
  to end against a recorded fixture.

### Phase 6 — Polish
- Update README to lead with the chat flow; demote YAML to "advanced usage."
- Keep the old CLI working but link to chat as the recommended path.
- Add a notebook `notebooks/agent_walkthrough.ipynb` mirroring a chat
  session for documentation.

Each phase is independently committable and the existing tests should remain
green throughout.

## 8. Backwards Compatibility / Non-Goals

**Kept:**
- All public functions in `cvh_cost.__init__` (`compute_deterministic`,
  `run_monte_carlo`, `load_config`, etc.) keep their signatures.
- `python -m cvh_cost.cli config.yaml` still works.
- Existing tests pass without edits.
- Notebooks keep importing from `cvh_cost`.

**Out of scope for this refactor:**
- No web UI — chat happens in the terminal.
- No persisting sessions across processes (in-memory only, v1).
- No new financial features (rent-vs-buy, mortgage optimization, taxes
  beyond the existing `RecurringOtherCost` lever).
- No per-user accounts / auth.

## 9. Risks & Open Questions

1. **API key handling.** The agent needs an `ANTHROPIC_API_KEY`; market data
   may need FRED/Treasury access (Treasury is keyless, FRED needs a free
   key). Document in README; fail fast with a clear message if missing.
2. **Tool latency.** MC with `num_sims=10_000` on the advanced config takes
   noticeable seconds. Decide: stream a "running…" message, or auto-downscale
   `num_sims` for interactive runs and let the user opt up.
3. **Question batching.** Need to make sure the prompt actively pushes Claude
   to batch — otherwise UX feels like a chatbot interrogation. Worth A/B
   testing prompt variants in Phase 5.
4. **Provenance.** Every number Claude reports should be traceable to either
   (a) a user answer, (b) a market fetch, or (c) a computed result. Plan: the
   `assemble_params` output carries a `source` per field, and the system
   prompt requires Claude to cite sources in the final summary.
5. **Cost.** Each session = several Claude calls. Sonnet 4.6 is the default
   for that reason; Opus only on user request.
6. **Question bank scope.** The intake bank above is a v1 baseline; we'll
   expand based on what missing-info patterns show up in early use.

## 10. First PR Checklist (Phase 1)

- [ ] `git mv` the five core modules into `cvh_cost/core/`.
- [ ] `git mv` the YAML loader into `cvh_cost/config/yaml_config.py`.
- [ ] Update internal imports inside the moved files.
- [ ] Update `cvh_cost/__init__.py` re-exports.
- [ ] Update `cvh_cost/cli.py` to import from new locations.
- [ ] `pytest` green.
- [ ] `mypy src` green.
