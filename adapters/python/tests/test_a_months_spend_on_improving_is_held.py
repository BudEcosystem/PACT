"""`cycle-limits.per-month:` refuses a cycle, rather than describing one.

The field is `tier: core` and `S-GOV` — a spend cap on a system that rewrites
itself — and for a round it was READ, VALIDATED, and then reported on
`Outcome.unmeasured` with the sentence *"nothing here counts a month's spend, so
this ceiling is recorded and not held"*. The schema's own help said the same. So
a workspace could write `per-month: 20 USD` on the line that governs how much
self-improvement it will pay for, and spend without bound.

The argument for that state was *"a `Learner` is one cycle and nothing here sees
a month"*, and it was wrong in exactly one place. The running total does not have
to live in the process. It lives in the WORKSPACE — one append-only file under
`.pact/learning/`, the same place and the same shape `watch:` already keeps a
record of what a run did — so next Friday's cycle can see what last Friday's
cost.

**Every cap in this file comes off the author's own `learning.yaml`.** Nothing
here writes `20 USD` in Python: the worked example is copied, checked, loaded
through `pact show` — the door every adapter reads through — and the number the
author typed is what refuses. A test that built `Permissions(per_month="20 USD")`
would prove the comparison works and say nothing about whether the author's line
reaches it, which is the defect this project keeps shipping.

The reading lines are `Permissions.per_month_cap` (which parses the author's
text) and the `cap is not None and self.month.kept` block in `Learner.cycle`
(which refuses). Delete either and
`test_the_authors_own_monthly_ceiling_refuses_the_cycle_that_would_cross_it`
fails.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.evals import Case  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.learning import (  # noqa: E402
    LEDGER, UNDER, Learner, MonthlySpend, Proposal,
)
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"

# Deliberately free of the words the blast-radius classifier watches for, the
# same two strings `test_learning.py` uses: the subject here is the money, and a
# proposal that tripped CLASS-HIGH would be refused before the spend ever came up.
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
    """A transport that says what its call cost.

    `ReferenceTransport` deliberately does not: it is bound to no model, so it
    has no price to charge, and it is the one transport that keeps the
    *"nobody could count this"* route exercised. Both halves are held here —
    this one for the ceiling that bites, that one for the sentence that says it
    cannot.
    """

    name = "costing"

    def __init__(self, script: Script, money: float = 2.0) -> None:
        super().__init__(script)
        self._money = money

    def usage(self) -> tuple[int, float]:
        return 100, self._money


def costing(money: float = 2.0):
    """A `transport_for` that prices every call at `money`."""

    def build(spec: AgentSpec):
        return Costing(_script(spec), money=money)

    return build


def free(spec: AgentSpec):
    """A `transport_for` bound to nothing, so nobody can price the calls."""
    return ReferenceTransport(_script(spec))


def _script(spec: AgentSpec) -> Script:
    """A model that only answers gradeably once the instructions say how to.

    The mechanism the whole thesis rests on in miniature, and the reason the
    cycles below are real cycles: the contract is unchanged, the instructions
    change, and the measured result moves.
    """
    if "one word at the start" in spec.instructions:
        return Script([Turn("Decision: approved. Amount: 40 USD.")])
    return Script([Turn("It depends on the circumstances.")])


def workspace(tmp_path: Path) -> tuple[Path, dict]:
    """The shipped worked example on disk, checked, and loaded for real.

    `pact show` is the same door every adapter reads through, so what comes back
    is what a runtime would see. The tree is CHECKED first: a document
    `pact check` refuses must never be the thing a test asserts behaviour about,
    or the test is describing a workspace nobody could ship.
    """
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    root = tmp_path / "refund-desk"
    # `.pact/` is EXCLUDED, and not for tidiness: it is the workspace's own
    # derived area, and `spend.jsonl` lives there. A stray ledger in the
    # shipped tree — one test pointing a real cycle at `examples/` is enough —
    # arrives here as this month's opening balance. Twenty-eight recorded runs
    # at `money: 0.0` diluted `per_run` to zero, so the forecast could never
    # cross `20 USD` and every ceiling assertion below went red for a reason
    # none of them named. `test_watching_a_run.py` already copies this way.
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns(".pact"))
    checked = subprocess.run(
        [str(PACT_BIN), "check", str(root)], capture_output=True, text=True
    )
    assert checked.returncode == 0, (
        "the tree these assertions are about has to be one `pact check` accepts:\n"
        + checked.stdout
    )
    shown = subprocess.run(
        [str(PACT_BIN), "show", str(root)], capture_output=True, text=True, check=True
    )
    return root, json.loads(shown.stdout)


def learner_in(root: Path, doc: dict) -> Learner:
    """One cycle — one Friday — against the workspace on disk.

    A fresh `Learner` per cycle on purpose: that is what a real schedule does,
    and it is the only way to show that the month's total survives the process
    that spent it. Nothing about the ceiling is passed in; it comes off
    `learning.yaml` through `Permissions.from_document`, and the folder it is
    kept in comes off `spec.workspace`.
    """
    L = Learner.from_document(
        doc, replace(SPEC, workspace=str(root)), tools={}, cases=HOLDOUT, bar=0.5
    )
    L.holdout = HOLDOUT
    return L


def a_proposal() -> Proposal:
    return Proposal("instructions", BAD, GOOD, "say the outcome first")


# ───────────────────────────────── the ceiling the author wrote, and what it refuses


def test_the_worked_example_still_writes_a_monthly_ceiling_to_be_held(tmp_path) -> None:
    """The fixture guard. Every assertion below is about the author's own number,
    so the file losing that number has to fail loudly rather than quietly turning
    the rest of this module into a test of nothing."""
    _, doc = workspace(tmp_path)
    limits = doc["learning"]["cycle-limits"]
    assert limits["per-month"] == "20 USD", limits
    # Its two siblings on the same line, which were enforced a round earlier. A
    # ceiling wired while the ones beside it default is how round 5 went wrong.
    assert limits["per-cycle"] == 4 and limits["evals"] == 2000, limits


def test_the_authors_own_monthly_ceiling_refuses_the_cycle_that_would_cross_it(
    tmp_path,
) -> None:
    """Three Fridays. The third one is refused, by the line in `learning.yaml`.

    Nothing is pre-seeded and nothing is constructed: the first two cycles really
    run, really spend, and really write down what they spent, and the third is
    told no because the sum of the first two plus what it would cost crosses
    `per-month: 20 USD`. That is the difference between a value that REACHES the
    cap and a cap that REFUSES — the distinction round 5 shipped on the wrong
    side of.
    """
    root, doc = workspace(tmp_path)
    per_call = 2.0  # 8.00 USD a cycle, against the author's 20 USD

    first = learner_in(root, doc).cycle(a_proposal(), costing(per_call))
    assert "per-month" not in first.reason, (
        "the first cycle of a month has no evidence to forecast from and must "
        f"not be refused on none: {first.reason}"
    )
    second = learner_in(root, doc).cycle(a_proposal(), costing(per_call))
    assert "per-month" not in second.reason, second.reason

    third = learner_in(root, doc).cycle(a_proposal(), costing(per_call))
    assert not third.applied
    assert "cycle-limits.per-month: 20 USD" in third.reason, third.reason
    assert third.verdict_before is None and third.verdict_after is None, (
        "a cycle over the month's cap must be refused BEFORE it scores anything "
        "— refusing afterwards spends exactly the money the line exists to save"
    )


def test_a_refused_cycle_says_what_has_been_spent_and_when_the_ceiling_lifts(
    tmp_path,
) -> None:
    """D13: a refusal a person cannot act on is a refusal they will route around.

    The reader here is whoever approves the budget, so the sentence has to carry
    the line they typed, what has gone, what this would take it to, and when it
    starts again — not "monthly limit exceeded".
    """
    root, doc = workspace(tmp_path)
    for _ in range(2):
        learner_in(root, doc).cycle(a_proposal(), costing(2.0))
    said = learner_in(root, doc).cycle(a_proposal(), costing(2.0)).reason

    assert "cycle-limits.per-month: 20 USD" in said, said
    assert "16.00 USD" in said, f"what has already gone is not in the sentence: {said}"
    assert "24.00 USD" in said, f"what this cycle would take it to is missing: {said}"
    assert MonthlySpend().in_words() in said, f"which month is not named: {said}"
    assert MonthlySpend().next_in_words() in said, f"when it lifts is not said: {said}"


def test_what_one_cycle_spent_is_still_there_for_the_next_one(tmp_path) -> None:
    """The whole reason the total lives in the workspace and not in the process.

    A `Learner` is one cycle. Left in memory, `per-month` would reset every
    Friday and cap nothing — which is precisely the argument that kept it
    unenforced.
    """
    root, doc = workspace(tmp_path)
    learner_in(root, doc).cycle(a_proposal(), costing(2.0))

    record = root / UNDER / LEDGER
    assert record.exists(), f"nothing was written down at {record}"
    rows = [json.loads(l) for l in record.read_text().splitlines() if l.strip()]
    assert len(rows) == 1, rows
    assert rows[0]["money"] == pytest.approx(2.0 * RUNS_PER_CYCLE)
    assert rows[0]["runs"] == RUNS_PER_CYCLE

    # And a cycle built fresh, in the way a schedule builds one, reads it back.
    assert learner_in(root, doc).month.money == pytest.approx(8.0)


def test_a_cycle_refused_for_the_month_still_counts_the_ones_that_did_spend(
    tmp_path,
) -> None:
    """A refusal costs nothing, so it adds nothing — and does not clear anything
    either. Without this the third cycle could quietly write a zero row and the
    fourth would forecast from a diluted average."""
    root, doc = workspace(tmp_path)
    for _ in range(3):
        learner_in(root, doc).cycle(a_proposal(), costing(2.0))

    rows = [
        json.loads(l)
        for l in (root / UNDER / LEDGER).read_text().splitlines()
        if l.strip()
    ]
    assert len(rows) == 2, f"the refused cycle wrote a row: {rows}"
    assert learner_in(root, doc).month.money == pytest.approx(16.0)


def test_a_cycle_held_for_review_still_counts_what_it_spent(tmp_path) -> None:
    """The worked example says `enabled: propose-only`, so every cycle ends
    "held for review" — and the scoring still happened. A ceiling that only
    counted the cycles that APPLIED something would never count anything at all
    in the workspace this repository ships."""
    root, doc = workspace(tmp_path)
    out = learner_in(root, doc).cycle(a_proposal(), costing(2.0))

    assert not out.applied and "propose-only" in out.reason, out.reason
    assert learner_in(root, doc).month.money == pytest.approx(8.0)


def test_last_months_spending_is_not_charged_to_this_month(tmp_path) -> None:
    """The word "monthly" doing its job. The file is append-only and keeps
    everything; only rows stamped with this month are added up, so a workspace
    does not inherit a ceiling it already served."""
    root, doc = workspace(tmp_path)
    last = date.today().replace(day=1)
    last = last.replace(year=last.year - 1)
    MonthlySpend(root=root, today=lambda: last).add(1000.0, 40)

    fresh = learner_in(root, doc)
    assert fresh.month.money == 0.0, "last year's rows were charged to this month"
    out = fresh.cycle(a_proposal(), costing(2.0))
    assert "per-month" not in out.reason, out.reason

    rows = [
        json.loads(l)
        for l in (root / UNDER / LEDGER).read_text().splitlines()
        if l.strip()
    ]
    assert len(rows) == 2, "the old row was rewritten rather than kept"


def test_the_record_of_what_improving_cost_carries_no_words_from_any_conversation(
    tmp_path,
) -> None:
    """A month, an amount, a count. Nothing else, ever.

    §8.8 requirement 3 makes a learning cycle carry per-case failures *"with the
    error text"*, and failures are the customer's own words. `watches.RECORDED`
    settles the same question with an allow-list; here it is settled by there
    being nothing else to write — which is the stronger form, because a future
    keyword cannot leak through a shape that has no room for one.
    """
    root, doc = workspace(tmp_path)
    learner_in(root, doc).cycle(a_proposal(), costing(2.0))

    for line in (root / UNDER / LEDGER).read_text().splitlines():
        if line.strip():
            assert set(json.loads(line)) == {"month", "money", "runs"}, line


def test_a_workspace_that_has_improved_itself_still_checks_clean(tmp_path) -> None:
    """Why the record goes under `.pact/`. The loader skips any name beginning
    with a dot, so running a cycle cannot make the next `pact check` fail — write
    it to `reports/` instead and the author is told *"'reports' is not something
    a workspace can have"*, a mistake they did not make and cannot understand."""
    root, doc = workspace(tmp_path)
    learner_in(root, doc).cycle(a_proposal(), costing(2.0))

    again = subprocess.run(
        [str(PACT_BIN), "check", str(root)], capture_output=True, text=True
    )
    assert again.returncode == 0, again.stdout
    assert "loaded cleanly" in again.stdout, again.stdout


