"""A run that stopped must not arrive shaped like a run that finished.

`PactAgent` is the Pydantic AI face of PACT's own loop (D12 / FR-4.1.1): PACT
drives, `PydanticAITransport` carries one model call, and the caller gets back
the SDK's own `AgentRunResult`. That crossing has one place where it can quietly
lie, and this file is about that place.

**The measurement.** `harness.RunResult.output` is typed `str` and every halt
path writes an English SENTENCE into it. Run against the worked example
(`examples/refund-desk`), which declares

    answers-with:
      decision: one of approved, declined
      reason: text
      amount: money

the three halts produce:

| how it ended     | `RunResult.halted` | `RunResult.output`                                        |
|------------------|--------------------|-----------------------------------------------------------|
| ran out of steps | `step-limit`       | `Stopped before finishing: this run reached the limit …`  |
| a rule stopped it| `stopped-by-rule`  | `A person has to send this.`                              |
| a stage gave up  | `stage-limit`      | `{"decision": "approved", "reason": …, "amount": …}`      |

The third row is the one that matters most and is the reason this file exists.
`stage-limit` copies `result.steps[-1].text` into `output`, so a run that gave up
part-way through the author's `loop:` hands back something that PARSES AS THE
DECLARED SHAPE. It is the worst outcome available and the one that looks most
like success — a caller that reads `.output` and validates it against
`answers-with:` sees a well-formed approved refund for 40 USD from a run that
never reached its `reply` stage.

Rows one and two fail the other way and are no better. `_output_type_for(spec)`
turns `answers-with:` into a `PromptedOutput(StructuredDict(...))`, so an
`AgentRunResult` built by copying `RunResult.output` straight across carries a
`str` where its own `output_type` promises a mapping. Every downstream consumer
— a validator, a `pydantic_evals` case, a second agent taking this one's answer
as input, a type checker — is then reasoning about a contract the value does not
keep.

**So a halt is a TYPE here, not a string to be read.** `PactAgent` returns a
`Halted` on `.output`, the way this SDK already returns `DeferredToolRequests`
for the other thing that is not an answer, and it carries what the harness
knew: which halt it was (`halted`), which ceiling ended it (`stopped_by`), and
the words the run wrote (`words`). Nothing is discarded — but nothing that is
not an answer is handed back where an answer is declared.

What this file pins, in order: the halt is a distinct type; the crossing loses
nothing the harness said; the ceiling the author wrote is readable off it; a run
that really answered still comes back in the declared shape; the agent's own
`output_type` admits both; and the `RunResult` → `AgentRunResult` adaptation
carries the conversation and the spend rather than defaulting them away.
"""

from __future__ import annotations

import asyncio
import dataclasses
import importlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Mapping

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters import harness  # noqa: E402
from pact_adapters.harness import RunResult, ToolCall  # noqa: E402
from pact_adapters.interceptors import Chain, Interceptor  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.limits import Action  # noqa: E402
from pact_adapters.loops import STANDARD, Loop  # noqa: E402
from pact_adapters.pydantic_ai_interop import _output_type_for  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.suspension import (  # noqa: E402
    ASKED_A_PERSON,
    CONTEXT_TOO_LONG,
    OUT_OF_BUDGET,
)
from pact_adapters.transports.pydantic_ai_transport import (  # noqa: E402
    PydanticAITransport,
)

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"

pydantic_ai = pytest.importorskip("pydantic_ai")


# ─────────────────────────────────────────────────────── the agent under test


@pytest.fixture(scope="module")
def pact_agent() -> Any:
    """`PactAgent`, imported HERE and not at the top of this file.

    A module-level import of something that does not exist yet is a COLLECTION
    error: pytest prints one line for the whole file and no test names, so
    "which of these does the missing piece break" cannot be answered and the
    list of failures stops being the specification. Imported per test, every
    assertion below fails on its own and says what it wanted.
    """
    return importlib.import_module("pact_adapters.pact_agent").PactAgent


@pytest.fixture(scope="module")
def halted_type() -> Any:
    """The type a halt arrives as. Same reason it is imported here as above."""
    return importlib.import_module("pact_adapters.pact_agent").Halted


@pytest.fixture(scope="module")
def suspended_type() -> Any:
    """The exception a park with nothing pending leaves by.

    A park is not a halt and must not arrive as one: the run continues the
    moment somebody answers, so the value of an `AgentRunResult` here is a
    value a caller can log and forget — and forgetting it leaves the person
    never asked and the spend already made thrown away.
    """
    return importlib.import_module("pact_adapters.pact_agent").PactSuspended


@pytest.fixture(scope="module")
def document() -> dict:
    """The worked example, loaded the only way an adapter may load one (P-1)."""
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(PACT_BIN), "show", str(EXAMPLE)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


@pytest.fixture(scope="module")
def spec(document: dict) -> AgentSpec:
    """`examples/refund-desk`, chosen because it DECLARES `answers-with:`.

    An agent with no declared shape has no bug here at all — its `output_type`
    is `str` and a sentence in `.output` keeps the contract. The whole defect
    lives in the gap between a declared mapping and a written sentence, so the
    test has to be run against an agent that declares one, and this is the one
    the distribution ships.

    Built with no workspace root on purpose. `watch/tool-calls.yaml` writes its
    record into the workspace when it has one, and a test suite that appends to
    `examples/` is a test suite that edits the thing it is measuring.
    """
    return AgentSpec.from_document(document, "refund-desk")


ASKED = "refund order A-1, the jacket arrived torn"

#: What the model says when it is answering properly: the author's three fields,
#: as JSON, which is what `answers-with-mode:` unset (`prompted`) asks it for.
ANSWERED = json.dumps(
    {"decision": "approved", "reason": "the item arrived faulty", "amount": "40 USD"}
)


Halting = Callable[[AgentSpec], "tuple[AgentSpec, Script, dict[str, Any]]"]


