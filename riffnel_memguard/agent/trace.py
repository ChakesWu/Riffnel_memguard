"""Turn one agent run into an incident (the TraceRecorder of the design)."""
from __future__ import annotations

from ..core.models import Incident


def capture(agent, question: str, scope: dict, occurred_at: str, incident_id: str, agent_id: str = "agent") -> Incident:
    """Run the agent once and record the question, answer and the memories it retrieved."""
    answer, retrieved = agent.answer(question, scope)
    return Incident(id=incident_id, occurred_at=occurred_at, agent_id=agent_id, scope=scope, question=question,
                    answer=answer, retrieved_ids=retrieved)
