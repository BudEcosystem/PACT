"""`PactAgent` is a door onto `harness.run`, and this is the evidence that it changes nothing.

**What this file is not.** It is not a permission slip. `PactAgent` is HARNESS
LOWERING (FR-4.1.1): the OBJECT is a `pydantic_ai.agent.abstract.AbstractAgent`
so it goes wherever an `Agent` goes, and the LOOP is still `harness.run` over a
PACT transport, so the author's stages, ceilings, rules and gate are the ones
that execute. Nothing about that arrangement needs a conformance argument to be
allowed — it is the arrangement D12 asks for. What it needs is EVIDENCE, because
a facade is exactly the shape of thing that can quietly become a second runtime:
one dropped keyword on the way to `harness.run` and the author's `run-inputs:`
stop arriving, one extra model call and the loop is a different loop, and the
scripted answer comes back byte-identical either way.

So this file borrows the Conformance Report's *method* and not its authority. It
runs the same scripted eval twice — once as `harness.run(spec,
ReferenceTransport(script), …)`, the framework-free control arm, and once through
`PactAgent` — and compares the four things `conformance.report()` compares:
`trace()`, `output`, `halted`, and how many times the script was asked. The
tolerance is `conformance.EPSILON`, which is `0.0`, and for the reason declared
there: a scripted model has nothing legitimate to differ about, so a non-zero
tolerance would be room for a real divergence to hide in.

`PactAgent` is deliberately NOT in `conformance.TARGETS`, and
`test_the_facade_is_not_an_adapter_and_the_report_is_right_not_to_list_it` holds
the reason structurally rather than in prose: every row of that report is a
`Transport` — an object with `model_call` and `lattice` that the report
constructs from a `Script` alone — and the facade is a CALLER of the harness, not
a seam under it. Listing it would make the report claim to have measured an
adapter that does not exist.

**What is asserted, and what is refused.** M1 shipped 1621 green tests in which
39 of 39 mutations survived, and
`test_the_golden_set_runs_everywhere.py:114-130` records why: *"a scripted model
says the same thing whatever you tell it, so comparing what it said compares the
script."* Nothing below asserts that the model said `ANSWER`. What is asserted is
what the code DID: which tools ran and with which arguments (`trace()`), what the
model was SHOWN at each step (`_watching`), which ceiling ended the run
(`halted`, `stopped_by`), how many model calls the loop made (`Script.calls`),
and which TYPE arrives for a run that did not answer.
"""

from __future__ import annotations

import asyncio
import copy
import dataclasses
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.conformance import EPSILON, TARGETS  # noqa: E402
from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.limits import Action  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"

pytest.importorskip("pydantic_ai")

from pact_adapters.pact_agent import (  # noqa: E402
    Halted,
    PactAgent,
    PactSuspended,
)
from pact_adapters.transports.pydantic_ai_transport import (  # noqa: E402
    PydanticAITransport,
)

#: What is asked. The worked example's own subject, so the run reaches the
#: author's gate, the author's `careful` loop and the author's ceilings rather
#: than a path no document describes.
ASKED = "refund order A-1"

#: The author's three `answers-with:` fields as JSON, which is what the unset
#: mode (`prompted`) asks the model for. Never asserted against — it is here so
#: that a run REACHES `done` and the comparison has a finished run to compare.
ANSWER = json.dumps(
    {"decision": "approved", "reason": "the item arrived faulty", "amount": "40 USD"}
)

#: The values the surrounding system supplies for the author's `run-inputs:`.
#: `refund-desk` declares `customer-id` and binds it into every action of both
#: tools, so a run handed this and a run handed nothing call the same tool with
#: DIFFERENT arguments — which is what makes `run_inputs=` visible in a trace
#: instead of being a keyword nothing can see.
SUPPLIED = {"customer-id": "C-9"}


