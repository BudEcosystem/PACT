"""The team store: memory a lead shares with its team, behind an admission gate.

`docs/98-PRIMITIVES-ENGINEERING-PLAN.md` WP-8. A fact the lead remembers with
`shared-with: the-team` is offered to the lead and to every teammate as one
tool, named after the fact, with two actions:

* `read` — every entry written so far, oldest first, each with who wrote it;
* `write` — add one entry. It is written only if it fits `shaped-like:`, every
  `admitted-when:` line holds of it (read as `entry.<part>`), and the agent
  named by `admitted-by:` answers yes. A refusal is the tool's answer, so the
  writer is told why on its next turn.

What this is for: `docs/remediation/F7` refused a blackboard because "there is
nothing an agent can write that another agent can read". What this is careful
about: `docs/92-SWARM.md` §6.3 — "the accuracy lives in the admission gate, not
the queue". A store with no gate reproduces the systems that measured no
benefit, so the gate is not optional decoration: a fact with `admitted-by:` and
no judge to ask refuses every write (fail closed), and says so.

**Who runs the judge.** The admitting agent is a run like any other, and a run
needs a transport — the host's. So the host passes `admit=`: a callable given
the judge's name, the fact and the entry, returning `(yes, because)` — usually
by running the judge with the same `run` and reading its `yes or no` line.

**What the entries are.** One list per fact per request, kept in a `Board` the
root run creates and hands down to every teammate it starts, the way the
activation meter rides a grant. A host that wants the board to outlive the
request passes its own `Board`.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Mapping

from .conditions import ABSENT, all_hold
from .detectors import DECLARED

if TYPE_CHECKING:
    from .facts import Fact

#: `admit(judge, fact, entry) -> (yes, because)`.
Admit = Callable[[str, str, Mapping[str, Any]], "tuple[bool, str]"]


@dataclass
class Board:
    """Every entry written to each shared fact, in order."""

    entries: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def read(self, fact: str) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(e) for e in self.entries.get(fact, [])]

    def write(self, fact: str, entry: Mapping[str, Any], by: str) -> None:
        with self._lock:
            self.entries.setdefault(fact, []).append({"by": by, "entry": dict(entry)})


def _choices(written: str) -> list[str] | None:
    w = written.strip().removesuffix(", optional").strip()
    for prefix in ("one of ", "one-of ", "either "):
        if w.startswith(prefix):
            rest = w[len(prefix):].replace(" or ", ", ")
            return [c.strip() for c in rest.split(",") if c.strip()]
    return None


def misfits(shape: Mapping[str, Any] | None, entry: Mapping[str, Any]) -> list[str]:
    """What is wrong with `entry` against `shaped-like:`, in words. Empty: fits."""
    if not shape:
        return []
    said: list[str] = []
    for part in entry:
        if part not in shape:
            said.append(f"it has `{part}`, which this board does not keep")
    for part, written in shape.items():
        text = str(written)
        optional = text.strip().endswith(", optional")
        if part not in entry:
            if not optional:
                said.append(f"it has no `{part}`")
            continue
        allowed = _choices(text)
        if allowed is not None and str(entry[part]).strip() not in allowed:
            said.append(f"`{part}` is {entry[part]!r}, and must be one of {', '.join(allowed)}")
    return said


def tool_for(
    fact: "Fact",
    board: Board,
    writer: str,
    admit: Admit | None,
    detectors: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any], Callable[[dict[str, Any]], str]]:
    """The tool definition a model is offered for one shared fact, and its body."""
    definition = {
        "name": fact.name,
        "description": (
            f"the team's shared {fact.description}: `read` it, or `write` one entry to it"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["read", "write"]},
                "entry": {"type": "object"},
            },
            "required": ["action"],
        },
    }

    def call(args: dict[str, Any]) -> str:
        action = str(args.get("action") or "read").strip()
        if action == "read":
            return json.dumps(board.read(fact.name), ensure_ascii=False)
        if action != "write":
            return f"not done: {fact.name!r} can be read or written, not {action!r}"
        entry = args.get("entry")
        if isinstance(entry, str):
            try:
                entry = json.loads(entry)
            except ValueError:
                entry = None
        if not isinstance(entry, Mapping):
            return f"not written: an entry for {fact.name!r} is a set of named parts"
        wrong = misfits(fact.shaped_like, entry)
        if wrong:
            return f"not written to {fact.name!r}: " + "; ".join(wrong)
        if fact.admitted_when:

            def read(binding: str) -> Any:
                if binding.startswith("entry."):
                    return entry.get(binding[len("entry."):], ABSENT)
                return ABSENT

            known = DECLARED.set(dict(detectors or {}))
            try:
                held = all_hold(fact.admitted_when, read)
            finally:
                DECLARED.reset(known)
            if held is not True:
                why = "does not meet" if held is False else "cannot be checked against"
                return (
                    f"not written to {fact.name!r}: it {why} what this board admits "
                    f"({json.dumps(list(fact.admitted_when), ensure_ascii=False)})"
                )
        if fact.admitted_by:
            if admit is None:
                return (
                    f"not written to {fact.name!r}: every entry is read by "
                    f"{fact.admitted_by!r} first, and this run has nobody to ask it — "
                    f"refused rather than let in unread"
                )
            yes, because = admit(fact.admitted_by, fact.name, entry)
            if not yes:
                return (
                    f"not written to {fact.name!r}: {fact.admitted_by} said no"
                    + (f" — {because}" if because else "")
                )
        board.write(fact.name, entry, writer)
        return f"written to {fact.name!r}"

    return definition, call

