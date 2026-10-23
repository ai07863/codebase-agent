import os
from dataclasses import dataclass, field
from pathlib import Path
import tree_sitter_python as tspython
from tree_sitter import Language, Parser


@dataclass
class CodeNode:
    node_id: str
    type: str
    name: str
    file_path: str
    start_line: int
    end_line: int
    signature: str
    docstring: str
    calls: list[str] = field(default_factory=list)
    body: str = ""


_PARSER_CACHE = {}


def _get_parser(language: str):
    if language in _PARSER_CACHE:
        return _PARSER_CACHE[language]
    parser = None
    try:
        if language == "python":
            parser = Parser(Language(tspython.language()))
        elif language == "go":
            import tree_sitter_go as tsgo
            parser = Parser(Language(tsgo.language()))
    except Exception:
        parser = None
    _PARSER_CACHE[language] = parser
    return parser


def _detect_language(file_path: str) -> str | None:
    ext = Path(file_path).suffix
    mapping = {".py": "python", ".js": "javascript", ".ts": "typescript", ".go": "go", ".java": "java"}
    return mapping.get(ext)


# Per-language tree-sitter node types.
_LANG_CONFIG = {
    "python": {
        "function": {"function_definition"},
        "method": set(),
        "class": {"class_definition"},
        "call": {"call"},
        "body_field": "body",
    },
    "go": {
        "function": {"function_declaration"},
        "method": {"method_declaration"},
        "class": {"type_declaration"},
        "call": {"call_expression"},
        "body_field": "body",
    },
}


_SOURCE_EXTENSIONS = {".py", ".js", ".ts", ".go", ".java"}
_IGNORED_DIRS = {
    "node_modules", "venv", ".venv", "env", "dist", "build", "target",
    "__pycache__", "site-packages", ".tox", ".mypy_cache", ".pytest_cache", "vendor",
}
_MAX_FILE_BYTES = 1_000_000


def _iter_source_files(root: Path, max_bytes: int = _MAX_FILE_BYTES) -> list[Path]:
    results: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if not d.startswith(".") and d not in _IGNORED_DIRS
        )
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if path.suffix not in _SOURCE_EXTENSIONS:
                continue
            try:
                if path.stat().st_size > max_bytes:
                    continue
            except OSError:
                continue
            results.append(path)
    return results


def _extract_docstring(node, source_bytes: bytes) -> str:
    body = node.child_by_field_name("body")
    if body is None or body.child_count == 0:
        return ""
    first = body.child(0)
    if first.type == "expression_statement" and first.child(0) and first.child(0).type == "string":
        return source_bytes[first.start_byte:first.end_byte].decode("utf-8").strip("\"'")
    return ""


def _go_doc(node, source_bytes: bytes) -> str:
    parts = []
    sibling = node.prev_sibling
    while sibling is not None and sibling.type == "comment":
        parts.append(source_bytes[sibling.start_byte:sibling.end_byte].decode("utf-8"))
        sibling = sibling.prev_sibling
    parts.reverse()
    cleaned = []
    for part in parts:
        line = part.strip()
        if line.startswith("//"):
            line = line[2:]
        elif line.startswith("/*"):
            line = line[2:]
        if line.endswith("*/"):
            line = line[:-2]
        cleaned.append(line.strip())
    return "\n".join(c for c in cleaned if c).strip()


def _extract_doc(node, source_bytes: bytes, lang: str) -> str:
    if lang == "python":
        return _extract_docstring(node, source_bytes)
    return _go_doc(node, source_bytes)


def _normalize_call_name(name: str) -> str:
    name = name.strip()
    if "." in name:
        name = name.rsplit(".", 1)[-1]
    return name


def _extract_calls(node, source_bytes: bytes, call_types: set) -> list[str]:
    calls = []
    if node.type in call_types:
        func_node = node.child(0)
        if func_node:
            raw = source_bytes[func_node.start_byte:func_node.end_byte].decode("utf-8")
            calls.append(_normalize_call_name(raw))
    for child in node.children:
        calls.extend(_extract_calls(child, source_bytes, call_types))
    return calls


def _decl_name(node, source_bytes: bytes, lang: str) -> str | None:
    name_node = node.child_by_field_name("name")
    if name_node is None and node.type == "type_declaration":
        for child in node.children:
            if child.type == "type_spec":
                name_node = child.child_by_field_name("name")
                break
    if name_node is None:
        return None
    return source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8")


def _traverse(node, source_bytes: bytes, file_path: str, lang: str,
              inside_class: bool = False) -> list[CodeNode]:
    cfg = _LANG_CONFIG[lang]
    nodes = []
    node_type_raw = node.type
    if node_type_raw in cfg["function"] or node_type_raw in cfg["method"] or node_type_raw in cfg["class"]:
        name = _decl_name(node, source_bytes, lang)
        if name:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            body = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
            sig = body.split("\n")[0].strip()
            docstring = _extract_doc(node, source_bytes, lang)
            if node_type_raw in cfg["class"]:
                node_type = "class"
            elif node_type_raw in cfg["method"]:
                node_type = "method"
            else:
                node_type = "method" if (lang == "python" and inside_class) else "function"
            calls = _extract_calls(node, source_bytes, cfg["call"])
            node_id = f"{file_path}:{name}:{start_line}"
            nodes.append(CodeNode(
                node_id=node_id,
                type=node_type,
                name=name,
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                signature=sig,
                docstring=docstring,
                calls=list(set(calls)),
                body=body,
            ))
            if node_type_raw in cfg["class"]:
                class_body = node.child_by_field_name(cfg["body_field"])
                if class_body:
                    for child in class_body.children:
                        nodes.extend(_traverse(child, source_bytes, file_path, lang, inside_class=True))
    else:
        for child in node.children:
            nodes.extend(_traverse(child, source_bytes, file_path, lang, inside_class))
    return nodes


def parse_repo(repo_path: str) -> list[CodeNode]:
    nodes = []
    root = Path(repo_path)
    for file_path in _iter_source_files(root):
        lang = _detect_language(str(file_path))
        if not lang or lang not in _LANG_CONFIG:
            continue
        parser = _get_parser(lang)
        if parser is None:
            continue
        try:
            source_bytes = file_path.read_bytes()
            tree = parser.parse(source_bytes)
        except OSError:
            continue
        rel_path = str(file_path.relative_to(root))
        nodes.extend(_traverse(tree.root_node, source_bytes, rel_path, lang))
    return nodes