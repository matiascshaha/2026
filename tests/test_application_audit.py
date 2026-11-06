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
        self.assertNotEqual(run('submit', app).returncode, 0)
        bad = run('freeze', app, str(self.root / 'missing-private-file'))
        self.assertNotEqual(bad.returncode, 0)
        self.assertNotIn(b'missing-private-file', bad.stderr)
        self.assertFalse(json.loads(bad.stderr)['ok'])

    def test_no_submit_command_or_executor(self):
        source = Path(SPEC.origin).read_text()
        self.assertNotIn("add_parser('submit')", source)
        self.assertNotIn('import requests', source)
        self.assertNotIn('import subprocess', source)


if __name__ == '__main__':
    unittest.main()
