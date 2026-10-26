from agent.router import classify_query, is_overview_query
from agent.tools.ast_search import ast_search_tool
from agent.tools.file_reader import read_file_tool


def test_classify_query():
    assert classify_query("where is the greet function defined?") == "exact"
    assert classify_query("how does authentication work?") == "semantic"


def test_classify_query_ignores_punctuation():
    assert classify_query("Where is Frobnicate() defined?") == "exact"
    assert classify_query("Which class handles requests?") == "exact"
    assert classify_query("How does the auth flow work?") == "semantic"


def test_is_overview_query():
    assert is_overview_query("这个项目的总体框架是什么")
    assert is_overview_query("Describe the overall architecture")
    assert is_overview_query("项目结构是怎么组织的")
    assert not is_overview_query("where is Session defined")
    assert not is_overview_query("How does authentication work?")


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


class _EmptyVectorStore:
    def search(self, query, embedder, k):
        return []


def _session_index():
    from retrieval.ast_index import ASTIndex
    from code_parser.ast_parser import CodeNode
    nodes = [CodeNode(node_id="a", type="function", name="Session", file_path="s.py",
                      start_line=1, end_line=2, signature="def Session():", docstring="", calls=[])]
    return ASTIndex(nodes)


def test_retrieve_exact_route_returns_ast_hit():
    from agent.react_loop import _retrieve
    results = _retrieve("where is Session defined", _EmptyVectorStore(), _session_index(), None, "exact")
    assert results
    assert results[0].node_id == "a"


def test_retrieve_semantic_route_uses_lexical_match():
    from agent.react_loop import _retrieve
    results = _retrieve("Session", _EmptyVectorStore(), _session_index(), None, "semantic")
    assert results
    assert results[0].node_id == "a"


def test_choose_identifier_prefers_existing_name():
    from agent.react_loop import _choose_identifier
    idx = _session_index()
    assert _choose_identifier("where is the Session defined", idx) == "Session"
    assert _choose_identifier("the login method in Session class", idx) == "Session"


def test_build_messages_includes_history():
    from agent.react_loop import _build_messages
    history = [
        {"role": "user", "content": "where is Session"},
        {"role": "assistant", "content": "in s.py"},
        {"role": "system", "content": "IGNORED"},
    ]
    msgs = _build_messages("那它调用谁", "CTX_BODY", False, history)
    assert msgs[0]["role"] == "system"
    assert any(m["content"] == "in s.py" for m in msgs)
    assert not any(m["content"] == "IGNORED" for m in msgs)
    assert msgs[-1]["role"] == "user"
    assert "CTX_BODY" in msgs[-1]["content"]


def test_build_messages_includes_recall():
    from agent.react_loop import _build_messages
    recall = [{"role": "assistant", "text": "早期回答：融合用 RRF"}]
    msgs = _build_messages("那它调用谁", "CTX_BODY", False, [], recall)
    system_text = "\n".join(m["content"] for m in msgs if m["role"] == "system")
    assert "RRF" in system_text


def test_build_user_message_adds_diagram_instruction_for_overview():
    from agent.react_loop import _build_user_message
    msg = _build_user_message("说说总体框架", "CONTEXT_BODY", overview=True)
    assert "mermaid" in msg
    assert "CONTEXT_BODY" in msg
    plain = _build_user_message("where is Session defined", "CONTEXT_BODY", overview=False)
    assert "mermaid" not in plain
    assert "CONTEXT_BODY" in plain


def test_build_context_includes_project_map():
    import tempfile
    from pathlib import Path
    from agent.react_loop import _build_context
    from retrieval.vector_store import SearchResult

    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "m.py").write_text("def f():\n    pass\n")
        results = [SearchResult(node_id="n", name="f", file_path="m.py",
                                start_line=1, end_line=2, score=0.0)]
        context = _build_context(results, tmp, project_map="m.py (1)")
        assert "Project structure" in context
        assert "m.py (1)" in context
        assert "def f()" in context


def test_read_snippet_reads_requested_lines():
    import tempfile
    from pathlib import Path
    from agent.react_loop import _read_snippet

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "mod.py"
        src.write_text("line1\nline2\nline3\nline4\n")
        snippet = _read_snippet(tmp, "mod.py", 2, 3)
        assert "line2" in snippet
        assert "line3" in snippet
        assert "line1" not in snippet


def test_read_snippet_missing_file_returns_empty():
    from agent.react_loop import _read_snippet

    assert _read_snippet("does_not_exist_dir", "nope.py", 1, 5) == ""


def test_extract_identifier_from_question():
    from agent.react_loop import _extract_identifier

    assert _extract_identifier("where is Session defined") == "Session"
    assert _extract_identifier("find the parse_repo function") == "parse_repo"