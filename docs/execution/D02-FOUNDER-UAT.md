# Combined D01 + D02 Founder Acceptance

The Founder explicitly deferred D01 localhost UAT until D02 completion.

This acceptance sheet therefore verifies **both Day 1 Foundation and Day 2 Canonical Domain Model** in one local session.

Day 3 remains locked until both days are explicitly approved.

## 1. Start the local stack

```bash
make env
make dev
```

Expected: backend and frontend become healthy.

## 2. Verify D01 foundation

Open:

```text
http://localhost:5173
```

Expected:

- Eduvijna / Education Intelligence Engine is visible;
- Backend = Connected;
- Environment = local.

Open:

```text
http://localhost:8000/health
```

Expected:

```json
{"status":"ok"}
```

Open:

```text
http://localhost:8000/ready
```

Expected:

```json
{"status":"ready"}
```

Open:

```text
http://localhost:8000/docs
```

Expected: FastAPI OpenAPI UI loads.

## 3. Confirm D02 model metadata

Open:

```text
http://localhost:8000/api/v1/system/domain-model
```

Expected:

- `version` = `d02`;
- curriculum node types include `grade_year`, `medium`, `subject`, `unit`, `chapter`, `topic`, `concept`;
- question types include single-choice, multiple-choice, numerical, descriptive, passage-based and multi-part;
- source types include official and non-official provenance categories;
- diagnostic categories include concept/formula/calculation/misconception/application/reasoning/prerequisite gaps.

## 4. Run the synthetic D02 domain verification

```bash
docker compose exec backend python -m app.domain_verify
```

Expected JSON contains synthetic examples of:

- curriculum pack + academic version;
- hierarchy ending in concepts;
- concept prerequisite;
- learning outcome + competency;
- generic exam pack + version;
- exact-count rule;
- range-count rule;
- question + options + diagnostic metadata;
- source provenance;
- test definition;
- institution policy record.

No real CBSE/JEE/etc. content is expected on D02.

## 5. Run the full automated suite

```bash
make lint
make test
```

Expected:

- Ruff passes;
- mypy passes;
- backend pytest passes;
- frontend typecheck/build passes;
- D02 migration round trip passes.

## 6. Verify D01 persistence

Seed data if needed through the existing local stack, then stop without deleting volumes:

```bash
docker compose down
docker compose up -d
```

Do **not** use `docker compose down -v`.

Expected:

- `/ready` returns ready again;
- SQLite volume remains present;
- automated CI already verifies a real `SystemSetting` row is readable after this restart.

## 7. Inspect D02 migration state

```bash
docker compose exec backend alembic current
```

Expected:

```text
20261002_0004
```

Automated CI verifies the full migration chain and populated-data preservation. For a disposable
local UAT database only, verify head -> D01 -> head explicitly:

```bash
docker compose exec backend alembic downgrade 20261001_0001
docker compose exec backend alembic upgrade head
```

Both commands must succeed.

## 8. Confirm D02 integrity rules

The automated suite verifies:

- SQLite foreign keys are enabled;
- orphan FK rows are rejected;
- learners cannot reference a primary teacher from another institution;
- Admin/API-client institution references cannot cross organization boundaries;
- concept prerequisite edges persist correctly;
- concept self-reference/duplicates are rejected where applicable;
- curriculum root codes are unique per version;
- sibling codes are unique within version/parent scope regardless of node type;
- curriculum parents cannot cross CurriculumVersion boundaries;
- exam exact counts cannot contradict persisted min/max ranges;
- PostgreSQL dialect compilation succeeds without PostgreSQL-only canonical types;
- populated question options/assets/provenance/test membership survive migration upgrade/downgrade/re-upgrade;
- canonical question context/provenance, rubric and paper-blueprint schemas reject malformed inputs;
- backend credentials are not injected into the frontend container.

## 9. Confirm scope discipline

D02 must **not** contain:

- source URL/PDF ingestion;
- AnythingLLM retrieval;
- real exam-specific JEE/CUET/CLAT rules;
- question generation;
- learner attempts/mastery;
- Day-3 source activation logic.

## Founder response

If all combined checks pass, send both explicit approvals:

```text
APPROVE DAY 1
APPROVE DAY 2
```

If any check fails, send:

```text
REJECT DAY 1
```

or

```text
REJECT DAY 2
```

with the failing step and observed result.

**D03 remains locked until the combined Founder acceptance is complete.**
