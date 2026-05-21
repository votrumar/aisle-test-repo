from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://monitoring:monitoring@localhost:5432/monitoring"
    jwt_secret: SecretStr = SecretStr("dev-secret-do-not-use")


settings = Settings()


@lru_cache
def get_settings() -> Settings:
    return settings
