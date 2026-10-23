from dataclasses import replace
from retrieval.vector_store import VectorStore
from retrieval.ast_index import ASTIndex
from embedding.embedder import Embedder


_RRF_K = 60


def _reciprocal_rank_fusion(rank_lists: list[list]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for results in rank_lists:
        for rank, result in enumerate(results):
            scores[result.node_id] = scores.get(result.node_id, 0.0) + 1.0 / (_RRF_K + rank + 1)
    return scores


def diversify(results: list, k: int, per_file: int = 3) -> list:
    counts: dict[str, int] = {}
    picked = []
    for result in results:
        count = counts.get(result.file_path, 0)
        if count >= per_file:
            continue
        counts[result.file_path] = count + 1
        picked.append(result)
        if len(picked) >= k:
            break
    return picked


def hybrid_search(
    query: str,
    vector_store: VectorStore,
    ast_index: ASTIndex,
    embedder: Embedder,
    k: int = 5,
) -> list:
    rank_lists = [
        ast_index.search_by_name(query),
        vector_store.search(query, embedder, k),
        ast_index.bm25.search(query, k),
    ]
    representatives: dict[str, object] = {}
    for results in rank_lists:
        for result in results:
            representatives.setdefault(result.node_id, result)

    fused = _reciprocal_rank_fusion(rank_lists)
    ordered = sorted(fused, key=lambda node_id: fused[node_id], reverse=True)
    return [replace(representatives[node_id], score=fused[node_id]) for node_id in ordered[:k]]