# internal-ai-search backend

This backend follows a phased roadmap. Implemented so far:

- **Step 1:** FastAPI bootstrap + PostgreSQL + pgvector health (`GET /health`, `GET /health/db`)
- **Step 2:** Ollama LLM health (`GET /health/llm`)
- **Step 3:** Ollama embedding health — test vector + 1024-dimension check (`GET /health/embedding`)
- **Step 4:** pgvector smoke test — embedding + temp table insert + cosine search (`GET /health/vector-db`)
- **Step 5:** Data source registrations — WebDAV-backed stores CRUD (`/api/data-sources`)
- **Step 6:** WebDAV connection probe — PROPFIND smoke test (`POST /api/data-sources/{id}/test-connection`)
- **Step 7:** WebDAV root listing — PROPFIND Depth:1 preview (`POST /api/data-sources/{id}/list-root`, no `files` table writes)
- **Step 8:** WebDAV root sync — upsert Depth:1 children into `files` (`POST /api/data-sources/{id}/sync-root`, no recursion / downloads / deletion detection)
- **Step 9:** File statistics — read-only aggregation over `files` (`GET /api/files/stats`, `GET /api/data-sources/{id}/file-stats`, SQL-side grouping only)
- **Step 10:** WebDAV recursive sync — bounded BFS over PROPFIND Depth:1 (`POST /api/data-sources/{id}/sync-tree`), upserts every visited item into `files` with `exclusion_policies` applied. No downloads / hashing / deletion detection.
- **Step 11:** Deletion detection (soft-mark) for `sync-tree` (`detect_deleted=true`) — rows missing from a complete, unfiltered walk are flipped to `analysis_status='DELETED'` inside the same transaction. No physical row deletion, no `document_chunks` touches.

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
│  │  ├─ listing.py
│  │  └─ recursive_listing.py
│  ├─ api/
│  │  ├─ health.py
│  │  ├─ data_sources.py
│  │  └─ files.py
│  ├─ services/
│  │  ├─ __init__.py
│  │  ├─ data_source_service.py
│  │  ├─ exclusion_policy_service.py
│  │  ├─ file_recursive_sync_service.py
│  │  ├─ file_stats_service.py
│  │  ├─ file_sync_service.py
│  │  ├─ files_deletion_service.py
│  │  ├─ files_upsert.py
│  │  └─ scan_jobs_service.py
│  ├─ utils/
│  │  ├─ __init__.py
│  │  └─ file_type.py
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

### WebDAV probe, listing, and sync (Steps 6–8, 10)

- `WEBDAV_TIMEOUT_SECONDS` — per-`PROPFIND` HTTP timeout (seconds). Applied to `test-connection`, `list-root`, `sync-root`, **and every per-folder PROPFIND during `sync-tree`** (each folder gets its own request).

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

### WebDAV root sync (`POST /api/data-sources/{id}/sync-root`, Step 8)

Persists **direct children only** under the configured `webdav_root_path` into the **`files`** table via **`PROPFIND`** + **`Depth: 1`** (same request shape as Step 7). One level only — there is **no recursion**, **no download**, **no body analysis**, **no chunking / embedding**, and **no deletion detection** in this milestone.

