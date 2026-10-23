import hashlib
from dataclasses import dataclass
import chromadb
from chromadb.config import Settings as ChromaSettings
from code_parser.ast_parser import CodeNode
from embedding.embedder import Embedder


_EMBED_MAX_CHARS = 2000


def _node_text(node: CodeNode) -> str:
    parts = [node.name, node.signature, node.docstring, node.body]
    return "\n".join(p for p in parts if p)[:_EMBED_MAX_CHARS]


def _node_hash(node: CodeNode) -> str:
    return hashlib.md5(_node_text(node).encode("utf-8")).hexdigest()


@dataclass
class SearchResult:
    node_id: str
    name: str
    file_path: str
    start_line: int
    end_line: int
    score: float


_CLIENTS: dict[str, "chromadb.ClientAPI"] = {}


def _get_client(persist_dir: str):
    client = _CLIENTS.get(persist_dir)
    if client is None:
        client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        _CLIENTS[persist_dir] = client
    return client


class VectorStore:
    def __init__(self, repo_name: str = "default", persist_dir: str = "./data/chroma"):
        self.client = _get_client(persist_dir)
        self.collection = self.client.get_or_create_collection(
            name=f"code_nodes_{repo_name}",
            metadata={"hnsw:space": "cosine"},
        )
        self._repo_name = repo_name

    def add(self, nodes: list[CodeNode], embedder: Embedder):
        """Incremental: only embed nodes that are new or whose content changed."""
        if not nodes:
            return
        ids = [n.node_id for n in nodes]
        hashes = {n.node_id: _node_hash(n) for n in nodes}

        existing = self.collection.get(ids=ids, include=["metadatas"])
        existing_hash: dict[str, str | None] = {}
        metas = existing.get("metadatas") or []
        for i, existing_id in enumerate(existing.get("ids", [])):
            meta = metas[i] if i < len(metas) else {}
            existing_hash[existing_id] = (meta or {}).get("hash")

        to_embed = [n for n in nodes if existing_hash.get(n.node_id) != hashes[n.node_id]]
        if to_embed:
            vectors = embedder.encode([_node_text(n) for n in to_embed])
            self.collection.upsert(
                ids=[n.node_id for n in to_embed],
                embeddings=vectors,
                metadatas=[{"type": n.type, "name": n.name, "file_path": n.file_path,
                            "start_line": n.start_line, "end_line": n.end_line,
                            "hash": hashes[n.node_id]} for n in to_embed],
            )

        keep = set(ids)
        try:
            all_ids = set(self.collection.get()["ids"])
        except Exception:
            all_ids = set()
        stale = all_ids - keep
        if stale:
            self.collection.delete(ids=list(stale))

    def search(self, query: str, embedder: Embedder, k: int = 5) -> list[SearchResult]:
        if self.collection.count() == 0:
            return []
        query_vec = embedder.encode([query])
        results = self.collection.query(query_embeddings=query_vec, n_results=k)
        if not results["ids"] or not results["ids"][0]:
            return []
        items = []
        for i in range(len(results["ids"][0])):
            items.append(SearchResult(
                node_id=results["ids"][0][i],
                name=results["metadatas"][0][i]["name"],
                file_path=results["metadatas"][0][i]["file_path"],
                start_line=results["metadatas"][0][i]["start_line"],
                end_line=results["metadatas"][0][i]["end_line"],
                score=results["distances"][0][i],
            ))
        return items
