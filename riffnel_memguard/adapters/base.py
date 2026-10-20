"""Adapter interface and the JSON-file reference store."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Protocol

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ..core.models import MemoryRecord, scope_compatible


class MemoryListingTruncated(RuntimeError):
    """A store returned as many memories as the limit allows, so the listing may be incomplete."""


class MemoryStoreAdapter(Protocol):
    name: str

    def list(self, scope: Optional[dict] = None) -> list[MemoryRecord]: ...
    def get(self, external_id: str) -> Optional[MemoryRecord]: ...
    def search(self, query: str, scope: dict, k: int) -> list[tuple[MemoryRecord, float]]: ...
    def add(self, record: MemoryRecord) -> str: ...
    def invalidate(self, external_id: str, reason: str) -> None: ...
    def quarantine(self, external_id: str, reason: str) -> None: ...
    def restore(self, external_id: str) -> None: ...
    def delete(self, external_id: str) -> None: ...
    def rescope(self, external_id: str, scope: dict) -> None: ...
    def snapshot(self) -> bytes: ...


def similarity(query: str, texts: list[str]) -> list[float]:
    """Character 2-3 gram TF-IDF cosine similarity (no model download, deterministic)."""
    if not texts:
        return []
    vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 3))
    m = vec.fit_transform(texts + [query])
    return [float(x) for x in cosine_similarity(m[-1], m[:-1])[0]]


class JsonFileStore:
    """Reference store: a JSON list of memory records on disk."""

    name = "json"

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._records: dict[str, MemoryRecord] = {}
        if self.path.exists():
            for d in json.loads(self.path.read_text(encoding="utf-8")):
                r = MemoryRecord(**d)
                self._records[r.id] = r

    def _save(self) -> None:
        data = [r.model_dump() for r in self._records.values()]
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list(self, scope: Optional[dict] = None) -> list[MemoryRecord]:
        recs = list(self._records.values())
        return [r for r in recs if scope_compatible(r.scope, scope)] if scope else recs

    def get(self, external_id: str) -> Optional[MemoryRecord]:
        return self._records.get(external_id)

    def search(self, query: str, scope: dict, k: int) -> list[tuple[MemoryRecord, float]]:
        cands = [r for r in self._records.values() if r.status == "active" and scope_compatible(r.scope, scope)]
        scores = similarity(query, [r.content for r in cands])
        ranked = sorted(zip(cands, scores), key=lambda x: (-x[1], x[0].id))
        return ranked[:k]

    def add(self, record: MemoryRecord) -> str:
        self._records[record.id] = record
        self._save()
        return record.id

    def _set_status(self, external_id: str, status: str) -> None:
        self._records[external_id].status = status
        self._save()

    def invalidate(self, external_id: str, reason: str) -> None:
        self._set_status(external_id, "invalidated")

    def quarantine(self, external_id: str, reason: str) -> None:
        self._set_status(external_id, "quarantined")

    def restore(self, external_id: str) -> None:
        self._set_status(external_id, "active")

    def delete(self, external_id: str) -> None:
        self._records.pop(external_id, None)
        self._save()

    def rescope(self, external_id: str, scope: dict) -> None:
        self._records[external_id].scope = scope
        self._save()

    def snapshot(self) -> bytes:
        data = [self._records[k].model_dump() for k in sorted(self._records)]
        return json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
