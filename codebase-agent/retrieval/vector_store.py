from dataclasses import dataclass
import chromadb
from chromadb.config import Settings as ChromaSettings
from code_parser.ast_parser import CodeNode
from embedding.embedder import Embedder


@dataclass
class SearchResult:
    node_id: str
    name: str
    file_path: str
    start_line: int
    end_line: int
    score: float


class VectorStore:
    def __init__(self, repo_name: str = "default", persist_dir: str = "./data/chroma"):
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=f"code_nodes_{repo_name}",
            metadata={"hnsw:space": "cosine"},
        )
        self._repo_name = repo_name

    def add(self, nodes: list[CodeNode], embedder: Embedder):
        texts = [f"{n.signature}\n{n.docstring}" for n in nodes]
        vectors = embedder.encode(texts)
        ids = [n.node_id for n in nodes]
        metadatas = [{"type": n.type, "name": n.name, "file_path": n.file_path,
                       "start_line": n.start_line, "end_line": n.end_line} for n in nodes]
        existing = self.collection.get(ids=ids)
        if existing["ids"]:
            self.collection.delete(ids=existing["ids"])
        self.collection.add(ids=ids, embeddings=vectors, metadatas=metadatas)

    def search(self, query: str, embedder: Embedder, k: int = 5) -> list[SearchResult]:
        query_vec = embedder.encode([query])
        results = self.collection.query(query_embeddings=query_vec, n_results=k)
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