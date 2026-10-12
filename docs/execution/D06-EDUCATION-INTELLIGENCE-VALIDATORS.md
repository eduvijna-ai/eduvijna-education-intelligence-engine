# Day 6 — Education Intelligence Validators

Base: `a40c28a3167d9cee0b6ec0e4944ed414fc2a4dd6` on `develop`. Founder signed off Day 5 on 2026-10-07. Day 5 merge commit is `5d3927b5e582b2c5aa898b5e755bfbb194eca74b`. D5-DS01 remains deferred and open as issue #16; Day 6 must not weaken or bypass that source gate.

**Authoritative numbering:** D6-01…D6-36 in this document match the PR handoff and `D06-SCOPE-MAP.md`. Paper-level cognitive/competency percentage distribution is **Day 10**, not Day 6.

## Objective

Build Eduvijna's deterministic, auditable Education Intelligence validation layer on top of the merged canonical domain/source/curriculum architecture.

By the Day 6 completion gate, Eduvijna must accept a canonical assessment item and return versioned validation results for:
- locked cognitive levels and competency tagging;
- learning-outcome and official competency alignment;
- per-item target vs observed cognition and cognitive-progression primitives;
- rubric integrity, design-time difficulty, age/grade appropriateness;
- structural clarity and educational-quality rules;
- bias/safety and policy precedence with institution boundaries.

Day 6 validates supplied content and metadata. It does **not** generate questions, call AnythingLLM, orchestrate LangGraph, implement exam planners, paper-level distribution engines, diagnostic distractors, or learner remediation.

## Locked taxonomy boundary

Competencies: knowledge, conceptual_understanding, application, analysis, problem_solving, hots.

Cognitive levels: remember, understand, apply, analyze, evaluate.

Taxonomies are versioned/configurable; do not silently remap official v1 values.

## Core result contract

Every validator result must be machine-readable and auditable (`validator_id`, `validator_version`, `status`, `rule_codes`, `target`, `observed`, `evidence`, versions, provenance, `created_at`). Insufficient evidence may return `review_required`.

## Task list (D6-01…D6-36)

| ID | Summary |
|----|---------|
| D6-01 | Freeze Day 6 scope map; exclude Days 7–10+ product/RAG/planner work |
| D6-02 | Generic validator architecture (registry, composition, no board branches) |
| D6-03 | Standard `ValidationResult` contract |
| D6-04 | Versioned taxonomy registry (idempotent seed, historical versions) |
| D6-05 | Cognitive taxonomy validator |
| D6-06 | Competency taxonomy validator |
| D6-07 | Learning-outcome validator (exact curriculum/version/grade/medium/subject) |
| D6-08 | Source-backed competency validator |
| D6-09 | Cognitive-demand evidence model |
| D6-10 | Target vs observed cognitive level (per item) |
| D6-11 | Cognitive-progression primitives (no paper distribution) |
| D6-12 | Design-time difficulty profile model |
| D6-13 | Difficulty validator |
| D6-14 | Age/grade appropriateness |
| D6-15 | Structural clarity validator |
| D6-16 | Educational-quality rule pack |
| D6-17 | Canonical rubric model |
| D6-18 | Rubric integrity validator |
| D6-19 | Versioned policy registry |
| D6-20 | Policy precedence engine |
| D6-21 | Institution override boundary |
| D6-22 | Bias/fairness/safety validator |
| D6-23 | Evidence-authority separation |
| D6-24 | Exact provenance binding |
| D6-25 | Composed `ValidationRun` |
| D6-26 | Severity/blocking semantics from versioned metadata |
| D6-27 | Human-readable evidence output |
| D6-28 | Validation audit history |
| D6-29 | Deterministic/idempotent validation |
| D6-30 | Internal service/CLI (`EducationIntelligenceValidationService`, `day6_verify`) |
| D6-31 | Positive CBSE/Telangana fixtures |
| D6-32 | Adversarial fixtures |
| D6-33 | SQLite/PostgreSQL compatibility |
| D6-34 | Alembic migration safety |
| D6-35 | Founder verification harness |
| D6-36 | Evidence map and stop gate |

Implementation and test mapping: `D06-SCOPE-MAP.md`.

## Founder acceptance demonstration

```text
canonical assessment item
  -> curriculum/version/LO validation
  -> competency validation
  -> cognitive-level validation (per item)
  -> cognitive-progression primitives
  -> difficulty validation
  -> age/grade + educational-quality validation
  -> rubric validation when applicable
  -> bias/safety + policy precedence
  -> structured ValidationRun
  -> exact provenance / rule codes
```

Paper-level cognitive/competency distribution for supplied item sets is **Day 10**.

## Completion gate

Day 6 engineering is complete when D6-01…D6-36 are evidenced, deterministic versioned validation is reproducible, policy precedence is fail-closed, D5-DS01 remains open, independent review has no blocker/major finding, and full CI is green on one exact candidate SHA.

## Explicit exclusions

- AnythingLLM / RAG (Day 7)
- LangGraph (Day 8)
- Diagnostic distractors (Day 9)
- Prerequisite/root-cause diagnostics and **paper-level cognitive/competency distribution** (Day 10)
- Exam paper planners/generation (later examination days)
- Learner adaptation (Days 15–16)
- Public REST/MCP (Day 17)
- Final React product surfaces (Day 18)
