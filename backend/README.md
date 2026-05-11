# internal-ai-search backend

This backend follows a phased roadmap. Implemented so far:

- **Step 1:** FastAPI bootstrap + PostgreSQL + pgvector health (`GET /health`, `GET /health/db`)
- **Step 2:** Ollama LLM health (`GET /health/llm`)
- **Step 3:** Ollama embedding health — test vector + 1024-dimension check (`GET /health/embedding`)
- **Step 4:** pgvector smoke test — embedding + temp table insert + cosine search (`GET /health/vector-db`)
- **Step 5:** Data source registrations — WebDAV-backed stores CRUD (`/api/data-sources`)
- **Step 6:** WebDAV connection probe — PROPFIND smoke test (`POST /api/data-sources/{id}/test-connection`)
- **Step 7:** WebDAV root listing — PROPFIND Depth:1 preview (`POST /api/data-sources/{id}/list-root`, no `files` table writes)

## Project structure

```text
backend/
├─ app/
│  ├─ main.py
│  ├─ core/
│  │  ├─ config.py
│  │  └─ security.py
│  ├─ db/
│  │  ├─ database.py
│  │  ├─ health.py
│  │  └─ vector_health.py
│  ├─ llm/
│  │  ├─ __init__.py
│  │  ├─ ollama_client.py
│  │  └─ health.py
│  ├─ embedding/
│  │  ├─ __init__.py
│  │  ├─ ollama_embedding_client.py
│  │  └─ health.py
│  ├─ webdav/
│  │  ├─ __init__.py
│  │  ├─ client.py
│  │  ├─ connection_test.py
│  │  └─ listing.py
│  ├─ api/
│  │  ├─ health.py
│  │  └─ data_sources.py
│  ├─ services/
│  │  ├─ __init__.py
│  │  └─ data_source_service.py
│  └─ schemas/
│     └─ data_source.py
├─ requirements.txt
├─ .env.example
└─ README.md
```

## 1) Setup

From the `backend` directory:

```bash
python -m venv .venv
```

### Windows (PowerShell)

```powershell
.venv\Scripts\Activate.ps1
```

### macOS/Linux

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## 2) Environment variables

Create `.env` from `.env.example` and fill values:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

### Database (Step 1)

- `SERVICE_NAME`
- `DB_HOST`
- `DB_PORT`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`

### Data source credential encryption (Step 5)

- `DATA_SOURCE_SECRET_KEY` — used with **cryptography Fernet** to encrypt `credential_secret_enc` before it is persisted. Use a randomly generated Fernet key (recommended)

  ```powershell
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```

  or supply any non-empty string (the backend derives a Fernet-compatible key via SHA-256 — convenient for development, weaker than a dedicated key). Rotate before production and **never** commit production keys.

### WebDAV probe & listing (Steps 6–7)

- `WEBDAV_TIMEOUT_SECONDS` — HTTP timeout (seconds) for `PROPFIND` during `POST /api/data-sources/{id}/test-connection` and `POST /api/data-sources/{id}/list-root`.

### Ollama (Step 2)

- `OLLAMA_BASE_URL` — default `http://localhost:11434`
- `OLLAMA_MODEL` — e.g. `gemma3` (matches tags like `gemma3:latest`)
- `OLLAMA_TIMEOUT_SECONDS` — HTTP timeout for Ollama calls (seconds)

### Embeddings (Step 3)

LLM (`OLLAMA_MODEL`, e.g. `gemma3`) and embedding model are **separate**. RAG/search will use the embedding model below.

Example `.env` fragment:

```env
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=bge-m3
EMBEDDING_DIMENSION=1024
EMBEDDING_TEST_TEXT=사내 지식 검색 시스템 임베딩 테스트 문장입니다.
EMBEDDING_TIMEOUT_SECONDS=20
```

- **`EMBEDDING_PROVIDER`:** currently only `ollama` is implemented.
- **`EMBEDDING_MODEL`:** Ollama model tag for embeddings (default `bge-m3`). Change when switching models (e.g. a **KURE-v1**-family model) as long as it still exposes **1024** dimensions for this project phase.
- **`EMBEDDING_DIMENSION`:** expected vector length for health check (**1024** for current roadmap: **bge-m3** or KURE-v1-class models). Mismatch returns JSON error; the API process does not exit.
- **`EMBEDDING_TEST_TEXT`:** sentence sent to Ollama for the probe call.
- **`EMBEDDING_TIMEOUT_SECONDS`:** HTTP timeout for embedding requests.

