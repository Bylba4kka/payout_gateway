from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # БД
    postgres_db: str
    postgres_user: str
    postgres_password: str
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_echo: bool = False

    # Авторизация (bearer-токен)
    api_token: SecretStr

    # --- вебхуки ---
    webhook_url: str
    webhook_timeout: float = 10.0
    webhook_max_attempts: int = 5
    webhook_retry_base_delay: float = 5.0
    webhook_retry_max_delay: float = 3600.0

    # Обработка переводов
    source_wallet_address: str = "internal-wallet"  # адрес горячего кошелька в блокчейне, с которого уходят деньги
    worker_poll_interval: float = 1.0  # сек, пауза, когда очередь пуста
    run_workers: bool = True  # False: поднять только API (воркеры в отдельном процессе)

    # app
    debug: bool = False
    title: str = "payout_gateway"
    description: str = "Payout Gateway"

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
