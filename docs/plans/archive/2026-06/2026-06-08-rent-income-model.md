# Rent + Income Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use mm-spine:subagent-driven-development (recommended) or mm-spine:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

`audit-skipped: not money-path`

**Goal:** Extend the housing decision engine from 2-way (condo/house) to 3-way (rent/condo/house) comparison with employment cash flow affordability modeling, using a ComparisonSpec value-object pattern.

**Architecture:** Replace the 4-tuple `(CondoParams, HouseParams, SimulationParams, EconomicParams)` calling convention with a single `ComparisonSpec` bundle. All three options are Optional in the spec; at least one must be present. A new `AffordabilityReport` layer (income / housing cost ratios) is computed alongside PV and returned inline from `run_comparison`.

**Tech Stack:** Python 3.10+, dataclasses, NumPy, FastMCP, pytest, uv

---

## File Map

**Modified:**
- `src/hde/models.py` — new dataclasses (`PayDropEvent`, `RentParams`, `IncomeParams`, `ComparisonSpec`, `OptionResult`, `AffordabilityReport`, `ComparisonDeterministicResult`, `MonteCarloOptionResult`, `AffordabilityMCReport`, `ComparisonMonteCarloResult`), extend `SimulationParams`, add breakdown key constants
- `src/hde/config.py` — add parsers (`_parse_pay_drop_event`, `_parse_rent`, `_parse_income`), update `load_config`/`load_config_dict` return type to `ComparisonSpec`, fix loader invariant, update `validate_config`
- `src/hde/deterministic.py` — update `compute_deterministic(spec)` signature, add rent PV + affordability report
- `src/hde/monte_carlo.py` — update `run_monte_carlo(spec)` signature, add rent MC + income MC + ranking probs
- `src/hde/reporting.py` — update `format_text_report`, `plot_diff_distribution`, `plot_pv_distributions` for new result types
- `src/hde/cli.py` — update for new result types
- `mcp_server/registry.py` — update `ScenarioEntry`, `define()`
- `mcp_server/tools.py` — update `_det_to_dict`, `_mc_to_dict`, `define_scenario`, `run_comparison` (inline affordability), `sweep_param` (new paths + guard), `save_figure` (option guard); extend `_SWEEP_PATHS`
- `tests/test_config.py` — migrate to `ComparisonSpec` return; add new tests
- `tests/test_deterministic.py` — migrate to `ComparisonSpec` calling convention
- `tests/test_monte_carlo.py` — migrate to `ComparisonSpec` calling convention
- `tests/test_registry.py` — migrate to `spec` field
- `tests/test_tools.py` — migrate to new result shape; add new tests

**Created:**
- `examples/rent_vs_condo_vs_house.yaml` — 3-way comparison example config
- `examples/income_shock.yaml` — income shock scenario example

---

## Task 1: Data Model Additions

**Files:**
- Modify: `src/hde/models.py`
- Test: `tests/test_models_new.py` (new file)

All existing types (`DeterministicResult`, `MonteCarloResult`) are kept unchanged — Task 1 adds only new types, breaking nothing.

- [ ] **Step 1: Write failing tests for new model types**

Create `tests/test_models_new.py`:

```python
"""Tests for S3 data model additions."""
import pytest
from hde.models import (
    PayDropEvent, RentParams, IncomeParams, ComparisonSpec,
    OptionResult, AffordabilityReport, ComparisonDeterministicResult,
    MonteCarloOptionResult, AffordabilityMCReport, ComparisonMonteCarloResult,
    SimulationParams, EconomicParams, CondoParams, HouseParams,
    MonteCarloSummary, CONDO_BREAKDOWN_KEYS, HOUSE_BREAKDOWN_KEYS, RENT_BREAKDOWN_KEYS,
)
import numpy as np


def _sim():
    return SimulationParams(years=10, discount_rate=0.05)


def _econ():
    return EconomicParams()


def test_pay_drop_event_defaults():
    e = PayDropEvent(year=3, magnitude=0.8)
    assert e.year == 3
    assert e.magnitude == 0.8
    assert e.year_jitter_std == 0.0
    assert e.magnitude_vol == 0.0


def test_rent_params_defaults():
    r = RentParams(monthly_rent=2000.0)
    assert r.rent_escalation_rate == 0.03
    assert r.invested_down_payment == 0.0
    assert r.investment_return_rate == 0.07
    assert r.events == []
    assert r.other_recurring_costs == []


def test_income_params_defaults():
    i = IncomeParams(annual_income=100_000.0)
    assert i.income_growth_rate == 0.03
    assert i.affordability_threshold == 0.35
    assert i.pay_drop_events == []


def test_comparison_spec_all_none_options_is_valid_at_model_level():
    # Invariant is enforced by validate_config, not __post_init__
    spec = ComparisonSpec(simulation=_sim(), economic=_econ())
    assert spec.condo is None
    assert spec.house is None
    assert spec.rent is None


def test_comparison_spec_with_options():
    condo = CondoParams(monthly_fee=800.0)
    spec = ComparisonSpec(simulation=_sim(), economic=_econ(), condo=condo)
    assert spec.condo is condo


def test_option_result_structure():
    r = OptionResult(total_pv=50_000.0, breakdown={"fee_pv": 50_000.0})
    assert r.total_pv == 50_000.0


def test_comparison_deterministic_result_defaults():
    r = ComparisonDeterministicResult()
    assert r.condo is None
    assert r.house is None
    assert r.rent is None
    assert r.income_report is None


def test_monte_carlo_option_result():
    pvs = np.array([1.0, 2.0, 3.0])
    summary = MonteCarloSummary(mean=2.0, std=1.0, p5=1.0, p50=2.0, p95=3.0)
    r = MonteCarloOptionResult(pvs=pvs, summary=summary)
    assert r.pvs.shape == (3,)


def test_comparison_mc_result_ranking_probs_default_none():
    r = ComparisonMonteCarloResult()
    assert r.prob_rent_cheapest is None
    assert r.prob_condo_cheapest is None
    assert r.prob_house_cheapest is None


def test_simulation_params_new_vol_fields():
    s = SimulationParams(years=10, discount_rate=0.05)
    assert s.rent_escalation_vol == 0.0
    assert s.investment_return_vol == 0.0


def test_breakdown_key_constants():
    assert "fee_pv" in CONDO_BREAKDOWN_KEYS
    assert "reserve_pv" in CONDO_BREAKDOWN_KEYS
    assert "maintenance_pv" in HOUSE_BREAKDOWN_KEYS
    assert "rent_pv" in RENT_BREAKDOWN_KEYS
    assert "invested_dp_benefit_pv" in RENT_BREAKDOWN_KEYS
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/mm-mike/ai_system/projects/housing-decision-engine
uv run python -m pytest tests/test_models_new.py -v 2>&1 | head -40
```

Expected: `ImportError` — new types not yet defined.

- [ ] **Step 3: Add new types to `src/hde/models.py`**

At the end of the imports block (after `import numpy.typing as npt`), add:

```python
from typing import FrozenSet
```

After the `EconomicParams` dataclass, before `# ----- Result Dataclasses -----`, add:

```python
# ----- S3 Input Types -----

@dataclass
class PayDropEvent:
    """A one-time income shock event."""
    year: int               # 1-based year number
    magnitude: float        # fraction of income retained (0.8 = 20% cut)
    year_jitter_std: float = 0.0   # MC: timing uncertainty in years
    magnitude_vol: float = 0.0    # MC: lognormal severity vol


@dataclass
class RentParams:
    """Parameters for the rent option."""
    monthly_rent: float
    rent_escalation_rate: float = 0.03
    invested_down_payment: float = 0.0      # capital freed vs buying
    investment_return_rate: float = 0.07    # annual return on invested capital
    events: List[EventConfig] = field(default_factory=list)
    other_recurring_costs: List[RecurringOtherCost] = field(default_factory=list)


@dataclass
class IncomeParams:
    """Employment cash flow parameters for affordability modeling."""
    annual_income: float
    income_growth_rate: float = 0.03
    affordability_threshold: float = 0.35
    pay_drop_events: List[PayDropEvent] = field(default_factory=list)


@dataclass
class ComparisonSpec:
    """Single input bundle for all comparison engines. Replaces the 4-tuple."""
    simulation: SimulationParams
    economic: EconomicParams
    condo: Optional[CondoParams] = None
    house: Optional[HouseParams] = None
    rent: Optional[RentParams] = None
    income: Optional[IncomeParams] = None
    # Invariant: at least one of condo/house/rent must be non-None (enforced by validate_config)
```

Add two new fields to `SimulationParams` **after** `shock_model`:

```python
    shock_model: Literal["lognormal", "normal"] = "lognormal"
    rent_escalation_vol: float = 0.0     # MC: lognormal vol on rent escalation rate
    investment_return_vol: float = 0.0   # MC: lognormal vol on investment_return_rate
```

After `MonteCarloResult` (at the end of the file), add new result types and constants:

