"""The deadline and the audience on the screen belong to the WAIT, not to the
question printed on it.

`shown._under_the_contract` makes three substitutions into the author's
question before it is rendered — the answer names, the deadline, the audience —
and only the first had a test. Both of the other two could be deleted
(`if asked_of is not None:` and `if waits_for or asked_of is not None:` each
replaced by `if False:`) and the whole suite still passed, so the guarantee its
own docstring states was held by nothing.

It is worth holding, because the two really do come apart in the shipped
example. `suspension._named_questions` takes the FIRST `ask-a-person` rule's
question as the one whose deadline governs a `needs-approval` wait — that is
`is-this-ok`, at 30m — while `Gate.for_call` shows the NARROWEST rule that
fired, which above 500 USD is `how-much-to-refund`, at 4h. Printing `answer
within: 4h` above a wait that expires in thirty minutes tells a support lead
something the run will not honour, and nothing was stopping it.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from consenting import allowing_the_connection  # noqa: E402
from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.questions import Question, Shape  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.shown import words_for  # noqa: E402
from pact_adapters.suspension import NEEDS_APPROVAL  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"

#: What the two tools answer. The claim under test is what is printed above a
#: park, not what a tool says back, so both are answered locally and offline.
TOOLS = {
    "zendesk": lambda a: "lamp, 6 days ago, broken",
    "payments": lambda a: "refunded",
}


def a_question_asked_of_leads_within_four_hours() -> Question:
    """`questions/how-much-to-refund.yaml`, as the loader hands it over."""
    return Question(
        name="how-much-to-refund",
        asks="How much should we refund on this order?",
        answer={"amount": Shape.parse("money"), "because": Shape.parse("text")},
        asked_of=("support-leads",),
        answer_within="4h",
    )


def _loaded(tree: Path) -> dict:
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(PACT_BIN), "show", str(tree)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


@pytest.fixture(scope="session")
def document() -> dict:
    return _loaded(EXAMPLE)


def a_refund_a_person_has_to_set() -> Script:
    """Over 500 USD, which is the author's second rule and a different question."""
    return Script([
        Turn(
            "Issuing the refund.",
            (
                ToolCall(
                    "payments",
                    {
                        "action": "issue-refund",
                        "order-number": "A-1182",
                        "amount": "600.00 USD",
                    },
                ),
            ),
        ),
        Turn("Done."),
    ])


def _parked_over_five_hundred(doc: dict) -> "object":
    """The worked example, run until a person has to set a 600 USD figure."""
    spec = AgentSpec.from_document(doc, "refund-desk")
    result = allowing_the_connection(
        spec,
        lambda: ReferenceTransport(a_refund_a_person_has_to_set()),
        "refund A-1182",
        TOOLS,
        now=0.0,
    )
    assert result.suspension is not None, result.halted
    assert result.suspension.reason == NEEDS_APPROVAL, result.suspension.reason
    return result.suspension


# ────────────────────────────────────────────── the substitution, on its own


def test_the_deadline_a_person_reads_is_the_one_the_wait_will_actually_honour() -> None:
    """A question written for a four-hour wait, shown at a thirty-minute one.

    The wording, the `because:` and the values shown stay the author's. The
    deadline does not: it is a promise about when this run will stop waiting,
    and only the wait knows that.
    """
    words = words_for(
        a_question_asked_of_leads_within_four_hours(),
        "payments",
        {},
        waits_for="30m",
        asked_of=["support-manager"],
    )

    assert "answer within: 30m" in words, words
    assert "4h" not in words, "the question's own deadline is not this wait's:\n" + words


def test_the_people_a_park_says_it_asked_are_the_people_the_wait_asked() -> None:
    """The other half of the same substitution, and the more expensive one: a
    screen naming a team who cannot clear this wait sends the decision to
    somebody whose answer the run will refuse."""
    words = words_for(
        a_question_asked_of_leads_within_four_hours(),
        "payments",
        {},
        waits_for="30m",
        asked_of=["support-manager"],
    )

    assert "asked of: support-manager" in words, words
    assert "support-leads" not in words, (
        "the question's own audience was printed over the wait's:\n" + words
    )


def test_a_wait_with_no_deadline_and_no_audience_prints_neither() -> None:
    """`waiting-for-another-agent` configures nothing (§7.14 WAIT-2), so the
    harness passes `waits_for=""` and `asked_of=()`. Both have to CLEAR the
    question's own lines rather than fall through to them — an empty wait is not
    an invitation to borrow another question's audience."""
    words = words_for(
        a_question_asked_of_leads_within_four_hours(), "fraud-checker", {},
        waits_for="", asked_of=(),
    )

    assert "answer within:" not in words, words
    assert "asked of:" not in words, words
    assert "How much should we refund on this order?" in words, (
        "the author's wording is theirs and stays:\n" + words
    )


# ──────────────────────────────────── the same guarantee, from the author's files


def test_the_worked_examples_own_two_rules_put_one_questions_words_under_the_others_clock(
    document: dict,
) -> None:
    """Nothing is constructed here. Two lines the author wrote, read together.

    `policies/approvals.yaml` names `is-this-ok` first and `how-much-to-refund`
    second. The first is what `suspension._named_questions` takes the deadline
    from; the second is what `Gate.for_call` shows once the amount is over 500
    USD. So this park prints `how-much-to-refund`'s question under
    `is-this-ok`'s thirty minutes, and a screen that printed the shown
    question's own `answer-within: 4h` would be promising a support lead three
    and a half hours the run has already decided not to give them.
    """
    words = _parked_over_five_hundred(document).in_words

    assert "How much should we refund on this order?" in words, words
    assert "answer within: 30m" in words, words
    assert "answer within: 4h" not in words, words


def test_changing_who_is_asked_in_the_governing_question_changes_who_the_park_names(
    tmp_path,
) -> None:
    """The authored path for the audience half, proved by editing one line.

    Two runs of the same tree differing only in `questions/is-this-ok.yaml`'s
    `asked-of:`. The question SHOWN — `how-much-to-refund` — still says
    `support-leads` in both, so if the screen were rendering the shown
    question's own audience nothing here would move. It moves, which is what
    makes the line the author typed the one a person reads.
    """
    tree = tmp_path / "refund-desk"
    shutil.copytree(EXAMPLE, tree)
    governing = tree / "questions" / "is-this-ok.yaml"
    edited = governing.read_text().replace(
        "asked-of: [support-leads]", "asked-of: [night-shift]"
    )
    assert edited != governing.read_text(), "the line to edit is not where it was"
    governing.write_text(edited)
    shown = (tree / "questions" / "how-much-to-refund.yaml").read_text()
    assert "asked-of: [support-leads]" in shown, "the shown question still says leads"

    words = _parked_over_five_hundred(_loaded(tree)).in_words

    assert "asked of: night-shift" in words, words
    assert "support-leads" not in words, words
