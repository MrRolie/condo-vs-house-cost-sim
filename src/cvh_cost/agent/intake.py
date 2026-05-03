"""Canonical question bank Claude consults during intake.

The actual user-facing questioning is done by Claude itself; this module is a
structured reference plus small helpers (validation, coercion, missing-required
detection). Tools in :mod:`cvh_cost.agent` look here for canonical question
ids, prompts, types, defaults, and the dotted ``target`` paths that say which
``AssembledParams`` field a given answer feeds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional


QuestionType = Literal[
    "text",
    "numeric",
    "currency",
    "percent",
    "single_choice",
    "multi_choice",
    "year",
    "boolean",
]


@dataclass
class Question:
    """One canonical intake question.

    Attributes:
        id: Stable identifier; matches the key in :data:`QUESTION_BANK`.
        prompt: Natural-language phrasing Claude can use verbatim or paraphrase.
        qtype: One of :data:`QuestionType`.
        required: Whether this answer must be present before assembly.
        choices: Allowed values for ``single_choice`` / ``multi_choice``.
        help: Short clarification Claude can show on request.
        target: Dotted path into :class:`AssembledParams` that this answer
            feeds (e.g. ``"sim.years"``). ``None`` means the answer is
            informational / used indirectly.
        units: Human-readable units (``"USD"``, ``"USD/month"``, ``"%"``,
            ``"years"``).
        default: Suggested default if user is unsure.
        section: Logical grouping (``"horizon"``, ``"condo"``, ``"house"``,
            ``"risk"``).
    """

    id: str
    prompt: str
    qtype: QuestionType
    required: bool = True
    choices: Optional[list[str]] = None
    help: Optional[str] = None
    target: Optional[str] = None
    units: Optional[str] = None
    default: Any = None
    section: str = "horizon"


# ---------------------------------------------------------------------------
# Canonical question bank
# ---------------------------------------------------------------------------

_QUESTIONS: list[Question] = [
    # ----- Horizon & discounting -----
    Question(
        id="horizon_years",
        prompt="Over how many years do you want to compare costs?",
        qtype="numeric",
        target="sim.years",
        units="years",
        default=20,
        section="horizon",
    ),
    Question(
        id="discount_rate_source",
        prompt="Should I use the current market rate (10y Treasury) for discounting, or do you have a custom rate in mind?",
        qtype="single_choice",
        choices=["use_market_rate", "use_custom"],
        default="use_market_rate",
        help="market rate uses 10y Treasury; custom lets you set your own",
        section="horizon",
    ),
    Question(
        id="discount_rate_custom",
        prompt="What discount rate should I use? (e.g. 4% or 0.04)",
        qtype="percent",
        required=False,
        target="sim.discount_rate",
        units="%",
        help="Only needed if you chose 'use_custom' for discount_rate_source.",
        section="horizon",
    ),
    Question(
        id="economic_mode",
        prompt="Do you want results in real (inflation-adjusted) or nominal dollars?",
        qtype="single_choice",
        choices=["real", "nominal"],
        target="econ.mode",
        default="real",
        section="horizon",
    ),
    # ----- Condo -----
    Question(
        id="condo_price",
        prompt="What is the condo's purchase price?",
        qtype="currency",
        units="USD",
        help="purchase price; not used directly but informs context",
        section="condo",
    ),
    Question(
        id="condo_monthly_hoa",
        prompt="What is the current monthly HOA / condo fee?",
        qtype="currency",
        target="condo.monthly_fee",
        units="USD/month",
        section="condo",
    ),
    Question(
        id="condo_hoa_growth",
        prompt="What annual growth rate should I assume for the HOA fee? (e.g. 2%)",
        qtype="percent",
        target="condo.fee_escalation_rate",
        units="%",
        default=0.02,
        section="condo",
    ),
    Question(
        id="condo_hoa_covers",
        prompt="What does the HOA fee cover? Pick all that apply.",
        qtype="multi_choice",
        choices=[
            "water",
            "trash",
            "exterior_insurance",
            "amenities",
            "reserves",
            "landscaping",
            "other",
        ],
        section="condo",
    ),
    Question(
        id="condo_reserve_balance",
        prompt="What is the HOA's current reserve balance, if known?",
        qtype="currency",
        required=False,
        target="condo.reserve_initial_balance",
        units="USD",
        default=0,
        section="condo",
    ),
    Question(
        id="condo_reserve_contribution_rate",
        prompt="What fraction of annual fees is set aside for reserves each year?",
        qtype="percent",
        required=False,
        target="condo.reserve_contribution_rate",
        units="%",
        default=0,
        section="condo",
    ),
    Question(
        id="condo_special_assessment_history",
        prompt="Have there been any large special assessments in the last 10 years?",
        qtype="text",
        required=False,
        help="any large assessments in last 10 years?",
        section="condo",
    ),
    # ----- House -----
    Question(
        id="house_price",
        prompt="What is the house's purchase price (or current value)?",
        qtype="currency",
        target="house.initial_value",
        units="USD",
        section="house",
    ),
    Question(
        id="house_year_built",
        prompt="What year was the house built?",
        qtype="year",
        required=False,
        units="year",
        section="house",
    ),
    Question(
        id="house_value_growth",
        prompt="What annual growth rate should I assume for the house's value?",
        qtype="percent",
        target="house.value_growth_rate",
        units="%",
        default=0.02,
        section="house",
    ),
    Question(
        id="house_maintenance_rate",
        prompt="What annual maintenance budget should I assume, as a fraction of house value? (1.2% is a common rule of thumb)",
        qtype="percent",
        target="house.annual_maintenance_rate",
        units="%",
        default=0.012,
        section="house",
    ),
    Question(
        id="house_known_upcoming_events",
        prompt="Any known upcoming big-ticket items? (roof, HVAC, plumbing, etc. with rough year + cost)",
        qtype="text",
        required=False,
        help="roof, HVAC, plumbing, etc. with rough year + cost",
        section="house",
    ),
    Question(
        id="region",
        prompt="What region is the property in? (e.g. 'Boston, MA')",
        qtype="text",
        required=False,
        help="for benchmark lookup; e.g. 'Boston, MA'",
        section="house",
    ),
    # ----- Risk -----
    Question(
        id="risk_focus_percentile",
        prompt="When weighing risk, which percentile of the cost distribution matters most to you?",
        qtype="single_choice",
        choices=["p5", "p50", "p95", "mean"],
        default="p95",
        help="which percentile of the cost distribution matters most to you?",
        section="risk",
    ),
    Question(
        id="mc_num_sims",
        prompt="How many Monte Carlo simulations should I run? (default 10,000)",
        qtype="numeric",
        required=False,
        target="sim.num_sims",
        default=10_000,
        section="risk",
    ),
]


QUESTION_BANK: dict[str, Question] = {q.id: q for q in _QUESTIONS}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_question(qid: str) -> Question:
    """Return the canonical :class:`Question` for ``qid``.

    Raises:
        KeyError: if ``qid`` is not in :data:`QUESTION_BANK`.
    """
    if qid not in QUESTION_BANK:
        raise KeyError(f"Unknown question id: {qid!r}")
    return QUESTION_BANK[qid]


def required_questions() -> list[Question]:
    """Return all questions whose ``required`` flag is ``True``."""
    return [q for q in QUESTION_BANK.values() if q.required]


def questions_for_section(section: str) -> list[Question]:
    """Return questions in the given logical section.

    Args:
        section: One of ``"horizon"``, ``"condo"``, ``"house"``, ``"risk"``.
    """
    return [q for q in QUESTION_BANK.values() if q.section == section]


def missing_required(answers: dict[str, Any]) -> list[Question]:
    """Return required questions whose answers are missing or ``None``."""
    out: list[Question] = []
    for q in required_questions():
        v = answers.get(q.id, None)
        if v is None:
            out.append(q)
    return out


# ----- Validation / coercion -----


def _coerce_percent(value: Any) -> float:
    """Normalize percent input.

    Accepts ``0.05``, ``5`` (interpreted as 5%), ``"5%"``, ``"5.0%"``,
    ``"0.05"``. Always returns a fraction (``0.05`` for 5%).
    """
    if isinstance(value, bool):
        raise ValueError(f"cannot coerce bool to percent: {value!r}")
    if isinstance(value, (int, float)):
        f = float(value)
    elif isinstance(value, str):
        s = value.strip()
        had_percent = s.endswith("%")
        if had_percent:
            s = s[:-1].strip()
        s = s.replace(",", "")
        try:
            f = float(s)
        except ValueError as e:
            raise ValueError(f"cannot parse percent: {value!r}") from e
        if had_percent:
            f = f / 100.0
            return f
    else:
        raise ValueError(f"cannot coerce to percent: {value!r}")
    # If the bare numeric is > 1 we assume the user wrote "5" meaning 5%.
    # Below or equal to 1 we assume already a fraction (so "0.05" stays 0.05).
    if f > 1.0:
        f = f / 100.0
    return f


def _coerce_currency(value: Any) -> float:
    """Normalize currency input. Strips ``$`` and ``,``."""
    if isinstance(value, bool):
        raise ValueError(f"cannot coerce bool to currency: {value!r}")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip().replace("$", "").replace(",", "").strip()
        try:
            return float(s)
        except ValueError as e:
            raise ValueError(f"cannot parse currency: {value!r}") from e
    raise ValueError(f"cannot coerce to currency: {value!r}")


def _coerce_numeric(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError(f"cannot coerce bool to numeric: {value!r}")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip().replace(",", "")
        try:
            return float(s)
        except ValueError as e:
            raise ValueError(f"cannot parse numeric: {value!r}") from e
    raise ValueError(f"cannot coerce to numeric: {value!r}")


def _coerce_year(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError(f"cannot coerce bool to year: {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"year must be an integer: {value!r}")
        return int(value)
    if isinstance(value, str):
        s = value.strip().replace(",", "")
        try:
            return int(s)
        except ValueError as e:
            raise ValueError(f"cannot parse year: {value!r}") from e
    raise ValueError(f"cannot coerce to year: {value!r}")


def _coerce_boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        s = value.strip().lower()
        if s in {"yes", "y", "true", "t", "1"}:
            return True
        if s in {"no", "n", "false", "f", "0"}:
            return False
        raise ValueError(f"cannot parse boolean: {value!r}")
    raise ValueError(f"cannot coerce to boolean: {value!r}")


def coerce_answer(qid: str, value: Any) -> Any:
    """Normalize an answer to the canonical type for question ``qid``.

    - ``percent`` -> float fraction (``"5%"`` -> ``0.05``)
    - ``currency`` -> float, strips ``$`` and commas
    - ``numeric`` -> float
    - ``year`` -> int
    - ``boolean`` -> bool, accepts ``"yes"``/``"no"`` etc.
    - ``single_choice`` -> str (validated against ``choices``)
    - ``multi_choice`` -> ``list[str]`` (each validated)
    - ``text`` -> str

    Raises:
        ValueError: if the value cannot be coerced or fails choice validation.
        KeyError: if ``qid`` is unknown.
    """
    q = get_question(qid)
    if value is None:
        return None
    if q.qtype == "percent":
        return _coerce_percent(value)
    if q.qtype == "currency":
        return _coerce_currency(value)
    if q.qtype == "numeric":
        return _coerce_numeric(value)
    if q.qtype == "year":
        return _coerce_year(value)
    if q.qtype == "boolean":
        return _coerce_boolean(value)
    if q.qtype == "single_choice":
        s = str(value).strip()
        if q.choices is not None and s not in q.choices:
            raise ValueError(
                f"answer for {qid!r} must be one of {q.choices!r}, got {value!r}"
            )
        return s
    if q.qtype == "multi_choice":
        if isinstance(value, str):
            items = [v.strip() for v in value.split(",") if v.strip()]
        elif isinstance(value, (list, tuple, set)):
            items = [str(v).strip() for v in value]
        else:
            raise ValueError(f"multi_choice expects list or comma-string: {value!r}")
        if q.choices is not None:
            for it in items:
                if it not in q.choices:
                    raise ValueError(
                        f"answer for {qid!r} contains invalid choice {it!r}; "
                        f"allowed: {q.choices!r}"
                    )
        return items
    # text fallthrough
    return str(value)


def validate_answer(qid: str, value: Any) -> tuple[bool, Optional[str]]:
    """Return ``(is_valid, error_message)`` for the given answer.

    A return of ``(True, None)`` means the value can be coerced and (for
    years) is in the plausible range ``[1900, 2100]``. Otherwise the second
    element is a human-readable error.
    """
    if qid not in QUESTION_BANK:
        return False, f"unknown question id: {qid!r}"
    q = QUESTION_BANK[qid]
    if value is None:
        if q.required:
            return False, f"{qid!r} is required"
        return True, None
    try:
        coerced = coerce_answer(qid, value)
    except (ValueError, KeyError) as e:
        return False, str(e)
    if q.qtype == "year":
        if not isinstance(coerced, int) or coerced < 1900 or coerced > 2100:
            return False, f"year out of range [1900, 2100]: {coerced!r}"
    if q.qtype in ("currency", "numeric"):
        if not isinstance(coerced, float):
            return False, f"expected float for {qid!r}, got {type(coerced).__name__}"
    return True, None


__all__ = [
    "Question",
    "QuestionType",
    "QUESTION_BANK",
    "get_question",
    "required_questions",
    "questions_for_section",
    "missing_required",
    "validate_answer",
    "coerce_answer",
]
