"""D4 — AC-3.5's "is this enough to mean anything" gate, measured on a proxy.

`optimising.measured` documents its first parameter as *the held-out COUNT* and
answers `enough-to-mean-something` from it. Its one production caller,
`scoring._margin_line`, handed it `len(verdict_after.results)` — the number of
GRADED RESULTS. On the `Learner.cycle` path the two coincide, because `cycle`
scores against `self.holdout` and `_score` returns one result per case. Nothing
held them together: the coupling lived in the fact that one function happened to
be called by another, and the gate that decides whether an improvement claim is
a measurement at all was reading a number that only stands in for the split.

The direction that matters is over-claiming. A scoring run that graded more than
the held-out split — the train cases too, say, which is the very mistake a frozen
split exists to catch — would make the report call a three-case split big enough
to support a claim. That is the report saying *"this is a measurement"* about
the one arrangement where it certainly is not.

So `Outcome` now carries `held_out`, and `cycle` stamps it from `len(self.holdout)`
ONCE, on the way out, for every exit it has.

That "once" is half the fix. The first version set the field at each of the
twelve `Outcome(...)` exits `cycle` has, and twelve copies of one fact is twelve
chances for the thirteenth exit to forget — which is not hypothetical: the count
was measured missing from three of them mid-repair, and the whole of this file
stayed green, because every test in it took the same `held for review` branch.
So the exits below are covered one by one AND there is only one line left to
forget.

Mutations, both measured:

* Delete the `replace(..., held_out=len(self.holdout))` stamp in `Learner.cycle`.
  Every case of `test_every_exit_that_reports_a_split_reports_the_real_one` goes
  red, and so does `test_the_report_counts_the_cases_that_were_actually_held_out`
  — the count falls to the field default of 0 and the report tells a reviewer
  their three-case split was no cases at all.
* In `scoring._margin_line`, put back `len(getattr(after, "results", ()))` in
  place of `outcome.held_out`. Only
  `test_a_split_too_small_to_claim_on_is_still_too_small` goes red, on the
  caution line — six graded results read as a big enough split. Every other test
  in this file stays green, which is exactly what made the proxy invisible.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.evals import Case, CaseOutcome, Verdict  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.learning import (  # noqa: E402
    APPLIES_ITSELF,
    PROPOSE_ONLY,
    Learner,
    Permissions,
    Proposal,
)
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.scoring import Proposed, render_proposal  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

TRAIN = [
    Case(key="a-clear-approve", when="a lamp arrived broken",
         expect={"decision": "approved"}),
    Case(key="b-outside-window", when="bought a year ago",
         expect={"decision": "declined"}),
    Case(key="c-no-receipt", when="no receipt anywhere",
         expect={"decision": "declined"}),
]
HELD = [
    Case(key="x-personalised", when="a mug with a name on it",
         expect={"decision": "declined"}),
    Case(key="y-sale-item", when="a jacket from the sale",
         expect={"decision": "approved"}),
    Case(key="z-gift", when="a gift with no order number",
         expect={"decision": "declined"}),
]

#: A wording change — the one field a cycle scores — that carries a rule word
#: (`always`), so the cycle measures it and then holds it for review.
EDIT = Proposal(
    field="instructions",
    before="Answer the customer.",
    after="Answer the customer. Always say the decision first.",
    rationale="written from a-clear-approve",
)

#: The same shape of edit with nothing in it the prose classifier recognises, so
#: `classify` answers LOW and the cycle runs past `needs_a_person` to the exits
#: the author's own settings decide. `EDIT` above classifies HIGH — `always`
#: reads as a rule change — and every test in the first version of this file
#: used it, which is how three uncounted exits went unnoticed. (It used to say
#: "in the first sentence" and was HIGH by accident: `sent`, left open, matched
#: `sentence`. `test_a_sentence_is_not_something_that_was_sent.py`.)
WORDING = Proposal(
    field="instructions",
    before="Answer the customer.",
    after="Answer the customer clearly and briefly.",
    rationale="written from b-outside-window",
)


def _learner(**over) -> Learner:
    spec = AgentSpec(name="Desk", description="d", instructions=EDIT.before)
    fields = dict(
        spec=spec, train=list(TRAIN), holdout=list(HELD),
        rules=[], bar=0.5, tools={}, permissions=Permissions.default(),
    )
    fields.update(over)
    return Learner(**fields)


def _cycled(learner: Learner):
    return learner.cycle(
        EDIT, lambda _spec: ReferenceTransport(Script([Turn("approved")] * 12))
    )


def _report(outcome) -> str:
    return render_proposal(
        Proposed(workspace="examples/refund-desk", agent="Desk",
                 field="instructions", source="a file", outcome=outcome)
    )


def test_the_report_counts_the_cases_that_were_actually_held_out() -> None:
    """The plain path: what the reviewer is told is the split the author froze.

    Read off the `Learner` that ran the cycle rather than off anything the run
    produced, so the sentence cannot drift from the thing it describes.
    """
    learner = _learner()
    outcome = _cycled(learner)

    # Which exit this took, said out loud. The suite runs in random order and
    # shares no state by design, but a cycle that came out of a different branch
    # would be a different test wearing this one's name — and the count is set
    # per-branch, so silently testing another branch is the one failure this
    # file cannot afford.
    assert "held for review" in outcome.reason, outcome.reason
    assert outcome.verdict_before is not None, outcome.reason
    assert outcome.held_out == len(learner.holdout) == 3, outcome.held_out

    said = _report(outcome)
    assert "over 3 held-out case(s)" in said, (
        "the report does not say how many cases the claim rests on:\n" + said
    )


def test_a_split_too_small_to_claim_on_is_still_too_small() -> None:
    """The over-claim, which is what the proxy could hide.

    This learner's scorer grades six cases — the whole suite, not the frozen
    three. That is a real mistake with a name: scoring against everything is
    exactly what a held-out split exists to prevent, and it is the arrangement in
    which "six results, so this is a measurement" is most wrong. The split is
    three cases whatever any scoring run returns, and three cases cannot support
    a claim that an optimiser works.
    """
    class ScoresTheWholeSuite(Learner):
        def _score(self, spec, cases, transport_for) -> Verdict:  # type: ignore[override]
            everything = [
                CaseOutcome(key=c.key, passed=True, why="")
                for c in TRAIN + HELD
            ]
            # A better score for the candidate, so the run reaches the margin
            # line rather than being refused before it.
            score = 1.0 if spec.instructions == EDIT.after else 0.5
            return Verdict("PASS", score, 0.7, everything)

    learner = ScoresTheWholeSuite(
        spec=AgentSpec(name="Desk", description="d", instructions=EDIT.before),
        train=list(TRAIN), holdout=list(HELD), rules=[], bar=0.5, tools={},
        permissions=Permissions.default(),
    )
    outcome = _cycled(learner)
    assert "held for review" in outcome.reason, outcome.reason
    assert outcome.verdict_after is not None, outcome.reason
    assert len(outcome.verdict_after.results) == 6, "the stand-in scorer changed"

    said = _report(outcome)
    assert "over 3 held-out case(s)" in said, (
        "the report counted the graded results and not the frozen split, so a "
        "three-case split was reported as six:\n" + said
    )
    assert "not a measurement" in said, (
        "a margin cleared over three held-out cases was reported as a "
        "measurement:\n" + said
    )


def test_a_split_big_enough_is_not_qualified_away() -> None:
    """The other side of the same gate: six held-out cases clear the caution, and
    a report that hedged a real measurement would be as unhelpful as one that
    over-claimed."""
    six = HELD + [
        Case(key=f"w-{i}", when=f"another situation {i}",
             expect={"decision": "approved"})
        for i in range(3)
    ]
    outcome = _cycled(_learner(holdout=six))
    assert "held for review" in outcome.reason, outcome.reason
    assert outcome.held_out == 6, outcome.held_out
    said = _report(outcome)
    assert "not a measurement" not in said, said
    assert "margin" in said, said


class _FixedScore(Learner):
    """A `Learner` whose scoring is a decision rather than a measurement.

    The exits below are reached by the RELATION between the two scores, and the
    reference transport answers the same words whatever the instructions say —
    so a real scoring run puts `after == before` and every path lands on the
    same refusal. What is under test here is which COUNT reaches the report, not
    how a score is arrived at, so the score is stated and the branch is chosen.
    """

    #: What the candidate scores relative to the incumbent's 0.5.
    candidate_scores = 1.0

    def _score(self, spec, cases, transport_for) -> Verdict:  # type: ignore[override]
        results = [CaseOutcome(key=c.key, passed=True, why="") for c in cases]
        score = (
            self.candidate_scores if spec.instructions == WORDING.after else 0.5
        )
        return Verdict("PASS", score, 0.5, results)


def _fixed(permissions: Permissions, candidate_scores: float = 1.0) -> Learner:
    learner = _FixedScore(
        spec=AgentSpec(name="Desk", description="d", instructions=WORDING.before),
        train=list(TRAIN), holdout=list(HELD), rules=[], bar=0.5, tools={},
        permissions=permissions,
    )
    learner.candidate_scores = candidate_scores
    return learner


#: The verdict-bearing exits of `Learner.cycle` — every answer a reviewer can be
#: given that carries two scores and therefore prints a margin line. Each one
#: used to build its own `Outcome` and set the count by hand.
#:
#: `id`, how to get there, what the answer says, and whether it applied.
EXITS = (
    pytest.param(
        Permissions.default(), EDIT, 1.0, "held for review", False,
        id="a-person-must-look-at-it",
    ),
    pytest.param(
        Permissions(enabled=PROPOSE_ONLY, low=("instructions",), stated=True),
        WORDING, 1.0, "held for review", False,
        id="propose-only-so-nothing-applies-itself",
    ),
    pytest.param(
        Permissions(enabled=APPLIES_ITSELF, low=("instructions",), stated=True),
        WORDING, 1.0, "held-out score improved", True,
        id="applied",
    ),
    pytest.param(
        Permissions(enabled=APPLIES_ITSELF, low=("instructions",), stated=True),
        WORDING, 0.2, "did not improve", False,
        id="refused-because-it-did-not-improve",
    ),
)


@pytest.mark.parametrize("permissions,proposal,candidate,says,applied", EXITS)
def test_every_exit_that_reports_a_split_reports_the_real_one(
    permissions: Permissions, proposal: Proposal, candidate: float,
    says: str, applied: bool,
) -> None:
    """The invariant, on every answer a reviewer can be handed.

    Not one path. `Learner.cycle` has four exits that carry both verdicts, and
    the count was correct on one of them while the whole of this file passed.
    The two a reviewer sees most are the ones that were wrong: `applied` and the
    propose-only refusal, which is the answer the worked example gets on every
    single cycle.
    """
    learner = _fixed(permissions, candidate)
    outcome = learner.cycle(
        proposal, lambda _spec: ReferenceTransport(Script([Turn("approved")] * 12))
    )

    assert says in outcome.reason, (
        f"this case meant to reach the {says!r} exit and reached: {outcome.reason}"
    )
    assert outcome.applied is applied, outcome.reason
    assert outcome.verdict_before is not None and outcome.verdict_after is not None, (
        f"no verdicts, so no margin line and nothing to count: {outcome.reason}"
    )
    assert outcome.held_out == len(learner.holdout) == 3, (
        f"the {says!r} exit reported {outcome.held_out} held-out case(s) about a "
        f"split of {len(learner.holdout)}"
    )

    said = _report(outcome)
    assert "over 3 held-out case(s), so this is not a measurement" in said, (
        "the report did not tell the reviewer how few cases the margin rests "
        "on:\n" + said
    )


def test_a_count_that_never_arrived_is_not_printed_as_a_count_of_none() -> None:
    """A lost count says it was lost, rather than reporting a split of zero.

    `Outcome.held_out` defaults to 0, and 0 is the value that makes the report
    print *"over 0 held-out case(s), so this is not a measurement"* — a sentence
    about a three-case split that is wrong, and that reads as an abundance of
    caution rather than as a bug. That is precisely how three uncounted exits
    survived a full green suite.

    A cycle cannot legitimately produce this: `_decide` refuses before spending
    anything when nothing is held out, and that refusal carries no verdicts. So
    two verdicts and a zero mean the count was dropped between the `Learner` and
    the page, and the page says so.

    Mutation: delete the `if not said["held-out-cases"]` branch in
    `scoring._margin_line`. Without it this test goes red on the "did not reach"
    sentence and the report resumes claiming a real split was no cases at all.
    """
    learner = _fixed(
        Permissions(enabled=APPLIES_ITSELF, low=("instructions",), stated=True)
    )
    outcome = learner.cycle(
        WORDING, lambda _spec: ReferenceTransport(Script([Turn("approved")] * 12))
    )
    assert outcome.verdict_after is not None and outcome.verdict_after.results

    # The count dropped on the way out, which is the shape of the defect rather
    # than a state any branch of `_decide` can reach.
    outcome.held_out = 0
    said = _report(outcome)

    assert "over 0 held-out case(s)" not in said, (
        "a split whose size never arrived was reported as a split of no cases "
        "at all:\n" + said
    )
    assert "did not reach this report" in said, (
        "the report printed a margin without saying that the one number "
        "deciding whether it means anything is missing:\n" + said
    )
