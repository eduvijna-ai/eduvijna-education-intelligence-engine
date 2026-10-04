# Day 5 — Telangana curricula (approved D5-01…D5-34)

Base: 7f1f86fe9e24dee3a663f1e7702df0946c1138ba. Founder signed off Day 4 and approved this plan plus seven attached tasks on 2026-10-04. Day 6 remains locked. Source-dependent portions remain blocked until actual evidence passes.

## Objective and base
Extend merged Day 4 architecture at commit 7f1f86fe9e24dee3a663f1e7702df0946c1138ba for Telangana SCERT Classes I–X and Telangana Intermediate First/Second Year. Deliver auditable catalogues and bounded source-backed examples with explicit version, year, medium, subject and exact-source boundaries. Reuse generic curriculum_intelligence services, catalogue parser, evidence/acceptance helpers, typed framework structure and LO links, reviewed baselines, official demonstration, source lifecycle and immutable 0009 marking-scheme provenance. Do not assume new schema is required.

## Verified source caveats
Source worker verified the Telangana government directory https://www.telangana.gov.in/state-web-directory/ maps the Board of Intermediate Education to https://tgbie.cgg.gov.in . The board portal returned F5 HTTP 403 in the cloud browser. No current TGBIE syllabus PDF was parsed. Current 2026–27 First Year Mathematics IA naming, revision and applicability remain unverified and blocked; no claim that historical Math IA is the current subject.
SCERT official search-indexed textbook page https://www.scert.telangana.gov.in/Home.aspx/Pdf/pdf/DisplayContent.aspx?encry=ammkNW4%2Fgx+NeApstGPX+A%3D%3D explicitly identifies TEXT BOOKS I TO X 2025–26 and VIII entries 8TM_PHY/8TM_BIO/8EM_PHY/8EM_BIO, including some Part1/Part2 labels. A separate official PDF index https://www.scert.telangana.gov.in/DisplayImage.aspx?encry=Ytc1G1ftx++8OiL2XRvtdg%3D%3D is 2025–26 DRAFT and labels VIII Physical Science Part1/Part2 Bilingual, with biology TM/EM separately. Live EBooks.aspx returned HTTP 502; other SCERT retrieval timed out. Indexed discovery is not document fetching or parsing.
SCERT syllabus index distinguishes General Science VI–VII from Physical Science and Bio. Science VIII–X. Preserve the VIII Physical Science/Biological Science split, book parts and bilingual status. A homepage Academic Calendar 2026–27 does not promote 2025–26 textbook content to current-year applicability. Final implementation must verify exact official document bytes, edition, applicability and subject/medium/part boundaries.

## Bounded initial scope
Catalogue the official SCERT I–X and Intermediate First/Second Year subject/book resources and medium labels exposed by selected official inventories, with exact snapshots and scope. Materialize entries only where class/year, medium and applicability are evidenced; catalogue presence is not detailed syllabus ingestion.
Detailed SCERT slice: VIII Physical Science and Biological Science, one named chapter per required component in English, plus one officially corresponding Telugu-medium chapter to prove medium handling; retain official parts/bilingual labels and validate correspondence from documents.
Detailed Intermediate slice: one mathematics chapter from First Year and one from Second Year in English, plus one officially corresponding Telugu-medium First Year slice where available. Preserve the locked First Year Math IA UAT under its verified historical version. Represent a revised current subject separately when evidence establishes it; do not silently rename UAT or treat historical content as current.
Before implementation, name each selected chapter, document, academic version and medium in the scope manifest. Remaining classes/subjects/chapters are catalogue-only unless explicitly added. No exhaustive textbook transcription or implied all-subject ingestion.

## Source requirements
Use official SCERT Telangana and officially verified Intermediate authority publications, indexes, syllabi and applicability/revision notices. Distinguish textbook edition, academic applicability, publication and retrieval dates. Preserve legacy names as evidence-backed aliases rather than conflating versions. Each detailed slice requires retrieved official bytes, exact SourceRevision/checksum, identity, verified scope and page/section locators. Blocked sources stay blocked. Metadata-only registration, unofficial mirrors and synthetic fixtures cannot satisfy official evidence.

## Task list

D5-01 — Freeze the Day 5 scope
Deliver a requirements-to-task map, exact base commit, catalogue boundaries and named detailed-source slices. Acceptance: every locked Day 5 requirement and both UAT anchors are mapped; future-day exclusions and unresolved source decisions are explicit.

