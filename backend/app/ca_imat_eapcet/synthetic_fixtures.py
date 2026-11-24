from __future__ import annotations

from dataclasses import dataclass

from app.ca_imat_eapcet.constants import (
    EAPCET_ENGINEERING_SECTIONS,
    IMAT_OPTIONS_PER_QUESTION,
    IMAT_TOTAL_QUESTIONS,
)
from app.ca_imat_eapcet.content_validation import derive_content_fingerprint
from app.ca_imat_eapcet.contracts import DescriptiveItemContract, DescriptiveSubpart, QuestionRef


@dataclass(frozen=True, slots=True)
class SyntheticPools:
    objective_by_paper: dict[str, tuple[QuestionRef, ...]]
    descriptive_samples: tuple[DescriptiveItemContract, ...]
    pool_fingerprint: str
    demonstration_only: bool = True


def _mcq(
    *,
    qid: str,
    paper_or_section: str,
    stem_text: str,
    options: dict[str, str],
    correct_key: str,
    topic_code: str,
    marks_correct: float = 1.0,
    marks_incorrect: float = 0.0,
) -> QuestionRef:
    fp = derive_content_fingerprint(
        stem_text=stem_text,
        options=options,
        correct_key=correct_key,
    )
    return QuestionRef(
        question_id=qid,
        paper_or_section=paper_or_section,
        topic_code=topic_code,
        fingerprint=fp,
        correct_key=correct_key,
        marks_if_correct=marks_correct,
        marks_if_incorrect=marks_incorrect,
        stem_text=stem_text,
        options=options,
        question_kind="objective",
        independently_validated=False,
    )


def build_ca_quant_pool(*, size: int) -> tuple[QuestionRef, ...]:
    items: list[QuestionRef] = []
    for i in range(size):
        base = 200 + i
        pct = 15
        correct_val = str(int(base * pct / 100))
        options = {
            "A": str(int(base * 0.10)),
            "B": correct_val,
            "C": str(int(base * 0.20)),
            "D": str(int(base * 0.25)),
        }
        stem = f"CA_QA: What is {pct}% of {base}?"
        items.append(
            _mcq(
                qid=f"ca_qa_{i:03d}",
                paper_or_section="paper3_quantitative_aptitude",
                stem_text=stem,
                options=options,
                correct_key="B",
                topic_code="percentages",
            )
        )
    return tuple(items)


def build_ca_economics_pool(*, size: int) -> tuple[QuestionRef, ...]:
    stems = [
        (
            "CA_BE: Opportunity cost is best defined as:",
            {
                "A": "Accounting profit after tax",
                "B": "Value of the next best alternative forgone",
                "C": "Total revenue minus explicit costs",
                "D": "Marginal cost of production",
            },
            "B",
        ),
        (
            "CA_BE: Law of demand states price rises then quantity demanded:",
            {"A": "Rises", "B": "Falls", "C": "Unchanged", "D": "Doubles"},
            "B",
        ),
    ]
    items: list[QuestionRef] = []
    for i in range(size):
        stem, opts, key = stems[i % len(stems)]
        stem = f"{stem} (item {i})"
        items.append(
            _mcq(
                qid=f"ca_be_{i:03d}",
                paper_or_section="paper4_business_economics",
                stem_text=stem,
                options=opts,
                correct_key=key,
                topic_code="microeconomics",
            )
        )
    return tuple(items)


def build_accounting_descriptive() -> DescriptiveItemContract:
    subparts = [
        DescriptiveSubpart(
            subpart_id="acct_journal",
            prompt=(
                "From the following original scenario, journalize: Cash sales Rs 12,000; "
                "credit purchases Rs 5,000. Show totals that reconcile."
            ),
            max_marks=6.0,
            model_solution_steps=[
                "Debit Cash 12000; Credit Sales 12000",
                "Debit Purchases 5000; Credit Creditors 5000",
                "Trial balance debits equal credits",
            ],
            partial_credit_bounds=(0.0, 6.0),
        ),
        DescriptiveSubpart(
            subpart_id="acct_tb",
            prompt="Prepare a one-line trial balance total check proving debit = credit.",
            max_marks=4.0,
            model_solution_steps=["Sum debits", "Sum credits", "Demonstrate equality"],
            partial_credit_bounds=(0.0, 4.0),
        ),
    ]
    return DescriptiveItemContract(
        item_id="paper1_accounting_desc_001",
        paper_code="paper1_accounting",
        stem_intro=(
            "Original ICAI-style accounting scenario (synthetic, not copyrighted RTP text)."
        ),
        subparts=subparts,
        total_marks=10.0,
        rubric_valid=True,
        automated_grading_claimed=False,
    )


