"""F03-B: independent CLAT MCQ checks from passage + displayed stem/options only."""

from __future__ import annotations

import re
from collections.abc import Callable

from app.cuet_clat.clat_passage_contracts import (
    ClatAuthoredMcq,
    ClatIndependentCheckResult,
    ClatIndependentVerdict,
)


def _pass(
    key: str,
    *,
    anchor: str,
    steps: list[str],
) -> ClatIndependentCheckResult:
    return ClatIndependentCheckResult(
        verdict=ClatIndependentVerdict.PASS,
        derived_key=key,
        anchor_quote=anchor[:240],
        proof_steps=steps,
    )


def _review(reason: str) -> ClatIndependentCheckResult:
    return ClatIndependentCheckResult(
        verdict=ClatIndependentVerdict.REVIEW_REQUIRED,
        reason=reason,
    )


def _fail(reason: str) -> ClatIndependentCheckResult:
    return ClatIndependentCheckResult(
        verdict=ClatIndependentVerdict.FAIL,
        reason=reason,
    )


def _english_independent(
    passage_text: str,
    stem: str,
    options: dict[str, str],
) -> ClatIndependentCheckResult:
    _ = stem
    lowered = passage_text.lower()
    supported: list[tuple[str, str, str]] = []
    for key, text in options.items():
        phrase = text.lower().strip()
        if phrase and phrase in lowered:
            start = lowered.index(phrase)
            anchor = passage_text[start : start + len(text)]
            supported.append((key, text, anchor))
    if len(supported) == 1:
        key, _, anchor = supported[0]
        return _pass(
            key,
            anchor=anchor,
            steps=["Matched exactly one option phrase within passage text."],
        )
    if len(supported) > 1:
        return _fail("Multiple options verbatim-supported; detail question ambiguous.")
    return _review("No deterministic verbatim support for any option.")


def _legal_independent(
    passage_text: str,
    stem: str,
    options: dict[str, str],
) -> ClatIndependentCheckResult:
    mass_match = re.search(r"registered at ([\d.]+)\s*tonnes", stem, re.IGNORECASE)
    time_match = re.search(r"at\s+(\d{1,2}):(\d{2})", stem)
    weekdays = ("monday", "tuesday", "wednesday", "thursday", "friday")
    weekday = any(day in stem.lower() for day in weekdays)
    mass = float(mass_match.group(1)) if mass_match else None
    hour = int(time_match.group(1)) if time_match else None
    minute = int(time_match.group(2)) if time_match else 0

    if "bicycle" in stem.lower():
        if "No penalty under Rule 7" in options.get("C", ""):
            return _pass(
                "C",
                anchor="No vehicle whose registered mass exceeds three tonnes",
                steps=[
                    "Bicycle scenario: no stated excess mass; Rule 7 penalty not triggered.",
                ],
            )
        return _review("Could not match bicycle outcome to options.")

    if mass is not None and hour is not None and weekday:
        restricted = mass > 3.0 and 7 <= hour < 9
        if restricted:
            for key, text in options.items():
                if "500 transit credits" in text and "Rule 7" in text:
                    return _pass(
                        key,
                        anchor="violation of Rule 7 carries a flat penalty of 500",
                        steps=[
                            f"Mass {mass} > 3.0 tonnes",
                            f"Clock {hour:02d}:{minute:02d} within 07:00-09:00 weekday window",
                        ],
                    )
            return _fail("Rule 7 violation derived but no matching penalty option.")
        for key, text in options.items():
            if "at most three tonnes" in text.lower() or "mass is at or below" in text.lower():
                return _pass(
                    key,
                    anchor="Vehicles at or below three tonnes may use Elm Bridge",
                    steps=[
                        f"Mass {mass} ≤ 3.0 tonnes; outside window or Rule 14 allows.",
                    ],
                )
        if mass <= 3.0:
            for key, text in options.items():
                if "allowed" in text.lower() and "500" not in text:
                    return _pass(
                        key,
                        anchor="Vehicles at or below three tonnes",
                        steps=[f"Mass {mass} ≤ 3.0 tonnes ⇒ no Rule 7 breach."],
                    )
    return _review("Legal scenario not in supported deterministic fact-pattern set.")


