"""Why `cost-per-request-under: NaN USD` has to be refused where it is written.

Money was the only quantity in PACT with no floor under it. A length of time
carries its own bottom (`finishes-within: 0s` is `schema/below-the-floor`,
*"which is no time at all"*) and a percentage carries a `0..=1` range in the
type; money carried only its currency. So `NaN USD`, `inf USD`, `-5 USD` and
`0 USD` all printed *"OK — loaded cleanly"*.

This file holds the CONSEQUENCE, which is the reason the refusal is worth a
diagnostic rather than a shrug. Every ceiling is compared as `spent >= limit`
(`Limits.reached`), and in IEEE-754 every comparison against a NaN is false. So a
spend cap of `NaN USD` is not a loose cap or a strange cap: **it is no cap at
all**, and it used to arrive on a run that reported itself fully metered, under
an author who believes they capped their spend — the exact outcome
`models/catalog.yaml` and `Limits.priced_at_nothing` already name as the thing
to avoid, arriving by a route nothing was watching.

The refusal itself is `crates/pact-schema/src/lib.rs`, `Schema::check_floor`, and
`crates/pact-schema/tests/a_spend_cap_is_an_amount_of_money_and_has_a_bottom.rs`
holds its wording. The last test here drives the real `pact check` over a real
workspace, so a Rust check "simplified" away fails on this side too.

BOTH DOORS ARE NOW GUARDED, and they are guarded differently, which is the
thing to read before editing either:

* A DOCUMENT is REFUSED. Nothing an author writes and hands to `pact check` can
  carry a cap that could never fire. That is `Schema::check_floor`, and the last
  three tests here drive the real binary over a real workspace to hold it.
  THEY ARE NOT THE ONLY DOOR ANY MORE, and they should not have been the only
  one: both skip when `target/debug/pact` is missing and neither builds it, so
  the Rust arm could be deleted and every `cargo test` stay green — measured, 60
  of 60 test targets in `pact-cli`. The one that cannot go stale is
  `crates/pact-cli/tests/a_money_ceiling_that_could_never_hold_is_refused.rs`,
  which cargo builds the binary for.
* A SPEC BUILT IN CODE is REPORTED. `pact check` never sees one, so there is
  nothing to refuse and somebody has to be told instead: a cap no spend can be
  at or above is dropped rather than carried as a row `Limits.reached` can never
  satisfy, and `cost-per-request-under` is named on `RunResult.unmetered`.
  The guard is on the VALUE and not on any reader — `Limits.__post_init__`, so
  `Limits(cost_per_request_under=float('nan'))` and `dataclasses.replace` go the
  same way as `from_mapping` — and `ceilings()` plus `ceilingsNothingCanReach` in
  `adapters/typescript/src/limits.ts` do the same job for the second port, which
  has no construction hook to put it in.

  **And the same door on the OTHER money ceiling is refused rather than
  reported.** `learning.cycle-limits.per-month` had this guard on no route at
  all — measured, three real cycles spending 8.00, 16.00 and 24.00 USD with
  `Outcome.unmeasured` empty on every one, which is worse than silence because
  that channel exists to say the ceiling did not hold. It now drops the cap,
  names the field, and REFUSES the cycle, because there the decision point is a
  method call before any money has been spent and refusing costs nothing
  structural. The asymmetry is argued at
  `test_a_spend_cap_nothing_can_reach_holds_nothing_and_says_so.py` and held by
  `test_a_monthly_ceiling_nothing_can_reach_refuses_the_cycle.py`.

The tests above the binary ones USED TO ASSERT THE SILENCE — `cap parsed as NaN`,
`reached(...) is None` at every spend there is, `'cost-per-request-under' not in
r.unmetered` — because that silence was the before-picture this file existed to
name. They were flipped in the change that closed the second door, and what
they now assert is the report: the cap is not carried, the money row is gone
from the algebra, and the field is named on the honesty channel. The whole EFFECT
across both ports, and the argument for `unmetered` over `never_reached`, is
`tests/test_a_spend_cap_nothing_can_reach_holds_nothing_and_says_so.py`.

The third field that can carry money, `more-than:` on an approval gate, is
neither of these. It is a GATE and not a ceiling, so a zero on it is a strict
rule rather than a broken one and the floor deliberately never reaches it — but
a NON-finite threshold is not a strict gate either, and its refusal lives in
`crates/pact-loader/src/money.rs` with
`crates/pact-cli/tests/a_gate_whose_figure_is_not_a_figure_is_refused.rs` over
it. The measured consequence of that one is at the bottom of this file, because
it is not the one the arithmetic suggests.

Mutation: restore `_ => return` as the last arm of `Schema::check_floor` (i.e.
delete the `Coerced::Money` arm above it) and rebuild the CLI. Without it
`test_the_checker_refuses_a_spend_cap_that_could_never_have_fired` fails — the
workspace loads cleanly — while everything above it stays green, because those
tests describe what the harness does with a document that should never have got
this far.
"""

