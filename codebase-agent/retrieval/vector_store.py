import hashlib
from dataclasses import dataclass
import chromadb
from chromadb.config import Settings as ChromaSettings
from code_parser.ast_parser import CodeNode
from embedding.embedder import Embedder


_EMBED_MAX_CHARS = 2000
_CHUNK_CHARS = 1200
_CHUNK_OVERLAP = 200


def _node_text(node: CodeNode) -> str:
    parts = [node.name, node.signature, node.docstring, node.body]
    return "\n".join(p for p in parts if p)[:_EMBED_MAX_CHARS]


def _node_full_text(node: CodeNode) -> str:
    parts = [node.name, node.signature, node.docstring, node.body]
    return "\n".join(p for p in parts if p)


def _chunk_text(text: str, size: int = _CHUNK_CHARS, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    if len(text) <= size:
        return [text]
    step = max(1, size - overlap)
    chunks = [text[i:i + size] for i in range(0, len(text), step)]
    return chunks


def _chunk_hash(model_name: str, text: str) -> str:
    return hashlib.md5(f"{model_name}\0{text}".encode("utf-8")).hexdigest()


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
        """Chunk long nodes; incrementally embed only new/changed chunks."""
        if not nodes:
            return
        model_name = getattr(embedder, "model_name", "")
        entries = []  # (chunk_id, node, chunk_text)
        for node in nodes:
            for index, chunk in enumerate(_chunk_text(_node_full_text(node))):
                entries.append((f"{node.node_id}#{index}", node, chunk))

        ids = [entry[0] for entry in entries]
        hashes = {cid: _chunk_hash(model_name, chunk) for cid, _node, chunk in entries}

        existing = self.collection.get(ids=ids, include=["metadatas"])
        existing_hash: dict[str, str | None] = {}
        metas = existing.get("metadatas") or []
        for i, existing_id in enumerate(existing.get("ids", [])):
            meta = metas[i] if i < len(metas) else {}
            existing_hash[existing_id] = (meta or {}).get("hash")

        to_embed = [entry for entry in entries if existing_hash.get(entry[0]) != hashes[entry[0]]]
        if to_embed:
            vectors = embedder.encode([entry[2] for entry in to_embed])
            self.collection.upsert(
                ids=[entry[0] for entry in to_embed],
                embeddings=vectors,
                metadatas=[{"type": entry[1].type, "name": entry[1].name,
                            "file_path": entry[1].file_path, "start_line": entry[1].start_line,
                            "end_line": entry[1].end_line, "node_id": entry[1].node_id,
                            "hash": hashes[entry[0]]} for entry in to_embed],
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
        results = self.collection.query(query_embeddings=query_vec, n_results=max(k * 3, k))
        if not results["ids"] or not results["ids"][0]:
            return []
        best: dict[str, SearchResult] = {}
        for i in range(len(results["ids"][0])):
            meta = results["metadatas"][0][i]
            node_id = meta.get("node_id", results["ids"][0][i])
            distance = results["distances"][0][i]
            current = best.get(node_id)
            if current is None or distance < current.score:
                best[node_id] = SearchResult(
                    node_id=node_id,
                    name=meta["name"],
                    file_path=meta["file_path"],
                    start_line=meta["start_line"],
                    end_line=meta["end_line"],
                    score=distance,
                )
        return sorted(best.values(), key=lambda r: r.score)[:k]