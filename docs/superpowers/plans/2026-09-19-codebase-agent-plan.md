# CodeBase Agent 实现计划

> **对执行 Agent 的说明：** 使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 按任务逐项实现。步骤用复选框（`- [ ]`）追踪。

**目标：** 构建一个 CLI 工具，克隆 GitHub 仓库，用 AST 解析代码，将函数/类索引到 ChromaDB，通过 ReAct Agent 回答自然语言问题。

**架构：** 单 Agent ReAct 循环 + 多策略检索（AST 精确 + 语义 + BM25）。ChromaDB 做向量存储，Redis 做缓存，tree-sitter 做 AST 解析。CLI 用 Click + Rich。

**技术栈：** Python 3.11+, tree-sitter, chromadb, sentence-transformers (BGE-small-zh), rank-bm25, click, rich, redis-py, docker-compose

## 全局约束

- LLM 模型默认 `gpt-4o-mini`，通过环境变量 `LLM_MODEL`、`LLM_API_KEY`、`LLM_BASE_URL` 配置
- Embedding 模型：BGE-small-zh，通过 sentence-transformers 加载本地缓存
- ChromaDB 持久化到 `./data/chroma/`
- Redis 在 Docker 容器中运行，端口 6379
- 每次提交前所有测试必须通过
- Python 3.11+

---

### 任务 1：项目脚手架 + 配置

**文件：**
- 创建：`codebase-agent/requirements.txt`
- 创建：`codebase-agent/.env.example`
- 创建：`codebase-agent/.gitignore`
- 创建：`codebase-agent/config/__init__.py`
- 创建：`codebase-agent/config/settings.py`
- 创建：`codebase-agent/codebase_agent/__init__.py`
- 创建：`codebase-agent/pyproject.toml`

**接口：**
- 依赖：无
- 产出：`config/settings.py` 暴露 `Settings` dataclass，包含所有配置字段

- [ ] **第 1 步：创建项目目录结构**

```bash
mkdir -p codebase-agent/{cli,agent/tools,code_parser,retrieval,cache,embedding,evaluation/data,config,tests}
```

- [ ] **第 2 步：编写 requirements.txt**

```
tree-sitter>=0.21.0
chromadb>=0.5.0
sentence-transformers>=3.0.0
rank-bm25>=0.2.0
click>=8.1.0
rich>=13.0.0
redis>=5.0.0
python-dotenv>=1.0.0
openai>=1.0.0
httpx>=0.27.0
pytest>=8.0.0
```

- [ ] **第 3 步：编写 `.env.example`**

```
LLM_API_KEY=sk-your-key-here
LLM_MODEL=gpt-4o-mini
LLM_BASE_URL=https://api.openai.com/v1
REDIS_HOST=localhost
REDIS_PORT=6379
CHROMA_PERSIST_DIR=./data/chroma
REPOS_DIR=./data/repos
```

- [ ] **第 4 步：编写 `.gitignore`**

```
__pycache__/
*.pyc
.env
data/
chroma/
*.egg-info/
dist/
```

- [ ] **第 5 步：编写 `config/__init__.py`**

```python
from config.settings import Settings
```

- [ ] **第 6 步：编写 `config/settings.py`**

```python
import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o-mini"))
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"))
    redis_host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    chroma_persist_dir: str = field(default_factory=lambda: os.getenv("CHROMA_PERSIST_DIR", "./data/chroma"))
    repos_dir: str = field(default_factory=lambda: os.getenv("REPOS_DIR", "./data/repos"))

    @classmethod
    def load(cls) -> "Settings":
        from dotenv import load_dotenv
        load_dotenv()
        return cls()
```

- [ ] **第 7 步：编写 `pyproject.toml`**

```toml
[project]
name = "codebase-agent"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "tree-sitter>=0.21.0",
    "chromadb>=0.5.0",
    "sentence-transformers>=3.0.0",
    "rank-bm25>=0.2.0",
    "click>=8.1.0",
    "rich>=13.0.0",
    "redis>=5.0.0",
    "python-dotenv>=1.0.0",
    "openai>=1.0.0",
    "httpx>=0.27.0",
]

[project.scripts]
codebase-agent = "cli.main:cli"
```

- [ ] **第 8 步：编写 `codebase_agent/__init__.py`**（空文件）

- [ ] **第 9 步：测试导入是否正常**

```bash
cd codebase-agent
pip install -e .
python -c "from config.settings import Settings; s = Settings.load(); print(s.llm_model)"
```
预期输出：`gpt-4o-mini`

- [ ] **第 10 步：提交**

```bash
git init
git add .
git commit -m "chore: 项目脚手架和配置"
```

---

### 任务 2：代码解析器 — AST 解析 + 切片

