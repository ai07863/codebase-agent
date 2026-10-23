import pytest
from web.files import resolve_repo_file, slice_lines


def test_slice_lines_returns_window_around_range():
    text = "\n".join(f"line{i}" for i in range(1, 101))
    window = slice_lines(text, 50, 52, context=5, max_lines=400)
    assert window["first_line"] == 45
    assert "line45" in window["content"]
    assert "line50" in window["content"]
    assert "line1\n" not in window["content"]
    assert window["total_lines"] == 100


def test_slice_lines_caps_window_when_no_range():
    text = "\n".join(f"line{i}" for i in range(1, 1001))
    window = slice_lines(text, 1, 0, max_lines=50)
    assert window["content"].count("\n") + 1 <= 50
    assert window["first_line"] == 1


def test_resolve_repo_file_returns_file_inside_root(tmp_path):
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "a.py").write_text("x = 1")
    assert resolve_repo_file(root, "pkg/a.py").name == "a.py"


def test_resolve_repo_file_rejects_traversal(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "secret.txt").write_text("secret")
    with pytest.raises(ValueError):
        resolve_repo_file(root, "../secret.txt")


def test_resolve_repo_file_missing_raises(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    with pytest.raises(FileNotFoundError):
        resolve_repo_file(root, "missing.py")


def test_resolve_repo_file_falls_back_to_basename_and_partial_path(tmp_path):
    root = tmp_path / "repo"
    (root / "backend" / "app").mkdir(parents=True)
    (root / "backend" / "app" / "react_agent.py").write_text("x = 1")
    assert resolve_repo_file(root, "react_agent.py").name == "react_agent.py"
    assert resolve_repo_file(root, "app/react_agent.py").name == "react_agent.py"
    assert resolve_repo_file(root, "backend\\app\\react_agent.py").name == "react_agent.py"


def test_resolve_repo_file_lowercase_basename_match(tmp_path):
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "LangChain.py").write_text("x = 1")
    assert resolve_repo_file(root, "langchain.py").name == "LangChain.py"