# AGENTS.md

## Purpose
Generate exactly two tailored files from:
- `master_brag_sheet.md`
- `resume_base.md`
- `preferences.md`
- `job_description.txt`

Optional supporting output when requested:
- `<company_name>_application_answers.md`

## Recommended Workspace
Use the per-company workspace under `jobs/<company_slug>/`:
- Keep source-of-truth context under `context/`:
  - `context/master_brag_sheet.md`
  - `context/resume_base.md`
  - `context/preferences.md`
  - `context/resume_quality_guide.md`
  - `context/profile_links.md`
- Keep incoming job descriptions under `intake/`:
  - `intake/job_description.txt`
  - `intake/application_questions.txt`
- For each target job, use:
  - `jobs/<company_slug>/job_description.txt`
  - `jobs/<company_slug>/<company_slug>_resume.md`
  - `jobs/<company_slug>/<company_slug>_cover_letter.md`
  - `jobs/<company_slug>/<company_slug>_application_answers.md` (optional)

Helper commands:
- Create workspace: `./scripts/prepare_application.sh --company <company> --job-description <path> [--snapshot]`
- Export PDFs: `./scripts/export_pdfs.sh --company <company_slug>`
- Generate structured Q&A template: `./scripts/generate_application_answers.sh --company <company_slug>`

Track record behavior:
- If `prepare_application.sh` detects a changed `job_description.txt` for an existing company workspace, it snapshots current outputs into `jobs/<company_slug>/history/<timestamp>/` before new generation.

Outputs:
- `<company_name>_resume.md`
- `<company_name>_cover_letter.md`

`<company_name>` must come from the target employer in `job_description.txt`, be lowercase, use underscores instead of spaces, and include the file extension.

Example:
- `robinhood_resume.md`
- `robinhood_cover_letter.md`

## Inputs
- `@master_brag_sheet.md` — source-of-truth achievement inventory
- `@resume_base.md` — baseline career structure
- `@preferences.md` — tone and wording guardrails
- `@resume_quality_guide.md` — compact quality and formatting guide
- `@profile_links.md` — static links for copy/paste (LinkedIn, GitHub, Website)
- `@job_description.txt` — target role
- `@application_questions.txt` — user-defined application questions (optional)

`job_description.txt` should contain raw pasted role content only. Do not include a "Compressed Summary" template block in that file.

## Workflow
1. Compact `job_description.txt` into a short structured role summary.
2. Match the most relevant evidence from `master_brag_sheet.md`.
3. Use `resume_base.md` only as the factual scaffold.
4. Apply `preferences.md` and `resume_quality_guide.md`.
5. Produce both final files.

Optional workflow when requested:
6. Read `application_questions.txt` and produce `<company_name>_application_answers.md` with short, role-specific answers.

## Rules
- Do not invent experience, metrics, scope, or leadership.
- Use the brag sheet as evidence, not the resume base.
- Prioritize relevance to the job description.
- Use concise, credible, technical wording.
- Avoid generic corporate fluff.
- Keep personal projects separate from company work.
- Resume target: one page when exported to PDF.
- Cover letter target: one page when exported to PDF.
- Cover letter should stay concise (roughly 220-320 words unless user overrides).
- If generating application answers, include a top copy/paste links section from `profile_links.md`.
- The task is not complete until both files are produced with correct company-based filenames.

## Length Budget (Default)
- Resume summary: max 2 lines.
- Dexcom bullets: 4-6 max, only highest-signal evidence for the role.
- Older roles: 2-3 bullets each.
- Personal project: 1-2 bullets.
- Skills: compact grouped list, no long taxonomy.
- Cover letter: 3 short paragraphs plus sign-off.

## Brag references
- `@master_brag_sheet.md#built-a-regression-orchestration-and-historical-dashboard-platform-for-large-scale-automated-test-runs`
- `@master_brag_sheet.md#built-a-pr-driven-testrail-sync-tool-for-regulated-release-documentation`
- `@master_brag_sheet.md#centralized-cross-repo-ui-flow-logic-for-scalable-end-to-end-test-maintenance`
- `@master_brag_sheet.md#drove-architectural-cleanup-and-maintainability-standards-across-the-automation-codebase`
- `@master_brag_sheet.md#built-developer-tooling-to-simplify-execution-onboarding-and-local-parallel-test-workflows`
- `@master_brag_sheet.md#migrated-parallel-test-execution-architecture-to-gke-with-kubernetes-based-orchestration`
- `@master_brag_sheet.md#built-a-slack-to-jira-agent-to-convert-team-discussion-context-into-structured-work-items`
- `@master_brag_sheet.md#built-a-richer-test-results-dashboard-experience-by-shifting-runtime-visibility-away-from-testrail`
- `@master_brag_sheet.md#built-an-ai-agent-ready-repo-knowledge-system-for-coding-standards-refactors-and-test-planning-workflows`
- `@master_brag_sheet.md#built-an-ai-assisted-discord-trade-alert-system-to-react-faster-to-analyst-research-and-convert-unstructured-messages-into-validated-trading-signals-and-optional-broker-executable-orders`