# ───────────────────────────────────── the honest half: when it cannot be held


def test_a_cycle_handed_no_folder_says_the_month_cannot_be_kept(tmp_path) -> None:
    """Invariant P-1: an adapter may be given the document and no tree. Then
    there is nowhere to keep a month, and the honest answer is to say so with a
    line to type — not to enforce the ceiling against a total that starts at zero
    in every process, which would report a cap that never fires."""
    _, doc = workspace(tmp_path)
    L = Learner.from_document(doc, SPEC, tools={}, cases=HOLDOUT, bar=0.5)
    L.holdout = HOLDOUT
    out = L.cycle(a_proposal(), costing(2.0))

    said = "\n".join(out.unmeasured)
    assert "cycle-limits.per-month: 20 USD" in said, said
    assert "nowhere to keep" in said, said
    assert "Fix:" in said and ".pact/learning/" in said, "no line to type: " + said


def test_a_cycle_nobody_could_price_says_the_ceiling_can_never_be_reached(
    tmp_path,
) -> None:
    """The other half, and the one that stops this shipping as a display value.

    `ReferenceTransport` is bound to no model, so nothing can price what it
    carried and the month's total never moves. A cap enforced against that is a
    cap that reports itself held and refuses nothing — the exact failure
    `RunResult.unmetered` exists to name one layer down.
    """
    root, doc = workspace(tmp_path)
    out = learner_in(root, doc).cycle(a_proposal(), free)

    said = "\n".join(out.unmeasured)
    assert "cycle-limits.per-month: 20 USD" in said, said
    assert "could put a price" in said, said
    assert "models/catalog.yaml" in said, "no line to type: " + said


