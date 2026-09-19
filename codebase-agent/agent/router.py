_EXACT_KEYWORDS = {"where", "defined", "function", "class", "method", "definition", "location"}


def classify_query(query: str) -> str:
    q = query.lower()
    words = set(q.split())
    if words & _EXACT_KEYWORDS:
        return "exact"
    return "semantic"