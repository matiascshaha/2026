# Contributing

## Choose the right type of change

- **Tooling/docs:** improve context retrieval, scripts, tests, or instructions. Keep
  examples synthetic and leave the canonical personal context untouched.
- **Personal context:** add or correct career facts only when the owner asks and
  supplies or confirms them. Keep evidence, organization, ownership, and impact
  specific. Do not invent metrics, scope, dates, leadership, or skills.

This repository is public. New contact details, job filters, draft applications,
private achievement evidence, and context exports should stay in `.private/` or
`jobs/` unless the owner explicitly authorizes their publication. A request to
prepare a resume does not authorize a public commit of it. Ignore rules do not
protect already tracked files or remove their history.

## Discover before editing

```sh
git status --short
python3 scripts/agent.py index
python3 scripts/agent.py search --query "relevant topic" --limit 5
python3 scripts/agent.py read --id <id_from_results>
```

Read `AGENTS.md` and relevant workflow instructions. Keep unrelated user edits intact.
For facts, cite the returned source path and line range, and retain its `source_sha256`
if storing a local claim/evidence mapping. Search ranking is not factual verification.

## Make a focused branch

```sh
git switch -c feat/<short-description>
```

Prefer small, reviewable changes. The Python helper uses only the standard library
and supports Python 3.10+. Preserve machine-readable JSON output and structured error
behavior. Do not add a database or model/API dependency just to retrieve context.
No runtime credentials are needed for this workflow.

For later brag-sheet additions, follow the existing `## Achievement` blocks and
provide a unique `Title:`. Preserve the distinction between professional and personal
work, and tie impact to confirmed evidence. Body edits preserve the achievement ID;
renaming a title changes it. Do not duplicate a fact across conflicting entries.

## Verify

```sh
python3 scripts/agent.py validate
python3 -m unittest discover -s tests -v
for script in scripts/*.sh pdf_gen/*.sh; do bash -n "$script" || exit; done
git diff --check
git diff --stat
git status --short
```

Tests use synthetic temporary sources, never personal context. CI runs the tests on
Linux/macOS with Python 3.10/3.12. Shell PDF tests mock the converter; changes affecting
real rendering additionally need actual PDF generation, page checks, and visual
inspection. Disclose any unavailable checks instead of calling them passed.

When preparing application materials, the existing workflow still requires both
Markdown documents and both PDFs unless the owner waives PDF generation. The exporter
validates both documents and stages both PDFs before replacing prior files. The two
final renames are individually atomic, not a multi-file transaction.

## Review and contribute

Inspect the diff for new personal data, generated files, secrets, and unrelated
changes. Stage named files, not an unchecked `git add .`:

```sh
git add <reviewed-paths>
git diff --cached --check
git diff --cached
```

Commit and push the feature branch only within the owner's publication authorization.
Open a **draft pull request** against `main` unless the owner specifies otherwise.
Include the purpose, changed behavior, tests run, limitations, and privacy review.
Do not merge, deploy, change repo visibility, or grant access as a side effect.
Check CI for the exact pushed commit and report its result. A draft PR is reviewable
work, not permission to merge or publish additional personal information.
