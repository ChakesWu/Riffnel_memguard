"""On-disk workspace: memories, sources, tests, audit log and a JSON state file."""
from __future__ import annotations

import json
import os
import shutil
from contextlib import contextmanager
from pathlib import Path

from ..adapters.base import JsonFileStore
from .audit import AuditLog
from .locking import atomic_write, file_lock
from .models import Source, TestCase

EXAMPLES_ROOT = Path(__file__).resolve().parents[1] / "examples"
EXAMPLES = EXAMPLES_ROOT / "bank"  # kept for callers that import it


class Workspace:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    @property
    def initialized(self) -> bool:
        return (self.root / "memories.json").exists()

    def init(self, example: bool | str = True) -> None:
        """example: True or "bank" (Chinese example bank), "bank_br" (Brazilian bank in zh/pt/en), False (empty)."""
        self.root.mkdir(parents=True, exist_ok=True)
        if example:
            name = "bank" if example is True else example
            src = EXAMPLES_ROOT / name
            if not src.is_dir():
                raise ValueError(f"unknown example {name!r}; choose bank or bank_br")
            for n in ("memories.json", "sources.json", "tests.json", "i18n_checks.json"):
                if (src / n).exists():
                    shutil.copy(src / n, self.root / n)
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
        return AuditLog(self.root / "audit.db", key=os.environ.get("RIFFNEL_AUDIT_KEY"))

    @property
    def clauses(self):
        data = json.loads((self.root / "sources.json").read_text(encoding="utf-8"))
        return [c for s in data for c in Source(**s).clauses]

    @property
    def tests(self):
        return [TestCase(**t) for t in json.loads((self.root / "tests.json").read_text(encoding="utf-8"))]

    # -- state: read-only snapshot, or a locked read-modify-write transaction -----------------------
    @property
    def i18n_checks(self) -> list[dict]:
        """Cross-lingual consistency checks: the same question in several languages (see engines/crosslingual.py)."""
        f = self.root / "i18n_checks.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []

    def state(self) -> dict:
        self._require()
        return json.loads((self.root / "state.json").read_text(encoding="utf-8"))

    def _write_state(self, st: dict) -> None:
        atomic_write(self.root / "state.json", json.dumps(st, ensure_ascii=False, indent=2))

    def save_state(self, st: dict) -> None:
        """Atomic write. Prefer `transaction()`: a bare save can overwrite a concurrent change."""
        self._write_state(st)

    @contextmanager
    def transaction(self):
        """Lock the workspace, load the state, yield it, and write it back if the block succeeds.

        Concurrent commands wait for each other instead of overwriting each other's changes. The lock is held while
        the block runs (including calls to an external agent), and it is not re-entrant.
        """
        self._require()
        with file_lock(self.root / "state.lock"):
            st = self.state()
            yield st
            self._write_state(st)

    # -- sensitive values needed only between an erasure request and its verification ----------------
    @property
    def secrets_dir(self) -> Path:
        return self.root / "secrets"

    def put_secret(self, name: str, data: dict) -> None:
        self.secrets_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.secrets_dir, 0o700)
        except OSError:
            pass
        atomic_write(self.secrets_dir / f"{name}.json", json.dumps(data, ensure_ascii=False), mode=0o600)

    def get_secret(self, name: str) -> dict | None:
        f = self.secrets_dir / f"{name}.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None

    def drop_secret(self, name: str) -> bool:
        f = self.secrets_dir / f"{name}.json"
        if not f.exists():
            return False
        # overwrite before unlinking: best effort only, journaling filesystems and SSDs may keep copies
        try:
            f.write_bytes(b"\0" * f.stat().st_size)
        except OSError:
            pass
        f.unlink()
        return True