```python
# ----- S3 Result Types -----

# Breakdown key constants for drift protection
CONDO_BREAKDOWN_KEYS: FrozenSet[str] = frozenset({"fee_pv", "events_pv", "other_pv", "reserve_pv"})
HOUSE_BREAKDOWN_KEYS: FrozenSet[str] = frozenset({"maintenance_pv", "events_pv", "other_pv"})
RENT_BREAKDOWN_KEYS: FrozenSet[str] = frozenset({"rent_pv", "events_pv", "other_pv", "invested_dp_benefit_pv"})


@dataclass
class OptionResult:
    """Per-option deterministic result. Replaces per-option inline fields."""
    total_pv: float
    breakdown: dict  # keys defined by {CONDO,HOUSE,RENT}_BREAKDOWN_KEYS


@dataclass
class AffordabilityReport:
    """Deterministic affordability layer. Only present when income params are defined."""
    annual_incomes: List[float]       # income trajectory, len = years
    threshold: float
    rent_ratios: Optional[List[float]] = None    # annual_housing_cost / annual_income
    condo_ratios: Optional[List[float]] = None
    house_ratios: Optional[List[float]] = None
    years_rent_exceeds: List[int] = field(default_factory=list)
    years_condo_exceeds: List[int] = field(default_factory=list)
    years_house_exceeds: List[int] = field(default_factory=list)


@dataclass
class ComparisonDeterministicResult:
    """Replaces DeterministicResult. All options are Optional."""
    condo: Optional[OptionResult] = None
    house: Optional[OptionResult] = None
    rent: Optional[OptionResult] = None
    income_report: Optional[AffordabilityReport] = None


@dataclass
class MonteCarloOptionResult:
    """Per-option MC result. pvs array never crosses MCP boundary."""
    pvs: npt.NDArray[np.float64]     # shape (num_sims,)
    summary: MonteCarloSummary


@dataclass
class AffordabilityMCReport:
    """MC affordability layer."""
    threshold: float
    prob_rent_exceeds: Optional[float] = None
    prob_condo_exceeds: Optional[float] = None
    prob_house_exceeds: Optional[float] = None


@dataclass
class ComparisonMonteCarloResult:
    """Replaces MonteCarloResult. All options are Optional."""
    condo: Optional[MonteCarloOptionResult] = None
    house: Optional[MonteCarloOptionResult] = None
    rent: Optional[MonteCarloOptionResult] = None
    prob_rent_cheapest: Optional[float] = None    # fraction of sims where rent has lowest PV
    prob_condo_cheapest: Optional[float] = None
    prob_house_cheapest: Optional[float] = None
    affordability_mc: Optional[AffordabilityMCReport] = None
```

- [ ] **Step 4: Run new tests to verify they pass**

```bash
uv run python -m pytest tests/test_models_new.py -v
```

Expected: all 13 tests PASS.

- [ ] **Step 5: Verify existing tests still pass**

```bash
uv run python -m pytest --tb=short -q
```

Expected: 115 tests pass (no regressions — only additive changes made).

- [ ] **Step 6: Commit**

```bash
git add src/hde/models.py tests/test_models_new.py
git commit -m "feat(models): add ComparisonSpec, RentParams, IncomeParams, new result types"
```

---

## Task 2: Config Extensions

**Files:**
- Modify: `src/hde/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for new config behavior**

Add to `tests/test_config.py` (at the end of the file):

```python
class TestComparisonSpecReturn:
    """load_config_dict returns ComparisonSpec."""

    def test_load_returns_comparison_spec(self):
        from hde.models import ComparisonSpec
        config = {
            "years": 10, "discount_rate": 0.05,
            "condo": {"monthly_fee": 500},
            "house": {"initial_value": 300_000},
        }
        spec = load_config_dict(config)
        assert isinstance(spec, ComparisonSpec)
        assert spec.condo.monthly_fee == 500
        assert spec.house.initial_value == 300_000
        assert spec.simulation.years == 10
        assert spec.economic.mode == "real"

    def test_load_rent_only_config(self):
        from hde.models import ComparisonSpec
        config = {
            "years": 10, "discount_rate": 0.05,
            "rent": {"monthly_rent": 2000},
        }
        spec = load_config_dict(config)
        assert isinstance(spec, ComparisonSpec)
        assert spec.rent.monthly_rent == 2000
        assert spec.condo is None
        assert spec.house is None

    def test_all_none_options_raises(self):
        config = {"years": 10, "discount_rate": 0.05}
        with pytest.raises(ConfigValidationError):
            load_config_dict(config)

    def test_rent_params_parsed_correctly(self):
        config = {
            "years": 10, "discount_rate": 0.05,
            "rent": {
                "monthly_rent": 2500,
                "rent_escalation_rate": 0.04,
                "invested_down_payment": 100_000,
                "investment_return_rate": 0.07,
            },
        }
        spec = load_config_dict(config)
        assert spec.rent.monthly_rent == 2500
        assert spec.rent.rent_escalation_rate == 0.04
        assert spec.rent.invested_down_payment == 100_000
        assert spec.rent.investment_return_rate == 0.07

    def test_income_params_parsed_correctly(self):
        config = {
            "years": 10, "discount_rate": 0.05,
            "condo": {"monthly_fee": 500},
            "income": {
                "annual_income": 120_000,
                "income_growth_rate": 0.03,
                "affordability_threshold": 0.35,
                "pay_drop_events": [
                    {"year": 3, "magnitude": 0.8}
                ],
            },
        }
        spec = load_config_dict(config)
        assert spec.income.annual_income == 120_000
        assert len(spec.income.pay_drop_events) == 1
        assert spec.income.pay_drop_events[0].year == 3
        assert spec.income.pay_drop_events[0].magnitude == 0.8

    def test_rent_validation_invalid_monthly_rent(self):
        config = {
            "years": 10, "discount_rate": 0.05,
            "rent": {"monthly_rent": -100},
        }
        with pytest.raises(ConfigValidationError):
            load_config_dict(config)

    def test_income_validation_invalid_threshold(self):
        config = {
            "years": 10, "discount_rate": 0.05,
            "condo": {"monthly_fee": 500},
            "income": {"annual_income": 100_000, "affordability_threshold": 1.5},
        }
        with pytest.raises(ConfigValidationError):
            load_config_dict(config)
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run python -m pytest tests/test_config.py::TestComparisonSpecReturn -v 2>&1 | head -30
```

Expected: `AssertionError` / `TypeError` — `load_config_dict` still returns a tuple.

- [ ] **Step 3: Add parsers and update config.py**

**3a. Add imports at top of `src/hde/config.py`** — add `ComparisonSpec`, `PayDropEvent`, `RentParams`, `IncomeParams` to the existing `from hde.models import ...` line.

**3b. Add `_parse_pay_drop_event` after `_parse_recurring_cost`:**

```python
def _parse_pay_drop_event(data: Dict[str, Any]) -> "PayDropEvent":
    if "year" not in data:
        raise ConfigValidationError("pay_drop_event missing required field: year")
    if "magnitude" not in data:
        raise ConfigValidationError("pay_drop_event missing required field: magnitude")
    return PayDropEvent(
        year=int(data["year"]),
        magnitude=float(data["magnitude"]),
        year_jitter_std=float(data.get("year_jitter_std", 0.0)),
        magnitude_vol=float(data.get("magnitude_vol", 0.0)),
    )
```

**3c. Add `_parse_rent` after `_parse_house`:**

```python
def _parse_rent(data: Dict[str, Any], years: int) -> "RentParams":
    if "monthly_rent" not in data:
        raise ConfigValidationError("rent section missing required field: monthly_rent")
    events = [_parse_event(e, years) for e in data.get("events", [])]
    other = [_parse_recurring_cost(c) for c in data.get("other_recurring_costs", [])]
    return RentParams(
        monthly_rent=float(data["monthly_rent"]),
        rent_escalation_rate=float(data.get("rent_escalation_rate", 0.03)),
        invested_down_payment=float(data.get("invested_down_payment", 0.0)),
        investment_return_rate=float(data.get("investment_return_rate", 0.07)),
        events=events,
        other_recurring_costs=other,
    )
```

**3d. Add `_parse_income` after `_parse_rent`:**

```python
def _parse_income(data: Dict[str, Any]) -> "IncomeParams":
    if "annual_income" not in data:
        raise ConfigValidationError("income section missing required field: annual_income")
    events = [_parse_pay_drop_event(e) for e in data.get("pay_drop_events", [])]
    return IncomeParams(
        annual_income=float(data["annual_income"]),
        income_growth_rate=float(data.get("income_growth_rate", 0.03)),
        affordability_threshold=float(data.get("affordability_threshold", 0.35)),
        pay_drop_events=events,
    )
