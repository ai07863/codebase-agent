from pathlib import Path
from code_parser.ast_parser import CodeNode, parse_repo
from code_parser.relationship import find_callers, build_call_graph
from analysis.pr_diff import ChangedFile, PRDiff


def analyze_impact(diff: PRDiff, repo_path: str) -> dict:
    nodes = parse_repo(repo_path)
    call_graph = build_call_graph(nodes)
    caller_cache = {}
    for node in nodes:
        callers = find_callers(nodes, node.name)
        if callers:
            caller_cache[node.name] = callers

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
        "risk_score": _calculate_risk(changed_functions, impacted, nodes),
    }


def _find_changed_functions(files: list[ChangedFile], nodes: list[CodeNode]) -> list[str]:
    changed = []
    for f in files:
        for node in nodes:
            if node.file_path == f.path:
                changed.append(node.name)
    return list(set(changed))


def _calculate_risk(changed_functions: list[str], impacted: dict, nodes: list[CodeNode]) -> str:
    if not changed_functions:
        return "none"

    total_callers = sum(len(v) for v in impacted.values())
    node_map = {n.name: n for n in nodes}
    func_complexity = sum(len(node_map.get(f, CodeNode(node_id="", type="", name="",
        file_path="", start_line=0, end_line=0, signature="", docstring="")))
        .signature for f in changed_functions)

    if total_callers > 20 or len(changed_functions) > 10 or func_complexity > 500:
        return "high"
    elif total_callers > 5 or len(changed_functions) > 3:
        return "medium"
    return "low"