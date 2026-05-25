# Code Review Crew

Multi-agent code review system. Paste a GitHub PR URL, get a structured review back from 5 specialized AI reviewers running **in parallel**:

| Reviewer | Looks for |
|----------|-----------|
| 🔒 Security | injection, XSS, secrets in code, auth bypasses, OWASP top 10 |
| ⚡ Performance | N+1 queries, O(n²) loops, blocking I/O, memory leaks |
| 🎨 Style | naming, formatting, idiomatic patterns per language |
| 🧪 Tests | coverage of new code, edge cases, test quality |
| 🛠️ Maintainability | complexity, modularity, naming, SOLID violations |

Each reviewer outputs structured comments (file, line range, severity, suggested fix). A **6th consolidator agent** then runs sequentially over their outputs: it dedupes overlapping findings (e.g. when style and maintainability both flag the same naming issue), drops noise, and formats every comment in [Conventional Comments](https://conventionalcomments.org) style (`praise:`, `issue:`, `nit:`, `suggestion:`, `question:`, `thought:`, `chore:`) so the reader knows at a glance whether a comment is blocking or optional.

## Why CrewAI for this?

Five **independent** agents (asyncio + crew.kickoff_async) — each reviewer runs against the same diff and produces its own ReviewerOutput. Aggregation happens after all return, then the consolidator merges them into the final review.

Concurrency is configurable. On **Groq free tier (12K TPM)**, default is sequential (`REVIEW_CONCURRENCY=1`) — firing 5 at once would burn ~13K input tokens in one second and trip the rate limit. On **Groq Dev Tier** or any paid tier, set `REVIEW_CONCURRENCY=5` in `.env` for full parallelism (5× faster).

```
REVIEW_CONCURRENCY=1      # safe default — sequential, ~75s for 5 reviewers
REVIEW_STAGGER_SECONDS=3  # delay between starts (only matters when CONCURRENCY > 1)
```

## Setup

```bash
git clone <repo>
cd code_review_crew

# Reuse the parent venv if you already have one:
# (from f:\CrewAi)
.venv\Scripts\activate

# Or create fresh:
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

```bash
cp .env.example .env
# Fill in GROQ_API_KEY (required) and GITHUB_TOKEN (optional)
```

## Run

### CLI
```bash
python main.py
```
Prompts for a GitHub PR URL, prints a markdown report.

### Backend
```bash
uvicorn api.server:app --port 8002 --reload
```
- `GET /docs` — Swagger UI
- `POST /reviews` — manually queue a review by PR URL
- `GET /reviews` — list past reviews
- `GET /reviews/{id}` — full status + report
- `POST /webhook/github` — GitHub webhook receiver (HMAC verified, see below)

Manual trigger example:
```bash
curl -X POST http://localhost:8002/reviews \
  -H "Content-Type: application/json" \
  -d '{"pr_url":"https://github.com/owner/repo/pull/123","post_to_github":false}'
```

## 🤖 GitHub webhook automation (auto-review every new PR)

Wire your repo's webhooks to this backend → every new PR (or new commit on a PR) automatically gets a review posted as a comment ~60s later. Same pattern as CodeRabbit, Greptile, Sourcery.

### 1. Expose the backend publicly (local dev with ngrok)

GitHub needs a public HTTPS URL to deliver webhooks to. For local dev, use [ngrok](https://ngrok.com/download):

```bash
# Terminal 1: backend
uvicorn api.server:app --port 8002

# Terminal 2: ngrok
ngrok http 8002
# → Forwarding: https://abc123.ngrok-free.app -> localhost:8002
```

Copy that `https://...ngrok-free.app` URL.

### 2. Generate a webhook secret
```bash
# Linux/macOS
openssl rand -hex 32

# Windows PowerShell
-join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Max 256) })
```
Put it in `.env` as `GITHUB_WEBHOOK_SECRET=...`.

### 3. Configure the webhook in your GitHub repo

`Repo → Settings → Webhooks → Add webhook`:

| Field | Value |
|-------|-------|
| Payload URL | `https://abc123.ngrok-free.app/webhook/github` |
| Content type | `application/json` |
| Secret | (same value as `GITHUB_WEBHOOK_SECRET` above) |
| SSL verification | Enable |
| Which events? | Let me select → **Pull requests** only |

### 4. Test it
Open a new PR in that repo. Within ~60s a comment appears with the full review.

### How it works
1. GitHub POSTs `pull_request` event to `/webhook/github`
2. Server verifies HMAC SHA-256 signature against your secret
3. Filters to `opened`, `synchronize`, `reopened` actions only
4. Dedupes by `head_sha` — won't re-review the same commit
5. Queues review on background thread, returns 200 immediately (GitHub gives up at 10s)
6. Background: fetch PR → 5 reviewers (parallel) → consolidator (sequential) → POST inline review with one comment per finding

## Frontend dashboard

Live dashboard for triggering reviews + watching them run:

```bash
cd frontend
npm install
npm run dev -- --port 3001
```

Then open <http://localhost:3001>:
- Home page lists all past reviews with status badges (queued / running / done / failed) and live polling
- Trigger form lets you queue any GitHub PR URL by hand (no webhook needed)
- Review detail page renders the consolidated findings with Conventional Comments badges, file:line locations, severity, and per-finding "flagged by:" attribution back to the original specialist(s)
- Set `NEXT_PUBLIC_API_URL` in `frontend/.env.local` if the backend runs on a different host/port

## Stack
- CrewAI 1.14 (5 agents, parallel kickoff)
- Groq Llama 3.3 70B
- GitHub REST API (no PyGithub dep — straight `requests`)
- FastAPI + SQLite + SSE
- Next.js 16 + Tailwind 4