from __future__ import annotations

import asyncio
import math
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec, ToolSpec  # noqa: E402
from pact_adapters.limits import Limits, Meter  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"

#: The author's own line, with one figure changed. Everything else about the
#: agent is the shipped example's.
WRITTEN = {
    "steps-at-most": 6,
    "cost-per-request-under": "NaN USD",
    "when-it-runs-out": "stop-and-say-so",
}

SPEC = AgentSpec(
    name="Refund Desk",
    description="Decides refunds",
    instructions="Decide, then issue the refund.",
    tools=(ToolSpec("zendesk", "read the ticket"),),
)
TOOLS = {"zendesk": lambda a: "lamp, broken, 6 days ago"}


class Spending(ReferenceTransport):
    """A scripted model that says what each call cost, so the money meter moves.

    The same seam `Costing` uses in `test_termination.py`: `harness._meter_usage`
    probes an optional `usage()`, so a transport that answers it is a run whose
    spend cap is genuinely enforceable. That is what makes the silence below a
    finding rather than an artefact of a stand-in that could not measure.
    """

    name = "spending"
    #: Declared, because `harness.run` defaults it to `False` (B6). This file is
    #: about a cap that is not a FIGURE; a stand-in that stayed silent would put
    #: the same field on `unmetered` for an unrelated reason and the two would be
    #: indistinguishable in the assertion.
    prices_money = True

    def __init__(self, script: Script, money: float = 1000.0) -> None:
        super().__init__(script)
        self._money = money

    def usage(self) -> tuple[int, float]:
        return 100, self._money


def never_finishes() -> Script:
    return Script([Turn("still working", (ToolCall("zendesk", {}),))])


def test_a_spend_cap_of_nan_is_not_carried_as_a_ceiling_at_all() -> None:
    """`Limits.from_mapping` on the line directly: what the run is handed.

    FLIPPED. This used to assert `cost_per_request_under is not None` and
    `math.isnan(...)` — *"the cap parsed as NaN, as written"* — and then that
    `reached` said nothing at a thousand dollars, a billion,
    `sys.float_info.max` and `inf`, because `x >= nan` is false for every x
    there is. All of that was true and all of it was the defect.

    A row `reached` can never satisfy is not a loose ceiling, it is no ceiling,
    so it is not carried as one. `reached` still answers `None` at every spend —
    that half cannot change, there is nothing to compare against — but it now
    answers `None` because there is no money row rather than because the
    comparison quietly fails, and the field is named where a person reads it.
    """
    limits = Limits.from_mapping(WRITTEN)
    assert limits.cost_per_request_under is None, (
        f"a cap of NaN was passed through as a figure: "
        f"{limits.cost_per_request_under!r}"
    )
    assert limits.nothing_can_reach == ("cost-per-request-under",)
    assert [c.field for c in limits.ceilings() if c.reads == "money"] == [], (
        "the money row is still in the algebra: " + str(limits.ceilings())
    )

    for spent in (0.0, 1_000.0, 1e9, sys.float_info.max, math.inf):
        meter = Meter(started=0.0, money=spent)
        assert limits.reached(meter, now=0.0) is None, (
            f"a spend of {spent} cannot reach a cap that is not there"
        )


def test_an_infinite_spend_cap_goes_the_same_way() -> None:
    # `inf` fails for a different reason from NaN — the comparison works fine
    # and nothing can ever be larger — and arrives at the same place, so both
    # leave by the same arm rather than only the strange-looking one.
    #
    # FLIPPED. This asserted only `reached(...) is None`, which stayed true
    # after the fix for a completely different reason — so it is the cap itself
    # that is asserted on now, not the silence downstream of it.
    limits = Limits.from_mapping({**WRITTEN, "cost-per-request-under": "inf USD"})
    assert limits.cost_per_request_under is None, limits.cost_per_request_under
    assert limits.nothing_can_reach == ("cost-per-request-under",)
    assert limits.reached(Meter(started=0.0, money=sys.float_info.max), now=0.0) is None