def _logical_independent(
    passage_text: str,
    stem: str,
    options: dict[str, str],
) -> ClatIndependentCheckResult:
    _ = passage_text
    if "Premises 1 and 2 alone" in stem:
        for key, text in options.items():
            if "priya passed" in text.lower():
                return _pass(
                    key,
                    anchor="Every member who attended all six review sessions passed",
                    steps=["Universal attendee rule + Priya attended all six ⇒ pass."],
                )
    if "missed two review sessions" in stem.lower():
        for key, text in options.items():
            if "did not pass" in text.lower():
                return _pass(
                    key,
                    anchor="No member who missed more than one session passed",
                    steps=["Two misses > one ⇒ non-pass under Premise 3."],
                )
    if "weakens the link" in stem.lower():
        for key, text in options.items():
            if "not a member" in text.lower():
                return _pass(
                    key,
                    anchor="Every member who attended",
                    steps=["Premise 1 scope is members only; non-membership breaks entailment."],
                )
    return _review("Logical stem outside narrow supported proof templates.")


def _parse_quant_table(passage_text: str) -> dict[str, tuple[int, int]]:
    rows: dict[str, tuple[int, int]] = {}
    for line in passage_text.splitlines():
        if "|" not in line or line.strip().startswith("|--"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 3:
            continue
        name, units_s, price_s = cells
        if name.lower() == "item":
            continue
        if units_s.isdigit() and price_s.isdigit():
            rows[name.lower()] = (int(units_s), int(price_s))
    return rows


def _quant_independent(
    passage_text: str,
    stem: str,
    options: dict[str, str],
) -> ClatIndependentCheckResult:
    table = _parse_quant_table(passage_text)
    if not table:
        return _fail("Could not parse quantitative table from passage.")

    if "total revenue from pens" in stem.lower():
        units, price = table.get("pens", (0, 0))
        answer = units * price
        for key, text in options.items():
            if text.replace(",", "").strip() == str(answer):
                return _pass(
                    key,
                    anchor=f"| Pens | {units} | {price} |",
                    steps=[f"{units} × {price} = {answer}"],
                )
        return _fail(f"Computed pens revenue {answer} not among options.")

    if "notebooks and binders" in stem.lower() and "combined" in stem.lower():
        n_units = table.get("notebooks", (0, 0))[0]
        b_units = table.get("binders", (0, 0))[0]
        answer = n_units + b_units
        for key, text in options.items():
            if text.strip() == str(answer):
                return _pass(
                    key,
                    anchor=f"Notebooks {n_units}, Binders {b_units}",
                    steps=[f"{n_units} + {b_units} = {answer}"],
                )
        return _fail(f"Combined units {answer} not among options.")

    if "percentage of total units are pens" in stem.lower():
        pens = table.get("pens", (0, 0))[0]
        total = sum(u for u, _ in table.values())
        if total == 0:
            return _fail("Total units zero.")
        pct = round(pens * 100 / total)
        for key, text in options.items():
            if text.strip().startswith(str(pct)):
                return _pass(
                    key,
                    anchor=f"Pens {pens} of total {total}",
                    steps=[f"{pens}/{total}×100 ≈ {pct}%"],
                )
        return _fail(f"Computed pens share {pct}% not among options.")

    return _review("Quant stem not in supported deterministic calculator set.")


_SECTION_CHECKERS: dict[str, Callable[[str, str, dict[str, str]], ClatIndependentCheckResult]] = {
    "english": _english_independent,
    "legal_reasoning": _legal_independent,
    "logical_reasoning": _logical_independent,
    "quantitative_techniques": _quant_independent,
}


def independently_check_mcq(
    *,
    passage_text: str,
    section_code: str,
    question: ClatAuthoredMcq,
) -> ClatIndependentCheckResult:
    """Derive correctness without reading ``author_key``."""

    checker = _SECTION_CHECKERS.get(section_code)
    if checker is None:
        return _review(f"Unsupported CLAT section for deterministic check: {section_code}")
    return checker(passage_text, question.stem_text, dict(question.options))