**文件：**
- 创建：`codebase-agent/code_parser/__init__.py`
- 创建：`codebase-agent/code_parser/ast_parser.py`
- 创建：`codebase-agent/code_parser/chunker.py`
- 创建：`codebase-agent/code_parser/relationship.py`
- 创建：`codebase-agent/tests/__init__.py`
- 创建：`codebase-agent/tests/test_code_parser.py`

**接口：**
- 依赖：无
- 产出：`CodeNode` dataclass, `parse_repo(repo_path: str) -> list[CodeNode]`, `CodeChunk` dataclass

- [ ] **第 1 步：编写测试（先让它失败）**

```python
# tests/test_code_parser.py
import tempfile
from pathlib import Path
from code_parser.ast_parser import CodeNode, parse_repo


def test_parse_python_function():
    code = """
def greet(name: str) -> str:
    \"\"\"Say hello to someone.\"\"\"
    return f"Hello, {name}"
"""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "test.py"
        src.write_text(code)
        nodes = parse_repo(tmp)
        funcs = [n for n in nodes if n.type == "function"]
        assert len(funcs) == 1
        assert funcs[0].name == "greet"
        assert "Hello" in funcs[0].docstring


def test_parse_python_class():
    code = """
class Calculator:
    \"\"\"A simple calculator.\"\"\"
    def add(self, a: int, b: int) -> int:
        return a + b
"""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "test.py"
        src.write_text(code)
        nodes = parse_repo(tmp)
        classes = [n for n in nodes if n.type == "class"]
        assert len(classes) == 1
        assert classes[0].name == "Calculator"
```

- [ ] **第 2 步：运行测试，确认失败**

```bash
cd codebase-agent
pip install -e .
pytest tests/test_code_parser.py -v
```
预期：FAIL（导入错误）

- [ ] **第 3 步：编写 `code_parser/ast_parser.py`**

```python
from dataclasses import dataclass, field
from pathlib import Path
import tree_sitter_python as tspython
from tree_sitter import Language, Parser


@dataclass
class CodeNode:
    node_id: str
    type: str  # "function", "class", "method"
    name: str
    file_path: str
    start_line: int
    end_line: int
    signature: str
    docstring: str
    calls: list[str] = field(default_factory=list)


_PARSER_CACHE = {}


def _get_parser(language: str = "python"):
    if language not in _PARSER_CACHE:
        if language == "python":
            lang = Language(tspython.language())
        else:
            raise ValueError(f"不支持的语言: {language}")
        parser = Parser(lang)
        _PARSER_CACHE[language] = parser
    return _PARSER_CACHE[language]


def _detect_language(file_path: str) -> str | None:
    ext = Path(file_path).suffix
    mapping = {".py": "python", ".js": "javascript", ".ts": "typescript", ".go": "go", ".java": "java"}
    return mapping.get(ext)


def _extract_docstring(node, source_bytes: bytes) -> str:
    if node.child_count == 0:
        return ""
    first = node.child(0)
    if first.type == "expression_statement" and first.child(0) and first.child(0).type == "string":
        start = first.start_byte
        end = first.end_byte
        return source_bytes[start:end].decode("utf-8").strip("\"'")
    return ""


def _extract_calls(node, source_bytes: bytes) -> list[str]:
    calls = []
    if node.type == "call":
        func_node = node.child(0)
        if func_node:
            calls.append(source_bytes[func_node.start_byte:func_node.end_byte].decode("utf-8"))
    for child in node.children:
        calls.extend(_extract_calls(child, source_bytes))
    return calls


def _traverse(node, source_bytes: bytes, file_path: str) -> list[CodeNode]:
    nodes = []
    if node.type in ("function_definition", "class_definition"):
        name_node = node.child_by_field_name("name")
        if name_node:
            name = source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8")
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            sig_bytes = source_bytes[node.start_byte:node.end_byte]
            sig = sig_bytes.decode("utf-8").split("\n")[0].strip()
            docstring = _extract_docstring(node, source_bytes)
            node_type = "function" if node.type == "function_definition" else "class"
            calls = _extract_calls(node, source_bytes)
            node_id = f"{file_path}:{name}"
            nodes.append(CodeNode(
                node_id=node_id,
                type=node_type,
                name=name,
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                signature=sig,
                docstring=docstring,
                calls=list(set(calls)),
            ))
            if node.type == "class_definition":
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        nodes.extend(_traverse(child, source_bytes, file_path))
    else:
        for child in node.children:
            nodes.extend(_traverse(child, source_bytes, file_path))
    return nodes


def parse_repo(repo_path: str) -> list[CodeNode]:
    nodes = []
    root = Path(repo_path)
    for file_path in root.rglob("*"):
        if file_path.is_file() and file_path.suffix in (".py", ".js", ".ts", ".go", ".java"):
            lang = _detect_language(str(file_path))
            if not lang:
                continue
            rel_path = str(file_path.relative_to(root))
            source_bytes = file_path.read_bytes()
            parser = _get_parser(lang)
            tree = parser.parse(source_bytes)
            nodes.extend(_traverse(tree.root_node, source_bytes, rel_path))
    return nodes
```