def _ran_out_of_steps(spec: AgentSpec) -> "tuple[AgentSpec, Script, dict[str, Any]]":
    """The `_ran_out` STOP path: a model that never stops looking things up.

    `when-it-runs-out:` is forced to `stop-and-say-so` because the shipped file
    says `ask-a-person`, and an `ask-a-person` ceiling SUSPENDS — a different
    outcome with a different bug. This test is about the ceiling that ends the
    run, so it asks for the ending the schema calls the safe one.
    """
    return (
        replace(
            spec,
            max_steps=2,
            limits=replace(spec.limits, when_it_runs_out=Action.STOP, asks=""),
            loop=Loop.from_library(STANDARD),
        ),
        # `zendesk/read-ticket` and not `payments`: the author's
        # `policies/approvals.yaml` gates every `zendesk/reply` and any refund
        # over 200 USD, and a gated call parks the run instead of spending a
        # step. Reading a ticket is the one thing this agent may do unwatched.
        Script([
            Turn(
                "looking the ticket up",
                (ToolCall("zendesk", {"ticket-id": "T-1", "action": "read-ticket"}),),
            )
        ]),
        {"zendesk": lambda args: "delivered two days ago, reported torn"},
    )


def _a_rule_stopped_it(spec: AgentSpec) -> "tuple[AgentSpec, Script, dict[str, Any]]":
    """The `decision.stop` path: an interceptor that ends the run at the reply.

    One of the three sentences the format can carry out, written the way an
    author writes it, so the halt under test is the one a real `interceptors/`
    document produces rather than a `Decision` built by hand.
    """
    guard = Interceptor.from_document(
        "nothing-approved-goes-out-unread",
        {
            "description": "Stops an approval reaching the customer unread.",
            "when": "turn.message.after",
            "may": ["stop-the-run"],
            "rules": [
                'if the answer mentions "approved", stop and say "A person has to '
                'send this one. Nothing has been paid out."'
            ],
        },
    )
    chain = Chain()
    chain.add(guard)
    return (
        replace(spec, chain=chain, loop=Loop.from_library(STANDARD)),
        Script([Turn(ANSWERED)]),
        {},
    )


def _a_stage_used_up_its_turns(spec: AgentSpec) -> "tuple[AgentSpec, Script, dict[str, Any]]":
    """The `stage-limit` path, and the sharpest case in this file.

    One stage with `at-most: 1` whose `then:` leads only back to itself.
    `Loop.stage_to_run` detects the ring of spent stages and gives up, and the line
    it gives up on is `result.output = result.steps[-1].text` — so `output`
    becomes whatever the model last said. Measured on this exact loop: the run
    halted at `stage-limit` carrying `{"decision": "approved", "reason":
    "the item arrived faulty", "amount": "40 USD"}`, a value that validates
    cleanly against the author's `answers-with:` block and describes a refund
    the loop never finished deciding.
    """
    once = Loop.from_mapping(
        "one-look",
        {
            "description": "One look and no more.",
            "starts-at": "work",
            "steps": {
                "work": {
                    "does": "use-tools",
                    "at-most": 1,
                    "then": {"used-a-tool": "work", "answered": "work"},
                }
            },
        },
    )
    return replace(spec, loop=once), Script([Turn(ANSWERED)]), {}


#: The three halts, by the tag the harness reports for each.
HALTS: "list[tuple[str, Halting]]" = [
    ("step-limit", _ran_out_of_steps),
    ("stopped-by-rule", _a_rule_stopped_it),
    ("stage-limit", _a_stage_used_up_its_turns),
]


def _through_pact_agent(pact_agent: Any, spec: AgentSpec, halting: Halting) -> Any:
    """One halting run, through `PactAgent`."""
    halted, script, tools = halting(spec)
    agent = pact_agent.for_spec(
        halted,
        transport=PydanticAITransport(script),
        # `tool_impls` and not `tools`, because `harness.run` already calls this
        # map `tool_impls` and it is the same map. Two spellings for one thing is
        # the `same-setting-twice` mistake arriving in a signature.
        tool_impls=tools,
    )
    return agent.run_sync(ASKED)


def _through_the_harness(spec: AgentSpec, halting: Halting) -> RunResult:
    """The same run, through the harness alone — what `PactAgent` must not lose."""
    halted, script, tools = halting(spec)
    return asyncio.run(
        harness.run(halted, PydanticAITransport(script), ASKED, tool_impls=tools)
    )


# ────────────────────────────────────── a halt is a type, not a string to read


@pytest.mark.parametrize("tag,halting", HALTS, ids=[t for t, _ in HALTS])
def test_no_halt_path_hands_back_something_shaped_like_an_answer(
    pact_agent: Any, halted_type: Any, spec: AgentSpec, tag: str, halting: Halting
) -> None:
    """A run that stopped must not be readable as a run that decided.

    This agent's `answers-with:` says the answer is a mapping with a `decision`,
    a `reason` and an `amount`. If a halt arrives on `.output` as a `str`, every
    consumer downstream is holding a value its declared type says it cannot be;
    if it arrives as a mapping — which `stage-limit` produces, because it copies
    the model's last words and the model's last words parse — then a refund
    nobody finished deciding is indistinguishable from one that was decided.

    Both readings are the same failure: the caller cannot tell. A distinct type
    is what makes the question answerable without reading English prose, which
    is the only check a downstream consumer can actually perform.
    """
    result = _through_pact_agent(pact_agent, spec, halting)
    assert isinstance(result.output, halted_type), (
        f"a run that halted at {tag!r} came back as "
        f"{type(result.output).__name__}, which is what an answer looks like"
    )
    assert not isinstance(result.output, (str, bytes, Mapping)), (
        "a halt that is also a str or a mapping can still be read as the "
        "declared shape by anything that does not know to check the type first"
    )
    # And it cannot be edited into an answer in place. A mutable halt is one a
    # retry wrapper can rewrite to `final` on its way past, which puts the lie
    # back exactly where the type was meant to remove it.
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.output.halted = "final"


def test_a_halt_with_no_words_says_nothing_rather_than_inventing_some(
    halted_type: Any,
) -> None:
    """The two optional fields are optional because a halt may not have them.

    `words` is *the sentence the harness composed* and `stopped_by` is *the
    ceiling as a VALUE, if one ended it* — and a halt can have neither: a
    `stopped-by-rule` names no ceiling, and a path that wrote no sentence has no
    sentence. What a default must never do is fill the gap, because `words` is
    the field whose whole job is to be the only thing a person reads. A default
    of `"stopped"`, `"halted"` or the name of the reason is prose this run never
    wrote, arriving in the one slot a caller is entitled to quote verbatim — and
    it is indistinguishable from a sentence the harness DID compose, which is
    the same lie one level up that made `Halted` a type in the first place.

    Cheap to pin and cheap to break: the field is defaulted, so nothing in the
    module's own construction site would notice it changing.
    """
    bare = halted_type(halted="stopped-by-rule")
    assert bare.words == "", (
        f"a halt that composed no sentence came with one anyway: {bare.words!r}"
    )
    assert bare.stopped_by is None, (
        f"a halt that no ceiling ended names one anyway: {bare.stopped_by!r}"
    )
    assert bare.halted == "stopped-by-rule", "the reason is not defaulted at all"