def _tool(name: str) -> Any:
    """A tool that answers with the ARGUMENT NAMES it was actually handed.

    A tool returning a fixed string makes every `trace()` comparison blind to the
    half of a call that matters: `zendesk` called with `{action, ticket-id}` and
    `zendesk` called with `{action, ticket-id, customer-id}` produce the same
    trace, because `Step.tool_results` records what the tool said and
    `Step.tool_calls` records what the MODEL chose — and the author's `binds:`
    lines are added between the two. So the one place a dropped `run-inputs:` is
    visible is what the tool received, and that is what this puts in the trace.
    """

    def ran(args: "dict[str, Any]") -> str:
        return f"{name} was called with " + json.dumps(sorted(args))

    return ran


TOOLS = {name: _tool(name) for name in ("zendesk", "payments", "refund-policy")}


def _answers_at_once() -> Script:
    """One turn: the model answers and nothing is called."""
    return Script([Turn(ANSWER)])


def _calls_a_tool_first() -> Script:
    """A tool call, then an answer.

    The one-turn script is the one `conformance.report()` uses and its own
    `not-compared` list names the gap in it: *"multi-step tool sequences: the
    script answers without calling a tool"*. A facade that never passed
    `tool_impls` through, or passed it to the wrong keyword, is invisible to a
    run where no tool is called and is a wall of `error: no tool named 'zendesk'`
    in this one.
    """
    return Script([
        Turn(
            "looking the ticket up",
            (ToolCall("zendesk", {"action": "read-ticket", "ticket-id": "T-1"}),),
        ),
        Turn(ANSWER),
    ])


SCRIPTS = {
    "answers-at-once": _answers_at_once,
    "calls-a-tool-first": _calls_a_tool_first,
}


def _over_the_reference(script: Script, spec: AgentSpec) -> Any:
    """The facade over the SAME transport the control arm uses.

    This is the pairing in which the facade is the only variable at all: both
    sides are the script with no framework under it, so a divergence here cannot
    be blamed on Pydantic AI and is the facade's, entirely.
    """
    return ReferenceTransport(script)


def _over_pydantic_ai(script: Script, spec: AgentSpec) -> Any:
    """The facade over the transport it builds for itself.

    Constructed here the way `PactAgent.__init__` constructs it — the author's
    bound model and their workspace — so the watching variant of this pairing
    measures the same thing the `script=` door does.
    """
    return PydanticAITransport(script, model=spec.model or None, workspace=spec.workspace)


TRANSPORTS = {
    "over-the-reference-transport": _over_the_reference,
    "over-pydantic-ai": _over_pydantic_ai,
}


def _watching(make: Any) -> Any:
    """A transport that keeps what every model call was HANDED.

    The same shim `conformance._Watching` puts around the reference — and it is
    here for the claim a run's own result cannot make. `trace()` records what
    came BACK; a facade that ran the wrong spec, put a different question in
    front of the model, or offered a different tool list at a stage is invisible
    in a trace driven by a script and visible only in what went IN.

    `conformance.report()` collects `told` and `offered` and then compares
    neither: `same` is four fields and none of them is an input. So this is the
    half of that method the report leaves on the floor.

    Wrapped on the INSTANCE rather than subclassed, because the two transports
    take different constructor arguments and a subclass per transport is two
    places for this shim to differ from itself.
    """

    def build(script: Script, spec: AgentSpec) -> Any:
        transport = make(script, spec)
        shown: "list[dict[str, Any]]" = []
        inner = transport.model_call

        async def model_call(system: Any, history: Any, tools: Any) -> Any:
            shown.append({
                "system": system,
                # Copied, because the harness goes on appending to the SAME list
                # after the call returns — a reference here records the end of
                # the run once per step and compares nothing.
                "history": copy.deepcopy(list(history)),
                "offered": [t["name"] for t in tools],
            })
            return await inner(system, history, tools)

        transport.model_call = model_call
        transport.shown = shown
        return transport

    return build


def _compared(ran: Any, script: Script) -> "dict[str, Any]":
    """The four fields `conformance.report()` compares, off one run.

    `calls` is in here for the reason `Script` states in its own docstring: a
    runtime that calls the model a different number of times has changed the
    loop, even when the final text happens to match — which, with a scripted
    model, it always does.
    """
    return {
        "trace": ran.trace(),
        "output": ran.output,
        "halted": ran.halted,
        "calls": script.calls,
    }