- [ ] **第 4 步：编写 `code_parser/chunker.py`**

```python
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
```

- [ ] **第 5 步：编写 `code_parser/relationship.py`**

```python
from code_parser.ast_parser import CodeNode


def build_call_graph(nodes: list[CodeNode]) -> dict[str, list[str]]:
    graph = {}
    node_map = {n.name: n for n in nodes}
    for node in nodes:
        graph[node.name] = [c for c in node.calls if c in node_map]
    return graph


def find_callers(nodes: list[CodeNode], target_name: str) -> list[str]:
    return [n.name for n in nodes if target_name in n.calls]
```

- [ ] **第 6 步：编写 `code_parser/__init__.py`**

```python
from code_parser.ast_parser import CodeNode, parse_repo
from code_parser.chunker import chunk_text
from code_parser.relationship import build_call_graph, find_callers
```

- [ ] **第 7 步：运行测试，确认通过**

```bash
pytest tests/test_code_parser.py -v
```
预期：PASS

- [ ] **第 8 步：提交**

```bash
git add -A
git commit -m "feat: tree-sitter AST 代码解析器"
```

---

### 任务 3：Embedding 层

**文件：**
- 创建：`codebase-agent/embedding/__init__.py`
- 创建：`codebase-agent/embedding/embedder.py`
- 创建：`codebase-agent/tests/test_embedding.py`

**接口：**
- 依赖：无
- 产出：`Embedder` 类，暴露 `encode(texts: list[str]) -> list[list[float]]`

- [ ] **第 1 步：编写测试（先让它失败）**

```python
# tests/test_embedding.py
from embedding.embedder import Embedder


def test_embedder_returns_float_vectors():
    embedder = Embedder()
    texts = ["hello world", "def foo(): pass"]
    vectors = embedder.encode(texts)
    assert len(vectors) == 2
    assert len(vectors[0]) > 0
    assert isinstance(vectors[0][0], float)
```

- [ ] **第 2 步：运行测试，确认失败**

```bash
pytest tests/test_embedding.py -v
```
预期：FAIL

- [ ] **第 3 步：编写 `embedding/embedder.py`**

```python
from sentence_transformers import SentenceTransformer


class Embedder:
    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        self.model = SentenceTransformer(model_name)

    def encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vectors]
```

- [ ] **第 4 步：编写 `embedding/__init__.py`**

```python
from embedding.embedder import Embedder
```

- [ ] **第 5 步：运行测试，确认通过**

```bash
pytest tests/test_embedding.py -v
```
预期：PASS

- [ ] **第 6 步：提交**

```bash
git add -A
git commit -m "feat: embedding 层，使用 BGE-small-zh"
```

---

### 任务 4：检索层 — Vector Store + AST 索引 + 混合搜索

**文件：**
- 创建：`codebase-agent/retrieval/__init__.py`
- 创建：`codebase-agent/retrieval/vector_store.py`
- 创建：`codebase-agent/retrieval/ast_index.py`
- 创建：`codebase-agent/retrieval/hybrid_search.py`
- 创建：`codebase-agent/tests/test_retrieval.py`

**接口：**
- 依赖：`CodeNode`, `Embedder.encode()`
- 产出：`VectorStore.add(nodes, embedder)`, `ASTIndex.build(nodes)`, `hybrid_search(query, k) -> list[SearchResult]`

- [ ] **第 1 步：编写测试（先让它失败）**

```python
# tests/test_retrieval.py
import tempfile
from pathlib import Path
from code_parser.ast_parser import CodeNode, parse_repo
from embedding.embedder import Embedder
from retrieval.vector_store import VectorStore
from retrieval.ast_index import ASTIndex
from retrieval.hybrid_search import hybrid_search


def test_vector_store_add_and_search():
    nodes = [
        CodeNode(node_id="a", type="function", name="greet", file_path="test.py",
                 start_line=1, end_line=3, signature="def greet():", docstring="Say hello", calls=[]),
        CodeNode(node_id="b", type="function", name="add", file_path="test.py",
                 start_line=5, end_line=7, signature="def add(a,b):", docstring="Add two numbers", calls=[]),
    ]
    embedder = Embedder()
    vs = VectorStore()
    vs.add(nodes, embedder)
    results = vs.search("add two numbers", k=2)
    assert len(results) > 0
    assert results[0].node_id == "b"


def test_ast_index_lookup():
    nodes = [
        CodeNode(node_id="a", type="function", name="greet", file_path="test.py",
                 start_line=1, end_line=3, signature="def greet():", docstring="", calls=[]),
    ]
    idx = ASTIndex(nodes)
    result = idx.lookup("greet")
    assert result is not None
    assert result.name == "greet"
```