Ollama calls: primary **`POST /api/embed`** with `{"model", "input"}`; if no usable vector is returned, **`POST /api/embeddings`** with `{"model", "prompt"}` is tried as a fallback.

## 3) Ollama (Step 2)

**Ollama must be running** on the host/port in `OLLAMA_BASE_URL` for `GET /health/llm` to report success.

### Check installed models

```bash
ollama list
```

### Pull / run the configured model (example: gemma3)

```bash
ollama run gemma3
```

(Use the exact model name you installed; tags like `gemma3:latest` still match `OLLAMA_MODEL=gemma3`.)

### Pull embedding model (Step 3, example: bge-m3)

```bash
ollama pull bge-m3
```

If the embedding model is missing or Ollama is down, `GET /health/embedding` returns **`status: "error"` JSON**; the FastAPI app keeps running.

## 4) Run API

Working directory must be `backend` (so `app` package resolves):

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 5) Test endpoints

### GET /health

```bash
curl http://localhost:8000/health
```

Expected shape:

```json
{
  "status": "ok",
  "service": "internal-ai-search-backend"
}
```

### GET /health/db

```bash
curl http://localhost:8000/health/db
```

Expected response includes DB connection status, database name, user, PostgreSQL version, and pgvector status. If the DB is unreachable, the response is still JSON with `status: "error"` (the FastAPI process does not exit).

### GET /health/llm

```bash
curl http://localhost:8000/health/llm
```

- **Success:** `status` is `ok`, `ollama_reachable` and `model_available` are `true`, `available_models` lists names returned by Ollama’s `/api/tags`.
- **Ollama stopped / connection refused:** `status` is `error`, `ollama_reachable` is `false`, `available_models` is `[]`, and `error` explains the failure. **The API server keeps running**; only this endpoint returns an error payload.
- **Ollama up but configured model missing:** `ollama_reachable` is `true`, `model_available` is `false`, `available_models` lists other installed models, `message` indicates the configured model is not available.

Ollama is called only when this route is hit (not at app startup).

### GET /health/embedding

```bash
curl http://localhost:8000/health/embedding
```

- **Success:** `status` is `ok`, `actual_dimension` equals `expected_dimension` (default **1024**), `dimension_matched` is `true`, `test_text` echoes the configured probe sentence.
- **Failure (Ollama down / model missing / HTTP error):** `status` is `error`, `actual_dimension` is `null`, `message` is `Failed to generate embedding`, and `error` has details. The server stays up.
- **Dimension mismatch:** `actual_dimension` is set (e.g. `768`), `dimension_matched` is `false`, `message` is `Embedding dimension mismatch`.

Embedding checks run **only** when this endpoint is called (not at startup).

### GET /health/vector-db (Step 4)

```bash
curl http://localhost:8000/health/vector-db
```

End-to-end **smoke test**: the same Ollama embedding client as `GET /health/embedding` builds a **1024**-dim vector from `EMBEDDING_TEST_TEXT`, inserts it into a **`TEMP` table** `tmp_vector_health_check` with `embedding vector(1024)` and **`ON COMMIT DROP`** (no writes to `document_chunks` or other app tables), verifies size via `vector_dims` when available, then runs a **cosine-distance** ordering query and reports `top_similarity` as **`1 - (embedding <=> query)`** (identical vectors should be **≥ 0.999**).

The response includes **`schema_check`**: pgvector extension presence/version, whether `public.document_chunks` exists, whether `embedding` is a `vector` type, and declared dimension when `vector(1024)` is visible. If migrations are not applied yet, missing tables produce **`warnings`** in `schema_check`; the handler still completes the temp-table test when the DB connection works.

**Requirements for the happy path**

- **Ollama** running with **`ollama pull bge-m3`** (or another model matching `EMBEDDING_MODEL` that outputs **1024** dimensions).
- **PostgreSQL** reachable with **`DB_*`** from `.env`, **`vector`** extension enabled, and **`gen_random_uuid()`** available (PostgreSQL **13+** for built-in `gen_random_uuid()`).

