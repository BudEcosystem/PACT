"""A ceiling nothing can ever be at or above is reported, in both ports.

`crates/pact-schema/src/lib.rs` (`Schema::check_floor`) refuses
`cost-per-request-under: NaN USD` where an AUTHOR writes it, and
`test_a_spend_cap_that_can_never_be_reached.py` holds that refusal. It reaches
one of the two doors. A spec BUILT IN CODE is the other, it is a route this repo
supports and tests, and on it the cap went straight through — measured, before
the change, on both ports::

    'NaN USD'    -> cost_per_request_under=nan currency='USD'
        reached at 1000.0                   -> None
        reached at 1.7976931348623157e+308  -> None
        reached at inf                      -> None
    'inf USD'    -> cost_per_request_under=inf currency='USD'
        reached at 1000.0                   -> None
        reached at 1.7976931348623157e+308  -> None

    WHOLE RUN under `NaN USD`: spent=6000.0 halted='step-limit' unmetered=()

and, through `adapters/typescript/src/limits.ts`::

    "NaN USD"   -> costPerRequestUnder=NaN currency="USD"
        reached at 1000                     -> null
        unmeterable(countsTokens=true, pricesMoney=true) -> []

Six thousand dollars spent under a five-cent intention, `unmetered` empty, and
so the author is told the ceiling they wrote was enforced. That is the exact
outcome `models/catalog.yaml` and `Limits.priced_at_nothing` already name as the
thing to avoid — *"a spend cap that can never be reached, under an author who
believes they capped their spend"* — arriving by the one route nothing watched.

**THE GUARD IS ON THE VALUE, NOT ON THE READER.** It was on the reader first —
`Limits.from_mapping`, `limitsFrom` — and that left the identical hole open on
every other way of building the same object. Measured with the reader guarded::

    Limits(cost_per_request_under=float('nan'), cost_currency='USD')
        -> spent=6000.0 halted='step-limit' unmetered=()
           ceilings=['cost-per-request-under']
    replace(parsed_0_05, cost_per_request_under=float('inf'))
        -> cap=inf  nothing_can_reach=()  money rows=['cost-per-request-under']
    {...limitsFrom({"cost-per-request-under": "NaN USD"}), costPerRequestUnder: 0.1}
        -> ceilings=['cost-per-request-under'] nothingCanReach=['cost-per-request-under']

The first is the before-picture verbatim, through the constructor written
directly at twenty-one sites in this directory. The second is what `harness`
itself does when a join policy grants a member its share. The third is the same
thing running the OTHER way in the second port: a stale name beside a real
ceiling, so a run could halt at `cost-limit` on the very field it had just said
held nothing. `Limits.__post_init__` is where every Python route meets;
`ceilings()` and `ceilingsNothingCanReach` are where every TypeScript route meets,
because an object literal has no construction hook.

**THE RECORD IS THE FIGURE, NOT A NAME**, and the first round of this fix got
that wrong. `Limits` carried a `nothing_can_reach` tuple of field names, whose
own comment read *"DERIVED, not accepted … Passing it in by hand does not make
it true"*. Measured against that sentence::

    Limits(tool_calls_at_most=1, nothing_can_reach=('tool-calls-at-most',))
      -> ceilings=['tool-calls-at-most']  halted='tool-call-limit'
         unmetered=('tool-calls-at-most',)
         "these ceilings held nothing, because no amount of money can ever be at
          or above the figure written: tool-calls-at-most. fix: write an amount
          of money on that line …"

A ceiling that STOPPED the run, on the channel whose wording is *"cannot
promise"*, with a money remedy for a tool-call ceiling — the wrong-diagnosis
failure `_unmetered_caveats` exists to remove, reintroduced by the field that
was meant to remove it. `__post_init__` only ever touched that tuple inside the
two arms gated on the money cap being present, so any name for any field went
through untouched, and `replace(nan_limits, cost_per_request_under=None)` kept
the claim after the cap it was about had gone.

A name is an assertion and carries nothing to check it against. What is stored
now is the FIGURE the author wrote, one slot per ceiling that can hold one
(`cap_nothing_can_reach`, `wall_nothing_can_reach`), and `nothing_can_reach` is
a read-only view over those. There is no constructor argument spelling the claim,
a hand-set record that is a figure something CAN reach is dropped, and a real
figure arriving clears the record beside it.

**BOTH FLOAT CEILINGS, not one.** `wall_clock_s` carried the identical pathology
through the identical constructor door and was silent — measured on the same
six-step harness::

    wall inf -> rows=['runs-for-at-most'] halted='step-limit' unmetered=()
    wall nan -> rows=['runs-for-at-most'] halted='step-limit' unmetered=()

which is the money before-picture verbatim, one field over, at the same moment
`__post_init__` calls *"the one moment at which every route into it meets"*.
`seconds('inf')`, `seconds('nan')` and `seconds('1e400')` are all `None`, so the
authored route was already shut and the constructor was the only way in. B10 owns
the rest of that family — a meter poisoned by a remote agent's `"cost": NaN`, a
price list resolving to `nan`, a resume through `Meter.restored` — and none of
those is a figure inside a `Limits`.

The second port had the same hole, through its own version of the same door —
`{...limitsFrom({}), wallClockS: Infinity}` built a `finishes-within` row and
`ceilingsNothingCanReach` said nothing — so once the first port started reporting it
the two runtimes answered differently about one object. Guarded there in
`ceilings()`, which is where every TypeScript route meets, and held by
`test_the_second_port_refuses_the_other_unreachable_ceiling_too`.

**THE CURRENCY IS KEPT.** `__post_init__` used to clear `cost_currency` beside
the amount, and nothing recorded it, so the clearing arm could not give it back.
On this guard's own motivating path — `harness._delegating`, two members of one
team handed the same 0.10 USD share by the same policy::

    member wrote 'NaN USD'  -> `cost-per-request-under` (0.11 of 0.1)
    member wrote '0.50 USD' -> `cost-per-request-under` (0.11 of 0.1 USD)

Same spread, same stop, two sentences — and the second port keeps the currency
through the same spread, so this was also the two ports printing different
`stoppedBy.unit` and `stoppedBy.sentence`, which is the pair `run-trace.ts`
projects in order to be compared.

**THE THIRD READER REPORTS AS WELL AS DROPS.** `Slo` took the drop and skipped
the report: `Slo.unmetered()` returned `self.written`, built from
`first-reply-within` and `per-word-under` only, so the name could never arrive
there. Masked because `Limits` and `Slo` usually take one authored block;
decoupled, measured through the real harness with `limits=Limits()`::

    slo cap nan -> cap=None unmetered=() never_reached=() spent=6000.0
    slo cap inf -> cap=None unmetered=() never_reached=() spent=6000.0

Six thousand dollars under a `surface: S-GOV, tier: core` cap that was silently
deleted — the silent degradation T7 and FR-8.1.1 forbid, inside the change
written against it, and for `inf` a strict regression from a wrong-reason
sentence to no sentence at all. `Slo` is also frozen now, because
`Slo.__post_init__` argues the guard belongs *"on construction, where every route
in meets"* — the property `Limits` has by being frozen and `Slo` did not have at
all (`s.cost_per_request_under = float('nan')` after construction restored the
whole pathology).

WHICH HONESTY CHANNEL, and why it is not the other one. There are two:
`RunResult.unmetered` (*"this run cannot promise to hold these"*) and
`RunResult.never_reached` (*"the meter is right and the answer is always
zero"*). This lands on `unmetered`, for two reasons and not for a preference:

* `never_reached` is a fact about the BINDING. `harness._never_reached` builds
  its sentence out of the bound model's catalogue price and returns nothing when
  the price cannot be sourced; a cap that never parsed to a figure has no price
  to look up and would need a second, unrelated sentence shape in one field.
  A cap nothing can reach is a fact about the WRITTEN LINE, known at parse time,
  with no transport in the picture at all.
* `never_reached` exists in ONE port. `adapters/typescript/src/harness.ts` has
  `unmetered`, `unenforced` and — since a corpus nobody looked in stopped being
  silent there — `unretrieved`, and `run-trace.ts` is the cross-port shape the
  two runtimes are compared on. Reporting this there would mean inventing a
  channel in the second port to carry a fact that has no reader waiting for it:
  `unretrieved` was earned by having a DIFFERENT recipient from `unenforced` (a
  corpus nobody read is whoever runs the thing's, not the author's), and a spend
  cap that never parsed to a figure has the same recipient as everything else on
  `unmetered` — the author, sent to the line they typed.

`unmetered`'s own wording is *"cannot promise"* and not *"did not enforce"*, and
that is what is true here: the cap is off the ceilings, so nothing is being
enforced against it, and the author is told so by name — in a sentence that
sends them to the LINE. The first version of that sentence did not: `scoring`
renders every member of `unmetered` with *"fix: nothing to type — what can be
measured depends on what the model reports back"*, which for a figure the author
typed is a wrong diagnosis attached to a right field name, and a remedy telling
them not to act. `_unmetered_caveats` splits the two.

WHAT IS DELIBERATELY NOT GUARDED. `-inf USD` is non-finite and is left alone.
It is the opposite pathology: `spent >= -Infinity` is true of every spend, so it
fires on the first step and stops the run LOUDLY at `(0 of -inf USD)`. Nothing
about it is silent, `check_floor` refuses it in a document like every other
figure below the floor, and
`test_both_ports_read_every_way_a_spend_cap_is_written.py` pins it as *"the one
non-finite cap a run can reach"* and compares that sentence across the two
ports byte for byte. The guard is therefore *"no spend can ever be at or above
this"*, not *"this is not finite"* — and
`test_the_second_port_still_stops_on_the_one_cap_a_run_can_reach` below is what
makes every `stoppedBy` assertion in this file discriminate rather than decorate.

**WHAT HOLDS THE SECOND PORT, and what used to.** Every TypeScript assertion in
this file read `ceilingsNothingCanReach`, a field `run-trace.ts` computes for this
suite and no shipped consumer of that port reads. Measured: with the
`!nothingCanReach(...)` guard deleted from `ceilings()` in `limits.ts` and the
port driven on this file's own `NaN USD` fixture, EVERY key of the output was
byte-identical to the unmutated run except that projection — `unmetered`,
`halted`, `stoppedBy`, `output` and `unenforced` all unchanged, and `unmetered`
still carrying `cost-per-request-under` because `unmeterable()` supplies it for
the B6 *"nothing here can price it"* reason. A guard held only by the driver's
own arithmetic is a guard held by nothing. `run-trace.ts` now takes a
`prices-money` argv that switches the B6 reason off — it declares the transport
CAN be priced and touches nothing else, so the money meter still never leaves
zero — and the two cross-port tests assert on the SHIPPED `unmetered` array under
it.

Mutation: THIRTEEN, each one edit, each measured against this file (29 passed).

 1. `Limits.__post_init__` (`limits.py`) — `if False and figure is not None and
    _nothing_can_reach(figure)`, so nothing is ever moved off a ceiling field.
    **18 failed, 11 passed**, on thirteen distinct tests: the run reports itself
    fully metered while six thousand dollars go out, on all four Python routes at
    once, on the wall-clock ceiling, on the machine-readable event, on both
    caveat sentences, and the cross-port test goes with it.
 2. The clearing arm beside it — `elif False:`, so a record survives a real
    figure arriving. **2 failed, 27 passed:**
    `test_a_member_given_a_real_share_stops_saying_its_cap_holds_nothing` and
    `test_the_claim_cannot_be_handed_to_the_object_from_outside`. That one edit
    puts `session.limit.failed: [('cost-per-request-under',)]` back on a member
    enforcing the join policy's real 0.10 USD ceiling.
 3. The arm that refuses a record no predicate agrees with — `if False and held
    is not None and …`. **1 failed, 28 passed:**
    `test_the_claim_cannot_be_handed_to_the_object_from_outside`. This is the arm
    a tuple of NAMES could not have had.
 4. `("wall_clock_s", "wall_nothing_can_reach")` deleted from the pair the loop
    walks, so the guard sees money only — the shape this fix shipped in for a
    round. **4 failed, 25 passed**, including
    `test_the_other_ceiling_in_the_same_dataclass_goes_the_same_way` on both
    figures and the duration remedy.
 5. `Slo.__post_init__` (`slo.py`) — `if False and cap is not None and …`, so the
    third reader keeps its own copy of the cap. **4 failed, 25 passed**, on the
    wrong-reason sentence, the six thousand dollars, the event, and the
    duplicate.
 6. `Slo.unmetered()` — `held = ()`, so the third reader drops and says nothing,
    which is what it did. **3 failed, 26 passed.**
 7. `held_nothing=[]` on `session.limit.failed` (`harness.py`), so the
    machine-readable channel carries one reason for two causes again. **1 failed,
    28 passed:** `test_the_machine_readable_report_carries_the_reason_the_prose
    _does`.
 8. The `dict.fromkeys` line deleted, so two readers of one line name it twice.
    **1 failed, 28 passed.**
 9. `slo=replace(member.slo, cost_per_request_under=granted)` deleted from
    `harness._delegating`, so the join hands the share to the enforcing reader
    and not to the reporting one. **1 failed, 28 passed.**
10. The `seconds` remedy deleted from `_unmetered_caveats` (`scoring.py`), so a
    duration that holds nothing is sent to the money line. **1 failed, 27
    passed:** `test_a_duration_that_holds_nothing_is_not_sent_to_the_money_line`.
11. `ceilings()` in `adapters/typescript/src/limits.ts` — drop the
    `&& !nothingCanReach(l.costPerRequestUnder)` guard, so the money row is built
    again. **4 failed, 25 passed:** both parametrisations of
    `test_the_second_port_names_the_same_cap_on_the_same_channel` and of
    `test_both_ports_name_it_for_one_document`. Measured on the shipped
    `unmetered` array, which comes back `[]` under the mutation. The docstring
    claimed those four before `prices-money` existed and the true figure was
    **2 failed, 17 passed** — the two `test_both_ports_name_it_for_one_document`
    cases did not bite at all, because their TypeScript assertion was satisfied
    by `unmeterable()`'s own finding.
12. The same guard on the WALL-CLOCK row in `limits.ts` — drop
    `&& !nothingCanReach(l.wallClockS)`. **1 failed, 28 passed:**
    `test_the_second_port_refuses_the_other_unreachable_ceiling_too`.
13. The `wallClockField` line deleted from `ceilingsNothingCanReach`, so the row is
    refused and nothing names it. **1 failed, 28 passed:** the same test.

`test_the_control_cap_still_stops_the_run_it_was_written_for`, the wall-clock
control inside
`test_the_other_ceiling_in_the_same_dataclass_goes_the_same_way`,
`test_the_second_port_still_stops_on_the_one_cap_a_run_can_reach` and every test
in `test_both_ports_read_every_way_a_spend_cap_is_written.py` stay green under
all thirteen, because they are about ceilings that ARE figures.

**THE SECOND-PORT HALF SKIPS WITHOUT `node`, and the gate now refuses to run
without one.** Measured with a `node` on PATH that exits 127: this file reports
`13 passed, 6 skipped` and exits 0, and the whole adapter suite reports
`1857 passed, 75 skipped` against `1945 passed, 7 skipped` — 68 tests stopped
running and said so only in a skip list nobody reads. `scripts/test-all.sh` had
no `node` check at all; it has one now, beside the `target/debug/pact` check that
exists for exactly this reason.
"""

