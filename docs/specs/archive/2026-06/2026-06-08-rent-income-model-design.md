# Rent + Income Model Design

**money-path: no**

**Status:** DRAFT  
**Date:** 2026-06-08  
**Session:** S3 brainstorm-to-execute  
**Roadmap:** `docs/roadmaps/2026-06-07_housing-decision-engine.md`

---

## Goal

Extend the housing decision engine from a 2-way (condo vs house) comparison to a 3-way (rent vs condo vs house) comparison, and add an employment cash flow model that provides an affordability ratio layer alongside the PV comparison.

The engine should answer two questions simultaneously:
1. **Which option is cheapest?** — PV comparison (deterministic + MC)
2. **Which option is survivable?** — affordability ratios (housing cost / income) per year, with pay-drop event modeling

---

## Scope

### In
- `RentParams` dataclass + rent PV computation (deterministic + MC)
- `IncomeParams` + `PayDropEvent` dataclass + affordability ratio layer
- `ComparisonSpec` value-object replacing the `(condo, house, sim, econ)` 4-tuple
- Refactored `compute_deterministic(spec)` and `run_monte_carlo(spec)` signatures
- New result types: `ComparisonDeterministicResult`, `ComparisonMonteCarloResult`, `MonteCarloOptionResult`, `AffordabilityReport`, `AffordabilityMCReport`
- `config.py`: `load_config_dict` returns `ComparisonSpec` (breaking — all callers migrate)
- `SimulationParams`: 2 new MC volatility fields (`rent_escalation_vol`, `investment_return_vol`)
- MCP: affordability inline in `run_comparison` return, updated `ScenarioEntry`, extended `_SWEEP_PATHS`
- All 115 existing tests migrated to `ComparisonSpec` calling convention
- `src/hde/reporting.py`, `src/hde/cli.py` (quiet-mode), `mcp_server/tools.py` (`sweep_param`) migrated to new result types

### Out
- Mortgage modeling / equity tracking (buy-side PV stays as-is)
- Geographic tax rules
- Multi-user / SaaS concerns
- Crisis event model (forced-sell on income shock) — deferred to S4

---

## Design Decisions

### D1 — Total economic picture intent
Comparison includes all economically relevant cash flows. For rent, this means modeling the investment return earned on capital freed from not making a down payment. The buy-side (condo/house) does not gain a matching opportunity cost term — symmetry is preserved because neither buy-side model tracks home equity at sale.

### D2 — Opportunity cost on rent side only
`RentParams.invested_down_payment` + `RentParams.investment_return_rate` define the capital freed and its return. The PV of the terminal investment value reduces rent's total cost. When `investment_return_rate == discount_rate`, the benefit equals the invested principal exactly.

### D3 — Income as affordability overlay, not PV adjustment
Income does not enter the PV comparison score. It generates a parallel `AffordabilityReport` with year-by-year ratios (housing cost / income). The PV question and the survivability question are answered separately and reported together.

### D4 — Option C architecture (ComparisonSpec value-object bundle)
All parameters bundled into `ComparisonSpec`. `compute_deterministic` and `run_monte_carlo` accept `ComparisonSpec` exclusively. Breaking change — trades short-term migration cost for clean S4 extensibility (add `MarketScenarioParams` to `ComparisonSpec` without touching function signatures).

### D5 — Affordability inline in `run_comparison` (revised from initial design)
Affordability report included as a nullable `"affordability"` key in `run_comparison` return value. It is already-computed data (not a separate operation), so the atomic-tool principle does not apply. One call returns PV results + affordability together when income params are present. No 7th tool added — server stays at 6 tools.

---

## Data Model

### New types in `src/hde/models.py`

