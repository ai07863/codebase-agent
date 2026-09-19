from pathlib import Path


def read_file_tool(file_path: str, start_line: int = 1, end_line: int | None = None) -> str:
    p = Path(file_path)
    if not p.exists():
        return f"File not found: {file_path}"
    lines = p.read_text(encoding="utf-8").splitlines()
    end = end_line or len(lines)
    selected = lines[start_line - 1:end]
    return "\n".join(selected)