D5-02 — Verify official authorities and applicability
Record official authority names, historical aliases, syllabus notices, textbook editions and academic applicability. Acceptance: current and historical records are distinguishable; unresolved/conflicting applicability cannot become active current-year curriculum.

D5-03 — Build the official-source manifest
Add SCERT and Intermediate index/document entries with authority, curriculum, source class, class/year, medium, subject, applicability, URL and copyright/storage metadata. Acceptance: all required slices/inventories have entries; assessments/indexes are not mislabeled detailed syllabus evidence.

D5-04 — Reuse the Day 3/4 ingestion lifecycle
Use registration, revision, extraction, validation, approval, activation, audit and private storage. Acceptance: unchanged retrieval is idempotent; changed bytes create candidate/diff; fetching or normalization never silently changes active content.

D5-05 — Handle unavailable official material honestly
Persist exact failed document, official URL, reason, affected task and permitted manual-upload route. Acceptance: blocked required slices yield incomplete official report and nonzero verification; manual official documents undergo identical provenance/applicability checks.

D5-06 — Add separate versioned curriculum packs
Create SCERT and Intermediate packs through generic services, retaining framework linkage only where supported. Acceptance: independent identities/sources/versions survive DB round trips; no CBSE identity reuse or automatic NCF equivalence.

D5-07 — Model school class versus Intermediate year
Represent SCERT I–X and Intermediate First/Second Year explicitly. Acceptance: aliases resolve only within correct pack/version; First Year cannot silently become SCERT XI, and Second Year cannot become First Year.

D5-08 — Implement medium-aware identity and lookup
Retain official medium labels alongside normalized codes, version-scoped aliases and unknown/unverified states. Acceptance: English/Telugu do not overwrite; missing medium, bilingual title or language subject is not inferred to be instructional medium.

D5-09 — Ingest the SCERT catalogue
Parse selected I–X inventories into grade/medium/subject/book entries; ambiguous/shared applicability remains unresolved. Acceptance: every inventory row is accounted for, including unavailable resources and duplicates; only evidenced combinations materialize.

D5-10 — Ingest the Intermediate catalogue
Represent First/Second Year subjects/papers under verified versions with official names/codes. Acceptance: combined listings do not imply both-year applicability; IA/IB/IIA/IIB or revised labels stay distinct where evidence distinguishes them.

D5-11 — Preserve historical and revised mathematics identities
Record version-specific names/aliases, retirement/supersession and evidence-backed successor relations. Acceptance: historical Math IA remains queryable with original sources; current-year lookup returns evidenced current subject or unresolved result, never guessed alias.

D5-12 — Normalize the bounded detailed hierarchy
Populate named Subject → Unit/Chapter → Topic → Concept slices, retaining official headings/locators separately from derived metadata. Acceptance: no invented official labels; placeholders/derived concepts explicit; checked bytes/pages support required paths.

D5-13 — Establish the SCERT VIII science UAT foundation
Provide selected Physical Science and Biological Science paths with official book/part split and medium evidence. Acceptance: engineering queries traverse complete paths and return provenance; demonstrated chapters are separate from un-ingested remainder.

D5-14 — Establish the Intermediate UAT and year-separation foundation
Provide selected First/Second Year mathematics paths and preserve historical Math IA UAT. Acceptance: queries show both years, historical/current applicability and medium correctly; no question-generation success is claimed.

D5-15 — Reuse learning-outcome and competency mappings
Map bounded slices only where supported, retaining wording and direct/derived/partial/unresolved status. Acceptance: unsupported links unresolved; CBSE/NCERT mapping not automatically official Telangana mapping. Day 6 validators excluded.

D5-16 — Add evidence-backed cross-medium relationships
Link selected officially corresponding content with separate records/local labels. Acceptance: matching titles/numbers alone insufficient; missing/divergent/reordered chapters explicit; generated translations never official.

D5-17 — Enforce immutable exact-source provenance
Bind snapshots, nodes, mappings and relationships to correct revision/locator using shared guards. Acceptance: wrong/stale domain/class/year/medium/subject revision rejected for new active writes; historical bindings preserved.

D5-18 — Preserve syllabus/assessment separation
Classify model papers/exam schemes/assessment resources separately; reuse existing evidence structures only if needed. Acceptance: assessments cannot introduce syllabus membership or subject equivalence; no new examination-pattern subsystem.

