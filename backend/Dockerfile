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
COPY .eduvijna/execution-state.yml ./.eduvijna/execution-state.yml
COPY .github/workflows/ci.yml ./.github/workflows/ci.yml
RUN pip install --no-cache-dir '.[dev]'
RUN mkdir -p /app/data && chown -R eduvijna:eduvijna /app

USER eduvijna
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