@pytest.mark.parametrize("tag,halting", HALTS, ids=[t for t, _ in HALTS])
def test_everything_the_harness_said_about_the_halt_survives_the_crossing(
    pact_agent: Any, spec: AgentSpec, tag: str, halting: Halting
) -> None:
    """Typing the halt must not be a way of losing what the halt said.

    The obvious way to satisfy the test above is to hand back a marker that
    says only "this stopped", and that is worse than the sentence it replaced:
    the harness composed words a person can act on — which setting, both
    figures, what to type next (D13) — and a marker with none of them sends the
    reader nowhere. So the same run is driven twice, once through `PactAgent`
    and once through `harness.run` alone, and the three facts the harness knew
    have to be equal on both sides.
    """
    mine = _through_pact_agent(pact_agent, spec, halting)
    theirs = _through_the_harness(spec, halting)

    assert theirs.halted == tag, "the scenario no longer produces the halt it names"
    assert mine.output.halted == theirs.halted
    assert mine.output.words == theirs.output, (
        "the words the harness wrote are the only thing a person can read; "
        "dropping them to make room for a type is trading one lie for a silence"
    )
    assert mine.output.stopped_by == theirs.stopped_by


def test_the_ceiling_the_author_wrote_is_readable_off_the_halt(
    pact_agent: Any, spec: AgentSpec
) -> None:
    """Which ceiling ended it has to be a value, not a sentence to be parsed.

    `RunResult.stopped_by` carries the setting the author typed, the number they
    wrote and the number reached — and it is the field that makes
    `answer-with-what-it-has` safe to offer at all, because it is how "ran out
    and answered anyway" is told from "finished". A caller deciding whether to
    raise a ceiling, retry, or escalate needs those figures; recovering them by
    regex from `Stopped before finishing: … (2 of 2 steps).` is not a caller
    reading a contract, it is a caller reading prose in a language that can
    change.
    """
    result = _through_pact_agent(pact_agent, spec, _ran_out_of_steps)
    reached = result.output.stopped_by
    assert reached is not None, "the run stopped at a ceiling and did not say which"
    assert reached.ceiling.field == "steps-at-most"
    assert reached.ceiling.limit == 2.0
    assert reached.at == 2.0
    # The author's own `when-it-runs-out:`, because the three actions are not
    # three severities of one thing — `stop-and-say-so` leaves work unfinished,
    # `answer-with-what-it-has` trades completeness for an answer, and a caller
    # that cannot tell them apart cannot tell whether the words it received were
    # meant to be used.
    assert reached.action is Action.STOP


# ───────────────────────────────────────────── and the other half still works


def test_a_run_that_really_answered_comes_back_in_the_shape_the_author_declared(
    pact_agent: Any, halted_type: Any, spec: AgentSpec
) -> None:
    """Every test above passes on an agent that always returns a halt.

    So this is the half that stops the fix from being a way of never answering.
    The author wrote three fields under `answers-with:` and `_output_type_for`
    turns them into a `StructuredDict`; a run that reached `done` has to produce
    that mapping, with those keys, and not the JSON text the model emitted —
    because a caller handed a string still has to parse it, and where it parses
    it and how it reports a failure is exactly the divergence between two
    runtimes that PACT exists to remove.
    """
    answering = replace(spec, loop=Loop.from_library(STANDARD))
    agent = pact_agent.for_spec(
        answering, transport=PydanticAITransport(Script([Turn(ANSWERED)])), tool_impls={}
    )
    result = agent.run_sync(ASKED)

    assert not isinstance(result.output, halted_type), "a finished run reported a halt"
    assert isinstance(result.output, Mapping), (
        f"the author declared a mapping and got {type(result.output).__name__}"
    )
    assert dict(result.output) == {
        "decision": "approved",
        "reason": "the item arrived faulty",
        "amount": "40 USD",
    }


def test_a_finished_run_and_a_halted_one_are_told_apart_without_reading_the_prose(
    pact_agent: Any, spec: AgentSpec
) -> None:
    """The two outcomes of `stage-limit` are byte-identical in `.output` today.

    Measured: the same script, the same spec and the same words produce
    `halted='final'` under `pact:loop/standard` and `halted='stage-limit'` under
    a loop whose only stage has used up its `at-most:` — and `RunResult.output`
    is the same JSON both times. A consumer holding only `.output` cannot
    distinguish a decided refund from an abandoned one, which is the single
    concrete way this defect issues money it should not.
    """
    finished = _through_pact_agent(
        pact_agent, replace(spec, loop=Loop.from_library(STANDARD)), lambda s: (s, Script([Turn(ANSWERED)]), {})
    )
    gave_up = _through_pact_agent(pact_agent, spec, _a_stage_used_up_its_turns)

    assert _through_the_harness(spec, _a_stage_used_up_its_turns).output == ANSWERED, (
        "the scenario no longer reproduces the identical-words case"
    )
    assert type(finished.output) is not type(gave_up.output), (
        "a run that finished and a run that gave up mid-loop arrived as the "
        "same type carrying the same words"
    )


