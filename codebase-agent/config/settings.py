import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o-mini"))
    embedding_model: str = field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5"))
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"))
    redis_host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    redis_port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    chroma_persist_dir: str = field(default_factory=lambda: os.getenv("CHROMA_PERSIST_DIR", "./data/chroma"))
    repos_dir: str = field(default_factory=lambda: os.getenv("REPOS_DIR", "./data/repos"))
    history_db: str = field(default_factory=lambda: os.getenv("HISTORY_DB", "./data/history.db"))
    repo_cache_dir: str = field(default_factory=lambda: os.getenv("REPO_CACHE_DIR", "./data/cache"))
    api_token: str = field(default_factory=lambda: os.getenv("API_TOKEN", ""))
    cors_origins: str = field(default_factory=lambda: os.getenv("CORS_ORIGINS", ""))
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "0").lower() in ("1", "true", "yes"))

    @classmethod
    def load(cls) -> "Settings":
        from dotenv import load_dotenv
        load_dotenv()
        return cls()