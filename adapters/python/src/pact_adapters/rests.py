"""A tool that keeps failing is rested for a while (docs/98 WP-13).

The Allowance primitive's revoke-for-a-period (`docs/97-PRIMITIVES.md` §5.4),
written `rests-after: 3` and `rests-for: 5m` on a tool: the agent circuit
breaker. After that many failures in a row, a call to the tool is not made —
the model is told the tool is resting and until when, so it can do something
else — and once the period has passed it is tried again. One success resets
the count.

A failure is what `harness._call_tool` already returns for one: text starting
`error:`. The record is per run unless the host passes one `Rests` to many runs,
which is how a tool that is down for everyone stays rested for everyone.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Mapping


@dataclass
class Rests:
    """Failures in a row, and rests, by tool."""

    failures: dict[str, int] = field(default_factory=dict)
    until: dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def resting(self, tool: str, now: float) -> float | None:
        """When `tool` may be tried again, if it is resting now; else `None`."""
        with self._lock:
            back = self.until.get(tool)
            if back is None or back <= now:
                return None
            return back

    def record(self, tool: str, failed: bool, now: float, rule: "tuple[int, float] | None") -> bool:
        """Count one call's outcome. True when this failure put the tool to rest."""
        with self._lock:
            if not failed:
                self.failures.pop(tool, None)
                return False
            n = self.failures.get(tool, 0) + 1
            self.failures[tool] = n
            if rule is not None and n >= rule[0]:
                self.until[tool] = now + rule[1]
                self.failures[tool] = 0
                return True
            return False


def rules_of(doc: Mapping, uses: "set[str]") -> dict[str, tuple[int, float]]:
    """`(rests-after, rests-for in seconds)` for each tool the agent uses that says both."""
    from .limits import seconds

    out: dict[str, tuple[int, float]] = {}
    for name, body in (doc.get("tools") or {}).items():
        if name not in uses or not isinstance(body, Mapping):
            continue
        after = body.get("rests-after")
        period = seconds(body.get("rests-for"))
        if after is None or period is None:
            continue
        try:
            out[str(name)] = (int(after), float(period))
        except (TypeError, ValueError):
            continue
    return out
