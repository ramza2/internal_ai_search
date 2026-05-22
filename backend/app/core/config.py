from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "internal-ai-search-backend"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma3"
    # Timeout used by the /api/tags health probe. Must stay short so
    # ``GET /health/llm`` fails fast when Ollama is down.
    ollama_timeout_seconds: float = 10.0
    # Timeout for /api/generate (RAG answer endpoint). Generation runs
    # on CPU in many dev setups and can legitimately take 30–60s for
    # gemma3, so this is decoupled from the health-probe timeout.
    ollama_generate_timeout_seconds: float = 60.0

    embedding_provider: str = "ollama"
    embedding_model: str = "bge-m3"
    embedding_dimension: int = 1024
    embedding_test_text: str = "사내 지식 검색 시스템 임베딩 테스트 문장입니다."
    embedding_timeout_seconds: float = 20.0

    db_host: str = "localhost"
    db_port: int = 5433
    db_name: str = "internal_ai_search"
    db_user: str = "openlink"
    db_password: str = ""

    data_source_secret_key: str = "change-this-secret-key-in-production"

    webdav_timeout_seconds: float = 15.0

    # --- Step 19: JWT + initial admin bootstrap -------------------------
    jwt_secret_key: str = "change-this-jwt-secret-key-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 720

    initial_admin_login_id: str = "admin"
    initial_admin_password: str = ""
    initial_admin_name: str = "Initial Admin"
    initial_admin_email: str = "admin@example.com"
    initial_admin_department: str = "System"

    password_min_length: int = 8

    # --- DB polling worker (skeleton; separate process) -----------------
    worker_enabled: bool = False
    worker_id: str = "local-worker-1"
    worker_poll_interval_seconds: float = 5.0
    worker_heartbeat_interval_seconds: float = 10.0
    worker_stale_timeout_minutes: int = 30
    worker_max_jobs_per_loop: int = 1

    # --- HWP binary parser (hwp5txt / hwp5html subprocess; AGPL — see README) --
    hwp_extraction_strategy: str = "tiered"
    hwp5txt_bin: str = "hwp5txt"
    hwp5html_bin: str = "hwp5html"
    hwp_parser_timeout_seconds: int = 120
    hwp_min_extracted_text_length: int = 50
    hwp_html_min_extracted_text_length: int = 50
    hwp_html_min_gain_ratio: float = 1.5

    # FULL sync-tree (worker/pipeline only): optional emergency item cap. 0 = none.
    sync_tree_emergency_max_items: int = 0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def db_dsn(self) -> str:
        return (
            f"host={self.db_host} "
            f"port={self.db_port} "
            f"dbname={self.db_name} "
            f"user={self.db_user} "
            f"password={self.db_password}"
        )


settings = Settings()
