"""One line gates one action, and the run stops for a person exactly as it would
if the author had written three files.

Gating one action used to cost a question in `questions/`, a policy in
`policies/`, and a rule inside it naming `<tool>/<action>` — thirteen lines and
four concepts. Eve charges one file and two lines. `needs-a-person: yes` is the
short spelling, and the only interesting question about it is whether the gate it
buys is the same gate.

Every test here drives `harness.run` on **`tests/trees/one-line-gate/`, loaded
through the real Rust loader**, and passes no gate, no rules and no approvals.
Nothing below constructs a `Question`, a `Rule` or a `Gate`: an object built here
would prove the object works and say nothing about whether the author's line
reaches it, which is the defect this project keeps shipping. The negative control
is `test_deleting_the_one_line_lets_the_refund_through_with_nobody_asked` — the
same tree, one line removed, and the money moves.

The tree has **no `questions/` folder and no `policies/` folder**, so a gate that
appears here cannot have come from anywhere but that line.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.questions import (  # noqa: E402
    LIBRARY,
    SHIPPED_QUESTION,
    Question,
    gated_actions,
    questions_for,
)
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.suspension import (  # noqa: E402
    NEEDS_APPROVAL,
    PauseRule,
    Resumption,
    Suspension,
    rule_for,
)
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
TREE = REPO / "tests" / "trees" / "one-line-gate"
PACT_BIN = REPO / "target" / "debug" / "pact"

#: The refund the tree's own tool file is written around.
REFUND = {"action": "issue-refund", "order-number": "A-1182", "amount": "300.00 USD"}
LOOKUP = {"action": "look-up-order", "order-number": "A-1182"}


def _load(root: Path) -> dict[str, Any]:
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(PACT_BIN), "show", str(root)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    """The one-line-gate tree through the real Rust loader (invariant P-1)."""
    return _load(TREE)


def _script(*calls: dict[str, Any]) -> Script:
    return Script([
        Turn("Refunding.", tuple(ToolCall("payments", dict(c)) for c in calls)),
        Turn("Done."),
    ])


class Ledger:
    """Every real payments invocation. Whether money moved is the whole point."""

    def __init__(self) -> None:
        self.paid: list[dict[str, Any]] = []

    def tools(self) -> dict:
        def payments(args):
            self.paid.append(dict(args))
            return f"paid {args.get('amount')}"

        return {"payments": payments}


def _run(document: dict, ledger: Ledger, *calls: dict[str, Any], **kw):
    """The authored path: nothing passed but the author's own document."""
    spec = AgentSpec.from_document(document, "desk")
    return asyncio.run(
        run(spec, ReferenceTransport(_script(*calls)), "refund A-1182",
            ledger.tools(), now=0.0, **kw)
    )


# ─────────────────────────── the author's line, stopping a call


def test_a_refund_the_author_gated_in_one_line_stops_and_waits_for_a_person(
    document: dict,
) -> None:
    """The whole item. One line in `tools/payments.yaml` and no other governance
    file anywhere, and the refund does not happen until somebody says so."""
    assert "questions" not in document, "the short form writes no question file"
    assert "policies" not in document, "and no policy file"

    ledger = Ledger()
    out = _run(document, ledger, REFUND)

    assert out.halted == "suspended", f"the refund ran unasked: {out.halted}"
    assert out.suspension is not None
    assert out.suspension.reason == NEEDS_APPROVAL
    assert ledger.paid == [], f"money moved before anybody was asked: {ledger.paid}"


def test_the_read_only_action_beside_it_is_not_gated_by_its_neighbours_line(
    document: dict,
) -> None:
    """`needs-a-person:` is a line on one ACTION.

    A shorthand that gated the whole tool would stop the read-only lookup nobody
    wrote a line about — which is the spelling `pact check` refuses outright in
    the long form, as `loader/rule-names-no-action`.
    """
    ledger = Ledger()
    out = _run(document, ledger, LOOKUP)
    assert out.halted == "final", f"a lookup nobody gated waited anyway: {out.halted}"
    assert len(ledger.paid) == 1 and ledger.paid[0]["action"] == "look-up-order"


