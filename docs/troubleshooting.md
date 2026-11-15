# Troubleshooting & FAQ Guide

Common issues and solutions when running the **Enterprise RAG AI Assistant**.

---

## 1. Database Connection Issues

### Issue: `psql: error: connection to server at "127.0.0.1", port 5434 failed: Connection refused`
- **Cause**: PostgreSQL daemon is not running on the designated port.
- **Solution**:
  - Verify PostgreSQL service status:
    ```powershell
    pg_ctl status -D <path_to_data_dir>
    ```
  - Start the PostgreSQL daemon:
    ```powershell
    postgres -D <path_to_data_dir> -p 5434
    ```

### Issue: `type "vector" does not exist`
- **Cause**: The `pgvector` extension is not enabled in the database.
- **Solution**:
  Connect as superuser and execute:
  ```sql
  CREATE EXTENSION IF NOT EXISTS vector;
  ```

---

## 2. Ingestion Pipeline & Chunks

### Issue: Assistant replies *"I cannot find sufficient information in the provided corporate documents"*
- **Checks**:
  1. Verify document status in the Document Library (`/documents`). Status must be `COMPLETED`.
  2. If status is `UPLOADED`, ensure the backend server was running when the upload completed so the background ingestion worker (`BackgroundTasks`) can process the document.
  3. Inspect `document_chunks` table:
     ```sql
     SELECT count(*) FROM document_chunks;
     ```
  4. Ensure the uploaded PDF is not an image-only scan without an OCR layer. The system uses PyMuPDF layout-aware text extraction which requires extractable text streams.

---

## 3. Frontend & Build

### Issue: `Zone Allocation failed - process out of memory` during `npm run build`
- **Cause**: Node.js default V8 heap allocation exceeded on Windows during TypeScript compilation.
- **Solution**:
  Increase heap space:
  ```powershell
  $env:NODE_OPTIONS="--max-old-space-size=4096"
  npm run build
  ```

### Issue: `Cannot connect to API` or CORS errors
- **Cause**: Vite development proxy or backend CORS mismatch.
- **Solution**:
  - Ensure backend is running on `http://127.0.0.1:8000`.
  - Check `frontend/vite.config.ts` has the `/api` proxy target configured for `http://localhost:8000`.
  - Verify `CORS_ORIGINS` in `.env` includes `http://localhost:3000`.

---

## 4. Authentication & Multi-Tenancy

### Issue: `401 Unauthorized: Invalid credentials or organization slug`
- **Cause**: The email does not belong to the organization specified by the slug.
- **Solution**:
  - Verify organization slug. For demo accounts, use `acme-corp`.
  - For admin account, use `admin@acme.com` and `Password123!`.
  - Use the one-click **"Quick Fill Demo Accounts"** buttons on the login page.