def _divergence(baseline: "dict[str, Any]", got: "dict[str, Any]") -> "list[str]":
    """How far apart two runs are, in the units this comparison has.

    The report's comparison is an equality over four fields, so the distance
    between two runs is the number of those fields that differ. `EPSILON` is
    `0.0` and is imported rather than restated, so a tolerance loosened in the
    artifact is loosened here too and cannot be loosened here alone.
    """
    return [field for field in baseline if baseline[field] != got[field]]


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
    return AgentSpec.from_document(document, "refund-desk", str(EXAMPLE))


def _reference(spec: AgentSpec, script: Script, **how: Any) -> Any:
    """The control arm: `harness.run` with no framework anywhere near it."""
    return asyncio.run(
        run(spec, ReferenceTransport(script), ASKED, tool_impls=dict(TOOLS), **how)
    )


def _through_the_facade(agent: PactAgent, **how: Any) -> Any:
    """One facade run, as the PACT record the comparison is made on.

    A park leaves through `PactSuspended` rather than returning, so the record
    is fetched off the exception — which is the point of carrying it there: a
    park that lost the run would make the two sides incomparable exactly where
    comparing them matters most.
    """
    try:
        return asyncio.run(agent.run(ASKED, **how)).pact
    except PactSuspended as parked:
        return parked.result.pact


# ────────────────────────────────── the four fields the report compares


@pytest.mark.parametrize("shape", sorted(SCRIPTS))
@pytest.mark.parametrize("way", sorted(TRANSPORTS))
def test_the_facade_and_the_reference_agree_on_every_field_the_report_compares(
    spec: AgentSpec, shape: str, way: str
) -> None:
    """A facade that quietly runs a different loop is a second runtime nobody declared.

    This is the whole claim of `PactAgent` in one assertion. Everything that
    could make it false is a silent change to what executes: a `tool_impls` that
    never arrives (every call comes back `error: no tool named …`), an extra
    model call (`calls` moves), a different spec (`trace` moves), a ceiling
    decided somewhere other than `limits.py` (`halted` moves). None of them
    change what the scripted model SAYS, which is why none of them is caught by
    reading `.output` as text — and why the report compares four fields rather
    than one.

    Both transports, because they fail differently: the reference pairing is the
    facade as the ONLY variable, and the Pydantic AI pairing is the transport a
    caller actually gets.
    """
    baseline_script = SCRIPTS[shape]()
    baseline = _compared(_reference(spec, baseline_script), baseline_script)

    facade_script = SCRIPTS[shape]()
    agent = PactAgent.for_spec(
        spec,
        transport=TRANSPORTS[way](facade_script, spec),
        tool_impls=dict(TOOLS),
    )
    got = _compared(_through_the_facade(agent), facade_script)

    diverged = _divergence(baseline, got)
    assert len(diverged) <= EPSILON, (
        f"the facade {way} diverged from the framework-free reference on "
        f"{diverged}, and the declared tolerance is {EPSILON}:\n"
        + json.dumps(
            {f: {"reference": baseline[f], "facade": got[f]} for f in diverged},
            indent=2,
            default=str,
        )
    )


