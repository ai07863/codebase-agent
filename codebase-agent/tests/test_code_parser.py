import tempfile
from pathlib import Path
from code_parser.ast_parser import CodeNode, parse_repo


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