from __future__ import annotations

import asyncio
import json
import math
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.evals import Case  # noqa: E402
from pact_adapters.events import Bus  # noqa: E402
from pact_adapters.harness import ToolCall, delegate_by_running, run  # noqa: E402
from pact_adapters.ir import AgentSpec, ToolSpec  # noqa: E402
from pact_adapters.limits import Limits, Meter  # noqa: E402
from pact_adapters.scoring import _run_every_case  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.slo import Slo, against_the_catalogue  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
TS_DIR = REPO / "adapters" / "typescript"

SPEC = AgentSpec(
    name="Refund Desk",
    description="Decides refunds",
    instructions="Decide, then issue the refund.",
    tools=(ToolSpec("zendesk", "read the ticket"),),
)
TOOLS = {"zendesk": lambda a: "lamp, broken, 6 days ago"}

#: The two spellings a run can never spend up to. Both are things
#: `coerce::money`'s `parse::<f64>()` reads, so both can be written.
UNREACHABLE = ("NaN USD", "inf USD")

#: The same two as bare floats, for the routes where nothing is parsed at all.
UNREACHABLE_FIGURES = (float("nan"), math.inf)


class Spending(ReferenceTransport):
    """A scripted model that says what each call cost, so the money meter moves.

    The same seam `Costing` uses in `test_termination.py`: `harness._meter_usage`
    probes an optional `usage()`, so a transport that answers it is a run whose
    spend cap is genuinely enforceable — which is what makes the silence this
    file measured a finding rather than an artefact of a stand-in that could not
    count.
    """

    name = "spending"
    #: Declared, because `harness.run` defaults it to `False` (B6). Without this
    #: line every money ceiling in this file would arrive on `unmetered` for the
    #: undeclared-transport reason and the control test below could not tell that
    #: from the *"nothing can reach it"* reason it exists to measure.
    prices_money = True

    def usage(self) -> tuple[int, float]:
        return 100, 1000.0


def _block(written: str) -> dict[str, object]:
    return {
        "steps-at-most": 6,
        "cost-per-request-under": written,
        "when-it-runs-out": "stop-and-say-so",
    }


def _never_finishes() -> Script:
    return Script([Turn("still working", (ToolCall("zendesk", {}),))])


def _run_with(limits: Limits):
    """The whole harness, six model calls at 1000 USD each, under `limits`."""
    spec = replace(SPEC, max_steps=6, limits=limits)
    return spec, asyncio.run(
        run(spec, Spending(_never_finishes()), "please refund my lamp", TOOLS)
    )


def _run_here(written: str):
    return _run_with(Limits.from_mapping(_block(written)))


def _held_nothing(spec: AgentSpec, r, written: object) -> None:
    """What has to be true of a run whose cap no spend can be at or above.

    One helper for four routes into the same object, so the routes differ in the
    test bodies and the CLAIM cannot drift between them.
    """
    assert r.spent >= 6_000.0, f"the transport priced its calls: {r.spent}"
    assert "cost-per-request-under" in r.unmetered, (
        f"`cost-per-request-under: {written}` cannot be at or above any spend "
        f"there is, and this run reported itself fully metered anyway: "
        f"unmetered={r.unmetered} spent={r.spent}"
    )
    # And it is not carried as a ceiling, because a row nothing can ever satisfy
    # is not a ceiling — it is a line the author has to be sent back to.
    assert spec.limits.cost_per_request_under is None, (
        f"the cap was passed through as a ceiling: "
        f"{spec.limits.cost_per_request_under!r}"
    )
    assert [c.field for c in spec.limits.ceilings() if c.reads == "money"] == [], (
        "a money row nothing can reach is still in the algebra: "
        + str(spec.limits.ceilings())
    )
    # The step ceiling is what ended it, and it says so — a run that stops for
    # one reason and reports another is the failure the whole module is about.
    assert r.halted == "step-limit", (r.halted, r.spent)
    assert r.stopped_by is not None and r.stopped_by.ceiling.field == "steps-at-most"


