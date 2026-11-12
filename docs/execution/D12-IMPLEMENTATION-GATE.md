# D12 Implementation Authority / Day11 Dependency Exception

**Founder authorization:** 2026-11-12 — “ok, approved Day 12 tasks list. so now provide cursor handoff to implement.” This approves **engineering implementation D12-01…D12-36** in [Issue #33](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/issues/33), NOT evidence-free D12-36 completion, merge, deployment or Day13 activation.

**Baseline:** New dedicated feature branch from `develop@1f7bff808cbddd979a9161823d42458a5d68eb88`. Existing Day11 [Draft PR #31](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/pull/31) at `d0f0745f6573bba0cfa93fa8eb0674cdd3b689d2` stays Draft/unmerged. Day11 holds: 13 PASS, 22 PARTIAL held, D11-36 pending. Issue #32 original NTA source gate stays OPEN.

## Explicit exception to ordinary next-day sequencing
The Founder authorized **Day12 implementation notwithstanding the outstanding Day11 source/production acceptance**. This is a **dependency exception**, not a Day11 acceptance, waiver, merge, or Day12 release gate. `day12_unlock:false` on Day11 is deliberate. This branch marks Day11 ON_HOLD and Day12 ACTIVE for builder work only; `founder_approval:false` still governs final signoff.

## Isolation and engineering strategy
- Work only on `feature/day12-jee-advanced-intelligence` against `develop`. Do not cherry-pick or depend on unmerged JEE Main Day11 logic; reuse merged Day2–10 canonical models and services (`ExamPack`, `ExamVersion`, `ExamSection`, `ExamBlueprintRule`, source lifecycle, Day6/7/8/9/10).
- If a generic paper planner abstraction is essential, implement the **smallest scoped generic extension** directly in the Day12 branch with its own migrations, tests and backward-compatibility checks. Never use JEE Main's synthetic fixtures as genuine JEE Advanced evidence.
- If truly impossible without importing unfinished Day11 PR #31, **STOP_WITH_NAMED_DEPENDENCY** and request a separate Founder-reviewed plan; do not force a merge or accidentally silently stack.
- Cursor builder must use **Composer 2.5 standard (not Fast)** with no usage-based overage, cloud-agent on-demand billing or second builder. One bounded final candidate / independent Chief AI Architect exact-HEAD review. Respect `.eduvijna/pytest-targets.txt` and the three-iteration CI repair circuit breaker.

## JEE Advanced examination authority and source boundary
- [Official JEE Advanced 2026 brochure](https://jeeadv.ac.in/documents/IBEnglish_2026.pdf) describes **two compulsory papers**, three hours each, Physics/Chemistry/Mathematics and paper-specific marking instructions; [official 2026 syllabus](https://jeeadv.ac.in/documents/jee-advanced-2026-syllabus.pdf), [2026 official exam site](https://jeeadv.ac.in/), [archive](https://jeeadv.ac.in/archive.html) provide discovery points.
- Authenticate original 2026 paper-specific instructions, question papers and final answer keys through the approved Source Intelligence PDF lifecycle before any production-style reference replica claim. Store immutable SHA/page locator/approved revision IDs and actual authorized curator audit. If unavailable, fail closed, use clearly labelled synthetic demonstration and report `SOURCE_PENDING`.
- **No verified official 2027 JEE Advanced pattern is authorized.** Do not assume 2026 paper structure, detailed scoring, count or distribution is the 2027 pattern.

## Acceptance protocol
- Freeze Day12 scope map across all 36 tasks, with task ID → implementation/test/original source evidence; maintain candid PASS/PARTIAL/SOURCE_PENDING.
- Preserve strict counts for subject/topic practice, source-verified Paper1/Paper2 version/rules, partial-score and multiple-answer validation, no duplicate items, safe durable replay and subject/tenant isolation.
- Run Ruff, Mypy, scoped impacted Days2–10 tests and Day12, SQLite Alembic and PostgreSQL DDL compile/static validation, Day12 exact SHA verifier and one full historical `pytest tests/` on final candidate; report Docker/AnythingLLM/live PostgreSQL as NOT RUN unless proven.
- Keep PR Draft/unmerged, Day12 `founder_approval:false`, Day13 LOCKED. Founder localhost/Docker all-days UAT remains deferred, not PASS. D12-36 requires **separate** Founder final acceptance.