"""Facts a shortening may not destroy (G9).

The gap Eve's own documentation revealed. Its compaction *"resets
read-before-write tracking (so a write afterward re-reads the file whose read
evidence was summarized away) and re-injects the active todo list"*
(`docs/concepts/default-harness.md`). Two special cases, hardcoded, of one
general thing: **a fact the run established, which the messages that established
it no longer carry once those messages are summarised.**

`always-keep:` on a context policy pins MESSAGES, and that is not the same
mechanism. A recorded approval can be pinned because somebody said it. *"This
file was read at revision 41"* cannot, because it was never a message — it is
something the run came to know. Pinning cannot reach it, so before this module
a shortening silently destroyed the evidence a `policy:` depends on, and the
check that reads it afterwards passed on nothing at all.

**A check that passes because its evidence is gone is worse than a check that
fails.** That is the whole argument for this file.

Eve solves the two cases it happened to hit and says plainly that there is no
per-tool hook to configure, so the third case — whatever a particular author
needs to survive — has nowhere to go. Here the author declares it:
`survives-shortening: yes`, and `stops-being-true-when:` for when it goes stale.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping, Sequence

from .yes_no import said_yes

#: The label a re-stated fact carries, so a later tidy can tell one apart from
#: ordinary conversation and never summarise it back into prose.
FACT_LABEL = "a-fact-that-survives"


#: The one thing that makes a fact stale that a run can actually observe.
#:
#: `stops-being-true-when:` is `list of text` and the schema's own help offers
#: *"`the file changes` or `the turn ends`"* — but nothing in PACT watches files,
#: and a run is the only thing here that knows when a turn is over. An author who
#: writes a trigger nothing raises has a fact that never expires, and believes
#: otherwise, which is precisely the T7 breach the rest of this codebase reports
#: rather than swallows.
TURN_ENDS = "the turn ends"

#: Every sentence a run can raise. Closed, and small on purpose: a longer list
#: would be a promise to observe things nothing observes.
RAISED_BY_A_RUN: tuple[str, ...] = (TURN_ENDS,)


@dataclass(frozen=True)
class Fact:
    """One thing the run knows, declared to outlive the messages behind it."""

    name: str
    description: str
    #: Sentences from `stops-being-true-when:`. Matched by equality against what
    #: the run reports happening, not evaluated — a predicate language here
    #: would be a second way to say what `when-this` already says.
    stale_when: tuple[str, ...] = ()
    #: Whether `survives-shortening: yes` was written.
    #:
    #: It used to decide whether the fact was HELD at all, and that was this
    #: module reading its own name too narrowly. `remembers:` is the agent's
    #: memory; a summary destroying the messages behind one entry is what this
    #: flag is about, and every OTHER entry is still memory. Holding only the
    #: pinned ones meant `bind: remembers.x` had nothing to read and
    #: `remember-as:` had nowhere to write, on the two fields whose whole purpose
    #: is to make memory a thing the format can name.
    #:
    #: Defaults to True because a `Fact` built directly, rather than read off a
    #: document, is one somebody wrote out in order to pin it — which is what
    #: every such construction in this repository means. `from_document` always
    #: says which it is.
    survives: bool = True
    #: `lasts:` as written (`one-step`, `one-turn`, `one-conversation`,
    #: `forever`). Required by the schema, so a fact read off a document always
    #: says; one built directly lasts `forever`, the widest, so nothing is
    #: forgotten that its author did not say to forget.
    lasts: str = "forever"
    #: `forget-after:` as written (a duration such as `30d`), or `None`.
    forget_after: Any = None
    #: `starts-as:`: its value before anything has happened, or `None`.
    starts_as: Any = None
    #: `shaped-like:`: what a value must look like (the `takes:` vocabulary),
    #: or `None` for any text. A runtime holds a write to it.
    shaped_like: Mapping[str, Any] | None = None
    #: `never-from:`: the sources that may never write here (`tool output`,
    #: `retrieval`, `the customer`, `a teammate`). PACT carries the line; the
    #: system keeping the store refuses the write (the schema's own help).
    never_from: tuple[str, ...] = ()

    def said(self, value: Any) -> str:
        """How the fact reads once the messages behind it are gone.

        Written as a statement about the past rather than as an instruction: a
        re-stated fact is evidence, and evidence that reads like a command is
        how a summary becomes a prompt-injection surface.
        """
        return f"[recorded earlier] {self.description}: {value}"


@dataclass
class Facts:
    """Which facts survive a shortening, and what each is worth now."""

    declared: Mapping[str, Fact] = field(default_factory=dict)
    #: name → value, for facts this run has actually established.
    held: dict[str, Any] = field(default_factory=dict)
    #: Facts dropped because something in `stops-being-true-when:` happened.
    forgotten: list[str] = field(default_factory=list)

    @staticmethod
    def from_document(doc: Mapping[str, Any], agent_key: str) -> "Facts":
        """Read `remembers:` — every entry, and what each one asks for.

        It used to keep only the entries writing `survives-shortening: yes`, on
        the argument that anything else "is none of this module's business". That
        was true while this was only about a summary, and it stopped being true
        the moment `bind: remembers.<n>` and `remember-as:` existed: those read
        and write the agent's memory, and there was no memory here to read or
        write. One store, and the flag decides only what a shortening re-states.
        """
        agents = doc.get("agents") or {}
        return Facts.of((agents.get(agent_key) or {}).get("remembers"))

    @staticmethod
    def of(block: Any) -> "Facts":
        """One `remembers:` block, wherever it is written — an agent's, or a
        port's (`port.remembers:` is the same `map of group:state`, so it is
        read by the same reader and held to the same terms)."""
        block = block if isinstance(block, Mapping) else {}
        out: dict[str, Fact] = {}
        for name, raw in block.items():
            if not isinstance(raw, Mapping):
                continue
            stale = raw.get("stops-being-true-when") or []
            shaped = raw.get("shaped-like")
            out[str(name)] = Fact(
                name=str(name),
                description=str(raw.get("description") or name),
                stale_when=tuple(str(s) for s in stale),
                survives=said_yes(raw.get("survives-shortening")),
                lasts=str(raw.get("lasts") or "forever"),
                forget_after=raw.get("forget-after"),
                starts_as=raw.get("starts-as"),
                shaped_like=dict(shaped) if isinstance(shaped, Mapping) else None,
                never_from=tuple(str(s) for s in raw.get("never-from") or ()),
            )
        return Facts(declared=out)

    def fresh(self) -> "Facts":
        """The same declarations, nothing held: what one run starts from.

        `AgentSpec.facts` is one object per compiled agent, so a runtime that
        records into it shares one run's memory with every other run of that
        agent. A run takes its own copy here and records into that.
        """
        return Facts(declared=self.declared)

    def record(self, name: str, value: Any) -> None:
        """The run learned something. Silent for anything not declared: a fact
        nobody said should survive is not one this module may invent."""
        if name in self.declared:
            self.held[name] = value

    def forget(self, name: str) -> None:
        """The run was told to forget it (`forget`). Not stale, so not reported
        as `forgotten`: nothing that relied on it was surprised."""
        self.held.pop(name, None)

    def something_happened(self, what: str) -> list[str]:
        """Report an event; forget every fact that named it as making it stale.

        Returns what was forgotten, so the caller can say so rather than letting
        a rule quietly start reading nothing.
        """
        gone = [
            n for n, f in self.declared.items() if n in self.held and what in f.stale_when
        ]
        for n in gone:
            self.held.pop(n, None)
            if n not in self.forgotten:
                self.forgotten.append(n)
        return gone

    def value(self, name: str) -> Any:
        """What this run knows under that name, or nothing.

        The read half of the pair `record` is the write half of. Silent for a
        name nobody declared, for the same reason `record` is: a fact the author
        did not write down is not one this module may invent.
        """
        return self.held.get(name) if name in self.declared else None

    def surviving(self) -> list[tuple[Fact, Any]]:
        """The facts a shortening must re-state — the pinned ones alone.

        Filtered HERE rather than at the door, so ordinary memory is held without
        being pushed back into a summarised conversation. An entry that never
        said `survives-shortening: yes` is memory the author wanted kept, not
        evidence they wanted repeated.
        """
        return [
            (self.declared[n], v)
            for n, v in self.held.items()
            if n in self.declared and self.declared[n].survives
        ]

    def restated(self, make_message) -> list[Any]:
        """One message per surviving fact, for the tail of a shortened history.

        `make_message` is passed in rather than imported so this module does not
        depend on `context_policy`, which depends on nothing but itself and is
        the half that has to stay portable.
        """
        return [make_message(f.said(v), FACT_LABEL) for f, v in self.surviving()]

    def never_raised(self) -> list[str]:
        """Stale-triggers an author wrote that nothing here will ever raise.

        The other half of `stops-being-true-when:`, and the half that matters: a
        fact whose only trigger is `the file changes` never goes stale, because
        no part of PACT watches a file. Saying so is the difference between a
        line that does nothing and a line the author knows does nothing.

        Reported rather than refused at check time on purpose. The vocabulary is
        deliberately open — the schema's comment says a closed predicate language
        would mean *"an author who has to invent an expression to say so will
        write nothing"* — so a trigger PACT cannot raise today is a reasonable
        thing to have written, and may be raised by a host that knows more than
        the harness does.
        """
        out: list[str] = []
        for name, fact in self.declared.items():
            for said in fact.stale_when:
                if said in RAISED_BY_A_RUN:
                    continue
                out.append(
                    f"remembers.{name}.stops-being-true-when: `{said}` — nothing "
                    f"in a run raises that, so this fact never goes stale here. "
                    f"fix: use one of {', '.join(RAISED_BY_A_RUN)}, or have the "
                    f"system running this tell the run when it happens."
                )
        return out

    def unenforced(self) -> list[str]:
        """Sentences for `RunResult.unenforced` — what a rule can no longer read.

        A forgotten fact is reported rather than dropped for the reason the rest
        of this codebase reports rather than drops: an author who wrote a rule,
        got no enforcement and no word about it has been told something untrue.
        """
        return [
            f"the fact `{n}` was forgotten before the run finished, so any rule "
            f"that reads it decided on nothing. "
            f"fix: widen or remove its `stops-being-true-when:` line, or move the "
            f"rule earlier than the thing that makes it stale."
            for n in self.forgotten
        ]


