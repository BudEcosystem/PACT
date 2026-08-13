"""`cycle-limits.per-month: NaN USD` — the second money ceiling, at the door no
checker stands at.

B3 put a floor under money in `Schema::check_floor`, and it reaches BOTH fields
the specification types `money`: `limits.cost-per-request-under` and
`learning.cycle-limits.per-month`. That closes the DOCUMENT route for both —
`crates/pact-cli/tests/a_money_ceiling_that_could_never_hold_is_refused.rs` drives
the shipped binary over a real workspace and holds it.

It closed the RUN-TIME route for only one of them. A spec built in code never
meets `pact check`, which is the entire reason `Limits.__post_init__` exists;
and one module over, `Permissions.per_month` had no such guard on any route.
Measured before this file, three real cycles against a real `.pact/learning/`
ledger with `per-month: NaN USD` handed to `Learner.from_document`::

    cycle 1: applied=False  month_total=8.0   unmeasured=()
    cycle 2: applied=False  month_total=16.0  unmeasured=()
    cycle 3: applied=False  month_total=24.0  unmeasured=()

Twenty-four dollars of self-improvement on a `tier: core`, `S-GOV` line, and
`Outcome.unmeasured` — the honesty channel built for exactly this field, whose
own docstring enumerated *"three things that can still stop the ceiling
biting"* — empty on every cycle. That is worse than the before-picture B3
started from: it is not silence, it is an affirmation. The enforcement site is
`if would_reach > amount:` and every comparison against a NaN is false, so the
refusal underneath it was dead code at every spend there is.

THE ANSWER HERE IS FAIL-CLOSED, AND THAT IS THE OPPOSITE OF THE ONE `limits.py`
GIVES. `Limits.__post_init__` drops the cap, records `cost-per-request-under` on
`RunResult.unmetered`, and lets the run proceed, because the object it guards is
a frozen dataclass built on the delegation path — `harness._delegating` calls
`replace()` on a member whose own cap is `NaN USD` and hands it the join policy's
real share — so refusing at construction would kill a run that is one line away
from being correct. `Learner._decide` has no such constraint: it is a method
call, no money has been spent yet, and two ceilings above this one already answer
with `Outcome(False, ...)`. FR-8.1.1 (docs/30-FRD.md) says a lossy step is
*"fail-closed by default"*, and here fail-closed costs nothing structural, so it
is taken. The field is named on `Outcome.unmeasured` as well, because a reviewer
asking that channel which ceilings held must not get `()` for the one ceiling
that held nothing at all.

**The document is built in code here, and that is the point rather than a
shortcut.** `test_a_months_spend_on_improving_is_held.py` insists every cap it
asserts about comes off the author's own `learning.yaml` through `pact show`,
and it is right to: that is how you prove the author's line reaches the
comparison. It cannot be done for these values, because `pact check` refuses
them — which is the other half of the fix working. So the fixture guard below
reads the shipped `learning.yaml` as text and pins the number the CONTROL uses,
and the unreachable figures are handed in the one way a runtime can still
receive them.

Mutation, in `adapters/python/src/pact_adapters/learning.py`: restore
`per_month_cap` to `return money(self.per_month) if self.per_month else None`,
and delete both `if self.permissions.per_month_holds_nothing():` blocks — the
refusal in `Learner._decide` and the fourth sentence in `Learner._unmeasured`.
Measured with all three reverted: **24 of the 29 cases below fail**, and the 5
that stay green are the controls — the fixture guard, `20 USD`, `0 USD`,
`-inf USD`, and the month that cannot be kept — because those are the behaviours
this change must not have moved.

The two halves are held separately, which was measured rather than assumed.
Reverting only `per_month_cap` and the refusal leaves **18 failing**: the
honesty channel keeps its sentence, so a fix that reported and did not refuse
would still be caught by the three refusal tests. Reverting only the
`_unmeasured` branch leaves the six `..._named_on_the_honesty_channel` cases
failing on their own.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.evals import Case  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.learning import (  # noqa: E402
    LEDGER,
    UNDER,
    Learner,
    Permissions,
    Proposal,
)
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"

#: The number the shipped `learning.yaml` writes, pinned by the fixture guard
#: below so the control cannot drift away from the worked example.
SHIPPED = "20 USD"

#: Every way of writing a monthly ceiling no spend can ever be above. `-inf` is
#: deliberately NOT here — see the test at the bottom for what it is instead.
UNREACHABLE = ["NaN USD", "nan USD", "inf USD", "Infinity USD", "USD inf", "$NaN"]

# Free of the words the blast-radius classifier watches for, the same two
# strings the sibling module uses: the subject is the money, and a proposal that
# tripped CLASS-HIGH would be refused before the spend ever came up.
BAD = "Answer the customer."
GOOD = "Answer the customer. State the outcome as one word at the start, then the figure."

SPEC = AgentSpec(name="Refund Desk", description="Decides refunds", instructions=BAD)

HOLDOUT = [
    Case("h1", "kettle faulty after 10 days", {"decision": "approved"}),
    Case("h2", "headphones, changed mind, 45 days", {"decision": "declined"}),
]

#: Two cases, scored twice — before and after — so one cycle is four model calls.
RUNS_PER_CYCLE = 2 * len(HOLDOUT)


class Costing(ReferenceTransport):
    """A transport that says what its call cost, so the month's total moves."""

    name = "costing"

    def __init__(self, script: Script, money: float = 2.0) -> None:
        super().__init__(script)
        self._money = money

    def usage(self) -> tuple[int, float]:
        return 100, self._money


