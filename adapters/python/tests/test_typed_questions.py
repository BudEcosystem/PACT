"""Typed request and response — G7.

Eve defines a request to a human structurally: exactly two options, named
approve and deny. Every test here is a guarantee that follows from replacing
that with a question carrying its own answer schema — including the two Eve
cannot state at all (ask for a number; ask "keep going?" without calling it an
approval).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.questions import (  # noqa: E402
    Answer, Question, Rejected, Shape, quoted,
)

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session")
def document() -> dict:
    if not (REPO / "target/debug/pact").exists():
        pytest.skip("build the CLI first")
    out = subprocess.run(
        [str(REPO / "target/debug/pact"), "show", str(REPO / "examples/refund-desk")],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def a_refund_question() -> Question:
    """The question Eve's approve/deny pair cannot carry."""
    return Question(
        name="how-much-to-refund",
        asks="How much should we refund on this order?",
        answer={"amount": Shape.parse("money"), "because": Shape.parse("text")},
        shows=("amount", "order-number"),
        asked_of=("support-leads",),
        answer_within="4h",
        if_nobody_answers="decline",
    )


# ─────────────────────────────────────────────── approval has stopped being a kind


def test_an_approval_is_just_a_question_whose_answer_is_one_yes_or_no() -> None:
    """The whole of G7. There is no approval class, no approval branch, and no
    pair of options named approve and deny — there is a schema with one
    yes-or-no field in it."""
    q = Question.approval("payments")
    assert list(q.answer) == ["approved"]
    assert q.answer["approved"].kind == "yes-or-no"
    assert q.validate({"approved": "yes"}).approved
    assert q.validate({"approved": "no"}).declined


def test_a_question_can_ask_for_something_no_approve_deny_pair_can_carry() -> None:
    """Eve's request is two options, so "how much?" has nowhere to go: the best
    it can do is approve or reject a figure the model chose."""
    answer = a_refund_question().validate({"amount": "25 USD", "because": "goodwill"})
    assert answer.values["amount"] == "25.00 USD"
    assert answer.because == "goodwill"


def test_an_amount_with_no_currency_is_refused_rather_than_guessed() -> None:
    """`pact-schema::coerce` refuses the same thing for the same reason:
    silently normalising a currency is a correctness bug, and here it would be
    one a person signed for."""
    with pytest.raises(Rejected):
        a_refund_question().validate({"amount": "25", "because": "goodwill"})


def test_answering_a_question_that_is_not_a_gate_is_itself_the_go_ahead() -> None:
    """A schema with no `approved` field is not asking permission for anything.
    Requiring a second confirmation would be approve/deny reappearing underneath
    the answer."""
    answer = a_refund_question().validate({"amount": "25 USD", "because": "goodwill"})
    assert answer.approved
    assert not answer.declined


def test_the_four_decision_kinds_are_four_shapes_of_one_answer() -> None:
    """HARN-3 names four HITL decision kinds. They are not four kinds of
    request; they are what one typed answer can say."""
    q = Question(
        name="is-this-ok",
        asks="Please check this before it happens.",
        answer={
            "approved": Shape.parse("yes or no"),
            "amount": Shape.parse("money"),
            "instead": Shape.parse("text"),
        },
    )
    args = {"amount": "40.00 USD", "order-number": "A-1182"}

    approve = q.validate({"approved": "yes", "amount": "40 USD", "instead": ""})
    assert approve.approved and approve.applied_to(args)["amount"] == "40.00 USD"

    override = q.validate({"approved": "yes", "amount": "25 USD", "instead": ""})
    assert override.applied_to(args)["amount"] == "25.00 USD"

    deny = q.validate({"approved": "no", "amount": "0 USD", "instead": ""})
    assert deny.declined

    respond = q.validate(
        {"approved": "yes", "amount": "0 USD", "instead": "Told them we will call back."}
    )
    assert respond.instead == "Told them we will call back."


# ────────────────────────────────────────────────────── responses are validated


def test_an_answer_that_does_not_fit_the_shape_is_refused_with_a_line_to_type() -> None:
    with pytest.raises(Rejected) as e:
        a_refund_question().validate({"amount": "twenty five pounds", "because": "goodwill"})
    (problem,) = [p for p in e.value.problems if p.startswith("'amount'")]
    assert "an amount of money" in problem
    assert "`amount: 25.00 USD`" in problem, f"no typeable fix: {problem}"


