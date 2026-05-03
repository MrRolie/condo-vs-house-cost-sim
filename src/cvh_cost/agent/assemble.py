"""Assemble the compute-core dataclasses from intake answers + market data.

This module bridges the human-driven intake layer (``cvh_cost.agent.intake``)
and the pure-compute parameter dataclasses in ``cvh_cost.core.models``. For
every field on :class:`AssembledParams`, the resolution order is:

1. The user's answer to the question whose ``target`` points at that field.
2. A relevant value from ``session.market`` (e.g. a Treasury yield).
3. The dataclass field's default.

Each populated field is annotated in ``AssembledParams.provenance`` with a
short string explaining where the value came from (``"user:<qid>"``,
``"market:<key>"``, ``"default"``, or ``"derived:<reason>"``).
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from cvh_cost.core.models import (
    CondoParams,
    EconomicParams,
    EventConfig,
    HouseParams,
    RecurringOtherCost,
    SimulationParams,
)
from cvh_cost.agent.intake import (
    QUESTION_BANK,
    coerce_answer,
    missing_required,
    validate_answer,
)
from cvh_cost.agent.session import AssembledParams, get_session


# ---------------------------------------------------------------------------
# Defaults (mirrors of dataclass defaults; kept here so resolution rules are
# explicit and discoverable, not silent).
# ---------------------------------------------------------------------------

_DEFAULT_HORIZON_YEARS = 20
_DEFAULT_DISCOUNT_RATE = 0.03
_DEFAULT_NUM_SIMS = 10_000
_DEFAULT_RANDOM_SEED = 42
_DEFAULT_ECON_MODE: Literal["real", "nominal"] = "real"
_DEFAULT_INFLATION_RATE = 0.0

_DEFAULT_HOA_GROWTH = 0.02
_DEFAULT_RESERVE_BALANCE = 0.0
_DEFAULT_RESERVE_CONTRIB = 0.0

_DEFAULT_HOUSE_VALUE_GROWTH = 0.02
_DEFAULT_HOUSE_MAINT_RATE = 0.012

_DEFAULT_HOUSE_MAINT_VOL = 0.25
_DEFAULT_CONDO_FEE_VOL = 0.05
_DEFAULT_OTHER_COST_VOL = 0.10


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _coerced_or_none(intake: dict[str, Any], qid: str) -> Any:
    """Return the coerced value for ``qid`` if present and not ``None``."""
    if qid not in intake:
        return None
    raw = intake[qid]
    if raw is None:
        return None
    return coerce_answer(qid, raw)


def _resolve(
    intake: dict[str, Any],
    market: dict[str, Any],
    qid: Optional[str],
    market_key: Optional[str],
    default: Any,
) -> tuple[Any, str]:
    """Resolve a single field. Returns ``(value, provenance_string)``."""
    if qid is not None:
        v = _coerced_or_none(intake, qid)
        if v is not None:
            return v, f"user:{qid}"
    if market_key is not None and market_key in market and market[market_key] is not None:
        return market[market_key], f"market:{market_key}"
    return default, "default"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def assemble_from_session() -> AssembledParams:
    """Build :class:`AssembledParams` from the current session.

    Reads ``session.intake`` and ``session.market``, applies the resolution
    rules documented at the top of this module, sets ``session.params`` to
    the result, and returns it. Safe to call repeatedly.
    """
    s = get_session()
    intake = s.intake
    market = s.market

    provenance: dict[str, str] = {}

    # ---------- Simulation horizon & discounting ----------
    years_val, years_prov = _resolve(
        intake, market, qid="horizon_years", market_key=None, default=_DEFAULT_HORIZON_YEARS
    )
    years = int(years_val)
    provenance["sim.years"] = years_prov

    # Discount rate: explicit branch by user-selected source.
    discount_source = _coerced_or_none(intake, "discount_rate_source")
    if discount_source == "use_custom":
        custom = _coerced_or_none(intake, "discount_rate_custom")
        if custom is not None:
            discount_rate = float(custom)
            provenance["sim.discount_rate"] = "user:discount_rate_custom"
        elif "treasury_10y" in market and market["treasury_10y"] is not None:
            # User said custom but never provided one; fall back to market.
            discount_rate = float(market["treasury_10y"])
            provenance["sim.discount_rate"] = "derived:custom_requested_but_missing,fell_back_to_market:treasury_10y"
        else:
            discount_rate = _DEFAULT_DISCOUNT_RATE
            provenance["sim.discount_rate"] = "default"
    else:
        # use_market_rate or unset
        if "treasury_10y" in market and market["treasury_10y"] is not None:
            discount_rate = float(market["treasury_10y"])
            provenance["sim.discount_rate"] = "market:treasury_10y"
        else:
            # Fall through to a custom value only if the user actually gave one.
            custom = _coerced_or_none(intake, "discount_rate_custom")
            if custom is not None:
                discount_rate = float(custom)
                provenance["sim.discount_rate"] = "user:discount_rate_custom"
            else:
                discount_rate = _DEFAULT_DISCOUNT_RATE
                provenance["sim.discount_rate"] = "default"

    num_sims_val, num_sims_prov = _resolve(
        intake, market, qid="mc_num_sims", market_key=None, default=_DEFAULT_NUM_SIMS
    )
    num_sims = int(num_sims_val)
    provenance["sim.num_sims"] = num_sims_prov

    provenance["sim.random_seed"] = "default"

    # Volatilities: defaults for now.
    provenance["sim.house_maintenance_vol"] = "default"
    provenance["sim.condo_fee_vol"] = "default"
    provenance["sim.other_cost_vol"] = "default"

    sim = SimulationParams(
        years=years,
        discount_rate=discount_rate,
        num_sims=num_sims,
        random_seed=_DEFAULT_RANDOM_SEED,
        house_maintenance_vol=_DEFAULT_HOUSE_MAINT_VOL,
        condo_fee_vol=_DEFAULT_CONDO_FEE_VOL,
        other_cost_vol=_DEFAULT_OTHER_COST_VOL,
    )

    # ---------- Economic params ----------
    mode_val, mode_prov = _resolve(
        intake, market, qid="economic_mode", market_key=None, default=_DEFAULT_ECON_MODE
    )
    mode: Literal["real", "nominal"] = "nominal" if mode_val == "nominal" else "real"
    provenance["econ.mode"] = mode_prov

    if mode == "nominal" and "cpi_yoy" in market and market["cpi_yoy"] is not None:
        inflation_rate = float(market["cpi_yoy"])
        provenance["econ.inflation_rate"] = "market:cpi_yoy"
    else:
        inflation_rate = _DEFAULT_INFLATION_RATE
        provenance["econ.inflation_rate"] = "default"

    econ = EconomicParams(mode=mode, inflation_rate=inflation_rate, inflation_vol=0.0)

    # ---------- Condo ----------
    monthly_fee_val, monthly_fee_prov = _resolve(
        intake, market, qid="condo_monthly_hoa", market_key=None, default=0.0
    )
    monthly_fee = float(monthly_fee_val)
    provenance["condo.monthly_fee"] = monthly_fee_prov

    fee_growth_val, fee_growth_prov = _resolve(
        intake, market, qid="condo_hoa_growth", market_key=None, default=_DEFAULT_HOA_GROWTH
    )
    fee_growth = float(fee_growth_val)
    provenance["condo.fee_escalation_rate"] = fee_growth_prov

    reserve_bal_val, reserve_bal_prov = _resolve(
        intake, market, qid="condo_reserve_balance", market_key=None, default=_DEFAULT_RESERVE_BALANCE
    )
    reserve_balance = float(reserve_bal_val)
    provenance["condo.reserve_initial_balance"] = reserve_bal_prov

    reserve_contrib_val, reserve_contrib_prov = _resolve(
        intake, market, qid="condo_reserve_contribution_rate", market_key=None, default=_DEFAULT_RESERVE_CONTRIB
    )
    reserve_contrib = float(reserve_contrib_val)
    provenance["condo.reserve_contribution_rate"] = reserve_contrib_prov

    # Preserve any events/recurring costs already on the existing session.params
    # so reassembly after add_event() doesn't wipe them out.
    prior_condo_events: list[EventConfig] = []
    prior_condo_other: list[RecurringOtherCost] = []
    prior_house_events: list[EventConfig] = []
    prior_house_other: list[RecurringOtherCost] = []
    if s.params is not None:
        prior_condo_events = list(s.params.condo.events)
        prior_condo_other = list(s.params.condo.other_recurring_costs)
        prior_house_events = list(s.params.house.events)
        prior_house_other = list(s.params.house.other_recurring_costs)

    condo = CondoParams(
        monthly_fee=monthly_fee,
        fee_escalation_rate=fee_growth,
        events=prior_condo_events,
        other_recurring_costs=prior_condo_other,
        reserve_contribution_rate=reserve_contrib,
        reserve_initial_balance=reserve_balance,
    )

    # ---------- House ----------
    house_price_val, house_price_prov = _resolve(
        intake, market, qid="house_price", market_key=None, default=0.0
    )
    house_initial = float(house_price_val)
    provenance["house.initial_value"] = house_price_prov

    house_growth_val, house_growth_prov = _resolve(
        intake, market, qid="house_value_growth", market_key=None, default=_DEFAULT_HOUSE_VALUE_GROWTH
    )
    house_growth = float(house_growth_val)
    provenance["house.value_growth_rate"] = house_growth_prov

    house_maint_val, house_maint_prov = _resolve(
        intake, market, qid="house_maintenance_rate", market_key=None, default=_DEFAULT_HOUSE_MAINT_RATE
    )
    house_maint = float(house_maint_val)
    provenance["house.annual_maintenance_rate"] = house_maint_prov

    house = HouseParams(
        initial_value=house_initial,
        value_growth_rate=house_growth,
        annual_maintenance_rate=house_maint,
        events=prior_house_events,
        other_recurring_costs=prior_house_other,
    )

    assembled = AssembledParams(
        condo=condo,
        house=house,
        sim=sim,
        econ=econ,
        provenance=provenance,
    )
    s.params = assembled
    s.log("assemble_from_session", provenance=dict(provenance))
    return assembled


def add_event(side: Literal["condo", "house"], **kwargs: Any) -> EventConfig:
    """Append an :class:`EventConfig` to ``session.params.{side}.events``.

    Raises:
        ValueError: if ``session.params`` has not been assembled yet, or
            ``side`` is not ``"condo"`` / ``"house"``.
    """
    s = get_session()
    if s.params is None:
        raise ValueError("session.params not assembled — call assemble_from_session() first")
    if side not in ("condo", "house"):
        raise ValueError(f"side must be 'condo' or 'house', got {side!r}")
    event = EventConfig(**kwargs)
    target = getattr(s.params, side)
    target.events.append(event)
    s.log("add_event", side=side, event=kwargs)
    return event


def add_other_recurring(side: Literal["condo", "house"], **kwargs: Any) -> RecurringOtherCost:
    """Append a :class:`RecurringOtherCost` to ``session.params.{side}``.

    Raises:
        ValueError: if ``session.params`` has not been assembled yet, or
            ``side`` is not ``"condo"`` / ``"house"``.
    """
    s = get_session()
    if s.params is None:
        raise ValueError("session.params not assembled — call assemble_from_session() first")
    if side not in ("condo", "house"):
        raise ValueError(f"side must be 'condo' or 'house', got {side!r}")
    cost = RecurringOtherCost(**kwargs)
    target = getattr(s.params, side)
    target.other_recurring_costs.append(cost)
    s.log("add_other_recurring", side=side, cost=kwargs)
    return cost


def intake_summary() -> dict:
    """Return a structured view of the current intake state.

    Format::

        {
          "by_section": {
            "horizon": {qid: answer, ...},
            "condo":   {qid: answer, ...},
            "house":   {qid: answer, ...},
            "risk":    {qid: answer, ...},
          },
          "missing_required": [qid, ...],
          "unknown_keys": [qid, ...],   # keys in intake not in QUESTION_BANK
        }
    """
    s = get_session()
    answers = s.intake
    by_section: dict[str, dict[str, Any]] = {}
    for qid, q in QUESTION_BANK.items():
        if qid in answers and answers[qid] is not None:
            by_section.setdefault(q.section, {})[qid] = answers[qid]
    missing = [q.id for q in missing_required(answers)]
    unknown = [k for k in answers.keys() if k not in QUESTION_BANK]
    return {
        "by_section": by_section,
        "missing_required": missing,
        "unknown_keys": unknown,
    }


def set_intake(qid: str, value: Any) -> None:
    """Validate, coerce, and write ``value`` into ``session.intake[qid]``.

    Raises:
        KeyError: if ``qid`` is not in :data:`QUESTION_BANK`.
        ValueError: if ``value`` fails validation for ``qid``.
    """
    if qid not in QUESTION_BANK:
        raise KeyError(f"unknown question id: {qid!r}")
    ok, err = validate_answer(qid, value)
    if not ok:
        raise ValueError(f"invalid answer for {qid!r}: {err}")
    s = get_session()
    if value is None:
        s.intake[qid] = None
    else:
        s.intake[qid] = coerce_answer(qid, value)
    s.log("set_intake", qid=qid, value=s.intake[qid])


__all__ = [
    "assemble_from_session",
    "add_event",
    "add_other_recurring",
    "intake_summary",
    "set_intake",
]