- **Upsert key:** **`(data_source_id, remote_path)`** — duplicates are prevented via the table's `UNIQUE` constraint and `INSERT ... ON CONFLICT ... DO UPDATE`. The endpoint distinguishes inserts vs updates using PostgreSQL's `xmax = 0` trick on the `RETURNING` row.
- **Field mapping** (from the WebDAV item → `files` column):
  `name → filename`, `extension`, `is_directory`, `size_bytes`, `etag`, `last_modified` (parsed from listing's ISO-8601 string), `content_type → mime_type`. `content_hash` and `last_indexed_at` are kept **`NULL`** at this stage.
- **`analysis_status` policy**
  - Directories → **`SKIPPED`** (folders are not analyzed).
  - Files (new rows) → **`PENDING`**.
  - Files (existing rows) → reset to **`PENDING`** only if **`etag`** or **`last_modified`** changed; otherwise the current status is preserved (e.g. `COMPLETED` stays `COMPLETED`).
- **Transactions:** the **entire upsert batch + the `data_sources` finalization** runs inside one transaction. Any failure rolls back the whole batch (no partial successes); `scan_jobs` is recorded as **`FAILED`** in that case.
- **`scan_jobs` (best-effort):** a `MANUAL_SCAN` row is inserted as **`RUNNING`** before the WebDAV fetch and finalized to **`COMPLETED`** / **`FAILED`** afterwards. `requested_by` is `NULL` (auth comes later). If the `scan_jobs` table or its enum types are not present yet, the column is silently skipped and the response shows `"scan_job_id": null`.
- **`data_sources` on success:** **`last_scan_at`**, **`last_connection_test_at`**, **`last_connection_success = TRUE`**, **`last_connection_message = "WebDAV root sync succeeded"`** (or **`"...succeeded with truncated result"`**), and **`updated_at`** are all set in the same transaction.
- **`data_sources` on failure:** `last_scan_at` is **not** touched; `last_connection_*` and `updated_at` reflect the failure summary.
- **Query parameters**
  - **`limit`** (default **1000**, max **10000**) — cap on items processed; if more entries exist, the response returns `truncated: true` and a warning `Result was truncated by limit=N`.
  - **`include_hidden`** (default **`false`**) — same hidden-name filter as Step 7 (`.git`, `.svn`, `.env`, `.idea`, `.vscode`, names starting with `.`). Formal exclusions will later follow `exclusion_policies`.
- **Out of scope:** WebDAV recursion, deletion / rename detection (existing rows missing from the listing are **not** marked `DELETED`), file downloads, content hashing, mime sniffing, chunking, embeddings, and `document_chunks` writes. Those move to later milestones.
- **Security:** identical to Steps 6–7 — `credential_secret`, `credential_secret_enc`, `Authorization`, and plaintext passwords are **never** logged or returned, including in error bodies.

```bash
curl -X POST "http://localhost:8000/api/data-sources/{id}/sync-root?limit=1000&include_hidden=false"
```

### File statistics (`GET /api/files/stats`, `GET /api/data-sources/{id}/file-stats`, Step 9)

Read-only dashboard endpoint that aggregates the **`files`** table. All counts and totals are computed in SQL using **`COUNT`**, **`SUM`**, and **`GROUP BY`** with **`FILTER (WHERE ...)`** clauses; the API never materializes the full row set in Python. The Top-N largest files use a single **`ORDER BY size_bytes DESC LIMIT 10`** query.

- **Scope**
  - **`data_source_id`** (query, optional) — restricts the aggregation to a single data source. When omitted, the response covers every data source and includes a **`by_data_source`** breakdown.
  - **`include_deleted`** (default **`false`**) — when `false`, rows with **`analysis_status = 'DELETED'`** are excluded from every section (summary, status, extension, file type, top files, per-source).
- **Sections**
  - **`summary`** — `total_items` (folders + files), `total_files`, `total_directories`, `total_size_bytes` (files only — folders carry `NULL` sizes), `total_size_human` (binary units, KB = 1024), `latest_modified_at` (max `last_modified` across rows in scope), `last_synced_at` (data source's `last_scan_at`, or the latest across all data sources when unscoped).
  - **`by_analysis_status`** — `[ { status, count } ]` over all in-scope rows (folders are **`SKIPPED`**, files cycle through `PENDING` → `PROCESSING` → `COMPLETED` / `FAILED`).
  - **`by_extension`** — files only (`is_directory = FALSE`); extension is lower-cased server-side, and rows with no extension are rendered as **`"(none)"`**. Each row carries the matching **`file_type`** label.
  - **`by_file_type`** — files only; rolled up by the file-type classification below.
  - **`top_largest_files`** — up to **10** files in scope, with `id`, `filename`, `remote_path`, `extension`, `size_bytes`, `size_human`, and `last_modified` (ISO-8601).
  - **`by_data_source`** *(only when `data_source_id` is omitted)* — one row per registered data source with `total_files`, `total_directories`, `total_size_bytes`, and the data source's `last_scan_at`.
- **File-type classification** (extension is normalized via `lower(trim(extension))`; empty/`NULL` ⇒ `UNKNOWN`):
  - **`DOCUMENT`** — `txt, md, markdown, pdf, doc, docx, hwp, hwpx, ppt, pptx, xls, xlsx, csv`
  - **`SOURCE_CODE`** — `py, java, kt, js, ts, tsx, jsx, c, cpp, h, hpp, cs, go, rs, php, rb, swift, sql, html, css, scss, vue`
  - **`CONFIG`** — `json, xml, yaml, yml, ini, conf, properties, env, toml`
  - **`LOG`** — `log`
  - **`ARCHIVE`** — `zip, 7z, rar, tar, gz, tgz`
  - **`IMAGE`** — `png, jpg, jpeg, gif, bmp, webp, svg, psd, ai`
  - **`AUDIO_VIDEO`** — `mp3, wav, mp4, avi, mov, mkv, webm`
  - **`BINARY`** — `exe, dll, so, dylib, class, jar, war, ear, bin, o, obj`
  - **`UNKNOWN`** — anything else (or no extension).

  The classification is owned by **`app/utils/file_type.py`**. The same constants drive the Python helper (`classify_extension`) and the SQL `CASE` (`FILE_TYPE_CASE_SQL`) so reports and DB aggregation stay in lock-step.
- **Convenience alias:** **`GET /api/data-sources/{id}/file-stats?include_deleted=false`** returns the same payload as **`GET /api/files/stats?data_source_id={id}`** and responds **404 `Data source not found`** when the id is unknown.
- **Out of scope:** this milestone never triggers a WebDAV call, recursion, download, body analysis, chunking, embedding, or deletion / move detection — it is purely a `files`-table read.

```bash
curl "http://localhost:8000/api/files/stats"
curl "http://localhost:8000/api/files/stats?data_source_id={id}"
curl "http://localhost:8000/api/files/stats?include_deleted=true"
curl "http://localhost:8000/api/data-sources/{id}/file-stats"
```

### WebDAV recursive sync (`POST /api/data-sources/{id}/sync-tree`, Step 10)

Bounded **BFS** over **`PROPFIND`** with **`Depth: 1`** per folder. Walks the tree below `webdav_root_path` (or below `start_path` when set), normalizes each item's path **relative to `webdav_root_path`**, applies the configured exclusions, and **upserts** every survivor into the **`files`** table in a single transaction. No content downloads, no hashing, no chunking, no embedding, no deletion detection in this milestone.

- **Query parameters**
  - **`start_path`** (default **`/`**) — path **relative to `webdav_root_path`**; e.g. `/`, `/project-a`, `/docs/sub`. Percent-encoded segment-by-segment before being appended to the WebDAV URL.
  - **`max_depth`** (default **`3`**, range **0–20**) — number of folder layers below `start_path` that are entered. With `max_depth=0` only direct children of `start_path` are recorded (equivalent to `sync-root` rooted at `start_path`).
  - **`max_items`** (default **`5000`**, max **`50000`**) — hard cap on the items collected before a transaction-time upsert. When reached, the response carries `truncated: true` and `Result was truncated by max_items=N` in `warnings`.
  - **`include_hidden`** (default **`false`**) — drops names beginning with `.` (covers `.git`, `.env`, `.svn`, `.idea`, `.vscode`, ...). Applied **regardless** of `apply_exclusions`.
  - **`apply_exclusions`** (default **`true`**) — when `false`, skips the `exclusion_policies` DB read entirely (the hidden-name rule above still applies).
- **`exclusion_policies` semantics** (active rows where `data_source_id IS NULL` are global; rows matching the requested `data_source_id` add per-source rules)
  - **`FOLDER`** — folder name match (case-insensitive, leading/trailing slashes stripped). Excluded folders are dropped from `items` **and** their subtree is not enqueued.
  - **`EXTENSION`** — file extension match (case-insensitive, `.` ignored).
  - **`PATH_PATTERN`** — simple substring match against the data-source-relative `remote_path`.
  - **`MAX_FILE_SIZE`** — `pattern` parsed as integer bytes; files larger than that are excluded. Multiple policies → the **most restrictive** value wins. Unparseable values are ignored and recorded in `warnings`.
  - If the table or enum types are not yet present, the loader returns an empty filter and adds a warning; the sync still runs.
- **`files` upsert** (shared with `sync-root` via `services/files_upsert.py`): conflicts on `(data_source_id, remote_path)`, refreshes metadata, flips files back to **`PENDING`** only when `etag` / `last_modified` actually changed, keeps folders as **`SKIPPED`**, and never persists ciphertext or credentials.
- **Transactionality:** the WebDAV walk runs **outside** any DB transaction (it's network I/O bounded by `max_items`); the collected items are then upserted alongside the `data_sources.last_scan_at` finalization inside **one** DB transaction (whole-batch rollback on failure).
- **`data_sources` finalization**
  - Success / partial → `last_scan_at`, `last_connection_test_at`, `last_connection_success = TRUE`, `last_connection_message = "WebDAV recursive sync succeeded"` / `"...stopped by max_items limit"` / `"...completed with some failed directories"`.
  - Fatal failure on the *start folder* (auth, 404, connection error, …) → `last_connection_*` only; **`last_scan_at` is not bumped**.
- **`scan_jobs`** (best-effort): `MANUAL_SCAN` row created as `RUNNING`; finalized with `total_files = total_remote_items`, `processed_files = inserted + updated`, `completed_files = processed_files`, `failed_files = failed_count`, `skipped_files = excluded + directories`. Partial successes still finalize as **`COMPLETED`** but carry a short `error_message` summary of failed folders.
- **Response shape** — counters include `visited_directories`, `total_remote_items`, `processed_items`, `inserted_count`, `updated_count`, `directories_count`, `files_count`, `excluded_count`, `failed_count`, `truncated`. Partial runs add `failed_paths[]` (capped at 20). `warnings[]` is also capped at 20.
- **Out of scope (Step 10):** file downloads, content hashing / `content_hash`, mime sniffing beyond the server-provided `getcontenttype`, chunking, embeddings, and `document_chunks` writes. Deletion detection is added in **Step 11** below as an opt-in extension of this endpoint.
- **Operational note:** this endpoint runs synchronously inside the HTTP request, with `max_depth` / `max_items` for safety. The current shape is **intentionally minimal**; in production the recursive walk is expected to move to a worker queue (separate process) so that long traversals do not hold an HTTP connection.

```bash
# Whole tree from root, three levels deep, default exclusions on
curl -X POST "http://localhost:8000/api/data-sources/{id}/sync-tree?start_path=/&max_depth=3&max_items=5000&include_hidden=false&apply_exclusions=true"

# Deeper walk under a subfolder, hidden names included, exclusions off
curl -X POST "http://localhost:8000/api/data-sources/{id}/sync-tree?start_path=/project-a&max_depth=5&max_items=10000&include_hidden=true&apply_exclusions=false"
```

### Deleted-file detection (`detect_deleted=true`, Step 11)

`sync-tree` accepts an opt-in **`detect_deleted`** query parameter (default **`false`**). When enabled, rows in `files` that fall inside the current `start_path` scope but were **not** observed during this walk are flipped to a **soft** `analysis_status = 'DELETED'`. The on-disk row is **never physically deleted** — this prevents stale documents from showing up in future searches without losing the historical record.

- **Default is `false`** on purpose: turning detection on without operator intent could mass-mark thousands of rows after a misconfigured run. With `detect_deleted=false` a single warning is returned:
  - `"Deleted detection is disabled. Existing files not found in this sync were not marked as DELETED."`
- **All of the following must hold** for detection to actually execute (any failure → detection skipped, `deleted_marked_count = 0`, an explanatory warning is appended):
  - `detect_deleted=true`
  - `truncated=false` — a `max_items`-truncated walk cannot conclude that the unseen tail is gone.
  - `failed_count=0` — folders that errored may legitimately still contain the missing rows.
  - `apply_exclusions=false` — exclusion rules can hide a file in this run that was visible in the previous one; treating it as deleted would corrupt the index.
  - `include_hidden=true` — hidden names dropped by the walk are not deletion candidates.
  - WebDAV BFS itself succeeded (no fatal start-folder error).
- **Skip warnings** are aggregated, so multiple reasons can be reported at once:
  - `"Deleted detection was skipped because sync result was truncated."`
  - `"Deleted detection was skipped because some directories failed to sync."`
  - `"Deleted detection was skipped because exclusion policies were applied. Run with apply_exclusions=false for deleted detection."`
  - `"Deleted detection was skipped because hidden items were excluded."`
- **Scope filter** — `start_path` is normalized (always leading `/`, no trailing `/` except root):
  - `start_path=/` → entire `data_source_id` is the deletion candidate set.
  - `start_path=/project-a` → `remote_path = '/project-a'` **or** `remote_path LIKE '/project-a/%' ESCAPE '!'`. `%`, `_`, and `!` in the path are escaped before the `LIKE` so a folder literally named `100%docs` does the right thing. `!` is the escape character (instead of the conventional `\\`) to avoid PostgreSQL's `standard_conforming_strings` quoting quirks.
- **Detection SQL** runs inside the **same transaction** as the upsert batch:
  - `CREATE TEMP TABLE tmp_collected_paths(remote_path TEXT PRIMARY KEY) ON COMMIT DROP`
  - Bulk-load this run's `remote_path`s via `COPY ... FROM STDIN`.
  - `UPDATE files SET analysis_status='DELETED'::analysis_status, analysis_error_code=NULL, analysis_error_message='File not found in latest WebDAV sync', updated_at=NOW() WHERE data_source_id=%s AND analysis_status<>'DELETED' AND <scope> AND NOT EXISTS (SELECT 1 FROM tmp_collected_paths t WHERE t.remote_path = files.remote_path)`
  - `last_indexed_at` is **left untouched** (analysis state is moving, not analysis history).
- **Transaction policy** — upserts + deletion mark + `data_sources.last_scan_at` finalization commit together. If the deletion UPDATE fails, the **entire batch is rolled back**, `scan_jobs` is marked `FAILED` with `error_message='Failed to mark deleted files'`, and `last_scan_at` is **not** bumped. The HTTP response body uses the same message and includes the original DB error string.
- **`scan_jobs` integration** — `scan_jobs.deleted_files` carries `deleted_marked_count` on success (0 when detection is skipped or disabled). The history row stays `COMPLETED` for partial-but-successful runs; only deletion-marking failures turn it `FAILED`.
- **Stats integration** — `GET /api/files/stats` and `GET /api/data-sources/{id}/file-stats` already honor the `include_deleted` query (default `false`); rows soft-marked here only appear when the caller passes `include_deleted=true`. The `by_analysis_status` slice surfaces a `DELETED` bucket in that mode.
- **`document_chunks` policy (future):** when later steps start writing `document_chunks`, every row associated with a `DELETED` file **must** be deactivated or removed and the **RAG search path must filter out `DELETED` files** before retrieval. This milestone deliberately writes nothing to `document_chunks`.

```bash
# Detection enabled and gates satisfied (no exclusions, hidden included)
curl -X POST "http://localhost:8000/api/data-sources/{id}/sync-tree?start_path=/&max_depth=3&max_items=5000&include_hidden=true&apply_exclusions=false&detect_deleted=true"

# Detection requested but exclusions are still on → response carries
# deleted_marked_count=0 and an apply_exclusions skip-warning
curl -X POST "http://localhost:8000/api/data-sources/{id}/sync-tree?start_path=/project-a&max_depth=4&max_items=10000&include_hidden=true&apply_exclusions=true&detect_deleted=true"
```

## Notes

- Steps 1–11 wire health checks, pgvector smoke tests, credential-safe data-source CRUD, a **minimal** DAV probe, **one-level** WebDAV previews and sync, a read-only **file statistics** endpoint, a **bounded recursive** WebDAV sync (BFS, Depth:1 per folder, `max_depth` / `max_items`) with **`exclusion_policies`** applied, and **opt-in soft-mark deletion detection** for that recursive sync — still **no** file downloads, content hashing, chunking, embeddings, `document_chunks` writes, authenticated UI, RBAC, or RAG/search.
- Structure is kept small for later ingestion, delta sync, scheduling, Docker Compose packaging, React admin screens, and search APIs.
