import subprocess
import sys
from pathlib import Path
import click
from rich.console import Console
from rich.markdown import Markdown
from config.settings import Settings
from code_parser.ast_parser import parse_repo
from code_parser.repo_cache import parse_repo_cached
from code_parser.relationship import build_call_graph
from embedding.embedder import Embedder
from retrieval.vector_store import VectorStore
from retrieval.ast_index import ASTIndex
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
    nodes = parse_repo_cached(str(repo_path), settings.repo_cache_dir)
    console.print(f"[green]找到 {len(nodes)} 个函数/类[/]")

    console.print("[green]正在构建搜索索引...[/]")
    embedder = Embedder(settings.embedding_model)
    vector_store = VectorStore(repo_name=repo_name, persist_dir=settings.chroma_persist_dir)
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