def test_a_ceiling_that_is_being_held_says_nothing_at_all(tmp_path) -> None:
    """The control, and the reason the door above is worth reading. A field that
    always had something in it would tell a reviewer nothing about which cycles
    were governed and which were not."""
    root, doc = workspace(tmp_path)
    assert learner_in(root, doc).cycle(a_proposal(), costing(2.0)).unmeasured == ()


def test_a_month_priced_at_nothing_is_told_apart_from_a_month_nobody_priced(
    tmp_path,
) -> None:
    """Two zeros, two different facts, two different fixes.

    `models/catalog.yaml` publishes five rows at `0 USD` in and `0 USD` out —
    weights this machine serves — so a workspace can count every call perfectly
    and still total 0.00 for the life of the month. Saying "nobody could measure
    it" there would send the author looking for a transport; the ceiling that
    still bites is the eval-run count beside it.
    """
    root, doc = workspace(tmp_path)
    out = learner_in(root, doc).cycle(a_proposal(), costing(0.0))

    said = "\n".join(out.unmeasured)
    assert "priced at nothing" in said, said
    assert "cycle-limits.evals:" in said, "the ceiling that still works: " + said
    assert "could put a price" not in said, "that is the other fact: " + said


# ───────── AC-5.5: a refused candidate changes what the next cycle does


