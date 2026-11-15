# Contributing to Enterprise RAG AI Assistant

Thank you for your interest in contributing to the **Enterprise RAG AI Assistant** project! We welcome contributions to improve features, performance, security, and documentation.

---

## 1. Code of Conduct

We are committed to providing a welcoming, inclusive, and harassment-free environment for all contributors. Please treat everyone with dignity, empathy, and professional courtesy.

---

## 2. Development Workflow

1. **Fork the Repository**:
   Click "Fork" on GitHub and clone your fork locally:
   ```bash
   git clone https://github.com/<your-username>/-Enterprise-RAG-AI-Assistant.git
   cd -Enterprise-RAG-AI-Assistant
   ```

2. **Create a Feature Branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Backend Setup**:
   ```bash
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1   # Windows PowerShell
   # source .venv/bin/activate    # Linux / macOS
   pip install -r backend/requirements.txt
   ```

4. **Frontend Setup**:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

5. **Run Database Migrations**:
   ```bash
   cd backend
   alembic upgrade head
   ```

---

## 3. Coding Standards & Conventions

- **Python (Backend)**:
  - Adhere to **PEP 8** style guide.
  - Type annotations are required for all function arguments and return types.
  - Async/await conventions must be preserved across database queries and I/O operations.
  - Multi-tenant isolation must be enforced with explicit `organization_id` filters and PostgreSQL Row Level Security (RLS).
  - Never commit hardcoded credentials, JWT secrets, or API keys.

- **TypeScript / React (Frontend)**:
  - Strictly typed components and interfaces (`strict: true` in `tsconfig.json`).
  - Use Tailwind CSS utility classes; avoid inline styles.
  - Ensure zero TypeScript compiler errors before submitting (`npm run build`).

---

## 4. Testing Requirements

All contributions must include unit or integration test coverage:
```bash
# Run backend test suite
pytest -c backend/pytest.ini backend/tests --cov=backend/app

# Run evaluation benchmark
python -m app.evaluation.cli
```

- New features should maintain or increase the project's **85%+ code coverage**.
- All tests must pass cleanly before opening a Pull Request.

---

## 5. Submitting a Pull Request

1. Commit your changes with clear, descriptive commit messages adhering to [Conventional Commits](https://www.conventionalcommits.org/):
   ```bash
   git commit -m "feat(retrieval): implement dynamic dense/sparse weight tuning"
   ```
2. Push your feature branch:
   ```bash
   git push origin feature/your-feature-name
   ```
3. Open a Pull Request against the `main` branch. Provide a comprehensive description of the problem solved, architectural considerations, and test verification output.
