from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongo_url: str = "mongodb://localhost:27017"
    mongo_db: str = "medchat"
    redis_url: str = "redis://localhost:6379/0"

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""

    log_level: str = "INFO"
    # CORS: comma-separated allowed origins. "*" allows everything (dev only).
    cors_origins: str = "*"

    # ─── Auth ──────────────────────────────────────────────────────────────
    # Multi-user. Anyone can hit POST /api/auth/register unless
    # allow_signup is set to False (lock the instance to existing users).
    jwt_secret:   str = "dev-only-change-me-in-prod"
    jwt_ttl_days: int = 30
    allow_signup: bool = True

    extraction_timeout_s: float = 8.0
    suggestion_timeout_s: float = 20.0
    cache_ttl_s: int = 60 * 60 * 24

    # Model IDs — verified against current 2026 tiers.
    claude_fast_model: str = "claude-haiku-4-5-20251001"
    claude_strong_model: str = "claude-sonnet-4-6"
    openai_fast_model: str = "gpt-4.1-mini"
    openai_strong_model: str = "gpt-4.1"
    openai_transcribe_model: str = "whisper-1"
    gemini_fast_model: str = "gemini-2.5-flash"
    gemini_strong_model: str = "gemini-2.5-pro"


settings = Settings()