def test_what_the_agent_says_it_returns_admits_both_an_answer_and_a_halt(
    pact_agent: Any, halted_type: Any, spec: AgentSpec
) -> None:
    """An `output_type` that names only the answer lies in the other direction.

    `AbstractAgent.output_type` is what every SDK consumer reads to know what a
    run can hand back — a validator, `output_json_schema()`, a type checker.
    Declaring `PromptedOutput(StructuredDict(...))` alone while `run()` can
    return a `Halted` is the same defect as putting a `str` in a mapping-shaped
    slot, pointing the other way: the value is now honest and the declaration is
    not.

    This SDK already has the shape for it. `DeferredToolRequests` is the other
    thing a run can hand back that is not an answer, and it is declared by being
    a member of the output union — `output_type=[str, DeferredToolRequests]`.
    A halt is that, so it is spelled that way.
    """
    agent = pact_agent.for_spec(
        spec, transport=PydanticAITransport(Script([Turn(ANSWERED)])), tool_impls={}
    )
    declared = agent.output_type
    members = list(declared) if isinstance(declared, (list, tuple)) else [declared]

    assert halted_type in members, (
        "this agent can return a Halted and its own output_type does not say so"
    )
    answers = [m for m in members if m is not halted_type]
    assert answers, "the declared output type says a halt is all this agent returns"
    # The author's shape, put to the model the way the author asked — the same
    # object `build_agent()` uses, so the two Pydantic AI doors cannot come to
    # disagree about what one document declares.
    assert type(answers[0]).__name__ == type(_output_type_for(spec)).__name__

    from pydantic import TypeAdapter

    schema = TypeAdapter(answers[0].outputs).json_schema()
    assert sorted(schema["properties"]) == ["amount", "decision", "reason"]


# ───────────────────────────── the rest of the adaptation, which is not output


@pytest.mark.parametrize("tag,halting", HALTS, ids=[t for t, _ in HALTS])
def test_a_halt_still_arrives_in_the_sdks_own_result_type(
    pact_agent: Any, spec: AgentSpec, tag: str, halting: Halting
) -> None:
    """A bespoke return shape would put the halt outside every tool that reads it.

    The point of `PactAgent` is that PACT's loop is usable from code written
    against Pydantic AI (D12): `.output`, `.all_messages()`, `.usage`,
    `AgentRunResultEvent`, `pydantic_evals`. A halt is the run outcome most
    likely to be handled by generic code — a retry wrapper, a run recorder — so
    it is the one that must not be the case where the SDK's own type stops
    arriving.
    """
    from pydantic_ai import AgentRunResult

    result = _through_pact_agent(pact_agent, spec, halting)
    assert isinstance(result, AgentRunResult)


def test_the_conversation_the_run_had_is_readable_off_the_result(
    pact_agent: Any, spec: AgentSpec
) -> None:
    """`AgentRunResult(output=…)` alone reports a run that never said anything.

    Its `_state` defaults to an empty `GraphAgentState`, so `all_messages()` is
    `[]` and `new_messages()` is `[]` — and a caller who follows this SDK's own
    documented way of continuing a conversation, `message_history=
    result.all_messages()`, hands the next turn nothing. The agent forgets the
    ticket, the customer is asked for the order number again, and nothing
    anywhere reports an error.

    So the steps PACT recorded have to reach the messages: the question the run
    was actually asked — `RunResult.asked`, which is the question AFTER the
    author's redaction rules ran, never the string the caller typed — and every
    step's words.
    """
    agent = pact_agent.for_spec(
        replace(spec, loop=Loop.from_library(STANDARD)),
        transport=PydanticAITransport(Script([Turn(ANSWERED)])),
        tool_impls={},
    )
    result = agent.run_sync(ASKED)

    messages = result.all_messages()
    assert messages, "the run happened and the result says nothing was said"
    # Read off the PARTS and not off `all_messages_json()`: the answer is itself
    # JSON, so its quotes come back escaped and a substring test against the
    # serialised history passes or fails on the encoder rather than on whether
    # the words are there.
    said = [
        part.content
        for message in messages
        for part in message.parts
        if isinstance(getattr(part, "content", None), str)
    ]
    assert ASKED in said, "the question the run was asked is not in its own history"
    assert ANSWERED in said, "the words the run answered with are not in its own history"
    assert result.new_messages(), "nothing on this result is new, on a run with no history"


# ─────────────────────────────── a park is not a halt, and leaves another way


#: What the ticket tool says back. One string, because two tests below read it
#: out of the conversation the result carries and a second copy would let them
#: pass against a history nobody wrote.
LOOKED_UP = "delivered two days ago, reported torn"

#: The three parks with NO call pending, named from `suspension` — the module
#: that decides them — and deliberately NOT imported from `pact_agent`, which is
#: the thing under test. A test that reads its expectation out of the object it
#: is measuring agrees with that object by construction: emptying the list there
#: would empty this one too, and every assertion below would go on passing while
#: no park left by any door at all.
_PARKS_A_CALLER_CANNOT_ANSWER = (ASKED_A_PERSON, OUT_OF_BUDGET, CONTEXT_TOO_LONG)

#: An answer big enough to be gated. `policies/approvals.yaml` sends any
#: `payments/issue-refund` over 200 USD to a person, and the connection to the
#: payments server has to be consented to before that — either way the run
#: parks WITH a call in hand, which is the half `DeferredToolRequests` is for.
OVER_THE_LINE = json.dumps(
    {"decision": "approved", "reason": "the item arrived faulty", "amount": "300 USD"}
)


def _looking_it_up() -> Turn:
    return Turn(
        "looking the ticket up",
        (ToolCall("zendesk", {"ticket-id": "T-1", "action": "read-ticket"}),),
    )


def _ran_out_the_way_the_document_says(
    spec: AgentSpec, ran: "list[str]"
) -> "tuple[AgentSpec, Script, dict[str, Any]]":
    """The ceiling `limits.yaml` really writes, which is `ask-a-person`.

    `_ran_out_of_steps` above forces `stop-and-say-so` because it is about the
    ceiling that ENDS a run. This one leaves the shipped line alone, so the same
    ceiling parks instead — the run is waiting for whoever owns the budget, and
    everything below is about what a caller is handed while it waits.
    """
    return (
        replace(spec, max_steps=2, loop=Loop.from_library(STANDARD)),
        Script([_looking_it_up(), _looking_it_up(), Turn(ANSWERED)]),
        {"zendesk": lambda args: (ran.append("zendesk"), LOOKED_UP)[1]},
    )