def test_a_real_run_under_a_nan_cap_spends_and_says_the_cap_held_nothing() -> None:
    """The consequence through the whole harness, not through the comparison.

    The transport reports 1000 USD per model call and the run makes six of them.
    Nothing can stop it — that half is arithmetic — so what has to be true is
    that the run does not ALSO claim the ceiling was holding.

    FLIPPED. This asserted `'cost-per-request-under' not in r.unmetered` under
    the heading *"the run reported the cap as fully enforced"*: six thousand
    dollars out, `unmetered=()`, and an author told the ceiling they wrote was
    being enforced. It is now on `unmetered`, which is the channel that says
    *"this run cannot promise to hold these"*.
    """
    spec = replace(SPEC, max_steps=6, limits=Limits.from_mapping(WRITTEN))
    r = asyncio.run(run(spec, Spending(never_finishes()), "please refund my lamp", TOOLS))

    assert r.spent >= 6_000.0, f"the transport priced its calls: {r.spent}"
    assert "cost-per-request-under" in r.unmetered, (
        "the run reported the cap as fully enforced: " + str(r.unmetered)
    )
    assert r.halted == "step-limit", (
        "the STEP ceiling is what ended it. The spend cap could bind nothing at "
        f"any figure: halted={r.halted} spent={r.spent}"
    )
    assert r.stopped_by is not None
    assert r.stopped_by.ceiling.field == "steps-at-most", r.stopped_by.ceiling.field


def test_the_same_run_under_a_real_cap_stops_on_the_call_that_breaks_it() -> None:
    # The control. Everything above is identical except the figure, so the
    # silence up there is the cap's and not the transport's.
    spec = replace(
        SPEC,
        max_steps=6,
        limits=Limits.from_mapping({**WRITTEN, "cost-per-request-under": "0.05 USD"}),
    )
    r = asyncio.run(run(spec, Spending(never_finishes()), "please refund my lamp", TOOLS))

    assert r.halted == "cost-limit", (r.halted, r.spent)
    assert r.stopped_by is not None
    assert r.stopped_by.ceiling.field == "cost-per-request-under"
    assert "0.05" in r.stopped_by.sentence() and "USD" in r.stopped_by.sentence()


def test_the_checker_refuses_a_spend_cap_that_could_never_have_fired(tmp_path) -> None:
    """And so no author can write the document the four tests above describe.

    Through the real binary over a real copy of the worked example, because the
    claim is about what `pact check` does to a workspace an author hands it —
    the same command the README tells them to run.
    """
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")

    for written in ("NaN USD", "inf USD", "-5 USD", "0 USD"):
        root = tmp_path / written.replace(" ", "-")
        shutil.copytree(EXAMPLE, root)
        limits = root / "agents" / "refund-desk" / "limits.yaml"
        text = limits.read_text()
        assert "cost-per-request-under: 0.05 USD" in text, text
        limits.write_text(
            text.replace(
                "cost-per-request-under: 0.05 USD", f"cost-per-request-under: {written}"
            )
        )

        out = subprocess.run(
            [str(PACT_BIN), "check", str(root)], capture_output=True, text=True
        )
        said = out.stdout + out.stderr
        assert out.returncode != 0, f"`{written}` loaded cleanly:\n{said}"
        assert "rule: schema/below-the-floor" in said, (
            f"`{written}` was not refused as a cap that could never work:\n{said}"
        )
        assert "cost-per-request-under" in said, f"the line is named:\n{said}"


def test_the_other_ceiling_priced_in_money_is_refused_in_a_real_workspace(
    tmp_path,
) -> None:
    """`learning.cycle-limits.per-month` is the second money ceiling, and it is a
    shipped line in the worked example — `per-month: 20 USD`.

    Held through the binary as well as at the library seam, because the floor
    belongs to the TYPE and the whole argument for putting it there is that it
    reaches every money field without being remembered per field. A test that
    only ever pointed at `cost-per-request-under` could not tell that apart from
    a check wired to one field's name.
    """
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")

    for written in ("NaN USD", "inf USD", "-5 USD", "0 USD"):
        root = tmp_path / ("learning-" + written.replace(" ", "-"))
        shutil.copytree(EXAMPLE, root)
        learning = root / "learning.yaml"
        text = learning.read_text()
        assert "per-month: 20 USD" in text, text
        learning.write_text(text.replace("per-month: 20 USD", f"per-month: {written}"))

        out = subprocess.run(
            [str(PACT_BIN), "check", str(root)], capture_output=True, text=True
        )
        said = out.stdout + out.stderr
        assert out.returncode != 0, f"`per-month: {written}` loaded cleanly:\n{said}"
        assert "rule: schema/below-the-floor" in said, said
        assert "'per-month' is " + written in said, f"the line is quoted:\n{said}"