def test_the_facade_built_from_a_script_alone_runs_what_the_reference_ran(
    spec: AgentSpec,
) -> None:
    """The door a caller actually uses is the door nothing else here opens.

    Every other test hands `PactAgent` a transport somebody else built.
    `PactAgent.__init__` has its own construction line for the `script=` case —
    it builds `PydanticAITransport(script, model=…, workspace=…)` — and a caller
    who wrote `PactAgent.for_spec(spec, script=…)` is running THAT object.

    The three assertions are three different failures, and the last two do not
    show up in a trace at all:

    * the loop diverges — the four fields, as everywhere else;
    * the WRONG MODEL is bound, which is a run executing on something nobody
      asked for and which `harness` can only report as a pin mismatch after the
      fact;
    * the WORKSPACE is lost, so a row this workspace added to its own
      `models/catalog.yaml` prices and sizes nothing — and a spend cap over a
      model nothing can price is a ceiling reported as `unmetered` rather than
      enforced.
    """
    baseline_script = _calls_a_tool_first()
    baseline = _compared(_reference(spec, baseline_script), baseline_script)

    facade_script = _calls_a_tool_first()
    agent = PactAgent.for_spec(spec, script=facade_script, tool_impls=dict(TOOLS))
    got = _compared(_through_the_facade(agent), facade_script)

    assert len(_divergence(baseline, got)) <= EPSILON, (
        f"a PactAgent built from a script alone diverged on "
        f"{_divergence(baseline, got)}"
    )
    # `_transport` rather than a transport this test built, because the object
    # under test IS the one `PactAgent.__init__` constructed — there is no other
    # way to ask what it bound, and a test that built its own would be checking
    # its own arithmetic.
    assert agent._transport.workspace == spec.workspace, (
        f"the self-built transport bound the workspace "
        f"{agent._transport.workspace!r} and the author's document is at "
        f"{spec.workspace!r} — a model this workspace priced in its own "
        "`models/catalog.yaml` is unpriced, and the author's spend cap comes "
        "back on `unmetered`"
    )
    # A second agent, whose author pinned a `model:`. `refund-desk` pins none, so
    # the line under test (`model=spec.model or None`) is indistinguishable from
    # dropping the argument on that document alone.
    pinned = dataclasses.replace(spec, model="qwen2.5-7b-instruct")
    held = PactAgent.for_spec(pinned, script=_answers_at_once())
    assert held._transport.model == "qwen2.5-7b-instruct", (
        f"the author pinned `model: qwen2.5-7b-instruct` and the transport bound "
        f"{held._transport.model!r} — the run executes on a model nobody asked "
        "for"
    )


def test_this_comparison_would_notice_a_divergence(spec: AgentSpec) -> None:
    """A comparison that cannot fail is an all-green report that measured nothing.

    Every assertion in this file rests on `_divergence` being able to see a
    difference. `trace()`, `output`, `halted` and `calls` are all things a
    scripted run reproduces exactly, so a helper that compared the wrong objects
    — two views of one run, say, or two empty dicts — would agree with itself
    forever and the facade could diverge freely underneath it.

    So: change ONE line of the author's document, run the same script through
    both sides, and require the comparison to report it. `steps-at-most: 1`
    stops the run a step in, which moves `halted`, `trace` and `calls` at once.
    """
    script = _calls_a_tool_first()
    unchanged = _compared(_reference(spec, script), script)

    stops_early = dataclasses.replace(spec, max_steps=1)
    other_script = _calls_a_tool_first()
    changed = _compared(_reference(stops_early, other_script), other_script)

    assert _divergence(unchanged, changed), (
        "an agent stopped after one step compared equal to one that ran to "
        "`done` — this file's comparison sees nothing and neither do its tests"
    )


# ──────────────────────────────────────────── what the model was shown


@pytest.mark.parametrize("way", sorted(TRANSPORTS))
def test_the_facade_shows_the_model_what_the_reference_showed_it(
    spec: AgentSpec, way: str
) -> None:
    """A facade that ran the wrong agent is invisible in an answer a script wrote.

    `trace()` records what came back, and what comes back from a scripted model
    is the script. So a facade that put a different question in front of the
    model, ran a spec with different instructions, or offered a different tool
    list at a stage produces a byte-identical trace and a byte-identical answer.
    The only place any of that is visible is the arguments the harness handed to
    `model_call`, step by step — the system text, the conversation, and the names
    of the tools the stage allowed.

    That third one is the author's `loop:` doing its job. `refund-desk`'s
    `re-read` stage declares `may-use: [zendesk, refund-policy]`, and
    `refund-policy` is a skill rather than a tool, so that one step is offered
    `zendesk` alone while the stages either side of it are offered everything —
    and the `reply` stage is offered nothing at all. A facade that let something
    else drive the loop would offer the whole set at every step and answer
    identically.
    """
    baseline_transport = _watching(_over_the_reference)(_calls_a_tool_first(), spec)
    asyncio.run(run(spec, baseline_transport, ASKED, tool_impls=dict(TOOLS)))
    assert len({tuple(step["offered"]) for step in baseline_transport.shown}) > 1, (
        "the reference offered the same tools at every step, so comparing the "
        "offers says nothing about whether the author's `loop:` ran — this "
        "assertion has gone vacuous and the document it leans on has changed"
    )

    facade_script = _calls_a_tool_first()
    facade_transport = _watching(TRANSPORTS[way])(facade_script, spec)
    agent = PactAgent.for_spec(
        spec, transport=facade_transport, tool_impls=dict(TOOLS)
    )
    _through_the_facade(agent)
    shown = facade_transport.shown

    assert [step["offered"] for step in shown] == [
        step["offered"] for step in baseline_transport.shown
    ], "the facade offered the model a different tool list from the reference"
    assert [step["system"] for step in shown] == [
        step["system"] for step in baseline_transport.shown
    ], "the facade told the model something the reference did not"
    assert [step["history"] for step in shown] == [
        step["history"] for step in baseline_transport.shown
    ], "the facade put a different conversation in front of the model"


