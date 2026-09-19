import hashlib
import json
import redis


class Cache:
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        self.client = redis.Redis(host=host, port=port, db=db, decode_responses=True)

    def _make_key(self, key: str) -> str:
        return f"codebase-agent:{hashlib.md5(key.encode()).hexdigest()}"

    def get(self, key: str) -> str | None:
        val = self.client.get(self._make_key(key))
        return val

    def set(self, key: str, value: str, ttl: int = 3600):
        self.client.set(self._make_key(key), value, ex=ttl)

    def exists(self, key: str) -> bool:
        return self.client.exists(self._make_key(key)) > 0

    def close(self):
        self.client.close()

    def clear_db(self):
        self.client.flushdb()