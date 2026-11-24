from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.ca_imat_eapcet.constants import (
    EAPCET_ENGINEERING_SECTIONS,
    IMAT_OPTIONS_PER_QUESTION,
    IMAT_TOTAL_QUESTIONS,
)
from app.ca_imat_eapcet.content_validation import derive_content_fingerprint
from app.ca_imat_eapcet.contracts import DescriptiveItemContract, DescriptiveSubpart, QuestionRef
from app.ca_imat_eapcet.synthetic_item_banks import (
    CA_ECONOMICS_TOPICS,
    IMAT_BIOLOGY_BANK,
    IMAT_CHEMISTRY_BANK,
    IMAT_PHYSICS_BANK,
)


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
        base = 20 * (i + 1)
        pct = 15
        correct_val = str((Decimal(base) * Decimal(pct) / Decimal(100)).quantize(Decimal("0.01")))
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
    items: list[QuestionRef] = []
    for i in range(size):
        body, opts, key = CA_ECONOMICS_TOPICS[i % len(CA_ECONOMICS_TOPICS)]
        stem = f"CA_BE: {body} Case {i + 1}."
        items.append(
            _mcq(
                qid=f"ca_be_{i:03d}",
                paper_or_section="paper4_business_economics",
                stem_text=stem,
                options=dict(opts),
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


_READING_BANK = (
    ("If all A are B and all B are C, are all A necessarily C?", "Yes"),
    ("No mammals are plants. A whale is a mammal. Is a whale a plant?", "No"),
    ("If it rains, the ground is wet. The ground is wet. Did it rain?", "Cannot say"),
    ("Every student passed. Maria is a student. Did Maria pass?", "Yes"),
    ("Some birds cannot fly. Penguins are birds. Can all penguins fly?", "No"),
    ("If x>5 then x>2. x=6. Is x>2?", "Yes"),
    ("All squares are rectangles. Is every rectangle a square?", "No"),
    ("If today is Monday, tomorrow is Tuesday. Today is Monday. Tomorrow?", "Tuesday"),
    ("No cats are dogs. Felix is a cat. Is Felix a dog?", "No"),
    ("Either A or B. Not B. Therefore?", "A"),
)

_LOGIC_BANK = (
    ("If P implies Q and P is true, is Q true?", "Yes"),
    ("If P implies Q and Q is false, is P false?", "Yes"),
    ("Contrapositive of 'if P then Q' is equivalent?", "Yes"),
    ("If all A are B, is 'some B are A' always true?", "Sometimes"),
    ("De Morgan: not (P and Q) equals?", "not P or not Q"),
    ("Is 'if P then Q' equivalent to 'not P or Q'?", "Yes"),
    ("If P and Q, is P true?", "Yes"),
    ("Exclusive or: exactly one of P,Q is true. P true Q false?", "True"),
    ("If no A are B, can some A be B?", "Never"),
    ("Modus tollens: if P then Q, not Q, conclude?", "not P"),
)


def _imat_section_item(section: str, idx: int) -> QuestionRef:
    if section == "biology":
        body, options, correct, topic = IMAT_BIOLOGY_BANK[idx % len(IMAT_BIOLOGY_BANK)]
        stem = f"IMAT_BIO: {body}"
    elif section == "math":
        val = 3 + 7 * 2 + idx
        stem = f"IMAT_MATH: Evaluate 3 + 7 * 2 + {idx}"
        vals = [val - 1, val, val + 1, val + 2, val + 3]
        options = {k: str(v) for k, v in zip("ABCDE", vals, strict=True)}
        correct = "B"
        topic = "arithmetic"
    elif section == "reading":
        body, ans = _READING_BANK[idx % len(_READING_BANK)]
        stem = f"IMAT_READ: {body}"
        options = {
            "A": ans,
            "B": "Maybe",
            "C": "Never",
            "D": "Uncertain",
            "E": "Unknown",
        }
        correct = "A"
        topic = "reading"
    elif section == "logic":
        body, ans = _LOGIC_BANK[idx % len(_LOGIC_BANK)]
        stem = f"IMAT_LOGIC: {body}"
        options = {
            "A": ans,
            "B": "No",
            "C": "Unknown",
            "D": "Only if B=C",
            "E": "Only sometimes",
        }
        correct = "A"
        topic = "logic"
    elif section == "chemistry":
        body, options, correct, topic = IMAT_CHEMISTRY_BANK[idx % len(IMAT_CHEMISTRY_BANK)]
        stem = f"IMAT_CHEMISTRY: {body}"
    elif section == "physics":
        body, options, correct, topic = IMAT_PHYSICS_BANK[idx % len(IMAT_PHYSICS_BANK)]
        stem = f"IMAT_PHYSICS: {body}"
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


def _eapcet_section_item(stream: str, section: str, local: int, global_idx: int) -> QuestionRef:
    idx = local
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
        mass = 2 + local
        weight = mass * 10
        stem = f"EAP_PHY: A {mass} kg block on Earth (g=10 m/s^2). Weight in newtons?"
        options = {
            "A": str(weight - 5),
            "B": str(weight),
            "C": str(weight + 3),
            "D": str(weight + 7),
        }
        correct = "B"
        topic = "mechanics"
    elif section == "chemistry":
        atomic_num = 3 + local
        elements = (
            "lithium",
            "beryllium",
            "boron",
            "carbon",
            "nitrogen",
            "oxygen",
            "fluorine",
            "neon",
            "sodium",
            "magnesium",
        )
        ans_text = elements[local % len(elements)]
        stem = f"EAP_CHEM: Element with atomic number {atomic_num} matches which name?"
        options = {"A": ans_text, "B": "helium", "C": "argon", "D": "krypton"}
        correct = "A"
        topic = "chemistry"
    elif section == "botany":
        tissues = ("parenchyma", "collenchyma", "sclerenchyma", "xylem")
        ans = tissues[local % len(tissues)]
        stem = (
            f"EAP_BOT: In plant specimen {local + 1}, which tissue best matches "
            f"specialized food-storage parenchyma?"
        )
        options = {"A": ans, "B": "ribosome", "C": "centriole", "D": "nucleolus"}
        correct = "A"
        topic = "botany"
    elif section == "zoology":
        prompts = (
            ("blood filtration", "kidney"),
            ("gas exchange", "lung"),
            ("bile secretion", "liver"),
            ("systemic circulation pump", "heart"),
        )
        role, ans = prompts[local % len(prompts)]
        stem = f"EAP_ZOO: Sample {local + 1}: primary organ for {role}?"
        options = {"A": ans, "B": "spleen", "C": "pancreas", "D": "thyroid"}
        correct = "A"
        topic = "zoology"
    else:
        stem = f"EAP_{section.upper()}: Concept check {idx}"
        options = {k: f"{section}_{k}" for k in "ABCD"}
        correct = "A"
        topic = section
    return _mcq(
        qid=f"eapcet_{stream}_{section}_{global_idx:04d}",
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
    global_idx = 0
    for section, count in sections.items():
        for local in range(count):
            items.append(_eapcet_section_item(stream, section, local, global_idx))
            global_idx += 1
    return tuple(items)


def filter_pool(
    pool: tuple[QuestionRef, ...],
    *,
    paper_or_section: str,
    topic_code: str | None,
) -> tuple[QuestionRef, ...]:
    out = pool
    if paper_or_section and paper_or_section not in ("full_paper", ""):
        out = tuple(q for q in out if q.paper_or_section == paper_or_section)
    if topic_code:
        out = tuple(q for q in out if q.topic_code == topic_code)
    return out