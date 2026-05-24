"""CLI entry. Prompts for a GitHub PR URL, runs all 5 reviewers in parallel, prints markdown report."""

from dotenv import load_dotenv

load_dotenv()

# Importing services applies the crewai cache_breakpoint patch via services/__init__.py
from services.models import ReviewReport
from services.review import run_review

SEVERITY_GLYPH = {"critical": "🔴", "warning": "🟡", "suggestion": "🔵"}
REVIEWER_GLYPH = {
    "security": "🔒",
    "performance": "⚡",
    "style": "🎨",
    "tests": "🧪",
    "maintainability": "🛠️",
}


def render_markdown(report: ReviewReport) -> str:
    lines = [
        f"# Code Review: {report.pr_title}",
        f"<{report.pr_url}>",
        "",
        f"**{len(report.all_comments)} comments** "
        f"({report.critical_count} critical, "
        f"{sum(1 for c in report.all_comments if c.severity == 'warning')} warnings, "
        f"{sum(1 for c in report.all_comments if c.severity == 'suggestion')} suggestions)",
        "",
        "---",
    ]
    for r in report.reviewers:
        glyph = REVIEWER_GLYPH.get(r.reviewer, "•")
        lines.append(f"\n## {glyph} {r.reviewer.title()}")
        lines.append(f"_{r.overall_assessment}_")
        if not r.comments:
            lines.append("\n_No issues flagged._")
            continue
        for c in r.comments:
            sev_glyph = SEVERITY_GLYPH.get(c.severity, "•")
            loc = f"`{c.file}`" if c.line_start == 0 else f"`{c.file}:{c.line_start}`" + (
                f"-{c.line_end}" if c.line_end != c.line_start else ""
            )
            lines.append(f"\n### {sev_glyph} {c.title}")
            lines.append(f"_{c.severity}_ · {loc}")
            lines.append("")
            lines.append(c.body)
            if c.suggested_fix:
                lines.append("\n**Suggested fix:**")
                lines.append(f"```\n{c.suggested_fix}\n```")
    return "\n".join(lines)


def main() -> None:
    print("\n" + "=" * 60)
    print("CODE REVIEW CREW")
    print("=" * 60)
    pr_url = input("GitHub PR URL: ").strip()
    if not pr_url:
        print("No URL provided. Exiting.")
        return

    print(f"\nFetching PR + running 5 reviewers in parallel...\n")

    seen: set[str] = set()

    def on_progress(reviewer: str, status: str) -> None:
        key = f"{reviewer}:{status}"
        if key in seen:
            return
        seen.add(key)
        if reviewer == "__fetch__":
            print(f"  [{'⏳' if status == 'started' else '✓'}] Fetching PR")
        else:
            glyph = REVIEWER_GLYPH.get(reviewer, "•")
            print(f"  [{'⏳' if status == 'started' else '✓'}] {glyph} {reviewer.title()}")

    report = run_review(pr_url, on_progress=on_progress)

    md = render_markdown(report)
    print("\n" + "=" * 60)
    print(md)

    # Save full report
    out_path = "review.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"\n(Saved to {out_path})")


if __name__ == "__main__":
    main()
