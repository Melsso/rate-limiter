from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379"
    rate_limit: int = 5
    rate_window: int = 60

    class Config:
        env_file = ".env"


settings = Settings()