def build_business_laws_descriptive() -> DescriptiveItemContract:
    subparts = [
        DescriptiveSubpart(
            subpart_id="law_offer",
            prompt=(
                "A shopkeeper displays a camera with a price tag but states it is not for sale. "
                "Analyse whether a valid offer exists under the Indian Contract Act framework."
            ),
            max_marks=6.0,
            model_solution_steps=[
                "Define offer vs invitation to treat",
                "Apply display-of-goods principle",
                "Reasoned conclusion",
            ],
            partial_credit_bounds=(0.0, 6.0),
        ),
        DescriptiveSubpart(
            subpart_id="law_remedy",
            prompt="State the primary equitable remedy for misrepresentation and justify briefly.",
            max_marks=4.0,
            model_solution_steps=["Identify rescission", "Link to misrepresentation facts"],
            partial_credit_bounds=(0.0, 4.0),
        ),
    ]
    return DescriptiveItemContract(
        item_id="paper2_business_laws_desc_001",
        paper_code="paper2_business_laws",
        stem_intro="Original contract-law fact pattern (synthetic demonstration).",
        subparts=subparts,
        total_marks=10.0,
        rubric_valid=True,
        automated_grading_claimed=False,
    )


def build_ca_pools(*, per_paper: int = 50) -> SyntheticPools:
    pools = {
        "paper3_quantitative_aptitude": build_ca_quant_pool(size=per_paper),
        "paper4_business_economics": build_ca_economics_pool(size=per_paper),
    }
    descriptive = (build_accounting_descriptive(), build_business_laws_descriptive())
    fp = derive_content_fingerprint(stem_text="ca_pool", options={"v": "1"}, correct_key="v")
    return SyntheticPools(
        objective_by_paper=pools,
        descriptive_samples=descriptive,
        pool_fingerprint=fp,
    )


def _imat_section_item(section: str, idx: int) -> QuestionRef:
    if section == "biology":
        stem = (
            f"IMAT_BIO: Which organelle is primarily responsible for "
            f"cellular respiration? ({idx})"
        )
        options = {
            "A": "mitochondrion",
            "B": "nucleus",
            "C": "ribosome",
            "D": "golgi apparatus",
            "E": "centriole",
        }
        correct = "A"
        topic = "biology_cell"
    elif section == "math":
        val = 3 + 7 * 2 + idx
        stem = f"IMAT_MATH: Evaluate 3 + 7 * 2 + {idx}"
        vals = [val - 1, val, val + 1, val + 2, val + 3]
        options = {k: str(v) for k, v in zip("ABCDE", vals, strict=True)}
        correct = "B"
        topic = "arithmetic"
    elif section == "reading":
        stem = f"IMAT_READ: If all A are B and all B are C, are all A necessarily C? ({idx})"
        options = {
            "A": "Yes",
            "B": "No",
            "C": "Only if B=C",
            "D": "Cannot say",
            "E": "Only sometimes",
        }
        correct = "A"
        topic = "reading"
    elif section == "logic":
        stem = f"IMAT_LOGIC: If all A are B and all B are C, are all A necessarily C? ({idx})"
        options = {
            "A": "Yes",
            "B": "No",
            "C": "Only if B=C",
            "D": "Cannot say",
            "E": "Only sometimes",
        }
        correct = "A"
        topic = "logic"
    elif section == "chemistry":
        stem = f"IMAT_CHEMISTRY: What is the chemical formula of water? ({idx})"
        options = {"A": "H2O", "B": "CO2", "C": "NaCl", "D": "O2", "E": "CH4"}
        correct = "A"
        topic = "chemistry"
    elif section == "physics":
        stem = f"IMAT_PHYSICS: What is the SI unit of force? ({idx})"
        options = {"A": "newton", "B": "joule", "C": "watt", "D": "pascal", "E": "ampere"}
        correct = "A"
        topic = "physics"
    else:
        stem = f"IMAT_{section.upper()}: Concept check {idx}"
        options = {
            chr(ord("A") + j): f"{section}_choice_{j}" for j in range(IMAT_OPTIONS_PER_QUESTION)
        }
        correct = "A"
        topic = section
    return _mcq(
        qid=f"imat_{section}_{idx:03d}",
        paper_or_section=section,
        stem_text=stem,
        options=options,
        correct_key=correct,
        topic_code=topic,
        marks_correct=1.5,
    )