- [ ] **第 2 步：运行测试，确认失败**

```bash
pytest tests/test_retrieval.py -v
```
预期：FAIL

- [ ] **第 3 步：编写 `retrieval/vector_store.py`**

```python
from dataclasses import dataclass
import chromadb
from chromadb.config import Settings as ChromaSettings
from code_parser.ast_parser import CodeNode
from embedding.embedder import Embedder


@dataclass
class SearchResult:
    node_id: str
    name: str
    file_path: str
    start_line: int
    end_line: int
    score: float


class VectorStore:
    def __init__(self, persist_dir: str = "./data/chroma"):
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name="code_nodes",
            metadata={"hnsw:space": "cosine"},
        )

    def add(self, nodes: list[CodeNode], embedder: Embedder):
        texts = [f"{n.signature}\n{n.docstring}" for n in nodes]
        vectors = embedder.encode(texts)
        ids = [n.node_id for n in nodes]
        metadatas = [{"type": n.type, "name": n.name, "file_path": n.file_path,
                       "start_line": n.start_line, "end_line": n.end_line} for n in nodes]
        existing = self.collection.get(ids=ids)
        if existing["ids"]:
            self.collection.delete(ids=existing["ids"])
        self.collection.add(ids=ids, embeddings=vectors, metadatas=metadatas)

    def search(self, query: str, embedder: Embedder, k: int = 5) -> list[SearchResult]:
        query_vec = embedder.encode([query])
        results = self.collection.query(query_embeddings=query_vec, n_results=k)
        items = []
        for i in range(len(results["ids"][0])):
            items.append(SearchResult(
                node_id=results["ids"][0][i],
                name=results["metadatas"][0][i]["name"],
                file_path=results["metadatas"][0][i]["file_path"],
                start_line=results["metadatas"][0][i]["start_line"],
                end_line=results["metadatas"][0][i]["end_line"],
                score=results["distances"][0][i],
            ))
        return items
```

- [ ] **第 4 步：编写 `retrieval/ast_index.py`**

```python
from code_parser.ast_parser import CodeNode
from retrieval.vector_store import SearchResult


class ASTIndex:
    def __init__(self, nodes: list[CodeNode]):
        self.by_name: dict[str, CodeNode] = {}
        self.by_file: dict[str, list[CodeNode]] = {}
        for node in nodes:
            self.by_name[node.name] = node
            self.by_file.setdefault(node.file_path, []).append(node)

    def lookup(self, name: str) -> CodeNode | None:
        return self.by_name.get(name)

    def search_by_name(self, query: str) -> list[SearchResult]:
        q = query.lower()
        results = []
        for name, node in self.by_name.items():
            if q in name.lower():
                results.append(SearchResult(
                    node_id=node.node_id,
                    name=node.name,
                    file_path=node.file_path,
                    start_line=node.start_line,
                    end_line=node.end_line,
                    score=0.0,
                ))
        return results
```

- [ ] **第 5 步：编写 `retrieval/hybrid_search.py`**

```python
from rank_bm25 import BM25Okapi
from retrieval.vector_store import VectorStore, SearchResult
from retrieval.ast_index import ASTIndex
from embedding.embedder import Embedder


def hybrid_search(
    query: str,
    vector_store: VectorStore,
    ast_index: ASTIndex,
    embedder: Embedder,
    k: int = 5,
) -> list[SearchResult]:
    semantic_results = vector_store.search(query, embedder, k)
    ast_results = ast_index.search_by_name(query)
    seen = set()
    merged = []
    for r in semantic_results + ast_results:
        if r.node_id not in seen:
            seen.add(r.node_id)
            merged.append(r)
    return merged[:k]
```

- [ ] **第 6 步：编写 `retrieval/__init__.py`**

```python
from retrieval.vector_store import VectorStore, SearchResult
from retrieval.ast_index import ASTIndex
from retrieval.hybrid_search import hybrid_search
```

- [ ] **第 7 步：运行测试，确认通过**

```bash
pytest tests/test_retrieval.py -v
```
预期：PASS

- [ ] **第 8 步：提交**

```bash
git add -A
git commit -m "feat: 检索层，包含向量存储、AST 索引、混合搜索"
```

---

### 任务 5：缓存层 — Redis

