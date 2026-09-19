from retrieval.vector_store import VectorStore, SearchResult
from retrieval.ast_index import ASTIndex
from embedding.embedder import Embedder


def hybrid_search(
    query: str,
    vector_store: VectorStore,
    ast_index: ASTIndex,
    embedder: Embedder,
    k: int = 5,
) -> list[SearchResult]:
    semantic_results = vector_store.search(query, embedder, k)
    ast_results = ast_index.search_by_name(query)
    seen = set()
    merged = []
    for r in semantic_results + ast_results:
        if r.node_id not in seen:
            seen.add(r.node_id)
            merged.append(r)
    return merged[:k]