def test_the_question_the_facade_asks_is_the_question_it_was_handed(
    spec: AgentSpec,
) -> None:
    """A prompt that reached nothing is a run that answered a question nobody asked.

    `PactAgent.run` takes this SDK's `user_prompt=` and `harness.run` takes one
    string, and the line between them is `_asked()`. If that line dropped the
    words — passed the empty string, or the SDK's own default — the scripted
    model would answer exactly as before and `trace()` would be identical,
    because a script does not read its input. What changes is the conversation
    the model was shown and `RunResult.asked`, which is the field every promoted
    eval case is written from.
    """
    transport = _watching(_over_the_reference)(_answers_at_once(), spec)
    agent = PactAgent.for_spec(spec, transport=transport, tool_impls=dict(TOOLS))
    ran = _through_the_facade(agent)

    assert ran.asked == ASKED, (
        f"the run recorded {ran.asked!r} as what it was asked, and it was handed "
        f"{ASKED!r} — every eval case promoted from this run would carry the "
        "wrong question"
    )
    first = transport.shown[0]["history"]
    assert any(ASKED in json.dumps(entry, default=str) for entry in first), (
        f"the model was never shown the question: {first}"
    )


# ────────────────────────────────────── what the surrounding system supplies


def test_a_run_input_the_facade_was_handed_reaches_the_tool_the_reference_called(
    spec: AgentSpec,
) -> None:
    """A dropped `deps=` calls the author's tool without the argument they bound.

    This is the failure `PactAgent.run`'s own docstring records from the worked
    example: *"the payments tool received `{order-number, amount, action}` and
    never `customer-id`, so whose order went on being something nobody
    supplied."* `deps=` on this SDK's `run()` IS the author's `run-inputs:` —
    which is why `deps_type` answers `dict` — and every action of both
    `refund-desk` tools carries `customer-id: run-inputs.customer-id` under
    `binds:`.

    Dropped, nothing raises: the model still chooses the same call, the script
    still answers, the trace still shows `zendesk` with the arguments the MODEL
    picked. The tool is simply called with one argument fewer, and the only
    witness is what the tool received — which `_tool` puts in the trace.
    """
    baseline_script = _calls_a_tool_first()
    baseline = _compared(
        _reference(spec, baseline_script, run_inputs=SUPPLIED), baseline_script
    )

    facade_script = _calls_a_tool_first()
    agent = PactAgent.for_spec(
        spec,
        transport=ReferenceTransport(facade_script),
        tool_impls=dict(TOOLS),
    )
    got = _compared(_through_the_facade(agent, deps=SUPPLIED), facade_script)

    reached = json.dumps(got["trace"])
    assert "customer-id" in reached, (
        "the facade was handed the author's `run-inputs:` and the tool was "
        f"called without them: {reached}"
    )
    assert len(_divergence(baseline, got)) <= EPSILON, (
        f"the facade diverged on {_divergence(baseline, got)} with "
        "`run-inputs:` supplied"
    )


# ─────────────────────────────────────────── a run that did not finish


