# config.py
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent   # project root

class Settings(BaseSettings):
    SECRET_KEY: str
    DATABASE_URL: str = "sqlite:///./data/test.db"
    RESEND_API_KEY: str
    FROM_EMAIL: str = "onboarding@resend.dev"
    FRONTEND_URL: str = "http://127.0.0.1:8000"
    ENVIRONMENT: str = "development"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ALGORITHM: str = "HS256"
    VERSION: str
    
    # Cloudflare R2
    R2_ACCOUNT_ID: str
    R2_ACCESS_KEY_ID: str
    R2_SECRET_ACCESS_KEY: str
    R2_BUCKET: str
    R2_ENDPOINT: str
    R2_PUBLIC_URL: str

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",             # ignore any extra variables in .env
        case_sensitive=False,       # optional but recommended
    )

settings = Settings()