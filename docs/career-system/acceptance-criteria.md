# Future acceptance criteria

These are lightweight examples to develop when implementing the workflow. They
are not new tests, evidence of passing tests, or a prerequisite for finishing this
documentation phase. Keep existing repository checks running.

- **FR01-03:** Import an old recommendation without marking it applied. A confirmed
  receipt for the same job blocks a duplicate, while a different role at the same
  employer remains distinct. Missing evidence leaves application status unknown.
- **FR04-07 / NFR02:** Given a selected role, reconstruct the exact final packet,
  answers, input job description, and supporting source revisions. A changed source
  hash or packet revision is visible and does not silently replace prior evidence.
- **FR05 / FR11:** A required answer absent from confirmed context produces a
  specific request for input rather than a fabricated answer.
- **FR08:** An approved career correction updates the intended canonical source
  without silently publishing a profile change or altering prior application records.
- **FR09-10 / FR13:** The owner can inspect the packet and status. An unauthorized,
  expired, revoked, or materially changed submission is blocked, and pausing future
  submissions leaves discovery and historical records available.
- **FR12 / NFR03:** A timeout after submit becomes `submission_unknown`, not success
  or an automatic retry. Concurrent runs cannot create two active attempts for the
  same confirmed job identity. Recovery preserves saved packets and events.
- **NFR01 / NFR05:** A repository diff and CI output contain no real private
  application data. The private audit summary exposes useful evidence and blockers
  without credentials or unrelated personal information.

Use synthetic jobs and career fixtures for automated tests. Add focused tests
alongside each implemented requirement and a controlled end-to-end verification
before enabling unattended submission. Do not use live applications as test data
or submit an application merely to test a flow.

## Implemented offline checks

`tests/test_application_audit.py` now covers the offline portions: lead imports
are not submissions, confirmed provider identities deduplicate under concurrency,
URL-only matches stay uncertain, packet bytes and source mappings are frozen,
missing facts stay as declared blockers, receipts and uncertain outcomes are
distinct, corruption/deleted artifacts are detected, writes roll back on failure,
and records persist across reopen. Tests use synthetic files and a temporary CLI
checkout. See [implementation limits](assisted-audit.md). The remaining criteria
above still require a coordinator and controlled assisted end-to-end verification.
