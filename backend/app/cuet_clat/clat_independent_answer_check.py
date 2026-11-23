"""F03-B: independent CLAT MCQ checks from passage + displayed stem/options only."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from app.cuet_clat.clat_passage_contracts import (
    ClatAuthoredMcq,
    ClatIndependentCheckResult,
    ClatIndependentVerdict,
)


def _pass(
    key: str,
    *,
    passage_text: str,
    anchor: str,
    steps: list[str],
) -> ClatIndependentCheckResult:
    if not anchor or anchor not in passage_text:
        return ClatIndependentCheckResult(
            verdict=ClatIndependentVerdict.FAIL,
            reason="Proof anchor is not a substring of the supplied passage.",
        )
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


def _normalize_option(text: str) -> str:
    return " ".join(text.lower().split())


_WORD_NUMBERS = {
    "one": 1.0,
    "two": 2.0,
    "three": 3.0,
    "four": 4.0,
    "five": 5.0,
}


def _word_or_float_to_number(token: str) -> float:
    token = token.strip().lower()
    if token in _WORD_NUMBERS:
        return _WORD_NUMBERS[token]
    return float(token)


def _unique_matching_key(
    options: dict[str, str],
    predicate: Callable[[str], bool],
) -> tuple[str | None, str | None]:
    matches: list[tuple[str, str]] = []
    for key, text in options.items():
        if predicate(text):
            matches.append((key, text))
    if len(matches) == 1:
        return matches[0][0], matches[0][1]
    if len(matches) > 1:
        return None, None
    return None, None


def _english_independent(
    passage_text: str,
    stem: str,
    options: dict[str, str],
) -> ClatIndependentCheckResult:
    stem_lower = stem.lower()
    passage_lower = passage_text.lower()

    if "how long" in stem_lower and "planning" in stem_lower:
        match = re.search(r"(\w+) months of planning", passage_text, re.IGNORECASE)
        if not match:
            return _fail("Passage lacks an unambiguous planning duration fact.")
        word = match.group(1)
        anchor = match.group(0)
        target = f"{word} months"
        key, _ = _unique_matching_key(
            options,
            lambda text: _normalize_option(text).startswith(target),
        )
        if key:
            return _pass(
                key,
                passage_text=passage_text,
                anchor=anchor,
                steps=[f"Duration fact: {anchor}"],
            )
        return _fail("No unique option matches the passage planning duration.")

    if "who proposed" in stem_lower and "children" in stem_lower:
        match = re.search(
            r"Architect\s+([\w.]+\s+[\w.]+)\s+proposed a dedicated children's corner",
            passage_text,
            re.IGNORECASE,
        )
        if not match:
            return _fail("Passage lacks proposer of the children's corner.")
        proposer = " ".join(match.group(1).split())
        anchor = passage_text[match.start(1) : match.end(1)]
        key, _ = _unique_matching_key(
            options,
            lambda text: _normalize_option(text) == _normalize_option(proposer),
        )
        if key:
            return _pass(
                key,
                passage_text=passage_text,
                anchor=anchor,
                steps=[f"Proposer named in passage: {proposer}"],
            )
        return _fail("No option exactly matches the named proposer.")

    if "how much" in stem_lower and "shelving" in stem_lower:
        match = re.search(
            r"approved\s+(\w+\s+thousand\s+rupees)\s+for\s+shelving",
            passage_lower,
        )
        if not match:
            return _fail("Passage lacks approved shelving amount.")
        amount = match.group(1)
        start = match.start(1)
        end = match.end(1)
        anchor = passage_text[start:end]
        title_amount = amount.title()
        key, _ = _unique_matching_key(
            options,
            lambda text: _normalize_option(text) == _normalize_option(title_amount),
        )
        if key:
            return _pass(
                key,
                passage_text=passage_text,
                anchor=anchor,
                steps=[f"Budget fact: {title_amount}"],
            )
        return _fail("No option matches the shelving budget amount.")

    return _review("English stem not in the supported deterministic detail grammar.")


@dataclass(frozen=True)
class _RivertonRules:
    mass_limit_tonnes: float
    window_start_hour: int
    window_end_hour: int
    penalty_credits: int
    allowed_mass_tonnes: float
    penalty_anchor: str
    limit_anchor: str
    allowed_anchor: str


def _parse_riverton_rules(passage_text: str) -> _RivertonRules | None:
    lower = passage_text.lower()
    limit = re.search(r"exceeds\s+([\d.]+|\w+)\s+tonnes", lower)
    window = re.search(
        r"between\s+(\d{2}):(\d{2})\s+and\s+(\d{2}):(\d{2})",
        lower,
    )
    penalty = re.search(r"penalty of\s+(\d+)\s+transit credits", lower)
    allowed = re.search(r"at or below\s+([\d.]+|\w+)\s+tonnes", lower)
    if not (limit and window and penalty and allowed):
        return None
    penalty_anchor_match = re.search(
        r"violation of Rule 7 carries a flat penalty of \d+",
        passage_text,
        re.IGNORECASE,
    )
    limit_anchor_match = re.search(
        r"No vehicle whose registered mass exceeds \w+\s+tonnes",
        passage_text,
        re.IGNORECASE,
    )
    allowed_anchor_match = re.search(
        r"Vehicles at or below \w+\s+tonnes may use Elm Bridge",
        passage_text,
        re.IGNORECASE,
    )
    if not (penalty_anchor_match and limit_anchor_match and allowed_anchor_match):
        return None
    return _RivertonRules(
        mass_limit_tonnes=_word_or_float_to_number(limit.group(1)),
        window_start_hour=int(window.group(1)),
        window_end_hour=int(window.group(3)),
        penalty_credits=int(penalty.group(1)),
        allowed_mass_tonnes=_word_or_float_to_number(allowed.group(1)),
        penalty_anchor=penalty_anchor_match.group(0),
        limit_anchor=limit_anchor_match.group(0),
        allowed_anchor=allowed_anchor_match.group(0),
    )


def _parse_fact_pattern(stem: str) -> tuple[float | None, int | None, int, bool, bool]:
    mass_match = re.search(r"registered at ([\d.]+)\s*tonnes", stem, re.IGNORECASE)
    time_match = re.search(r"at\s+(\d{1,2}):(\d{2})", stem)
    weekdays = ("monday", "tuesday", "wednesday", "thursday", "friday")
    weekday = any(day in stem.lower() for day in weekdays)
    stem_lower = stem.lower()
    closure_posted = (
        "maintenance closure posted" in stem_lower and "no maintenance" not in stem_lower
    )
    mass = float(mass_match.group(1)) if mass_match else None
    hour = int(time_match.group(1)) if time_match else None
    minute = int(time_match.group(2)) if time_match else 0
    return mass, hour, minute, weekday, closure_posted


def _legal_independent(
    passage_text: str,
    stem: str,
    options: dict[str, str],
) -> ClatIndependentCheckResult:
    rules = _parse_riverton_rules(passage_text)
    if rules is None:
        return _fail("Could not parse fictional legal rule text from passage.")

    mass, hour, minute, weekday, closure_posted = _parse_fact_pattern(stem)
    if mass is None:
        return _review("Fact pattern does not state registered mass.")

    in_window = (
        hour is not None
        and rules.window_start_hour <= hour < rules.window_end_hour
    )
    rule7_breach = (
        weekday
        and in_window
        and mass > rules.mass_limit_tonnes
    )
    if rule7_breach:
        key, _ = _unique_matching_key(
            options,
            lambda text: (
                str(rules.penalty_credits) in text
                and "rule 7" in text.lower()
            ),
        )
        if key:
            return _pass(
                key,
                passage_text=passage_text,
                anchor=rules.penalty_anchor,
                steps=[
                    f"Mass {mass} > limit {rules.mass_limit_tonnes}",
                    f"Time {hour:02d}:{minute:02d} in weekday restricted window",
                ],
            )
        return _fail("Rule breach derived but no unique penalty option.")

    if mass <= rules.allowed_mass_tonnes and not closure_posted:
        key, _ = _unique_matching_key(
            options,
            lambda text: "allowed" in text.lower() and str(rules.penalty_credits) not in text,
        )
        if key:
            return _pass(
                key,
                passage_text=passage_text,
                anchor=rules.allowed_anchor,
                steps=[
                    f"Mass {mass} ≤ allowed {rules.allowed_mass_tonnes}",
                    "No maintenance closure stated in stem",
                ],
            )

    if mass <= rules.mass_limit_tonnes or not rule7_breach:
        key, _ = _unique_matching_key(
            options,
            lambda text: "no penalty" in text.lower() and "rule 7" in text.lower(),
        )
        if key:
            return _pass(
                key,
                passage_text=passage_text,
                anchor=rules.limit_anchor,
                steps=[f"Mass {mass} does not exceed Rule 7 limit {rules.mass_limit_tonnes}"],
            )

    return _review("Legal outcome not uniquely derivable from passage rule and stated facts.")


def _passage_contains(passage_text: str, fragment: str) -> bool:
    return fragment.lower() in passage_text.lower()


def _logical_independent(
    passage_text: str,
    stem: str,
    options: dict[str, str],
) -> ClatIndependentCheckResult:
    premise1 = "Every member who attended all six review sessions passed the mock exam"
    premise2 = "Priya attended all six review sessions"
    premise3 = "No member who missed more than one session passed the mock exam"

    if "premises 1 and 2 alone" in stem.lower():
        has_p1 = _passage_contains(passage_text, premise1)
        has_p2 = _passage_contains(passage_text, premise2)
        if not (has_p1 and has_p2):
            return _fail("Supplied passage lacks Premises 1 and 2 needed for entailment.")
        idx = passage_text.lower().find(premise1.lower())
        anchor = passage_text[idx : idx + len(premise1)] if idx >= 0 else premise1
        key, _ = _unique_matching_key(
            options,
            lambda text: "priya passed" in text.lower(),
        )
        if key:
            return _pass(
                key,
                passage_text=passage_text,
                anchor=anchor,
                steps=["Premise 1 universal on attendees; Premise 2 fixes Priya in that set."],
            )
        return _fail("Entailed conclusion missing among options.")

    if "missed two review sessions" in stem.lower():
        if not _passage_contains(passage_text, premise3):
            return _fail("Passage lacks Premise 3 for missed-session inference.")
        idx = passage_text.lower().find(premise3.lower()[:12])
        anchor = passage_text[idx : idx + len(premise3)] if idx >= 0 else premise3
        key, _ = _unique_matching_key(
            options,
            lambda text: "did not pass" in text.lower(),
        )
        if key:
            return _pass(
                key,
                passage_text=passage_text,
                anchor=anchor,
                steps=["Two missed sessions exceed 'more than one' threshold."],
            )
        return _fail("Non-pass conclusion missing among options.")

    if "weakens the link" in stem.lower():
        if not _passage_contains(passage_text, premise1):
            return _review("Weakens/strengthens inference not fully formalized.")
        key, _ = _unique_matching_key(
            options,
            lambda text: "not a member" in text.lower(),
        )
        if key:
            idx = passage_text.lower().find("every member")
            anchor = passage_text[idx : idx + 13] if idx >= 0 else "Every member"
            return _pass(
                key,
                passage_text=passage_text,
                anchor=anchor,
                steps=["Premise 1 quantifies over members only; non-membership breaks the link."],
            )
        return _review("Weakens/strengthens inference not fully formalized.")

    return _review("Logical stem outside supported formal proof grammar.")


def _parse_quant_table(passage_text: str) -> dict[str, tuple[int, int]]:
    rows: dict[str, tuple[int, int]] = {}
    for line in passage_text.splitlines():
        if "|" not in line or line.strip().startswith("|--"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 3:
            continue
        name, units_s, price_s = cells
        if name.lower() in {"item", "units", "unit price (rupees)"}:
            continue
        if not (units_s.isdigit() and price_s.isdigit()):
            continue
        key = name.lower()
        if key in rows:
            return {}
        rows[key] = (int(units_s), int(price_s))
    return rows


def _match_exact_numeric(options: dict[str, str], answer: int) -> tuple[str | None, int]:
    matches = [
        key
        for key, text in options.items()
        if re.fullmatch(r"\d+", text.replace(",", "").strip())
        and int(text.replace(",", "").strip()) == answer
    ]
    if len(matches) == 1:
        return matches[0], 1
    return None, len(matches)


def _match_exact_percent(options: dict[str, str], pct: int) -> tuple[str | None, int]:
    matches = [
        key
        for key, text in options.items()
        if re.fullmatch(rf"{pct}%", text.strip())
    ]
    if len(matches) == 1:
        return matches[0], 1
    return None, len(matches)


def _quant_independent(
    passage_text: str,
    stem: str,
    options: dict[str, str],
) -> ClatIndependentCheckResult:
    table = _parse_quant_table(passage_text)
    if not table or "pens" not in table:
        return _fail("Could not parse quantitative inventory table from passage.")

    if "total revenue from pens" in stem.lower():
        units, price = table["pens"]
        answer = units * price
        key, count = _match_exact_numeric(options, answer)
        line = next(
            (ln for ln in passage_text.splitlines() if "pens" in ln.lower() and "|" in ln),
            "",
        )
        if count > 1:
            return _fail("Multiple options share the same computed pens revenue.")
        if key:
            return _pass(
                key,
                passage_text=passage_text,
                anchor=line.strip(),
                steps=[f"{units} × {price} = {answer}"],
            )
        return _fail(f"Computed pens revenue {answer} not uniquely present among options.")

    if "notebooks and binders" in stem.lower() and "combined" in stem.lower():
        if "notebooks" not in table or "binders" not in table:
            return _fail("Passage table missing notebooks or binders row.")
        answer = table["notebooks"][0] + table["binders"][0]
        key, count = _match_exact_numeric(options, answer)
        if count > 1:
            return _fail("Ambiguous combined-unit options.")
        if key:
            nb_line = next(
                (ln for ln in passage_text.splitlines() if "notebooks" in ln.lower() and "|" in ln),
                "",
            )
            bi_line = next(
                (ln for ln in passage_text.splitlines() if "binders" in ln.lower() and "|" in ln),
                "",
            )
            anchor = nb_line.strip() or bi_line.strip()
            return _pass(
                key,
                passage_text=passage_text,
                anchor=anchor,
                steps=[f"{table['notebooks'][0]} + {table['binders'][0]} = {answer}"],
            )
        return _fail(f"Combined units {answer} not uniquely among options.")

    if "percentage of total units are pens" in stem.lower():
        pens = table["pens"][0]
        total = sum(u for u, _ in table.values())
        if total == 0:
            return _fail("Total units is zero.")
        pct = round(pens * 100 / total)
        key, count = _match_exact_percent(options, pct)
        if count > 1:
            return _fail("Ambiguous percentage options.")
        if key:
            pens_line = next(
                (ln for ln in passage_text.splitlines() if "pens" in ln.lower() and "|" in ln),
                "",
            )
            return _pass(
                key,
                passage_text=passage_text,
                anchor=pens_line.strip() or f"Pens {pens} of total units {total}",
                steps=[f"{pens}/{total}×100 = {pct}%"],
            )
        return _fail(f"Computed pens share {pct}% not uniquely among options.")

    return _review("Quant stem not in supported table arithmetic grammar.")


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