```python
@dataclass
class PayDropEvent:
    year: int               # 1-based year number
    magnitude: float        # fraction of income retained (0.8 = 20% cut)
    year_jitter_std: float = 0.0   # MC: timing uncertainty (0 = deterministic year)
    magnitude_vol: float = 0.0    # MC: lognormal severity vol


@dataclass
class RentParams:
    monthly_rent: float
    rent_escalation_rate: float = 0.03
    invested_down_payment: float = 0.0       # capital freed vs buying down payment
    investment_return_rate: float = 0.07     # annual return on invested capital
    events: list[EventConfig] = field(default_factory=list)
    other_recurring_costs: list[RecurringOtherCost] = field(default_factory=list)


@dataclass
class IncomeParams:
    annual_income: float
    income_growth_rate: float = 0.03
    affordability_threshold: float = 0.35    # flag when housing_cost/income > threshold
    pay_drop_events: list[PayDropEvent] = field(default_factory=list)


@dataclass
class ComparisonSpec:
    simulation: SimulationParams
    economic: EconomicParams
    condo: CondoParams | None = None
    house: HouseParams | None = None
    rent: RentParams | None = None
    income: IncomeParams | None = None
    # Invariant: at least one of condo / house / rent must be non-None
```

### New/refactored result types in `src/hde/models.py`

```python
@dataclass
class OptionResult:
    """Per-option deterministic result."""
    total_pv: float
    breakdown: dict[str, float]
    # Rent breakdown keys: rent_pv, events_pv, other_pv, invested_dp_benefit_pv (negative)
    # Condo breakdown keys: fee_pv, events_pv, other_pv, reserve_pv
    # House breakdown keys: maintenance_pv, events_pv, other_pv


@dataclass
class AffordabilityReport:
    """Deterministic affordability layer (income-present scenarios only)."""
    annual_incomes: list[float]           # income trajectory, len = years
    threshold: float
    rent_ratios: list[float] | None       # annual_housing_cost / annual_income, per year
    condo_ratios: list[float] | None
    house_ratios: list[float] | None
    years_rent_exceeds: list[int]         # 1-based year numbers where ratio > threshold
    years_condo_exceeds: list[int]
    years_house_exceeds: list[int]


@dataclass
class ComparisonDeterministicResult:
    """Replaces DeterministicResult."""
    condo: OptionResult | None = None
    house: OptionResult | None = None
    rent: OptionResult | None = None
    income_report: AffordabilityReport | None = None


@dataclass
class MonteCarloOptionResult:
    """Per-option MC result. Replaces inline condo/house fields in MonteCarloResult."""
    pvs: np.ndarray               # shape (num_sims,) — never crosses MCP boundary
    summary: MonteCarloSummary    # scalar stats only


@dataclass
class AffordabilityMCReport:
    """MC affordability layer."""
    threshold: float
    prob_rent_exceeds: float | None    # P(max ratio in sim > threshold)
    prob_condo_exceeds: float | None
    prob_house_exceeds: float | None


@dataclass
class ComparisonMonteCarloResult:
    """Replaces MonteCarloResult."""
    condo: MonteCarloOptionResult | None = None
    house: MonteCarloOptionResult | None = None
    rent: MonteCarloOptionResult | None = None
    # 3-way ranking probabilities (computed from pvs arrays before they're discarded).
    # Replaces the old prob_house_more_expensive + diff_summary fields.
    prob_rent_cheapest: float | None = None    # fraction of sims where rent has lowest PV
    prob_condo_cheapest: float | None = None
    prob_house_cheapest: float | None = None
    affordability_mc: AffordabilityMCReport | None = None
```

**Note on diffs:** `diff_pv` and `diff_summary` (2-way era) are dropped. Claude reads per-option `total_pv` values and computes comparisons directly. Probabilistic ranking (`prob_X_cheapest`) is computed from simulation arrays via `np.argmin([rent_pvs, condo_pvs, house_pvs], axis=0)` before arrays are discarded — cannot be recomputed from summary scalars alone.

`MonteCarloSummary` (existing dataclass with mean/std/p5/p50/p95) is **unchanged**.

### `SimulationParams` additions (two new fields, both default 0.0)

```python
rent_escalation_vol: float = 0.0     # MC: lognormal vol on rent escalation rate
investment_return_vol: float = 0.0   # MC: lognormal vol on investment_return_rate
```

---

## Engine Refactor

### Signatures

```python
# src/hde/deterministic.py
def compute_deterministic(spec: ComparisonSpec) -> ComparisonDeterministicResult: ...

# src/hde/monte_carlo.py
def run_monte_carlo(spec: ComparisonSpec) -> ComparisonMonteCarloResult: ...
```

