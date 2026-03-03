from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./credit_appraisal.db"

    NEWSAPI_KEY: str = ""
    SUREPASS_API_KEY: str = ""
    COMPDATA_API_KEY: str = ""

    SECRET_KEY: str = "supersecretkey_change_in_production"
    BASE_INTEREST_RATE: float = 10.0
    DEFAULT_LTV_RATIO: float = 0.70

    TEMPLATES_DIR: str = "../templates"
    ML_MODEL_PATH: str = "models_ml/credit_model.pkl"

    class Config:
        env_file = ".env"


settings = Settings()
