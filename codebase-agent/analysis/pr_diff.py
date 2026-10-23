import ssl
import re
import httpx
from dataclasses import dataclass, field


def _ssl_verify():
    """Use the OS trust store (via truststore) when available.

    Corporate/accelerator proxies (e.g. Steam++/Watt Toolkit) install their own
    root CA into the Windows store; Python's bundled certifi bundle does not know
    it, so plain httpx fails TLS verification. truststore makes httpx trust the
    same store git/.NET use."""
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        return True


@dataclass
class ChangedFile:
    path: str
    additions: int
    deletions: int
    patch: str
    status: str  # added, modified, deleted, renamed


@dataclass
class PRInfo:
    owner: str
    repo: str
    number: int
    title: str
    description: str
    base_branch: str
    head_branch: str


@dataclass
class PRDiff:
    pr: PRInfo
    files: list[ChangedFile] = field(default_factory=list)


def parse_github_url(url: str) -> PRInfo | None:
    pattern = r"github\.com/([^/]+)/([^/]+)/pull/(\d+)"
    m = re.search(pattern, url)
    if not m:
        return None
    return PRInfo(owner=m.group(1), repo=m.group(2), number=int(m.group(3)),
                  title="", description="", base_branch="", head_branch="")


def fetch_pr_diff(url: str, token: str | None = None) -> PRDiff:
    pr_info = parse_github_url(url)
    if not pr_info:
        raise ValueError(f"Invalid GitHub PR URL: {url}")

    headers = {"Accept": "application/vnd.github.v3.diff"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    diff_url = f"https://api.github.com/repos/{pr_info.owner}/{pr_info.repo}/pulls/{pr_info.number}"
    headers_meta = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers_meta["Authorization"] = f"Bearer {token}"

    with httpx.Client(verify=_ssl_verify()) as client:
        meta_resp = client.get(diff_url, headers=headers_meta)
        meta_resp.raise_for_status()
        meta = meta_resp.json()
        pr_info.title = meta.get("title", "")
        pr_info.description = meta.get("body", "")
        pr_info.base_branch = meta.get("base", {}).get("ref", "")
        pr_info.head_branch = meta.get("head", {}).get("ref", "")

        diff_resp = client.get(diff_url, headers=headers)
        diff_resp.raise_for_status()
        raw_diff = diff_resp.text

    files = _parse_diff(raw_diff)
    return PRDiff(pr=pr_info, files=files)


_DIFF_GIT_RE = re.compile(r"^diff --git a/(.+) b/(.+)$")


def _strip_path_prefix(path: str) -> str:
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path


def _parse_diff(raw_diff: str) -> list[ChangedFile]:
    files: list[ChangedFile] = []
    current: ChangedFile | None = None

    for line in raw_diff.split("\n"):
        if line.startswith("diff --git "):
            if current is not None:
                files.append(current)
            m = _DIFF_GIT_RE.match(line)
            path = m.group(2) if m else line[len("diff --git "):].strip()
            current = ChangedFile(path=path, additions=0, deletions=0, patch="", status="modified")
            continue
        if current is None:
            continue

        if line.startswith("new file mode"):
            current.status = "added"
        elif line.startswith("deleted file mode"):
            current.status = "deleted"
        elif line.startswith("rename from "):
            current.status = "renamed"
        elif line.startswith("rename to "):
            current.status = "renamed"
            current.path = _strip_path_prefix(line[len("rename to "):].strip())
        elif line.startswith("--- "):
            if line[4:].strip() == "/dev/null":
                current.status = "added"
        elif line.startswith("+++ "):
            target = line[4:].strip()
            if target == "/dev/null":
                current.status = "deleted"
            else:
                current.path = _strip_path_prefix(target)
        elif line.startswith("@@") or line.startswith(" ") or line.startswith("\\ No newline"):
            current.patch += line + "\n"
        elif line.startswith("+"):
            current.additions += 1
            current.patch += line + "\n"
        elif line.startswith("-"):
            current.deletions += 1
            current.patch += line + "\n"

    if current is not None:
        files.append(current)
    return files