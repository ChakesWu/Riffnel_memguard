"""Append-only audit log: a SHA-256 hash chain (SQLite) with an optional HMAC on every event.

The hash chain alone detects edits to single events, but anyone who can write the file can recompute the whole chain.
With a key (`RIFFNEL_AUDIT_KEY`) every event also carries an HMAC-SHA256 of its hash, so rewriting the chain needs the
key. An HMAC is symmetric: whoever holds the key can forge events, and nobody without it can verify. For public
verification, publish the chain head (`audit head`) somewhere the operator cannot edit.
"""
from __future__ import annotations

import hashlib
import hmac
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .models import sha256_text

GENESIS = "0" * 64


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AuditLog:
    def __init__(self, path: str | Path, clock: Callable[[], str] = _now, key: str | bytes | None = None):
        self.path = str(path)
        self.clock = clock
        self.key = key.encode("utf-8") if isinstance(key, str) and key else (key or None)
        with self._conn() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS audit_events ("
                "seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT, action TEXT,"
                "object_type TEXT, object_id TEXT, payload_sha256 TEXT, prev_hash TEXT, hash TEXT, mac TEXT)"
            )
            if "mac" not in {r[1] for r in c.execute("PRAGMA table_info(audit_events)")}:
                c.execute("ALTER TABLE audit_events ADD COLUMN mac TEXT")  # database written before signing existed

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    @staticmethod
    def _hash(prev: str, seq: int, ts: str, actor: str, action: str, ot: str, oid: str, psha: str) -> str:
        return sha256_text("|".join([prev, str(seq), ts, actor, action, ot, oid, psha]))

    def _mac(self, h: str) -> Optional[str]:
        return hmac.new(self.key, h.encode("utf-8"), hashlib.sha256).hexdigest() if self.key else None

    def append(self, actor: str, action: str, object_type: str, object_id: str, payload_sha256: str = "") -> int:
        """Record an event. Never pass deleted content: only ids and hashes."""
        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")  # two writers must not both extend the same head
            row = c.execute("SELECT seq, hash FROM audit_events ORDER BY seq DESC LIMIT 1").fetchone()
            seq, prev = (row[0] + 1, row[1]) if row else (1, GENESIS)
            ts = self.clock()
            h = self._hash(prev, seq, ts, actor, action, object_type, object_id, payload_sha256)
            c.execute(
                "INSERT INTO audit_events (seq, ts, actor, action, object_type, object_id, payload_sha256, prev_hash, hash, mac)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (seq, ts, actor, action, object_type, object_id, payload_sha256, prev, h, self._mac(h)),
            )
            return seq

    def events(self) -> list[tuple]:
        """Rows as (seq, ts, actor, action, object_type, object_id, payload_sha256, prev_hash, hash)."""
        with self._conn() as c:
            return c.execute(
                "SELECT seq, ts, actor, action, object_type, object_id, payload_sha256, prev_hash, hash"
                " FROM audit_events ORDER BY seq").fetchall()

    def head(self) -> tuple[int, str]:
        """(sequence number, hash) of the newest event: publish it somewhere the operator cannot edit."""
        ev = self.events()
        return (ev[-1][0], ev[-1][8]) if ev else (0, GENESIS)

    def verify(self) -> tuple[bool, Optional[int]]:
        """Return (ok, first_bad_seq). With a key, every event must also carry a valid HMAC."""
        prev = GENESIS
        with self._conn() as c:
            macs = dict(c.execute("SELECT seq, mac FROM audit_events"))
        for seq, ts, actor, action, ot, oid, psha, p, h in self.events():
            if p != prev or h != self._hash(prev, seq, ts, actor, action, ot, oid, psha):
                return False, seq
            if self.key and not hmac.compare_digest(macs.get(seq) or "", self._mac(h) or ""):
                return False, seq
            prev = h
        return True, None

    @property
    def signed(self) -> bool:
        with self._conn() as c:
            row = c.execute("SELECT COUNT(*), COUNT(mac) FROM audit_events").fetchone()
        return bool(row[0]) and row[0] == row[1]