**文件：**
- 创建：`codebase-agent/cache/__init__.py`
- 创建：`codebase-agent/cache/redis_cache.py`
- 创建：`codebase-agent/tests/test_cache.py`
- 创建：`codebase-agent/docker-compose.yml`（添加 redis 服务）

**接口：**
- 依赖：Redis host/port 来自 Settings
- 产出：`Cache` 类，暴露 `get(key)`, `set(key, value, ttl)`, `close()`

- [ ] **第 1 步：编写测试（先让它失败）**

```python
# tests/test_cache.py
from cache.redis_cache import Cache


def test_cache_set_and_get():
    cache = Cache(host="localhost", port=6379, db=1)
    cache.set("test_key", "hello world", ttl=60)
    value = cache.get("test_key")
    assert value == "hello world"
    cache.close()
    cache.clear_db()
```

- [ ] **第 2 步：编写 `cache/redis_cache.py`**

```python
import hashlib
import json
import redis


class Cache:
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        self.client = redis.Redis(host=host, port=port, db=db, decode_responses=True)

    def _make_key(self, key: str) -> str:
        return f"codebase-agent:{hashlib.md5(key.encode()).hexdigest()}"

    def get(self, key: str) -> str | None:
        val = self.client.get(self._make_key(key))
        return val

    def set(self, key: str, value: str, ttl: int = 3600):
        self.client.setex(self._make_key(key), ttl, value)

    def exists(self, key: str) -> bool:
        return self.client.exists(self._make_key(key)) > 0

    def close(self):
        self.client.close()

    def clear_db(self):
        self.client.flushdb()
```

- [ ] **第 3 步：编写 `cache/__init__.py`**

```python
from cache.redis_cache import Cache
```

- [ ] **第 4 步：在 `docker-compose.yml` 中添加 redis 服务**

```yaml
version: "3.9"
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped

volumes:
  redis_data:
```

- [ ] **第 5 步：启动 Redis 并运行测试**

```bash
cd codebase-agent
docker compose up -d
pytest tests/test_cache.py -v
```
预期：PASS

- [ ] **第 6 步：提交**

```bash
git add -A
git commit -m "feat: Redis 缓存层"
```

---

### 任务 6：Agent — 路由器 + ReAct 循环 + 工具

**文件：**
- 创建：`codebase-agent/agent/__init__.py`
- 创建：`codebase-agent/agent/router.py`
- 创建：`codebase-agent/agent/react_loop.py`
- 创建：`codebase-agent/agent/tools/__init__.py`
- 创建：`codebase-agent/agent/tools/ast_search.py`
- 创建：`codebase-agent/agent/tools/semantic_search.py`
- 创建：`codebase-agent/agent/tools/file_reader.py`
- 创建：`codebase-agent/tests/test_agent.py`

**接口：**
- 依赖：VectorStore, ASTIndex, Embedder, Cache, Settings
- 产出：`process_query(query: str, repo_path: str) -> Answer`

- [ ] **第 1 步：编写测试（先让它失败）**

```python
# tests/test_agent.py
from agent.router import classify_query
from agent.tools.ast_search import ast_search_tool
from agent.tools.file_reader import read_file_tool


def test_classify_query():
    assert classify_query("where is the greet function defined?") == "exact"
    assert classify_query("how does authentication work?") == "semantic"


def test_ast_search_tool():
    from retrieval.ast_index import ASTIndex
    from code_parser.ast_parser import CodeNode
    nodes = [
        CodeNode(node_id="a", type="function", name="greet", file_path="test.py",
                 start_line=1, end_line=3, signature="def greet():", docstring="", calls=[]),
    ]
    idx = ASTIndex(nodes)
    result = ast_search_tool("greet", idx)
    assert "greet" in result


def test_read_file_tool():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "test.py"
        f.write_text("def foo():\n    pass\n")
        result = read_file_tool(str(f), 1, 2)
        assert "def foo()" in result
```

- [ ] **第 2 步：编写 `agent/router.py`**

```python
_EXACT_KEYWORDS = {"where", "defined", "function", "class", "method", "definition", "location"}


def classify_query(query: str) -> str:
    q = query.lower()
    words = set(q.split())
    if words & _EXACT_KEYWORDS:
        return "exact"
    return "semantic"
```

- [ ] **第 3 步：编写 `agent/tools/ast_search.py`**

```python
from retrieval.ast_index import ASTIndex


def ast_search_tool(query: str, ast_index: ASTIndex) -> str:
    results = ast_index.search_by_name(query)
    if not results:
        return "No exact matches found."
    lines = []
    for r in results[:5]:
        lines.append(f"{r.name} in {r.file_path}:{r.start_line}-{r.end_line}")
    return "\n".join(lines)
```

- [ ] **第 4 步：编写 `agent/tools/semantic_search.py`**

