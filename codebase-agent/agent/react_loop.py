from openai import OpenAI
from config.settings import Settings
from retrieval.vector_store import VectorStore
from retrieval.ast_index import ASTIndex
from embedding.embedder import Embedder
from agent.router import classify_query
from agent.tools.ast_search import ast_search_tool
from agent.tools.semantic_search import semantic_search_tool
from agent.tools.file_reader import read_file_tool
from cache.redis_cache import Cache


_SYSTEM_PROMPT = """You are a codebase analysis assistant. You help developers understand code.

Available tools:
- ast_search(query): Search for functions/classes by name
- semantic_search(query): Search for code by conceptual meaning
- read_file(path, start_line, end_line): Read code from a file

For each question:
1. Think about what information you need
2. Use the appropriate tool(s)
3. Synthesize the answer with file paths and line numbers

Always cite your sources (file paths and line numbers)."""


def process_query(query: str, repo_path: str, vector_store: VectorStore,
                  ast_index: ASTIndex, embedder: Embedder, settings: Settings) -> str:
    repo_name = repo_path.rstrip("/\\").split("/")[-1].split("\\")[-1]
    cache_key = f"qa:{repo_name}:{query}"

    cache = Cache(host=settings.redis_host, port=settings.redis_port)
    try:
        cached = cache.get(cache_key)
        if cached:
            return cached

        client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        route = classify_query(query)

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ]

        if route == "exact":
            ast_result = ast_search_tool(query, ast_index)
            messages.append({"role": "assistant", "content": f"I looked up '{query}' in the AST index:\n{ast_result}"})
        else:
            sem_result = semantic_search_tool(query, vector_store, embedder)
            messages.append({"role": "assistant", "content": f"I searched semantically for '{query}':\n{sem_result}"})

        messages.append({"role": "user", "content": "Based on the above information, provide a complete answer. Include file paths and line numbers."})

        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=0.3,
        )

        answer = response.choices[0].message.content
        cache.set(cache_key, answer, ttl=86400)
        return answer
    finally:
        cache.close()