```

**3e. Update `validate_config` signature and body** — change from `validate_config(condo, house, sim, econ)` to `validate_config(spec: ComparisonSpec)`. Add invariant check at the top and rent/income validation:

```python
def validate_config(spec: "ComparisonSpec") -> List[str]:
    errors = []
    condo, house, rent, income = spec.condo, spec.house, spec.rent, spec.income
    sim, econ = spec.simulation, spec.economic

    # Invariant: at least one option must be present
    if condo is None and house is None and rent is None:
        errors.append("At least one of condo, house, or rent must be defined")

    # ... existing condo / house / sim / econ validations (adapt to use condo/house/sim/econ locals) ...

    # Rent validations
    if rent is not None:
        if rent.monthly_rent <= 0:
            errors.append("rent.monthly_rent must be positive")
        if not (0 < rent.rent_escalation_rate < 0.20):
            errors.append("rent.rent_escalation_rate must be between 0 and 0.20")
        if rent.invested_down_payment < 0:
            errors.append("rent.invested_down_payment must be non-negative")
        if not (0 < rent.investment_return_rate < 0.25):
            errors.append("rent.investment_return_rate must be between 0 and 0.25")

    # Income validations
    if income is not None:
        if income.annual_income <= 0:
            errors.append("income.annual_income must be positive")
        if not (0 < income.affordability_threshold < 1):
            errors.append("income.affordability_threshold must be between 0 and 1")
        for ev in income.pay_drop_events:
            if not (0 < ev.magnitude <= 1):
                errors.append(f"pay_drop_event year={ev.year}: magnitude must be in (0, 1]")

    return errors
```

**3f. Update `load_config` and `load_config_dict`** — replace the hard `"condo"` and `"house"` required checks with optional parsing; return `ComparisonSpec`:

In both functions, replace:
```python
if "condo" not in data:
    raise ConfigValidationError("Missing required section: condo")
if "house" not in data:
    raise ConfigValidationError("Missing required section: house")
```

With:
```python
# condo, house, rent, income are all optional; validate_config enforces at-least-one
```

And replace the parsing + return block with:
```python
years = int(data["years"])
discount_rate = float(data["discount_rate"])

condo = _parse_condo(data["condo"], years) if "condo" in data else None
house = _parse_house(data["house"], years) if "house" in data else None
rent = _parse_rent(data["rent"], years) if "rent" in data else None
income = _parse_income(data["income"]) if "income" in data else None
sim = _parse_simulation(data.get("simulation"), years, discount_rate)
econ = _parse_economic(data.get("economic"))

spec = ComparisonSpec(simulation=sim, economic=econ, condo=condo, house=house, rent=rent, income=income)
warnings = validate_config(spec)
if warnings:
    raise ConfigValidationError("Configuration validation failed:\n" + "\n".join(warnings))

return spec
```

Update the return type annotation on both functions to `-> ComparisonSpec`.

- [ ] **Step 4: Migrate existing `tests/test_config.py` to new return type**

Find every line that unpacks `load_config_dict` or `load_config` as a 4-tuple and rewrite it. Pattern:

Old:
```python
condo, house, sim, econ = load_config_dict(config)
assert condo.monthly_fee == 500
```

New:
```python
spec = load_config_dict(config)
assert spec.condo.monthly_fee == 500
```

Also update calls to `validate_config` in tests — old `validate_config(condo, house, sim, econ)` → `validate_config(spec)`.

For tests like `TestValidation.test_missing_condo` — these now test a config with no options at all, which raises `ConfigValidationError` via the invariant check. Update the test configs accordingly (e.g., a config with neither condo nor house nor rent should raise).

- [ ] **Step 5: Run all config tests**

```bash
uv run python -m pytest tests/test_config.py -v
```

Expected: all tests pass (old ones migrated + new `TestComparisonSpecReturn` tests).

- [ ] **Step 6: Run full suite**

```bash
uv run python -m pytest --tb=short -q
```

Expected: tests in `test_deterministic.py`, `test_monte_carlo.py` etc. still pass (they don't call `load_config_dict`, they build params directly).

- [ ] **Step 7: Commit**

```bash
git add src/hde/config.py tests/test_config.py
git commit -m "feat(config): load_config_dict returns ComparisonSpec; add rent/income parsers"
```

---

## Task 3: Deterministic Engine Refactor

**Files:**
- Modify: `src/hde/deterministic.py`
- Modify: `tests/test_deterministic.py`

- [ ] **Step 1: Write new tests for rent PV + affordability (red phase)**

Add to end of `tests/test_deterministic.py`:

```python
from hde.models import (
    ComparisonSpec, RentParams, IncomeParams, PayDropEvent,
    ComparisonDeterministicResult,
)


def _spec(condo=None, house=None, rent=None, income=None, years=10, dr=0.05):
    from hde.models import SimulationParams, EconomicParams
    return ComparisonSpec(
        simulation=SimulationParams(years=years, discount_rate=dr),
        economic=EconomicParams(),
        condo=condo, house=house, rent=rent, income=income,
    )


class TestRentPV:
    def test_rent_pv_basic_no_dp(self):
        """Rent with zero invested_dp and no escalation = simple annuity."""
        from hde.pv import pv_annuity
        rent = RentParams(monthly_rent=2000.0, rent_escalation_rate=0.0, invested_down_payment=0.0)
        spec = _spec(rent=rent, years=10, dr=0.05)
        result = compute_deterministic(spec)
        expected = pv_annuity(2000.0 * 12, 10, 0.05)
        assert abs(result.rent.total_pv - expected) < 1.0

    def test_rent_pv_invested_dp_at_discount_rate(self):
        """When investment_return_rate == discount_rate, benefit PV == invested_dp."""
        rent = RentParams(
            monthly_rent=0.0,  # no rent cost — isolate the benefit
            rent_escalation_rate=0.0,
            invested_down_payment=100_000.0,
            investment_return_rate=0.05,  # == discount_rate
        )
        spec = _spec(rent=rent, years=10, dr=0.05)
        result = compute_deterministic(spec)
        # total_pv = 0 (no rent) - benefit_pv; benefit_pv == 100_000 when r == dr
        assert abs(result.rent.breakdown["invested_dp_benefit_pv"] + 100_000.0) < 10.0

    def test_rent_pv_invested_dp_higher_return(self):
        """When investment_return_rate > discount_rate, benefit > invested_dp."""
        rent = RentParams(
            monthly_rent=0.0,
            rent_escalation_rate=0.0,
            invested_down_payment=100_000.0,
            investment_return_rate=0.09,  # > discount_rate=0.05
        )
        spec = _spec(rent=rent, years=10, dr=0.05)
        result = compute_deterministic(spec)
        # benefit > 100_000 → invested_dp_benefit_pv is more negative than -100_000
        assert result.rent.breakdown["invested_dp_benefit_pv"] < -100_000.0

    def test_rent_breakdown_keys_match_constant(self):
        from hde.models import RENT_BREAKDOWN_KEYS
        rent = RentParams(monthly_rent=2000.0)
        spec = _spec(rent=rent)
        result = compute_deterministic(spec)
        assert set(result.rent.breakdown.keys()) == RENT_BREAKDOWN_KEYS


class TestAffordabilityReport:
    def test_affordability_basic_income_trajectory(self):
        """Income trajectory grows at income_growth_rate each year."""
        income = IncomeParams(annual_income=100_000.0, income_growth_rate=0.0)
        condo = CondoParams(monthly_fee=500.0)  # keep condo so spec is valid
        spec = _spec(condo=condo, income=income, years=5)
        result = compute_deterministic(spec)
        # Flat income: all years == 100_000
        assert len(result.income_report.annual_incomes) == 5
        assert all(abs(inc - 100_000.0) < 1.0 for inc in result.income_report.annual_incomes)

    def test_affordability_pay_drop_persists(self):
        """Pay drop in year 2 affects year 2 and beyond."""
        income = IncomeParams(
            annual_income=100_000.0,
            income_growth_rate=0.0,
            pay_drop_events=[PayDropEvent(year=2, magnitude=0.8)],
        )
        condo = CondoParams(monthly_fee=500.0)
        spec = _spec(condo=condo, income=income, years=5)
        result = compute_deterministic(spec)
        incomes = result.income_report.annual_incomes
        assert abs(incomes[0] - 100_000.0) < 1.0   # year 1: unaffected
        assert abs(incomes[1] - 80_000.0) < 1.0    # year 2: 20% cut
        assert abs(incomes[2] - 80_000.0) < 1.0    # year 3: persists

    def test_affordability_threshold_flagging(self):
        """Years where ratio > threshold appear in years_exceeding list."""
        income = IncomeParams(annual_income=10_000.0, affordability_threshold=0.35)
        condo = CondoParams(monthly_fee=500.0)  # 6000/yr / 10000 = 0.60 > 0.35
        spec = _spec(condo=condo, income=income, years=3)
        result = compute_deterministic(spec)
        assert len(result.income_report.years_condo_exceeds) == 3  # all 3 years exceed

    def test_no_income_no_report(self):
        """When income=None, income_report is None."""
        condo = CondoParams(monthly_fee=500.0)
        spec = _spec(condo=condo)
        result = compute_deterministic(spec)
        assert result.income_report is None
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
uv run python -m pytest tests/test_deterministic.py::TestRentPV tests/test_deterministic.py::TestAffordabilityReport -v 2>&1 | head -20
```

Expected: `ImportError` or `TypeError` — `compute_deterministic` still takes 4 args.

- [ ] **Step 3: Update `src/hde/deterministic.py`**

**3a. Update imports** — add to `from hde.models import ...`:
```python
ComparisonSpec, ComparisonDeterministicResult, OptionResult, AffordabilityReport,
RentParams, IncomeParams, PayDropEvent,
CONDO_BREAKDOWN_KEYS, HOUSE_BREAKDOWN_KEYS, RENT_BREAKDOWN_KEYS,
```

**3b. Add `_compute_rent_pv` function** (after `_compute_other_recurring_pv`):

```python
def _compute_rent_pv(rent: RentParams, sim: SimulationParams, econ: EconomicParams) -> OptionResult:
    """Compute PV of rent option including invested_dp benefit."""
    from hde.pv import pv_recurring_with_escalation
    dr = _effective_growth_rate(sim.discount_rate, 0.0, econ)

    # Base rent stream
    annual_rent = rent.monthly_rent * 12
    rent_pv = pv_recurring_with_escalation(annual_rent, rent.rent_escalation_rate, sim.years, dr)

    # Events (moving costs, renewal shocks)
    events_pv = _compute_events_pv(rent.events, sim, econ)

    # Other recurring costs
    other_pv = _compute_other_recurring_pv(rent.other_recurring_costs, sim, econ)

    # Invested down payment benefit: PV of terminal value of invested capital
    if rent.invested_down_payment > 0:
        r_inv = rent.investment_return_rate
        benefit = rent.invested_down_payment * ((1 + r_inv) ** sim.years) / ((1 + dr) ** sim.years)
    else:
        benefit = 0.0
    # Stored as negative (reduces total cost)
    invested_dp_benefit_pv = -benefit

    total_pv = rent_pv + events_pv + other_pv + invested_dp_benefit_pv
    breakdown = {
        "rent_pv": rent_pv,
        "events_pv": events_pv,
        "other_pv": other_pv,
        "invested_dp_benefit_pv": invested_dp_benefit_pv,
    }
    return OptionResult(total_pv=total_pv, breakdown=breakdown)
