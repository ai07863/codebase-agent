import ssl as _ssl
from analysis.pr_diff import parse_github_url, _parse_diff, _ssl_verify, PRInfo, PRDiff, ChangedFile
from analysis.impact import _extract_changed_lines
from analysis.report import generate_report, format_report


def test_format_report_is_chinese_and_includes_summary():
    diff = PRDiff(
        pr=PRInfo("owner", "repo", 7, "修复登录", "描述内容", "main", "feature"),
        files=[ChangedFile("a.py", 2, 1, "", "modified")],
    )
    impact = {
        "total_files": 1,
        "total_additions": 2,
        "total_deletions": 1,
        "changed_functions": ["login"],
        "impacted_callers": {"login": ["handle"]},
        "file_breakdown": [{
            "file": "a.py", "status": "modified", "additions": 2, "deletions": 1,
            "affected_functions": ["login"], "total_functions_in_file": 3,
        }],
        "risk_score": "medium",
    }
    report = format_report(diff, impact, summary="这个 PR 修改了登录逻辑。")
    md = report["markdown_report"]
    assert "AI 总结" in md
    assert "这个 PR 修改了登录逻辑。" in md
    assert "风险" in md
    assert "变更文件" in md
    assert report["summary"] == "这个 PR 修改了登录逻辑。"


def test_ssl_verify_returns_context_or_true():
    verify = _ssl_verify()
    assert verify is True or isinstance(verify, _ssl.SSLContext)


def test_parse_github_url():
    url = "https://github.com/gin-gonic/gin/pull/123"
    info = parse_github_url(url)
    assert info is not None
    assert info.owner == "gin-gonic"
    assert info.repo == "gin"
    assert info.number == 123


def test_parse_github_url_invalid():
    assert parse_github_url("https://example.com") is None


def test_parse_diff_counts_real_changed_lines():
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
    assert files[0].additions == 2
    assert files[0].deletions == 1


def test_parse_diff_detects_added_deleted_and_renamed_files():
    raw = (
        "diff --git a/newfile.py b/newfile.py\n"
        "new file mode 100644\n"
        "index 0000000..abc1234\n"
        "--- /dev/null\n"
        "+++ b/newfile.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+line one\n"
        "+line two\n"
        "diff --git a/gone.py b/gone.py\n"
        "deleted file mode 100644\n"
        "index abc1234..0000000\n"
        "--- a/gone.py\n"
        "+++ /dev/null\n"
        "@@ -1,2 +0,0 @@\n"
        "-line one\n"
        "-line two\n"
        "diff --git a/old.py b/new.py\n"
        "similarity index 90%\n"
        "rename from old.py\n"
        "rename to new.py\n"
        "index abc1234..def5678 100644\n"
        "--- a/old.py\n"
        "+++ b/new.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-old\n"
        "+new\n"
    )
    files = {f.path: f for f in _parse_diff(raw)}
    assert set(files) == {"newfile.py", "gone.py", "new.py"}
    assert files["newfile.py"].status == "added"
    assert files["newfile.py"].additions == 2
    assert files["gone.py"].status == "deleted"
    assert files["gone.py"].deletions == 2
    assert files["new.py"].status == "renamed"
    assert files["new.py"].additions == 1
    assert files["new.py"].deletions == 1


def test_extract_changed_lines_counts_pure_deletions():
    raw = (
        "diff --git a/mod.py b/mod.py\n"
        "index abc..def 100644\n"
        "--- a/mod.py\n"
        "+++ b/mod.py\n"
        "@@ -10,3 +10,1 @@\n"
        " context\n"
        "-removed one\n"
        "-removed two\n"
    )
    files = _parse_diff(raw)
    changed = _extract_changed_lines(files)
    assert changed["mod.py"] == {11}


def test_extract_changed_lines_maps_only_added_new_lines():
    raw = (
        "diff --git a/mod.py b/mod.py\n"
        "index abc..def 100644\n"
        "--- a/mod.py\n"
        "+++ b/mod.py\n"
        "@@ -10,4 +10,6 @@ def foo():\n"
        " context = 1\n"
        "-removed\n"
        "+added one\n"
        "+added two\n"
        " context = 2\n"
    )
    files = _parse_diff(raw)
    changed = _extract_changed_lines(files)
    assert changed["mod.py"] == {11, 12}