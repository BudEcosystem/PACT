"""The PACT harness — the loop PACT owns (decision D12, thesis T3).

A framework is used only as a *transport*: something that can perform one model
call and execute one tool. The step sequence, halting, tool dispatch, retry and
history construction all live here, identically for every target. That is what
makes two frameworks produce the same behaviour rather than merely accepting
the same file.

The alternative — mapping onto each framework's own agent abstraction — is what
every prior "universal agent format" attempted, and is why they were lossy.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

#: `Summariser` is imported rather than restated: a context policy that says
#: `summarised-by:` needs one, the harness never writes one itself — summarising
#: means a model call, and which model is the author's line — and two spellings
#: of the same callable is how a runtime comes to satisfy one and not the other.
from .context_policy import (
    Summariser,
    Tidied,
    Tidier,
    from_history,
    summary_request,
    to_history,
)
#: At-most-once, from the author's own `same-request-key:` line. `money.rs` does
#: the check-time half and says the runtime half is a separate question; this is
#: the answer, and without it the field was a guarantee nothing kept.
from .at_most_once import WITHHELD, Ledger
from .delegation import (
    Asker,
    Grant,
    Handoff,
    OverBudget,
    Pool,
    Teamwork,
    ask_team,
    asked_too_often,
    carried_on_without,
    granted,
    request_for,
)
from .diagnostics import locate
from .events import Bus
from .facts import TURN_ENDS, Facts
from .holes import fill
from .interceptors import Chain
from .ir import AgentSpec, SkillSpec
from .limits import RAN_OUT, Action, Meter, Reached, step_ceiling
from .loops import DONE, Does, Loop, LoopError, Phase
from .questions import AN_AGENT, ANYTHING, Gate, Question, Rejected, Wait
#: Three outcomes where this file used to read two. `_cleared` returned a bare
#: bool, so "a person said no" and "nobody has answered" were the same value and
#: every caller re-parked on both — see `rulings` for the measured shape of that.
#: `where`, `answer_to` and `ruling` are the old `_key`, `_answer_to` and
#: `_cleared`, moved beside the vocabulary they now return.
from .rulings import Ruling, answer_to, refused_in_words, ruling, where
from .yes_no import said_yes
#: What each park has to put in front of a person. One import and five call
#: sites, because for a round only ONE of those five rendered its question at
#: all and the other four handed somebody an answer contract and an empty
#: string. `shown` owns which values a park has to offer; `Question.for_person`
#: stays the only rendering there is (ASK-4, Y18/AD-46).
from .shown import a_stage, spent, teammate, tidying, words_for
from .suspension import (
    ASKED_A_PERSON,
    CONTEXT_TOO_LONG,
    GO_AHEAD,
    NEEDS_APPROVAL,
    NEEDS_PERMISSION,
    OUT_OF_BUDGET,
    WAITING_FOR_ANOTHER_AGENT,
    Expect,
    Resumption,
    Suspension,
    WrongAnswer,
    clears,
    rule_for,
    suspend,
)


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class Step:
    """One turn of the loop, recorded so two runs can be compared exactly."""

    index: int
    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    tool_results: tuple[str, ...] = ()


@dataclass
class RunResult:
    output: str
    steps: list[Step] = field(default_factory=list)
    halted: str = "final"
    suspension: "Suspension | None" = None
    #: One entry per step in which the team was asked. Kept because "two of the
    #: three agreed and the third was never waited for" is a fact about the run
    #: that the transcript alone reads as unanimity.
    handoffs: list[Handoff] = field(default_factory=list)
    #: Which ceiling ended this run, if one did — the setting the author typed,
    #: the number they wrote, the number reached, and what was done about it.
    #: Set even when the run produced a perfectly good answer, because
    #: `answer-with-what-it-has` is only safe to offer if "answered early" can
    #: be told from "finished".
    stopped_by: "Reached | None" = None
    #: The passages this run actually retrieved, if anything retrieved any (A2).
    #:
    #: A fact ABOUT THE RUN, and so a field on the run — not a line an author
    #: types. Three of the four canonical retrieval metrics
    #: (`contextual_precision`, `contextual_recall`, `contextual_relevancy`)
    #: never read the answer at all, so grading them against passages the author
    #: hand-wrote scores the author's own typing: the result is identical whether
    #: the runtime retrieved the right passage, the wrong one, or nothing.
    #:
    #: Empty when nothing retrieved anything, which is the honest state for a
    #: workspace with no corpus — and `case.from-these-passages:` is what an
    #: author writes when they want a grader to have a gold context anyway.
    retrieved: tuple[str, ...] = ()
    #: Sets of documents this run could not consult, each a sentence naming the
    #: entry, why, and a line to type (A7).
    #:
    #: The FIFTH honesty channel, and a fifth rather than a fifth use of
    #: `unenforced` for the reason `never_reached` is not `unmetered`: "the rule
    #: could not be evaluated" sends the author to the rule, "the corpus was
    #: never read" sends them to whoever runs the thing — and in between those
    #: two sentences the agent answers from what the model already knew.
    #:
    #: PACT does not retrieve. A host that does puts a sentence here when it
    #: could not, and `must-cite: yes` on such an entry FAILS THE TURN: the
    #: alternative is an answer that cites a document it never opened, which is
    #: the worst outcome available and the one that looks most like success.
    unretrieved: tuple[str, ...] = ()
    #: Ceilings this transport cannot promise to measure, so this run does not
    #: guarantee them. Reported rather than dropped: an author who wrote a spend
    #: cap and got no enforcement and no message has been told something untrue.
    #:
    #: *"Cannot promise"* and not *"did not enforce"*, because of one case that
    #: is real and would otherwise put this list at odds with `halted`. A
    #: transport bound to an **agent** rather than a model can be TOLD a figure
    #: it can never itself price: `A2ATransport` declares `prices_money = False`
    #: because no row in `models/catalog.yaml` can ever price somebody else's
    #: agent — and if that agent volunteers a cost anyway, `_meter_usage` adds
    #: it and `Limits.reached` fires on it like any other. So
    #: `cost-per-request-under` can appear here on a run that stopped at
    #: `cost-limit`. **That pair is the intended report, not an accident**: the
    #: ceiling bound this one exchange because somebody else chose to say what it
    #: cost, and this run could not promise it would bind the next. Dropping the
    #: stop to make the two lists agree would be the worse report — an author
    #: told at the END of a run that their cap was unmeasurable, having already
    #: gone through it. Pinned by
    #: `tests/test_a_remote_agents_bill_is_not_a_ceiling_we_hold.py`.
    #:
    #: One member is not about the transport at all: a spend cap NO spend can
    #: ever be at or above (`cost-per-request-under: NaN USD`, `inf USD`), which
    #: `Limits.__post_init__` refuses to carry as a ceiling, whichever of the
    #: four ways of building one it arrived by. It is here rather
    #: than on `never_reached` because that field is a fact about the BINDING —
    #: built out of the bound model's catalogue price — and this one is known
    #: from the written line before a transport is chosen; and because it exists
    #: in one port, so reporting it there would need a third channel invented in
    #: the second. *"Cannot promise"* is exactly what is true of it. Argued at
    #: `limits._nothing_can_reach`, pinned by
    #: `tests/test_a_spend_cap_nothing_can_reach_holds_nothing_and_says_so.py`.
    unmetered: tuple[str, ...] = ()
    #: Rules the author wrote that this run could not decide, each a sentence
    #: naming the file, the line, what was not applied and a line to type. A
    #: different fact from `unmetered` and so a different field: `unmetered` is
    #: a ceiling nobody could measure, this is a rule nobody could evaluate.
    _unenforced: tuple[str, ...] = ()
    #: What the interceptor CHAIN could not do, held as the chain's own live list
    #: rather than copied.
    #:
    #: A rewriting rule with nothing to run its program leaves the words as they
    #: were and records why — and the chain records it WHILE the run is going, at
    #: whichever moment that rule fires. Copying the list at any one point would
    #: catch whatever had happened by then and miss the rest, and this run has a
    #: dozen ways to end. So the list itself is carried and read at the end,
    #: which is the only reading that is right at every exit.
    chain_notes: list[str] = field(default_factory=list)
    #: Watches the author wrote that this run could not write down, because
    #: nothing said where the workspace is. Same door as `unmetered` and for the
    #: same reason: an author who wrote a watch and got neither a record nor a
    #: word about it has been told something untrue (T7).
    unwatched: tuple[str, ...] = ()
    #: Ceilings that were measured perfectly and can never be reached, each a
    #: sentence naming the file, the line, why, and a line to type.
    #:
    #: A fourth fact and so a fourth field, and the distinction is the whole
    #: point: `unmetered` says *nobody could count this*, and this says *the
    #: count is right and the answer is always zero*. `cost-per-request-under:
    #: 0.05 USD` bound to a model the catalogue prices at 0 USD in and 0 USD out
    #: — which five of the nine shipped rows are, because this machine serves
    #: them — reports as fully enforced and can never fire. Collapsing the two
    #: would tell the author "nobody could measure it", which is untrue and would
    #: send them looking for a transport rather than for `tokens-at-most:`.
    never_reached: tuple[str, ...] = ()
    #: What this run used, as far as the transport could say. Carried so a
    #: parent that delegated can charge a child's spend to the child's share —
    #: for a round `Grant.spend` had no caller outside tests, so the allowance
    #: the join policy computed was published on `step.delegate.started` and
    #: enforced by nothing.
    #: Facts that did not survive the turn, by name. Read from
    #: `Facts.something_happened` at the end, so a reviewer can see what a NEXT
    #: turn cannot rely on — a fact silently expiring is how a rule comes to
    #: decide on nothing later.
    facts_expired: tuple[str, ...] = ()
    #: What this run was actually asked, AFTER the author's interceptor chain
    #: ran on it. Not the string the caller passed: a workspace with a redaction
    #: rule has already had it rewritten by the time the run sees it, and this is
    #: what everything downstream — a promoted eval case above all — must read.
    asked: str = ""
    used: "Meter | None" = None
    #: Which stage of the authored loop ran at each step, in order. Deliberately
    #: NOT part of `trace()`: the trace is the cross-runtime contract that seven
    #: transports and a second language are held to byte-for-byte, and a field
    #: only one of them can produce would quietly weaken it. The path is how you
    #: see that the loop document did something.
    phases: list[str] = field(default_factory=list)
    #: One entry per step in which the conversation was tidied. Also outside
    #: `trace()`, for the same reason — but recorded, because Eve returns a bare
    #: message array and leaves "did it summarise, and does it actually fit now"
    #: unanswerable to its own caller.
    tidyings: list["Tidied"] = field(default_factory=list)

    @property
    def unenforced(self) -> tuple[str, ...]:
        """Rules the author wrote that this run could not carry out.

        Read rather than stored, so what the CHAIN could not do arrives with
        everything else. The chain records its own sentences while the run is
        going — a rewriting rule with nothing to run its program leaves the words
        as they were and says why — and the only reader was the `Chain` object,
        which a host never holds. So the run was silent about the one thing §8.5
        gave back to authors, on every run where it did not happen.

        Deduplicated, because one chain is shared across the steps of a run and a
        rule that could not fire on three of them is one thing to fix.
        """
        out = list(self._unenforced)
        for said in self.chain_notes:
            if said not in out:
                out.append(said)
        return tuple(out)

    @unenforced.setter
    def unenforced(self, value: "Sequence[str]") -> None:
        self._unenforced = tuple(value)

    @property
    def spent(self) -> float:
        """Money this run is known to have spent. Zero when nothing could say.

        Read off the meter rather than copied onto every return path, because
        the meter IS what the run spent and a second copy of it is how a figure
        comes to disagree with itself. Zero here means "nothing counted it",
        which `unmetered` states in words on the same result.
        """
        return self.used.money if self.used is not None else 0.0

    def as_record(self) -> dict[str, Any]:
        """This run, in the shape a case can be written from (AC-4.4).

        **Takes no argument, and that is the security property.** The first
        version took `asked: str` from the caller, and the obvious thing to pass
        is the question as typed — so promoting a run whose author had a
        `redact-card-numbers` rule wrote the card number into an eval case file
        that then gets committed. Measured on the worked example: the digits were
        in the file. The docstring claimed redaction came for free, and it did
        for the trace and not for the question.

        `asked` is now `RunResult.asked`, set by the harness from the message
        AFTER the interceptor chain ran — so there is no argument for a caller to
        get wrong, which is the only version of this that stays true.
        """
        return {
            "asked": self.asked,
            "output": self.output,
            "halted": self.halted,
            "trace": self.trace(),
        }

    def trace(self) -> list[dict[str, Any]]:
        """The comparable shape. Two transports agree iff these are equal."""
        return [
            {
                "index": s.index,
                "text": s.text,
                "tools": [{"name": c.name, "args": c.args} for c in s.tool_calls],
                "results": list(s.tool_results),
            }
            for s in self.steps
        ]


class Transport(Protocol):
    """What a framework must provide. Deliberately one method.

    Anything larger would let a framework's own control flow leak into the loop,
    which is exactly the divergence PACT exists to remove.

    Six things are *asked for* and never required, and all six follow the same
    rule: a transport that cannot answer says nothing and the run reports what it
    could not therefore enforce, rather than guessing a number.

    * `usage()` — `(tokens, money)` for the last call. The money half may be
      `None`: a token count is knowable whenever a call is made and a price only
      if the catalogue publishes one, and running the two together took
      `tokens-at-most` away from an author serving their own model on their own
      machine — the one place that ceiling is the only one left.
    * `prices_money` — whether the catalogue prices the bound model. A plain
      attribute rather than a method, because it is decided once at construction
      and never changes; absent means "the same as whether `usage()` exists",
      which is what a stand-in bound to no model honestly is. **Every transport
      that has a `usage()` should declare this**, and one that binds an AGENT
      rather than a model must: it has a `usage()` and can never have a row in
      `models/catalog.yaml`, so leaving it absent reported a spend cap over a
      remote agent as enforced and metered 0.00 forever.
    * `context_window()` — how many tokens this model can hold, which is what a
      `context-policy:` is measured against. A scripted stand-in has no window
      and no tokeniser, and a required field most implementers would have to
      invent a number for is worse than an absent one.
    * `model` — which model id this transport actually bound. Read only to
      compare against the author's `model:` pin: when the two disagree the run
      is executing on a model nobody asked for, and that is reported rather than
      substituted for.
    * `write_summary(text, model)` — one summarising call, made with a DIFFERENT
      model, which is what `context-policy.summarised-by:` asks for. Synchronous
      because tidying is: `Tidier.apply` decides mid-history what to fold, and a
      summariser it has to await would make every strategy async. The harness
      runs the whole of tidying off the event loop (`asyncio.to_thread`) so that
      staying synchronous costs a delegated sibling nothing. A transport that
      cannot re-bind reports `summarised-by` on `RunResult.unmetered`, the same
      door `usage` and `context_window` go out of.
    * `summary_usage()` — what the LAST summarising call cost. Separate from
      `usage()` because it is a different transport instance: `write_summary`
      binds a second model, so its bill never reaches `usage()` on this one. A
      transport that cannot say puts `summarised-by-cost` on
      `RunResult.unmetered`, which is the fifth thing to leave by that door and
      the reason the door exists.
    """

    name: str

    def lattice(self) -> dict[str, str]: ...

    async def model_call(
        self, system: str, history: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> tuple[str, list[ToolCall]]: ...


ToolFn = Callable[[dict[str, Any]], str]

#: What a CodeAct stage asks the locked room to run. Not a program name from the
#: tree — the code was written this second, by the model — so the room is asked
#: under a reserved word rather than a name an author could collide with.
RUN_CODE_IN_THE_ROOM = "pact:run-code"

#: What each kind of wait asks a person, when the author has named no question.
#:
#: These are WORDINGS, not option pairs. Every one of them wants a yes-or-no,
#: which is the point of G7: approval is not a kind of request here, it is the
#: commonest answer SHAPE, so an author who needs a figure or a choice of three
#: writes a `questions/` entry instead of needing a mechanism that does not
#: exist. Eve hardcodes the pair — "exactly two options named approve and deny"
#: — which is why its own budget prompt below has to impersonate an approval.
_DEFAULT_ASKS: Mapping[str, str] = {
    NEEDS_APPROVAL: "Please check this before it happens.",
    NEEDS_PERMISSION: "This needs a permission we do not have. Grant it?",
    OUT_OF_BUDGET: "This reached its limit before it finished. Keep going?",
    CONTEXT_TOO_LONG: "The conversation no longer fits. Carry on with less of it?",
    # The fifth, and the one that had nothing. A run waiting on a teammate this
    # process cannot run parks like every other wait and, with no question named
    # for it, rendered an empty string — which from the outside is
    # indistinguishable from a run that has hung, the one outcome `shown.py`'s
    # own rule says must never happen. §7.14 WAIT-2 has no row configuring this
    # reason, so the wording is here rather than in a file: there is nowhere in
    # the schema to write it, deliberately, because a teammate is not a person
    # to ask.
    WAITING_FOR_ANOTHER_AGENT: "This is waiting for another agent to answer.",
}


#: What PACT picks when the author left `answers-with-mode:` out. Its help
#: promises exactly this — *"PACT picks from the shape you declared above, and
#: records what it picked"* — and for a round nothing picked anything.
#:
#: `prompted` and not `native-json-schema`, for two reasons that are the same
#: reason: it is the only mode all seven transports can honour, and the only one
#: that needs nothing off this machine (D17).
CHOSEN_ANSWER_MODE = "prompted"

#: Modes that constrain the answer at the provider rather than in the prompt.
#: No transport here implements either, so they are REPORTED rather than
#: silently served as prose — a run that used prompting where the author asked
#: for a schema is the silent degradation T7 forbids.
MODES_NOTHING_HERE_DELIVERS = ("native-json-schema", "tool")


#: Every `run()` parameter that has an AUTHORED source, and the expression in
#: `run` that derives it. This is the register the root cause needed.
#:
#: The defect it closes: `run()` takes sixteen optional objects, and "use what
#: the author wrote when the host passes nothing" was a separate hand-written
#: line for each. There were seven such lines for sixteen parameters. Authored
#: configuration and host overrides shared one channel, so derivation was
#: optional, per-parameter, and **invisible when omitted** — and the test that
#: would notice is the one nobody writes, because injecting the object is easier
#: than loading a document. Six mechanisms shipped built, tested and unreachable
#: that way; `remembers:` was the sixth, and it landed in the change whose
#: purpose was to fix this class of defect.
#:
#: Splitting the channel into a `Bound` object was the first plan. It does not
#: survive contact with two of the sixteen: `summarise` and `tidy` close over
#: this run's `meter`, so they cannot be built before the run exists, and an
#: object holding fourteen-of-sixteen would leave exactly the invisible gap it
#: was for. A register covers all sixteen uniformly instead, and
#: `test_the_boundary_between_a_document_and_a_run_is_declared` makes it total:
#: **a new parameter that is in neither this map nor `SUPPLIED_BY_THE_HOST` fails
#: the suite**, so adding a mechanism forces the decision to be written down.
DERIVED_FROM_THE_DOCUMENT: dict[str, str] = {
    "chain": "spec.chain",
    "teamwork": "spec.teamwork",
    "loop": "spec.loop",
    "asking": "spec.asking",
    "tidy": "spec.tidier",
    "team_budget": "spec.limits.cost_per_request_under",
    "summarise": "_summariser(transport, spec",
}

#: Parameters with no authored source, because they are facts about the process
#: rather than about the agent. A name here is a DECISION that no document
#: describes it — not an omission.
#:
#: `needs_approval`, `approved`, `gates` and `answer` are the shorthand a host
#: uses to answer a wait; the author's own version of that decision is
#: `policy:`, which arrives through `asking` above. `run_inputs` is the value
#: side of `run-inputs:` — the author declares the keys, the surrounding system
#: supplies what goes in them.
SUPPLIED_BY_THE_HOST: frozenset[str] = frozenset({
    "transport", "user_input", "tool_impls", "bus", "now", "clock",
    "resume", "answer", "approved", "needs_approval", "gates",
    "ask_member", "run_inputs",
    # The value side of `remembers:`. The NAMES, their shapes and who may write
    # them are all authored and reach `AgentSpec.facts`; what this conversation
    # already knows is not a fact about the document at all — `lasts:
    # one-conversation` is longer than one `run()`, so the store is the host's.
    "remembered",
    # The activation meter behind `limits.asks-itself-at-most:`. The FIGURE is
    # authored and reaches `Limits.asks_itself_at_most`; this parameter is the
    # count of what already happened on this request, which no document can
    # know. It exists as a parameter so `delegate_by_running` can hand the
    # root's meter to the runs it starts — a host passes nothing.
    "at_work",
    # The transport serving `model-for-checking:`. The MODEL NAME is authored;
    # which transport serves it is not something any document can say, for the
    # same reason `transport` itself is here.
    "checking_transport",
    # What a retrieval runtime looked up (A7). PACT does not retrieve, embed,
    # index or chunk — the §4 declared-and-delegated pattern — so which passages
    # came back is a fact only the host has. What the DOCUMENT says is which sets
    # of documents exist, how they are found and whether a source must be cited,
    # and all of that reaches `AgentSpec.knowledge`.
    "retrieved_by",
    # What starts a carried program (P6/P7). The DOCUMENT says which programs
    # exist, what they take, what they answer with and what they may spend; what
    # can actually start one is a property of the machine, exactly as `transport`
    # and `tool_impls` are. Nothing in `src/` builds one — this port does not
    # bundle a WebAssembly engine, because fetching one would put a network
    # dependency in the core of a project whose promise is that everything runs
    # air-gapped (D17), and vendoring one would make the portable artifact carry
    # a runtime it cannot keep current.
    #
    # A host that has one passes it. A host that has not gets the sentence:
    # every program this agent could have reached is named on `unenforced`
    # before the first call, because the failure otherwise is `error: no tool
    # named ...`, which reads as a mistake in the author's own file.
    "run_program",
})


def _and_list(names: "Sequence[str]") -> str:
    """`a`, `a and b`, `a, b and c` — for a sentence a customer reads."""
    quoted = [f"'{n}'" for n in names]
    if len(quoted) <= 1:
        return quoted[0] if quoted else ""
    return f"{', '.join(quoted[:-1])} and {quoted[-1]}"


def _projection_for(
    spec: AgentSpec, tool: str, args: "Mapping[str, Any]"
) -> str:
    """The program that shortens what this call answered, if the author named one.

    A call carries which ACTION it is (`ir._takes` declares `action:` on every
    tool with an `actions:` block), so a tool offering several actions projects
    only the one the author wrote it on. A call that names no action matches a
    projection only when the tool has exactly one — otherwise there is nothing to
    say which projection was meant, and guessing is how the wrong one runs.
    """
    named = [(where, prog) for where, prog in spec.projections if where.startswith(f"{tool}/")]
    if not named:
        return ""
    action = str(args.get("action", "")).strip()
    if action:
        for where, prog in named:
            if where == f"{tool}/{action}":
                return prog
        return ""
    return named[0][1] if len(named) == 1 else ""


async def run(
    spec: AgentSpec,
    transport: Transport,
    user_input: str,
    tool_impls: dict[str, ToolFn] | None = None,
    needs_approval: frozenset[str] = frozenset(),
    resume: "Suspension | None" = None,
    #: What a retrieval runtime looked up, by the name of the set it looked in
    #: (A7). PACT retrieves nothing itself; a host that does hands this in, and
    #: everything declared and absent from it is reported on
    #: `RunResult.unretrieved`. `None` means nothing retrieved anything, which is
    #: the honest state on a machine with no index.
    retrieved_by: "Mapping[str, Sequence[str]] | None" = None,
    approved: frozenset[str] = frozenset(),
    bus: Bus | None = None,
    chain: Chain | None = None,
    gates: Mapping[str, str] | None = None,
    answer: "Resumption | None" = None,
    now: float | None = None,
    ask_member: "Asker | None" = None,
    teamwork: "Teamwork | None" = None,
    team_budget: float | None = None,
    loop: "Loop | None" = None,
    tidy: "Tidier | None" = None,
    summarise: "Summariser | None" = None,
    clock: Callable[[], float] | None = None,
    asking: "Gate | Mapping[str, Question] | None" = None,
    run_inputs: Mapping[str, Any] | None = None,
    checking_transport: Transport | None = None,
    #: How many times this request has already put each agent to work, by name —
    #: the meter `limits.asks-itself-at-most:` is spent against. Created fresh
    #: at the root run and shared down through `delegate_by_running`, so a
    #: circle spends one figure per ACTIVATION rather than one per level of
    #: nesting. Hosts pass nothing; a document that never writes the line fills
    #: the dict and nothing ever reads it.
    run_program: "Callable[[str, dict[str, Any]], str] | None" = None,
    at_work: dict[str, int] | None = None,
    #: What this conversation already knows, by the names the agent's own
    #: `remembers:` block declares — the value side of `bind: remembers.<n>`.
    #:
    #: A host parameter and not a document one, because `lasts:
    #: one-conversation` outlives a single `run()` and where a conversation's
    #: memory is KEPT is the surrounding system's (§4). PACT says what is
    #: remembered, what shape it is, and who may write it; the store is
    #: somebody else's, exactly as the model and the tools are.
    #:
    #: A name nobody declared is ignored rather than held, the same rule
    #: `Facts.record` follows on the way out: a fact the author did not write
    #: down is not one a run may invent.
    remembered: Mapping[str, Any] | None = None,
) -> RunResult:
    """Drive `spec` to completion over `transport`.

    Halts on: a step with no tool calls (`final`), one of the author's ceilings
    (`step-limit`, `tool-call-limit`, `time-limit`, `cost-limit`,
    `token-limit`), a rule stopping it (`stopped-by-rule`), or a wait for
    something outside the run (`suspended`). All of them are recorded
    distinctly, because a run that stopped because it ran out of budget is not
    the same as one that finished, and reporting them alike would be the silent
    degradation T7 forbids.

    Every ceiling comes from `limits:` and carries the author's own
    `when-it-runs-out` (G2). Eve has none of them — no step, turn, wall-clock or
    spend limit exists anywhere in it — so a run there ends only by answering or
    by exhausting a token budget, and the two are reported the same way.

    `clock` is separate from `now` on purpose: `now` is one timestamp for the
    whole run, used to decide whether a *wait* has expired, while the wall-clock
    ceiling needs a reading that advances. A test passes a fake one; nothing
    else ever does.

    `needs_approval` and `approved` are shorthand for the commonest wait. They
    fold into `gates` and `answer` on the two lines below and have no separate
    code path — the same relationship `schedule` has to `port` in the schema.

    `ask_member` is what makes the team runnable *here*. Given one, the members
    the model asks in a step are joined under the author's own `teamwork.yaml`
    (G8) instead of parking the run; without one, a teammate is still work
    happening elsewhere and the run suspends for it as before. `teamwork=` is the
    host's override; nothing has to be passed for the author's `waits-for:`,
    `starts:`, `shares:` and `if-someone-fails:` to be the ones that run.

    What the team may spend between them is the author's
    `cost-per-request-under`, and it executes with nothing passed at all — the
    same shape `loop`, `tidy` and `summarise` have. `team_budget=` remains the
    host's override and still wins, including `team_budget=0.0` to mean "do not
    meter them at all". ONE pot serves the whole request: it is built here and
    handed to every join, and what the team spends is added to this run's own
    meter, so one written ceiling bounds the parent, its team and their teams
    rather than being one ceiling per agent per step.

    The author's approval policy stops calls with nothing passed at all. `gated`
    below is seeded from `needs_approval=`/`gates=` for a host that has its own
    reason, and then from `policies/<name>.yaml` through `spec.asking`, decided
    against the arguments the model chose — so `more-than: 200 USD` means 200 in
    both directions. A rule naming one ACTION of a tool is decided by the action
    the call carries, so `zendesk/reply` stops a reply and lets `read-ticket`
    through. A call that names no action at all is reported on
    `RunResult.unenforced` rather than guessed at either way; see
    `Rule.decidable`.

    `loop` is the shape of the thinking, and it comes from the author's document
    (G1). Every step below belongs to a named stage; which tools exist and what
    the model is told differ per stage, and where to go next is the stage's own
    `then:`. Passing nothing uses the agent's own — which is `pact:loop/standard`
    unless it says otherwise, and executing that must reproduce exactly what this
    harness did before loops were readable at all.

    The author's `context-policy:` (G3) executes with nothing passed at all.
    `tidy` is the same override `chain` and `loop` are: a host may hand in its
    own, and handing in nothing uses the agent's own line. For a round this
    argument was the ONLY door — `spec.context_policy` was resolved, read by
    nobody, and the worked example's `context-policy: long-threads` tidied
    nothing unless a host wrote Python to build a `Tidier`. That is "experts
    write code for that", which D14 rules out for every capability in the core,
    and it is the same defect this file confessed to for interceptors one round
    earlier. `summarise` is the runtime's summariser; the three rungs that need
    no model run without it.

    `run_inputs` is what the SURROUNDING SYSTEM supplies for this run — the
    agent's own `run-inputs:` keys — and it is how the author's `bind:` lines
    execute. Both halves were validated at check time and neither was carried
    out: measured on the worked example, the payments tool received
    `{order-number, amount, action}` and never `customer-id`, so *"whose order"*
    went on being something nobody supplied. A bound argument is merged into the
    call AFTER the interceptor chain has seen it, so a redaction rule still reads
    the real value; a `bind:` nothing fills is named on `RunResult.unenforced`
    rather than passed as an empty string.
    """
    tool_impls = tool_impls or {}
    # What this run has already spent a same-request key on. The author's own
    # `same-request-key:` lines, with nothing passed in — the same door `chain`,
    # `loop`, `tidy` and `teamwork` come through, and for the same reason: a
    # guarantee that needs a host to construct an object is "experts write code
    # for that", which D14 rules out for every capability in the core.
    once = Ledger(spec.request_keys) if resume is None else Ledger.resumed(
        spec.request_keys, resume.spent_keys
    )
    supplied: dict[str, Any] = dict(run_inputs or {})
    # What the conversation already knows, seeded into the one store `remember-as:`
    # writes to and `bind: remembers.<n>` reads from. Through `record` rather than
    # into `held` directly, so an undeclared name is dropped here exactly as it
    # would be on the way out.
    for _known, _value in (remembered or {}).items():
        spec.facts.record(str(_known), _value)
    # 02P A1: `{{run-inputs.<n>}}` and `{{remembers.<n>}}` in the instructions
    # are filled here, once, before the model reads a word — from what this run
    # was handed and what the conversation already knows. Strict: a hole with no
    # value raises `holes.Unfilled` naming it, because literal braces in front
    # of a model are the silent mis-translation the holes exist to end.
    if spec.holes:
        spec = replace(
            spec,
            instructions=fill(
                spec.instructions, run_inputs=supplied, remembers=spec.facts.held
            ),
        )
    bus = bus or Bus()
    #: Agents this request may put to work because a VALUE named one — the
    #: dynamic half of `team:` (P4). `{name of the agent: why it is here}`.
    #:
    #: `agent` is the one answer shape whose value is a name from this same tree
    #: rather than a datum, and until this line it was validated as a plain key
    #: and then dereferenced by nothing: a document could declare
    #: `second-look: agent`, a ticketing system could supply `night-shift`, and
    #: the only agents a run could hand work to were still the static `team:`
    #: keys. The shape existed and could not be put to work.
    #:
    #: The rule that makes admitting it safe is enforced at the delegation site,
    #: in `delegate_by_running.ask`, and it is the static rule relocated: the
    #: loader legalises a `team:` circle only when every member on it writes
    #: `limits.asks-itself-at-most:`, and a dynamically named agent is on no
    #: static circle the loader could have looked at, so the obligation moves
    #: from the circle to the receivable agent. Admission is what carries the
    #: fact that far; refusal is not made here, because here is not where a
    #: member's own `limits:` is read and a refusal that never becomes a member
    #: FAILURE would take the whole run down instead of reaching the author's
    #: `if-someone-fails:`.
    #:
    #: A name the author already wrote under `team:` is left alone. The sentence
    #: there is the author's own and it is what the model reads when choosing,
    #: so replacing it with a generated one would make a documented teammate
    #: describe itself worse whenever the surrounding system happened to name it.
    named_by_value: dict[str, str] = {}
    if ask_member is not None:
        for declared in spec.agent_valued_inputs:
            try:
                chosen = AN_AGENT.read(supplied[declared])
            except (KeyError, Rejected):
                # Nothing supplied, or not a name. A declared input the
                # surrounding system did not fill is already reported through
                # `bind:`/`unenforced`, and a value that is not a plain key was
                # never a name this workspace could hold — neither is a reason
                # to refuse a run that may not delegate at all.
                continue
            if chosen not in spec.team:
                named_by_value.setdefault(
                    chosen, f"chosen for this request by {declared}"
                )
    # `asks-itself-at-most:`'s meter. Counting is unconditional — one increment
    # per activation of this spec, the root's own being the first — and reading
    # it is not: only `delegate_by_running` consults it, and only for a member
    # whose author wrote the figure. A dict rather than anything on the call
    # stack, because sequential re-asks must spend too: a member that returned
    # and is asked again is a new activation at the same depth.
    at_work = {} if at_work is None else at_work
    at_work[spec.name] = at_work.get(spec.name, 0) + 1
    if ask_member is not None:
        # `Asker` takes one argument, and the spend check belongs where the
        # member's own `limits:` is read — inside `delegate_by_running.ask`,
        # which this function never sees. The meter rides the grant to get
        # there; an asker handed a grant it never looks at behaves as before.
        inner_ask = ask_member
        #: Frozen here rather than read live, so a grant carries what this run
        #: admitted and not whatever the dict says by the time it is asked.
        by_value = frozenset(named_by_value)

        async def sharing_the_meter(grant: Grant) -> str:
            grant.at_work = at_work
            # HOW this member was reached, which is what decides whether it owes
            # a figure of its own (P4). It rides the grant for the reason the
            # meter does: `Asker` takes one argument, and the check belongs
            # where the member's own `limits:` is read. An asker that never
            # looks at it behaves exactly as before.
            grant.named_by_value = by_value
            return await inner_ask(grant)

        ask_member = sharing_the_meter
    # The author's own rules, unless a caller supplied its own set. Read from
    # the agent's `interceptors:` line the same way its loop and its context
    # policy are — for a round this line said `chain or Chain()`, so the two
    # documents in the worked example loaded, validated and did nothing, and
    # the card numbers they say they stop reached the model.
    chain = spec.chain if chain is None else chain
    # AND THE RUNNER THE CHAIN COULD NOT HAVE BEEN BUILT WITH. `AgentSpec.
    # from_document` is handed a loaded document and nothing else (P-1), so it
    # has no host to ask for one; `run()` has one and never passed it on. Through
    # the shipped entry point a rewriting rule therefore never rewrote anything —
    # measured, `run(..., run_program=shout)` returned the words unchanged — and
    # the sentence the chain recorded about it reached nobody, because only the
    # chain object held it and a host does not hold the chain.
    chain.use_runner(run_program)
    now = time.time() if now is None else now
    clock = clock or time.monotonic
    # The author's own join policy, unless a caller supplied one. `is None`, not
    # `or`, matching the `chain` line above: for a round this read
    # `teamwork or Teamwork()` and `Teamwork.from_document` had no caller in
    # `src/` at all, so `examples/refund-desk/agents/refund-desk/teamwork.yaml`
    # loaded, validated, and was replaced at this line by a policy nobody wrote.
    # Measured on the shipped example: the 60/40 shares came out 0.025/0.025,
    # and a failing `fraud-checker` returned `final` with the refund approved —
    # which the file's own comment says must never happen. The pot reached the
    # run a round before the rules for dividing it did.
    teamwork = spec.teamwork if teamwork is None else teamwork
    # What the team may spend between them, from the author's own `limits:`.
    # Read once, here rather than at the call site, so there is one place that
    # decides where the number came from.
    #
    # Eve has no spend cap of any kind, so the only thing it can share out
    # between children is *tokens*, and it shares them evenly because there is
    # no authored money for a share to be a share OF. PACT's ceiling is money
    # and it is `cost-per-request-under` in the agent's own `limits.yaml`, so
    # `divides-the-budget: by-share` divides the author's line rather than a
    # number a host had to know to pass in.
    #
    # For a round this read `team_budget: float = 0.0` and NO caller anywhere
    # supplied it: the worked example's 60/40 shares were parsed, validated and
    # applied to an empty pot, and every `step.delegate.started` truthfully
    # carried `allowance: inf`. That is "a host writes code for that", which
    # D14 rules out for every capability in the core — the same defect this
    # file confessed to for interceptors, and again for `context-policy:`.
    #
    # `is None`, not `or`: a host passing 0.0 means "do not meter them", and
    # `or` would overwrite that with the author's ceiling. An UNSET ceiling
    # stays unmetered too, because `Pool` reads a total of zero as no budget
    # declared — a limit nobody wrote must never become a limit of nothing.
    if team_budget is None:
        team_budget = spec.limits.cost_per_request_under or 0.0
    # ONE pot for the whole request, built here and handed to every join. It was
    # built inside `ask_team`, which is called from inside the step loop, so a
    # script that asked the team on two steps was granted the author's ceiling
    # twice — measured: 0.10 USD spent under a written 0.05 USD cap, with nothing
    # refused anywhere. `cost-per-request-under` is help-texted as "the most one
    # REQUEST may cost", so a fresh pot per step is not a reading of it.
    #
    # Over the whole team rather than over whoever the model asked in this step,
    # for the same reason: a member asked on step four must not be granted a
    # share sized as though the team were smaller.
    # Over everyone this request may ask, including whoever a value named: a
    # member admitted by value spends the parent's money like any other, and
    # sizing the shares as though the team were smaller is the same overstatement
    # the per-step pot was. Empty when nothing was named by value, which is every
    # document that declares no `agent`-shaped run-input.
    team_pot = Pool(
        team_budget,
        teamwork.divides_the_budget,
        sorted({*spec.team, *named_by_value}),
        teamwork.shares,
    )
    # `is None`, not `or`, matching `chain` and `teamwork` above. A `Loop` is
    # always truthy so nothing was losing its stages today — but this is the
    # pattern that made `chain or Chain()` and `teamwork or Teamwork()` discard
    # two documents the author had written, and one spelling for one rule is
    # what keeps the next one from being the falsy case.
    loop = spec.loop if loop is None else loop
    # Which way the author's `answers-with:` is put to the model, and what to say
    # when this process cannot do it the way they asked. `answers-with:` is
    # `tier: core`, sits in the worked example, is emitted by `pact show` — and
    # was read by nothing, so every scripted answer in the eval suite hand-writes
    # the format the document already specified.
    answer_mode = spec.answers_with_mode or CHOSEN_ANSWER_MODE
    shape_to_ask_for = spec.answers_with if answer_mode == CHOSEN_ANSWER_MODE else {}
    unhonoured_mode: tuple[str, ...] = ()
    # And the second model, if the author asked for one and the host supplied it.
    # Reported rather than assumed either way: `model-for-checking:` had zero
    # readers in any runtime for a session, so the field validated, held itself
    # against `loop:`, and changed nothing about any run.
    if spec.model_for_checking and checking_transport is None:
        unhonoured_mode += (
            f"model-for-checking: {spec.model_for_checking} — every stage used "
            f"`{spec.model or 'the bound model'}`, because this run was handed one "
            f"transport and a second model needs a second one. The checking stages "
            f"were done by the same model as the doing. fix: nothing to type — the "
            f"system running this has to serve `{spec.model_for_checking}` too and "
            f"pass it in.",
        )
    if spec.answers_with and answer_mode in MODES_NOTHING_HERE_DELIVERS:
        unhonoured_mode = (
            f"answers-with-mode: {answer_mode} — the answer was not constrained "
            f"at the model, because no transport here can do that. The shape you "
            f"wrote under `answers-with:` held nothing on this run. fix: write "
            f"`answers-with-mode: {CHOSEN_ANSWER_MODE}`, which asks for the same "
            f"shape in the instructions and works on every target.",
        )
    # The line `chain` got, and `loop` got, and this did not. Without it the
    # author's `context-policy:` was a setting the loader resolved and nothing
    # read: `spec.context_policy` was set from the document and every `Tidier`
    # in the repository was built by a test.
    #
    # `summarise` gets the same treatment one level down. `summarised-by:` names
    # a second model, and for a round the only way to make that line do anything
    # was for a host to write Python and hand a callable in — so the worked
    # example's `summarise-older` rung silently fell through to the bottom of
    # the ladder on every run. D14 rules out "experts write code for that" for
    # every capability in the core.
    def _charge_summary(cost: "tuple[int, float] | None") -> None:
        """What the summarising model cost, on the meter the ceiling reads.

        `summarised-by:` names a SECOND model, so the call goes out over a second
        transport that `_meter_usage` never sees. Left alone it is one model call
        per tidy — potentially one per step on a long thread — charged to nothing,
        under an author who wrote `cost-per-request-under`. `meter` is rebound on
        resume and this reads it at call time, so a resumed run charges the meter
        it actually came back with rather than the one it started under.

        `None` means the second transport made its call and nobody could price
        it, which is a different fact from its having cost nothing. It used to
        arrive as `(0, 0.0)` — reachable from the shipped distribution with one
        line, since `models/catalog.yaml` publishes `gpt-5.4` as `cost: unknown`
        — so a `summarised-by:` model spent outside a cap that reported itself
        fully enforced. Reported late rather than at the top of the run because
        that is the first moment anything knows: `summary_usage` is probed once,
        before any summarising model is bound.
        """
        if cost is None:
            if "summarised-by-cost" not in result.unmetered:
                result.unmetered = result.unmetered + ("summarised-by-cost",)
            return
        tokens, money = cost
        meter.tokens += int(tokens)
        meter.money += float(money)

    summarise = (
        summarise if summarise is not None else _summariser(transport, spec, _charge_summary)
    )
    tidy = (
        tidy
        if tidy is not None
        else spec.tidier(_window(transport, spec.model, spec.workspace), summarise)
    )
    #: Steps a person has already said to carry on past, oversized. One step
    #: each, so a second overflow is a second decision rather than a standing
    #: permission nobody remembers granting.
    carried_on_at: set[int] = set()

    # Who this run can ask for help without leaving the process. The sentence
    # the author wrote under `team:` is what the model reads when choosing, so
    # it is carried through rather than replaced with a generated one.
    delegates: dict[str, str] = dict(spec.team) if ask_member is not None else {}
    # Plus whoever a value named (P4). `named_by_value` is already empty unless
    # `ask_member` is not None, so this line adds nothing to a run that cannot
    # delegate at all — a name admitted where nothing can run it would be a tool
    # offered that answers to nobody.
    delegates.update(named_by_value)

    # Why each name is gated. One map for every reason a run can wait, so the
    # branch below is written once instead of once per park kind.
    gated: dict[str, str] = {n: NEEDS_APPROVAL for n in needs_approval}
    gated.update(gates or {})
    # A teammate with no local implementation is not a missing tool; it is work
    # happening somewhere else, and waiting for it is a suspension like any
    # other. Eve needs a bespoke park kind and a child-turn state key for this.
    for member in spec.team:
        if member not in tool_impls and member not in delegates:
            gated.setdefault(member, WAITING_FOR_ANOTHER_AGENT)
    # There is deliberately no fourth seeding here for a connection the author
    # wrote `asks-to-connect:` about, and the absence is now a decision that has
    # been made rather than one outstanding. It was tried here once and measured:
    # a wait seeded into this map is one the eval runner cannot turn off, because
    # `Gate.asking_only()` reaches `spec.asking` and nothing else, so every scored
    # case touching `payments` came back "did not answer" and the model under test
    # was blamed for a connection nobody had granted. And this map holds ONE
    # reason per name, while `payments` at 300 USD needs both an approval and a
    # connection consent. So the consent lives on the GATE — `Rule.gates` with
    # `Rule.for_reason`, ordered by `questions.ASKED_IN_ORDER` — where
    # suppression and precedence are one place instead of two. §7.14 gap (1).

    # The author's question for each thing that can be waited on, by name. Where
    # there is none the wait asks a plain yes-or-no, which is what `approved=`
    # below is shorthand for — approval has no separate path here because it is
    # not a separate kind of request (G7).
    # One rule per line the author wrote, not one per tool. `for_call` picks
    # between two rules over the same tool from the arguments the model chose,
    # so a 210 USD refund gets the 200 USD question rather than the 500 USD one
    # the flat map used to leave standing.
    #
    # `spec.asking` is the author's own, and it is the default rather than the
    # override — the same shape `loop`, `tidy` and `chain` have. Until this line
    # existed `questions_for` was defined in `src/` and called only from tests,
    # so `policies/approvals.yaml` needed a host to hand its own set in, and its
    # opening sentence — "This is enforcement, not a note in the instructions" —
    # was untrue of every run.
    asking = Gate.of(spec.asking if asking is None else asking)

    given: dict[str, Any] = {n: "approve" for n in approved}
    # What earlier waits in this run were already let past. ONE call can stop
    # twice for two reasons — `payments` needs the connection consent in
    # `resources/payments-server.yaml` and then the approval in
    # `policies/approvals.yaml` — and a resume carries only the answer to the wait
    # it is resuming, so without this the consent granted at the first park is
    # missing at the second and the run asks for it again, and again.
    if resume is not None:
        given.update(resume.granted)
    if answer is not None:
        if resume is not None and not resume.accepts(answer):
            raise WrongAnswer(
                "this answer was written for a different wait, so it has not been "
                f"applied. It answers {answer.correlation_key!r}; this run is "
                f"waiting on {resume.correlation_key!r} ({resume.reason}). "
                "Fetch the current question and answer that one."
            )
        given.update(answer.values)

    tool_defs = [
        {"name": t.name, "description": t.description, "parameters": t.parameters}
        for t in spec.tools
    ] + [
        # Every teammate is offered, whether or not this process can run them.
        # A model that is never told a teammate exists can never ask for one, so
        # gating a name nobody can say would leave `waiting-for-another-agent`
        # unreachable. The sentence is the author's own from `team:`.
        {"name": m, "description": f"ask {m} for help: {brief}".rstrip(": "), "parameters": {}}
        for m, brief in sorted(spec.team.items())
    ] + [
        # And whoever a value named (P4), after the author's own and in name
        # order, so one document plus one set of run-inputs is one tool list on
        # every transport. The sentence is generated because there is no
        # authored one to carry — the author did not know who this would be —
        # and it says where the name came from rather than what the agent does,
        # which is the only thing this run actually knows.
        {"name": m, "description": f"ask {m} for help: {brief}", "parameters": {}}
        for m, brief in sorted(named_by_value.items())
    ]
    # A stage may only narrow what the agent already has. Checked once, before
    # the first model call, so a typo in a branch taken on the fortieth step
    # fails on the first one instead.
    loop.check_against(
        tuple(t.name for t in spec.tools) + tuple(spec.team),
        skill_names=spec.skill_names,
    )

    result = RunResult(output="")
    # The chain's own live list, so what a rule could not do is reported by the
    # RUN and not only by an object the host never sees.
    result.chain_notes = chain.unenforced
    # The author's own `watch/` documents, attached to the bus this run emits
    # on. The OBSERVE half of the event lattice, and deliberately a kind of its
    # own rather than an interceptor with an empty `may:` — Eve's 28 lifecycle
    # events are all observe-only and it has no mutating hook at all, so keeping
    # the two constructs apart is what lets the safe one be beginner-tier
    # (`tier: core` on every field) while the dangerous one is not
    # (`workspace.interceptors` is `tier: expert`). Folded together, turning a
    # thing that looks into a thing that changes would be one word added to a
    # `may:` list in a document nobody thought needed reviewing.
    #
    # Here rather than behind an argument, for the reason `chain` is: for a round
    # `Bus.on(pattern, fn)` took a PYTHON CALLABLE and was the only way to watch
    # a run, so observing — the strictly safer power — was a host capability
    # while mutation was already authorable. D14 rules out "experts write code
    # for that" for every capability in the core, and this was the one it could
    # not reach.
    result.unwatched = spec.watches.subscribe(bus, spec.workspace)
    # Whatever the gate could not decide before the run began. The action-scoped
    # half of this moved into the step body, where the call is: `Gate.unenforced`
    # is the load-time channel and `Gate.undecided_on` the per-call one, and both
    # arrive on this one field.
    #
    # There is no longer a sentence here about a connection the author gated and
    # this run does not: the run does. `AgentSpec.connection_consents` and
    # `ir._consents` are deleted rather than left beside a working gate — a
    # report that an authored line is unenforced, printed by a runtime that
    # enforces it, is the same untruth pointing the other way. Nor is there one
    # about a `spends-money: yes` action no approval rule names: that is a fact
    # about two DOCUMENTS read together, which `pact check` now says
    # (`pact-loader::money`) before a customer is waiting rather than a run
    # saying it afterwards.
    # Plus the author's answer shape when this process could not constrain it
    # the way they asked. Same door as every other line they wrote that held
    # nothing, so a reviewer finds all of them in one place.
    # Plus every `stops-being-true-when:` trigger nothing here can raise. A fact
    # whose only trigger is `the file changes` never goes stale, because no part
    # of PACT watches a file — and the author who wrote it believes otherwise.
    result.unenforced = (
        asking.unenforced + unhonoured_mode + tuple(spec.facts.never_raised())
        # And whatever the TRANSPORT says the author wrote that it cannot carry
        # out. Asked for the same way `usage` and `apply_settings` are — a
        # transport that has nothing to say says nothing — and the case it exists
        # for is `A2ATransport`, where the remote agent owns the loop so the
        # author's stages, rules and ceilings decide nothing.
        + tuple(getattr(transport, "unenforced", tuple)() or ())
    )
    pending: tuple[ToolCall, ...] = ()
    pending_text: str = ""
    already: dict[str, str] = {}
    limit = spec.max_steps

    # Every stage an interceptor can send this run to, held against the loop
    # here rather than when a rule fires. `Loop.check_against` states the
    # standard one line above — "a typo in a branch taken on the fortieth step
    # fails on the first one instead" — and a redirect destination is by
    # construction the rarely-taken branch it describes. It was exempt for a
    # round: a one-character typo cost a model call and a real refund before the
    # loop's own diagnostic surfaced it.
    for name in sorted(chain.destinations()):
        if _sent_to(loop, name, result, bus, 0) is None:
            return result

    # What this run has spent. Tokens and money are only knowable if the
    # transport says what a call cost; a ceiling over something nobody is
    # counting is reported as unenforced rather than quietly skipped, because an
    # author who wrote a spend cap and got neither enforcement nor a word about
    # it has been told something untrue (T7).
    meter = Meter(started=clock())
    result.used = meter
    reports_usage = callable(getattr(transport, "usage", None))
    # Two questions, not one. A transport can count tokens on every call it makes
    # and still be bound to a model the catalogue publishes no price for — that
    # is what a locally-served row with a window and no `cost:` block IS, and it
    # is what an air-gapped workspace adds to its own `models/catalog.yaml`. For
    # a round the two were the same question, so such a row silently lost
    # `tokens-at-most` as well: the one ceiling whose help text promises it
    # "still bites when there is no price list". A transport that says nothing
    # about pricing is taken to be as silent about money as it is about tokens,
    # which is exactly what the stand-in bound to no model is.
    #
    # **The default is `False`, and it used to be `reports_usage`.** Reading the
    # money answer off the TOKEN answer meant a transport that has a `usage()`
    # and can never be priced was taken to price its calls. `A2ATransport` is
    # exactly that: bound to an agent rather than a model, so no row in
    # `models/catalog.yaml` can ever describe it, and its own `usage()` says the
    # answer is "almost always None". A spend cap over a remote agent was
    # therefore reported as ENFORCED and metered 0.00 for the life of the
    # workspace — the outcome `transports/_metering.py` opens by forbidding.
    #
    # Declaring `prices_money = False` on that one transport fixed the INSTANCE.
    # It did not fix the class, and the class is where the reachable surface is:
    # nothing in `src/` constructs a transport, so every transport that ever runs
    # is written by a host or copied from the out-of-tree exemplar — and that
    # exemplar shipped the same `usage()`-without-a-declaration for a round,
    # measured, after the instance fix landed. A default that grants a capability
    # to everyone who has not thought about it hands the cost of not having
    # thought about it to the AUTHOR, who wrote a spend cap and cannot read this
    # file. D14: *"expert users write code for this" is not an acceptable answer
    # for any capability in the core.*
    #
    # **`False` is not the mirror-image lie, and that is what changed.** The
    # objection to it was that four stand-ins in this suite return a real money
    # figure from `usage()` and declare nothing, so they would report a cap as
    # unmeasurable while the meter ticked. That objection was written against
    # `RunResult.unmetered`'s OLD wording, *"did not enforce"* — under which it
    # holds. The field now says *"could not promise to measure"*, which is
    # exactly and only what is true of a transport that never said it could
    # price: the harness has no promise, because nobody made it one. The four
    # stand-ins now declare `prices_money = True` (`Costing` in
    # tests/test_termination.py and tests/test_a_months_spend_on_improving_is_held.py,
    # `Spending` in tests/test_a_spend_cap_that_can_never_be_reached.py and
    # tests/test_a_spend_cap_nothing_can_reach_holds_nothing_and_says_so.py), which
    # is the declaration a real host-written transport that CAN price would make
    # anyway — and those four were the whole cost, measured: flipping the default
    # with nothing else changed reddened exactly four tests out of 1930.
    # `transports/mock.py` is unaffected either way because it has no `usage()`.
    #
    # The seam itself is filed in
    #   tests/test_no_default_decides_a_capability_in_secret.py
    # under `OPTIONAL_ON_THE_TRANSPORT`, which is the ledger that exists because
    # this default was a capability decision the AC-7.2 audit structurally could
    # not see: it walks module-level upper-case NUMBERS, and this is an inline
    # boolean fallback on a `getattr`.
    prices_money = bool(getattr(transport, "prices_money", False))
    result.unmetered = spec.limits.unmeterable(reports_usage, prices_money)
    # A ceiling that is not a figure any reading can be at or above — `NaN USD`,
    # `inf USD`, and `runs-for-at-most` carrying `inf` through the constructor.
    # Same door, and it is the door rather than `never_reached` because that
    # field is a fact about the BINDING (built out of the bound model's catalogue
    # price) and this is a fact about the written line, known before a transport
    # is chosen. `Limits.__post_init__` has already refused to carry it as a
    # ceiling; without this it would be refused in silence, which is the same T7
    # breach one step further on. Argued in full at `limits._nothing_can_reach`
    # and pinned by
    # `tests/test_a_spend_cap_nothing_can_reach_holds_nothing_and_says_so.py`.
    held_nothing = spec.limits.nothing_can_reach
    result.unmetered = result.unmetered + held_nothing
    # The two latency promises nothing on this run measures. `slo.py` carried a
    # `Budget` that would have — `note_first_token`, `check_elapsed`, `add_cost`
    # — and nothing in `src/` ever constructed one, so `first-reply-within` and
    # `per-word-under` were held by no run and said so nowhere. The `Budget` is
    # deleted (it duplicated `Limits`); the reporting is here, so an author who
    # wrote a latency promise is told it is holding nothing.
    #
    # `Slo` also answers for the spend cap it read, which `Limits` read too — the
    # two take the same authored `limits:` block on the authored path, so this is
    # the one place in the concatenation where two sources can name one field.
    # Deduplicated below rather than by asking either side to stay quiet: each is
    # right to report what it read, and it is the LIST that must say a thing once.
    result.unmetered = result.unmetered + spec.slo.unmetered()
    if spec.slo.cap_nothing_can_reach is not None:
        held_nothing = tuple(dict.fromkeys(held_nothing + ("cost-per-request-under",)))
    # The author's `settings:` block, handed to the transport that can take it —
    # and named on the result when it cannot, or when it can take only some of
    # it. For a round the whole group crossed no boundary at all: twelve fields,
    # `max-tokens` and `thinking` at `tier: core`, in zero source files anywhere.
    # `max-tokens`' help makes a specific behavioural claim about truncation and
    # nothing did it.
    if spec.settings:
        take = getattr(transport, "apply_settings", None)
        left_over = tuple(spec.settings) if take is None else tuple(take(spec.settings))
        result.unmetered = result.unmetered + tuple(f"settings.{k}" for k in left_over)
    # Once, in the order it was first said. Two objects read
    # `cost-per-request-under:` off one authored block and both are right to
    # report a figure nothing can reach, so without this an author reading a
    # scored run is shown `cost-per-request-under, cost-per-request-under` and a
    # `watches:` subscriber gets the name twice in one payload. `dict.fromkeys`
    # rather than a `set`, because the order here is `ceilings()`' order and a
    # report that shuffles between runs is the instability `ceilings()` fixes
    # one file over.
    result.unmetered = tuple(dict.fromkeys(result.unmetered))
    # A money ceiling measured against a model that is FREE. Different from
    # `unmetered` and so a different field: nothing failed to measure — the meter
    # works perfectly and reads 0.00 on every call, for the life of the
    # workspace. `models/catalog.yaml` names this outcome as the thing to avoid
    # ("a spend cap that can never be reached, under an author who believes they
    # capped their spend"), and it arrives from the other direction: five of the
    # nine shipped rows are locally served and publish a SOURCED zero. The
    # worked example pins no `model:`, so it binds one of them.
    result.never_reached = _never_reached(spec, transport, prices_money)
    # A context policy is measured against what the model can hold, and a
    # transport that will not say cannot be tidied for. Reported through the same
    # door and for the same reason a spend cap with no price list is: an author
    # who wrote `context-policy: long-threads` and got neither tidying nor a word
    # about it has been told something untrue. Silence here is the T7 breach
    # `unmetered` exists to prevent.
    # A carried program with nothing to start it (P7). Named BEFORE the first
    # call, one sentence per program, because the alternative an author meets is
    # `error: no tool named ...` on the tool that reaches it — a true sentence
    # about a different thing, which reads as a typo in a file that is correct.
    #
    # The same door `context-policy` uses one line down, and for the same reason:
    # a capability this run could not honour is said out loud rather than
    # discovered.
    if run_program is None:
        result.unenforced = result.unenforced + tuple(
            f"`{where}` shortens what it answers with using the program "
            f"`{prog}`, and nothing here can run a carried program — so the whole "
            f"answer reaches the model."
            for where, prog in spec.projections
        ) + tuple(
            f"program `{p.name}`: nothing here can run a carried program, so "
            f"{'it is offered to the model and answers nothing' if p.reached_by == ('uses',) else ', '.join(p.reached_by) + ' reaches nothing'}. "
            f"Whatever runs your agents has to supply a locked room that hosts "
            f"`{p.engine or 'this kind of program'}`."
            for p in spec.programs
        )
    # And the other half of the same honesty, for the run that CAN start one.
    # `allow-egress:` gained `programs` as its eighth part and the schema's
    # sentence for it is that without the word "a program runs in a room with the
    # door shut". PACT never opens the body and never watches the room, so it
    # cannot hold that door — the host that supplied `run_program` does, and it
    # is handed the author's answer on every `ProgramSpec.may_reach_outside`.
    #
    # What is left is a promise this run is trusting somebody else to keep, and
    # R30's rule is that such a promise is said out loud rather than assumed:
    # "`allow-egress: []` is a sentence a person approved, and a check that passes
    # under it turns that approval into decoration". One sentence, not one per
    # program, because there is one door and one host.
    #
    # Said BOTH ways round, which is the repair to the first version of this. It
    # spoke only when the grant was withheld, so the safer arrangement was the
    # noisy one and granting a carried body the outside world said nothing at
    # all — the signal inverted, on the one line of this that a reviewer most
    # wants to see.
    if run_program is not None and spec.programs:
        named = ", ".join("`" + p.name + "`" for p in spec.programs)
        many = len(spec.programs) != 1
        result.unenforced = result.unenforced + (
            (
                f"`allow-egress:` names `programs`, so {named} "
                f"{'are' if many else 'is'} allowed to reach outside this box. What "
                f"{'they' if many else 'it'} can actually reach is the room's, and "
                f"PACT never opens a carried body or watches the room."
            )
            if spec.programs_may_reach_outside
            else (
                f"`allow-egress:` does not name `programs`, so {named} "
                f"{'run' if many else 'runs'} with the door shut — and PACT cannot "
                f"check that it is: it never opens a carried body and never watches "
                f"the room. Whatever supplied the runner holds that door."
            ),
        )
    if spec.context_policy is not None and tidy is None:
        result.unmetered = result.unmetered + ("context-policy",)
    # Everything the policy itself could not resolve. `ContextPolicy.problems`
    # was collected at build time and read by nothing in `src/`, so a pin that
    # matched nothing and a `drop-parts` step that named no kind of content were
    # both carried into the run in silence — and a pin that silently matches
    # nothing is precisely the failure `always-keep:` exists to prevent.
    if spec.context_policy is not None:
        result.unenforced = result.unenforced + tuple(
            f"{p.rule}: {p.message} Fix: {p.fix}" for p in spec.context_policy.problems
        )
    # A policy that names a second model and got no summariser has one rung of
    # its ladder doing nothing. Same door, same reason: `summarise-older` that
    # silently does not fire is a step the author wrote, watched load cleanly,
    # and never ran.
    if (
        spec.context_policy is not None
        and spec.context_policy.summarised_by
        and summarise is None
    ):
        result.unmetered = result.unmetered + ("summarised-by",)
    # A summariser that runs and cannot say what it cost. `summarised-by:` names
    # a SECOND model, so `write_summary` builds a second transport internally and
    # `_meter_usage` — which reads `usage()` off the one transport handed to
    # `run()` — never sees that call. On a long thread that is one extra model
    # call per tidy, charged to nothing, under an author who wrote
    # `cost-per-request-under`. Same door as every other ceiling nobody can
    # measure, because the alternative is a run that reports neither the spend
    # nor the fact that it could not count it.
    if summarise is not None and not callable(getattr(transport, "summary_usage", None)):
        result.unmetered = result.unmetered + ("summarised-by-cost",)
    # The author pinned one model and something else ran. Not substituted for —
    # measuring against the pin would tidy for a window the running model does
    # not have — and not ignored either, because the run is then answering on a
    # model nobody chose. Named, with both ids, so the mis-binding arrives as a
    # sentence rather than as a score that quietly moved.
    bound = str(getattr(transport, "model", "") or "")
    if spec.model and bound and spec.model != bound:
        result.unmetered = result.unmetered + ("model-pin",)
    # A procedure with no procedure in it. The skill's own routing lines still
    # reach the model, so this is not a failure to deliver — it is the author
    # having written a signpost and believing they wrote rules. Named rather
    # than dropped, for the reason every other line on this field is: a run that
    # quietly does less than the file says has told the author something untrue.
    # A `bind:` the surrounding system did not fill. Same door: for a round
    # `bind:` was checked by `pact check` and executed by nothing at all, and
    # unlike `context-policy` and `summarised-by` it was not even reported.
    result.unenforced = result.unenforced + _unfilled_binds(spec, supplied)
    # 02P A4. An action's `answers-with:` is checked by `pact check` and carried
    # by `ir.ToolSpec`, and a tool here answers in TEXT, so nothing on this
    # runtime holds a result to it. Said, for `bind:`'s reason one line up.
    result.unenforced = result.unenforced + _unchecked_answers(spec)
    # A7. PACT does not retrieve, so a set of documents this run never consulted
    # is the ordinary state on a machine with no index — and it must not be the
    # SILENT state, because the agent then answers from what the model already
    # knew and nobody is told the corpus was never opened.
    #
    # `retrieved_by` is what a host that DOES retrieve hands in. Absent, every
    # declared set is unretrieved, which is the honest reading: nothing here
    # fetched anything.
    #
    # The name is wrapped in typed single quotes and NOT in `!r`. `!r` spells a
    # name one way and a name with an apostrophe in it the other — `'handbook'`
    # against `"bob's-handbook"` — and `pact check` accepts both names, so the
    # spelling would depend on the name. Every other place a corpus name reaches
    # a person already types the quotes: `_and_list` two hundred lines above (the
    # `must-cite` refusal), `crates/pact-cli/src/main.rs` (*"is a set of documents
    # with no documents in it"*), and `neverLookedIn` in the second port, whose
    # sentence must match this one word for word. `!r` was one file spelling one
    # name two ways and two ports spelling one absence two ways.
    for corpus in spec.knowledge:
        if corpus.name in (retrieved_by or {}):
            continue
        result.unretrieved = result.unretrieved + (
            f"'{corpus.name}' is a set of documents and nothing in this run looked "
            f"anything up in it, so the answer comes from what the model already "
            f"knew. fix: run this where a retrieval runtime serves "
            f"`knowledge/{corpus.name}/documents/`, or take `{corpus.name}` off "
            f"this agent's `uses:` line.",
        )
    # And the half that is not a report. `must-cite: yes` says an answer with no
    # source is not an answer; an entry the run could not consult has no source
    # to give. Answering anyway produces the worst outcome available and the one
    # that looks most like success — an answer from what the model already knew,
    # citing a document it never opened — so the turn fails instead.
    #
    # Checked HERE, before a single model call, because paying for an answer that
    # cannot be given is the other thing that would look like working.
    ungrounded = [c.name for c in spec.knowledge if c.must_cite and c.name not in (retrieved_by or {})]
    if ungrounded:
        result.halted = "no-sources"
        result.output = (
            f"I could not read {_and_list(ungrounded)}, and I am only allowed to answer "
            f"from what is in there — so I have nothing to answer from."
        )
        bus.emit("turn.run.failed", at=(0,), reason="no-sources")
        return result
    for empty in (s.name for s in spec.skills if not s.content):
        result.unenforced = result.unenforced + (
            f"skill {empty!r} has a description and no body, so nothing but its "
            f"description reaches the model — put the procedure itself in "
            f"`skills/{empty}/SKILL.md` under the settings.",
        )
    if result.unmetered:
        bus.emit(
            "session.limit.failed",
            limits=list(result.unmetered),
            # WHICH of those the transport had nothing to do with. `unmetered`
            # carries two reasons and this payload carried one, beside the
            # transport's name — so a subscriber was handed the right field with
            # the wrong cause, which is the defect `scoring._unmetered_caveats`
            # splits the prose to avoid, surviving on the machine-readable half.
            # Measured, both reasons through the real bus before this line::
            #
            #   figure-nothing-can-reach -> {'limits': ['cost-per-request-under'],
            #                                'transport': 'spending', ...}
            #   transport-cannot-price   -> {'limits': ['cost-per-request-under'],
            #                                'transport': 'unpriced',  ...}
            #
            # byte-identical apart from the transport name, and the transport is
            # named in the case where the transport is innocent. `session.limit
            # .failed` is an address an author may subscribe a `watch:` to
            # (`watches.EMITTED`, `spec/schema.yaml`), and B6 requires this event
            # to carry the same list and the same wording as `unmetered`; T7
            # requires the machine-readable report, not only the prose.
            held_nothing=list(held_nothing),
            transport=getattr(transport, "name", "this transport"),
            pinned=spec.model,
            bound=bound,
        )
    phase_name = loop.starts_at
    visits: dict[str, int] = {}
    #: Answers a person has given to an `ask-someone` stage, keyed by stage.
    person_said: dict[str, str] = {}

    if resume is None:
        # Interceptors run BEFORE anything reaches the model, which is the only
        # point at which redaction is worth anything.
        seen, decision = chain.run("step.message.before", {"content": user_input})
        if decision.stop is not None:
            result.halted = "stopped-by-rule"
            result.output = decision.stop
            bus.emit("turn.run.cancelled", reason=decision.stop)
            return result
        # Marked here, once, because here is the only place that knows this is
        # the opening ask. A context policy pinning `the customer's original
        # request` reads this mark; deriving it later from "the first message
        # with role user" would quietly move it the moment the real one was
        # summarised away.
        history: list[dict[str, Any]] = [
            {"role": "user", "content": seen["content"], "labels": ["first-request"]}
        ]
        bus.emit("session.run.started", input=seen["content"])
        # The redacted question, kept on the result. `RunResult.as_record` reads
        # it rather than taking one from a caller, so a promoted eval case
        # carries what the rules allowed and not what was typed.
        result.asked = seen["content"]
        bus.emit("turn.run.started")
        start = 0
    else:
        # Continue exactly where the wait happened. The model is NOT re-asked
        # for the step that was already decided, and tools that already ran are
        # not run again — that is what makes resume exactly-once rather than
        # at-least-once.
        history = list(resume.history)
        result.steps = list(resume.steps)
        start = resume.step_index
        pending = resume.awaiting
        pending_text = resume.text
        already = dict(resume.completed)
        # Where in the author's loop it had got to. An older record with no
        # stage resumes at the first one, which is exactly right for the
        # one-stage shape and honest about the rest.
        phase_name = resume.phase or loop.starts_at
        visits = dict(resume.visits)
        # A run cannot get a fresh budget by being interrupted. What it had
        # already spent comes back with it, and only the time spent WAITING is
        # forgiven — nobody should fail a deadline because the approver went to
        # lunch. Eve has nothing to carry here, because it has nothing to spend.
        meter = Meter.restored(resume.used, clock(), start)
        result.used = meter

        if resume.expired(now):
            outcome = _give_up(resume, now, result, bus)
            if outcome is not None:
                return outcome
            # `decline` falls through. Whatever was waited on is refused and the
            # run carries on knowing that. It is never granted: a timeout that
            # grants is not a gate, it is a delay.
            if resume.reason == OUT_OF_BUDGET:
                return _out_of_budget(result, bus, start)
            if resume.reason == ASKED_A_PERSON:
                # The stage asked and nobody came. Recording that as the stage's
                # own words is the honest reading — the run continues knowing it,
                # rather than continuing as if an answer had arrived.
                person_said[resume.phase] = "Nobody answered in time."
            for call in resume.awaiting:
                already.setdefault(call.name, "refused: nobody answered in time")
        else:
            # A teammate's reply IS the result of the call that delegated to
            # them, so it lands as a completed call rather than as a clearance.
            for name, value in given.items():
                if gated.get(name) == WAITING_FOR_ANOTHER_AGENT and value:
                    already.setdefault(name, value)

            if resume.reason == ASKED_A_PERSON:
                said = _said(resume, given, "answer")
                if not said:
                    result.halted = "suspended"
                    result.suspension = resume
                    bus.emit("turn.run.cancelled", at=(start,), reason=ASKED_A_PERSON)
                    return result
                person_said[resume.phase] = said

            # A person has ruled on a teammate that could not answer
            # (`if-someone-fails: ask-a-person`). A go-ahead means carry on
            # without them; anything else leaves the run waiting, which the gate
            # branch below already knows how to do — so it does it, rather than
            # this growing a second way to park.
            for name in {n.split(".", 1)[0] for n in given}:
                if name not in delegates:
                    continue
                if (
                    ruling(
                        NEEDS_APPROVAL, name, asking.for_call(name, {}), given,
                        run_program=run_program,
                    )
                    is Ruling.CLEARED
                ):
                    already.setdefault(name, carried_on_without(name))
                else:
                    gated[name] = NEEDS_APPROVAL

            if resume.reason == OUT_OF_BUDGET:
                said = _said(resume, given, "decision")
                if clears(OUT_OF_BUDGET, said):
                    # A fresh budget of the same size — what Eve's session-limit
                    # continuation grants — which can itself run out, under a
                    # new key, so a second continuation is a second decision.
                    limit = start + spec.max_steps
                elif said:
                    return _out_of_budget(result, bus, start)
                else:
                    result.halted = "suspended"
                    result.suspension = resume
                    bus.emit("turn.run.failed", at=(start,), reason=OUT_OF_BUDGET)
                    return result

            if resume.reason == CONTEXT_TOO_LONG:
                said = _said(resume, given, "conversation")
                if ruling(
                    CONTEXT_TOO_LONG, "conversation",
                    asking.for_call("conversation", {}), given,
                    run_program=run_program,
                ) is Ruling.CLEARED:
                    # Permission for THIS step only. A later step that overflows
                    # again is a different `at`, so a different correlation key,
                    # so a second decision — the same rule the budget wait uses.
                    carried_on_at.add(start)
                elif said or answer_to(
                    asking.for_call("conversation", {}), "conversation", given,
                    run_program=run_program,
                ):
                    result.halted = "context-too-long"
                    result.output = result.steps[-1].text if result.steps else ""
                    bus.emit("turn.run.failed", at=(start,), reason=CONTEXT_TOO_LONG)
                    return result
                else:
                    result.halted = "suspended"
                    result.suspension = resume
                    bus.emit("turn.run.failed", at=(start,), reason=CONTEXT_TOO_LONG)
                    return result

    for i in range(start, limit):
        meter.steps = i
        # Checked at the top of the step, not the bottom: a run that is already
        # out of time or money must not start work it cannot pay to finish.
        if (out := spec.limits.reached(meter, clock())) is not None:
            return await _ran_out(
                out, spec=spec, transport=transport, result=result, history=history,
                already=already, bus=bus, meter=meter, now=now, clock=clock, at=i,
                phase=phase_name, visits=visits, asking=asking, once=once, chain=chain, given=given,
            )
        # Which stage runs now. A stage that has used up its `at-most` is routed
        # past here rather than after the fact, so it never spends a model call
        # discovering that it was not allowed to run.
        phase, gave_up = loop.stage_to_run(phase_name, visits)
        if phase is None:
            result.output = result.steps[-1].text if result.steps else ""
            if gave_up:
                result.halted = "stage-limit"
                bus.emit("turn.run.failed", at=(i,), reason=gave_up)
            else:
                result.halted = "final"
                bus.emit("turn.run.completed", at=(i,))
            return _turn_ended(result, spec.facts)
        phase_name = phase.name
        result.phases.append(phase_name)

        bus.emit("step.run.started", at=(i,))
        bus.emit("step.stage.started", at=(i,), name=phase_name, does=phase.does.value)

        # A stage that asks a person makes no model call at all. It is the same
        # suspension every other wait uses, under one more `x-` reason — the
        # claim that module makes being spent rather than restated.
        if phase.does is Does.ASK:
            said = person_said.pop(phase_name, None)
            if said is None:
                # The stage's own `asks:` question, if it named one. Without it
                # this park carried wording and nothing else — no audience, no
                # deadline, no shape for the answer — which is the one thing
                # the schema says at every other `asks:` must never happen.
                stage_question = asking.for_call(phase_name, {})
                stage_rule = rule_for(spec.pauses, ASKED_A_PERSON)
                parked = suspend(
                    ASKED_A_PERSON,
                    _asks_about(ASKED_A_PERSON, "answer", stage_question)
                    if stage_question is not None
                    else [Expect("answer", ANYTHING, means=phase.instruction())],
                    at=i,
                    about=[phase_name],
                    now=now,
                    rule=stage_rule,
                )
                # What the person actually reads. A stage that named no
                # question still shows its own `says:` line rather than an empty
                # park: a run stopped with nothing to show is, from the outside,
                # indistinguishable from a run that has hung.
                parked.in_words = words_for(
                    stage_question,
                    phase_name,
                    a_stage(phase_name, phase.instruction()),
                    otherwise=phase.instruction(),
                    contract=parked.asks,
                    waits_for=stage_rule.answer_within if stage_rule else "",
                    asked_of=tuple(stage_rule.who_can_answer) if stage_rule else (),
                )
                _park_state(
                    parked,
                    result=result,
                    history=history,
                    at=i,
                    already=already,
                    once=once,
                    given=given,
                    phase=phase_name,
                    visits=visits,
                    meter=meter,
                    clock=clock,
                    text=phase.instruction(),
                )
                result.halted = "suspended"
                result.suspension = parked
                bus.emit("step.input.requested", at=(i,), name=phase_name)
                return result
            result.steps.append(Step(index=i, text=said))
            history.append({"role": "user", "content": said})
            visits[phase_name] = visits.get(phase_name, 0) + 1
            bus.emit("step.stage.completed", at=(i,), name=phase_name, outcome="answered")
            # `said` here, not `text`: in this branch the words are the PERSON'S
            # answer, and `text` is not bound at all. A router reads what the
            # stage produced, and what an `ask-someone` stage produces is the
            # reply somebody typed.
            nxt = _where_next(
                loop, phase, "answered", result, bus, i, run_program=run_program, said=said
            )
            if nxt is None:
                return result
            if nxt == DONE:
                return _finish(result, chain, bus, i, said, spec.facts)
            phase_name = nxt
            continue

        # What exists in this stage. Eve resolves the tool set once per run,
        # which is why a planning step there can see the payment tool; here it
        # is the stage's own line.
        offered = set(phase.tools_offered(tuple(d["name"] for d in tool_defs)))
        step_tools = [d for d in tool_defs if d["name"] in offered]
        readable = set(phase.skills_offered(spec.skill_names))
        step_skills = tuple(s for s in spec.skills if s.name in readable)

        if pending:
            text, calls = pending_text, list(pending)
            pending = ()
        else:
            # Tidy BEFORE the model call, and keep what tidying produced — the
            # same placement Eve uses (`tool-loop.ts:691-702`, "before the model
            # call so compacted messages flow into history") and for the same
            # reason: tidying only for the call would re-summarise every step
            # and pay for the summary again each time.
            if tidy is not None:
                # Off the event loop, always. `summarise-older` is the one rung
                # that makes a model call, and the bridge that finishes it from
                # synchronous code BLOCKS the calling thread by design
                # (`transports/_summarise.py` argues why). Called inline, that
                # thread is the loop's, so a delegated child that tidied froze
                # every sibling and every `gives-up-after:` in the run —
                # measured end-to-end on authored lines only: a 500ms deadline
                # fired at 1.07s and a member whose answer HAD arrived was
                # recorded `out-of-time`. Recording a member that answered as
                # having missed a deadline is exactly the silent mis-statement
                # T7 forbids. In a worker thread the bridge finds no running
                # loop, uses `asyncio.run` directly, and blocks nobody.
                history, tidied = await asyncio.to_thread(_tidy, tidy, history, bus, i)
                if tidied is not None:
                    result.tidyings.append(tidied)
                    if tidied.outcome == "asked-a-person" and i not in carried_on_at:
                        tidy_rule = rule_for(spec.pauses, CONTEXT_TOO_LONG)
                        parked = suspend(
                            CONTEXT_TOO_LONG,
                            _asks_about(
                                CONTEXT_TOO_LONG, "conversation",
                                asking.for_call("conversation", {}),
                            ),
                            at=i,
                            about=["conversation"],
                            now=now,
                            rule=tidy_rule,
                        )
                        # The `how-much-over` figure the tidier already wrote,
                        # reaching the person who has to decide about it. Carried
                        # with the run rather than rebuilt on the far side (D23:
                        # the process may die while somebody thinks), and quoted
                        # in its own labelled region like every shown value.
                        parked.in_words = words_for(
                            asking.for_call("conversation", {}),
                            "conversation",
                            tidying(tidied),
                            otherwise=_DEFAULT_ASKS[CONTEXT_TOO_LONG],
                            contract=parked.asks,
                            waits_for=tidy_rule.answer_within if tidy_rule else "",
                            asked_of=tuple(tidy_rule.who_can_answer) if tidy_rule else (),
                        )
                        _park_state(
                            parked,
                            result=result,
                            history=history,
                            at=i,
                            already=already,
                            once=once,
                            given=given,
                            phase=phase_name,
                            visits=visits,
                            meter=meter,
                            clock=clock,
                        )
                        result.halted = "suspended"
                        result.suspension = parked
                        return result
            bus.emit("step.model.requested", at=(i,))
            # The author's better model for the stages that check work, when they
            # asked for one and the host serves it. `Does.CHECK` is the scope the
            # schema chose and says why: a model chosen per STEP re-ingests the
            # conversation every step, which is the pathological case Eve's own
            # docs warn about, so the stage is the scope and the per-step form is
            # deliberately not spellable.
            asking_now = (
                checking_transport
                if checking_transport is not None
                and spec.model_for_checking
                and phase.does is Does.CHECK
                else transport
            )
            # CodeAct (P8 wave 8). The model writes the working, the locked
            # room runs it, and what it prints comes back as this step's result.
            #
            # It is offered NOTHING else — `step_tools` is not passed — which is
            # the whole safety argument in one line: a snippet cannot call a
            # gated action, spend money or ask an agent, because none of them is
            # in front of it. What it can do is compute, in a room with
            # deny-by-default egress and the stage's own fuel.
            #
            # A stage that cannot run anything is refused rather than quietly
            # becoming a `think` stage: an author who wrote `does: run-code`,
            # watched it load and got prose instead has been told something
            # untrue.
            if phase.does is Does.RUN_CODE:
                if run_program is None:
                    result.halted = "no-locked-room"
                    result.output = (
                        f"stage {phase_name!r} writes code to be run, and nothing here can "
                        f"run a carried program. Whatever runs your agents has to supply a "
                        f"locked room."
                    )
                    result.unenforced = result.unenforced + (result.output,)
                    return result
                wrote, _ = await asking_now.model_call(
                    _system_for(spec.instructions, phase, step_skills), history, []
                )
                _meter_usage(asking_now, meter)
                # THE SNIPPET IS WORDS THE MODEL PRODUCED, and it goes into
                # `history` like any others — so it meets the rules at the same
                # address a stage's prose does. A card number typed into a
                # comment was the same leak by a shorter route, and this was the
                # one thing a model wrote in this harness that no rule ever saw.
                written, decision = chain.run("step.message.after", {"content": wrote})
                if decision.stop is not None:
                    result.halted = "stopped-by-rule"
                    result.output = decision.stop
                    bus.emit("turn.run.cancelled", at=(i,), reason=decision.stop)
                    return result
                # WHAT IS RECORDED IS NOT WHAT IS RUN, and this file already
                # draws that line two hundred lines down about a tool's
                # arguments: "Rewriting `call` decides what is WRITTEN DOWN,
                # never what runs."
                #
                # Masking the snippet on the way IN changed the arithmetic. The
                # card pattern deliberately over-matches, which is right for
                # prose and destructive for code: `order_id = 9780306406157`
                # became `order_id = [removed]` and the room raised NameError —
                # and under the shipped redaction file the bank-account pattern
                # contains `\b\d{8}\b`, so any eight-digit literal went the same
                # way. Worse, it does not always fail loudly:
                # `print(len("9780306406157"))` becomes `print(len("[removed]"))`
                # and the model answers from `9`.
                #
                # So the transcript gets the masked words and the room gets the
                # ones the model wrote — UNLESS the author granted `programs` the
                # outside world, where a verbatim snippet is a real way out and
                # the caution goes the other way round.
                original = wrote
                to_run = written["content"] if spec.programs_may_reach_outside else original
                wrote = written["content"]
                # Said out loud whichever way round it went. A reader of the
                # trace is looking at something other than what ran, and a
                # control quietly doing something else is the shape T7 forbids.
                if wrote != original:
                    result.unenforced = result.unenforced + (
                        (
                            f"stage {phase_name!r} writes code to be run, and a hiding "
                            f"rule changed it before it ran — `allow-egress:` names "
                            f"`programs`, so the room may reach outside and is given the "
                            f"hidden form rather than what the model wrote. What it "
                            f"worked out may not be what was asked for."
                        )
                        if to_run != original
                        else (
                            f"stage {phase_name!r} writes code to be run, and a hiding "
                            f"rule changed it. The room ran what the model wrote; the "
                            f"transcript shows the hidden form, so the two do not match."
                        ),
                    )
                ran = _call_tool(
                    lambda a: run_program(RUN_CODE_IN_THE_ROOM, a),
                    ToolCall(name=RUN_CODE_IN_THE_ROOM, args={"code": to_run}),
                )
                meter.tool_calls += 1
                # AND WHAT THE ROOM PRINTED IS A TOOL RESULT. It is metered as
                # one and appended to `history` as one, and the argument the tool
                # path makes in its own comment applies unchanged: a result read
                # back to the model next turn "leaves by the same door as
                # anything else". `redaction.yaml`'s promise is "what must never
                # leave this workspace", and a locked room's output was outside
                # it.
                came_back, decision = chain.run(
                    "step.tool.completed", {"name": RUN_CODE_IN_THE_ROOM, "content": ran}
                )
                if decision.stop is not None:
                    result.halted = "stopped-by-rule"
                    result.output = decision.stop
                    bus.emit("turn.run.cancelled", at=(i,), reason=decision.stop)
                    return result
                ran = came_back["content"]
                history.append({"role": "assistant", "content": wrote})
                history.append({"role": "user", "content": ran})
                result.steps.append(
                    Step(index=i, text=wrote, tool_calls=(), tool_results=(ran,))
                )
                visits[phase_name] = visits.get(phase_name, 0) + 1
                bus.emit(
                    "step.stage.completed", at=(i,), name=phase_name, outcome="answered"
                )
                nxt = _where_next(
                    loop, phase, "answered", result, bus, i,
                    run_program=run_program, said=wrote,
                )
                if nxt is None:
                    return result
                if nxt == DONE:
                    return _finish(result, chain, bus, i, ran, spec.facts)
                phase_name = nxt
                continue

            text, calls = await asking_now.model_call(
                _system_for(
                    spec.instructions, phase, step_skills,
                    # The author's declared answer shape, on every stage. Not
                    # only the last: a `check-its-work` stage that cannot see
                    # what the answer must contain cannot check it against
                    # that, which is the one thing it is for.
                    answers_with=shape_to_ask_for,
                    # Anything an MCP server said about itself, already fenced.
                    # On EVERY stage, for the same reason the shape is: a stage
                    # that cannot see what a server claims cannot notice the
                    # claim is being made — and a region that appeared on only
                    # some stages would be a fence with a gap in it.
                    external=spec.external_prose,
                ),
                history,
                step_tools,
            )
            bus.emit("step.model.completed", at=(i,), text=text, tools=[c.name for c in calls])
            # What that call cost. Checked immediately: a spend cap enforced one
            # step late has already spent the step that broke it.
            _meter_usage(transport, meter)
            if (out := spec.limits.reached(meter, clock())) is not None:
                return await _ran_out(
                    out, spec=spec, transport=transport, result=result, history=history,
                    already=already, bus=bus, meter=meter, now=now, clock=clock, at=i,
                    phase=phase_name, visits=visits, asking=asking, once=once, chain=chain, given=given,
                )

        # A call to something this stage does not offer is refused, and the
        # refusal is handed back to the model. Dropping it silently would lose an
        # action the model really took (T7); running it would make `may-use:`
        # advisory.
        #
        # The two refusals stay distinguishable, because they call for opposite
        # fixes: a tool the agent does not have at all is a name to correct,
        # while one the stage withholds is a `may-use:` line to widen. Reporting
        # both as a stage problem would send an author editing the loop to add a
        # tool that was never spelled right in the first place.
        have = {d["name"] for d in tool_defs}
        refused = {
            c.name: (
                f"error: no tool named {c.name!r}"
                if c.name not in have
                else f"error: {c.name!r} is not available in the {phase_name!r} stage"
            )
            for c in calls
            if c.name not in offered
        }
        for name in sorted(refused):
            bus.emit(
                "step.tool.cancelled",
                at=(i,),
                name=name,
                reason="no such tool" if name not in have else "not in this stage",
            )

        if not calls:
            visits[phase_name] = visits.get(phase_name, 0) + 1
            bus.emit("step.stage.completed", at=(i,), name=phase_name, outcome="answered")
            nxt = _where_next(
                loop, phase, "answered", result, bus, i, run_program=run_program, said=text
            )
            if nxt is None:
                return result
            if nxt == DONE:
                answered, decision = chain.run("turn.message.after", {"content": text})
                if decision.stop is not None:
                    result.halted = "stopped-by-rule"
                    result.output = decision.stop
                    bus.emit("turn.run.cancelled", at=(i,), reason=decision.stop)
                    return result
                text = answered["content"]
                result.steps.append(Step(index=i, text=text))
                result.output = text
                result.halted = "final"
                bus.emit("turn.message.completed", at=(i,), text=text)
                bus.emit("turn.run.completed", at=(i,))
                return _turn_ended(result, spec.facts)
            # A stage that finished its say on the way somewhere else. Those
            # words are a step, not the turn's reply, so the rule that guards
            # the reply does not fire on them — `step.message.after` does.
            onward, decision = chain.run("step.message.after", {"content": text})
            if decision.stop is not None:
                result.halted = "stopped-by-rule"
                result.output = decision.stop
                bus.emit("turn.run.cancelled", at=(i,), reason=decision.stop)
                return result
            text = onward["content"]
            result.steps.append(Step(index=i, text=text))
            history.append({"role": "assistant", "content": text})
            bus.emit("step.message.completed", at=(i,), text=text)
            phase_name = nxt
            continue

        # One park for every reason. Approval, a missing permission and a
        # teammate doing the work are the same event here — the run cannot go on
        # until something outside it happens — so they share a branch, a shape
        # and a guard. Eve writes this three times, plus twice more elsewhere.
        # PER CALL, not per tool name. `rulings.where`'s own docstring claims "two calls
        # blocked in the same step cannot answer for one another" — true only for
        # two DIFFERENT tools. Two calls to `payments` in one step collapsed onto
        # one key: `args_of` was `{c.name: c.args}`, last wins, so the approver
        # was shown the second call's values twice and, answering `payments: yes`,
        # released both — including a 300 USD refund they were never shown. With
        # a 600 USD call beside a 40 USD one it was worse: the 600 selected
        # `how-much-to-refund` while the gate was handed the 40's arguments, so
        # the wait was keyed and rendered as `is-this-ok`, and answering exactly
        # what it demanded re-parked the run under the same key for ever.
        #
        # `slot()` keeps the plain tool name when a step calls that tool once,
        # which is every step in the worked example and every answer anybody has
        # already written down; only a repeat gets `payments#1`.
        seen_names: dict[str, int] = {}
        slots: list[str] = []
        for c in calls:
            n = seen_names.get(c.name, 0)
            seen_names[c.name] = n + 1
            slots.append(c.name if n == 0 else f"{c.name}#{n}")

        # What the author's approval policy stops, decided against the arguments
        # the model actually chose. Per step and not once per run: `payments`
        # above 200 USD waits and `payments` at 40 USD does not, and a gate that
        # stuck after the first big refund would stop the small one too, which is
        # not what `more-than: 200 USD` says. `gated` still wins where a host set
        # it, so `needs_approval=` remains an override rather than a rival.
        #
        # WHY each call waits, not whether. A name can carry rules for two reasons
        # — `payments` has a threshold in `policies/approvals.yaml` and a
        # connection consent in `resources/payments-server.yaml` — so a boolean
        # forced this line to invent the reason, and inventing `needs-approval` is
        # how a consent park came to be keyed and rendered as a refund approval.
        # `Gate.waits_for` returns every reason in the order a person is asked
        # them (`questions.ASKED_IN_ORDER`: consent before approval, argued
        # there).
        #
        # Keyed by SLOT, and by slot for exactly the reason the paragraph above
        # gives about `args_of`. Measured while merging the two: a batch issuing
        # 300 USD and then 40 USD over the same connection, keyed by NAME, kept
        # only the 40 USD call's waits — it is under the author's line, so it has
        # no approval — and the 300 USD refund a person had never been asked
        # about ran the moment the connection was allowed.
        #
        # Only slots with at least one reason go in, so `slot in step_gated`
        # below goes on meaning "this call is waiting for something".
        #
        # And nobody waits for a call that cannot run. A key another call
        # already spent (`same-request-key:`) means `once.hold` below will
        # withhold this one whatever a person answers, so it is not put to
        # them: it falls through to that refusal, which the model reads as the
        # call's result. A look, not a claim — the key is spent only when a
        # call is let through — and read off the arguments the tool would
        # receive (`_with_binds`), like the claim. A call this run already
        # made (`already`) is replayed from its record and never reaches here
        # twice, so the key a call itself spent is not held against it.
        step_gated: dict[str, tuple[Wait, ...]] = {}
        for slot, c in zip(slots, calls):
            if c.name not in already and once.look(c.name, _with_binds(spec, c, supplied).args):
                continue
            if waits := asking.waits_for(c.name, c.args, gated.get(c.name, "")):
                step_gated[slot] = waits

        # And what the author's policy could NOT decide about these calls. A rule
        # naming one action of a tool is enforced when the call says which action it
        # is; when the call says nothing, stopping it would stop the read-only lookup
        # nobody wrote a rule about, so the rule is reported rather than guessed at.
        # Per call, not once at the top of the run: whether `zendesk/reply` could be
        # applied is a fact about a CALL, and reporting it at the top said it about
        # runs that obeyed the rule and about runs that never touched `zendesk`.
        for c in calls:
            for said in asking.undecided_on(c.name, c.args):
                if said not in result.unenforced:
                    result.unenforced += (said,)

        # What this run's answers say about each wait — decided ONCE, keyed by
        # (call, REASON), and read three times below. It used to be decided twice
        # by two different tests: one kept a call the person had cleared out of
        # `blocked` (right) and the other kept it out of the execution (wrong),
        # so a batch with any call still waiting deferred every call the person
        # had already approved. Measured: a step calling `zendesk`, `payments`
        # and `email` with the last two gated, answered `payments: approve` and
        # nothing yet about `email`, ran `['zendesk']` — `payments` was approved
        # by a person and never happened.
        #
        # THREE outcomes, not two. `_cleared` returned a bare bool, so a refusal
        # and silence were the same value and both re-parked — measured, answering
        # `decline` asked the same thing again under a new key, and answering it
        # again asked a third time. Eve's approval is "exactly two options named
        # approve and deny"; PACT had only the first one working, while
        # `questions.Answer.declined` sat built and unreachable from here.
        #
        # One entry per (call, reason) because one call can be waiting for two
        # things at once and each is cleared by its own answer. `w.asked_as or
        # slot` is the name that answer goes under: the consent is about the
        # connection and is answered under the connection's name, the approval is
        # about the call. Both questions ask for `approved` and `because`, so
        # sharing a name is how one person's yes to the connection would have
        # released a refund they were never shown. And the reason is passed on to
        # `_asked_at`, so the answer a call is tested against is the one the
        # person was actually shown.
        rulings: dict[tuple[str, str], Ruling] = {
            (slot, w.reason): ruling(
                w.reason,
                w.asked_as or slot,
                _asked_at(asking, w.reason, c.name, c.args),
                given,
                run_program=run_program,
            )
            for slot, c in zip(slots, calls)
            for w in step_gated.get(slot, ())
        }
        # A refusal ENDS the wait. Recorded exactly the way the timeout path a few
        # hundred lines up records one — into `already`, as the result of the call
        # — so three things hold at once: the run does not park on it again, the
        # call never executes on this pass or on any resume (`already` is what
        # makes resume exactly-once), and the model reads the refusal as what came
        # back from the tool it asked for, so it can carry on or stop rather than
        # finding that the thing it asked for never happened and nothing says so.
        #
        # Decided per NAME, because `already` is keyed by name and one entry
        # cannot hold two outcomes — the same limit that makes two calls to one
        # tool WAIT together below. So a refusal of any call to a name stops every
        # call to that name in this batch: the safe direction, since the other one
        # is issuing a refund a person turned down.
        #
        # What it must never do is claim somebody refused a call they were never
        # shown, which is the mis-statement `refused_in_words` exists to avoid at
        # the level of a single answer. So a name only PARTLY refused says the
        # refusal that really happened and then says why the rest of the name
        # stopped too, as a limit of the record rather than as something a person
        # did — the reader gets the reason they gave and is not told they gave it
        # about a call they never saw.
        by_name: dict[str, list[tuple[str, ToolCall]]] = {}
        for slot, c in zip(slots, calls):
            by_name.setdefault(c.name, []).append((slot, c))
        for name, group in by_name.items():
            if name in already or name in refused:
                continue
            turned_down = [
                (slot, c, w)
                for slot, c in group
                for w in step_gated.get(slot, ())
                if rulings[(slot, w.reason)] is Ruling.REFUSED
            ]
            if not turned_down:
                continue
            at, refused_call, wait = turned_down[0]
            said_no = refused_in_words(
                wait.asked_as or at,
                _asked_at(asking, wait.reason, refused_call.name, refused_call.args),
                given,
                run_program=run_program,
            )
            if len({where_at for where_at, _, _ in turned_down}) < len(group):
                said_no += (
                    f". This step made {len(group)} calls to {name!r} and one record "
                    f"per tool cannot hold two answers, so none of them happened"
                )
            already[name] = said_no
            # The address a call that was decided-and-not-done already uses — the
            # same one a tool the stage withholds and a call a rule redirected are
            # published under. A refusal is not a new kind of event, it is one
            # more reason for that one.
            bus.emit(
                "step.tool.cancelled", at=(i,), name=name, reason="a person said no",
            )
        blocked = [
            (slot, c, w)
            for slot, c in zip(slots, calls)
            for w in step_gated.get(slot, ())
            if c.name not in already
            and c.name not in refused
            and rulings[(slot, w.reason)] is Ruling.NOT_YET
        ]
        if blocked:
            # Everything this batch may do is done BEFORE the run parks, in the
            # batch's own order. A person who approves two of three actions gets
            # those two: deferring them until the last answer arrives is not what
            # they said, and when that answer never comes, "deferred" means
            # "never". `already` stays the exactly-once ledger, so a second resume
            # replays these from the record instead of running them again, and the
            # order is the batch's own so the trace is the same on every transport
            # — the byte-identical-trace claim covers this path.
            #
            # Three kinds of call are held back, and each was measured running
            # when it should not have:
            #
            # * one no answer has cleared — that is the same `rulings` the park
            #   itself reads, rather than a second predicate beside it that can
            #   disagree with it;
            # * one the stage REFUSED — it was decided, not deferred. Without this
            #   word the loop ran tools the stage had just withheld: on a
            #   `may-use: [zendesk, payments]` stage whose model also called
            #   `email`, the park's ledger came back holding an `email` entry with
            #   its implementation run, while the model was told `email` "is not
            #   available in the 'gather' stage";
            # * one addressed to a TEAMMATE — that is work happening elsewhere,
            #   not a local tool. `_call_tool` has no implementation to find for a
            #   member name, so the ledger recorded `error: no tool named
            #   'fraud-checker'`; a completed call is never re-asked, so the
            #   resumed run served the model that error and the teammate was never
            #   asked at all.
            #
            # And a cleared call whose NAME still has another call waiting waits
            # too, because `already` is keyed by name: one entry cannot hold two
            # outcomes, so carrying an approved 300 USD refund forward would hand
            # its result to the 40 USD one nobody has answered. Both wait, and
            # answering both releases both, which is what happened before any of
            # this changed.
            waiting_names = {c.name for _, c, _ in blocked}
            for slot, call in zip(slots, calls):
                if (
                    call.name in already
                    or call.name in refused
                    or call.name in delegates
                    or call.name in waiting_names
                    or any(
                        rulings[(slot, w.reason)] is not Ruling.CLEARED
                        for w in step_gated.get(slot, ())
                    )
                ):
                    continue
                carried = _with_binds(spec, call, supplied)
                # A person cleared every gate on this call, so the run now KNOWS
                # something its messages will not carry once they are summarised
                # away: that this was approved (G9). Recorded here rather than
                # where the answer arrives, because here is the point at which
                # the clearance became a fact about the run instead of an
                # answer about a question.
                #
                # `record` is silent for anything the author did not declare
                # `survives-shortening:`, so a workspace that asked for none of
                # this is unaffected.
                for w in step_gated.get(slot, ()):
                    spec.facts.record(
                        f"{w.asked_as or slot}-was-approved",
                        f"cleared for {call.name} at step {i}",
                    )
                # A call carried out before the run parks spends its key like
                # any other. Without this a batch that parks for a second call
                # could issue the first refund twice across two resumes, which
                # is the one thing the field forbids.
                already[call.name] = once.hold(call.name, carried.args) or _call_tool(
                    tool_impls.get(call.name), carried
                )
            # The first uncleared reason of the first blocked call, which is the
            # first in `ASKED_IN_ORDER` — consent before approval. A run that
            # needs both meets them one at a time, in that order.
            reason = blocked[0][2].reason
            # Keyed by the WAIT, so the values shown are the values of the call
            # the person is deciding about. Two calls over one connection are one
            # consent (the question's own file: "asked once, not once per
            # customer"), so the first call's values illustrate it and `dict`
            # order keeps that stable.
            waiting_on: list[str] = []
            args_of: dict[str, Any] = {}
            # Which tool each wait really is about, for the rule lookup — the rule
            # is a property of the tool, the wait is a property of the call.
            tool_of: dict[str, str] = {}
            for slot, c, w in blocked:
                if w.reason != reason:
                    continue
                about = w.asked_as or slot
                if about not in args_of:
                    waiting_on.append(about)
                    args_of[about] = c.args
                    tool_of[about] = c.name
            # `reason` is handed to the gate, not only used to group the names.
            # Until it was, a `needs-permission` park on `payments` rendered
            # `is-this-ok` — "Please check this before it happens.", 30 minutes,
            # escalate — because that is the first rule the author wrote about
            # that name. The person was asked to approve a refund when what was
            # waiting was whether this desk may use the payments connection.
            #
            # One entry per blocked thing: what the wait asks about it, and the
            # question to put. Both computed once, because the two used to be
            # computed separately and disagreed — see below.
            put = [
                (n, q, _asks_about(reason, n, q))
                for n in waiting_on
                for q in [_asked_at(asking, reason, tool_of[n], args_of.get(n, {}))]
            ]
            # The deadline, the addressee and what to do when nobody answers come
            # from the rule. WHAT is asked comes from the question bound to
            # *this* call, so two calls blocked in the same step keep separate
            # answers — a parallel batch is exactly where a gate fires, and one
            # flat set of answer names would let a yes about the cheap call clear
            # the costly one.
            rule = rule_for(spec.pauses, reason)
            if any(q is not None for _, q, _ in put) and rule is not None:
                rule = replace(rule, asks_for=())
            parked = suspend(
                reason,
                [e for _, _, asks in put for e in asks],
                at=i,
                about=waiting_on,
                now=now,
                rule=rule,
            )
            # What the person actually reads, carried with the run rather than
            # rebuilt afterwards: the process may die while they think (D23), and
            # rebuilding it could show them wording that no longer matches what
            # was asked. Values are quoted data in their own labelled region, so
            # a customer's text cannot forge a line of it (Y18/AD-46).
            #
            # Through `shown.words_for` like the other four. This was the one
            # park that rendered `Question.for_person()` directly, and it printed
            # a screen the wait itself refuses: the line above clears the rule's
            # contract, so `suspend` keys the wait on `payments` /
            # `payments.because`, while the question printed its author's own
            # field names — *"answer with: approved (yes or no), because (some
            # text)"*. Measured on the worked example:
            # `w.answer(approved="yes", because="ok")` came back *"this wait did
            # not ask for 'approved'. It asked for: payments, payments.because."*
            # `words_for`'s own docstring says the `contract=` argument exists to
            # stop exactly that, and this park was the one not passing it.
            #
            # The deadline and the audience come from the RULE for the same
            # reason. A `waiting-for-another-agent` park has no rule at all —
            # §7.14 WAIT-2 says nothing configures that reason — so it rendered
            # `is-this-ok`'s *"asked of: support-leads"* and *"answer within:
            # 30m"* over a wait whose `who_can_answer` was empty and whose
            # `waits_for` was `None`: an audience and a deadline borrowed from
            # another question entirely.
            parked.in_words = "\n\n".join(
                said
                for n, q, asks in put
                if (
                    said := words_for(
                        q,
                        n,
                        args_of.get(n, {}),
                        otherwise=_DEFAULT_ASKS.get(reason, ""),
                        contract=asks,
                        waits_for=rule.answer_within if rule else "",
                        asked_of=tuple(rule.who_can_answer) if rule else (),
                    )
                )
            )
            _park_state(
                parked,
                result=result,
                history=history,
                at=i,
                already=already,
                once=once,
                given=given,
                phase=phase_name,
                visits=visits,
                meter=meter,
                clock=clock,
                text=text,
                awaiting=tuple(calls),
            )
            result.halted = "suspended"
            result.suspension = parked
            bus.emit("step.approval.requested", at=(i,), reason=reason, waiting_on=waiting_on)
            return result

        # Everyone the model asked for help in this step is joined ONCE, under
        # the authored policy. Eve joins them with a fixed all-or-nothing
        # barrier, starts them serially and splits the budget evenly; here the
        # three are separate authored fields, so a race costs the fastest
        # member's latency rather than the slowest's.
        replies: dict[str, str] = {}
        to_ask = [
            c for c in calls
            if c.name in delegates and c.name not in already and c.name not in refused
        ]
        if to_ask:
            _, decision = chain.run(
                "step.delegate.before", {"members": [c.name for c in to_ask]}
            )
            if decision.stop is not None:
                result.halted = "stopped-by-rule"
                result.output = decision.stop
                bus.emit("step.delegate.cancelled", at=(i,), reason=decision.stop)
                return result
            handoff = await ask_team(
                [c.name for c in to_ask],
                ask_member,
                teamwork,
                bus=bus,
                requests={c.name: _request(c, text) for c in to_ask},
                pool=team_pot,
            )
            result.handoffs.append(handoff)
            # What the team spent counts against the ceiling the author wrote.
            # Without this line `cost-per-request-under: 0.05 USD` permitted the
            # parent's 0.05 plus an uncapped team, and one more of each per level
            # of nesting — so one written ceiling was one ceiling PER AGENT, which
            # is not what "the most one request may cost" says. Checked at the top
            # of the next step, through the same door every other ceiling uses.
            meter.money += handoff.spent
            if handoff.needs_a_person:
                # A member failed and the author said to ask. Everything that
                # did arrive is carried forward, so the person's decision costs
                # nobody a second run.
                for a in handoff.answers:
                    if a.ok:
                        already[a.member] = a.text
                for slot, call in zip(slots, calls):
                    if (slot in step_gated or call.name in delegates
                            or call.name in already):
                        continue
                    carried = _with_binds(spec, call, supplied)
                    # A call carried out before the run parks spends its key
                    # like any other. Without this a batch that parks for a
                    # second call could issue the first refund twice across two
                    # resumes, which is the one thing the field forbids.
                    already[call.name] = once.hold(call.name, carried.args) or _call_tool(
                        tool_impls.get(call.name), carried
                    )
                who = handoff.needs_a_person
                # The author's `teamwork.asks` question if there is one, and a
                # plain go-ahead if not — the same two lines every other wait
                # uses, so "carry on without the fraud check?" can be a written
                # question rather than a hardcoded yes/no pair (G7).
                team_rule = rule_for(spec.pauses, NEEDS_APPROVAL)
                parked = suspend(
                    NEEDS_APPROVAL,
                    _asks_about(NEEDS_APPROVAL, who, asking.for_call(who, {})),
                    at=i,
                    about=[who],
                    now=now,
                    rule=team_rule,
                )
                # Who could not answer and why, in the words the transcript
                # already uses. A teammate may be a remote agent relaying
                # customer text, so it reaches the person quoted in its own
                # region rather than folded into the author's sentence (Y18).
                parked.in_words = words_for(
                    asking.for_call(who, {}),
                    who,
                    teammate(who, handoff.said(who), [a.member for a in handoff.good]),
                    otherwise=_DEFAULT_ASKS[NEEDS_APPROVAL],
                    contract=parked.asks,
                    waits_for=team_rule.answer_within if team_rule else "",
                    asked_of=tuple(team_rule.who_can_answer) if team_rule else (),
                )
                _park_state(
                    parked,
                    result=result,
                    history=history,
                    at=i,
                    already=already,
                    once=once,
                    given=given,
                    phase=phase_name,
                    visits=visits,
                    meter=meter,
                    clock=clock,
                    text=text,
                    awaiting=tuple(calls),
                )
                result.halted = "suspended"
                result.suspension = parked
                bus.emit(
                    "step.approval.requested", at=(i,), reason=NEEDS_APPROVAL, waiting_on=[who]
                )
                return result
            replies = {a.member: handoff.said(a.member) for a in handoff.answers}

        outputs: list[str] = []
        ran: list[ToolCall] = []
        out_of_calls: "Reached | None" = None
        #: The stage a rule sent this run to instead of doing the call it was
        #: about to do (G5's third outcome, `send-elsewhere`).
        sent_to: str = ""
        # `slot` beside `call`, because what a person answered about this call is
        # filed under the SLOT — `payments#1` for the second refund in a batch —
        # and reading it under the tool's name would hand the second call the
        # first one's answer.
        for slot, call in zip(slots, calls):
            if call.name in refused:
                outputs.append(refused[call.name])
                ran.append(call)
                continue
            if call.name in replies:
                outputs.append(replies[call.name])
                ran.append(call)
                continue
            if call.name in already:
                # A call carried out BEFORE the run parked, replayed from where
                # it was put aside. Two things lived below this `continue` and
                # neither happened to it: what the author said to keep was never
                # kept, so a gated batch lost the fact; and the interceptor chain
                # never saw the result, so a redaction rule did not apply to a
                # value that goes into `history` and is read back to the model
                # exactly like any other.
                #
                # The same shape as the code stage one file over: a result that
                # reaches the model by a path no rule watches. Parking is not a
                # reason for the rules to stop.
                seen, decision = chain.run(
                    "step.tool.completed",
                    {"name": call.name, "content": already[call.name]},
                )
                if decision.stop is not None:
                    result.halted = "stopped-by-rule"
                    result.output = decision.stop
                    bus.emit("turn.run.cancelled", at=(i,), reason=decision.stop)
                    return result
                _keep_what_it_answered(spec, call, seen["content"])
                outputs.append(seen["content"])
                ran.append(call)
                continue
            # Before the call, not after it. `tool-calls-at-most: 40` that lets
            # the 41st through because it arrived in the same batch as the 40th
            # is not a ceiling, it is a suggestion — and a batch is exactly where
            # a runaway agent spends fastest.
            if (out_of_calls := spec.limits.reached(meter, clock())) is not None:
                break

            # What the person said, if they were asked. Their answer is not only
            # a yes: it may set a value the model proposed, or replace the call
            # with what they wrote. Eve's request is two options, so both of
            # those need a mechanism it does not have; here they are two shapes
            # of one typed answer (G7, and HARN-3's four decision kinds).
            # Read under the SAME reason the wait was put under, so the answer
            # is parsed against the question the person actually saw. Reading a
            # connection consent through the refund-approval question's shape
            # would drop the `because:` they typed and could take a shape
            # mismatch for a refusal.
            # Which of this call's waits is about the CALL. A connection consent
            # is about the connection — answered under the connection's name, and
            # unable to set an argument — so reading the person's answer to it
            # here would look for a key that is not there. The approval is the one
            # that can change what runs.
            about_call = next(
                (w.reason for w in reversed(step_gated.get(slot, ())) if not w.asked_as),
                "",
            )
            said = (
                answer_to(
                    asking.for_call(call.name, call.args, about_call), slot, given,
                    run_program=run_program,
                )
                if slot in step_gated
                else None
            )
            args = dict(call.args)
            if said is not None:
                if said.instead is not None:
                    outputs.append(said.instead)
                    ran.append(call)
                    bus.emit("step.approval.completed", at=(i,), name=call.name,
                             outcome="answered-instead")
                    continue
                args = said.applied_to(args)
                if args != call.args:
                    bus.emit("step.approval.completed", at=(i,), name=call.name,
                             outcome="changed", changed=sorted(
                                 k for k in args if args[k] != call.args.get(k)))

            # `so-far` is every tool this run has already called, including the
            # ones earlier in this same batch. It is in the payload rather than
            # counted inside a rule because a run parks and comes back in
            # another process (D23): a counter held by the rule would start
            # again at nought, so "no more than one refund per conversation"
            # would let the second one through exactly when it mattered.
            checked, decision = chain.run(
                "step.tool.before",
                {
                    "name": call.name,
                    "args": args,
                    "so-far": [c.name for s in result.steps for c in s.tool_calls]
                    + [c.name for c in ran],
                },
            )
            # What the rule left is what happened. A `hide-values` rule masking
            # inside `args` has to reach the RECORD as well as the call: the
            # trace is the transcript, and a card number the tool never saw but
            # the trace kept has still left the building, which is the one thing
            # `interceptors/redact-card-numbers.yaml` exists to stop.
            #
            # Before the redirect below rather than after it, because a
            # redirected call is recorded too — `ran.append(call)` runs on that
            # path as well — and a value that must not survive in the record must
            # not survive on the path where the tool never even ran. Rewriting
            # `call` decides what is WRITTEN DOWN, never what runs; the redirect
            # still breaks out before `fn(...)` is reached.
            #
            # Everything below then reads `call`, including the tool itself. One
            # place holds what the rules left, so the record and the call cannot
            # disagree about it — which they did for a round, when the tool was
            # handed the masked args and the trace kept the original.
            call = ToolCall(call.name, checked["args"])

            # At-most-once, from the author's own `same-request-key:` line.
            #
            # AHEAD of `stop-the-run` below, and that order is measured rather
            # than preferred. `examples/refund-desk` binds
            # `interceptors/stop-runaway-refunds.yaml`, which counts calls to a
            # tool BY NAME — so the other order ends the run at the second
            # `payments` call with *"A second refund in one conversation needs a
            # person"* whether or not it is the same refund, and
            # `same-request-key: order-number` could never decide anything on
            # the shipped example. It is also the wrong sentence: telling a
            # person a second refund needs them, when the only thing asked for
            # was the first refund a second time, is the mis-statement T7
            # forbids. A withheld duplicate still lands in `ran`, so it still
            # counts towards that rule and a genuinely different second refund
            # stops the run exactly as before.
            #
            # AFTER `call = ToolCall(...)`, so the key is read off the arguments
            # the rules left and a withheld call is recorded with a card number
            # already masked.
            #
            # Bound arguments are merged first: `money.rs` holds
            # `same-request-key:` against `takes:` PLUS `bind:`, so a key the
            # surrounding system fills is a real key and reading it off the
            # model's arguments alone would find nothing there.
            sent = _with_binds(spec, call, supplied)
            # A name no tool answers to claims nothing. `hold` deliberately
            # claims before the tool is reached, because a call that ran and
            # then failed or timed out may still have moved money — nobody can
            # say it did not, so the key is spent and the retry is refused. A
            # name this run has no implementation for is the opposite case: it
            # cannot have done anything, and spending its key would tell the
            # model's next turn that a refund "already ran in this run" when
            # nothing ran at all. That is the same mis-statement this module
            # exists to remove, pointing the other way.
            can_run = call.name in tool_impls or call.name in delegates
            if can_run and (twice := once.hold(call.name, sent.args)):
                # Recorded as asked-for-and-not-done, exactly as a refused call
                # and a redirected one are: the model reads why on its next turn
                # instead of finding that the thing it asked for never happened
                # and nothing says so (T7).
                outputs.append(twice)
                ran.append(call)
                bus.emit("step.tool.cancelled", at=(i,), name=call.name, reason=WITHHELD)
                continue
            # A key the call never carried is a rule this run could not apply,
            # not a call to refuse. Same door `asking.undecided_on` goes out of,
            # a few hundred lines up, and for the same reason.
            for said in once.unenforced():
                if said not in result.unenforced:
                    result.unenforced += (said,)

            if decision.stop is not None:
                result.halted = "stopped-by-rule"
                result.output = decision.stop
                bus.emit("step.tool.cancelled", at=(i,), name=call.name, reason=decision.stop)
                return result

            if decision.redirect is not None:
                # A rule sent the run elsewhere instead of doing this (G5). The
                # call is recorded as asked-for-and-not-done rather than dropped:
                # it was DECIDED, exactly as a refused call is, and the model
                # reads why on its next turn instead of finding that the thing it
                # asked for never happened and nothing says so (T7). The calls
                # after it in this batch were merely never reached, which is how
                # the ceiling break below already leaves them.
                sent_to = decision.redirect
                outputs.append(
                    f"not done: a rule sent this run to the {sent_to!r} stage instead"
                )
                ran.append(call)
                bus.emit(
                    "step.tool.cancelled", at=(i,), name=call.name,
                    reason=f"sent to the {sent_to!r} stage",
                )
                break

            bus.emit("step.tool.started", at=(i,), name=call.name)
            # The surrounding system's own arguments, merged AFTER the chain
            # has run: a redaction rule still sees the real value, and the
            # model never saw the name at all. Merged once, above, because the
            # at-most-once record reads the same call the tool receives.
            out = _call_tool(tool_impls.get(call.name), sent)
            meter.tool_calls += 1
            # SHORTENED AT THE SOURCE, before anything reads it (P8 wave 5).
            #
            # Before the interceptor chain, deliberately: a redaction rule should
            # see what the model will actually be told, and running it over
            # thirty-six fields nobody will read is work for nothing. Before
            # `history`, necessarily — the whole point is that the payload never
            # becomes something paid for on every later turn.
            #
            # A projection nothing can run leaves the answer WHOLE and says so on
            # `unenforced` (built above): silently serving the full payload while
            # reporting success is the failure this line exists to remove.
            projecting = _projection_for(spec, call.name, sent.args)
            if projecting and run_program is not None:
                try:
                    out = str(run_program(projecting, {"result": out}))
                except Exception as e:  # noqa: BLE001 — a program's failure is data
                    out = f"error: the projection {projecting!r} could not run: {e}"
            # WHAT CAME BACK, through the same rules as everything else.
            #
            # Every other moment the chain is offered is "words are about to
            # leave", so nothing ever saw a RESULT: a card number the agent typed
            # into a `payments` argument was masked, and the same card number
            # `payments` handed back was not — while `redaction.yaml`'s own
            # promise is "what must never leave this workspace". A tool result
            # goes into `history` and is read back to the model on the next turn,
            # so an unmasked one leaves by the same door as anything else.
            #
            # The bus already emitted here; the chain was simply never handed it.
            # `Decision.stop` is honoured because a result can be the first sight
            # of something that must end the run; `redirect` is not offered at
            # this address (`Carries.somewhere_else` is false) because the call
            # has already happened and there is nothing left to send elsewhere.
            seen, decision = chain.run(
                "step.tool.completed", {"name": call.name, "content": out}
            )
            if decision.stop is not None:
                result.halted = "stopped-by-rule"
                result.output = decision.stop
                outputs.append(f"not done: {decision.stop}")
                ran.append(call)
                result.steps.append(
                    Step(index=i, text=text, tool_calls=tuple(ran), tool_results=tuple(outputs))
                )
                bus.emit("turn.run.cancelled", at=(i,), reason=decision.stop)
                return result
            out = seen["content"]
            # KEPT, where the author said to keep it (`remember-as:`).
            #
            # After the chain, and that is the point: a tool result goes into
            # `history` and is read back to the model next turn, and a fact is
            # re-stated into a later prompt by `context-policy`. Written before
            # the chain it would be the one copy of the answer nothing masked,
            # and the memory would put back exactly what the redaction took out.
            #
            # `Facts.record` is silent for a name the agent never declared, which
            # is also what makes this line inert in every tree that writes none.
            # A `never-from:` violation is refused at check time, where the author
            # is (`loader/a-tool-may-not-write-there`), so a document that reaches
            # a run cannot carry one.
            _keep_what_it_answered(spec, call, out)
            outputs.append(out)
            ran.append(call)
            bus.emit("step.tool.completed", at=(i,), name=call.name)

        result.steps.append(
            Step(index=i, text=text, tool_calls=tuple(ran), tool_results=tuple(outputs))
        )
        history.append(
            {"role": "assistant", "content": text, "tool_calls": [c.name for c in ran]}
        )
        for call, out in zip(ran, outputs):
            history.append({"role": "tool", "name": call.name, "content": out})

        # The ceiling was reached part-way through a batch. What did run is
        # recorded above — dropping it would lose actions that really happened —
        # and the rest never does.
        if out_of_calls is not None:
            meter.steps = i + 1
            return await _ran_out(
                out_of_calls, spec=spec, transport=transport, result=result,
                history=history, already=already, bus=bus, meter=meter, now=now,
                clock=clock, at=i, phase=phase_name, visits=visits, asking=asking, once=once, chain=chain, given=given,
            )

        visits[phase_name] = visits.get(phase_name, 0) + 1

        # The ledger is the ledger for THIS step, and the step is over. It was
        # declared once for the whole run and cleared nowhere, so a later step
        # calling the same tool with different arguments was answered from the
        # earlier step's cached result and the tool was never invoked. Measured
        # on the worked example: step 0 read ticket `T-1` and parked for a
        # connection consent; after the consent, step 1 asked for `T-999` and the
        # trace recorded `{'ticket-id': 'T-999', 'results': ['TICKET T-1: ...']}`
        # — another ticket's contents served as the answer, and a call claimed in
        # the transcript that never happened. A person's refusal travelled the
        # same way: one `no` about one call silently answered every later call to
        # that name, without anyone being shown it.
        #
        # It has to stay live for the whole of a PARKED step — pre-park
        # execution, refusals, the handoff branch, and the replay of `pending` on
        # resume — which is why it is cleared here, at the one point the batch is
        # fully recorded and the loop is about to move on, and not at the top.
        already = {}

        # A rule redirected the run. The stage's own `then:` is NOT consulted —
        # `send-elsewhere` names where it goes, and that naming is the whole
        # difference between it and `stop-the-run`. So a redirect is not a fourth
        # outcome: the three in `then:` stay three, because a redirect never
        # routes through them.
        #
        # The visit above is counted first, so a stage's `at-most:` still bounds
        # a rule that keeps sending the run back into it.
        if sent_to:
            bus.emit(
                "step.stage.completed", at=(i,), name=phase_name,
                outcome="sent-elsewhere", to=sent_to,
            )
            nxt = _sent_to(loop, sent_to, result, bus, i)
            if nxt is None:
                return result
            phase_name = nxt
            continue

        # An `answer` stage answers; that is the whole of what it is for. Any
        # call it made was refused above and is recorded, so nothing is lost by
        # reading the stage the way the author wrote it.
        outcome = "answered" if phase.does is Does.ANSWER else "used-a-tool"
        bus.emit("step.stage.completed", at=(i,), name=phase_name, outcome=outcome)
        nxt = _where_next(
            loop, phase, outcome, result, bus, i, run_program=run_program, said=text
        )
        if nxt is None:
            return result
        if nxt == DONE:
            return _finish(result, chain, bus, i, text, spec.facts)
        phase_name = nxt

    result.output = result.steps[-1].text if result.steps else ""

    # The step ceiling. It is the loop's own bound rather than a row checked
    # inside it, but it ends the run through the same door as every other
    # ceiling, so `steps-at-most` and `cost-per-request-under` cannot drift into
    # behaving differently — which is exactly what happens when each limit gets
    # its own ending.
    meter.steps = limit
    return await _ran_out(
        Reached(step_ceiling(limit), float(limit), spec.limits.when_it_runs_out),
        spec=spec, transport=transport, result=result, history=history,
        already=already, bus=bus, meter=meter, now=now, clock=clock, at=limit,
        phase=phase_name, visits=visits, asking=asking, once=once, chain=chain, given=given,
    )


def _park_state(
    parked: "Suspension",
    *,
    result: RunResult,
    history: list[dict[str, Any]],
    at: int,
    already: dict[str, str],
    once: "Ledger",
    given: dict[str, str],
    phase: str,
    visits: "dict[str, int] | None",
    meter: Meter,
    clock: Callable[[], float],
    text: str = "",
    awaiting: "tuple[ToolCall, ...]" = (),
) -> "Suspension":
    """Everything a resume needs, filled in one place (B1, B2, B4).

    Five sites parked a run and each filled a different subset by hand. Four of
    the five never set `used`, and `Meter.restored` falls back to the step index
    for STEPS alone — so seconds, tool calls, tokens and money all restarted at
    zero. MEASURED, with `tool-calls-at-most: 5`: three calls before an approval
    park and four after it, **seven against a ceiling of five**. Parking is what
    happens while a person decides whether money may go out, so the one place the
    guarantee is worth most is the one place it was lost.

    `spent_keys` was the same shape one field over: `Suspension.escalate` copied
    `used` and `granted` and dropped it, so a run that escalated could issue a
    payment it had already issued.

    A helper rather than five careful edits, because five careful edits is what
    was there. The two genuinely per-site values are `text` and `awaiting` — a
    budget park has no pending call and a tool park has both — and they are
    parameters with the empty default that is correct for the sites without them.
    """
    parked.steps = list(result.steps)
    parked.history = list(history)
    parked.step_index = at
    parked.completed = dict(already)
    parked.phase = phase
    parked.visits = dict(visits or {})
    # The three that carry a GUARANTEE across the process boundary, rather than
    # just the place the run had got to.
    parked.used = meter.as_dict(clock())
    parked.granted = dict(given)
    parked.spent_keys = once.used()
    if text:
        parked.text = text
    if awaiting:
        parked.awaiting = awaiting
    return parked


async def _ran_out(
    reached: "Reached",
    *,
    #: What this run has already spent a same-request key on. Required rather
    #: than defaulted, because a caller that forgets it loses the at-most-once
    #: guarantee across the park in silence — the failure mode this whole
    #: module exists to remove.
    once: "Ledger",
    #: The interceptor chain in force. Required rather than defaulted, for the
    #: reason `once` is: a caller that forgets it loses the rules on the closing
    #: answer in silence, and the closing answer is the one nobody planned for.
    chain: "Chain",
    #: What this run has already been allowed, by the name each wait was
    #: answered under. Required for the reason `once` and `chain` are: without
    #: it a budget park drops every consent the run had been given, so a person
    #: who approved a connection before the ceiling is asked for it again after
    #: it — the "asks twice for one permission" loop `granted` exists to end.
    given: dict[str, str],
    spec: AgentSpec,
    transport: Transport,
    result: RunResult,
    history: list[dict[str, Any]],
    already: dict[str, str],
    bus: Bus,
    meter: Meter,
    now: float,
    clock: Callable[[], float],
    at: int,
    phase: str = "",
    visits: dict[str, int] | None = None,
    #: The questions in force for this run. Passed rather than read back off
    #: `spec`, because `asking=` on `run()` is an override a host may hand in and
    #: a budget park that consulted `spec.asking` would put a question the host
    #: had just replaced. `None` means the agent's own, so a caller with nothing
    #: to override behaves exactly as before.
    asking: "Gate | None" = None,
) -> RunResult:
    """A ceiling has been reached. Do what the author said, and say which one.

    The three actions are not three severities of one thing. `stop-and-say-so`
    leaves the work unfinished and admits it; `ask-a-person` hands the decision
    to whoever owns the budget; `answer-with-what-it-has` trades completeness
    for an answer. Which is right depends on the work, so the author picks and
    the schema refuses a ceiling that does not.

    Every path sets `stopped_by`, including the one that produces a good answer.
    That is the property that makes the third choice safe to offer at all: "ran
    out and answered anyway" must never arrive looking like "finished".
    """
    result.stopped_by = reached
    result.halted = reached.ceiling.halted
    bus.emit(
        "turn.limit.completed",
        at=(at,),
        limit=reached.ceiling.field,
        ceiling=reached.ceiling.limit,
        reached=reached.at,
        action=reached.action.value,
    )

    if reached.action is Action.ASK:
        # The same suspension every other wait uses. A budget that has run out
        # is not a new kind of park; it is the run needing something from
        # outside itself, which is the primitive's whole definition. Eve keys a
        # session-limit continuation by session, separately from its four other
        # park kinds, and cannot express any of the other ceilings at all.
        budget_rule = rule_for(spec.pauses, OUT_OF_BUDGET)
        parked = suspend(
            OUT_OF_BUDGET,
            [_ask_for(OUT_OF_BUDGET, "decision")],
            at=at,
            about=["decision"],
            now=now,
            rule=budget_rule,
        )
        _park_state(
            parked,
            result=result,
            history=history,
            at=at,
            already=already,
            once=once,
            given=given,
            phase=phase,
            visits=visits,
            meter=meter,
            clock=clock,
        )
        # What the person reads: the author's `limits.asks` question, with the
        # figures it asks to be shown. `questions/keep-going.yaml` writes
        # `shows: [spent-so-far, steps-taken]`, and until this line existed it
        # was put to somebody who saw the answer contract and nothing else.
        # Tokens and money are real only where the transport reports them — the
        # same test `unmetered` applies — so a run that could not count them says
        # so instead of showing a zero to somebody deciding whether to spend
        # more.
        parked.in_words = words_for(
            (asking if asking is not None else Gate.of(spec.asking)).for_call(
                "decision", {}
            ),
            "decision",
            spent(
                parked.used,
                counted=callable(getattr(transport, "usage", None)),
                which_limit=reached.what,
            ),
            otherwise=_DEFAULT_ASKS[OUT_OF_BUDGET],
            contract=parked.asks,
            waits_for=budget_rule.answer_within if budget_rule else "",
            asked_of=tuple(budget_rule.who_can_answer) if budget_rule else (),
        )
        result.halted = "suspended"
        result.suspension = parked
        bus.emit("turn.run.failed", at=(at,), reason=OUT_OF_BUDGET)
        return result

    if reached.action is Action.ANSWER:
        # One closing call with NO tools offered, so the model has to answer
        # from what it already has instead of starting more work. smolagents
        # does the same at its step limit (`_handle_max_steps_reached`), and it
        # is the right shape: the alternative is to pay for everything and then
        # throw the answer away. The closing call is deliberately outside the
        # budget — charging for the work and withholding the answer helps
        # nobody — and the run still reports the ceiling it reached.
        bus.emit("step.model.requested", at=(at,))
        text, _ = await transport.model_call(spec.instructions, history, [])
        # THE SAME RULES AS EVERY OTHER REPLY. `_finish`'s docstring states the
        # guarantee this used to break, word for word: "a redaction rule cannot
        # be escaped by finishing from a stage rather than by running out of
        # steps." Running out of steps was the escape. A card number the author
        # forbade in an answer arrived whole in the one answer nobody planned
        # for, and the more expensive the run the likelier it was to be this one.
        answered, decision = chain.run("turn.message.after", {"content": text})
        if decision.stop is not None:
            # THE CEILING STAYS REPORTED. `limits.RAN_OUT` is the set a caller
            # asks "did it run out?" with, and this run did run out — a rule
            # firing on the way past must not make that unreportable. So
            # `halted` and `stopped_by`, both already set above, are left alone
            # and only the words change. The step carries the stop text rather
            # than the model's, because the answer that was refused must not
            # survive in the trace: a redaction visible nowhere but the
            # transcript is a redaction in name only.
            result.output = decision.stop
            result.steps.append(Step(index=at, text=decision.stop))
            bus.emit("turn.run.cancelled", at=(at,), reason=decision.stop)
            return result
        said = answered["content"]
        result.steps.append(Step(index=at, text=said))
        result.output = said
        bus.emit("turn.message.completed", at=(at,), text=said)
        bus.emit("turn.run.completed", at=(at,))
        return result

    result.output = reached.sentence()
    bus.emit("turn.run.failed", at=(at,), reason=reached.ceiling.halted)
    return result


def _said(parked: "Suspension", given: Mapping[str, Any], fallback: str) -> Any:
    """What the person answered, whatever the question turned out to be called.

    The name comes from the wait itself, because the author names it: once
    `limits.asks` or a `pauses/` rule points at a `questions/` entry (G7), the
    field is whatever that entry declared, and a hardcoded key silently reads
    nothing on every such run — the wait re-parks and the person's answer
    vanishes without a word. `fallback` is the built-in name used when no
    question was named, so a wait with no author rule behaves exactly as before.
    """
    for expect in parked.asks:
        if expect.name in given:
            return given[expect.name]
    return given.get(fallback, "")


def _ask_for(reason: str, name: str) -> Expect:
    """What one wait asks about one thing, before an author's question replaces it.

    A yes-or-no, carrying the wording that goes with it — deliberately not a
    pair of options named approve and deny. That pair is what makes Eve's budget
    prompt pretend to be an approval, and having a shape here is what lets an
    author swap in `questions/how-much-to-refund.yaml` without the loop learning
    a second way to ask (G7).

    One reason wants free text instead, and it is the one that is not a person's
    decision at all: a teammate's REPLY is the result of the call that delegated
    to them (`suspension.clears` says so, and accepts any non-empty answer for
    it). Asking for a yes-or-no there means `Suspension.answer(policy_checker=
    "the policy allows it")` is refused by its own contract while `clears` would
    have taken it.
    """
    if reason == WAITING_FOR_ANOTHER_AGENT:
        return Expect(name, ANYTHING, means=_DEFAULT_ASKS[WAITING_FOR_ANOTHER_AGENT])
    return Expect(name, GO_AHEAD, means=_DEFAULT_ASKS.get(reason, ""))


def _with_binds(spec: AgentSpec, call: "ToolCall", supplied: Mapping[str, Any]) -> "ToolCall":
    """The call as the tool receives it — the model's arguments plus the
    author's bound ones. A copy, so what was recorded on the trace stays what
    the model actually chose."""
    filled = _bound_args(spec, call, supplied)
    if not filled:
        return call
    return ToolCall(name=call.name, args={**call.args, **filled})


#: The two namespaces a `bind:` source may name, and where each is filled from.
#:
#: `run-inputs.` is what the surrounding system passed for this run; `remembers.`
#: is what this conversation already knows. Both are stated here rather than
#: parsed at each site, because there were two sites and they disagreed: one
#: stripped `run-inputs.` and left `remembers.` alone — so a bind from memory
#: looked up the literal key `"remembers.verified-account"`, found nothing, and
#: made the call WITHOUT the identity — and the other glued the prefix back on,
#: reporting the miss as `run-inputs.remembers.verified-account`, a namespace
#: that does not exist.
RUN_INPUTS = "run-inputs."
REMEMBERS = "remembers."


def _bind_source(written: str) -> tuple[str, str]:
    """A `bind:` line split into the namespace it names and the name in it.

    A source with no prefix is a `run-inputs:` key written the short way, which
    is what every tree wrote before `remembers.` existed and what the field's
    own help still shows.
    """
    if written.startswith(REMEMBERS):
        return REMEMBERS, written[len(REMEMBERS):]
    if written.startswith(RUN_INPUTS):
        return RUN_INPUTS, written[len(RUN_INPUTS):]
    return RUN_INPUTS, written


def _bind_value(spec: AgentSpec, written: str, supplied: Mapping[str, Any]) -> Any:
    """What fills this `bind:` line on this run, or nothing.

    `None` means nothing filled it — reported by the caller, never passed on as
    an empty string: an empty customer id is worse than a call that says out loud
    that the identity never arrived.
    """
    namespace, name = _bind_source(written)
    if namespace == REMEMBERS:
        return spec.facts.value(name)
    return supplied.get(name)


def _keep_what_it_answered(spec: AgentSpec, call: "ToolCall", answered: str) -> None:
    """Write this action's answer where `remember-as:` says to put it.

    Looked up by the ACTION the call names, exactly as `_bound_args` looks up a
    bind, so the two halves of one pair are addressed the same way.
    """
    tool = next((t for t in spec.tools if t.name == call.name), None)
    if tool is None or not tool.remembers:
        return
    named = str(call.args.get("action") or "")
    if named in tool.remembers:
        where = tool.remembers[named]
    elif "" in tool.remembers:
        where = tool.remembers[""]
    elif len(tool.remembers) == 1 and not named:
        where = next(iter(tool.remembers.values()))
    else:
        return
    spec.facts.record(where, answered)


def _bound_args(spec: AgentSpec, call: "ToolCall", supplied: Mapping[str, Any]) -> dict[str, str]:
    """The author's `bind:` lines for this call, filled from `run-inputs`.

    Looked up by the ACTION the call names, falling back to a tool with a single
    action and then to the `""` key a tool with no `actions:` block uses. The
    model never chose these and cannot have named them: they are not in
    `parameters`, which is the whole of the field's promise.

    Returns the pairs that could be filled. What could not is reported by the
    caller — an empty string in place of a customer id is worse than a call that
    says out loud that the identity never arrived.
    """
    tool = next((t for t in spec.tools if t.name == call.name), None)
    if tool is None or not tool.binds:
        return {}
    named = str(call.args.get("action") or "")
    if named in tool.binds:
        wanted = tool.binds[named]
    elif "" in tool.binds:
        wanted = tool.binds[""]
    elif len(tool.binds) == 1 and not named:
        wanted = next(iter(tool.binds.values()))
    else:
        return {}
    out: dict[str, str] = {}
    for arg, source in wanted.items():
        value = _bind_value(spec, source, supplied)
        if value is not None:
            out[arg] = str(value)
    return out


def _unfilled_binds(spec: AgentSpec, supplied: Mapping[str, Any]) -> tuple[str, ...]:
    """Every `bind:` line nothing on this run can fill, in the author's words.

    Reported once, before the first model call, rather than per call: an author
    who left `customer-id` out of what the surrounding system passes has one
    thing to fix, not one per refund.
    """
    out: list[str] = []
    for tool in spec.tools:
        for action, wanted in sorted(tool.binds.items()):
            for arg, source in sorted(wanted.items()):
                if _bind_value(spec, source, supplied) is not None:
                    continue
                namespace, key = _bind_source(source)
                where = f"{tool.name}/{action}" if action else tool.name
                # The namespace the AUTHOR wrote. It used to print
                # `run-inputs.` in front of whatever was written, so a bind from
                # memory was reported as `run-inputs.remembers.verified-account`
                # and the fix it implied did not exist — the same defect the
                # checker's own diagnostic goes out of its way to avoid, on the
                # other side of the same field.
                nothing = (
                    "this conversation remembers nothing under"
                    if namespace == REMEMBERS
                    else "nothing supplied"
                )
                out.append(
                    f"bind: {where} needs {arg!r} filled from `{namespace}{key}`, "
                    f"and {nothing} {key!r} for this run — so the call is "
                    f"made without it."
                )
    return tuple(out)


def _unchecked_answers(spec: AgentSpec) -> tuple[str, ...]:
    """Every action whose `answers-with:` this runtime cannot hold a result to.

    A tool here returns a string, so a declared return type is a promise this
    loop has nothing to check against. A host whose tools return typed values
    checks them with `pydantic_ai_interop.return_schema_for`.
    """
    return tuple(
        f"answers-with: {tool.name}/{action} says what it hands back "
        f"({', '.join(sorted(shape))}), and this runtime hands a tool's result to "
        "the model as text, unchecked — run it on a host whose tools return "
        "typed results to hold it."
        for tool in spec.tools
        for action, shape in sorted(tool.answers_with.items())
    )


def _call_tool(fn, call: "ToolCall") -> str:
    """Run one tool, and treat a failure as data rather than as a crash.

    `out = fn(call.args)` had no guard at any of its three sites, so a tool that
    raised took the whole run with it: a two-step run where `zendesk` had already
    succeeded and `payments` timed out produced no `RunResult` at all — no
    `halted`, no `trace()`, no `suspension` — so the call that really happened was
    unrecoverable and there was nothing to resume from.

    `delegation.one()` states the rule this follows: *"a child's failure is data,
    not a crash."* D14 makes MCP the headline no-code tool mechanism, and a
    network timeout is that mechanism's ordinary failure — the model can read
    `error: ...` and decide what to do, exactly as it does for a tool that does
    not exist.

    `asyncio.CancelledError` is re-raised: a cancelled run is not a failed tool,
    and swallowing it would make a stopped run look like one that carried on.
    """
    if fn is None:
        return f"error: no tool named {call.name!r}"
    try:
        return fn(call.args)
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001 — the point is that nothing escapes
        return f"error: {call.name!r} could not run: {e}"


def _asked_at(
    asking: Gate, reason: str, name: str, args: Mapping[str, Any]
) -> "Question | None":
    """The author's question for one thing at one park, or nothing.

    One place, so the question the wait is KEYED on and the question the person
    is SHOWN cannot come from two different lookups.

    Nothing for a teammate this process cannot run. `questions_for` registers
    `teamwork.asks` against every member's name, and that registration is for the
    park where a member FAILED and the author said to ask — not for the park
    where the run is simply waiting on somebody else's process. Without this the
    second borrowed the first's wording: a run waiting on `fraud-checker`
    rendered *"Please check this before it happens."* and asked for `approved`
    and `because`, so the teammate's own reply could not clear the wait it was
    the answer to. It is the same mistake `Rule.for_reason` was added to fix one
    park over, and it is fixed here rather than there because there is no rule to
    narrow — §7.14 WAIT-2 configures nothing for this reason, deliberately: a
    teammate is not a person to ask.
    """
    if reason == WAITING_FOR_ANOTHER_AGENT:
        return None
    return asking.for_call(name, args, reason)


def _asks_about(reason: str, name: str, question: "Question | None") -> list[Expect]:
    """What one wait asks about one thing: a yes-or-no, or a whole schema."""
    if question is None:
        return [_ask_for(reason, name)]
    how_many = len(question.answer)
    return [
        Expect(where(name, f, how_many), shape, means=question.asks)
        for f, shape in question.answer.items()
    ]


def _meter_usage(transport: Transport, meter: Meter) -> None:
    """Add what the last model call cost, if the transport can say.

    Optional rather than part of `model_call`, because most transports honestly
    cannot answer — a scripted model has no price and no tokeniser — and a
    required field that most implementers have to invent a number for is worse
    than an absent one. What a transport cannot measure is reported as
    unenforced at the top of the run instead of being guessed at here.
    """
    report = getattr(transport, "usage", None)
    if not callable(report):
        return
    counted = report()
    if counted is None:
        # HAS the method and could not measure THIS call. Distinct from not
        # having it at all, and until this line it was a `TypeError` unpacking
        # `None` — a transport that answered honestly took the run down.
        #
        # The docstring above already states the rule: *"what a transport cannot
        # measure is reported as unenforced at the top of the run instead of
        # being guessed at here"*. It was true of a transport with no `usage()`
        # and not of one whose `usage()` returned nothing, which is the same
        # fact arriving by a different route. `A2ATransport` is that case:
        # another agent's token count is not ours to know.
        return
    tokens, money = counted
    meter.tokens += int(tokens)
    # `None` is a transport that counted the call and could not price it — a
    # locally-served model with no `cost:` block. The token count still reaches
    # `tokens-at-most`; the money ceiling is on `RunResult.unmetered` and there
    # is nothing to add. Adding 0.0 here would be the same "spend cap that can
    # never be reached" `_metering` opens by forbidding.
    if money is not None:
        meter.money += float(money)


def _window(transport: Transport, pinned: str = "", workspace: str = "") -> int | None:
    """How much this model can hold, if anything here can say.

    Probed exactly as `usage` is, and optional for the same reason: a scripted
    stand-in has no window, and a required field most implementers would have to
    invent a number for is worse than an absent one. A policy that cannot be
    measured is named on `RunResult.unmetered` rather than skipped in silence.

    The transport is asked FIRST and its answer wins, because the transport is
    what actually ran: a runtime serving the same weights with a shorter
    `num_ctx` than the catalogue publishes knows something the catalogue does
    not, and tidying against the larger figure would overflow it.

    `pinned` is the author's `model:` line, and it is the fallback rather than
    the override. It closes the case that had no answer at all — a transport
    that cannot say, under an agent that named exactly which model it wants — by
    asking the catalogue the same question the transport would have. A pin that
    DISAGREES with what the transport bound is a mis-binding and is reported on
    `RunResult.unmetered`; it never silently changes the number the policy is
    measured against.

    `workspace` brings the override layer into the fallback. A machine serving a
    model this distribution has never heard of writes a row for it in its own
    `models/catalog.yaml`; a run that never opened that file would accept the
    row at check time and still report the policy as unmeasurable, which is the
    same half-connected seam one hop along.
    """
    says = getattr(transport, "context_window", None)
    window = says() if callable(says) else None
    if window:
        return int(window)
    # Nothing on the transport can say. Two things here might still know which
    # model this is — the author's pin, and the id the transport bound — and
    # both are looked up in the catalogue rather than guessed from.
    from . import resolve as _resolve

    for named in (pinned, str(getattr(transport, "model", "") or "")):
        if not named:
            continue
        catalogued = _resolve.window_of(named, workspace=workspace or None)
        if catalogued:
            return int(catalogued)
    return None


def _never_reached(
    spec: AgentSpec, transport: Transport, prices_money: bool
) -> tuple[str, ...]:
    """Money ceilings whose meter is correct and always zero.

    `Limits.priced_at_nothing` decides; this supplies the price and writes the
    sentence. The price is the BOUND model's — a fact about the binding, not
    about the file, which is why this is answered at run time and not by
    `pact check`: the author's `model:` line may be absent (`examples/refund-desk`
    writes none) and the transport's own default is then what actually runs.

    Scoped to what this run can be sure of, and the sentence says so. The
    working model and the `summarised-by:` model are both looked up, because
    both spend on this run's own meter. A TEAMMATE's spend arrives through
    `handoff.spent` and is charged here too, but the child binds its own
    transport and this process cannot see that binding — so the wording is about
    the calls this run makes for itself, which is what was actually checked.

    **"Asked and got zero" is not "never asked", and this used to say the
    second in the words of the first.** The sentence below asserts a fact about
    the author's own tree — *"the model catalogue publishes that row at 0 USD in
    and 0 USD out"* — and then D11 hangs a recommendation off it. On a transport
    with no `.model` and a spec with no `model:`, `models` is `[""]`: the loop
    `continue`d past every lookup, `total` stayed at its initial `0.0`, and
    `Limits.priced_at_nothing(0.0)` reported every money ceiling as priced at
    nothing, having asked the catalogue nothing. The `None` guard that exists for
    exactly this is INSIDE the loop and never ran. So a claim about a catalogue
    row was fabricated for an empty model name, and the `tokens-at-most: 200000`
    fix beside it was sized from a price nobody published — a recommendation
    founded on an invented row, which inverts D11 rather than meeting it.
    `asked` is therefore counted rather than inferred from `total`.
    """
    if not prices_money or not spec.limits.ceilings():
        return ()
    from . import resolve as _resolve

    ws = spec.workspace or None
    models = [str(getattr(transport, "model", "") or "") or spec.model]
    if spec.context_policy is not None and spec.context_policy.summarised_by:
        models.append(spec.context_policy.summarised_by)
    #: A million tokens in and a million out, on every model this run can bill
    #: for itself. Anything above zero and the ceiling is reachable.
    total = 0.0
    #: How many of those models the catalogue was actually asked about. Zero
    #: means nothing here knows which model runs, so there is no row to make a
    #: claim about and `total`'s `0.0` is an initial value rather than a price.
    asked = 0
    for name in models:
        if not name:
            continue
        priced = _resolve.price_of(name, 1_000_000, 1_000_000, workspace=ws)
        if priced is None:
            return ()  # unpriced is `unmetered`'s business, not this one
        total += priced
        asked += 1
    if not asked:
        return ()  # nothing was looked up, so nothing can be said about a row

    out: list[str] = []
    # A spec built in code carries no key and no tree, and `locate` then names
    # the path it would have been at. `<this agent>` rather than an empty
    # segment, so the sentence reads as the shape of a path instead of as a
    # broken one — `diagnostics.locate` makes the same choice for a document
    # handed over without its files.
    whose = f"agents/{spec.key}" if spec.key else "agents/<this agent>"
    for field in spec.limits.priced_at_nothing(total):
        file, line = locate(
            Path(spec.workspace) if spec.workspace else None,
            whose,
            "limits",
            "limits",
            field,
        )
        out.append(
            f"{file}:{line} — `{field}` is measured against "
            f"`{models[0]}`, and the model catalogue publishes that row at "
            f"0 USD in and 0 USD out. Every call this run makes for itself costs "
            f"0.00, so nothing it does on its own can reach this ceiling. "
            f"fix: write `tokens-at-most: 200000` beside it — that is the "
            f"ceiling that still bites when the model is free."
        )
    return tuple(out)


def _summariser(
    transport: Transport,
    spec: AgentSpec,
    charge: "Callable[[tuple[int, float] | None], None] | None" = None,
) -> "Summariser | None":
    """The author's `summarised-by:` line, ready to run, or nothing.

    `summarise-older` is the one rung of a context policy that needs a model
    call, and `context-policy.summarised-by:` is where the author says which
    model makes it — separate from the one doing the work, because a weaker
    model summarising its own history compounds its own mistakes. Eve gets this
    right too (`PublicAgentCompactionDefinition`), and it is one of the few
    places PACT copies rather than generalises.

    What was missing was the last hop. The field was parsed, validated and
    resolved, and the only way to make it *do* anything was for a host to write
    Python and pass `summarise=` in — so `examples/refund-desk`'s ladder fell
    through `summarise-older` to `keep-recent-only` and then to
    `if-it-still-does-not-fit: ask-a-person`, on a conversation a summariser
    would have handled. This asks the transport to re-bind to the named model
    instead. A transport that cannot returns nothing, and the run says so on
    `RunResult.unmetered` rather than leaving a rung that quietly never fires.
    """
    policy = spec.context_policy
    if policy is None or not policy.summarised_by:
        return None
    writes = getattr(transport, "write_summary", None)
    if not callable(writes):
        return None
    model = policy.summarised_by
    reports = getattr(transport, "summary_usage", None)

    def summarise(messages: Any, previous: str) -> str:
        # The summariser is shown the conversation as text and the summary it
        # wrote last time, which is the checkpoint rule: a summary is extended,
        # never summarised again.
        said = str(writes(summary_request(messages, previous), model))
        # What that second call cost, if the transport can say. Optional exactly
        # as `usage` is, and reported as unenforced when it cannot — an author
        # who wrote a spend cap and a `summarised-by:` model is otherwise paying
        # for a call that no ceiling counts and nothing names. `None` back from
        # `summary_usage()` means the call happened and nobody could price it,
        # which `charge` reports; it is NOT the same as `(0, 0.0)`, and treating
        # the two alike is what billed an unpriced summariser at nothing.
        if charge is not None and callable(reports):
            charge(reports())
        return said

    return summarise


def _tidy(
    tidier: "Tidier", history: list[dict[str, Any]], bus: Bus, at: int
) -> tuple[list[dict[str, Any]], "Tidied | None"]:
    """Apply the author's context policy to the running history.

    Returns the history unchanged and `None` when nothing needed doing, so a
    conversation that fits is not converted back and forth for no reason and a
    run with a policy it never triggers is byte-identical to one without.

    Called from a worker thread (`run()` says why), so the two events below are
    emitted off the loop. That is a real consequence and worth stating: an
    observer registered on `step.compaction.*` may be called from a thread other
    than the one that registered it. Nothing in the bus minds — the ledger is a
    list and appending to one is indivisible — and the ordering an observer can
    rely on was already the ordering of a run with concurrent delegates, which
    is per-member and never global.
    """
    messages = from_history(history)
    if not tidier.needed(messages):
        return history, None
    bus.emit("step.compaction.started", at=(at,), before=tidier.measure(messages))
    tidied = tidier.apply(messages)
    bus.emit(
        "step.compaction.completed",
        at=(at,),
        before=tidied.before,
        after=tidied.after,
        outcome=tidied.outcome,
        did=list(tidied.fired),
        notes=list(tidied.notes),
    )
    return to_history(tidied.messages), tidied


#: Argument names a model reaches for when handing work to a teammate. Checked
#: in a fixed order so the same tree produces the same request text on every
#: transport — a delegation whose wording depends on dict order is not portable.
_REQUEST_KEYS: tuple[str, ...] = ("message", "question", "ask", "task", "input")


def _request(call: ToolCall, step_text: str) -> str:
    """What the parent is actually asking this member.

    Eve degrades a delegation to `{message: string}` and loses everything else;
    here the whole call is preserved and only *rendered* as text, so a typed
    request can replace this without the members noticing.
    """
    for key in _REQUEST_KEYS:
        value = call.args.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return json.dumps(call.args, sort_keys=True) if call.args else step_text


def delegate_by_running(
    document: dict[str, Any],
    transport_for: Callable[[AgentSpec], Transport],
    tool_impls: dict[str, ToolFn] | None = None,
    bus: Bus | None = None,
) -> Asker:
    """Ask a team member by *running* it — this same harness, one level down.

    Delegation is not a different execution model, so it does not get a
    different loop. A member is an agent in the same document, run by the same
    `run`, and its budget is whatever the join policy granted it.

    Its budget really is: the grant becomes the child's own
    `cost-per-request-under`, and what the child spent is charged back to the
    grant when it returns. For a round neither happened — `Grant.spend` had no
    caller anywhere outside tests — so the allowance the join policy computed was
    published on `step.delegate.started` and enforced by nothing, `OverBudget`
    was unreachable on any real run, and a member with no `limits:` of its own
    (which both members of the worked example are) ran unmetered. That is
    verbatim the failure Y10 and §4.3 [R5] exist to prevent: "the supervisor plus
    two specialists could run past the author's `cost-per-request-under: 0.05
    USD` while the author believed they had capped it".

    The gate is NOT suppressed for a member. A specialist with its own
    `policy: ...` is an agent whose approval rules are its own, and a parent
    running it must not be able to turn them off by being the caller.
    """

    async def ask(grant: Grant) -> str:
        member = AgentSpec.from_document(document, grant.member)
        # `asks-itself-at-most:` is spent per ACTIVATION, against the meter the
        # requesting run shares down (`run.at_work`, riding the grant). The
        # refusal is this member's failure — the same path `OverBudget` takes —
        # so the author's `if-someone-fails:` decides what happens next rather
        # than the whole run crashing. A grant that carries no meter (an asker
        # called outside `run`) has nothing to count against and spends nothing.
        figure = member.limits.asks_itself_at_most
        at_work: dict[str, int] | None = getattr(grant, "at_work", None)
        # THE DYNAMIC-BOTTOM RULE (P4). An agent put to work BY VALUE — admitted
        # because a `run-inputs:` value of shape `agent` named it, not because
        # the author wrote it under `team:` — may only be reached if it writes
        # its own `limits.asks-itself-at-most:` figure.
        #
        # This is the static rule relocated, not a new one. `pact-loader`'s
        # `teams.rs` legalises a `team:` circle exactly when every member on it
        # writes the figure, and that check is what makes recursion terminate.
        # It can only be made over a graph that exists at check time; under
        # dynamic dispatch the potential call graph is "any agent an
        # `agent`-shaped value can name", which is every agent in the workspace
        # and no smaller set. So the member-writes-its-own-figure obligation
        # moves off the circle and onto the receivable agent, where it can be
        # decided from that agent alone.
        #
        # Refused HERE and not at admission, because here is where the member's
        # own `limits:` is read and where a refusal becomes that member's
        # FAILURE — the same `OverBudget`-shaped path — so the author's
        # `if-someone-fails:` decides what happens next. Refusing at admission
        # would take the whole run down over a name the author never wrote.
        # `base: yes` says it never runs, and a VALUE is the door that skips
        # every check the tree could have made: the name arrives from a
        # surrounding system this document cannot see. Five doors already hold
        # that promise at check time — `team:`, a port's `answers:`, a stage's
        # `may-use:`, `discover` and `card` — and this is the sixth, the only one
        # the harness has to hold itself.
        #
        # A SECOND rule, not a special case of the one below it: a base may
        # perfectly well carry `asks-itself-at-most:` — it is the pattern its
        # descendants inherit — and satisfy the dynamic-bottom rule completely
        # while still being a thing that must never run.
        #
        # Refused here rather than at admission for the reason everything else
        # here is: this is where the member's own document is read, and a refusal
        # here is that member's FAILURE, so `if-someone-fails:` decides.
        entry = (document.get("agents") or {}).get(grant.member)
        if isinstance(entry, Mapping) and said_yes(entry.get("base")):
            raise RuntimeError(
                f"'{grant.member}' says `base: yes`, so it never runs — it is something "
                f"for other agents to be `based-on:`, not something work is handed to. "
                f"Name an agent that answers for itself."
            )
        if figure is None and grant.member in getattr(grant, "named_by_value", ()):
            raise RuntimeError(
                f"'{grant.member}' was named for this request by value, and an "
                "agent put to work by name may only be reached if it writes its "
                f"own bottom. Add `limits.asks-itself-at-most:` to "
                f"'{grant.member}' — the figure says how many times one request "
                "may put it to work."
            )
        if (
            figure is not None
            and at_work is not None
            # The meter is keyed by AgentSpec.name (what run() increments),
            # which is the `name:` line when the author wrote one and the map
            # key otherwise. Reading by the map key here would let an agent
            # whose `name:` differs from its key recurse past its own figure.
            and at_work.get(member.name, 0) >= figure
        ):
            raise RuntimeError(asked_too_often(grant.member, figure))
        # The share is the child's ceiling, not merely a number the parent
        # remembers. A member that writes its own tighter `limits:` keeps it —
        # the smaller of the two binds, because inheriting a budget downward
        # must never RAISE one the child set for itself.
        #
        # BOTH readers of `cost-per-request-under:`, and not just the one that
        # enforces. `Limits` and `Slo` are built from the same authored block, so
        # a member that wrote `NaN USD` has the figure recorded in two places;
        # replacing one left the other saying the cap held nothing while the run
        # was being held to the join policy's real 0.10 USD share — the same
        # stale-claim defect `Limits.__post_init__` clears, one object over.
        # `delegation.granted` is the one place that is done, so a runtime other
        # than this harness holds a member to the same figure.
        member = granted(member, grant.allowance)
        asked = request_for(grant)  # what earlier members said, then the request
        out = await run(
            member, transport_for(member), asked, tool_impls or {}, bus=bus,
            # The parent's meter, so the member's activation is the same
            # request's spending and not a fresh count. Inert when no figure is
            # written anywhere: the dict fills and nothing reads it.
            at_work=at_work,
            # Recursion exactly where it is budgeted: a member that wrote the
            # figure may ask its own team — itself included — through this same
            # asker, and the meter above is what bounds it. A member without
            # the line keeps the old behaviour to the byte: a teammate is work
            # happening elsewhere, and its run suspends for it.
            ask_member=ask if figure is not None else None,
        )
        # What it cost comes off its share. `OverBudget` is raised as this
        # member's failure rather than allowed out of the join, so the author's
        # `if-someone-fails:` decides what happens next — which is the whole
        # reason a failure is data here and not an exception.
        try:
            grant.spend(out.spent)
        except OverBudget as over:
            raise RuntimeError(str(over)) from None
        # A member that ran out of its own budget still has something to say,
        # and what it says includes which ceiling it reached. Treating that as a
        # crash would hide a partial answer the parent could use; treating it as
        # a clean finish would hide that it was cut short.
        if out.halted != "final" and out.halted not in RAN_OUT:
            raise RuntimeError(f"{grant.member} stopped: {out.halted}")
        return out.output

    return ask


def _give_up(
    parked: Suspension, now: float, result: RunResult, bus: Bus
) -> RunResult | None:
    """Nobody answered in time. Returns a finished result, or `None` to carry on.

    Eve parks indefinitely — a run waiting on an approver who has left the
    company waits forever, and nothing anywhere can say otherwise. The one
    outcome deliberately unavailable here is approval: a timeout that approves
    turns "ask a person" into "wait a while, then do it".
    """
    if parked.if_nobody_answers == "escalate":
        result.halted = "suspended"
        result.suspension = parked.escalate(now)
        bus.emit(
            "turn.approval.failed",
            at=(parked.step_index,),
            reason=parked.reason,
            outcome="escalate",
        )
        return result
    if parked.if_nobody_answers == "stop-and-say-so":
        result.halted = "gave-up-waiting"
        result.output = (
            f"Stopped: nobody answered the request for {parked.reason} in time."
        )
        bus.emit(
            "turn.run.cancelled", at=(parked.step_index,), reason="gave-up-waiting"
        )
        return result
    bus.emit(
        "turn.approval.failed",
        at=(parked.step_index,),
        reason=parked.reason,
        outcome="decline",
    )
    return None


def _answer_shape_in_words(shape: Mapping[str, str]) -> str:
    """The author's `answers-with:` as an instruction to the model.

    Their own words for each field, unchanged — `one of approved, declined` is
    already the clearest statement of that constraint, and rewriting it into JSON
    Schema would put a second description of one rule in the tree.
    """
    lines = "\n".join(f"- {name}: {says}" for name, says in shape.items())
    return (
        "## What your answer must contain\n\n"
        "End your reply with each of these, one per line, using exactly these "
        "names:\n\n" + lines
    )


def _system_for(
    instructions: str,
    phase: Phase,
    skills: tuple[SkillSpec, ...] = (),
    answers_with: "Mapping[str, str] | None" = None,
    external: tuple[str, ...] = (),
) -> str:
    """The system text for one stage.

    The agent's own instructions stay first and unchanged: a stage adds to what
    the agent is, it does not replace it. Eve resolves one system prompt for the
    whole run, which is why a planning step there reads the same words as an
    answering one — here the stage's line is appended, so `plan` and `answer`
    differ by exactly what the author wrote and by nothing else.

    Then the written procedures this stage may read. They come LAST and under a
    heading of their own so that an agent's own instructions are never displaced
    by a long document, and so `may-use:` narrows the procedures a stage reads
    the same way it narrows the tools a stage may call — see
    `Phase.skills_offered` for the one asymmetry between the two.

    Then, and only then, `external` — text somebody outside this tree wrote, which
    today is an MCP server's own prose. AD-71 says it *"may never precede authored
    instructions"*, and the placement here is what makes that true of the whole
    system message rather than of one field of it: after the procedures, because
    AD-78 is explicit that a `SKILL.md` body IS the refund policy, so external
    text placed between `instructions:` and the procedures would sit in front of
    the policy it must never outrank. Unfenced text is REFUSED rather than fenced
    here as a kindness — a caller that got this far with raw server prose has a
    bug one level up, and quietly fixing it would hide whichever other path is
    handling the same text unfenced.
    """
    stage = phase.instruction()
    parts = [p for p in (instructions, stage) if p]
    if skills:
        body = "\n\n".join(s.in_words() for s in skills)
        parts.append(
            "## The written procedures you follow\n\n"
            "These are the rules of this work. Follow them exactly, and quote "
            "them when they decide something.\n\n" + body
        )
    if external:
        # The fence is checked by `mcp_bridge.fenced_regions`, not here. The
        # PLACING is this function's decision and differs from every other
        # caller's — after the procedures, because AD-78 says a `SKILL.md` body
        # IS the refund policy and external text in front of it would outrank
        # the policy. Whether the text may reach a model at all is not this
        # function's decision, and it was written twice before it was written
        # once: the same loop and the same `ValueError` in two wordings, which
        # is a fence that grows a gap the day one copy learns a case.
        from .mcp_bridge import fenced_regions

        parts.extend(fenced_regions(external))
    # LAST, after the procedures and after anything external, because it is what
    # to do with the answer once the rules have decided it — and because a shape
    # stated before a long document is the part a model forgets.
    if answers_with:
        parts.append(_answer_shape_in_words(answers_with))
    return "\n\n".join(parts)


def _where_next(
    loop: Loop,
    phase: Phase,
    outcome: str,
    result: RunResult,
    bus: Bus,
    at: int,
    run_program: "Callable[[str, dict[str, Any]], str] | None" = None,
    said: str = "",
) -> str | None:
    """The next stage's name, or `None` when the loop cannot say.

    An unrouted outcome is a gap in what the author wrote, so the run ends
    carrying the message `Loop.route` composed — which names the stage, the
    outcome, and the line to add. It returns `None` instead of raising so the
    steps already taken stay on the result: a run that got eight steps in before
    meeting a missing `then:` should still show those eight.
    """
    try:
        return loop.route(phase, outcome, run_program=run_program, said=said)
    except LoopError as e:
        result.halted = "loop-error"
        result.output = str(e)
        bus.emit("turn.run.failed", at=(at,), reason=str(e))
        return None


def _sent_to(
    loop: Loop, name: str, result: RunResult, bus: Bus, at: int
) -> str | None:
    """The stage a redirect named, or `None` when this loop has not got it.

    Deliberately `Loop.phase` — the same door `Loop.stage_to_run` opens — so a
    misspelled destination gets the loop's own diagnostic, which names the loop
    and lists the stages it has. A second message written here would be a second
    thing to keep in step with the first, and it would be the one telling an
    author which stages exist while the loop file changed underneath it.

    It ends the run the way `_where_next` does, and for the same reason: the
    steps already taken stay on the result, so a run that got eight steps in
    before meeting a typo still shows those eight.
    """
    try:
        loop.phase(name)
    except LoopError as e:
        result.halted = "loop-error"
        result.output = str(e)
        bus.emit("turn.run.failed", at=(at,), reason=str(e))
        return None
    return name


def _turn_ended(result: RunResult, facts: "Facts | None") -> RunResult:
    """Expire what the author said does not outlive a turn, and say which.

    Called from **every** path that ends a turn, and there are three: the loop
    reaching `done`, a stage answering, and the run running out of stages. The
    first version wired only one of the three, so a fact expired or survived
    depending on which way the run happened to finish — which is not a property
    anybody could have reasoned about from the document.

    NOT called on a suspension. A parked run is waiting, not finished, and
    expiring its facts would forget the approval it is parked on — the whole of
    G9: `payments-was-approved` has to survive the wait for the person who
    granted it.
    """
    if facts is not None:
        result.facts_expired = tuple(facts.something_happened(TURN_ENDS))
    return result


def _finish(
    result: RunResult,
    chain: Chain,
    bus: Bus,
    at: int,
    text: str,
    facts: "Facts | None" = None,
) -> RunResult:
    """The loop reached `done`; the stage's words become the turn's reply.

    Routed through `turn.message.after` like every other reply, so a redaction
    rule cannot be escaped by finishing from a stage rather than by running out
    of steps. The step that carried the words is rewritten to match, because a
    redaction visible in the answer but not in the recorded step would be a
    redaction in name only.
    """
    answered, decision = chain.run("turn.message.after", {"content": text})
    if decision.stop is not None:
        result.halted = "stopped-by-rule"
        result.output = decision.stop
        bus.emit("turn.run.cancelled", at=(at,), reason=decision.stop)
        return result
    said = answered["content"]
    if said != text and result.steps:
        result.steps[-1] = replace(result.steps[-1], text=said)
    result.output = said
    _turn_ended(result, facts)
    result.halted = "final"
    bus.emit("turn.message.completed", at=(at,), text=said)
    bus.emit("turn.run.completed", at=(at,))
    return result


def _out_of_budget(result: RunResult, bus: Bus, at: int) -> RunResult:
    """The run asked for more budget and did not get it. Distinct from
    `step-limit`, which is a run that was never allowed to ask."""
    result.halted = "out-of-budget"
    result.output = result.steps[-1].text if result.steps else ""
    bus.emit("turn.run.failed", at=(at,), reason=OUT_OF_BUDGET)
    return result