def _stops_where_it_runs_out(spec: AgentSpec) -> AgentSpec:
    """The author's document with two lines changed: a ceiling of one step, and
    `when-it-runs-out: stop-and-say-so` instead of `ask-a-person`.

    Changed rather than a second example, so everything else about the run — the
    `careful` loop, the gate, the tools, the answer shape — is still the worked
    example's own.
    """
    return dataclasses.replace(
        spec,
        max_steps=1,
        limits=dataclasses.replace(spec.limits, when_it_runs_out=Action.STOP),
    )


def test_a_facade_run_that_stopped_stopped_where_the_reference_stopped(
    spec: AgentSpec,
) -> None:
    """"Ran out of budget" arriving as an answer is the worst outcome that looks like success.

    `RunResult.output` is typed `str` and the halt paths write English into it,
    so a facade that handed a halt back as an ordinary answer would give a caller
    a string that a validator accepts, a `pydantic_evals` case scores, and a
    second agent reads as this one's answer. That is why `.output` is a `Halted`
    TYPE here — a distinct type is the only check a downstream consumer can make
    without parsing prose in a language that can change.

    And the halt must be the SAME halt: same `halted`, same ceiling, same figure.
    A facade that stopped for its own reason at its own moment would still hand
    back a `Halted`, and only the comparison against the reference says which
    ceiling actually fired.
    """
    stops = _stops_where_it_runs_out(spec)

    baseline_script = _calls_a_tool_first()
    reference = _reference(stops, baseline_script)
    baseline = _compared(reference, baseline_script)

    facade_script = _calls_a_tool_first()
    agent = PactAgent.for_spec(
        stops, transport=ReferenceTransport(facade_script), tool_impls=dict(TOOLS)
    )
    result = asyncio.run(agent.run(ASKED))
    got = _compared(result.pact, facade_script)

    assert reference.halted != "final", (
        "this test needs a run that did NOT finish, and this one finished — the "
        "ceiling it leans on has moved"
    )
    assert len(_divergence(baseline, got)) <= EPSILON, (
        f"the facade stopped somewhere else: {_divergence(baseline, got)}"
    )
    assert isinstance(result.output, Halted), (
        f"a run that stopped at {reference.halted} arrived as "
        f"{type(result.output).__name__}, which a caller downstream treats as "
        "an answer"
    )
    assert result.output.halted == reference.halted, result.output
    assert result.output.stopped_by == reference.stopped_by, (
        "the facade named a different ceiling from the one that fired"
    )


def test_a_park_through_the_facade_is_the_park_the_reference_parked_at(
    spec: AgentSpec,
) -> None:
    """A park returned as a value is a person never asked and paid-for work thrown away.

    `refund-desk` writes `when-it-runs-out: ask-a-person`, so a run that hits its
    ceiling does not stop — it waits, with a question for `support-leads` and a
    record that a resume needs. A facade that returned that as an ordinary result
    would let a caller drop it: `.output` would be read, the run would look
    finished, and the wait would be answered by nobody.

    So the park leaves by an exception, and the record must survive the throw
    intact. The `Suspension` on the exception is required to BE the one on the
    run — the same object, never a copy — because two copies of what a run is
    waiting for is two answers to what a resume must accept.
    """
    parks = dataclasses.replace(spec, max_steps=1)

    baseline_script = _calls_a_tool_first()
    reference = _reference(parks, baseline_script)
    baseline = _compared(reference, baseline_script)
    assert reference.halted == "suspended", (
        f"this test needs a run that PARKED and this one halted "
        f"{reference.halted!r} — `when-it-runs-out:` has moved"
    )

    facade_script = _calls_a_tool_first()
    agent = PactAgent.for_spec(
        parks, transport=ReferenceTransport(facade_script), tool_impls=dict(TOOLS)
    )
    with pytest.raises(PactSuspended) as raised:
        asyncio.run(agent.run(ASKED))

    got = _compared(raised.value.result.pact, facade_script)
    assert len(_divergence(baseline, got)) <= EPSILON, (
        f"the facade parked somewhere else: {_divergence(baseline, got)}"
    )
    assert raised.value.parked is raised.value.result.pact.suspension, (
        "the park on the exception is a copy of the one on the run — the two can "
        "come to disagree about what is being waited for"
    )
    assert raised.value.parked.reason == reference.suspension.reason


