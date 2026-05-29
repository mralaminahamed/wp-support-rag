# Security Policy

Author: Al Amin Ahamed.

## Reporting a vulnerability

Please report security issues **privately** via GitHub Security Advisories:
<https://github.com/mralaminahamed/wp-support-rag/security/advisories/new>.

Do **not** open a public issue or PR for a vulnerability. Include a description,
reproduction steps, and impact. You'll get an acknowledgement and a fix
timeline.

## Scope

This is a self-hosted RAG service. Areas of particular interest:

- **Prompt injection / context isolation** — user questions and retrieved
  context are fenced as non-instructional input (NFR-SC-3); report any bypass.
- **Citation integrity** — only URLs of supplied chunks may appear in answers
  (FR-GN-8); report fabricated or smuggled citations.
- **Admin auth** — `/api/v1/admin/*` is bearer-protected (FR-DL-4); report
  authz gaps.
- **Secret handling** — API keys and the admin token come from the environment
  and must never be logged or returned in responses.
- **Rate limiting / abuse** of the public query and feedback endpoints.

## Handling secrets

Never include real API keys, tokens, or `.env` contents in issues, PRs, logs,
or test fixtures. All external calls are mocked or VCR-replayed in the test
suite.
