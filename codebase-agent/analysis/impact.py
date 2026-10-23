import re
from code_parser.ast_parser import CodeNode, parse_repo
from code_parser.relationship import find_callers
from analysis.pr_diff import ChangedFile, PRDiff


_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _extract_changed_lines(files: list[ChangedFile]) -> dict[str, set[int]]:
    changed_lines: dict[str, set[int]] = {}
    for f in files:
        lines: set[int] = set()
        new_line_no = 0
        for line in f.patch.split("\n"):
            m = _HUNK_RE.match(line)
            if m:
                new_line_no = int(m.group(1))
                continue
            if line.startswith("+++") or line.startswith("---"):
                continue
            if line.startswith("+"):
                lines.add(new_line_no)
                new_line_no += 1
            elif line.startswith("-"):
                continue
            elif line.startswith(" "):
                new_line_no += 1
        if lines:
            changed_lines[f.path] = lines
    return changed_lines


def _find_changed_functions(files: list[ChangedFile], nodes: list[CodeNode]) -> list[str]:
    changed_lines = _extract_changed_lines(files)
    if not changed_lines:
        return []

    changed = set()
    for node in nodes:
        file_lines = changed_lines.get(node.file_path)
        if file_lines:
            func_lines = set(range(node.start_line, node.end_line + 1))
            if func_lines & file_lines:
                changed.add(node.name)
    return list(changed)


def _calculate_risk(changed_functions: list[str], impacted: dict) -> str:
    if not changed_functions:
        return "none"

    total_callers = sum(len(v) for v in impacted.values())
    if total_callers > 15 or len(changed_functions) > 8:
        return "high"
    elif total_callers > 3 or len(changed_functions) > 2:
        return "medium"
    return "low"


def analyze_impact(diff: PRDiff, repo_path: str) -> dict:
    nodes = parse_repo(repo_path)
    changed_functions = _find_changed_functions(diff.files, nodes)

    impacted = {}
    for func in changed_functions:
        callers = find_callers(nodes, func)
        impacted[func] = callers if callers else []

    file_breakdown = []
    for f in diff.files:
        file_funcs = [n for n in nodes if n.file_path == f.path]
        affected_funcs = [n.name for n in file_funcs if n.name in changed_functions]
        file_breakdown.append({
            "file": f.path,
            "status": f.status,
            "additions": f.additions,
            "deletions": f.deletions,
            "affected_functions": affected_funcs,
            "total_functions_in_file": len(file_funcs),
        })

    return {
        "total_files": len(diff.files),
        "total_additions": sum(f.additions for f in diff.files),
        "total_deletions": sum(f.deletions for f in diff.files),
        "changed_functions": changed_functions,
        "impacted_callers": impacted,
        "file_breakdown": file_breakdown,
        "risk_score": _calculate_risk(changed_functions, impacted),
    }