def test_a_threshold_a_person_is_asked_above_is_refused_for_a_different_reason(
    tmp_path,
) -> None:
    """The third money-shaped field, and the one the floor deliberately misses.

    `more-than:` is a GATE, not a ceiling. `more-than: 0 USD` — "ask a person
    about every refund" — is a workspace being strict, and nothing ever runs out
    against a threshold, so the money floor must not reach it and does not.

    A NON-finite threshold is a different thing, and it used to load clean. The
    consequence is NOT the one the arithmetic suggests: `amount > NaN` is never
    evaluated, because `questions._amount` never gets a number out of `NaN USD`
    at all. See the test below for what actually happens. The refusal is
    `crates/pact-loader/src/money.rs`, under its own rule.
    """
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")

    def checked(written: str) -> str:
        root = tmp_path / ("gate-" + written.replace(" ", "-").replace("$", "d"))
        shutil.copytree(EXAMPLE, root)
        rules = root / "policies" / "approvals.yaml"
        text = rules.read_text()
        assert "more-than: 200 USD" in text, text
        rules.write_text(text.replace("more-than: 200 USD", f"more-than: {written}", 1))
        out = subprocess.run(
            [str(PACT_BIN), "check", str(root)], capture_output=True, text=True
        )
        return out.stdout + out.stderr

    for written in ("NaN USD", "inf USD"):
        said = checked(written)
        assert "rule: loader/threshold-is-not-a-figure" in said, (
            f"`more-than: {written}` still loads:\n{said}"
        )
        assert "rule: schema/below-the-floor" not in said, (
            "a gate is not a ceiling, and must not be told it is one:\n" + said
        )

    # And the decision itself: a zero threshold is a strict rule, not a broken
    # one, and the whole workspace still loads.
    said = checked("0 USD")
    assert "loaded cleanly" in said, (
        "`more-than: 0 USD` means 'ask about every refund', which is allowed:\n" + said
    )


def test_a_threshold_nothing_can_read_stops_every_call_rather_than_none() -> None:
    """WHY the refusal above is worth a diagnostic — measured, not reasoned.

    It is tempting to say a `NaN` threshold makes the gate vanish, because
    `amount > NaN` is false for every amount and money would go out with nobody
    asked. That is wrong, and it is wrong for the reason this whole issue exists:
    the comparison is never reached. `_amount` looks for DIGITS, finds none in
    `NaN USD`, and returns `None`; `_atom_stops` then answers `True` for a
    threshold it cannot read, on purpose — its own docstring says refusing to ask
    because of a typo "would turn a typo into a disabled gate".

    So the real consequence is the opposite one and still a defect: the gate
    swallows the figure, and a 1 USD refund parks for a manager exactly as a
    10,000 USD one does, on a line that reads like a threshold. Written down
    here because the first draft of this change claimed the other consequence
    from the arithmetic alone.
    """
    from pact_adapters import questions  # noqa: PLC0415

    gate = {"tool": "payments/issue-refund", "arg": "amount", "more-than": "NaN USD"}
    assert questions._amount("NaN USD") is None, "no digits, so no threshold"
    assert questions._amount("inf USD") is None

    for called_with in ("1 USD", "10 USD", "10000 USD"):
        assert questions._atom_stops(gate, {"amount": called_with}) is True, (
            f"a refund of {called_with} did NOT park for a person — which would be "
            "the other, worse defect"
        )

    # The control: the shipped threshold behaves as a threshold.
    real = {**gate, "more-than": "200 USD"}
    assert questions._atom_stops(real, {"amount": "10000 USD"}) is True
    assert questions._atom_stops(real, {"amount": "10 USD"}) is False


