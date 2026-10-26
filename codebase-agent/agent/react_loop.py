import logging
import re
from pathlib import Path
from openai import OpenAI
from config.settings import Settings
from retrieval.vector_store import VectorStore, SearchResult
from retrieval.ast_index import ASTIndex
from retrieval.hybrid_search import hybrid_search, diversify
from embedding.embedder import Embedder
from agent.router import classify_query, is_overview_query
from agent.tools.file_reader import read_file_tool
from code_parser.relationship import build_project_map
from cache.redis_cache import Cache


logger = logging.getLogger("codebase-agent.retrieval")


_SYSTEM_PROMPT = """You are a codebase analysis assistant. You answer questions about a code repository.

You are given:
1. A project structure map (files and how many functions/classes each contains).
2. Relevant source excerpts.

Rules:
1. Base your answer on the provided material. Do not invent files, modules, or APIs that are not shown.
2. Cite sources compactly: name the file like `path/to/file.py`. Add `:line` only when pointing at one specific definition, and never cite a line range.
3. Do not repeat the same citation in every sentence.
4. Answer as much as the material allows. If part of the question is not covered, briefly say which part is missing instead of padding the answer with caveats."""


_STOP_WORDS = {
    "where", "is", "are", "the", "a", "an", "defined", "function", "class",
    "method", "definition", "location", "of", "how", "does", "do", "work",
    "works", "what", "which", "in", "to", "for", "find", "show", "me", "this",
    "that", "and", "or", "used", "use",
}

_MAX_SNIPPET_LINES = 80


def _identifiers(query: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", query)
    return [t for t in tokens if t.lower() not in _STOP_WORDS]


def _extract_identifier(query: str) -> str:
    candidates = _identifiers(query)
    return candidates[0] if candidates else query


def _choose_identifier(query: str, ast_index: ASTIndex) -> str:
    """Pick the query token that actually exists in the index (not just the first)."""
    candidates = _identifiers(query)
    for candidate in candidates:
        if ast_index.lookup(candidate):
            return candidate
    return candidates[0] if candidates else query


def _read_snippet(repo_path: str, file_path: str, start_line: int, end_line: int,
                  max_lines: int = _MAX_SNIPPET_LINES) -> str:
    full = Path(repo_path) / file_path
    if not full.exists():
        return ""
    end = min(end_line, start_line + max_lines - 1)
    return read_file_tool(str(full), start_line, end)


def _retrieve(query: str, vector_store: VectorStore, ast_index: ASTIndex,
              embedder: Embedder, route: str, k: int = 5,
              overview: bool = False) -> list[SearchResult]:
    if route == "exact":
        results = ast_index.search_by_name(_choose_identifier(query, ast_index))
        if results:
            return results[:k]
    if overview:
        return diversify(hybrid_search(query, vector_store, ast_index, embedder, k * 3), k)
    return hybrid_search(query, vector_store, ast_index, embedder, k)


def _build_context(results: list[SearchResult], repo_path: str, project_map: str = "") -> str:
    sections = []
    if project_map:
        sections.append(f"## Project structure\n{project_map}")
    blocks = []
    for r in results:
        code = _read_snippet(repo_path, r.file_path, r.start_line, r.end_line)
        if code:
            blocks.append(f"### {r.file_path} — {r.name}\n```python\n{code}\n```")
    source = "\n\n".join(blocks) if blocks else "(no source code retrieved)"
    sections.append(f"## Relevant source\n{source}")
    return "\n\n".join(sections)


_DIAGRAM_INSTRUCTION = (
    "This is a structure/architecture question. Also include a Mermaid flowchart "
    "(a fenced ```mermaid block starting with `graph TD`) that summarizes the main "
    "modules/files and how they relate, based on the project structure above."
)


def _build_user_message(query: str, context: str, overview: bool = False) -> str:
    parts = [
        f"Question: {query}",
        f"Material retrieved from the repository:\n\n{context}",
    ]
    if overview:
        parts.append(_DIAGRAM_INSTRUCTION)
    parts.append(
        "Answer the question based on the material above. "
        "Cite files compactly (line numbers only for specific definitions)."
    )
    return "\n\n".join(parts)


def _build_messages(query: str, context: str, overview: bool = False,
                    history: list[dict] | None = None) -> list[dict]:
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    for msg in (history or [])[-12:]:
        role = msg.get("role")
        content = msg.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": _build_user_message(query, context, overview)})
    return messages


def _chat(client: OpenAI, model: str, messages: list[dict],
          timeout: float = 60, retries: int = 1):
    last = None
    for _ in range(retries + 1):
        try:
            return client.chat.completions.create(
                model=model, messages=messages, temperature=0.3, timeout=timeout,
            )
        except Exception as exc:
            text = str(exc)
            if "403" in text or "401" in text or "PermissionDenied" in type(exc).__name__:
                raise
            last = exc
    raise last


def _open_cache(settings: Settings) -> Cache | None:
    try:
        return Cache(host=settings.redis_host, port=settings.redis_port)
    except Exception:
        return None


def _cache_get(cache: Cache | None, key: str) -> str | None:
    if cache is None:
        return None
    try:
        return cache.get(key)
    except Exception:
        return None


def _cache_set(cache: Cache | None, key: str, value: str, ttl: int = 86400) -> None:
    if cache is None:
        return
    try:
        cache.set(key, value, ttl=ttl)
    except Exception:
        pass


def process_query(query: str, repo_path: str, vector_store: VectorStore,
                  ast_index: ASTIndex, embedder: Embedder, settings: Settings,
                  history: list[dict] | None = None) -> str:
    repo_name = repo_path.rstrip("/\\").split("/")[-1].split("\\")[-1]
    cache_key = f"qa:v2:{repo_name}:{query}"

    cache = _open_cache(settings)
    try:
        cached = _cache_get(cache, cache_key)
        if cached:
            return cached

        client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        route = classify_query(query)
        overview = is_overview_query(query)
        k = 10 if overview else 5
        results = _retrieve(query, vector_store, ast_index, embedder, route, k=k, overview=overview)
        project_map = build_project_map(ast_index.nodes)
        context = _build_context(results, repo_path, project_map)
        logger.info(
            "QA repo=%s route=%s hits=%s context_chars=%d",
            repo_name,
            route,
            [(r.name, r.file_path, round(r.score, 3)) for r in results],
            len(context),
        )

        messages = _build_messages(query, context, overview, history)

        response = _chat(client, settings.llm_model, messages)

        answer = response.choices[0].message.content or ""
        _cache_set(cache, cache_key, answer)
        return answer
    finally:
        if cache is not None:
            cache.close()