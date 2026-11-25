# Day 18 — React Product Surfaces 36-task scope and evidence matrix

**Status:** **0 PASS / 35 PARTIAL / 0 SOURCE_PENDING / 1 NOT_STARTED = 36 rows.** D18-36 pending Founder signoff.  
**Authoritative specification:** [Issue #62](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/issues/62).  
**Branch:** `feature/day18-react-product-surfaces` (PR #63). Day11 PR31, Day15 PR57, Day17 PR61 held.

| ID | Approved task | Evidence / test IDs | State | Blocker / remaining proof |
|---|---|---|---|---|
| D18-01 | Scope and dependency freeze | `governance.py`, `D18-SCOPE-MAP.md`, `test_day18_m0_governance.py` | PARTIAL | Founder exact-HEAD review pending |
| D18-02 | Frontend architecture | `App.tsx`, `AppRouter.tsx`, `features/*`, `playwright.config.ts` | PARTIAL | PR #63 review |
| D18-03 | Product shell | `ProductShell.tsx`, `styles.css`, `e2e/day18.spec.ts` | PARTIAL | Responsive tablet proof in browser |
| D18-04 | Capability readiness | `capability/readiness.ts`, `FoundationStatusPage.tsx` | PARTIAL | Tamper tests partial in e2e |
| D18-05 | API client contracts | `contracts/allowed-endpoints.ts`, `api/health.ts`, `api/system.ts` | PARTIAL | Only merged endpoints whitelisted |
| D18-06 | Authentication surfaces | `AuthDesignPage.tsx`, `day17-inert.ts` | PARTIAL | No credential capture |
| D18-07 | Role and tenant navigation | `catalogue.ts`, `ProductShell.tsx` | PARTIAL | Design fixtures only |
| D18-08 | Question Studio shell | `QuestionStudioPage.tsx` | PARTIAL | Generation disabled |
| D18-09 | Curriculum selection | `curriculumScope.ts`, studio cascade | PARTIAL | Leaf concept validation |
| D18-10 | Exam selection | `exams.ts`, exam pack select | PARTIAL | Source-pending labels |
| D18-11 | Exact-count practice controls | `positiveInteger.ts`, `e2e/day18.spec.ts` | PARTIAL | Overflow bound demo-only |
| D18-12 | Replica paper controls | `exams.ts` TWO_PAPER_CONTRACT | PARTIAL | Issuance blocked |
| D18-13 | Question preview | `questions-teacher.ts`, `StemRenderer.tsx` | PARTIAL | Teacher/student separation |
| D18-14 | STEM rendering | `safeRender.ts`, katex, studio table/SVG | PARTIAL | Adversarial HTML not fuzzed |
| D18-15 | Educational metadata | teacher preview meta-dl | PARTIAL | Synthetic competency codes |
| D18-16 | Provenance panel | studio provenance section | PARTIAL | No activation |
| D18-17 | Validation and repair UI | studio validation + FailClosedAction | PARTIAL | No fake PASS |
| D18-18 | Async job UX | `jobs.ts`, studio job panel | PARTIAL | Static fixtures only |
| D18-19 | Paper preview | `SYNTHETIC_PAPER_PREVIEW` table | PARTIAL | Planned vs delivered shown |
| D18-20 | Print/export | `exportPrint.ts`, studio export buttons | PARTIAL | Watermarked synthetic only |
| D18-21 | Student runner shell | `StudentRunnerPage.tsx` | PARTIAL | No submission |
| D18-22 | Answer interaction | runner MCQ/multiselect/numerical/descriptive | PARTIAL | Ephemeral memory only |
| D18-23 | Student result view | `StudentResultPage.tsx` | PARTIAL | Illustrative score only |
| D18-24 | Student diagnostics | `StudentDiagnosticsPage.tsx` | PARTIAL | Unknown vs weak labels |
| D18-25 | Teacher diagnostics | `TeacherDiagnosticsPage.tsx` | PARTIAL | No real cohort data |
| D18-26 | Adaptive remediation surface | `RemediationPage.tsx` | PARTIAL | Runtime blocked |
| D18-27 | Knowledge and teacher library | `KnowledgeLibraryPage.tsx` | PARTIAL | Unavailable backend |
| D18-28 | Source administration | `SourceAdminPage.tsx` | PARTIAL | Live intake off |
| D18-29 | Exam/curriculum onboarding | `PackOnboardingPage.tsx` | PARTIAL | No writes |
| D18-30 | Policy and API administration | `PolicyAdminPage.tsx` | PARTIAL | Day17 held |
| D18-31 | Accessibility and responsive design | `styles.css`, focus styles, `e2e/day18.spec.ts` | PARTIAL | Full contrast audit deferred |
| D18-32 | Privacy and frontend security | `containment.py`, student fixtures | PARTIAL | Storage tamper e2e partial |
| D18-33 | Fixture and integration discipline | `catalogue.ts`, `containment.py` | PARTIAL | No mock-as-real server |
| D18-34 | End-to-end UI verification | `frontend/e2e/day18.spec.ts` | PARTIAL | Playwright local/CI only |
| D18-35 | CI and Founder verifier | `day18_verify.py`, `test_day18_verify_sha.py`, targeted-ci | PARTIAL | Full regression deferred |
| D18-36 | Independent acceptance and stop | This matrix | NOT_STARTED | Chief Architect + Founder |

## Acceptance rules
- UI must remain default-deny; no path elevates capability while Day17 and other holds remain.
- Student runner bundles must not ship answer keys or correctness labels.
- Only merged health/system endpoints may be called from the client allowlist.
- D18-36 remains NOT_STARTED until separate Founder signoff; Day19 stays locked.