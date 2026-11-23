"""F03-B: original synthetic CLAT passages (four non-news sections only)."""

from __future__ import annotations

from app.cuet_clat.clat_passage_contracts import ClatAuthoredMcq, ClatOriginalPassage

ENGLISH_PASSAGE = ClatOriginalPassage(
    passage_id="d13-clat-p-english-001",
    section_code="english",
    passage_text=(
        "The hillside town of Alderford opened a community library in 2019. "
        "Volunteers spent three months of planning before construction began. "
        "Architect Ms. Rao proposed a dedicated children's corner with low shelves "
        "and story cushions. The council approved forty thousand rupees for shelving "
        "and lighting, but deferred purchases of new computers until the next budget cycle. "
        "By spring, weekday foot traffic doubled, and weekend reading circles became "
        "a regular fixture."
    ),
    questions=[
        ClatAuthoredMcq(
            question_id="d13-clat-q-english-001",
            passage_id="d13-clat-p-english-001",
            section_code="english",
            stem_text="According to the passage, how long did volunteers spend on planning?",
            options={
                "A": "One month",
                "B": "Three months",
                "C": "Six months",
                "D": "One year",
            },
            author_key="B",
            explanation="The passage states volunteers spent three months of planning.",
        ),
        ClatAuthoredMcq(
            question_id="d13-clat-q-english-002",
            passage_id="d13-clat-p-english-001",
            section_code="english",
            stem_text="Who proposed the children's corner with low shelves?",
            options={
                "A": "The council treasurer",
                "B": "A weekend reading coach",
                "C": "Ms. Rao",
                "D": "The head librarian",
            },
            author_key="C",
            explanation="Ms. Rao proposed the children's corner.",
        ),
        ClatAuthoredMcq(
            question_id="d13-clat-q-english-003",
            passage_id="d13-clat-p-english-001",
            section_code="english",
            stem_text="How much did the council approve for shelving and lighting?",
            options={
                "A": "Twenty thousand rupees",
                "B": "Thirty thousand rupees",
                "C": "Forty thousand rupees",
                "D": "Fifty thousand rupees",
            },
            author_key="C",
            explanation="The council approved forty thousand rupees.",
        ),
    ],
)

LEGAL_PASSAGE = ClatOriginalPassage(
    passage_id="d13-clat-p-legal-001",
    section_code="legal_reasoning",
    passage_text=(
        "Riverton Transit Code (fictional exercise only — not Indian law). "
        "Rule 7: No vehicle whose registered mass exceeds three tonnes may use "
        "Elm Bridge on weekdays between 07:00 and 09:00. Rule 12: A violation "
        "of Rule 7 carries a flat penalty of 500 transit credits payable within "
        "fourteen days. Rule 14: Vehicles at or below three tonnes may use Elm "
        "Bridge at any time unless a maintenance closure is posted."
    ),
    questions=[
        ClatAuthoredMcq(
            question_id="d13-clat-q-legal-001",
            passage_id="d13-clat-p-legal-001",
            section_code="legal_reasoning",
            stem_text=(
                "A delivery truck registered at 4.2 tonnes crosses Elm Bridge on "
                "Wednesday at 08:15. Under the Riverton Transit Code, what follows?"
            ),
            options={
                "A": "No penalty because the truck is commercial",
                "B": "The truck must pay 500 transit credits for a Rule 7 violation",
                "C": "The truck may cross without penalty before 09:30",
                "D": "Rule 7 does not apply to weekday mornings",
            },
            author_key="B",
            explanation="Mass exceeds three tonnes in the restricted window (Rule 12).",
        ),
        ClatAuthoredMcq(
            question_id="d13-clat-q-legal-002",
            passage_id="d13-clat-p-legal-001",
            section_code="legal_reasoning",
            stem_text=(
                "A kick-scooter registered at 0.15 tonnes crosses Elm Bridge on "
                "Tuesday at 07:45. What penalty applies?"
            ),
            options={
                "A": "500 transit credits",
                "B": "250 transit credits",
                "C": "No penalty under Rule 7",
                "D": "Automatic impoundment",
            },
            author_key="C",
            explanation="Registered mass 0.15 t is below Rule 7 during the morning window.",
        ),
        ClatAuthoredMcq(
            question_id="d13-clat-q-legal-003",
            passage_id="d13-clat-p-legal-001",
            section_code="legal_reasoning",
            stem_text=(
                "A passenger car registered at 2.8 tonnes uses Elm Bridge on Friday "
                "at 10:00 with no maintenance closure posted. What is the outcome?"
            ),
            options={
                "A": "Rule 7 violation and 500 credits",
                "B": "Use is allowed because mass is at most three tonnes",
                "C": "Use is forbidden on all weekdays",
                "D": "A 500-credit penalty applies regardless of mass",
            },
            author_key="B",
            explanation="Rule 14 allows at-or-below three tonnes when no closure is posted.",
        ),
    ],
)

