"""Smoke tests for the Phase-2 agent session and analysis wrappers."""

import json
import os

import pytest

from cvh_cost.core.models import (
    CondoParams,
    HouseParams,
    SimulationParams,
    EconomicParams,
)
from cvh_cost.agent.session import (
    AnalysisArtifact,
    AssembledParams,
    get_session,
    reset_session,
    session_snapshot,
)
from cvh_cost.agent.analysis import (
    assemble_params_snapshot,
    list_artifacts,
    plot_results,
    run_deterministic,
    run_monte_carlo,
    summarize_results,
)


def _build_params() -> AssembledParams:
    return AssembledParams(
        condo=CondoParams(monthly_fee=400, fee_escalation_rate=0.02),
        house=HouseParams(
            initial_value=400_000,
            annual_maintenance_rate=0.012,
            value_growth_rate=0.01,
        ),
        sim=SimulationParams(years=10, discount_rate=0.03, num_sims=500, random_seed=42),
        econ=EconomicParams(),
        provenance={"sim.discount_rate": "default"},
    )


@pytest.fixture(autouse=True)
def _fresh_session():
    """Each test gets a clean module-level session."""
    reset_session()
    yield
    reset_session()


class TestSessionRoundtrip:
    def test_session_roundtrip(self):
        # Mutate intake.
        s = get_session()
        s.intake["horizon_years"] = 25
        s.intake["risk_tolerance"] = "moderate"

        # Store an artifact (deterministic, no numpy arrays needed).
        params = _build_params()
        s.params = params
        handle = s.next_handle("det")
        assert handle == "det_001"
        artifact = AnalysisArtifact(
            handle=handle,
            kind="deterministic",
            params=params,
            deterministic=None,
        )
        s.store_artifact(artifact)
        assert handle in s.artifacts

        # Snapshot must be JSON-serializable end-to-end.
        snap = session_snapshot()
        encoded = json.dumps(snap)
        assert "horizon_years" in encoded
        assert handle in encoded

        # next_handle increments per-prefix.
        assert s.next_handle("det") == "det_002"
        assert s.next_handle("mc") == "mc_001"

        # reset_session wipes everything.
        reset_session()
        s2 = get_session()
        assert s2 is not s
        assert s2.intake == {}
        assert s2.artifacts == {}
        assert s2.params is None


class TestAnalysisEndToEnd:
    def test_analysis_runs_end_to_end(self, tmp_path):
        s = get_session()
        s.params = _build_params()

        # snapshot view returns the params before any compute.
        snap = assemble_params_snapshot()
        assert snap["sim"]["years"] == 10
        assert snap["provenance"]["sim.discount_rate"] == "default"

        # Deterministic run.
        det_out = run_deterministic()
        assert det_out["handle"] == "det_001"
        assert "diff_pv" in det_out["result"]
        assert "condo_pv_total" in det_out["result"]
        assert isinstance(det_out["result"]["diff_pv"], float)

        # Monte Carlo with explicit small num_sims, ensuring arrays stay hidden.
        mc_out = run_monte_carlo(num_sims=200)
        assert mc_out["handle"] == "mc_001"
        summary = mc_out["summary"]
        for group in ("condo", "house", "diff"):
            assert set(summary[group].keys()) == {"mean", "std", "p5", "p50", "p95"}
        assert "prob_house_more_expensive" in summary
        assert summary["num_sims"] == 200
        # Make sure the wrapper never leaks ndarrays.
        assert "condo_pv" not in summary
        assert "house_pv" not in summary
        # And that the full mc result is JSON-serializable from the response.
        json.dumps(mc_out)

        # Override patch is honored without mutating session params.
        det_override = run_deterministic({"sim.discount_rate": 0.05})
        assert det_override["handle"] == "det_002"
        assert det_override["result"]["diff_pv"] != det_out["result"]["diff_pv"]
        assert s.params.sim.discount_rate == 0.03  # unchanged

        # Text report has dollar-sign formatting and is non-empty.
        report = summarize_results(mc_out["handle"])
        assert isinstance(report, str)
        assert len(report) > 0
        assert "$" in report

        # list_artifacts surfaces both runs.
        listing = list_artifacts()
        handles = {row["handle"] for row in listing}
        assert {"det_001", "det_002", "mc_001"}.issubset(handles)

        # Plot to a known path.
        out = tmp_path / "diff.png"
        path = plot_results(mc_out["handle"], kind="diff", out_path=str(out))
        assert path == str(out)
        assert os.path.getsize(path) > 0

        # Bad handles raise.
        with pytest.raises(KeyError):
            summarize_results("nope_999")
        with pytest.raises(KeyError):
            plot_results("nope_999")

        # Bad override path raises.
        with pytest.raises(ValueError):
            run_deterministic({"sim.does_not_exist": 1.0})
        with pytest.raises(ValueError):
            run_deterministic({"no_dot": 1.0})

    def test_run_without_params_raises(self):
        # Fresh session has no params.
        with pytest.raises(ValueError):
            run_deterministic()
        with pytest.raises(ValueError):
            run_monte_carlo()
