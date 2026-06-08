from __future__ import annotations
from dataclasses import dataclass
from hde.models import DeterministicResult, MonteCarloResult


@dataclass
class ScenarioEntry:
    name: str
    raw_config: dict
    params: tuple  # (CondoParams, HouseParams, SimulationParams, EconomicParams)
    det_result: DeterministicResult | None = None
    mc_result: MonteCarloResult | None = None


_REGISTRY: dict[str, ScenarioEntry] = {}


def define(name: str, raw_config: dict, params: tuple) -> None:
    _REGISTRY[name] = ScenarioEntry(name=name, raw_config=raw_config, params=params)


def get(name: str) -> ScenarioEntry:
    if name not in _REGISTRY:
        raise KeyError(name)
    return _REGISTRY[name]


def all_entries() -> list[dict]:
    return [
        {
            "name": e.name,
            "has_det_result": e.det_result is not None,
            "has_mc_result": e.mc_result is not None,
        }
        for e in _REGISTRY.values()
    ]


def remove(name: str) -> None:
    if name not in _REGISTRY:
        raise KeyError(name)
    del _REGISTRY[name]


def store_results(
    name: str,
    det_result: DeterministicResult | None = None,
    mc_result: MonteCarloResult | None = None,
) -> None:
    entry = get(name)
    entry.det_result = det_result
    entry.mc_result = mc_result


def clear() -> None:
    """Reset registry state. For tests only."""
    _REGISTRY.clear()
