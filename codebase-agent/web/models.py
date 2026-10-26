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
    conversation_id: str | None = None
    context_conversation_id: str | None = None


class QueryResponse(BaseModel):
    answer: str
    repo_name: str
    conversation_id: str | None = None


class Message(BaseModel):
    role: str
    content: str
    created_at: str


class ConversationInfo(BaseModel):
    id: str
    repo: str
    title: str
    created_at: str
    updated_at: str


class Conversation(ConversationInfo):
    messages: list[Message] = []


class CreateConversationRequest(BaseModel):
    repo: str
    title: str = ""


class RepoInfo(BaseModel):
    name: str
    analyzed: bool
    nodes_count: int | None = None


class ErrorResponse(BaseModel):
    detail: str


class FileView(BaseModel):
    path: str
    content: str
    start: int
    end: int
    total_lines: int
    first_line: int = 1


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
    summary: str = ""
    stats: PRStats
    files: list[FileBreakdown]
    impacted_callers: dict[str, list[str]]
    markdown_report: str