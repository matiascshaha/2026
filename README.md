# Job Application Workflow

## Daily Flow (2 commands + 1 prompt)
1. Prepare workspace for a company:
```bash
./scripts/prepare_application.sh --company apple --job-description ./intake/job_description.txt
```

To force a history snapshot before regenerating even when the JD is unchanged:
```bash
./scripts/prepare_application.sh --company apple --job-description ./intake/job_description.txt --snapshot
```

`job_description.txt` should be raw pasted content only. If a `# Compressed Summary` placeholder exists, `prepare_application.sh` strips it automatically in the company workspace copy.

If the same company already has outputs and the incoming job description changes, `prepare_application.sh` creates an automatic snapshot under:
```text
./jobs/<company_slug>/history/<timestamp>/
```
This preserves prior resume/cover letter/application answers/PDFs as a local track record.

2. Ask Codex in chat:
```text
Generate apple resume + cover letter from AGENTS.md and export PDFs.
```
3. Optional manual export:
```bash
./scripts/export_pdfs.sh --company apple
```

## Structured Application Q&A
Set your custom questions in:
```text
./intake/application_questions.txt
```

Generate a structured answers file in the company workspace:
```bash
./scripts/generate_application_answers.sh --company apple --overwrite
```

Then ask Codex to fill answers into:
```text
./jobs/apple/apple_application_answers.md
```

Static copy/paste links are kept in:
```text
./context/profile_links.md
```

## PDF Length Control (Default 1 page each)
`export_pdfs.sh` enforces page limits by default:
- resume max pages: `1`
- cover letter max pages: `1`

Overrides:
```bash
./scripts/export_pdfs.sh --company apple --max-resume-pages 1 --max-cover-letter-pages 1
```

Disable checks:
```bash
./scripts/export_pdfs.sh --company apple --no-page-check
```

## Structure
```text
.
├── AGENTS.md
├── README.md
├── context/
│   ├── master_brag_sheet.md
│   ├── resume_base.md
│   ├── preferences.md
│   ├── resume_quality_guide.md
│   └── profile_links.md
├── intake/
│   ├── job_description.txt
│   └── application_questions.txt
├── jobs/
│   └── <company_slug>/
│       ├── AGENTS.md
│       ├── master_brag_sheet.md
│       ├── resume_base.md
│       ├── preferences.md
│       ├── profile_links.md
│       ├── job_description.txt
│       ├── <company_slug>_resume.md
│       ├── <company_slug>_cover_letter.md
│       ├── <company_slug>_application_answers.md
│       ├── history/
│       └── pdf/
├── scripts/
│   ├── prepare_application.sh
│   ├── export_pdfs.sh
│   ├── generate_application_answers.sh
│   └── setup_pdf_tools.sh
```
