#!/usr/bin/env bash
# Render Build Script for Enterprise RAG AI Assistant
# Performs dependency installation, frontend compilation, database migrations, and data seeding.
set -e

echo "=== [1/4] Installing Python Backend Dependencies ==="
python --version
python -m pip install --upgrade pip setuptools wheel
pip install -r backend/requirements.txt

echo "=== [2/4] Compiling React SPA Frontend ==="
cd frontend
if [ -f package-lock.json ]; then
  npm ci --prefer-offline --no-audit
else
  npm install --no-audit
fi
npm run build
cd ..

echo "=== [3/4] Running Alembic Database Migrations ==="
cd backend
alembic upgrade head

echo "=== [4/4] Idempotent Database Seeding ==="
python scripts/seed_data.py
cd ..

echo "=== Build & Migration Succeeded Successfully ==="
