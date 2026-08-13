"""A tool that fails is a RESULT; a tool that is cancelled ends the run.

`harness._call_tool` (harness.py:2516-2541) is the whole of PACT's tool-error
policy, and it is four lines with two different answers in them:

* **Anything a tool raises becomes the string `error: <name> could not run: <e>`
  and the run carries on.** Its own docstring quotes `delegation.one()` for the
  rule — *"a child's failure is data, not a crash"* — and names what the missing
  guard cost: a two-step run where `zendesk` had already succeeded and
  `payments` timed out produced no `RunResult` at all, so the call that really
  happened was unrecoverable and there was nothing to resume from.
* **`asyncio.CancelledError` is re-raised.** A cancelled run is not a failed
  tool, and swallowing it would make a stopped run look like one that carried
  on.

This SDK's own loop answers both differently. A tool that raises inside
`_agent_graph` becomes a `ToolFailed` / `ToolRetryError`, which SPENDS one of the
agent's retries and asks the model again — so the same document run through
Pydantic AI's loop bills an extra model call PACT never makes, and exhausts a
budget PACT does not have. `PactAgent` must keep PACT's answer, and it keeps it
by not owning this decision at all: `run` awaits `harness.run`, and `_call_tool`
is inside that await.

**So this file is mostly a guard against a future edit, and every test is
written to survive being right today.** A `try/except` added around
`await harness.run(...)` — to attach a nicer message, to translate into an
`AgentRunError`, to return a `Halted` instead of raising — is the edit these
tests exist to catch, and each of the three doors into this class is opened
separately because `run_sync` has a hand-written branch that the inherited one
does not use.

**Parity with `harness.run` is asserted and is not, on its own, worth
anything.** Both arms of every comparison below run the same `_call_tool`, so
they agree by construction — the burn `test_the_golden_set_runs_everywhere.py`
lines 114-130 records applies here in full. So every parity assertion is paired
with one that names the fact independently: the LITERAL sentence a failed tool
leaves, the number of times the model was asked, which tool ran and which did
not, and the exception OBJECT that escaped.
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

from pact_adapters import harness  # noqa: E402
from pact_adapters.harness import RunResult, ToolCall  # noqa: E402
from pact_adapters.ir import AgentSpec, ToolSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.suspension import Resumption  # noqa: E402
from pact_adapters.transports.pydantic_ai_transport import (  # noqa: E402
    PydanticAITransport,
)

pydantic_ai = pytest.importorskip("pydantic_ai")

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"

ASKED = "Can I get a refund?"

#: The two tool names, written once, because the sentence a failed tool leaves
#: quotes the name and an assertion that spelled it a second time would go on
#: passing after the tool was renamed.
LOOKS_UP = "zendesk"
SPENDS = "payments"

#: What the tool's own exception says. A sentence a person would recognise, not
#: `"boom"`: the whole claim is that the model is shown the REAL reason, and a
#: placeholder would still match a `_call_tool` that dropped `{e}` for a fixed
#: string.
WHY_IT_FAILED = "payments.example.com timed out after 30s"

#: What `payments` says when it works — asserted, because the step AFTER the
#: failure is where "the run continued" is visible as something that happened
#: rather than as something the script said.
REFUNDED = "refunded"

SPEC = AgentSpec(
    name="Refund Desk",
    description="Decides refunds",
    instructions="Decide refunds.",
    tools=(
        ToolSpec(LOOKS_UP, "read the ticket"),
        ToolSpec(SPENDS, "issue a refund"),
    ),
)


class Tool:
    """One tool implementation that RECORDS every call before doing anything.

    The record is the point. A scripted model calls what the script says
    whatever happens, so "the run continued" and "the run stopped" produce the
    same transcript up to the point they differ — and the only thing that tells
    them apart is whether the tool on the far side of the failure was ever
    entered. `calls` is that fact.
    """

    def __init__(self, *, raises: BaseException | None = None, returns: str = "") -> None:
        self.calls: list[dict[str, Any]] = []
        self._raises = raises
        self._returns = returns

    def __call__(self, args: Any) -> str:
        self.calls.append(dict(args or {}))
        if self._raises is not None:
            raise self._raises
        return self._returns


def three_turns() -> Script:
    """Look the ticket up, then spend the money, then answer.

    Three steps so that the failure is in the MIDDLE of a run rather than at the
    end of one: a `_call_tool` that let the exception through would end the run
    at step 0, and a run that ends at step 0 with a final answer is
    indistinguishable from a run that finished if the script only had one step.
    """
    return Script([
        Turn("Checking the ticket.", (ToolCall(LOOKS_UP, {"ticket": "T-1"}),)),
        Turn("Issuing the refund.", (ToolCall(SPENDS, {"amount": "40"}),)),
        Turn("Approved: the item arrived damaged within 30 days."),
    ])


def failed(name: str, because: str) -> str:
    """The sentence `_call_tool` leaves in the trace, spelled out here on purpose.

    Written as a literal rather than imported from `harness`, because importing
    the format string would make every assertion below agree with whatever
    `_call_tool` was last edited to say. This is the cross-runtime wording — the
    TypeScript port has to produce it too — so it is pinned where a change to it
    is visible as a test failure and not as a silently updated expectation.
    """
    return f"error: {name!r} could not run: {because}"


def facade(script: Script, tools: dict[str, Any], *, spec: AgentSpec = SPEC) -> Any:
    """The run entered through `PactAgent.run_sync`, the door callers hold."""
    from pact_adapters.pact_agent import PactAgent

    return PactAgent.for_spec(spec, script=script, tool_impls=tools).run_sync(ASKED)


def bare(script: Script, tools: dict[str, Any], *, spec: AgentSpec = SPEC) -> RunResult:
    """The same run as `harness.run` performs it, with nothing wrapped round it."""
    return asyncio.run(harness.run(spec, PydanticAITransport(script), ASKED, tools))


# ───────────────────────────────────────────────── a failure is data (part a)


def test_a_tool_that_raises_leaves_the_error_where_the_model_can_read_it() -> None:
    """A dropped failure is a call that happened with nothing anywhere saying so.

    If `PactAgent` let a tool's exception out — or caught it and returned a
    `Halted`, or attached its own wording — the run would have no `RunResult`,
    no trace and no suspension, and the `zendesk` lookup that DID happen would be
    unrecoverable. `_call_tool` instead hands the model the same shape it already
    gets for a tool that does not exist, so the model can read `error: …` and
    decide what to do.

    The literal sentence is asserted, not just its presence: `{e}` and not
    `{e!r}`, the tool's own name, and the exception's own words. A `_call_tool`
    that reported `error: a tool failed` would satisfy every parity test in this
    repository and tell the model nothing it could act on.
    """
    looks_up = Tool(raises=ValueError(WHY_IT_FAILED))
    ours = facade(three_turns(), {LOOKS_UP: looks_up, SPENDS: Tool(returns=REFUNDED)})

    assert ours.pact.halted == "final", (
        f"a failed tool ended the run as {ours.pact.halted!r}; a child's failure "
        f"is data, not a halt"
    )
    assert ours.pact.suspension is None, "a failed tool parked the run"
    assert ours.pact.trace()[0]["results"] == [failed(LOOKS_UP, WHY_IT_FAILED)], (
        json.dumps(ours.pact.trace()[0], indent=2)
    )
    # The tool really was entered, so the string above is a record of a call that
    # was made and failed — not of one the harness declined to make.
    assert looks_up.calls == [{"ticket": "T-1"}], (
        f"the failing tool was called {looks_up.calls}; an error string with no "
        f"call behind it is a lookup that silently never happened"
    )


def test_the_step_after_a_failed_tool_still_runs_and_costs_no_retry() -> None:
    """A retry spent on a failed tool is a model call the author never authorised.

    This SDK's loop turns a raising tool into `ToolRetryError`, decrements the
    tool-retry budget and asks the model AGAIN with the failure attached. PACT
    does not: one step, one model call, and the failure travels forward as an
    ordinary result. A facade that acquired the retry would bill an extra call
    per failure and reach `steps-at-most` somewhere the author cannot predict.

    So the count is asserted against the steps rather than against a number typed
    here, and the tool on the far side of the failure is asserted to have RUN —
    which is the whole of "the run continued", said as something that happened.
    """
    script = three_turns()
    spends = Tool(returns=REFUNDED)
    ours = facade(script, {LOOKS_UP: Tool(raises=ValueError(WHY_IT_FAILED)), SPENDS: spends})

    assert len(ours.pact.steps) == 3, ours.pact.trace()
    assert script.calls == len(ours.pact.steps), (
        f"the model was asked {script.calls} times across {len(ours.pact.steps)} "
        f"steps — a failed tool bought somebody an extra turn"
    )
    assert spends.calls == [{"amount": "40"}], (
        f"the tool after the failure was called {spends.calls}; the run did not "
        f"carry on past the failure"
    )
    assert ours.pact.trace()[1]["results"] == [REFUNDED]
    # A failed call is still a call: it is counted against `tool-calls-at-most`
    # and against the usage this SDK reports, because a tool that fails has still
    # been reached and a ceiling that only counts successes cannot stop a loop
    # that only fails.
    assert ours.pact.used is not None and ours.pact.used.tool_calls == 2
    assert ours.usage.tool_calls == 2, ours.usage


def test_a_failed_tool_does_not_arrive_shaped_like_a_halted_run() -> None:
    """`Halted` means the run stopped; a failed tool is a run that did not.

    `_answer_of` returns a `Halted` for every outcome that is not `final`, and it
    is the type a caller checks before believing `.output`. A facade that decided
    a failed tool was a halt would make an ordinary timeout — the most common
    thing an MCP tool does (D14) — look identical to a ceiling being hit, and the
    caller's retry logic would fire on a run that answered perfectly well.
    """
    from pact_adapters.pact_agent import Halted

    ours = facade(
        three_turns(),
        {LOOKS_UP: Tool(raises=ValueError(WHY_IT_FAILED)), SPENDS: Tool(returns=REFUNDED)},
    )

    assert not isinstance(ours.output, Halted), ours.output
    assert ours.pact.stopped_by is None, ours.pact.stopped_by


# ──────────────────────────────────── a cancellation is not data (part b)


def test_a_cancelled_tool_stops_the_facade_instead_of_becoming_an_error_string() -> None:
    """A swallowed cancellation is a stopped run reporting itself as finished.

    `_call_tool` re-raises `asyncio.CancelledError` before the blanket handler
    ever sees it, and the reason is in its docstring: a cancelled run is not a
    failed tool. If `PactAgent` turned it into `error: 'zendesk' could not run:`
    the run would go on to spend the money at the next step — the deployment that
    cancelled it having no way to know it was ignored — and would hand back an
    `AgentRunResult` describing a refund nobody authorised.

    The exception OBJECT is asserted, not just its type: `run_until_complete`
    puts the coroutine on a task, and a task that re-raised a NEW
    `CancelledError` would lose whatever the canceller attached to it.
    """
    stopping = asyncio.CancelledError()
    looks_up, spends = Tool(raises=stopping), Tool(returns=REFUNDED)
    script = three_turns()

    with pytest.raises(asyncio.CancelledError) as stopped:
        facade(script, {LOOKS_UP: looks_up, SPENDS: spends})

    assert stopped.value is stopping, (
        f"a different CancelledError came out ({stopped.value!r}); something "
        f"between the tool and the caller re-raised its own"
    )
    assert type(stopped.value) is asyncio.CancelledError
    # The run STOPPED, and that is a fact about what ran rather than about what
    # was raised: the tool that spends the money was never entered, and the model
    # was never asked a second time.
    assert looks_up.calls == [{"ticket": "T-1"}]
    assert spends.calls == [], (
        f"the run carried on past a cancellation and called {SPENDS} "
        f"{spends.calls} — the cancellation was treated as a failed tool"
    )
    assert script.calls == 1, (
        f"the model was asked {script.calls} times after the run was cancelled"
    )


def test_a_cancellation_is_not_translated_into_this_sdks_own_failure() -> None:
    """A translated cancellation is caught by `except AgentRunError` and ignored.

    Everything this SDK raises for a tool that went wrong descends from
    `AgentRunError`, and callers written against it catch exactly that. PACT's
    cancellation must not land there: `asyncio.CancelledError` is a
    `BaseException` precisely so that `except Exception` — the shape of every
    retry wrapper ever written — does not swallow it. A `PactAgent` that wrapped
    it in `ToolFailed`, `ToolRetryError` or `UnexpectedModelBehavior` would put a
    stopped run inside the one handler that is guaranteed to keep going.
    """
    from pydantic_ai.exceptions import AgentRunError, ToolFailed, ToolRetryError

    with pytest.raises(BaseException) as stopped:
        facade(
            three_turns(),
            {LOOKS_UP: Tool(raises=asyncio.CancelledError()), SPENDS: Tool(returns=REFUNDED)},
        )

    raised = stopped.value
    assert isinstance(raised, asyncio.CancelledError)
    assert not isinstance(raised, Exception), (
        f"{type(raised).__name__} is an ordinary Exception, so every "
        f"`except Exception` between here and the canceller swallows the stop"
    )
    for wrapper in (AgentRunError, ToolFailed, ToolRetryError):
        assert not isinstance(raised, wrapper), (
            f"the cancellation arrived as a {wrapper.__name__}, which callers "
            f"catch and carry on from"
        )


def test_both_doors_and_the_resume_door_all_re_raise_the_cancellation() -> None:
    """`run_sync` has a hand-written branch, and a branch is a place to differ.

    `PactAgent.run_sync` forwards to the inherited method when nothing is parked
    and calls `run_until_complete(self.run(...))` itself when a `resume=`/
    `answer=` is in hand. Those are two different paths onto the event loop and
    only one of them is this file's default. A cancellation that escaped one and
    not the other would mean a run resumed after a park could be cancelled and
    keep going — which is exactly the run that has already spent money once.
    """
    from pact_adapters.pact_agent import PactAgent

    doors: dict[str, Any] = {
        "run_sync": lambda agent: agent.run_sync(ASKED),
        "run": lambda agent: asyncio.run(agent.run(ASKED)),
        # `answer=` with nothing parked is refused by nothing and reaches
        # `harness.run` as an answer to no wait; it is passed here only because
        # it is what selects `run_sync`'s other branch.
        "run_sync(answer=)": lambda agent: agent.run_sync(
            ASKED, answer=Resumption("no wait is keyed to this")
        ),
    }
    for door, enter in doors.items():
        stopping = asyncio.CancelledError()
        spends = Tool(returns=REFUNDED)
        agent = PactAgent.for_spec(
            SPEC,
            script=three_turns(),
            tool_impls={LOOKS_UP: Tool(raises=stopping), SPENDS: spends},
        )
        with pytest.raises(asyncio.CancelledError) as stopped:
            enter(agent)
        assert stopped.value is stopping, f"{door} raised its own {stopped.value!r}"
        assert spends.calls == [], f"{door} carried on past the cancellation"


def test_a_tool_that_stops_the_process_is_not_data_either() -> None:
    """`except Exception` and not `except BaseException`, and the difference is Ctrl-C.

    A `KeyboardInterrupt` or a `SystemExit` raised inside a tool is the operator
    or the runtime ending this process, not the tool reporting a problem.
    `_call_tool` catches `Exception`, so both travel out untouched. Widened to
    `BaseException` — the obvious-looking tidy-up, given the comment beside it
    says *"the point is that nothing escapes"* — a Ctrl-C during a refund would
    become `error: 'zendesk' could not run:` and the run would go on to call
    `payments`, which is a process that cannot be stopped issuing money while
    somebody holds the key down.
    """
    interrupting = KeyboardInterrupt("the operator pressed Ctrl-C")
    spends = Tool(returns=REFUNDED)

    with pytest.raises(KeyboardInterrupt) as stopped:
        facade(three_turns(), {LOOKS_UP: Tool(raises=interrupting), SPENDS: spends})

    assert stopped.value is interrupting
    assert spends.calls == [], (
        f"the run called {SPENDS} after a KeyboardInterrupt: {spends.calls}"
    )


def test_only_the_exception_the_tool_raised_decides_which_of_the_two_happens() -> None:
    """One tool, one script, one facade — and two outcomes, on the exception alone.

    Asserted together because each half alone is satisfiable by the wrong thing:
    a facade that re-raised everything passes the cancellation tests, a facade
    that swallowed everything passes the failure tests, and only the pair rules
    out both. Nothing else differs between these two runs — same spec, same
    turns, same tool names, same arguments.
    """
    carried_on = facade(
        three_turns(),
        {LOOKS_UP: Tool(raises=ValueError(WHY_IT_FAILED)), SPENDS: Tool(returns=REFUNDED)},
    )
    assert carried_on.pact.trace()[0]["results"] == [failed(LOOKS_UP, WHY_IT_FAILED)]
    assert len(carried_on.pact.steps) == 3

    with pytest.raises(asyncio.CancelledError):
        facade(
            three_turns(),
            {LOOKS_UP: Tool(raises=asyncio.CancelledError()), SPENDS: Tool(returns=REFUNDED)},
        )


# ──────────────────────────────── the words are the harness's own (part c)


def test_the_words_a_failed_tool_leaves_are_the_ones_harness_run_writes() -> None:
    """Two spellings of one failure is one runtime the TypeScript port cannot match.

    The sentence a failed tool leaves goes into the model's history and is read
    back on the next turn, so it is part of the trace two runtimes are compared
    on — `RunResult.trace()` carries `results` verbatim. A facade that improved
    the wording on the way out (`Tool 'zendesk' failed: …`) would make every
    portability comparison in this repository fail against a run that behaved
    identically, and would do it for the friendliest possible reason.

    The parity assertion below is true by construction — both arms call the same
    `_call_tool` — so the literal is checked FIRST on the harness arm. Two runs
    agreeing on `error: a tool failed` would satisfy the equality and pin
    nothing.
    """
    theirs = bare(
        three_turns(),
        {LOOKS_UP: Tool(raises=ValueError(WHY_IT_FAILED)), SPENDS: Tool(returns=REFUNDED)},
    )
    ours = facade(
        three_turns(),
        {LOOKS_UP: Tool(raises=ValueError(WHY_IT_FAILED)), SPENDS: Tool(returns=REFUNDED)},
    )

    assert theirs.trace()[0]["results"] == [failed(LOOKS_UP, WHY_IT_FAILED)], (
        json.dumps(theirs.trace(), indent=2)
    )
    assert ours.pact.trace() == theirs.trace(), json.dumps(
        {"facade": ours.pact.trace(), "harness": theirs.trace()}, indent=2
    )
    assert ours.pact.halted == theirs.halted
    assert ours.pact.output == theirs.output


def test_a_cancelled_tool_ends_both_arms_the_same_way() -> None:
    """A facade that survives what `harness.run` cannot is a second policy.

    `harness.run` has no `RunResult` to hand back for a cancelled run and does
    not invent one. The facade must be equally empty-handed: anything it returned
    here would be a record PACT itself does not have, composed on the way out of
    a run that was stopped.
    """
    stopping = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError) as theirs:
        bare(three_turns(), {LOOKS_UP: Tool(raises=stopping), SPENDS: Tool(returns=REFUNDED)})
    with pytest.raises(asyncio.CancelledError) as ours:
        facade(three_turns(), {LOOKS_UP: Tool(raises=stopping), SPENDS: Tool(returns=REFUNDED)})

    assert theirs.value is stopping and ours.value is stopping
    assert type(ours.value) is type(theirs.value)


# ──────────────────────────────────────────── the same, on an authored document


@pytest.fixture(scope="module")
def refund_desk() -> AgentSpec:
    """`examples/refund-desk`, loaded by the real Rust loader (invariant P-1).

    The synthetic spec above carries no interceptors, no gate, no stages and no
    ceilings, and every one of those sits between the model's tool call and
    `_call_tool`. This arm is the one that says a failure is still data once a
    real document's chain, gate and `loop: careful` are in the way.
    """
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(PACT_BIN), "show", str(EXAMPLE)], capture_output=True, text=True, check=True
    )
    return AgentSpec.from_document(json.loads(out.stdout), "refund-desk", str(EXAMPLE))


def careful_turns() -> Script:
    """One lookup, then one plain answer per remaining stage of `loop: careful`."""
    return Script([
        Turn("Checking the ticket.", (ToolCall(LOOKS_UP, {"ticket": "T-1"}),)),
        Turn("The ticket says the lamp arrived broken 6 days ago."),
        Turn("Rule 2 applies: faulty on arrival, and 6 days is inside the window."),
        Turn("Approved: the item arrived damaged within 30 days."),
    ])


def test_an_authored_document_treats_a_failed_tool_as_data_through_the_facade(
    refund_desk: AgentSpec,
) -> None:
    """The worked example is where a real chain sits between the call and the tool.

    `refund-desk` runs `loop: careful`, an interceptor chain and an approval
    gate, and each of them can decide a call never happens. None of them may turn
    a call that DID happen and failed into a stopped run: the customer would be
    told nothing, the ticket lookup would be lost, and the three stages the
    author wrote would never reach the one that replies.
    """
    looks_up = Tool(raises=ValueError(WHY_IT_FAILED))
    theirs = bare(
        careful_turns(),
        {LOOKS_UP: Tool(raises=ValueError(WHY_IT_FAILED)), SPENDS: Tool(returns=REFUNDED)},
        spec=refund_desk,
    )
    ours = facade(
        careful_turns(), {LOOKS_UP: looks_up, SPENDS: Tool(returns=REFUNDED)}, spec=refund_desk
    )

    assert looks_up.calls, "the authored document never reached the tool at all"
    assert theirs.trace()[0]["results"] == [failed(LOOKS_UP, WHY_IT_FAILED)], (
        json.dumps(theirs.trace(), indent=2)
    )
    assert ours.pact.halted == "final"
    assert len(ours.pact.steps) == 4, ours.pact.trace()
    assert ours.pact.trace() == theirs.trace(), json.dumps(
        {"facade": ours.pact.trace(), "harness": theirs.trace()}, indent=2
    )


def test_an_authored_document_still_lets_a_cancellation_out(
    refund_desk: AgentSpec,
) -> None:
    """A gate, a chain and three stages must not become somewhere a stop is lost.

    Every layer `refund-desk` adds is a `try`/`finally` more between the tool and
    the caller, and a cancellation that any of them absorbed would leave the run
    going on inside a process that was told to stop — with `payments` still ahead
    of it.
    """
    stopping = asyncio.CancelledError()
    spends = Tool(returns=REFUNDED)

    with pytest.raises(asyncio.CancelledError) as stopped:
        facade(
            careful_turns(),
            {LOOKS_UP: Tool(raises=stopping), SPENDS: spends},
            spec=refund_desk,
        )

    assert stopped.value is stopping
    assert spends.calls == []
