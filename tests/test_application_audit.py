"""Synthetic fixtures only: never access real career or application records."""
import concurrent.futures
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('application_audit', Path(__file__).resolve().parents[1] / 'scripts/application_audit.py')
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        # macOS /var is a system symlink; establish the canonical temporary root
        # before testing intentional symlinks inside our private storage fixture.
        self.root = Path(self.temp.name).resolve()
        self.store = audit.AuditStore(self.root / 'private')
        self.lead = {'lead_id': 'example-1', 'employer': 'Example Labs', 'role_title': 'Engineer', 'source_url': 'https://example.invalid/jobs/42?job=42#details', 'provider': 'example-tenant', 'provider_job_id': '42', 'discovered_at': '2026-01-01T12:00:00Z'}
        self.app = self.store.import_lead(self.lead)['application_id']
        self.manifest = {'files': {}, 'context': {'source-1': 'source.txt'}, 'context_revision': 'synthetic-revision', 'tailoring_notes': 'Emphasize the supported test fixture claim.', 'claims': [{'claim': 'Built a fixture', 'source_id': 'source-1', 'source_sha256': audit.digest(b'Built a fixture.\nSecond line.\n'), 'start_line': 1, 'end_line': 1}]}
        (self.root / 'source.txt').write_bytes(b'Built a fixture.\nSecond line.\n')
        for name in audit.REQUIRED:
            filename = name + '.test'
            (self.root / filename).write_bytes(b'%PDF-1.4\nsynthetic fixture' if name.endswith('_pdf') else b'Synthetic job or packet.\n')
            self.manifest['files'][name] = filename

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def freeze(self):
        return self.store.freeze(self.app, self.manifest, self.root)

    def test_import_is_not_application_and_provider_deduplicates(self):
        again = self.store.import_lead(dict(self.lead, lead_id='later-lead'))
        self.assertTrue(again['existing'])
        self.assertEqual(again['application_id'], self.app)
        self.assertEqual(self.store.inspect(self.app)['application']['status'], 'discovered')
        self.assertFalse(self.store.inspect(self.app)['submission_enabled'])
        different = self.store.import_lead(dict(self.lead, provider_job_id='43'))
        self.assertNotEqual(different['application_id'], self.app)

    def test_url_only_is_uncertain_not_automatic_duplicate(self):
        lead = dict(self.lead)
        del lead['provider_job_id']
        first = self.store.import_lead(lead)
        second = self.store.import_lead(lead)
        self.assertNotEqual(first['application_id'], second['application_id'])
        self.assertIn(first['application_id'], second['possible_duplicates'])

    def test_provider_namespace_and_employer_keep_distinct_roles(self):
        self.assertNotEqual(self.app, self.store.import_lead(dict(self.lead, provider='other-tenant'))['application_id'])
        self.assertNotEqual(self.app, self.store.import_lead(dict(self.lead, employer='Other Employer'))['application_id'])

    def test_requires_timezone_and_availability_check(self):
        for changes in ({'discovered_at': '2026-01-01'}, {'availability': 'open'}, {'provider': None}, {'source_url': 'https://user:password@example.invalid/'}):
            with self.assertRaises(audit.AuditError):
                self.store.import_lead(dict(self.lead, **changes))

    def test_frozen_bytes_survive_changes_and_reopen(self):
        self.freeze()
        original = self.store.artifact(self.app, 1, 'files/resume_md')
        (self.root / self.manifest['files']['resume_md']).write_text('Changed fixture')
        self.freeze()
        self.store.close()
        self.store = audit.AuditStore(self.root / 'private')
        self.assertEqual(self.store.artifact(self.app, 1, 'files/resume_md'), original)
        self.assertEqual(self.store.artifact(self.app, 2, 'files/resume_md'), b'Changed fixture')
        self.assertTrue(self.store.inspect(self.app)['integrity_ok'])

    def test_bad_hash_and_lines_rejected_without_partial_packet(self):
        self.manifest['claims'][0]['source_sha256'] = 'incorrect'
        with self.assertRaises(audit.AuditError):
            self.freeze()
        self.assertEqual(self.store.inspect(self.app)['packets'], [])
        self.manifest['claims'][0]['source_sha256'] = audit.digest((self.root / 'source.txt').read_bytes())
        self.manifest['claims'][0]['end_line'] = 50
        with self.assertRaises(audit.AuditError):
            self.freeze()
        self.manifest['claims'][0]['end_line'] = True
        with self.assertRaises(audit.AuditError):
            self.freeze()

    def test_missing_pdf_rejected(self):
        del self.manifest['files']['resume_pdf']
        with self.assertRaises(audit.AuditError):
            self.freeze()

    def test_blockers_record_needs_input(self):
        self.manifest['blockers'] = ['Confirm required fact']
        self.freeze()
        view = self.store.inspect(self.app)
        self.assertEqual(view['application']['status'], 'needs_input')
        self.assertEqual(view['packets'][0]['blockers'], ['Confirm required fact'])

    def test_outcome_confirmation_requires_evidence(self):
        self.freeze()
        with self.assertRaises(audit.AuditError):
            self.store.observe(self.app, 'submitted', 'Claim without receipt')
        self.store.observe(self.app, 'submitted', 'Operator verified confirmation', b'Synthetic receipt', 1)
        self.assertEqual(self.store.inspect(self.app)['application']['status'], 'submitted')
        with self.assertRaises(audit.AuditError):
            self.freeze()
        with self.assertRaises(audit.AuditError):
            self.store.observe(self.app, 'failed', 'Cannot overwrite confirmation')

    def test_unknown_blocks_regeneration_until_evidence(self):
        self.freeze()
        self.store.observe(self.app, 'submission_unknown', 'External site timed out', revision=1)
        with self.assertRaises(audit.AuditError):
            self.freeze()
        with self.assertRaises(audit.AuditError):
            self.store.observe(self.app, 'failed', 'Guess')
        self.store.observe(self.app, 'failed', 'Checked site; no application exists', b'Synthetic site evidence')
        self.freeze()
        kinds = [e['details'].get('outcome') for e in self.store.inspect(self.app)['events']]
        self.assertIn('submission_unknown', kinds)
        self.assertIn('failed', kinds)

    def test_integrity_detects_artifact_modification(self):
        self.freeze()
        with self.store.db:
            self.store.db.execute("UPDATE artifacts SET content = ? WHERE name = 'files/resume_md'", (b'tampered',))
        self.assertFalse(self.store.inspect(self.app)['integrity_ok'])
        with self.assertRaises(audit.AuditError):
            self.store.artifact(self.app, 1, 'files/resume_md')

    def test_invalid_revision_cannot_record_outcome(self):
        with self.assertRaises(audit.AuditError):
            self.store.observe(self.app, 'submitted', 'Receipt', b'Receipt', 99)
        self.assertEqual(self.store.inspect(self.app)['application']['status'], 'discovered')

    def test_private_permissions_and_symlink_refusal(self):
        self.assertEqual((self.root / 'private').stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.root / 'private/audit.sqlite').stat().st_mode & 0o777, 0o600)
        (self.root / 'alias').symlink_to(self.root / 'private', target_is_directory=True)
        with self.assertRaises(audit.AuditError):
            audit.AuditStore(self.root / 'alias')

    def test_concurrent_imports_have_one_confirmed_identity(self):
        def create(_):
            store = audit.AuditStore(self.root / 'private')
            try:
                return store.import_lead(dict(self.lead, provider_job_id='concurrent'))['application_id']
            finally:
                store.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            ids = list(pool.map(create, range(8)))
        self.assertEqual(len(set(ids)), 1)

    def test_empty_or_invalid_evidence_cannot_confirm_or_reconcile(self):
        self.store.observe(self.app, 'submission_unknown', 'Unknown')
        for evidence in (b'', 'not bytes', b'x' * (audit.MAX_FILE_BYTES + 1)):
            for outcome in ('submitted', 'failed'):
                with self.assertRaises(audit.AuditError):
                    self.store.observe(self.app, outcome, 'Observation', evidence)
        self.assertEqual(self.store.inspect(self.app)['application']['status'], 'submission_unknown')

    def test_missing_artifact_or_context_fails_integrity(self):
        self.freeze()
        with self.store.db:
            self.store.db.execute("DELETE FROM artifacts WHERE name = 'files/resume_pdf'")
        self.assertFalse(self.store.inspect(self.app)['integrity_ok'])
        self.freeze()
        with self.store.db:
            self.store.db.execute("DELETE FROM artifacts WHERE name = 'context/source-1' AND revision = 2")
        self.assertFalse(self.store.inspect(self.app)['packets'][1]['integrity_ok'])

    def test_receipt_roundtrip_and_tamper_detection(self):
        self.store.observe(self.app, 'submitted', 'Confirmation', b'Synthetic receipt')
        event = self.store.inspect(self.app)['events'][-1]['id']
        self.assertEqual(self.store.receipt(self.app, event), b'Synthetic receipt')
        with self.store.db:
            self.store.db.execute('UPDATE events SET evidence = ? WHERE id = ?', (b'changed', event))
        self.assertFalse(self.store.inspect(self.app)['integrity_ok'])
        with self.assertRaises(audit.AuditError):
            self.store.receipt(self.app, event)

    def test_bad_pdf_and_oversized_file_rejected(self):
        (self.root / self.manifest['files']['resume_pdf']).write_bytes(b'not pdf')
        with self.assertRaises(audit.AuditError):
            self.freeze()
        large = self.root / 'large'
        with large.open('wb') as f:
            f.truncate(audit.MAX_FILE_BYTES + 1)
        with self.assertRaises(audit.AuditError):
            audit.read_bytes(large)

    def test_database_link_refusal(self):
        other = self.root / 'other'
        other.mkdir()
        (other / 'audit.sqlite').symlink_to(self.root / 'private/audit.sqlite')
        with self.assertRaises(audit.AuditError):
            audit.AuditStore(other)

    def test_packet_transaction_rolls_back_after_write_error(self):
        with self.store.db:
            self.store.db.execute("CREATE TRIGGER fail_artifact BEFORE INSERT ON artifacts BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
        with self.assertRaises(sqlite3.Error):
            self.freeze()
        view = self.store.inspect(self.app)
        self.assertEqual(view['packets'], [])
        self.assertEqual(view['application']['status'], 'discovered')
        self.assertEqual(len(view['events']), 1)

    def test_concurrent_packet_revisions(self):
        def freeze(_):
            store = audit.AuditStore(self.root / 'private')
            try:
                return store.freeze(self.app, self.manifest, self.root)['revision']
            finally:
                store.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            revisions = list(pool.map(freeze, range(8)))
        self.assertEqual(sorted(revisions), list(range(1, 9)))
        self.assertTrue(self.store.inspect(self.app)['integrity_ok'])

    def test_cli_roundtrip_and_no_submit(self):
        scripts = self.root / 'checkout/scripts'
        scripts.mkdir(parents=True)
        script = scripts / 'application_audit.py'
        script.write_bytes(Path(SPEC.origin).read_bytes())
        lead_path = self.root / 'lead.json'
        lead_path.write_text(json.dumps(self.lead))
        manifest_path = self.root / 'manifest.json'
        manifest_path.write_text(json.dumps(self.manifest))
        def run(*args):
            return subprocess.run([sys.executable, str(script), *args], capture_output=True)
        imported = run('import-lead', str(lead_path))
        self.assertEqual(imported.returncode, 0, imported.stderr)
        app = json.loads(imported.stdout)['result']['application_id']
        self.assertEqual(run('freeze', app, str(manifest_path)).returncode, 0)
        view = json.loads(run('inspect', app).stdout)['result']
        self.assertTrue(view['integrity_ok'])
        self.assertFalse(view['submission_enabled'])
        self.assertEqual(run('extract', app, '1', 'files/resume_md').stdout, b'Synthetic job or packet.\n')
        reservation = json.loads(run('reserve-attempt', app, '1', '--destination', 'https://example.invalid/apply', '--request-id', 'cli-request').stdout)['result']
        self.assertFalse(reservation['execution_authorized'])
        attempt = reservation['attempt']['id']
        self.assertEqual(len(json.loads(run('pending-attempts').stdout)['result']['attempts']), 1)
        note = self.root / 'note.txt'
        note.write_text('Synthetic timeout observation')
        resolved = run('resolve-attempt', attempt, '--outcome', 'submission_unknown', '--note-file', str(note))
        self.assertEqual(json.loads(resolved.stdout)['result']['attempt']['state'], 'submission_unknown')
        self.assertNotEqual(run('submit', app).returncode, 0)
        bad = run('freeze', app, str(self.root / 'missing-private-file'))
        self.assertNotEqual(bad.returncode, 0)
        self.assertNotIn(b'missing-private-file', bad.stderr)
        self.assertFalse(json.loads(bad.stderr)['ok'])

    def reserve(self, request_id='request-1'):
        return self.store.reserve_attempt(self.app, 1, 'https://example.invalid/apply/42', request_id)

    def test_reservation_is_not_authorization_and_survives_reopen(self):
        self.freeze()
        result = self.reserve()
        self.assertFalse(result['submission_enabled'])
        self.assertFalse(result['execution_authorized'])
        self.store.close()
        self.store = audit.AuditStore(self.root / 'private')
        view = self.store.inspect(self.app)
        self.assertEqual(view['application']['status'], 'attempt_reserved')
        self.assertEqual(view['attempts'][0]['state'], 'reserved')
        with self.assertRaises(audit.AuditError):
            self.reserve('another-request')
        with self.assertRaises(audit.AuditError):
            self.freeze()
        with self.assertRaises(audit.AuditError):
            self.store.observe(self.app, 'failed', 'Legacy bypass', b'evidence')

    def test_idempotent_reservation_and_changed_binding_rejection(self):
        self.freeze()
        first = self.reserve()
        again = self.reserve()
        self.assertEqual(first['attempt']['id'], again['attempt']['id'])
        self.assertTrue(again['existing'])
        for app, rev, dest in ((self.app, 2, 'https://example.invalid/apply/42'),
                               ('other-app', 1, 'https://example.invalid/apply/42'),
                               (self.app, 1, 'https://other.invalid/apply')):
            with self.assertRaises(audit.AuditError):
                self.store.reserve_attempt(app, rev, dest, 'request-1')
        events = self.store.inspect(self.app)['events']
        self.assertEqual(sum(e['kind'] == 'attempt_reserved' for e in events), 1)

    def test_concurrent_attempts_only_one_owner(self):
        self.freeze()
        def reserve(index):
            store = audit.AuditStore(self.root / 'private')
            try:
                try:
                    return store.reserve_attempt(self.app, 1, 'https://example.invalid/apply/42', f'request-{index}')['attempt']['id']
                except audit.AuditError:
                    return None
            finally:
                store.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(reserve, range(8)))
        self.assertEqual(sum(result is not None for result in results), 1)

    def test_concurrent_same_request_returns_same_attempt(self):
        self.freeze()
        def reserve(_):
            store = audit.AuditStore(self.root / 'private')
            try:
                return store.reserve_attempt(self.app, 1, 'https://example.invalid/apply/42', 'same-request')['attempt']['id']
            finally:
                store.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(reserve, range(8)))
        self.assertEqual(len(set(results)), 1)

    def test_uncertain_attempt_requires_evidence_and_keeps_history(self):
        self.freeze()
        attempt = self.reserve()['attempt']['id']
        self.store.resolve_attempt(attempt, 'submission_unknown', 'Interrupted after handoff')
        for evidence in (None, b'', 'invalid'):
            with self.assertRaises(audit.AuditError):
                self.store.resolve_attempt(attempt, 'failed', 'No proof', evidence)
        with self.assertRaises(audit.AuditError):
            self.reserve('retry')
        self.store.resolve_attempt(attempt, 'failed', 'Verified no submission', b'Synthetic site check')
        second = self.reserve('new-explicit-request')
        self.assertNotEqual(second['attempt']['id'], attempt)
        self.assertEqual(len(self.store.inspect(self.app)['attempts']), 2)
        self.assertEqual(self.reserve()['attempt']['state'], 'failed')

    def test_confirmed_attempt_blocks_new_work_and_overwrite(self):
        self.freeze()
        attempt = self.reserve()['attempt']['id']
        self.store.resolve_attempt(attempt, 'submitted', 'Confirmed', b'Synthetic receipt')
        with self.assertRaises(audit.AuditError):
            self.reserve('second')
        with self.assertRaises(audit.AuditError):
            self.store.resolve_attempt(attempt, 'failed', 'Overwrite', b'Other evidence')
        with self.assertRaises(audit.AuditError):
            self.freeze()
        self.assertEqual(self.store.import_lead(self.lead)['application_id'], self.app)

    def test_reservation_rejects_stale_blocked_or_uncertain_identity(self):
        self.freeze()
        self.freeze()
        with self.assertRaises(audit.AuditError):
            self.reserve()
        self.manifest['blockers'] = ['Missing required fact']
        self.freeze()
        with self.assertRaises(audit.AuditError):
            self.store.reserve_attempt(self.app, 3, 'https://example.invalid/apply', 'blocked')
        uncertain = dict(self.lead)
        del uncertain['provider_job_id']
        other = self.store.import_lead(uncertain)['application_id']
        self.manifest['blockers'] = []
        self.store.freeze(other, self.manifest, self.root)
        with self.assertRaises(audit.AuditError):
            self.store.reserve_attempt(other, 1, 'https://example.invalid/apply', 'uncertain')

    def test_reservation_rejects_corruption(self):
        self.freeze()
        with self.store.db:
            self.store.db.execute("DELETE FROM artifacts WHERE name = 'files/resume_pdf'")
        with self.assertRaises(audit.AuditError):
            self.reserve()

    def test_reservation_transaction_rolls_back_with_event(self):
        self.freeze()
        with self.store.db:
            self.store.db.execute("CREATE TRIGGER fail_event BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
        with self.assertRaises(sqlite3.Error):
            self.reserve()
        self.assertEqual(self.store.inspect(self.app)['attempts'], [])
        self.assertEqual(self.store.inspect(self.app)['application']['status'], 'prepared')

    def test_schema_one_migrates_without_losing_frozen_data(self):
        self.freeze()
        original = self.store.artifact(self.app, 1, 'files/resume_md')
        with self.store.db:
            self.store.db.execute('DROP TABLE attempts')
            self.store.db.execute('PRAGMA user_version = 1')
        self.store.close()
        self.store = audit.AuditStore(self.root / 'private')
        self.assertEqual(self.store.db.execute('PRAGMA user_version').fetchone()[0], 3)
        self.assertEqual(self.store.artifact(self.app, 1, 'files/resume_md'), original)
        self.reserve()

    def test_reconciliation_event_failure_rolls_back_state(self):
        self.freeze()
        attempt = self.reserve()['attempt']['id']
        with self.store.db:
            self.store.db.execute("CREATE TRIGGER fail_resolution BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
        with self.assertRaises(sqlite3.Error):
            self.store.resolve_attempt(attempt, 'submitted', 'Confirmed', b'Synthetic receipt')
        view = self.store.inspect(self.app)
        self.assertEqual(view['application']['status'], 'attempt_reserved')
        self.assertEqual(view['attempts'][0]['state'], 'reserved')

    def test_process_exit_before_and_after_reservation_commit(self):
        self.freeze()
        script = """
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location('audit', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
store = module.AuditStore(sys.argv[2])
if sys.argv[4] == 'before':
    store._event = lambda *args, **kwargs: os._exit(23)
store.reserve_attempt(sys.argv[3], 1, 'https://example.invalid/apply/42', 'process-request')
os._exit(23)
"""
        def crash(mode):
            result = subprocess.run([sys.executable, '-c', script, str(SPEC.origin), str(self.root / 'private'), self.app, mode], capture_output=True)
            self.assertEqual(result.returncode, 23, result.stderr)
        crash('before')
        self.assertEqual(self.store.inspect(self.app)['attempts'], [])
        self.assertEqual(self.store.inspect(self.app)['application']['status'], 'prepared')
        crash('after')
        view = self.store.inspect(self.app)
        self.assertEqual(view['attempts'][0]['state'], 'reserved')
        self.assertEqual(view['application']['status'], 'attempt_reserved')
        with self.assertRaises(audit.AuditError):
            self.reserve('new-process-request')

    def test_no_submit_command_or_executor(self):
        source = Path(SPEC.origin).read_text()
        self.assertNotIn("add_parser('submit')", source)
        self.assertNotIn('import requests', source)
        self.assertNotIn('import subprocess', source)


if __name__ == '__main__':
    unittest.main()
