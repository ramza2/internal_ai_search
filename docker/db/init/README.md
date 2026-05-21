# docker/db/init

Optional `docker-entrypoint-initdb.d` SQL can be placed here.

**Current dev flow:** schema is applied by the **`db-migrate`** compose service via `scripts/apply_migrations.py` (baseline + `backend/db/migrations/*.sql`), not by initdb hooks.

To reset the dev database:

```bash
docker compose -f docker-compose.dev.yml down -v
docker compose --env-file backend/.env -f docker-compose.dev.yml up -d
```

`down -v` deletes the `internal_ai_search_db_data` named volume.