D5-19 — Harden integrity and idempotency
Test deterministic IDs, duplicate siblings, missing parents, cross-version/year/medium parents, cycles and alias collisions. Acceptance: repeat ingestion preserves IDs/counts; collisions visible; new revision cannot mutate history.

D5-20 — Preserve approved active state during change
Demonstrate candidate change, review/activation and supersession for a Telangana slice. Acceptance: failed/unapproved changes preserve prior active curriculum; approved replacement retains historical queries/evidence.

D5-21 — Deliver internal retrieval and provenance queries
Reuse service/CLI patterns for pack/version/class-or-year/medium/subject paths, catalogue, aliases and historical retrieval. Acceptance: every dimension constrains lookup; missing/ambiguous dimensions return ambiguity rather than wrong default.

D5-22 — Produce honest coverage and aggregate acceptance
Report expected inventory entries, unique materialized catalogue entries, unresolved/shared/blocked items and detailed paths separately by pack/version/class-or-year/medium. Acceptance: snapshot-backed denominators reconcile; missing rows/empty scopes/zero denominators/missing required paths/double counts cannot pass; path counts derive from successful verification.

D5-23 — Preserve migration compatibility
Reuse schema where sufficient; necessary changes use new successor after 0009, issued migrations untouched. Acceptance: fresh/populated Day 4 upgrade, downgrade/re-upgrade, drift/failure rollback tested; IDs/audits/bindings preserved; unsafe lossy downgrade fails safely.

D5-24 — Build positive and adversarial Day 5 tests
Use distinctly synthetic draft/inactive fixtures and mocked failures. Acceptance: both packs/Intermediate years, I–X catalogue boundaries, two media, historical/current aliases, changed sources, rejected wrong scope, incomplete coverage and assessment contamination covered; synthetic passes cannot satisfy live official gate.

D5-25 — Add deterministic Founder verification
Provide isolated synthetic verifier and explicitly invoked live-official verifier using Day 4 conventions. Acceptance: exact revisions/checksums/pages, required paths, counts/blockers reported; required missing constituent exits nonzero; no application DB mutation by default.

D5-26 — Run full regression on exact candidate
Run backend suite, Ruff, mypy, domain/source/Day 4/Day 5 verification, frontend typecheck/build, migrations, PostgreSQL DDL compile and CI Compose/env/persistence smoke where available. Acceptance: applicable checks green on same revision; preserve 268-test Day 4 coverage plus new tests; distinguish DDL compile from live PostgreSQL.

D5-27 — Complete independent review and reproducible handoff
Deliver task-evidence map, code/test references, official-source report, exact commit/CI links, independent Codex findings/closure, reproduction commands and catalogue-only/unresolved limits. Acceptance: no blocker/major findings; evidence matches delivered revision; private/bulk copyrighted documents absent from public Git.

## Completion and stop gate
Required live official evidence, integrity tests, full regression and independent review must pass before Day 5 engineering-complete claim. Missing required source or unresolved current-versus-historical UAT identity remains named blocker or explicit user scope decision, never hidden by synthetic tests. Founder separately signs off completion. Stop before Day 6: no educational quality/policy validator engine, RAG/AnythingLLM, LangGraph, public API/final UI, question generation or expanded prerequisite intelligence.


## Additional approved tasks

D5-28 — Separate syllabus, textbook, learning-outcome, academic-standard, teacher-handbook, academic-calendar and assessment domains. Only governing syllabus/version evidence establishes curriculum membership or activation. Draft textbook evidence remains draft.

D5-29 — Preserve all media actually present, including Telugu, English, Urdu, Hindi, Kannada, Marathi, Tamil and Other Media; separate first/second-language role, subject language, instructional medium, bilingual status and Part 1/2.

D5-30 — Independently ingest Telangana-specific learning outcomes and academic standards with exact revision, grade/stage, subject, medium, version/status and locator. No automatic NCERT/NCF equivalence.

D5-31 — Preserve Intermediate General/Vocational family and source-backed course/group applicability. Catalogue presence never grants universal applicability.

D5-32 — Preserve original Indic/Urdu text losslessly; normalized/transliterated labels separate. Unicode corruption and canonical alias collisions fail review. Verify persistence round trips.

D5-33 — Private runtime bytes only; no bulk PDFs/textbooks in public Git or CI artifacts. Public evidence consists of metadata/checksums/short derived structures.

D5-34 — Generic second-pack architecture proof using shared CurriculumPack/source/alignment services. Board-specific parsers/data are allowed, board-specific branches in generic engines are not.