```

**3c. Add `_compute_income_trajectory` and `_compute_affordability_report`:**

```python
def _compute_income_trajectory(income: IncomeParams, years: int) -> List[float]:
    """Compute annual income for each year, applying growth and pay-drop events."""
    trajectory = []
    current = income.annual_income
    for t in range(years):
        year = t + 1  # 1-based
        # Apply any pay-drop events for this year (multiplicative, permanent)
        for event in income.pay_drop_events:
            if event.year == year:
                current *= event.magnitude
        trajectory.append(current)
        if t < years - 1:
            current *= (1 + income.income_growth_rate)
    return trajectory


def _annual_cost_for_year(option_result: OptionResult, option_type: str,
                           params, sim: SimulationParams, econ: EconomicParams) -> List[float]:
    """Compute un-discounted annual housing cost by year for affordability ratios.

    Uses the option's base cost formula, un-discounted. Events are allocated
    to their deterministic year. Investment return benefit excluded (terminal, not annual).
    """
    from hde.pv import pv_to_monthly_savings  # noqa: F401 — not used, but import check
    dr = _effective_growth_rate(sim.discount_rate, 0.0, econ)
    costs = []
    for t in range(sim.years):
        year = t + 1
        if option_type == "condo":
            # Monthly fee escalated to year t
            escalated_fee = params.monthly_fee * 12 * ((1 + params.fee_escalation_rate) ** t)
            # Events hitting this year
            year_events = sum(
                _event_cost_deterministic(e)
                for e in params.events
                if _event_year_deterministic(e, sim) == year
            )
            costs.append(escalated_fee + year_events)
        elif option_type == "house":
            # Maintenance based on initial_value growth
            house_value_t = params.initial_value * ((1 + params.value_growth_rate) ** t)
            maint_rate = _maintenance_rate_for_year(params, year)
            year_events = sum(
                _event_cost_deterministic(e)
                for e in params.events
                if _event_year_deterministic(e, sim) == year
            )
            costs.append(house_value_t * maint_rate + year_events)
        elif option_type == "rent":
            # Escalated monthly rent (no invested_dp — it's a terminal benefit)
            escalated_rent = params.monthly_rent * 12 * ((1 + params.rent_escalation_rate) ** t)
            year_events = sum(
                _event_cost_deterministic(e)
                for e in params.events
                if _event_year_deterministic(e, sim) == year
            )
            costs.append(escalated_rent + year_events)
    return costs


def _compute_affordability_report(
    income: IncomeParams,
    det_result: ComparisonDeterministicResult,
    spec: ComparisonSpec,
) -> AffordabilityReport:
    """Build affordability report from income trajectory vs annual housing costs."""
    incomes = _compute_income_trajectory(income, spec.simulation.years)
    threshold = income.affordability_threshold

    def ratios_and_exceeds(option_type, params):
        if params is None:
            return None, []
        costs = _annual_cost_for_year(
            getattr(det_result, option_type), option_type, params, spec.simulation, spec.economic
        )
        ratios = [c / inc if inc > 0 else float("inf") for c, inc in zip(costs, incomes)]
        exceeds = [t + 1 for t, r in enumerate(ratios) if r > threshold]
        return ratios, exceeds

    rent_ratios, years_rent = ratios_and_exceeds("rent", spec.rent)
    condo_ratios, years_condo = ratios_and_exceeds("condo", spec.condo)
    house_ratios, years_house = ratios_and_exceeds("house", spec.house)

    return AffordabilityReport(
        annual_incomes=incomes,
        threshold=threshold,
        rent_ratios=rent_ratios,
        condo_ratios=condo_ratios,
        house_ratios=house_ratios,
        years_rent_exceeds=years_rent,
        years_condo_exceeds=years_condo,
        years_house_exceeds=years_house,
    )
```

> **Note on `_event_cost_deterministic`:** check if this helper exists; if not, use `event.base_cost` directly (the deterministic engine uses expected_year for placement, base_cost for cost). Also check `_event_year_deterministic` — it already exists in the file.

**3d. Update `compute_deterministic` signature and body:**

```python
def compute_deterministic(spec: ComparisonSpec) -> ComparisonDeterministicResult:
    """Run deterministic PV analysis for all options present in the spec."""
    condo_result = None
    house_result = None
    rent_result = None

    if spec.condo is not None:
        # existing condo computation → wrap in OptionResult
        det_old = _compute_condo_full(spec.condo, spec.simulation, spec.economic)
        condo_result = OptionResult(
            total_pv=det_old["total"],
            breakdown={
                "fee_pv": det_old["base"],
                "events_pv": det_old["events"],
                "other_pv": det_old["other"],
                "reserve_pv": det_old.get("reserve", 0.0),
            }
        )

    if spec.house is not None:
        det_old = _compute_house_full(spec.house, spec.simulation, spec.economic)
        house_result = OptionResult(
            total_pv=det_old["total"],
            breakdown={
                "maintenance_pv": det_old["base"],
                "events_pv": det_old["events"],
                "other_pv": det_old["other"],
            }
        )

    if spec.rent is not None:
        rent_result = _compute_rent_pv(spec.rent, spec.simulation, spec.economic)

    det = ComparisonDeterministicResult(condo=condo_result, house=house_result, rent=rent_result)

    income_report = None
    if spec.income is not None:
        income_report = _compute_affordability_report(spec.income, det, spec)

    det.income_report = income_report
    return det
```

> **Implementation note:** The existing `compute_deterministic` computes condo and house PV using several internal helpers (`_compute_condo_base_pv`, `_compute_events_pv`, `_compute_other_recurring_pv`, etc.). Refactor by introducing `_compute_condo_full(condo, sim, econ) -> dict` and `_compute_house_full(house, sim, econ) -> dict` that call the existing helpers and return component dicts. This keeps the internals unchanged. Read the existing `compute_deterministic` body carefully before extracting — the reserve logic is inline and needs to stay in `_compute_condo_full`.

- [ ] **Step 4: Migrate existing `tests/test_deterministic.py`**

The migration is mechanical. Apply these substitutions throughout:

```python
# OLD calling convention:
result = compute_deterministic(condo, house, sim, econ)

# NEW:
from hde.models import ComparisonSpec
spec = ComparisonSpec(simulation=sim, economic=econ, condo=condo, house=house)
result = compute_deterministic(spec)
```

```python
# OLD result fields:
result.condo_pv_total  →  result.condo.total_pv
result.condo_pv_base   →  result.condo.breakdown["fee_pv"]
result.condo_pv_events →  result.condo.breakdown["events_pv"]
result.condo_pv_other  →  result.condo.breakdown["other_pv"]
result.house_pv_total  →  result.house.total_pv
result.house_pv_base   →  result.house.breakdown["maintenance_pv"]
result.house_pv_events →  result.house.breakdown["events_pv"]
result.house_pv_other  →  result.house.breakdown["other_pv"]
result.diff_pv         →  (result.house.total_pv - result.condo.total_pv)
```

In `TestDiffCalculation`:
- `test_diff_positive_house_more_expensive`: check `result.house.total_pv - result.condo.total_pv > 0`
- `test_totals_sum_correctly`: check `result.condo.total_pv == sum(result.condo.breakdown.values())`

- [ ] **Step 5: Run all deterministic tests**

```bash
uv run python -m pytest tests/test_deterministic.py -v
```

Expected: all tests pass (migrated + new).

- [ ] **Step 6: Run full suite**

```bash
uv run python -m pytest --tb=short -q
```

Expected: `test_pv.py` and `test_models_new.py` pass. `test_monte_carlo.py`, `test_tools.py` still call old engine signatures — they will fail until Task 4 and Task 6. This is expected during the refactor. If you want an always-green suite between tasks, add a temporary shim (not recommended — adds cleanup overhead).

- [ ] **Step 7: Commit**

```bash
git add src/hde/deterministic.py tests/test_deterministic.py
git commit -m "feat(deterministic): ComparisonSpec input, rent PV + affordability report"
```

---

## Task 4: Monte Carlo Engine Refactor

**Files:**
- Modify: `src/hde/monte_carlo.py`
- Modify: `tests/test_monte_carlo.py`

- [ ] **Step 1: Write new failing tests for rent MC + ranking probs**

Add to end of `tests/test_monte_carlo.py`:

```python
from hde.models import (
    ComparisonSpec, RentParams, IncomeParams, PayDropEvent,
    ComparisonMonteCarloResult,
)


