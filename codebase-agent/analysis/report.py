import logging
from analysis.pr_diff import PRDiff
from analysis.impact import analyze_impact


logger = logging.getLogger("codebase-agent.pr")

_STATUS_ZH = {"added": "新增", "modified": "修改", "deleted": "删除", "renamed": "重命名"}
_RISK_ZH = {"high": "高", "medium": "中", "low": "低", "none": "无"}


def _llm_summary(impact: dict, diff: PRDiff, settings) -> str:
    try:
        from openai import OpenAI

        files = "\n".join(
            "- {file}（{status}，+{add}/-{dele}，触及函数：{funcs}）".format(
                file=fb["file"],
                status=_STATUS_ZH.get(fb["status"], fb["status"]),
                add=fb["additions"],
                dele=fb["deletions"],
                funcs="、".join(fb["affected_functions"]) or "无",
            )
            for fb in impact["file_breakdown"]
        )
        callers = "\n".join(
            "- {fn} 被这些函数调用：{cs}".format(fn=fn, cs="、".join(cs))
            for fn, cs in impact["impacted_callers"].items()
            if cs
        ) or "无"

        prompt = (
            f"PR 标题：{diff.pr.title}\n"
            f"PR 描述：{(diff.pr.description or '')[:500]}\n\n"
            f"变更文件：\n{files}\n\n"
            f"可能受影响的下游调用：\n{callers}\n\n"
            f"系统评估的风险等级：{_RISK_ZH.get(impact['risk_score'], impact['risk_score'])}\n\n"
            "请用简体中文写一段简明总结：这个 PR 改了什么、影响哪些模块或函数、可能的风险点。"
            "3-6 句话，让不懂代码的人也大致能看懂；不要逐条罗列文件路径。"
        )
        client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        resp = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": "你是代码评审助手，用简体中文简洁地回答。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            timeout=60,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.warning("PR 总结生成失败：%s", exc)
        return ""


def format_report(diff: PRDiff, impact: dict, summary: str = "") -> dict:
    sections = []
    sections.append(f"# PR #{diff.pr.number}：{diff.pr.title}")
    sections.append("")
    sections.append(f"**仓库：** {diff.pr.owner}/{diff.pr.repo}")
    sections.append(f"**分支：** {diff.pr.base_branch} ← {diff.pr.head_branch}")
    sections.append("")
    if diff.pr.description:
        sections.append(f"> {diff.pr.description}")
        sections.append("")

    sections.append("## AI 总结")
    sections.append(summary or "（未生成 AI 总结，可能是模型不可用）")
    sections.append("")

    sections.append("## 概览")
    sections.append(f"- 变更文件：{impact['total_files']} 个")
    sections.append(f"- 代码增删：+{impact['total_additions']} / -{impact['total_deletions']} 行")
    sections.append(f"- 受影响函数：{len(impact['changed_functions'])} 个")
    sections.append(f"- 风险等级：{_RISK_ZH.get(impact['risk_score'], impact['risk_score'])}")
    sections.append("")

    sections.append("## 变更文件")
    for fb in impact["file_breakdown"]:
        status = _STATUS_ZH.get(fb["status"], fb["status"])
        sections.append(f"### {fb['file']}（{status}）")
        sections.append(f"- 增删：+{fb['additions']} / -{fb['deletions']} 行")
        sections.append(f"- 触及函数：{len(fb['affected_functions'])}/{fb['total_functions_in_file']} 个")
        if fb["affected_functions"]:
            sections.append(f"- 涉及：`{'`、`'.join(fb['affected_functions'])}`")
        sections.append("")

    sections.append("## 影响分析")
    has_callers = any(callers for callers in impact["impacted_callers"].values())
    if has_callers:
        sections.append("以下函数可能受本次改动影响（被其它函数调用）：")
        for func, callers in impact["impacted_callers"].items():
            if callers:
                sections.append(f"- `{func}` 被调用：`{'`、`'.join(callers)}`")
        sections.append("")
    else:
        sections.append("未检测到下游调用。")
        sections.append("")

    sections.append("## 风险评估")
    risk = impact["risk_score"]
    if risk == "high":
        sections.append("**高风险**：改动较大、影响面广，建议重点评审并补充测试。")
    elif risk == "medium":
        sections.append("**中风险**：中等改动，请仔细检查受影响的区域。")
    elif risk == "none":
        sections.append("**无**：没有识别到被修改的函数。")
    else:
        sections.append("**低风险**：改动小、范围可控。")

    return {
        "pr_number": diff.pr.number,
        "title": diff.pr.title,
        "repo": f"{diff.pr.owner}/{diff.pr.repo}",
        "base_branch": diff.pr.base_branch,
        "head_branch": diff.pr.head_branch,
        "risk_score": impact["risk_score"],
        "summary": summary,
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


def generate_report(diff: PRDiff, repo_path: str, settings=None) -> dict:
    impact = analyze_impact(diff, repo_path)
    summary = _llm_summary(impact, diff, settings) if settings is not None else ""
    return format_report(diff, impact, summary)