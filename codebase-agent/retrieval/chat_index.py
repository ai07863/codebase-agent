from retrieval.vector_store import _get_client


_MAX_CHARS = 2000


class ChatIndex:
    """Embedding index over conversation messages, for 'RAG over chat history'."""

    def __init__(self, persist_dir: str = "./data/chroma"):
        self.client = _get_client(persist_dir)

    def _collection(self, conv_id: str):
        return self.client.get_or_create_collection(name=f"chat_{conv_id}")

    def add(self, conv_id: str, msg_id: int, role: str, text: str, embedder) -> None:
        text = (text or "").strip()
        if not text:
            return
        snippet = text[:_MAX_CHARS]
        vector = embedder.encode([snippet])[0]
        self._collection(conv_id).upsert(
            ids=[str(msg_id)],
            embeddings=[vector],
            metadatas=[{"role": role, "text": snippet}],
        )

    def query(self, conv_id: str, text: str, embedder, k: int = 4) -> list[dict]:
        collection = self._collection(conv_id)
        if collection.count() == 0:
            return []
        try:
            vector = embedder.encode([text])[0]
            res = collection.query(query_embeddings=[vector], n_results=k)
        except Exception:
            return []
        if not res.get("ids") or not res["ids"][0]:
            return []
        out = []
        for i in range(len(res["ids"][0])):
            meta = res["metadatas"][0][i] or {}
            out.append({"id": res["ids"][0][i], "role": meta.get("role", "user"),
                        "text": meta.get("text", "")})
        return out