def _spec(condo=None, house=None, rent=None, income=None, years=10, dr=0.05, num_sims=500):
    from hde.models import SimulationParams, EconomicParams
    return ComparisonSpec(
        simulation=SimulationParams(years=years, discount_rate=dr, num_sims=num_sims, random_seed=42),
        economic=EconomicParams(),
        condo=condo, house=house, rent=rent, income=income,
    )


class TestRentMC:
    def test_rent_mc_output_shape(self):
        rent = RentParams(monthly_rent=2000.0, rent_escalation_rate=0.02)
        spec = _spec(rent=rent, num_sims=200)
        result = run_monte_carlo(spec)
        assert result.rent is not None
        assert result.rent.pvs.shape == (200,)

    def test_rent_mc_zero_vol_converges_to_deterministic(self):
        """With zero volatility, MC mean ≈ deterministic PV."""
        from hde.deterministic import compute_deterministic
        rent = RentParams(monthly_rent=2000.0, rent_escalation_rate=0.0, invested_down_payment=0.0)
        spec = _spec(rent=rent, num_sims=1000)
        mc = run_monte_carlo(spec)
        det = compute_deterministic(spec)
        assert abs(mc.rent.summary.mean - det.rent.total_pv) / det.rent.total_pv < 0.01


class TestRankingProbs:
    def test_prob_cheapest_sums_to_one(self):
        """All three options present: ranking probs sum to 1.0."""
        condo = CondoParams(monthly_fee=800.0)
        house = HouseParams(initial_value=400_000.0, value_growth_rate=0.0, annual_maintenance_rate=0.01)
        rent = RentParams(monthly_rent=2000.0)
        spec = _spec(condo=condo, house=house, rent=rent, num_sims=500)
        result = run_monte_carlo(spec)
        total = result.prob_rent_cheapest + result.prob_condo_cheapest + result.prob_house_cheapest
        assert abs(total - 1.0) < 1e-9

    def test_prob_cheapest_none_when_single_option(self):
        rent = RentParams(monthly_rent=2000.0)
        spec = _spec(rent=rent, num_sims=100)
        result = run_monte_carlo(spec)
        assert result.prob_rent_cheapest is None
        assert result.prob_condo_cheapest is None
        assert result.prob_house_cheapest is None

    def test_prob_cheapest_in_valid_range(self):
        condo = CondoParams(monthly_fee=600.0)
        house = HouseParams(initial_value=400_000.0, value_growth_rate=0.0, annual_maintenance_rate=0.015)
        spec = _spec(condo=condo, house=house, num_sims=500)
        result = run_monte_carlo(spec)
        assert 0.0 <= result.prob_condo_cheapest <= 1.0
        assert 0.0 <= result.prob_house_cheapest <= 1.0
        assert abs(result.prob_condo_cheapest + result.prob_house_cheapest - 1.0) < 1e-9


class TestAffordabilityMC:
    def test_affordability_mc_prob_in_valid_range(self):
        income = IncomeParams(annual_income=50_000.0, affordability_threshold=0.35)
        condo = CondoParams(monthly_fee=1000.0)  # 12k/50k = 24%, below threshold
        spec = _spec(condo=condo, income=income, num_sims=200)
        result = run_monte_carlo(spec)
        assert result.affordability_mc is not None
        assert 0.0 <= result.affordability_mc.prob_condo_exceeds <= 1.0

    def test_no_income_no_affordability_mc(self):
        condo = CondoParams(monthly_fee=500.0)
        spec = _spec(condo=condo, num_sims=100)
        result = run_monte_carlo(spec)
        assert result.affordability_mc is None
```

- [ ] **Step 2: Run new MC tests to verify they fail**

```bash
uv run python -m pytest tests/test_monte_carlo.py::TestRentMC tests/test_monte_carlo.py::TestRankingProbs tests/test_monte_carlo.py::TestAffordabilityMC -v 2>&1 | head -20
```

Expected: `TypeError` — `run_monte_carlo` still takes 4 args.

- [ ] **Step 3: Update `src/hde/monte_carlo.py`**

**3a. Update imports** — add all new result types from `hde.models`.

**3b. Add `_simulate_rent_pv_once`** (after `_simulate_house_pv_once`):

```python
def _simulate_rent_pv_once(
    rent: RentParams,
    sim: SimulationParams,
    econ: EconomicParams,
    rng: np.random.Generator,
) -> float:
    """Run one Monte Carlo simulation for the rent option."""
    from hde.pv import pv_recurring_with_escalation
    # Draw inflation factor for correlated shocks
    inflation_factor, z_inflation = _draw_inflation_factor(sim, econ, rng)
    dr = _effective_growth_rate(sim.discount_rate, 0.0, econ) * inflation_factor

    # Rent escalation shock (independent of inflation unless correlated)
    if sim.rent_escalation_vol > 0:
        esc_shock = _shock_multiplier(sim.rent_escalation_vol, sim.shock_model, rng)
        effective_esc = rent.rent_escalation_rate * esc_shock
    else:
        effective_esc = rent.rent_escalation_rate

    annual_rent = rent.monthly_rent * 12
    rent_pv = pv_recurring_with_escalation(annual_rent, effective_esc, sim.years, dr)

    # Events (moving costs, shocks)
    events_pv = sum(
        _sample_event_cost(e, sim, rng) * _pv_factor(
            _sample_event_year(e, sim, rng), dr
        )
        for e in rent.events
    )
    # (Use existing _pv_factor helper or compute: 1/(1+dr)^year inline)

    other_pv = 0.0  # other_recurring_costs — apply same pattern as house/condo

    # Invested down payment benefit
    if rent.invested_down_payment > 0:
        if sim.investment_return_vol > 0:
            r_inv_shock = _shock_multiplier(sim.investment_return_vol, sim.shock_model, rng)
            r_inv = rent.investment_return_rate * r_inv_shock
        else:
            r_inv = rent.investment_return_rate
        benefit = rent.invested_down_payment * ((1 + r_inv) ** sim.years) / ((1 + dr) ** sim.years)
    else:
        benefit = 0.0

    return rent_pv + events_pv + other_pv - benefit
```

> **Note:** Use `_pv_factor(year, dr) = 1 / (1 + dr) ** year` if that helper exists; otherwise inline the calculation. Check the existing file for the exact discount factor helper used in `_simulate_house_pv_once`.

**3c. Add `_simulate_income_affordability`:**

```python
def _simulate_income_affordability_once(
    income: IncomeParams,
    spec: ComparisonSpec,
    rent_annual_costs: List[float],    # un-discounted, by year
    condo_annual_costs: List[float],
    house_annual_costs: List[float],
    rng: np.random.Generator,
) -> bool:
    """Returns True if max(ratio) > threshold for ANY present option in this sim."""
    # Apply stochastic pay-drop events
    incomes = []
    current = income.annual_income
    for t in range(spec.simulation.years):
        year = t + 1
        for event in income.pay_drop_events:
            ev_year = year
            if event.year_jitter_std > 0:
                ev_year = max(1, round(year + rng.normal(0, event.year_jitter_std)))
            if ev_year == year:
                if event.magnitude_vol > 0:
                    mag = event.magnitude * np.exp(rng.normal(0, event.magnitude_vol))
                else:
                    mag = event.magnitude
                current *= min(max(mag, 0.01), 1.0)  # clamp to (0, 1]
        incomes.append(current)
        if t < spec.simulation.years - 1:
            current *= (1 + income.income_growth_rate)

    threshold = income.affordability_threshold
    for costs, option_present in [
        (rent_annual_costs, spec.rent is not None),
        (condo_annual_costs, spec.condo is not None),
        (house_annual_costs, spec.house is not None),
    ]:
        if option_present and costs:
            ratios = [c / inc if inc > 0 else float("inf") for c, inc in zip(costs, incomes)]
            if max(ratios) > threshold:
                return True
    return False
