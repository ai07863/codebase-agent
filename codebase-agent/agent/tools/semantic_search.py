from retrieval.vector_store import VectorStore
from embedding.embedder import Embedder


def semantic_search_tool(query: str, vector_store: VectorStore, embedder: Embedder) -> str:
    results = vector_store.search(query, embedder, k=5)
    if not results:
        return "No semantic matches found."
    lines = []
    for r in results:
        lines.append(f"[{r.score:.3f}] {r.name} in {r.file_path}:{r.start_line}-{r.end_line}")
    return "\n".join(lines)