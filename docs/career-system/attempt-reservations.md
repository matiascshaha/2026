# Agent orchestration: attempt reservation and recovery

This second offline slice adds durable attempt coordination to the audit ledger.
It is useful for an agent that will eventually connect radar discoveries, context
retrieval, preparation, and a separately authorized application action. It does
not implement that external action, verify permission, or enable unattended work.

## Safety contract

- A reservation is **not authorization**. Every reservation/result returns
  `submission_enabled: false` and `execution_authorized: false`. There is no
  submission adapter, browser controller, credential handling, or enable switch.
- Only an application with a provider-scoped job identity, a complete latest
  packet with no declared blockers, and passing stored-byte integrity checks can
  reserve. Provider identity is operator supplied, not independently verified.
- One unresolved or submitted attempt may hold a job identity. SQLite transactions
  and a partial unique index enforce this across concurrent processes sharing the
  same database. Copies of a database are not coordinated with each other.
- The reservation binds application, exact packet revision, destination and a
  caller-supplied request ID. Retrying the same request ID with the same binding
  returns the original attempt, even after it has resolved. Changing its binding
  is rejected. An existing response must never trigger a second external action.
- Reservations do not expire and are not automatically released. A crash leaves
  the attempt reserved. Treat its outcome as unknown until the actual destination
  and evidence have been checked; never assume no submission because the process
  stopped or a timeout elapsed.
- A submitted or failed resolution requires nonempty evidence. In this contract,
  `failed` means **verified no submission**, not merely a timeout or failed client
  response. Use `submission_unknown` whenever that distinction is uncertain.
- Only an explicit new request ID can create another attempt after evidence-based
  failure reconciliation. Submitted attempts block future reservations. Resolving
  an already terminal attempt is rejected; inspect its saved result after an
  uncertain local response rather than resubmitting or changing that outcome.
- Packet freezing and legacy `observe` cannot bypass an unresolved attempt.
  Use the attempt-specific reconciliation interface so the receipt stays tied to
  its exact revision and destination. History is preserved in timestamped events.

These controls prevent duplicate **reservations**, not duplicate external
applications. An agent that bypasses the ledger, two unsynchronized databases,
incorrect job identities, or an adapter that clicks twice remain outside this
foundation's guarantees. The application site is not part of the SQLite transaction.

## Commands

Keep real data and captured output in ignored private storage. All URLs below are
synthetic. Request IDs are arbitrary nonsecret identifiers; generate and retain
one before reserving, and reuse it only to recover that exact reservation request.

```sh
python3 scripts/application_audit.py reserve-attempt APPLICATION_ID 1 \
  --destination https://example.invalid/apply/42 --request-id synthetic-request-1
python3 scripts/application_audit.py pending-attempts
python3 scripts/application_audit.py inspect APPLICATION_ID
```

The application status becomes `attempt_reserved`. On restart, inspect pending
attempts first. Neither `reserved` nor an idempotent response permits an external
action. Mark an interrupted or uncertain attempt without releasing its lock:

```sh
python3 scripts/application_audit.py resolve-attempt ATTEMPT_ID \
  --outcome submission_unknown --note-file .private/recovery-note.txt
```

After independently checking receipt or destination evidence, record the verified
outcome. These are local recordkeeping commands, not instructions to submit:

```sh
python3 scripts/application_audit.py resolve-attempt ATTEMPT_ID \
  --outcome submitted --note-file .private/outcome-note.txt \
  --evidence-file .private/sanitized-receipt.txt
```

For verified no-submission, use `--outcome failed` with reconciliation evidence.
There is no blind cancel/release/retry command. Evidence remains operator reported,
not cryptographically or independently verified. Do not store credentials or
unrelated personal information in evidence.

## Storage and migration

Schema version 2 adds attempts and a unique unresolved/submitted identity index.
Opening a schema-1 database upgrades it transactionally without changing existing
applications, packet bytes, or events. The JSON envelope remains version 1;
inspection adds an `attempts` field. Back up important private data before upgrading.
Older version-1 software rejects the upgraded database rather than silently ignoring
attempt locks. Never run old software against a separately copied stale database
while coordinating live work. No downgrade or cross-device sync is provided.

## Remaining integration before real autonomous execution

The agent can act as the coordinator; a new hosted service is not required merely
to glue existing tools together. However, the following steps are not supplied by
this reservation CLI and must be verified before enabling an external adapter:

1. Identify the real radar event/feed and dispatch each selected lead once.
2. Recheck posting availability, role-level application history and uncertain matches.
3. Retrieve full career context, prepare answers and documents, visually verify
   the final exports, and freeze source-linked packets in the private ledger.
4. Establish applicable user authorization, allowed recipients/data/actions,
   destination and packet binding, and policy-required exceptions. A reservation
   does not satisfy or infer that authority, including for changes in destination.
5. Implement a single-execution adapter and recovery protocol. Save the reservation
   before the action, stop on uncertain results, and reconcile actual site evidence.
6. Verify a controlled assisted end-to-end workflow plus authorized durable storage,
   retention, encrypted backup, and restoration before relying on unattended runs.

Synthetic tests cover concurrent unique and identical requests, retained locks
across reopen, rollback, packet binding, corruption, legacy bypass, reconciliation,
confirmation, and schema migration. No application was submitted as a test.
