"""Four doors on this SDK say `stream`, and a PACT run has no stream to give them.

`AbstractAgent` offers `run_stream`, `run_stream_sync`, `run_stream_events` and
an `event_stream_handler=` that every one of them feeds. Behind all four,
`PactAgent` runs `harness.run`, whose transport seam is
`model_call(system, history, tools) -> (text, calls)` — one whole model call,
handed back whole. There is no token stream, no partial response, and no node
boundary to hand anybody.

`pact_agent.py`'s own module docstring forbids exactly one answer to that:
*"a refusal with no reason is the same defect as a silent drop, because the
caller's next move depends entirely on why"*. Accept-and-silently-degrade is
that defect twice — the caller is told nothing AND given nothing. So each door
gets one of the two honest answers, and this file pins which:

* `run_stream` — **refuses under its own name.** It hands back a live
  `StreamedRunResult`, and this SDK's own second constructor for one
  (`result.py:445-458`) would let a shim return the finished run wearing a
  stream's clothes. Measured on the worked example, which declares
  `answers-with:`: `stream_text()` on such an object raises `stream_text() can
  only be used with text responses`, a sentence naming nothing about the
  document; on a text agent it yields the whole answer once and calls it a
  delta.
* `run_stream_sync` — **refuses under its own name**, with the synchronous fix.
* `run_stream_events` — **emits the finished run as ONE terminal
  `AgentRunResultEvent`**, and says so in its docstring and on
  `RunResult.unenforced`.
* `event_stream_handler=` — **held, never called, and reported** on
  `RunResult.unenforced`, because it cannot be refused: `run_stream_events`
  passes one into `self.run` itself.

And the word in the other file has to survive all that.
`PydanticAITransport.lattice()` publishes `streaming: emulated`, which the
lattice's own comment defines as *PACT's harness provides it above the
transport*. The reconciliation is that the emulation exists at exactly ONE
granularity — a run that finished, as a single event — so the door that can be
served at that granularity is served, and the two that demand a finer one refuse
and NAME the one that is the emulation. Both refusals quote the word, so the two
files cannot drift apart in silence; the last test here is what fails if they do.

Every assertion below is about what the code DID: which exception type escaped,
how many events came out, whether the tool ran, whether the handler was called,
which sentence the run recorded. The script says the same thing whatever it is
told, so comparing what it said would compare the script.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import RunResult, ToolCall  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.loops import STANDARD, Loop  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.pydantic_ai_transport import (  # noqa: E402
    PydanticAITransport,
)

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"

pydantic_ai = pytest.importorskip("pydantic_ai")

from pydantic_ai.exceptions import UserError  # noqa: E402
from pydantic_ai.run import AgentRunResultEvent  # noqa: E402

#: What a refusal is allowed to BE. Three types rather than one, because which
#: exception a shim raises is a matter of taste and what it says is not — every
#: test below reads the message. `TypeError` is deliberately absent: a method
#: that does not exist at all raises one, and that would let a class pass these
#: tests by deleting the door instead of answering it.
REFUSALS = (NotImplementedError, UserError, ValueError)

#: The prompt every run here is given. A real sentence rather than `"hi"`,
#: because two of these tests refuse before anything runs and a reader has to be
#: able to tell the refusal is not about the prompt.
ASK = "refund order A-1"

#: What a run that answers properly says: the author's three `answers-with:`
#: fields as JSON, which is what the unset mode (`prompted`) asks the model for.
#: It is also the reason `run_stream` cannot honestly return the finished run —
#: an answer of this shape is not a `str`, and `StreamedRunResult.stream_text()`
#: refuses anything that is not.
ANSWERED = json.dumps(
    {"decision": "approved", "reason": "the item arrived faulty", "amount": "40 USD"}
)


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
    """The example over `pact:loop/standard`.

    The document's own `careful` loop is four stages, and every test here is
    about a door rather than about the stages — four turns would prove nothing
    the first turn does not.
    """
    loaded = AgentSpec.from_document(document, "refund-desk", str(EXAMPLE))
    return dataclasses.replace(loaded, loop=Loop.from_library(STANDARD))


def _script() -> Script:
    """One tool call and then the answer.

    A tool call rather than a bare answer, because "the run happened" is the
    claim several tests below make, and a scripted model says the same words
    whether or not the harness ran anything. A tool that RAN is a fact about the
    run that the script cannot fake.
    """
    return Script(
        [
            Turn("Checking the ticket.", (ToolCall("zendesk", {"ticket": "T-1"}),)),
            Turn(ANSWERED),
        ]
    )


def held(spec: AgentSpec, *, ran: "list[str] | None" = None, **how: Any) -> Any:
    """One PACT agent this SDK can hold, with a transport and a tool that records.

    Imported inside the function rather than at module scope so a missing class
    fails each test on its own name instead of collapsing the file into one
    collection error.

    `ran` is where the tool implementations record themselves. It is the only
    honest witness that a run happened: `RunResult.output` is whatever the script
    was told to say, and it says it whether the harness executed one stage or
    none.
    """
    from pact_adapters.pact_agent import PactAgent

    log = ran if ran is not None else []
    return PactAgent.for_spec(
        spec,
        transport=PydanticAITransport(_script()),
        tool_impls={
            "zendesk": lambda args: log.append("zendesk") or "T-1: lamp, broken",
            "payments": lambda args: log.append("payments") or "ok",
        },
        **how,
    )


def _events(agent: Any, **how: Any) -> list[Any]:
    """Everything `run_stream_events` yields, in order, drained to the end."""

    async def drain() -> list[Any]:
        got: list[Any] = []
        async with agent.run_stream_events(ASK, **how) as events:
            async for event in events:
                got.append(event)
        return got

    return asyncio.run(drain())


# ───────────────────────────────────── the two doors that hand out a handle


def test_run_stream_refuses_under_its_own_name_and_not_under_somebody_elses(
    spec: AgentSpec,
) -> None:
    """A caller who typed `run_stream` was answered about a method they never called.

    `AbstractAgent.run_stream` opens `self.iter()`, so a class that refuses
    `iter()` alone refuses this door too — with `iter()`'s sentence. Measured
    before this test existed: `agent.run_stream(ASK)` raised *"`iter()` is not
    something a PACT agent can offer. It hands back an `AgentRun` over
    `_agent_graph`'s node stream…"*, which names a method the caller never
    typed, a class they never asked for, and nothing about streaming. The next
    move a streaming caller has is `run_stream_events` — the one door that does
    work — and that sentence does not contain it.

    So the door is refused by name, with the seam that makes streaming
    impossible and the door that is possible both named in the message.
    """
    agent = held(spec)

    async def stream() -> None:
        async with agent.run_stream(ASK):
            pass  # pragma: no cover - reaching the body is the failure

    with pytest.raises(REFUSALS) as trouble:
        asyncio.run(stream())

    said = str(trouble.value)
    assert said.strip(), "a bare refusal carries no message at all"
    assert "`run_stream()`" in said, (
        "the caller typed `run_stream` and the refusal named something else"
    )
    assert "iter()" not in said, (
        "this is `iter()`'s sentence reaching a caller who never called `iter()`"
    )
    assert "model_call(system, history, tools)" in said, (
        "name the seam, which is WHY there is nothing partial to stream"
    )
    assert "run_stream_events" in said, "name the streaming door that does work"


def test_run_stream_refuses_when_it_is_called_and_not_only_when_it_is_entered(
    spec: AgentSpec,
) -> None:
    """A context manager that fails on entry is still an object somebody can hold.

    `AbstractAgent.run_stream` is an `@asynccontextmanager`, so a refusal raised
    inside its body does not happen until `__aenter__` — and until then the
    caller has a perfectly ordinary-looking object they can store on `self`, put
    in a list of pending streams, or pass to a helper. The traceback then names
    whoever entered it rather than whoever asked to stream, which on an async
    fan-out is a different function in a different file.

    Refusing at the call puts the failure on the line the caller typed the word.
    """
    with pytest.raises(REFUSALS) as trouble:
        held(spec).run_stream(ASK)

    assert "`run_stream()`" in str(trouble.value)


def test_run_stream_sync_refuses_under_its_own_name_and_names_the_synchronous_way(
    spec: AgentSpec,
) -> None:
    """The sync door's fix is not the async door's fix, and a shared sentence sends it.

    `AbstractAgent.run_stream_sync` wraps `self.run_stream`, so a class that
    answers only the async door answers this one with the async door's name and
    the async door's advice — and `run_stream_events()` is an async context
    manager, which is precisely what a caller standing in synchronous code
    cannot use. The line that caller needs is `run_sync()`.

    The refusal is also raised where they typed it: `StreamedRunResultSync`
    enters the stream inside its own `__init__` (`result.py:776-777`), so a
    caller who wrote `with agent.run_stream_sync(...) as r:` and a caller who
    wrote `r = agent.run_stream_sync(...)` must both be stopped.
    """
    agent = held(spec)

    with pytest.raises(REFUSALS) as trouble:
        with agent.run_stream_sync(ASK):
            pass  # pragma: no cover - reaching the body is the failure

    said = str(trouble.value)
    assert "`run_stream_sync()`" in said, (
        "the sync caller was refused under the async door's name"
    )
    assert "iter()" not in said, "the old sentence about a third method is back"
    assert "run_sync()" in said, (
        "a caller in synchronous code was sent to an async context manager"
    )

    # And with no `with` at all: the SDK enters the stream in the constructor,
    # so a caller who never opens a block still reaches the refusal.
    with pytest.raises(REFUSALS):
        held(spec).run_stream_sync(ASK)


# ──────────────────────────────── the door that is answered, not refused


def test_the_event_door_yields_the_finished_run_and_never_an_empty_stream(
    spec: AgentSpec,
) -> None:
    """A stream that yields nothing is a run that never happened, and this one did.

    `run_stream_events` cannot be refused without breaking the one streaming
    shape PACT can honestly serve, and it must not be answered with silence
    either: an iterator that ends immediately is byte-identical, from the
    consumer's side, to an agent that did nothing at all. Here the agent ran the
    author's `loop:`, called the author's tool and reached `final` — and the
    consumer has to be able to see that.

    Exactly one event, because the count is the claim. Two would mean somebody
    started synthesising boundaries the document does not describe; zero would
    mean the door reports nothing about a run that spent money.
    """
    ran: list[str] = []
    got = _events(held(spec, ran=ran))

    assert ran == ["zendesk"], (
        f"the author's tool did not run, so this stream is reporting nothing: {ran}"
    )
    assert len(got) == 1, (
        f"expected one terminal event and got {[type(e).__name__ for e in got]}"
    )
    assert isinstance(got[0], AgentRunResultEvent), (
        f"the one event is not the SDK's terminal event but a {type(got[0]).__name__}"
    )


def test_the_terminal_event_carries_the_whole_pact_run_and_not_a_husk(
    spec: AgentSpec,
) -> None:
    """A terminal event with an empty result is silence wearing an event's shape.

    The point of answering this door rather than refusing it is that a consumer
    written against `run_stream_events` gets the run — every stage it walked,
    every tool it called, the meter, and the honesty channels `AgentRunResult`
    has no field for. So the event's result must carry `.pact`, and that
    `RunResult` must be the same run `run_sync` performs from the same script:
    if the streaming door quietly took a different path, `trace()` is where it
    shows.
    """
    got = _events(held(spec))
    streamed = got[-1].result

    assert isinstance(streamed, pydantic_ai.AgentRunResult)
    assert isinstance(streamed.pact, RunResult), (
        "the terminal event carries no PACT run, so the trace, the meter and "
        "every honesty channel were dropped on the way through this door"
    )
    assert streamed.pact.halted == "final"

    directly = held(spec).run_sync(ASK)
    assert streamed.pact.trace() == directly.pact.trace(), (
        "the event door walked a different loop than the plain door: "
        f"{streamed.pact.trace()} vs {directly.pact.trace()}"
    )
    # The tool call the script made is IN that trace, so the equality above is
    # comparing two runs that did something rather than two empty lists.
    assert [c["name"] for s in streamed.pact.trace() for c in s["tools"]] == ["zendesk"]


def test_a_handler_this_door_passes_is_never_called_and_the_run_says_so(
    spec: AgentSpec,
) -> None:
    """A held handler and a run nothing happened in look identical from outside.

    `run_stream_events` passes an `event_stream_handler=` into `self.run` — that
    is how the inherited method collects events — so the argument cannot be
    refused, and PACT cannot call it: there is no partial response to hand it.
    What is left is saying so, on the channel whose own line is *a rule the
    author wrote that this run could not decide*.

    The sentence has to carry the whole answer, not half of it. *"Nothing was
    streamed to it"* alone leaves a caller believing the run produced nothing;
    the second half — the finished run still arrives, once, as the terminal
    `AgentRunResultEvent` — is what tells them where their answer is. Both halves
    are asserted because the first shipped without the second.
    """
    called: list[Any] = []

    async def watch(ctx: Any, stream: Any) -> None:
        called.append(ctx)  # pragma: no cover - being called at all is the failure

    got = _events(held(spec, event_stream_handler=watch))

    assert called == [], (
        "a handler was called, so something invented partial-response boundaries "
        "this document does not describe"
    )
    named = [s for s in got[-1].result.pact.unenforced if "event_stream_handler" in s]
    assert named, (
        f"a handler was held and never called and nothing said so: "
        f"{got[-1].result.pact.unenforced}"
    )
    assert "run_stream_events" in named[0] and "terminal" in named[0], (
        f"the caller is told nothing streamed and not where the answer went: "
        f"{named[0]}"
    )


def test_a_run_that_cannot_start_reaches_the_consumer_instead_of_ending_the_stream(
    spec: AgentSpec,
) -> None:
    """A refusal swallowed by a stream is the emptiest lie of all.

    `for_spec(spec)` with no transport is the inspection door, and running such
    an agent refuses by name. Through `run_stream_events` that refusal is raised
    inside a background task, and a door that let the task's exception close the
    stream quietly would hand the consumer zero events and no error — a run that
    was never even attempted, indistinguishable from one that produced nothing.

    Asserted on the exception TYPE reaching the consumer and on the sentence it
    carries, because "the loop ended" is what both outcomes look like.
    """
    from pact_adapters.pact_agent import PactAgent

    unbound = PactAgent.for_spec(spec)

    with pytest.raises(REFUSALS) as trouble:
        _events(unbound)

    assert "transport=" in str(trouble.value), (
        "the consumer got an exception that does not say how to fix it"
    )


def test_an_agent_the_author_left_unnamed_is_not_renamed_self_by_this_door(
    spec: AgentSpec,
) -> None:
    """Forwarding a method that reads the caller's frame renames the agent `self`.

    `AbstractAgent.run_stream_events` calls `self._infer_name(inspect
    .currentframe())`, which walks ONE frame outward and takes whatever local
    variable the agent is bound to. Overriding the method to fix its docstring
    inserts a frame — and the only local holding the agent there is `self`, so
    an agent whose author wrote no `name:` turns up in every trace, log line and
    span of the surrounding system called `self`.

    The document's own agent is unaffected because it HAS a name; this is the
    one the author left blank, which is exactly the case the SDK's inference
    exists for.
    """
    from pact_adapters.pact_agent import PactAgent

    anonymous = dataclasses.replace(spec, name="", key="")
    surname = PactAgent.for_spec(
        anonymous, transport=PydanticAITransport(_script()), tool_impls={}
    )
    assert surname.name is None, "this spec still names the agent, so nothing is inferred"

    # Called from THIS frame and not through `_events`, because the frame walked
    # is the whole subject: a helper in between would name the agent after the
    # helper's own local and the test would measure nothing about the door.
    opened = surname.run_stream_events(ASK)

    async def drained() -> None:
        async with opened as events:
            async for _ in events:
                pass

    asyncio.run(drained())

    assert surname.name == "surname", (
        f"the agent was named after this method's own frame, not the caller's: "
        f"{surname.name!r}"
    )


def test_a_caller_who_turned_naming_off_still_has_it_off_after_this_door(
    spec: AgentSpec,
) -> None:
    """Popping `infer_name` and not passing it on is inference turned back on.

    The test above measures the DEFAULT path, and on that path handling
    `infer_name` here and forwarding it as well are indistinguishable: this
    method infers the name first, so the inherited one finds a name already set
    and does nothing. The two come apart on the path a caller chose — `run_
    stream_events(..., infer_name=False)` on an agent whose author wrote no
    `name:`, which is a host that names its agents itself and does not want a
    local variable deciding.

    `how.pop("infer_name", True)` consumes the caller's `False`, so forwarding
    `**how` without re-stating it hands the inherited method its own default of
    `True`. That method then calls `self._infer_name(inspect.currentframe())`
    one frame below this override, where the only local holding the agent is
    `self` — so the caller who explicitly asked for no naming gets the worst
    name there is, and gets it from the argument they used to prevent exactly
    that.

    Nothing anywhere reports it: the run is identical, the events are identical,
    and the agent is simply called `self` in every trace and span from then on.
    """
    from pact_adapters.pact_agent import PactAgent

    anonymous = dataclasses.replace(spec, name="", key="")
    unnamed = PactAgent.for_spec(
        anonymous, transport=PydanticAITransport(_script()), tool_impls={}
    )
    assert unnamed.name is None, "this spec still names the agent"

    opened = unnamed.run_stream_events(ASK, infer_name=False)

    async def drained() -> None:
        async with opened as events:
            async for _ in events:
                pass

    asyncio.run(drained())

    assert unnamed.name != "self", (
        "`infer_name=False` was consumed here and not passed on, so the "
        "inherited door inferred a name anyway and took it from this override's "
        "own frame — the agent is now called `self` everywhere"
    )
    assert unnamed.name is None, (
        f"the caller asked for no name inference and the agent came back named "
        f"{unnamed.name!r}"
    )


# ─────────────────────────────── the word the other file publishes


def test_every_door_that_says_stream_is_answered_here_and_none_is_left_inherited(
    spec: AgentSpec,
) -> None:
    """An inherited streaming door ships this SDK's promise as if PACT kept it.

    `AbstractAgent.run_stream_events`'s docstring is a worked example printing
    `PartStartEvent`, `PartDeltaEvent` and `PartEndEvent`. Inherited unchanged
    onto a `PactAgent`, that is what `help(agent.run_stream_events)`, an IDE
    tooltip and every doc generator show a caller — a per-token stream this class
    cannot produce. A surface is where a shim can lie, and a docstring carried by
    this SDK's own tooling is a surface.

    So each of the three methods answers with its own words, and each says which
    of the two honest answers it gives.
    """
    from pact_adapters.pact_agent import PactAgent

    for door in ("run_stream", "run_stream_sync", "run_stream_events"):
        assert door in PactAgent.__dict__, (
            f"`{door}` is inherited, so this class ships the SDK's promise unchanged"
        )

    from pydantic_ai.agent.abstract import AbstractAgent

    events_doc = PactAgent.run_stream_events.__doc__ or ""
    assert events_doc != AbstractAgent.run_stream_events.__doc__, (
        "this door still carries the SDK's own docstring, which promises a "
        "per-token stream this class cannot produce"
    )
    # The SDK's rendered example, which is the part a reader believes because it
    # shows output rather than describing it. A `PactAgent` that reproduced it
    # would be showing events no run here emits.
    assert "PartStartEvent(index=0" not in events_doc, (
        "this door still advertises per-token events it cannot produce"
    )
    assert "terminal" in events_doc and "AgentRunResultEvent" in events_doc, (
        "the door that emits one event does not say that it emits one event"
    )
    for door in ("run_stream", "run_stream_sync"):
        said = getattr(PactAgent, door).__doc__ or ""
        assert "Refused" in said, f"`{door}` does not say that it refuses"


def test_the_word_the_transport_publishes_is_the_one_this_facade_behaves_like(
    spec: AgentSpec,
) -> None:
    """Two files describing one capability drift apart, and only the word gets read.

    `PydanticAITransport.lattice()` publishes `streaming: emulated`, and the
    lattice's own comment defines that as *PACT's harness provides it above the
    transport* — a claim a conformance report prints and a host reads to decide
    whether this adapter can serve a streaming UI. `PactAgent` is where that
    claim is either kept or contradicted, and it is in a different file.

    `emulated` survives here for one reason and it must be a true one: the
    harness provides streaming at exactly one granularity — the finished run, as
    one terminal event — so `run_stream_events` really does deliver, and the two
    doors that demand a finer granularity refuse rather than pretend. Had every
    door refused, `emulated` would be `unsupported` and the report would be
    false.

    So the word is read off the transport and required to appear in both
    refusals. Change it there and this fails here; delete the working door and
    this fails too.
    """
    word = PydanticAITransport(_script()).lattice()["streaming"]
    assert word == "emulated", (
        f"the transport now publishes `streaming: {word}`, which this facade "
        f"does not behave like: one door delivers the finished run as a single "
        f"terminal event and two refuse"
    )

    # The claim is kept: the emulated door really does deliver the run.
    got = _events(held(spec))
    assert len(got) == 1 and got[-1].result.pact.halted == "final", (
        f"`streaming: {word}` is published and no door provides it: {got}"
    )

    # And the two refusals quote the same word, so neither file can be changed
    # without the other's sentence going stale in a test rather than in a host's
    # capability report.
    for door, call in (
        ("run_stream", lambda a: a.run_stream(ASK)),
        ("run_stream_sync", lambda a: a.run_stream_sync(ASK)),
    ):
        with pytest.raises(REFUSALS) as trouble:
            call(held(spec))
        said = str(trouble.value)
        assert f"streaming: {word}" in said, (
            f"`{door}` refuses without naming the word the transport publishes, "
            f"so the two files can disagree and nothing says so"
        )
        assert "single terminal event" in said, (
            f"`{door}` names the word but not what the emulation actually is"
        )
