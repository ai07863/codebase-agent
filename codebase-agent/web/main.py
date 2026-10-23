import logging
import shutil
import subprocess
import traceback
from pathlib import Path
from threading import Lock
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from config.settings import Settings
from code_parser.ast_parser import parse_repo
from code_parser.repo_cache import parse_repo_cached
from code_parser.relationship import build_call_graph, graph_data, file_level_edges
from embedding.embedder import Embedder
from retrieval.vector_store import VectorStore
from retrieval.ast_index import ASTIndex
from agent.react_loop import process_query
from web.models import (
    AnalyzeRequest, AnalyzeResponse, QueryRequest, QueryResponse, RepoInfo,
    PRRequest, PRResponse, FileView, Conversation, ConversationInfo, CreateConversationRequest,
)
from web.files import resolve_repo_file, slice_lines
from web.store import ConversationStore
from analysis.report import generate_report
from analysis.pr_diff import fetch_pr_diff, parse_github_url


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("codebase-agent")

settings = Settings.load()
_history = ConversationStore(settings.history_db)
_STATIC_DIR = Path(__file__).resolve().parent / "static"
_MAX_VIEW_BYTES = 300_000
_embedder: Embedder | None = None
_indexes: dict[str, tuple[VectorStore, ASTIndex]] = {}
_index_lock = Lock()
_cache: dict[str, tuple[list, dict]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _embedder
    logger.info("正在加载 Embedding 模型 %s（首次需下载）...", settings.embedding_model)
    _embedder = Embedder(settings.embedding_model)
    logger.info("模型加载完成，服务已就绪")
    yield


app = FastAPI(title="CodeBase Agent API", version="0.2.0", lifespan=lifespan)

_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()] or [
    "http://127.0.0.1:8000", "http://localhost:8000",
]
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def _auth_middleware(request: Request, call_next):
    token = settings.api_token
    path = request.url.path
    public = path == "/health" or path.startswith("/ui") or path.startswith("/openapi")
    if token and not public:
        provided = request.headers.get("x-api-token") or request.headers.get("authorization", "")
        if provided.lower().startswith("bearer "):
            provided = provided[7:]
        if provided.strip() != token:
            return JSONResponse(status_code=401, content={"detail": "未授权：缺少或错误的 API Token"})
    return await call_next(request)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("未处理异常 %s %s：%s\n%s", request.method, request.url.path, exc, traceback.format_exc())
    detail = f"服务器内部错误：{exc}" if settings.debug else "服务器内部错误，请查看服务端日志"
    return JSONResponse(status_code=500, content={"detail": detail})
