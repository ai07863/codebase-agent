from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    repo_url: str
    branch: str | None = None


class AnalyzeResponse(BaseModel):
    repo_name: str
    nodes_count: int
    status: str


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    answer: str
    repo_name: str


class RepoInfo(BaseModel):
    name: str
    analyzed: bool
    nodes_count: int | None = None


class ErrorResponse(BaseModel):
    detail: str


class PRRequest(BaseModel):
    pr_url: str
    github_token: str | None = None


class FileBreakdown(BaseModel):
    file: str
    status: str
    additions: int
    deletions: int
    affected_functions: list[str]
    total_functions_in_file: int


class PRStats(BaseModel):
    files_changed: int
    additions: int
    deletions: int
    functions_affected: int


class PRResponse(BaseModel):
    pr_number: int
    title: str
    repo: str
    base_branch: str
    head_branch: str
    risk_score: str
    stats: PRStats
    files: list[FileBreakdown]
    impacted_callers: dict[str, list[str]]
    markdown_report: str