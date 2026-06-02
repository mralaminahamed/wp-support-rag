# Security Policy

## Scope

WP Plugin Support Desk RAG is an operator-facing admin console. It is **not** a public-facing service in its default configuration (`robots: noindex, nofollow`). The embeddable widget is the public surface — it only exposes the rate-limited query and feedback endpoints.

The security-critical surfaces are:

- **Admin console** (`/api/v1/admin/*`) — HTTP-only cookie JWT; never expose without a strong JWT secret
- **Public query API** (`/api/v1/query*`) — rate-limited per hashed IP; no authentication
- **Auth endpoints** (`/api/v1/auth/*`) — session cookies, password reset tokens, invite tokens
- **LLM prompt injection** — user input is fenced in delimited blocks, never concatenated into system instructions
- **Citation fabrication** — the citation validator strips any URL not present in the supplied chunk set; the LLM cannot cite sources it was not given

## What we consider a vulnerability

- Auth bypass on any `/api/v1/admin/*` endpoint
- Cookie theft or session fixation on the admin console
- Prompt injection that causes the system to emit fabricated URLs as citations
- Path traversal or SSRF via GitHub ingestion URLs or the Ollama base URL
- SQL injection via any query parameter
- Disclosure of `jwt_secret`, API keys, or hashed IP values in logs or responses
- XSS in the React admin console
- Invite token or password reset token reuse after expiry
- Docker container escape or privilege escalation

## What is out of scope

- Rate-limiting bypass on the public query endpoint (intentionally lenient for local development; operators must configure stricter limits for production)
- The accuracy or completeness of plugin documentation answers (this is a RAG tool grounded in provided docs — quality is an eval concern, not a security concern)
- Denial-of-service via large plugin docs (the chunker enforces a hard token cap)

## Reporting a vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Email: **mrabir.ahamed@gmail.com**

Include:
- A description of the vulnerability and its potential impact
- Steps to reproduce (curl commands, payloads, screenshots)
- The version / commit hash you tested against

You will receive an acknowledgement within 48 hours. We aim to release a fix within 14 days for critical issues and 30 days for lower-severity findings.

We do not currently have a bug bounty programme.

## Security design notes

| Decision | Where |
|---|---|
| HTTP-only cookie JWT (no localStorage) | `apps/api/app/api/routes_auth.py` |
| Access token 15 min TTL, refresh token 7 day TTL | `apps/api/app/config.py` |
| Fine-grained permissions embedded in JWT | `apps/api/app/api/deps.py` `require_permission` |
| Raw IPs never logged (SHA-256 hashed) | `apps/api/app/api/routes_query.py` |
| Prompt fencing (user input in delimited blocks) | `apps/api/app/prompts/` |
| Citation validator strips foreign URLs | `apps/api/app/rag/citation.py` |
| Cost circuit breaker (prevents unbounded LLM spend) | `apps/api/app/llm/` |
| Invite tokens expire after 48 h | `apps/api/app/db/models.py` `InviteToken` |
| Password reset tokens expire after 1 h | `apps/api/app/db/models.py` `PasswordResetToken` |

## Supported versions

Only the latest commit on the `main` branch receives security fixes. There are no versioned release tracks at this time.
