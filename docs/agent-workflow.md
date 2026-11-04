# Retrieving repository context

The repository's Markdown stays the source of truth. The read-only Python CLI makes
it discoverable without a database, model call, API key, network request, or package
installation. Use Python 3.10 or newer.

## Start small, retrieve only what is relevant

From the repository root:

```sh
python3 scripts/agent.py index
python3 scripts/agent.py search --query "authentication OAuth" --limit 3
python3 scripts/agent.py search --query "Python tooling" --kind achievement
python3 scripts/agent.py read --id document_preferences
python3 scripts/agent.py read --id <achievement_or_section_id_from_results>
python3 scripts/agent.py validate
```

- `index`: source paths/hashes, document IDs, section IDs, achievement IDs, titles,
  tags, and line references. It omits full source contents.
- `search`: deterministic lexical ranking across achievements and other context
  sections. Results include exact source references and excerpts of at most 3,000
  characters. Use `--kind achievement` or `--kind section` to narrow results.
- `read`: retrieve the complete document, section, or achievement by a discovered
  ID. For documents, canonical filenames such as `resume_base.md` also work.
  Arbitrary paths are not accepted.
- `export`: emit the whole context bundle when a consumer actually needs it.
- `validate`: check required sources, UTF-8 decoding, nonempty content, and unique
  achievement titles. This verifies structure, not factual truth or completeness.

Each data command prints exactly one JSON object. Success uses `ok: true`, exit 0.
Usage, source, or identifier errors use `ok: false`, an error code/message, and exit
2. `--help` is human-readable. An empty search result is successful, with
`total_matches: 0`; it does not mean the user lacks the skill or experience.

## Source and evidence contract

The five canonical source files are:

1. `context/master_brag_sheet.md`: achievement evidence.
2. `context/resume_base.md`: factual career structure.
3. `context/preferences.md`: tone and positioning.
4. `context/resume_quality_guide.md`: quality/formatting guidance.
5. `context/profile_links.md`: profile links.

Every response carries `schema_version: 1`. Documents include `id`, `path`,
`sha256`, `line_count`, and (when read/exported) `content`. Document contents preserve
the original UTF-8 bytes, including line endings. SHA-256 hashes refer to those bytes.

Achievements and sections include `id`, `title`, `source`, `source_sha256`,
`line_start`, `line_end`, and (when read/exported) `content`. Line references are
one-based and inclusive. Extracted section contents normalize line separators to
LF and trim outer whitespace. Use the source hash to detect a changed source before
reusing older line references.

Achievement IDs are derived from the case-insensitive title. They remain stable
when body details change; title changes produce new IDs. Duplicate titles fail
explicitly. Each brag entry uses `## Achievement` and a nonempty `Title:` field.
Professional/personal `Context`, `Organization`, and `Tags` are exposed when present.
No values are inferred from missing fields. Section IDs use source filename,
case-insensitive heading, and occurrence number; renaming/reordering duplicate
headings can change IDs.

Search ranks the number of distinct matched query terms first, then weighted title,
tag, and body matches. Matching is case-insensitive substring matching, not semantic
search. It never adds facts, assesses job eligibility, or certifies a claim. Read
complete records before relying on excerpts and keep professional work separate
from personal projects.

## Privacy

This repository is public. Source access does not imply permission to send its
contents somewhere else. Keep new exports and private working notes in ignored
`.private/`, and generated application packages in ignored `jobs/`:

```sh
mkdir -p .private
python3 scripts/agent.py export > .private/context.json
```

These directories are local conveniences, not encrypted storage. Git ignore rules
do not remove already tracked content or change repository visibility. Existing
personal source files are unchanged by this tooling contribution. Do not print
context into public CI logs or commit real data as test fixtures.

The CLI itself is read-only: it does not write files, update sources, submit
applications, contact employers, or change a job radar. Shell redirection above is
an explicit local export. Job radar and autopilot design are deferred.

## Agent contribution workflow

See [CONTRIBUTING.md](../CONTRIBUTING.md) for the exact branch, test, review, and draft
PR flow. Agents should first read root `AGENTS.md`, discover relevant context with
`index`/`search`, and retrieve only the records needed. Do not rewrite personal
context while making tooling changes. A later brag-sheet contribution should add
only owner-confirmed facts with a unique title and clear professional/personal
provenance, then run `validate`. Publication needs its own authorized scope.
