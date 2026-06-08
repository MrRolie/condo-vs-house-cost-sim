# mcp_server/main.py
from fastmcp import FastMCP
from mcp_server.tools import (
    define_scenario,
    run_comparison,
    sweep_param,
    save_figure,
    list_scenarios,
    delete_scenario,
)

mcp = FastMCP(
    name="housing-decision-engine",
    instructions=(
        "Housing cost comparison engine. Define named scenarios with define_scenario_tool, "
        "then run comparisons, sweep parameters, and save figures. "
        "Scenarios are session-scoped — they reset when the server restarts. "
        "mode values for run_comparison_tool: 'deterministic', 'monte_carlo', or 'both'. "
        "Use list_scenarios_tool to orient yourself in a long session."
    ),
)


@mcp.tool
def define_scenario_tool(name: str, config: dict) -> dict:
    """Define a named housing scenario from a config dict.

    Required config keys: 'years' (int), 'discount_rate' (float),
    'condo' dict with 'monthly_fee' (float),
    'house' dict with 'initial_value' (float).

    Optional: 'economic', 'simulation' sections — see examples/basic_config.yaml.
    Returns {name, status, condo_monthly_fee, house_initial_value, years} or {error}.
    """
    return define_scenario(name, config)


@mcp.tool
def run_comparison_tool(name: str, mode: str = "both") -> dict:
    """Run a housing cost comparison for a named scenario.

    mode: 'deterministic' (fast), 'monte_carlo' (full uncertainty), or 'both' (default).
    Returns text report + structured summary. Caches MC results for save_figure_tool.
    """
    return run_comparison(name, mode)


@mcp.tool
def sweep_param_tool(name: str, param_path: str, values: list) -> dict:
    """Sweep a scalar parameter across values using the deterministic engine.

    Supported param_path values (dot-notation, flat scalars only):
    years, discount_rate,
    condo.monthly_fee, condo.fee_escalation_rate, condo.reserve_contribution_rate,
    house.initial_value, house.value_growth_rate, house.annual_maintenance_rate,
    simulation.house_maintenance_vol, simulation.condo_fee_vol,
    economic.inflation_rate.

    Returns {name, param_path, rows: [{value, condo_pv_total, house_pv_total, diff_pv}]}.
    """
    return sweep_param(name, param_path, values)


@mcp.tool
def save_figure_tool(name: str, figure_type: str) -> dict:
    """Save a matplotlib figure to ~/.cache/hde/figures/ and return its absolute path.

    figure_type: 'diff_distribution' or 'pv_distributions'.
    Requires run_comparison_tool with mode='monte_carlo' or 'both' first.
    Use Claude Code's SendUserFile with the returned path to show the figure to the user.
    """
    return save_figure(name, figure_type)


@mcp.tool
def list_scenarios_tool() -> dict:
    """List all scenarios defined in this session with their result-cached status."""
    return list_scenarios()


@mcp.tool
def delete_scenario_tool(name: str) -> dict:
    """Remove a scenario from the session registry."""
    return delete_scenario(name)


def run() -> None:
    mcp.run()


if __name__ == "__main__":
    run()
