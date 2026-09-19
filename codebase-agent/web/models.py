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