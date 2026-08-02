"""The event lattice — one address for everything that happens.

Eve publishes 28 lifecycle events as a flat closed union. Adding one means
editing the union, the channel subset, the hook map and the compiled manifest —
which is a large part of why that manifest is at schema version 36.

Those 28 events are not 28 unrelated things. They are a **scope × subject ×
phase** lattice:

    session ▸ turn ▸ step ▸ action        (scopes, strictly nested)
    requested → started → completed | failed | cancelled   (phases)
    message, reasoning, tool, approval, input, compaction, delegate (subjects)

Addressing them as `<scope>.<subject>.<phase>` means a new subject costs one
row rather than a new event family, and a listener can subscribe to a prefix
(`step.tool`) instead of enumerating members.

The other reason this matters: an **interceptor** attaches to the same address
an observer does, so "watch this" and "change this" agree on where *this* is.
Eve cannot express the second at all — its own source says handlers "are
observe-only. They cannot inject model context."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterator


class Scope(str, Enum):
    """Strictly nested. A step belongs to a turn, a turn to a session."""

    SESSION = "session"
    TURN = "turn"
    STEP = "step"
    ACTION = "action"


class Phase(str, Enum):
    REQUESTED = "requested"
    BEFORE = "before"
    STARTED = "started"
    AFTER = "after"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


#: Closed for now, open by construction: adding `retrieval` or `handoff` is one
#: entry, not a new event family. Author-defined subjects use an `x-` prefix and
#: are never confused with these.
SUBJECTS = (
    "message", "reasoning", "tool", "approval", "input",
    # `stage`, not `phase`. The schema group was called `phase` for a round
    # while its own help text, the worked example and every run-time message
    # said "stage", and the only place the other word ever surfaced was an
    # address an author might type. One thing, one name (D13).
    "compaction", "delegate", "model", "run", "stage",
    # A ceiling being reached (G2). The subject is the LIMIT and the phase is
    # what became of it: `completed` where a ceiling has been used up, `failed`
    # where one cannot be applied at all because nothing is counting. Adding it
    # cost this line, which is the lattice's whole claim — Eve's equivalent is
    # editing the union, the channel subset, the hook map and the manifest.
    "limit",
)


@dataclass(frozen=True)
class Address:
    """`<scope>.<subject>.<phase>` — where something happens."""

    scope: Scope
    subject: str
    phase: Phase

    def __str__(self) -> str:
        return f"{self.scope.value}.{self.subject}.{self.phase.value}"

    @staticmethod
    def parse(text: str) -> "Address":
        parts = text.strip().split(".")
        if len(parts) != 3:
            raise ValueError(
                f"{text!r} is not an event address; it should look like "
                f"'step.tool.before' — a part, a thing, and a moment"
            )
        scope, subject, phase = parts
        try:
            s = Scope(scope)
        except ValueError:
            raise ValueError(
                f"{scope!r} is not a part of a run. Use one of: "
                + ", ".join(x.value for x in Scope)
            ) from None
        try:
            p = Phase(phase)
        except ValueError:
            raise ValueError(
                f"{phase!r} is not a moment. Use one of: "
                + ", ".join(x.value for x in Phase)
            ) from None
        if subject not in SUBJECTS and not subject.startswith("x-"):
            raise ValueError(
                f"{subject!r} is not something that happens. Use one of: "
                + ", ".join(SUBJECTS)
                + " — or prefix your own with 'x-'."
            )
        return Address(s, subject, p)

    def matches(self, pattern: str) -> bool:
        """Prefix matching, so `step.tool` catches every phase of it.

        Subscribing to a prefix is what keeps a listener from having to
        enumerate phases it does not care about — the thing Eve's flat union
        makes impossible.
        """
        if pattern in ("*", ""):
            return True
        mine = str(self).split(".")
        theirs = pattern.strip().split(".")
        if len(theirs) > len(mine):
            return False
        return all(t in ("*", m) for t, m in zip(theirs, mine))


@dataclass
class Event:
    address: Address
    payload: dict[str, Any] = field(default_factory=dict)
    #: Where in the run this happened: session/turn/step indices. One address
    #: replaces the `{sequence, stepIndex, turnId}` triple Eve stamps on every
    #: content event.
    at: tuple[int, ...] = ()

    def __str__(self) -> str:
        return f"{self.address} {self.payload}"


Observer = Callable[[Event], None]


class Bus:
    """Delivers events to observers, in registration order.

    Deliberately synchronous and ordered: an observer that sees events out of
    order cannot reconstruct what happened, and reconstructing what happened is
    the whole reason the ledger exists.
    """

    def __init__(self) -> None:
        self._observers: list[tuple[str, Observer]] = []
        self.log: list[Event] = []

    def on(self, pattern: str, fn: Observer) -> None:
        self._observers.append((pattern, fn))

    def emit(self, address: str, at: tuple[int, ...] = (), **payload: Any) -> Event:
        event = Event(Address.parse(address), payload, at)
        self.log.append(event)
        for pattern, fn in self._observers:
            if event.address.matches(pattern):
                fn(event)
        return event

    def seen(self, pattern: str) -> Iterator[Event]:
        return (e for e in self.log if e.address.matches(pattern))