def test_deleting_the_one_line_lets_the_refund_through_with_nobody_asked(
    tmp_path: Path,
) -> None:
    """The negative control, and the only thing that proves the AUTHOR's line is
    what stops the call.

    The same tree with one line removed, loaded the same way, run the same way.
    If this ever goes green alongside the test above, the gate is coming from
    somewhere in the adapter rather than from the file.
    """
    copy = tmp_path / "no-line"
    shutil.copytree(TREE, copy)
    tool = copy / "tools" / "payments.yaml"
    text = tool.read_text()
    assert "needs-a-person: yes" in text, "the line this test deletes must exist"
    tool.write_text(text.replace("    needs-a-person: yes\n", ""))

    ledger = Ledger()
    out = _run(_load(copy), ledger, REFUND)
    assert out.halted == "final", out.halted
    assert len(ledger.paid) == 1, "with the line gone the refund is simply made"


# ─────────────────────────── what the person actually reads


def test_the_person_is_shown_which_tool_is_about_to_do_what_and_with_which_values(
    document: dict,
) -> None:
    """A screen a person can act on, not a placeholder.

    The shipped question's wording is fixed and cannot name an action, so the
    desugaring supplies both halves the author would otherwise have typed: a
    `because:` built from the action's own `description:`, and a `shows:` read
    off its `takes:`. Without them the approver reads one sentence about "this"
    and has no idea what "this" is.
    """
    out = _run(document, Ledger(), REFUND)
    said = out.suspension.in_words

    assert "issue-refund" in said and "payments" in said, said
    assert "Send money back to the customer" in said, (
        f"the action's own description never reaches the person: {said}"
    )
    assert "300.00 USD" in said and "A-1182" in said, f"no values on the screen: {said}"
    assert SHIPPED_QUESTION not in said, f"the person read the name of a file: {said}"

    # And the values are DATA, in their own labelled region — never folded into
    # the wording (Y18/AD-46). A customer-supplied order number must not be able
    # to read as an instruction to the approver.
    assert '"300.00 USD"' in said, f"a shown value must be quoted: {said}"


def test_the_screen_tells_the_person_how_long_they_have_and_who_is_being_asked(
    document: dict,
) -> None:
    """The three lines that make a wait a wait rather than a hang.

    Read off the park, which reads them off the shipped question — so a gate
    written in one line cannot end up addressed to nobody with no deadline while
    everything you can assert about the gate itself is right.
    """
    out = _run(document, Ledger(), REFUND)
    said = out.suspension.in_words
    assert "whoever-is-running-this" in said, said
    assert "30m" in said, said

    rule = rule_for(PauseRule.from_document(document, "desk"), NEEDS_APPROVAL)
    assert rule is not None, "a short gate parked with no waiting rule at all"
    assert rule.waits_for == 1800.0, rule.waits_for
    assert rule.who_can_answer == ("whoever-is-running-this",)
    assert rule.if_nobody_answers == "stop-and-say-so"


# ─────────────────────────── yes, no, and nobody


def test_a_person_saying_yes_lets_the_refund_through_and_only_then(
    document: dict,
) -> None:
    """The wait ends the way any other wait ends: with an answer, carried across
    a real process boundary."""
    ledger = Ledger()
    first = _run(document, ledger, REFUND)
    parked = Suspension.from_json(first.suspension.to_json())

    after = _run(
        document, ledger, REFUND,
        resume=parked,
        answer=parked.answer(payments="yes", **{"payments.because": "the customer is owed it"}),
    )
    assert after.halted == "final", after.halted
    assert len(ledger.paid) == 1, f"the refund happened {len(ledger.paid)} times: {ledger.paid}"
    assert ledger.paid[0]["amount"] == "300.00 USD"


def test_a_person_saying_no_ends_the_run_rather_than_asking_the_same_thing_again(
    document: dict,
) -> None:
    """A refusal is an answer. The short form gets the same three outcomes the
    long form does — yes, no, and nobody — or it is Eve's approve-only widget
    under a new name."""
    ledger = Ledger()
    first = _run(document, ledger, REFUND)
    parked = Suspension.from_json(first.suspension.to_json())

    after = _run(
        document, ledger, REFUND,
        resume=parked,
        answer=parked.answer(payments="no", **{"payments.because": "outside the window"}),
    )
    assert after.halted == "final", f"a refusal that re-parks looks like silence: {after.halted}"
    assert ledger.paid == [], "money moved after a person said no"
    refused = [r for step in after.trace() for r in step["results"] if r.startswith("refused:")]
    assert refused, f"the run's own record does not say a person refused: {after.trace()}"


