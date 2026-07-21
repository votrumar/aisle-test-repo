from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_EXAMPLE_REMOTE_SENSOR_KEY_ENCRYPTION_SECRET = "CHANGE_ME_GENERATE_A_UNIQUE_FERNET_KEY"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://monitoring:monitoring@localhost:5432/monitoring"
    jwt_secret: SecretStr = SecretStr("dev-secret-do-not-use")
    remote_sensor_key_encryption_secret: SecretStr

    @field_validator("remote_sensor_key_encryption_secret")
    @classmethod
    def validate_remote_sensor_key_encryption_secret(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if raw == _EXAMPLE_REMOTE_SENSOR_KEY_ENCRYPTION_SECRET:
            raise ValueError("REMOTE_SENSOR_KEY_ENCRYPTION_SECRET must be a unique generated value")
        Fernet(raw.encode("utf-8"))
        return value


settings = Settings()


@lru_cache
def get_settings() -> Settings:
    return settings
