# Career system documentation

The job radar finds opportunities. The `2026` repository supplies career context
and tools for resumes, cover letters, application answers, brag-sheet updates,
and profile updates. A proposed application coordinator connects those pieces
and records what happened.

## Read in this order

1. [Goals and user needs](goals.md): why the system exists and its boundaries.
2. [System requirements](requirements.md): required behavior and quality.
3. [Technical design](technical-design.md): components, contracts, storage, and flow.
4. [Future acceptance criteria](acceptance-criteria.md): a small verification backlog.

This is an initial design baseline dated 6 November 2026. Writing it does not
implement or enable the proposed workflow. No new automated tests are required
for this documentation phase; existing repository checks still apply.

## Current and proposed

| Capability | Current position |
| --- | --- |
| Job discovery | Existing external job radar; no radar implementation is in this repository. |
| Career evidence | Canonical Markdown and a merged read-only Python JSON interface. |
| Application preparation | Existing workspace, Q&A-template, and PDF-export helpers, used with agent/manual drafting. |
| Brag-sheet and profile maintenance | Owner-confirmed context edits and agent/manual drafting; no automatic external profile publishing. |
| Radar-to-application connection | Proposed. |
| Persistent application audit and duplicate prevention | Proposed. Existing file snapshots are only a partial record. |
| Unattended application submission | Proposed, not enabled by these documents. |

## Where information belongs

Keep these versioned, non-personal design documents in `docs/career-system/` and
link to them from the root README. Keep the CLI's detailed contract in
[agent-workflow.md](../agent-workflow.md), rather than copying it here.

This repository is public. Actual application answers, receipts, contact details,
job filters, permissions, and audit records do not belong in these documents,
public issues, examples, or CI logs. Use ignored `jobs/` for existing application
workspaces and private storage for the proposed audit system. Ignore rules are
not encryption, backup, or protection for already tracked content.

If the radar or coordinator later gets its own repository, implementation-specific
instructions should live beside that code. This directory should retain the
cross-system goals, requirements, and interface overview, with links rather than
duplicate specifications.

## Maintenance

Keep stable `G`, `FR`, and `NFR` identifiers. A behavior change should identify its
user goal, update affected requirements and design, and add acceptance criteria
when implementation begins. Mark proposals as implemented only with a reference
to the actual change and its verification. Record substantial later design
choices in short decision notes here when needed.
