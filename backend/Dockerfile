FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EDUVIJNA_EXECUTION_STATE_PATH=/app/.eduvijna/execution-state.yml

WORKDIR /app

RUN addgroup --system eduvijna && adduser --system --ingroup eduvijna eduvijna
COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY backend/tests ./tests
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./
COPY content/curricula ./content/curricula
COPY docs/execution/D06-EDUCATION-INTELLIGENCE-VALIDATORS.md ./docs/execution/D06-EDUCATION-INTELLIGENCE-VALIDATORS.md
COPY docs/execution/D07-KNOWLEDGE-INTELLIGENCE-ANYTHINGLLM.md ./docs/execution/D07-KNOWLEDGE-INTELLIGENCE-ANYTHINGLLM.md
COPY docs/execution/D12-SCOPE-MAP.md ./docs/execution/D12-SCOPE-MAP.md
COPY docs/execution/D13-SCOPE-MAP.md ./docs/execution/D13-SCOPE-MAP.md
COPY .eduvijna/execution-state.yml ./.eduvijna/execution-state.yml
COPY .github/workflows/ci.yml ./.github/workflows/ci.yml
RUN pip install --no-cache-dir '.[dev]'
ARG EDUVIJNA_BUILD_REVISION=
RUN if [ -n "${EDUVIJNA_BUILD_REVISION}" ]; then \
      printf '%s' "${EDUVIJNA_BUILD_REVISION}" > /app/.eduvijna/build-revision && \
      chmod 444 /app/.eduvijna/build-revision; \
    fi
RUN mkdir -p /app/data && chown -R eduvijna:eduvijna /app

USER eduvijna
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
