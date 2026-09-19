from code_parser.ast_parser import CodeNode


def build_call_graph(nodes: list[CodeNode]) -> dict[str, list[str]]:
    graph = {}
    node_map = {n.name: n for n in nodes}
    for node in nodes:
        graph[node.name] = [c for c in node.calls if c in node_map]
    return graph


def find_callers(nodes: list[CodeNode], target_name: str) -> list[str]:
    return [n.name for n in nodes if target_name in n.calls]