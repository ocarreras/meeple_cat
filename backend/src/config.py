from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://meeple:meeple_dev@localhost:5432/meeple"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    # OIDC token settings
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    frontend_url: str = "http://localhost:3000"
    base_url: str = "http://localhost:8000"

    # Game engine
    disconnect_grace_period_seconds: int = 30
    game_engine_grpc_url: str = "localhost:50051"

    # Admin
    admin_email: str = "uri@str.cat"

    # Google OIDC (empty = disabled)
    google_client_id: str = ""
    google_client_secret: str = ""

    model_config = SettingsConfigDict(
        env_prefix="MEEPLE_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
