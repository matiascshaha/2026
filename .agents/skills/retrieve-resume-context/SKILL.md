---
name: retrieve-resume-context
description: Retrieve career context, preferences, profile links, and source-linked achievements from this repository before drafting application materials or contributing approved context/tooling changes.
---

# Retrieve resume context

1. Read root `AGENTS.md` and `docs/agent-workflow.md`.
2. From the repo root, run `python3 scripts/agent.py index`.
3. Search relevant topics with `python3 scripts/agent.py search --query "topic" --limit 5`.
4. Retrieve complete evidence with `python3 scripts/agent.py read --id <returned_id>`.
5. Read `document_preferences` and `document_resume_quality_guide` before drafting.
6. Use the brag sheet as achievement evidence and the resume base as the career scaffold.
7. Preserve source path, line references, and source hash for reviewable factual claims.

The CLI returns JSON and performs no writes or network requests. Search is lexical,
not a verdict on experience or job fit. Do not invent facts or merge personal projects
into company experience. Keep exports in ignored `.private/`; this repo is public.

For contributions, follow `CONTRIBUTING.md`, run `python3 scripts/agent.py validate`
and the synthetic tests, review the exact diff, and publish only within authorization.
A tool/context contribution never authorizes applications, radar changes, or sharing
private information. Use the existing job-application workflow for actual documents.
