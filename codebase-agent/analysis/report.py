from analysis.pr_diff import PRDiff
from analysis.impact import analyze_impact


def generate_report(diff: PRDiff, repo_path: str) -> dict:
    impact = analyze_impact(diff, repo_path)

    sections = []
    sections.append(f"# PR #{diff.pr.number}: {diff.pr.title}")
    sections.append("")
    sections.append(f"**Repo:** {diff.pr.owner}/{diff.pr.repo}")
    sections.append(f"**Branch:** {diff.pr.base_branch} ← {diff.pr.head_branch}")
    sections.append("")
    if diff.pr.description:
        sections.append(f"> {diff.pr.description}")
        sections.append("")

    sections.append("## Summary")
    sections.append(f"- {impact['total_files']} files changed")
    sections.append(f"- +{impact['total_additions']}/-{impact['total_deletions']} lines")
    sections.append(f"- {len(impact['changed_functions'])} functions affected")
    sections.append(f"- Risk: **{impact['risk_score'].upper()}**")
    sections.append("")

    sections.append("## Files Changed")
    for fb in impact["file_breakdown"]:
        emoji = {"added": "🟢", "modified": "🟡", "deleted": "🔴"}.get(fb["status"], "⚪")
        sections.append(f"### {emoji} {fb['file']} ({fb['status']})")
        sections.append(f"- +{fb['additions']}/-{fb['deletions']} lines")
        sections.append(f"- {len(fb['affected_functions'])}/{fb['total_functions_in_file']} functions touched")
        if fb['affected_functions']:
            sections.append(f"- Functions: `{'`, `'.join(fb['affected_functions'])}`")
        sections.append("")

    sections.append("## Impact Analysis")
    if impact["impacted_callers"]:
        sections.append("Functions that may be affected by these changes:")
        for func, callers in impact["impacted_callers"].items():
            if callers:
                sections.append(f"- `{func}` is called by: `{'`, `'.join(callers)}`")
        sections.append("")
    else:
        sections.append("No downstream callers detected.")
        sections.append("")

    sections.append("## Risk Assessment")
    risk = impact["risk_score"]
    if risk == "high":
        sections.append("⚠️ **High Risk** — Large change with broad impact. Recommend thorough review and testing.")
    elif risk == "medium":
        sections.append("⚡ **Medium Risk** — Moderate change. Review impacted areas carefully.")
    else:
        sections.append("✅ **Low Risk** — Small, contained change.")

    return {
        "pr_number": diff.pr.number,
        "title": diff.pr.title,
        "repo": f"{diff.pr.owner}/{diff.pr.repo}",
        "base_branch": diff.pr.base_branch,
        "head_branch": diff.pr.head_branch,
        "risk_score": impact["risk_score"],
        "stats": {
            "files_changed": impact["total_files"],
            "additions": impact["total_additions"],
            "deletions": impact["total_deletions"],
            "functions_affected": len(impact["changed_functions"]),
        },
        "files": impact["file_breakdown"],
        "impacted_callers": impact["impacted_callers"],
        "markdown_report": "\n".join(sections),
    }