# ------------------------------------------------------------- the first port


@pytest.mark.parametrize("written", UNREACHABLE)
def test_a_run_under_a_cap_nothing_can_reach_says_so_and_spends_anyway(
    written: str,
) -> None:
    """The EFFECT, through the whole harness: what the author is told.

    The transport reports 1000 USD per model call and the run makes six of them,
    and the run is REPORTED-AND-CONTINUED rather than refused. That was a
    decision, and this docstring used to call it an impossibility — *"nothing can
    stop it, that half is arithmetic and cannot be fixed here"* — which is not
    true and froze the weaker behaviour behind a claim nobody could argue with.
    Measured: the classification has already happened before a single step runs::

        Limits.from_mapping({'cost-per-request-under': 'NaN JPY', ...})
          -> cap=None currency='' nothing_can_reach=('cost-per-request-under',)
             ceilings=()

    Once `_nothing_can_reach` has answered, refusing to start was available.

    WHY IT IS NOT TAKEN HERE, against FR-8.1.1 (*"no lossy operation may proceed
    silently; each MUST emit a report entry and be fail-closed by default"*). The
    fail-closed half of that requirement is met where an author is: `pact check`
    REFUSES a document carrying this figure (`Schema::check_floor`, held by
    `crates/pact-cli/tests/a_money_ceiling_that_could_never_hold_is_refused.rs`),
    so nothing shippable reaches this path. What is left is a `Limits` built in
    code, and the object is a frozen dataclass on the DELEGATION path:
    `harness._delegating` calls `replace(member.limits,
    cost_per_request_under=allowed)` on a member whose own cap is `NaN USD` and
    hands it the join policy's real share. Raising in `__post_init__` would kill
    that run one line before it became correct, and it would raise from
    `from_mapping` — turning a reportable line into a crash in a process the
    author never started. So this member reports, like every other member of
    `unmetered`, and the channel stays one kind of thing.

    Where fail-closed COSTS nothing structural it is taken instead, and that is
    not hypothetical: `Learner._decide` refuses the cycle outright for the other
    money ceiling, because there the decision point is a method call with no
    money spent yet and `Outcome(False, ...)` is already the module's ordinary
    answer. See
    `tests/test_a_monthly_ceiling_nothing_can_reach_refuses_the_cycle.py`.

    So what has to be true here is that the run does not also CLAIM the ceiling
    was holding. It names it on the honesty channel instead.
    """
    spec, r = _run_here(written)
    _held_nothing(spec, r, written)


@pytest.mark.parametrize("figure", UNREACHABLE_FIGURES)
def test_the_same_cap_handed_straight_to_the_constructor_goes_the_same_way(
    figure: float,
) -> None:
    """`Limits(cost_per_request_under=float('nan'))` — no reader in sight.

    THE route, not a route: `Limits(...)` is written directly at twenty-one
    sites in this directory (`Limits(cost_per_request_under=0.05)` at
    `test_model_pin.py` and `test_termination.py` among them), which is more
    than `from_mapping` is called from tests at all. Guarding the reader and
    calling the gap closed left this measuring `spent=6000.0 halted='step-limit'
    unmetered=()` — the before-picture word for word, through a door nobody had
    looked at.
    """
    spec, r = _run_with(Limits(cost_per_request_under=figure, cost_currency="USD"))
    _held_nothing(spec, r, figure)


@pytest.mark.parametrize("figure", UNREACHABLE_FIGURES)
def test_a_real_cap_replaced_by_one_nothing_can_reach_goes_the_same_way(
    figure: float,
) -> None:
    """`dataclasses.replace` is the third door, and `harness` walks through it.

    A `Limits` is frozen, so `replace` is how anything changes one, and
    `harness._delegating` uses it on every delegated member. It builds a NEW
    object, so `__post_init__` runs — which is the whole reason the guard is
    there and not in the reader.
    """
    parsed = Limits.from_mapping(_block("0.05 USD"))
    assert parsed.cost_per_request_under == 0.05, "the control parsed"
    spec, r = _run_with(replace(parsed, cost_per_request_under=figure))
    _held_nothing(spec, r, figure)


def test_the_control_cap_still_stops_the_run_it_was_written_for() -> None:
    """Everything above is identical except the figure, so the report up there
    is the cap's doing and not the transport's."""
    spec, r = _run_here("0.05 USD")

    assert "cost-per-request-under" not in r.unmetered, (
        "a cap that is a figure is enforced and must not be named as one that "
        "is not: " + str(r.unmetered)
    )
    assert spec.limits.cost_per_request_under == 0.05
    assert r.halted == "cost-limit", (r.halted, r.spent)
    assert r.stopped_by is not None
    assert r.stopped_by.ceiling.field == "cost-per-request-under"
    assert "0.05" in r.stopped_by.sentence() and "USD" in r.stopped_by.sentence()


def test_a_cap_nothing_can_reach_is_not_a_team_budget_either() -> None:
    """The second thing the figure was read as, and the one nothing named.

    `harness` shares a team's allowance out of `spec.limits.cost_per_request_under`
    — `team_budget = spec.limits.cost_per_request_under or 0.0`, and `nan` is
    truthy, so a NaN cap was handed to the join policy as the money a whole team
    had to divide. Pinned here rather than argued: the same guard has to make it
    zero, which is what an agent with no usable cap actually has.
    """
    assert Limits.from_mapping(_block("NaN USD")).cost_per_request_under is None
    budget = Limits.from_mapping(_block("NaN USD")).cost_per_request_under or 0.0
    assert budget == 0.0 and not math.isnan(budget), budget


def test_the_claim_cannot_be_handed_to_the_object_from_outside() -> None:
    """`nothing_can_reach` is a view over the figures, not a value anyone passes.

    It was a FIELD, whose own comment read *"DERIVED, not accepted … Passing it
    in by hand does not make it true"*, and `__post_init__` only ever touched
    that tuple inside the two arms gated on the money cap being present — so any
    name for any field, handed in by anyone, went through untouched. Measured
    against the claim::

        Limits(tool_calls_at_most=1, nothing_can_reach=('tool-calls-at-most',))
          -> nothing_can_reach=('tool-calls-at-most',)  ceilings=['tool-calls-at-most']
             halted='tool-call-limit'  unmetered=('tool-calls-at-most',)
             "these ceilings held nothing, because no amount of money can ever be
              at or above the figure written: tool-calls-at-most.
              fix: write an amount of money on that line …"

    A ceiling that STOPPED the run, reported on the channel whose wording is
    *"cannot promise"*, with a money remedy for a tool-call ceiling — which is
    the wrong-diagnosis failure `_unmetered_caveats` was written to remove,
    reintroduced by the field meant to remove it.

    A record made of a NAME cannot be checked, because a name carries no figure.
    The record is the FIGURE now — and it is a PRIVATE TYPE, which is the half
    this test did not have and the docstring claimed anyway.

    **THE FIGURE SLOTS WERE PUBLIC CONSTRUCTOR ARGUMENTS, and this test looked
    only where they were safe.** It asserted `Limits(cap_nothing_can_reach=0.05)`
    and `Limits(wall_nothing_can_reach=30.0)` — the two values the predicate
    DISAGREES with, which is the one arm that dropped them. Every figure the
    predicate agrees with went straight through. Measured on the tree before
    this, no edits::

        Limits(cap_nothing_can_reach=inf).nothing_can_reach
          -> ('cost-per-request-under',)          <- no cost line anywhere
        Limits(wall_nothing_can_reach=inf).held_nothing()
          -> (('runs-for-at-most', 'seconds'),)
        Limits(tool_calls_at_most=1, wall_nothing_can_reach=inf,
               wall_clock_field='tool-calls-at-most')
          -> halted='tool-call-limit'
             stopped_by=Ceiling(field='tool-calls-at-most', ... limit=1)
             unmetered=('tool-calls-at-most',)
        Limits(wall_nothing_can_reach=inf, wall_clock_field='anything-the-caller-likes')
          -> held_nothing() = (('anything-the-caller-likes', 'seconds'),)

    and through the real caveat renderer::

        "these ceilings held nothing, because no length of time can ever be at
         or above the figure written: tool-calls-at-most. fix: write a length of
         time on that line, like `runs-for-at-most: 30s`."
        "… : anything-the-caller-likes. fix: write a length of time on that line …"
        "these ceilings held nothing, because no amount of money can ever be at
         or above the figure written: cost-per-request-under. fix: write an
         amount of money on that line …"      <- from a `Limits` with no cost line

    which is the ORIGINAL defect at the top of this file word for word: a ceiling
    that demonstrably STOPPED the run, named on the channel whose wording is
    *"cannot promise"*, with a remedy for a line that has no such figure on it —
    and an ARBITRARY field name forged into an author's report, because
    `held_nothing()` quotes `wall_clock_field` and that was a free-form string.
    `Slo` carried the identical hole (`Slo(cap_nothing_can_reach=inf).unmetered()
    -> ('cost-per-request-under',)`).

    A predicate can never be the gate on a record, because the forger simply
    passes a figure the predicate agrees with. The gate is the TYPE: the record
    is `limits._HeldNothing`, module private, `__post_init__` answers anything
    else with a `TypeError`, and `wall_clock_field` is checked against a closed
    vocabulary. There is no constructor argument spelling the claim now, which is
    what this docstring said while three of them existed.

    **AND THE KEEP DIRECTION.** Arm three had its DROP direction held here and
    its KEEP direction held nowhere: measured, replacing it with an unconditional
    drop (`if held is not None:`) left all four holding files green — 82 passed,
    4 skipped, the same as baseline — while silently restoring the defect on the
    delegation path, which is where `harness.py`'s
    `replace(member.limits, cost_per_request_under=granted)` lives. The two
    `replace` assertions at the end of this test are that direction.
    """
    for spelling in ("nothing_can_reach", "cap_nothing_can_reach", "wall_nothing_can_reach"):
        with pytest.raises(TypeError):
            Limits(tool_calls_at_most=1, **{spelling: float("inf")})  # type: ignore[arg-type]
    # And the slot that does exist refuses a figure — by TYPE, so a caller who
    # guesses the private name still cannot spell the claim.
    for forged in (float("inf"), float("nan"), 0.05, ("cost-per-request-under",)):
        with pytest.raises(TypeError):
            Limits(_held_nothing=forged)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Slo(cap_nothing_can_reach=float("inf"))  # type: ignore[call-arg]

    # A name that no ceiling of this object could have come off is refused too,
    # because `held_nothing()` quotes it straight into the author's report.
    for name in ("anything-the-caller-likes", "tool-calls-at-most", ""):
        with pytest.raises(ValueError):
            Limits(wall_clock_s=math.inf, wall_clock_field=name)
    for good in ("runs-for-at-most", "finishes-within"):
        assert Limits(wall_clock_s=math.inf, wall_clock_field=good).nothing_can_reach == (
            good,
        )

    # A real cap arriving beside a record clears it — the delegation arm, reached
    # here without delegation.
    handed = replace(
        Limits(cost_per_request_under=float("nan"), cost_currency="USD"),
        cost_per_request_under=0.10,
    )
    assert handed.nothing_can_reach == (), handed
    assert handed.cost_per_request_under == 0.10

    # THE OTHER DIRECTION, which nothing held: a record survives a `replace` that
    # does not touch the ceiling it is about. `harness._delegating` replaces one
    # field and every other one has to arrive untouched — and by then the figure
    # is off the ceiling field, so an object rebuilt from the figures alone would
    # lose the claim and the run would go silent again.
    kept = Limits(cost_per_request_under=float("nan"), cost_currency="USD")
    assert kept.nothing_can_reach == ("cost-per-request-under",)
    for changed in (
        replace(kept, cost_currency="EUR"),
        replace(kept, tool_calls_at_most=3),
        replace(kept, when_it_runs_out=kept.when_it_runs_out),
    ):
        assert changed.nothing_can_reach == ("cost-per-request-under",), changed
    slo_kept = Slo(cost_per_request_under=float("nan"), cost_currency="USD")
    assert replace(slo_kept, measured_at="p99").unmetered() == (
        "cost-per-request-under",
    )