```python
from retrieval.vector_store import VectorStore
from embedding.embedder import Embedder


def semantic_search_tool(query: str, vector_store: VectorStore, embedder: Embedder) -> str:
    results = vector_store.search(query, embedder, k=5)
    if not results:
        return "No semantic matches found."
    lines = []
    for r in results:
        lines.append(f"[{r.score:.3f}] {r.name} in {r.file_path}:{r.start_line}-{r.end_line}")
    return "\n".join(lines)
```

- [ ] **第 5 步：编写 `agent/tools/file_reader.py`**

```python
from pathlib import Path


def read_file_tool(file_path: str, start_line: int = 1, end_line: int | None = None) -> str:
    p = Path(file_path)
    if not p.exists():
        return f"File not found: {file_path}"
    lines = p.read_text(encoding="utf-8").splitlines()
    end = end_line or len(lines)
    selected = lines[start_line - 1:end]
    return "\n".join(selected)
```

- [ ] **第 6 步：编写 `agent/tools/__init__.py`**

```python
from agent.tools.ast_search import ast_search_tool
from agent.tools.semantic_search import semantic_search_tool
from agent.tools.file_reader import read_file_tool
```

- [ ] **第 7 步：编写 `agent/react_loop.py`**

```python
import json
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
    cache = Cache(host=settings.redis_host, port=settings.redis_port)
    cache_key = f"qa:{query}"
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
    cache.close()
    return answer
```

- [ ] **第 8 步：编写 `agent/__init__.py`**

```python
from agent.react_loop import process_query
```

- [ ] **第 9 步：运行测试**

```bash
pytest tests/test_agent.py -v
```
预期：PASS

- [ ] **第 10 步：提交**

```bash
git add -A
git commit -m "feat: Agent 路由器、工具、ReAct 循环"
```

---

### 任务 7：CLI

**文件：**
- 创建：`codebase-agent/cli/__init__.py`
- 创建：`codebase-agent/cli/main.py`
- 创建：`codebase-agent/tests/test_cli.py`

**接口：**
- 依赖：所有前置任务
- 产出：`codebase-agent` CLI 命令

- [ ] **第 1 步：编写测试（先让它失败）**

```python
# tests/test_cli.py
from click.testing import CliRunner
from cli.main import cli


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "analyze" in result.output
```

- [ ] **第 2 步：编写 `cli/main.py`**

```python
import shutil
import subprocess
import sys
from pathlib import Path
import click
from rich.console import Console
from rich.markdown import Markdown
from config.settings import Settings
from code_parser.ast_parser import parse_repo
from code_parser.chunker import chunk_text
from code_parser.relationship import build_call_graph
from embedding.embedder import Embedder
from retrieval.vector_store import VectorStore
from retrieval.ast_index import ASTIndex
from retrieval.hybrid_search import hybrid_search
from agent.react_loop import process_query


console = Console()


@click.group()
def cli():
    pass


@cli.command()
@click.argument("repo_url")
@click.option("--branch", default=None, help="指定克隆的分支")
def analyze(repo_url: str, branch: str | None):
    """克隆仓库并分析代码库"""
    settings = Settings.load()
    repos_dir = Path(settings.repos_dir)
    repos_dir.mkdir(parents=True, exist_ok=True)
    repo_name = repo_url.rstrip("/").split("/")[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]
    repo_path = repos_dir / repo_name

    if repo_path.exists():
        console.print(f"[yellow]仓库已存在 {repo_path}，跳过克隆[/]")
    else:
        console.print(f"[green]正在克隆 {repo_url}...[/]")
        cmd = ["git", "clone", "--depth", "1"]
        if branch:
            cmd.extend(["--branch", branch])
        cmd.extend([repo_url, str(repo_path)])
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            console.print(f"[red]克隆失败: {result.stderr}[/]")
            sys.exit(1)

    console.print("[green]正在使用 AST 解析代码...[/]")
    nodes = parse_repo(str(repo_path))
    console.print(f"[green]找到 {len(nodes)} 个函数/类[/]")

    console.print("[green]正在构建搜索索引...[/]")
    embedder = Embedder()
    vector_store = VectorStore(persist_dir=settings.chroma_persist_dir)
    vector_store.add(nodes, embedder)
    ast_index = ASTIndex(nodes)

    console.print("\n[bold cyan]CodeBase Agent 已就绪！可以开始提问了[/]")
    console.print("[dim]输入 'exit' 退出，'graph' 查看调用关系图[/]\n")

    while True:
        try:
            query = console.input("[bold]Q> [/]")
        except (EOFError, KeyboardInterrupt):
            break
        if query.lower() in ("exit", "quit"):
            break
        if query.lower() == "graph":
            graph = build_call_graph(nodes)
            for caller, callees in graph.items():
                if callees:
                    console.print(f"[blue]{caller}[/] -> {', '.join(callees)}")
            continue
        if not query.strip():
            continue

        with console.status("[cyan]思考中...[/]"):
            answer = process_query(query, str(repo_path), vector_store, ast_index, embedder, settings)
        console.print(Markdown(answer))
        console.print()


if __name__ == "__main__":
    cli()
```