**Recommended:** apply your real schema (including `document_chunks`) before relying on `schema_check` in production readiness reviews. This endpoint never inserts into `document_chunks`.

**Success example**

```json
{
  "status": "ok",
  "embedding_model": "bge-m3",
  "expected_dimension": 1024,
  "generated_dimension": 1024,
  "db_insert_success": true,
  "db_vector_dimension": 1024,
  "dimension_matched": true,
  "similarity_search_success": true,
  "top_similarity": 1.0,
  "test_text": "사내 지식 검색 시스템 임베딩 테스트 문장입니다.",
  "message": "pgvector insert/search smoke test is healthy",
  "schema_check": {
    "pgvector_enabled": true,
    "pgvector_version": "0.8.0",
    "document_chunks_exists": true,
    "document_chunks_embedding_is_vector": true,
    "document_chunks_embedding_dimension": 1024,
    "warnings": []
  }
}
```

**Failure examples**

- **Embedding failure** (Ollama down / model missing): `status` is `error`, `generated_dimension` is `null`, `message` is `Failed to generate embedding`, `schema_check` is `null`.
- **DB / pgvector failure:** `generated_dimension` may be `1024`, but `db_insert_success` is `false`, `message` is `Failed to insert/search vector in pgvector`, `error` has the DB exception text, `schema_check` included when gathered.
- **Dimension mismatch** (embedding length ≠ `EMBEDDING_DIMENSION`, or DB `vector_dims` ≠ expected): `status` is `error`, appropriate `message` / `error` strings.

If Ollama or PostgreSQL is unavailable, the FastAPI process **does not exit**; only this route returns JSON errors.

### Data sources — `/api/data-sources` (Step 5)

Minimal **registration API** for multiple storage backends connected over **WebDAV** (OwnCloud / Nextcloud are just `source_type` flavors; **GENERIC_WEBDAV** covers other servers). **`LOCAL_FOLDER` is stubbed**: you may create rows, responses may include **`warnings`** about limited support.

- **Credentials:** request field `credential_secret` (plain text password or app password). It is **encrypted at rest** in `credential_secret_enc` (**never** echoed in responses). Responses expose only **`has_credential: bool`**.
- **Deactivate vs delete:** `PATCH .../deactivate` sets **`is_active = false`**. Rows are retained so linked `files` / `document_chunks` (later) remain referentially safe.
- **No connectivity tests:** this milestone does **not** call WebDAV (`PROPFIND`, etc.).
- **`PUT` credential rules:** omit `credential_secret` or send **`null`** to keep the saved secret; **`""`** returns **400**. When **`server_url` or `webdav_root_path` changes**, the response may include a **`warnings`** array with a relocation hint.

Supported `source_type` values:

- **`OWNCLOUD`**
- **`NEXTCLOUD`**
- **`GENERIC_WEBDAV`**
- **`LOCAL_FOLDER`** *(stub)*

Recommended: apply migrations so `public.data_sources` (and enums) exist before exercising these endpoints.

Examples (PowerShell / `curl` on Windows):

```powershell
curl -X POST http://localhost:8000/api/data-sources -H "Content-Type: application/json" -d '{\"name\":\"사내 문서함\",\"source_type\":\"OWNCLOUD\",\"server_url\":\"https://cloud.company.com\",\"webdav_root_path\":\"/remote.php/dav/files/admin\",\"username\":\"admin\",\"credential_secret\":\"app-password\",\"description\":\"사내 전체 공개 문서 저장소\",\"is_active\":true}'
curl http://localhost:8000/api/data-sources
curl http://localhost:8000/api/data-sources/{id}
curl -X PUT http://localhost:8000/api/data-sources/{id} -H "Content-Type: application/json" -d '{"name":"사내 문서함","server_url":"https://cloud.company.com"}'
curl -X PATCH http://localhost:8000/api/data-sources/{id}/deactivate
curl -X PATCH http://localhost:8000/api/data-sources/{id}/activate
```

### WebDAV connection test (`POST /api/data-sources/{id}/test-connection`, Step 6)

