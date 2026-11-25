# Day 17 — REST, Jobs, Auth and MCP scope ledger

**Status:** candidate 3/3 final — R3 bounded security closure (36 rows). D17-36 pending Founder signoff.  
**Specification:** [Issue #60](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/issues/60).  
**Branch:** `feature/day17-rest-jobs-auth-mcp` → `develop`. Base `9400ce13af13c13c5158fa06c90f7f2517abbe93`.

| ID | Task | Evidence | State | Notes |
|---|---|---|---|---|
| D17-01 | Scope and dependency freeze | `platform/governance.py`, `platform/dependency_closure.py`, `test_day17_governance.py` | PARTIAL | Founder exact-HEAD review pending |
| D17-02 | Capability readiness registry | `platform/capability_registry.py`, `test_day17_capability.py` | PARTIAL | Deny-by-default; no caller override |
| D17-03 | Shared application services | `platform/services/*`, REST/MCP/worker share | PARTIAL | Blocked paths centralized |
| D17-04 | Canonical contracts | `platform/schemas/*`, `extra=forbid` | PARTIAL | UUID strict on routes |
| D17-05 | Standard errors | `platform/errors.py`, `main.py` handler | PARTIAL | CAPABILITY_NOT_READY stable |
| D17-06 | OpenAPI | FastAPI route models + description | PARTIAL | Readiness documented |
| D17-07 | Application identity | `models/platform_auth.py`, tenancy ORM | PARTIAL | Teacher/admin principals |
| D17-08 | Application authentication | `platform/auth/service.py`, `session_epoch.py` | PARTIAL | F17-01 refresh rotation + logout epoch |
| D17-09 | API keys | `platform/auth/api_keys.py`, `delegation.py` | PARTIAL | F17-01 scope subset + api_keys:manage |
| D17-10 | RBAC | `platform/auth/rbac.py` | PARTIAL | Deny default matrix |
| D17-11 | Tenant isolation | `principal.py`, route checks | PARTIAL | Server-derived scope |
| D17-12 | Permission scopes | capability registry scopes | PARTIAL | Least privilege bundles |
| D17-13 | Security controls | `platform/security/limits.py` | PARTIAL | F17-06 streamed body + bounded rate buckets |
| D17-14 | Security audit | `platform/auth/audit.py` | PARTIAL | No credential payload |
| D17-15 | Curriculum/exam APIs | `services/curriculum.py`, routes | PARTIAL | No officiality inflation |
| D17-16 | Knowledge/source APIs | `services/knowledge.py` | BLOCKED | F17-05 fail-closed; no fake hits |
| D17-17 | Question generation API | `services/questions.py` | BLOCKED | CAPABILITY_NOT_READY |
| D17-18 | Question validation API | `services/questions.py` | BLOCKED | F17-05 explicit CAPABILITY_NOT_READY |
| D17-19 | Mock examination API | `services/questions.py` | BLOCKED | Day14 issuance containment |
| D17-20 | Learner APIs | `services/blocked.py`, routes | BLOCKED | Day15 ON_HOLD |
| D17-21 | Adaptive remediation APIs | `services/blocked.py` | BLOCKED | Day16 runtime disabled |
| D17-22 | Admin APIs | routes `admin/sources` | PARTIAL | Live intake disabled |
| D17-23 | Durable job model | `models/platform_jobs.py`, migration `0022` | PARTIAL | Additive migration |
| D17-24 | Submission/idempotency | `jobs/service.py`, migration `0023` | PARTIAL | F17-03 scoped idempotency + owner |
| D17-25 | Worker execution | `jobs/worker.py`, `synthetic.py` | PARTIAL | F17-04 CAS claim + internal fixture |
| D17-26 | Lifecycle/progress | `jobs/enums.py` | PARTIAL | Legal transitions table |
| D17-27 | Retry/recovery | `jobs/service.py` lease recovery | PARTIAL | F17-04 max_attempts + fence checks |
| D17-28 | Concurrency/transactions | `test_day17_jobs.py` | PARTIAL | SQLite FOR UPDATE tests |
| D17-29 | Status/cancel APIs | routes `/jobs` | PARTIAL | Tenant-scoped reads |
| D17-30 | Operations | `services/operations.py`, `/ready` | PARTIAL | No blocked provider calls |
| D17-31 | MCP foundation | `mcp/server.py`, `platform/mcp/auth.py` | PARTIAL | F17-02 credential-bound principal |
| D17-32 | MCP tools | `platform/mcp/tools.py` | PARTIAL | F17-02 no spoofed identity args |
| D17-33 | MCP resources/prompts | tool stubs | PARTIAL | No sensitive bypass |
| D17-34 | MCP security/parity | `test_day17_mcp.py` | PARTIAL | Blocked learner/remediation |
| D17-35 | Regression/verifier | `day17_verify.py`, `scope_ledger.py`, `test_day17_f17_security.py` | PARTIAL | F17-06 ledger loader + PG0021 NOT_RUN |
| D17-36 | Independent acceptance | This matrix | NOT_STARTED | Founder signoff pending |

## Dependency closure (explicit)

- Day11 PR31 ON_HOLD — not imported  
- Day12 live source intake DISABLED  
- Day13 PG migration 0021 BLOCKER — live PG verification NOT_RUN  
- Day14 academic validation + issuance DISABLED  
- Day15 PR57 ON_HOLD — learner processing blocked  
- Day16 runtime remediation DISABLED  
- Day18 LOCKED  