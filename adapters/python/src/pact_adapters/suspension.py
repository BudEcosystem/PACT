"""Suspension — the one way a run stops and comes back.

Eve parks for five different reasons and each one is its own mechanism: a
pending-approval record keyed by tool call, an OAuth authorisation keyed by
scope, a subagent wait keyed by child turn, a session-limit continuation keyed
by session, and a deferred input request. Five state keys, five resume shapes,
and five guards deciding whether the answer that just arrived is the answer
*this* run was waiting for. Adding a sixth reason means writing all five parts
again — which is why its compiled manifest is at version 36.

They are one thing: **the run cannot continue until something outside it
happens.** All that differs between them is

* why it stopped — `reason`
* what has to come back — `asks`
* which wait an answer answers — `correlation_key`
* how long to wait, and what to do if nobody comes — `waits_for` and
  `if_nobody_answers`

so those are *fields*, not subsystems. A sixth reason costs one row in
[`REASONS`] — or an `x-` prefix, exactly as the event lattice already does for
subjects — and no new shape at all.

Two things Eve does not have, which fall out of unifying rather than being
added:

* **A wait can time out.** Eve parks indefinitely; a run waiting for an
  approver who left the company waits forever. Here every wait declares how
  long it lasts and what happens next, and what happens next is never
  "approve".
* **A stale answer cannot land.** One `correlation_key`, derived from what the
  run was actually waiting for, replaces five bespoke guards. An answer to a
  question the run has moved past is refused by name.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Sequence

# `4h`, `30m`, `500ms` — the same spellings the schema's `duration` accepts.
# One implementation, in `limits`, rather than a near-copy here: the copies
# this replaces all read `1m30s` as one second, a wait ninety times shorter
# than the one written, with nothing anywhere to say so.
from .limits import seconds
from .questions import (
    ANYTHING,
    LIBRARY as QUESTION_LIBRARY,
    SHIPPED_QUESTION,
    Question,
    Rejected,
    Shape,
    asking_stages,
    gated_actions,
    policies_over,
)

if TYPE_CHECKING:  # pragma: no cover - import cycle avoided at runtime
    from .harness import Step, ToolCall


# ─────────────────────────────────────────────────────────────── the vocabulary

NEEDS_APPROVAL = "needs-approval"
NEEDS_PERMISSION = "needs-permission"
WAITING_FOR_ANOTHER_AGENT = "waiting-for-another-agent"
OUT_OF_BUDGET = "out-of-budget"
CONTEXT_TOO_LONG = "context-too-long"

#: A stage of the authored loop that stops to ask a person (`does: ask-someone`).
#: Registered through the `x-` escape this module publishes rather than by
#: widening the closed list — the whole claim above is that a new reason costs
#: one string, so this is that claim being used rather than restated.
#:
#: It lives here rather than in the harness because it is the harness's *fifth*
#: reason to wait and this is where the other five are read off the author's
#: document. While it lived over there, `_named_questions` had no branch for it,
#: so an `ask-someone` stage parked with no audience, no deadline and no answer
#: shape — the one thing the schema says at `context-policy.asks` must never
#: happen: "a run that stops with nothing to ask is a run that hangs."
ASKED_A_PERSON = "x-asked-a-person"

#: Closed for the reasons PACT itself knows how to park for, open by
#: construction for anything else. The first four are Eve's five bespoke park
#: kinds, and the whole point is that they now differ only by this string.
#:
#: The fifth is the claim above being cashed. `if-it-still-does-not-fit:
#: ask-a-person` (G3) needed a new reason to park for, and it cost this row and
#: nothing else — a go-ahead is a go-ahead, whatever was being waited for. It is
#: listed here rather than taking the `x-` escape because it comes from a
#: `tier: core` field of the schema: an author writing core PACT should not end
#: up parked under a reason whose prefix says "somebody's own". Eve has no
#: equivalent at all — when its compaction ladder bottoms out it sends the
#: oversized history and says nothing (`harness/compaction.ts:241`).
REASONS: tuple[str, ...] = (
    NEEDS_APPROVAL,             # eve: pending HITL approval, keyed by tool call
    NEEDS_PERMISSION,           # eve: scoped OAuth park, keyed by scope
    WAITING_FOR_ANOTHER_AGENT,  # eve: subagent wait, keyed by child turn
    OUT_OF_BUDGET,              # eve: session-limit continuation, keyed by session
    CONTEXT_TOO_LONG,           # eve: nothing — it truncates and carries on
)

#: What to do when nobody answers in time. `approve` is deliberately absent:
#: a timeout that approves turns "ask a person" into "wait a bit, then do it".
TIMEOUT_ACTIONS: tuple[str, ...] = (
    "stop-and-say-so",  # end the run and say why
    "decline",          # refuse the thing being waited on, keep going
    "escalate",         # stay parked, under a new key, for someone else to answer
)

#: The shape of a go-ahead. **Not a table of words, one row per reason.**
#:
#: A wait is cleared by a *yes*, read through the same [`Shape`] a question uses
#: to ask for one (G7). The table this replaces was Eve's "exactly two options
#: named approve and deny" reproduced once per park kind — so a sixth kind of
#: wait needed a sixth row, and a wait that wanted a number rather than a word
#: could not be expressed at any price. `Shape` accepts `approve`, `granted` and
#: `carry-on` as spellings of yes, so the words an author may already have
#: written keep working and no longer live here.
GO_AHEAD = Shape("yes-or-no")


class WrongAnswer(ValueError):
    """An answer that does not fit the wait it was given for.

    Typed so a caller can tell "the approver typed something odd" apart from
    "this answer belongs to a run that has already moved on", and refuse each
    differently.
    """


def check_reason(reason: str) -> str:
    """Reject a reason nobody can act on, naming the ones that work."""
    if reason in REASONS or reason.startswith("x-"):
        return reason
    raise WrongAnswer(
        f"{reason!r} is not a reason a run can wait. Use one of: "
        + ", ".join(REASONS)
        + " — or prefix your own with 'x-'."
    )


def clears(reason: str, answer: Any) -> bool:
    """Does `answer` let the run past a wait of this kind?

    Read through the answer's own shape rather than matched against a word, so
    every reason to wait — including one an author invents with an `x-` prefix —
    is cleared the same way, by a yes. Anything that is not a yes, including
    silence, leaves the run parked.

    A teammate's reply is the one exception: any non-empty answer clears that
    wait, because the reply *is* the result of the call that delegated to them.
    """
    if reason == WAITING_FOR_ANOTHER_AGENT:
        return bool(answer)
    try:
        return GO_AHEAD.read(answer) is True
    except Rejected:
        return False


def correlation_key(reason: str, at: int, about: Sequence[str]) -> str:
    """Which wait an answer answers.

    Derived from what the run was actually waiting for, so it is the same in
    every framework and the same before and after the process dies — the two
    properties Eve's five separate state keys each have to establish for
    themselves. Deliberately not random: two transports running the same tree
    must park under the same key, or a resume is framework-specific.
    """
    material = "|".join([reason, str(at), *sorted(about)])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


# ──────────────────────────────────────────────────────── what has to come back


@dataclass(frozen=True)
class Expect:
    """One thing a wait asks for before the run may continue.

    It carries a [`Shape`], not a list of permitted words (G7). That is the
    difference between a wait that can ask "how much should we refund?" and one
    that can only ever offer two options: Eve's request to a human *is* two
    options named approve and deny, so there is nowhere a shape could be written
    even if somebody wanted one, and its own session-limit prompt has to
    impersonate an approval as a result.

    `ANYTHING` — free text — is the shape for a wait with no closed answer, such
    as a teammate's reply or a reason for declining.
    """

    name: str
    shape: Shape = ANYTHING
    required: bool = True
    means: str = ""

    @property
    def choices(self) -> tuple[str, ...]:
        """The words a closed answer allows; empty for every other shape."""
        return self.shape.choices

    def check(self, value: Any) -> Any:
        """Read `value` as this shape, or refuse it saying what to type."""
        try:
            return self.shape.read(value)
        except Rejected as e:
            raise WrongAnswer(
                f"the answer to {self.name!r} {e.problems[0]}. "
                f"Write `{self.name}: {self.shape.example()}`."
            ) from None

    @staticmethod
    def parse(name: str, described: str) -> "Expect":
        """Read one line of a question's `answer:` block.

        The vocabulary is `questions.Shape`'s, which is the one the schema
        already uses for `answers-with:` — so an author who has written one has
        written the other, and `yes or no` works because it is what the schema's
        own help text tells them to type.

        Anything the vocabulary does not recognise is a sentence describing what
        to write, and is taken as free text. Refusing it would turn `answer:`
        into a closed list of five words and put "explain in your own words"
        out of reach.
        """
        text = (described or "").strip()
        try:
            return Expect(name, Shape.parse(text), means=text)
        except Rejected:
            return Expect(name, ANYTHING, means=text)


# ───────────────────────────────────────────────────────────────── the resuming


@dataclass(frozen=True)
class Resumption:
    """A typed answer to one suspension.

    It carries the key of the wait it answers, so an answer is never applied to
    a wait it was not written for. That single check replaces the per-park-kind
    guards Eve writes five times.
    """

    correlation_key: str
    values: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({"correlation-key": self.correlation_key, "values": self.values},
                          sort_keys=True)

    @staticmethod
    def from_json(text: str) -> "Resumption":
        d = json.loads(text)
        return Resumption(str(d.get("correlation-key", "")), dict(d.get("values") or {}))


# ─────────────────────────────────────────────────────────────── the rule itself


@dataclass(frozen=True)
class PauseRule:
    """An author's answer to "what happens while the run is stopped".

    There is deliberately **no `pauses/` kind in the schema**. Everything a rule
    needs — the wording, the answer shape, who is asked, the deadline, and what
    follows it — is already what a `question` is, and a second kind carrying the
    same five fields would be two places to write one thing and two places for
    them to disagree. So a pause rule is *derived*: for each reason a run can
    wait, the schema already names the question to ask, and this reads it.

        out-of-budget              `limits.asks`
        needs-approval             `policies.<the agent's>.ask-a-person[].question`
        needs-permission           `resources.<r>.asks-to-connect`
        context-too-long           `context-policies.<the agent's>.asks`
        x-asked-a-person           `loops.<the agent's>.steps.<stage>.asks`
        waiting-for-another-agent  nothing — a teammate is not a person to ask

    Every one of those `asks:` lines sits next to an `ask-a-person` choice, which
    is the rule the schema now holds throughout: a place that can stop and ask
    must be able to name what it asks, or the run parks with nothing to show and
    is indistinguishable from a hang.
    """

    when: str
    asks_for: tuple[Expect, ...] = ()
    waits_for: float | None = None
    if_nobody_answers: str = "stop-and-say-so"
    who_can_answer: tuple[str, ...] = ()
    #: `answer-within:` exactly as the author typed it, beside the seconds.
    #:
    #: Both, because two different readers need two different things: a clock
    #: needs `1800.0` and a person reads `30m`. It is carried here rather than
    #: recovered from the question shown, because the question shown may not be
    #: the question this rule came from — `how-much-to-refund` is put at a wait
    #: `is-this-ok` governs — and printing `answer within: 4h` above a wait that
    #: expires in thirty minutes tells somebody a thing the run will not honour.
    answer_within: str = ""
    #: Who is asked instead when nobody answers in time (`escalates-to:`), for
    #: `if_nobody_answers == "escalate"`. Carried here for the reason
    #: `answer_within` is: the question SHOWN at a wait may not be the one this
    #: rule came from, and the rule is what governs the deadline and what follows
    #: it — so the people to escalate to are the rule's, not the shown question's.
    escalates_to: tuple[str, ...] = ()

    @staticmethod
    def from_question(when: str, question: Mapping[str, Any]) -> "PauseRule":
        """One rule, read off the question the author already wrote."""
        check_reason(when)
        asks = tuple(
            Expect.parse(name, str(text))
            for name, text in sorted((question.get("answer") or {}).items())
        )
        action = str(question.get("if-nobody-answers") or "stop-and-say-so").strip()
        if action not in TIMEOUT_ACTIONS:
            raise WrongAnswer(
                f"{action!r} is not something to do when nobody answers. "
                f"Use one of: {', '.join(TIMEOUT_ACTIONS)}. "
                "There is deliberately no way to approve on a timeout."
            )
        return PauseRule(
            when=when,
            asks_for=asks,
            waits_for=seconds(question.get("answer-within")),
            if_nobody_answers=action,
            who_can_answer=tuple(_as_list(question.get("asked-of"))),
            answer_within=str(question.get("answer-within") or "").strip(),
            escalates_to=tuple(_as_list(question.get("escalates-to"))),
        )

    @staticmethod
    def from_document(doc: Mapping[str, Any], agent_key: str) -> tuple["PauseRule", ...]:
        """The waiting rules that apply to one agent, in reason order.

        A reason whose `asks:` line is missing simply has no rule, and a wait
        with no rule waits forever without ever proceeding on its own — the
        conservative direction, and the same one Eve is stuck in.

        A `pact:question/...` name resolves against `questions.LIBRARY`, which is
        the whole reason a gate written as `needs-a-person: yes` is not a weaker
        gate (F17). Without this line the short form parked with `waits_for`
        `None`, `who_can_answer` empty and `if_nobody_answers` defaulted — a run
        that waits forever, addressed to nobody, next to a shipped question whose
        own file says thirty minutes and `stop-and-say-so`. That is precisely the
        "resolved and read by nobody" defect one subsystem over, and it would
        have been invisible: the gate stops the call, so everything you can
        assert about the park is right.
        """
        questions = {**QUESTION_LIBRARY, **(doc.get("questions") or {})}
        rules: list[PauseRule] = []
        for reason, name in _named_questions(doc, agent_key):
            entry = questions.get(name)
            if isinstance(entry, dict):
                rules.append(PauseRule.from_question(reason, entry))
        return tuple(rules)


def rule_for(rules: Iterable[PauseRule], reason: str) -> PauseRule | None:
    return next((r for r in rules if r.when == reason), None)


def connections_needing_permission(
    doc: Mapping[str, Any], agent_key: str
) -> dict[str, str]:
    """The tools this agent may not use until a person allows the connection,
    each with the question that asks for it.

    Three lines the author already wrote, read as one chain: the agent's
    `uses:` names a tool, the tool's `connect:` names a server, and the server's
    `asks-to-connect:` names the question to put before anything goes over it.
    So which calls wait is derived from the document rather than from a list a
    host maintains beside it — which is the whole of D14 for this capability,
    since the person who added the payments server is not a person who could
    edit a host's Python.

    Per agent rather than per workspace, which is a fix this carries as well as
    a resolution. The reading it replaces scanned `resources:` whole and took
    the first entry with an `asks-to-connect:` line, so `fraud-checker` — which
    uses `zendesk` and nothing else — was handed a waiting rule derived from the
    payments server it cannot reach. Inert today, but the wrong kind of inert:
    only one rule survives per reason, so the first thing that ever parked that
    agent for a permission would have silently inherited payments' deadline and
    payments' approvers.
    """
    resources = doc.get("resources") or {}
    tools = doc.get("tools") or {}
    agent = ((doc.get("agents") or {}).get(agent_key) or {})
    waits: dict[str, str] = {}
    for used in sorted(_as_list(agent.get("uses"))):
        tool = tools.get(used)
        if not isinstance(tool, dict):
            continue  # a skill or a teammate, not a tool — it connects to nothing
        # `connect:` names ONE server, and `pact check` resolves it against
        # `resources:`. It used to be a one-key map (`mcp: payments-server`)
        # whose key nothing ever read and whose value nothing resolved, so a
        # one-character typo silently deleted this whole consent gate.
        server = str(tool.get("connect") or "").strip()
        entry = resources.get(server)
        if isinstance(entry, dict):
            # A locked room's `asks-to-run:` is the same wait one door over: the
            # consent in front of running a carried body there at all, asked
            # before the first run and kept for the room (`asked_as` is the
            # resource), exactly as a connection's is. Read here so the gate and
            # the pause rules learn of it from one walk, as they do of
            # `asks-to-connect:`.
            asks = str(entry.get("asks-to-connect", "")).strip()
            if not asks and str(entry.get("resource-kind", "")).strip() == "sandbox":
                asks = str(entry.get("asks-to-run", "")).strip()
            if asks:
                waits[used] = asks
    return waits


def question_for(doc: Mapping[str, Any], agent_key: str, reason: str) -> str | None:
    """The question this agent puts when it stops for `reason`, or `None`.

    The same reading `PauseRule.from_document` makes, for a runtime that has to
    ASK at a wait that is not about one call (a ceiling reached, a conversation
    that cannot be shortened enough, a teammate that failed) and so needs the
    question by name, not only the rule that governs its deadline.
    """
    return next((name for why, name in _named_questions(doc, agent_key) if why == reason), None)


def _named_questions(doc: Mapping[str, Any], agent_key: str) -> list[tuple[str, str]]:
    """Every `(reason, question name)` this agent could stop at.

    One place, so that a new reason means one line here and nothing else — and so
    that "which places can stop and ask?" is a list somebody can read rather than
    a search through the harness.
    """
    agent = ((doc.get("agents") or {}).get(agent_key) or {})
    found: list[tuple[str, str]] = []

    limits = agent.get("limits") or {}
    if str(limits.get("when-it-runs-out", "")).strip() == "ask-a-person":
        found.append((OUT_OF_BUDGET, _asked(limits, "limits", "when-it-runs-out")))

    # Every policy that covers this agent, not only the one it NAMES — see
    # `questions.policies_over`. A policy saying `applies-to: every-agent`
    # produced no pause rule at all for the agents that had not named it.
    for _, policy in policies_over(doc, agent):
        picked = False
        for rule in policy.get("ask-a-person") or []:
            if isinstance(rule, dict) and str(rule.get("question", "")).strip():
                # The first is the one whose deadline governs the wait. Which
                # question is *shown* depends on the rule that fired and is
                # decided where the gate is, not here.
                found.append((NEEDS_APPROVAL, str(rule["question"]).strip()))
                picked = True
                break
        if picked:
            break

    # `needs-a-person: yes` on an action this agent can reach (F17). AFTER the
    # policies, because only the first rule per reason survives the dedup at the
    # bottom and a written rule has to keep governing the wait — it is the one
    # that can say a different audience or a different deadline. An action a rule
    # already decides never reaches here at all; `gated_actions` drops it.
    if gated_actions(doc, agent_key):
        found.append((NEEDS_APPROVAL, SHIPPED_QUESTION))

    team = agent.get("teamwork") or {}
    if str(team.get("if-someone-fails", "")).strip() == "ask-a-person":
        found.append((NEEDS_APPROVAL, _asked(team, "teamwork", "if-someone-fails")))

    # Only a server this agent can actually reach — see
    # `connections_needing_permission` for why that is stricter than it was.
    for asks in connections_needing_permission(doc, agent_key).values():
        found.append((NEEDS_PERMISSION, asks))
        break

    tidying = (doc.get("context-policies") or {}).get(
        str(agent.get("context-policy", "")).strip()
    ) or {}
    if str(tidying.get("if-it-still-does-not-fit", "")).strip() == "ask-a-person":
        found.append(
            (CONTEXT_TOO_LONG, _asked(tidying, "context policy", "if-it-still-does-not-fit"))
        )

    # A stage of the authored loop that stops to ask (G1 meeting G7). It is read
    # through `Loop.resolve` rather than off the raw mapping so a stage
    # inherited by `based-on:` is found too — an author who forks a shipped
    # shape and adds nothing still gets whatever that shape asks.
    for stage_name, asks in _one_asking_stage(doc, agent):
        found.append((
            ASKED_A_PERSON,
            _asked({"asks": asks}, f"stage {stage_name!r}", "", saying="does: ask-someone"),
        ))

    # First rule per reason wins, so an agent that can stop for one reason in two
    # places does not end up with two deadlines for one wait.
    seen: set[str] = set()
    return [
        (reason, name)
        for reason, name in found
        if name and not (reason in seen or seen.add(reason))
    ]


def _one_asking_stage(doc: Mapping[str, Any], agent: Mapping[str, Any]) -> list[tuple[str, str]]:
    """The `ask-someone` stages of this agent's loop, refused if they disagree.

    Only one rule survives per reason to wait (see the dedup below), so a second
    stage naming a *different* question would silently borrow the first one's
    deadline, audience and answer shape. Refused rather than collapsed: that is
    the T7 degradation this module exists to prevent, not a smaller version of
    the feature.
    """
    stages = asking_stages(doc, agent)
    named = {asks for _, asks in stages if asks}
    if len(named) > 1:
        raise WrongAnswer(
            f"the loop this agent thinks in has more than one stage that asks a "
            f"person, and they name different questions: "
            f"{', '.join(sorted(named))}. Only one of them can govern the wait. "
            f"Fix: point every `ask-someone` stage at the same question, or "
            f"split them into two loops."
        )
    return stages


def _asked(block: Mapping[str, Any], where: str, chose: str, saying: str = "") -> str:
    """The question named next to an `ask-a-person`, or a refusal saying to add one.

    The schema cannot say "required when another field has this value" without
    growing a conditional language, so it is checked here — the same place and
    for the same reason `questions.Request.from_document` checks that a rule
    which escalates names somebody to escalate to. Left unchecked it would
    produce the worst possible outcome: a run parked with nothing to show, which
    from the outside is indistinguishable from a hang.
    """
    name = str(block.get("asks", "")).strip()
    if name:
        return name
    raise WrongAnswer(
        f"the {where} says `{saying or f'{chose}: ask-a-person'}`, but names no "
        f"question to put to them, so the run would stop with nothing to show. "
        f"Add a line next to it: `asks: <the name of a file in questions/>`."
    )


# ──────────────────────────────────────────────────────────────── the suspension


@dataclass
class Suspension:
    """A run stopped mid-flight, and everything needed to continue it in a
    *different process*.

    This is the shape decision D23 needs: an approval gate is only meaningful if
    the process can die while a human thinks. Holding the pause in memory would
    make "ask a person" a synchronous call with a very long timeout.

    One shape covers all four reasons. The three blocks below are why it stopped,
    what would let it continue, and where it had got to — and only the first two
    are anyone's business but the loop's.
    """

    # Why it stopped, and what would let it continue.
    reason: str
    asks: tuple[Expect, ...] = ()
    correlation_key: str = ""
    waits_for: float | None = None
    parked_at: float = 0.0
    if_nobody_answers: str = "stop-and-say-so"
    who_can_answer: tuple[str, ...] = ()
    #: What the person actually reads, already laid out in labelled regions with
    #: every value quoted (`Question.for_person`). Carried rather than rebuilt on
    #: the far side: the process may die while somebody thinks, and rebuilding
    #: could show them wording that no longer matches what was asked.
    in_words: str = ""

    # Where the run had got to. Opaque to whoever answers.
    awaiting: tuple["ToolCall", ...] = ()
    text: str = ""
    steps: list["Step"] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    step_index: int = 0
    completed: dict[str, str] = field(default_factory=dict)
    #: Which stage of the agent's loop it had reached, and how many times each
    #: stage has run. Carried because the loop is authored (G1): a run that
    #: parks in the `check` stage of a three-stage shape and resumes at the
    #: start has silently taken a different path through the author's document.
    #: An empty `phase` means the loop's first stage, which is exactly right for
    #: the one-stage shape everything gets by default.
    phase: str = ""
    visits: dict[str, int] = field(default_factory=dict)
    #: What the run had already spent — steps, tool calls, seconds worked,
    #: tokens, money. Carried so a run cannot be given a fresh budget by being
    #: interrupted: without it, parking for an approval would silently reset
    #: every ceiling the author set (G2). Empty for a record written by anything
    #: that does not meter, which resumes from the step index alone.
    used: dict[str, float] = field(default_factory=dict)
    #: What earlier waits in this run were already let past, by the name each was
    #: answered under.
    #:
    #: Carried because ONE call can stop twice for two different reasons —
    #: `payments` needs the connection consent in
    #: `resources/payments-server.yaml` and then the approval in
    #: `policies/approvals.yaml` — while a resume brings only the answer to the
    #: wait it is resuming. Without this the consent granted at the first park is
    #: absent at the second, so the run re-parks for a permission somebody has
    #: already given, and gives it again, for ever.
    #:
    #: Eve cannot reach this shape at all: its five park kinds are five
    #: subsystems and no call is ever in two of them, which is also why nothing
    #: there has to decide which one a person meets first.
    granted: dict[str, str] = field(default_factory=dict)
    #: Which `same-request-key:` values this run has already spent, as
    #: `(tool, action, value)` triples.
    #:
    #: Beside `used` and for exactly the reason its comment gives one line up: a
    #: run cannot get a fresh at-most-once record by being interrupted. Parking
    #: is what happens while a person decides whether a refund may go out, so
    #: "issued before the park, issuable again after it" is the one place the
    #: guarantee is worth most and the one place a per-process record would lose
    #: it. Empty for a record written before this field existed, which resumes
    #: with no keys spent — the same honest degradation `used` already has.
    spent_keys: tuple[tuple[str, str, str], ...] = ()

    def __post_init__(self) -> None:
        check_reason(self.reason)

    # -- answering ---------------------------------------------------------

    def answer(self, **values: str) -> Resumption:
        """Turn what a person said into a typed resumption, or refuse it.

        Refusing here rather than at resume time means the person who typed the
        answer gets the message, instead of the run failing later in front of
        somebody who cannot fix it.
        """
        asked = {e.name: e for e in self.asks}
        for name, value in values.items():
            expect = asked.get(name)
            if expect is None:
                raise WrongAnswer(
                    f"this wait did not ask for {name!r}. It asked for: "
                    + (", ".join(asked) or "nothing")
                    + "."
                )
            expect.check(value)
        for name, expect in asked.items():
            if expect.required and name not in values:
                choices = expect.shape.example()
                raise WrongAnswer(
                    f"the answer is missing {name!r}. Add `{name}: {choices}`."
                )
        return Resumption(self.correlation_key, dict(values))

    def accepts(self, resumption: Resumption) -> bool:
        """The one guard. An answer to a wait this run has moved past is not an
        answer to this wait, however plausible it looks."""
        return resumption.correlation_key == self.correlation_key

    # -- waiting -----------------------------------------------------------

    def expired(self, now: float) -> bool:
        """Has nobody answered in time? A wait with no `waits-for` never expires,
        which is Eve's only behaviour and here is a choice an author makes."""
        return self.waits_for is not None and now - self.parked_at > self.waits_for

    def escalate(self, now: float) -> "Suspension":
        """Re-park under a new key so the answer nobody gave cannot arrive late
        and be applied to the escalated wait."""
        fresh = correlation_key(
            self.reason, self.step_index, [*(c.name for c in self.awaiting), "escalated"]
        )
        return Suspension(
            reason=self.reason, asks=self.asks, correlation_key=fresh,
            waits_for=self.waits_for, parked_at=now,
            if_nobody_answers="stop-and-say-so", who_can_answer=self.who_can_answer,
            # The next person is shown the same words, not a summary of them.
            in_words=self.in_words,
            awaiting=self.awaiting, text=self.text, steps=list(self.steps),
            history=list(self.history), step_index=self.step_index,
            completed=dict(self.completed),
            phase=self.phase, visits=dict(self.visits), used=dict(self.used),
            # An escalation is the same wait put to somebody else, so what this
            # run had already been allowed is still allowed. Dropping it would
            # send the escalated run back to the first wait it had already
            # cleared.
            granted=dict(self.granted),
            # And the same argument one field over, which this line was missing.
            # `spent_keys` is what stops a run being handed a fresh at-most-once
            # record by being interrupted, and an escalation is an interruption
            # — the run is the same run, put to a second person. Without this,
            # a refund issued before the first approval expired could be issued
            # again after the second one, which is the exact guarantee
            # `same-request-key:` exists to make and the exact moment it is
            # worth most: money moving while a person decides.
            spent_keys=tuple(self.spent_keys),
        )

    # -- crossing a process boundary ---------------------------------------

    def to_json(self) -> str:
        """The durable form. Durability is the point of the primitive, so
        writing it down belongs to the primitive rather than to each caller."""
        return json.dumps(
            {
                "reason": self.reason,
                "asks": [
                    # The shape, not the words it happens to allow. A run that
                    # comes back in another process has to ask for the same
                    # typed thing it asked for before it died.
                    {"name": e.name, "shape": e.shape.written(),
                     "required": e.required, "means": e.means}
                    for e in self.asks
                ],
                "correlation-key": self.correlation_key,
                "waits-for": self.waits_for,
                "parked-at": self.parked_at,
                "if-nobody-answers": self.if_nobody_answers,
                "who-can-answer": list(self.who_can_answer),
                "in-words": self.in_words,
                "awaiting": [{"name": c.name, "args": c.args} for c in self.awaiting],
                "text": self.text,
                "steps": [
                    {
                        "index": s.index,
                        "text": s.text,
                        "tools": [{"name": c.name, "args": c.args} for c in s.tool_calls],
                        "results": list(s.tool_results),
                    }
                    for s in self.steps
                ],
                "history": self.history,
                "step-index": self.step_index,
                "completed": self.completed,
                "phase": self.phase,
                "visits": self.visits,
                "used": self.used,
                "granted": self.granted,
                # A list of lists, because that is what JSON has. Read back as
                # tuples below, so the record's shape on this side of the
                # process boundary is the same one it had on the other.
                "spent-keys": [list(k) for k in self.spent_keys],
            },
            sort_keys=True,
        )

    @staticmethod
    def from_json(text: str) -> "Suspension":
        # Imported here rather than at the top: the record types belong to the
        # loop, and the loop imports this module. Same pattern as `Chain.at`.
        from .harness import Step, ToolCall

        d = json.loads(text)
        return Suspension(
            reason=str(d["reason"]),
            asks=tuple(
                Expect(a["name"], Shape.parse(a.get("shape") or "text"),
                       bool(a.get("required", True)),
                       str(a.get("means", "")))
                for a in d.get("asks") or []
            ),
            correlation_key=str(d.get("correlation-key", "")),
            waits_for=d.get("waits-for"),
            parked_at=float(d.get("parked-at") or 0.0),
            if_nobody_answers=str(d.get("if-nobody-answers") or "stop-and-say-so"),
            who_can_answer=tuple(d.get("who-can-answer") or ()),
            in_words=str(d.get("in-words") or ""),
            awaiting=tuple(ToolCall(c["name"], c["args"]) for c in d.get("awaiting") or []),
            text=str(d.get("text", "")),
            steps=[
                Step(
                    index=s["index"],
                    text=s["text"],
                    tool_calls=tuple(ToolCall(c["name"], c["args"]) for c in s.get("tools") or []),
                    tool_results=tuple(s.get("results") or ()),
                )
                for s in d.get("steps") or []
            ],
            history=list(d.get("history") or []),
            step_index=int(d.get("step-index") or 0),
            completed=dict(d.get("completed") or {}),
            phase=str(d.get("phase") or ""),
            visits={str(k): int(v) for k, v in (d.get("visits") or {}).items()},
            used={str(k): float(v) for k, v in (d.get("used") or {}).items()},
            granted={str(k): str(v) for k, v in (d.get("granted") or {}).items()},
            spent_keys=tuple(
                (str(t), str(a), str(v)) for t, a, v in (d.get("spent-keys") or ())
            ),
        )


def suspend(
    reason: str,
    asks: Sequence[Expect] = (),
    *,
    at: int = 0,
    about: Sequence[str] = (),
    now: float = 0.0,
    rule: PauseRule | None = None,
) -> Suspension:
    """Park a run. The whole primitive, in one call.

    `rule` is the author's YAML — how long to wait, what to do if nobody comes,
    what to ask for. Passing none means the built-in behaviour: ask for what the
    caller says, wait forever, and never proceed on your own.
    """
    check_reason(reason)
    contract = tuple(rule.asks_for) if rule and rule.asks_for else tuple(asks)
    return Suspension(
        reason=reason,
        asks=contract,
        correlation_key=correlation_key(reason, at, list(about)),
        waits_for=rule.waits_for if rule else None,
        parked_at=now,
        if_nobody_answers=rule.if_nobody_answers if rule else "stop-and-say-so",
        who_can_answer=tuple(rule.who_can_answer) if rule else (),
    )


# ────────────────────────────────────────────────────────────────────── helpers




def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        return [str(x) for x in v if isinstance(x, str)]
    return []