def _script(spec: AgentSpec) -> Script:
    if "one word at the start" in spec.instructions:
        return Script([Turn("Decision: approved. Amount: 40 USD.")])
    return Script([Turn("It depends on the circumstances.")])


def costing(money: float = 2.0):
    def build(spec: AgentSpec):
        return Costing(_script(spec), money=money)

    return build


def document(written: str) -> dict:
    """A `learning:` block of the shape the worked example ships, one line changed.

    `enabled: propose-only` and the two sibling ceilings are the shipped values;
    only `per-month` moves, so every difference below is that line's doing.
    """
    return {
        "learning": {
            "enabled": "propose-only",
            "cycle-limits": {"per-cycle": 4, "per-month": written, "evals": 2000},
        }
    }


def cycle_in(root: Path, written: str):
    """One cycle — one Friday — against the workspace folder on disk.

    A fresh `Learner` per cycle, because that is what a schedule does and it is
    the only way the month's total can be shown to survive the process that
    spent it.
    """
    learner = Learner.from_document(
        document(written),
        replace(SPEC, workspace=str(root)),
        tools={},
        cases=HOLDOUT,
        bar=0.5,
    )
    learner.holdout = HOLDOUT
    return learner.cycle(
        Proposal("instructions", BAD, GOOD, "say the outcome first"), costing(2.0)
    )


def spent_in(root: Path) -> float:
    """What the workspace's own ledger says improving has cost this month."""
    record = root / UNDER / LEDGER
    if not record.exists():
        return 0.0
    rows = [json.loads(x) for x in record.read_text().splitlines() if x.strip()]
    return sum(r["money"] for r in rows)


# ─────────────────────────────────────────────────────────── the fixture guard


def test_the_worked_example_still_writes_the_number_the_control_uses() -> None:
    """The control below is the author's own figure, so the file losing it has to
    fail loudly rather than quietly turning that control into a test of nothing.

    Read as text, not through an adapter: invariant P-1 says an adapter may be
    handed only the document, and this is a test reading a fixture.
    """
    text = (EXAMPLE / "learning.yaml").read_text()
    assert f"per-month: {SHIPPED}" in text, text


# ───────────────────────────────────────────── the ceiling that is not a figure


@pytest.mark.parametrize("written", UNREACHABLE)
def test_a_ceiling_nothing_can_reach_is_not_carried_as_a_figure(written: str) -> None:
    """`Permissions.per_month_cap()` hands back nothing rather than a `nan`.

    Both routes: the dataclass built by hand, and `from_document`, which is the
    one a runtime handed a `canonical.json` walks through. Before this, both
    returned `(nan, 'USD')` and the comparison underneath was dead at every
    spend.
    """
    by_hand = Permissions(per_month=written)
    assert by_hand.per_month_cap() is None, by_hand.per_month_cap()
    assert by_hand.per_month_holds_nothing() is True

    from_doc = Permissions.from_document(document(written))
    assert from_doc.per_month == written, "the author's own text is still carried"
    assert from_doc.per_month_cap() is None, from_doc.per_month_cap()


