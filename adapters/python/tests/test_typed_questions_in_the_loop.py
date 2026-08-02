"""A typed question, executed — G7 where it actually bites.

The module tests next door prove the shape. These prove the loop obeys it: that
a person's answer is validated before anything happens, that it can set a value
the model chose, that it can replace the action entirely, and that a question
which is not an approval works through the same path as one that is.

If any of this only decorated the run, every assertion below would still pass
with the answer thrown away — so each one is written against what the tool
actually received.
"""

from __future__ import annotations

import asyncio
#: The harness is read as source, not imported, to enumerate every place a run
#: can park — see `_every_suspend_in_the_harness`.
import ast
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from consenting import allowing_the_connection  # noqa: E402
from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec, ToolSpec  # noqa: E402
from pact_adapters.loops import Loop  # noqa: E402
from pact_adapters.questions import (  # noqa: E402
    Question, Rejected, Shape, questions_for,
)
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.suspension import (  # noqa: E402
    ASKED_A_PERSON, NEEDS_APPROVAL, Resumption, Suspension, WrongAnswer,
)
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

SPEC = AgentSpec(
    name="Refund Desk",
    description="Decides refunds",
    instructions="Decide, then issue the refund.",
    tools=(ToolSpec("zendesk", "read the ticket"), ToolSpec("payments", "issue a refund")),
)

GATED = frozenset({"payments"})


