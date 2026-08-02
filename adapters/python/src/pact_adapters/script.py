"""A deterministic scripted model.

Two things make this load-bearing rather than a testing convenience:

* **Air-gap (D17).** The whole pipeline must run with no network. A scripted
  model is the only way an eval suite is meaningful offline.
* **It isolates the variable.** A portability test that used a live model would
  measure sampling noise, not adapter fidelity. Driving both transports from the
  *same* script means any trace difference is the adapter's fault, which is
  precisely the claim under test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .harness import ToolCall


@dataclass
class Turn:
    text: str
    tool_calls: tuple[ToolCall, ...] = ()


class Script:
    """Replays a fixed sequence of model turns, and counts how often it is asked.

    The call count is part of the contract: a transport that calls the model a
    different number of times has changed the loop, even if the final text
    happens to match.
    """

    def __init__(self, turns: list[Turn]) -> None:
        self._turns = turns
        self.calls = 0

    def next_turn(self, history: list[dict[str, Any]]) -> Turn:
        """Select purely from `history`, never from `self.calls`.

        A counter cannot survive a process restart, so a counter-driven script
        replays turns that already happened and quietly breaks resume. Keying on
        the conversation makes the script behave the way a real model does:
        stateless, and a function of what it is shown.
        """
        turned = sum(1 for m in history if m.get("role") == "assistant")
        self.calls += 1
        return self._turns[min(turned, len(self._turns) - 1)]