@pytest.mark.parametrize("written", UNREACHABLE)
def test_a_cycle_under_a_ceiling_nothing_can_reach_is_refused_before_it_spends(
    tmp_path, written: str
) -> None:
    """FAIL-CLOSED, and measurably: the ledger is still empty afterwards.

    Not "the cycle was refused" alone — a refusal that arrives after both scoring
    runs is a report of the overspend rather than a cap, which is the distinction
    the `per-month` forecast was built around in the first place. So what is
    asserted is the money: nothing was written to `.pact/learning/`, because
    nothing was scored.
    """
    out = cycle_in(tmp_path, written)

    assert not out.applied, out.reason
    assert spent_in(tmp_path) == 0.0, (
        f"`per-month: {written}` cannot be held and the cycle spent anyway: "
        f"{spent_in(tmp_path)}"
    )
    assert out.verdict_before is None and out.verdict_after is None, (
        "refused after scoring is not refused: it spends exactly the money the "
        "line exists to save"
    )


@pytest.mark.parametrize("written", UNREACHABLE)
def test_the_refusal_quotes_the_line_and_offers_one_a_person_can_type(
    tmp_path, written: str
) -> None:
    """D13: a refusal a person cannot act on is a refusal they will route around.

    The reader is whoever approves the budget for a self-improving system, and
    they have no source to read. So the sentence carries the field, what they
    wrote, and the line to type instead — and never the words a programmer would
    reach for.
    """
    said = cycle_in(tmp_path, written).reason

    assert f"cycle-limits.per-month: {written}" in said, said
    assert "no amount of money can ever be above this" in said, said
    assert "per-month: 20 USD" in said, f"the fix is not a line they can type: {said}"
    for jargon in ["NaN", "non-finite", "IEEE", "float", "nan("]:
        if jargon in written:
            continue
        assert jargon not in said, f"the refusal says {jargon!r} to a non-programmer: {said}"


@pytest.mark.parametrize("written", UNREACHABLE)
def test_the_ceiling_that_held_nothing_is_named_on_the_honesty_channel(
    tmp_path, written: str
) -> None:
    """`Outcome.unmeasured` — the door built for this exact field.

    Its own docstring enumerated three ways the ceiling can fail to bite and
    returned `()` otherwise, so in an ordinary priced run a `NaN` cap came back
    as a ceiling that HELD. A reviewer asking this channel which ceilings held
    must not be told "all of them" by an empty tuple.
    """
    out = cycle_in(tmp_path, written)

    assert out.unmeasured, (
        f"`per-month: {written}` held nothing and the cycle said nothing about "
        f"it: unmeasured={out.unmeasured}"
    )
    named = "\n".join(out.unmeasured)
    assert "cycle-limits.per-month" in named, named
    assert written in named, f"what the author wrote is not quoted back: {named}"


def test_the_three_reasons_that_are_facts_about_the_world_still_report_and_run(
    tmp_path,
) -> None:
    """The fourth sentence must not have swallowed the other three.

    A cycle handed the settings without the folder they came from is the first of
    them: nothing is wrong with the line, there is simply nowhere to keep a
    month's total. That one is REPORTED and the cycle runs — refusing it would
    punish a caller for driving `Learner` the way invariant P-1 says an adapter
    may be driven.
    """
    learner = Learner.from_document(
        document(SHIPPED), SPEC, tools={}, cases=HOLDOUT, bar=0.5
    )
    learner.holdout = HOLDOUT
    out = learner.cycle(
        Proposal("instructions", BAD, GOOD, "say the outcome first"), costing(2.0)
    )

    named = "\n".join(out.unmeasured)
    assert "nowhere to keep what improving has cost" in named, named
    assert out.verdict_before is not None, (
        "a month that cannot be kept is a reported ceiling, not a refused cycle: "
        + out.reason
    )


