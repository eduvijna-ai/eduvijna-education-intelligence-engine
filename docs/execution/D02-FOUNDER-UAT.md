# D02 Founder Acceptance — Canonical Domain Model

Day 3 remains locked until the Founder approves this gate.

## 1. Start the local stack

```bash
docker compose up --build -d
```

Expected: backend and frontend become healthy.

## 2. Confirm D02 model metadata endpoint

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

## 3. Run the synthetic domain verification

```bash
docker compose exec backend python -m app.domain_verify
```

Expected JSON contains all of the following synthetic structures:

- curriculum pack + academic version;
- concept + prerequisite;
- learning outcome + competency;
- generic exam pack + version;
- exact-count rule;
- range-count rule;
- question with diagnostic distractor metadata;
- source provenance;
- test definition;
- institution policy override.

No real CBSE/JEE/etc. content is expected on D02.

## 4. Run full tests

```bash
make test
```

Expected:

- backend tests pass;
- frontend typecheck/build pass;
- Alembic D02 -> D01 downgrade and D01 -> D02 re-upgrade pass.

## 5. Inspect migration state

```bash
docker compose exec backend alembic current
```

Expected head:

```text
20261001_0002
```

Then optionally verify rollback:

```bash
docker compose exec backend alembic downgrade 20261001_0001
docker compose exec backend alembic upgrade head
```

Both commands must succeed.

## 6. Confirm scope discipline

D02 must contain domain contracts only.

It must **not** contain:

- source URL/PDF ingestion;
- AnythingLLM retrieval;
- exam-specific JEE/CUET/CLAT rules;
- question generation;
- learner attempts/mastery;
- Day-3 source activation logic.

## Founder response

If all checks pass:

`APPROVE DAY 2`

If a check fails:

`REJECT DAY 2` plus the failing step and observed result.
