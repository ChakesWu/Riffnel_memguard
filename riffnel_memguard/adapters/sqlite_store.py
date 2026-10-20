"""SQLite adapter: use an existing table of memories, or create the reference table.

Column names are configurable, so a table written by another application can be investigated and corrected in place.
Only `id` and `content` are required. Without a `status` column the store cannot invalidate or quarantine a memory
(those calls raise), and corrections that need it must be done by deleting and re-adding.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Optional

from ..core.models import MemoryRecord, scope_compatible
from .base import similarity

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _ident(name: str) -> str:
    if not _IDENT.match(name):
        raise ValueError(f"unsafe SQL identifier: {name!r}")
    return name


class SQLiteStore:
    name = "sqlite"

    def __init__(self, path: str | Path, table: str = "memories", id_col: str = "id", content_col: str = "content",
                 scope_cols: tuple[str, ...] = ("user", "product"), status_col: Optional[str] = "status",
                 kind_col: Optional[str] = "kind", key_col: Optional[str] = "key", value_col: Optional[str] = "value",
                 derived_col: Optional[str] = "derived_from", written_col: Optional[str] = "written_at",
                 create: bool = True):
        self.path = Path(path)
        self.table = _ident(table)
        self.cols = {"id": _ident(id_col), "content": _ident(content_col)}
        for k, v in (("status", status_col), ("kind", kind_col), ("key", key_col), ("value", value_col),
                     ("derived", derived_col), ("written", written_col)):
            if v:
                self.cols[k] = _ident(v)
        self.scope_cols = tuple(_ident(c) for c in scope_cols)
        with self._conn() as c:
            exists = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (self.table,)).fetchone()
            if not exists:
                if not create:
                    raise ValueError(f"table {self.table!r} not found in {self.path}")
                cols = ", ".join([f'"{self.cols["id"]}" TEXT PRIMARY KEY', f'"{self.cols["content"]}" TEXT NOT NULL']
                                 + [f'"{c_}" TEXT' for k, c_ in self.cols.items() if k not in ("id", "content")]
                                 + [f'"{s}" TEXT' for s in self.scope_cols])
                c.execute(f'CREATE TABLE "{self.table}" ({cols})')
            self._check_columns(c)

    def _conn(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    def _check_columns(self, c) -> None:
        have = {r["name"] for r in c.execute(f'PRAGMA table_info("{self.table}")')}
        missing = [n for n in [*self.cols.values(), *self.scope_cols] if n not in have]
        if missing:
            raise ValueError(f"table {self.table!r} lacks columns {missing}; adjust the column mapping")

    # -- conversion -------------------------------------------------------------------------------
    def _record(self, row: sqlite3.Row) -> MemoryRecord:
        g = lambda k: row[self.cols[k]] if k in self.cols else None  # noqa: E731
        value = g("value")
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                pass
        derived = g("derived")
        return MemoryRecord(
            id=str(g("id")), content=g("content") or "", kind=g("kind") or "fact",
            scope={s: row[s] for s in self.scope_cols if row[s] not in (None, "")}, key=g("key"), value=value,
            status=g("status") or "active", written_at=g("written") or "",
            derived_from=json.loads(derived) if derived else [])

    def _select(self, where: str = "", args: tuple = ()) -> list[sqlite3.Row]:
        with self._conn() as c:
            return c.execute(f'SELECT * FROM "{self.table}" {where}', args).fetchall()

    # -- MemoryStoreAdapter -----------------------------------------------------------------------
    def list(self, scope: Optional[dict] = None) -> list[MemoryRecord]:
        recs = [self._record(r) for r in self._select()]
        return [r for r in recs if scope_compatible(r.scope, scope)] if scope else recs

    def get(self, external_id: str) -> Optional[MemoryRecord]:
        rows = self._select(f'WHERE "{self.cols["id"]}" = ?', (external_id,))
        return self._record(rows[0]) if rows else None

    def search(self, query: str, scope: dict, k: int) -> list[tuple[MemoryRecord, float]]:
        cands = [r for r in self.list(scope) if r.status == "active"]
        scores = similarity(query, [r.content for r in cands])
        return sorted(zip(cands, scores), key=lambda x: (-x[1], x[0].id))[:k]

    def add(self, record: MemoryRecord) -> str:
        vals = {self.cols["id"]: record.id, self.cols["content"]: record.content}
        for k, v in (("status", record.status), ("kind", record.kind), ("key", record.key),
                     ("value", None if record.value is None else json.dumps(record.value)),
                     ("derived", json.dumps(record.derived_from) if record.derived_from else None),
                     ("written", record.written_at)):
            if k in self.cols:
                vals[self.cols[k]] = v
        for s in self.scope_cols:
            vals[s] = record.scope.get(s)
        cols = ", ".join(f'"{c}"' for c in vals)
        with self._conn() as c:
            c.execute(f'INSERT INTO "{self.table}" ({cols}) VALUES ({", ".join("?" * len(vals))})', tuple(vals.values()))
        return record.id

    def _set_status(self, external_id: str, status: str) -> None:
        if "status" not in self.cols:
            raise NotImplementedError("this table has no status column; delete and re-add instead")
        with self._conn() as c:
            n = c.execute(f'UPDATE "{self.table}" SET "{self.cols["status"]}" = ? WHERE "{self.cols["id"]}" = ?',
                          (status, external_id)).rowcount
        if not n:
            raise KeyError(external_id)

    def invalidate(self, external_id: str, reason: str) -> None:
        self._set_status(external_id, "invalidated")

    def quarantine(self, external_id: str, reason: str) -> None:
        self._set_status(external_id, "quarantined")

    def restore(self, external_id: str) -> None:
        self._set_status(external_id, "active")

    def rescope(self, external_id: str, scope: dict) -> None:
        sets = ", ".join(f'"{s}" = ?' for s in self.scope_cols)
        with self._conn() as c:
            n = c.execute(f'UPDATE "{self.table}" SET {sets} WHERE "{self.cols["id"]}" = ?',
                          (*[scope.get(s) for s in self.scope_cols], external_id)).rowcount
        if not n:
            raise KeyError(external_id)

    def delete(self, external_id: str) -> None:
        """Physical delete. Depending on how SQLite was built, deleted bytes can stay in free pages (the build used in
        development did not keep them); overwrite and compact anyway so the result does not depend on the build."""
        con = sqlite3.connect(self.path)
        try:
            con.execute("PRAGMA secure_delete = ON")
            con.execute(f'DELETE FROM "{self.table}" WHERE "{self.cols["id"]}" = ?', (external_id,))
            con.commit()
            con.execute("VACUUM")
        finally:
            con.close()

    def snapshot(self) -> bytes:
        data = sorted((r.model_dump() for r in self.list()), key=lambda d: d["id"])
        return json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
