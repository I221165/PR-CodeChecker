"""Post a completed ReviewReport back to a GitHub PR.

Two modes:
  - post_summary_comment: single PR-level comment with the full markdown report (simple, robust)
  - post_inline_review:   a GitHub "review" with one inline comment per ReviewComment
                          (validates line numbers against the diff first; falls back to summary if needed)
"""

import os
import re

import requests

from services.models import PullRequestFile, ReviewComment, ReviewReport

GITHUB_API = "https://api.github.com"


def _headers() -> dict[str, str]:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError(
            "GITHUB_TOKEN missing — need a PAT with `pull_requests:write` (or `repo` for private repos) "
            "to post review comments back to GitHub."
        )
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


SEVERITY_GLYPH = {"critical": "🔴", "warning": "🟡", "suggestion": "🔵"}
REVIEWER_GLYPH = {
    "security": "🔒",
    "performance": "⚡",
    "style": "🎨",
    "tests": "🧪",
    "maintainability": "🛠️",
}


def render_markdown(report: ReviewReport) -> str:
    """Render the report as a GitHub-flavored markdown comment."""
    lines = [
        "## 🤖 Code Review Crew",
        f"_Reviewed by 5 specialised AI agents (security, performance, style, tests, maintainability)._",
        "",
        f"**{len(report.all_comments)} findings** "
        f"· {report.critical_count} critical "
        f"· {sum(1 for c in report.all_comments if c.severity == 'warning')} warnings "
        f"· {sum(1 for c in report.all_comments if c.severity == 'suggestion')} suggestions",
        "",
    ]
    for r in report.reviewers:
        glyph = REVIEWER_GLYPH.get(r.reviewer, "•")
        lines.append(f"\n<details><summary>{glyph} <b>{r.reviewer.title()}</b> — {len(r.comments)} finding(s)</summary>\n")
        lines.append(f"\n_{r.overall_assessment}_\n")
        if not r.comments:
            lines.append("\n_No issues flagged._")
        else:
            for c in r.comments:
                sev = SEVERITY_GLYPH.get(c.severity, "•")
                loc = (
                    f"`{c.file}`"
                    if c.line_start == 0
                    else f"`{c.file}:{c.line_start}`" + (f"-{c.line_end}" if c.line_end != c.line_start else "")
                )
                lines.append(f"\n#### {sev} {c.title}")
                lines.append(f"_{c.severity}_ · {loc}")
                lines.append("")
                lines.append(c.body)
                if c.suggested_fix:
                    lines.append("\n**Suggested fix:**")
                    lines.append(f"```\n{c.suggested_fix}\n```")
        lines.append("\n</details>")
    lines.append("\n---")
    lines.append("_Powered by [Code Review Crew](https://github.com/) · CrewAI + Groq Llama 3.3_")
    return "\n".join(lines)


def post_summary_comment(owner: str, repo: str, pr_number: int, report: ReviewReport) -> str:
    """Post one comment on the PR with the full markdown report. Returns the comment HTML URL."""
    body = render_markdown(report)
    # GitHub treats PR comments as Issue comments
    url = f"{GITHUB_API}/repos/{owner}/{repo}/issues/{pr_number}/comments"
    resp = requests.post(url, headers=_headers(), json={"body": body}, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"GitHub comment POST failed: {resp.status_code} {resp.text}")
    return resp.json()["html_url"]


# ── Inline-review machinery ───────────────────────────────────────────────────
_HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def _diff_commentable_lines(patch: str | None) -> set[int]:
    """Parse a unified-diff patch and return the set of new-file line numbers
    that GitHub will accept inline comments on (additions + context lines on the
    new side). Deletions are LEFT-side, we ignore them for inline posting."""
    if not patch:
        return set()
    lines: set[int] = set()
    new_line: int | None = None
    for raw in patch.splitlines():
        m = _HUNK_HEADER_RE.match(raw)
        if m:
            new_line = int(m.group(1))
            continue
        if new_line is None:
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            lines.add(new_line)
            new_line += 1
        elif raw.startswith("-") and not raw.startswith("---"):
            # deletion, doesn't consume a new-side line
            continue
        elif raw.startswith(" "):
            # context line, exists on both sides
            lines.add(new_line)
            new_line += 1
        # anything else (\\, blank, etc.) doesn't advance
    return lines


