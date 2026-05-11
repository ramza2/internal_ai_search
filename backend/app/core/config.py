from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "internal-ai-search-backend"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma3"
    ollama_timeout_seconds: float = 10.0

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
