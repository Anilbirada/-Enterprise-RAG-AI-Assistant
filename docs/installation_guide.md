# Installation & Setup Guide

This guide walks through setting up the **Enterprise RAG AI Assistant** locally on **Windows PowerShell** and **Linux/macOS**.

---

## 1. Prerequisites

- **Python**: Version `3.11` or `3.12`
- **Node.js**: Version `18+` or `20+` with `npm`
- **PostgreSQL**: Version `16+` with `pgvector 0.8.0+`
- **Git**

---

## 2. Clone the Repository

```bash
git clone https://github.com/Anilbirada/-Enterprise-RAG-AI-Assistant.git
cd -Enterprise-RAG-AI-Assistant
```

---

## 3. Backend Setup

### Windows PowerShell:
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r backend/requirements.txt
```

### Linux / macOS:
```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r backend/requirements.txt
```

---

## 4. Environment Configuration

Copy the example environment template to create `.env`:
```powershell
cp .env.example .env
```

Ensure your `.env` contains valid database credentials:
```env
APP_ENV=development
SECRET_KEY=enterprise-rag-super-secure-jwt-secret-key-at-least-32-chars-long
POSTGRES_SERVER=localhost
POSTGRES_PORT=5434
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=enterprise_rag_db
OPENAI_API_KEY=your-openai-api-key-here
```
> **Note:** If `OPENAI_API_KEY` is omitted, the application automatically uses deterministic offline mock embeddings and generation, allowing full local execution and testing without cost or internet connection.

---

## 5. Database Initialization & Migrations

```powershell
cd backend
alembic upgrade head
```

### Optional: Seed Initial Demo Accounts
```powershell
python scripts/seed_data.py
```
This seeds:
- **Organization:** `Acme Corporation` (Slug: `acme-corp`)
- **Admin User:** `admin@acme.com` / `Password123!`
- **Knowledge Manager:** `km@acme.com` / `Password123!`
- **Employee User:** `employee@acme.com` / `Password123!`

---

## 6. Frontend Setup

```powershell
cd ../frontend
npm install
```

---

## 7. Starting the Application

### Start the Backend Server:
```powershell
# In project root with active .venv:
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```
- API Docs: `http://localhost:8000/docs`
- Health Check: `http://localhost:8000/api/v1/health`

### Start the Frontend Dev Server:
```powershell
# In the frontend directory:
npm run dev
```
- Web Application: `http://localhost:3000`

---

## 8. Running the Automated Test Suite

```powershell
# From project root:
pytest -c backend/pytest.ini backend/tests --cov=backend/app --cov-report=term-missing
```
Expected output: **151 passed (86% coverage)**.
