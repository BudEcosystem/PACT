"""A permission the author granted is a permission the cycle can act on (P5).

`learning.yaml`'s `may-improve-on-its-own:` is `tier: core` and offers four
words — `phrasing`, `examples`, `skill-notes`, `when-skills-are-used`. Each maps
to spec fields through `SAFE_TO_CHANGE`, and that mapping is the author's whole
grant: it is how a support lead says *this may change without me, and nothing
else may*.

Three of the four could never be acted on. `CAN_BE_APPLIED` was the one-element
tuple `("instructions",)`, so an author who wrote
`may-improve-on-its-own: [skill-notes]` granted something no cycle could ever
put into effect, and every proposal came back with a sentence about a mechanical
limit of the process rather than about their document. That is a governance
surface that loads and does nothing — the defect this format refuses everywhere
else, sitting in the one file whose subject is what may change unattended.

The mechanical excuse was real for exactly one of them and false for the other
two. `_with` rewrites the spec that gets SCORED, so a field a run never reads
cannot be applied: both scoring runs would grade the same agent. A skill's body
and its four routing lines are not that — `SkillSpec.in_words()` puts every one
of them into the system message, so a change to them changes what the model is
told and therefore what it scores. What was missing was the ability to rewrite
one, not the ability to score one.

So: `skill-notes` and `when-skills-are-used` become real, `examples` is reported
for the reason that is actually true about it, and the author's grant means what
it says.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from pact_adapters.ir import AgentSpec, SkillSpec  # noqa: E402
from pact_adapters.learning import (  # noqa: E402
    CAN_BE_APPLIED,
    SAFE_TO_CHANGE,
    Learner,
    Permissions,
    Proposal,
)

#: A desk with one written procedure. The procedure's body and its routing lines
#: are what a cycle may now rewrite; the desk's own `description:` is what it may
#: not, and the two are in one document so the difference is measured rather than
#: asserted.
DESK = AgentSpec(
    name="refund-desk",
    description="Decides refunds.",
    instructions="Answer the question.",
    skills=(
        SkillSpec(
            name="refund-policy",
            description="How to decide a refund.",
            use_when="the customer is asking for money back",
            do_not_use_when="the customer wants an exchange",
            if_unsure="decline and hand to a person",
            content="Refunds are available for 30 days.",
        ),
    ),
)


def _learner(**kw) -> Learner:
    """A learner over the desk above. `_with` builds a candidate and scores
    nothing, so the cases, rules, bar and tools are empty on purpose — what is
    under test is which candidate can be BUILT."""
    return Learner(
        spec=DESK,
        train=[],
        holdout=[],
        rules=[],
        bar=0.5,
        tools={},
        permissions=Permissions(**kw),
    )


# ─────────────────────────────────── the grant and what can be acted on agree


def test_every_word_the_author_may_grant_names_a_field_a_cycle_can_apply() -> None:
    """The register that closes the gap, stated as a property.

    A word offered under `may-improve-on-its-own:` that names a field no cycle
    can apply is a permission the author cannot use. Either it is applicable, or
    it is on the list of fields nothing in a run reads — and that list has to say
    why, one entry at a time, so a third state cannot appear by omission.
    """
    from pact_adapters.learning import READ_BY_NO_RUN

    for word, fields in SAFE_TO_CHANGE.items():
        for field in fields:
            assert field in CAN_BE_APPLIED or field in READ_BY_NO_RUN, (
                f"`may-improve-on-its-own: [{word}]` grants a change to `{field}`, and a "
                f"cycle can neither apply it nor say why not. Add it to CAN_BE_APPLIED, or "
                f"to READ_BY_NO_RUN with the reason no run reads it."
            )


def test_a_reason_is_written_for_every_field_no_run_reads() -> None:
    """An excuse with no reason is the shape this whole module argues against."""
    from pact_adapters.learning import READ_BY_NO_RUN

    for field, why in READ_BY_NO_RUN.items():
        assert len(why) > 20, f"`{field}` is excused with no real reason"


# ────────────────────────────────────────────────── what became possible (P5)


def test_a_skills_body_can_be_rewritten_because_a_run_reads_it() -> None:
    """`skill-notes` was granted and could not be acted on.

    The body reaches the model through `SkillSpec.in_words()`, so a candidate
    carrying a different one is genuinely a different agent to score — which is
    the whole condition `CAN_BE_APPLIED` exists to express.
    """
    learner = _learner(enabled="propose-only", low=("skill-notes",))
    candidate = learner._with(
        Proposal("content", "Refunds are available for 30 days.", "Refunds are available for 30 days from delivery.")
    )
    assert candidate is not DESK
    assert candidate.skills[0].content == "Refunds are available for 30 days from delivery."
    # And nothing else moved.
    assert candidate.instructions == DESK.instructions
    assert candidate.skills[0].use_when == DESK.skills[0].use_when
    # The words really do reach the model.
    assert "from delivery" in candidate.skills[0].in_words()


@pytest.mark.parametrize(
    ("field", "before"),
    [
        ("use-when", "the customer is asking for money back"),
        ("do-not-use-when", "the customer wants an exchange"),
        ("if-unsure", "decline and hand to a person"),
    ],
)
def test_each_routing_line_can_be_rewritten(field: str, before: str) -> None:
    """`when-skills-are-used` names three fields, and all three are routing.

    They decide which procedure the model opens, which is why the schema keeps
    this word off by default — and why it has to actually work when it is on.

    `before` is the procedure's REAL current text, because that is what says
    which procedure the edit is for.
    """
    learner = _learner(enabled="propose-only", low=("when-skills-are-used",))
    candidate = learner._with(Proposal(field, before, "the customer mentions a refund"))
    attr = field.replace("-", "_")
    assert getattr(candidate.skills[0], attr) == "the customer mentions a refund"
    assert candidate.skills[0].content == DESK.skills[0].content


def test_a_proposal_against_text_no_procedure_holds_is_refused() -> None:
    """A proposal is made against what the cycle READ.

    If no procedure carries the text being replaced, the document has moved
    since — and applying the edit to whichever procedure happened to be first
    would silently rewrite the wrong one.
    """
    learner = _learner(enabled="propose-only", low=("when-skills-are-used",))
    with pytest.raises(ValueError) as raised:
        learner._with(Proposal("use-when", "something nobody wrote", "anything"))
    assert "has moved" in str(raised.value)


def test_instructions_still_apply_exactly_as_before() -> None:
    """The one field that always worked, unchanged."""
    learner = _learner(enabled="propose-only")
    candidate = learner._with(Proposal("instructions", "Answer the question.", "Answer briefly."))
    assert candidate.instructions == "Answer briefly."
    assert candidate.skills == DESK.skills


# ──────────────────────────────────────────── what is still refused, and why


def test_a_field_no_run_reads_is_refused_for_the_reason_that_is_true() -> None:
    """`examples` names `description:`, and no run reads it.

    The refusal has to say THAT, rather than a sentence about which fields this
    process happens to rewrite — a reviewer reading the second one learns
    nothing about their document.
    """
    learner = _learner(enabled="propose-only", low=("examples",), stated=True)
    with pytest.raises(ValueError) as raised:
        learner._with(Proposal("description", "Decides refunds.", "Decides refunds fairly."))
    said = str(raised.value)
    assert "description" in said
    assert "no run reads" in said or "nothing in a run reads" in said


def test_a_high_risk_field_is_still_refused_by_the_classifier_and_not_by_this() -> None:
    """Widening what CAN be applied must not widen what MAY be.

    `uses:` is on `HIGH_RISK_FIELDS`, and the sentence a reviewer gets about it
    has to be the classifier's — the mechanical limit must not mask a governance
    answer. This is the property `cycle` already had and that P5 must not break.
    """
    learner = _learner(enabled="applies-safe-changes-itself", low=("phrasing",))
    with pytest.raises(ValueError):
        learner._with(Proposal("uses", "a", "b"))


def test_a_skill_change_on_a_spec_with_no_skills_says_so() -> None:
    """A grant is not a promise that the document has one."""
    bare = AgentSpec(name="d", description="x", instructions="y")
    learner = Learner(
        spec=bare, train=[], holdout=[], rules=[], bar=0.5, tools={},
        permissions=Permissions(enabled="propose-only", low=("skill-notes",)),
    )
    with pytest.raises(ValueError) as raised:
        learner._with(Proposal("content", "a", "b"))
    assert "no written procedure" in str(raised.value)