def test_the_currency_the_author_wrote_survives_the_share_they_are_handed() -> None:
    """The join hands a member a figure; the member still knows what currency.

    `__post_init__` used to clear `cost_currency` beside the amount, and nothing
    recorded it, so the clearing arm could not give it back. Measured on this
    guard's own motivating path, two members of one team handed the same 0.10 USD
    share by the same policy::

        member wrote 'NaN USD'  -> `cost-per-request-under` (0.11 of 0.1)
        member wrote '0.50 USD' -> `cost-per-request-under` (0.11 of 0.1 USD)

    Same spread, same stop, two sentences. The second port keeps the currency
    through the same spread (`spend("NaN USD") -> amount=NaN currency="USD"`), so
    this was also the two ports printing different `stoppedBy.unit` and
    `stoppedBy.sentence` — the pair `run-trace.ts` projects in order to be
    compared, and `Ceiling.unit` records that a wrong currency in this sentence
    was a shipped defect once already.
    """
    parsed = Limits.from_mapping(_block("NaN USD"))
    assert parsed.cost_per_request_under is None and parsed.cost_currency == "USD"

    handed = replace(parsed, cost_per_request_under=0.10)
    meter = Meter(started=0.0)
    meter.money = 0.11
    stop = handed.reached(meter, 0.0)
    assert stop is not None and stop.ceiling.field == "cost-per-request-under"
    assert stop.what == "`cost-per-request-under` (0.11 of 0.1 USD)", stop.what
    # Against the member beside it in the same team, which is the comparison
    # that made the missing noun visible.
    real = replace(Limits.from_mapping(_block("0.50 USD")), cost_per_request_under=0.10)
    assert real.reached(meter, 0.0).what == stop.what


@pytest.mark.parametrize("figure", UNREACHABLE_FIGURES)
def test_the_other_ceiling_in_the_same_dataclass_goes_the_same_way(
    figure: float,
) -> None:
    """`runs-for-at-most` carries the identical pathology through the identical
    door, and for a round `__post_init__` inspected one of the two.

    Its own docstring says *"a `Limits` is frozen, so there is exactly one moment
    at which every route into it meets, and this is it"* — and at that moment it
    looked only at the money field. Measured on this same six-step harness::

        wall inf -> rows=['runs-for-at-most'] halted='step-limit' unmetered=()
        wall nan -> rows=['runs-for-at-most'] halted='step-limit' unmetered=()
        cap  inf -> rows=[]                   halted='step-limit'
                    unmetered=('cost-per-request-under',)

    The first two lines are the money before-picture verbatim, one field over.
    The AUTHORED route is already shut — `seconds('inf')`, `seconds('nan')` and
    `seconds('1e400')` are all `None`, and `Limits.from_mapping({'runs-for-at-
    most': 'inf'})` builds no row — so a spec built in code is the only way in,
    which is exactly the door this whole file is about.

    `-inf` is left alone here for the reason it is left alone for money: elapsed
    seconds are `>= -inf` on the first check, so it fires loudly rather than
    silently. B10 owns the rest of that family — a poisoned meter, a price list,
    a resume — and none of those is a figure inside a `Limits`.
    """
    spec, r = _run_with(Limits(wall_clock_s=figure))

    assert [c.field for c in spec.limits.ceilings()] == [], (
        "a wall-clock row no elapsed time can ever be at or above is still in "
        "the algebra: " + str(spec.limits.ceilings())
    )
    assert spec.limits.wall_clock_s is None, spec.limits.wall_clock_s
    assert "runs-for-at-most" in r.unmetered, (
        f"`runs-for-at-most: {figure}` held nothing and the run said nothing "
        f"about it: unmetered={r.unmetered}"
    )
    assert r.halted == "step-limit", (r.halted, r.stopped_by)

    # And the field name reported is the LINE the author wrote, which is not
    # always `runs-for-at-most`.
    other = Limits(wall_clock_s=figure, wall_clock_field="finishes-within")
    assert other.nothing_can_reach == ("finishes-within",), other

    # The control: a wall-clock ceiling that IS a length of time still stops a run.
    spec, r = _run_with(Limits(wall_clock_s=0.0))
    assert r.halted == "time-limit", (r.halted, r.unmetered)
    assert "runs-for-at-most" not in r.unmetered, r.unmetered


#: The two COUNTING ceilings, with the line to fix and the meter each reads.
#: `Limits` carries four ceiling fields and the guard covered two of them.
COUNTED = (
    ("tokens_at_most", "tokens-at-most", "tokens", "no number of tokens"),
    ("tool_calls_at_most", "tool-calls-at-most", "tool calls", "no number of tool calls"),
)


@pytest.mark.parametrize("attr,line,noun,because", COUNTED)
@pytest.mark.parametrize("figure", UNREACHABLE_FIGURES)
def test_every_ceiling_the_object_carries_goes_the_same_way(
    figure: float, attr: str, line: str, noun: str, because: str
) -> None:
    """The guard was enumerated over FIELDS, and the defect is a property of the
    FIGURE — so it kept escaping through whichever field nobody had listed.

    `__post_init__` walked the money field alone for a round and `wall_clock_s`
    was silent; the test above is what closed that. It then walked the two
    FLOATS, and `tokens_at_most` and `tool_calls_at_most` were silent for exactly
    the same reason: `at >= limit` is one comparison, and `nan` and `inf` defeat
    it identically whatever it is counting. Measured on this same harness, with
    the two-float guard in place and no other edit::

        Limits(tokens_at_most=inf)     rows=['tokens-at-most']
                                       reached(meter@1e12 tokens) -> None
                                       unmetered=()
        Limits(tool_calls_at_most=inf) rows=['tool-calls-at-most']
                                       reached(meter@1e12 calls) -> None
                                       unmetered=()

    A row built, a comparison nothing can satisfy, and every honesty channel
    empty — the before-picture at the top of this file, two fields over. The
    second port had it too, through its own door: measured on live `limits.ts`,
    `{...limitsFrom({}), tokensAtMost: Infinity}` gave
    `rows=["tokens-at-most"] reached@1e9=null caps=[]`.

    The authored route is shut on both (`whole(json.loads('1e999'))` is `None`,
    and `pact check` refuses the line before that), so this is the CONSTRUCTOR
    door — the door this whole file exists for, and one written at more than
    forty `Limits(` sites across this directory.

    The list is `limits._CEILING_FIELDS` now rather than a pair somebody
    remembered, and `_unmetered_caveats` grew a remedy for each `reads` it can
    produce: a `reads` that table does not know falls through to *"nothing to
    type — what can be measured depends on what the model reports back"*, which
    for a figure the author typed is the wrong-diagnosis failure that function
    exists to remove.

    Mutation: delete either counting row from `_CEILING_FIELDS` in `limits.py`
    and this test goes red on that field, in both parametrisations, on the row,
    on the channel and on the sentence.
    """
    spec, r = _run_with(Limits(**{attr: figure}))

    assert [c.field for c in spec.limits.ceilings()] == [], (
        f"a `{line}` row no count can ever be at or above is still in the "
        "algebra: " + str(spec.limits.ceilings())
    )
    assert getattr(spec.limits, attr) is None, getattr(spec.limits, attr)
    assert line in r.unmetered, (
        f"`{line}: {figure}` held nothing and the run said nothing about it: "
        f"unmetered={r.unmetered}"
    )
    assert r.halted == "step-limit", (r.halted, r.stopped_by)

    # And the REMEDY names the kind of figure that line takes. A right field
    # name with a wrong remedy is the failure `_unmetered_caveats` was written
    # to remove, and a `reads` with no remedy of its own lands on the
    # transport's — *"nothing to type"* — for a figure the author typed.
    said = [c for c in _caveats(Limits(**{attr: figure})).splitlines() if line in c]
    assert said, (line, _caveats(Limits(**{attr: figure})))
    assert any(f"{because} can ever be at or above the figure written" in c for c in said), (
        because, said
    )
    assert any(f"write a whole number of {noun} on that line" in c for c in said), (
        noun, said
    )
    assert not any("nothing to type" in c for c in said), said


