import re

_EXACT_KEYWORDS = {"where", "defined", "function", "class", "method", "definition", "location"}

_OVERVIEW_EN = {"architecture", "overview", "structure", "framework", "layout", "modules"}
_OVERVIEW_CJK = ("框架", "架构", "结构", "组织", "模块", "目录", "分层", "整体", "概览", "组成")


def classify_query(query: str) -> str:
    words = set(re.findall(r"[a-z]+", query.lower()))
    if words & _EXACT_KEYWORDS:
        return "exact"
    return "semantic"


def is_overview_query(query: str) -> bool:
    words = set(re.findall(r"[a-z]+", query.lower()))
    if words & _OVERVIEW_EN:
        return True
    return any(keyword in query for keyword in _OVERVIEW_CJK)