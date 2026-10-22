import os
from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    APP_NAME: str = "Cloud-Native RFID Library System"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./rfid_library.db")

    # Security & JWT
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "rfid-cloud-secret-token-key-2026-production-grade")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # RFID Security & Edge Ingestion
    HMAC_REPLAY_WINDOW_SECONDS: int = int(os.getenv("HMAC_REPLAY_WINDOW_SECONDS", "60"))
    RFID_DEBOUNCE_WINDOW_SECONDS: float = float(os.getenv("RFID_DEBOUNCE_WINDOW_SECONDS", "2.0"))
    SESSION_TIMEOUT_SECONDS: int = int(os.getenv("SESSION_TIMEOUT_SECONDS", "90"))

    # Circulation Rules
    DEFAULT_LOAN_DAYS: int = int(os.getenv("DEFAULT_LOAN_DAYS", "14"))
    MAX_BOOKS_PER_MEMBER: int = int(os.getenv("MAX_BOOKS_PER_MEMBER", "5"))
    MAX_RENEWALS_PER_LOAN: int = int(os.getenv("MAX_RENEWALS_PER_LOAN", "1"))
    FINE_PER_DAY: float = float(os.getenv("FINE_PER_DAY", "1.00"))

    # CORS
    CORS_ORIGINS: List[str] = ["*"]

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()
