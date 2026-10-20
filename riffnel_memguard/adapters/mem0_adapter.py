"""Adapter for Mem0 open source (`mem0ai`, Apache-2.0).

Riffnel fields live in Mem0 metadata under an `rf_` prefix; scope keys other than `user` are stored as plain
metadata keys so Mem0 filters can use them. `agent_id` is used as the namespace that makes `get_all` work.

Mem0 keeps a history table (`history.db`) with the old and new text of every memory. Deleting a memory through
`Memory.delete` leaves that text behind, so this adapter exposes those rows as *traces*: the erasure probes read
them, and a `delete` through this adapter scrubs them (`purge_traces`).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import warnings
from pathlib import Path
from typing import Any, Optional

from ..core.models import MemoryRecord, scope_compatible

TRACE = "trace:"
TESTED_MEM0_PREFIX = "2.2."  # mem0ai 2.2.x is what this adapter was run against; other versions may change the API
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class MemoryListingTruncated(RuntimeError):
    """Mem0 returned as many memories as the limit allows, so the listing may be incomplete."""

_RF = ("rf_status", "rf_kind", "rf_key", "rf_value", "rf_derived_from", "rf_supersedes", "rf_source_ref",
       "rf_written_at", "rf_planned_id")


class OfflineHashEmbedder:
    """Deterministic character 2-3 gram hashing embedder: a test seam that needs no model download or API key.

    Mem0 calls `embed(text, memory_action)` on its embedding object; production setups should configure a real
    embedder in Mem0 instead of using this one.
    """

    dims = 512

    def __init__(self):
        from sklearn.feature_extraction.text import HashingVectorizer
        self.config = None
        self._v = HashingVectorizer(analyzer="char", ngram_range=(2, 3), n_features=self.dims, norm="l2",
                                    alternate_sign=False)

    def embed(self, text, memory_action=None):
        return self._v.transform([text]).toarray()[0].tolist()


def _disable_mem0_telemetry() -> None:
    """Mem0 sends anonymous telemetry to PostHog by default. Riffnel runs offline, so switch it off.

    Mem0 reads MEM0_TELEMETRY when its telemetry module is imported, and builds a client then, so setting the
    environment variable is not enough if `mem0` was imported earlier: patch the module as well.
    """
    os.environ["MEM0_TELEMETRY"] = "False"
    import mem0.memory.telemetry as t
    t.MEM0_TELEMETRY = False
    if getattr(t, "client_telemetry", None) is not None:
        t.client_telemetry.posthog = None


REAL_EMBEDDER_MODEL = "BAAI/bge-small-zh-v1.5"  # 512-dim Chinese model, MIT licensed on its model card (unverified here)


def make_memory(workdir: str | Path, embedder: str = "hash"):
    """A real `mem0.Memory` backed by local Qdrant and SQLite history.

    embedder="hash": the offline test seam above (no download). embedder="fastembed": Mem0's own fastembed embedder
    with `REAL_EMBEDDER_MODEL`, downloaded from Hugging Face on first use (needs `pip install fastembed`; on networks
    that block the Xet download host, `HF_HUB_DISABLE_XET=1` is set for you).

    Forces Mem0 telemetry off. If you wrap your own `Memory` in `Mem0Adapter`, its telemetry settings are untouched.
    """
    if embedder not in ("hash", "fastembed"):
        raise ValueError("embedder must be 'hash' or 'fastembed'")
    _disable_mem0_telemetry()
    from mem0 import Memory
    import mem0.memory.main as mem0_main
    wd = Path(workdir)
    wd.mkdir(parents=True, exist_ok=True)
    # Mem0 keeps a second local Qdrant under ~/.mem0 shared by every Memory in the process (two instances
    # collide on its lock). Point it at this working directory instead.
    mem0_main.mem0_dir = str(wd / ".mem0")
    dims = OfflineHashEmbedder.dims if embedder == "hash" else 512
    if embedder == "fastembed":
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        if "huggingface_hub" in sys.modules:  # the constant is read at import time, so patch it if already loaded
            import huggingface_hub.constants as hf_constants
            if os.environ["HF_HUB_DISABLE_XET"] == "1" and hasattr(hf_constants, "HF_HUB_DISABLE_XET"):
                hf_constants.HF_HUB_DISABLE_XET = True
        emb_cfg = {"provider": "fastembed", "config": {"model": REAL_EMBEDDER_MODEL, "embedding_dims": dims}}
    else:
        emb_cfg = {"provider": "openai", "config": {"api_key": "unused", "embedding_dims": dims}}
    cfg = {
        "embedder": emb_cfg,
        "vector_store": {"provider": "qdrant", "config": {"path": str(wd / "qdrant"), "collection_name": "riffnel",
                                                          "embedding_model_dims": dims}},
        "history_db_path": str(wd / "history.db"),
        "llm": {"provider": "openai", "config": {"api_key": "unused"}},  # never called: we add with infer=False
    }
    m = Memory.from_config(cfg)
    if embedder == "hash":
        m.embedding_model = OfflineHashEmbedder()
    return m


def make_offline_memory(workdir: str | Path):
    """Kept for compatibility: the offline hash-embedder stack."""
    return make_memory(workdir, "hash")


class Mem0Adapter:
    name = "mem0"

    def __init__(self, memory, agent_id: str = "riffnel", history_db: Optional[str | Path] = None,
                 max_items: int = 100_000, page_size: int = 500):
        """`max_items` bounds how many memories one listing may return; reaching it raises MemoryListingTruncated
        instead of silently returning a partial list. Mem0's `get_all` has no offset or cursor, so a listing asks for
        `page_size` items and doubles the limit until the answer is smaller than the limit."""
        try:
            import mem0
            version = getattr(mem0, "__version__", "unknown")
            if not str(version).startswith(TESTED_MEM0_PREFIX):
                warnings.warn(f"mem0ai {version} has not been tested with this adapter (tested: {TESTED_MEM0_PREFIX}x)",
                              RuntimeWarning, stacklevel=2)
        except ImportError:
            pass
        self.m = memory
        self.agent_id = agent_id
        self.max_items = max_items
        self.page_size = max(1, page_size)
        self.history_db = Path(history_db or getattr(getattr(memory, "config", None), "history_db_path", "") or "")

    # -- conversion -------------------------------------------------------------------------------
    def _record(self, item: dict) -> MemoryRecord:
        md = dict(item.get("metadata") or {})
        scope = {k: v for k, v in md.items() if not k.startswith("rf_")}
        if item.get("user_id"):
            scope["user"] = item["user_id"]
        return MemoryRecord(
            id=md.get("rf_planned_id") or item["id"], content=item.get("memory", ""),
            kind=md.get("rf_kind", "fact"), scope=scope, key=md.get("rf_key"), value=md.get("rf_value"),
            status=md.get("rf_status", "active"), written_at=md.get("rf_written_at", ""),
            derived_from=md.get("rf_derived_from") or [], supersedes=md.get("rf_supersedes"),
            source_ref=md.get("rf_source_ref"))

    def _get_all(self, extra: Optional[dict], limit: int) -> list[dict]:
        filters = {"agent_id": self.agent_id, **(extra or {})}
        res = self.m.get_all(filters=filters, top_k=limit, show_expired=True)
        return res["results"] if isinstance(res, dict) else res

    def _items(self) -> list[dict]:
        limit = min(self.page_size, self.max_items)
        while True:
            items = self._get_all(None, limit)
            if len(items) < limit:
                return items
            if limit >= self.max_items:
                raise MemoryListingTruncated(
                    f"Mem0 returned {len(items)} memories for agent_id={self.agent_id!r}, the adapter's max_items; "
                    "the listing may be incomplete. Raise max_items or partition the data by agent_id.")
            limit = min(limit * 2, self.max_items)

    def _resolve(self, external_id: str) -> Optional[dict]:
        """Find one memory by Mem0 id or by the id Riffnel planned for it, without listing everything."""
        if _UUID.match(external_id):
            it = self.m.get(external_id)
            if it and it.get("agent_id") == self.agent_id:
                return it
        hits = self._get_all({"rf_planned_id": external_id}, 2)
        return hits[0] if hits else None

    def _meta(self, rec: MemoryRecord) -> dict:
        md = {k: v for k, v in rec.scope.items() if k != "user"}
        md.update(rf_status=rec.status, rf_kind=rec.kind, rf_written_at=rec.written_at, rf_planned_id=rec.id)
        for k, v in (("rf_key", rec.key), ("rf_value", rec.value), ("rf_supersedes", rec.supersedes),
                     ("rf_source_ref", rec.source_ref)):
            if v is not None:
                md[k] = v
        if rec.derived_from:
            md["rf_derived_from"] = list(rec.derived_from)
        return md

    # -- MemoryStoreAdapter -----------------------------------------------------------------------
    def list(self, scope: Optional[dict] = None) -> list[MemoryRecord]:
        recs = [self._record(i) for i in self._items()]
        return [r for r in recs if scope_compatible(r.scope, scope)] if scope else recs

    def get(self, external_id: str) -> Optional[MemoryRecord]:
        if external_id.startswith(TRACE):
            return next((t for t in self.traces() if t.id == external_id), None)
        it = self._resolve(external_id)
        return self._record(it) if it else None

    def search(self, query: str, scope: dict, k: int) -> list[tuple[MemoryRecord, float]]:
        res = self.m.search(query, filters={"agent_id": self.agent_id, "rf_status": "active"},
                            top_k=max(50, k * 10), threshold=0.0)
        items = res["results"] if isinstance(res, dict) else res
        out = []
        for it in items:
            r = self._record(it)
            if r.status == "active" and scope_compatible(r.scope, scope):
                out.append((r, float(it.get("score") or 0.0)))
        return sorted(out, key=lambda x: (-x[1], x[0].id))[:k]

    def add(self, record: MemoryRecord) -> str:
        kw: dict[str, Any] = {"agent_id": self.agent_id, "metadata": self._meta(record), "infer": False}
        if record.scope.get("user"):
            kw["user_id"] = record.scope["user"]
        self.m.add(record.content, **kw)
        return record.id

    def _set_status(self, external_id: str, status: str) -> None:
        it = self._resolve(external_id)
        if it is None:
            raise KeyError(external_id)
        md = dict(it.get("metadata") or {})
        md["rf_status"] = status
        self.m.update(it["id"], metadata=md)

    def invalidate(self, external_id: str, reason: str) -> None:
        self._set_status(external_id, "invalidated")

    def quarantine(self, external_id: str, reason: str) -> None:
        self._set_status(external_id, "quarantined")

    def restore(self, external_id: str) -> None:
        self._set_status(external_id, "active")

    def rescope(self, external_id: str, scope: dict) -> None:
        it = self._resolve(external_id)
        if it is None:
            raise KeyError(external_id)
        md = {k: v for k, v in (it.get("metadata") or {}).items() if k.startswith("rf_")}
        md.update({k: v for k, v in scope.items() if k != "user"})
        self.m.update(it["id"], metadata=md)

    def delete(self, external_id: str) -> None:
        if external_id.startswith(TRACE):
            self._delete_trace_rows([external_id[len(TRACE):]])
            return
        it = self._resolve(external_id)
        if it is not None:
            self.m.delete(it["id"])
            self.purge_traces(it["id"])

    def snapshot(self) -> bytes:
        data = sorted((r.model_dump() for r in self.list()), key=lambda d: d["id"])
        return json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")

    # -- traces: history rows Mem0 leaves behind --------------------------------------------------
    def _history_rows(self) -> list[tuple]:
        if not self.history_db or not self.history_db.exists():
            return []
        with sqlite3.connect(self.history_db) as c:
            return c.execute("SELECT id, memory_id, old_memory, new_memory FROM history").fetchall()

    def traces(self) -> list[MemoryRecord]:
        """History rows as pseudo records (`trace:<row id>`) so the erasure probes can see them."""
        return [MemoryRecord(id=f"{TRACE}{rid}", kind="episodic", status="active",
                             content=" | ".join(t for t in (old, new) if t))
                for rid, _mid, old, new in self._history_rows()]

    def _delete_trace_rows(self, row_ids: list[str]) -> None:
        if not row_ids or not self.history_db.exists():
            return
        with sqlite3.connect(self.history_db) as c:
            c.executemany("DELETE FROM history WHERE id = ?", [(r,) for r in row_ids])
        self._vacuum()

    def purge_traces(self, memory_id: str) -> None:
        """Remove every history row of a memory, then compact the file so the bytes do not linger."""
        if not self.history_db or not self.history_db.exists():
            return
        with sqlite3.connect(self.history_db) as c:
            c.execute("DELETE FROM history WHERE memory_id = ?", (memory_id,))
        self._vacuum()

    def _vacuum(self) -> None:
        con = sqlite3.connect(self.history_db)
        try:
            con.execute("VACUUM")
        finally:
            con.close()
