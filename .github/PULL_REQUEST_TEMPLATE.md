<!-- Author: Al Amin Ahamed. Keep PRs scoped and gate-green. -->

## Summary

<!-- What changed and why. Cite spec ids where relevant (e.g. FR-GN-6, NFR-SC-3). -->

## Related

- Spec: <!-- FR-/NFR- ids from docs/01-SRS.md -->
- Issue: <!-- #123, if any -->

## Changes

-

## Quality gates

<!-- All must pass before merge (definition of done, CLAUDE.md). -->

- [ ] `ruff check .` and `ruff format --check .` clean (apps/api)
- [ ] `mypy --strict app eval` clean (apps/api)
- [ ] `pytest` green (apps/api)
- [ ] Admin app: `pnpm type-check`, `pnpm lint`, `pnpm build`, `pnpm e2e` green (apps/admin)
- [ ] For `app/prompts/`, `app/rag/`, or `eval/dataset/` changes: eval harness passes its thresholds
- [ ] No stubs / `# TODO`; public functions have Google-style docstrings

## Notes for reviewers

<!-- Migrations, config flags, re-embedding, or rollout considerations. -->
