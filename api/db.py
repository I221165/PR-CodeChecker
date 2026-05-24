from datetime import datetime
from typing import Optional

from sqlmodel import Field, Session, SQLModel, create_engine

DB_URL = "sqlite:///code_review_crew.db"
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})


class Review(SQLModel, table=True):
    """One review of one PR (possibly re-triggered when new commits are pushed)."""
    id: str = Field(primary_key=True)             # uuid hex
    pr_url: str = Field(index=True)
    pr_title: str = ""
    owner: str
    repo: str
    pr_number: int
    head_sha: str = ""                            # commit SHA reviewed — lets us skip if unchanged
    trigger: str = "manual"                       # "manual" | "webhook" | "scheduled"

    status: str = "queued"                        # queued | running | done | failed
    progress_message: Optional[str] = None
    error: Optional[str] = None
    posted_comment_url: Optional[str] = None      # the GitHub comment URL after posting

    report_json: Optional[str] = None             # full ReviewReport.model_dump_json()

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)
