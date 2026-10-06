# D04 — NCF / NCERT / CBSE Curriculum Intelligence

Status: ACTIVE  
Base: develop @ e64e361f53708d6d052bc19067a70d43cb3e34a6  
Builder branch: feature/day4-ncf-ncert-cbse  
Builder preference: Cursor Composer 2.5 Fast *(historical Day 4 record)*; zero-overage fallback is ChatGPT–GitHub connected implementation. Current Cursor model: standard Composer 2.5 per `AGENTS.md` (Founder override 2026-10-05).  
Reviewer: Codex  
Founder gate: stop after Day-4 engineering is green; do not unlock Day 5.

## Objective

Implement a source-backed, versioned CBSE CurriculumPack aligned to NCF/NCERT, preserving the hierarchy:

Education Framework → Curriculum → Academic Version → Grade/Year → Medium → Subject → Unit → Chapter → Topic → Concept → Learning Outcome → Competency → Prerequisites.

Day 4 is curriculum/source intelligence only. Do not implement question generation, LangGraph, AnythingLLM/RAG, Telangana curricula, public curriculum REST APIs, or final React curriculum administration UI.

## Authoritative source manifest

Use official authorities only for rules/evidence. If an official document cannot be retrieved, record it as blocked/review-required; do not substitute an unofficial copy.

1. Ministry of Education — NCF School Education 2023
   - authority: Ministry of Education, Government of India
   - type: official framework
   - URL: https://www.education.gov.in/sites/upload_files/mhrd/files/ncf_2023.pdf
2. NCERT — Learning Outcomes at Secondary Stage
   - authority: NCERT
   - type: official learning outcomes
   - URL: https://ncert.nic.in/pdf/publication/otherpublications/learning_outcomes.pdf
3. NCERT — official publication index / Learning Outcomes links
   - authority: NCERT
   - type: official publication index
   - URL: https://www.ncert.nic.in/
4. CBSE Academics — Curriculum 2026-27
   - authority: CBSE
   - type: official curriculum index
   - URL: https://cbseacademic.nic.in/curriculum_2027.html
5. CBSE Academics — Class X SQP + Marking Schemes 2026-27
   - authority: CBSE
   - type: official assessment evidence
   - URL: https://cbseacademic.nic.in/SQP_CLASSX_2026-27.html
6. CBSE Academics — Class XII SQP + Marking Schemes 2026-27
   - authority: CBSE
   - type: official assessment evidence
   - URL: https://cbseacademic.nic.in/SQP_CLASSXII_2026-27.html

The source registry may add exact subject-PDF URLs discovered from these official index pages, but may not add commercial coaching mirrors as official evidence.

## Implementation principles

- Reuse Day-2 curriculum models and Day-3 Source Intelligence; do not build a second ingestion system.
- Every derived curriculum/alignment/evidence record must bind to an exact SourceRevision where the schema supports it.
- Preserve official wording/locator separately from normalized Eduvijna metadata.
- Deterministic stable identities for repeat ingestion.
- Syllabus rules and SQP/marking-scheme evidence are different domains.
- Unsupported NCF↔CBSE mappings must remain inferred/partial/unresolved/review-required.
- Do not copy bulk copyrighted PDFs into public Git.
- Synthetic fixtures must be explicitly marked synthetic.
- SQLite local and PostgreSQL compile compatibility are mandatory.
- All prior Day-1/2/3 regression tests remain green.

## Acceptance checklist