def test_a_duration_that_holds_nothing_is_not_sent_to_the_money_line() -> None:
    """Two kinds of unreachable ceiling, two remedies, and folding them lies.

    *"No amount of money can ever be at or above the figure written … fix: write
    an amount of money on that line"* is exactly as wrong for `runs-for-at-most:
    inf` as the transport's *"nothing to type"* was for `cost-per-request-under:
    NaN USD` — a right field name with a wrong diagnosis and a remedy pointing at
    a line with no money on it. `Limits.held_nothing()` carries `Ceiling.reads`
    beside each name so `_unmetered_caveats` can tell them apart.
    """
    said = _caveats(Limits(wall_clock_s=math.inf, cost_per_request_under=float("nan")))

    assert "no length of time can ever be at or above the figure written" in said, said
    assert "no amount of money can ever be at or above the figure written" in said, said
    for line in said.splitlines():
        assert not ("runs-for-at-most" in line and "cost-per-request-under" in line), (
            "the two remedies were run together into one sentence: " + line
        )
        if "runs-for-at-most" in line:
            assert "write a length of time on that line" in line, line
            assert "amount of money" not in line, (
                "a duration ceiling was sent to the money line: " + line
            )


def test_the_latency_reader_reports_the_cap_it_dropped() -> None:
    """`Slo` reads the same authored line, and its drop shipped without a report.

    `Slo.__post_init__` deleted the amount and the currency and recorded nothing:
    `Slo.unmetered()` returned `self.written`, which is built from
    `first-reply-within` and `per-word-under` only and could never carry this
    name. The coupling to `Limits` — both are built from one authored `limits:`
    block — is the only reason that was invisible. Broken here by giving the spec
    an EMPTY `limits:` and putting the figure on the `slo` alone. Measured before
    the record existed, through this same six-step harness::

        slo cap nan -> cap=None cur='' unmetered=() never_reached=() spent=6000.0
        slo cap inf -> cap=None cur='' unmetered=() never_reached=() spent=6000.0

    Six thousand dollars under a `surface: S-GOV, tier: core` cap the author
    typed, silently deleted, with every honesty channel empty — the silent
    degradation T7 and FR-8.1.1 forbid, inside the change that exists to stop it.
    For `inf` it was a strict regression: `against_the_catalogue` used to say
    something wrong, and then said nothing at all.
    """
    for figure in UNREACHABLE_FIGURES:
        spec = replace(
            SPEC, max_steps=6, limits=Limits(),
            slo=Slo(cost_per_request_under=figure, cost_currency="USD"),
        )
        r = asyncio.run(
            run(spec, Spending(_never_finishes()), "please refund my lamp", TOOLS)
        )
        assert r.spent >= 6_000.0, r.spent
        assert "cost-per-request-under" in r.unmetered, (
            f"`Slo` was handed {figure!r}, dropped it, and said nothing: "
            f"unmetered={r.unmetered} spent={r.spent}"
        )
    # And the control: a cap that is a figure is not named.
    spec = replace(
        SPEC, max_steps=6, limits=Limits(),
        slo=Slo(cost_per_request_under=0.05, cost_currency="USD"),
    )
    r = asyncio.run(run(spec, Spending(_never_finishes()), "please refund", TOOLS))
    assert "cost-per-request-under" not in r.unmetered, r.unmetered


def test_the_name_is_said_once_when_both_readers_read_one_line() -> None:
    """`Limits` and `Slo` both read `cost-per-request-under:` off one block.

    Both are right to report it and the LIST is what must say a thing once —
    `_unmetered_caveats` joins the array into a sentence, so a duplicate reads as
    *"cost-per-request-under, cost-per-request-under"*, and a `watches:`
    subscriber gets the name twice in one payload.
    """
    document = {"agents": {"desk": {
        "name": "Refund Desk", "description": "Decides refunds",
        "instructions": "Decide.",
        "limits": _block("NaN USD"),
    }}}
    spec = AgentSpec.from_document(document, "desk")
    assert spec.limits.nothing_can_reach == ("cost-per-request-under",)
    assert spec.slo.cap_nothing_can_reach is not None, "both readers took the line"

    r = asyncio.run(run(spec, Spending(_never_finishes()), "please refund", TOOLS))
    assert list(r.unmetered).count("cost-per-request-under") == 1, r.unmetered


# -------------------------------------------------- and it stops saying it


def _team_document(member_cap: object) -> dict:
    """A supervisor with one specialist, built in code — the route under test.

    Not loaded from a folder, and it could not be: `pact check` and `pact show`
    both refuse `cost-per-request-under: NaN USD` with `schema/below-the-floor`,
    which is the authored door doing its job. A document assembled in code is the
    only way a member can carry one, and it is the way this whole file is about.
    """
    checker: dict[str, object] = {
        "name": "Policy Checker",
        "description": "Checks the written policy.",
        "instructions": "Say whether it is covered.",
        "limits": {"steps-at-most": 2, "when-it-runs-out": "stop-and-say-so"},
    }
    if member_cap is not None:
        checker["limits"]["cost-per-request-under"] = member_cap  # type: ignore[index]
    return {
        "agents": {
            "desk": {
                "name": "Refund Desk",
                "description": "Decides refunds",
                "instructions": "Ask the checker, then decide.",
                "team": {"policy-checker": "Checks the written policy."},
                "teamwork": {
                    "waits-for": "everyone",
                    "starts": "all-at-once",
                    "divides-the-budget": "by-share",
                    "shares": {"policy-checker": "100%"},
                    "if-someone-fails": "carry-on",
                },
                "limits": {
                    "cost-per-request-under": "0.10 USD",
                    "steps-at-most": 4,
                    "when-it-runs-out": "stop-and-say-so",
                },
            },
            "policy-checker": checker,
        }
    }


class Cheap(ReferenceTransport):
    """Prices every call, and cheaply — so nothing lands on `unmetered` unless
    a ceiling genuinely holds nothing."""

    name = "cheap"
    prices_money = True

    def usage(self) -> tuple[int, float]:
        return 10, 0.001


class Uncounted(ReferenceTransport):
    """Prices its calls and counts no tokens. The positive control's transport.

    `tokens-at-most` run through this genuinely lands on `unmetered`, for the
    OTHER reason — nothing said how many tokens a call carried — so the empty
    lists below can be told from a channel nobody is speaking on. It declares
    `prices_money` so the join policy's money share does NOT come along too:
    B6 split the two questions precisely so a transport can answer one and not
    the other, and the control wants exactly one name on the list.
    """

    name = "uncounted"
    prices_money = True


def _ran_the_team(
    member_cap: object, member_tokens: int | None = None
) -> list[tuple[str, ...]]:
    """Every `session.limit.failed` the whole run emitted, parent and member.

    The member's run shares the parent's bus, so what a delegated agent reports
    about its own ceilings arrives here. That is the only way out: the member's
    `RunResult` is consumed inside the join and never reaches the caller, and a
    test that reached inside the join for it would be testing the join rather
    than the report.

    `member_tokens` exists only for the POSITIVE CONTROL below, and it exists
    because three assertions in this section were assertions of ABSENCE over a
    channel nothing here proved was alive. Measured: with
    `harness.py`'s `if result.unmetered:` turned into `if False and
    result.unmetered:` — deleting the whole `session.limit.failed` emission —
    this file reported `19 passed`. Writing `tokens-at-most` on the member and
    running it through a transport with no `usage()` puts a name on this list
    for a reason B8 is not about, so `== []` afterwards means *the channel was
    live and stayed quiet*.
    """
    document = _team_document(member_cap)
    if member_tokens is not None:
        document["agents"]["policy-checker"]["limits"]["tokens-at-most"] = member_tokens
    desk = AgentSpec.from_document(document, "desk")
    asking = Script([
        Turn("asking", (ToolCall("policy-checker", {"question": "is it covered?"}),)),
        Turn("Approved."),
    ])
    member_transport = Uncounted if member_tokens is not None else Cheap
    bus = Bus()
    said: list[tuple[str, ...]] = []
    bus.on("session.limit.failed", lambda e: said.append(tuple(e.payload["limits"])))
    result = asyncio.run(
        run(desk, Cheap(asking), "please refund my lamp", {},
            ask_member=delegate_by_running(
                document, lambda _m: member_transport(Script([Turn("covered")])), bus=bus),
            bus=bus)
    )
    assert result.halted == "final", (result.halted, result.output)
    return said


