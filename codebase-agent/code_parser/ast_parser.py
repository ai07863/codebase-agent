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


_PARSER_CACHE = {}


def _get_parser(language: str = "python"):
    if language not in _PARSER_CACHE:
        if language == "python":
            lang = Language(tspython.language())
        else:
            return None
        parser = Parser(lang)
        _PARSER_CACHE[language] = parser
    return _PARSER_CACHE[language]


def _detect_language(file_path: str) -> str | None:
    ext = Path(file_path).suffix
    mapping = {".py": "python", ".js": "javascript", ".ts": "typescript", ".go": "go", ".java": "java"}
    return mapping.get(ext)


def _extract_docstring(node, source_bytes: bytes) -> str:
    body = node.child_by_field_name("body")
    if body is None or body.child_count == 0:
        return ""
    first = body.child(0)
    if first.type == "expression_statement" and first.child(0) and first.child(0).type == "string":
        start = first.start_byte
        end = first.end_byte
        return source_bytes[start:end].decode("utf-8").strip("\"'")
    return ""


def _extract_calls(node, source_bytes: bytes) -> list[str]:
    calls = []
    if node.type == "call":
        func_node = node.child(0)
        if func_node:
            calls.append(source_bytes[func_node.start_byte:func_node.end_byte].decode("utf-8"))
    for child in node.children:
        calls.extend(_extract_calls(child, source_bytes))
    return calls


def _traverse(node, source_bytes: bytes, file_path: str, inside_class: bool = False) -> list[CodeNode]:
    nodes = []
    if node.type in ("function_definition", "class_definition"):
        name_node = node.child_by_field_name("name")
        if name_node:
            name = source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8")
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            sig_bytes = source_bytes[node.start_byte:node.end_byte]
            sig = sig_bytes.decode("utf-8").split("\n")[0].strip()
            docstring = _extract_docstring(node, source_bytes)
            if node.type == "function_definition":
                node_type = "method" if inside_class else "function"
            else:
                node_type = "class"
            calls = _extract_calls(node, source_bytes)
            node_id = f"{file_path}:{name}"
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
            ))
            if node.type == "class_definition":
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        nodes.extend(_traverse(child, source_bytes, file_path, inside_class=True))
    else:
        for child in node.children:
            nodes.extend(_traverse(child, source_bytes, file_path, inside_class))
    return nodes


def parse_repo(repo_path: str) -> list[CodeNode]:
    nodes = []
    root = Path(repo_path)
    for file_path in root.rglob("*"):
        if file_path.is_file() and file_path.suffix in (".py", ".js", ".ts", ".go", ".java"):
            lang = _detect_language(str(file_path))
            if not lang:
                continue
            rel_path = str(file_path.relative_to(root))
            source_bytes = file_path.read_bytes()
            parser = _get_parser(lang)
            if parser is None:
                continue
            tree = parser.parse(source_bytes)
            nodes.extend(_traverse(tree.root_node, source_bytes, rel_path))
    return nodes