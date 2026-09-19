from retrieval.vector_store import VectorStore
from retrieval.ast_index import ASTIndex
from retrieval.hybrid_search import hybrid_search
from code_parser.ast_parser import CodeNode
from embedding.embedder import Embedder


def test_vector_store_add_and_search():
    nodes = [
        CodeNode(node_id="a", type="function", name="greet", file_path="test.py",
                 start_line=1, end_line=3, signature="def greet():", docstring="Say hello", calls=[]),
        CodeNode(node_id="b", type="function", name="add", file_path="test.py",
                 start_line=5, end_line=7, signature="def add(a,b):", docstring="Add two numbers", calls=[]),
    ]
    embedder = Embedder()
    vs = VectorStore(repo_name="test")
    vs.add(nodes, embedder)
    results = vs.search("add two numbers", embedder, k=2)
    assert len(results) > 0
    assert results[0].node_id == "b"


def test_ast_index_lookup():
    nodes = [
        CodeNode(node_id="a", type="function", name="greet", file_path="test.py",
                 start_line=1, end_line=3, signature="def greet():", docstring="", calls=[]),
    ]
    idx = ASTIndex(nodes)
    result = idx.lookup_one("greet")
    assert result is not None
    assert result.name == "greet"