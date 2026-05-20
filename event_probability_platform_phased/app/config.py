from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: str = "dev"
    database_url: str = "postgresql+psycopg://prob:prob@localhost:5432/probability"
    redis_url: str = "redis://localhost:6379/0"

    odds_api_key: str = ""
    odds_api_sport: str = "basketball_nba"
    odds_api_regions: str = "us"
    odds_api_markets: str = "h2h"
    odds_api_odds_format: str = "decimal"
    odds_api_poll_seconds: float = 5.0

    polymarket_gamma_base: str = "https://gamma-api.polymarket.com"
    polymarket_clob_base: str = "https://clob.polymarket.com"

    kalshi_api_key_id: str = ""
    kalshi_private_key_path: str = ""

    model_refresh_ms: int = 1000
    monte_carlo_paths: int = 20000
    default_vol_per_sqrt_min: float = 0.045
    default_mean_reversion: float = 0.05


@lru_cache
def get_settings() -> Settings:
    return Settings()
