"""Data models shared by all engines."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(obj: Any) -> str:
    return sha256_text(json.dumps(obj, ensure_ascii=False, sort_keys=True))


def scope_compatible(record_scope: dict, query_scope: dict) -> bool:
    """A record fits a query scope unless a shared key has a different value."""
    return all(query_scope.get(k, v) == v for k, v in record_scope.items())


class MemoryRecord(BaseModel):
    id: str
    content: str
    kind: Literal["fact", "summary", "preference", "episodic"] = "fact"
    scope: dict[str, str] = Field(default_factory=dict)
    key: Optional[str] = None
    value: Any = None
    status: Literal["active", "invalidated", "deleted", "quarantined"] = "active"
    written_at: str = ""
    derived_from: list[str] = Field(default_factory=list)
    supersedes: Optional[str] = None

    def sha(self) -> str:
        return sha256_json(self.model_dump())


class ClauseVersion(BaseModel):
    id: str
    version: str
    text: str
    value: Any
    valid_from: str
    valid_to: Optional[str] = None


class Clause(BaseModel):
    id: str
    key: str
    title: str
    scope: dict[str, str] = Field(default_factory=dict)
    unit: str
    keywords: list[str]
    versions: list[ClauseVersion]

    def version_at(self, date: str) -> Optional[ClauseVersion]:
        for v in self.versions:
            if v.valid_from <= date and (v.valid_to is None or date <= v.valid_to):
                return v
        return None

    def superseded_at(self, date: str) -> list[ClauseVersion]:
        return [v for v in self.versions if v.valid_to is not None and v.valid_to < date]


class Source(BaseModel):
    id: str
    name: str
    issuer: str
    type: str
    clauses: list[Clause]


class Incident(BaseModel):
    id: str
    occurred_at: str
    agent_id: str
    scope: dict[str, str]
    question: str
    answer: str
    retrieved_ids: list[str] = Field(default_factory=list)


class Claim(BaseModel):
    key: str
    value: Any
    span: str


FindingClass = Literal["M1", "M2", "M3", "M4", "M5", "M6"]


class Finding(BaseModel):
    cls: FindingClass
    memory_id: str
    incident_id: Optional[str] = None
    confidence: float
    evidence: dict[str, Any] = Field(default_factory=dict)


class Action(BaseModel):
    type: Literal["invalidate", "add", "delete", "purge_derived", "quarantine", "rescope", "advice"]
    target: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    before_sha256: Optional[str] = None
    after_sha256: Optional[str] = None


class Plan(BaseModel):
    id: str
    incident_id: Optional[str] = None
    actions: list[Action]
    status: Literal["draft", "approved", "applied", "rolled_back"] = "draft"
    approved_by: Optional[str] = None


class TestCase(BaseModel):
    __test__ = False
    id: str
    key: str
    question: str
    scope: dict[str, str]
    must_include: list[str] = Field(default_factory=list)
    must_not_include: list[str] = Field(default_factory=list)
