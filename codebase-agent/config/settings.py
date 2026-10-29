import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o-mini"))
    embedding_model: str = field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5"))
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"))
    llm_timeout: float = field(default_factory=lambda: float(os.getenv("LLM_TIMEOUT", "60")))
    llm_retries: int = field(default_factory=lambda: int(os.getenv("LLM_RETRIES", "2")))
    llm_price_input_per_1k: float = field(default_factory=lambda: float(os.getenv("LLM_PRICE_INPUT_PER_1K", "0")))
    llm_price_output_per_1k: float = field(default_factory=lambda: float(os.getenv("LLM_PRICE_OUTPUT_PER_1K", "0")))
    llm_budget_usd: float = field(default_factory=lambda: float(os.getenv("LLM_BUDGET_USD", "0")))
    redis_host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    redis_port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    chroma_persist_dir: str = field(default_factory=lambda: os.getenv("CHROMA_PERSIST_DIR", "./data/chroma"))
    repos_dir: str = field(default_factory=lambda: os.getenv("REPOS_DIR", "./data/repos"))
    history_db: str = field(default_factory=lambda: os.getenv("HISTORY_DB", "./data/history.db"))
    repo_cache_dir: str = field(default_factory=lambda: os.getenv("REPO_CACHE_DIR", "./data/cache"))
    api_token: str = field(default_factory=lambda: os.getenv("API_TOKEN", ""))
    rate_limit_per_min: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MIN", "60")))
    cors_origins: str = field(default_factory=lambda: os.getenv("CORS_ORIGINS", ""))
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "0").lower() in ("1", "true", "yes"))

    @classmethod
    def load(cls) -> "Settings":
        from dotenv import load_dotenv
        load_dotenv()
        return cls()