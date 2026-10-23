from collections import Counter
from code_parser.ast_parser import CodeNode


def build_project_map(nodes: list[CodeNode], max_files: int = 60) -> str:
    counts = Counter(node.file_path for node in nodes)
    files = sorted(counts)
    lines = [f"{path} ({counts[path]})" for path in files[:max_files]]
    if len(files) > max_files:
        lines.append(f"... (+{len(files) - max_files} more files)")
    return "\n".join(lines)


def build_call_graph(nodes: list[CodeNode]) -> dict[str, list[str]]:
    defined = {n.name for n in nodes}
    graph: dict[str, list[str]] = {}
    for node in nodes:
        callees = graph.setdefault(node.name, [])
        for call in node.calls:
            if call in defined and call not in callees:
                callees.append(call)
    return graph


def find_callers(nodes: list[CodeNode], target_name: str) -> list[str]:
    return [n.name for n in nodes if target_name in n.calls]


def _file_of(nodes: list[CodeNode]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for node in nodes:
        mapping.setdefault(node.name, node.file_path)
    return mapping


def file_level_edges(nodes: list[CodeNode]) -> list[dict]:
    defined = {n.name for n in nodes}
    files = _file_of(nodes)
    counts: Counter = Counter()
    for node in nodes:
        for call in node.calls:
            if call not in defined:
                continue
            target_file = files.get(call)
            if not target_file or target_file == node.file_path:
                continue
            counts[(node.file_path, target_file)] += 1
    return [{"source": s, "target": t, "count": c} for (s, t), c in sorted(counts.items())]


def _short_desc(node: CodeNode) -> str:
    text = (node.docstring or "").strip()
    if text:
        first = text.splitlines()[0].strip()
        return first[:120]
    return (node.signature or "").strip()[:120]


def graph_data(nodes: list[CodeNode], max_nodes: int = 400, max_edges: int = 800) -> dict:
    graph = build_call_graph(nodes)
    files = _file_of(nodes)
    node_by_name: dict[str, CodeNode] = {}
    for node in nodes:
        node_by_name.setdefault(node.name, node)
    in_deg: Counter = Counter()
    out_deg: Counter = Counter()
    edges: list[tuple[str, str]] = []
    for caller, callees in graph.items():
        for callee in callees:
            if caller == callee:
                continue
            edges.append((caller, callee))
            in_deg[callee] += 1
            out_deg[caller] += 1

    truncated = len(edges) > max_edges
    edges = edges[:max_edges]
    used = set()
    for source, target in edges:
        used.add(source)
        used.add(target)
    node_ids = sorted(used, key=lambda name: (-(in_deg[name] + out_deg[name]), name))
    if len(node_ids) > max_nodes:
        node_ids = node_ids[:max_nodes]
        truncated = True
    allowed = set(node_ids)
    edges = [(s, t) for s, t in edges if s in allowed and t in allowed]
    def describe(name: str) -> str:
        node = node_by_name.get(name)
        return _short_desc(node) if node else ""

    return {
        "nodes": [
            {"id": n, "file": files.get(n, ""), "desc": describe(n), "in": in_deg[n], "out": out_deg[n]}
            for n in node_ids
        ],
        "edges": [{"source": s, "target": t} for s, t in edges],
        "truncated": truncated,
    }


def graph_to_mermaid(graph: dict[str, list[str]], max_edges: int = 150) -> str:
    edges = []
    for caller, callees in graph.items():
        for callee in callees:
            if caller == callee:
                continue
            edges.append((caller, callee))
    truncated = len(edges) > max_edges
    edges = edges[:max_edges]
    lines = ["```mermaid", "graph TD"]
    for caller, callee in edges:
        lines.append(f"    {caller}[{caller}] --> {callee}[{callee}]")
    if truncated:
        lines.append(f'    truncated_note["⚠ 关系过多，仅显示前 {max_edges} 条"]')
    lines.append("```")
    return "\n".join(lines)