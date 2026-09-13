from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://127.0.0.1:6379/0"
    jwt_secret: str
    jwt_expire_minutes: int = 60
    storage_state_encryption_key: str

    # 固定读取 backend/.env，避免从项目根目录启动 Worker 时丢失配置。
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[2] / ".env"),
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