def _a_gated_batch(
    spec: AgentSpec, ran: "list[str]"
) -> "tuple[AgentSpec, Script, dict[str, Any]]":
    """One turn calling three things, one of which the author's gate stops.

    Written as one turn on purpose, because the two facts `_pending` exists for
    are only visible in a batch. `zendesk` is cleared and RUNS before the park
    — *a person who approves two of three actions gets those two* — so listing
    it as something to approve asks somebody to authorise a lookup that already
    happened; and the two `payments` calls share a name, so the slot each is
    filed under is the only thing that tells the 300 USD refund from the 400 USD
    one beside it.
    """
    return (
        replace(spec, loop=Loop.from_library(STANDARD)),
        Script([
            Turn(
                "paying both of these out",
                (
                    ToolCall("zendesk", {"ticket-id": "T-1", "action": "read-ticket"}),
                    ToolCall("payments", {"amount": "300 USD", "action": "issue-refund"}),
                    ToolCall("payments", {"amount": "400 USD", "action": "issue-refund"}),
                ),
            ),
            Turn(OVER_THE_LINE),
        ]),
        {
            "zendesk": lambda args: (ran.append("zendesk"), LOOKED_UP)[1],
            "payments": lambda args: (
                ran.append(f"payments {args.get('amount')}"),
                "refund issued",
            )[1],
        },
    )


def _built(pact_agent: Any, made: "tuple[AgentSpec, Script, dict[str, Any]]") -> Any:
    """A FRESH agent over the same document, as a second process would build one."""
    said, script, tools = made
    return pact_agent.for_spec(
        said, transport=PydanticAITransport(script), tool_impls=tools
    )


def test_a_park_with_nothing_pending_leaves_by_the_door_a_caller_cannot_ignore(
    pact_agent: Any, suspended_type: Any, halted_type: Any, spec: AgentSpec
) -> None:
    """A returned park is a park a caller can drop on the floor.

    Measured on this example, whose `limits.yaml` says `when-it-runs-out:
    ask-a-person`: the run reaches the ceiling, parks under `out-of-budget` with
    nothing pending, and this door RETURNED it. A caller who did not know to
    type-check `.output` read the run's own mid-run words as the desk's
    decision; one who did was told by a `Halted` that the run had STOPPED. It
    had not — it is waiting, and on both readings the person who can end the
    wait is never shown the question, while the spend already made is thrown
    away. An exception is the one outcome a caller cannot fail to notice.

    Everything the run knew rides on it, because raising must not be a way of
    losing the run: `parked` is `RunResult.suspension` ITSELF (never a copy, so
    the two cannot come to disagree about what the run is waiting for) and
    `result` is the `AgentRunResult` this door would otherwise have returned.
    """
    ran: list[str] = []
    with pytest.raises(suspended_type) as waiting:
        _built(pact_agent, _ran_out_the_way_the_document_says(spec, ran)).run_sync(ASKED)

    parked = waiting.value.parked
    assert spec.limits.when_it_runs_out is Action.ASK, (
        "the shipped ceiling stopped asking a person, so this scenario parks for "
        "a reason the document no longer gives"
    )
    assert parked.reason == OUT_OF_BUDGET
    assert parked.reason in _PARKS_A_CALLER_CANNOT_ANSWER
    assert parked.awaiting == (), (
        "this park has no call pending, which is why it has no "
        "DeferredToolRequests to hand anybody"
    )
    assert waiting.value.result.pact.suspension is parked, (
        "the park on the exception and the park on the run are one record or "
        "they are two that can disagree"
    )
    assert waiting.value.result.pact.halted == "suspended"
    assert ran == ["zendesk", "zendesk"], (
        f"the run did the work and the caller is being told nothing about it: {ran}"
    )


def test_the_words_a_parked_run_carries_are_the_ones_the_harness_composed(
    pact_agent: Any, suspended_type: Any, halted_type: Any, spec: AgentSpec
) -> None:
    """At a park `RunResult.output` is the model's mid-run chatter, not the reason.

    No park path writes a sentence into `output`: `harness._ran_out` returns
    inside the `ask-a-person` branch, BEFORE the `result.output =
    reached.sentence()` its other two actions reach. So a facade that copies
    `RunResult.output` across hands the caller "looking the ticket up" as the
    reason the run stopped, while the sentence naming the ceiling, both figures
    and who to ask sits unread on `Suspension.in_words` — the field the harness
    composes and carries ACROSS the process boundary precisely so the words a
    person reads cannot be rebuilt into something else later (D23).
    """
    ran: list[str] = []
    made = _ran_out_the_way_the_document_says(spec, ran)
    with pytest.raises(suspended_type) as waiting:
        _built(pact_agent, made).run_sync(ASKED)

    parked, result = waiting.value.parked, waiting.value.result
    theirs = asyncio.run(
        harness.run(made[0], PydanticAITransport(made[1]), ASKED, tool_impls=made[2])
    )
    assert theirs.suspension is not None and theirs.output != theirs.suspension.in_words, (
        "the harness stopped leaving the model's own words on `output` at a park, "
        "so this test no longer distinguishes the two"
    )
    assert isinstance(result.output, halted_type)
    assert result.output.halted == "suspended"
    assert result.output.words == parked.in_words, (
        "the caller was handed the model's mid-run chatter as the reason the run "
        "stopped"
    )
    assert result.output.stopped_by == theirs.stopped_by

    said = str(waiting.value)
    assert parked.reason in said, "name what the run is waiting for"
    assert parked.in_words and parked.in_words in said, (
        "the question a person has to be shown is the whole point of the park"
    )
    assert parked.who_can_answer, "this ceiling names who may answer it"
    assert f"in_words` to {', '.join(parked.who_can_answer)}" in said, (
        "the caller is told to show the question to somebody unnamed, on a park "
        "whose own record names exactly who can end it"
    )
    assert "resume=" in said and "answer=" in said, (
        "a refusal with no way back in is the dead end the exception exists to "
        "prevent"
    )


def test_a_park_that_composed_no_question_does_not_say_it_is_asking_nothing(
    pact_agent: Any, suspended_type: Any
) -> None:
    """The sentence is built out of the record, and a record can be bare.

    Every park the shipped document produces carries `in_words`, so the branch
    that leaves it out is the one no run in this file reaches — and a caller who
    meets it reads *It is asking:* followed by two blank lines and then the fix.
    An exception whose text is assembled unconditionally is how a message comes
    to describe something that is not there, which is the same defect as a halt
    shaped like an answer, one type down.
    """
    from pact_adapters.suspension import Suspension

    said = str(suspended_type(Suspension(reason=OUT_OF_BUDGET), None))
    assert "It is asking" not in said, (
        "a park with no question composed said it was asking one"
    )
    assert OUT_OF_BUDGET in said and "resume=" in said, (
        "and it still has to say what the run is waiting for and how to go on"
    )


