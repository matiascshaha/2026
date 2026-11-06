#!/usr/bin/env python3
"""Offline assisted application audit. No network, upload, or submission capability."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
from urllib.parse import urlsplit, urlunsplit
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 20 * 1024 * 1024
REQUIRED = {'job_description', 'resume_md', 'cover_letter_md', 'resume_pdf', 'cover_letter_pdf'}
OPTIONAL = {'questions', 'answers'}
TERMINAL = {'submitted', 'already_applied', 'submission_unknown'}


class AuditError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require_text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise AuditError(f'{field} must be nonempty text')
    return value.strip()


def timestamp(value, field):
    value = require_text(value, field)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise AuditError(f'{field} must be an ISO timestamp') from exc
    if parsed.tzinfo is None:
        raise AuditError(f'{field} must include a timezone')
    return parsed.astimezone(timezone.utc).isoformat()


def canonical_url(value):
    parsed = urlsplit(require_text(value, 'source_url'))
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
        raise AuditError('source_url must be an HTTP(S) URL without credentials')
    # Keep query parameters: some ATSs put the job identity in the query.
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip('/') or '/', parsed.query, ''))


def read_bytes(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise AuditError('Each input must be a regular file no larger than 20 MiB')
    data = path.read_bytes()
    if not data or len(data) > MAX_FILE_BYTES:
        raise AuditError('Input files must be nonempty and no larger than 20 MiB')
    return data


class AuditStore:
    def __init__(self, directory):
        directory = Path(directory).absolute()
        for part in [directory, *directory.parents]:
            if part.is_symlink():
                raise AuditError('Private storage must not use symlink directories')
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(directory, 0o700)
        path = directory / 'audit.sqlite'
        if path.is_symlink() or (path.exists() and (not path.is_file() or path.stat().st_nlink != 1)):
            raise AuditError('Audit database must be a regular, non-linked private file')
        # O_NOFOLLOW prevents following an existing database symlink on POSIX.
        fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            os.close(fd)
            raise AuditError('Audit database must be a regular, non-linked private file')
        os.fchmod(fd, 0o600)
        os.close(fd)
        self.db = sqlite3.connect(path, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys = ON')
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, 1):
            raise AuditError('Unsupported audit database version')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS applications (
                id TEXT PRIMARY KEY, identity TEXT UNIQUE, lead TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS packets (
                application_id TEXT NOT NULL REFERENCES applications(id),
                revision INTEGER NOT NULL, metadata TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(application_id, revision)
            );
            CREATE TABLE IF NOT EXISTS artifacts (
                application_id TEXT NOT NULL, revision INTEGER NOT NULL,
                name TEXT NOT NULL, sha256 TEXT NOT NULL, content BLOB NOT NULL,
                PRIMARY KEY(application_id, revision, name),
                FOREIGN KEY(application_id, revision) REFERENCES packets(application_id, revision)
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, application_id TEXT NOT NULL REFERENCES applications(id),
                occurred_at TEXT NOT NULL, kind TEXT NOT NULL, details TEXT NOT NULL,
                evidence BLOB, evidence_sha256 TEXT
            );
            PRAGMA user_version = 1;
        ''')

    def close(self):
        self.db.close()

    def _application(self, app_id):
        row = self.db.execute('SELECT * FROM applications WHERE id = ?', (app_id,)).fetchone()
        if row is None:
            raise AuditError('Unknown application ID')
        return row

    def _event(self, app_id, kind, details, evidence=None):
        self.db.execute('INSERT INTO events(application_id, occurred_at, kind, details, evidence, evidence_sha256) VALUES (?, ?, ?, ?, ?, ?)',
                        (app_id, now(), kind, json.dumps(details), evidence, digest(evidence) if evidence else None))

    def import_lead(self, lead):
        if not isinstance(lead, dict):
            raise AuditError('Lead must be a JSON object')
        clean = {key: require_text(lead.get(key), key) for key in ('lead_id', 'employer', 'role_title')}
        clean['source_url'] = canonical_url(lead.get('source_url'))
        clean['discovered_at'] = timestamp(lead.get('discovered_at'), 'discovered_at')
        clean['availability'] = lead.get('availability', 'unverified')
        if clean['availability'] not in {'open', 'closed', 'unverified'}:
            raise AuditError('availability must be open, closed, or unverified')
        clean['checked_at'] = timestamp(lead['checked_at'], 'checked_at') if lead.get('checked_at') else None
        if clean['availability'] != 'unverified' and not clean['checked_at']:
            raise AuditError('A declared availability check needs checked_at')
        provider_id = lead.get('provider_job_id')
        clean['provider_job_id'] = require_text(provider_id, 'provider_job_id') if provider_id is not None else None
        # Require an explicit provider namespace: host alone can contain multiple ATS tenants.
        provider = lead.get('provider')
        clean['provider'] = require_text(provider, 'provider') if provider_id is not None else None
        identity = digest(json.dumps([clean['employer'].casefold(), clean['provider'].casefold(), clean['provider_job_id']]).encode()) if provider_id is not None else None
        app_id = str(uuid.uuid4())
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if identity:
                existing = self.db.execute('SELECT id FROM applications WHERE identity = ?', (identity,)).fetchone()
                if existing:
                    self._event(existing['id'], 'lead_seen_again', clean)
                    return {'application_id': existing['id'], 'existing': True}
            # URL-only matches are review candidates, never proof of an application.
            candidates = []
            for row in self.db.execute('SELECT id, lead FROM applications'):
                prior = json.loads(row['lead'])
                if prior['source_url'] == clean['source_url']:
                    candidates.append(row['id'])
            self.db.execute('INSERT INTO applications VALUES (?, ?, ?, ?, ?)',
                            (app_id, identity, json.dumps(clean), 'discovered', now()))
            self._event(app_id, 'lead_imported', {'lead': clean, 'possible_duplicates': candidates,
                                               'identity_confidence': 'provider_id' if identity else 'needs_review'})
        return {'application_id': app_id, 'existing': False, 'possible_duplicates': candidates}

    def freeze(self, app_id, manifest, base):
        if not isinstance(manifest, dict):
            raise AuditError('Packet manifest must be a JSON object')
        files = manifest.get('files')
        contexts = manifest.get('context')
        if not isinstance(files, dict) or not REQUIRED.issubset(files) or set(files) - REQUIRED - OPTIONAL:
            raise AuditError('files must contain job_description, resume_md, cover_letter_md, resume_pdf, cover_letter_pdf; optional questions and answers')
        if not isinstance(contexts, dict) or not contexts:
            raise AuditError('context must map source IDs to exact source files used')
        blobs = {}
        for prefix, entries in (('files', files), ('context', contexts)):
            for name, filename in entries.items():
                require_text(name, 'artifact name')
                require_text(filename, 'artifact path')
                data = read_bytes(Path(base) / filename)
                if name in {'resume_pdf', 'cover_letter_pdf'} and prefix == 'files' and not data.startswith(b'%PDF-'):
                    raise AuditError('PDF artifacts must have a PDF header')
                blobs[f'{prefix}/{name}'] = data
        choices = require_text(manifest.get('tailoring_notes'), 'tailoring_notes')
        revision_ref = require_text(manifest.get('context_revision'), 'context_revision')
        blockers = manifest.get('blockers', [])
        if not isinstance(blockers, list) or any(not isinstance(x, str) or not x.strip() for x in blockers):
            raise AuditError('blockers must be a list of nonempty questions or review blockers')
        mappings = manifest.get('claims')
        if not isinstance(mappings, list) or not mappings:
            raise AuditError('claims must contain at least one claim-to-evidence mapping')
        checked = []
        for mapping in mappings:
            if not isinstance(mapping, dict):
                raise AuditError('Each claim must be an object')
            claim = require_text(mapping.get('claim'), 'claim')
            source = require_text(mapping.get('source_id'), 'source_id')
            data = blobs.get(f'context/{source}')
            if data is None or mapping.get('source_sha256') != digest(data):
                raise AuditError('Claim source hash must match a saved context source')
            start, end = mapping.get('start_line'), mapping.get('end_line')
            if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(data.decode('utf-8').splitlines()):
                raise AuditError('Claim line range must exist in its saved UTF-8 source')
            checked.append({'claim': claim, 'source_id': source, 'source_sha256': digest(data), 'start_line': start, 'end_line': end})
        metadata = {'context_revision': revision_ref, 'tailoring_notes': choices, 'blockers': blockers, 'claims': checked,
                    'inventory': {name: digest(data) for name, data in blobs.items()}}
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            app = self._application(app_id)
            if app['status'] in TERMINAL:
                raise AuditError('Confirmed or uncertain application history blocks new packet revisions; reconcile before further work')
            revision = self.db.execute('SELECT COALESCE(MAX(revision), 0) + 1 FROM packets WHERE application_id = ?', (app_id,)).fetchone()[0]
            self.db.execute('INSERT INTO packets VALUES (?, ?, ?, ?)', (app_id, revision, json.dumps(metadata), now()))
            for name, data in blobs.items():
                self.db.execute('INSERT INTO artifacts VALUES (?, ?, ?, ?, ?)', (app_id, revision, name, digest(data), data))
            self.db.execute('UPDATE applications SET status = ? WHERE id = ?', ('needs_input' if blockers else 'prepared', app_id))
            self._event(app_id, 'packet_frozen', {'revision': revision, 'blockers': blockers, 'submission_enabled': False})
        return {'application_id': app_id, 'revision': revision, 'submission_enabled': False}

    def observe(self, app_id, outcome, note, evidence=None, revision=None):
        if outcome not in {'submitted', 'already_applied', 'submission_unknown', 'failed'}:
            raise AuditError('Unsupported external outcome')
        note = require_text(note, 'note')
        if evidence is not None and (not isinstance(evidence, bytes) or not evidence or len(evidence) > MAX_FILE_BYTES):
            raise AuditError('Evidence must be nonempty bytes no larger than 20 MiB')
        if outcome in {'submitted', 'already_applied'} and evidence is None:
            raise AuditError('Confirmed external outcomes require saved receipt or site evidence')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            app = self._application(app_id)
            if revision is not None and not self.db.execute('SELECT 1 FROM packets WHERE application_id = ? AND revision = ?', (app_id, revision)).fetchone():
                raise AuditError('Unknown packet revision')
            if app['status'] in {'submitted', 'already_applied'}:
                raise AuditError('Confirmed outcomes cannot be overwritten')
            if app['status'] == 'submission_unknown' and outcome == 'failed' and evidence is None:
                raise AuditError('An uncertain submission needs reconciliation evidence before recording failure')
            self._event(app_id, 'external_outcome_observed', {'outcome': outcome, 'note': note, 'revision': revision,
                        'provenance': 'operator-reported; not independently verified', 'authorization': 'not captured by this offline tool'}, evidence)
            self.db.execute('UPDATE applications SET status = ? WHERE id = ?', (outcome, app_id))
        return {'application_id': app_id, 'status': outcome}

    def inspect(self, app_id):
        app = dict(self._application(app_id))
        app['lead'] = json.loads(app.pop('lead'))
        app.pop('identity')
        packets = []
        integrity = True
        for row in self.db.execute('SELECT * FROM packets WHERE application_id = ? ORDER BY revision', (app_id,)):
            packet = {'revision': row['revision'], 'created_at': row['created_at'], **json.loads(row['metadata']), 'artifacts': []}
            for artifact in self.db.execute('SELECT * FROM artifacts WHERE application_id = ? AND revision = ? ORDER BY name', (app_id, row['revision'])):
                valid = digest(artifact['content']) == artifact['sha256']
                integrity = integrity and valid
                packet['artifacts'].append({'name': artifact['name'], 'sha256': artifact['sha256'], 'bytes': len(artifact['content']), 'integrity_ok': valid})
            actual = {item['name']: item['sha256'] for item in packet['artifacts']}
            packet['integrity_ok'] = (actual == packet['inventory']
                                      and {f'files/{name}' for name in REQUIRED}.issubset(actual)
                                      and all(f"context/{claim['source_id']}" in actual for claim in packet['claims'])
                                      and all(item['integrity_ok'] for item in packet['artifacts']))
            integrity = integrity and packet['integrity_ok']
            packets.append(packet)
        events = []
        for row in self.db.execute('SELECT * FROM events WHERE application_id = ? ORDER BY id', (app_id,)):
            valid = digest(row['evidence']) == row['evidence_sha256'] if row['evidence'] is not None else row['evidence_sha256'] is None
            integrity = integrity and valid
            events.append({'id': row['id'], 'occurred_at': row['occurred_at'], 'kind': row['kind'], 'details': json.loads(row['details']), 'evidence_sha256': row['evidence_sha256'], 'integrity_ok': valid})
        return {'application': app, 'packets': packets, 'events': events, 'integrity_ok': integrity,
                'submission_enabled': False, 'warning': 'Prepared is not submitted or authorized. External outcomes are operator-reported. No receipt does not prove no application.'}

    def artifact(self, app_id, revision, name):
        row = self.db.execute('SELECT content, sha256 FROM artifacts WHERE application_id = ? AND revision = ? AND name = ?', (app_id, revision, name)).fetchone()
        if row is None or digest(row['content']) != row['sha256']:
            raise AuditError('Artifact missing or integrity check failed')
        return row['content']

    def receipt(self, app_id, event_id):
        row = self.db.execute('SELECT evidence, evidence_sha256 FROM events WHERE application_id = ? AND id = ?', (app_id, event_id)).fetchone()
        if row is None or row['evidence'] is None or digest(row['evidence']) != row['evidence_sha256']:
            raise AuditError('Evidence missing or integrity check failed')
        return row['evidence']


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    imp = commands.add_parser('import-lead')
    imp.add_argument('lead_json', type=Path)
    freeze = commands.add_parser('freeze')
    freeze.add_argument('application_id')
    freeze.add_argument('manifest_json', type=Path)
    show = commands.add_parser('inspect')
    show.add_argument('application_id')
    commands.add_parser('list')
    observe = commands.add_parser('observe')
    observe.add_argument('application_id')
    observe.add_argument('--outcome', required=True, choices=['submitted', 'already_applied', 'submission_unknown', 'failed'])
    observe.add_argument('--note-file', type=Path, required=True)
    observe.add_argument('--evidence-file', type=Path)
    observe.add_argument('--revision', type=int)
    extract = commands.add_parser('extract')
    extract.add_argument('application_id')
    extract.add_argument('revision', type=int)
    extract.add_argument('name')
    receipt = commands.add_parser('extract-evidence')
    receipt.add_argument('application_id')
    receipt.add_argument('event_id', type=int)
    args = parser.parse_args()
    store = None
    try:
        store = AuditStore(ROOT / '.private' / 'career-system')
        if args.command == 'import-lead':
            result = store.import_lead(json.loads(read_bytes(args.lead_json)))
        elif args.command == 'freeze':
            result = store.freeze(args.application_id, json.loads(read_bytes(args.manifest_json)), args.manifest_json.parent)
        elif args.command == 'observe':
            result = store.observe(args.application_id, args.outcome, read_bytes(args.note_file).decode('utf-8'), read_bytes(args.evidence_file) if args.evidence_file else None, args.revision)
        elif args.command == 'inspect':
            result = store.inspect(args.application_id)
        elif args.command == 'extract':
            sys.stdout.buffer.write(store.artifact(args.application_id, args.revision, args.name))
            return 0
        elif args.command == 'extract-evidence':
            sys.stdout.buffer.write(store.receipt(args.application_id, args.event_id))
            return 0
        else:
            result = {'applications': [dict(row) for row in store.db.execute('SELECT id, status, created_at FROM applications ORDER BY created_at')], 'submission_enabled': False}
        print(json.dumps({'schema_version': 1, 'ok': True, 'result': result}, indent=2))
        return 0
    except (AuditError, OSError, ValueError, sqlite3.Error, TypeError) as exc:
        # Do not echo input paths, application content, or SQLite error details.
        message = str(exc) if isinstance(exc, AuditError) else 'Unable to process input or access audit storage'
        print(json.dumps({'schema_version': 1, 'ok': False, 'error': message}), file=sys.stderr)
        return 1
    finally:
        if store is not None:
            store.close()


if __name__ == '__main__':
    raise SystemExit(main())
