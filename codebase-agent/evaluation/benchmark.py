import argparse
import json
import sys
import time
from pathlib import Path

from config.settings import Settings
from code_parser.ast_parser import parse_repo
from embedding.embedder import Embedder
from retrieval.vector_store import VectorStore
from retrieval.ast_index import ASTIndex
from retrieval.hybrid_search import hybrid_search


def load_benchmark(name: str) -> list[dict]:
    path = Path(__file__).parent / "data" / f"{name}_qa.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round((len(ordered) - 1) * p)))]


def evaluate_retrieval(repo_path: str, benchmark: list[dict], embedder: Embedder,
                       vector_store: VectorStore, ast_index: ASTIndex, k: int = 3) -> dict:
    hits = 0
    latencies: list[float] = []
    details: list[dict] = []
    for item in benchmark:
        started = time.perf_counter()
        results = hybrid_search(item["question"], vector_store, ast_index, embedder, k=k)
        elapsed_ms = (time.perf_counter() - started) * 1000
        latencies.append(elapsed_ms)
        hit = any(item["source_file"] in r.file_path for r in results)
        if hit:
            hits += 1
        details.append({
            "id": item.get("id"),
            "question": item["question"],
            "hit": hit,
            "latency_ms": round(elapsed_ms, 2),
            "retrieved": [r.file_path for r in results],
        })

    total = len(benchmark)
    return {
        "top_k_hit_rate": hits / total if total else 0.0,
        "k": k,
        "total": total,
        "hits": hits,
        "latency_p50_ms": round(_percentile(latencies, 0.5), 2) if latencies else None,
        "latency_p95_ms": round(_percentile(latencies, 0.95), 2) if latencies else None,
        "details": details,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="检索评测：Top-k 命中率 + 延迟")
    ap.add_argument("repo_name")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--out", help="把 JSON 结果写到指定路径")
    ap.add_argument("--json", action="store_true", help="直接打印 JSON")
    ap.add_argument("--min-hit-rate", type=float, default=None,
                    help="命中率低于该值则以非零码退出（用于 CI/回归门槛）")
    args = ap.parse_args()

    settings = Settings.load()
    benchmark = load_benchmark(args.repo_name)
    repo_path = Path(settings.repos_dir) / args.repo_name
    if not repo_path.exists():
        print(f"仓库不存在 {repo_path}。请先运行 'codebase-agent analyze <url>'")
        sys.exit(1)

    nodes = parse_repo(str(repo_path))
    embedder = Embedder(settings.embedding_model)
    vector_store = VectorStore(repo_name=args.repo_name, persist_dir=settings.chroma_persist_dir)
    vector_store.add(nodes, embedder)
    ast_index = ASTIndex(nodes)

    result = evaluate_retrieval(str(repo_path), benchmark, embedder, vector_store, ast_index, k=args.k)

    if args.out:
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"Top-{result['k']} 命中率: {result['top_k_hit_rate']:.2%}")
        print(f"命中: {result['hits']}/{result['total']}")
        print(f"检索延迟 P50/P95: {result['latency_p50_ms']} / {result['latency_p95_ms']} ms")

    if args.min_hit_rate is not None and result["top_k_hit_rate"] < args.min_hit_rate:
        print(f"低于门槛 {args.min_hit_rate:.0%}，评测失败", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()