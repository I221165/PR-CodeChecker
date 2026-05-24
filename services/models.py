from typing import Literal
from pydantic import BaseModel


Severity = Literal["critical", "warning", "suggestion"]
ReviewerKind = Literal["security", "performance", "style", "tests", "maintainability"]


class ReviewComment(BaseModel):
    file: str                       # path/to/file.py
    line_start: int                 # 1-indexed; 0 means file-level (no specific line)
    line_end: int                   # inclusive
    severity: Severity
    title: str                      # one-line headline
    body: str                       # 1-3 sentence explanation
    suggested_fix: str | None = None  # short code snippet or "what to change"


class ReviewerOutput(BaseModel):
    """One reviewer's verdict on the entire PR."""
    reviewer: ReviewerKind
    overall_assessment: str         # 2-3 sentence summary across the whole PR
    comments: list[ReviewComment]


class PullRequestFile(BaseModel):
    """A single changed file in the PR."""
    filename: str
    status: str                     # "added", "modified", "removed", "renamed"
    additions: int
    deletions: int
    patch: str | None = None        # unified diff hunk(s); None for binary/huge files


class PullRequestMeta(BaseModel):
    """Just enough PR context for reviewers to do their job."""
    owner: str
    repo: str
    number: int
    title: str
    body: str
    head_sha: str
    base_sha: str
    author: str
    url: str
    files: list[PullRequestFile]


class ReviewReport(BaseModel):
    """Aggregated final output from all 5 reviewers."""
    pr_url: str
    pr_title: str
    reviewers: list[ReviewerOutput]

    @property
    def all_comments(self) -> list[ReviewComment]:
        return [c for r in self.reviewers for c in r.comments]

    @property
    def critical_count(self) -> int:
        return sum(1 for c in self.all_comments if c.severity == "critical")
