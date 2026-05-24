import type { Convention, ReviewStatus, ReviewTrigger, Severity, ReviewerKind } from "@/lib/types";

const STATUS_COLOR: Record<ReviewStatus, string> = {
  queued: "bg-neutral-100 text-neutral-700",
  running: "bg-sky-100 text-sky-700",
  done: "bg-emerald-100 text-emerald-700",
  failed: "bg-rose-100 text-rose-700",
};

const TRIGGER_GLYPH: Record<ReviewTrigger, string> = {
  manual: "✋",
  webhook: "🪝",
  scheduled: "⏰",
};

const SEVERITY_COLOR: Record<Severity, string> = {
  critical: "bg-rose-100 text-rose-700 border-rose-200",
  warning: "bg-amber-100 text-amber-700 border-amber-200",
  suggestion: "bg-sky-100 text-sky-700 border-sky-200",
};

export const REVIEWER_GLYPH: Record<ReviewerKind, string> = {
  security: "🔒",
  performance: "⚡",
  style: "🎨",
  tests: "🧪",
  maintainability: "🛠️",
};

export function StatusBadge({ status }: { status: ReviewStatus }) {
  const animate = status === "running" ? "animate-pulse" : "";
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_COLOR[status]} ${animate}`}>
      {status}
    </span>
  );
}

export function TriggerBadge({ trigger }: { trigger: ReviewTrigger }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-neutral-100 px-2 py-0.5 text-xs font-medium text-neutral-600">
      {TRIGGER_GLYPH[trigger]} {trigger}
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${SEVERITY_COLOR[severity]}`}>
      {severity}
    </span>
  );
}

const CONVENTION_COLOR: Record<Convention, string> = {
  praise: "bg-emerald-50 text-emerald-700 border-emerald-200",
  issue: "bg-rose-50 text-rose-700 border-rose-200",
  suggestion: "bg-sky-50 text-sky-700 border-sky-200",
  nit: "bg-neutral-50 text-neutral-600 border-neutral-200",
  question: "bg-violet-50 text-violet-700 border-violet-200",
  thought: "bg-amber-50 text-amber-700 border-amber-200",
  chore: "bg-neutral-50 text-neutral-600 border-neutral-200",
};

const CONVENTION_GLYPH: Record<Convention, string> = {
  praise: "🎉",
  issue: "❗",
  suggestion: "💡",
  nit: "🔹",
  question: "❓",
  thought: "💭",
  chore: "🧹",
};

export function ConventionBadge({ convention }: { convention: Convention }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium ${CONVENTION_COLOR[convention]}`}>
      <span>{CONVENTION_GLYPH[convention]}</span>
      <span>{convention}</span>
    </span>
  );
}