def test_every_threshold_the_checker_lets_through_is_read_back_as_what_was_written(
    tmp_path,
) -> None:
    """THE OTHER HALF OF THE GATE, and the half no refusal in Rust can hold.

    `crates/pact-loader/src/money.rs` refuses a threshold with NO figure in it.
    A threshold with the WRONG figure in it is a different defect and a worse
    one, because it is fail-OPEN: the gate loads, `pact check` says "loaded
    cleanly", `pact show` hands the adapters the line, and the gate then does
    not fire on the money it was written to stop.

    MEASURED, before `questions._NUMBER` was widened — every one of these
    printed "OK — … loaded cleanly (498 settings)" and exited 0 through both
    `pact check` and `pact show`:

        '$.50'    -> 50.0        '$0.50'    -> 0.5
        '.50 USD' -> 50.0        '0.50 USD' -> 0.5
        '.5 USD'  -> 5.0         '-.5 USD'  -> 5.0
        '.05 USD' -> 5.0         '-5 USD'   -> -5.0
        '1e5 USD' -> 1.0

    A gate an author wrote at fifty cents read as fifty dollars, so a 40 USD
    refund went out with nobody asked — the issue's own title, off by 100x. And
    `-.5 USD` read back as +5.0, which flips the SIGN: `-5 USD` is legal on
    purpose ("a gate is not a ceiling", pinned in
    `crates/pact-cli/tests/a_gate_whose_figure_is_not_a_figure_is_refused.rs`),
    so that is a gate deliberately written to stop on every refund there is,
    stopping none under five dollars.

    The cause was one missing alternative: `-?\\d+(?:\\.\\d+)?` requires a digit
    before the decimal point, and `_GROUPING` strips the space first, so
    `'.50 USD'` became `'.50USD'` and the first thing that matched was `50`.

    So this is the invariant, and it is the one a loader test cannot state:
    **for every threshold the checker accepts, the figure the run holds is the
    figure the author wrote.** A test asserting only that the document loads
    cannot see a gate that loads and then means something else.

    Mutation: restore `_NUMBER = re.compile(r"-?\\d+(?:\\.\\d+)?")` in
    `adapters/python/src/pact_adapters/questions.py`. The `.50 USD`, `$.50`,
    `.5 USD`, `-.5 USD` and `1e5 USD` rows below fail; nothing in `pact-loader`
    or `pact-cli` notices, because every one of those documents is valid.
    """
    from pact_adapters import questions  # noqa: PLC0415

    # (what goes in the file, what the parser hands the reader, what it means)
    written = [
        ("200 USD", "200 USD", 200.0),
        ("0 USD", "0 USD", 0.0),
        ("-5 USD", "-5 USD", -5.0),
        ("$.50", "$.50", 0.5),
        ("$0.50", "$0.50", 0.5),
        (".50 USD", ".50 USD", 0.5),
        (".5 USD", ".5 USD", 0.5),
        (".05 USD", ".05 USD", 0.05),
        ("-.5 USD", "-.5 USD", -0.5),
        ("1e5 USD", "1e5 USD", 100000.0),
        ("'1,000 USD'", "1,000 USD", 1000.0),
        ("+5 USD", "+5 USD", 5.0),
        ("$25", "$25", 25.0),
    ]

    for _, value, figure in written:
        assert questions._amount(value) == figure, (
            f"the run reads `more-than: {value}` as {questions._amount(value)}, "
            f"and the author wrote {figure}"
        )

    # And the harm, spelled out on the one that names this issue: a gate at
    # fifty cents fires on a 40 USD refund.
    cents = {"tool": "payments/issue-refund", "arg": "amount", "more-than": "$.50"}
    assert questions._atom_stops(cents, {"amount": "40 USD"}) is True, (
        "a 40 USD refund went out with nobody asked, under a gate written at 50c"
    )
    # And the sign is the sign that was written: a gate at -0.5 USD stops
    # everything, which is what "stop on any spend at all" means.
    every = {**cents, "more-than": "-.5 USD"}
    for amount in ("-0.10 USD", "0.10 USD", "4 USD", "6 USD"):
        assert questions._atom_stops(every, {"amount": amount}) is True, (
            f"a gate written at -0.5 USD let {amount} through"
        )

    # THE OTHER SIDE OF THE SAME PAIR: the checker really does accept all of
    # these, so the reader is the only thing standing between the author and a
    # gate that means something else. Driven through the real binary, because
    # a table of strings agreeing with itself proves nothing.
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    for i, (in_file, _, _) in enumerate(written):
        root = tmp_path / f"read-back-{i}"
        shutil.copytree(EXAMPLE, root)
        rules = root / "policies" / "approvals.yaml"
        text = rules.read_text()
        assert "more-than: 200 USD" in text, text
        rules.write_text(text.replace("more-than: 200 USD", f"more-than: {in_file}", 1))
        out = subprocess.run(
            [str(PACT_BIN), "check", str(root)], capture_output=True, text=True
        )
        said = out.stdout + out.stderr
        assert "loaded cleanly" in said, (
            f"`more-than: {in_file}` is a figure and the checker refused it:\n{said}"
        )


