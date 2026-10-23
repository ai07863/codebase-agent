from collections import defaultdict
from code_parser.ast_parser import CodeNode
from retrieval.vector_store import SearchResult
from retrieval.bm25_index import BM25Index


class ASTIndex:
    def __init__(self, nodes: list[CodeNode]):
        self.nodes: list[CodeNode] = list(nodes)
        self.by_name: dict[str, list[CodeNode]] = defaultdict(list)
        self.by_file: dict[str, list[CodeNode]] = defaultdict(list)
        for node in nodes:
            self.by_name[node.name].append(node)
            self.by_file[node.file_path].append(node)
        self.bm25 = BM25Index(self.nodes)

    def lookup(self, name: str) -> list[CodeNode]:
        return self.by_name.get(name, [])

    def lookup_one(self, name: str) -> CodeNode | None:
        results = self.by_name.get(name, [])
        return results[0] if results else None

    def search_by_name(self, query: str) -> list[SearchResult]:
        q = query.lower()
        results = []
        for name, nodes in self.by_name.items():
            if q in name.lower():
                for node in nodes:
                    results.append(SearchResult(
                        node_id=node.node_id,
                        name=node.name,
                        file_path=node.file_path,
                        start_line=node.start_line,
                        end_line=node.end_line,
                        score=0.0,
                    ))
        return results