def test_silence_can_never_become_a_yes_on_the_short_path(document: dict) -> None:
    """`if-nobody-answers:` on the shipped question is `stop-and-say-so`, and
    there is no spelling of approval anywhere on this path.

    Checked against the shipped question rather than against a run, because what
    matters is that no wording exists that would let a deadline approve — a run
    only shows the one that was chosen.
    """
    shipped = Question.from_document({}, SHIPPED_QUESTION)
    assert shipped.if_nobody_answers == "stop-and-say-so"
    unanswered = shipped.when_nobody_answers()
    assert unanswered.then == "stop-and-say-so"
    assert unanswered.answer is None, "a deadline produced an answer"
    assert unanswered.stop_because and "nobody answered" in unanswered.stop_because


# ─────────────────────────── it is a shorthand, not a second mechanism


def test_the_expert_path_wins_wherever_both_are_written() -> None:
    """A written rule says who is asked, how long they have and what shape the
    answer takes. None of that may be overruled by somebody else's one-liner, and
    a second wait appearing beside it would put two screens in front of one
    person for one call.

    Measured on the worked example, whose `payments/issue-refund` is gated the
    long way by two rules and two questions.
    """
    example = _load(REPO / "examples" / "refund-desk")
    before = questions_for(example, "refund-desk")

    both = json.loads(json.dumps(example))
    both["tools"]["payments"]["actions"]["issue-refund"]["needs-a-person"] = "yes"
    after = questions_for(both, "refund-desk")

    assert gated_actions(both, "refund-desk") == [], (
        "the short line produced a second gate beside a written rule"
    )
    assert len(after.rules["payments"]) == len(before.rules["payments"]), (
        "one call would now put two screens in front of one person"
    )


def test_the_shipped_question_here_and_the_one_in_spec_questions_have_not_drifted() -> None:
    """`questions.LIBRARY` says it mirrors `spec/questions/*.yaml`.

    Two copies exist because an adapter reads the loaded document and never the
    author's tree (invariant P-1). If this fails they have drifted, and the file
    is the source: `spec/questions/is-this-ok.yaml` is what an author can open
    and what `pact waits` reports from, so the copy here is what changes.

    Read through `Question.from_document` — the same door an author's own
    question goes through — so a difference in what is ASKED is caught and not
    only a difference in the text.
    """
    import yaml  # a dependency of the adapter's own test tooling

    published = sorted((REPO / "spec" / "questions").glob("*.yaml"))
    assert published, "spec/questions/ has nothing in it"
    assert {f"pact:question/{p.stem}" for p in published} == set(LIBRARY), (
        f"spec/questions/ ships {[p.stem for p in published]}; LIBRARY has {sorted(LIBRARY)}"
    )

    for path in published:
        name = f"pact:question/{path.stem}"
        on_disk = Question.from_document(
            {"questions": {name: yaml.safe_load(path.read_text())}}, name
        )
        in_here = Question.from_document({}, name)
        assert on_disk.asks == in_here.asks, (
            f"spec/questions/{path.name} says {on_disk.asks!r}; LIBRARY says {in_here.asks!r}"
        )
        assert on_disk.answer == in_here.answer, (
            f"spec/questions/{path.name} asks for {sorted(on_disk.answer)}; "
            f"LIBRARY asks for {sorted(in_here.answer)}"
        )
        assert on_disk.asked_of == in_here.asked_of
        assert on_disk.answer_within == in_here.answer_within
        assert on_disk.if_nobody_answers == in_here.if_nobody_answers


def test_a_call_that_does_not_say_which_action_it_is_is_reported_rather_than_guessed_at(
    document: dict,
) -> None:
    """The short form inherits the long form's honesty about what it cannot
    decide.

    `payments` has two actions and only one of them needs a person, so a call
    carrying no `action:` might be either. Stopping it would stop the read-only
    lookup nobody gated; letting it through would skip the gate. Neither is what
    the author wrote, so the run says so — the same sentence a rule naming one
    action produces, with the shorter fix.
    """
    out = _run(document, Ledger(), {"order-number": "A-1182", "amount": "300.00 USD"})
    said = " ".join(out.unenforced)
    assert "needs-a-person: yes" in said, f"nothing was said about it: {out.unenforced}"
    assert "tools/payments.yaml" in said, f"the sentence names no file: {said}"
    assert "fix:" in said and "look-up-order" in said, f"the fix has to be typeable: {said}"
