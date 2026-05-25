"""The 6th agent. After the 5 parallel reviewers complete, this agent ingests all their
findings and produces a single, deduped, conventional-comment-formatted list.

Goals:
  - Merge overlapping findings (e.g. style + maintainability both flagging the same naming issue)
  - Assign Conventional Comments prefix (praise / nit / suggestion / issue / question / thought / chore)
  - Drop low-value noise when there are higher-severity findings
  - Produce a 2-3 sentence overall summary
"""

import json

from crewai import Agent, Crew, Process, Task
from pydantic import BaseModel, ValidationError

from services.llms import lite_llm
from services.models import ReviewComment, ReviewerOutput


class ConsolidatedOutput(BaseModel):
    overall_summary: str
    findings: list[ReviewComment]


def consolidator_agent() -> Agent:
    # IMPORTANT: pass BOTH `llm` and `function_calling_llm` to the 8B model.
    # CrewAI uses `function_calling_llm` for tool calls. We also skip `output_pydantic`
    # on the task because CrewAI's pydantic-output converter holds a global LLM
    # reference that picks up the 70B singleton initialised by the reviewers, blowing
    # the Groq free-tier TPM bucket. We parse the agent's raw output ourselves.
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


JSON_SCHEMA_HINT = """{
  "overall_summary": "string (2-3 sentences)",
  "findings": [
    {
      "file": "string",
      "line_start": 0,
      "line_end": 0,
      "severity": "<HOW BAD IT IS — pick ONE: critical | warning | suggestion>",
      "convention": "<COMMENT LABEL — pick ONE: praise | issue | nit | question | thought | chore | suggestion>",
      "title": "string",
      "body": "string",
      "suggested_fix": "string or null",
      "origin_reviewers": ["security", "performance", "style", "tests", "maintainability"]
    }
  ]
}

CRITICAL: severity and convention are DIFFERENT fields.
  - severity = the SEVERITY LEVEL of the finding (critical / warning / suggestion)
  - convention = the COMMENT LABEL (praise / issue / nit / question / thought / chore / suggestion)
  Examples of valid pairings:
    severity=critical, convention=issue       (real bug)
    severity=warning,  convention=issue       (likely bug, should fix)
    severity=warning,  convention=question    (unclear, ask author)
    severity=suggestion, convention=nit       (cosmetic preference)
    severity=suggestion, convention=praise    (callout of good code)
    severity=suggestion, convention=suggestion (concrete optional improvement)
"""


# Map convention values -> the severity that's typically appropriate.
# Used as fallback when the model puts a convention value in the severity slot.
_CONVENTION_TO_SEVERITY: dict[str, str] = {
    "issue": "warning",
    "nit": "suggestion",
    "praise": "suggestion",
    "question": "suggestion",
    "thought": "suggestion",
    "chore": "suggestion",
    "suggestion": "suggestion",
}

_VALID_SEVERITIES = {"critical", "warning", "suggestion"}
_VALID_CONVENTIONS = {"praise", "issue", "suggestion", "nit", "question", "thought", "chore"}


def _fixup_finding(f: dict) -> dict:
    """Salvage a finding where severity and convention got swapped/confused.

    Small models (8B) sometimes put convention values into the severity field. Detect
    that and recover instead of failing the whole consolidator.
    """
    sev = f.get("severity")
    conv = f.get("convention")

    # severity holds a convention value → swap-and-infer
    if sev not in _VALID_SEVERITIES and sev in _VALID_CONVENTIONS:
        # If convention slot is empty or also invalid, promote severity's value to convention
        if conv not in _VALID_CONVENTIONS:
            f["convention"] = sev
        f["severity"] = _CONVENTION_TO_SEVERITY.get(sev, "suggestion")

    # convention holds a severity value → swap
    if f.get("convention") not in _VALID_CONVENTIONS and f.get("convention") in _VALID_SEVERITIES:
        # Pick a sensible default convention for that severity
        f["convention"] = {"critical": "issue", "warning": "issue", "suggestion": "suggestion"}.get(
            f["convention"], "suggestion"
        )

    # Default any still-missing/invalid fields
    if f.get("severity") not in _VALID_SEVERITIES:
        f["severity"] = "suggestion"
    if f.get("convention") not in _VALID_CONVENTIONS:
        f["convention"] = "suggestion"
    return f


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    return text.strip()


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
        You have 5 specialists' findings on the same PR. Produce ONE consolidated review.

        Rules:
          * If multiple specialists flagged the same issue (same file, similar line range,
            same root cause), MERGE them into one finding. Set origin_reviewers to all the
            specialists that caught it.
          * Drop pure duplicates (identical wording).
          * Drop "suggestion" severity items if there are ANY "critical" severity findings —
            don't bury bugs under nits.
          * Assign a `convention` prefix to each (see guide).
          * Keep file, line_start, line_end EXACTLY as the original reviewer reported.
          * Include 1-2 "praise" findings only if the assessments mention genuinely good code.

        {CONVENTION_GUIDE}

        5 specialists' raw findings:
        {raw_blob}

        Respond with VALID JSON ONLY (no prose, no markdown fences). Schema:
        {JSON_SCHEMA_HINT}
        """,
        expected_output="A single JSON object matching the schema above. No surrounding prose or fences.",
        agent=agent,
    )

    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
    result = await crew.kickoff_async()

    # Parse the raw text output ourselves — skips CrewAI's broken Pydantic converter.
    raw = _strip_fences(str(result.raw) if hasattr(result, "raw") else str(result))
    try:
        data = json.loads(raw)
        # 8B models sometimes confuse severity/convention — repair before validating
        if isinstance(data.get("findings"), list):
            data["findings"] = [_fixup_finding(f) if isinstance(f, dict) else f for f in data["findings"]]
        return ConsolidatedOutput.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as e:
        raise RuntimeError(f"Could not parse consolidator output: {type(e).__name__}: {e}\nRaw: {raw[:300]}") from e
