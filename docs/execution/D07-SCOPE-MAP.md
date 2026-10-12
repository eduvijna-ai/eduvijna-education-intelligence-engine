# D7-01 — Day 7 scope map (authoritative PR handoff)

Authoritative spec: `D07-KNOWLEDGE-INTELLIGENCE-ANYTHINGLLM.md`.

| ID | Requirement | Code / tests / evidence |
| --- | --- | --- |
| D7-01 | Freeze scope map | This document + PR checklist |
| D7-02 | Knowledge Intelligence package | `backend/app/knowledge_intelligence/` |
| D7-03 | AnythingLLM adapter protocol | `backend/app/adapters/anythingllm/protocol.py` |
| D7-04 | HTTP adapter | `backend/app/adapters/anythingllm/http_adapter.py` |
| D7-05 | Fake adapter | `backend/app/adapters/anythingllm/fake_adapter.py` |
| D7-06 | Availability semantics | `backend/app/adapters/anythingllm/types.py` |
| D7-07 | Versioned retrieval profile | `backend/app/knowledge_intelligence/retrieval_profile.py` |
| D7-08 | Source binding model | `backend/app/models/knowledge_intelligence.py` |
| D7-09 | ACTIVE eligibility gate | `backend/app/knowledge_intelligence/eligibility.py` |
| D7-10 | Ownership / isolation | `backend/app/knowledge_intelligence/scope.py` |
| D7-11 | Workspace resolution | `backend/app/knowledge_intelligence/workspace.py` |
| D7-12 | Safe payload preparation | `backend/app/knowledge_intelligence/payload.py` |
| D7-13 | Prompt-injection boundary | `backend/app/knowledge_intelligence/payload.py`, contracts |
| D7-14 | Idempotent indexing | `backend/app/knowledge_intelligence/indexing.py` |
| D7-15 | Supersession | `backend/app/knowledge_intelligence/indexing.py` |
| D7-16 | Retirement | `backend/app/knowledge_intelligence/indexing.py` |
| D7-17 | Retrieval request contract | `backend/app/knowledge_intelligence/contracts.py` |
| D7-18 | Scope filter compiler | `backend/app/knowledge_intelligence/retrieval.py` |
| D7-19 | Cross-tenant isolation | `backend/app/knowledge_intelligence/retrieval.py`, adversarial tests |
| D7-20 | Authority normalization | `backend/app/knowledge_intelligence/retrieval.py` |
| D7-21 | SourceRevision validation | `backend/app/knowledge_intelligence/retrieval.py` |
| D7-22 | Deduplication | `backend/app/knowledge_intelligence/retrieval.py` |
| D7-23 | Score / rank semantics | `backend/app/knowledge_intelligence/contracts.py` |
| D7-24 | Context pack builder | `backend/app/knowledge_intelligence/context_pack.py` |
| D7-25 | Context budget | `backend/app/knowledge_intelligence/context_pack.py` |
| D7-26 | Citation formatter | `backend/app/knowledge_intelligence/context_pack.py` |
| D7-27 | Retrieval audit | `backend/app/knowledge_intelligence/audit.py` |
| D7-28 | Failure / retry | adapter + indexing retry policy |
| D7-29 | Internal CLI | `backend/app/knowledge_cli.py` |
| D7-30 | Positive fixtures | `backend/app/knowledge_intelligence/fixtures.py` |
| D7-31 | Adversarial fixtures | fixtures + `tests/test_day7_*.py` |
| D7-32 | SQLite / PostgreSQL | models + migration |
| D7-33 | Migration safety | `backend/migrations/versions/20261012_0011_day7_knowledge_intelligence.py` |
| D7-34 | Targeted Day 7 test gate | `tests/test_day7*.py`, CI workflow |
| D7-35 | Founder verifier | `backend/app/day7_verify.py` |
| D7-36 | Final acceptance gate | PR Ready for Review + full regression (Founder) |

## Explicit exclusions (no Day 8+ leakage)

- No LangGraph orchestration (`app/graphs/`, agent graphs).
- No question authoring or generation engines.
- No new public REST/MCP knowledge endpoints (Day 17).
- No learner adaptation or exam planner logic.
- AnythingLLM remains the only AI/RAG gateway; no direct embedding/vector/provider calls in business services.
