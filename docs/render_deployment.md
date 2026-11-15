# Deploying Enterprise RAG AI Assistant to Render

This comprehensive guide walks you through deploying the **Enterprise RAG AI Assistant** onto [Render](https://render.com) using either the automated **Render Blueprint (Infrastructure-as-Code)** or the **Render Web Dashboard**.

---

## 🏗️ Architecture Overview on Render

The platform is designed to deploy cleanly on Render using a **unified full-stack web service** and a **managed PostgreSQL database with `pgvector`**:

```mermaid
flowchart TD
    Client["User Browser (Desktop/Mobile)"]
    RenderRouter["Render Edge Router & SSL Termination (HTTPS)"]
    WebService["Render Web Service (FastAPI + React SPA)"]
    Postgres["Render Managed PostgreSQL (v16 + pgvector)"]
    OpenAI["OpenAI API (text-embedding-3-small & gpt-4o-mini)"]

    Client -->|HTTPS / WSS| RenderRouter
    RenderRouter --> WebService
    WebService -->|SQLAlchemy AsyncPG Pool| Postgres
    WebService -->|REST / SSE Streaming| OpenAI
    WebService -->|Serves Compiled React 18 Assets| Client
```

### Key Highlights
- **Single-Service Full Stack:** FastAPI serves `/api/v1/*` routes while concurrently serving the pre-compiled React 18 SPA (`/`) with client-side routing fallback. Zero CORS issues and minimum latency.
- **Automated Database Lifecycle:** `render-build.sh` automatically runs `alembic upgrade head` (enabling `pgvector` and creating all business tables) and runs idempotent seeders (`seed_data.py`).
- **Free / Starter Tier Friendly:** Only **1 Web Service** and **1 PostgreSQL Database** are required.

---

## 🚀 Method 1: Deploy with Render Blueprint (Recommended)

Render Blueprints allow you to provision your entire cloud infrastructure using the included `render.yaml` file in this repository.

### Step 1: Push Repository to GitHub
Ensure you have pushed all your latest commits to your GitHub repository:
```bash
git push origin main
```

### Step 2: Create Blueprint on Render
1. Log in to [dashboard.render.com](https://dashboard.render.com).
2. Click the **"New +"** button in the top navigation bar and select **"Blueprint"**.
3. Connect your GitHub account and select the **`-Enterprise-RAG-AI-Assistant`** repository.
4. Render will parse `render.yaml` and display the resources to be created:
   - **Database:** `enterprise-rag-db` (PostgreSQL 16)
   - **Web Service:** `enterprise-rag-ai-assistant` (Python runtime with unified React SPA)
5. In the **Environment Variables** prompt, provide your `OPENAI_API_KEY`:
   - `OPENAI_API_KEY`: `sk-proj-...`
6. Click **"Apply"**.

Render will provision the database, install all Python and Node.js dependencies, compile the frontend, run database migrations, seed default demo accounts, and launch the service!

---

## 🛠️ Method 2: Manual Dashboard Setup

If you prefer to configure services manually via the Render web UI:

### Step 1: Create Managed PostgreSQL Database
1. Go to **Dashboard** -> **New +** -> **PostgreSQL**.
2. Configure:
   - **Name:** `enterprise-rag-db`
   - **Database Name:** `enterprise_rag`
   - **User:** `postgres`
   - **Region:** `Oregon (US West)` (or closest to your users)
   - **PostgreSQL Version:** `16`
   - **Plan:** `Free` (or `Starter` for production)
3. Click **Create Database**.
4. Once created, copy the **Internal Database URL** (e.g. `postgres://postgres:...@dpg-...-a.oregon-postgres.render.com/enterprise_rag`).

---

### Step 2: Create Web Service
1. Go to **Dashboard** -> **New +** -> **Web Service**.
2. Select your GitHub repository: `https://github.com/Anilbirada/-Enterprise-RAG-AI-Assistant`.
3. Configure settings:
   - **Name:** `enterprise-rag-ai-assistant`
   - **Region:** Same region as your database (`Oregon`)
   - **Branch:** `main`
   - **Runtime:** `Python 3`
   - **Build Command:**
     ```bash
     chmod +x render-build.sh && ./render-build.sh
     ```
   - **Start Command:**
     ```bash
     chmod +x start.sh && ./start.sh
     ```
   - **Health Check Path:** `/health`
   - **Plan:** `Free` or `Starter`

---

### Step 3: Configure Environment Variables
In the **Environment Variables** section of the Web Service, add:

| Variable Name | Value / Source | Description |
| :--- | :--- | :--- |
| `PYTHON_VERSION` | `3.11.9` | Prevents Python 3.14 pre-release compilation issues |
| `DATABASE_URL` | *Paste Internal Database URL from Step 1* | Render automatically handles asyncpg conversion |
| `OPENAI_API_KEY` | `sk-proj-...` | Required for embeddings & chat completions |
| `SECRET_KEY` | *(Click "Generate" or enter 32+ random characters)* | Cryptographic security signing |
| `JWT_SECRET_KEY` | *(Click "Generate" or enter 32+ random characters)* | JWT token signature |
| `APP_ENV` | `production` | Enables production security defaults |
| `STORAGE_PROVIDER` | `local` | Uploaded document storage |
| `LOG_LEVEL` | `INFO` | Application log verbosity |
| `CORS_ORIGINS` | `*` | Allowed client origins |

Click **"Create Web Service"**.

---

## ✅ Verifying Your Deployment

Once Render finishes deploying (marked by a green **"Live"** badge):

### 1. Check Container Health
Open your browser and navigate to:
```text
https://<your-service-name>.onrender.com/health
```
You should see:
```json
{"status": "healthy"}
```

### 2. Access the Web Application
Navigate to the root URL:
```text
https://<your-service-name>.onrender.com/
```
The React 18 Enterprise RAG application will load immediately.

### 3. Log In with Default Demo Credentials
The automated seeder pre-configures three role-based accounts:

| Role | Email | Password | Permissions |
| :--- | :--- | :--- | :--- |
| **Org Admin** | `admin@acme.com` | `Password123!` | Full admin access, audit logs, user management |
| **Knowledge Manager** | `km@acme.com` | `Password123!` | Upload, chunk, index, and manage documents |
| **Employee** | `employee@acme.com` | `Password123!` | Query assistant, view citations, interact with documents |

*(Tip: On the login screen, click any **"Quick Fill Demo Account"** button to automatically populate credentials).*

---

## 🔍 Troubleshooting Render Deployments

### 1. Database URL Protocol Mismatch
- **Issue:** SQLAlchemy async engine fails with `ValueError: invalid database scheme postgres://`.
- **Resolution:** The platform's configuration (`backend/app/core/config.py`) automatically detects `postgres://`, `postgresql://`, and converts them to `postgresql+asyncpg://` dynamically at runtime. No manual URL manipulation is necessary.

### 2. Free Tier Cold Starts
- **Issue:** On the Render Free plan, Web Services spin down after 15 minutes of inactivity. The first request after spin-down may take ~45–50 seconds to respond.
- **Resolution:** For zero cold starts, upgrade to Render's **Starter** plan ($7/mo) or configure an uptime monitor (e.g. [UptimeRobot](https://uptimerobot.com) pinging `/health` every 10 minutes).

### 3. Free Tier PostgreSQL Expiration
- **Issue:** Render Free PostgreSQL databases expire after 90 days.
- **Resolution:** For permanent production deployments, use Render's Starter Database ($7/mo) or connect an external managed PostgreSQL instance (e.g., Neon, Supabase, AWS RDS) by updating `DATABASE_URL`.

---

## 🛡️ Security Checklist for Production

- [x] Passwords hashed with **Argon2id** (`time_cost=3`, `memory_cost=64MB`).
- [x] Tenant context strictly verified via **Row-Level Security (RLS)**.
- [x] Session tokens rotated and revoked on logout.
- [x] Input files validated via magic byte detection (`python-magic`).
- [x] OpenAI API keys never stored in source code or database.
- [x] `SECRET_KEY` and `JWT_SECRET_KEY` generated with high-entropy randomness.
