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
    # Multi-user. Anyone can hit POST /api/auth/register only when
    # allow_signup is True. Default is False so a fresh production instance
    # never accidentally accepts strangers; flip it to True (env or .env)
    # for local dev or once you've decided the instance is ready to
    # accept new accounts.
    jwt_secret:   str = "dev-only-change-me-in-prod"
    jwt_ttl_days: int = 30
    allow_signup: bool = False

    extraction_timeout_s: float = 8.0
    suggestion_timeout_s: float = 20.0
    cache_ttl_s: int = 60 * 60 * 24

    # Model IDs — verified against current 2026 tiers.
    claude_fast_model: str = "claude-haiku-4-5-20251001"
    claude_strong_model: str = "claude-sonnet-4-5"
    openai_fast_model: str = "gpt-4.1-mini"
    openai_strong_model: str = "gpt-4.1"
    openai_transcribe_model: str = "whisper-1"
    gemini_fast_model: str = "gemini-2.5-flash"
    gemini_strong_model: str = "gemini-2.5-pro"

    # ─── Extraction safety mode ────────────────────────────────────────────
    # Hot-path extraction defaults to Sonnet, not Haiku. The live eval over
    # our 30-example gold corpus shows Sonnet's hallucination rate on
    # value-bearing fields (medications/vitals/labs) is 5.8% vs Haiku's
    # 13.1% — a critical gap for a medical app where dose/value accuracy
    # matters. Sonnet TTFT is ~50% slower than Haiku but still under 1s,
    # so the perceived UX cost is minimal. Per-pass cost goes from $0.08
    # to $0.24 against the eval corpus, which is fractions of a cent per
    # real-world report.
    #
    # Override via env to revert to Haiku (e.g. for high-volume / lower-
    # stakes flows): set EXTRACT_SAFE_MODE=false.
    extract_safe_mode: bool = True


settings = Settings()
