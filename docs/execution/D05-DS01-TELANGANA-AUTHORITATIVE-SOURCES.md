# D5-DS01 — Telangana Authoritative Source Completion (Deferred)

Status: **DEFERRED_BY_FOUNDER**

This backlog preserves the five authoritative evidence packages intentionally deferred from Day 5 engineering closure. It does not weaken the existing live-source acceptance gate. Until this backlog is completed, Eduvijna must not claim that Telangana curriculum data is fully official-source verified for production use.

## Deferred evidence packages

1. **SCERT VIII science governing sources**
   - Physical Science: English + corresponding Telugu governing syllabus.
   - Biological Science: English + corresponding Telugu governing syllabus.
   - Academic applicability/version notice for the selected edition/year.

2. **SCERT I–X official inventory**
   - Complete selected official inventory snapshot.
   - Grade, instructional medium, subject language, language role, bilingual state, and Part 1/2 where present.
   - Preserve unavailable/duplicate/shared entries and exact source-row locators.

3. **Telangana Learning Outcomes / Academic Standards**
   - Official originals.
   - Exact class/stage, subject, medium, version/status, wording/code and locator.
   - No automatic NCERT/NCF equivalence.

4. **Intermediate catalogue and applicability**
   - Official First/Second Year General and Vocational subject/paper catalogue.
   - Source-backed course/group applicability, including MPC/BiPC/CEC/MEC/HEC only where official evidence states it.
   - Catalogue presence must not imply universal applicability.

5. **Historical/current Intermediate mathematics**
   - Historical First Year Mathematics IA governing syllabus.
   - Applicable current First/Second Year mathematics syllabi/version notices.
   - IA/IB/IIA/IIB identities and successor/history relationships only where evidenced.
   - Corresponding Telugu material where required by the Day-5 bounded scope.

## Required future workflow

For every supplied original:

1. register source metadata and issuing URL;
2. ingest the original privately through the existing Source Intelligence lifecycle;
3. extract without silent OCR/substitution unless separately approved;
4. validate exact source bytes/checksum;
5. review/diff changed revisions;
6. approve and activate only after applicability is verified;
7. materialize the frozen Day-5 catalogue/slices;
8. verify English↔Telugu relationships from bounded source evidence;
9. run Unicode/Indic fidelity checks on actual extracted text;
10. run `python -m app.day5_verify --fetch-official`.

## Completion gate

D5-DS01 is complete only when:

- all frozen required academic manifest identities are present and distinct;
- required official originals are verified through exact SourceRevisions;
- catalogue denominators reconcile without missing/duplicate/conflicting rows;
- all frozen detailed slices/relationships are source-backed;
- current/historical Intermediate identities and course applicability are proven;
- the Day-5 live official-source verifier exits 0;
- exact-head CI is green;
- independent Codex review has no blocker/major findings.

## Non-claims while deferred

While this backlog is open:

- source-discovery metadata is not governing curriculum evidence;
- Founder-provided prose is not official source evidence;
- supplemental government directories do not establish syllabus membership;
- annual plans/model papers do not substitute for governing syllabi;
- Day-5 deterministic/synthetic verification does not imply official-source acceptance;
- no public Git artifact may contain bulk copyrighted source files.

Day 6+ engineering may proceed after Founder signs off Day 5 under the explicit status **engineering complete / authoritative source ingestion deferred**, but any feature that needs fully verified Telangana source data must continue to fail closed or surface a review-required state until D5-DS01 is completed.
