import os
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv

# Load .env file from project root
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

class Settings(BaseModel):
    # API Keys
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")
    UPSTREAM_BASE_URL: str = os.getenv("UPSTREAM_BASE_URL", "https://api.openai.com/v1")
    UPSTREAM_API_KEY: str = os.getenv("UPSTREAM_API_KEY", "")

    # Server Settings
    HOST: str = os.getenv("HEIMDALL_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("HEIMDALL_PORT", "8000"))

    # Semantic Cache Settings
    SIMILARITY_THRESHOLD: float = float(os.getenv("HEIMDALL_SIMILARITY_THRESHOLD", "0.85"))
    FRESHNESS_THRESHOLD: float = float(os.getenv("HEIMDALL_FRESHNESS_THRESHOLD", "70.0"))

    # Volatility TTLs (in seconds)
    TTL_STATIC_SECONDS: int = 365 * 24 * 3600       # Historical, math, definitions
    TTL_MODERATE_SECONDS: int = 30 * 24 * 3600      # General tech docs, company overviews
    TTL_VOLATILE_SECONDS: int = 3 * 24 * 3600       # Pricing, APIs, leadership, news

settings = Settings()
