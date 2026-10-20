"""Reference agent (simulated bank assistant). Offline, deterministic."""
from __future__ import annotations


class BankAssistAgent:
    """Retrieve the top-k memories and answer with the best hit. Scope filtering can be disabled to show M3."""

    def __init__(self, store, k: int = 1, scope_filter: bool = True):
        self.store = store
        self.k = k
        self.scope_filter = scope_filter

    def answer(self, question: str, scope: dict) -> tuple[str, list[str]]:
        hits = self.store.search(question, scope if self.scope_filter else {}, self.k)
        if not hits:
            return "抱歉，我没有相关信息。", []
        return hits[0][0].content, [r.id for r, _ in hits]