@pytest.fixture(scope="session")
def document() -> dict:
    if not (REPO / "target/debug/pact").exists():
        pytest.skip("build the CLI first")
    out = subprocess.run(
        [str(REPO / "target/debug/pact"), "show", str(REPO / "examples/refund-desk")],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


class Watching:
    """Records what each tool was actually called with."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def tools(self) -> dict:
        def zendesk(a):
            self.calls.append(("zendesk", dict(a)))
            return "lamp, 6 days ago, broken, 40 USD"

        def payments(a):
            self.calls.append(("payments", dict(a)))
            return f"refunded {a.get('amount')}"

        return {"zendesk": zendesk, "payments": payments}

    def args_of(self, name: str) -> dict:
        return next(a for n, a in self.calls if n == name)


def script() -> Script:
    """A parallel batch: read the ticket AND issue the refund in one step."""
    return Script([
        Turn("Reading the ticket and issuing the refund.",
             (ToolCall("zendesk", {"id": "T-1"}),
              ToolCall("payments", {"amount": "40.00 USD", "order-number": "A-1182"}))),
        Turn("Done."),
    ])


def how_much() -> Question:
    """A question no approve/deny pair can carry."""
    return Question(
        name="how-much-to-refund",
        asks="How much should we refund on this order?",
        answer={"amount": Shape.parse("money"), "because": Shape.parse("text")},
        shows=("amount", "order-number"),
        asked_of=("support-leads",),
        if_nobody_answers="decline",
    )


def is_this_ok() -> Question:
    return Question(
        name="is-this-ok",
        asks="Please check this before it happens.",
        answer={"approved": Shape.parse("yes or no"), "because": Shape.parse("text")},
        shows=("amount",),
        if_nobody_answers="decline",
    )


def go(**kw):
    seen = Watching()
    result = asyncio.run(
        run(SPEC, ReferenceTransport(script()), "refund me", seen.tools(),
            needs_approval=GATED, **kw)
    )
    return result, seen


# ─────────────────────────────────────────────────────── the request that is put


def test_the_question_the_author_wrote_is_what_the_person_is_asked() -> None:
    result, _ = go(asking={"payments": how_much()})
    assert result.halted == "suspended"
    assert "How much should we refund on this order?" in result.suspension.in_words


def test_the_wait_asks_for_the_shape_the_question_declared() -> None:
    """Not two options named approve and deny. That substitution is what makes
    Eve's own budget prompt pretend to be an approval."""
    result, _ = go(asking={"payments": how_much()})
    asked = {e.name: e.shape.kind for e in result.suspension.asks}
    assert asked == {"payments.amount": "money", "payments.because": "text"}


def test_only_the_values_the_question_asks_to_show_reach_the_person() -> None:
    result, _ = go(asking={"payments": how_much()})
    words = result.suspension.in_words
    assert 'amount: "40.00 USD"' in words
    assert 'order-number: "A-1182"' in words


def test_what_the_person_reads_survives_the_process_that_asked_it() -> None:
    """The run parks so somebody can think, and the process may die while they
    do. Rebuilding the request afterwards could show them different words."""
    result, _ = go(asking={"payments": how_much()})
    revived = Suspension.from_json(result.suspension.to_json())
    assert revived.in_words == result.suspension.in_words
    assert {e.name: e.shape.kind for e in revived.asks} == {
        "payments.amount": "money", "payments.because": "text"
    }


# ───────────────────────────────────────────────────── the answer that comes back


def test_a_person_can_set_the_figure_and_the_tool_receives_theirs() -> None:
    """The case Eve structurally cannot reach: its request is two options, so
    the most a person can do is approve or reject the number the model chose."""
    first, _ = go(asking={"payments": how_much()})
    result, seen = go(
        asking={"payments": how_much()},
        resume=first.suspension,
        answer=first.suspension.answer(
            **{"payments.amount": "25 USD", "payments.because": "postage only"}
        ),
    )
    assert result.halted == "final"
    assert seen.args_of("payments")["amount"] == "25.00 USD", seen.calls
    assert seen.args_of("payments")["order-number"] == "A-1182", "untouched values stay"


def test_answering_a_question_that_is_not_a_gate_is_itself_the_go_ahead() -> None:
    """Asking "how much?" and then asking a second time whether they meant it
    would be approve/deny growing back underneath the answer."""
    first, _ = go(asking={"payments": how_much()})
    result, seen = go(
        asking={"payments": how_much()},
        resume=first.suspension,
        answer=first.suspension.answer(
            **{"payments.amount": "25 USD", "payments.because": "postage only"}
        ),
    )
    assert result.halted == "final"
    assert any(n == "payments" for n, _ in seen.calls)


def test_a_person_may_replace_the_action_with_their_own_answer() -> None:
    """`answer-instead` in the schema; `respond-on-behalf` in HARN-3. Not a
    fourth kind of request — a fourth thing one typed answer can say."""
    q = Question(
        name="is-this-ok",
        asks="Please check this before it happens.",
        answer={"approved": Shape.parse("yes or no"), "instead": Shape.parse("text")},
    )
    first, _ = go(asking={"payments": q})
    result, seen = go(
        asking={"payments": q},
        resume=first.suspension,
        answer=first.suspension.answer(
            payments="yes", **{"payments.instead": "I refunded this by hand."}
        ),
    )
    assert result.halted == "final"
    assert not any(n == "payments" for n, _ in seen.calls), "the tool must not have run"
    assert "I refunded this by hand." in json.dumps(result.trace())


def test_declining_stops_the_tool_and_ends_the_run_in_the_persons_own_words() -> None:
    """A refusal is an ANSWER: it ends its own wait rather than restating it.

    This asserted `suspended` for as long as `_cleared` returned a bare bool, so
    a person who said no and a person who had said nothing were the same value
    and both re-parked. Ending the run is the guarantee `rulings.py` exists for,
    and the `because:` they typed reaches the record so the model can say
    something to the customer instead of the run stopping with nothing to show.
    """
    first, _ = go(asking={"payments": is_this_ok()})
    result, seen = go(
        asking={"payments": is_this_ok()},
        resume=first.suspension,
        answer=first.suspension.answer(
            payments="no", **{"payments.because": "outside the window"}
        ),
    )
    assert result.halted == "final"
    assert not any(n == "payments" for n, _ in seen.calls)
    assert "outside the window" in json.dumps(result.trace())


def test_an_answer_that_does_not_fit_the_shape_never_reaches_the_tool() -> None:
    """The dangerous failure would be accepting it and dropping the value: the
    person believes they set 25 and the model's 40 goes out."""
    first, _ = go(asking={"payments": how_much()})
    with pytest.raises(Exception) as e:
        first.suspension.answer(
            **{"payments.amount": "twenty five quid", "payments.because": "x"}
        )
    assert "payments.amount" in str(e.value)
    assert "25.00 USD" in str(e.value), f"the fix has to be typeable: {e.value}"


def test_a_half_answered_question_leaves_the_run_where_it_was() -> None:
    """Built past the front-door check on purpose, so what is under test is the
    loop's own guard rather than the one the person typing already met."""
    from pact_adapters.suspension import Resumption

    first, _ = go(asking={"payments": how_much()})
    result, seen = go(
        asking={"payments": how_much()},
        resume=first.suspension,
        answer=Resumption(first.suspension.correlation_key, {"payments.amount": "25 USD"}),
    )
    assert result.halted == "suspended"
    assert not any(n == "payments" for n, _ in seen.calls)


def test_two_calls_blocked_at_once_cannot_answer_for_each_other() -> None:
    """A parallel batch is exactly where an approval gate fires, so one flat
    answer namespace would let a yes about the cheap call clear the costly one."""
    result, _ = go(gates={"zendesk": NEEDS_APPROVAL, "payments": NEEDS_APPROVAL},
                   asking={"payments": how_much(), "zendesk": how_much()})
    names = sorted(e.name for e in result.suspension.asks)
    assert names == ["payments.amount", "payments.because",
                     "zendesk.amount", "zendesk.because"]


# ─────────────────────────────────────────────────── nothing changes when unused


def test_a_run_with_no_questions_behaves_exactly_as_before() -> None:
    """Approval shorthand is the boolean-schema case of the same mechanism, so
    the mechanism has to cost nothing when nobody uses the general form."""
    first, _ = go()
    assert first.halted == "suspended"
    result, seen = go(resume=first.suspension, approved=frozenset({"payments"}))
    assert result.halted == "final"
    assert seen.args_of("payments")["amount"] == "40.00 USD"


# ──────────────────────────────────────────────────────── authored, not coded


def test_the_worked_example_wires_its_questions_with_no_code(document: dict) -> None:
    """D14. `policies/approvals.yaml` names a question, `limits.asks` names
    another, and this is the whole of the wiring."""
    wired = questions_for(document, "refund-desk")
    assert wired["zendesk"].name == "is-this-ok"
    assert wired["decision"].name == "keep-going", "the budget question is asked as itself"
    assert wired["payments"].because, "the rule's reason reaches the person"


def test_two_rules_over_one_tool_stay_two_rules(document: dict) -> None:
    """`policies/approvals.yaml` asks `is-this-ok` above 200 USD and
    `how-much-to-refund` above 500. Keyed by tool name in rule order, the two
    collapsed to one and the last won — so a 210 USD refund was put to a person
    as the 500 USD question, and the lower rule's `because:` was never shown.
    Nothing reported the loss, which is the silent degradation of a governance
    setting T7 forbids and D28-2 names.

    Both still apply at 600, and the narrower one wins: over 200 a person
    approves the figure the model chose, over 500 a person sets it, and 600 is
    both."""
    wired = questions_for(document, "refund-desk")

    at_210 = wired.for_call("payments", {"amount": "210.00 USD"})
    assert at_210 is not None and at_210.name == "is-this-ok"
    assert at_210.because == "a refund over 200 USD is a management decision"

    at_600 = wired.for_call("payments", {"amount": "600.00 USD"})
    assert at_600 is not None and at_600.name == "how-much-to-refund"


def test_a_rule_pointing_at_a_deleted_question_is_caught_before_money_moves(
    document: dict,
) -> None:
    broken = json.loads(json.dumps(document))
    broken["policies"]["approvals"]["ask-a-person"][0]["question"] = "is-this-okay"
    with pytest.raises(Rejected) as e:
        questions_for(broken, "refund-desk")
    assert "is-this-okay" in str(e.value)
    assert "questions/is-this-okay.yaml" in str(e.value), "the fix has to be typeable"


def test_the_person_reads_the_rule_that_actually_fired(document: dict) -> None:
    """The same defect, one level up: it is not enough that the right question
    is *chosen*, the right wording has to reach the approver. A 210 USD refund
    must read "Please check this before it happens." with the 200 USD reason
    under it — not "How much should we refund on this order?", which is the
    question for a decision nobody has reached yet."""
    spec = AgentSpec.from_document(document, "refund-desk")
    seen = Watching()

    def script_210() -> Script:
        return Script([
            Turn("refunding", (ToolCall("payments", {"amount": "210.00 USD"}),)),
        ])

    result = allowing_the_connection(
        spec, lambda: ReferenceTransport(script_210()), "refund me", seen.tools(),
        needs_approval=GATED, asking=questions_for(document, "refund-desk"),
    )
    assert result.halted == "suspended"
    words = result.suspension.in_words
    assert "Please check this before it happens." in words, words
    assert "a refund over 200 USD is a management decision" in words, words
    assert "How much should we refund" not in words, words


# ───────────────────────── the policy stops the call, with nothing handed in
#
# Everything above hands the gate in — `needs_approval=GATED` and
# `asking=questions_for(...)` — which is exactly the move that hid the defect
# below for as long as it existed. `run()` seeded its gate from the host's
# argument alone, so `policies/approvals.yaml` — whose first line reads "This is
# enforcement, not a note in the instructions" — was, as shipped, a note in the
# instructions. Measured: a 300 USD `payments` call returned `final` and the
# tool ran.


def test_a_refund_over_the_written_limit_waits_for_a_person_with_nothing_passed_in(
    document: dict,
) -> None:
    spec = AgentSpec.from_document(document, "refund-desk")
    seen = Watching()

    def over() -> Script:
        return Script([
            Turn("refunding", (ToolCall("payments", {"amount": "300.00 USD"}),)),
            Turn("Refunded."),
        ])

    result = allowing_the_connection(
        spec, lambda: ReferenceTransport(over()), "refund me", seen.tools()
    )

    assert result.halted == "suspended", result.output
    assert result.suspension is not None
    assert result.suspension.reason == NEEDS_APPROVAL
    assert not any(n == "payments" for n, _ in seen.calls), (
        "the money moved before anyone was asked"
    )
    assert "a refund over 200 USD is a management decision" in result.suspension.in_words


def test_a_refund_under_the_written_limit_is_not_stopped_by_the_same_rule(
    document: dict,
) -> None:
    """`more-than: 200 USD` has to mean 200, in both directions.

    A gate that fired on every `payments` call would be the safe direction and
    the wrong reading — the author wrote a threshold, and stopping the 40 USD
    refunds it lets through is how a governance setting turns into a nuisance
    somebody switches off.
    """
    spec = AgentSpec.from_document(document, "refund-desk")
    seen = Watching()

    def under() -> Script:
        return Script([
            Turn("refunding", (ToolCall("payments", {"amount": "40.00 USD"}),)),
            Turn("Refunded."),
        ])

    result = allowing_the_connection(
        spec, lambda: ReferenceTransport(under()), "refund me", seen.tools()
    )

    assert result.halted == "final"
    assert [n for n, _ in seen.calls] == ["payments"]


def test_a_call_that_does_not_say_which_action_it_is_is_not_gated_on_a_guess(
    document: dict,
) -> None:
    """`zendesk/reply` names one ACTION, and this call says only `zendesk`.

    The rule itself is enforced now: a call carrying `action: reply` waits for a
    person and one carrying `action: read-ticket` does not — both asserted next
    door in `test_action_scoped_approvals.py`, along with the run-level report.
    What is left here is the call that says neither. Gating it would stop the
    read-only lookup the author wrote no rule about, so the run does not gate it
    — and does not go quiet either: the gate has a sentence ready naming the
    file, the line and a line that fixes it.

    It used to assert `fix: write \\`zendesk\\`` — advice `pact check` refuses as
    `loader/rule-names-no-action`, and which would have gated the lookup too.
    """
    spec = AgentSpec.from_document(document, "refund-desk", REPO / "examples/refund-desk")
    seen = Watching()
    looking = Script([
        Turn("looking", (ToolCall("zendesk", {"ticket": "T-1"}),)),
        Turn("Approved."),
    ])
    result = asyncio.run(run(spec, ReferenceTransport(looking), "refund me", seen.tools()))

    assert result.halted == "final", "a read-only lookup must not need approval"
    said = "\n".join(spec.asking.undecided_on("zendesk", {"ticket": "T-1"}))
    assert "zendesk/reply" in said, said
    assert "policies/approvals.yaml:" in said, "name the file and the line"
    assert "fix: write a rule for `zendesk/read-ticket`" in said, "and a line to type"


def test_an_eval_run_says_out_loud_that_it_turns_the_gate_off(document: dict) -> None:
    """A run that parks cannot be scored — so the eval runner suppresses the
    gate, and this is the assertion that it is a decision rather than an
    oversight. `asking_only()` keeps every question and removes every stop, so
    the wording an eval asserts on is unchanged and only the parking goes."""
    spec = AgentSpec.from_document(document, "refund-desk")
    seen = Watching()
    over = Script([
        Turn("refunding", (ToolCall("payments", {"amount": "300.00 USD"}),)),
        Turn("Refunded."),
    ])
    result = asyncio.run(
        run(spec, ReferenceTransport(over), "refund me", seen.tools(),
            asking=spec.asking.asking_only())
    )

    assert result.halted == "final"
    assert [n for n, _ in seen.calls] == ["payments"]
    # and the questions are still there to be asked about
    assert spec.asking.asking_only().for_call("payments", {"amount": "300 USD"}) is not None


def test_the_policys_own_gate_survives_a_park_and_lets_the_call_through_once(
    document: dict,
) -> None:
    """The gate the author wrote has to come back the same on the far side.

    A run parks in one process and resumes in another (D23), and the gate is now
    derived from the document rather than handed in — so the resumed leg has to
    re-derive the same decision, accept the answer, and run the call **once**.
    A gate that re-fired here would park forever; one that vanished would let the
    money out without the answer being read.
    """
    spec = AgentSpec.from_document(document, "refund-desk")
    seen = Watching()

    def script() -> Script:
        return Script([
            Turn("refunding", (ToolCall("payments", {"amount": "300.00 USD"}),)),
            Turn("Refunded."),
        ])

    parked = allowing_the_connection(
        spec, lambda: ReferenceTransport(script()), "refund me", seen.tools()
    )
    assert parked.halted == "suspended"
    assert not seen.calls

    said = Resumption(
        parked.suspension.correlation_key,
        {"payments": True, "payments.because": "signed off by the duty manager"},
    )
    done = asyncio.run(
        run(spec, ReferenceTransport(script()), "refund me", seen.tools(),
            resume=parked.suspension, answer=said)
    )

    assert done.halted == "final"
    assert done.output == "Refunded."
    assert [n for n, _ in seen.calls] == ["payments"], seen.calls


# ───────────────── every park that carries a question puts words in front of somebody
#
# The gap this closes, measured before it did: driving `replace(SPEC, max_steps=2,
# limits=Limits(when_it_runs_out=Action.ASK))` against `ReferenceTransport(
# never_finishes())` produced `halted='suspended'`, `reason='out-of-budget'` and
# `in_words=''`. The same on the worked example, with nothing passed: the park
# read `asked-of: [support-leads]`, `answer-within: 10m`,
# `if-nobody-answers: stop-and-say-so` and `keep-going (yes or no)` correctly out
# of `questions/keep-going.yaml` — and showed a person the answer contract and
# not one word. Three of the five places a run can park did that; only the tool
# gate rendered its question. So `shows: [spent-so-far, steps-taken]` and
# `shows: [how-much-over]` were lines an author wrote that reached nobody.
#
# The table below is keyed by the expression each `suspend(...)` in the harness
# names its reason with, so a SIXTH place to park arrives with no driver, and
# `test_every_place_the_harness_can_park...` fails instead of a park quietly
# shipping with nothing to show.


def _a_tool_call_the_policy_stops(document: dict):
    """`policies/approvals.yaml`, over 200 USD. The one that already worked."""
    spec = AgentSpec.from_document(document, "refund-desk")
    over = Script([
        Turn("refunding", (ToolCall("payments",
                                    {"amount": "300.00 USD", "order-number": "A-1182"}),)),
    ])
    return asyncio.run(
        run(spec, ReferenceTransport(over), "refund me", Watching().tools())
    )


def _a_ceiling_reached_before_an_answer(document: dict):
    """`limits.when-it-runs-out: ask-a-person`, on a model that never stops."""
    spec = replace(AgentSpec.from_document(document, "refund-desk"), max_steps=2)
    return asyncio.run(
        run(spec, ReferenceTransport(_never_finishes()), "refund me", Watching().tools())
    )


def _a_conversation_nobody_can_shrink(document: dict):
    """`context-policies/long-threads.yaml`, whose last line is `ask-a-person`."""
    spec = AgentSpec.from_document(document, "refund-desk", REPO / "examples/refund-desk")
    return asyncio.run(
        run(spec, _HoldsAlmostNothing(60), "my lamp arrived broken " * 200,
            {"zendesk": lambda a: "lamp " * 500},
            summarise=lambda text, model="": "in short: " + text[:40])
    )


def _a_teammate_that_could_not_answer(document: dict):
    """`teamwork.yaml`'s `if-someone-fails: ask-a-person`, with one down."""
    spec = AgentSpec.from_document(document, "refund-desk")

    async def ask(grant):
        if grant.member == "fraud-checker":
            raise RuntimeError("the ticket system is down")
        return "covered by the policy"

    both = Script([
        Turn("Consulting the team.",
             (ToolCall("policy-checker", {"question": "covered?"}),
              ToolCall("fraud-checker", {"question": "genuine?"}))),
        Turn("Approved."),
    ])
    return asyncio.run(
        run(spec, ReferenceTransport(both), "refund me",
            {"zendesk": lambda a: "lamp, broken"}, ask_member=ask)
    )


def _a_stage_that_stops_to_ask(document: dict):
    """`does: ask-someone` — the worked example has no such stage, so this one
    is a workspace written here. It is still the authored path: a document with
    a loop and a question in it, and nothing handed to `run()`."""
    doc = _asking_workspace(asks="is-this-within-policy")
    spec = AgentSpec.from_document(doc, "desk")
    return asyncio.run(
        run(spec, ReferenceTransport(Script([Turn("Approved.")])), "refund me",
            Watching().tools())
    )


#: One entry per `suspend(...)` in the harness, keyed by the source expression
#: that names its reason. `reason` is a variable at the tool gate, which is why
#: it reads as it does — the key is the text in the file, not a constant, so
#: nothing can be added to the harness without this table noticing.
DRIVEN = {
    "reason": _a_tool_call_the_policy_stops,
    "OUT_OF_BUDGET": _a_ceiling_reached_before_an_answer,
    "CONTEXT_TOO_LONG": _a_conversation_nobody_can_shrink,
    "NEEDS_APPROVAL": _a_teammate_that_could_not_answer,
    "ASKED_A_PERSON": _a_stage_that_stops_to_ask,
}


def test_every_place_the_harness_can_park_has_a_run_below_that_drives_it() -> None:
    """A sixth park fails this test rather than slipping through.

    Four of the five parks shipped with `in_words == ''` because nothing
    anywhere enumerated them — each one was written where it was needed and read
    by nobody afterwards. So the enumeration is here, taken off the harness
    itself: every `suspend(...)` call, by the expression it names its reason
    with. A new one arrives with no driver, and the message says which file to
    look in.
    """
    parks = _every_suspend_in_the_harness()
    assert parks == set(DRIVEN), (
        "the ways a run can park no longer match the runs that drive them. "
        f"in the harness and not driven: {sorted(parks - set(DRIVEN))}; "
        f"driven and no longer in the harness: {sorted(set(DRIVEN) - parks)}. "
        "fix: add a driver to DRIVEN in this file for the new park, so that what "
        "a person reads there is asserted like every other park's."
    )


@pytest.mark.parametrize("park", sorted(DRIVEN))
def test_every_park_that_carries_a_question_puts_the_words_in_front_of_the_person(
    park: str, document: dict,
) -> None:
    """The whole of the gap, as one assertion repeated per park.

    A run stopped with an answer contract and no words is, from the outside,
    indistinguishable from a run that has hung — and it is worse than that here,
    because somebody is being asked to decide with nothing in front of them.
    """
    result = DRIVEN[park](document)
    assert result.halted == "suspended", result.output
    parked = result.suspension
    assert parked is not None
    assert parked.asks, "a park that asks for nothing is a hang"
    assert parked.in_words.strip(), (
        f"the {parked.reason} park shows a person {[e.name for e in parked.asks]} "
        "and no words at all"
    )


def test_the_figures_the_budget_question_asks_to_be_shown_reach_the_person(
    document: dict,
) -> None:
    """`shows: [spent-so-far, steps-taken]`, from the shipped file, arriving.

    Nothing is handed to `run()` here. The question, its audience, its deadline,
    its answer shape AND now its values all come off disk — which is the whole
    of D14 for this mechanism: a support lead writes a line in
    `questions/keep-going.yaml` and a person reads it.
    """
    words = _a_ceiling_reached_before_an_answer(document).suspension.in_words
    assert "This is taking longer than it should. Keep going?" in words, words
    assert 'steps-taken: "2"' in words, words
    assert "spent-so-far: " in words, words
    # And only what the question asked for. `spent()` offers six figures; the
    # author named two, so four of them are not on the screen.
    assert "tool-calls-made" not in words, words
    assert "which-limit" not in words, words


def test_a_run_that_could_not_count_what_it_spent_says_so_rather_than_showing_a_zero(
    document: dict,
) -> None:
    """A transport with no `usage()` leaves `money` at 0.0 on the meter, and
    `spent-so-far: "0.00 USD"` reads to an approver as "this has cost nothing".
    That is the silent mis-statement T7 forbids, arriving in the one place where
    somebody is about to act on it — so the run says it could not count."""
    could_not = _a_ceiling_reached_before_an_answer(document).suspension.in_words
    assert 'spent-so-far: "nothing here could count it"' in could_not, could_not

    class Costing(ReferenceTransport):
        """Says what a call cost, as the seven real transports do."""

        def usage(self) -> tuple[int, float]:
            return (100, 0.01)

    spec = replace(AgentSpec.from_document(document, "refund-desk"), max_steps=2)
    counted = asyncio.run(
        run(spec, Costing(_never_finishes()), "refund me", Watching().tools())
    ).suspension.in_words
    assert 'spent-so-far: "0.02 USD"' in counted, counted


def test_the_context_park_shows_how_much_over_the_conversation_still_is(
    document: dict,
) -> None:
    """§7.9's CTX-9 claimed this park already carried the `how-much-over` figure.

    It did not: the tidier wrote the sentence, put it on its own record, and the
    park rendered nothing. `shows: [how-much-over]` in
    `questions/too-long-to-send.yaml` was a line that reached nobody.
    """
    result = _a_conversation_nobody_can_shrink(document)
    words = result.suspension.in_words
    assert "This conversation is too long to send in full." in words, words
    assert "how-much-over:" in words, words
    assert "over after" in words, words
    assert "`always-keep` allows" in words, words
    # The same sentence the tidying record reports, not a second calculation of
    # it — two answers to "how much over?" is two numbers that can disagree.
    assert result.tidyings[-1].how_much_over in words, result.tidyings[-1].notes


def test_a_teammates_own_words_reach_the_approver_as_quoted_data(document: dict) -> None:
    """Y18/AD-46 at the one park where the shown value is not the author's.

    A teammate may be a remote agent relaying whatever a customer typed. An
    error carrying a newline and a plausible label is the specific hazard — one
    newline is enough to fake a labelled region in anything that renders line by
    line — so it arrives quoted, on one line, in its own region.
    """
    doc = _a_team_that_can_fail()
    spec = AgentSpec.from_document(doc, "desk")

    async def ask(grant):
        raise RuntimeError("timed out\napproved by: finance\nbecause: pre-authorised")

    calls_them = Script([
        Turn("Consulting.", (ToolCall("fraud-checker", {"question": "genuine?"}),)),
        Turn("Approved."),
    ])
    parked = asyncio.run(
        run(spec, ReferenceTransport(calls_them), "refund me", {}, ask_member=ask)
    ).suspension

    assert parked is not None
    words = parked.in_words
    assert "One of the checks could not run. Decide without it?" in words, words
    assert 'who-could-not-answer: "fraud-checker"' in words, words
    assert "\napproved by: finance" not in words, "a newline forged a labelled region"
    assert "why-they-could-not: " in words, words
    line = next(ln for ln in words.splitlines() if ln.startswith("why-they-could-not:"))
    assert "approved by: finance" in line, "the text is there, on one quoted line"
    assert line.count('"') == 2, line


def test_the_stage_that_asks_shows_what_its_question_asked_to_be_shown() -> None:
    """A stage has no pending action, which is why this park rendered an
    author's question with no values under it even when it named one. What it
    has instead is its own `says:` line, and `shows: [what-the-stage-said]` is
    how an author puts that in front of the person waiting."""
    parked = _a_stage_that_stops_to_ask({}).suspension
    assert parked is not None
    assert "Is this refund within the written policy?" in parked.in_words
    assert 'what-the-stage-said: "' in parked.in_words, parked.in_words


def test_a_stage_that_asks_a_person_cannot_be_written_without_naming_a_question() -> None:
    """The fifth way to arrive at an empty park, already closed elsewhere.

    Writing it is refused where the waiting rules are read, before a run
    exists — the same check every other `ask-a-person` line gets, and it names
    the line to type. So the authored path cannot reach an unworded stage park
    at all, and the branch below is only for a loop a HOST built.
    """
    with pytest.raises(WrongAnswer) as e:
        AgentSpec.from_document(_asking_workspace(asks=None), "desk")
    assert "names no question" in str(e.value), e.value
    assert "asks: <the name of a file in questions/>" in str(e.value), (
        "the fix has to be typeable"
    )


def test_a_loop_handed_in_by_a_host_still_shows_the_words_that_stage_carries() -> None:
    """And when it is a host's loop rather than an author's, the stage's own
    `says:` line is what the person reads.

    Put through the same `Question` as every other park, so the answer contract
    is printed under it rather than left to be guessed at — not through a second
    rendering that would be one more place for a value to be concatenated into
    somebody's wording.
    """
    handed_in = Loop.resolve(_asking_workspace(asks=None), "checked")
    parked = asyncio.run(
        run(SPEC, ReferenceTransport(Script([Turn("Approved.")])), "refund me",
            Watching().tools(), loop=handed_in)
    ).suspension

    assert parked is not None
    assert parked.reason == ASKED_A_PERSON
    assert "Is this refund within the written policy?" in parked.in_words
    assert "answer with:" in parked.in_words, parked.in_words


def test_what_the_person_reads_at_a_ceiling_survives_the_process_that_asked_it(
    document: dict,
) -> None:
    """D23, for the four parks that had nothing to carry until now.

    The words go across the boundary with the run rather than being rebuilt on
    the far side. Rebuilt, a person could be shown a figure that has moved since
    they were asked — and at a budget park the figure IS the question.
    """
    parked = _a_ceiling_reached_before_an_answer(document).suspension
    revived = Suspension.from_json(parked.to_json())
    assert revived.in_words == parked.in_words
    assert 'steps-taken: "2"' in revived.in_words


# ───────────────────────────────────────────────────────────── helpers for those


def _never_finishes() -> Script:
    """A model that keeps calling a tool and never answers — the shape a ceiling
    exists for."""
    return Script([Turn("still working", (ToolCall("zendesk", {}),))])


class _HoldsAlmostNothing:
    """A transport that says how little it holds, so the shipped context policy
    is measurable and its ladder can be made to bottom out."""

    name = "holds-almost-nothing"

    def __init__(self, window: int) -> None:
        self.context_window = lambda: window

    def lattice(self) -> dict:
        return {}

    async def model_call(self, system, history, tools):
        if not any(m.get("role") == "tool" for m in history):
            return "Looking up the ticket.", [ToolCall("zendesk", {})]
        return "DECISION: approved.", []


def _asking_workspace(asks: "str | None") -> dict:
    """One agent whose loop stops to ask, with and without a written question."""
    stage = {"does": "ask-someone", "says": "Is this refund within the written policy?",
             "then": {"answered": "work"}}
    if asks is not None:
        stage["asks"] = asks
    doc: dict = {
        "agents": {"desk": {"name": "Desk", "description": "d",
                            "instructions": "Decide.", "loop": "checked"}},
        "loops": {
            "checked": {
                "starts-at": "ask",
                "steps": {
                    "ask": stage,
                    "work": {"does": "use-tools",
                             "then": {"used-a-tool": "work", "answered": "done"}},
                },
            }
        },
    }
    if asks is not None:
        doc["questions"] = {
            asks: {
                "description": "Whether a refund is inside the written policy.",
                "says": "Is this refund within the written policy?",
                "answer": {"approved": "yes or no", "because": "text"},
                "shows": ["what-the-stage-said"],
                "asked-of": ["support-leads"],
                "answer-within": "10m",
                "if-nobody-answers": "stop-and-say-so",
            }
        }
    return doc


def _a_team_that_can_fail() -> dict:
    """One agent, one specialist, and the question asked when it cannot answer.

    Written here rather than added to the worked example because
    `questions/is-this-ok.yaml` is shared with the refund gate and shows an
    amount and an order number — a failed teammate has neither. What it has is
    on offer under the three names below, and this is a document that names two
    of them.
    """
    return {
        "agents": {
            "desk": {
                "name": "Desk", "description": "d",
                "instructions": "Ask the specialist, then decide.",
                "team": {"fraud-checker": "Looks for signs it is not genuine."},
                "teamwork": {"if-someone-fails": "ask-a-person",
                             "asks": "carry-on-without-them"},
            }
        },
        "questions": {
            "carry-on-without-them": {
                "description": "Whether to decide without a check that could not run.",
                "says": "One of the checks could not run. Decide without it?",
                "answer": {"approved": "yes or no", "because": "text"},
                "shows": ["who-could-not-answer", "why-they-could-not"],
                "asked-of": ["support-leads"],
                "answer-within": "30m",
                "if-nobody-answers": "stop-and-say-so",
            }
        },
    }


def _every_suspend_in_the_harness() -> set[str]:
    """The first argument of every `suspend(...)` in the harness, as written.

    Read off the source rather than kept in a list here, because a list here is
    a second thing to remember and the whole defect above was five places nobody
    was counting.
    """
    tree = ast.parse((REPO / "adapters/python/src/pact_adapters/harness.py").read_text())
    return {
        ast.unparse(node.args[0])
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", "") == "suspend"
        and node.args
    }
