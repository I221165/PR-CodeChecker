"""FastAPI server with:
  - GET /                    health
  - POST /reviews            manually trigger a review by PR URL (returns review_id)
  - GET /reviews             list past reviews
  - GET /reviews/{id}        full status + report
  - POST /webhook/github     GitHub webhook receiver (HMAC verified) — auto-trigger on PR events
"""

import hashlib
import hmac
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlmodel import select

load_dotenv()

from api.db import Review, get_session, init_db
from api.tasks import submit_review
from services.github import parse_pr_url


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Code Review Crew API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class TriggerRequest(BaseModel):
    pr_url: str
    post_to_github: bool = False        # default: just store, don't post (safer)


@app.get("/")
def root():
    return {"status": "ok", "service": "code-review-crew"}


@app.post("/reviews")
def trigger_review(req: TriggerRequest):
    """Manually queue a review of a PR."""
    try:
        owner, repo, pr_number = parse_pr_url(req.pr_url)
    except ValueError as e:
        raise HTTPException(400, str(e))

    review_id = uuid.uuid4().hex
    with get_session() as session:
        session.add(Review(
            id=review_id,
            pr_url=req.pr_url,
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            trigger="manual",
            status="queued",
        ))
        session.commit()

    submit_review(review_id, post_to_github=req.post_to_github)
    return {"review_id": review_id, "status": "queued"}


@app.get("/reviews")
def list_reviews(limit: int = 50):
    with get_session() as session:
        rows = session.exec(select(Review).order_by(Review.created_at.desc()).limit(limit)).all()
        # Exclude the heavy report_json from the list view
        return [
            {k: v for k, v in r.model_dump().items() if k != "report_json"}
            for r in rows
        ]


@app.get("/reviews/{review_id}")
def get_review(review_id: str):
    with get_session() as session:
        row = session.get(Review, review_id)
        if row is None:
            raise HTTPException(404, "Review not found")
        data = row.model_dump()
        # Parse report_json back into structured form if present
        if data["report_json"]:
            try:
                data["report"] = json.loads(data["report_json"])
            except Exception:
                data["report"] = None
        return data


# ── GitHub webhook ────────────────────────────────────────────────────────────
def _verify_signature(body: bytes, signature_header: str | None) -> bool:
    """Verify GitHub's `X-Hub-Signature-256` header against GITHUB_WEBHOOK_SECRET."""
    secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    if not secret:
        # No secret configured — refuse all webhooks (fail closed)
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
):
    """Receive a GitHub webhook event. Verify signature, queue review if it's a PR event."""
    body = await request.body()

    if not _verify_signature(body, x_hub_signature_256):
        raise HTTPException(401, "Invalid signature")

    # Only act on pull_request events
    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"event {x_github_event!r} not handled"}

    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    action = payload.get("action")
    # Only trigger on these PR actions:
    #   opened          — new PR
    #   synchronize     — new commits pushed
    #   reopened        — PR reopened after close
    if action not in ("opened", "synchronize", "reopened"):
        return {"status": "ignored", "reason": f"action {action!r} not handled"}

    pr = payload.get("pull_request", {})
    pr_url = pr.get("html_url")
    head_sha = pr.get("head", {}).get("sha", "")
    repo_full = payload.get("repository", {}).get("full_name", "")
    if not pr_url or "/" not in repo_full:
        raise HTTPException(400, "Missing pull_request.html_url or repository.full_name")
    owner, repo = repo_full.split("/", 1)
    pr_number = pr.get("number")

    # Dedupe: skip if we already reviewed this exact head_sha
    with get_session() as session:
        existing = session.exec(
            select(Review).where(Review.pr_url == pr_url, Review.head_sha == head_sha, Review.status == "done")
        ).first()
        if existing:
            return {"status": "skipped", "reason": "already reviewed this commit", "review_id": existing.id}

        review_id = uuid.uuid4().hex
        session.add(Review(
            id=review_id,
            pr_url=pr_url,
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            head_sha=head_sha,
            trigger="webhook",
            status="queued",
        ))
        session.commit()

    submit_review(review_id, post_to_github=True)
    return {"status": "queued", "review_id": review_id, "action": action}
