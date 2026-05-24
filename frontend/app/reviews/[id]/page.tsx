"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { ReviewDetail } from "@/lib/types";
import { ConventionBadge, REVIEWER_GLYPH, SeverityBadge, StatusBadge, TriggerBadge } from "@/app/components/badges";

export default function ReviewDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [review, setReview] = useState<ReviewDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setReview(await api.getReview(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    load();
    const iv = setInterval(() => {
      // Stop polling once terminal
      if (review && (review.status === "done" || review.status === "failed")) return;
      load();
    }, 2000);
    return () => clearInterval(iv);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, review?.status]);

  if (error && !review) {
    return <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">{error}</div>;
  }
  if (!review) return <p className="text-sm text-neutral-500">Loading...</p>;

  const r = review.report;
  // Prefer consolidated view; fall back to flattened reviewer comments
  const finalComments = r?.consolidated ?? (r ? r.reviewers.flatMap((x) => x.comments) : []);
  const counts = r ? {
    total: finalComments.length,
    critical: finalComments.filter((c) => c.severity === "critical").length,
    warning: finalComments.filter((c) => c.severity === "warning").length,
    suggestion: finalComments.filter((c) => c.severity === "suggestion").length,
  } : null;

  return (
    <div className="space-y-6">
      <Link href="/" className="text-sm text-neutral-600 hover:text-neutral-900">← Back to reviews</Link>

      <div className="rounded-lg border border-neutral-200 bg-white p-5 space-y-3">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="min-w-0">
            <p className="text-xs text-neutral-500">
              {review.owner}/{review.repo} · PR #{review.pr_number}
            </p>
            <h1 className="mt-1 text-xl font-semibold leading-tight">
              {review.pr_title || "(loading title...)"}
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <TriggerBadge trigger={review.trigger} />
            <StatusBadge status={review.status} />
          </div>
        </div>
        <div className="flex items-center gap-4 text-xs text-neutral-500 flex-wrap">
          <a href={review.pr_url} target="_blank" rel="noopener noreferrer" className="text-sky-700 hover:text-sky-900 underline break-all">
            {review.pr_url}
          </a>
          {review.head_sha && <span>commit <code className="bg-neutral-100 px-1.5 py-0.5 rounded">{review.head_sha.slice(0, 8)}</code></span>}
        </div>
        {review.progress_message && (
          <p className="text-sm text-neutral-700">{review.progress_message}</p>
        )}
        {review.posted_comment_url && (
          <a
            href={review.posted_comment_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700"
          >
            🔗 View posted comment on GitHub
          </a>
        )}
      </div>

      {review.status === "failed" && review.error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">
          <p className="font-medium mb-1">Failed</p>
          <pre className="whitespace-pre-wrap text-xs max-h-64 overflow-y-auto">{review.error}</pre>
        </div>
      )}

      {r?.overall_summary && (
        <section className="rounded-lg border border-neutral-200 bg-white p-5">
          <h2 className="text-sm font-medium text-neutral-700 mb-2">Overall verdict</h2>
          <p className="text-sm text-neutral-800 italic">{r.overall_summary}</p>
        </section>
      )}

      {counts && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label="Total findings" value={counts.total} />
          <Stat label="Critical" value={counts.critical} color={counts.critical > 0 ? "rose" : undefined} />
          <Stat label="Warnings" value={counts.warning} color={counts.warning > 0 ? "amber" : undefined} />
          <Stat label="Suggestions" value={counts.suggestion} />
        </div>
      )}

      {/* Consolidated findings (preferred view) */}
      {r?.consolidated && r.consolidated.length > 0 && (
        <section className="rounded-lg border border-neutral-200 bg-white p-5 space-y-3">
          <h2 className="text-sm font-medium text-neutral-700">Findings</h2>
          <ul className="space-y-4">
            {r.consolidated.map((c, i) => (
              <li key={i} className="border-l-4 border-neutral-200 pl-4 py-1">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <ConventionBadge convention={c.convention} />
                      <p className="font-medium">{c.title}</p>
                    </div>
                    <p className="text-xs text-neutral-500 mt-1 flex items-center gap-2 flex-wrap">
                      <code className="bg-neutral-100 px-1 py-0.5 rounded">{c.file}{c.line_start > 0 && `:${c.line_start}`}{c.line_end > c.line_start && `-${c.line_end}`}</code>
                      {c.origin_reviewers && c.origin_reviewers.length > 0 && (
                        <span className="text-neutral-400">
                          flagged by: {c.origin_reviewers.map((rk) => `${REVIEWER_GLYPH[rk]} ${rk}`).join(", ")}
                        </span>
                      )}
                    </p>
                  </div>
                  <SeverityBadge severity={c.severity} />
                </div>
                <p className="mt-2 text-sm text-neutral-700">{c.body}</p>
                {c.suggested_fix && (
                  <details className="mt-2">
                    <summary className="text-xs text-neutral-500 cursor-pointer hover:text-neutral-700">Suggested fix</summary>
                    <pre className="mt-2 whitespace-pre-wrap rounded bg-neutral-50 p-3 text-xs font-mono">{c.suggested_fix}</pre>
                  </details>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Raw per-reviewer assessments — collapsed by default */}
      {r?.reviewers && (
        <details className="rounded-lg border border-neutral-200 bg-white p-5">
          <summary className="text-sm font-medium text-neutral-700 cursor-pointer hover:text-neutral-900">
            Raw per-reviewer assessments (before consolidation)
          </summary>
          <div className="mt-4 space-y-4">
            {r.reviewers.map((rv) => (
              <div key={rv.reviewer} className="border-l-2 border-neutral-200 pl-3">
                <h3 className="text-sm font-medium flex items-center gap-2">
                  <span>{REVIEWER_GLYPH[rv.reviewer]}</span>
                  <span className="capitalize">{rv.reviewer}</span>
                  <span className="text-xs text-neutral-400">— {rv.comments.length} raw finding{rv.comments.length === 1 ? "" : "s"}</span>
                </h3>
                <p className="text-xs italic text-neutral-600 mt-1">{rv.overall_assessment}</p>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: number; color?: "rose" | "amber" }) {
  const cls = color === "rose" ? "text-rose-700" : color === "amber" ? "text-amber-700" : "text-neutral-900";
  return (
    <div className="rounded-md border border-neutral-200 bg-white px-3 py-2">
      <p className="text-xs text-neutral-500">{label}</p>
      <p className={`text-xl font-semibold ${cls}`}>{value}</p>
    </div>
  );
}
