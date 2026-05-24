"""Fetch a GitHub PR's metadata + changed files via the public REST API.

No PyGithub dependency — just `requests`. Works on public PRs without a token;
private PRs need `GITHUB_TOKEN` set in .env.
"""

import os
import re
from typing import Any

import requests

from services.models import PullRequestFile, PullRequestMeta

GITHUB_API = "https://api.github.com"

# Accepts forms like:
#   https://github.com/owner/repo/pull/123
#   https://github.com/owner/repo/pull/123/files
#   github.com/owner/repo/pull/123
PR_URL_RE = re.compile(r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<num>\d+)")


def parse_pr_url(url: str) -> tuple[str, str, int]:
    m = PR_URL_RE.search(url)
    if not m:
        raise ValueError(
            f"Not a recognised GitHub PR URL: {url!r}\n"
            "Expected: https://github.com/<owner>/<repo>/pull/<number>"
        )
    return m["owner"], m["repo"], int(m["num"])


def _headers() -> dict[str, str]:
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _get(path: str, **kwargs: Any) -> Any:
    resp = requests.get(f"{GITHUB_API}{path}", headers=_headers(), timeout=30, **kwargs)
    if resp.status_code == 404:
        raise FileNotFoundError(f"GitHub returned 404 for {path}")
    if resp.status_code == 403 and "rate limit" in resp.text.lower():
        raise RuntimeError(
            "GitHub API rate limit hit. Set GITHUB_TOKEN in .env to raise the cap "
            "from 60 to 5,000 requests/hour."
        )
    resp.raise_for_status()
    return resp.json()


def fetch_pr(url: str, max_files: int = 30, max_patch_chars: int = 8_000) -> PullRequestMeta:
    """Fetch PR metadata + changed files. Truncates very large diffs to keep token usage sane."""
    owner, repo, number = parse_pr_url(url)

    pr = _get(f"/repos/{owner}/{repo}/pulls/{number}")

    # GitHub paginates /files — fetch up to max_files
    files_raw: list[dict] = []
    page = 1
    while len(files_raw) < max_files:
        batch = _get(f"/repos/{owner}/{repo}/pulls/{number}/files", params={"per_page": 100, "page": page})
        if not batch:
            break
        files_raw.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    files_raw = files_raw[:max_files]

    files = []
    for f in files_raw:
        patch = f.get("patch")
        if patch and len(patch) > max_patch_chars:
            patch = patch[:max_patch_chars] + f"\n... [truncated, {len(patch) - max_patch_chars} more chars]"
        files.append(PullRequestFile(
            filename=f["filename"],
            status=f["status"],
            additions=f.get("additions", 0),
            deletions=f.get("deletions", 0),
            patch=patch,
        ))

    return PullRequestMeta(
        owner=owner,
        repo=repo,
        number=number,
        title=pr["title"],
        body=pr.get("body") or "",
        head_sha=pr["head"]["sha"],
        base_sha=pr["base"]["sha"],
        author=pr["user"]["login"],
        url=pr["html_url"],
        files=files,
    )


def format_pr_for_reviewer(pr: PullRequestMeta) -> str:
    """Render the PR as one big text blob to feed into a reviewer agent's prompt."""
    parts = [
        f"# PR #{pr.number}: {pr.title}",
        f"Author: @{pr.author}",
        f"Repo: {pr.owner}/{pr.repo}",
        "",
        "## Description",
        pr.body or "(no description)",
        "",
        f"## Changed files ({len(pr.files)})",
    ]
    for f in pr.files:
        parts.append(f"\n### {f.filename}  [{f.status}, +{f.additions} -{f.deletions}]")
        if f.patch:
            parts.append("```diff")
            parts.append(f.patch)
            parts.append("```")
        else:
            parts.append("_(binary or too large — no patch)_")
    return "\n".join(parts)