def test_a_threshold_that_is_not_a_finite_number_reads_as_no_threshold_at_all() -> None:
    """The one genuinely fail-OPEN path in this area, and it is two lines to close.

    `'NaN USD'` is TEXT: no digits, `_amount` returns `None`, and `_atom_stops`
    stops the call — absurd, and safe, and the case the whole issue was measured
    against. A float `nan` is not text. It went through the `isinstance(value,
    (int, float))` branch, came back as `nan`, and `nan > anything` is `False`,
    so the gate silently never fired. MEASURED:

        _atom_stops({..., 'more-than': float('nan')}, {'amount': '999999 USD'})
        -> False
        _atom_stops({..., 'more-than': float('inf')}, {'amount': '999999 USD'})
        -> False

    A 999,999 USD refund past a gate, with nothing on any report saying so.
    FR-8.1.1 (docs/30-FRD.md, thesis T7): *"No lossy operation anywhere may
    proceed silently; each MUST emit a report entry and be fail-closed by
    default."* B3's own record states the standard for the fix —
    `docs/70-PRODUCTION-GAP-REGISTER.md`, *"The guard is on the VALUE, not on a
    reader"* — so the guard is on `_amount`, where both callers and any future
    third one go through it.

    `pact check` never sees this document: a float `nan` cannot be written in
    YAML (`crates/pact-doc/src/yaml.rs` keeps `.nan` as text on purpose), so it
    arrives only from a spec built in code — which is exactly the door
    `Limits.__post_init__` guards for the other money field, and exactly the
    reason that door exists.

    Mutation: restore `return float(value)` in `questions._amount`. Both
    assertions below fail; every Rust test stays green, because no document can
    express this.
    """
    from pact_adapters import questions  # noqa: PLC0415

    gate = {"tool": "payments/issue-refund", "arg": "amount"}
    for threshold in (float("nan"), float("inf"), float("-inf")):
        assert questions._amount(threshold) is None, (
            f"{threshold!r} is not a figure and must not be read as one"
        )
        assert questions._atom_stops({**gate, "more-than": threshold}, {"amount": "999999 USD"}), (
            f"a 999999 USD refund went out unasked under `more-than: {threshold!r}`"
        )
    # The control: a finite float threshold is still a threshold.
    real = {**gate, "more-than": 200.0}
    assert questions._atom_stops(real, {"amount": "10000 USD"}) is True
    assert questions._atom_stops(real, {"amount": "10 USD"}) is False


@pytest.mark.parametrize("amount", ["Infinity", "NaN", "inf USD", float("inf"), float("nan")])
def test_an_amount_that_is_not_a_finite_number_does_not_slip_under_the_gate(
    amount: object,
) -> None:
    """The same fail-open, on the other side of the comparison.

    The threshold was closed above; the ARGUMENT was not. `_amount` reads a
    non-finite amount as no figure, and `_atom_stops` then treated "no figure"
    as "no amount": `value is not None and value > threshold` is `False`, so a
    model asking to refund `Infinity` went past a 200 USD gate with nobody
    asked. An amount the call carries and nothing can read stops the call.
    """
    from pact_adapters import questions  # noqa: PLC0415

    gate = {"tool": "payments/issue-refund", "arg": "amount", "more-than": "200 USD"}
    assert questions._atom_stops(gate, {"amount": amount}) is True, (
        f"a refund of {amount!r} went out unasked under `more-than: 200 USD`"
    )
    # The controls: a call with no amount at all is not over any line, and a
    # figure is still compared as one.
    assert questions._atom_stops(gate, {"order-number": "O-9"}) is False
    assert questions._atom_stops(gate, {"amount": "10 USD"}) is False
