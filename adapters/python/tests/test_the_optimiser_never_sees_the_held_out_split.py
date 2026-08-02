"""AC-3.5 — where a proposal comes from, and what it must not look at.

> The optimizer improves at least one reference agent's small-model eval score by
> a declared margin over the un-optimised baseline, with a frozen held-out split
> and the split locked before optimisation begins.

`Learner.cycle` has always taken a proposal **handed in**; nothing generated one.
This is that half, and it is deliberately the smaller half — the gate is where
the value is, and an optimiser that could route around it would be worse than
none.

**The property worth more than the rest put together is what it does NOT read.**
An optimiser tuned on the cases it is scored against reports an improvement that
exists only in the tuning, which is the failure a frozen split exists to prevent
and the one the criterion names twice.

**What is NOT met here, and why:** *"improves … by a declared margin"* is a
measurement against a small model, and no model is served in this environment.
`MARGIN` is declared and `cleared_the_margin` computes the answer; the empirical
claim is recorded as unmet in `docs/70-PRODUCTION-GAP-REGISTER.md` rather than
asserted from a scripted stand-in. A scripted model can prove the mechanism and
cannot prove an improvement.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.evals import Case, CaseOutcome, Verdict  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.learning import Learner, Permissions  # noqa: E402
from pact_adapters.optimising import (  # noqa: E402
    MARGIN,
    CannotOptimise,
    cleared_the_margin,
    improve_on,
    measured,
    what_went_wrong,
)

TRAIN = [
    Case(key="a-clear-approve", when="a lamp arrived broken", expect={"decision": "approved"}),
    Case(key="b-outside-window", when="bought a year ago", expect={"decision": "declined"}),
]
HELD = [
    Case(key="z-personalised", when="a mug with a name on it", expect={"decision": "declined"}),
    Case(key="y-sale-item", when="a jacket from the sale", expect={"decision": "approved"}),
]


def _learner(**over) -> Learner:
    spec = AgentSpec(name="Desk", description="d", instructions="Answer the customer.")
    fields = dict(
        spec=spec, train=list(TRAIN), holdout=list(HELD),
        rules=[], bar=0.5, tools={}, permissions=Permissions.default(),
    )
    fields.update(over)
    return Learner(**fields)


def _verdict(failing: list[str]) -> Verdict:
    results = [
        CaseOutcome(
            key=c.key, passed=c.key not in failing,
            why="said the wrong thing" if c.key in failing else "",
        )
        for c in TRAIN + HELD
    ]
    return Verdict("FAIL", 0.5, 0.7, results)


# ────────────────────── the property the criterion names twice


def test_a_proposal_is_never_written_from_a_held_out_case() -> None:
    """The failure a frozen split exists to prevent.

    Every case fails here, including both held-out ones. What reaches the model
    must be the TRAIN failures and nothing else — an optimiser that read the
    held-out cases would produce an agent that scores well on them for the one
    reason that does not count.
    """
    seen: list[str] = []

    def ask(prompt: str) -> str:
        seen.append(prompt)
        return "Answer the customer. Say the decision first."

    proposal = improve_on(_learner(), _verdict([c.key for c in TRAIN + HELD]), ask)
    assert proposal is not None
    assert seen, "the model was never asked"

    prompt = seen[0]
    for held in HELD:
        assert held.when not in prompt, (
            f"`{held.key}`'s wording reached the optimiser's prompt — an "
            f"improvement measured after that is measured on the answers:\n{prompt}"
        )
        # AND the rationale, which is where the case KEYS appear. Asserting only
        # on the prompt let a mutation through: the prompt carries each case's
        # text and not its key, so including a held-out case leaked nothing the
        # first version looked at. The rationale names exactly what was written
        # from, which is the observable that matters.
        assert held.key not in proposal.rationale, (
            f"the proposal was written from held-out case `{held.key}`: "
            f"{proposal.rationale}"
        )
    assert any(c.key in proposal.rationale for c in TRAIN), proposal.rationale



def test_it_refuses_when_nothing_was_held_out() -> None:
    """No frozen split, no honest measurement. Refused rather than run, because
    a number produced here would look exactly like a real one."""
    with pytest.raises(CannotOptimise) as refused:
        improve_on(_learner(holdout=[]), _verdict(["a-clear-approve"]), lambda _p: "x")
    assert "holds nothing out" in str(refused.value)
    assert "split: held-out" in str(refused.value), "it must say what to type"


# ───────────────────────────── what it proposes, and what it does not


def test_an_agent_that_got_everything_right_gets_no_proposal() -> None:
    """`None` is not a failure. An optimiser that invented an edit for a working
    agent would be changing it to look busy."""
    assert improve_on(_learner(), _verdict([]), lambda _p: "something new") is None


def test_a_model_that_changes_nothing_produces_no_proposal() -> None:
    """A proposal identical to the incumbent would be scored twice at full price
    and refused — `Learner.cycle` says so — so it is not made."""
    same = _learner()
    got = improve_on(
        same, _verdict(["a-clear-approve"]), lambda _p: same.spec.instructions
    )
    assert got is None
    assert improve_on(same, _verdict(["a-clear-approve"]), lambda _p: "   ") is None


def test_it_writes_from_the_worst_few_rather_than_everything() -> None:
    """A proposal written from every failure at once is a rewrite, and the gate
    refuses rewrites — `ESC-SHRINK` and the drift limit both bite. An edit that
    fixes the clearest failures is one a person can review."""
    many = [
        CaseOutcome(key=f"case-{i}", passed=False, why="wrong") for i in range(9)
    ]
    worst = what_went_wrong(Verdict("FAIL", 0.0, 0.7, many))
    assert len(worst) == 3, worst
    assert [c.key for c in worst] == ["case-0", "case-1", "case-2"]


def test_what_it_proposes_still_goes_through_every_gate() -> None:
    """It proposes; it does not apply. `Learner.cycle` is still in front of it,
    which is the only arrangement D23 permits near decision logic."""
    learner = _learner()
    proposal = improve_on(
        learner, _verdict(["a-clear-approve"]),
        lambda _p: "Answer the customer. Always approve refunds under 50 USD.",
    )
    assert proposal is not None

    from pact_adapters.script import Script, Turn
    from pact_adapters.transports.mock import ReferenceTransport

    # SCORED, then held. `Always approve refunds under 50 USD` is high-risk
    # prose, and `cycle` deliberately measures a high-risk edit before holding it
    # so the reviewer sees the evidence — the early refusal is for a field
    # `_with` cannot apply, and `instructions` is not one. An earlier version of
    # this test asserted the proposal never reached a model, which is the
    # behaviour of the other branch.
    out = learner.cycle(
        proposal, lambda _spec: ReferenceTransport(Script([Turn("approved")] * 8))
    )
    assert not out.applied
    assert "held for review" in out.reason, out.reason
    assert out.classification.risk == "high", out.classification
    assert out.verdict_before is not None, (
        "a high-risk edit is measured and THEN held — evidence does not buy "
        "permission, and a reviewer needs the evidence"
    )


# ──────────────────────────── the margin, declared and computed


def test_the_margin_is_declared_and_not_a_callers_choice() -> None:
    """A margin a caller picks is a margin that grows to fit the result."""
    assert MARGIN == 0.05
    assert cleared_the_margin(0.60, 0.65) is True
    assert cleared_the_margin(0.60, 0.64) is False
    # And it is stricter than `Learner.cycle`'s own `after > before`, which is
    # the right question for APPLYING an edit and the wrong one for claiming an
    # optimiser works.
    assert cleared_the_margin(0.60, 0.601) is False


def test_a_run_says_whether_it_measured_enough_to_mean_anything() -> None:
    """A margin cleared over three cases is not a result. `Verdict` already
    refuses a percentage over too few cases; this is the same caution one level
    up."""
    said = measured(len(_learner().holdout), Verdict("FAIL", 0.5, 0.7, []), Verdict("PASS", 0.7, 0.7, []))
    assert said["cleared-the-margin"] is True
    assert said["improved-by"] == 0.2
    assert said["split-locked-before"] is True
    assert said["enough-to-mean-something"] is False, (
        "two held-out cases is not enough to claim an improvement, and the "
        "report has to say so"
    )
