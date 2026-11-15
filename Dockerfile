# ==============================================================================
# Multi-Stage Production Dockerfile: Enterprise RAG AI Assistant
# Stage 1: Build React 18 + Vite TypeScript SPA
# Stage 2: Python 3.12 Slim Runtime + Dependencies + Unified Static Serving
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Frontend Build
# ------------------------------------------------------------------------------
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci --prefer-offline --no-audit

COPY frontend/ ./
RUN npm run build

# ------------------------------------------------------------------------------
# Stage 2: Final Production Runtime
# ------------------------------------------------------------------------------
FROM python:3.12-slim AS runner

# Install essential system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r ./backend/requirements.txt

# Copy backend source code and migrations
COPY backend ./backend

# Copy compiled frontend assets from Stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Ensure storage directory exists
RUN mkdir -p /app/storage_data

# Environment configuration
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    APP_ENV=production

# Copy entrypoint script
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
