"""Налаштування застосунку. Значення беруться зі змінних оточення / файлу .env."""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_SECRETS = {"change-me", ""}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "RoadMap API"
    environment: str = "local"
    api_prefix: str = "/api/v1"

    # Підключення до PostgreSQL + PostGIS
    postgres_user: str = "roadmap"
    postgres_password: str = "roadmap"
    postgres_db: str = "roadmap"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Безпека (JWT) — справжнє значення тільки в .env
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # Актуальна версія текстів згоди (п. 3.5). Зміна версії вимагає повторної згоди.
    consent_version: str = "1.0"

    # Звідки фронтенд може звертатися до API (через кому)
    cors_origins: str = "http://localhost:5173"

    @model_validator(mode="after")
    def _secret_must_be_set_outside_local(self) -> "Settings":
        if self.environment not in {"local", "test"} and (
            self.jwt_secret in INSECURE_SECRETS or len(self.jwt_secret) < 32
        ):
            raise ValueError("JWT_SECRET має бути заданий у .env і містити щонайменше 32 символи")
        return self

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