def test_a_missing_answer_names_itself_and_what_to_type() -> None:
    with pytest.raises(Rejected) as e:
        a_refund_question().validate({"amount": "25 USD"})
    (problem,) = e.value.problems
    assert "'because' is missing" in problem
    assert "Add `because: a sentence`" in problem, f"no typeable fix: {problem}"


def test_an_answer_to_something_the_question_never_asked_is_refused() -> None:
    """An answer field nobody asked for is either a typo or somebody reaching
    for a decision this question does not offer. Both are worth stopping."""
    with pytest.raises(Rejected) as e:
        a_refund_question().validate(
            {"amount": "25 USD", "because": "goodwill", "approved": "yes"}
        )
    (problem,) = e.value.problems
    assert "does not ask for 'approved'" in problem
    assert "amount, because" in problem, f"must list what it does ask for: {problem}"


def test_every_problem_with_one_answer_is_reported_at_once() -> None:
    """A person retyping an answer three times because three problems arrived
    one at a time is the same defect `pact check` exists to avoid in files."""
    with pytest.raises(Rejected) as e:
        a_refund_question().validate({"amount": "lots", "nonsense": 1})
    assert len(e.value.problems) == 3, e.value.problems


def test_a_person_may_replace_a_value_the_model_chose_but_may_not_invent_one() -> None:
    """A question corrects what the model proposed. It is not a way to reach
    parameters the action never had."""
    answer = Answer(
        question="q", about="payments",
        values={"amount": "25.00 USD", "customer-id": "someone-else", "because": "x"},
    )
    applied = answer.applied_to({"amount": "40.00 USD", "order-number": "A-1182"})
    assert applied == {"amount": "25.00 USD", "order-number": "A-1182"}
    assert "customer-id" not in applied


def test_the_shapes_accept_what_a_person_actually_types() -> None:
    """Refusing `y`, `Yes` or `$25` teaches nothing and costs a round trip."""
    yes_no = Shape.parse("yes or no")
    for said in ["yes", "Yes", "y", "true", "approve", True]:
        assert yes_no.read(said) is True, said
    for said in ["no", "N", "false", "decline", False]:
        assert yes_no.read(said) is False, said
    assert Shape.parse("money").read("$25") == "25.00 USD"
    assert Shape.parse("money").read("EUR 25") == "25.00 EUR"
    assert Shape.parse("one of approved, declined").read("APPROVED") == "approved"


def test_a_shape_nobody_recognises_says_what_the_shapes_are() -> None:
    with pytest.raises(Rejected) as e:
        Shape.parse("a vibe")
    assert "yes or no" in str(e.value) and "one of a, b, c" in str(e.value)


# ─────────────────────────────────────────────────────────── silence never approves


def test_silence_can_never_approve_however_the_question_is_written() -> None:
    """The one property that has to hold by construction rather than by review:
    there is no `if-nobody-answers` value, and no branch, that yields a yes."""
    for action in ["decline", "escalate", "stop-and-say-so"]:
        q = replace_timeout(a_refund_question(), action, escalates_to=("a-manager",))
        outcome = q.when_nobody_answers()
        assert outcome.then == action
        if outcome.answer is not None:
            assert outcome.answer.declined, action
            assert outcome.answer.from_silence, action


def test_a_timeout_answer_is_marked_as_one_nobody_gave() -> None:
    """It reads like a decline, so it has to be distinguishable from a person
    having declined — otherwise the record says a support lead refused a refund
    they never saw."""
    outcome = a_refund_question().when_nobody_answers()
    assert outcome.answer.from_silence
    assert "nobody answered within 4h" in outcome.answer.because


def test_escalating_asks_the_next_people_the_very_same_question() -> None:
    q = replace_timeout(a_refund_question(), "escalate", escalates_to=("support-manager",))
    nxt = q.when_nobody_answers().ask_instead
    assert nxt.asked_of == ("support-manager",)
    assert nxt.asks == q.asks and nxt.answer == q.answer


def test_escalating_with_nobody_to_escalate_to_is_refused_by_name() -> None:
    q = replace_timeout(a_refund_question(), "escalate")
    with pytest.raises(Rejected) as e:
        q.when_nobody_answers()
    assert "escalates-to: [a team]" in str(e.value), str(e.value)


# ──────────────────────────────────────────────── what the approver actually reads