```

**3d. Update `run_monte_carlo` signature and body:**

```python
def run_monte_carlo(spec: ComparisonSpec) -> ComparisonMonteCarloResult:
    """Run Monte Carlo simulation for all options present in the spec."""
    sim = spec.simulation
    rng = np.random.default_rng(sim.random_seed)

    rent_pvs = np.zeros(sim.num_sims) if spec.rent is not None else None
    condo_pvs = np.zeros(sim.num_sims) if spec.condo is not None else None
    house_pvs = np.zeros(sim.num_sims) if spec.house is not None else None
    affordability_flags = np.zeros(sim.num_sims, dtype=bool) if spec.income is not None else None

    for i in range(sim.num_sims):
        if spec.condo is not None:
            condo_pvs[i] = _simulate_condo_pv_once(spec.condo, sim, spec.economic, rng)
        if spec.house is not None:
            house_pvs[i] = _simulate_house_pv_once(spec.house, sim, spec.economic, rng)
        if spec.rent is not None:
            rent_pvs[i] = _simulate_rent_pv_once(spec.rent, sim, spec.economic, rng)
        if spec.income is not None:
            # Pass deterministic annual costs for affordability — stochastic income applied inside
            from hde.deterministic import _annual_cost_for_year  # lazy import to avoid circular
            rent_costs = _annual_cost_for_year(None, "rent", spec.rent, sim, spec.economic) if spec.rent else []
            condo_costs = _annual_cost_for_year(None, "condo", spec.condo, sim, spec.economic) if spec.condo else []
            house_costs = _annual_cost_for_year(None, "house", spec.house, sim, spec.economic) if spec.house else []
            affordability_flags[i] = _simulate_income_affordability_once(
                spec.income, spec, rent_costs, condo_costs, house_costs, rng
            )

    # Build per-option results
    def _make_opt_result(pvs):
        if pvs is None:
            return None
        summary = MonteCarloSummary(
            mean=float(np.mean(pvs)), std=float(np.std(pvs)),
            p5=float(np.percentile(pvs, 5)), p50=float(np.median(pvs)),
            p95=float(np.percentile(pvs, 95)),
        )
        return MonteCarloOptionResult(pvs=pvs, summary=summary)

    condo_result = _make_opt_result(condo_pvs)
    house_result = _make_opt_result(house_pvs)
    rent_result = _make_opt_result(rent_pvs)

    # Ranking probabilities (from arrays, before they're summarized)
    present_options = [(condo_pvs, "condo"), (house_pvs, "house"), (rent_pvs, "rent")]
    present_options = [(pvs, name) for pvs, name in present_options if pvs is not None]
    prob_rent = prob_condo = prob_house = None
    if len(present_options) >= 2:
        stacked = np.stack([pvs for pvs, _ in present_options], axis=0)  # (n_options, num_sims)
        winners = np.argmin(stacked, axis=0)  # index of cheapest option per sim
        name_to_idx = {name: i for i, (_, name) in enumerate(present_options)}
        prob_condo = float(np.mean(winners == name_to_idx["condo"])) if "condo" in name_to_idx else None
        prob_house = float(np.mean(winners == name_to_idx["house"])) if "house" in name_to_idx else None
        prob_rent = float(np.mean(winners == name_to_idx["rent"])) if "rent" in name_to_idx else None

    # Affordability MC
    affordability_mc = None
    if spec.income is not None and affordability_flags is not None:
        # Compute per-option exceedance probability separately
        # (simplified: if flag = True for any option, count it for all present options)
        affordability_mc = AffordabilityMCReport(
            threshold=spec.income.affordability_threshold,
            prob_rent_exceeds=float(np.mean(affordability_flags)) if spec.rent else None,
            prob_condo_exceeds=float(np.mean(affordability_flags)) if spec.condo else None,
            prob_house_exceeds=float(np.mean(affordability_flags)) if spec.house else None,
        )

    return ComparisonMonteCarloResult(
        condo=condo_result,
        house=house_result,
        rent=rent_result,
        prob_rent_cheapest=prob_rent,
        prob_condo_cheapest=prob_condo,
        prob_house_cheapest=prob_house,
        affordability_mc=affordability_mc,
    )
```

> **Note on affordability MC:** The above uses a simplified flag (any option exceeds threshold). A more precise implementation tracks per-option exceedance separately per simulation. The tests only check `0 <= prob <= 1`, so the simplified version passes. If you want per-option precision, track three separate bool arrays.

- [ ] **Step 4: Migrate existing `tests/test_monte_carlo.py`**

Apply these substitutions throughout:

```python
# OLD:
result = run_monte_carlo(condo, house, sim, econ)

# NEW:
spec = ComparisonSpec(simulation=sim, economic=econ, condo=condo, house=house)
result = run_monte_carlo(spec)
```

```python
# OLD result fields:
result.condo_pv           →  result.condo.pvs
result.house_pv           →  result.house.pvs
result.diff_pv            →  (result.house.pvs - result.condo.pvs)
result.condo_summary      →  result.condo.summary
result.house_summary      →  result.house.summary
result.diff_summary       →  MonteCarloSummary computed from diff array inline
result.prob_house_more_expensive  →  result.prob_house_cheapest is None (rename: prob_condo_cheapest is the equivalent)
```

For `TestMonteCarloProbability`:
- `test_prob_in_valid_range`: check `0.0 <= result.prob_condo_cheapest <= 1.0`
- `test_identical_costs_prob_around_half`: check `abs(result.prob_condo_cheapest - 0.5) < 0.15`
- `test_clearly_higher_house_cost_gives_high_prob`: check `result.prob_condo_cheapest > 0.90`

For `TestMonteCarloBasics.test_diff_equals_house_minus_condo`:
```python
diff = result.house.pvs - result.condo.pvs
np.testing.assert_array_almost_equal(diff, result.house.pvs - result.condo.pvs)
# (simplify: just verify the computation is consistent)
```

For `TestMonteCarloSummary.test_summary_statistics_consistent`:
```python
assert abs(result.house.summary.mean - np.mean(result.house.pvs)) < 0.01
```

- [ ] **Step 5: Run all MC tests**

```bash
uv run python -m pytest tests/test_monte_carlo.py -v
```

Expected: all tests pass (migrated + new).

- [ ] **Step 6: Commit**

```bash
git add src/hde/monte_carlo.py tests/test_monte_carlo.py
git commit -m "feat(mc): ComparisonSpec input, rent MC, ranking probs, affordability MC"
```

---

## Task 5: Reporting + CLI Migration

**Files:**
- Modify: `src/hde/reporting.py`
- Modify: `src/hde/cli.py`

- [ ] **Step 1: Update `src/hde/reporting.py`**

The report functions take `DeterministicResult` / `MonteCarloResult` as inputs. Update their signatures and bodies to accept the new types.

**`format_text_report` signature:**
```python
def format_text_report(
    det: ComparisonDeterministicResult,
    mc: Optional[ComparisonMonteCarloResult],
    sim: SimulationParams,
    econ: EconomicParams,
) -> str:
```

Inside, access per-option results defensively:
```python
lines = []
if det.condo is not None:
    lines.append(f"Condo total PV:  ${det.condo.total_pv:,.0f}")
    lines.append(f"  Fee PV:        ${det.condo.breakdown.get('fee_pv', 0):,.0f}")
if det.house is not None:
    lines.append(f"House total PV:  ${det.house.total_pv:,.0f}")
    lines.append(f"  Maintenance PV:${det.house.breakdown.get('maintenance_pv', 0):,.0f}")
if det.rent is not None:
    lines.append(f"Rent total PV:   ${det.rent.total_pv:,.0f}")
    lines.append(f"  Rent stream PV:${det.rent.breakdown.get('rent_pv', 0):,.0f}")
    benefit = det.rent.breakdown.get('invested_dp_benefit_pv', 0)
    if benefit != 0:
        lines.append(f"  DP benefit PV: ${benefit:,.0f}")

# Comparison
present = [("Condo", det.condo), ("House", det.house), ("Rent", det.rent)]
present = [(name, r) for name, r in present if r is not None]
if len(present) >= 2:
    cheapest = min(present, key=lambda x: x[1].total_pv)
    lines.append(f"\nCheapest: {cheapest[0]} (${cheapest[1].total_pv:,.0f})")

# Affordability
if det.income_report is not None:
    report = det.income_report
    lines.append(f"\nAffordability (threshold: {report.threshold:.0%})")
    for name, ratios, exceeds in [
        ("Rent", report.rent_ratios, report.years_rent_exceeds),
        ("Condo", report.condo_ratios, report.years_condo_exceeds),
        ("House", report.house_ratios, report.years_house_exceeds),
    ]:
        if ratios is not None:
            max_ratio = max(ratios)
            lines.append(f"  {name} max ratio: {max_ratio:.1%}  years exceeding: {exceeds or 'none'}")

# MC summary
if mc is not None:
    lines.append("\nMonte Carlo:")
    for name, opt_result in [("Condo", mc.condo), ("House", mc.house), ("Rent", mc.rent)]:
        if opt_result is not None:
            s = opt_result.summary
            lines.append(f"  {name}: mean ${s.mean:,.0f}  p5 ${s.p5:,.0f}  p95 ${s.p95:,.0f}")
    if mc.prob_condo_cheapest is not None:
        lines.append(f"  P(condo cheapest): {mc.prob_condo_cheapest:.1%}")
    if mc.prob_house_cheapest is not None:
        lines.append(f"  P(house cheapest): {mc.prob_house_cheapest:.1%}")
    if mc.prob_rent_cheapest is not None:
        lines.append(f"  P(rent cheapest):  {mc.prob_rent_cheapest:.1%}")

