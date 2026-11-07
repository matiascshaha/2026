"""Non-network synthetic execution adapter and recovery contract."""
import base64
import concurrent.futures
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

import test_radar_context
import agent_execution as execution
from application_audit import AuditError


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_radar_context.RadarTests()
        self.fixture.setUp()
        f = self.fixture
        f.store.close()
        f.store = execution.ExecutionStore(f.private)
        self.store, self.root, self.private = f.store, f.root, f.private
        f.stage()
        self.app = f.complete()['application_id']
        self.attempt = self.store.reserve_attempt(self.app, 1, f.lead['source_url'], 'execution-1')['attempt']['id']
        self.review = self.store.review_template(self.attempt)
        self.review.update(reviewer='Synthetic adapter test', scope_description='Fixture-only simulated action, no network.',
                           reviewed_at=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
                           expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
                           user_instruction_refs=['synthetic instruction fixture'])
        for check in self.review['checks'].values():
            check.update(status='reviewed_clear', explanation='Synthetic fixture reviewed only.',
                         evidence_refs=['synthetic fixture observation'])

    def tearDown(self):
        self.fixture.tearDown()

    def adapter(self, handoff):
        self.assertFalse(handoff['execution_authorized'])
        self.assertEqual(handoff['binding']['destination'], self.fixture.lead['source_url'])
        for name, item in handoff['artifacts'].items():
            self.assertEqual(base64.b64decode(item['base64']), self.store.artifact(self.app, 1, name))
        self.assertFalse(any(name.startswith('context/') for name in handoff['artifacts']))
        return {'binding': handoff['binding'], 'outcome': 'submitted', 'note': 'Synthetic simulated receipt.', 'evidence': b'Fixture receipt, not an application.'}

    def test_full_workflow_and_replay(self):
        result = self.store.execute(self.attempt, self.review, self.root, self.adapter)
        self.assertEqual(result['attempt']['state'], 'submitted')
        replay = self.store.execute(self.attempt, {}, '/missing', lambda _: self.fail('replayed'))
        self.assertFalse(replay['dispatch_new'])
        self.assertNotIn('artifacts', replay)
        view = self.store.inspect(self.app)
        self.assertEqual(len(view['dispatches']), 1)
        self.assertEqual(view['dispatches'][0]['review'], self.review)
        self.assertTrue(view['integrity_ok'])
        self.assertEqual(view['events'][-1]['kind'], 'attempt_reconciled')

    def test_concurrent_invocation_at_most_once(self):
        calls, lock = [], threading.Lock()
        def adapter(handoff):
            with lock:
                calls.append(handoff['binding']['attempt_id'])
            return {'binding': handoff['binding'], 'outcome': 'submission_unknown', 'note': 'Synthetic pause.'}
        def run(_):
            store = execution.ExecutionStore(self.private)
            try:
                return store.execute(self.attempt, self.review, self.root, adapter)
            finally:
                store.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(run, range(12)))
        self.assertEqual(calls, [self.attempt])
        self.assertEqual(sum(r.get('recovery_only', False) for r in results), 11)

    def test_reviews_fail_closed(self):
        variants = []
        for name in execution.CHECKS:
            for change in ('missing', 'pending', 'no_evidence', 'no_explanation'):
                review = deepcopy(self.review)
                if change == 'missing':
                    del review['checks'][name]
                elif change == 'pending':
                    review['checks'][name]['status'] = 'pending'
                elif change == 'no_evidence':
                    review['checks'][name]['evidence_refs'] = []
                else:
                    review['checks'][name]['explanation'] = ''
                variants.append(review)
        for field, value in [('outstanding_blockers', ['Unknown eligibility']),
                             ('outstanding_blockers', None), ('user_instruction_refs', []),
                             ('expires_at', (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()),
                             ('expires_at', (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()),
                             ('reviewed_at', (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat())]:
            review = deepcopy(self.review)
            review[field] = value
            variants.append(review)
        for review in variants:
            with self.subTest(review=review), self.assertRaises(AuditError):
                self.store.execute(self.attempt, review, self.root, lambda _: self.fail('invoked'))
        self.assertFalse(self.store.recover(self.attempt)['dispatch_claimed'])
        self.assertEqual(self.store.recover(self.attempt)['attempt']['state'], 'reserved')

    def test_changed_binding_destination_or_packet(self):
        for field, value in [('destination', 'https://other.invalid/apply'), ('revision', 2), ('packet_sha256', 'different')]:
            review = deepcopy(self.review)
            review['binding'][field] = value
            with self.assertRaises(AuditError):
                self.store.claim(self.attempt, review, self.root)
        with self.assertRaises(AuditError):
            self.store.reserve_attempt(self.app, 1, 'https://other.invalid/apply', 'execution-1')

    def test_stale_context_and_expired_intake(self):
        path = self.root / 'context/preferences.md'
        old = path.read_bytes()
        path.write_bytes(b'Changed source')
        with self.assertRaisesRegex(AuditError, 'context changed'):
            self.store.claim(self.attempt, self.review, self.root)
        path.write_bytes(old)
        with patch('radar_context.datetime', wraps=datetime) as clock:
            clock.now.return_value = datetime.now(timezone.utc) + timedelta(days=2)
            with self.assertRaisesRegex(AuditError, 'stale'):
                self.store.claim(self.attempt, self.review, self.root)
        self.assertFalse(self.store.recover(self.attempt)['dispatch_claimed'])

    def test_crash_after_action_before_receipt(self):
        review_path = self.root / 'review.json'
        review_path.write_text(json.dumps(self.review))
        marker = self.root / 'synthetic-invocations'
        program = '''import json, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from agent_execution import ExecutionStore
store = ExecutionStore(sys.argv[2])
def crash(handoff):
    Path(sys.argv[6]).write_text('synthetic invocation')
    os._exit(23)
store.execute(sys.argv[3], json.loads(Path(sys.argv[4]).read_text()), Path(sys.argv[5]), crash)
'''
        run = subprocess.run([sys.executable, '-c', program, str(Path(execution.__file__).parent),
                              str(self.private), self.attempt, str(review_path), str(self.root), str(marker)])
        self.assertEqual(run.returncode, 23)
        self.assertTrue(marker.exists())
        self.assertEqual(self.store.recover(self.attempt)['attempt']['state'], 'submission_unknown')
        self.store.execute(self.attempt, self.review, self.root, lambda _: self.fail('replayed after crash'))
        with self.assertRaises(AuditError):
            self.store.resolve_attempt(self.attempt, 'failed', 'Timeout alone')
        with self.assertRaises(AuditError):
            self.store.reserve_attempt(self.app, 1, self.fixture.lead['source_url'], 'new-id')
        self.store.reconcile(self.attempt, self.review['binding'], 'submitted', 'Independent synthetic reconciliation.', b'Synthetic receipt')
        self.assertEqual(self.store.recover(self.attempt)['attempt']['state'], 'submitted')

    def test_lost_handoff_never_reissued_and_failed_does_not_unlock(self):
        self.store.claim(self.attempt, self.review, self.root)  # Lost before adapter invoked.
        self.assertNotIn('artifacts', self.store.claim(self.attempt, self.review, self.root))
        self.store.resolve_attempt(self.attempt, 'failed', 'Verified fixture did not execute.', b'Synthetic no-submission evidence')
        second = self.store.reserve_attempt(self.app, 1, self.fixture.lead['source_url'], 'new-id')['attempt']['id']
        review = deepcopy(self.review)
        review['binding'] = self.store.review_template(second)['binding']
        with self.assertRaisesRegex(AuditError, 'already been dispatched'):
            self.store.execute(second, review, self.root, lambda _: self.fail('second invocation'))

    def test_rollback_before_dispatch_and_nested_transaction_rejection(self):
        with self.store.transaction():
            with self.assertRaisesRegex(AuditError, 'durable transaction'):
                self.store.claim(self.attempt, self.review, self.root)
        with patch.object(self.store, '_event', side_effect=sqlite3.OperationalError('fixture')):
            with self.assertRaises(sqlite3.OperationalError):
                self.store.execute(self.attempt, self.review, self.root, lambda _: self.fail('uncommitted invocation'))
        self.assertFalse(self.store.recover(self.attempt)['dispatch_claimed'])
        self.assertEqual(self.store.recover(self.attempt)['attempt']['state'], 'reserved')

    def test_wrong_receipt_binding_keeps_lock(self):
        self.store.claim(self.attempt, self.review, self.root)
        binding = deepcopy(self.review['binding'])
        binding['destination'] = 'https://other.invalid/'
        with self.assertRaises(AuditError):
            self.store.reconcile(self.attempt, binding, 'submitted', 'Wrong destination receipt', b'Synthetic receipt')
        self.assertEqual(self.store.recover(self.attempt)['attempt']['state'], 'submission_unknown')

    def test_invalid_adapter_receipt_keeps_lock(self):
        with self.assertRaises(AuditError):
            self.store.execute(self.attempt, self.review, self.root, lambda handoff: {'binding': handoff['binding'], 'outcome': 'submitted', 'note': 'No receipt'})
        self.assertEqual(self.store.recover(self.attempt)['attempt']['state'], 'submission_unknown')

    def test_legacy_migration_preserves_unknown_locks(self):
        self.store.resolve_attempt(self.attempt, 'submission_unknown', 'Legacy uncertain history')
        with self.store.db:
            self.store.db.execute('DROP TABLE execution_dispatches')
            self.store.db.execute('PRAGMA user_version = 3')
        self.store.close()
        self.store = self.fixture.store = execution.ExecutionStore(self.private)
        self.assertEqual(self.store.db.execute('PRAGMA user_version').fetchone()[0], 4)
        with self.assertRaises(AuditError):
            self.store.claim(self.attempt, self.review, self.root)
        self.assertEqual(self.store.recover(self.attempt)['attempt']['state'], 'submission_unknown')

    def test_legacy_reserved_lock_is_not_assumed_unused(self):
        with self.store.db:
            self.store.db.execute('DROP TABLE execution_dispatches')
            self.store.db.execute('PRAGMA user_version = 3')
        self.store.close()
        self.store = self.fixture.store = execution.ExecutionStore(self.private)
        with self.assertRaisesRegex(AuditError, 'Pre-upgrade'):
            self.store.claim(self.attempt, self.review, self.root)
        self.store.resolve_attempt(self.attempt, 'failed', 'Synthetic no-submission review', b'Synthetic evidence')
        second = self.store.reserve_attempt(self.app, 1, self.fixture.lead['source_url'], 'new-id')['attempt']['id']
        review = deepcopy(self.review)
        review['binding'] = self.store.review_template(second)['binding']
        with self.assertRaisesRegex(AuditError, 'Pre-upgrade'):
            self.store.claim(second, review, self.root)

    def test_legacy_packet_without_handoff_cannot_dispatch(self):
        with self.store.db:
            self.store.db.execute('DELETE FROM workflow_intakes')
        with self.assertRaisesRegex(AuditError, 'completed radar/context handoff'):
            self.store.claim(self.attempt, self.review, self.root)

    def test_review_corruption_is_visible(self):
        self.store.claim(self.attempt, self.review, self.root)
        with self.store.db:
            self.store.db.execute('UPDATE execution_dispatches SET review = ?', (b'{}',))
        self.assertFalse(self.store.inspect(self.app)['integrity_ok'])
        with self.assertRaises(AuditError):
            self.store.claim(self.attempt, self.review, self.root)

    def test_cli_errors_are_actionable_and_sanitized(self):
        command = [sys.executable, execution.__file__, '--store', str(self.private), 'claim', self.attempt,
                   '--review', str(self.root / 'review.json'), '--context-root', str(self.root)]
        (self.root / 'review.json').write_text('{}')
        result = subprocess.run(command, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('exact attempt, packet, and destination', json.loads(result.stderr)['error'])
        (self.root / 'review.json').unlink()
        result = subprocess.run(command, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(str(self.root), result.stderr)

    def test_cli_concurrent_claim_and_recovery(self):
        path = self.root / 'review.json'
        path.write_text(json.dumps(self.review))
        command = [sys.executable, execution.__file__, '--store', str(self.private), 'claim', self.attempt,
                   '--review', str(path), '--context-root', str(self.root)]
        def run(_):
            result = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)['result']
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(run, range(4)))
        self.assertEqual(sum(r['dispatch_new'] for r in results), 1)
        self.assertEqual(sum('artifacts' in r for r in results), 1)
        result = subprocess.run([sys.executable, execution.__file__, '--store', str(self.private),
                                 'recover', self.attempt], text=True, capture_output=True)
        self.assertTrue(json.loads(result.stdout)['result']['recovery_only'])
        receipt = self.root / 'receipt.json'
        receipt.write_text(json.dumps({'binding': self.review['binding'], 'outcome': 'submitted',
                                       'note': 'Synthetic CLI reconciliation'}))
        evidence = self.root / 'receipt-evidence.txt'
        evidence.write_bytes(b'Synthetic receipt only')
        result = subprocess.run([sys.executable, execution.__file__, '--store', str(self.private),
                                 'reconcile', self.attempt, '--receipt', str(receipt), '--evidence', str(evidence)],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['result']['attempt']['state'], 'submitted')


if __name__ == '__main__':
    unittest.main()
