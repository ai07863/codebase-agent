import time
from code_parser.repo_cache import parse_repo_cached, source_fingerprint


def _repo_with_file(tmp_path, content="x=1"):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text(content)
    return root


def test_parse_repo_cached_reuses_cache(tmp_path):
    root = _repo_with_file(tmp_path)
    cache = tmp_path / "cache"
    calls = {"n": 0}

    def parser(_path):
        calls["n"] += 1
        return []

    parse_repo_cached(root, cache, parser=parser)
    parse_repo_cached(root, cache, parser=parser)
    assert calls["n"] == 1


def test_parse_repo_cached_reparses_after_change(tmp_path):
    root = _repo_with_file(tmp_path)
    cache = tmp_path / "cache"
    calls = {"n": 0}

    def parser(_path):
        calls["n"] += 1
        return []

    parse_repo_cached(root, cache, parser=parser)
    time.sleep(0.01)
    (root / "a.py").write_text("x = 2  # changed")
    parse_repo_cached(root, cache, parser=parser)
    assert calls["n"] == 2


def test_source_fingerprint_changes_with_content(tmp_path):
    root = _repo_with_file(tmp_path)
    before = source_fingerprint(root)
    time.sleep(0.01)
    (root / "a.py").write_text("totally different")
    assert source_fingerprint(root) != before