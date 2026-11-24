"""D13-25: originally authored demonstration passages (no copyrighted bulk text)."""

from __future__ import annotations

ORIGINAL_PASSAGE_LIBRARY: dict[str, str] = {
    "english_demo_1": (
        "A municipal council debated whether evening markets should extend their hours. "
        "Traders argued that longer hours would increase household convenience, while "
        "residents cited noise and safety concerns after sunset."
    ),
    "legal_demo_1": (
        "Rule: A person who accepts a parcel knowing it was misdelivered must return it "
        "within seven days or compensate the rightful owner for its fair value."
    ),
    "logical_demo_1": (
        "Every student who completes the workshop receives a certificate. "
        "Some certificate holders also mentor new participants."
    ),
    "current_affairs_demo_1": (
        "Synthetic dated brief (2026-09-01): A regional science fair announced grants "
        "for school laboratories; the cited policy memo is a demonstration fixture only."
    ),
    "quantitative_demo_1": (
        "Table (synthetic): Units sold in three quarters were 120, 150, and 180. "
        "Management asked for the average quarterly sales and the percentage increase "
        "from the first to the third quarter."
    ),
}


def passage_for_section(section_code: str, *, index: int) -> tuple[str, str]:
    key_map = {
        "english": "english_demo_1",
        "legal_reasoning": "legal_demo_1",
        "logical_reasoning": "logical_demo_1",
        "current_affairs_gk": "current_affairs_demo_1",
        "quantitative_techniques": "quantitative_demo_1",
    }
    base = key_map.get(section_code, "english_demo_1")
    text = ORIGINAL_PASSAGE_LIBRARY[base]
    passage_id = f"passage_{section_code}_{index}"
    return passage_id, text