FROM python:3.13.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends curl ffmpeg postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend /app/backend
COPY contracts /app/contracts
COPY fixtures /app/fixtures
RUN python -m pip install --upgrade "pip==26.0.1" \
    && python -m pip install /app/backend

RUN groupadd --system polyglot && useradd --system --gid polyglot --home /app polyglot \
    && mkdir -p /data/object-storage && chown -R polyglot:polyglot /data /app

USER polyglot
WORKDIR /app/backend
EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && python -m polyglot.bootstrap.pilot && uvicorn polyglot.interfaces.http.app:create_runtime_app --factory --host 0.0.0.0 --port 8000 --no-access-log"]
