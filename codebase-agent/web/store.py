import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init()

    def _conn(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def _init(self) -> None:
        parent = Path(self.db_path).parent
        if str(parent):
            parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS conversations ("
                "id TEXT PRIMARY KEY, repo TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', "
                "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS messages ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL, "
                "role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL)"
            )

    def create(self, repo: str, title: str = "") -> str:
        conv_id = uuid.uuid4().hex
        now = _now()
        with self._conn() as con:
            con.execute(
                "INSERT INTO conversations (id, repo, title, created_at, updated_at) VALUES (?,?,?,?,?)",
                (conv_id, repo, title, now, now),
            )
        return conv_id

    def list(self) -> list[dict]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT id, repo, title, created_at, updated_at "
                "FROM conversations ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get(self, conv_id: str) -> dict | None:
        with self._conn() as con:
            row = con.execute(
                "SELECT id, repo, title, created_at, updated_at FROM conversations WHERE id = ?",
                (conv_id,),
            ).fetchone()
            if row is None:
                return None
            msgs = con.execute(
                "SELECT role, content, created_at FROM messages "
                "WHERE conversation_id = ? ORDER BY id ASC",
                (conv_id,),
            ).fetchall()
        conversation = dict(row)
        conversation["messages"] = [dict(m) for m in msgs]
        return conversation

    def add_message(self, conv_id: str, role: str, content: str) -> None:
        now = _now()
        with self._conn() as con:
            con.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?,?,?,?)",
                (conv_id, role, content, now),
            )
            con.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conv_id))

    def message_count(self, conv_id: str) -> int:
        with self._conn() as con:
            row = con.execute(
                "SELECT COUNT(*) AS n FROM messages WHERE conversation_id = ?", (conv_id,)
            ).fetchone()
        return int(row["n"])

    def delete(self, conv_id: str) -> None:
        with self._conn() as con:
            con.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
            con.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))