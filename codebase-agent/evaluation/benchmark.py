import json
import sys
from pathlib import Path
from config.settings import Settings
from code_parser.ast_parser import parse_repo
from embedding.embedder import Embedder
from retrieval.vector_store import VectorStore
from retrieval.ast_index import ASTIndex
from retrieval.hybrid_search import hybrid_search


def load_benchmark(name: str) -> list[dict]:
    path = Path(__file__).parent / "data" / f"{name}_qa.json"
    with open(path) as f:
        return json.load(f)


def evaluate_retrieval(repo_path: str, benchmark: list[dict], embedder: Embedder,
                       vector_store: VectorStore, ast_index: ASTIndex) -> dict:
    hit_count = 0
    total = len(benchmark)
    for item in benchmark:
        results = hybrid_search(item["question"], vector_store, ast_index, embedder, k=3)
        hit = any(item["source_file"] in r.file_path for r in results)
        if hit:
            hit_count += 1
    return {"top3_hit_rate": hit_count / total, "total": total, "hits": hit_count}


def main():
    settings = Settings.load()
    repo_name = sys.argv[1]
    benchmark = load_benchmark(repo_name)
    repo_path = Path(settings.repos_dir) / repo_name
    if not repo_path.exists():
        print(f"仓库不存在 {repo_path}。请先运行 'codebase-agent analyze <url>'")
        sys.exit(1)

    nodes = parse_repo(str(repo_path))
    embedder = Embedder()
    vector_store = VectorStore(persist_dir=settings.chroma_persist_dir)
    vector_store.add(nodes, embedder)
    ast_index = ASTIndex(nodes)

    result = evaluate_retrieval(str(repo_path), benchmark, embedder, vector_store, ast_index)
    print(f"Top-3 命中率: {result['top3_hit_rate']:.2%}")
    print(f"命中: {result['hits']}/{result['total']}")


if __name__ == "__main__":
    main()