LOGICAL_PASSAGE = ClatOriginalPassage(
    passage_id="d13-clat-p-logical-001",
    section_code="logical_reasoning",
    passage_text=(
        "Argument (fictional study group). Premise 1: Every member who attended "
        "all six review sessions passed the mock exam. Premise 2: Priya attended "
        "all six review sessions. Premise 3: No member who missed more than one "
        "session passed the mock exam. Conclusion candidate: Priya passed the mock exam."
    ),
    questions=[
        ClatAuthoredMcq(
            question_id="d13-clat-q-logical-001",
            passage_id="d13-clat-p-logical-001",
            section_code="logical_reasoning",
            stem_text="Which conclusion necessarily follows from Premises 1 and 2 alone?",
            options={
                "A": "Priya passed the mock exam",
                "B": "Priya missed more than one session",
                "C": "Some attendees failed the mock exam",
                "D": "Priya did not attend session six",
            },
            author_key="A",
            explanation="Premise 1 universal on attendees; Premise 2 places Priya in that set.",
        ),
        ClatAuthoredMcq(
            question_id="d13-clat-q-logical-002",
            passage_id="d13-clat-p-logical-001",
            section_code="logical_reasoning",
            stem_text=(
                "If Sam missed two review sessions, which statement is necessarily true "
                "given Premise 3?"
            ),
            options={
                "A": "Sam passed the mock exam",
                "B": "Sam attended all six sessions",
                "C": "Sam did not pass the mock exam",
                "D": "Sam attended exactly one session",
            },
            author_key="C",
            explanation="Missing two sessions satisfies 'more than one', so Sam did not pass.",
        ),
        ClatAuthoredMcq(
            question_id="d13-clat-q-logical-003",
            passage_id="d13-clat-p-logical-001",
            section_code="logical_reasoning",
            stem_text=(
                "Which option weakens the link between Premise 2 and the conclusion "
                "that Priya passed?"
            ),
            options={
                "A": "Priya attended all six review sessions",
                "B": "Priya was not a member of the study group",
                "C": "Premise 1 references attendees of all six sessions",
                "D": "The mock exam had twenty questions",
            },
            author_key="B",
            explanation="Premise 1 is about members; if Priya was not a member, the link breaks.",
        ),
    ],
)

QUANT_PASSAGE = ClatOriginalPassage(
    passage_id="d13-clat-p-quant-001",
    section_code="quantitative_techniques",
    passage_text=(
        "Inventory snapshot — Alderford supply closet (fictional data):\n"
        "| Item | Units | Unit price (rupees) |\n"
        "|------|-------|---------------------|\n"
        "| Pens | 12 | 50 |\n"
        "| Notebooks | 8 | 75 |\n"
        "| Binders | 5 | 120 |"
    ),
    questions=[
        ClatAuthoredMcq(
            question_id="d13-clat-q-quant-001",
            passage_id="d13-clat-p-quant-001",
            section_code="quantitative_techniques",
            stem_text="What is the total revenue from Pens (units times unit price)?",
            options={
                "A": "500",
                "B": "550",
                "C": "600",
                "D": "650",
            },
            author_key="C",
            explanation="12 × 50 = 600.",
        ),
        ClatAuthoredMcq(
            question_id="d13-clat-q-quant-002",
            passage_id="d13-clat-p-quant-001",
            section_code="quantitative_techniques",
            stem_text="How many units of Notebooks and Binders are there combined?",
            options={
                "A": "10",
                "B": "11",
                "C": "12",
                "D": "13",
            },
            author_key="D",
            explanation="8 + 5 = 13.",
        ),
        ClatAuthoredMcq(
            question_id="d13-clat-q-quant-003",
            passage_id="d13-clat-p-quant-001",
            section_code="quantitative_techniques",
            stem_text="What percentage of total units are Pens (nearest whole percent)?",
            options={
                "A": "38%",
                "B": "40%",
                "C": "42%",
                "D": "48%",
            },
            author_key="D",
            explanation="Total units 25; pens 12 → 48%.",
        ),
    ],
)


def load_original_synthetic_f03b_passages() -> tuple[ClatOriginalPassage, ...]:
    """Return the fixed F03-B synthetic passage set (four sections, twelve MCQs)."""

    return (ENGLISH_PASSAGE, LEGAL_PASSAGE, LOGICAL_PASSAGE, QUANT_PASSAGE)


def load_official_f03b_passages() -> tuple[ClatOriginalPassage, ...]:
    """Backward-compatible alias — synthetic fixtures only, not official CLAT sources."""

    return load_original_synthetic_f03b_passages()