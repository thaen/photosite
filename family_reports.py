"""Private, durable per-application bug inbox; shared with its independent worker.

Vendored identically in ADHD Log and Family Video. No web process starts an agent.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess

STATES = ('queued', 'running', 'fixed', 'needs_attention', 'failed')


def now():
    return datetime.now(timezone.utc).isoformat()


def revision(root):
    try:
        return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root,
                                       stderr=subprocess.DEVNULL, timeout=5).decode().strip()
    except (OSError, subprocess.SubprocessError):
        return None


class Inbox:
    def __init__(self, directory, root, app, title):
        self.directory, self.root = Path(directory), Path(root)
        self.app, self.title = app, title

    @contextmanager
    def database(self):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = self.directory / 'reports.sqlite3'
        # Create privately, including on first use by the web service.
        fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(fd)
        os.chmod(path, 0o600)
        db = sqlite3.connect(path, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            db.execute('''CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY, created TEXT NOT NULL, updated TEXT NOT NULL,
                note TEXT NOT NULL, context TEXT NOT NULL, status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0, result TEXT, history TEXT NOT NULL)''')
            with db:
                yield db
        finally:
            db.close()

    def decode(self, row, detail=True):
        item = dict(row)
        context = json.loads(item.pop('context'))
        item['app'], item['title'] = self.app, self.title
        item['history'] = json.loads(item['history'])
        item['result'] = json.loads(item['result']) if item['result'] else None
        if detail:
            item['context'] = context
        return item

    def get(self, db, ident):
        row = db.execute('SELECT * FROM reports WHERE id=?', (ident,)).fetchone()
        if row is None:
            raise ValueError('Report not found')
        return self.decode(row)

    def create(self, value, facts=None):
        if not isinstance(value, dict):
            raise ValueError('Expected an object')
        ident, note, context = value.get('id'), value.get('note'), value.get('context')
        if not isinstance(ident, str) or not re.fullmatch(r'[a-zA-Z0-9-]{16,80}', ident):
            raise ValueError('Invalid report ID')
        if not isinstance(note, str) or not 1 <= len(note.strip()) <= 2000:
            raise ValueError('Write a short note (up to 2,000 characters)')
        if (not isinstance(context, dict) or not isinstance(context.get('path'), str)
                or not context['path'].startswith('/') or len(context['path']) > 2000
                or not isinstance(context.get('details'), dict)):
            raise ValueError('Missing application context')
        if len(json.dumps(context).encode()) > 120000:
            raise ValueError('Report context is too large')
        with self.database() as db:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT * FROM reports WHERE id=?', (ident,)).fetchone()
            if previous:
                if previous['note'] != note.strip():
                    raise ValueError('Report ID already used')
                return self.decode(previous)
            stamp = now()
            # Repository selection and authority never come from browser data.
            context = dict(context, app=self.app, title=self.title,
                           server={'revision': revision(self.root), 'receivedAt': stamp, **(facts or {})})
            history = [{'at': stamp, 'status': 'queued', 'message': 'Report saved; waiting for the fix worker.'}]
            db.execute('INSERT INTO reports (id,created,updated,note,context,status,history) VALUES (?,?,?,?,?,?,?)',
                       (ident, stamp, stamp, note.strip(), json.dumps(context), 'queued', json.dumps(history)))
            return self.get(db, ident)

    def listing(self, before=None):
        with self.database() as db:
            rows = db.execute('SELECT rowid AS sequence,* FROM reports WHERE rowid<? ORDER BY rowid DESC LIMIT 51',
                              (int(before) if before else 9223372036854775807,)).fetchall()
            return {'reports': [self.decode(row, False) for row in rows[:50]],
                    'next': str(rows[49]['sequence']) if len(rows) > 50 else None}

    def transition(self, db, ident, status, message, result=None):
        if status not in STATES:
            raise ValueError('Invalid report status')
        item, stamp = self.get(db, ident), now()
        history = item['history'] + [{'at': stamp, 'status': status, 'message': message}]
        db.execute('UPDATE reports SET status=?,updated=?,history=?,result=? WHERE id=?',
                   (status, stamp, json.dumps(history), json.dumps(result) if result else None, ident))

    def retry(self, ident):
        with self.database() as db:
            db.execute('BEGIN IMMEDIATE')
            if self.get(db, ident)['status'] not in ('failed', 'needs_attention'):
                raise ValueError('Only failed reports or reports needing attention can be retried')
            self.transition(db, ident, 'queued', 'Retry requested from report history.')
            return self.get(db, ident)

    def claim(self):
        with self.database() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT id FROM reports WHERE status='queued' ORDER BY rowid LIMIT 1").fetchone()
            if row is None:
                return None
            self.transition(db, row['id'], 'running', 'Fixing agent started.')
            db.execute('UPDATE reports SET attempts=attempts+1 WHERE id=?', (row['id'],))
            return self.get(db, row['id'])

    def recover(self):
        with self.database() as db:
            for row in db.execute("SELECT id FROM reports WHERE status='running'").fetchall():
                self.transition(db, row['id'], 'needs_attention', 'Worker interrupted. Inspect the saved attempt before retrying.')
