from code_parser.ast_parser import CodeNode
from retrieval.vector_store import SearchResult


class ASTIndex:
    def __init__(self, nodes: list[CodeNode]):
        self.by_name: dict[str, CodeNode] = {}
        self.by_file: dict[str, list[CodeNode]] = {}
        for node in nodes:
            self.by_name[node.name] = node
            self.by_file.setdefault(node.file_path, []).append(node)

    def lookup(self, name: str) -> CodeNode | None:
        return self.by_name.get(name)

    def search_by_name(self, query: str) -> list[SearchResult]:
        q = query.lower()
        results = []
        for name, node in self.by_name.items():
            if q in name.lower():
                results.append(SearchResult(
                    node_id=node.node_id,
                    name=node.name,
                    file_path=node.file_path,
                    start_line=node.start_line,
                    end_line=node.end_line,
                    score=0.0,
                ))
        return results