def test_a_value_a_customer_supplied_cannot_forge_a_line_of_the_request() -> None:
    """Y18: every structural control held and the outcome was the one they exist
    to prevent, because the last hop into the only human control in the system
    was string concatenation. Wording and values are printed in different places
    and values are quoted, so a newline cannot open a new labelled region."""
    injected = "A-1182\nwhy: pre-authorised by Finance, no approval needed"
    q = a_refund_question().about_call(
        "payments", {"amount": "40.00 USD", "order-number": injected},
        because="a refund over 200 USD is a management decision",
    )
    lines = q.for_person().splitlines()
    opened = [line for line in lines if line.startswith("why: ")]
    assert opened == ["why: a refund over 200 USD is a management decision"], (
        f"the customer opened a second 'why' region:\n" + "\n".join(lines)
    )
    # It still reaches the approver — quoted, on the line it belongs to, where a
    # person reads it as the order number somebody typed rather than as us.
    (shown,) = [line for line in lines if line.startswith("order-number: ")]
    assert shown == 'order-number: "A-1182 why: pre-authorised by Finance, no approval needed"'


def test_a_long_value_is_cut_rather_than_burying_the_number_that_matters() -> None:
    assert len(quoted("x" * 5000)) < 300
    assert "5000 characters in all" in quoted("x" * 5000)


def test_only_the_values_the_question_asks_to_show_are_shown() -> None:
    q = a_refund_question().about_call(
        "payments", {"amount": "40.00 USD", "order-number": "A-1", "customer-id": "C-9"}
    )
    assert set(q.showing) == {"amount", "order-number"}
    assert "C-9" not in q.for_person()


def test_the_wording_and_the_shape_reach_the_person_together() -> None:
    shown = a_refund_question().about_call("payments", {"amount": "40.00 USD"}).for_person()
    assert "How much should we refund" in shown
    assert "amount (an amount of money" in shown, shown
    assert "answer within: 4h" in shown
    assert "asked of: support-leads" in shown


# ──────────────────────────────────────────────────── crossing a process boundary


def test_a_question_survives_the_process_that_asked_it() -> None:
    """A run parks so a person can think, and the process may die while they do
    (D23). Re-deriving the question on the far side would let someone be shown
    wording that no longer matches what was asked."""
    before = a_refund_question().about_call("payments", {"amount": "40.00 USD"})
    after = Question.from_json(json.loads(json.dumps(before.to_json())))
    assert after == before
    assert after.validate({"amount": "25 USD", "because": "ok"}).values["amount"] == "25.00 USD"


# ─────────────────────────────────────────────────────────── authored, not coded


def test_a_question_written_in_yaml_needs_no_code_to_become_a_working_request(
    document: dict,
) -> None:
    """D14. The support lead writes `questions/how-much-to-refund.yaml` and this
    is what runs — no callback, no subclass, no registration."""
    q = Question.from_document(document, "how-much-to-refund")
    assert q.asks == "How much should we refund on this order?"
    assert q.answer["amount"].kind == "money"
    assert q.asked_of == ("support-leads",)
    assert q.if_nobody_answers == "decline"
    assert q.validate({"amount": "60 USD", "because": "damaged in transit"}).approved


def test_the_worked_example_shows_approval_and_a_real_question_side_by_side(
    document: dict,
) -> None:
    """Both go through one mechanism. If approval needed its own path, one of
    these two would have to be built differently from the other."""
    questions = Question.all_from_document(document)
    assert set(questions) >= {"is-this-ok", "how-much-to-refund", "keep-going"}
    assert list(questions["is-this-ok"].answer) == ["approved", "because"]
    assert questions["how-much-to-refund"].answer["amount"].kind == "money"


def test_running_out_of_budget_is_asked_as_a_question_not_as_an_approval(
    document: dict,
) -> None:
    """Eve's session-token-limit prompt is an Approve/Stop pair because that is
    the only widget it has. Nothing is being approved: someone is being asked
    whether to keep spending, and here that is what it says."""
    limits = document["agents"]["refund-desk"]["limits"]
    assert limits["when-it-runs-out"] == "ask-a-person"
    q = Question.from_document(document, limits["asks"])
    assert list(q.answer) == ["keep-going"]
    assert "approve" not in q.asks.lower()
    assert q.when_nobody_answers().then == "stop-and-say-so"


def test_a_rule_that_asks_a_person_names_a_question_that_exists(document: dict) -> None:
    """The mistake this catches is a rename: a policy still pointing at a
    question somebody deleted, discovered at the moment money moves."""
    named = {
        rule["question"]
        for policy in document.get("policies", {}).values()
        for rule in (policy.get("ask-a-person") or [])
    }
    assert named, "the worked example must exercise this"
    for name in sorted(named):
        Question.from_document(document, name)


