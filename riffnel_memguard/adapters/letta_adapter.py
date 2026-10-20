"""Adapter for Letta archival memory (`letta-client`, Apache-2.0): one Letta agent's passages are the memory store.

Letta passages can be created, listed, searched and deleted, but not modified, and their tags are fixed at creation.
So Riffnel keeps its fields in tags (`rf_id`, `rf_status`, `rf_key`, `sc:<scope key>=<value>`, ...) and changes a
memory by writing a new passage and then deleting the old one; the logical id (`rf_id`) stays the same while the
Letta passage id changes. Passages an agent wrote itself carry no tags: they are listed as active, unscoped memories
whose id is the Letta passage id, and keep that id when they are later replaced.

Covered: archival passages. Not covered: core memory blocks, conversation messages, files.
"""
from __future__ import annotations

import json
import warnings
from typing import Any, Optional

from ..core.models import MemoryRecord, scope_compatible
from .base import MemoryListingTruncated

TESTED_CLIENT_PREFIX = "1.10."   # letta-client
TESTED_SERVER_PREFIX = "0.16."   # Letta server (REST), as reported by /v1/health


def _tag_value(tags: list[str], prefix: str) -> Optional[str]:
    return next((t[len(prefix):] for t in tags if t.startswith(prefix)), None)


def _text(p: Any) -> str:
    return getattr(p, "text", None) or getattr(p, "content", "") or ""