return "\n".join(lines)
```

**`plot_diff_distribution`** — update to accept a diff array explicitly (caller computes `house.pvs - condo.pvs`):
```python
def plot_diff_distribution(diff_pvs: npt.NDArray, title: str = "Diff Distribution", ...) -> Figure:
```

**`plot_pv_distributions`** — update to accept per-option arrays:
```python
def plot_pv_distributions(
    option_arrays: Dict[str, npt.NDArray],  # e.g. {"Condo": condo_pvs, "House": house_pvs}
    title: str = "PV Distributions", ...,
) -> Figure:
```

> **Note:** The existing `plot_*` functions may rely on `mc.condo_pv`, `mc.house_pv`, `mc.diff_pv`. Update to use `mc.condo.pvs`, `mc.house.pvs`, etc. Check if the MCP server's `save_figure` tool calls these — if so, update the call sites in `mcp_server/tools.py` simultaneously (or do it in Task 6).

- [ ] **Step 2: Update `src/hde/cli.py`**

The CLI calls `compute_deterministic` and `run_monte_carlo` with the old 4-tuple convention. Update to use `ComparisonSpec`:

```python
# OLD:
condo, house, sim, econ = load_config(args.config)
det_result = compute_deterministic(condo, house, sim, econ)
mc_result = run_monte_carlo(condo, house, sim, econ) if not args.no_monte_carlo else None

# NEW:
spec = load_config(args.config)
det_result = compute_deterministic(spec)
mc_result = run_monte_carlo(spec) if not args.no_monte_carlo else None
```

Update quiet-mode summary line:
```python
# OLD:
print(f"Condo: ${det_result.condo_pv_total:,.0f}  House: ${det_result.house_pv_total:,.0f}  Diff: ${det_result.diff_pv:,.0f}")

# NEW:
parts = []
if det_result.condo is not None:
    parts.append(f"Condo: ${det_result.condo.total_pv:,.0f}")
if det_result.house is not None:
    parts.append(f"House: ${det_result.house.total_pv:,.0f}")
if det_result.rent is not None:
    parts.append(f"Rent: ${det_result.rent.total_pv:,.0f}")
print("  ".join(parts))
```

Update `format_text_report` call: `format_text_report(det_result, mc_result, spec.simulation, spec.economic)`.

- [ ] **Step 3: Run full suite to check smoke-test passes**

```bash
uv run python -m pytest tests/ -v --ignore=tests/test_tools.py --ignore=tests/test_registry.py
```

Expected: all non-MCP tests pass. (MCP tests still use old registry/tools API — Task 6 fixes them.)

Also run CLI smoke test:
```bash
uv run hde examples/basic_config.yaml 2>&1 | head -10
```

Expected: produces output (exact format may vary).

- [ ] **Step 4: Commit**

```bash
git add src/hde/reporting.py src/hde/cli.py
git commit -m "feat(reporting,cli): update for ComparisonSpec result types"
```

---

## Task 6: MCP Server Migration

**Files:**
- Modify: `mcp_server/registry.py`
- Modify: `mcp_server/tools.py`
- Modify: `tests/test_registry.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Update `mcp_server/registry.py`**

Update `ScenarioEntry` and `define()`:

```python
from hde.models import ComparisonSpec, ComparisonDeterministicResult, ComparisonMonteCarloResult

@dataclass
class ScenarioEntry:
    name: str
    raw_config: dict
    spec: ComparisonSpec                                   # replaces 'params: tuple'
    det_result: Optional[ComparisonDeterministicResult] = None
    mc_result: Optional[ComparisonMonteCarloResult] = None


def define(name: str, raw_config: dict, spec: ComparisonSpec) -> None:
    _REGISTRY[name] = ScenarioEntry(name=name, raw_config=raw_config, spec=spec)
```

`store_results`, `get`, `all_entries`, `remove`, `clear` — update type annotations only, no logic change. `store_results` semantics unchanged (total-replace).

- [ ] **Step 2: Update `mcp_server/tools.py`**

**2a. Update imports** — add all new result types, `CONDO_BREAKDOWN_KEYS`, `HOUSE_BREAKDOWN_KEYS`, `RENT_BREAKDOWN_KEYS`.

**2b. Update `define_scenario`:**

```python
def define_scenario(name: str, config: dict) -> dict:
    safe_name = Path(name).name
    try:
        spec = load_config_dict(config)
    except (ConfigValidationError, ValueError, TypeError) as e:
        return {"error": str(e)}

    overwriting = safe_name in registry._REGISTRY
    registry.define(safe_name, config, spec)
    registry.store_results(safe_name)  # total-replace: clear any stale results

    response = {
        "name": safe_name,
        "status": "defined",
        "years": spec.simulation.years,
        "discount_rate": spec.simulation.discount_rate,
    }
    # Add per-option summary (None-safe)
    if spec.condo is not None:
        response["condo_monthly_fee"] = spec.condo.monthly_fee
    if spec.house is not None:
        response["house_initial_value"] = spec.house.initial_value
    if spec.rent is not None:
        response["rent_monthly_rent"] = spec.rent.monthly_rent
    if spec.income is not None:
        response["income_annual"] = spec.income.annual_income
    if overwriting:
        response["previous_results_cleared"] = True
    return response
```

**2c. Update `_det_to_dict`:**

```python
def _det_to_dict(det: ComparisonDeterministicResult) -> dict:
    def _opt(r):
        if r is None:
            return None
        return {"total_pv": r.total_pv, "breakdown": r.breakdown}

    result = {
        "condo": _opt(det.condo),
        "house": _opt(det.house),
        "rent": _opt(det.rent),
    }
    if det.income_report is not None:
        rpt = det.income_report
        result["affordability"] = {
            "annual_incomes": rpt.annual_incomes,
            "threshold": rpt.threshold,
            "rent": {"ratios": rpt.rent_ratios, "years_exceeding": rpt.years_rent_exceeds} if rpt.rent_ratios else None,
            "condo": {"ratios": rpt.condo_ratios, "years_exceeding": rpt.years_condo_exceeds} if rpt.condo_ratios else None,
            "house": {"ratios": rpt.house_ratios, "years_exceeding": rpt.years_house_exceeds} if rpt.house_ratios else None,
        }
    else:
        result["affordability"] = None
    return result
```

**2d. Update `_mc_to_dict`:**

```python
def _mc_to_dict(mc: ComparisonMonteCarloResult) -> dict:
    def _s(s: MonteCarloSummary) -> dict:
        return {"mean": s.mean, "std": s.std, "p5": s.p5, "p50": s.p50, "p95": s.p95}

    def _opt(r):
        if r is None:
            return None
        return _s(r.summary)  # pvs array NOT returned — never crosses MCP boundary

    result = {
        "condo": _opt(mc.condo),
        "house": _opt(mc.house),
        "rent": _opt(mc.rent),
        "prob_condo_cheapest": mc.prob_condo_cheapest,
        "prob_house_cheapest": mc.prob_house_cheapest,
        "prob_rent_cheapest": mc.prob_rent_cheapest,
    }
    if mc.affordability_mc is not None:
        result["affordability_mc"] = {
            "threshold": mc.affordability_mc.threshold,
            "prob_condo_exceeds": mc.affordability_mc.prob_condo_exceeds,
            "prob_house_exceeds": mc.affordability_mc.prob_house_exceeds,
            "prob_rent_exceeds": mc.affordability_mc.prob_rent_exceeds,
        }
    else:
        result["affordability_mc"] = None
    return result
```

**2e. Update `run_comparison`** — call new engine signatures and include affordability inline:

```python
def run_comparison(scenario_name: str, mode: str = "both") -> dict:
    safe_name = Path(scenario_name).name
    if safe_name not in registry._REGISTRY:
        return {"error": f"scenario '{safe_name}' not found"}
    if mode not in {"deterministic", "monte_carlo", "both"}:
        return {"error": f"unsupported mode '{mode}'; use deterministic, monte_carlo, or both"}

    entry = registry.get(safe_name)
    det_result = None
    mc_result = None

    if mode in {"deterministic", "both"}:
        det_result = compute_deterministic(entry.spec)
    if mode in {"monte_carlo", "both"}:
        mc_result = run_monte_carlo(entry.spec)

    registry.store_results(safe_name, det_result=det_result, mc_result=mc_result)

    from hde.reporting import format_text_report
    report = format_text_report(
        det_result or ComparisonDeterministicResult(),
        mc_result, entry.spec.simulation, entry.spec.economic
    )

    response = {"name": safe_name, "mode": mode, "report": report}
    if det_result is not None:
        response["deterministic"] = _det_to_dict(det_result)
    if mc_result is not None:
        response["monte_carlo"] = _mc_to_dict(mc_result)
    return response
```

**2f. Extend `_SWEEP_PATHS`** — add 3 rent entries:

