import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone


class SignalStore:
    def __init__(self, path: str):
        self.path = path
        self._init_db()

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=30)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        with self.connection() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS signals (
                    signal_id TEXT PRIMARY KEY,
                    received_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    result TEXT
                )
            ''')

    def reserve(self, signal_id: str, payload: dict) -> bool:
        try:
            with self.connection() as conn:
                conn.execute(
                    'INSERT INTO signals(signal_id, received_at, status, payload) VALUES (?, ?, ?, ?)',
                    (signal_id, datetime.now(timezone.utc).isoformat(), 'RECEIVED', json.dumps(payload))
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def finish(self, signal_id: str, status: str, result: dict):
        with self.connection() as conn:
            conn.execute(
                'UPDATE signals SET status=?, result=? WHERE signal_id=?',
                (status, json.dumps(result, default=str), signal_id)
            )
