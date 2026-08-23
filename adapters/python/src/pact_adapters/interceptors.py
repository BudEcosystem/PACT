"""Interceptors — rules that may CHANGE what happens, not merely watch it.

Eve has 28 lifecycle events and every one is observe-only; its own source is
explicit: *"Handlers are observe-only. They cannot inject model context."* The
consequences are concrete — there is no way to redact a value before it reaches
the model, and no way to stop a tool call on a condition the approval rules
cannot express. Its only mutation point is a channel adapter rewriting an
*emitted event*, which is after the fact.

An interceptor attaches to the same address an observer does (see `events`), so
"watch this" and "change this" agree on where *this* is.

**Powers are declared and closed, and each one means one thing.** An interceptor
states what it `may` do and anything else is refused at load time. That is the
difference between a rule you can review and a callback that can do whatever it
likes — and it is what lets the blast-radius classifier (D23) reason about an
interceptor at all.

The three change-powers were enforced as one bit for a round: a change needed
*any* of `change-the-request | change-the-answer | hide-values`, and which one
was never asked, on the argument that the bound address bounds what a change can
reach. That argument held only while redaction reached a message's `content`.
A rule masking inside a tool call's `args` binds at `step.tool.before` — a
request-shaped address doing a hiding-shaped thing — so `Decision.by` names the
power and both checks read it.

# The authoring door, and why it is the only one that matters

For one round this module had two builders and both took programmer input: a
dict of Python regexes, and a Python callable. Nothing anywhere read the
`rules:` sentences an author actually writes, so
`examples/refund-desk/interceptors/redact-card-numbers.yaml` loaded, validated,
and let every card number through. That is the "experts write code for that"
answer D14 rules out for every capability in the core.

`Chain.from_document` is the fix and the door: it reads the agent's
`interceptors:` list, finds each document, and turns its `rules:` into a body
over a **closed sentence vocabulary** — five forms, listed in the
`interceptor.rules` help text in `spec/schema.yaml`, which is where the list is
maintained. A sentence outside the vocabulary is REFUSED by name rather than
loaded and ignored, because a rule that validates and does nothing is worse than
one that fails: the author believes they are protected.

# The same objection, one level up: a POWER that does nothing

`send-elsewhere` spent a round declarable and enforced and inert. The power was
refused when undeclared and the chain short-circuited on a redirect, so nothing
unsound could happen — but no sentence produced one and no address acted on one,
so an interceptor declaring it changed nothing. That is the "loads and does
nothing" failure wearing a different hat, and it is why two things landed
together: the fourth sentence form, which is the only way an author can ever ask
for a redirect, and a table of the addresses where one is carried out. A redirect
sentence bound anywhere else is refused at load with the address to type.

# One question, asked once: `WIRED`

Then the same objection arrived a third time, because that table was built for
redirects alone. `hide-values` was checked against the address's SUBJECT, which
let five addresses the harness never emits through — a card-number rule bound at
`step.tool.completed` loaded cleanly and masked nothing. The two counting
sentences had no check at all, so `stop and say "…"` bound at
`turn.message.after` saw a payload with neither `name` nor `so-far` and answered
"no" forever, while its twin — same counter, same condition — was checked.

Three powers asking one question in three places is how they came to disagree, so
there is one table now (`WIRED`) saying what each address carries, and three
readings of it. The next address the harness binds is one row.

# And a power that no sentence reaches

`change-the-request` and `change-the-answer` were two of five choices in `may:`
and no form in the vocabulary produces either — every one of them hides, stops,
or sends the run elsewhere. So an author could type one and then be refused by
every rule they wrote. They are out of the authoring surface (`AUTHORABLE`) and
recorded in `docs/50-NOT-COPIED.md` §6 with the sentence that would let them back
in; they stay in `Power` because the typed escape §5.5 requires still produces
them. A choice nothing can exercise reads as a capability, which is the same
deception as a rule that loads and does nothing.

# And the ORDER they run in, which used to be the filename's

Three lines above `sorted(declared.items())` this file said *"Order matters: the
chain threads each change into the next, and a redaction that runs after a guard
has read the value has redacted nothing"* — and then sorted the workspace-wide
rules by name. Measured: an `aaa-hide.yaml` ran before
`redact-card-numbers-in-tool-calls` and the same file renamed `zzz-hide.yaml` ran
after it. A safety property decided by a filename, with no line an author could
type to say otherwise, which is exactly the "significant ordering game" D18
forbids.

`runs-at:` is that line, and `order_for` is what makes it one a support lead (D13)
almost never has to write: leaving it out puts a rule that HIDES values ahead of
every rule that does not, so the sentence the help text makes — *hiding runs
before reading* — is what you get for writing nothing, rather than what you get
when the alphabet agrees.

Where the alphabet would still be deciding something that matters, the chain is
refused instead of guessed at. `Chain.run` returns at the first stop or redirect,
so a rule that can END the chain running in front of one that hides values does
not delay the hiding, it deletes it — and the harness writes what the chain left
into the record on that path, with its own comment saying a value that must not
survive in the record must not survive where the tool never even ran. That pair
has to state its order (`_hiding_runs_first`).

# TWO VOCABULARIES FOR ONE ACT, and the field neither of them read

`redaction.hide` said the same thing this module's `rules:` says — take this out
before it leaves — in its own separate closed list, and each list was missing
what the other had. Measured on the shipped tree, three files apart, mirrored:
`anything that looks like a card number` (every line of `redaction.yaml`) was
refused under `rules:`, and `replace anything that looks like a card number with
"[card number removed]"` (the shipped interceptor's own line) was refused under
`hide:`. An author who learned one spelling had learned nothing about the other.

They are ONE list now, shared by the `&the-hiding-sentences` anchor in
`spec/schema.yaml`, so the next sentence added is added to both by construction.
`_BARE` is the form this side gained; `_REPLACE` and `_SAME` are the two the
other side gained. What they do not share is what each file MAY do: an
interceptor says so under `may:`, a redaction hides and does nothing else, and
the two counting sentences are therefore refused there — by `always-may:` on the
checking side and by `fixed_powers` here, with the sentences that DO work printed
under the refusal, because a redaction has no `may:` line and "add one" is a fix
nobody can type.

The merge turned up the larger defect. **`redaction.hide` was read by nobody.**
It was in the schema, was `required:`, was resolved by the loader and printed by
`pact show`, and appeared in no source file in either language — so the worked
example's own *"an email address must never leave this workspace"* hid no email
address anywhere, on any agent, in any run. `Interceptor.from_redaction` and the
one line in `Chain.from_document` that calls it are the door, and the floor they
build is bound to every moment that carries values: "must never leave" is not a
statement about one point in a run, and asking a support lead which of the three
they meant is asking the wrong person a question with one right answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .diagnostics import locate

#: How much of a rule to look for when finding the line it was written on.
#: Enough to be unique in a file, short enough to survive the line breaks a
#: folded scalar puts in — and every long rule in the worked example is a folded
#: scalar, because that is what a readable YAML file looks like.
NEEDLE = 40


#: The name the workspace's own redaction runs under in a chain.
#:
#: It has spaces in it, and that is deliberate: an entry under `interceptors/` is
#: named by its file stem, so no interceptor an author writes can collide with
#: this one and be sent to the wrong file by the two helpers below.
REDACTION = "the workspace redaction"


def _at(source: "Path | None", name: str, phrase: str) -> tuple[str, int]:
    """The file and line one rule was written on, for either kind of document.

    The workspace redaction is written in `redaction.yaml` at the top of the
    tree — the Expansion Rule makes that file the workspace's `redaction:`
    setting, the way `learning.yaml` is its `learning:`. Sending its author to
    `interceptors/…` would be the synthesised path this module already got
    caught doing once, one kind over.
    """
    if name == REDACTION:
        return locate(source, ".", "redaction", "redaction", phrase[:NEEDLE])
    return locate(source, "interceptors", "interceptor", name, phrase[:NEEDLE])


def _where(source: "Path | None", name: str, phrase: str) -> str:
    """`interceptors/x.yaml:14` — the file and line, never a synthesised path.

    Named once because eight messages print it, and for a round each of them
    printed `f"interceptors/{name}.yaml"` instead: a path built out of the entry
    name, which is wrong for every interceptor written as a folder and carries
    no line for any of them.
    """
    file, line = _at(source, name, phrase)
    return f"{file}:{line}"


class Power(str, Enum):
    """What an interceptor is allowed to do. Closed on purpose."""

    CHANGE_REQUEST = "change-the-request"
    CHANGE_ANSWER = "change-the-answer"
    HIDE_VALUES = "hide-values"
    STOP = "stop-the-run"
    REDIRECT = "send-elsewhere"


#: The powers an author may write under `may:`, which is not all of them.
#:
#: No sentence in the closed vocabulary rewrites — every one of them hides,
#: stops, or sends the run elsewhere — so `change-the-request` and
#: `change-the-answer` were choices a non-coder could type and nothing could
#: ever reach: the rule they declared them for was refused by the next check
#: down. They are gone from `interceptor.may` in `spec/schema.yaml` and recorded
#: in `docs/50-NOT-COPIED.md` §6 as host-only, and they stay in `Power` because
#: the typed escape §5.5 requires can still produce one from a host's own
#: process. A choice no YAML can exercise is worse than an absent one: it reads
#: as a capability.
AUTHORABLE: frozenset[Power] = frozenset(
    {
        Power.HIDE_VALUES,
        Power.STOP,
        Power.REDIRECT,
        # BACK, because a sentence reaches them now. R24's argument was that a
        # choice nothing can exercise reads as a capability; the two rewriting
        # sentences added to `forms:` exercise these, so the same argument puts
        # them back. What made the sentence writable is the `program` kind: §6's
        # worry was that a mid-run rewrite is not reviewable the way
        # `instructions:` is, and a carried program is — a file in the folder,
        # fingerprinted, declared, and refused unless it is `pure`.
        Power.CHANGE_ANSWER,
        Power.CHANGE_REQUEST,
    }
)

#: The powers that END a chain. `Chain.run` returns at the first stop or
#: redirect, so nothing bound after one of these at the same moment runs at all —
#: which is why the order between one of these and a `hide-values` rule is a
#: safety property and not a preference.
ENDS_THE_CHAIN: frozenset[Power] = frozenset({Power.STOP, Power.REDIRECT})

#: Where a rule runs when its author wrote no `runs-at:` line, in two bands.
#:
#: A rule that HIDES a value has to run before any rule that reads it, and until
#: `runs-at:` existed that held only where the alphabet happened to agree — an
#: `aaa-hide.yaml` ran before the worked example's card rule and the same file
#: renamed `zzz-hide.yaml` ran after it. Making the safe order the DEFAULT is
#: what keeps a support lead (D13) from having to reason about ordering at all:
#: writing nothing gets you hiding-before-reading, and the number is for the
#: rarer case where you want something else.
#:
#: Ten and fifty rather than one and two, and they are the numbers the help text
#: prints: gaps leave room to put a rule between two others without renumbering
#: everything around it.
HIDING_RUNS_AT = 10
EVERYTHING_ELSE_RUNS_AT = 50

#: Where the workspace's own `redaction.yaml` runs: AFTER the rules an agent's
#: author wrote, and before anything that can end the chain.
#:
#: Last among the hiders because a floor is a backstop, not an override. The
#: worked example writes `replace anything that looks like a card number with
#: "[card number removed]"` in an interceptor and `anything that looks like a
#: card number` in `redaction.yaml`; run the floor first and the author's chosen
#: words never appear, so a rule they wrote and can read becomes one that loads
#: and does nothing. Run it last and both are true — their words where their rule
#: matched, `[removed]` everywhere else it did not.
#:
#: Still ahead of `EVERYTHING_ELSE_RUNS_AT`, because `Chain.run` returns at the
#: first stop or redirect: a floor behind a guard is not a delayed floor, it is
#: no floor at all, and that is the pairing `_hiding_runs_first` refuses.
REDACTION_RUNS_AT = 20



def order_for(may: frozenset[Power]) -> int:
    """Which band a rule with these powers runs in when it names no number."""
    return HIDING_RUNS_AT if Power.HIDE_VALUES in may else EVERYTHING_ELSE_RUNS_AT


class Refused(RuntimeError):
    """An interceptor tried to do something it did not declare."""


@dataclass
class Runner:
    """The host's program runner, in a box a chain can be handed one of later.

    A `Chain` is built by `AgentSpec.from_document`, which is handed a loaded
    document and nothing else (invariant P-1) — no runner exists at that moment,
    because running a carried body is the host's and the host arrives at `run()`.
    The runner used to be closed over at build time, so through the shipped entry
    point a rewriting rule never rewrote anything: measured, `run(...,
    run_program=shout)` returned the words unchanged and `RunResult.unenforced`
    was empty, while the chain object nobody could see held the sentence saying
    why.

    A box rather than a rebuilt chain, because rebuilding would need the document
    the spec no longer carries, and because every rule in one chain shares one
    runner by construction this way.
    """

    call: "Callable[[str, dict[str, Any]], str] | None" = None


class InterceptorError(ValueError):
    """An authoring mistake in an interceptor document.

    Raised rather than absorbed, and for the same reason `LoopError` is: a rule
    nobody can carry out has no defensible fallback, and the only fallback
    available — ignore it — is the failure this module exists to remove. Every
    message names the file, which rule it is, what is wrong, and a line to type.
    """


#: How each power reads in a sentence, so a refusal says what was attempted in
#: the words the author used rather than in an enum name. One table rather than
#: a string written out at each check — the three used to disagree in tone.
SAYS: Mapping[Power, str] = {
    Power.CHANGE_REQUEST: "change the request",
    Power.CHANGE_ANSWER: "change the answer",
    Power.HIDE_VALUES: "hide values",
    Power.STOP: "stop the run",
    Power.REDIRECT: "send the run elsewhere",
}

#: The same five, said of a rule rather than of an attempt — "this rule hides
#: values" against "tried to hide values". Two tables because English needs two
#: and one table used with the wrong grammar reads as a bug in the tool, which is
#: the last thing an author meeting a refusal should be wondering about.
DOES: Mapping[Power, str] = {
    Power.CHANGE_REQUEST: "changes the request",
    Power.CHANGE_ANSWER: "changes the answer",
    Power.HIDE_VALUES: "hides values",
    Power.STOP: "stops the run",
    Power.REDIRECT: "sends the run to another stage",
}


@dataclass
class Decision:
    """What an interceptor did. `None` fields mean "left alone"."""

    changed: dict[str, Any] | None = None
    stop: str | None = None
    redirect: str | None = None
    #: WHICH change power a `changed` used. Required whenever `changed` is set.
    #:
    #: For a round the three change-powers were enforced as one bit: a change
    #: needed *any* of `change-the-request | change-the-answer | hide-values`,
    #: and which one was never asked. The justification was that the bound
    #: address bounds what a change can reach — true only while redaction
    #: reached a message's `content` and nothing else. A rule that masks inside
    #: a tool call's `args` is bound at `step.tool.before`, a request-shaped
    #: address, so the address no longer says which power is in play and the
    #: decision has to.
    by: Power | None = None

    @property
    def is_noop(self) -> bool:
        return self.changed is None and self.stop is None and self.redirect is None


#: An interceptor body: sees the payload, returns what to change.
Body = Callable[[dict[str, Any]], Decision]


@dataclass
class Interceptor:
    name: str
    #: The event addresses (or prefixes) this runs at — ALWAYS a tuple, even
    #: when the author wrote one line.
    #:
    #: It held a single string for a round, so a rule that had to run at two
    #: moments had to be written twice, and the worked example shipped the
    #: proof: `redact-card-numbers.yaml` and
    #: `redact-card-numbers-in-tool-calls.yaml` differed in `description:` and
    #: `when:` and in nothing else — same powers, same scope, the same two
    #: sentences copied out. Two copies of one rule is two places to add the
    #: next thing that must be hidden and two places for them to disagree.
    when: tuple[str, ...]
    may: frozenset[Power]
    body: Body
    description: str = ""
    #: The stages this interceptor's redirect sentences name. Carried so the
    #: harness can hold them against the loop before the first model call —
    #: `Loop.check_against` sets that standard for `may-use:` in its own
    #: docstring, and a redirect destination is by construction the rarely-taken
    #: branch it describes.
    goes_to: frozenset[str] = frozenset()
    #: What the author wrote under `runs-at:`, and `None` when they wrote
    #: nothing. Kept exactly as written rather than filled in on the way past,
    #: because `_hiding_runs_first` has to be able to tell an order that was
    #: STATED from one that fell out of which file was read first.
    runs_at: int | None = None

    def __post_init__(self) -> None:
        """One address written as one string is the one-element tuple it means.

        Here rather than only in `from_document`, because a string is itself
        iterable: `any(addr.matches(w) for w in "step.tool.before")` asks about
        nineteen single characters, matches none of them, and silently binds the
        rule to nothing. A host constructing one directly (§5.5) must not be able
        to reach that by writing the obvious thing.
        """
        if isinstance(self.when, str):
            self.when = (self.when,)
        else:
            self.when = tuple(self.when)

    @property
    def order(self) -> int:
        """Where this rule sits among the rules at the same moment.

        The author's own number when there is one, and the band its powers put
        it in when there is not — see `order_for`. Lower runs first.
        """
        return order_for(self.may) if self.runs_at is None else self.runs_at

    def apply(self, payload: dict[str, Any]) -> Decision:
        """Run it, then check it stayed inside its declared powers.

        Checked *after* rather than trusted before, because a declaration that
        is never verified is documentation, not a control.
        """
        decision = self.body(dict(payload))

        if decision.stop is not None and Power.STOP not in self.may:
            raise Refused(
                f"'{self.name}' tried to {SAYS[Power.STOP]}, but it may only "
                f"{self._powers()}"
            )
        if decision.redirect is not None and Power.REDIRECT not in self.may:
            raise Refused(
                f"'{self.name}' tried to {SAYS[Power.REDIRECT]}, but it may only "
                f"{self._powers()}"
            )
        if decision.changed is not None:
            # Which of the three, not whether any of the three. A change that
            # will not say which power it used cannot be checked against `may:`
            # at all, so it is refused rather than waved through against the
            # union — waving it through is the one-bit enforcement this replaces.
            if decision.by is None:
                raise Refused(
                    f"'{self.name}' changed values without saying which power it "
                    f"used, so nothing can hold it to what it may do. Fix: return "
                    f"`Decision(changed=..., by=Power.HIDE_VALUES)` — or "
                    f"`Power.CHANGE_REQUEST` / `Power.CHANGE_ANSWER`, whichever "
                    f"it is."
                )
            if decision.by not in self.may:
                raise Refused(
                    f"'{self.name}' tried to {SAYS[decision.by]}, but it may only "
                    f"{self._powers()}"
                )
        return decision

    def _powers(self) -> str:
        return ", ".join(sorted(p.value for p in self.may)) or "do nothing"

    # ------------------------------------------------------------ from config

    @staticmethod
    def from_document(
        name: str,
        raw: Mapping[str, Any],
        source: "Path | None" = None,
        programs: "Mapping[str, Any] | None" = None,
        run_program: "Callable[[str, dict[str, Any]], str] | None" = None,
        runner: "Runner | None" = None,
        unenforced: "list[str] | None" = None,
    ) -> "Interceptor":
        """Build one from the document shape — `when`, `may`, `rules`.

        This is the only path in. There is deliberately no privileged builder
        beside it: an interceptor PACT ships would otherwise be one an author
        cannot fork, which is the same objection this project makes to Eve's
        compiled manifest.

        `source` is the workspace root, and it is what turns every message below
        from a guess into a location. Without it the file is named and the line
        is 1; with it the file is the one on disk — including the folder
        spelling, `interceptors/<name>/interceptor.yaml`, which the synthesised
        path `interceptors/<name>.yaml` never matched.
        """
        where = _where(source, name, "")
        if not isinstance(raw, Mapping):
            raise InterceptorError(
                f"{where}: this should be a set of settings, not "
                f"{type(raw).__name__}. Fix: write it as `when:`, `may:` and "
                f"`rules:` lines."
            )

        # A list, and a bare address is the one-element list it means. The
        # schema says the same (`type: list of event-address`), so an author who
        # writes one moment never learns there is a list, and an author whose
        # rule needs two moments adds a line instead of a file.
        when = tuple(a for a in (s.strip() for s in _as_list(raw.get("when"))) if a)
        if not when:
            raise InterceptorError(
                f"{where}: this rule does not say when it runs. "
                f"Fix: add a line `when: step.message.before` — a part of the "
                f"run, a thing that happens, and a moment. Write more than one "
                f"with a `- ` in front of each."
            )
        for address in when:
            _check_address(_where(source, name, address), address)

        may = _powers(_where(source, name, "may:"), raw.get("may"))
        rules = _rule_list(where, raw.get("rules"))
        body, goes_to = _compile_rules(
            source, name, rules, when, may,
            programs=programs,
            runner=runner if runner is not None else Runner(run_program),
            unenforced=unenforced,
        )

        return Interceptor(
            name=name,
            when=when,
            may=may,
            body=body,
            description=str(raw.get("description") or "").strip(),
            goes_to=goes_to,
            # The line that made the order the author's rather than the
            # filesystem's. Read here and nowhere else, so there is one place
            # that decides what an unwritten `runs-at:` means.
            runs_at=_runs_at(_where(source, name, "runs-at"), raw.get("runs-at")),
        )

    @staticmethod
    def from_redaction(
        raw: Mapping[str, Any], source: "Path | None" = None
    ) -> "Interceptor | None":
        """The workspace's own `redaction.yaml`, as the rule it always described.

        **This is not a privileged builder beside `from_document`** — the two
        read two files an author writes, through one sentence compiler, and
        neither can do anything the other's file could not say. What it is, is
        the line that was missing: `redaction.hide` was in the schema, was
        `required:`, was resolved out of the tree by the loader and printed by
        `pact show`, and appeared in **no** source file in either language. The
        worked example's own `redaction.yaml` says an email address must never
        leave this workspace, and nothing hid one anywhere. That is this
        project's most-repeated defect — an authoring field added, resolved, and
        read by nobody — on the surface where the cost is somebody's personal
        details in a transcript.

        A redaction is bound to every moment that carries values rather than to a
        moment the author picks, because "must never leave" is not a statement
        about one point in a run: the same email address leaves through the model
        call, through a tool argument and through the reply, and asking a support
        lead which of the three they meant is asking the wrong person a question
        with only one right answer.

        `None` when the workspace has no redaction, which is the honest default —
        a run with no floor is byte-identical to one before this existed.
        """
        if not isinstance(raw, Mapping):
            return None
        hide = _as_list(raw.get("hide"))
        if not hide:
            return None
        # Fixed, not read: `redaction.yaml` has no `may:` line and should not —
        # it hides, and a required list with one thing to say is the R58 shape.
        # `always-may: [hide-values]` in `spec/schema.yaml` is the same statement
        # on the checking side, and it is what stops the shared vocabulary
        # handing this file two sentences it cannot perform.
        may = frozenset({Power.HIDE_VALUES})
        body, goes_to = _compile_rules(
            source,
            REDACTION,
            hide,
            HIDES_AT,
            may,
            where="a redaction",
            fixed_powers=True,
        )
        return Interceptor(
            name=REDACTION,
            when=HIDES_AT,
            may=may,
            body=body,
            description=str(raw.get("description") or "").strip(),
            goes_to=goes_to,
            runs_at=REDACTION_RUNS_AT,
        )


@dataclass
class Chain:
    """The interceptors registered for a run, applied in the order they say."""

    interceptors: list[Interceptor] = field(default_factory=list)
    #: What the rules in this chain could NOT do, in sentences (P8 wave 6).
    #:
    #: A rewriting rule with nothing to run its program leaves the words exactly
    #: as they were and records why here, so the run can report it. Silently
    #: passing the words through would leave the author believing their program
    #: had run — the "loads and does nothing" failure this whole vocabulary
    #: exists to refuse, one level up.
    unenforced: list[str] = field(default_factory=list)
    #: The host's program runner, shared by every rule in this chain.
    #:
    #: Set at build time when a caller has one, and set again by
    #: [`Chain.use_runner`] at the start of a run — which is the only moment a
    #: host's runner exists, and the moment the chain was never handed one.
    runner: Runner = field(default_factory=Runner)

    def use_runner(self, run_program: "Callable[[str, dict[str, Any]], str] | None") -> None:
        """Hand this chain the host's program runner, at the start of a run.

        `AgentSpec.from_document` builds the chain from a loaded document and has
        no runner to give it; `run()` had one and never passed it on. So a
        rewriting rule — the whole of what §8.5 gave back to authors — never
        rewrote anything through the shipped entry point, and the sentence the
        chain recorded about it reached nobody.
        """
        if run_program is not None:
            self.runner.call = run_program

    def add(self, i: Interceptor) -> None:
        """Put it where it RUNS, not where it arrived.

        Sorted on every add rather than once at the end, so `run`, `at` and
        anyone reading `interceptors` all see the one order the run will really
        use. The list was in arrival order, and arrival order for the
        workspace-wide rules was `sorted(declared.items())` — the FILENAMES —
        three lines under a comment calling that order load-bearing.

        The sort is stable and the key is the NUMBER alone. Adding the name to
        the key would hand the alphabet the one ordering signal an author
        already controls — the order they wrote their own `interceptors:` list
        in — which is the thing this field exists to take away from it. Equal
        numbers therefore mean *"whichever, I do not mind"*; where not minding
        would be unsafe, `_hiding_runs_first` refuses the chain rather than
        picking for them.
        """
        self.interceptors.append(i)
        self.interceptors.sort(key=lambda x: x.order)

    def at(self, address: str) -> list[Interceptor]:
        """The rules bound to this moment — by ANY of the moments each names.

        This is the line the author's second `when:` entry reaches. It read
        `addr.matches(i.when)` against a single string for a round, which is
        why `redact-card-numbers-in-tool-calls.yaml` had to exist: the only way
        to be at two moments was to be two files.
        """
        from .events import Address

        addr = Address.parse(address)
        return [i for i in self.interceptors if any(addr.matches(w) for w in i.when)]

    def destinations(self) -> frozenset[str]:
        """Every stage this chain's redirect rules can send a run to.

        Exposed so the harness can hold them against the loop **before the first
        model call**, through `Loop.phase` — the same door and the same
        diagnostic a misspelled destination met when the rule fired. That is the
        standard `Loop.check_against` sets in its own docstring: *"a typo in a
        rarely-taken branch fails at the start of the run instead of forty steps
        in"*. A redirect destination is by construction a rarely-taken branch,
        and it was the one thing exempt from it — an author with a typo shipped
        it and met it on the second refund, after a real one had been issued.
        """
        return frozenset(name for i in self.interceptors for name in i.goes_to)

    def run(self, address: str, payload: dict[str, Any]) -> tuple[dict[str, Any], Decision]:
        """Apply every interceptor at `address`, threading changes through.

        Stops at the first `stop` or `redirect` — a run that has been halted
        must not then be quietly modified by a later rule, because the audit
        trail would show a change to something that never happened.
        """
        current = dict(payload)
        rewrote = False
        for i in self.at(address):
            decision = i.apply(current)
            if decision.stop is not None or decision.redirect is not None:
                return current, decision
            if decision.changed is not None:
                current = decision.changed
            if decision.by in (Power.CHANGE_ANSWER, Power.CHANGE_REQUEST):
                rewrote = True
        # THE FLOOR IS WHAT THE WORDS MEET LAST, when something rewrote them.
        #
        # Putting rewriting before hiding inside one document's body fixed one
        # shape and left the commoner one: the hiding is `redaction.yaml` and the
        # rewrite is an interceptor, so they are separate rules in this list. The
        # floor runs FIRST and has to — `_hiding_runs_first` refuses any other
        # order, because a guard that reads a value must never see an unmasked
        # one — and a rewriter after it introduced a card number that nothing
        # masked. Measured, on two files an author would ordinarily write: the
        # whole number came out.
        #
        # So the floor is applied once more, and only when the words really
        # changed under it: a chain that hides and does nothing else is
        # byte-identical to what it was. `redaction.yaml`'s promise is "what must
        # never leave this workspace", and a floor that the last rule can step
        # over is not one.
        if rewrote:
            for i in self.at(address):
                if i.name != REDACTION:
                    continue
                again = i.apply(current)
                if again.changed is not None:
                    current = again.changed
        return current, Decision()

    @staticmethod
    def from_document(
        doc: Mapping[str, Any],
        agent_key: str,
        source: "Path | None" = None,
        run_program: "Callable[[str, dict[str, Any]], str] | None" = None,
    ) -> "Chain":
        """Every rule that covers one agent, in the order those rules state.

        Order is the author's — through `runs-at:`, which is a line they can
        type. It used to be the filesystem's: the chain threads each change into
        the next and a redaction that runs after a guard has read the value has
        redacted nothing, and which of two workspace-wide rules went first was
        decided by `sorted(declared.items())`, three lines under the comment
        saying so.

        `source` is the workspace root and is optional for the same reason
        `ContextPolicy.from_document`'s is: an adapter is handed a loaded
        document (invariant P-1) and may not have the tree. Given one, every
        diagnostic below names a real file and a real line.
        """
        agents = doc.get("agents") or {}
        agent = agents.get(agent_key) or {}
        declared = doc.get("interceptors") or {}
        chain = Chain()
        # ONE box, shared by every rule this chain builds, so `use_runner` at the
        # start of a run reaches all of them.
        chain.runner = Runner(run_program)
        # THE LINE THAT READS `redaction.yaml`. Without it that file was in the
        # schema, `required:`, resolved by the loader, printed by `pact show` and
        # read by nothing in either language — so the worked example's own
        # "an email address must never leave this workspace" hid no email address
        # anywhere, on any agent, in any run. Here rather than in `run()` because
        # it belongs to the same chain the agent's own rules do: what must never
        # leave is a floor UNDER them, not a second mechanism beside them, and one
        # chain is what lets `runs-at:` order the floor against them.
        floor = Interceptor.from_redaction(doc.get("redaction") or {}, source)
        if floor is not None:
            chain.add(floor)
        # Workspace-wide rules FIRST, then the ones this agent named.
        #
        # `applies-to: every-agent` is on the rule rather than on a second
        # binding field, because a rule that must cover everything is a property
        # of the rule. Redaction used to be opt-in per agent while watching —
        # which can do nothing — was workspace-wide, so the worked example's two
        # card-number rules covered one of its three agents and the other two
        # read customer tickets with no redaction at all. The agent that forgets
        # to list it is the one that leaks.
        #
        # An agent's own list ADDS rather than replaces, so nobody can drop a
        # workspace rule by writing a line. Order matters: the chain threads each
        # change into the next, and a redaction that runs after a guard has read
        # the value has redacted nothing — so `Chain.add` puts each rule where
        # its `runs-at:` says rather than where it arrived. Adding the
        # workspace-wide ones first therefore no longer DECIDES anything; it only
        # settles rules whose numbers are equal, and where equal would be unsafe
        # the chain is refused below.
        everywhere = [
            name
            for name, entry in sorted(declared.items())
            if isinstance(entry, Mapping)
            and str(entry.get("applies-to") or "").strip() == "every-agent"
        ]
        named = _as_list(agent.get("interceptors"))
        for name in everywhere:
            if name not in named:
                chain.add(
                    Interceptor.from_document(
                        name, declared[name], source,
                        programs=doc.get("programs"),
                        runner=chain.runner,
                        unenforced=chain.unenforced,
                    )
                )
        for name in named:
            entry = declared.get(name)
            if entry is None:
                known = ", ".join(sorted(declared)) or "none"
                raise InterceptorError(
                    f"agent {agent_key!r} names a rule called {name!r}, and this "
                    f"workspace has no such rule. It declares: {known}. "
                    f"Fix: change that line to one of those, or add a file "
                    f"`interceptors/{name}.yaml`."
                )
            chain.add(
                Interceptor.from_document(
                    name, entry, source,
                    programs=doc.get("programs"),
                    runner=chain.runner,
                    unenforced=chain.unenforced,
                )
            )
        _hiding_runs_first(chain, source)
        return chain


# ─────────────────────────────────────────────────────── the sentence vocabulary

#: What a redaction rule can recognise, and the pattern behind each. Closed, and
#: mirrored in the `interceptor.rules` help text in `spec/schema.yaml`, which is
#: where the list is maintained for whoever is typing — the same relationship
#: `loops.Does` has to `stage.does`.
#:
#: Over-matching is the safe direction here and under-matching is not, so the
#: card pattern accepts the spacing people actually type — and the bank-account
#: pattern accepts the four shapes people actually write. It used to accept two
#: and neither was the common one: the IBAN alternative demanded the part after
#: the country code be a whole number of four-character groups, which `GB33BUKB
#: 20201555555555` written without spaces is not, and the UK alternative demanded
#: the account number follow the sort code with exactly one space and no words
#: between, which `sort code 12-34-56 account 12345678` is not. A rule an author
#: wrote about bank accounts matched neither. The alternatives are separate
#: because a sort code alone identifies a branch and an eight-digit account alone
#: is the rest of it; masking either is enough to break the pair.
RECOGNISES: Mapping[str, str] = {
    # `{13,16}` needed a word boundary right after the 16th digit, so a LONGER
    # run of digits matched nothing at all — a 19-digit card (Maestro, some
    # UnionPay, all valid under ISO/IEC 7812) went through untouched, in the
    # message and in a tool argument. This module's own note says over-matching
    # is the safe direction here and under-matching is not, so the bound is open
    # at the top rather than a ceiling that turns into a miss.
    "card number": r"\b(?:\d[ -]*?){12,}\d\b",
    "bank account": (
        # IBAN in four-character groups. The trailing `{1,3}` is the short last
        # group a real IBAN ends on — a GB one is 22 characters, so written in
        # fours it ends `... 9268 19`, and without this the two digits stayed on
        # the page beside `[removed]`.
        r"\b[A-Z]{2}\d{2}(?:[ ][A-Z0-9]{4}){2,7}(?:[ ][A-Z0-9]{1,3})?\b"
        r"|\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b"              # IBAN, run together
        r"|\b\d{2}[- ]\d{2}[- ]\d{2}\b"                   # UK sort code
        r"|\b\d{8}\b"                                     # UK account number
    ),
    "email address": r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b",
    "phone number": r"\+?\d[\d ()-]{7,}\d",
}


@dataclass(frozen=True)
class Carries:
    """What the run has in hand at one address, in the words the rules use.

    This is the answer to the only question the three load-time checks below
    ask — *at this moment, does the run hold the thing this sentence needs?* —
    and it is one answer rather than three because three is how they came to
    disagree. `send-elsewhere` was checked against a table of full addresses,
    `hide-values` against the address's SUBJECT alone (so `step.tool.completed`
    and `turn.message.before` passed a check that only `step.tool.before` could
    honour), and the counting sentences were not checked at all.
    """

    #: Whether a `replace ...` sentence can reach anything here. The FIELD is not
    #: named: the body picks it out of the payload it is handed, so a binding
    #: written as a prefix (`step.message`) masks whatever that address carries
    #: rather than whatever its spelling happened to resolve to at load time.
    values: bool = False
    #: `name` and `so-far` are in the payload, so a call can be counted here.
    which_tool: bool = False
    #: The harness reads `Decision.redirect` here and re-enters the loop.
    somewhere_else: bool = False
    #: `content` holds an ANSWER — words the model has just produced — rather
    #: than words on their way in. A rule whose condition reads what was said
    #: needs one of these; `step.message.before` carries `content` too and it is
    #: the customer's, so a rule about what the agent says would fire on what
    #: was said TO it.
    an_answer: bool = False


#: Every address the reference harness hands to `Chain.run`, and what it carries.
#:
#: This table is the thing that stops a power going back to being one that loads
#: and does nothing. A rule bound where the run cannot honour it is refused at
#: LOAD with the address to type, so the next address that starts carrying
#: values, or a tool name, or a redirect, is one edit here — and a rule the
#: harness stops emitting fails a test rather than quietly becoming decoration.
#:
#: `args` is a redaction target because the worked example's reason for existing
#: is to stop a card number leaving, and a card number typed into a `payments`
#: argument is the likeliest way one does.
#:
#: `step.delegate.before` carries only the members being asked; masking a
#: teammate's NAME would rename them, so it carries nothing a rule can hide.
WIRED: Mapping[str, Carries] = {
    "step.message.before": Carries(values=True),
    "step.message.after": Carries(values=True, an_answer=True),
    "turn.message.after": Carries(values=True, an_answer=True),
    "step.tool.before": Carries(values=True, which_tool=True, somewhere_else=True),
    # What a tool handed back. `values=True` and nothing else.
    #
    # NOT `which_tool`, even though the payload carries `name`: that flag's
    # promise is that a call can be COUNTED here, which needs `so-far` as well —
    # and counting in order to prevent a call has to happen before the call.
    # Stopping after the money moved is not stopping, so a counting rule bound
    # here would load and do nothing, which is the one thing this table exists
    # to refuse.
    #
    # NOT `somewhere_else`: the call has already happened and there is nothing
    # left to send elsewhere. NOT `an_answer`: a tool result is not something the
    # agent said, and a rule about what the agent says must not fire on what a
    # tool told it.
    "step.tool.completed": Carries(values=True),
    "step.delegate.before": Carries(),
}

#: The payload fields a redaction reaches, looked for in this order. A message's
#: `content` is a string and a tool call's `args` is a map; the masker walks
#: whatever shape it is handed, so one list covers both.
#:
#: Read from the PAYLOAD at run time rather than fixed at load time. The old code
#: resolved one field name from the binding's subject, which meant a prefix
#: binding resolved to the wrong field or to none — and it is what let the
#: address check be written against the subject in the first place.
VALUE_FIELDS: tuple[str, ...] = ("content", "args")

#: Where a redirect is ACTED ON. Derived, so it cannot drift from `WIRED`.
REDIRECTS_AT: tuple[str, ...] = tuple(
    a for a, c in WIRED.items() if c.somewhere_else
)

#: Where the workspace's `redaction.yaml` is carried out — every moment the run
#: is holding values, because "must never leave" is not a statement about one of
#: them. Derived from the same table for the same reason `REDIRECTS_AT` is: the
#: next moment the harness starts handing values to a chain is one row, and the
#: floor covers it without anybody remembering to add it here too.
HIDES_AT: tuple[str, ...] = tuple(a for a, c in WIRED.items() if c.values)

#: Named once so the places that print each cannot drift from the table or from
#: each other — the load-time refusals, and §7.10.
WHERE_HIDING_WORKS = (
    "one of the moments that carries values: "
    + ", ".join(f"`{a}`" for a, c in WIRED.items() if c.values)
    + " — before words reach the model, before a value is handed to a tool, "
    "or before either is written down"
)

WHERE_REDIRECTING_WORKS = (
    "`step.tool.before` — before a tool runs is the only moment at which the "
    "run can still go somewhere else instead of running it"
)

WHERE_READING_AN_ANSWER_WORKS = (
    "`turn.message.after` for the reply the customer reads, or "
    "`step.message.after` for every answer along the way"
)

WHERE_COUNTING_WORKS = (
    "`step.tool.before` — before a tool runs is the only moment at which the "
    "run knows which tool is about to be called"
)

#: What a sentence that names no replacement leaves behind.
#:
#: `anything that looks like a card number` is `replace ... with "…"` with the
#: words left out, and somebody writing a list of what must never leave has no
#: opinion about the words — asking them for one to say "take this out" is why
#: `redaction.hide` grew a second vocabulary in the first place. It is the same
#: string the "you have to say what to replace it with" refusal already offers,
#: so what an author is told to type and what they get by typing nothing agree.
REMOVED = "[removed]"

_A = r"(?:an?|the)\s+"
_REPLACE = re.compile(
    rf'^replace\s+anything\s+that\s+looks\s+like\s+{_A}(?P<thing>.+?)\s+with\s+"(?P<text>.*)"$',
    re.IGNORECASE,
)
_SAME = re.compile(
    rf"^do\s+the\s+same\s+for\s+anything\s+that\s+looks\s+like\s+{_A}(?P<thing>.+?)$",
    re.IGNORECASE,
)
#: The sentence `redaction.hide` had and `interceptor.rules` did not, now shared
#: by both through the `&the-hiding-sentences` anchor in `spec/schema.yaml`.
#:
#: Tried AFTER the two above, and it cannot take either of them: both begin with
#: a word this one does not (`replace`, `do`), and this one is anchored at the
#: start of the sentence.
_BARE = re.compile(
    rf"^anything\s+that\s+looks\s+like\s+{_A}(?P<thing>.+?)$",
    re.IGNORECASE,
)
#: The condition the two counting sentences share, written once. They differ in
#: what they do about it and in nothing else — one ends the run, the other sends
#: it to another stage — so "more than n times in one run" has one spelling, one
#: tolerance for `time`/`times`, and one counter behind it.
_COUNTED = (
    r"^if\s+(?P<tool>[\w./-]+)\s+is\s+called\s+more\s+than\s+(?P<n>\d+)\s+times?"
    r"\s+in\s+one\s+run,\s+"
)
_CALL_LIMIT = re.compile(_COUNTED + r'stop\s+and\s+say\s+"(?P<why>.*)"$', re.IGNORECASE)
_CALL_REDIRECT = re.compile(
    _COUNTED + r"go\s+to\s+(?:the\s+)?(?P<stage>[\w-]+)(?:\s+stage)?\s+instead$",
    re.IGNORECASE,
)

#: `replace the answer with what <a program> returns` — and the same for what the
#: model is about to be told. Two sentences, one shape, because the difference is
#: only which end of the step they stand at.
_REWRITE_ANSWER = re.compile(
    r"^replace\s+the\s+answer\s+with\s+what\s+(?P<program>[A-Za-z0-9-]+)\s+returns$",
    re.IGNORECASE,
)
_REWRITE_REQUEST = re.compile(
    r"^replace\s+what\s+the\s+model\s+is\s+told\s+with\s+what\s+"
    r"(?P<program>[A-Za-z0-9-]+)\s+returns$",
    re.IGNORECASE,
)

_MENTIONS = re.compile(
    r'^if\s+the\s+answer\s+mentions\s+(?P<words>.+?)\s*,\s*'
    r'stop\s+and\s+say\s+"(?P<why>.*)"$',
    re.IGNORECASE,
)


def said_any(words: "Sequence[str]", text: str) -> list[str]:
    """Which of `words` appear in `text`, folded to lower case. The whole test.

    ONE matcher, used by two acts. `evals.must-not-contain` grades a recorded
    case and this stops a live run; they are different acts, which is why both
    exist, but they are the same QUESTION — does the answer say this word — and
    an author who has written one has written the other. Two implementations of
    one question is how two vocabularies come to disagree, which is the merge
    `spec/schema.yaml`'s hiding sentences already record.

    A plain substring test and deliberately not a meaning test. `diagnos`
    catches `diagnosis` and `diagnosed` because it is a prefix, not because
    anything here knows what either word means. For meaning, a `judged:` rule in
    `evals/` with a `graded-by:` model is the mechanism, and it is a different
    one on purpose: this decides without a model, which is what lets it run
    inside a live turn.
    """
    low = text.lower()
    return [str(w) for w in words if str(w).strip().lower() in low]


def _quoted_words(written: str) -> list[str]:
    """The words an author listed, out of `"one", "two", "three"`.

    Quotes are required and not merely tolerated, because the alternative reads
    ambiguously: `mentions refund, arrive` could be two words or one phrase with
    a comma in it, and the difference decides whether a rule fires. Quoting says
    which, and it is what `must-not-contain:` already looks like in `evals/`.
    """
    return [m.group(1).strip() for m in re.finditer(r'"([^"]*)"', written) if m.group(1).strip()]


def _mentions(words: "Sequence[str]", why: str) -> Callable[[dict[str, Any]], "Decision | None"]:
    """Stop the turn when the answer says one of the author's words.

    The condition reads the ANSWER, which no sentence in this vocabulary did
    before: both stopping sentences count tool calls and are pinned to
    `step.tool.before`. So `may: [stop-the-run]` at `turn.message.after` was a
    power nothing could use, and "never give medical advice" was not expressible
    at all — the single most-wanted rule in the persona trial and the one gap the
    format had no answer to.
    """

    def check(payload: dict[str, Any]) -> "Decision | None":
        if not said_any(words, str(payload.get("content", ""))):
            return None
        return Decision(stop=why)

    return check


#: Printed under every refusal, so the author is never told what is wrong
#: without being told what to write instead.
FORMS: tuple[str, ...] = (
    'replace anything that looks like a <thing> with "<text>"',
    "do the same for anything that looks like a <thing>",
    "anything that looks like a <thing>",
    'if <a tool> is called more than <n> times in one run, stop and say "<why>"',
    "if <a tool> is called more than <n> times in one run, go to the <stage> "
    "stage instead",
    'if the answer mentions "<word>", "<word>", stop and say "<why>"',
)

#: Which power each of those sentences needs, so a refusal can offer the ones a
#: document is actually able to carry out. `redaction.yaml` hides and does
#: nothing else, so listing the two counting sentences under a refusal there
#: would offer the author the sentence they just wrote as the repair for having
#: written it. The Rust half asks the same question through
#: `Forms::spellings_needing`, off the same `needs:` written in the schema.
NEEDED_BY: Mapping[str, Power] = {
    FORMS[0]: Power.HIDE_VALUES,
    FORMS[1]: Power.HIDE_VALUES,
    FORMS[2]: Power.HIDE_VALUES,
    FORMS[3]: Power.STOP,
    FORMS[4]: Power.REDIRECT,
    FORMS[5]: Power.STOP,
}


#: The sentences that are not rules on their own — they carry on from the line
#: above and reuse the words it left behind. `continues: yes` on the same form in
#: `spec/schema.yaml` is this fact on the checking side, so `pact check` and the
#: run refuse the same file. It was in neither for a round: an interceptor whose
#: one rule was `do the same for anything that looks like a card number` printed
#: `OK — … loaded cleanly (17 settings)` and was then refused here.
CONTINUES: frozenset[str] = frozenset({FORMS[1]})

#: What a continuing sentence can carry on FROM, which is the same list it can be
#: replaced BY — so one list answers both ways out of that refusal. Derived from
#: `FORMS` rather than written out again, so a sixth hiding sentence is offered
#: here by being added there and nowhere else.
ON_ITS_OWN: tuple[str, ...] = tuple(
    f for f in FORMS if f not in CONTINUES and NEEDED_BY[f] is Power.HIDE_VALUES
)


def forms_for(may: frozenset[Power]) -> tuple[str, ...]:
    """The sentences a document holding exactly these powers can carry out."""
    return tuple(f for f in FORMS if NEEDED_BY[f] in may)


def _compile_rules(
    source: "Path | None",
    name: str,
    rules: Sequence[str],
    when: Sequence[str],
    may: frozenset[Power],
    *,
    where: str = "",
    fixed_powers: bool = False,
    programs: "Mapping[str, Any] | None" = None,
    runner: "Runner | None" = None,
    unenforced: "list[str] | None" = None,
) -> tuple[Body, frozenset[str]]:
    """Turn an interceptor's sentences into one body, and name where it may go.

    A redaction and a guard in the same document compose: the redactions build
    one pattern table applied in order, and each guard is a test that can end the
    step — by stopping the run, or by sending it to another stage. Those are not
    three kinds of interceptor, they are sentences in one document.

    The stage names its redirect sentences point at come back with the body, so
    the harness can hold them against the loop **before the first model call**
    rather than when a rule fires — see `Chain.destinations`.

    `fixed_powers` says the powers came from the KIND rather than from a `may:`
    line the author wrote — which is what `redaction.yaml` is, and it is the
    other half of `always-may:` in `spec/schema.yaml`. It changes only the
    refusals: "add a line under `may:`" names a setting a redaction does not
    have, and a fix nobody can type is not one. `where` names the document in
    the words a diagnostic should use it in ("a redaction"), and defaults to the
    interceptor wording every existing message already carries.
    """
    doc = where or "this interceptor"
    at_document = _where(source, name, "")
    patterns: list[tuple[re.Pattern[str], str]] = []
    destinations: set[str] = set()
    # A guard returns the decision it reached, not a reason string. One list
    # rather than one list per consequence: stopping and redirecting are the
    # same test with different endings, and a second list beside this one would
    # be a second place for "no more than one refund" to be counted differently.
    guards: list[Callable[[dict[str, Any]], Decision | None]] = []
    #: The guards whose condition is the WORDS rather than a count, run after any
    #: rewriting so they see what will really be said. See `_mentions` below.
    reads_the_words: list[Callable[[dict[str, Any]], Decision | None]] = []
    #: `(program, power)` per rewriting sentence, applied after the hiders and
    #: before the guards — a rewriter should see what the redactions left, and a
    #: guard should read what will actually be said.
    rewriters: list[tuple[str, Power]] = []
    last_replacement: str | None = None

    for n, sentence in enumerate(rules, start=1):
        text = " ".join(str(sentence).strip().split())
        # The rule's OWN line, found in the file the Expansion Rule says it came
        # from. Every message below used to read `interceptors/<name>.yaml,
        # rule 3` — a path that does not exist when the rule was written as a
        # folder, and a rule number the author has to count out by hand.
        at = f"{_where(source, name, text)}, rule {n}"

        spelled_out = _REPLACE.match(text)
        same_again = None if spelled_out else _SAME.match(text)
        # The third hiding sentence, and the one this module could not read for a
        # round: `anything that looks like a card number` is what the shipped
        # `redaction.yaml` writes on every line, and writing it under `rules:`
        # was refused as "not a rule PACT knows how to carry out". It is
        # `replace ... with "…"` with the words left out, so it takes the same
        # branch and only decides what goes in their place.
        bare = None if (spelled_out or same_again) else _BARE.match(text)
        if spelled_out or same_again or bare:
            found = spelled_out or same_again or bare
            assert found is not None
            thing = found.group("thing").strip().lower()
            # Asked FIRST, and it used to be asked last. `do the same for
            # anything that looks like a shoe size` written on its own met the
            # refusal below it, whose fix wrote the author's own word back into a
            # sentence — `replace anything that looks like a shoe size with
            # "[removed]"` — which the very next check then refused. A fix that
            # sends the author straight to the next refusal is a fix in shape
            # only, which is the standard this module already sets one screen
            # down for `redaction.yaml` and the two counting sentences. The thing
            # is a property of this sentence alone, so it can always be asked
            # first.
            if thing not in RECOGNISES:
                raise InterceptorError(
                    f"{at}: nothing here knows what {thing!r} looks like. "
                    f"The things that can be recognised are: "
                    f"{', '.join(sorted(RECOGNISES))}. "
                    f"Fix: use one of those."
                )
            if spelled_out is not None:
                last_replacement = spelled_out.group("text")
            elif bare is not None:
                # It does set the replacement, so `do the same for …` written
                # under it reuses `[removed]` rather than refusing. A sentence
                # that plainly hides something, followed by one that says "and
                # that too", must not be told nothing above it says what to
                # replace anything with.
                last_replacement = REMOVED
            elif last_replacement is None:
                # Word for word the refusal `pact check` prints
                # (`schema/rule-with-nothing-above-it`), off the `continues: yes`
                # written on this sentence in `spec/schema.yaml`. The two halves
                # are in different languages and the author must not be able to
                # tell which one refused them — and for a round only this half
                # refused at all, so a file whose one rule was `do the same for
                # …` printed "loaded cleanly" from the only tool D13's author
                # runs and was rejected by the run.
                raise InterceptorError(
                    f"{at}: {text!r} says to do the same as the rule before it, "
                    f"and no rule before it says what to do. "
                    f"Fix: write one of these here instead — or put one above "
                    f"this line and let this one carry on from it:\n  "
                    + "\n  ".join(ON_ITS_OWN)
                )
            # One sentence, one power. This used to accept any of the three
            # change-powers, which is how `may:` came to mean "it changes
            # something" instead of "it does this". A masking rule declaring
            # `change-the-request` was claiming a broader power than it uses,
            # and a reviewer reading `may:` learned less than the rules did.
            if Power.HIDE_VALUES not in may:
                raise InterceptorError(
                    _lacks(at, doc, may, Power.HIDE_VALUES, fixed_powers)
                )
            # Where the run is actually holding values to replace. Asked of the
            # WHOLE address, not of its subject: `subject in REDACTS` let
            # `step.tool.completed`, `turn.message.before`, `session.message.
            # before` and `action.tool.before` through — four addresses the
            # harness never hands to a chain, at which a card-number rule loaded
            # cleanly and masked nothing.
            if not _carries(when, "values"):
                raise InterceptorError(
                    f"{at}: nothing at {_spell(when)} carries values to replace, "
                    f"so this rule would do nothing. Fix: change `when:` to "
                    f"{WHERE_HIDING_WORKS}."
                )
            patterns.append((re.compile(RECOGNISES[thing]), last_replacement))
            continue

        rewrite = _REWRITE_ANSWER.match(text)
        rewrites_request = None if rewrite else _REWRITE_REQUEST.match(text)
        if rewrite or rewrites_request:
            found = rewrite or rewrites_request
            assert found is not None
            power = Power.CHANGE_ANSWER if rewrite else Power.CHANGE_REQUEST
            if power not in may:
                raise InterceptorError(_lacks(at, doc, may, power, fixed_powers))
            named = found.group("program")
            if programs is not None and named not in programs:
                raise InterceptorError(
                    f"{at}: this rule replaces what it was given with what '{named}' "
                    f"returns, and '{named}' is not a program this workspace carries. "
                    f"Fix: write it in `programs/{named}/program.yaml`, or name one of: "
                    f"{', '.join(sorted(programs)) or 'nothing here yet'}."
                )
            rewriters.append((named, power))
            continue

        if m := _MENTIONS.match(text):
            if Power.STOP not in may:
                raise InterceptorError(_lacks(at, doc, may, Power.STOP, fixed_powers))
            # The condition reads what came back, so the moment has to be one
            # that carries an answer. The same question the two counting
            # sentences are asked one branch down, through the same helper: a
            # rule no named moment can carry out loads and does nothing, which
            # is the failure this whole module exists to refuse.
            if not _carries(when, "an_answer"):
                raise InterceptorError(
                    f"{at}: nothing at {_spell(when)} carries an answer to read, so "
                    f"this rule would do nothing. Fix: change `when:` to "
                    f"{WHERE_READING_AN_ANSWER_WORKS}."
                )
            words = _quoted_words(m.group("words"))
            if not words:
                raise InterceptorError(
                    f'{at}: this rule names no words to look for. Fix: write them in '
                    f'quotes, separated by commas — `if the answer mentions '
                    f'"diagnosis", "dosage", stop and say "..."`.'
                )
            # ON THE WORD-READING LIST, not the general guard list. It is the
            # one sentence whose condition reads what the agent SAID, so it has
            # to see what will actually be said — including anything a rewriting
            # rule beside it introduced. Measured before this split: a rewriter
            # whose program returned "this is a diagnosis" walked straight past
            # `if the answer mentions "diagnos", stop and say "..."` in the same
            # document, because the guard had already run on the words before.
            #
            # The counting guards stay where they are, and must: they are about
            # how many times a TOOL was called, re-running one would count the
            # same call twice, and a rewrite does not change a call count.
            reads_the_words.append(_mentions(words, m.group("why")))
            continue

        if m := _CALL_LIMIT.match(text):
            if Power.STOP not in may:
                raise InterceptorError(_lacks(at, doc, may, Power.STOP, fixed_powers))
            # The same check its twin below has, for the same reason and one
            # round later. This sentence counts calls out of `name` and `so-far`,
            # which only a moment that knows which tool is about to run can
            # supply — so bound at `turn.message.after` it loaded, saw a payload
            # with neither field, and returned "no" forever. Two sentences
            # sharing one counter were held to two standards.
            if not _carries(when, "which_tool"):
                raise InterceptorError(
                    f"{at}: nothing at {_spell(when)} counts tool calls, so this "
                    f"rule would do nothing. Fix: change `when:` to "
                    f"{WHERE_COUNTING_WORKS}."
                )
            guards.append(_call_limit(m.group("tool"), int(m.group("n")), stop=m.group("why")))
            continue

        if m := _CALL_REDIRECT.match(text):
            if Power.REDIRECT not in may:
                raise InterceptorError(
                    _lacks(at, doc, may, Power.REDIRECT, fixed_powers)
                )
            # The check that keeps this power from going inert again. A redirect
            # is carried out at the addresses `WIRED` marks `somewhere_else` and
            # nowhere else, so a rule bound elsewhere is refused here rather than
            # loaded and quietly ignored — which is what `send-elsewhere`
            # amounted to at every address for a round.
            if not _carries(when, "somewhere_else"):
                raise InterceptorError(
                    f"{at}: nothing at {_spell(when)} can send the run somewhere "
                    f"else, so this rule would do nothing. Fix: change `when:` to "
                    f"{WHERE_REDIRECTING_WORKS}."
                )
            if not _carries(when, "which_tool"):
                raise InterceptorError(
                    f"{at}: nothing at {_spell(when)} counts tool calls, so this "
                    f"rule would do nothing. Fix: change `when:` to "
                    f"{WHERE_COUNTING_WORKS}."
                )
            # The stage name is not resolved here — an interceptor document does
            # not know which loop will be in force, the same reason §7.12's REF-3
            # gives for `may-use:`. It is carried out instead, so the AGENT can
            # hold it: the agent knows both its `loop:` and its `interceptors:`,
            # and the harness checks every destination through `Loop.phase`
            # before the first model call. That comment used to CLAIM this check
            # and there was none: a typo'd destination cost a model call and a
            # real refund before it surfaced.
            destinations.add(m.group("stage"))
            guards.append(_call_limit(m.group("tool"), int(m.group("n")), to=m.group("stage")))
            continue

        # The five sentences, narrowed to the ones THIS document can perform.
        # `redaction.yaml` may only hide, and offering it `stop and say "…"` as
        # the repair for a sentence it cannot carry out would send the author
        # straight to the next refusal. Where the powers come from a `may:` line
        # this is the whole list again, exactly as it was.
        offer = forms_for(may) if fixed_powers else FORMS
        raise InterceptorError(
            f"{at}: {text!r} is not a rule PACT knows how to carry out, so it "
            f"would load and do nothing. Fix: write one of:\n  "
            + "\n  ".join(offer)
        )

    def body(payload: dict[str, Any]) -> Decision:
        #: Set when a rewriting sentence changed the words, so the hiders below
        #: work on what will really be said and the decision carries both.
        rewritten: Power | None = None
        for check in guards:
            decided = check(payload)
            if decided is not None:
                return decided
        # A rewriting sentence, applied after the hiders below have had their say
        # about the value and before anything reads what will be said.
        #
        # A rewriter with nothing to run it leaves the words EXACTLY as they were
        # and says so, rather than half-applying: a rule that silently passed the
        # words through would have the author believing their program had run,
        # which is the "loads and does nothing" failure the whole vocabulary
        # exists to refuse.
        if rewriters and "content" in payload:
            # Read at CALL time, not closed over at build time: the chain is
            # built from the document and the runner arrives with the run.
            run_program = runner.call if runner is not None else None
            if run_program is None:
                for named, _ in rewriters:
                    said = (
                        f"the rule at {at_document} replaces what it was given with what "
                        f"`{named}` returns, and nothing here can run a carried program — "
                        f"so the words were left exactly as they were."
                    )
                    if unenforced is not None and said not in unenforced:
                        unenforced.append(said)
            else:
                out = dict(payload)
                by: Power | None = None
                for named, power in rewriters:
                    try:
                        out["content"] = str(run_program(named, {"content": out["content"]}))
                        by = power
                    except Exception as e:  # noqa: BLE001 — a program's failure is data
                        said = (
                            f"the rule at {at_document} could not run `{named}`: {e} — "
                            f"so the words were left exactly as they were."
                        )
                        if unenforced is not None and said not in unenforced:
                            unenforced.append(said)
                        out = dict(payload)
                        by = None
                        break
                if by is not None:
                    # FALLS THROUGH to the hiders rather than returning. Returning
                    # here skipped every masking rule in the same document, so a
                    # rewriting rule silently disabled the redaction beside it —
                    # measured, a card number survived a chain whose own first
                    # rule was written to remove it. An author who reads two
                    # rules and gets one is worse off than one whose rewrite was
                    # refused outright, and it is the attack §8.5 says a rewrite
                    # cannot mount.
                    #
                    # Rewrite THEN hide, in that order: the hiders have to see
                    # the words that will actually be said, including any a
                    # rewriter introduced.
                    payload = out
                    rewritten = by
        # NOW the guards whose condition is the words. After any rewriting,
        # because that is what makes them true of what will be said, and before
        # the hiders, because a rule that stops on a word must see the word
        # rather than `[removed]`.
        for check in reads_the_words:
            decided = check(payload)
            if decided is not None:
                return decided
        if not patterns:
            return Decision(changed=payload, by=rewritten) if rewritten else Decision()
        # Which field to mask comes from the payload in hand, not from how the
        # binding was spelled. `step.message` and `step.message.before` are the
        # same rule to the chain, and they used to be different rules here.
        out = dict(payload)
        touched = False
        for name in VALUE_FIELDS:
            if name not in payload:
                continue
            after = _mask(payload[name], patterns)
            if after != payload[name]:
                out[name] = after
                touched = True
        if touched:
            # `hide-values` is the power reported when both happened: it is the
            # one a reviewer cares that the chain still had, and the rewrite is
            # visible in the words themselves.
            return Decision(changed=out, by=Power.HIDE_VALUES)
        return Decision(changed=payload, by=rewritten) if rewritten else Decision()

    return body, frozenset(destinations)


def _mask(value: Any, patterns: Sequence[tuple[re.Pattern[str], str]]) -> Any:
    """Apply the pattern table to this value and to everything inside it.

    A message's `content` is a string and a tool call's `args` is a map, so the
    walk is over SHAPES rather than one field per address. Nesting is walked for
    the same reason the top level is: a card number in `args["card"]["number"]`
    has left the building exactly as surely as one in a top-level argument, and
    an author who wrote one sentence about card numbers believes both are
    covered.

    Keys are left alone. Masking one renames an argument, and a tool handed
    `[card number removed]` where it expected `number` fails in a way that reads
    as the tool's fault.

    A number is masked by its text form, because `{"card": 4111111111111111}` is
    a string that skipped its quotes and is a shape card numbers really arrive
    in. The type changes only where the value MATCHED — anything that did not is
    handed back exactly as it came, so an amount stays a number. Over-matching
    is the safe direction here and under-matching is not, which is the same
    trade `RECOGNISES` already makes in its patterns.
    """
    if isinstance(value, str):
        return _substitute(value, patterns)
    if isinstance(value, Mapping):
        return {k: _mask(v, patterns) for k, v in value.items()}
    if isinstance(value, tuple):
        return tuple(_mask(v, patterns) for v in value)
    if isinstance(value, list):
        return [_mask(v, patterns) for v in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        spelled = str(value)
        after = _substitute(spelled, patterns)
        return after if after != spelled else value
    return value


@lru_cache(maxsize=None)
def _scanner(patterns: tuple[tuple[re.Pattern[str], str], ...]) -> re.Pattern[str]:
    """One expression that finds where ANY of the patterns could begin.

    Only used to skip the parts of a long string nothing recognises, so the walk
    below costs one linear scan rather than one attempt per character.
    """
    return re.compile("|".join(f"(?:{rx.pattern})" for rx, _ in patterns))


def _substitute(text: str, patterns: Sequence[tuple[re.Pattern[str], str]]) -> str:
    """Replace every run any sentence recognises — longest match wins.

    This used to be one `rx.sub` per pattern in the order the sentences were
    written, and two of the things an author can name overlap: the middle of an
    IBAN written in four-character groups is sixteen digits, which is exactly
    what a card number looks like. Applied in turn, the card pattern ate the
    middle of the IBAN and left its head standing — `my iban is GB29 NWBK 6016
    1331 9268 19` came out as `my iban is GB29 NWBK [removed]`. Which of the two
    won was decided by which sentence the author happened to write first, and a
    support lead cannot be expected to reason about that (D13). Longest match
    wins instead, so two sentences that both say "hide this" give the same answer
    whichever order they are in.

    The vocabulary is closed, and nothing in it can begin *inside* a longer
    member of it — a card number is digits and an IBAN starts with letters — so
    taking the longest match at each place any of them can start covers every
    one of them.
    """
    if not patterns:
        return text
    scan = _scanner(tuple(patterns))
    out: list[str] = []
    i = 0
    while (found := scan.search(text, i)) is not None:
        start = found.start()
        end, replacement = start, ""
        for rx, repl in patterns:
            m = rx.match(text, start)
            if m is not None and m.end() > end:
                end, replacement = m.end(), repl
        if end <= start:
            # The alternation matched where no single pattern does, which cannot
            # happen — written out anyway so the loop always advances rather
            # than hanging on a value someone put in a tool result.
            out.append(text[i : start + 1])
            i = start + 1
            continue
        out.append(text[i:start])
        out.append(replacement)
        i = end
    out.append(text[i:])
    return "".join(out)


def _call_limit(
    tool: str, at_most: int, *, stop: str = "", to: str = ""
) -> Callable[[dict[str, Any]], Decision | None]:
    """One tool is about to be called once too often. End the step accordingly.

    Two sentences share this counter because they share the condition and differ
    only in the ending: `stop and say "…"` ends the run, `go to the <stage>
    stage instead` re-enters the loop there. Writing the count twice would be
    writing two answers to "how many refunds has this run issued", which is
    exactly the question that must have one.

    Counted from `so-far`, which the harness hands in, rather than from a
    counter held here: a run parks and comes back in another process (D23), and
    a counter in this process would start again at nought — so the second refund
    the rule exists to stop would be the first one it ever saw.
    """
    head = tool.split("/")[0]

    def check(payload: dict[str, Any]) -> Decision | None:
        if str(payload.get("name", "")).split("/")[0] != head:
            return None
        so_far = payload.get("so-far") or ()
        already = sum(1 for n in so_far if str(n).split("/")[0] == head)
        if already < at_most:
            return None
        # Built fresh each time it fires rather than shared: a `Decision` is an
        # ordinary record and a caller that adjusted one would be adjusting
        # every later firing of the same rule.
        return Decision(stop=stop or None, redirect=to or None)

    return check


def _carries(when: Sequence[str], what: str) -> bool:
    """Does any address any of `when` catches carry `what`?

    Asked through the same matching the chain uses, so a prefix binding
    (`step.tool`, or `*`) is judged by what it really catches rather than by
    string equality — a rule that would fire at `step.tool.before` is accepted
    however the author chose to spell the binding.

    ANY of the moments named, not all of them: a file that redacts at two
    moments and counts tool calls at one is exactly the composition a list of
    moments exists to allow, and the counting sentence really does fire at the
    moment that counts. What stays refused is the failure this was written for —
    a sentence NO named moment can carry out, which loads and does nothing.

    One function for all three powers. It was written for redirects alone, and
    while it existed the redaction check next to it was still keyed on the
    address's subject and the counting sentences had no check at all; a shared
    question asked three ways is how they came to disagree.
    """
    return any(getattr(WIRED[a], what) for a in _moments(when))


def _moments(when: Sequence[str]) -> frozenset[str]:
    """Which of the moments the harness really hands a chain this binding catches.

    Asked through the same matching `Chain.at` uses, so a prefix (`step.tool`, or
    `*`) is judged by what it really catches rather than by string equality.

    One function rather than two: `_carries` asks *"does any of them carry this
    power"* and `_hiding_runs_first` asks *"do these two rules ever meet"*, and
    those are the same question about the same table. Asking it twice is how the
    three power checks came to disagree in the first place.
    """
    from .events import Address

    return frozenset(
        address
        for address in WIRED
        for bound in when
        if Address.parse(address).matches(bound)
    )


def _runs_at(where: str, raw: Any) -> int | None:
    """The number under `runs-at:`, or `None` for "the author did not say".

    Refused here as well as by `pact check`, and not because the loader is
    untrusted: an adapter is handed a document (invariant P-1) and may be handed
    one that never went through the checker, and a `runs-at:` nobody can read as
    a number would otherwise fall back to the band — which is silently the
    opposite of what somebody who bothered to type a number wanted.
    """
    if raw is None:
        return None
    # `isinstance(True, int)` is true in Python, and `runs-at: yes` is a thing a
    # person writes. It would arrive here as 1 — the very first rule at its
    # moment — which is not a reading of "yes" anybody intended.
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise InterceptorError(
            f"{where}: `runs-at:` is a whole number saying which rule at the same "
            f"moment goes first, and this is {raw!r}. Fix: write `runs-at: 10` — "
            f"lower numbers run first."
        )
    if raw < 1:
        raise InterceptorError(
            f"{where}: `runs-at: {raw}` — the earliest a rule can run is 1. "
            f"Fix: write `runs-at: 1`, and leave gaps between your numbers "
            f"(10, 20, 30) so there is room to put a rule between two others "
            f"later."
        )
    return raw


def _hiding_runs_first(chain: Chain, source: "Path | None") -> None:
    """Refuse a chain where a rule that can END it may run before one that hides.

    `Chain.run` returns at the first stop or redirect, so a rule that ends the
    chain does not DELAY the rules after it, it deletes them. On the redirect
    path the harness then writes what the chain left into the run's own record
    (`call = ToolCall(call.name, checked["args"])`), under its own comment: *"a
    value that must not survive in the record must not survive on the path where
    the tool never even ran"*. So a guard ordered in front of a redaction leaves
    the card number in the transcript — the one thing
    `interceptors/redact-card-numbers.yaml` exists to stop.

    Equal numbers are refused too, and that is the point of the check rather than
    a strictness on top of it. Equal means the order comes from whichever rule
    was added first, which for two workspace-wide rules is their FILENAMES; the
    measurement that prompted this field was a file changing what it was safe
    against by being renamed. Refused rather than silently reordered, because
    reordering would be this module deciding which of two rules an author meant
    to come first, and the two orders differ in what ends up written down.
    """
    for ender in chain.interceptors:
        if not (ender.may & ENDS_THE_CHAIN):
            continue
        for hider in chain.interceptors:
            if hider is ender or Power.HIDE_VALUES not in hider.may:
                continue
            shared = _moments(ender.when) & _moments(hider.when)
            if not shared or ender.order > hider.order:
                continue
            first = min(ender.order, hider.order)
            stated = (
                f"it is set to go first (`runs-at: {ender.order}` against "
                f"`runs-at: {hider.order}`)"
                if ender.order < hider.order
                else f"nothing says which of them goes first — both run at "
                f"{ender.order}, so the order is whichever file was read first"
            )
            raise InterceptorError(
                f"{_where(source, ender.name, 'runs-at')}: {ender.name!r} can end "
                f"the run at {_spell(sorted(shared))}, {hider.name!r} hides "
                f"values at the same moment, and {stated}. Nothing after the rule "
                f"that ends a run happens, so the values {hider.name!r} says it "
                f"hides would be handed on and written down. Fix: put the hiding "
                f"first — `runs-at: {first}` in {_file(source, hider.name)}, and "
                f"`runs-at: {first + 10}` in {_file(source, ender.name)}."
            )


def _spell(when: Sequence[str]) -> str:
    """The moments a rule named, for a message. One reads as it always did."""
    return "`" + "`, `".join(when) + "`"


def _lacks(at: str, doc: str, may: frozenset[Power], needs: Power, fixed: bool) -> str:
    """A sentence needing a power this document has not got — refused two ways.

    A document that CHOOSES what it may do is told which line to add, which is
    what every one of these messages has always said. A document whose powers
    come with the KIND — `redaction.yaml`, which hides and does nothing else —
    has no `may:` list to add a line to, so it is told what it can do instead,
    with the sentences it can carry out written out.

    The split arrived with the shared vocabulary. `redaction.hide` and
    `interceptor.rules` are one list now (`&the-hiding-sentences`), so `hide:`
    is offered five sentences and can perform three, and the two it cannot must
    meet a refusal an author can act on. Offering "add `- stop-the-run` under
    `may:`" in a file that has no `may:` is a fix nobody can type, which is the
    same dead end as no fix at all.

    The Rust half prints the same two shapes off the same data — see
    `Schema::check_sentences` and `Forms::spellings_needing` — because an author
    must not be able to tell which of the two languages refused them.
    """
    if not fixed:
        return (
            f"{at}: this rule {DOES[needs]}, and {doc} does not say it may. "
            f"Fix: add a line under `may:` — `- {needs.value}`."
        )
    can = ", ".join(SAYS[p] for p in Power if p in may) or "do nothing"
    return (
        f"{at}: this rule {DOES[needs]}, and {doc} may only {can}. "
        f"Fix: write one of:\n  " + "\n  ".join(forms_for(may))
    )


def _file(source: "Path | None", name: str) -> str:
    """The file a rule lives in, without a line.

    `_where` is for pointing at a mistake and carries the line it is on; a fix
    that says *"add a line to this file"* wants the file alone, because there is
    no line yet to point at.
    """
    return _at(source, name, "")[0]


def _check_address(where: str, when: str) -> None:
    from .events import Address

    try:
        Address.parse(when)
    except ValueError as e:
        raise InterceptorError(f"{where}: {e}") from None


def _powers(where: str, raw: Any) -> frozenset[Power]:
    """The powers a document declared, held to the ones a document may declare.

    `AUTHORABLE`, not `Power`: the list an author is offered has to be the list
    an author can use, and two of the five are reachable only from a host's own
    process. Offering them here would name a fifth choice that every sentence
    below then refuses.
    """
    offered = ", ".join(p.value for p in Power if p in AUTHORABLE)
    values = _as_list(raw)
    if not values:
        raise InterceptorError(
            f"{where}: this rule does not say what it may do, so it may do "
            f"nothing. Fix: add a `may:` list — one of: {offered}."
        )
    out: set[Power] = set()
    for v in values:
        try:
            power = Power(v)
        except ValueError:
            raise InterceptorError(
                f"{where}: {v!r} is not something an interceptor may do. "
                f"Fix: use one of: {offered}."
            ) from None
        if power not in AUTHORABLE:
            raise InterceptorError(
                f"{where}: {v!r} cannot be asked for from a file — no rule you "
                f"can write uses it, so it would sit there meaning nothing. It "
                f"is available only to the system running this "
                f"(docs/50-NOT-COPIED.md §6). Fix: use one of: {offered}."
            )
        out.add(power)
    return frozenset(out)


def _rule_list(where: str, raw: Any) -> list[str]:
    rules = _as_list(raw)
    if not rules:
        raise InterceptorError(
            f"{where}: this rule says what it may do and never says what it "
            f"does. Fix: add a `rules:` list — for example:\n  " + FORMS[0]
        )
    return rules


def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    # A tuple as well as a list. `Interceptor.when` is a tuple once it is built,
    # so a host handing one back through `guard()` would otherwise have every
    # address silently dropped and get a rule bound to nothing.
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    return []


# ──────────────────────────────────────────────────── the typed escape (F-2/§5.5)


def guard(
    name: str,
    when: "str | Sequence[str]",
    check: Callable[[dict[str, Any]], str | None],
) -> Interceptor:
    """A stop-the-run interceptor whose test is a function. **Not an authoring
    path** — `Chain.from_document` is that, and it takes no code.

    This is the typed escape hatch §5.5 requires every mechanism to have: a host
    embedding the harness can express a condition the sentence vocabulary does
    not yet carry, in its own process, without that becoming the way an author
    is expected to work. `check` returns a reason, or None.

    `when` takes one address or several, the same as the authored field does: a
    host that had to build two guards to cover two moments would be meeting the
    limit the YAML no longer has.
    """

    def body(payload: dict[str, Any]) -> Decision:
        reason = check(payload)
        return Decision(stop=reason) if reason else Decision()

    return Interceptor(
        name=name,
        when=tuple(_as_list(when)),
        may=frozenset({Power.STOP}),
        body=body,
    )
