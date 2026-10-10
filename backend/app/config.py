from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="STW_")

    database_url: str = "sqlite:///./stewarding.db"
    secret_key: str = ""
    token_minutes: int = 600
    cors_origins: str = "http://localhost:5173"
    seed_password: str = ""


settings = Settings()
