"""Run any program as the agent under test: `--agent-cmd "python my_agent.py"`.

Protocol (one question per process, language independent):
- stdin : one JSON line  {"question": "...", "scope": {"product": "gold_card"}}
- stdout: the LAST non-empty line must be one JSON object  {"answer": "...", "retrieved_ids": ["id1", "id2"]}
  (anything printed before it, such as logs, is ignored). `retrieved_ids` are the memory ids that were in the
  agent's context; they must be ids in the store Riffnel investigates, or attribution cannot work.
- exit code 0 on success; anything else is an error and stderr is shown.

The command is split with shlex and run WITHOUT a shell. It is trusted configuration: it runs with your permissions,
so never build it from untrusted input.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess

MAX_OUTPUT = 1_000_000


class AgentCommandError(RuntimeError):
    """The external agent could not be run or answered outside the protocol."""


class CommandAgent:
    """Same `answer(question, scope) -> (answer, retrieved_ids)` interface as the other agents."""

    def __init__(self, command: str | list[str], timeout: float = 60.0, cwd: str | None = None,
                 env: dict | None = None):
        self.argv = list(command) if isinstance(command, (list, tuple)) else shlex.split(command, posix=os.name != "nt")
        if not self.argv:
            raise AgentCommandError("empty agent command")
        self.timeout, self.cwd, self.env = timeout, cwd, env
        self.model_name = f"command:{self.argv[0]}"

    def answer(self, question: str, scope: dict) -> tuple[str, list[str]]:
        payload = json.dumps({"question": question, "scope": scope}, ensure_ascii=False) + "\n"
        try:
            proc = subprocess.run(self.argv, input=payload, capture_output=True, text=True, encoding="utf-8",
                                  timeout=self.timeout, cwd=self.cwd, env=self.env)
        except FileNotFoundError:
            raise AgentCommandError(f"cannot start agent command {self.argv[0]!r}: not found")
        except subprocess.TimeoutExpired:
            raise AgentCommandError(f"agent command timed out after {self.timeout:g}s")
        if proc.returncode != 0:
            raise AgentCommandError(f"agent command exited with {proc.returncode}: {proc.stderr.strip()[-500:]}")
        if len(proc.stdout) > MAX_OUTPUT:
            raise AgentCommandError(f"agent output is larger than {MAX_OUTPUT} bytes")
        lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        if not lines:
            raise AgentCommandError("agent command printed nothing")
        try:
            out = json.loads(lines[-1])
        except json.JSONDecodeError:
            raise AgentCommandError(f"the last stdout line is not JSON: {lines[-1][:200]!r}")
        if not isinstance(out, dict) or not isinstance(out.get("answer"), str):
            raise AgentCommandError('the JSON object needs a string field "answer"')
        ids = out.get("retrieved_ids", [])
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            raise AgentCommandError('"retrieved_ids" must be a list of strings')
        return out["answer"], ids
