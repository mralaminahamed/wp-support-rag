# WP Plugin Support Desk RAG — Documentation Set

**Author:** Al Amin Ahamed ([@mralaminahamed](https://github.com/mralaminahamed))
**Version:** 1.0 · May 2026

A grounded RAG service that answers WordPress plugin support questions from the author's own
documentation corpus (GitHub + WordPress.org), built to deflect repetitive support tickets.

## Contents

| File | Purpose |
|---|---|
| `01-SRS.md` | Software Requirements Specification — functional/non-functional requirements, acceptance criteria, golden-dataset spec. |
| `02-Architecture.md` | Architecture & design — components, request lifecycle, full data model (DDL), prompt registry, ADRs. |
| `03-Implementation-Plan.md` | Nine-phase build plan with definitions of done, the one-week schedule, and a risk register. |
| `04-Claude-Code-Prompts.md` | Ready-to-paste Claude Code prompts, one per phase, plus a final acceptance pass. |
| `claude-md/` | The `CLAUDE.md` context files — drop these into the repository as-is. |

## How the pieces fit

```
01-SRS  ──defines──▶  02-Architecture  ──realised by──▶  03-Implementation-Plan
                                                                  │
                                                          drives each phase
                                                                  ▼
                                                      04-Claude-Code-Prompts
                                                                  │
                                              executed under the conventions in
                                                                  ▼
                                                          claude-md/*  (loaded by Claude Code)
```

## Placing the CLAUDE.md files

Copy `claude-md/` into the repository root, preserving the tree. Claude Code loads the root file
globally and the nested files when working in their directories:

```
wp-support-rag/
├── CLAUDE.md                      ← claude-md/CLAUDE.md
├── docs/
│   ├── 01-SRS.md
│   ├── 02-Architecture.md
│   ├── 03-Implementation-Plan.md
│   └── 04-Claude-Code-Prompts.md
├── app/
│   ├── CLAUDE.md                  ← claude-md/app/CLAUDE.md
│   ├── ingestion/CLAUDE.md        ← claude-md/app/ingestion/CLAUDE.md
│   └── rag/CLAUDE.md              ← claude-md/app/rag/CLAUDE.md
└── tests/
    └── CLAUDE.md                  ← claude-md/tests/CLAUDE.md
```

Keep `docs/` in the working tree so the phase prompts can reference requirement and component ids
(e.g. FR-GN-6, ADR-002) directly.

## Build order

Run the phases in `04-Claude-Code-Prompts.md` strictly in sequence (Phase 0 → 8). Do not start a phase
until the previous phase's definition of done in `03-Implementation-Plan.md` is met. Gates
(`ruff`, `mypy --strict`, `pytest`, and the eval harness) must be green at every phase boundary.
