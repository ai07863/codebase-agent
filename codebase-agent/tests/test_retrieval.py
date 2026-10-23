from retrieval.vector_store import VectorStore, SearchResult, _node_text
from retrieval.ast_index import ASTIndex
from retrieval.bm25_index import BM25Index
from retrieval.hybrid_search import hybrid_search, diversify
from code_parser.ast_parser import CodeNode
from embedding.embedder import Embedder


def _make_node(node_id, name, signature="", docstring="", file_path="test.py"):
    return CodeNode(node_id=node_id, type="function", name=name, file_path=file_path,
                    start_line=1, end_line=3, signature=signature, docstring=docstring, calls=[])


class _EmptyVectorStore:
    def search(self, query, embedder, k):
        return []


class _OneHitVectorStore:
    def search(self, query, embedder, k):
        return [SearchResult(node_id="x", name="OtherThing", file_path="x.py",
                             start_line=1, end_line=2, score=0.1)]


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


def test_node_text_includes_name_docstring_and_body():
    node = CodeNode(node_id="a", type="function", name="run_stream", file_path="x.py",
                    start_line=1, end_line=3, signature="def run_stream():",
                    docstring="流式执行", calls=[],
                    body="def run_stream():\n    handle_low_confidence()")
    text = _node_text(node)
    assert "run_stream" in text
    assert "流式执行" in text
    assert "handle_low_confidence" in text


def test_node_text_truncates_long_body():
    node = CodeNode(node_id="a", type="function", name="big", file_path="x.py",
                    start_line=1, end_line=3, signature="def big():", docstring="",
                    calls=[], body="x" * 10000)
    assert len(_node_text(node)) <= 2000


def test_bm25_matches_chinese_query():
    nodes = [
        _make_node("a", "run_stream", "def run_stream():", "低置信度时追加转人工提示"),
        _make_node("b", "get_rates", "def get_rates():", "查询实时汇率"),
    ]
    results = BM25Index(nodes).search("低置信度怎么处理", k=1)
    assert results
    assert results[0].name == "run_stream"


def test_bm25_ranks_lexical_match_first():
    nodes = [
        _make_node("a", "greet", "def greet():", "Say hello to someone"),
        _make_node("b", "parse_config", "def parse_config():", "Parse the configuration file"),
        _make_node("c", "render_json", "def render_json():", "Render a JSON response"),
    ]
    results = BM25Index(nodes).search("parse configuration", k=3)
    assert results
    assert results[0].name == "parse_config"


def test_bm25_empty_index_returns_no_results():
    assert BM25Index([]).search("anything") == []


def test_bm25_splits_camel_case_and_snake_case():
    nodes = [
        _make_node("a", "SessionManager", "class SessionManager:", "Handles user sessions"),
        _make_node("b", "parse_config_file", "def parse_config_file():", "Read settings"),
    ]
    idx = BM25Index(nodes)
    assert idx.search("session manager", k=1)[0].name == "SessionManager"
    assert idx.search("config file", k=1)[0].name == "parse_config_file"


def test_hybrid_search_keeps_exact_ast_hit_within_k():
    nodes = [_make_node("a", "SessionManager", "class SessionManager:", "Manages sessions")]
    ast_index = ASTIndex(nodes)
    results = hybrid_search("SessionManager", _OneHitVectorStore(), ast_index, None, k=1)
    assert len(results) == 1
    assert results[0].node_id == "a"


def test_diversify_caps_results_per_file():
    results = [
        SearchResult(node_id=f"a{i}", name="x", file_path="a.py", start_line=1, end_line=2, score=0.0)
        for i in range(5)
    ] + [SearchResult(node_id="b0", name="y", file_path="b.py", start_line=1, end_line=2, score=0.0)]
    out = diversify(results, k=4, per_file=2)
    assert [r.node_id for r in out] == ["a0", "a1", "b0"]


def test_hybrid_search_uses_vector_results_when_no_lexical_match():
    nodes = [_make_node("a", "greet", "def greet():", "Say hello")]
    ast_index = ASTIndex(nodes)
    results = hybrid_search("completely unrelated phrase", _OneHitVectorStore(), ast_index, None, k=2)
    assert any(r.node_id == "x" for r in results)