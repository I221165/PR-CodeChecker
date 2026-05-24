from typing import Literal
from pydantic import BaseModel


Severity = Literal["critical", "warning", "suggestion"]
ReviewerKind = Literal["security", "performance", "style", "tests", "maintainability"]
# Conventional Comments (https://conventionalcomments.org) — sets reader expectations
Convention = Literal["praise", "nit", "suggestion", "issue", "question", "thought", "chore"]


class ReviewComment(BaseModel):
    file: str                       # path/to/file.py
    line_start: int                 # 1-indexed; 0 means file-level (no specific line)
    line_end: int                   # inclusive
    severity: Severity
    convention: Convention = "issue"   # Conventional Comments prefix
    title: str                      # one-line headline
    body: str                       # 1-3 sentence explanation
    suggested_fix: str | None = None  # short code snippet or "what to change"
    origin_reviewers: list[ReviewerKind] | None = None  # which agent(s) flagged this (filled by consolidator)


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
    """Aggregated final output from all 5 reviewers, optionally consolidated by the 6th agent."""
    pr_url: str
    pr_title: str
    reviewers: list[ReviewerOutput]                    # raw outputs from the 5 parallel reviewers
    consolidated: list[ReviewComment] | None = None    # deduped, conventional-prefixed final list (preferred for display)
    overall_summary: str | None = None                 # 2-3 sentence verdict across the whole PR (from consolidator)

    @property
    def all_comments(self) -> list[ReviewComment]:
        """Final comments preferred for display: consolidated if present, else union of all reviewers."""
        if self.consolidated is not None:
            return self.consolidated
        return [c for r in self.reviewers for c in r.comments]

    @property
    def critical_count(self) -> int:
        return sum(1 for c in self.all_comments if c.severity == "critical")
