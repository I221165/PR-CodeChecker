"""The 6th agent. After the 5 parallel reviewers complete, this agent ingests all their
findings and produces a single, deduped, conventional-comment-formatted list.

Goals:
  - Merge overlapping findings (e.g. style + maintainability both flagging the same naming issue)
  - Assign Conventional Comments prefix (praise / nit / suggestion / issue / question / thought / chore)
  - Drop low-value noise when there are higher-severity findings
  - Produce a 2-3 sentence overall summary
"""

from crewai import Agent, Crew, Process, Task
from pydantic import BaseModel

from services.llms import lite_llm
from services.models import ReviewComment, ReviewerOutput


class ConsolidatedOutput(BaseModel):
    overall_summary: str
    findings: list[ReviewComment]


def consolidator_agent() -> Agent:
    # IMPORTANT: pass BOTH `llm` and `function_calling_llm` to the 8B model.
    # CrewAI uses `function_calling_llm` for the internal structured-output converter
    # that backs `output_pydantic`. If left unset it falls back to something that
    # competes with the 70B reviewer bucket — hence we explicitly point both at 8B.
    llm = lite_llm()
    return Agent(
        role="Review Consolidator",
        goal="Merge 5 reviewers' findings into one clean, prioritised, deduped list using Conventional Comments format",
        backstory=(
            "You are a tech lead who has just received 5 separate code reviews on the same PR from "
            "five specialists. Your job is to produce the ONE consolidated review that the author will "
            "actually read. You merge overlapping findings (same file:line range, same root issue) into "
            "single comments. You assign a Conventional Comments prefix to each. You drop pure noise — "
            "if there are real bugs, low-value style suggestions get dropped. You always include 1-2 "
            "'praise:' comments when the PR has genuinely good code, because real reviewers do this. "
            "You write a 2-3 sentence overall verdict at the top."
        ),
        llm=llm,
        function_calling_llm=llm,
        verbose=False,
    )


CONVENTION_GUIDE = """
Conventional Comments prefix guide (assign exactly one per finding):
  - "praise:"     genuinely good code worth calling out (use sparingly but always include 1-2 if warranted)
  - "issue:"      a real problem that should block merge (use for critical/warning severity)
  - "suggestion:" a concrete improvement that's not blocking
  - "nit:"        trivial style/preference; the author can ignore
  - "question:"   you need clarification before you can judge
  - "thought:"    forward-looking observation, no action required
  - "chore:"      housekeeping ask (add to changelog, update docs, etc.)
"""


async def consolidate(reviewer_outputs: list[ReviewerOutput]) -> ConsolidatedOutput:
    """Run the consolidator agent on the 5 reviewers' outputs."""
    raw_blob_parts = []
    for r in reviewer_outputs:
        raw_blob_parts.append(f"\n## Reviewer: {r.reviewer}")
        raw_blob_parts.append(f"Assessment: {r.overall_assessment}")
        if not r.comments:
            raw_blob_parts.append("(no findings)")
            continue
        for c in r.comments:
            line_spec = f"{c.line_start}" if c.line_start == c.line_end else f"{c.line_start}-{c.line_end}"
            raw_blob_parts.append(
                f"  - [{c.severity}] {c.file}:{line_spec} — {c.title}: {c.body}"
                + (f"  FIX: {c.suggested_fix}" if c.suggested_fix else "")
            )
    raw_blob = "\n".join(raw_blob_parts)

    agent = consolidator_agent()
    task = Task(
        description=f"""
        You have 5 specialists' findings on the same PR. Produce a ConsolidatedOutput:
          - overall_summary: 2-3 plain-English sentences. State the PR's main intent if obvious, the
            most important issue(s), and overall risk.
          - findings: a clean list of ReviewComment objects. For each:
              * If multiple specialists flagged the same issue (same file, similar line range,
                same root cause), MERGE them into one ReviewComment. Set origin_reviewers to all
                the specialists that caught it.
              * Drop pure duplicates (identical wording).
              * Drop "suggestion" severity items if there are ANY "critical" severity findings —
                don't make the author wade through nits when there's a real bug.
              * Assign a `convention` prefix to each (see guide below).
              * Keep file, line_start, line_end exactly as the original reviewer reported them.
              * If you can identify a clearly well-written piece of code in the assessments,
                add 1-2 "praise:" findings (severity="suggestion", file from context).

        {CONVENTION_GUIDE}

        5 specialists' raw findings:
        {raw_blob}
        """,
        expected_output="A ConsolidatedOutput with overall_summary + a deduped/prefixed list of findings.",
        output_pydantic=ConsolidatedOutput,
        agent=agent,
    )

    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
    await crew.kickoff_async()
    return task.output.pydantic
