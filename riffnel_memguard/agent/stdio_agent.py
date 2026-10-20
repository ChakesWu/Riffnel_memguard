"""Reference agent that speaks the `--agent-cmd` protocol over a Riffnel workspace store.

    riffnel-memguard ask "金卡免年费需要刷几笔？" --scope product=gold_card --at 2026-08-10 \\
        --agent-cmd "python -m riffnel_memguard.agent.stdio_agent --workspace .riffnel"

Copy this file as a starting point to wrap your own agent: read one JSON line, answer, print one JSON line.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..adapters.base import JsonFileStore
from .bank import BankAssistAgent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True, help="Riffnel workspace directory (reads memories.json)")
    ap.add_argument("--k", type=int, default=1)
    ap.add_argument("--log", help="append each question to this file (used by tests)")
    args = ap.parse_args(argv)
    req = json.loads(sys.stdin.readline())
    if args.log:
        with open(args.log, "a", encoding="utf-8") as f:
            f.write(req["question"] + "\n")
    agent = BankAssistAgent(JsonFileStore(Path(args.workspace) / "memories.json"), k=args.k)
    answer, ids = agent.answer(req["question"], req.get("scope", {}))
    print(json.dumps({"answer": answer, "retrieved_ids": ids}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