# ───────────────────────────────────────────────────────────────── the controls


def test_the_authors_own_ceiling_still_runs_the_cycles_it_was_written_for(
    tmp_path,
) -> None:
    """THE CONTROL. Everything above is identical except the figure.

    Three Fridays at 8.00 USD each against the shipped `20 USD`: the first two
    run and spend, the third is refused at 16.00 USD because 24.00 would cross.
    If the guard added above had reached a figure that IS one, this is where it
    would show.
    """
    assert cycle_in(tmp_path, SHIPPED).verdict_before is not None
    assert spent_in(tmp_path) == pytest.approx(2.0 * RUNS_PER_CYCLE)
    cycle_in(tmp_path, SHIPPED)
    assert spent_in(tmp_path) == pytest.approx(2 * 2.0 * RUNS_PER_CYCLE)

    third = cycle_in(tmp_path, SHIPPED)
    assert not third.applied
    assert f"cycle-limits.per-month: {SHIPPED}" in third.reason, third.reason
    assert "16.00 USD" in third.reason and "24.00 USD" in third.reason, third.reason
    assert third.unmeasured == (), (
        "a ceiling that refused a cycle is a ceiling that held: " + str(third.unmeasured)
    )
    assert spent_in(tmp_path) == pytest.approx(2 * 2.0 * RUNS_PER_CYCLE), (
        "the refused cycle spent money"
    )


def test_a_ceiling_a_cycle_crosses_immediately_is_a_wrong_one_and_not_an_absent_one(
    tmp_path,
) -> None:
    """`-inf USD` is the one non-finite figure that is NOT on this list.

    `limits._nothing_can_reach` excludes it on purpose and says why: a run
    reaches `-inf` on its first step, so it is a ceiling that fires too early
    rather than one that never fires, and the author is told so loudly by the
    ordinary refusal. Held here so a later tidy-up that replaced the test with
    `not math.isfinite` would fail: that would send `-inf` down the new path and
    replace a working (if wrong) ceiling's sentence with "no amount of money can
    ever be above this", which is false of it.
    """
    assert Permissions(per_month="-inf USD").per_month_holds_nothing() is False
    cap = Permissions(per_month="-inf USD").per_month_cap()
    assert cap is not None and cap[0] == -math.inf, cap

    out = cycle_in(tmp_path, "-inf USD")
    assert not out.applied
    assert "improving this system has already cost" in out.reason, out.reason
    assert "no amount of money can ever be above this" not in out.reason, out.reason


def test_a_monthly_ceiling_of_zero_lets_one_cycle_through_and_then_refuses(
    tmp_path,
) -> None:
    """MEASURED, and it is the reason `Schema::check_floor`'s doc had to change.

    That doc said money was *"the same argument on the same comparison"* as a
    duration and applied it to both money ceilings. It is not the same
    comparison. `Limits.reached` is `at >= c.limit`, so `cost-per-request-under:
    0 USD` is reached before the first step. `Learner._decide` is `would_reach >
    amount`, and `MonthlySpend.per_run` is `0.0` until something has been scored,
    so on the first cycle of a month `0.0 > 0.0` is false and the cycle RUNS.

    So `per-month: 0 USD` does not stop everything instantly — it lets exactly
    one cycle's worth of spend through and refuses from then on, which is not
    what its author meant by zero either. It is still refused where the author
    writes it, and now for the reason measured here rather than for a borrowed
    one. This test is what makes that sentence in the Rust doc checkable.
    """
    first = cycle_in(tmp_path, "0 USD")
    assert first.verdict_before is not None, (
        "a zero monthly ceiling did NOT stop the first cycle instantly: " + first.reason
    )
    assert spent_in(tmp_path) == pytest.approx(2.0 * RUNS_PER_CYCLE)

    second = cycle_in(tmp_path, "0 USD")
    assert not second.applied
    assert "cycle-limits.per-month: 0 USD" in second.reason, second.reason
    assert spent_in(tmp_path) == pytest.approx(2.0 * RUNS_PER_CYCLE), (
        "the second cycle spent as well"
    )
