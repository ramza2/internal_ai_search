"""Service-layer HWP reprocess verify (no JWT/password in output)."""
from __future__ import annotations

import json
from uuid import UUID

from app.core.config import Settings
from app.services.file_contents_service import fetch_pending_document_files
from app.services.pending_document_processor_service import run_process_pending_documents


def main() -> int:
    settings = Settings()
    ds = UUID("cd148eec-6d05-4486-b0b4-ebecebb3860a")
    ext = frozenset({"hwp"})
    before = fetch_pending_document_files(
        ds_id=ds,
        limit=5,
        document_extensions=ext,
        reprocess_skipped=False,
        reprocess_hwp_no_extractable_text=True,
    )
    dry, code = run_process_pending_documents(
        settings,
        ds,
        limit=1,
        max_file_size_bytes=268_435_456,
        include_extensions=ext,
        dry_run=True,
        reprocess_skipped=False,
        reprocess_hwp_no_extractable_text=True,
    )
    out: dict = {
        "data_source_id": str(ds),
        "fetch_reprocess_targets": len(before),
        "dry_run_http_code": code,
        "dry_run_target_count": dry.get("target_count"),
        "dry_run_planned_actions": [
            (i.get("planned_action"), i.get("file_id"))
            for i in (dry.get("items") or [])[:3]
            if isinstance(i, dict)
        ],
        "dry_run_warnings": dry.get("warnings"),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if before else 1


if __name__ == "__main__":
    raise SystemExit(main())
