"""Run all 5 reviewer agents in parallel against a PR, then aggregate.

CrewAI's `kickoff_async` lets us run each one-agent crew concurrently. With Groq's free tier
(12K TPM), 5 reviewers firing at once for a small-medium PR usually fits in budget;
for huge PRs we'd need throttling, but the diff truncation in github.py keeps things bounded.
"""

import asyncio
import os
from typing import Awaitable, Callable

from crewai import Crew, Process, Task

from services.agents import REVIEWERS
from services.consolidator import consolidate
from services.github import fetch_pr, format_pr_for_reviewer
from services.models import (
    PullRequestMeta,
    ReviewerKind,
    ReviewerOutput,
    ReviewReport,
)


def _task_for(reviewer_kind: ReviewerKind, pr_blob: str) -> tuple[Task, Crew]:
    """Build a one-agent crew + task for a given reviewer."""
    agent = REVIEWERS[reviewer_kind]()
    task = Task(
        description=f"""
        Review the following GitHub pull request from the perspective of your role only.

        Output a ReviewerOutput object with:
        - reviewer: "{reviewer_kind}"
        - overall_assessment: 2-3 sentences summarising the PR from your domain
        - comments: list of specific issues you found. Each comment needs:
            - file: the file path (must match a file in the diff)
            - line_start, line_end: 1-indexed line numbers from the diff hunks
              (use 0,0 if a comment is file-level rather than line-specific)
            - severity: "critical" (blocks merge) | "warning" (should fix) | "suggestion" (nice to have)
            - title: one-line headline
            - body: 1-3 sentence explanation, plain text
            - suggested_fix: short concrete change (snippet or instruction), or null

        If the PR has no issues in your domain, return an empty comments list and say so in overall_assessment.

        Pull request:
        {pr_blob}
        """,
        expected_output="A ReviewerOutput with overall_assessment and a list of ReviewComment objects.",
        output_pydantic=ReviewerOutput,
        agent=agent,
    )
    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
    return task, crew


async def _run_reviewer(reviewer_kind: ReviewerKind, pr_blob: str) -> ReviewerOutput:
    """Run one reviewer crew and return its structured output. Failures degrade to an empty review."""
    task, crew = _task_for(reviewer_kind, pr_blob)
    try:
        await crew.kickoff_async()
        result = task.output.pydantic
        # Guard: the LLM occasionally returns the wrong reviewer label — normalize
        if isinstance(result, ReviewerOutput):
            result.reviewer = reviewer_kind
            return result
        return ReviewerOutput(reviewer=reviewer_kind, overall_assessment="(parse failed)", comments=[])
    except Exception as e:
        return ReviewerOutput(
            reviewer=reviewer_kind,
            overall_assessment=f"(reviewer failed: {type(e).__name__}: {e})",
            comments=[],
        )


async def run_review_async(
    pr_url: str,
    reviewers: list[ReviewerKind] | None = None,
    on_progress: Callable[[str, str], None] | None = None,
    max_concurrent: int | None = None,
    stagger_seconds: float | None = None,
) -> ReviewReport:
    """Fetch PR, run reviewers concurrently (bounded), return aggregated report.

    Throttling controls (env-overridable, defaults safe for Groq free tier):
        max_concurrent: how many reviewers run in parallel at once. Default 1 (sequential).
          Groq free tier: 12K TPM. Each reviewer is ~3-5K tokens, so 1-2 concurrent is the cap.
          On Groq Dev Tier, set REVIEW_CONCURRENCY=5 in .env for full parallelism.
        stagger_seconds: delay between successive reviewer starts. Default 3.

    `on_progress(reviewer, status)` is called with status in ("started", "done") so a UI
    can stream updates. Optional.
    """
    if reviewers is None:
        reviewers = list(REVIEWERS.keys())  # type: ignore[arg-type]
    if max_concurrent is None:
        max_concurrent = int(os.getenv("REVIEW_CONCURRENCY", "1"))
    if stagger_seconds is None:
        stagger_seconds = float(os.getenv("REVIEW_STAGGER_SECONDS", "3"))

    if on_progress:
        on_progress("__fetch__", "started")
    pr: PullRequestMeta = fetch_pr(pr_url)
    pr_blob = format_pr_for_reviewer(pr)
    if on_progress:
        on_progress("__fetch__", "done")

    sem = asyncio.Semaphore(max_concurrent)

    async def wrapped(idx: int, kind: ReviewerKind) -> ReviewerOutput:
        # Stagger start times so even at concurrency >1, calls don't fire simultaneously
        if stagger_seconds and idx > 0:
            await asyncio.sleep(idx * stagger_seconds)
        async with sem:
            if on_progress:
                on_progress(kind, "started")
            out = await _run_reviewer(kind, pr_blob)
            if on_progress:
                on_progress(kind, "done")
            return out

    coros: list[Awaitable[ReviewerOutput]] = [wrapped(i, k) for i, k in enumerate(reviewers)]
    outputs = await asyncio.gather(*coros)

    # Step 2: consolidator agent — runs sequentially after the 5 are done
    consolidated_comments = None
    overall_summary = None
    if on_progress:
        on_progress("__consolidator__", "started")
    try:
        cons = await consolidate(list(outputs))
        consolidated_comments = cons.findings
        overall_summary = cons.overall_summary
    except Exception as e:
        # Consolidator failure isn't fatal — fall back to showing the raw 5-reviewer outputs
        overall_summary = f"(consolidator failed: {type(e).__name__}: {e})"
    if on_progress:
        on_progress("__consolidator__", "done")

    return ReviewReport(
        pr_url=pr.url,
        pr_title=pr.title,
        reviewers=list(outputs),
        consolidated=consolidated_comments,
        overall_summary=overall_summary,
    )


def run_review(pr_url: str, **kwargs) -> ReviewReport:
    """Sync wrapper around run_review_async for CLI/non-async callers."""
    return asyncio.run(run_review_async(pr_url, **kwargs))