def test_the_same_edit_refused_twice_costs_nothing_the_second_time(
    tmp_path: Path,
) -> None:
    """`Learner.rejected` was a list nothing read.

    Its own comment beside the append said the purpose — *"a rejected candidate
    that is simply forgotten will be proposed again next cycle"* — and forgetting
    happened twice over: nothing consulted the list, and a `Learner` is built
    fresh per cycle, so it did not outlive the process that made it.

    Two cycles, two fresh `Learner`s, the same proposal. The first pays to find
    out. The second recognises it and spends nothing.
    """
    root, shipped = workspace(tmp_path)
    # The shipped example is `propose-only`, so every proposal is held for a
    # person BEFORE the scores are compared — and that refusal is deliberately
    # not remembered: a proposal turned away by a policy must be reviewable once
    # the policy changes. To reach the refusal AC-5.5 is about, the workspace has
    # to be one that applies its own safe changes.
    doc = json.loads(json.dumps(shipped))
    doc["learning"]["enabled"] = "applies-safe-changes-itself"
    doc["learning"].pop("keep-only-if", None)
    bad = Proposal("instructions", BAD, "Answer the customer. Be nice.", "no format")

    first = learner_in(root, doc)
    one = first.cycle(bad, costing(0.0))
    assert not one.applied
    assert "did not improve" in one.reason, one.reason
    spent_once = first.evals_spent
    assert spent_once > 0, "the first cycle has to actually pay, or this proves nothing"

    # A DIFFERENT Learner, as a real schedule would build — the point is that the
    # memory is in the workspace and not in the process.
    second = learner_in(root, doc)
    two = second.cycle(bad, costing(0.0))
    assert not two.applied
    assert "refused on" in two.reason, two.reason
    assert "did not improve" in two.reason, (
        "the second refusal must hand back the FIRST one's reason, or a reviewer "
        f"learns only that it was refused: {two.reason}"
    )
    assert second.evals_spent == 0, (
        f"the second cycle scored {second.evals_spent} case(s) to learn something "
        f"the workspace already knew"
    )