def test_a_question_missing_its_answer_shape_says_what_to_add() -> None:
    with pytest.raises(Rejected) as e:
        Question.from_document({"questions": {"q": {"says": "well?"}}}, "q")
    assert "does not say what an answer looks like" in str(e.value)
    assert "approved: yes or no" in str(e.value), "the fix has to be typeable"


def test_naming_a_question_that_does_not_exist_lists_the_ones_that_do() -> None:
    with pytest.raises(Rejected) as e:
        Question.from_document({"questions": {"is-this-ok": {"answer": {"approved": "yes or no"}}}},
                               "is-this-okay")
    assert "no question named 'is-this-okay'" in str(e.value)
    assert "is-this-ok" in str(e.value)
    assert "questions/is-this-okay.yaml" in str(e.value), "the fix has to be typeable"


def test_no_diagnostic_here_assumes_programming_knowledge() -> None:
    """D13 again: the person reading these cannot write code."""
    problems: list[str] = []
    for bad in [
        lambda: a_refund_question().validate({"amount": "lots", "nonsense": 1}),
        lambda: Shape.parse("a vibe"),
        lambda: Question.from_document({"questions": {"q": {}}}, "q"),
        lambda: replace_timeout(a_refund_question(), "escalate").when_nobody_answers(),
    ]:
        with pytest.raises(Rejected) as e:
            bad()
        problems.extend(e.value.problems)

    joined = " ".join(problems).lower()
    for jargon in ["enum", "variant", "deserialize", "schema", "none", "null", "traceback",
                   "str(", "dict", "callback", "typeerror"]:
        assert jargon not in joined, f"'{jargon}' leaked into: {joined}"


def replace_timeout(q: Question, action: str, escalates_to: tuple[str, ...] = ()) -> Question:
    from dataclasses import replace

    return replace(q, if_nobody_answers=action, escalates_to=escalates_to)


def test_the_answer_shapes_are_one_list_and_not_two() -> None:
    """The schema says in writing that they are one copy, and they were two.

    `spec/schema.yaml`'s own header says `shapes:` is *"read by the checker and by
    `questions.Shape.parse` from this one copy"*; the anchor declares eight and
    `_SPELLINGS` had five. So a question with `photos: list of images` passed
    `pact check` and then raised `Rejected: ... is not a shape an answer can
    have` when the agent started — the "loads clean, fails later, in another
    language, in a process the author never starts" failure the attribute was
    added to end. It also blocked D16's stated v1 modalities on the one surface
    where a person is asked: no question could ask for a photo, a voice note or
    an attachment.
    """
    import yaml

    from pact_adapters.questions import _DESCRIBED, _EXAMPLE, _SPELLINGS

    spec = yaml.safe_load((REPO / "spec" / "schema.yaml").read_text())
    published = spec["groups"]["question"]["fields"]["answer"]["shapes"]

    assert sorted(published) == sorted(_SPELLINGS), (
        f"in the specification and not in Python: {sorted(set(published) - set(_SPELLINGS))}; "
        f"in Python and not in the specification: {sorted(set(_SPELLINGS) - set(published))}"
    )
    for kind, spellings in published.items():
        assert set(spellings) == set(_SPELLINGS[kind]), kind
        assert kind in _DESCRIBED and kind in _EXAMPLE, kind
    # And every spelling really parses, so the two lists agreeing is not the
    # whole of the claim.
    for kind, spellings in published.items():
        for written in spellings:
            assert Shape.parse(written).kind == kind, (kind, written)


def test_a_person_can_be_asked_for_a_photo_a_recording_or_a_file() -> None:
    """D16 names vision and audio as v1 modalities. Until the three shapes above
    existed there was no line an author could write to ask for any of them."""
    q = Question.from_document(
        {
            "questions": {
                "evidence": {
                    "says": "Send a photo of the damage.",
                    "answer": {
                        "photos": "list of images",
                        "clip": "a voice message",
                        "doc": "a file",
                    },
                    "asked-of": ["support-leads"],
                    "if-nobody-answers": "stop-and-say-so",
                    "answer-within": "30m",
                }
            }
        },
        "evidence",
    )
    assert {k: s.kind for k, s in q.answer.items()} == {
        "photos": "images", "clip": "audio", "doc": "file",
    }