#: What `support-leads` say to the question `refund-desk` parks with. The park
#: asks for `keep-going` as a yes-or-no, and `Suspension.answer` refuses
#: anything else — so this is the author's own vocabulary, not this file's.
SAID = {"keep-going": "yes"}


@pytest.mark.parametrize("door", ["run", "run_sync"])
def test_the_way_back_into_a_park_lands_where_the_reference_lands(
    spec: AgentSpec, door: str
) -> None:
    """A park nobody can answer is the author's `ask-a-person` collapsed into `stop-and-say-so`.

    `harness.run` takes `resume=` and `answer=`, and for a round `PactAgent.run`
    took neither: the ceiling was reached, the question was carried on
    `RunResult.suspension`, and nothing a caller could type put the answer back.
    That is the author's choice discarded rather than degraded — the run stops
    for good on a document that says to ask somebody.

    The resumed leg is where the exactly-once guarantee lives, and it is a fact
    about the run rather than about the answer: the step taken BEFORE the park
    must appear in the resumed trace without being taken again, so `calls` on the
    resumed leg counts only the calls made after the wait. A facade that dropped
    `resume=` starts a fresh run — same script, same answer, one more model call
    and a tool called a second time, which on this document is a refund issued
    twice.

    `run_sync` as well as `run`, because this SDK's `run_sync` signature is a
    closed list with nowhere to name a park: `PactAgent.run_sync` overrides it
    for that one reason, and a resume reachable only from async code is the same
    dead end as no resume at all for every synchronous caller.
    """
    parks = dataclasses.replace(spec, max_steps=1)

    park_script = _calls_a_tool_first()
    parked = _reference(parks, park_script).suspension
    assert parked is not None, "this test needs a run that parked"

    baseline_script = _calls_a_tool_first()
    baseline = _compared(
        _reference(
            parks, baseline_script, resume=parked, answer=parked.answer(**SAID)
        ),
        baseline_script,
    )

    facade_park_script = _calls_a_tool_first()
    parking = PactAgent.for_spec(
        parks,
        transport=ReferenceTransport(facade_park_script),
        tool_impls=dict(TOOLS),
    )
    with pytest.raises(PactSuspended) as raised:
        asyncio.run(parking.run(ASKED))
    facade_parked = raised.value.parked

    facade_script = _calls_a_tool_first()
    agent = PactAgent.for_spec(
        parks, transport=ReferenceTransport(facade_script), tool_impls=dict(TOOLS)
    )
    how = {"resume": facade_parked, "answer": facade_parked.answer(**SAID)}
    try:
        if door == "run_sync":
            ran = agent.run_sync(ASKED, **how).pact
        else:
            ran = asyncio.run(agent.run(ASKED, **how)).pact
    except PactSuspended as again:
        ran = again.result.pact
    got = _compared(ran, facade_script)

    assert len(_divergence(baseline, got)) <= EPSILON, (
        f"the resumed run through `{door}` diverged from the resumed reference "
        f"on {_divergence(baseline, got)}:\n"
        + json.dumps(
            {
                f: {"reference": baseline[f], "facade": got[f]}
                for f in _divergence(baseline, got)
            },
            indent=2,
            default=str,
        )
    )
    # The park's own step, carried in rather than re-run. Stated separately from
    # the equality above, which would hold just as well if BOTH sides had
    # forgotten the park and started the run again from nothing.
    assert got["trace"][0]["tools"] == [
        {"name": call.name, "args": call.args}
        for call in facade_parked.steps[0].tool_calls
    ], (
        "the resumed run's first step is not the step taken before the park — "
        "the record went in and came out as something else"
    )
    assert len(got["trace"]) > got["calls"], (
        f"the resumed run has {len(got['trace'])} step(s) and made "
        f"{got['calls']} model call(s). More steps than calls is the only "
        "evidence that the pre-park step was carried in; equal means it was "
        "taken again, and on this document that is the tool called twice."
    )


