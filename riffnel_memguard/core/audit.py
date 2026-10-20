"""Append-only audit log with a SHA-256 hash chain (SQLite)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .models import sha256_text

GENESIS = "0" * 64


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AuditLog:
    def __init__(self, path: str | Path, clock: Callable[[], str] = _now):
        self.path = str(path)
        self.clock = clock
        with self._conn() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS audit_events ("
                "seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT, action TEXT,"
                "object_type TEXT, object_id TEXT, payload_sha256 TEXT, prev_hash TEXT, hash TEXT)"
            )

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    @staticmethod
    def _hash(prev: str, seq: int, ts: str, actor: str, action: str, ot: str, oid: str, psha: str) -> str:
        return sha256_text("|".join([prev, str(seq), ts, actor, action, ot, oid, psha]))

    def append(self, actor: str, action: str, object_type: str, object_id: str, payload_sha256: str = "") -> int:
        """Record an event. Never pass deleted content: only ids and hashes."""
        with self._conn() as c:
            row = c.execute("SELECT seq, hash FROM audit_events ORDER BY seq DESC LIMIT 1").fetchone()
            seq, prev = (row[0] + 1, row[1]) if row else (1, GENESIS)
            ts = self.clock()
            h = self._hash(prev, seq, ts, actor, action, object_type, object_id, payload_sha256)
            c.execute(
                "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?,?)",
                (seq, ts, actor, action, object_type, object_id, payload_sha256, prev, h),
            )
            return seq

    def events(self) -> list[tuple]:
        with self._conn() as c:
            return c.execute("SELECT * FROM audit_events ORDER BY seq").fetchall()

    def verify(self) -> tuple[bool, Optional[int]]:
        """Return (ok, first_bad_seq)."""
        prev = GENESIS
        for seq, ts, actor, action, ot, oid, psha, p, h in self.events():
            if p != prev or h != self._hash(prev, seq, ts, actor, action, ot, oid, psha):
                return False, seq
            prev = h
        return True, None
