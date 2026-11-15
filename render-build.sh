#!/usr/bin/env bash
# Render Build Script for Enterprise RAG AI Assistant
# Compiles backend dependencies and React frontend.
# NOTE: Database operations run in start.sh at runtime when Render internal network is active.
set -e

echo "=== [1/2] Installing Python Backend Dependencies ==="
python --version
python -m pip install --upgrade pip setuptools wheel
pip install -r backend/requirements.txt

echo "=== [2/2] Compiling React SPA Frontend ==="
cd frontend
if [ -f package-lock.json ]; then
  npm ci --prefer-offline --no-audit
else
  npm install --no-audit
fi
npm run build
cd ..

echo "=== Build Succeeded Successfully ==="