def build_imat_pool() -> tuple[QuestionRef, ...]:
    sections = ("reading", "logic", "biology", "chemistry", "physics", "math")
    per_section = IMAT_TOTAL_QUESTIONS // len(sections)
    items: list[QuestionRef] = []
    idx = 0
    for section in sections:
        for _ in range(per_section):
            items.append(_imat_section_item(section, idx))
            idx += 1
    return tuple(items)


def _eapcet_section_item(stream: str, section: str, idx: int) -> QuestionRef:
    if section == "mathematics":
        root_sum = 5 + idx
        stem = f"EAP_MAT: For x^2 - {root_sum}x + {6 + idx} = 0, what is the sum of the roots?"
        options = {
            "A": str(root_sum - 2),
            "B": str(root_sum),
            "C": str(root_sum + 1),
            "D": str(root_sum + 2),
        }
        correct = "B"
        topic = "algebra"
    elif section == "physics":
        stem = f"EAP_PHY: What is the SI unit of force? ({idx})"
        options = {"A": "joule", "B": "newton", "C": "watt", "D": "pascal"}
        correct = "B"
        topic = "mechanics"
    elif section == "chemistry":
        stem = f"EAP_CHEM: Which particle carries negative charge? ({idx})"
        options = {"A": "electron", "B": "proton", "C": "neutron", "D": "positron"}
        correct = "A"
        topic = "chemistry"
    elif section == "botany":
        stem = f"EAP_BOT: Photosynthesis occurs primarily in which plant organelle? ({idx})"
        options = {"A": "chloroplast", "B": "mitochondrion", "C": "nucleus", "D": "vacuole"}
        correct = "A"
        topic = "botany"
    elif section == "zoology":
        stem = f"EAP_ZOO: Which blood cells are primary oxygen carriers? ({idx})"
        options = {"A": "erythrocytes", "B": "platelets", "C": "neutrophils", "D": "lymphocytes"}
        correct = "A"
        topic = "zoology"
    else:
        stem = f"EAP_{section.upper()}: Concept check {idx}"
        options = {k: f"{section}_{k}" for k in "ABCD"}
        correct = "A"
        topic = section
    return _mcq(
        qid=f"eapcet_{stream}_{section}_{idx:04d}",
        paper_or_section=section,
        stem_text=stem,
        options=options,
        correct_key=correct,
        topic_code=topic,
    )


def build_eapcet_pool(*, stream: str) -> tuple[QuestionRef, ...]:
    if stream == "engineering":
        sections = EAPCET_ENGINEERING_SECTIONS
    else:
        from app.ca_imat_eapcet.constants import EAPCET_AP_SECTIONS_REFERENCE

        sections = EAPCET_AP_SECTIONS_REFERENCE
    items: list[QuestionRef] = []
    idx = 0
    for section, count in sections.items():
        for _ in range(count):
            items.append(_eapcet_section_item(stream, section, idx))
            idx += 1
    return tuple(items)


def filter_pool(
    pool: tuple[QuestionRef, ...],
    *,
    paper_or_section: str,
    topic_code: str | None,
) -> tuple[QuestionRef, ...]:
    if topic_code:
        return tuple(q for q in pool if q.topic_code == topic_code)
    if paper_or_section not in ("full_paper", ""):
        return tuple(q for q in pool if q.paper_or_section == paper_or_section)
    return pool