def test_the_channel_the_three_assertions_below_read_is_alive() -> None:
    """The positive control, and without it the three `== []` below say nothing.

    A member with `tokens-at-most` run on a transport that reports no `usage()`
    is a ceiling nothing measured — the OTHER reason a name reaches `unmetered`,
    and one this issue does not touch. It has to arrive on this exact list,
    through the same delegation and the same shared bus, or the empty lists in
    the next two tests are compatible with the emission having been deleted.
    Measured: deleting it leaves this file green without this test.
    """
    assert _ran_the_team(None, member_tokens=500) == [("tokens-at-most",)]


def test_a_member_given_a_real_share_stops_saying_its_cap_holds_nothing() -> None:
    """A member whose own cap is `NaN USD` is HANDED one that is a figure.

    `harness._delegating` does `replace(member.limits, cost_per_request_under=
    allowed)`, and `replace` copies every field it is not given — so the record
    the guard had made about the member's own cap travelled across untouched and
    sat beside the join policy's real 0.10 USD ceiling. Measured with only the
    setting half of the guard in place::

        member: cap=0.1  nothing_can_reach=('cost-per-request-under',)
        session.limit.failed: [('cost-per-request-under',)]

    which is a run that can halt at `cost-limit` on the very field it has just
    told the author it could not promise. A real figure arriving clears the
    record, which is why `__post_init__` has an arm for it.

    BOTH readers of the line are handed the share, not just the enforcing one.
    `Slo` reads `cost-per-request-under:` off the same authored block and reports
    it on the same `unmetered` array, so replacing only `member.limits` left the
    member enforcing 0.10 USD and still saying the cap held nothing — measured
    here as `[('cost-per-request-under',)]` after the `Limits` half was fixed.
    """
    said = _ran_the_team("NaN USD")

    assert said == [], (
        "a member enforcing the join policy's real 0.10 USD share still reported "
        f"a ceiling it said it could not promise: {said}"
    )


def test_a_member_with_no_cap_of_its_own_is_the_same_and_a_real_one_too() -> None:
    """The two controls beside it, so the test above is about the NaN and not
    about delegation being quiet in general.

    Quiet, not dead: `test_the_channel_the_three_assertions_below_read_is_alive`
    above puts a name on this same list through this same helper, so an empty
    list here is a measurement rather than an absence of one.
    """
    assert _ran_the_team(None) == [], "a member with no cap of its own"
    assert _ran_the_team("0.50 USD") == [], "a member with a cap that is a figure"


def _payload_of(limits: Limits, transport: type[ReferenceTransport]) -> dict:
    """The one `session.limit.failed` a run emits, off the real bus."""
    spec = replace(SPEC, max_steps=2, tools=(), limits=limits)
    bus = Bus()
    seen: list[dict] = []
    bus.on("session.limit.failed", lambda e: seen.append(dict(e.payload)))
    asyncio.run(run(spec, transport(Script([Turn("hello")])), "hello", {}, bus=bus))
    assert len(seen) == 1, seen
    return seen[0]


def test_the_machine_readable_report_carries_the_reason_the_prose_does() -> None:
    """`session.limit.failed` said one thing for two reasons, and named the
    transport for the one the transport did not cause.

    `_unmetered_caveats` splits the prose because *"nothing to type — what can be
    measured depends on what the model reports back"* is a wrong diagnosis for a
    figure the author typed. The split was applied to the sentence only.
    Measured, both reasons through the real bus before this::

        figure-nothing-can-reach -> {'limits': ['cost-per-request-under'],
                                     'transport': 'spending', ...}
        transport-cannot-price   -> {'limits': ['cost-per-request-under'],
                                     'transport': 'unpriced',  ...}

    Byte-identical apart from the transport's name, with the transport named in
    the case where the transport is innocent. This event is an address an author
    may subscribe a `watch:` to (`watches.EMITTED`, `spec/schema.yaml`), B6
    requires it to carry the same finding as `unmetered`, and T7 asks for the
    machine-readable report and not only the prose. The fix also made this newly
    reachable: before it, a code-built NaN cap emitted no event at all.
    """
    unreachable = _payload_of(Limits(cost_per_request_under=float("nan")), Spending)
    unpriced = _payload_of(Limits(cost_per_request_under=0.05), ReferenceTransport)

    assert unreachable["limits"] == ["cost-per-request-under"], unreachable
    assert unpriced["limits"] == ["cost-per-request-under"], unpriced
    assert unreachable["held_nothing"] == ["cost-per-request-under"], unreachable
    assert unpriced["held_nothing"] == [], (
        "the transport could not price this run, which is not the author's "
        f"figure holding nothing: {unpriced}"
    )
    # The two payloads must not be the same payload, which is what they were.
    assert unreachable["held_nothing"] != unpriced["held_nothing"]
    # And the `Slo` half reaches it too, on a spec whose `limits:` is empty.
    from_slo = replace(
        SPEC, max_steps=2, tools=(), limits=Limits(),
        slo=Slo(cost_per_request_under=math.inf, cost_currency="USD"),
    )
    bus = Bus()
    seen: list[dict] = []
    bus.on("session.limit.failed", lambda e: seen.append(dict(e.payload)))
    asyncio.run(run(from_slo, Spending(Script([Turn("hello")])), "hello", {}, bus=bus))
    assert seen and seen[0]["held_nothing"] == ["cost-per-request-under"], seen


# ------------------------------------------- and the sentence a person reads


def _caveats(limits: Limits, transport: type[ReferenceTransport] = Spending) -> str:
    """Everything a scored run said about how it differed from a real one."""
    spec = replace(SPEC, max_steps=2, tools=(), limits=limits)
    _, _, caveats, _ = _run_every_case(
        spec,
        [Case(key="greets", when="Say hello.", expect={"greeting": "hello"})],
        [],
        lambda: transport(Script([Turn("hello")])),
        {"agents": {}},
    )
    return "\n".join(caveats)


def test_the_report_sends_the_author_to_the_line_and_not_to_the_transport() -> None:
    """The one sentence this whole change produces for a person to read.

    It said the opposite of the remedy. `scoring` renders every member of
    `unmetered` with one hard-coded ending — *"fix: nothing to type — what can be
    measured depends on what the model reports back"* — which is exactly right
    for a ceiling no transport could count and exactly wrong for a figure the
    author typed. There IS something to type, and the model reports nothing
    that bears on it. A right field name with a wrong diagnosis and a remedy
    saying *do not act* is worse than silence, because it closes the question.
    """
    said = _caveats(Limits(cost_per_request_under=float("nan")))

    assert "cost-per-request-under" in said, said
    assert "no amount of money can ever be at or above the figure written" in said, said
    assert "fix: write an amount of money on that line" in said, said
    assert "0.05 USD" in said, "and the line to type, not just the instruction"
    assert "what can be measured depends on what the model reports back" not in said, (
        "the transport's remedy was attached to a figure the author wrote:\n" + said
    )


def test_the_other_reason_a_ceiling_lands_there_keeps_its_own_sentence() -> None:
    """Two reasons, two sentences, and the split is what makes either readable.

    `tokens-at-most` against a stand-in with no `usage()` genuinely IS *"nothing
    to type"*. Folding the two would have to lie about one of them.
    """
    said = _caveats(
        Limits(cost_per_request_under=float("inf"), tokens_at_most=500),
        transport=ReferenceTransport,
    )

    assert "tokens-at-most" in said and "nothing to type" in said, said
    assert "no amount of money can ever be at or above the figure written" in said, said
    for line in said.splitlines():
        assert not ("tokens-at-most" in line and "cost-per-request-under" in line), (
            "the two reasons were run together into one sentence: " + line
        )


def test_the_latency_reader_does_not_keep_a_copy_of_the_unreachable_cap() -> None:
    """`Slo.from_mapping` is the THIRD reader of `cost-per-request-under:`.

    So the answer had to become a property of the cap rather than of two of its
    three readers. `NaN USD` went quiet here rather than wrong —
    `against_the_catalogue` short-circuits on it, because `cheapest > nan` and
    `dearest < nan` are both false. `inf USD` did not. Measured before the
    guard, with `tokens-at-most: 1000` and a model priced at 1 USD/Mtok::

        `cost-per-request-under: inf USD` cannot be reached on a-model. The
        whole of `tokens-at-most: 1000` costs at most 0.0010 at the published
        price, so the run always stops on tokens and the money cap never binds.
        fix: lower `cost-per-request-under` below 0.0010 if you meant it to
        govern, or delete it ...

    A true sentence with the wrong reason in it: the cap is unreachable because
    it is infinity, not because a thousand tokens are cheap, and that sentence
    reads identically for a perfectly sensible cap of 1.00 USD. An author sent
    to *"lower `cost-per-request-under` below 0.0010"* has been pointed at the
    wrong line.
    """
    priced = (lambda went_in, came_out: (went_in + came_out) * 1e-6)

    for written in UNREACHABLE:
        slo = Slo.from_mapping({"cost-per-request-under": written})
        assert slo.cost_per_request_under is None, (written, slo)
        # And the CURRENCY is kept, which this assertion used to have the other
        # way round. `USD` is the half of the authored line that parsed
        # perfectly; deleting it destroyed something true, bought nothing —
        # `CeilingsDisagree.currency` is its only reader and
        # `against_the_catalogue` returns above it once the amount is gone — and
        # in `Limits` the same deletion made two members of one team print
        # different sentences for the same stop. `Limits.__post_init__` carries
        # that measurement.
        assert slo.cost_currency == "USD", (written, slo)
        assert against_the_catalogue(slo, 1000, "a-model", priced) is None, written
        # The figure is not merely gone: it is RECORDED, and that is what
        # `unmetered()` answers out of. The drop shipped without the report for a
        # round, and `Slo.written` could never have carried this name.
        assert slo.cap_nothing_can_reach is not None, (written, slo)
        assert slo.unmetered() == ("cost-per-request-under",), (written, slo)

    # And the control: two ceilings that really do disagree still say so.
    real = Slo.from_mapping({"cost-per-request-under": "0.01 USD"})
    disagree = against_the_catalogue(real, 1_000_000, "a-model", priced)
    assert disagree is not None and "cost-per-request-under" in str(disagree)