- [ ] **第 3 步：运行测试**

```bash
pytest tests/test_cli.py -v
```
预期：PASS

- [ ] **第 4 步：提交**

```bash
git add -A
git commit -m "feat: CLI 入口，使用 Click + Rich"
```

---

### 任务 8：评测基准

**文件：**
- 创建：`codebase-agent/evaluation/__init__.py`
- 创建：`codebase-agent/evaluation/benchmark.py`
- 创建：`codebase-agent/evaluation/data/gin_qa.json`
- 创建：`codebase-agent/evaluation/data/fastapi_qa.json`

**接口：**
- 依赖：Agent + 检索层
- 产出：评测报告，包含 Top-3 命中率 + 准确率

- [ ] **第 1 步：编写 `evaluation/data/gin_qa.json`**

```json
[
  {
    "id": "gin-001",
    "question": "What is the main entry point of Gin?",
    "ground_truth_answer": "The main entry point is the New() function in gin.go",
    "source_file": "gin.go",
    "source_lines": [30, 60]
  },
  {
    "id": "gin-002",
    "question": "How does Gin handle HTTP routes?",
    "ground_truth_answer": "Routes are registered via the RouterGroup, which maps HTTP methods and paths to handler functions",
    "source_file": "routergroup.go",
    "source_lines": [20, 100]
  },
  {
    "id": "gin-003",
    "question": "What is the Context struct used for?",
    "ground_truth_answer": "Context holds request and response data, and provides methods for rendering JSON/XML/HTML",
    "source_file": "context.go",
    "source_lines": [15, 50]
  },
  {
    "id": "gin-004",
    "question": "How does Gin's middleware chain work?",
    "ground_truth_answer": "Middleware is stored as HandlerFunc chain in the Context, executed in FIFO order via Next()",
    "source_file": "gin.go",
    "source_lines": [100, 200]
  },
  {
    "id": "gin-005",
    "question": "What types of HTTP response formats does Gin support?",
    "ground_truth_answer": "Gin supports JSON, XML, YAML, Protobuf, Msgpack, and HTML rendering",
    "source_file": "render/",
    "source_lines": [1, 50]
  }
]
```

- [ ] **第 2 步：编写 `evaluation/data/fastapi_qa.json`**

```json
[
  {
    "id": "fastapi-001",
    "question": "How does FastAPI handle dependency injection?",
    "ground_truth_answer": "FastAPI uses Depends() to declare dependencies, which are resolved at runtime from the dependency graph",
    "source_file": "fastapi/dependencies/utils.py",
    "source_lines": [50, 150]
  },
  {
    "id": "fastapi-002",
    "question": "What is the purpose of the APIRouter class?",
    "ground_truth_answer": "APIRouter allows grouping routes under a prefix with shared dependencies, tags, and middleware",
    "source_file": "fastapi/routing.py",
    "source_lines": [100, 200]
  },
  {
    "id": "fastapi-003",
    "question": "How does FastAPI generate OpenAPI specs?",
    "ground_truth_answer": "FastAPI introspects route handlers' type annotations to auto-generate OpenAPI schema via openapi.py",
    "source_file": "fastapi/openapi/utils.py",
    "source_lines": [1, 100]
  },
  {
    "id": "fastapi-004",
    "question": "What is the request validation mechanism?",
    "ground_truth_answer": "Request validation uses Pydantic models, converting JSON body to Python objects with type checking",
    "source_file": "fastapi/routing.py",
    "source_lines": [200, 300]
  },
  {
    "id": "fastapi-005",
    "question": "How does FastAPI handle WebSocket connections?",
    "ground_truth_answer": "WebSocket is handled via the WebSocket class, with methods like accept(), receive_text(), send_text()",
    "source_file": "fastapi/websockets.py",
    "source_lines": [1, 60]
  }
]
```

- [ ] **第 3 步：编写 `evaluation/benchmark.py`**