# ───────────────────────────────── the one thing the facade does change


def test_the_only_thing_the_facade_changes_is_the_shape_the_author_declared(
    spec: AgentSpec,
) -> None:
    """A caller left to parse the answer is the divergence PACT exists to remove.

    The facade's `.output` is NOT byte-identical to the reference's, and that is
    the one difference this file certifies rather than forbids: `answers-with:`
    makes `_output_type_for` a structured shape, so handing back the JSON TEXT
    would leave every caller to parse it themselves — and where they parse it and
    how they report a failure is exactly the divergence between two runtimes that
    PACT exists to remove.

    The claim is therefore an equality and not an inequality: the facade's
    `.output` is the reference's output READ, nothing added and nothing lost. And
    the text itself is still there byte-for-byte on `.pact.output`, so the
    comparison every other test in this file makes is made on the same string the
    reference produced.
    """
    baseline_script = _answers_at_once()
    reference = _reference(spec, baseline_script)
    assert reference.halted == "final", reference.halted

    facade_script = _answers_at_once()
    agent = PactAgent.for_spec(
        spec, transport=ReferenceTransport(facade_script), tool_impls=dict(TOOLS)
    )
    result = asyncio.run(agent.run(ASKED))

    assert result.pact.output == reference.output, (
        "the text the run produced is not the text the reference produced"
    )
    assert result.output == json.loads(reference.output), (
        f"the facade's `.output` is {result.output!r}, and the author's "
        "`answers-with:` says it should be the reference's answer read into the "
        "shape they declared — a caller handed the text parses it themselves"
    )


# ───────────────────────────── why this is evidence and not a report row


def test_the_facade_is_not_an_adapter_and_the_report_is_right_not_to_list_it() -> None:
    """A report row for the facade would claim to have measured an adapter that does not exist.

    Every row of `conformance.report()` is a `Transport`: the report constructs
    each target from a `Script` alone and asks it for a `lattice()`, and then
    `harness.run` drives it through `model_call`. `PactAgent` is neither — it is
    a CALLER of `harness.run`, constructed from an `AgentSpec`, and it has no
    seam under the loop to declare a lattice about.

    Adding it to `TARGETS` therefore does not produce a wrong row; it produces no
    report at all, because `declared = {name: cls(Script(…)).lattice() …}` runs
    before the first comparison. The evidence that the facade changes nothing is
    this file, and it has to be, because the report has no shape for it.

    Asserted structurally rather than by name, so the rule survives a target
    being added: what makes something a row is having the two members, and the
    facade has neither.
    """
    for name, cls in TARGETS.items():
        assert callable(getattr(cls, "model_call", None)), (
            f"{name} is a row of the conformance report and has no `model_call` "
            "— the report drives every target through that seam"
        )
        assert callable(getattr(cls, "lattice", None)), (
            f"{name} is a row of the conformance report and declares no lattice "
            "— `declared-before-execution` would be empty for it"
        )

    assert PactAgent not in TARGETS.values(), (
        "`PactAgent` is in the conformance report's targets. It is not a "
        "Transport: the report would fail at `cls(Script(…)).lattice()` before "
        "comparing anything. The evidence that the facade changes nothing is "
        "`tests/test_the_facade_scores_what_the_reference_scores.py`."
    )
    assert not hasattr(PactAgent, "model_call"), (
        "`PactAgent` grew a `model_call` — it is now shaped like a Transport, "
        "and something will list it as one. It is a caller of `harness.run`, not "
        "a seam under it."
    )
    assert not hasattr(PactAgent, "lattice"), (
        "`PactAgent` declares a lattice. A lattice is a statement about what one "
        "MODEL SEAM can do; the facade runs whichever transport it is handed and "
        "would be declaring somebody else's capabilities as its own."
    )
    # The exact construction `report()` performs on every target, which must not
    # accidentally succeed on the facade: a target that constructs and then
    # answers nothing is the silent half of this failure.
    with pytest.raises(Exception):
        PactAgent(Script([Turn(ANSWER)])).lattice()  # type: ignore[arg-type]