def test_a_park_with_a_call_pending_is_this_sdks_own_word_for_one(
    pact_agent: Any, spec: AgentSpec
) -> None:
    """An approval is a call waiting, and this SDK already has a shape for it.

    `DeferredToolRequests(approvals=[ToolCallPart(…)])` is what every consumer
    of this SDK already knows how to route and how to answer, so a park WITH a
    call keeps returning one rather than raising: its resume path leads back
    into a run rather than away from one.

    Three things about the list are the harness's and not this crossing's, and
    each is a way an approval UI shows a decision that cannot be made:

    * the call the gate CLEARED already ran, so it is not on the list;
    * a step's first call to a tool keeps the bare tool name and only the second
      gets `<name>#1`, which is the key an answer is filed and read under —
      numbering from one gives the FIRST call the harness's name for the SECOND,
      and the approval of one refund arrives as the answer to the other;
    * the correlation key is the run's, so a stale answer cannot land.
    """
    ran: list[str] = []
    result = _built(pact_agent, _a_gated_batch(spec, ran)).run_sync(ASKED)

    from pydantic_ai import DeferredToolRequests

    assert isinstance(result.output, DeferredToolRequests), (
        f"a park with a call pending came back as {type(result.output).__name__}"
    )
    parked = result.pact.suspension
    assert parked is not None and parked.reason not in _PARKS_A_CALLER_CANNOT_ANSWER
    assert ran == ["zendesk"], (
        f"the gate either did not stop the payment or did not let the lookup "
        f"through: {ran}"
    )
    assert [call.tool_name for call in result.output.approvals] == ["payments", "payments"]
    assert [call.tool_call_id for call in result.output.approvals] == [
        "payments",
        "payments#1",
    ], "these are the slots `harness.py:1461-1465` files an answer under"
    assert [call.args["amount"] for call in result.output.approvals] == [
        "300 USD",
        "400 USD",
    ], "the approvals were transposed, so a person approves the wrong figure"
    assert "zendesk" not in {c.tool_name for c in result.output.approvals}, (
        "the lookup already happened; asking somebody to approve it is a "
        "decision that cannot be made"
    )
    assert result.output.metadata == {
        "payments": {"correlation-key": parked.correlation_key, "reason": parked.reason},
        "payments#1": {
            "correlation-key": parked.correlation_key,
            "reason": parked.reason,
        },
    }
    assert parked.correlation_key, "a park with no key is a park a stale answer can land on"


def _yes(parked: Any) -> Any:
    """Whatever this wait asked for, answered in its own vocabulary."""
    said: dict[str, str] = {}
    for expect in parked.asks:
        if expect.choices:
            said[expect.name] = next(
                (w for w in ("approve", "yes", "granted", "carry-on") if w in expect.choices),
                expect.choices[0],
            )
        elif expect.shape.written() == "yes-or-no":
            said[expect.name] = "yes"
        else:
            said[expect.name] = "the item is faulty"
    return parked.answer(**said)


@pytest.mark.parametrize("door", ["run_sync", "run"])
def test_a_parked_run_continues_as_the_same_run_through_either_door(
    pact_agent: Any, suspended_type: Any, spec: AgentSpec, door: str
) -> None:
    """Without `resume=` and `answer=` a park is a dead end, and quietly.

    `harness.run` takes both, and this class taking neither is not a missing
    convenience: `when-it-runs-out: ask-a-person` — the worked example's own
    line — collapses into `stop-and-say-so`, because the ceiling is reached, the
    question is carried, and nothing a caller can type puts the answer back.
    That is the author's choice discarded rather than degraded.

    `run_sync` is the door that has to be written by hand — `AbstractAgent
    .run_sync` is a CLOSED signature of this SDK's own arguments with nowhere to
    name a park — so a resume reachable only from async code is the same dead
    end for every synchronous caller, and both are driven here.

    What proves it is the SAME run and not a fresh one is the tool: the run had
    already spent its two steps looking the ticket up, and a resumed run that
    started over would look it up again. A fresh budget by way of being
    interrupted is the failure `Suspension` carries the meter to prevent (D23).
    """
    ran: list[str] = []
    made = _ran_out_the_way_the_document_says(spec, ran)
    with pytest.raises(suspended_type) as waiting:
        _built(pact_agent, made).run_sync(ASKED)
    parked = waiting.value.parked
    before, spent = list(ran), waiting.value.result.pact.used

    agent = _built(pact_agent, _ran_out_the_way_the_document_says(spec, ran))
    if door == "run_sync":
        back = agent.run_sync(resume=parked, answer=_yes(parked))
    else:
        back = asyncio.run(agent.run(resume=parked, answer=_yes(parked)))

    assert back.pact.halted == "final", (
        "the answer was handed back and the run did not continue — a resume that "
        "starts over parks again on the same ceiling"
    )
    assert ran == before, (
        f"the resumed run re-ran work the parked one had already done: {ran}"
    )
    assert dict(back.output) == json.loads(ANSWERED), (
        "a continued run answers in the shape the author declared"
    )
    assert spent is not None and back.pact.used is not None
    assert back.pact.used.tokens > spent.tokens, (
        f"the parked run had spent {spent.tokens} tokens and the resumed one "
        f"reports {back.pact.used.tokens} — a meter that starts again from zero "
        f"is a ceiling a run can get past by being interrupted, which is the one "
        f"thing `Suspension` carries the meter to prevent (D23)"
    )


def test_a_park_handed_back_with_no_answer_yet_is_still_the_same_run(
    pact_agent: Any, suspended_type: Any, spec: AgentSpec
) -> None:
    """A person who has not answered yet is not a reason to start over.

    `resume=` without `answer=` is what a host holds while the question is on
    somebody's screen: the record is in hand, nobody has said anything, and the
    run is exactly where it was. The sync door is where that goes wrong,
    because `AbstractAgent.run_sync` is a closed signature — hand the call to
    the inherited method and BOTH arguments are dropped on the floor, so the
    same prompt runs again from the top: the ticket is looked up twice more, the
    spend is made twice, and the caller is handed a park that looks just like
    the one they were already holding.
    """
    ran: list[str] = []
    made = _ran_out_the_way_the_document_says(spec, ran)
    with pytest.raises(suspended_type) as first:
        _built(pact_agent, made).run_sync(ASKED)
    before, spent = list(ran), first.value.result.pact.used

    with pytest.raises(suspended_type) as again:
        _built(pact_agent, _ran_out_the_way_the_document_says(spec, ran)).run_sync(
            resume=first.value.parked
        )

    assert ran == before, (
        f"waiting for an answer re-ran the work the parked run had already "
        f"done: {ran}"
    )
    assert spent is not None and again.value.result.pact.used is not None
    assert again.value.result.pact.used.tokens == spent.tokens, (
        "the run started again from zero while the question was still on "
        "somebody's screen"
    )