app.mount("/ui", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")


def _ensure_repo(repo_name: str) -> Path:
    repo_path = Path(settings.repos_dir) / repo_name
    if not repo_path.exists():
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found. Analyze it first.")
    return repo_path


def _parse_nodes(repo_name: str) -> list:
    repo_path = _ensure_repo(repo_name)
    return parse_repo_cached(str(repo_path), settings.repo_cache_dir)


def _load_nodes_and_index(repo_name: str) -> tuple[list, VectorStore, ASTIndex]:
    if _embedder is None:
        raise HTTPException(status_code=503, detail="Embedding model is still loading. Try again shortly.")
    nodes = _parse_nodes(repo_name)
    vector_store = VectorStore(repo_name=repo_name, persist_dir=settings.chroma_persist_dir)
    vector_store.add(nodes, _embedder)
    ast_index = ASTIndex(nodes)
    return nodes, vector_store, ast_index


def _load_indexes(repo_name: str):
    with _index_lock:
        if repo_name in _indexes:
            return _indexes[repo_name]
        cached = _cache.get(repo_name)
    # Reuse nodes already parsed for the graph; only embed once, outside the lock.
    if cached is not None:
        nodes, graph = cached
    else:
        nodes = _parse_nodes(repo_name)
        graph = build_call_graph(nodes)
    if _embedder is None:
        raise HTTPException(status_code=503, detail="Embedding model is still loading. Try again shortly.")
    vector_store = VectorStore(repo_name=repo_name, persist_dir=settings.chroma_persist_dir)
    vector_store.add(nodes, _embedder)
    ast_index = ASTIndex(nodes)
    with _index_lock:
        _indexes.setdefault(repo_name, (vector_store, ast_index))
        _cache.setdefault(repo_name, (nodes, graph))
        return _indexes[repo_name]


def _get_cached(repo_name: str):
    with _index_lock:
        if repo_name in _cache:
            return _cache[repo_name]
    nodes = _parse_nodes(repo_name)
    with _index_lock:
        _cache.setdefault(repo_name, (nodes, build_call_graph(nodes)))
        return _cache[repo_name]


def _store_index(repo_name: str, nodes: list, vector_store: VectorStore, ast_index: ASTIndex) -> None:
    with _index_lock:
        _indexes[repo_name] = (vector_store, ast_index)
        _cache[repo_name] = (nodes, build_call_graph(nodes))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/repos/analyze", response_model=AnalyzeResponse)
def analyze_repo(req: AnalyzeRequest):
    repos_dir = Path(settings.repos_dir)
    repos_dir.mkdir(parents=True, exist_ok=True)
    repo_name = req.repo_url.rstrip("/").split("/")[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]
    repo_path = repos_dir / repo_name

    if not repo_path.exists():
        cmd = ["git", "clone", "--depth", "1"]
        if req.branch:
            cmd.extend(["--branch", req.branch])
        cmd.extend([req.repo_url, str(repo_path)])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode != 0:
            raise HTTPException(status_code=400, detail=f"Clone failed: {result.stderr}")

    nodes, vector_store, ast_index = _load_nodes_and_index(repo_name)
    _store_index(repo_name, nodes, vector_store, ast_index)

    return AnalyzeResponse(repo_name=repo_name, nodes_count=len(nodes), status="analyzed")


@app.get("/repos", response_model=list[RepoInfo])
def list_repos():
    repos_dir = Path(settings.repos_dir)
    if not repos_dir.exists():
        return []
    with _index_lock:
        known_counts = {name: len(nodes) for name, (nodes, _) in _cache.items()}
    results = []
    for d in repos_dir.iterdir():
        if d.is_dir():
            results.append(RepoInfo(name=d.name, analyzed=True, nodes_count=known_counts.get(d.name)))
    return results


@app.get("/repos/{repo_name}/status", response_model=RepoInfo)
def repo_status(repo_name: str):
    repo_path = Path(settings.repos_dir) / repo_name
    if not repo_path.exists():
        return RepoInfo(name=repo_name, analyzed=False)
    nodes, _ = _get_cached(repo_name)
    return RepoInfo(name=repo_name, analyzed=True, nodes_count=len(nodes))


@app.post("/repos/{repo_name}/query", response_model=QueryResponse)
def query_repo(repo_name: str, req: QueryRequest):
    repo_path = _ensure_repo(repo_name)
    vector_store, ast_index = _load_indexes(repo_name)
    conv_id = req.conversation_id
    history = []
    if conv_id:
        conv = _history.get(conv_id)
        if conv:
            history = [{"role": m["role"], "content": m["content"]} for m in conv["messages"]]
    answer = process_query(req.question, str(repo_path), vector_store, ast_index, _embedder,
                           settings, history=history)
    if conv_id:
        _history.add_message(conv_id, "user", req.question)
        _history.add_message(conv_id, "assistant", answer)
    return QueryResponse(answer=answer, repo_name=repo_name, conversation_id=conv_id)


@app.get("/conversations", response_model=list[ConversationInfo])
def list_conversations():
    return _history.list()


@app.post("/conversations", response_model=Conversation)
def create_conversation(req: CreateConversationRequest):
    conv_id = _history.create(req.repo, req.title)
    return _history.get(conv_id)


@app.get("/conversations/{conv_id}", response_model=Conversation)
def get_conversation(conv_id: str):
    conv = _history.get(conv_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@app.delete("/conversations/{conv_id}")
def delete_conversation(conv_id: str):
    _history.delete(conv_id)
    return {"status": "deleted"}


@app.delete("/repos/{repo_name}")
def delete_repo(repo_name: str):
    repo_path = Path(settings.repos_dir) / repo_name
    with _index_lock:
        _indexes.pop(repo_name, None)
        _cache.pop(repo_name, None)
    try:
        VectorStore(repo_name=repo_name, persist_dir=settings.chroma_persist_dir).client.delete_collection(
            f"code_nodes_{repo_name}"
        )
    except Exception as exc:
        logger.warning("删除集合失败：%s", exc)
    if repo_path.exists():
        shutil.rmtree(repo_path, ignore_errors=True)
    return {"status": "deleted", "repo": repo_name}


@app.get("/repos/{repo_name}/file", response_model=FileView)
def read_repo_file(repo_name: str, path: str, start: int = 1, end: int = 0):
    repo_path = _ensure_repo(repo_name)
    try:
        target = resolve_repo_file(repo_path, path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"File not found: {path}") from exc

    if target.stat().st_size > _MAX_VIEW_BYTES:
        raise HTTPException(status_code=413, detail="File too large to display")
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=415, detail="Binary or non-UTF-8 file") from exc

    window = slice_lines(text, start, end)
    return FileView(
        path=path, content=window["content"], start=max(1, start),
        end=end or window["total_lines"], total_lines=window["total_lines"],
        first_line=window["first_line"],
    )


@app.get("/repos/{repo_name}/graph")
def get_graph(repo_name: str):
    _ensure_repo(repo_name)
    nodes, graph = _get_cached(repo_name)
    data = graph_data(nodes)
    data["graph"] = graph
    data["file_edges"] = file_level_edges(nodes)
    return data


def _checkout_pr_head(repo_path: Path, pr_number: int) -> None:
    """Fetch the PR head so diff line numbers match the parsed source."""
    try:
        fetch = subprocess.run(
            ["git", "-C", str(repo_path), "fetch", "--depth", "1", "origin", f"pull/{pr_number}/head"],
            capture_output=True, text=True, timeout=180,
        )
        if fetch.returncode == 0:
            subprocess.run(["git", "-C", str(repo_path), "checkout", "-f", "FETCH_HEAD"],
                           capture_output=True, text=True, timeout=60)
        else:
            logger.warning("fetch PR head failed: %s", fetch.stderr)
    except Exception as exc:
        logger.warning("checkout PR head failed: %s", exc)


@app.post("/analysis/pr", response_model=PRResponse)
def analyze_pr(req: PRRequest):
    pr_info = parse_github_url(req.pr_url)
    if not pr_info:
        raise HTTPException(status_code=400, detail=f"Invalid PR URL: {req.pr_url}")

    repo_name = pr_info.repo
    repo_path = Path(settings.repos_dir) / repo_name
    if not repo_path.exists():
        cmd = ["git", "clone", "--depth", "1", f"https://github.com/{pr_info.owner}/{pr_info.repo}.git", str(repo_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode != 0:
            raise HTTPException(status_code=400, detail=f"Clone of {repo_name} failed: {result.stderr}")

    _checkout_pr_head(repo_path, pr_info.number)

    try:
        diff = fetch_pr_diff(req.pr_url, req.github_token)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch PR diff: {exc}") from exc

    report = generate_report(diff, str(repo_path), settings)
    return PRResponse(**report)