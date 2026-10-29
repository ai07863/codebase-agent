import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
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
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=5000")
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
            con.execute(
                "CREATE TABLE IF NOT EXISTS query_traces ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, repo TEXT, "
                "conversation_id TEXT, context_conversation_id TEXT, question TEXT, "
                "route TEXT, overview INTEGER, retrieved TEXT, context_chars INTEGER, "
                "context_tokens_est INTEGER, llm_model TEXT, llm_latency_ms INTEGER, "
                "llm_ok INTEGER, llm_error TEXT, cached INTEGER, answer_len INTEGER, "
                "cost_est REAL, fallback INTEGER)"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS answer_feedback ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, repo TEXT, "
                "conversation_id TEXT, question TEXT, rating INTEGER NOT NULL, comment TEXT)"
            )
            for column, kind in (("cost_est", "REAL"), ("fallback", "INTEGER")):
                try:
                    con.execute(f"ALTER TABLE query_traces ADD COLUMN {column} {kind}")
                except sqlite3.OperationalError:
                    pass

    def add_trace(self, trace: dict) -> None:
        with self._conn() as con:
            con.execute(
                "INSERT INTO query_traces (ts, repo, conversation_id, context_conversation_id, "
                "question, route, overview, retrieved, context_chars, context_tokens_est, "
                "llm_model, llm_latency_ms, llm_ok, llm_error, cached, answer_len, "
                "cost_est, fallback) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    trace.get("ts") or _now(),
                    trace.get("repo"),
                    trace.get("conversation_id"),
                    trace.get("context_conversation_id"),
                    trace.get("question"),
                    trace.get("route"),
                    1 if trace.get("overview") else 0,
                    json.dumps(trace.get("retrieved") or [], ensure_ascii=False),
                    trace.get("context_chars"),
                    trace.get("context_tokens_est"),
                    trace.get("llm_model"),
                    trace.get("llm_latency_ms"),
                    1 if trace.get("llm_ok") else 0,
                    trace.get("llm_error"),
                    1 if trace.get("cached") else 0,
                    trace.get("answer_len"),
                    trace.get("cost_est"),
                    1 if trace.get("fallback") else 0,
                ),
            )

    def recent_traces(self, limit: int = 50) -> list[dict]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT * FROM query_traces ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def add_feedback(self, fb: dict) -> None:
        with self._conn() as con:
            con.execute(
                "INSERT INTO answer_feedback (ts, repo, conversation_id, question, rating, comment) "
                "VALUES (?,?,?,?,?,?)",
                (
                    fb.get("ts") or _now(),
                    fb.get("repo"),
                    fb.get("conversation_id"),
                    fb.get("question"),
                    int(fb.get("rating", 0)),
                    fb.get("comment"),
                ),
            )

    def metrics_summary(self, days: int = 7) -> dict:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._conn() as con:
            rows = con.execute(
                "SELECT * FROM query_traces WHERE ts >= ?", (since,)
            ).fetchall()
            fbs = con.execute(
                "SELECT rating FROM answer_feedback WHERE ts >= ?", (since,)
            ).fetchall()
        n = len(rows)
        lat = sorted(r["llm_latency_ms"] for r in rows if r["llm_latency_ms"] is not None)
        cached = sum(1 for r in rows if r["cached"])
        errs = sum(1 for r in rows if r["llm_ok"] == 0)
        routes: dict[str, int] = {}
        for r in rows:
            key = r["route"] or "unknown"
            routes[key] = routes.get(key, 0) + 1

        def pct(p: float):
            if not lat:
                return None
            return lat[min(len(lat) - 1, int(round((len(lat) - 1) * p)))]

        up = sum(1 for f in fbs if f["rating"] > 0)
        down = sum(1 for f in fbs if f["rating"] < 0)
        return {
            "days": days,
            "queries": n,
            "cached": cached,
            "llm_errors": errs,
            "fallbacks": sum(1 for r in rows if r["fallback"]),
            "cost_total": round(sum(r["cost_est"] or 0 for r in rows), 6),
            "success_rate": round((n - errs) / n, 3) if n else None,
            "cache_rate": round(cached / n, 3) if n else None,
            "latency_p50_ms": pct(0.5),
            "latency_p95_ms": pct(0.95),
            "avg_context_chars": int(sum(r["context_chars"] or 0 for r in rows) / n) if n else None,
            "routes": routes,
            "feedback_up": up,
            "feedback_down": down,
            "feedback_good_rate": round(up / (up + down), 3) if (up + down) else None,
        }

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

    def add_message(self, conv_id: str, role: str, content: str) -> int:
        now = _now()
        with self._conn() as con:
            cur = con.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?,?,?,?)",
                (conv_id, role, content, now),
            )
            con.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conv_id))
            return int(cur.lastrowid)

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