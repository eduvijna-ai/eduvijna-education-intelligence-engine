# Day 13 — Founder localhost UAT runbook (Round 2/3)

**SHA:** `86a1fa36a95cf2d32cf1c17d89b17c667f311531`  
**UAT executed by Founder:** **NOT_RUN** (commands below validated by engineering in disposable localhost only).  
**No Day13 Creator UI** — generic React shell only; **no CUET/CLAT practice HTTP API** (`backend/app/api/router.py` → system routes under `/api/v1`).

## Prerequisites

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
export DATABASE_URL=sqlite:///./eduvijna_local.db   # or tmp file
export PATH="$PWD/.venv/bin:$PATH"                   # migration tests need `alembic` on PATH
python -m alembic -c alembic.ini upgrade head
```

Optional API: `uvicorn app.main:app --host 127.0.0.1 --port 8000` → `/health`, `/ready` only.

## `day13_verify` — authoritative JSON keys

Top-level keys from `backend/app/day13_verify.py` (use these names, not R1 typos):

| Key | Meaning |
|-----|---------|
| `math10` | CUET synthetic **10-question** practice allocation |
| `cuet_single_test_50` | CUET synthetic **50-question** single test |
| `clat_plan_summary` | CLAT **120-question** structural plan (ranges + clusters; reference demo) |
| `validated_clat_original_passage_examples` | F03-B **harness** validated original passage examples (`build_validated_clat_original_passage_examples`) |
| `clat_current_affairs_evidence_preflight` | F04-A CA/GK preflight (synthetic fixture only; official **NOT_READY**) |
| `cuet_reference_curator_approved` | Always **false** until NTA bytes + curator |
| `clat_official_curator_approved` | Always **false** until Consortium bytes + curator |
| `validated_persisted_synthetic` | F03-A harness pool (synthetic arithmetic; **not** official CUET) |
| `source_registry` | Manifest URLs; **SOURCE_PENDING** rights |

### Working commands (validated @ R2)

```bash
cd backend
# Full report
python -m app.day13_verify --json | python -m json.tool

# CUET 10 — synthetic only
python -m app.day13_verify --json | python -c "import json,sys; d=json.load(sys.stdin); m=d['math10']; print(m['verdict'], m.get('delivered_count'))"

# CUET 50 — synthetic only
python -m app.day13_verify --json | python -c "import json,sys; d=json.load(sys.stdin); s=d['cuet_single_test_50']; print(s['verdict'], s.get('question_count'))"

# CLAT 120 structural plan — reference demo, NOT official replica
python -m app.day13_verify --json | python -c "import json,sys; d=json.load(sys.stdin); p=d['clat_plan_summary']; print(p['verdict'], p['total_questions'], p.get('demonstration_only'))"

# Passage examples — F03-B harness (NOT legacy copyright_passages 120 planner text)
python -m app.day13_verify --json | python -c "import json,sys; d=json.load(sys.stdin); v=d['validated_clat_original_passage_examples']; print(v['verdict'], v['passage_count'], v.get('harness_only'))"

# CA/GK — synthetic preflight only; official_verified false
python -m app.day13_verify --json | python -c "import json,sys; d=json.load(sys.stdin); c=d['clat_current_affairs_evidence_preflight']; print(c)"
```

**Expected @ synthetic mode:** `math10` / `cuet_single_test_50` / `clat_plan_summary` → `pass` with counts **10 / 50 / 120**; curator flags **false**; `clat_current_affairs_evidence_preflight.official_verified` **false**.

**Official CUET 10/50 and CLAT 120 with curator/source-attested items:** **NOT_READY / SOURCE_PENDING** — not available in localhost without external curator action.

## Passage libraries — do not conflate

| Module | Role | Founder expectation |
|--------|------|---------------------|
| `copyright_passages.py` | Short **legacy structural** originals used in `ClatPaperPlanner` 120 demo | Reference-only reading clusters |
| `clat_original_passages.py` + `clat_validated_passage_service.py` | F03-B **authored synthetic examples** with harness token | `validated_clat_original_passage_examples` in verifier — **STOPPED** for production issuance |

## Scenario matrix

| # | Scenario | Command | Synthetic expectation | Official |
|---|---|---|---|---|
| UAT-01 | CUET Math 10 | `day13_verify` → `math10` | `pass`, count 10 | **NOT_READY** |
| UAT-02 | CUET Math 50 | → `cuet_single_test_50` | `pass`, count 50 | **NOT_READY** |
| UAT-03 | Wrong CUET year 2027 | `pytest tests/test_day13_f01_f02_repair.py -k 2027 -q` | Fail-closed | Isolation check |
| UAT-04 | Wrong medium | `pytest tests/test_day13_f01_f02_repair.py -k urdu -q` | Typed non-PASS | D13-10 gap |
| UAT-05 | CLAT 120 plan | → `clat_plan_summary` | 120, `demonstration_only` | **NOT_READY** |
| UAT-06 | Section ranges | `clat_plan_summary.section_allocations` + `constants.CLAT_SECTION_RANGES` | Approximate demo | Not exact official quotas |
| UAT-07 | Original passages (harness) | → `validated_clat_original_passage_examples` | Harness verdict | F03-B **STOP** |
| UAT-08 | Current affairs | → `clat_current_affairs_evidence_preflight` | Synthetic mechanics only | **SOURCE_PENDING** |
| UAT-09 | Tenant / replay | `pytest tests/test_day13_f03a_iter3.py tests/test_day13_d31a_durable_replay.py -q` | Typed isolation | No production auth |
| UAT-10 | Source gates | `cuet_reference_curator_approved`, `clat_official_curator_approved` in JSON | **false** | Curator action |
| UAT-11 | Persisted CUET pool | `pytest tests/test_day13_f03a_persisted.py -q` | Harness token required | F03-A **STOP** |

## Explicit non-goals

- **Do not** mark PR “Ready for review” or claim **Compose PASS** without Founder decision (Draft remains; compose-smoke **SKIPPED**).
- No Day12 #35 private intake, no official PDF activation, no AnythingLLM live calls.
- No `founder_approval` change; Day14 stays **LOCKED**.

## Related

- [D13-CLOSEOUT-REGRESSION-R2.md](./D13-CLOSEOUT-REGRESSION-R2.md)  
- [D13-FOUNDER-DECISION-PACKET.md](./D13-FOUNDER-DECISION-PACKET.md)