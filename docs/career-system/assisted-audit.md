# Assisted application audit: offline foundation

`scripts/application_audit.py` implements the first private, offline recordkeeping
slice of G5/G6. It does **not** discover jobs, draft prose, open websites, upload,
submit, authorize actions, or enable unattended work. There is no submission
command, network client, execution adapter, or configuration switch to enable one.
The existing read-only context CLI and company workspace helpers are unchanged.

## Implemented and deliberately deferred

- Import selected leads, preserving discovery versus application status. An exact
  employer + explicit provider namespace + provider job ID reuses one application
  record transactionally. Distinct roles remain distinct. Repeated observations
  append events. URL-only matches remain review candidates, not proven duplicates.
- Freeze complete packet revisions: raw job description, resume/cover-letter
  Markdown and PDFs, optional questions/answers, exact context source bytes,
  source revision label, claim/line/hash mappings, tailoring explanation and
  outstanding questions. Changes create new revisions instead of overwriting.
- Inspect timestamped events, materials, hashes, blockers and operator-reported
  external outcomes. Extract exact frozen artifact or receipt bytes for review.
- Record unknown external outcomes without calling them success. Confirmed
  outcomes require evidence. Unknown history blocks new packet preparation until
  failure is reconciled with evidence, or a confirmation is recorded. Confirmed
  outcomes cannot be overwritten. All old events remain visible.

This partially implements FR01, FR03, FR06, FR07, FR09 and FR11. It is not a
production implementation of FR10/FR12/FR13: no permissions registry,
submission coordinator, kill switch, retry executor, or website
verification exists. In particular, there is **no safe-to-submit signal**.
`prepared` means only that a packet was saved without declared blockers.
Structural checks do not verify that claims are true, all claims are mapped,
answers are complete, PDFs render correctly, availability is current, an operator's
receipt proves the stated outcome, or submission authority exists.

The subsequent [attempt reservation interface](attempt-reservations.md) now adds
local attempt locks and evidence-based recovery. It does not enable submission
or remove the limitations above. Use it instead of legacy `observe` whenever an
attempt has been reserved.

## Private storage and integrity

The CLI uses `.private/career-system/audit.sqlite` in this checkout. This path is
already ignored. The storage directory is mode 0700 and database mode 0600 on
POSIX; the CLI sets umask 077. Symlink storage paths and linked database files are
rejected. These controls are not encryption or protection against the same OS
user. Do not include secrets, cookies, authentication codes, or unrelated personal
data in inputs, notes or receipts. Sanitize receipt evidence before importing.

**Decision:** the initial SQLite ledger stores frozen artifact bytes as BLOBs,
rather than alongside files. Packet metadata, exact bytes, state, and event commit
in one transaction, avoiding a filesystem/database partial commit. This retains
the proposed ledger contract without introducing artifact recovery machinery yet.
Each input is limited to 20 MiB. A future larger store may move bytes into a
separate verified artifact store. No dependency beyond Python 3.10+ is required.

SHA-256 checks detect ordinary artifact/evidence corruption on inspection and
extraction. They do not make records tamper-proof: someone who can modify the
SQLite database can also modify hashes or metadata. Events are append-only through
this CLI, not protected by a cryptographic log or database access policy.

Storage is local and not backed up automatically. With all writers stopped and
connections closed, copy the database only to an authorized private backup
location. Reopen a restored copy in a private checkout and inspect/extract its
records before relying on it. Automated durable backup, encryption, retention,
and recovery remain required before unattended operation. Synthetic tests cover
close/reopen persistence, not a production disaster-recovery procedure.

## Assisted workflow

Keep all actual inputs, manifests, stdout captures and extracted files under
ignored `.private/` or `jobs/`. JSON output contains private audit information;
never paste real output into public issues or CI logs. Commands below use only
synthetic names. The CLI reads local files only. Import does not recheck a posting.

