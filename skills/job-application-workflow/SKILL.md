---
name: job-application-workflow
description: Generate tailored resume, cover letter, and optional application answers inside this repository's `jobs/<company_slug>/` workflow. Use when the user wants to create or update a job application package from `context/` source docs plus `intake/job_description.txt`, or when they ask how to run this repo's application process step by step.
---

# Job Application Workflow

Use this skill when working in this repository to produce role-specific application materials.

## Core Workflow

1. Read `AGENTS.md` first.
2. Confirm the required source files exist in `context/`:
   - `master_brag_sheet.md`
   - `resume_base.md`
   - `preferences.md`
   - `resume_quality_guide.md`
   - `profile_links.md`
3. Read `intake/job_description.txt`.
4. If the user wants application answers, also read `intake/application_questions.txt`.
5. Create or update the company workspace under `jobs/<company_slug>/`.
6. Generate:
   - `<company_slug>_resume.md`
   - `<company_slug>_cover_letter.md`
7. Generate `<company_slug>_application_answers.md` only when requested or when application questions are clearly part of the task.
8. Export PDFs when the user asks for them or when the request explicitly includes export.

## Company Workspace Rules

- Use the employer name from the job description to derive `<company_slug>`.
- Use lowercase and underscores for the slug.
- Keep the job-specific files under `jobs/<company_slug>/`.
- Keep shared source-of-truth files in `context/`; do not duplicate or rewrite them unless the user asks.

Expected job workspace outputs:

- `jobs/<company_slug>/job_description.txt`
- `jobs/<company_slug>/<company_slug>_resume.md`
- `jobs/<company_slug>/<company_slug>_cover_letter.md`
- `jobs/<company_slug>/<company_slug>_application_answers.md` (optional)
- `jobs/<company_slug>/pdf/` for exported PDFs

## Content Rules

- Use `master_brag_sheet.md` as the evidence source.
- Use `resume_base.md` as the factual scaffold only.
- Follow `preferences.md` and `resume_quality_guide.md`.
- Do not invent experience, metrics, leadership, or scope.
- Prioritize the strongest evidence for the target role.
- Keep personal projects separate from company experience.
- Keep the resume and cover letter concise enough to target one page each when exported.

## Generation Guidance

- Start by compacting the job description into a short mental summary of role needs, stack, seniority, domain, and differentiators.
- Match the highest-signal brag entries to those needs before writing.
- Prefer specific builder/infrastructure/tooling language over generic QA wording when the role is engineering-leaning.
- For AI or platform roles, prioritize agentic tooling, internal workflows, context systems, infrastructure, and cross-functional enablement.
- For QA/SDET roles, prioritize bug isolation, structured testing, automation coverage, CI, and verification loops.

## Repo Execution Guidance

Preferred path when the shell tooling works:

- Run `./scripts/prepare_application.sh --company <company> --job-description ./intake/job_description.txt`
- Optionally run `./scripts/generate_application_answers.sh --company <company_slug> --overwrite`
- Run `./scripts/export_pdfs.sh --company <company_slug>` when PDF export is requested

Fallback path when the Bash-oriented scripts do not work, especially on Windows:

- Create `jobs/<company_slug>/` manually
- Copy `intake/job_description.txt` into `jobs/<company_slug>/job_description.txt`
- Write the markdown outputs directly into that folder
- If PDF export tooling is unavailable, use an available local PDF generation path rather than blocking on the repo scripts

## Answering "How Do I Use This Repo?"

When the user asks for step-by-step usage, give the short practical flow:

1. Fill in or maintain the source docs in `context/`
2. Paste a new role into `intake/job_description.txt`
3. Optionally add application questions to `intake/application_questions.txt`
4. Prepare `jobs/<company_slug>/`
5. Generate the resume and cover letter from `AGENTS.md`
6. Optionally generate application answers
7. Export PDFs

## Completion Standard

The task is not complete until the requested outputs exist in the correct company workspace with company-based filenames.
