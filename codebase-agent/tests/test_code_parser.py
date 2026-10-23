import tempfile
from pathlib import Path
from code_parser.ast_parser import CodeNode, parse_repo, _normalize_call_name, _iter_source_files
from code_parser.relationship import (
    build_call_graph,
    graph_to_mermaid,
    build_project_map,
    file_level_edges,
    graph_data,
)


def _node(node_id, name, calls=None, file_path="x.py"):
    return CodeNode(node_id=node_id, type="function", name=name, file_path=file_path,
                    start_line=1, end_line=2, signature="", docstring="", calls=calls or [])


def test_normalize_call_name_strips_attribute_chains():
    assert _normalize_call_name("self.foo") == "foo"
    assert _normalize_call_name("cls.build") == "build"
    assert _normalize_call_name("pkg.mod.func") == "func"
    assert _normalize_call_name("plain") == "plain"


def test_iter_source_files_skips_ignored_and_hidden_dirs():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "pkg").mkdir()
        (root / "pkg" / "mod.py").write_text("x = 1")
        (root / "node_modules").mkdir()
        (root / "node_modules" / "dep.js").write_text("x")
        (root / ".git").mkdir()
        (root / ".git" / "hook.py").write_text("x")
        (root / "app.py").write_text("x = 1")
        (root / "notes.txt").write_text("x")
        found = {p.name for p in _iter_source_files(root)}
        assert found == {"app.py", "mod.py"}


def test_iter_source_files_respects_max_size():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "big.py").write_text("a" * 100)
        (root / "small.py").write_text("a")
        found = {p.name for p in _iter_source_files(root, max_bytes=10)}
        assert found == {"small.py"}


def test_build_call_graph_merges_duplicate_names():
    nodes = [
        _node("a1", "__init__", calls=["setup"]),
        _node("b1", "__init__", calls=["teardown"], file_path="y.py"),
        _node("s", "setup"),
        _node("t", "teardown"),
    ]
    graph = build_call_graph(nodes)
    assert set(graph["__init__"]) == {"setup", "teardown"}


def test_graph_to_mermaid_skips_self_loops_and_caps_edges():
    graph = {"a": ["a", "b"], "b": ["c"], "c": ["d"]}
    out = graph_to_mermaid(graph, max_edges=2)
    assert "a[a] --> a[a]" not in out
    assert out.count("-->") == 2


def test_file_level_edges_aggregate_calls_between_files():
    nodes = [
        _node("a", "f", calls=["g"], file_path="a.py"),
        _node("b", "g", calls=[], file_path="b.py"),
        _node("c", "h", calls=["g"], file_path="a.py"),
        _node("d", "self_call", calls=["f"], file_path="a.py"),
    ]
    edges = file_level_edges(nodes)
    assert {"source": "a.py", "target": "b.py", "count": 2} in edges
    assert all(e["source"] != e["target"] for e in edges)


def test_graph_data_returns_nodes_and_edges():
    nodes = [
        _node("a", "f", calls=["g"], file_path="a.py"),
        _node("b", "g", calls=[], file_path="b.py"),
    ]
    data = graph_data(nodes)
    assert {n["id"] for n in data["nodes"]} == {"f", "g"}
    assert {"source": "f", "target": "g"} in data["edges"]
    assert data["truncated"] is False


def test_graph_data_includes_function_description():
    nodes = [
        CodeNode(node_id="a", type="function", name="f", file_path="a.py",
                 start_line=1, end_line=2, signature="def f():", docstring="", calls=["g"]),
        CodeNode(node_id="b", type="function", name="g", file_path="b.py",
                 start_line=1, end_line=2, signature="def g():", docstring="获取订单状态。\n更多说明", calls=[]),
    ]
    data = graph_data(nodes)
    by_id = {n["id"]: n for n in data["nodes"]}
    assert by_id["g"]["desc"] == "获取订单状态。"
    assert by_id["f"]["desc"] == "def f():"


def test_build_project_map_lists_files_with_counts():
    nodes = [
        _node("a", "f", file_path="pkg/a.py"),
        _node("b", "g", file_path="pkg/a.py"),
        _node("c", "h", file_path="pkg/b.py"),
    ]
    text = build_project_map(nodes)
    assert "pkg/a.py (2)" in text
    assert "pkg/b.py (1)" in text


def test_build_project_map_truncates_many_files():
    nodes = [_node(str(i), f"f{i}", file_path=f"pkg/f{i}.py") for i in range(10)]
    text = build_project_map(nodes, max_files=3)
    assert "pkg/f0.py (1)" in text
    assert "pkg/f3.py (1)" not in text
    assert "more" in text.lower()


def test_parse_python_function():
    code = """
def greet(name: str) -> str:
    \"\"\"Say hello to someone.\"\"\"
    return f"Hello, {name}"
"""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "test.py"
        src.write_text(code)
        nodes = parse_repo(tmp)
        funcs = [n for n in nodes if n.type == "function"]
        assert len(funcs) == 1
        assert funcs[0].name == "greet"
        assert "hello" in funcs[0].docstring


def test_parse_python_class():
    code = """
class Calculator:
    \"\"\"A simple calculator.\"\"\"
    def add(self, a: int, b: int) -> int:
        return a + b
"""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "test.py"
        src.write_text(code)
        nodes = parse_repo(tmp)
        classes = [n for n in nodes if n.type == "class"]
        assert len(classes) == 1
        assert classes[0].name == "Calculator"