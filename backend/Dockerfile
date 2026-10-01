FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system eduvijna && adduser --system --ingroup eduvijna eduvijna
COPY pyproject.toml ./
COPY app ./app
COPY tests ./tests
COPY migrations ./migrations
COPY alembic.ini ./
RUN pip install --no-cache-dir '.[dev]'
RUN mkdir -p /app/data && chown -R eduvijna:eduvijna /app

USER eduvijna
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
