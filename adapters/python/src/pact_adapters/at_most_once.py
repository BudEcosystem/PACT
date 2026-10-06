"""At-most-once, from the author's own `same-request-key:` line.

`spec/schema.yaml`'s `action.same-request-key:` reads *"which argument makes two
calls 'the same call', so it runs once"*, and `spends-money:` beside it promises
*"the same refund cannot be paid twice"*. Half of that was true.

The **resolution** half shipped: `crates/pact-loader/src/money.rs` holds the
named argument against the action's `takes:` plus `bind:`, so
`same-request-key: ordr-number` is an error with a typeable fix. Its own
docstring says the rest out loud — *"Whether at-most-once is ENFORCED is a
separate, runtime question."*

The **runtime** half did not exist. Measured before this module:
`grep -rEn 'same-request-key|same_request_key' adapters/python/src` returned one
hit, a comment in `ir.py`, and nothing that enforced anything. A model that
called `payments/issue-refund` twice with the same `order-number` had the refund
issued twice, and `RunResult.unenforced` — the field this repository uses to say
*"you wrote a rule and this run could not apply it"* — was silent. So an author
who wrote the line was told nothing, which is the T7 mis-statement in its purest
form: the checker accepted the guarantee and the run did not keep it.

# What "the same call" means here

The record is keyed by **(tool, action, the value of the named argument)**,
which is the sentence the schema's help writes. All three parts matter:

* the **tool**, because two tools may both take an `order-number` and mean
  different things by it;
* the **action**, because `same-request-key:` is a field of an action —
  `look-up-order` and `issue-refund` may share `order-number` and only one of
  them must not happen twice;
* the **value**, because refunding `O-9` and refunding `O-14` are two calls.

# Claimed BEFORE the call, not after it

The key is spent when the call is let through, not when it comes back. That is
the difference between at-most-once and at-least-once: a payment call that timed
out may have moved the money anyway, so a ledger that only records successes
lets the retry through and pays twice — which is exactly the failure the field
exists to prevent. `_call_tool` turns a raised exception into `error: ...` data,
so "it failed" is a thing the model reads and can act on; "it may have happened"
is not a thing anything can tell.

The one call that is NOT let through is one there was nothing to call: a tool
the host never registered is answered `error: no tool named …` and cannot have
moved any money, so the harness asks nothing of this record for it. Spending a
key there would tell the model's retry that the refund "already ran in this
run", which is a sentence about something that never happened at all — the same
mis-statement this module exists to remove, pointing the other way.

# It withholds a call. It does not stop the run.

The refusal is handed back as the **result of the call the model asked for**,
in words a person can read, and the run carries on. That is the same shape a
tool the stage withholds, a call a person refused and a call a rule redirected
already have in `harness.py` — one more reason for `step.tool.cancelled`, not a
new kind of ending. Stopping the whole run instead would throw away the work of
every earlier step over a duplicate the model can simply be told about.

# What it deliberately will not guess

If the call carries no value for the named argument, nothing can tell two of
those calls apart — and treating "absent" as a value would make the first two
argument-less calls duplicates of each other, which is a refusal nobody asked
for. That case is reported on `RunResult.unenforced` with a line to type,
exactly as `Rule.decidable` reports an approval rule it cannot decide, rather
than guessed at in either direction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .questions import quoted

#: What `step.tool.cancelled` carries when a duplicate was withheld. One
#: spelling, because the event's `reason` is read by watches and by anyone
#: reconstructing a run, and two spellings of one outcome is how a reader comes
#: to count it twice.
WITHHELD = "the same request key was already used"


@dataclass(frozen=True)
class RequestKeys:
    """Which argument makes two calls to an action "the same call".

    One entry per `<tool>/<action>` that carries a `same-request-key:` line, plus
    every action name the tools have, which is what makes the fallback below
    safe rather than a guess.

    Read from the loaded document (invariant P-1: adapters consume `pact show`
    output, never author files) and narrowed to the tools the agent's own
    `uses:` line names — a tool no agent uses is never called, the same reason
    `money.rs` does not walk one.
    """

    #: `(tool, action) -> the argument that makes two calls one call`.
    keys: dict[tuple[str, str], str] = field(default_factory=dict)
    #: How far "the same call" reaches, per action, from
    #: `same-request-key-across:`. Absent means `this-run`, which is the only
    #: scope the reference harness enforces — `spent` is a dict built fresh in
    #: `run()` and restored from the parked suspension, so it survives a park
    #: and nothing wider.
    #:
    #: Carried so the REFUSAL can say which scope it is speaking about. It said
    #: "already ran in this run" whatever the author wrote, and on a workspace
    #: scope that sentence is false in the direction that matters: the call was
    #: made by another run, and telling somebody it was this one sends them
    #: looking through the wrong transcript.
    scopes: dict[tuple[str, str], str] = field(default_factory=dict)
    #: Every action each tool declares, keyed action names included, so
    #: "this tool has exactly one action" is answerable without re-reading the
    #: document. Only used to decide whether a call that named no action is
    #: unambiguous.
    actions: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.keys)

    @staticmethod
    def from_document(doc: Mapping[str, Any], agent_key: str) -> "RequestKeys":
        """The `same-request-key:` lines one agent can reach.

        Sorted, like `ir.py`'s `tools` and `skills`, so two readers in two
        languages never disagree about order.
        """
        agents = doc.get("agents") or {}
        agent = agents.get(agent_key) or {}
        used = set(_as_list(agent.get("uses")))
        keys: dict[tuple[str, str], str] = {}
        scopes: dict[tuple[str, str], str] = {}
        actions: dict[str, tuple[str, ...]] = {}
        for tool, spec in sorted((doc.get("tools") or {}).items()):
            if tool not in used or not isinstance(spec, Mapping):
                continue
            declared = spec.get("actions") or {}
            if not isinstance(declared, Mapping):
                continue
            actions[str(tool)] = tuple(sorted(str(a) for a in declared))
            for action, body in sorted(declared.items()):
                if not isinstance(body, Mapping):
                    continue
                named = str(body.get("same-request-key") or "").strip()
                if named:
                    keys[(str(tool), str(action))] = named
                    across = str(body.get("same-request-key-across") or "").strip()
                    if across:
                        scopes[(str(tool), str(action))] = across
        return RequestKeys(keys=keys, actions=actions, scopes=scopes)

    def action_of(self, tool: str, args: Mapping[str, Any]) -> str | None:
        """Which action this call names, or `None` when nothing can say.

        `ir.py`'s `_takes` offers `action: one of …` to the model whenever a tool
        has any actions at all, so a well-formed call names one. A call that does
        not is only resolved when the tool has **exactly one** action, where
        there is nothing to be ambiguous about.

        Deliberately narrower than `_bound_args`' fallback, which takes the
        single *bound* action when a call names none. The two are doing opposite
        things: that one ADDS an argument, and its worst case is a customer id
        reaching the wrong action; this one WITHHOLDS a call, and its worst case
        is a read refused because a sibling action moves money. Withholding on a
        guess is the wrong side to be wrong on.
        """
        named = str(args.get("action") or "").strip()
        if named:
            return named
        declared = self.actions.get(tool, ())
        return declared[0] if len(declared) == 1 else None

    def key_of(self, tool: str, args: Mapping[str, Any]) -> tuple[str, str] | None:
        """`(action, argument)` for a call that is held to at-most-once."""
        action = self.action_of(tool, args)
        if action is None:
            return None
        named = self.keys.get((tool, action))
        return None if named is None else (action, named)

    def claim(self, tool: str, args: Mapping[str, Any]) -> "Claim | None":
        """What this call would spend, or `None` when it is held to nothing.

        Pure: it reads the call and says what it is, and spends nothing. It is
        the half of `Ledger.hold` a runtime needs when the record of what was
        spent is not a dict in this process — a journal that outlives a crash,
        or a store shared by every run of a workspace, which is what
        `same-request-key-across:` wider than `this-run` asks for. The ledger
        and such a store then hold the same key and say the same sentence.
        """
        found = self.key_of(tool, args)
        if found is None:
            return None
        action, argument = found
        value = str(args[argument]).strip() if argument in args else None
        across = self.scopes.get((tool, action), "this-run")
        return Claim(tool=tool, action=action, argument=argument, value=value, across=across)


@dataclass(frozen=True)
class Claim:
    """One call's at-most-once key, how far it reaches, and its sentences.

    `value` is `None` when the call carries no value for the named argument:
    nothing can tell two such calls apart, so there is nothing to claim and
    `cannot_tell` says so (module docstring, "What it deliberately will not
    guess").
    """

    tool: str
    action: str
    argument: str
    value: str | None
    #: `same-request-key-across:` as written, `this-run` when it was not.
    across: str = "this-run"

    @property
    def key(self) -> tuple[str, str, str]:
        """`(tool, action, value)`: what "the same call" means (module docstring)."""
        return (self.tool, self.action, self.value or "")

    def cannot_tell(self) -> str:
        """The `RunResult.unenforced` sentence for a call with no key value."""
        where = f"{self.tool}/{self.action}"
        argument = self.argument
        return (
            f"same-request-key: {where} says two calls carrying the same "
            f"{argument!r} are one call, and this run called it with no "
            f"{argument!r} at all — so nothing could tell two of them apart "
            f"and the same call could be made twice. Add {argument!r} to "
            f"`takes:` on that action and make sure the call carries it, or "
            f"fill it from the surrounding system with "
            f"`bind: {{ {argument}: run-inputs.<name> }}`."
        )

    def refusal(self) -> str:
        """What the model is handed instead of a second call.

        The scope the AUTHOR wrote, not the one this process happens to keep.
        It said "already ran in this run" whatever they wrote, and on a
        workspace scope that is false in the direction that matters — the call
        was made by another run, and saying it was this one sends somebody
        looking through the wrong transcript for a payment that is not in it.
        """
        where_it_ran = {
            "the-team": "already ran, somewhere in this team,",
            "the-workspace": "already ran, somewhere in this workspace,",
        }.get(self.across, "already ran in this run")
        where = f"{self.tool}/{self.action}"
        return (
            f"not done: {where!r} {where_it_ran} with "
            f"{self.argument} {quoted(self.value or '')}, and its "
            f"`same-request-key: {self.argument}` makes two calls carrying the "
            f"same {self.argument} one call — so this one was withheld rather "
            f"than done a second time."
        )


@dataclass
class Ledger:
    """What this run has already spent, and what it therefore refuses.

    Mutable and per-run on purpose. `already` in `harness.py` is the same idea
    for one STEP and is cleared at the end of each one — see its own comment for
    what keeping it longer cost — so a second refund three steps later needed a
    record that outlives a step. This is that record, and it is keyed by the
    author's own argument rather than by the tool's name, which is why it can
    tell "refund `O-9` again" from "refund `O-14`".
    """

    keys: RequestKeys = field(default_factory=RequestKeys)
    #: `(tool, action, value)` for every call this run has let through.
    spent: dict[tuple[str, str, str], None] = field(default_factory=dict)
    #: One sentence per `<tool>/<action>` whose key could not be read off a
    #: call. Per action rather than per call: an author who left the argument
    #: out has one line to fix, not one per refund.
    cannot_tell: dict[tuple[str, str], str] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.keys)

    @staticmethod
    def resumed(
        keys: RequestKeys, spent: "tuple[tuple[str, str, str], ...] | None"
    ) -> "Ledger":
        """The ledger a parked run comes back with.

        A run cannot get a fresh at-most-once record by being interrupted, for
        the same reason `Meter.restored` exists one field along: the whole point
        of parking is that a person thinks while the process dies, and a refund
        approved before the park must not be issuable again after it.
        """
        return Ledger(keys=keys, spent={tuple(k): None for k in (spent or ())})

    def used(self) -> tuple[tuple[str, str, str], ...]:
        """The durable form — what to write down when a run parks."""
        return tuple(sorted(self.spent))

    def hold(self, tool: str, args: Mapping[str, Any]) -> str:
        """Claim this call's key, or say in words why it will not happen.

        Returns `""` when the call may run — including when the author wrote no
        `same-request-key:` for it, which is every call in a workspace that has
        not asked for this.

        One method rather than a `check` and a `record` pair, because the two
        must never be separable: a caller that checked and then forgot to record
        has an at-most-once guarantee that permits everything, and a caller that
        recorded without checking has one that refuses the first call. Claiming
        happens here, before the tool is reached — see the module docstring for
        why a call that failed still spends its key.
        """
        claim = self.keys.claim(tool, args)
        if claim is None:
            return ""
        if claim.value is None:
            # Nothing can tell two of these apart. Reported, not guessed at.
            self.cannot_tell.setdefault((tool, claim.action), claim.cannot_tell())
            return ""
        if claim.key in self.spent:
            return claim.refusal()
        self.spent[claim.key] = None
        return ""

    def look(self, tool: str, args: Mapping[str, Any]) -> str:
        """What `hold` would refuse this call with, spending nothing.

        `""` when the call could still run. Asked BEFORE a person is asked
        about a call: a key another call already spent means this one cannot
        happen whatever they answer, and asking them anyway is a false
        statement to the one reader whose time costs most. Measured on a live
        model that re-sent an approved purchase: one decision recorded once and
        approved four times, each yes answered with the refusal below.

        The key is still spent in one place only, `hold`, when a call is let
        through, so `hold`'s reason for being one method stands: a look that
        forgot to record has refused nothing it should not have, and permitted
        nothing, because it permits nothing.
        """
        claim = self.keys.claim(tool, args)
        if claim is None or claim.value is None or claim.key not in self.spent:
            return ""
        return claim.refusal()

    def unenforced(self) -> tuple[str, ...]:
        """Every `same-request-key:` line this run could not hold a call to.

        Sorted, so the same run reports the same sentences in the same order on
        every transport — `RunResult.unenforced` is read by the conformance
        driver and an order that depends on dictionary insertion is a divergence
        nobody wrote.
        """
        return tuple(self.cannot_tell[k] for k in sorted(self.cannot_tell))


def _as_list(value: Any) -> list[str]:
    """`uses:` as a list, whether it was written as one or not.

    A single name written without a dash is the same line with one entry, so
    both spellings are read — refusing the short one would be a rule about
    punctuation rather than about money. `money.rs`'s `uses()` says the same
    thing in Rust for the same field.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(x) for x in value]
    return []
