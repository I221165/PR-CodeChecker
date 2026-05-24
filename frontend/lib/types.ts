// Mirrors api/db.py Review + services/models.py

export type Severity = "critical" | "warning" | "suggestion";
export type ReviewerKind = "security" | "performance" | "style" | "tests" | "maintainability";
export type ReviewStatus = "queued" | "running" | "done" | "failed";
export type ReviewTrigger = "manual" | "webhook" | "scheduled";
export type Convention = "praise" | "nit" | "suggestion" | "issue" | "question" | "thought" | "chore";

export interface ReviewComment {
  file: string;
  line_start: number;
  line_end: number;
  severity: Severity;
  convention: Convention;
  title: string;
  body: string;
  suggested_fix: string | null;
  origin_reviewers: ReviewerKind[] | null;
}

export interface ReviewerOutput {
  reviewer: ReviewerKind;
  overall_assessment: string;
  comments: ReviewComment[];
}

export interface ReviewReport {
  pr_url: string;
  pr_title: string;
  reviewers: ReviewerOutput[];
  consolidated: ReviewComment[] | null;   // deduped & conventional-prefixed (preferred for display)
  overall_summary: string | null;
}

export interface ReviewRow {
  id: string;
  pr_url: string;
  pr_title: string;
  owner: string;
  repo: string;
  pr_number: number;
  head_sha: string;
  trigger: ReviewTrigger;
  status: ReviewStatus;
  progress_message: string | null;
  error: string | null;
  posted_comment_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReviewDetail extends ReviewRow {
  report_json: string | null;
  report: ReviewReport | null;
}

export interface TriggerResponse {
  review_id: string;
  status: string;
}