After registering a WebDAV-compatible source (`OWNCLOUD`, `NEXTCLOUD`, or `GENERIC_WEBDAV`), call this endpoint to verify **credentials and root path** with a single **`PROPFIND`**, **`Depth: 0`**, **`application/xml`** body against `server_url` + `webdav_root_path` (query strings are never appended). **`LOCAL_FOLDER` returns HTTP 400** with a structured JSON body and is intentionally unsupported for now.

- **Authentication:** HTTP **Basic Auth** using the stored **`username`** and **decrypted** app password token from **`credential_secret_enc`**. Responses and logs must **never** include the plaintext secret, ciphertext, `Authorization`, or Bearer material; error strings are intentionally generic.
- **OwnCloud vs Nextcloud vs generic:** the same DAV client runs for all supported `source_type` values.
- **App passwords:** for cloud products, configure an application-specific password rather than sharing the principal password when possible.
- **Scope:** verifies the **root URI** responds as WebDAV (**HTTP 207** typically, **200** also accepted); **no recursion**, **no** `files` table rows, downloads, embeddings, chunking, or search.
- **Persistence:** updates `last_connection_test_at`, `last_connection_success`, `last_connection_message`, and `updated_at` after each attempt (**including failures**).
- **`root_info`:** extracted from DAV XML where possible; if XML cannot be interpreted but HTTP succeeded, **`warnings`** may include `"Connected successfully, but failed to parse WebDAV XML response"` yet the test can still succeed.

```powershell
curl -X POST http://localhost:8000/api/data-sources/{id}/test-connection
```

See OpenAPI `/docs` for the response shape.

### WebDAV root listing (`POST /api/data-sources/{id}/list-root`, Step 7)

Returns **direct children only** under the configured `webdav_root_path` using **`PROPFIND`** with **`Depth: 1`**, **`Content-Type: application/xml`**, and the standard DAV propfind body (`displayname`, `getlastmodified`, `getetag`, `getcontentlength`, **`getcontenttype`**, **`resourcetype`**). **HTTP 207 Multi-Status** (or **200**) is parsed from `multistatus` / `response` elements with **namespace-safe** local-name matching.

- **No ingestion:** responses are **preview-only** — nothing is written to `files`, `document_chunks`, or embeddings. **`last_scan_at` is never updated** here.
- **Last connection:** on each call, **`last_connection_test_at`**, **`last_connection_success`**, **`last_connection_message`**, and **`updated_at`** may be refreshed (recommended on both success and failure). Success uses **`WebDAV root listing succeeded`** as the persisted message when the DAV round-trip and listing succeeded.
- **Query parameters**
  - **`limit`** (default **200**, max **5000**) — cap on returned `items`; if more entries exist after filtering, `truncated` is `true`, `warnings` includes `Result was truncated by limit=N`, and **`total_items`** reflects the full filtered count vs **`returned_items`**.
  - **`include_hidden`** (default **`false`**) — when `false`, drops preview-only hidden names (`.git`, `.svn`, `.env`, `.idea`, `.vscode`, and anything whose name starts with `.`). Formal exclusions will later follow `exclusion_policies`.
- **Items:** excludes the **root resource’s own** `response` (the first DAV entry matching the joined root path). **`remote_path`** is the path relative to `webdav_root_path`, always **`/`**-prefixed (no recursive paths in this milestone). **`href`** uses a **decoded** path (handles percent-encoding). **`last_modified`** is normalized to ISO-8601 when `getlastmodified` parses as RFC 2822/1123.
- **Auth & errors:** same rules as **`test-connection`** (Basic Auth, encrypted credential, `LOCAL_FOLDER` **400**, missing row **404**, no ciphertext or plaintext secrets or `Authorization` in responses/logs). Typical WebDAV failures return **HTTP 200** with `status: "error"` JSON (matching Step 6), except configuration problems (**400**) and unknown ids (**404**).

Example:

```bash
curl -X POST "http://localhost:8000/api/data-sources/{id}/list-root?limit=100&include_hidden=false"
```

## Notes

- Steps 1–7 wire health checks, pgvector smoke tests, credential-safe data-source CRUD, a **minimal** DAV probe, and **one-level** WebDAV previews — still **no** recursive crawl, ingestion, authenticated UI, RBAC, or RAG/search.
- Structure is kept small for later ingestion, delta sync, scheduling, Docker Compose packaging, React admin screens, and search APIs.