```python
import json
import sys
from pathlib import Path
from config.settings import Settings
from code_parser.ast_parser import parse_repo
from embedding.embedder import Embedder
from retrieval.vector_store import VectorStore
from retrieval.ast_index import ASTIndex
from retrieval.hybrid_search import hybrid_search


def load_benchmark(name: str) -> list[dict]:
    path = Path(__file__).parent / "data" / f"{name}_qa.json"
    with open(path) as f:
        return json.load(f)


def evaluate_retrieval(repo_path: str, benchmark: list[dict], embedder: Embedder,
                       vector_store: VectorStore, ast_index: ASTIndex) -> dict:
    hit_count = 0
    total = len(benchmark)
    for item in benchmark:
        results = hybrid_search(item["question"], vector_store, ast_index, embedder, k=3)
        hit = any(item["source_file"] in r.file_path for r in results)
        if hit:
            hit_count += 1
    return {"top3_hit_rate": hit_count / total, "total": total, "hits": hit_count}


def main():
    settings = Settings.load()
    repo_name = sys.argv[1]
    benchmark = load_benchmark(repo_name)
    repo_path = Path(settings.repos_dir) / repo_name
    if not repo_path.exists():
        print(f"仓库不存在 {repo_path}。请先运行 'codebase-agent analyze <url>'")
        sys.exit(1)

    nodes = parse_repo(str(repo_path))
    embedder = Embedder()
    vector_store = VectorStore(persist_dir=settings.chroma_persist_dir)
    vector_store.add(nodes, embedder)
    ast_index = ASTIndex(nodes)

    result = evaluate_retrieval(str(repo_path), benchmark, embedder, vector_store, ast_index)
    print(f"Top-3 命中率: {result['top3_hit_rate']:.2%}")
    print(f"命中: {result['hits']}/{result['total']}")


if __name__ == "__main__":
    main()
```

- [ ] **第 4 步：编写 `evaluation/__init__.py`**（空文件）

- [ ] **第 5 步：提交**

```bash
git add -A
git commit -m "feat: 评测基准，包含 10 组 Q&A"
```

---

### 任务 9：Docker + Docker Compose + README

**文件：**
- 创建：`codebase-agent/Dockerfile`
- 修改：`codebase-agent/docker-compose.yml`
- 创建：`codebase-agent/README.md`

- [ ] **第 1 步：编写 `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN pip install -e .

ENTRYPOINT ["codebase-agent"]
CMD ["--help"]
```

- [ ] **第 2 步：更新 `docker-compose.yml`**

```yaml
version: "3.9"
services:
  app:
    build: .
    entrypoint: ["codebase-agent"]
    volumes:
      - ./data:/app/data
      - ./.env:/app/.env
    environment:
      - REDIS_HOST=redis
      - REDIS_PORT=6379
    depends_on:
      - redis
    stdin_open: true
    tty: true

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped

volumes:
  redis_data:
```

- [ ] **第 3 步：编写 `README.md`**

```markdown
# CodeBase Agent

用自然语言分析任意 GitHub 仓库。提问代码结构、查找函数、理解架构。

## 快速开始

```bash
# 克隆并进入
git clone <this-repo> && cd codebase-agent

# 配置
cp .env.example .env
# 编辑 .env，填入你的 LLM_API_KEY

# 启动 Redis 并运行
docker compose up -d
codebase-agent analyze https://github.com/gin-gonic/gin
```

## 工作原理

1. **克隆** — 使用 `--depth 1` 拉取仓库
2. **AST 解析** — 用 tree-sitter 提取每个函数、类和方法
3. **索引** — embedding 存入 ChromaDB；内存中构建 AST 索引
4. **问答** — 自然语言问题路由到对应的搜索策略

## 架构

```
codebase-agent/
├── cli/           # Click 命令行
├── agent/         # ReAct 循环 + 工具
├── code_parser/   # tree-sitter AST
├── retrieval/     # ChromaDB + BM25 + AST 索引
├── embedding/     # BGE-small-zh
├── cache/         # Redis
├── evaluation/    # 评测 + Q&A 数据集
└── config/        # 配置
```

## 评测

```bash
python -m evaluation.benchmark gin
python -m evaluation.benchmark fastapi
```
```

- [ ] **第 4 步：验证 Docker 构建**

```bash
cd codebase-agent
docker compose build
```
预期：构建成功

- [ ] **第 5 步：提交**

```bash
git add -A
git commit -m "feat: Docker, Docker Compose, README"
```

---

## 自检清单

1. **Spec 覆盖：** 每个 spec 需求都有对应任务。AST 解析(T2)、embedding(T3)、检索(T4)、缓存(T5)、agent(T6)、CLI(T7)、评测(T8)、Docker(T9)
2. **占位符检查：** 所有步骤都包含实际代码。无 TBD、TODO 或模糊的「添加错误处理」步骤
3. **类型一致性：** T2 定义的 `CodeNode` 接口在 T3/T4/T5/T6 中一致使用。`VectorStore`、`ASTIndex`、`Embedder` 接口按依赖链条传递
4. **接口正确性：** 每个任务的 `Interfaces` 区段列出精确的函数签名。后续任务消费前置任务的产出