class LettaAdapter:
    name = "letta"

    def __init__(self, client, agent_id: str, page_size: int = 200, max_items: int = 100_000):
        self.c, self.agent_id = client, agent_id
        self.page_size, self.max_items = max(1, page_size), max_items
        try:
            import importlib.metadata as md
            cv = md.version("letta-client")
            sv = str(getattr(client.health(), "version", "unknown"))
            if not cv.startswith(TESTED_CLIENT_PREFIX) or not sv.startswith(TESTED_SERVER_PREFIX):
                warnings.warn(f"letta-client {cv} / server {sv} not tested with this adapter (tested: client "
                              f"{TESTED_CLIENT_PREFIX}x, server {TESTED_SERVER_PREFIX}x)", RuntimeWarning, stacklevel=2)
        except Exception:  # version checks must never block use
            pass

    # -- tags <-> records -------------------------------------------------------------------------
    @staticmethod
    def _encode(rec: MemoryRecord, extra: Optional[list[str]] = None) -> list[str]:
        tags = [f"rf_id:{rec.id}", f"rf_status:{rec.status}", f"rf_kind:{rec.kind}"]
        for prefix, v in (("rf_key", rec.key), ("rf_supersedes", rec.supersedes), ("rf_source_ref", rec.source_ref),
                          ("rf_written", rec.written_at or None)):
            if v is not None:
                tags.append(f"{prefix}:{v}")
        if rec.value is not None:
            tags.append(f"rf_value:{json.dumps(rec.value, ensure_ascii=False)}")
        tags += [f"rf_derived:{d}" for d in rec.derived_from]
        tags += [f"sc:{k}={v}" for k, v in rec.scope.items()]
        return tags + list(extra or [])

    @staticmethod
    def _decode(passage_id: str, text: str, tags: list[str]) -> MemoryRecord:
        value = _tag_value(tags, "rf_value:")
        return MemoryRecord(
            id=_tag_value(tags, "rf_id:") or passage_id, content=text, kind=_tag_value(tags, "rf_kind:") or "fact",
            scope={t[3:].split("=", 1)[0]: t[3:].split("=", 1)[1] for t in tags if t.startswith("sc:") and "=" in t},
            key=_tag_value(tags, "rf_key:"), value=json.loads(value) if value is not None else None,
            status=_tag_value(tags, "rf_status:") or "active", written_at=_tag_value(tags, "rf_written:") or "",
            derived_from=[t[len("rf_derived:"):] for t in tags if t.startswith("rf_derived:")],
            supersedes=_tag_value(tags, "rf_supersedes:"), source_ref=_tag_value(tags, "rf_source_ref:"))

    # -- listing (cursor pagination) --------------------------------------------------------------
    def _passages(self) -> list:
        out: list = []
        after = None
        while True:
            kw: dict[str, Any] = {"limit": self.page_size, "ascending": True}
            if after:
                kw["after"] = after
            page = self.c.agents.passages.list(self.agent_id, **kw)
            out += list(page)
            if len(page) < self.page_size:
                return out
            if len(out) >= self.max_items:
                raise MemoryListingTruncated(f"Letta agent {self.agent_id} has at least {len(out)} passages, the "
                                             "adapter's max_items; the listing may be incomplete.")
            after = page[-1].id

    def _grouped(self) -> dict[str, list]:
        groups: dict[str, list] = {}
        for p in self._passages():
            tags = list(p.tags or [])
            groups.setdefault(_tag_value(tags, "rf_id:") or p.id, []).append(p)
        return groups

    @classmethod
    def _record_of(cls, logical_id: str, parts: list) -> MemoryRecord:
        first = parts[0]  # several passages (chunks) of one memory are joined; tags come from the first
        return cls._decode(first.id, "".join(_text(p) for p in parts), list(first.tags or []))

    # -- MemoryStoreAdapter -----------------------------------------------------------------------
    def list(self, scope: Optional[dict] = None) -> list[MemoryRecord]:
        recs = [self._record_of(i, parts) for i, parts in self._grouped().items()]
        return [r for r in recs if scope_compatible(r.scope, scope)] if scope else recs

    def get(self, external_id: str) -> Optional[MemoryRecord]:
        parts = self._grouped().get(external_id)
        return self._record_of(external_id, parts) if parts else None

    def search(self, query: str, scope: dict, k: int) -> list[tuple[MemoryRecord, float]]:
        """Letta's search returns an ordered list without similarity scores, so the score is rank-derived (1/(1+rank))."""
        res = self.c.agents.passages.search(self.agent_id, query=query, top_k=max(50, k * 10))
        out = []
        for rank, r in enumerate(res.results):
            rec = self._decode(r.id, _text(r), list(r.tags or []))
            if rec.status == "active" and scope_compatible(rec.scope, scope):
                out.append((rec, 1.0 / (1 + rank)))
        return out[:k]

    def add(self, record: MemoryRecord) -> str:
        self.c.agents.passages.create(self.agent_id, text=record.content, tags=self._encode(record))
        return record.id

    def _replace(self, external_id: str, **changes) -> None:
        """Write the changed memory as a new passage first, then delete the old one(s): a failure loses nothing."""
        parts = self._grouped().get(external_id)
        if not parts:
            raise KeyError(external_id)
        rec = self._record_of(external_id, parts).model_copy(update={"id": external_id, **changes})
        extra = [t for t in (parts[0].tags or []) if not t.startswith(("rf_", "sc:"))]
        self.c.agents.passages.create(self.agent_id, text=rec.content, tags=self._encode(rec, extra))
        for p in parts:
            self.c.agents.passages.delete(p.id, agent_id=self.agent_id)

    def invalidate(self, external_id: str, reason: str) -> None:
        self._replace(external_id, status="invalidated")

    def quarantine(self, external_id: str, reason: str) -> None:
        self._replace(external_id, status="quarantined")

    def restore(self, external_id: str) -> None:
        self._replace(external_id, status="active")

    def rescope(self, external_id: str, scope: dict) -> None:
        self._replace(external_id, scope=dict(scope))

    def delete(self, external_id: str) -> None:
        """Delete every passage of the memory. In the tested setup (Letta 0.16.7 + PostgreSQL) this is a hard delete."""
        for p in self._grouped().get(external_id, []):
            self.c.agents.passages.delete(p.id, agent_id=self.agent_id)

    def snapshot(self) -> bytes:
        data = sorted((r.model_dump() for r in self.list()), key=lambda d: d["id"])
        return json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