# ------------------------------------------------------------ the second port


def _drive(spec_payload: str, prices_money: bool = False) -> subprocess.CompletedProcess:
    # The script never finishes — one turn with a tool call in it, which the
    # scripted model repeats — so the run reaches `steps-at-most: 6` and
    # `stoppedBy` carries a ceiling rather than being null whatever happens.
    # It was a single `{"text": "done"}` turn, and that made every `stoppedBy`
    # assertion on this side vacuously true.
    #
    # `prices_money` is argv[6], and argv[5] is the tool answers — `""` there
    # means "the defaults", which is what every call in this file used before the
    # flag existed. See `run-trace.ts` for why the flag is the only way the
    # SHIPPED `unmetered` array can answer the question this file asks.
    return subprocess.run(
        ["node", "--experimental-strip-types", "src/run-trace.ts",
         spec_payload,
         json.dumps({"turns": [
             {"text": "still working",
              "toolCalls": [{"name": "zendesk", "args": {}}]}
         ]}),
         "please refund my lamp",
         "",
         "prices-money" if prices_money else ""],
        cwd=TS_DIR, capture_output=True, text=True,
    )


def _payload(written: str | None) -> str:
    spec: dict[str, object] = {
        "name": "Refund Desk",
        "instructions": "Decide, then issue the refund.",
        "tools": [{"name": "zendesk", "description": "read the ticket"}],
        "maxSteps": 6,
    }
    if written is not None:
        spec["limits"] = _block(written)
    return json.dumps(spec)


def _probe() -> str | None:
    """`None` if the second port RUNS here, otherwise why it does not.

    Settled ONCE, against a document with no `limits:` block — nothing this file
    is about — for the reason `test_both_ports_read_every_way_a_spend_cap_is_
    written.py` gives at length: the suite's usual
    ``returncode != 0 -> pytest.skip`` idiom reports a REGRESSION in the port
    under test as a skip, so a `throw` in `limitsFrom` would turn this file
    green. After the probe, a non-zero return can only mean *this input* crashed
    it, and that is a failure.
    """
    try:
        out = _drive(_payload(None))
    except OSError as exc:                      # no `node` on PATH at all
        return f"node not runnable: {exc}"
    return None if out.returncode == 0 else f"node/AI SDK unavailable: {out.stderr[-300:]}"


UNAVAILABLE = _probe()


def _ts(written: str, prices_money: bool = False) -> dict:
    if UNAVAILABLE:
        pytest.skip(UNAVAILABLE)
    out = _drive(_payload(written), prices_money=prices_money)
    if out.returncode != 0:
        pytest.fail(
            f"the second port ran a document with no `limits:` block and then "
            f"exited {out.returncode} on `cost-per-request-under: {written!r}`. "
            f"That is this input crashing it, not a missing runtime.\n"
            f"{out.stderr[-2000:]}"
        )
    return json.loads(out.stdout)


@pytest.mark.parametrize("written", UNREACHABLE)
def test_the_second_port_names_the_same_cap_on_the_same_channel(written: str) -> None:
    """Through `run-trace.ts`, which is the shape the two runtimes are compared
    on — a unit test on `limitsFrom` alone would prove the reader and not the
    report, and the reader was never the thing an author reads.

    **Driven with `prices-money`, and that is what makes it bite.** Read without
    it, the whole TypeScript half of this file rested on `ceilingsNothingCanReach`,
    a field `run-trace.ts` computes for the Python suite and no shipped consumer
    of the second port reads. Measured: with the `!nothingCanReach(...)` guard
    deleted from `ceilings()` in `limits.ts`, every key of this port's output on
    this very fixture was byte-identical to the unmutated run EXCEPT that
    projection — `unmetered` stayed `["cost-per-request-under"]`, supplied by
    `unmeterable()` for the B6 *"nothing here can price it"* reason, and
    `halted`, `stoppedBy`, `output` and `unenforced` did not move. So the guard
    was held by the test driver's own arithmetic.

    `prices-money` switches the B6 reason off — it declares the transport CAN be
    priced, and touches nothing else, so the money meter still never leaves zero
    — and then the only thing that can put this field on the shipped `unmetered`
    array is the figure. The assertion below is on that array.

    **THE ROW THAT WAS NOT BUILT is asserted too, and that is what holds the
    guard.** `ceilingsNothingCanReach` derives its answer off `ceilings()`
    precisely so the row refused and the name reported cannot come apart — and
    that coupling was argued in a COMMENT in `limits.ts` and held by nothing.
    Measured on the current source, two one-line edits: re-derive
    `ceilingsNothingCanReach` off the `nothingCanReach` predicate instead of off
    `ceilings()` (which reads as a simplification and removes a `Set`), AND
    delete the money guard from `ceilings()`. Either edit ALONE reddens this
    file; the PAIR left it green — `54 passed, 4 skipped` both before and after —
    with the port building a `cost-per-request-under` row no spend can satisfy
    and shipping the name twice on `unmetered` in its own default configuration.
    Every assertion in the file read only the projection the two edits agree
    about. `run-trace.ts` now projects `ceilingRows` — the fields `ceilings()`
    actually built — and the assertion below is on that, so it bites the
    `ceilings()` guard however `ceilingsNothingCanReach` happens to be written.

    **BY EQUALITY, and WITHOUT `prices-money` as well.** Membership under
    `prices-money` was the one configuration in which the damage is invisible:
    measured under the mutation above, `pm=prices-money` gives
    `['cost-per-request-under']` while `pm=off` — what `VercelAITransport`
    actually declares — gives `['cost-per-request-under',
    'cost-per-request-under']`, because `harness.ts` concatenates
    `unmeterable()` and `ceilingsNothingCanReach()` with no dedupe where
    `harness.py` has `dict.fromkeys`. No assertion in this repository pinned that
    array by equality, so the second port could say the same thing twice to an
    author and nothing would notice.
    """
    ts = _ts(written, prices_money=True)

    assert ts["unmetered"] == ["cost-per-request-under"], (
        f"`cost-per-request-under: {written}` holds nothing in the second port "
        f"and the second port did not say exactly that once on the array a "
        f"person reads: unmetered={ts['unmetered']}"
    )
    # And on the projection too, which is how the Python suite tells the two
    # reasons apart. `harness.ts` merges them into one `unmetered` array on
    # purpose, because *"cannot promise"* is true of both.
    assert ts["ceilingsNothingCanReach"] == ["cost-per-request-under"], (
        f"`{written}` is on `unmetered` because nothing can PRICE this "
        "transport, not because nothing can REACH the cap — the second port has "
        f"stopped reading the figure: {ts['ceilingsNothingCanReach']}"
    )
    # THE ROW. Not derived from the projection above and not derived from the
    # predicate: this is what `ceilings()` handed `reached`, and a money row here
    # is a row the comparison could never satisfy.
    assert "cost-per-request-under" not in ts["ceilingRows"], (
        f"the second port built a money row for `{written}`, which `reached` can "
        f"never satisfy: ceilingRows={ts['ceilingRows']}"
    )
    # The same document WITHOUT the flag — the configuration a real consumer of
    # this port runs in, and the one the equality above cannot see. The name
    # arrives for the B6 reason as well as this one, and it arrives ONCE.
    shipped = _ts(written)
    assert shipped["unmetered"] == ["cost-per-request-under"], (
        "the second port named one line twice, or stopped naming it, in the "
        f"configuration `VercelAITransport` actually declares: {shipped['unmetered']}"
    )
    assert "cost-per-request-under" not in shipped["ceilingRows"], shipped["ceilingRows"]
    # The control on the flag itself: WITHOUT it the array cannot answer, and it
    # says so by carrying the field for a cap that IS a figure too. An assertion
    # above that would be true either way is one this line refuses to let stand.
    real = _ts("0.05 USD")
    assert real["unmetered"] == ["cost-per-request-under"], (
        "the B6 reason has stopped firing, so `prices-money` above is no longer "
        f"switching anything off and the assertion on it proves nothing: {real['unmetered']}"
    )
    # …and the control's row IS built, so the assertion on the absent one above
    # is about the figure and not about this port having forgotten money.
    assert real["ceilingRows"] == ["cost-per-request-under"], real["ceilingRows"]
    # The STEP ceiling is what ended it, and it says which. Not a vacuous
    # assertion: the same script under `-inf USD` stops at
    # `cost-per-request-under` on step zero, which is what
    # `test_the_second_port_still_stops_on_the_one_cap_a_run_can_reach` holds.
    assert ts["halted"] == "step-limit", (ts["halted"], ts["stoppedBy"])
    assert ts["stoppedBy"] is not None
    assert ts["stoppedBy"]["limit"] == "steps-at-most", (
        "nothing can be at or above this cap, so it cannot be what stopped the "
        f"run: {ts['stoppedBy']}"
    )