- [ ] D4-01 Official-source manifest with authority, version/applicability, document type, URL/file, checksum/provenance.
- [ ] D4-02 Day-3 lifecycle integration: register → revision → extract → validate → approve → activate.
- [ ] D4-03 Blocked-source fallback records exact missing official document; no unofficial silent substitution.
- [ ] D4-04 Canonical Indian/National EducationFramework record(s) with version/authority/provenance.
- [ ] D4-05 NCF-SE structure represented without flattening framework competencies into CBSE chapters.
- [ ] D4-06 NCERT learning outcomes ingested/mapped; official wording/source locator retained separately.
- [ ] D4-07 Competency registry with stable codes/IDs, framework/version linkage and provenance.
- [ ] D4-08 LearningOutcome registry linked to competency/stage/grade/subject/concepts where evidence permits.
- [ ] D4-09 No invented official mappings; unsupported links are inferred/unmapped/review-required.
- [ ] D4-10 First-class CBSE CurriculumPack.
- [ ] D4-11 CBSE 2026-27 CurriculumVersion, not timeless CBSE.
- [ ] D4-12 Initial CBSE secondary/senior-secondary grades required by locked scope.
- [ ] D4-13 Medium remains in canonical hierarchy even where source is not medium-specific.
- [ ] D4-14 Source-backed subject catalogue with stable IDs and official names/codes where available.
- [ ] D4-15 Normalize syllabus headings to Unit → Chapter → Topic while retaining source locators.
- [ ] D4-16 Concept extraction contract distinguishes official text from Eduvijna-derived concepts.
- [ ] D4-17 Deterministic stable IDs across unchanged re-ingestion.
- [ ] D4-18 Reject duplicate sibling codes, missing parents, self-links, cross-version parents, hierarchy cycles.
- [ ] D4-19 Framework↔CBSE alignments carry relationship type + evidence.
- [ ] D4-20 Alignment status/confidence: direct/exact, derived/partial, unresolved/review-required.
- [ ] D4-21 Coverage report for mapped/partial/unmapped CBSE scope.
- [ ] D4-22 Only clearly-supported prerequisite edges seeded; rich prerequisite intelligence remains Day 10.
- [ ] D4-23 Register official CBSE SQPs/marking schemes for later pattern intelligence.
- [ ] D4-24 Structured assessment evidence model for sections, marks, question categories, competency emphasis, etc.
- [ ] D4-25 SQP/MS bound to correct academic version/class/subject.
- [ ] D4-26 Syllabus membership and assessment evidence remain separate.
- [ ] D4-27 Exact active SourceRevision binding for framework/curriculum/outcome/competency/alignment/evidence records.
- [ ] D4-28 Supersession preserves old curriculum versions and references.
- [ ] D4-29 Unchanged re-ingestion is idempotent.
- [ ] D4-30 Changed source uses Day-3 diff/review; no silent active mapping mutation.
- [ ] D4-31 Copyright-safe public storage.
- [ ] D4-32 Synthetic fixtures cannot masquerade as official complete CBSE ingestion.
- [ ] D4-33 Curriculum ingestion/mapping/retrieval repository/service boundaries.
- [ ] D4-34 Generic CurriculumPack architecture; no CBSE-specific logic in generic core.
- [ ] D4-35 Internal engineering queries across framework→version→class→subject→hierarchy→concept/LO/competency.
- [ ] D4-36 Provenance query returns exact SourceRevision and locator.
- [ ] D4-37 NCF/NCERT ingestion tests.
- [ ] D4-38 CBSE hierarchy/version/idempotency tests.
- [ ] D4-39 Alignment direct/partial/unresolved tests.
- [ ] D4-40 Assessment evidence version-binding/separation tests.
- [ ] D4-41 Source-change regression preserves prior active curriculum until approval.
- [ ] D4-42 SQLite runtime + PostgreSQL DDL compile compatibility.
- [ ] D4-43 Alembic upgrade → downgrade → re-upgrade; populated-data preservation; failure rollback; alembic check.
- [ ] D4-44 Full Day-1/2/3 regression + lint/typecheck/frontend build/Compose smoke.
- [ ] D4-45 Founder Day-4 verification script demonstrating one complete source-backed curriculum path.
- [ ] D4-46 Founder coverage report with source inventory, entity counts, alignment coverage and unresolved items.
- [ ] D4-47 Completion report mapping every acceptance ID to code/test/evidence and stopping before Day 5.

## Expected code shape

Prefer additions under:
- backend/app/curriculum_intelligence/ (services, repositories/query helpers, ingestion normalization)
- backend/app/models/curriculum.py and associations only where domain persistence is genuinely missing
- backend/app/schemas/ for Day-4 internal contracts
- backend/migrations/versions/20261004_0008_*.py if persistence changes are needed
- backend/tests/test_day4_*.py
- content/curricula/ for copyright-safe manifests/normalized metadata only
- scripts/ingestion/ or backend CLI helpers for repeatable engineering ingestion/verification
- docs/execution/D04-*.md for completion/Founder evidence

Do not create CBSE-specific controllers or public routes on Day 4.

## Minimum source-backed demonstration

1. Official NCF/NCERT source
2. Active SourceRevision
3. EducationFramework / Competency / LearningOutcome
4. CBSE 2026-27 CurriculumVersion
5. Class → Subject → Unit/Chapter/Topic → derived Concept
6. Alignment with explicit status
7. Exact source locator/provenance

Separate assessment demonstration:

CBSE official SQP/MS → correct version/class/subject → AssessmentEvidence; evidence must not mutate syllabus membership.

## Builder exit commands

Run at minimum:
- backend pytest suite
- ruff
- mypy
- frontend typecheck/build
- alembic upgrade head
- alembic downgrade -1
- alembic upgrade head
- alembic check
- PostgreSQL compile tests
- Day-4 verification script
- Docker Compose smoke if available in CI

Attach exact results to the PR. No failing CI may be merged.
