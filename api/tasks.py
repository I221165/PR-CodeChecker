"""Background runner for reviews. Runs in a ThreadPoolExecutor so the FastAPI
webhook handler returns 200 immediately (GitHub gives up after 10s)."""

import asyncio
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from api.db import Review, get_session
from services.github import fetch_pr
from services.github_poster import post_inline_review, post_summary_comment
from services.review import run_review_async

logger = logging.getLogger("tasks")

# One worker = reviews never race each other for Groq's TPM. Tune up on paid tier.
_executor = ThreadPoolExecutor(max_workers=1)


def _update(review_id: str, **fields) -> None:
    with get_session() as session:
        row = session.get(Review, review_id)
        if row is None:
            return
        for k, v in fields.items():
            setattr(row, k, v)
        row.updated_at = datetime.utcnow()
        session.add(row)
        session.commit()


def _run_review(review_id: str, post_to_github: bool) -> None:
    """Runs in a background thread."""
    try:
        with get_session() as session:
            row = session.get(Review, review_id)
            if row is None:
                return
            pr_url = row.pr_url
            owner = row.owner
            repo = row.repo
            pr_number = row.pr_number

        _update(review_id, status="running", progress_message="Fetching PR and running 5 reviewers...")

        def on_progress(reviewer: str, status: str) -> None:
            if reviewer == "__fetch__":
                msg = "Fetching PR..." if status == "started" else "PR fetched — starting reviewers"
            else:
                msg = f"{reviewer}: {status}"
            _update(review_id, progress_message=msg)

        report = asyncio.run(run_review_async(pr_url, on_progress=on_progress))

        _update(
            review_id,
            status="done",
            progress_message=f"Review complete — {len(report.all_comments)} findings",
            report_json=report.model_dump_json(),
            pr_title=report.pr_title,
        )

        if post_to_github:
            try:
                # Re-fetch PR meta to get the files+patches (needed for inline line validation)
                pr_meta = fetch_pr(pr_url)
                url = post_inline_review(
                    owner=owner,
                    repo=repo,
                    pr_number=pr_number,
                    head_sha=pr_meta.head_sha,
                    report=report,
                    pr_files=pr_meta.files,
                )
                _update(review_id, posted_comment_url=url, progress_message=f"Posted inline review: {url}")
            except Exception as e:
                # post_inline_review falls back to summary comment internally and raises
                # with the fallback URL embedded. Capture either way.
                msg = str(e)
                _update(review_id, progress_message=f"Review done, posting result: {msg}")

    except Exception as e:
        _update(
            review_id,
            status="failed",
            error=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
        )


def submit_review(review_id: str, post_to_github: bool = False) -> None:
    """Queue a review to run on the background worker."""
    _executor.submit(_run_review, review_id, post_to_github)
