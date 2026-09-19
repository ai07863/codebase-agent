from retrieval.ast_index import ASTIndex


def ast_search_tool(query: str, ast_index: ASTIndex) -> str:
    results = ast_index.search_by_name(query)
    if not results:
        return "No exact matches found."
    lines = []
    for r in results[:5]:
        lines.append(f"{r.name} in {r.file_path}:{r.start_line}-{r.end_line}")
    return "\n".join(lines)