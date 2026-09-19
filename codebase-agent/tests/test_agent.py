from agent.router import classify_query
from agent.tools.ast_search import ast_search_tool
from agent.tools.file_reader import read_file_tool


def test_classify_query():
    assert classify_query("where is the greet function defined?") == "exact"
    assert classify_query("how does authentication work?") == "semantic"


def test_ast_search_tool():
    from retrieval.ast_index import ASTIndex
    from code_parser.ast_parser import CodeNode
    nodes = [
        CodeNode(node_id="a", type="function", name="greet", file_path="test.py",
                 start_line=1, end_line=3, signature="def greet():", docstring="", calls=[]),
    ]
    idx = ASTIndex(nodes)
    result = ast_search_tool("greet", idx)
    assert "greet" in result


def test_read_file_tool():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "test.py"
        f.write_text("def foo():\n    pass\n")
        result = read_file_tool(str(f), 1, 2)
        assert "def foo()" in result