def test_a_run_id_and_a_conversation_id_the_caller_gave_reach_the_result(
    pact_agent: Any, spec: AgentSpec
) -> None:
    """Two of this SDK's own arguments that PACT can honour, and so must.

    They are how a caller ties this run to their own record of it — a trace, a
    ticket, a conversation held across several runs. `AgentRunResult` reads both
    off the private `_state`, so a facade that builds one without them hands
    back a result that belongs to no conversation and no run, and the caller
    finds out by grepping their own logs for an id that is not there.
    """
    agent = pact_agent.for_spec(
        replace(spec, loop=Loop.from_library(STANDARD)),
        transport=PydanticAITransport(Script([Turn(ANSWERED)])),
        tool_impls={},
    )
    result = asyncio.run(agent.run(ASKED, run_id="r-7", conversation_id="c-9"))

    assert (result._state.run_id, result._state.conversation_id) == ("r-7", "c-9")
    # And a run nobody gave one to keeps whatever this SDK mints for itself.
    # Writing the argument through unconditionally is the other way to get the
    # line above green, and it replaces the SDK's own id with `None` — a result
    # that belongs to no run at all, in the field a tracer reads.
    plain = agent.run_sync(ASKED)
    assert plain._state.run_id and plain._state.run_id != "r-7", (
        "a run given no id came back carrying somebody else's, or none at all"
    )
    assert plain._state.conversation_id and plain._state.conversation_id != "c-9", (
        "the conversation this run belongs to was erased by a caller who named none"
    )


@pytest.mark.parametrize(
    "wrote,comes_back",
    [
        ("just the words, no JSON at all", "just the words, no JSON at all"),
        ("[1, 2]", "[1, 2]"),
        ('{"decision": "approved"}', {"decision": "approved"}),
    ],
)
def test_an_answer_that_is_not_the_declared_shape_comes_back_as_what_the_run_wrote(
    pact_agent: Any, spec: AgentSpec, wrote: str, comes_back: Any
) -> None:
    """Read and not VALIDATED, deliberately — and a JSON list is not a mapping.

    `answers-with:` makes `_output_type_for` a `StructuredDict`, so a caller
    handed the JSON TEXT still has to parse it, and where they parse it and how
    they report a failure is exactly the divergence between two runtimes PACT
    exists to remove. But the shape is put to the model by the harness, and a
    SECOND check here would be the `same-setting-twice` mistake: two places
    deciding whether one answer keeps one contract. So text that is not the
    declared shape comes back as the text the run wrote — inventing a parse
    failure at the door turns a bad answer into no answer.

    The list is the case a bare `json.loads` gets wrong: it parses, so a
    crossing that only catches `ValueError` hands a caller expecting a mapping
    something with no keys at all, and the failure surfaces wherever they first
    subscript it.
    """
    agent = pact_agent.for_spec(
        replace(spec, loop=Loop.from_library(STANDARD)),
        transport=PydanticAITransport(Script([Turn(wrote)])),
        tool_impls={},
    )
    said = agent.run_sync(ASKED).output
    assert said == comes_back
    assert type(said) is type(comes_back)


def test_an_agent_that_declares_no_shape_is_handed_its_answer_as_the_text_it_wrote(
    pact_agent: Any, spec: AgentSpec
) -> None:
    """`answers-with-mode: text` is a `str`, and JSON typed by a model is text.

    `_output_type_for` returns the bare `str` type for `text` and for an agent
    with no declared shape at all, and reading JSON out of either would
    contradict the type this same object publishes as `output_type` — a caller
    who checked the declaration would be holding a mapping their type checker
    says is a string.
    """
    agent = pact_agent.for_spec(
        replace(spec, loop=Loop.from_library(STANDARD), answers_with_mode="text"),
        transport=PydanticAITransport(Script([Turn(ANSWERED)])),
        tool_impls={},
    )
    said = agent.run_sync(ASKED).output
    assert isinstance(said, str) and said == ANSWERED
    assert agent.output_type[0] is str, "the declaration and the value disagree"


def test_the_conversation_on_the_result_is_the_dialect_the_harness_writes(
    pact_agent: Any, spec: AgentSpec
) -> None:
    """`all_messages()` is where the next turn comes from, entry by entry.

    The PACT dialect is not an implementation detail: `context_policy
    .from_history` reads it, `Pins` matches on its `labels`, and
    `_repair_pairing` decides which messages are sendable by comparing the
    strings inside `tool_calls` against the `name` on each tool entry. So this
    asserts the WHOLE history rather than that two strings appear somewhere in
    it — a crossing that drops the tool result, renames the pairing key, or
    forgets the `first-request` label passes every substring test and leaves the
    author's `always-keep:` line matching nothing.

    `RunResult.asked` and never the string the caller typed: it is the question
    AFTER the author's interceptor chain ran on it, so a workspace with a
    redaction rule has already had it rewritten — and a card number reaching a
    committed eval case file is the measured reason that distinction exists.
    """
    from pact_adapters.pact_agent import to_pact_history

    ran: list[str] = []
    agent = _built(pact_agent, (
        replace(spec, loop=Loop.from_library(STANDARD)),
        Script([_looking_it_up(), Turn(ANSWERED)]),
        {"zendesk": lambda args: (ran.append("zendesk"), LOOKED_UP)[1]},
    ))
    result = agent.run_sync(ASKED)

    back, report = to_pact_history(result.all_messages())
    assert back == [
        {"role": "user", "content": result.pact.asked, "labels": ["first-request"]},
        {
            "role": "assistant",
            "content": "looking the ticket up",
            "tool_calls": ["zendesk"],
        },
        {"role": "tool", "name": "zendesk", "content": LOOKED_UP},
        {"role": "assistant", "content": ANSWERED},
    ]
    assert result.pact.asked == ASKED, "the example redacts nothing out of this question"
    assert report.silent_losses == (), (
        f"the run's own conversation lost something on the way out: "
        f"{report.silent_losses}"
    )


