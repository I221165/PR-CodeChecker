"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { ReviewRow } from "@/lib/types";
import { StatusBadge, TriggerBadge } from "./components/badges";

export default function HomePage() {
  const router = useRouter();
  const [reviews, setReviews] = useState<ReviewRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [prUrl, setPrUrl] = useState("");
  const [postToGithub, setPostToGithub] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function load() {
    try {
      setReviews(await api.listReviews());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  async function handleTrigger(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!prUrl.trim()) return;
    setError(null);
    setSubmitting(true);
    try {
      const { review_id } = await api.trigger(prUrl.trim(), postToGithub);
      router.push(`/reviews/${review_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Reviews</h1>
        <p className="mt-1 text-sm text-neutral-600">
          Five AI agents review each PR in parallel: security, performance, style, tests, maintainability.
        </p>
      </div>

      <form onSubmit={handleTrigger} className="rounded-lg border border-neutral-200 bg-white p-4 space-y-3">
        <div>
          <label className="block text-xs font-medium text-neutral-700 mb-1">GitHub PR URL</label>
          <input
            value={prUrl}
            onChange={(e) => setPrUrl(e.target.value)}
            placeholder="https://github.com/owner/repo/pull/123"
            required
            className="w-full rounded-md border border-neutral-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-900"
          />
        </div>
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <label className="flex items-center gap-2 text-sm text-neutral-700">
            <input
              type="checkbox"
              checked={postToGithub}
              onChange={(e) => setPostToGithub(e.target.checked)}
              className="rounded border-neutral-300"
            />
            Post review as inline PR comments
            <span className="text-xs text-neutral-400">(needs GITHUB_TOKEN)</span>
          </label>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-50"
          >
            {submitting ? "Queuing..." : "Trigger review"}
          </button>
        </div>
      </form>

      {error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">{error}</div>
      )}

      <div className="space-y-3">
        <h2 className="text-sm font-medium text-neutral-700">
          {loading ? "Loading..." : `${reviews.length} review${reviews.length === 1 ? "" : "s"}`}
        </h2>
        {!loading && reviews.length === 0 && (
          <div className="rounded-lg border border-dashed border-neutral-300 p-8 text-center text-sm text-neutral-500">
            No reviews yet. Trigger one above, or set up the GitHub webhook so PRs auto-review.
          </div>
        )}
        {reviews.map((r) => (
          <Link
            key={r.id}
            href={`/reviews/${r.id}`}
            className="block rounded-lg border border-neutral-200 bg-white p-4 hover:border-neutral-300 hover:shadow-sm transition"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 text-xs text-neutral-500 flex-wrap">
                  <span>{r.owner}/{r.repo}</span>
                  <span>·</span>
                  <span>#{r.pr_number}</span>
                  <TriggerBadge trigger={r.trigger} />
                </div>
                <p className="mt-1 font-medium truncate">{r.pr_title || "(no title yet)"}</p>
                {r.progress_message && (
                  <p className="mt-1 text-xs text-neutral-500 truncate">{r.progress_message}</p>
                )}
              </div>
              <div className="flex flex-col items-end gap-1 shrink-0">
                <StatusBadge status={r.status} />
                <span className="text-xs text-neutral-400">{new Date(r.created_at).toLocaleString()}</span>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