def test_a_refusal_the_workspace_caused_is_not_held_against_the_edit(
    tmp_path: Path,
) -> None:
    """`enabled: off` refuses anything at all, and so does a spent ceiling.

    Remembering those would mean a proposal turned away by a switch could never
    be tried again once somebody flipped the switch back — which is a worse
    failure than re-scoring it, and not what the record is for.
    """
    root, doc = workspace(tmp_path)
    off = json.loads(json.dumps(doc))
    off["learning"]["enabled"] = "off"

    lr = learner_in(root, off)
    out = lr.cycle(a_proposal(), costing(0.0))
    assert not out.applied and "switched off" in out.reason, out.reason

    # Switched back on, the same proposal is scored rather than recognised.
    again = learner_in(root, doc)
    second = again.cycle(a_proposal(), costing(0.0))
    assert "refused on" not in second.reason, (
        f"a refusal caused by the workspace was held against the edit: {second.reason}"
    )


def test_a_workspace_with_no_folder_cannot_remember_and_says_nothing_false(
    tmp_path: Path,
) -> None:
    """Invariant P-1: an adapter may be handed the document without the tree.

    Then there is nowhere to keep a refusal, which is an ordinary state. What
    must not happen is a cycle behaving as though it had remembered.
    """
    from pact_adapters.learning import Refusals

    nowhere = Refusals.at(None)
    assert not nowhere.kept
    assert nowhere.why(a_proposal()) is None
    nowhere.add(a_proposal(), "no reason at all")   # must not raise
    assert nowhere.why(a_proposal()) is None, "it cannot remember and must not pretend"


def test_a_refusal_for_drift_is_not_held_against_the_edit_either(
    tmp_path: Path,
) -> None:
    """Drift is a property of how far the agent has moved SINCE the baseline, not
    of this edit.

    Re-baseline and the same proposal is a different question, so remembering it
    would make an edit permanently unaskable because of where the agent happened
    to be when it was first asked. The `enabled: off` test above cannot reach
    this branch — that refusal happens before any scoring — so without this the
    `remember=False` on the drift path is a decision nothing checks.
    """
    from dataclasses import replace as _replace

    from pact_adapters.learning import Baseline

    root, shipped = workspace(tmp_path)
    doc = json.loads(json.dumps(shipped))
    doc["learning"]["enabled"] = "applies-safe-changes-itself"
    doc["learning"].pop("keep-only-if", None)

    far_away = Baseline(instructions="something else entirely, from a long time ago", score=0.5)
    drifted = _replace(learner_in(root, doc), baseline=far_away, max_cumulative_drift=0.05)
    out = drifted.cycle(a_proposal(), costing(0.0))
    assert not out.applied
    assert "drift" in out.reason, out.reason

    # Re-baselined — the same proposal is SCORED again, not recognised.
    fresh = _replace(learner_in(root, doc), baseline=None)
    again = fresh.cycle(a_proposal(), costing(0.0))
    assert "refused on" not in again.reason, (
        f"a drift refusal was held against the edit, so re-baselining cannot "
        f"unblock it: {again.reason}"
    )
