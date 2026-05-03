"""In-process agent session state.

Holds intake answers, market fetches, assembled params, and analysis
artifacts across tool calls. Numpy arrays from Monte Carlo runs live in
artifacts here and are deliberately kept out of any LLM-facing surface.

The module exposes a single global session via :func:`get_session`. This is
intentionally simple — Phase 5 may revisit if multi-session support is
required.
"""

from __future__ import annotations

from dataclasses import dataclass, field, is_dataclass, asdict
from typing import Any, Optional

from cvh_cost.core.models import (
    CondoParams,
    HouseParams,
    SimulationParams,
    EconomicParams,
    DeterministicResult,
    MonteCarloResult,
)


@dataclass
class AssembledParams:
    """Bundle of dataclasses used to feed the compute core, plus provenance.

    Attributes:
        condo: Condo parameters.
        house: House parameters.
        sim: Simulation parameters.
        econ: Economic parameters.
        provenance: Dotted-path -> short string explaining where the value
            came from. Examples: ``"user:answer_id"``,
            ``"market:treasury_10y_2026-05-02"``, ``"default"``,
            ``"derived:..."``.
    """

    condo: CondoParams
    house: HouseParams
    sim: SimulationParams
    econ: EconomicParams
    provenance: dict[str, str] = field(default_factory=dict)


@dataclass
class AnalysisArtifact:
    """A handle to a computation result.

    The numpy arrays inside ``MonteCarloResult`` are kept here rather than
    ever returned to the LLM. The LLM only sees the ``handle`` plus a small
    JSON-safe summary.
    """

    handle: str  # short stable id like "mc_001"
    kind: str    # "deterministic" or "monte_carlo"
    params: AssembledParams
    deterministic: Optional[DeterministicResult] = None
    monte_carlo: Optional[MonteCarloResult] = None


@dataclass
class AgentSession:
    """All in-process state shared across tool calls during one chat run."""

    intake: dict[str, Any] = field(default_factory=dict)
    market: dict[str, Any] = field(default_factory=dict)
    params: Optional[AssembledParams] = None
    artifacts: dict[str, AnalysisArtifact] = field(default_factory=dict)
    transcript: list[dict] = field(default_factory=list)
    # internal counter for handle generation, keyed by prefix
    _handle_counters: dict[str, int] = field(default_factory=dict)

    def log(self, kind: str, **fields: Any) -> None:
        """Append a transcript entry."""
        entry: dict[str, Any] = {"kind": kind}
        entry.update(fields)
        self.transcript.append(entry)

    def next_handle(self, prefix: str) -> str:
        """Return the next stable handle for ``prefix`` (e.g. ``"det"`` -> ``"det_001"``)."""
        n = self._handle_counters.get(prefix, 0) + 1
        self._handle_counters[prefix] = n
        return f"{prefix}_{n:03d}"

    def store_artifact(self, artifact: AnalysisArtifact) -> str:
        """Record an artifact under its handle and return that handle."""
        self.artifacts[artifact.handle] = artifact
        return artifact.handle


# ----- Module-level singleton -----

_SESSION: Optional[AgentSession] = None


def get_session() -> AgentSession:
    """Return the singleton :class:`AgentSession`, creating it on first call."""
    global _SESSION
    if _SESSION is None:
        _SESSION = AgentSession()
    return _SESSION


def reset_session() -> None:
    """Wipe the singleton session. Used by tests and ``/reset`` flows."""
    global _SESSION
    _SESSION = None


# ----- JSON-safe snapshot helpers -----

def _to_jsonable(obj: Any) -> Any:
    """Recursively convert ``obj`` into something ``json.dumps`` will accept.

    - Dataclasses -> dict (recursing into fields)
    - Numpy arrays -> dropped (replaced with a small descriptor)
    - Numpy scalars -> python scalars
    - dict / list / tuple -> recurse
    - Everything else -> fall back to ``str(obj)`` if not natively JSON-safe.
    """
    # Late import so importing this module never forces numpy.
    try:
        import numpy as np  # type: ignore
    except Exception:  # pragma: no cover - numpy is a hard dep elsewhere
        np = None  # type: ignore

    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if np is not None:
        if isinstance(obj, np.ndarray):
            return {"__ndarray__": True, "shape": list(obj.shape), "dtype": str(obj.dtype)}
        if isinstance(obj, np.generic):
            return obj.item()
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if is_dataclass(obj) and not isinstance(obj, type):
        # asdict recurses but trips on numpy arrays — handle field-by-field.
        out: dict[str, Any] = {}
        for k, v in obj.__dict__.items():
            out[k] = _to_jsonable(v)
        return out
    # Fallback: stringify so json.dumps never blows up on inspection helpers.
    return str(obj)


def _artifact_snapshot(art: AnalysisArtifact) -> dict[str, Any]:
    """JSON-safe view of an artifact (drops numpy arrays)."""
    snap: dict[str, Any] = {
        "handle": art.handle,
        "kind": art.kind,
        "params": _to_jsonable(art.params),
    }
    if art.deterministic is not None:
        snap["deterministic"] = _to_jsonable(art.deterministic)
    if art.monte_carlo is not None:
        mc = art.monte_carlo
        snap["monte_carlo"] = {
            "condo_summary": _to_jsonable(mc.condo_summary),
            "house_summary": _to_jsonable(mc.house_summary),
            "diff_summary": _to_jsonable(mc.diff_summary),
            "prob_house_more_expensive": float(mc.prob_house_more_expensive),
            "num_sims": int(mc.condo_pv.shape[0]),
        }
    return snap


def session_snapshot() -> dict[str, Any]:
    """Return a JSON-safe snapshot of the current session state.

    Numpy arrays are intentionally dropped (replaced with shape/dtype
    descriptors). Useful for ``read_intake_state`` and debugging.
    """
    s = get_session()
    return {
        "intake": _to_jsonable(s.intake),
        "market": _to_jsonable(s.market),
        "params": _to_jsonable(s.params) if s.params is not None else None,
        "artifacts": {h: _artifact_snapshot(a) for h, a in s.artifacts.items()},
        "transcript": _to_jsonable(s.transcript),
    }


__all__ = [
    "AssembledParams",
    "AnalysisArtifact",
    "AgentSession",
    "get_session",
    "reset_session",
    "session_snapshot",
]