def _build_inline_comment(c: ReviewComment, commentable_by_file: dict[str, set[int]]) -> dict | None:
    """Convert a ReviewComment into a GitHub inline comment dict, or return None
    if the line isn't valid for inline (caller will fold it into the summary body)."""
    if c.line_start <= 0:
        return None
    valid = commentable_by_file.get(c.file)
    if not valid or c.line_start not in valid:
        return None

    body_parts = [
        f"**{SEVERITY_GLYPH.get(c.severity, '•')} {c.title}**  _({c.severity})_",
        "",
        c.body,
    ]
    if c.suggested_fix:
        # GitHub's ```suggestion blocks show as one-click-accept edits — but they require the
        # suggested text to literally replace those lines. We use a plain block instead so the
        # LLM doesn't have to produce something line-exact.
        body_parts.extend(["", "**Suggested fix:**", f"```\n{c.suggested_fix}\n```"])

    out: dict = {
        "path": c.file,
        "side": "RIGHT",
        "body": "\n".join(body_parts),
    }
    # Multi-line if range is wider than 1 line AND end is also commentable
    if c.line_end > c.line_start and c.line_end in valid:
        out["start_line"] = c.line_start
        out["start_side"] = "RIGHT"
        out["line"] = c.line_end
    else:
        out["line"] = c.line_start
    return out


def post_inline_review(
    owner: str,
    repo: str,
    pr_number: int,
    head_sha: str,
    report: ReviewReport,
    pr_files: list[PullRequestFile],
) -> str:
    """Post a GitHub PR review with inline comments per file:line, plus a summary body.

    Falls back to post_summary_comment() if zero comments survive line validation
    (e.g. PR has no diff patches we can attach to).
    """
    commentable = {f.filename: _diff_commentable_lines(f.patch) for f in pr_files}

    inline: list[dict] = []
    file_level_comments: list[ReviewComment] = []
    for r in report.reviewers:
        for c in r.comments:
            ic = _build_inline_comment(c, commentable)
            if ic is not None:
                inline.append(ic)
            else:
                file_level_comments.append(c)

    # Build the summary body: stats + assessments + any comments that couldn't go inline
    summary_lines = [
        "## 🤖 Code Review Crew",
        f"**{len(report.all_comments)} findings** "
        f"· {report.critical_count} critical "
        f"· {sum(1 for c in report.all_comments if c.severity == 'warning')} warnings "
        f"· {sum(1 for c in report.all_comments if c.severity == 'suggestion')} suggestions",
        "",
        f"Inline: **{len(inline)}**  ·  File-level (line outside diff): **{len(file_level_comments)}**",
        "",
    ]
    for r in report.reviewers:
        glyph = REVIEWER_GLYPH.get(r.reviewer, "•")
        summary_lines.append(f"- {glyph} **{r.reviewer.title()}** — {r.overall_assessment}")
    if file_level_comments:
        summary_lines.extend(["", "---", "### File-level findings (line not in diff)"])
        for c in file_level_comments:
            sev = SEVERITY_GLYPH.get(c.severity, "•")
            loc = f"`{c.file}`" + (f":{c.line_start}" if c.line_start else "")
            summary_lines.append(f"\n**{sev} {c.title}** _({c.severity})_  ·  {loc}\n\n{c.body}")
    summary_lines.append("\n---\n_Posted by [Code Review Crew](https://github.com/) · CrewAI + Groq_")
    summary_body = "\n".join(summary_lines)

    if not inline:
        # Nothing valid to attach inline — fall back to summary mode
        return post_summary_comment(owner, repo, pr_number, report)

    # Critical findings → request changes; otherwise just comment
    event = "REQUEST_CHANGES" if report.critical_count > 0 else "COMMENT"

    url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
    payload = {
        "commit_id": head_sha,
        "body": summary_body,
        "event": event,
        "comments": inline,
    }
    resp = requests.post(url, headers=_headers(), json=payload, timeout=30)
    if not resp.ok:
        # If GitHub rejects (e.g. some line still invalid), fall back to single comment
        # so the user still gets the review.
        try:
            err_detail = resp.json()
        except Exception:
            err_detail = resp.text
        fallback_url = post_summary_comment(owner, repo, pr_number, report)
        raise RuntimeError(
            f"Inline review failed ({resp.status_code}: {err_detail!r}); posted summary comment instead at {fallback_url}"
        )
    return resp.json()["html_url"]