@pytest.mark.parametrize("written", UNREACHABLE)
def test_both_ports_name_it_for_one_document(written: str) -> None:
    """One document, two runtimes, one answer.

    Asserted as two facts and not as one equality: `ts == mine` is `False ==
    False` when BOTH ports regress, which is the case a portability claim exists
    to catch and the one an equality cannot see.

    `prices-money` for the same reason the test above gives at length: without it
    the TypeScript assertion here was satisfied by `unmeterable()`'s B6 finding
    and stayed green with the second port's guard deleted. This half of the pair
    was decoration; the flag is what makes it a claim about the figure.

    The TypeScript side is asserted by EQUALITY and the Python side by
    membership, and the asymmetry is the point rather than an oversight. This
    port's `unmetered` has exactly one thing to say about this document, and
    `harness.ts` has no `dict.fromkeys` — so equality is the only assertion that
    can see it say that thing twice. The reference port's array carries the
    `settings.` and latency names too, and pinning it whole here would make this
    test fail for reasons that have nothing to do with the claim.
    """
    ts = _ts(written, prices_money=True)
    _, mine = _run_here(written)

    assert ts["unmetered"] == ["cost-per-request-under"], ts["unmetered"]
    assert "cost-per-request-under" in mine.unmetered, mine.unmetered
    # And the same document with no flag, which is what a consumer of this port
    # runs — the configuration in which a duplicate is possible at all.
    assert _ts(written)["unmetered"] == ["cost-per-request-under"]


def _in_the_second_port(source: str) -> dict:
    """Run one expression inside `adapters/typescript/src/limits.ts`.

    A UNIT probe, deliberately, and the only honest shape for the case below.
    Everywhere else in this file the second port is driven through
    `run-trace.ts`, because *"a unit test on `limitsFrom` alone would prove the
    reader and not the report"*. The wall-clock ceiling cannot be driven that
    way: `run-trace.ts` builds its `Limits` with `limitsFrom`, and
    `limitsFrom({"runs-for-at-most": "inf"}).wallClockS` is `null` — the reader
    refuses the figure, exactly as `seconds()` does in the first port. The door
    that is open is an object literal, which no JSON payload can reach, so a
    probe that builds one is the report for this case rather than a shortcut
    past it.
    """
    if UNAVAILABLE:
        pytest.skip(UNAVAILABLE)
    out = subprocess.run(
        ["node", "--experimental-strip-types", "--input-type=module", "-e", source],
        cwd=TS_DIR, capture_output=True, text=True,
    )
    if out.returncode != 0:
        pytest.fail(f"the second port could not run this probe:\n{out.stderr[-2000:]}")
    return json.loads(out.stdout)


#: Every ceiling `limits.ts` builds a row for, as
#: `(the field on the object, the line it reports, a figure that IS one)`.
#: The same four `Limits._CEILING_FIELDS` carries in the reference port.
SECOND_PORT_CEILINGS = (
    ("toolCallsAtMost", "tool-calls-at-most", 5),
    ("wallClockS", "finishes-within", 30),
    ("costPerRequestUnder", "cost-per-request-under", 0.05),
    ("tokensAtMost", "tokens-at-most", 1000),
)


@pytest.mark.parametrize("attr,line,real", SECOND_PORT_CEILINGS)
def test_the_second_port_refuses_every_unreachable_ceiling_too(
    attr: str, line: str, real: float
) -> None:
    """Every ceiling is guarded in both ports, or one document has two answers.

    The first port walks `_CEILING_FIELDS` at the one moment every route into a
    `Limits` meets. This port has no construction hook, so its guard lives at
    `ceilings()`, which is the read every ceiling goes through — and it guarded
    the money row only, then the money and clock rows. Measured before each
    repair, on plain object spreads::

        {...limitsFrom({}), wallClockS: Infinity}
          -> rows=['finishes-within']     caps=[]
        {...limitsFrom({}), tokensAtMost: Infinity}
          -> rows=['tokens-at-most']      caps=[]  reached@1e9=null
        {...limitsFrom({}), toolCallsAtMost: Infinity}
          -> rows=['tool-calls-at-most']  caps=[]  reached@1e9=null

    A live row nothing can ever be at or above, reported nowhere — and, once the
    first port started reporting it, the two ports answering differently about
    one object, which is the ambiguity the second port exists to expose.
    `runs-for-at-most` / `finishes-within` and `tokens-at-most` are all in §7.28
    list A, the keys the byte-identical-trace claim COVERS.

    **The ROW is asserted and not only the projection**, which is what makes this
    hold the guard rather than the arithmetic beside it:
    `ceilingsNothingCanReach` derives off `ceilings()`, so an assertion that
    reads only the projection goes green when BOTH are changed together — a pair
    of one-line edits that left the whole suite passing, measured. `rows == []`
    reads `ceilings()` directly.
    """
    got = _in_the_second_port(f"""
      import {{ ceilings, ceilingsNothingCanReach, limitsFrom, reached, newMeter }}
        from "./src/limits.ts";
      const at = (v) => {{ const l = {{ ...limitsFrom({{}}), {attr}: v }};
        const m = newMeter(0); m.toolCalls = 1e12; m.tokens = 1e12; m.money = 1e12;
        return {{ rows: ceilings(l).map((c) => c.field),
                 caps: ceilingsNothingCanReach(l),
                 hit: reached(l, m, 1e9) && reached(l, m, 1e9).ceiling.field }}; }};
      console.log(JSON.stringify({{
        inf: at(Infinity), nan: at(NaN), minus: at(-Infinity), real: at({real}),
        authored: limitsFrom(JSON.parse(
          '{{"runs-for-at-most":"inf","tokens-at-most":1e999,"tool-calls-at-most":1e999,'
          + '"cost-per-request-under":"inf USD"}}')),
      }}));
    """)

    # The authored route is shut on every one of them, which is what makes the
    # object literal the door under test. Read through `JSON.parse`, because that
    # is how `run-trace.ts` receives a document and `1e999` is `Infinity` there —
    # `pact check` refuses all four spellings before this, measured with the
    # shipped binary (`'tokens-at-most' should be a whole number, but it is some
    # text`, `schema/below-the-floor` for the money one).
    for key in ("wallClockS", "tokensAtMost", "toolCallsAtMost", "costPerRequestUnder"):
        assert got["authored"][key] is None, (
            "the authored route is supposed to be shut, which is what makes the "
            f"object literal the door under test: {key}={got['authored'][key]}"
        )
    for figure in ("inf", "nan"):
        assert got[figure]["rows"] == [], (attr, figure, got[figure])
        assert got[figure]["caps"] == [line], (attr, figure, got[figure])
        assert got[figure]["hit"] is None, (
            "a row was built that no reading can ever be at or above, and the "
            f"meter is holding 1e12 of everything: {got[figure]}"
        )
    # And the two controls, matching the first port's exactly: `-inf` fires on
    # the first check and is a wrong ceiling rather than an absent one, and a
    # figure that IS one still builds its row and is still reachable.
    assert got["minus"]["rows"] == [line] and got["minus"]["caps"] == []
    assert got["real"]["rows"] == [line] and got["real"]["caps"] == []
    assert got["real"]["hit"] == line, (attr, got["real"])


def test_the_second_port_leaves_a_cap_that_is_a_figure_alone() -> None:
    """The control on that side too: a real cap is not named as an unusable one,
    or the report fires on every run and stops being read.

    It is not named as STOPPING anything either, and that is honest rather than
    a miss: `VercelAITransport` drives a scripted model bound to no catalogue
    row, so it declares `pricesMoney = false` and the money meter never moves in
    this port. The step ceiling is what ends the run, and the Python half above
    carries the one that spends.

    **Read on `ceilingsNothingCanReach` and not on `unmetered`, and the difference
    is B6.** This used to assert `"cost-per-request-under" not in unmetered`,
    which was true only while the port claimed — falsely — that it could price
    its calls. Once that transport declared what it is, every money ceiling this
    port runs is on `unmetered` for the *"nothing here can price it"* reason, so
    the old assertion could no longer see which of the two findings had fired
    and would have gone green on the port forgetting how to read a figure.
    `run-trace.ts` projects the two apart for the suite; `harness.ts` keeps them
    merged for the author, where *"cannot promise"* is true of both.
    """
    ts = _ts("0.05 USD")
    assert "cost-per-request-under" not in ts["ceilingsNothingCanReach"], (
        "a cap that IS a figure was named as one no spend can reach: "
        + str(ts["ceilingsNothingCanReach"])
    )
    assert "cost-per-request-under" in ts["unmetered"], (
        "and it is still reported, because nothing in this port can price a "
        f"scripted model — the other finding, on the same array: {ts['unmetered']}"
    )
    assert ts["stoppedBy"]["limit"] == "steps-at-most", ts["stoppedBy"]


def test_the_second_port_still_stops_on_the_one_cap_a_run_can_reach() -> None:
    """`-inf USD`, deliberately not guarded, and the reason the assertions
    above are not decoration.

    `spent >= -Infinity` is true of every spend including zero, so this fires on
    step ZERO and stops the run loudly. It is a wrong ceiling, not an absent
    one, nothing about it is silent, and it is the only value that exercises the
    non-finite arm of `round()` in `limits.ts`. Guarding it would have deleted
    that coverage and made every `stoppedBy` assertion in this file vacuous at
    the same time.
    """
    ts = _ts("-inf USD")

    # On `ceilingsNothingCanReach` and not on `unmetered`, for the reason the test
    # above gives at length: since `VercelAITransport` declares
    # `pricesMoney = false` (B6), every money ceiling this port runs is on
    # `unmetered` because nothing here can PRICE one, and an assertion about
    # what nothing can REACH has to read the array that answers that question.
    assert "cost-per-request-under" not in ts["ceilingsNothingCanReach"], (
        "a cap every run reaches is not a cap nothing can reach: "
        + str(ts["ceilingsNothingCanReach"])
    )
    assert ts["halted"] == "cost-limit", (ts["halted"], ts["stoppedBy"])
    assert ts["stoppedBy"]["limit"] == "cost-per-request-under", ts["stoppedBy"]
    assert "(0 of -inf USD)" in ts["stoppedBy"]["sentence"], ts["stoppedBy"]
