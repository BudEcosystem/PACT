"""A spend cap over somebody else's agent is reported as unheld, not as enforced.

`A2ATransport` has a `usage()` method, and `harness.run` reads two facts off a
transport in two steps: `reports_usage` (does the method exist?) and
`prices_money` (can anything put a PRICE on what a call carried?). The second
defaulted to the first. So a transport that has `usage()` and never declared
`prices_money` was taken to price its calls — and this one is bound to an agent,
not to a model, so there is no catalogue row and no price, ever. Its own
`usage()` docstring says the answer is *"Almost always `None`"*.

The measured effect before the fix, on a run whose `limits:` wrote
`cost-per-request-under: 0.05 USD` against a stub agent that volunteered no
usage block at all:

```text
    AssertionError: the run told the author their spend cap was enforced
    against an agent nobody can price: ()
    assert 'cost-per-request-under' in ()
     +  where () = RunResult(output='Approved.', ... used=Meter(..., tokens=0,
        money=0.0), ...).unmetered
```

The author is told their spend cap is enforced, and the meter it is enforced
against reads 0.00 for the life of the workspace — which is the exact outcome
`transports/_metering.py` opens by forbidding: *"a spend cap that can never be
reached, under an author who believes they capped their spend."*

**And only the money half moves.** `tokens-at-most` is help-texted as *"the only
ceiling that still bites when there is no price list"*, and `Limits.unmeterable`
records losing it as a side effect of having no price as its own past defect. A
remote agent MAY volunteer a token count (`result.usage.totalTokens`), so that
question is still answered by whether `usage()` exists, and this file asserts the
two ceilings move independently.

**And the report can say both things at once, on purpose.** A remote agent MAY
volunteer a cost, and `_meter_usage` charges what it is told, so
`cost-per-request-under` can be on `unmetered` on a run that stopped at
`cost-limit`. Those are not in conflict once the field is read as written:
*"could not promise to measure"*. The run held the cap this once, because
somebody else chose to say what the call cost; it could not promise to hold the
next one. `test_a_cap_on_unmetered_can_still_be_the_thing_that_stopped_the_run`
asserts that pair so it is a decision rather than an accident, and
`RunResult.unmetered`'s own docstring argues it where a reader of the field
looks.

**The default flipped with the fix, and that is the class repair.** `harness.run`
and `learning.Learner` read `getattr(transport, "prices_money", False)`; they used
to read `getattr(..., reports_usage)`. Declaring the attribute on `A2ATransport`
fixed the INSTANCE and left the class open, and the class is the whole reachable
surface: nothing in `src/` constructs a transport, so every transport that ever
runs is written by a host or copied from `adapters/out-of-tree/echo_adapter/` —
and that exemplar shipped B6 verbatim for a round AFTER the instance fix landed,
measured. A default that grants the money answer to everyone who has not thought
about the question hands the cost of not having thought about it to the author,
who wrote a spend cap and cannot read `harness.py`. The recorded objection to
`False` — four suite stand-ins bill a real figure and declared nothing, so they
would report a cap as unmeasurable while the meter ticked — held against
`RunResult.unmetered`'s OLD wording, *"did not enforce"*. The field now says
*"could not promise to measure"*, and that is exactly what is true of a transport
that never said it could price. Measured cost of the flip with nothing else
changed: **4 failures out of 1930**, all four those stand-ins; they now declare
`prices_money = True`, the line a real transport that can price writes anyway.

**Eight mutations, each applied to the tree, measured, and reverted.** Two of
them are green and are recorded BECAUSE they are green — that is the fix working,
and it is the more useful fact.

1. Delete `prices_money = False` from `A2ATransport` (`a2a_transport.py`).
   → only `test_every_transport_that_counts_says_whether_it_can_price` goes red.
   Before the default flipped, this reddened four tests here; now the default
   agrees with the declaration, so the behaviour is unchanged and what holds the
   line is the class guard. **That is the intended shape.** A repair that only
   the instance's own declaration keeps true is one the next transport does not
   get.
2. `harness.py`: `_never_reached(spec, transport, prices_money)` →
   `_never_reached(spec, transport, reports_usage)`. → **green, whole suite.**
   This is the mutation that mattered, and its being green now is the point: it
   reintroduces the fabricated catalogue sentence at the CALLER, and the seam
   below no longer produces one. Before mutation 3 was fixed, this exact edit
   left the whole suite green while the report told the author a fact about their
   catalogue that no lookup produced — a docstring in this file quoted
   `never_reached = ()` as measured output and asserted nothing about it.
3. `harness.py`, `_never_reached`: delete the `if not asked: return ()` guard.
   → `test_a_ceiling_over_a_model_nobody_named_claims_nothing_about_a_catalogue`
   goes red. The report claims the catalogue prices `` at 0 USD in and 0 USD out,
   having asked it nothing, and sizes a `tokens-at-most:` recommendation off it.
4. Mutations 2 **and** 3 together → three red, including
   `test_a_cap_on_unmetered_can_still_be_the_thing_that_stopped_the_run` and
   `test_the_exemplar_a_third_party_copies_meters_a_spend_cap_honestly`. This is
   the pair that reconstructs the original two-channel defect end to end.
5. `adapters/out-of-tree/echo_adapter/transport.py`: delete `prices_money =
   False`. → `test_every_transport_that_counts_says_whether_it_can_price` and
   `test_the_exemplar_a_third_party_copies_meters_a_spend_cap_honestly` go red.
   Under the OLD guard — `src/pact_adapters/transports/*.py` only — nothing went
   red at all, which is the file's whole defect: the class guard could not see
   the one file in the repository whose purpose is to be copied.
6. Same file: `usage()` returns `(tokens, 0.0)` instead of `(tokens, None)`. →
   `test_the_exemplar_a_third_party_copies_meters_a_spend_cap_honestly` goes red.
   `_metering.py`: *"an unpriced row yields `None`, never zero."*
7. `adapters/typescript/src/vercel-transport.ts`: delete `pricesMoney = false`.
   → `test_the_second_port_declares_the_same_thing_about_the_same_seam` goes red.
   Green on the effect test, for mutation 1's reason: `harness.ts` now defaults
   to `false` as well, because two ports answering one author's
   `cost-per-request-under:` differently is the defect the cross-port suite is
   for.
8. `adapters/typescript/src/run-trace.ts`: delete the `pricesMoney` forward from
   `Watching`'s constructor → `test_the_wrapper_the_cross_port_suite_runs_
   through_forwards_every_seam` goes red; delete the `usage` forward and the
   effect test goes red too. The wrapper is the only door the Python suite has to
   that port, it had already swallowed `usage` once, and while a fix applied only
   to the transport was measured as `"unmetered":[]` — unchanged — that omission
   was invisible to every test in the repository.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.events import Bus  # noqa: E402
from pact_adapters.harness import run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.limits import Limits  # noqa: E402
from pact_adapters.transports.a2a_transport import A2ATransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
TS_DIR = REPO / "adapters" / "typescript"


class _AnAgent(BaseHTTPRequestHandler):
    """A stand-in for somebody else's agent. Answers, and says nothing else.

    The same shape `test_scoring_an_agent_that_is_not_here.py` uses, because the
    property under test is about a real run over the real transport and a stub
    that behaved differently would be measuring a different thing.
    """

    reply: dict[str, Any] = {}

    def do_POST(self) -> None:  # noqa: N802 — the base class names it
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        out = json.dumps(type(self).reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *_: Any) -> None:
        return          # a test that prints one line per request is unreadable


@pytest.fixture
def agent_at():
    """A stub agent on localhost. Returns `(url, handler)`."""
    server = HTTPServer(("127.0.0.1", 0), _AnAgent)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/", _AnAgent
    finally:
        server.shutdown()
        server.server_close()


def _capped() -> AgentSpec:
    """An author who wrote both ceilings, in one document."""
    return AgentSpec(
        name="Desk", description="Answers questions.",
        instructions="Answer the question.",
        limits=Limits(
            cost_per_request_under=0.05, cost_currency="USD", tokens_at_most=100_000
        ),
    )


SAID_NOTHING = {"result": {"parts": [{"kind": "text", "text": "Approved."}]}}


def _the_transports() -> list[Path]:
    """The nine transports, which is not the same as the files in the directory.

    `_metering.py`, `_summarise.py` and `_tool_choice.py` are shared code that
    every transport imports, not transports; the `_` prefix is how this tree says
    so, and the register row says so in words for a reader who counts the
    directory and gets twelve.
    """
    here = REPO / "adapters" / "python" / "src" / "pact_adapters" / "transports"
    return sorted(p for p in here.glob("*.py") if not p.name.startswith("_"))


def _the_exemplars() -> list[Path]:
    """The transports that ship OUTSIDE the package, to be copied.

    `_the_transports()` is the in-tree nine and it is the wrong population for a
    class guard. Nothing in `src/` constructs a transport — every transport that
    ever runs is written by a host or copied from `adapters/out-of-tree/`, and
    the exemplar shipped B6's exact defect, live and measured, for a round AFTER
    the instance was fixed in `a2a_transport.py`. A guard scoped to the files the
    defect could not reach is a guard that holds nothing.

    Asserted non-empty at the call site rather than here, because a glob that
    silently matches nothing is how a class guard becomes decorative.
    """
    here = REPO / "adapters" / "out-of-tree"
    return sorted(here.glob("*/transport.py"))


def _the_c5_row() -> str:
    """Row C5 of the production gap register, as one line of the real document."""
    register = (REPO / "docs" / "70-PRODUCTION-GAP-REGISTER.md").read_text()
    row = next(
        (line for line in register.splitlines() if line.startswith("| **C5**")), ""
    )
    assert row, "C5 is gone from the register"
    return row


# ───────────────────────────────────────────────── the effect on the report


def test_a_spend_cap_over_a_remote_agent_is_reported_as_unheld(agent_at) -> None:
    """The defect, at the only place an author ever sees it.

    Not the attribute — the sentence on `RunResult.unmetered`, which is what a
    report prints and what an author reads to find out which of the ceilings
    they wrote actually bound anything. Before the fix this list did not mention
    money at all, so the run said the cap held while the meter read 0.00.
    """
    url, handler = agent_at
    handler.reply = SAID_NOTHING
    out = asyncio.run(run(_capped(), A2ATransport(url), "can I have a refund?"))

    assert out.output == "Approved.", out.output
    assert "cost-per-request-under" in out.unmetered, (
        "the run told the author their spend cap was enforced against an agent "
        f"nobody can price: {out.unmetered}"
    )
    assert out.spent == 0.0, "and nothing was billed, which is the whole problem"


def test_the_token_ceiling_is_not_taken_away_with_the_money_one(agent_at) -> None:
    """The regression `Limits.unmeterable`'s docstring already records.

    Tokens and money are two questions. A remote agent MAY volunteer
    `result.usage.totalTokens` — `_what_it_cost` reads exactly that — and it is
    never told a price, so fixing the money answer must not collapse the two
    back into one. `tokens-at-most` is help-texted as *"the only ceiling that
    still bites when there is no price list"*.
    """
    url, handler = agent_at
    handler.reply = {
        "result": {
            "parts": [{"kind": "text", "text": "ok"}],
            "usage": {"totalTokens": 120},          # counted, and not priced
        }
    }
    out = asyncio.run(run(_capped(), A2ATransport(url), "hello"))

    assert "tokens-at-most" not in out.unmetered, (
        f"the count was knowable and the ceiling was dropped anyway: {out.unmetered}"
    )
    assert out.used is not None and out.used.tokens == 120, out.used
    assert "cost-per-request-under" in out.unmetered, out.unmetered


def test_a_price_the_agent_volunteers_still_reaches_the_meter(agent_at) -> None:
    """`prices_money: False` is a promise about the REPORT, not a gag on the meter.

    If the remote agent says what the call cost, `_meter_usage` charges it —
    asserted here on the meter itself, below the cap so that nothing halts and
    the metering is the only thing under test. Whether the CEILING then fires is
    the next test's job, because it is a different claim and this one used to
    make it in its docstring without checking it.
    """
    url, handler = agent_at
    handler.reply = {
        "result": {
            "parts": [{"kind": "text", "text": "ok"}],
            "usage": {"totalTokens": 120, "cost": 0.004},
        }
    }
    out = asyncio.run(run(_capped(), A2ATransport(url), "hello"))
    assert out.spent == pytest.approx(0.004), out.spent
    assert out.halted == "final", f"0.004 is under the 0.05 cap: {out.halted}"


def test_a_cap_on_unmetered_can_still_be_the_thing_that_stopped_the_run(
    agent_at,
) -> None:
    """The pair that reads like a contradiction, asserted as the intended report.

    `RunResult.unmetered` says *"could not promise to measure"*, not *"measured
    nothing"* — and this transport is the reason that wording is careful. It can
    be TOLD a figure it can never itself price, so on the one exchange where the
    remote agent volunteers a bill over the cap, BOTH are true at once:
    `cost-per-request-under` is on `unmetered` (no run here can promise it) and
    `halted` is `cost-limit` (this run held it anyway).

    Measured, at `cost: 5.00` against a `0.05 USD` cap:

    ```text
        halted        = 'cost-limit'
        unmetered     = ('cost-per-request-under',)
        spent         = 5.0
        never_reached = ()
    ```

    The alternative was to drop the money half in `usage()` so the two lists can
    never disagree. That buys a tidier report by throwing away a real stop, and
    the author it fails is the one who most needed it: told at the END of a run
    that their cap was unmeasurable, having already gone through it.

    **Three channels, three assertions.** `prices_money` moves `unmetered`,
    `never_reached` and the `session.limit.failed` record, and for a round only
    the first was asserted anywhere — so mutation 2 in this file's header
    (`_never_reached(spec, transport, reports_usage)`) left the entire suite
    green while the report told the author a fact about their catalogue that no
    lookup produced. All three are pinned below.
    """
    url, handler = agent_at
    handler.reply = {
        "result": {
            "parts": [{"kind": "text", "text": "ok"}],
            "usage": {"totalTokens": 120, "cost": 5.00},
        }
    }
    bus = Bus()
    out = asyncio.run(run(_capped(), A2ATransport(url), "hello", bus=bus))

    assert out.halted == "cost-limit", (
        "a bill the agent volunteered was over the author's cap and the run "
        f"carried on: {out.halted!r}"
    )
    assert "cost-per-request-under" in out.unmetered, (
        "the cap held this once because somebody else chose to say what the "
        f"call cost; no run here can promise that: {out.unmetered}"
    )
    assert out.spent == pytest.approx(5.00), out.spent
    # The second honesty channel the same flag moves, and the one that was held
    # by nothing. `never_reached` says *"the meter is correct and always zero,
    # because the catalogue prices this model at nothing"* — a claim about a row
    # in the author's own tree, with a `tokens-at-most:` recommendation sized
    # from it. There is no row: this transport is bound to an AGENT, so nothing
    # was looked up and nothing can be said. Anything but `()` here is the report
    # inventing a catalogue entry for an empty model name.
    assert out.never_reached == (), (
        "the run made a claim about the author's model catalogue on a run bound "
        f"to somebody else's agent, which no lookup produced: {out.never_reached}"
    )
    # And the third: the bus record, which is the only one of the three that
    # reaches the author's TREE (a `watches:` entry may subscribe to it —
    # `watches.EMITTED`, `spec/schema.yaml`'s `reaches:` list). It fires before
    # the first model call, so it cannot know how the run ended, and this pins
    # the pair that arrives together: a `session.limit.failed` naming
    # `cost-per-request-under` on a run that then HALTED on that ceiling.
    # `docs/20-ARCHITECTURE-DRAFT.md` states the address's meaning in words and
    # was amended with this fix so that "cannot promise to measure" is what it
    # says — the wording `RunResult.unmetered` itself carries.
    said = [e for e in bus.log if str(e.address) == "session.limit.failed"]
    assert [tuple(e.payload["limits"]) for e in said] == [
        ("cost-per-request-under",)
    ], [(str(e.address), e.payload) for e in said]
    # Nothing here reads `harness.py` as text. The contract is argued at
    # `RunResult.unmetered`'s own docstring, where a reader of the field finds
    # it, and this asserts the behaviour that docstring describes — a test that
    # pinned the sentence instead would go red on a rewording that changed
    # nothing, which is the failure mode the other test in this file records.


# ─────────────────────────── the run that claims nothing about a catalogue


def test_a_ceiling_over_a_model_nobody_named_claims_nothing_about_a_catalogue() -> None:
    """`never_reached` may only say what a lookup actually answered.

    Independent of B6 and one seam below it. `_never_reached` builds
    `models = [transport.model or spec.model]`; on a transport with no `.model`
    and a document with no `model:` line that is `[""]`, the loop `continue`d
    past every lookup, `total` stayed at its initial `0.0`, and
    `Limits.priced_at_nothing(0.0)` reported every money ceiling as priced at
    nothing. The `None` guard written for exactly this case is INSIDE the loop
    and never ran.

    The sentence it emitted, measured on the out-of-tree exemplar before the fix:

    ```text
        agents/<this agent>/limits.yaml:1 — `cost-per-request-under` is measured
        against ``, and the model catalogue publishes that row at 0 USD in and
        0 USD out. … fix: write `tokens-at-most: 200000` beside it …
    ```

    Two things are wrong with it and the second is worse. It states a fact about
    a row in the author's own tree that no lookup produced — for an EMPTY model
    name — and then D11's recommendation obligation hangs a `tokens-at-most:`
    figure off the fabricated price. D11 makes recommending an obligation; a
    recommendation founded on an invented catalogue row inverts it.

    B6 masks this for `A2ATransport` by short-circuiting on `prices_money`, which
    is a fix on one CALLER. This holds the seam: a transport that declares it can
    price, counts tokens, and names no model at all.
    """
    class PricesButNamesNothing:
        """Says it can price, and nothing here knows what model that is."""

        name = "prices-but-names-nothing"
        prices_money = True

        def usage(self) -> tuple[int, float]:
            return 10, 0.0

        async def model_call(self, system, history, tools):  # noqa: ANN001
            return "Approved.", []

    spec = AgentSpec(
        name="Desk", description="Answers questions.",
        instructions="Answer the question.",
        limits=Limits(cost_per_request_under=0.05, cost_currency="USD"),
    )
    assert spec.model == "", "the point of the test is that nothing names a model"
    out = asyncio.run(run(spec, PricesButNamesNothing(), "hello"))
    assert out.never_reached == (), (
        "the report told the author what their model catalogue publishes for a "
        f"model nobody named: {out.never_reached}"
    )


# ───────────────────────────────── and the default that made the absence bite


def test_a_transport_that_never_said_it_could_price_is_not_taken_to_have() -> None:
    """The default, asserted as behaviour rather than as prose.

    This used to assert row C5 of the register said the flip was still OPEN, and
    the flip has now landed: `harness.run` and `learning.Learner` read
    `getattr(transport, "prices_money", False)`. Answering the MONEY question
    with the TOKEN answer is what turned an undeclared attribute into a false
    claim of enforcement, and the population that default lands on is everything
    — nothing in `src/` constructs a transport, so every transport that ever runs
    is host-written or copied from `adapters/out-of-tree/`, which is exactly the
    population no in-tree declaration reaches.

    The objection to `False`, recorded at the time, was that it is the same lie
    pointing the other way: four stand-ins in this suite bill a real figure and
    declared nothing, so they would report a cap as unmeasurable while the meter
    ticked. That held against `RunResult.unmetered`'s OLD wording, *"did not
    enforce"*. The field now says *"could not promise to measure"*, which is
    exactly what is true of a transport that never said it could price — the
    harness has no promise because nobody made it one. The four stand-ins now
    declare `prices_money = True`, the line a real transport that can price
    writes anyway, and that was the entire measured cost of the flip: 4 failures
    out of 1930.

    Asserted here as an EFFECT, on a transport built in this test, because the
    earlier prose form went green on a register row and would have stayed green
    through the flip it was recommending.
    """
    class BillsAndSaysNothing:
        """Counts, bills, and never declares whether it can price. The shape
        every host-written transport starts as."""

        name = "bills-and-says-nothing"

        def usage(self) -> tuple[int, float]:
            return 10, 0.01

        async def model_call(self, system, history, tools):  # noqa: ANN001
            return "Approved.", []

    out = asyncio.run(run(_capped(), BillsAndSaysNothing(), "hello"))
    assert "cost-per-request-under" in out.unmetered, (
        "a transport that never said anything about pricing was taken to price "
        f"its calls, which is the B6 defect in its general form: {out.unmetered}"
    )
    assert "tokens-at-most" not in out.unmetered, (
        "and only the money half moves — the token count is real: "
        f"{out.unmetered}"
    )
    assert out.spent == pytest.approx(0.01), (
        "`prices_money` is a promise about the REPORT, not a gag on the meter: "
        f"{out.spent}"
    )
    row = _the_c5_row()
    assert "prices_money" in row, row
    assert "default" in row, row


def test_the_honest_and_inert_stand_in_is_unchanged() -> None:
    """`transports/mock.py` declares no `prices_money` on purpose and must stay
    exactly as it was: it is bound to no model, has no `usage()` at all, and is
    the one transport that keeps the `unmetered` route exercised. It is also the
    proof that the default flip is safe FOR IT — with no `usage()`,
    `reports_usage` is already `False` and both candidate defaults agree."""
    from pact_adapters.script import Script, Turn
    from pact_adapters.transports.mock import ReferenceTransport

    out = asyncio.run(
        run(_capped(), ReferenceTransport(Script([Turn("ok")])), "hello")
    )
    assert "cost-per-request-under" in out.unmetered, out.unmetered
    assert "tokens-at-most" in out.unmetered, out.unmetered


# ─────────────────────────────────── the two files a third party actually copies


def test_the_exemplar_a_third_party_copies_meters_a_spend_cap_honestly() -> None:
    """A real run over `adapters/out-of-tree/echo_adapter`, with both ceilings.

    The instance fix landed on `A2ATransport` and this file shipped B6 verbatim
    for a round afterwards — `usage()` returning `(tokens, 0.0)`, no declaration
    — and nothing tested it: `test_an_eighth_adapter_needs_no_core_change.py`
    imports it and its spec carries no `limits:` at all. Measured on that tree:

    ```text
        declares prices_money: <absent>
        usage(): (2, 0.0)
        unmetered    : ()
        never_reached: ('… `cost-per-request-under` is measured against ``, and
                        the model catalogue publishes that row at 0 USD in and
                        0 USD out. …',)
        spent        : 0.0
    ```

    `unmetered: ()` is the author being told the cap is enforced; `spent: 0.0` is
    the meter it is enforced against. Both wrongs at once, in the file the
    project hands a third party as the thing to copy — and the exemplar's own
    comment states the governing principle for itself: *"an exemplar that quietly
    omitted the newest one would teach the omission."*

    An effect, not a grep. `test_every_transport_that_counts_says_whether_it_can_
    price` now covers this file as source text; this is the run that shows the
    declaration is the RIGHT one, and that `usage()`'s `None` money half reaches
    `_meter_usage` without taking the token count with it.
    """
    out_of_tree = REPO / "adapters" / "out-of-tree"
    sys.path.insert(0, str(out_of_tree))
    try:
        from echo_adapter import EchoTransport
        transport = EchoTransport()
        assert transport.prices_money is False, "a scripted echo binds no row"
        assert transport.usage()[1] is None, (
            "`_metering.py`: an unpriced row yields `None`, never zero — a `0.0` "
            f"here is a spend cap that can never be reached: {transport.usage()}"
        )
        out = asyncio.run(run(_capped(), transport, "hello"))
    finally:
        sys.path.remove(str(out_of_tree))
        sys.modules.pop("echo_adapter", None)
        sys.modules.pop("echo_adapter.transport", None)

    assert "cost-per-request-under" in out.unmetered, (
        "the exemplar told the author their spend cap was enforced against a "
        f"meter nothing can move: {out.unmetered}"
    )
    assert "tokens-at-most" not in out.unmetered, (
        f"and the token count is real, so that ceiling stays: {out.unmetered}"
    )
    assert out.used is not None and out.used.tokens > 0, out.used
    assert out.never_reached == (), (
        "the report claimed the author's catalogue prices an empty model name "
        f"at zero, having asked it nothing: {out.never_reached}"
    )


def test_the_second_port_reports_a_spend_cap_it_cannot_price() -> None:
    """The same claim, through the only door the Python suite has to that port.

    Two separate omissions had to be fixed together for this to move, and that
    is why it is one test. `VercelAITransport` declared no `pricesMoney` — so the
    port shipped the mechanism with its false branch unreachable — AND
    `run-trace.ts`'s `Watching` wrapper forwarded only `name`, `lattice()` and
    `usage`, so a declaration on the transport would have been swallowed before
    reaching `harness.ts`. Measured, with the transport declaring and the wrapper
    not forwarding: `"unmetered":[]`, unchanged.

    The wrapper's own comment records having made this exact mistake once before,
    with `usage`: *"It was not, so the seventh target enforced no token or cost
    ceiling through the only path the Python suite has to it."* Driving through
    `run-trace.ts` rather than importing the class is deliberate — it is the path
    every cross-port test in this repository uses, so a field the wrapper drops
    is a field no test can see.
    """
    spec = json.dumps({
        "name": "Refund Desk",
        "instructions": "Decide, then issue the refund.",
        "tools": [{"name": "zendesk", "description": "read the ticket"}],
        "maxSteps": 8,
        "limits": {
            "cost-per-request-under": "0.05 USD",
            "tokens-at-most": 100000,
        },
    })
    done = subprocess.run(
        ["node", "--experimental-strip-types", "src/run-trace.ts",
         spec, json.dumps({"turns": [{"text": "done"}]}), "hello"],
        cwd=TS_DIR, capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stderr
    got = json.loads(done.stdout)
    assert "cost-per-request-under" in got["unmetered"], (
        "the second port told the author their spend cap was enforced against a "
        f"money meter hardcoded to 0: {got['unmetered']}"
    )
    assert "tokens-at-most" not in got["unmetered"], (
        "and only the money half moves — the scripted seam counts real tokens: "
        f"{got['unmetered']}"
    )


def test_the_wrapper_the_cross_port_suite_runs_through_forwards_every_seam() -> None:
    """`run-trace.ts`'s `Watching` is the only door, so what it drops is invisible.

    A class guard, and it is the one this file most needed. Every cross-port test
    in the repository reaches the TypeScript port by running `run-trace.ts`,
    which wraps the real transport in `Watching` to record what each stage put in
    front of the model. `Watching` forwards by hand, one member at a time, and
    each optional member of `Transport` it forgets is a capability the harness
    then decides from a default with nothing anywhere going red.

    It has happened twice. The wrapper's own comment records the first:
    `usage` was not forwarded, so *"the seventh target enforced no token or cost
    ceiling through the only path the Python suite has to it"* — the same spec
    that halted `token-limit` in one step on a bare `VercelAITransport` ran
    twenty steps to `step-limit` through the wrapper. `pricesMoney` was the
    second, and it is the reason a fix on the transport alone measured
    `"unmetered":[]`, unchanged.

    Neither was catchable by an effect test at the port boundary, and that is
    why this is a source-text guard rather than a run. Both fields' current
    values happen to agree with the harness default — `usage` absent, and
    `pricesMoney = false` matching the flipped default — so dropping either
    changes no observable output TODAY, on THIS transport. The next optional
    field, or the next transport that declares `pricesMoney = true`, is where the
    silence bites, and by then the wrapper is a file nobody is reading.
    """
    interface = (TS_DIR / "src" / "harness.ts").read_text()
    body = interface.split("export interface Transport {", 1)[1].split("\n}", 1)[0]
    optional = sorted(set(re.findall(r"^\s*(\w+)\??[?(:]", body, re.M)) & set(
        re.findall(r"^\s*(\w+)\?", body, re.M)
    ))
    assert "pricesMoney" in optional and "usage" in optional, optional

    wrapper = (TS_DIR / "src" / "run-trace.ts").read_text()
    watching = wrapper.split("class Watching implements Transport {", 1)[1]
    watching = watching.split("\n}", 1)[0]
    dropped = [f for f in optional if f"inner.{f}" not in watching]
    assert not dropped, (
        f"`Watching` in run-trace.ts never reads {dropped} off the transport it "
        "wraps, so a transport declaring one is indistinguishable from one that "
        "does not — through the only path the Python suite has to this port. "
        "Forward it in the constructor beside `usage` and `pricesMoney`."
    )


# ──────────────────────────────────────────────── and the register says so (E2)


def test_the_register_states_the_measured_metering_matrix() -> None:
    """C5 said *"No transport reports usage on most targets"*, and that was false.

    Eight of the nine transports implement `usage()`; the one that does not is
    the deliberate stand-in. The real hole was `apply_settings`, on two of nine.
    A register row that misnames which seam is missing sends the next reader to
    the wrong file.

    The `apply_settings` figure is now SEVEN of nine: `pydantic_ai_transport.py`,
    `langchain_transport.py` and `langgraph_transport.py` joined the two the row
    named, and `autogen_transport.py` and `openai_agents_transport.py` joined
    those. The number is asserted rather than bounded on purpose — this test is
    the thing that made the register's claim re-measurable, and it is supposed to
    fire every time the matrix moves so the row is rewritten with the reasons and
    not just the count. It fired for both of those changes and the row was
    rewritten each time.

    The two that remain are the two where there is nothing to map rather than
    something not yet mapped: `a2a_transport.py`, where the remote agent owns the
    loop and no generation parameter of PACT's crosses the boundary, and
    `mock.py`, which is bound to no model at all and is the control arm that
    keeps the `unmetered` route exercised. So a run of nine is the wrong target
    here; seven is the whole of it, and this assertion is what would make anyone
    who "fixed" the last two say why.
    """
    row = _the_c5_row()
    assert "No transport reports usage on most targets" not in row, row
    assert "apply_settings" in row, row

    files = _the_transports()
    assert len(files) == 9, (
        "a transport was added or removed — re-measure the matrix and update "
        f"row C5 of docs/70-PRODUCTION-GAP-REGISTER.md: {[p.name for p in files]}"
    )
    counted = sum("def usage(" in p.read_text() for p in files)
    settings = sum("def apply_settings(" in p.read_text() for p in files)
    assert (counted, settings) == (8, 7), (
        f"the matrix moved (usage {counted}, apply_settings {settings}) — row C5 "
        "of docs/70-PRODUCTION-GAP-REGISTER.md now states figures the tree does "
        "not"
    )
    assert f"{counted} of 9" in row and f"{settings} of 9" in row, row


def test_every_transport_that_counts_says_whether_it_can_price() -> None:
    """The defect CLASS, not the instance.

    B6 was one transport with a `usage()` and no `prices_money`, and it survived
    five end-to-end tests of itself because nothing anywhere asked the question
    of the whole directory. The default (`harness.run`, `learning.Learner`) still
    reads the money answer off the token answer, so the NEXT transport to ship a
    `usage()` and forget the declaration silently claims to price its calls —
    and the author it lies to is the one who wrote a spend cap.

    Declared, not correct: a file could say `prices_money = True` wrongly and
    this would pass. What it closes is the case that actually happened, which is
    nobody having thought about it at all.

    An ASSIGNMENT, not a mention. The first draft of this looked for the word,
    and the word survives in a comment explaining why the attribute matters — so
    deleting the declaration from `A2ATransport` left this green while three
    other tests in this file went red. A guard that a paragraph about the bug can
    satisfy is not a guard.

    **And the population is the whole of it, which it was not.** This globbed
    `src/pact_adapters/transports/*.py` while claiming the class — and the
    out-of-tree exemplar, the one file in this repository whose entire purpose is
    to be copied by a third party, had B6's defect LIVE under it: `usage()`
    returning `(tokens, 0.0)`, no declaration, and a real run over it reporting
    `cost-per-request-under: 0.05 USD` as enforced against a meter reading 0.00.
    Since nothing in `src/` constructs a transport, host-written and
    copied-from-the-exemplar transports are the entire reachable surface of this
    defect, so the exemplar was precisely the file that mattered. The second
    port's transports are held by
    `test_the_second_port_declares_the_same_thing_about_the_same_seam`, because
    the class is a property of the SYSTEM (T7: *"no silent degradation anywhere
    in the system"*) and not of one language.
    """
    declares = re.compile(r"^\s*(self\.)?prices_money\s*[:=]", re.M)
    files = _the_transports() + _the_exemplars()
    assert _the_exemplars(), (
        "no out-of-tree exemplar was found, so this guard is scoped to the "
        "population the defect could not reach — check the glob in "
        "`_the_exemplars()` against `adapters/out-of-tree/`"
    )
    silent = [
        str(p.relative_to(REPO))
        for p in files
        if "def usage(" in p.read_text() and not declares.search(p.read_text())
    ]
    assert not silent, (
        f"{silent} count what a call carried and never say whether anything can "
        "PRICE it, so `harness.run` falls back to its default and the author's "
        "money ceilings are decided by something that cannot know. Add "
        "`prices_money = <True|False>` to the class — `False` if it is bound to "
        "an agent or to a model no catalogue prices."
    )


def test_the_second_port_declares_the_same_thing_about_the_same_seam() -> None:
    """The other half of the class. T7 is a property of the system, not a port.

    The TypeScript port shipped the `pricesMoney` MECHANISM — the interface
    field, the two read sites in `harness.ts`, the parameter in `limits.ts` — and
    no transport anywhere that assigned it. So the false branch was unreachable
    by construction and `cost-per-request-under` could never appear on that
    port's `unmetered` for any document it ran, while a reader grepping the name
    found four hits and concluded the port was compliant.

    Source text rather than a run, for the same reason the Python half is: this
    closes "nobody thought about it", and the run that closes "and it works" is
    `test_the_second_port_reports_a_spend_cap_it_cannot_price` below.
    """
    src = TS_DIR / "src"
    declares = re.compile(r"^\s*(this\.)?pricesMoney\s*[:=]", re.M)
    files = sorted(src.glob("*-transport.ts"))
    assert files, f"no transport found under {src} — the glob has gone stale"
    silent = [
        p.name
        for p in files
        if re.search(r"^\s*usage\s*\(", p.read_text(), re.M)
        and not declares.search(p.read_text())
    ]
    assert not silent, (
        f"{silent} implement `usage()` and never declare `pricesMoney`, so "
        "`harness.ts` decides the author's money ceilings from a default. Add "
        "`pricesMoney = <true|false>` to the class, and forward it in "
        "`run-trace.ts`'s `Watching` wrapper — a declaration the wrapper drops "
        "is invisible to every cross-port test in this repository."
    )
