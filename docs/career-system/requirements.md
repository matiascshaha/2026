# System requirements

These requirements describe the whole career workflow, not just the Python CLI.
**Existing** means supported by the inspected repository. **Partial** means tools
or a manual process exist but the end-to-end requirement is not implemented.
**Proposed** means future implementation. The external radar is an existing input,
not a component verified or changed by this documentation contribution.

## Functional requirements

| ID | Requirement | Goal | Status |
| --- | --- | --- | --- |
| FR01 | Import selected current or historical radar leads with source URL, employer, role, available job ID, and observation time. Distinguish recommendation history from application history. | G1 | Partial: offline lead import; radar adapter deferred |
| FR02 | Recheck the employer's posting before applying. Record open, closed, or unverified status and when it was checked; do not treat an inaccessible page as a confirmed closure. | G1, G6 | Proposed |
| FR03 | Check role-level submission history and available receipts before any submission. Preserve uncertainty when evidence is missing; one employer can have several different roles. | G5, G6 | Partial: offline identity/history records; no submission executor |
| FR04 | Retrieve relevant canonical career context through a read-only interface, returning source identity, line references, and content hashes. Retrieve full evidence before relying on a search excerpt. | G2 | Existing |
| FR05 | Generate a tailored resume and cover letter, plus application answers when requested, using the career evidence and wording guidance. Unknown facts must be flagged, not invented. | G3 | Partial: helpers and drafting workflow |
| FR06 | Retain the exact input job description, questions, source versions, final answers, and final files used for each application. A later regeneration must not silently replace the submitted version. | G3, G5 | Partial: transactional offline packet snapshots and hashes |
| FR07 | Record a claim-to-evidence map and a short, user-readable explanation of major tailoring choices and edits. | G5 | Partial: offline claim map, notes and event inspection |
| FR08 | Support owner-confirmed career-context changes and profile drafts, preserving the distinction between personal projects and employer work. Publishing a profile change is a separate authorized action. | G2, G4 | Partial: manual contribution workflow |
| FR09 | Provide a per-application view of materials, outstanding questions, authorization, attempts, outcome evidence, and a timestamped history. | G5 | Partial: offline claim map, notes and event inspection |
| FR10 | Submit or upload only within the owner's authorized scope, destination, and data. Store that scope privately; a documentation, discovery, or drafting request does not enable submission. | G6 | Proposed execution gate |
| FR11 | Pause when a required fact is unknown, authority is insufficient, a destination materially changes, or the site requires user action. Resume without losing already completed work. | G3, G6 | Partial: declared packet blockers; no action executor |
| FR12 | Record an attempt before submission and its confirmed or uncertain result afterward. Never blindly retry an uncertain submission. Reconcile receipt or site evidence first. | G5, G6 | Proposed |
| FR13 | Offer read-only discovery, assisted preparation, and explicitly scoped submission as separate capabilities. The owner must be able to pause future submissions without losing records. | G1, G6 | Proposed coordinator modes |

## Quality requirements

- **NFR01 Privacy (G2, G5, G6).** Keep private application content, authorization,
  and receipts out of public Git history and logs. Store only necessary data.
  Credentials and authentication secrets must not enter the application audit.
- **NFR02 Provenance (G2, G3, G5).** Record the context revision and actual source
  hashes used. A changed hash invalidates old line references until rechecked.
  Retrieval or a structural validation pass does not prove factual truth.
- **NFR03 Reliability (G5, G6).** Preserve completed records across interruptions,
  prevent concurrent attempts for the same confirmed job identity, and distinguish
  failed actions from unknown outcomes. Define and verify backup/recovery before
  relying on the audit store for unattended work.
- **NFR04 Maintainability (G2, G6).** Keep retrieval independent of discovery and
  submission. Preserve the existing versioned JSON CLI contract; add adapters
  rather than making context retrieval dependent on a job site or model service.
- **NFR05 Usability (G3, G5).** Show plain-language status, blockers, links, and
  materials. Audit summaries should explain evidence and choices without requiring
  the owner to read machine logs.

See [assisted audit implementation](assisted-audit.md) for exact coverage, tests,
and limitations. These partial statuses do not mean an end-to-end application
coordinator is implemented.

## Before unattended submission

Documentation alone does not satisfy FR03, FR06-07, or FR09-13. Unattended submission
requires an implemented private ledger, versioned packets, duplicate and retry
controls, destination-specific checks, an agreed authorization scope, and a
verified assisted run. New acceptance tests can follow during implementation;
they are not required to complete this documentation phase.
