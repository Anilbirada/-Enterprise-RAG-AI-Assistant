#!/usr/bin/env bash
set -e

echo "[INIT] Applying database migrations via Alembic..."
cd /app/backend
alembic upgrade head

echo "[INIT] Checking / Seeding default database entities..."
python scripts/seed_data.py
cd /app

echo "[INIT] Starting Enterprise RAG FastAPI server on port ${PORT:-8000}..."
exec uvicorn app.main:app --app-dir /app/backend --host 0.0.0.0 --port "${PORT:-8000}"