The 4-tuple calling convention `(condo, house, sim, econ)` is eliminated. All call sites migrate to `ComparisonSpec`.

### Rent PV math (deterministic)

```
rent_pv = pv_recurring_with_escalation(monthly_rent × 12, rent_escalation_rate, years, dr)
         + pv_events(events, dr)
         + pv_other_recurring(other_recurring_costs, years, dr)
         - benefit_invested_dp

where dr = effective discount rate (nominal or real per economic mode)

benefit_invested_dp = invested_down_payment
                      × (1 + investment_return_rate)^years
                      / (1 + dr)^years
```

`benefit_invested_dp` is the PV of the terminal value of the renter's invested capital. It appears as `invested_dp_benefit_pv` (negative value) in the breakdown dict — the sign makes the subtraction visible in reports and MCP output.

**Mode handling:** when `economic.mode == "nominal"`, `investment_return_rate` is nominal. When `"real"`, it is real. Config validation warns if `investment_return_rate` appears implausibly high for the declared mode.

### Affordability computation (deterministic)

Income trajectory is computed year-by-year:
```python
income[0] = annual_income
income[t] = income[t-1] × (1 + income_growth_rate)
# Apply pay-drop events: income[event.year - 1] *= event.magnitude
```

Annual housing cost for each option uses **un-discounted cash flows** for that year (the ratio denominator is gross income, not PV). For condo/house, annual cost = maintenance + fees + events hitting that year. For rent, annual cost = monthly_rent × 12 × escalation factor for that year (investment return benefit is excluded from the affordability ratio — it's a terminal benefit, not an annual cash flow).

### MC extensions

**Rent MC:**
- `rent_escalation_rate` → lognormal shock with vol `simulation.rent_escalation_vol`, correlated with inflation via existing `_correlated_z` mechanism.
- `investment_return_rate` → lognormal shock with vol `simulation.investment_return_vol` (independent draw — investment returns are not correlated with inflation in this model).

**Income MC:**
- Each `PayDropEvent` is placed using normal jitter on year (`year_jitter_std`) and the magnitude is shocked lognormally (`magnitude_vol`) — same pattern as `EventConfig` in `_sample_event_year` / `_sample_event_cost`.
- If `year_jitter_std == 0` and `magnitude_vol == 0`: pay-drop is deterministic (same every simulation).

**Affordability MC:**
- For each simulation, compute per-year ratios for each present option.
- `prob_exceeds_threshold_any_year` = fraction of simulations where `max(ratio)` > `threshold`.

---

## Config Schema

### New YAML sections (both optional — existing 2-way configs remain valid)

```yaml
rent:                               # optional
  monthly_rent: 2500
  rent_escalation_rate: 0.04
  invested_down_payment: 150000     # capital freed vs down payment
  investment_return_rate: 0.07      # annual return on that capital
  events:
    - name: "moving costs"
      base_cost: 5000
      expected_year: 5
  other_recurring_costs: []

income:                             # optional
  annual_income: 120000
  income_growth_rate: 0.03
  affordability_threshold: 0.35
  pay_drop_events:
    - year: 3
      magnitude: 0.8                # retain 80% → 20% pay cut
      year_jitter_std: 0.0
      magnitude_vol: 0.0
```

### `config.py` changes
- Add `_parse_pay_drop_event(d)` → `PayDropEvent`
- Add `_parse_rent(d)` → `RentParams` (mirrors `_parse_condo` / `_parse_house` pattern)
- Add `_parse_income(d)` → `IncomeParams`
- `load_config_dict(d)` return type: `(CondoParams, HouseParams, SimulationParams, EconomicParams)` → **`ComparisonSpec`**
- `load_config(path)` same return type change
- `validate_config(spec: ComparisonSpec)` signature updated; adds rent/income range checks
- **Loader invariant fix:** remove hard-require for `condo` and `house` sections (current lines 330-333 and 365-368). Replace with: raise `ConfigValidationError` if all of `spec.condo`, `spec.house`, `spec.rent` are `None`. Configs with only a `rent` section (e.g., `examples/income_shock.yaml`) must load cleanly.

### `validate_config` additions
- `rent.monthly_rent > 0`
- `0 < rent.rent_escalation_rate < 0.20`
- `rent.invested_down_payment >= 0`
- `0 < rent.investment_return_rate < 0.25`
- `income.annual_income > 0`
- `income.affordability_threshold` in `(0, 1)`
- `pay_drop_event.magnitude` in `(0, 1]` (0 would be full income loss — allowed but warned)

---

## MCP Server Changes

### `mcp_server/registry.py`

`ScenarioEntry` stores `ComparisonSpec` instead of the 4-tuple:

```python
@dataclass
class ScenarioEntry:
    name: str
    raw_config: dict
    spec: ComparisonSpec                              # replaces (params: tuple)
    det_result: ComparisonDeterministicResult | None = None
    mc_result: ComparisonMonteCarloResult | None = None
```

`store_results` semantics unchanged: total-replace (always writes both fields, even if `None`).

### `mcp_server/tools.py`

- `define_scenario`: calls `load_config_dict(raw)` → `ComparisonSpec`; stores `entry.spec`. Guard: do NOT unconditionally read `entry.spec.condo.monthly_fee` / `entry.spec.house.initial_value` — check for None first.
- `run_comparison`: calls `compute_deterministic(entry.spec)` / `run_monte_carlo(entry.spec)`. Return value includes `"affordability"` key (nullable) with the full `AffordabilityReport` / `AffordabilityMCReport` when income params present.
- `_det_to_dict`: updated for `ComparisonDeterministicResult` (per-option `OptionResult` structure). Per-option breakdown keys centralized as module constants (`CONDO_BREAKDOWN_KEYS`, `HOUSE_BREAKDOWN_KEYS`, `RENT_BREAKDOWN_KEYS`) — drift protection when new breakdown fields are added.
- `_mc_to_dict`: updated for `ComparisonMonteCarloResult` (per-option `MonteCarloOptionResult` + `prob_X_cheapest` fields). MC numpy arrays still never cross MCP boundary — only `MonteCarloSummary` scalars returned.
- `save_figure`: add guard for options not present in spec — if `entry.spec.rent is None` and `figure_type == "rent"`, return error rather than raising `AttributeError`.
- `sweep_param`: guard added — if path starts with `"rent."` and `entry.spec.rent is None`, return `{"error": "scenario has no rent section; cannot sweep rent.* paths"}`.

### `_SWEEP_PATHS` extension (3 new entries)

```python
"rent.monthly_rent": ("rent", "monthly_rent"),
"rent.invested_down_payment": ("rent", "invested_down_payment"),
"rent.investment_return_rate": ("rent", "investment_return_rate"),
```

Total: 14 whitelisted paths (up from 11). Drift-guard test extended to cover rent paths with a rent-inclusive fixture config.

### `run_comparison` return shape (with affordability inline)

When `spec.income` is present, `run_comparison` return includes:
```json
{
  "condo": {"total_pv": ..., "breakdown": {...}},
  "house": {"total_pv": ..., "breakdown": {...}},
  "rent":  {"total_pv": ..., "breakdown": {...}},
  "prob_rent_cheapest": 0.41,
  "prob_condo_cheapest": 0.34,
  "prob_house_cheapest": 0.25,
  "affordability": {
    "annual_incomes": [...],
    "threshold": 0.35,
    "rent":  {"ratios": [...], "years_exceeding": [...]},
    "condo": {"ratios": [...], "years_exceeding": [...]},
    "house": {"ratios": [...], "years_exceeding": [...]}
  }
}
```

All per-option keys are `null` for options not in the scenario. `affordability` is `null` when no income params defined. `prob_X_cheapest` fields are `null` when MC not run or fewer than 2 options present.

### Existing tool signatures: unchanged

`define_scenario`, `run_comparison`, `sweep_param`, `save_figure`, `list_scenarios`, `delete_scenario` — tool signatures unchanged. Internal implementations updated for new result types. Server stays at **6 tools**.

---

## Test Migration Strategy

All 115 existing tests call `compute_deterministic(condo, house, sim, econ)` or `run_monte_carlo(condo, house, sim, econ)` with 4 positional args, and reference `result.condo_total_pv` / `result.house_total_pv` inline fields.

Migration:
- `compute_deterministic(condo, house, sim, econ)` → `compute_deterministic(ComparisonSpec(condo=condo, house=house, simulation=sim, economic=econ))`
- `result.condo_total_pv` → `result.condo.total_pv`
- `result.house_total_pv` → `result.house.total_pv`
- `result.condo_*_pv` → `result.condo.breakdown["fee_pv"]` etc.
- `mc_result.condo_pvs` → `mc_result.condo.pvs`
- `mc_result.condo_summary` → `mc_result.condo.summary`

Migration also covers (not only tests):
- `src/hde/reporting.py` — `format_text_report` and `plot_*` functions reference `DeterministicResult` / `MonteCarloResult` fields; update to `ComparisonDeterministicResult` / `ComparisonMonteCarloResult`
- `src/hde/cli.py` — quiet-mode summary logic reads `result.condo_total_pv` / `result.house_total_pv`; update to `result.condo.total_pv` etc.
- `mcp_server/tools.py` — `_det_to_dict`, `_mc_to_dict`, `sweep_param` all reference old result shape

A single implementer subagent handles all 115 tests + all above call sites in one task (mechanical search-and-replace pattern).

---

## New Test Coverage

- `test_rent_pv_basic` — rent with no events, no invested dp: equals `pv_recurring_with_escalation`
- `test_rent_pv_invested_dp_at_discount_rate` — when `investment_return_rate == discount_rate`, benefit == `invested_down_payment` (PV identity)
- `test_rent_pv_invested_dp_higher_return` — benefit > down_payment when return > discount rate
- `test_affordability_basic` — income trajectory computed correctly with growth rate
- `test_affordability_pay_drop` — pay-drop event applies to correct year
- `test_affordability_threshold_flagging` — years exceeding threshold populated correctly
- `test_three_way_comparison_deterministic` — all three options present, consistent discount rate
- `test_three_way_mc_affordability` — `prob_exceeds_threshold` is in [0, 1] and non-trivially non-zero when housing cost is high relative to income
- `test_comparison_spec_requires_at_least_one_option` — `ComparisonSpec` with all None options raises `ConfigValidationError`
- `test_sweep_param_rent_path_no_rent_section` — guard returns error dict when spec has no rent
- `test_drift_guard_sweep_paths_rent` — all 3 new `_SWEEP_PATHS` entries resolve against rent-inclusive fixture
- `test_load_config_rent_only` — YAML with only `rent` section (no condo/house) loads without error; `spec.condo` and `spec.house` are `None`
- `test_load_config_all_none_raises` — YAML with no condo/house/rent section raises `ConfigValidationError`
- `test_prob_cheapest_sums_to_one` — `prob_rent_cheapest + prob_condo_cheapest + prob_house_cheapest ≈ 1.0` (within float tolerance) when all three options present
- `test_prob_cheapest_none_when_single_option` — `prob_X_cheapest` all `None` when only one option present

---

## Walking Skeleton

No external boundary claims in this spec. All computation is in-process pure Python + NumPy. No walking-skeleton probe task required.

---

## MCP Tool Summary (post-S3)

Server stays at **6 tools** — no new tool added.

| Tool | Purpose | What changes |
|---|---|---|
| `define_scenario` | validate + store `ComparisonSpec` | internal: None-safe option guards |
| `run_comparison` | run det/MC, store results | return shape updated; `affordability` + `prob_X_cheapest` added |
| `sweep_param` | parameter sensitivity | +3 rent paths; rent-section guard added; migrated to new result types |
| `save_figure` | render MC figures | guard for absent options |
| `list_scenarios` | registry management | unchanged |
| `delete_scenario` | registry management | unchanged |

---

## Example YAML configs to add

- `examples/rent_vs_condo_vs_house.yaml` — 3-way comparison with invested down payment
- `examples/income_shock.yaml` — 20% pay cut in year 3; rent vs condo survivability