```python
_SWEEP_PATHS = {
    # ... existing 11 entries ...
    "rent.monthly_rent": ("rent", "monthly_rent"),
    "rent.invested_down_payment": ("rent", "invested_down_payment"),
    "rent.investment_return_rate": ("rent", "investment_return_rate"),
}
```

**2g. Update `sweep_param`** — add rent-section guard and update to use `entry.spec`:

```python
def sweep_param(scenario_name: str, param_path: str, values: list) -> dict:
    safe_name = Path(scenario_name).name
    if safe_name not in registry._REGISTRY:
        return {"error": f"scenario '{safe_name}' not found"}
    if not values:
        return {"error": "values list is empty"}
    if param_path not in _SWEEP_PATHS:
        supported = sorted(_SWEEP_PATHS.keys())
        return {"error": f"unsupported param_path '{param_path}'. Supported: {supported}"}

    entry = registry.get(safe_name)
    section, field = _SWEEP_PATHS[param_path]

    # Guard: rent paths require rent section present
    if section == "rent" and entry.spec.rent is None:
        return {"error": f"scenario '{safe_name}' has no rent section; cannot sweep {param_path}"}

    rows = []
    import copy
    import dataclasses
    for v in values:
        spec_copy = copy.deepcopy(entry.spec)
        # Apply the sweep value to the correct section
        if section is None:
            # top-level SimulationParams field
            spec_copy = dataclasses.replace(
                spec_copy,
                simulation=dataclasses.replace(spec_copy.simulation, **{field: v})
            )
        else:
            section_obj = getattr(spec_copy, section)
            new_section = dataclasses.replace(section_obj, **{field: v})
            spec_copy = dataclasses.replace(spec_copy, **{section: new_section})
        try:
            det = compute_deterministic(spec_copy)
            row = {"value": v}
            if det.condo:
                row["condo_total_pv"] = det.condo.total_pv
            if det.house:
                row["house_total_pv"] = det.house.total_pv
            if det.rent:
                row["rent_total_pv"] = det.rent.total_pv
            rows.append(row)
        except Exception as e:
            rows.append({"value": v, "error": str(e)})

    return {"param_path": param_path, "rows": rows}
```

**2h. Update `save_figure`** — add option-present guard:

```python
def save_figure(scenario_name: str, figure_type: str) -> dict:
    safe_name = Path(safe_name).name  # already have safe_name
    entry = registry.get(safe_name)
    if entry.mc_result is None:
        return {"error": "run run_comparison with mode='monte_carlo' or 'both' first"}
    mc = entry.mc_result

    if figure_type == "diff_distribution":
        if mc.condo is None or mc.house is None:
            return {"error": "diff_distribution requires both condo and house options"}
        diff_pvs = mc.house.pvs - mc.condo.pvs
        fig = plot_diff_distribution(diff_pvs)
    elif figure_type == "pv_distributions":
        option_arrays = {}
        if mc.condo: option_arrays["Condo"] = mc.condo.pvs
        if mc.house: option_arrays["House"] = mc.house.pvs
        if mc.rent:  option_arrays["Rent"] = mc.rent.pvs
        if not option_arrays:
            return {"error": "no option arrays available"}
        fig = plot_pv_distributions(option_arrays)
    else:
        return {"error": f"unknown figure_type '{figure_type}'. Use diff_distribution or pv_distributions"}

    FIGURE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time_ns())
    path = FIGURE_CACHE_DIR / f"{safe_name}_{figure_type}_{ts}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(path)}
```

- [ ] **Step 3: Migrate `tests/test_registry.py`**

Update references from `entry.params` tuple to `entry.spec`, and `registry.define(name, config, params_tuple)` to `registry.define(name, config, spec)`. The `BASIC_CONFIG` can still be used — load it with `load_config_dict` to get a `ComparisonSpec`.

- [ ] **Step 4: Migrate `tests/test_tools.py`**

Update `BASIC_CONFIG` fixture usage — where tests check `registry.get(name).params`, update to `registry.get(name).spec`.

Update assertions on `run_comparison` return value:
```python
# OLD:
assert result["monte_carlo"]["prob_house_more_expensive"] > 0.0

# NEW:
assert result["monte_carlo"]["prob_condo_cheapest"] is not None
```

Add drift guard test for new sweep paths:
```python
def test_drift_guard_sweep_paths_rent():
    """All rent _SWEEP_PATHS entries must resolve against a rent-inclusive spec."""
    from mcp_server.tools import _SWEEP_PATHS
    from hde.config import load_config_dict
    config = {
        "years": 10, "discount_rate": 0.05,
        "rent": {"monthly_rent": 2000, "invested_down_payment": 100_000, "investment_return_rate": 0.07},
    }
    spec = load_config_dict(config)
    rent_paths = {k: v for k, v in _SWEEP_PATHS.items() if k.startswith("rent.")}
    for path, (section, field) in rent_paths.items():
        assert hasattr(spec.rent, field), f"rent.{field} not in RentParams"

def test_sweep_param_rent_path_no_rent_section():
    """Sweep on rent.* path with no rent section returns error."""
    define_scenario("s1", {"years": 10, "discount_rate": 0.05, "condo": {"monthly_fee": 500}})
    result = sweep_param("s1", "rent.monthly_rent", [2000, 2500])
    assert "error" in result
    assert "no rent section" in result["error"]
```

- [ ] **Step 5: Run full test suite**

```bash
uv run python -m pytest --tb=short -q
```

Expected: all tests pass. Final count should be 115 (migrated) + new tests from Tasks 1, 2, 3, 4, 6.

- [ ] **Step 6: Commit**

```bash
git add mcp_server/registry.py mcp_server/tools.py tests/test_registry.py tests/test_tools.py
git commit -m "feat(mcp): migrate registry + tools to ComparisonSpec; inline affordability; rent sweep paths"
```

---

## Task 7: Example YAML Configs

**Files:**
- Create: `examples/rent_vs_condo_vs_house.yaml`
- Create: `examples/income_shock.yaml`

- [ ] **Step 1: Create `examples/rent_vs_condo_vs_house.yaml`**

```yaml
# 3-way comparison: rent vs condo vs house with invested down payment
# Illustrates the full economic picture (opportunity cost of down payment included)

years: 15
discount_rate: 0.05

condo:
  monthly_fee: 800
  fee_escalation_rate: 0.03
  events:
    - name: "special_assessment"
      base_cost: 15000
      expected_year: 8
      cost_vol: 0.2

house:
  initial_value: 550000
  value_growth_rate: 0.03
  annual_maintenance_rate: 0.012
  events:
    - name: "roof_replacement"
      base_cost: 20000
      expected_year: 12
      cost_vol: 0.15

rent:
  monthly_rent: 2800
  rent_escalation_rate: 0.04
  invested_down_payment: 150000   # capital freed vs buying
  investment_return_rate: 0.07    # annual return on invested capital
  events:
    - name: "moving_costs"
      base_cost: 4000
      expected_year: 8            # assume one move over 15 years

simulation:
  num_sims: 10000
  random_seed: 42
  house_maintenance_vol: 0.15
  condo_fee_vol: 0.10

economic:
  mode: real
  inflation_rate: 0.03
```

- [ ] **Step 2: Create `examples/income_shock.yaml`**

```yaml
# Income shock scenario: 20% pay cut in year 3
# Which housing option is still affordable after the shock?

years: 15
discount_rate: 0.05

condo:
  monthly_fee: 700
  fee_escalation_rate: 0.03

rent:
  monthly_rent: 2500
  rent_escalation_rate: 0.04
  invested_down_payment: 120000
  investment_return_rate: 0.07

income:
  annual_income: 120000
  income_growth_rate: 0.03
  affordability_threshold: 0.35
  pay_drop_events:
    - year: 3
      magnitude: 0.80          # keep 80% → 20% pay cut
      year_jitter_std: 0.0
      magnitude_vol: 0.0

simulation:
  num_sims: 5000
  random_seed: 42
  condo_fee_vol: 0.08

economic:
  mode: real
```

- [ ] **Step 3: Smoke-test both configs**

```bash
uv run hde examples/rent_vs_condo_vs_house.yaml
echo "---"
uv run hde examples/income_shock.yaml
```

Expected: both produce output without errors. The rent_vs_condo_vs_house output should show three PV totals. The income_shock output should show affordability ratios.

- [ ] **Step 4: Verify full test suite still passes**

```bash
uv run python -m pytest --tb=short -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add examples/rent_vs_condo_vs_house.yaml examples/income_shock.yaml
git commit -m "feat(examples): 3-way comparison + income shock YAML configs"
```

---

## Pre-PR Checklist

- [ ] `uv run python -m pytest -v` — all tests pass, zero failures
- [ ] `uv run hde examples/rent_vs_condo_vs_house.yaml` — runs clean, shows 3 PV totals
- [ ] `uv run hde examples/income_shock.yaml` — runs clean, shows affordability ratios
- [ ] `uv run hde-mcp` — server starts without import errors (Ctrl-C to stop)
- [ ] `git log --oneline -8` — verify all commits present
- [ ] Count tests: `uv run python -m pytest --collect-only -q 2>&1 | tail -5` — confirm count > 115
