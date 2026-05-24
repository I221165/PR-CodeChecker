import type { ReviewDetail, ReviewRow, TriggerResponse } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002";

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json();
}

export const api = {
  trigger(pr_url: string, post_to_github: boolean): Promise<TriggerResponse> {
    return fetchJson("/reviews", {
      method: "POST",
      body: JSON.stringify({ pr_url, post_to_github }),
    });
  },

  listReviews(limit = 50): Promise<ReviewRow[]> {
    return fetchJson(`/reviews?limit=${limit}`);
  },

  getReview(id: string): Promise<ReviewDetail> {
    return fetchJson(`/reviews/${id}`);
  },
};
