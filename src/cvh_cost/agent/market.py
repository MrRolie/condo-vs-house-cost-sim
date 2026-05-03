"""Market data fetchers for the agent layer.

For now these are fixture-backed: each function loads a small JSON file from
``cvh_cost/agent/fixtures/`` and caches the result on the
:class:`AgentSession`. The signatures match the future live-fetch interface
(`as_of`, `term`, etc.) so a later ``--online`` flag can swap implementations
without touching the call sites in ``assemble.py`` or the agent loop.

All return values are plain JSON-safe dicts. The ``source`` field is
``"fixture"`` for everything in this module; live sources will populate it
with ``"treasury.gov"``, ``"fred"``, etc.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Optional

from cvh_cost.agent.session import get_session


# ----- internal helpers -----

_FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Tenor strings, in ascending year-equivalent order, used by
# ``recommend_discount_rate`` to pick the closest match.
_TENOR_YEARS: dict[str, float] = {
    "1m": 1 / 12,
    "3m": 0.25,
    "6m": 0.5,
    "1y": 1.0,
    "2y": 2.0,
    "3y": 3.0,
    "5y": 5.0,
    "7y": 7.0,
    "10y": 10.0,
    "20y": 20.0,
    "30y": 30.0,
}

# Subset of tenors recommend_discount_rate selects from (per spec).
_RECOMMEND_TENORS: tuple[str, ...] = ("1y", "2y", "3y", "5y", "7y", "10y", "20y", "30y")


def _load_fixture(name: str) -> dict:
    """Read ``fixtures/<name>`` and return a fresh dict each call."""
    path = _FIXTURES_DIR / name
    with path.open("r", encoding="utf-8") as f:
        loaded: dict = json.load(f)
    return loaded


# ----- public tool surface -----

def fetch_rate_curve(as_of: Optional[str] = None) -> dict:
    """Return the Treasury par yield curve as of a given date.

    Output shape::

        {"as_of": "2026-05-02", "source": "fixture",
         "yields": {"1m": 0.0445, ..., "30y": 0.0468}}

    The ``as_of`` argument is currently informational (the fixture only
    contains one date). Caches the full curve under
    ``session.market['rate_curve']`` and the 10y yield under
    ``session.market['treasury_10y']`` for convenient access from
    ``assemble.py``.
    """
    data = _load_fixture("treasury_curve.json")

    s = get_session()
    s.market["rate_curve"] = data
    yields = data.get("yields", {})
    if "10y" in yields:
        s.market["treasury_10y"] = float(yields["10y"])
    return data


def fetch_mortgage_rate(term: int = 30, as_of: Optional[str] = None) -> dict:
    """Return the headline mortgage rate for ``term`` years (15 or 30).

    Output shape::

        {"as_of": "2026-05-02", "source": "fixture",
         "term": 30, "rate": 0.0635}

    Caches under ``session.market[f'mortgage_{term}y']``.
    """
    if term not in (15, 30):
        raise ValueError(f"unsupported mortgage term: {term} (expected 15 or 30)")

    data = _load_fixture("inflation.json")
    key = f"mortgage_{term}y"
    if key not in data:
        raise KeyError(f"mortgage fixture missing key {key!r}")

    out = {
        "as_of": data["as_of"],
        "source": data.get("source", "fixture"),
        "term": term,
        "rate": float(data[key]),
    }

    s = get_session()
    s.market[f"mortgage_{term}y"] = out
    return out


def fetch_inflation_expectations(as_of: Optional[str] = None) -> dict:
    """Return CPI and Treasury breakeven inflation expectations.

    Output shape::

        {"as_of": "2026-05-02", "source": "fixture",
         "cpi_yoy": 0.026, "core_cpi_yoy": 0.029,
         "breakeven_5y": 0.024, "breakeven_10y": 0.023}

    Caches the full dict under ``session.market['inflation']`` and a
    ``cpi_yoy`` shortcut under ``session.market['cpi_yoy']``.
    """
    data = _load_fixture("inflation.json")

    out = {
        "as_of": data["as_of"],
        "source": data.get("source", "fixture"),
        "cpi_yoy": float(data["cpi_yoy"]),
        "core_cpi_yoy": float(data["core_cpi_yoy"]),
        "breakeven_5y": float(data["breakeven_5y"]),
        "breakeven_10y": float(data["breakeven_10y"]),
    }

    s = get_session()
    s.market["inflation"] = out
    s.market["cpi_yoy"] = out["cpi_yoy"]
    return out


def fetch_regional_benchmarks(region: str) -> dict:
    """Look up typical maintenance / insurance / HOA values for ``region``.

    Performs a case-insensitive substring match: lowercase the input, then
    return the first non-default region key contained in the lowercased
    input. If nothing matches, return the ``"default"`` entry.

    Adds a ``matched_region`` field to the returned dict so the caller knows
    which key was used. Caches the result under
    ``session.market[f'benchmark:{matched_region}']``.
    """
    data = _load_fixture("regional_benchmarks.json")
    regions: dict[str, dict] = data.get("regions", {})

    needle = (region or "").lower().strip()
    matched_key = "default"
    if needle:
        for key in regions:
            if key == "default":
                continue
            if key in needle:
                matched_key = key
                break

    entry = regions.get(matched_key) or regions["default"]
    out = {
        "as_of": data["as_of"],
        "source": data.get("source", "fixture"),
        "matched_region": matched_key,
        "query": region,
        **entry,
    }

    s = get_session()
    s.market[f"benchmark:{matched_key}"] = out
    return out


def recommend_discount_rate(horizon_years: int, mode: str = "real") -> dict:
    """Suggest a discount rate by picking the curve tenor closest to horizon.

    Selects from the tenors ``(1, 2, 3, 5, 7, 10, 20, 30) y``. For
    ``mode='real'``, subtracts a Treasury breakeven inflation expectation
    (5y if ``horizon_years <= 7`` else 10y) and clamps the result at 0. For
    ``mode='nominal'``, returns the raw nominal yield.

    Auto-fetches the rate curve and inflation fixtures (and therefore caches
    them on the session) if they aren't already loaded.

    Output shape::

        {"rate": 0.0195, "tenor": "10y", "mode": "real",
         "rationale": "10y Treasury 4.25% - 10y breakeven 2.30% = 1.95% real"}
    """
    if mode not in ("real", "nominal"):
        raise ValueError(f"unknown mode: {mode!r} (expected 'real' or 'nominal')")
    if horizon_years <= 0:
        raise ValueError(f"horizon_years must be positive, got {horizon_years}")

    # Reuse session cache where possible to avoid re-reading fixtures.
    s = get_session()
    curve = s.market.get("rate_curve") or fetch_rate_curve()
    yields = curve["yields"]

    # Pick the recommend-tenor closest to the requested horizon.
    target = float(horizon_years)
    tenor = min(_RECOMMEND_TENORS, key=lambda t: abs(_TENOR_YEARS[t] - target))
    nominal = float(yields[tenor])

    if mode == "nominal":
        rationale = (
            f"{tenor} Treasury {nominal:.2%} (nominal, horizon={horizon_years}y)"
        )
        return {
            "rate": nominal,
            "tenor": tenor,
            "mode": "nominal",
            "rationale": rationale,
        }

    # mode == "real"
    inflation = s.market.get("inflation") or fetch_inflation_expectations()
    be_key = "breakeven_5y" if horizon_years <= 7 else "breakeven_10y"
    breakeven = float(inflation[be_key])
    real = max(0.0, nominal - breakeven)
    be_label = "5y" if be_key == "breakeven_5y" else "10y"
    rationale = (
        f"{tenor} Treasury {nominal:.2%} - {be_label} breakeven {breakeven:.2%} "
        f"= {real:.2%} real (horizon={horizon_years}y)"
    )
    return {
        "rate": real,
        "tenor": tenor,
        "mode": "real",
        "rationale": rationale,
    }


def market_snapshot() -> dict:
    """Return a deep-copied JSON-safe view of ``session.market``.

    Useful for a future ``read_market_state`` tool that lets Claude inspect
    everything it has fetched so far in a session.
    """
    return copy.deepcopy(get_session().market)


__all__ = [
    "fetch_rate_curve",
    "fetch_mortgage_rate",
    "fetch_inflation_expectations",
    "fetch_regional_benchmarks",
    "recommend_discount_rate",
    "market_snapshot",
]
