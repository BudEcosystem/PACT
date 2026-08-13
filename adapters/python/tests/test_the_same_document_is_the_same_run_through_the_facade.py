"""A `PactAgent` is the harness wearing a Pydantic AI face, and nothing else.

`PactAgent` does not exist yet. What it is meant to be is decided by D12 /
FR-4.1.1: a `pydantic_ai.agent.AbstractAgent` subclass whose `run`/`run_sync`
delegate to `pact_adapters.harness.run(spec, PydanticAITransport(...), ...)`, so
that a caller holding what looks like a Pydantic AI agent is in fact driving
PACT's loop with Pydantic AI carrying one model call at a time.

**This file is a facade-fidelity test and NOT a cross-engine parity claim, and
the distinction is the whole reason it is worth writing down.** Both arms of
every comparison below run the same `harness.run` over the same scripted turns,
so agreement is identical BY CONSTRUCTION. This repository has already measured
what that kind of comparison is worth as a claim about two different engines:
`tests/test_the_golden_set_runs_everywhere.py` lines 114-130 record two
mutations — deleting the answer shape from the second port's system text, and
deleting the skills from it — that left all fifty-nine trace assertions green,
because *a scripted model says the same thing whatever you tell it, so comparing
what it said compares the script*. Nothing here claims otherwise. Two runs of
one harness agreeing says nothing about Pydantic AI's loop and PACT's loop
agreeing, and no assertion below should ever be quoted as though it did.

What it IS worth is the one thing it can be worth: the alternative
implementation is real, shipped, and the tempting shortcut.
`pydantic_ai_interop.build_agent()` already turns a PACT spec into a live
`Agent` — tools bound, approvals bound — and its own docstring says what that
costs: *"The loop is Pydantic AI's. `loop:` stages, `interceptors:`,
`teamwork:`, `context-policy:`, `remembers:` and `when-it-runs-out:` are PACT
harness behaviour and this agent has none of them."* A `PactAgent` built by
wrapping `build_agent()` would satisfy the type, answer the question, and fail
every test in this file: no `re-read` stage, no `unenforced` sentences, no
`stopped_by`, no meter. That is the defect these tests exist to catch, and it is
a defect about the FACADE — which is exactly the scope claimed.

The document is `examples/refund-desk`, whose `loop: careful` is three stages
(gather, then re-read, then reply) with `payments` deliberately out of reach of
the stage that doubts. It is used here because a loop with more than one stage
is the cheapest thing that tells PACT's harness from anybody else's: a facade
that let `_agent_graph` drive has no stage vocabulary at all, so `phases` comes
back empty rather than wrong.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import RunResult, ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.limits import Meter  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.pydantic_ai_transport import (  # noqa: E402
    PydanticAITransport,
)

pydantic_ai = pytest.importorskip("pydantic_ai")

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"

#: The agent whose `loop:` line names `careful`. One place, because every
#: expectation below is about that shape and not about the standard one.
AGENT = "refund-desk"

ASKED = "Can I get a refund?"

#: Answered locally for the reason `script.py` gives: the claim under test is
#: which loop ran, not what a refund system says back, and D17 means this has to
#: run with no network at all.
TOOLS = {
    "zendesk": lambda a: f"ticket {a.get('ticket')}: lamp, 6 days ago, broken",
    "payments": lambda a: "refunded",
}


# ───────────────────────────────────────────────────────────────── the document


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    """The example tree, loaded by the real Rust loader (invariant P-1).

    A Python re-reading of the folder would be a second loader, and the two
    would drift — which is the same reason `test_portability.py` and
    `test_worked_example_loop.py` both come through this door.
    """
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(PACT_BIN), "show", str(EXAMPLE)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


@pytest.fixture(scope="module")
def spec(document: dict[str, Any]) -> AgentSpec:
    """The refund desk carrying its OWN shape of thinking.

    No `replace(..., loop=STANDARD)` here. `test_portability.py` substitutes the
    standard loop on purpose (its comment at lines 73-79 says why: seven
    transports, one loop), and that substitution is exactly what would make this
    file unable to see the difference it exists to see — a one-stage loop and no
    loop at all produce the same `phases` length of one per step.
    """
    return AgentSpec.from_document(document, AGENT, str(EXAMPLE))


# ─────────────────────────────────────────────────────── the two ways to run it


def careful_turns() -> Script:
    """One tool call, then one plain answer per remaining stage of `careful`.

    Four turns for four steps: the `gather` turn that looks the ticket up, the
    `gather` turn that ends the looking-up, the `re-read` turn that checks the
    decision against the policy, and the `reply` turn the customer sees.
    """
    return Script([
        Turn("Checking the ticket.", (ToolCall("zendesk", {"ticket": "T-1"}),)),
        Turn("The ticket says the lamp arrived broken 6 days ago."),
        Turn("Rule 2 applies: faulty on arrival, and 6 days is inside the window."),
        Turn("Approved: the item arrived damaged within 30 days."),
    ])


def a_turn_that_never_finishes() -> Script:
    """A model that calls a tool forever, so the author's ceiling has to decide.

    `Script.next_turn` clamps to the last entry, so one turn is a model that
    never stops — which is what makes `steps-at-most` and its
    `when-it-runs-out:` the thing that ends the run rather than the script.
    """
    return Script([Turn("still working", (ToolCall("zendesk", {}),))])


def through_the_harness(spec: AgentSpec, script: Script) -> RunResult:
    """The run as `harness.run` performs it, with nothing wrapped around it.

    Built as `PydanticAITransport(script)` with no workspace. Measured: passing
    `workspace=spec.workspace` changes none of the fields compared below, since
    the model this example binds is published free either way — so a facade that
    does pass the workspace through (and it should, or a workspace's own
    catalogue row prices nothing) still agrees with this arm.
    """
    return asyncio.run(run(spec, PydanticAITransport(script), ASKED, TOOLS))


def pact_agent_class() -> Any:
    """`PactAgent`, imported when a test asks for it rather than at module load.

    A module-level import of something that does not exist yet collapses the
    whole file into one collection error, which reports as a single line and
    hides which guarantees are outstanding. Imported here, each test below fails
    on its own and names the thing it wanted.
    """
    from pact_adapters.pact_agent import PactAgent

    return PactAgent


def through_the_facade(spec: AgentSpec, script: Script) -> Any:
    """The same run, entered through `PactAgent.run_sync`.

    The contract this file pins:

    * `PactAgent.for_spec(spec, script=..., tool_impls=...)` builds one;
    * `run_sync(prompt)` returns the SDK's own `AgentRunResult`, so a caller
      holding an `AbstractAgent` gets what the SDK promised them;
    * `.pact` on that result is the `harness.RunResult` the run actually
      produced. The SDK's result has five fields and none of them can carry a
      trace, a stage path, a meter or a list of rules nobody could decide — so
      the facade either publishes the PACT result or it throws away every
      honesty channel the harness has, which is the T7 breach the whole
      `unenforced`/`unmetered`/`never_reached` family exists to prevent.

    **A park leaves by the other door, and this helper follows it there.** This
    document's `limits.yaml` says `when-it-runs-out: ask-a-person`, so the
    ceiling scenario below does not END the run — it parks it, and `PactAgent`
    raises `PactSuspended` rather than returning a value a caller can drop on
    the floor. The record the run produced rides on the exception (`.result`),
    which is why catching it here loses nothing: every comparison in this file
    is against `harness.run`'s own `RunResult`, and that object is the same one
    either way. Which door a park leaves by is asserted on its own, in
    `test_a_park_leaves_this_facade_by_the_door_a_caller_cannot_ignore` — this
    helper is about the run, not about the door.
    """
    from pact_adapters.pact_agent import PactSuspended

    agent = pact_agent_class().for_spec(spec, script=script, tool_impls=TOOLS)
    try:
        return agent.run_sync(ASKED)
    except PactSuspended as waiting:
        assert waiting.result is not None, (
            "a park raised with no result throws away everything the run did"
        )
        assert waiting.result.pact.suspension is waiting.parked, (
            "the park on the exception and the park on the run are two records "
            "that can come to disagree about what the run is waiting for"
        )
        return waiting.result


class Watching(PydanticAITransport):
    """The same transport, keeping what each model call was handed.

    What a run RETURNS is the same on both arms by construction — one harness,
    one script — so the fields compared below cannot see a facade that let
    somebody else's loop drive as long as the answers matched. What the model
    was SHOWN can: the stage vocabulary decides which tools are offered at each
    step, and a loop with no stages offers all of them every time.
    """

    def __init__(self, script: Script) -> None:
        super().__init__(script)
        self.offered: list[list[str]] = []

    async def model_call(self, system: Any, history: Any, tools: Any) -> Any:
        self.offered.append(sorted(str(t.get("name", "")) for t in (tools or ())))
        return await super().model_call(system, history, tools)


def counted(meter: "Meter | None") -> dict[str, float]:
    """What a meter COUNTED, without the reading of the clock it started at.

    `Meter.started` is a `time.monotonic()` sample taken inside `harness.run`,
    so two runs of the same document can never carry the same one and comparing
    `Meter` objects whole would fail on every correct implementation. The four
    below are the ones a ceiling is measured against.
    """
    assert meter is not None, "a run with no meter measured nothing at all"
    return {
        "steps": meter.steps,
        "tool_calls": meter.tool_calls,
        "tokens": meter.tokens,
        "money": meter.money,
    }


# ───────────────────────────────────────────────────────────── the same run


def test_the_facade_runs_the_document_the_harness_would_have_run(spec: AgentSpec) -> None:
    """A facade that answers differently is a second implementation of the loop.

    The failure this prevents is not a wrong answer — it is a `PactAgent` built
    on `pydantic_ai_interop.build_agent()`, which produces a real Pydantic AI
    `Agent` whose loop is `_agent_graph`'s. Such an agent answers the question,
    types correctly, and enforces none of `loop:`, `interceptors:`, `teamwork:`,
    `context-policy:` or `when-it-runs-out:` — so the author's governed document
    would be running ungoverned behind a class named after it, and the only
    visible symptom is a transcript that no longer matches.
    """
    theirs = through_the_harness(spec, careful_turns())
    ours = through_the_facade(spec, careful_turns())

    assert ours.pact.trace() == theirs.trace(), json.dumps(
        {"facade": ours.pact.trace(), "harness": theirs.trace()}, indent=2
    )
    assert ours.pact.output == theirs.output
    assert ours.pact.halted == theirs.halted
    assert ours.pact.stopped_by == theirs.stopped_by
    assert ours.pact.unenforced == theirs.unenforced
    assert counted(ours.pact.used) == counted(theirs.used)
    # Non-empty first, because two empty traces are equal and would make every
    # line above true of a facade that ran nothing at all.
    assert theirs.trace(), "the harness arm recorded no steps, so nothing was compared"


def test_the_authored_stages_still_run_when_the_run_comes_through_the_facade(
    spec: AgentSpec,
) -> None:
    """`loops/careful.yaml` argues for a stage that cannot spend the money.

    Its own words: *the stage whose whole purpose is doubt must not be the stage
    that can spend the money*. That is a property of a RUN, and it survives only
    while something with a stage vocabulary is driving. Pydantic AI's loop has
    none — it resolves one tool set per run — so a facade that hands the wheel
    over does not narrow `re-read` to `zendesk`, it abolishes `re-read`. The
    customer then reads a decision written in the same breath as the last
    lookup, which is the exact mistake the file was written to stop.

    `phases` is checked rather than `trace()` because `RunResult.trace()`
    deliberately excludes the stage path (harness.py:210-212) — it is the
    cross-runtime contract, and only one runtime can produce stages. So the one
    field that tells PACT's loop from anybody else's is outside the field this
    file otherwise leans on.
    """
    theirs = through_the_harness(spec, careful_turns())
    ours = through_the_facade(spec, careful_turns())

    assert ours.pact.phases == theirs.phases, {
        "facade": ours.pact.phases,
        "harness": theirs.phases,
    }
    # Derived from the document, not written down here: an edit to the example
    # moves what this expects instead of quietly passing against a stale copy.
    checking = [
        name
        for name, step in (spec.loop.steps or {}).items()
        if step.does.value == "check-its-work"
    ]
    assert checking, f"{AGENT} no longer names a checking stage, so this asserts nothing"
    assert set(checking) <= set(ours.pact.phases), (
        f"the facade never entered {checking}, so the decision reached the customer "
        f"without being read back against the policy: {ours.pact.phases}"
    )


def test_a_ceiling_stops_the_facade_where_it_stops_the_harness(spec: AgentSpec) -> None:
    """A ceiling the facade does not hold is a runaway wearing a limit.

    `limits.yaml` is enforcement, not documentation: `steps-at-most` with the
    author's own `when-it-runs-out:` decides what happens at the edge. Pydantic
    AI has no agent-level ceiling at all — `UsageLimits` is an argument to
    `run()`, which `pydantic_ai_interop._SPEC_CANNOT_TAKE['limits']` says in so
    many words — so a facade that delegates the loop turns a written ceiling
    into a comment. The run then keeps calling the model, keeps calling the
    tool, and reports itself finished.

    `stopped_by` is what tells "answered early" from "finished", so it is
    asserted present as well as equal: both being `None` is exactly what a
    runaway looks like from here.
    """
    theirs = through_the_harness(spec, a_turn_that_never_finishes())
    ours = through_the_facade(spec, a_turn_that_never_finishes())

    assert theirs.stopped_by is not None, (
        "the harness arm did not reach a ceiling, so this test compares nothing — "
        "check `steps-at-most` in agents/refund-desk/limits.yaml"
    )
    assert theirs.halted != "final", "a run that ran out of steps did not finish"
    assert ours.pact.stopped_by == theirs.stopped_by
    assert ours.pact.halted == theirs.halted
    assert ours.pact.trace() == theirs.trace()
    assert counted(ours.pact.used) == counted(theirs.used)


def test_the_stage_that_doubts_is_offered_only_the_tools_it_may_use(
    spec: AgentSpec,
) -> None:
    """`may-use:` is a fact about one MODEL CALL, and only a stage can hold it.

    `loops/careful.yaml` writes `may-use: [zendesk, refund-policy]` on `re-read`
    and argues for it in one sentence: *the stage whose whole purpose is doubt
    must not be the stage that can spend the money*. Pydantic AI resolves one
    tool set per RUN, so a facade that hands the wheel to `_agent_graph` offers
    `payments` at every step — including the one that is supposed to be
    re-reading its own decision — and the only way to see that is to look at
    what the model was handed, because a scripted model calls what the script
    says whatever it is offered.

    Both arms are compared step by step rather than asserted against a list
    written here, and then the withheld tool is named on its own: two runs that
    both offered everything would agree perfectly and prove nothing.
    """
    theirs, ours = Watching(careful_turns()), Watching(careful_turns())
    asyncio.run(run(spec, theirs, ASKED, TOOLS))
    pact_agent_class().for_spec(spec, transport=ours, tool_impls=TOOLS).run_sync(ASKED)

    assert ours.offered == theirs.offered, {"facade": ours.offered, "harness": theirs.offered}
    doubting = [
        name
        for name, step in (spec.loop.steps or {}).items()
        if step.does.value == "check-its-work"
    ]
    narrowed = [step.may_use for name, step in (spec.loop.steps or {}).items() if name in doubting]
    assert narrowed and narrowed[0], f"{AGENT}'s doubting stage no longer narrows its tools"
    withheld = sorted({t.name for t in spec.tools} - set(narrowed[0]))
    assert withheld == ["payments"], "the example stopped withholding the tool that spends"

    assert any(withheld[0] not in offered for offered in ours.offered), (
        f"every step was offered {withheld[0]}, so the stage that doubts could "
        f"have spent the money: {ours.offered}"
    )
    assert [offered for offered in ours.offered if offered == ["zendesk"]], (
        f"no step was narrowed to the doubting stage's own `may-use:`: {ours.offered}"
    )


def test_a_park_leaves_this_facade_by_the_door_a_caller_cannot_ignore(
    spec: AgentSpec,
) -> None:
    """This document's ceiling parks, and a returned park is one a caller drops.

    `limits.yaml` says `when-it-runs-out: ask-a-person`, so the runaway above
    does not END — it waits for whoever owns the budget. A value handed back for
    a wait is a value that can be logged and forgotten, and forgetting it leaves
    the person never asked, the spend already made thrown away, and nothing
    anywhere reporting it. So this door raises, and everything the run knew
    rides on the exception: the park record ITSELF (never a copy) and the
    `AgentRunResult` that would otherwise have been returned.

    `harness.run` is the other arm here as everywhere in this file: the park a
    caller is shown has to be the park the harness produced, not a second
    description of it composed on the way out.
    """
    from pact_adapters.pact_agent import PactSuspended

    theirs = through_the_harness(spec, a_turn_that_never_finishes())
    agent = pact_agent_class().for_spec(
        spec, script=a_turn_that_never_finishes(), tool_impls=TOOLS
    )
    with pytest.raises(PactSuspended) as waiting:
        agent.run_sync(ASKED)

    assert theirs.suspension is not None, (
        "the harness arm did not park, so this test is about nothing — check "
        "`when-it-runs-out:` in agents/refund-desk/limits.yaml"
    )
    parked = waiting.value.parked
    assert parked.reason == theirs.suspension.reason
    assert parked.in_words == theirs.suspension.in_words
    assert waiting.value.result.pact.suspension is parked
    assert waiting.value.result.pact.trace() == theirs.trace(), (
        "the run carried on the exception is not the run the harness performed"
    )
    assert parked.in_words in str(waiting.value), (
        "the question a person has to be shown is not in what the caller reads"
    )


def test_the_facade_reports_the_same_rules_it_could_not_enforce(spec: AgentSpec) -> None:
    """An honesty channel the facade drops presents an ungoverned run as governed.

    `unenforced` is where a rule the author wrote and this run could not decide
    arrives as a sentence naming the file, the line and something to type. On
    this example it is not empty: four `bind:` lines nothing supplied a value
    for, and one approval rule about `zendesk/reply` that could not be applied
    to a call naming no action. A facade that returns a bare `AgentRunResult`
    has nowhere to put any of it, so the author is told their approval policy
    held on a run where it decided nothing — which is the silent degradation T7
    forbids, arriving through the friendliest door in the repository.
    """
    theirs = through_the_harness(spec, careful_turns())
    ours = through_the_facade(spec, careful_turns())

    assert theirs.unenforced, (
        "the harness arm reported nothing unenforced, so equality below is "
        "vacuous — this example is expected to carry unfilled `bind:` lines"
    )
    assert ours.pact.unenforced == theirs.unenforced, json.dumps(
        {"facade": list(ours.pact.unenforced), "harness": list(theirs.unenforced)},
        indent=2,
    )


def test_the_model_is_asked_the_same_number_of_times_either_way(spec: AgentSpec) -> None:
    """A different number of model calls is a different loop, matching text or not.

    `script.py` makes the count part of the contract for this reason, and
    `test_portability.py` holds all seven transports to it. The facade is the
    eighth thing that can get it wrong and the most likely to: an extra
    `_agent_graph` turn to satisfy an output validator, or a retry Pydantic AI
    owns and PACT does not, is invisible in the answer and doubles the bill.
    """
    theirs_script = careful_turns()
    ours_script = careful_turns()
    through_the_harness(spec, theirs_script)
    through_the_facade(spec, ours_script)

    assert theirs_script.calls, "the harness arm never called the model"
    assert ours_script.calls == theirs_script.calls, {
        "facade": ours_script.calls,
        "harness": theirs_script.calls,
    }


# ──────────────────────────────────────────────────────────── the facade half


def test_what_comes_back_is_the_sdks_own_result_carrying_the_pact_run(
    spec: AgentSpec,
) -> None:
    """A lookalike result breaks every caller the facade exists to serve.

    The point of wearing this face is that code written against Pydantic AI
    keeps working — and that code reads `.output`, hands the object on, and in
    the case of `AbstractAgent.run_stream_events` wraps it in an
    `AgentRunResultEvent(result=...)`. A namedtuple that happens to have an
    `output` attribute satisfies none of that, and the failure surfaces in
    somebody else's library rather than here.

    The other half is `.pact`: `AgentRunResult` has five fields
    (`pydantic_ai/run.py:489-501`) and not one of them can hold a trace, a stage
    path, a meter or a list of rules nobody could decide, so a facade that
    returns only what the SDK defines has thrown the whole PACT result away.
    """
    ours = through_the_facade(spec, careful_turns())

    assert isinstance(ours, pydantic_ai.AgentRunResult), (
        f"run_sync returned a {type(ours).__name__}; a caller holding an "
        f"AbstractAgent was promised an AgentRunResult"
    )
    assert isinstance(ours.pact, RunResult)
    # The SDK-facing answer and the PACT answer are the same words. Two spellings
    # of one run is how a caller comes to log one and act on the other.
    assert ours.output == ours.pact.output


def test_the_facade_is_an_agent_the_sdk_itself_would_accept(spec: AgentSpec) -> None:
    """Duck-typing here means the facade silently stops being one.

    `AbstractAgent` has eleven abstract members on 2.21 and its `run_sync`,
    `run_stream_events` and `run_stream_sync` are CONCRETE — they route through
    `self.run` and `self.iter`. Subclassing is therefore what keeps one loop in
    one place: override `run` and the synchronous door follows for free. A
    stand-alone class that merely has a `run_sync` gets no such guarantee, is
    refused wherever an `AbstractAgent` is annotated, and drifts from the SDK the
    first time that base class grows a parameter.

    `__abstractmethods__` is asserted empty rather than trusted to the
    constructor, because a class can be *defined* with holes in it and only
    raises when somebody instantiates it — which, for an agent built by a
    classmethod behind a fixture, can be a long way from where the hole is.
    """
    from pydantic_ai.agent import AbstractAgent

    agent = pact_agent_class().for_spec(spec, script=careful_turns(), tool_impls=TOOLS)

    assert isinstance(agent, AbstractAgent)
    assert type(agent).__abstractmethods__ == frozenset(), (
        f"PactAgent still leaves {sorted(type(agent).__abstractmethods__)} abstract"
    )
    # The author's own identity, not a generated one: an agent whose `name` is
    # not the document's is unfindable in whatever traced it.
    assert agent.name == (spec.name or spec.key)


def test_both_doors_into_the_facade_are_the_same_loop(spec: AgentSpec) -> None:
    """Two hand-written entry points drift, and only one of them gets tested.

    `AbstractAgent.run_sync` is concrete and calls `self.run` through
    `_utils.run_until_complete` (`agent/abstract.py:685-686`), so a `PactAgent`
    that overrides `run` alone has both doors by construction. One that writes
    `run_sync` separately has two implementations of the loop, and the async one
    — which `run_stream_events` also goes through — is the one no test in this
    file would otherwise open.
    """
    agent = pact_agent_class().for_spec(spec, script=careful_turns(), tool_impls=TOOLS)

    synchronous = agent.run_sync(ASKED)
    asynchronous = asyncio.run(agent.run(ASKED))

    assert asynchronous.pact.trace() == synchronous.pact.trace()
    assert asynchronous.pact.halted == synchronous.pact.halted
    assert asynchronous.pact.phases == synchronous.pact.phases
    assert asynchronous.output == synchronous.output


# ───────────────────────── the branching loop, which needed no second engine


def test_the_one_loop_that_forks_needs_no_driver_of_its_own() -> None:
    """`tree-of-thought` runs through this door, and that is the whole of W4.

    The rejected design — a `PactLoop` capability executing PACT's stages on
    Pydantic AI's graph — could not have carried this one. `_agent_graph` is a
    single linear cycle (`UserPromptNode` → `ModelRequestNode` → `CallToolsNode`)
    and a stage machine that forks has nowhere to fork INTO, so the plan booked a
    separate `agent.iter()` driver for it and deferred that as its own milestone.

    The façade makes the milestone empty rather than done. `run` awaits
    `harness.run`, so every loop the harness can walk arrives here already
    working, and a loop the harness gains later arrives working without this file
    being edited. Pinned rather than assumed, because "it should be free" is the
    kind of claim that is true right up until a door starts re-deriving the stage
    machine on its own — and the failure then is a loop silently walking one
    branch, which reads exactly like a loop that finished.
    """
    from pact_adapters.loops import Loop

    spec = AgentSpec(
        name="tot",
        description="picks between options it thought of",
        instructions="think it through",
        loop=Loop.from_library("pact:loop/tree-of-thought"),
        max_steps=8,
    )
    agent = pact_agent_class().for_spec(
        spec,
        script=Script([Turn("option A"), Turn("A is best"), Turn("final answer")]),
    )
    answered = agent.run_sync("pick one")

    # Every stage the library document declares, in the order it declares them —
    # not merely "it did not crash".
    assert answered.pact.phases == ["propose", "judge", "follow"]
    assert answered.pact.halted == "final"
    assert answered.output == "final answer"
