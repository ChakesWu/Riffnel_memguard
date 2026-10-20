"""On-disk workspace: memories, sources, tests, audit log and a JSON state file."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from ..adapters.base import JsonFileStore
from .audit import AuditLog
from .models import Source, TestCase

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "bank"


class Workspace:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    @property
    def initialized(self) -> bool:
        return (self.root / "memories.json").exists()

    def init(self, example: bool = True) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if example:
            for n in ("memories.json", "sources.json", "tests.json"):
                shutil.copy(EXAMPLES / n, self.root / n)
        self._write_state({"incidents": {}, "plans": {}, "erasures": {}, "verifications": {}})

    def _require(self) -> None:
        if not self.initialized:
            raise FileNotFoundError(f"workspace {self.root} is not initialized; run `riffnel-memguard init`")

    @property
    def store(self) -> JsonFileStore:
        self._require()
        return JsonFileStore(self.root / "memories.json")

    @property
    def audit(self) -> AuditLog:
        return AuditLog(self.root / "audit.db")

    @property
    def clauses(self):
        data = json.loads((self.root / "sources.json").read_text(encoding="utf-8"))
        return [c for s in data for c in Source(**s).clauses]

    @property
    def tests(self):
        return [TestCase(**t) for t in json.loads((self.root / "tests.json").read_text(encoding="utf-8"))]

    def state(self) -> dict:
        self._require()
        return json.loads((self.root / "state.json").read_text(encoding="utf-8"))

    def _write_state(self, st: dict) -> None:
        (self.root / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_state(self, st: dict) -> None:
        self._write_state(st)
