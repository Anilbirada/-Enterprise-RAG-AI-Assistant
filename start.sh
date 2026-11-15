#!/usr/bin/env bash
# Startup script for Render Web Service
# Runs database migrations and seeding at container runtime (when private network is connected),
# then starts the Uvicorn web server.
set -e

echo "=== [1/2] Running Alembic Database Migrations ==="
cd backend
alembic upgrade head

echo "=== [2/2] Idempotent Database Seeding ==="
python scripts/seed_data.py
cd ..

echo "=== Starting Enterprise RAG FastAPI Server on port ${PORT:-8000} ==="
exec uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port "${PORT:-8000}"
