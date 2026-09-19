import subprocess
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from config.settings import Settings
from code_parser.ast_parser import parse_repo
from code_parser.relationship import build_call_graph
from embedding.embedder import Embedder
from retrieval.vector_store import VectorStore
from retrieval.ast_index import ASTIndex
from agent.react_loop import process_query
from web.models import AnalyzeRequest, AnalyzeResponse, QueryRequest, QueryResponse, RepoInfo, PRRequest, PRResponse
from analysis.report import generate_report
from analysis.pr_diff import fetch_pr_diff, parse_github_url
from analysis.impact import analyze_impact


settings = Settings.load()
_embedder: Embedder | None = None
_indexes: dict[str, tuple[VectorStore, ASTIndex]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _embedder
    _embedder = Embedder()
    yield


app = FastAPI(title="CodeBase Agent API", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _ensure_repo(repo_name: str) -> Path:
    repo_path = Path(settings.repos_dir) / repo_name
    if not repo_path.exists():
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found. Analyze it first.")
    return repo_path


def _load_indexes(repo_name: str):
    if repo_name not in _indexes:
        repo_path = _ensure_repo(repo_name)
        nodes = parse_repo(str(repo_path))
        vector_store = VectorStore(persist_dir=settings.chroma_persist_dir)
        vector_store.add(nodes, _embedder)
        ast_index = ASTIndex(nodes)
        _indexes[repo_name] = (vector_store, ast_index)
    return _indexes[repo_name]


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
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise HTTPException(status_code=400, detail=f"Clone failed: {result.stderr}")

    nodes = parse_repo(str(repo_path))
    vector_store = VectorStore(persist_dir=settings.chroma_persist_dir)
    vector_store.add(nodes, _embedder)
    ast_index = ASTIndex(nodes)
    _indexes[repo_name] = (vector_store, ast_index)

    return AnalyzeResponse(repo_name=repo_name, nodes_count=len(nodes), status="analyzed")


@app.get("/repos", response_model=list[RepoInfo])
def list_repos():
    repos_dir = Path(settings.repos_dir)
    if not repos_dir.exists():
        return []
    results = []
    for d in repos_dir.iterdir():
        if d.is_dir():
            nodes = parse_repo(str(d))
            results.append(RepoInfo(name=d.name, analyzed=True, nodes_count=len(nodes)))
    return results


@app.get("/repos/{repo_name}/status", response_model=RepoInfo)
def repo_status(repo_name: str):
    repo_path = Path(settings.repos_dir) / repo_name
    if not repo_path.exists():
        return RepoInfo(name=repo_name, analyzed=False)
    nodes = parse_repo(str(repo_path))
    return RepoInfo(name=repo_name, analyzed=True, nodes_count=len(nodes))


@app.post("/repos/{repo_name}/query", response_model=QueryResponse)
def query_repo(repo_name: str, req: QueryRequest):
    repo_path = _ensure_repo(repo_name)
    vector_store, ast_index = _load_indexes(repo_name)
    answer = process_query(req.question, str(repo_path), vector_store, ast_index, _embedder, settings)
    return QueryResponse(answer=answer, repo_name=repo_name)


@app.get("/repos/{repo_name}/graph")
def get_graph(repo_name: str):
    repo_path = _ensure_repo(repo_name)
    nodes = parse_repo(str(repo_path))
    graph = build_call_graph(nodes)
    mermaid_lines = ["```mermaid", "graph TD"]
    for caller, callees in graph.items():
        for callee in callees:
            mermaid_lines.append(f"    {caller}[{caller}] --> {callee}[{callee}]")
    mermaid_lines.append("```")
    return {"mermaid": "\n".join(mermaid_lines), "graph": graph}


@app.post("/analysis/pr", response_model=PRResponse)
def analyze_pr(req: PRRequest):
    pr_info = parse_github_url(req.pr_url)
    if not pr_info:
        raise HTTPException(status_code=400, detail=f"Invalid PR URL: {req.pr_url}")

    repo_name = pr_info.repo
    repo_path = Path(settings.repos_dir) / repo_name
    if not repo_path.exists():
        cmd = ["git", "clone", "--depth", "1", f"https://github.com/{pr_info.owner}/{pr_info.repo}.git", str(repo_path)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise HTTPException(status_code=400, detail=f"Clone of {repo_name} failed: {result.stderr}")

    diff = fetch_pr_diff(req.pr_url, req.github_token)
    report = generate_report(diff, str(repo_path))
    return PRResponse(**report)