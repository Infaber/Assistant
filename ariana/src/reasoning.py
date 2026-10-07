"""Advisory reasoning boundary: plans are data, never executable permissions.

Extended Live is deliberately gated until interaction_status is supported end to
end. A future on-demand planner implements this protocol without access to tools.
The main assistant gathers facts and executes approved actions through normal tools.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ReasoningRequest:
    goal: str
    facts: tuple[str, ...]
    completed_steps: tuple[str, ...] = ()

    def __post_init__(self):
        if (
            len(self.goal) > 4000
            or len(self.facts) > 20
            or any(len(fact) > 2000 for fact in self.facts)
        ):
            raise ValueError(
                "Reasoning input is too large; summarize the relevant facts first."
            )


@dataclass(frozen=True)
class ReasoningAdvice:
    summary: str
    proposed_steps: tuple[str, ...]
    uncertainties: tuple[str, ...] = ()
    # No callable, credentials, tool handles, approval flag, or executable coordinates.


class AdvisoryPlanner(Protocol):
    async def advise(self, request: ReasoningRequest) -> ReasoningAdvice: ...
