import re
import httpx
from dataclasses import dataclass, field


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

    with httpx.Client() as client:
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


def _parse_diff(raw_diff: str) -> list[ChangedFile]:
    files = []
    current_file = None
    current_patch = []
    additions = 0
    deletions = 0

    for line in raw_diff.split("\n"):
        if line.startswith("diff --git"):
            if current_file:
                files.append(ChangedFile(
                    path=current_file, additions=additions, deletions=deletions,
                    patch="\n".join(current_patch), status="modified"))
            current_file = None
            current_patch = []
            additions = 0
            deletions = 0
        elif line.startswith("--- a/") or line.startswith("+++ b/"):
            if line.startswith("+++ b/"):
                current_file = line[6:]
        elif line.startswith("@@") and current_file:
            parts = line.split(" ")
            for part in parts:
                if part.startswith("+"):
                    counts = part[1:].split(",")
                    additions += int(counts[1]) if len(counts) > 1 else 1
                elif part.startswith("-"):
                    counts = part[1:].split(",")
                    deletions += int(counts[1]) if len(counts) > 1 else 1

        if current_file:
            current_patch.append(line)

    if current_file:
        files.append(ChangedFile(
            path=current_file, additions=additions, deletions=deletions,
            patch="\n".join(current_patch), status="modified"))

    for f in files:
        if "/dev/null" in f.patch.split("\n")[0]:
            f.status = "deleted" if f.deletions > 0 else "added"

    return files