def test_what_the_run_spent_reaches_the_result(pact_agent: Any, spec: AgentSpec) -> None:
    """A usage of zero is a ceiling that never fires, on every caller downstream.

    `UsageLimits` and any accounting above this agent read `AgentRunResult
    .usage`, which comes off the private `_state` — left at its default it is a
    `RunUsage()` of zeros. A caller totalling spend across a chain of runs then
    measures nothing and stops nothing, which is precisely the T7 failure
    `RunResult.unmetered` exists to prevent one level down: an author who
    believes they capped their spend and did not.

    Compared against the same run through the harness rather than asserted as
    "more than zero", because a hard-coded number would go stale the first time
    the scripted transport counts differently and a `> 0` would pass on a
    figure that was right once and is now anybody's.
    """
    # A run that CALLS something, because `tool_calls` is a figure that is zero
    # on every run that only answers — and a zero compares equal to a meter
    # nobody read.
    answering = replace(spec, loop=Loop.from_library(STANDARD))
    tools = {"zendesk": lambda args: LOOKED_UP}
    agent = pact_agent.for_spec(
        answering,
        transport=PydanticAITransport(Script([_looking_it_up(), Turn(ANSWERED)])),
        tool_impls=tools,
    )
    mine = agent.run_sync(ASKED)
    theirs = asyncio.run(
        harness.run(
            answering,
            PydanticAITransport(Script([_looking_it_up(), Turn(ANSWERED)])),
            ASKED,
            tool_impls=tools,
        )
    )

    assert theirs.used is not None and theirs.used.tokens > 0, (
        "the scripted transport stopped counting tokens, so this proves nothing"
    )
    assert mine.usage.total_tokens == theirs.used.tokens
    # The other two figures on `RunUsage`, because `total_tokens` alone is one
    # third of what a caller totals across a chain of runs — and because a
    # `requests` of zero is what a `UsageLimits(request_limit=…)` above this
    # agent measures itself against.
    assert mine.usage.requests == len(theirs.steps) > 0, (
        "the number of times the model was asked is how a caller above this "
        "agent counts what a loop cost them"
    )
    assert theirs.used.tool_calls > 0, "the run called nothing, so the figure below is zero either way"
    assert mine.usage.tool_calls == theirs.used.tool_calls


# ─────────────────── the third park with nothing pending, which nothing above reaches


class _AModelWithAlmostNoRoom(PydanticAITransport):
    """The scripted transport bound to a model that can hold almost nothing.

    The window is the runtime's answer and not the document's — `AgentSpec
    .tidier` takes it from `transport.context_window()` — so this is the one
    thing a test of the conversation ceiling has to supply, and supplying it
    here leaves the policy, its ladder and what it does when the ladder runs out
    entirely in the author's file.
    """

    def context_window(self) -> int:
        return 16


def _the_conversation_no_longer_fits(
    spec: AgentSpec,
) -> "tuple[AgentSpec, Script, dict[str, Any]]":
    """`if-it-still-does-not-fit: ask-a-person`, with a ladder that cannot help.

    An empty `then:` on purpose. The rungs are not what is under test — the park
    at the bottom of them is — and a ladder with rungs makes the scenario depend
    on how much four shortening steps happen to save against a window somebody
    may later change.
    """
    from pact_adapters.context_policy import ContextPolicy

    return (
        replace(
            spec,
            loop=Loop.from_library(STANDARD),
            context_policy=ContextPolicy.from_document(
                {
                    "context-policies": {
                        "no-room-at-all": {
                            "description": "Ask when it no longer fits.",
                            "when-full": "50%",
                            "if-it-still-does-not-fit": "ask-a-person",
                            "then": [],
                        }
                    }
                },
                "no-room-at-all",
            ),
        ),
        Script([Turn(ANSWERED)]),
        {},
    )


def test_a_conversation_that_no_longer_fits_leaves_by_the_same_door_a_ceiling_does(
    pact_agent: Any, suspended_type: Any, spec: AgentSpec
) -> None:
    """Three reasons park with nothing pending, and two of them are tested above.

    `context-too-long` is the third, and it is the one no other test in this
    file reaches: it is not a ceiling and not a `does: ask-someone` stage, it is
    the author's context policy running out of ladder. It parks the same way and
    for the same reason — `awaiting` is empty, so there is no
    `DeferredToolRequests` to hand anybody and nothing this SDK's own park shape
    can carry.

    So a list of park reasons that names only the two obvious ones sends this
    one back as a RETURNED value: a caller reads `.output`, finds a `Halted`
    saying the run stopped, and never shows anybody the question — while the
    run is waiting to be told whether to carry on with less of the conversation,
    and the work already paid for is thrown away when they log it and move on.
    The harness is driven first, so a scenario that stops producing this park
    fails as a stale fixture rather than passing as a green test.
    """
    made = _the_conversation_no_longer_fits(spec)
    said, script, tools = made
    theirs = asyncio.run(
        harness.run(said, _AModelWithAlmostNoRoom(Script([Turn(ANSWERED)])), ASKED,
                    tool_impls=tools)
    )
    assert theirs.halted == "suspended", (
        f"this conversation no longer parks, so the fixture proves nothing: "
        f"{theirs.halted}"
    )
    assert theirs.suspension is not None
    assert theirs.suspension.reason == CONTEXT_TOO_LONG, theirs.suspension.reason
    assert theirs.suspension.awaiting == (), (
        "the harness started parking this one WITH a call, which is the other "
        "half of this door and a different test"
    )
    assert CONTEXT_TOO_LONG in _PARKS_A_CALLER_CANNOT_ANSWER

    agent = pact_agent.for_spec(
        said, transport=_AModelWithAlmostNoRoom(script), tool_impls=tools
    )
    with pytest.raises(suspended_type) as waiting:
        agent.run_sync(ASKED)

    parked = waiting.value.parked
    assert parked.reason == CONTEXT_TOO_LONG
    assert waiting.value.result.pact.suspension is parked, (
        "the park on the exception and the park on the run are one record or "
        "they are two that can disagree"
    )
    assert parked.reason in str(waiting.value) and "resume=" in str(waiting.value), (
        "and the caller has to be told what the run is waiting for and how to "
        "answer it"
    )
