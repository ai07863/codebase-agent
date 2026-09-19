from code_parser.ast_parser import CodeNode


def chunk_text(nodes: list[CodeNode]) -> list[dict]:
    chunks = []
    for node in nodes:
        text = f"{node.signature}\n{node.docstring}".strip()
        if text:
            chunks.append({
                "node_id": node.node_id,
                "type": node.type,
                "name": node.name,
                "file_path": node.file_path,
                "start_line": node.start_line,
                "end_line": node.end_line,
                "text": text,
            })
    return chunks