import os
from pathlib import Path


_IGNORED_DIRS = {".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env",
                 "dist", "build", "__pycache__", "site-packages", ".tox", "target"}


def _normalize(rel_path: str) -> str:
    return rel_path.strip().lstrip("/").replace("\\", "/")


def _iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _IGNORED_DIRS and not d.startswith(".")]
        for name in filenames:
            yield Path(dirpath) / name


def slice_lines(text: str, start: int = 1, end: int = 0, context: int = 30,
                max_lines: int = 400) -> dict:
    """Return only a window of lines around the requested range (not the whole file)."""
    lines = text.splitlines()
    total = len(lines)
    start = max(1, start or 1)
    lo = max(1, start - context)
    if end and end >= start:
        hi = min(total, end + context)
    else:
        hi = min(total, lo + max_lines - 1)
    hi = min(hi, lo + max_lines - 1)
    return {
        "content": "\n".join(lines[lo - 1:hi]),
        "first_line": lo,
        "total_lines": total,
    }


def resolve_repo_file(repo_root: Path, rel_path: str) -> Path:
    root = Path(repo_root).resolve()
    rel = _normalize(rel_path)
    if not rel:
        raise FileNotFoundError(rel_path)

    candidate = (root / rel).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"path escapes repository root: {rel_path}")
    if candidate.is_file():
        return candidate

    # Fallback: the model may cite only a basename or a partial path.
    wanted = rel.lower()
    basename = Path(rel).name.lower()
    matches = []
    for path in _iter_files(root):
        rel_posix = path.relative_to(root).as_posix().lower()
        if rel_posix == wanted or rel_posix.endswith("/" + wanted) or path.name.lower() == basename:
            matches.append(path)
    if not matches:
        raise FileNotFoundError(rel_path)
    return sorted(matches, key=lambda p: len(p.as_posix()))[0].resolve()