1. Prepare a private lead JSON object:

   ```json
   {
     "lead_id": "radar-example-42",
     "source_url": "https://example.invalid/jobs/42",
     "employer": "Example Labs",
     "role_title": "Engineer",
     "provider": "example-ats-tenant",
     "provider_job_id": "42",
     "discovered_at": "2026-01-01T12:00:00Z",
     "availability": "unverified"
   }
   ```

   `provider` is a stable ATS/provider tenant namespace, not a changing display
   label. Omit both provider fields when the job ID is unknown. `open` or `closed`
   requires a timezone-bearing `checked_at`; this records the operator's check,
   not independent verification. Query parameters are retained because they can
   identify jobs. Credentials in URL userinfo are rejected; do not put secret
   query parameters in the source URL.

   ```sh
   python3 scripts/application_audit.py import-lead .private/lead.json
   python3 scripts/application_audit.py list
   ```

2. Use the existing context retrieval and preparation workflow. Review the full
   sources, create both Markdown documents, generate and visually inspect both
   PDFs, and save the job description and any questions/answers. Supply a manifest
   under `.private/` whose relative paths resolve beside the manifest:

   ```json
   {
     "files": {
       "job_description": "packet/job_description.txt",
       "resume_md": "packet/example_resume.md",
       "cover_letter_md": "packet/example_cover_letter.md",
       "resume_pdf": "packet/example_resume.pdf",
       "cover_letter_pdf": "packet/example_cover_letter.pdf",
       "questions": "packet/questions.txt",
       "answers": "packet/answers.md"
     },
     "context": {"source-id-from-context-cli": "packet/source.md"},
     "context_revision": "actual-commit-or-working-tree-label",
     "tailoring_notes": "Explain the main choices and edits in ordinary language.",
     "blockers": ["Confirm a required answer before any future application."],
     "claims": [{
       "claim": "Exact claim used in the packet",
       "source_id": "source-id-from-context-cli",
       "source_sha256": "replace-with-the-actual-64-character-source-hash",
       "start_line": 1,
       "end_line": 2
     }]
   }
   ```

   `questions` and `answers` are optional. All other `files` keys are required.
   The mapping hash and line range must match the exact saved UTF-8 source.
   The revision label is descriptive; source bytes/hashes record the actual input,
   including working-tree edits. A PDF header check is not a rendering check.

   ```sh
   python3 scripts/application_audit.py freeze APPLICATION_ID .private/manifest.json
   python3 scripts/application_audit.py inspect APPLICATION_ID
   python3 scripts/application_audit.py extract APPLICATION_ID 1 files/resume_pdf > .private/frozen_resume.pdf
   ```

3. If a separately authorized manual application has occurred, record the observed
   outcome. This tool does not execute that action or grant permission for it.
   The note and evidence are read from private files, not command-line text.

   ```sh
   python3 scripts/application_audit.py observe APPLICATION_ID \
     --outcome submitted --revision 1 \
     --note-file .private/outcome-note.txt --evidence-file .private/receipt.txt
   ```

   Outcomes: `submitted`, `already_applied`, `submission_unknown`, `failed`.
   The first two require evidence. A timeout is `submission_unknown`; never
   blindly retry a website action. Reconcile independently. `--revision` is
   optional for imported historical evidence when the exact packet is unknown;
   omission remains explicit in the event rather than guessing a packet match.
   Authorization is recorded as **not captured**, never inferred from this log.

   ```sh
   python3 scripts/application_audit.py extract-evidence APPLICATION_ID EVENT_ID > .private/receipt-copy.txt
   ```

All commands except byte extraction return a versioned JSON envelope. Expected
input/storage errors return nonzero and a JSON error on stderr without echoing
raw input or OS exception details. `inspect` exposes `integrity_ok`; do not rely
on any damaged record. There is currently no destructive edit/delete command or
confirmed-outcome correction command. Preserve the database and resolve mistakes
manually before extending this interface.

## Verification

Run the repository's existing checks in `CONTRIBUTING.md`. New tests use temporary
synthetic files only, covering identity matching, concurrent import, immutable
revisions, required artifacts, source hashes/lines, blockers, explicit receipt
requirements, uncertain-outcome recovery, private permissions, and integrity.
No live application, browser interaction, actual PDF render or unattended run is
used as a test. Add destination-specific tests and permission/attempt controls
before building any submission adapter.
