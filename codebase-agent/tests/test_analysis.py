from analysis.pr_diff import parse_github_url, _parse_diff
from analysis.report import generate_report


def test_parse_github_url():
    url = "https://github.com/gin-gonic/gin/pull/123"
    info = parse_github_url(url)
    assert info is not None
    assert info.owner == "gin-gonic"
    assert info.repo == "gin"
    assert info.number == 123


def test_parse_github_url_invalid():
    assert parse_github_url("https://example.com") is None


def test_parse_diff():
    raw = """diff --git a/main.py b/main.py
index abc..def 100644
--- a/main.py
+++ b/main.py
@@ -1,3 +1,4 @@
 def greet():
-    return "hello"
+    return "hello world"
+    print("new line")
"""
    files = _parse_diff(raw)
    assert len(files) == 1
    assert files[0].path == "main.py"
    assert files[0].additions > 0
    assert files[0].deletions > 0