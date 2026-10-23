import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from code_parser.ast_parser import CodeNode, parse_repo, _iter_source_files


def source_fingerprint(root: str | Path) -> str:
    root = Path(root)
    digest = hashlib.sha256()
    for path in _iter_source_files(root):
        try:
            stat = path.stat()
        except OSError:
            continue
        rel = path.relative_to(root)
        digest.update(f"{rel}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _cache_file(root: Path, cache_dir: str | Path) -> Path:
    key = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:16]
    return Path(cache_dir) / f"nodes-{key}.json"


def parse_repo_cached(root: str | Path, cache_dir: str | Path,
                      parser=parse_repo) -> list[CodeNode]:
    root = Path(root)
    cache_path = _cache_file(root, cache_dir)
    fingerprint = source_fingerprint(root)

    if cache_path.exists():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            if data.get("fingerprint") == fingerprint:
                return [CodeNode(**node) for node in data.get("nodes", [])]
        except (OSError, ValueError, TypeError):
            pass

    nodes = parser(str(root))
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"fingerprint": fingerprint, "nodes": [asdict(n) for n in nodes]}),
            encoding="utf-8",
        )
    except OSError:
        pass
    return nodes