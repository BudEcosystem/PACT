"""The shared cases, held to PACT's own runtime (`tests/conformance/`).

`reactions.json` and `workflows.json` are the portable half of what the suites
beside this file say in Python: a scripted run, written down, and everything
another runtime can observe of it. A runtime that is not this one replays the
same cases and compares its own answer with `expect` — which is how "it
conforms" becomes something that can be wrong, and how a behaviour that changes
with no change to the schema (what a deciding agent is given; when a tool stops
being offered) reaches a runtime that pins PACT without anybody reading a diff.

    PACT_BLESS=1 pytest tests/test_the_shared_cases_are_what_this_runtime_does.py

writes `expect` afresh from this runtime; read the diff before committing it,
because that diff is the list of things every other runtime now has to match.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from conformance_kit import CASES, REPO, replay  # noqa: E402

FILES = ("reactions.json", "workflows.json", "limits.json")


def _cases() -> list[tuple[str, dict[str, Any]]]:
    return [
        (f"{name.removesuffix('.json')}:{case['name']}", case)
        for name in FILES
        for case in json.loads((CASES / name).read_text())["cases"]
    ]


if os.environ.get("PACT_BLESS"):
    for _name in FILES:
        _path = CASES / _name
        _held = json.loads(_path.read_text())
        for _case in _held["cases"]:
            _case["expect"] = replay({k: v for k, v in _case.items() if k != "expect"})
        _path.write_text(json.dumps(_held, indent=1, ensure_ascii=False) + "\n")


@pytest.mark.parametrize("name, case", _cases(), ids=[n for n, _ in _cases()])
def test_a_case_is_what_this_runtime_does(name: str, case: dict[str, Any]) -> None:
    assert "expect" in case, f"{name} has no `expect:` — run with PACT_BLESS=1 and read what it writes"
    assert replay({k: v for k, v in case.items() if k != "expect"}) == case["expect"]


def test_every_case_names_a_tree_this_repository_has_and_has_a_name_of_its_own() -> None:
    names = [n for n, _ in _cases()]
    assert len(names) == len(set(names))
    for name, case in _cases():
        assert (REPO / case["tree"]).exists(), name
        assert ("agent" in case) != ("workflow" in case), f"{name}: one of `agent:` and `workflow:`"


def test_the_two_ways_of_writing_one_workspace_are_one_run() -> None:
    """`finance-first` as a folder and as one `.pact` file: the same case, and
    apart from the tree it names, the same `expect` to the letter."""
    by_name = {case["name"]: case for _, case in _cases()}
    folder = by_name["asked-first-then-a-person-then-once-then-told-after"]
    one_file = by_name["the-same-workspace-written-as-one-pact-file"]
    assert folder["expect"] == one_file["expect"]


def test_the_cases_say_the_things_they_are_there_to_say() -> None:
    """Read off `expect`, so a blessing that quietly changed what a case shows
    fails here in words."""
    by_name = {case["name"]: case["expect"] for _, case in _cases()}

    refund = by_name["asked-first-then-a-person-then-once-then-told-after"]
    assert refund["steps"][0]["results"][0].startswith("not done yet — finance-desk was asked first")
    assert refund["parks"] == [
        {"steps-finished": 1, "reason": "needs-approval", "asks": refund["parks"][0]["asks"], "executed-so-far": 0}
    ], "a person is asked in the step AFTER the held one — one step finished — with nothing run yet"
    assert [e[0] for e in refund["executed"]] == ["billing"], "once"
    assert [w["agent"] for w in refund["woken"]] == ["finance-desk", "auditor"]
    assert refund["unenforced"] == []

    refused = by_name["a-person-says-no-and-no-money-moves"]
    assert refused["executed"] == [] and [w["agent"] for w in refused["woken"]] == ["finance-desk"]

    said_first = by_name["saying-the-topic-first-does-not-spend-the-guard-on-the-call"]
    assert [r["certainty"] for r in said_first["reactions"]][:2] == ["guess", "exact"]
    assert said_first["steps"][1]["results"][0].startswith("not done yet")

    withdrawn = by_name["a-wrong-topic-then-the-right-one-and-then-the-tool-is-withdrawn"]
    assert "working-on" in withdrawn["offered"][0] and "working-on" in withdrawn["offered"][1]
    assert all("working-on" not in o for o in withdrawn["offered"][2:])

    stopped = by_name["a-stop-on-an-exact-signal-ends-the-run-before-the-call"]
    assert stopped["executed"] == [] and stopped["output"] == "A payment over 500 USD is not this desk's to make."

    each = by_name["each-different-call-is-held-once-and-the-same-call-goes-through"]
    assert [e[1]["to"] for e in each["executed"]] == ["ann", "bob"]
    assert [w["agent"] for w in each["woken"]] == ["reviewer", "reviewer"]

    alone = by_name["with-nobody-to-run-another-agent-the-call-goes-through-and-the-run-says-so"]
    assert len(alone["executed"]) == 1 and alone["woken"] == [] and len(alone["unenforced"]) == 1

    sorted_ = by_name["no-rule-holds-so-the-agent-decides-and-is-given-what-it-accepts"]
    assert sorted_["given"][0] == {"agent": "sorter", "given": {"message": "The app crashes."}}

    asked = by_name["the-agent-is-not-sure-so-a-person-decides-and-is-shown-the-message"]
    assert asked["shown"] == [{"question": "which-desk", "shown": {"input.message": "The app crashes."}}]

    found = by_name["a-deciding-agent-is-given-what-an-earlier-stage-found-and-the-bound-name-wins"]
    # `kind` is triage's `engine`, not the `cabin` the report came in with; the
    # `secret` the assigner does not accept is not given to it.
    assert found["given"][1] == {
        "agent": "assigner",
        "given": {"kind": "engine", "summary": "Oil leak at the cowling.", "urgency": "high"},
    }

    nothing = by_name["a-binding-that-reads-nothing-gives-nothing-under-that-name"]
    assert "kind" not in nothing["given"][1]["given"] and nothing["unenforced"] == []

    bound = by_name["a-one-value-item-goes-where-the-stage-binds-it"]
    assert [g["given"] for g in bound["given"]] == [
        {"note": "Invoice 14 is overdue."},
        {"note": "Lunch on Friday?"},
    ]
    assert bound["unenforced"] == []

    scored = by_name[
        "a-classifier-is-given-the-note-as-it-is-and-the-reader-is-given-the-instruction-first"
    ]
    # 60% sure where the rung asks for 85%: it passes on to the next RUNG. The
    # classifier was given the note alone; the reader, the instruction first.
    assert [g["agent"] for g in scored["given"]] == ["scorer", "reader"]
    assert scored["given"][0]["given"] == {"message": "Invoice 14 is overdue."}
    assert scored["given"][1]["given"]["message"].startswith("Pick the shelf for this note.\n\n")
    exactly = by_name["a-classifier-exactly-as-sure-as-the-line-asks-decides-and-nobody-else-is-asked"]
    assert [g["agent"] for g in exactly["given"]] == ["scorer"]
    unmeasured = by_name["a-classifier-that-gives-no-score-passes-the-decision-on"]
    assert [g["agent"] for g in unmeasured["given"]] == ["scorer", "reader"]

    agrees = by_name["a-second-opinion-that-agrees-leaves-the-rules-label-standing"]
    # The rule had decided, and the second opinion was asked all the same.
    assert [g["agent"] for g in agrees["given"]] == ["checker"] and agrees["shown"] == []
    assert agrees["answer"] == {"shelf": "bills", "decided": "rules"}
    differs = by_name["a-second-opinion-that-disagrees-leaves-nothing-standing-and-a-person-decides"]
    # `who` is the person, as the host named them beside their answer.
    assert differs["answer"] == {"shelf": "other", "decided": "person", "who": "dana"}
    assert [s["question"] for s in differs["shown"]] == ["which-shelf"]
    unsure = by_name["a-second-opinion-that-is-not-sure-leaves-nothing-standing-either"]
    assert unsure["answer"] == {"shelf": "bills", "decided": "person", "who": "dana"}
    alone = by_name["with-no-label-standing-the-second-opinion-decides-and-the-record-names-it"]
    assert alone["answer"] == {"shelf": "other", "decided": "agent", "who": "checker"}
    waits = by_name["a-disagreement-with-nobody-to-ask-parks-at-the-decision"]
    assert waits["halted"] == "parked" and waits["parked-at"] == "where"

    passed = by_name["a-loop-that-passes-says-how-many-rounds-it-took-and-that-it-passed"]
    assert passed["answer"] == {"rounds": 2, "ended": "passed", "outcome": "answered"}
    ran_out = by_name["a-loop-that-runs-out-says-so-and-ends-in-too-many-times"]
    assert ran_out["answer"] == {"rounds": 3, "ended": "ran-out", "outcome": "too-many-times"}

    closes = by_name["out-of-tool-calls-it-answers-with-what-it-has-in-one-request-with-no-tools"]
    # Both calls ran; the closing request was offered nothing; the run says
    # which ceiling ended it, and is not `final`.
    assert len(closes["executed"]) == 2 and closes["offered"][-1] == []
    assert closes["halted"] == "tool-call-limit" and closes["output"].startswith("Rent and gas")
    # And that request says why: which ceiling, and to answer from what it has.
    assert closes["closing"].startswith(
        "This run has reached its limit, `tool-calls-at-most` (2 of 2 tool calls)."
    )
    assert "NOT made" not in closes["closing"], "every call asked for was made"
    stops = by_name["out-of-tool-calls-it-stops-and-says-which-ceiling"]
    assert stops["halted"] == "tool-call-limit" and "`tool-calls-at-most` (2 of 2" in stops["output"]
    assert all(offer for offer in stops["offered"]), "no closing request is made"
    assert stops["closing"] == ""
    more = by_name["out-of-tool-calls-it-asks-a-person-and-a-yes-gives-it-the-same-budget-again"]
    assert more["halted"] == "final" and len(more["executed"]) == 3 and len(more["parks"]) == 1
    refused = by_name["out-of-tool-calls-it-asks-a-person-and-a-no-ends-the-run"]
    assert refused["halted"] == "out-of-budget" and len(refused["executed"]) == 2
    # It says which ceiling and that somebody said no. Not the model's last
    # words (there were none), and not "Waiting for a person".
    assert refused["output"] == (
        "Stopped before finishing: this run reached the limit you set with "
        "`tool-calls-at-most` (2 of 2 tool calls). A person was asked and said not to keep going."
    )
    silence = by_name["nobody-answers-the-budget-question-in-time"]
    # The same ending, and no person is said to have refused.
    assert silence["halted"] == "out-of-budget" and len(silence["executed"]) == 2
    assert silence["output"].endswith("A person was asked and nobody answered in time.")
    assert "said not to" not in silence["output"]
    both = by_name["two-ceilings-reached-together-and-a-no-names-the-one-that-stopped-the-run"]
    # At two of two steps and two of two lookups; the lookups stopped it.
    assert [e[1]["entry"] for e in both["executed"]] == ["rent", "gas"]
    assert "`tool-calls-at-most` (2 of 2 tool calls)" in both["output"]
    assert "steps-at-most" not in both["output"]
    together = by_name["a-third-call-asked-for-in-the-same-reply-as-the-second"]
    assert [e[1]["entry"] for e in together["executed"]] == ["rent", "gas"], "the third never ran"
    # The model is told the third was not made, so it does not answer as if it had been.
    assert (
        'were NOT made and have no result: ledger {"action": "look", "entry": "water"}.'
        in together["closing"]
    )
    paced = by_name["out-of-steps-it-answers-with-what-it-has"]
    assert paced["halted"] == "step-limit" and paced["offered"][-1] == []
    plain = by_name["an-answer-before-any-ceiling-is-an-ordinary-answer"]
    assert plain["halted"] == "final"

    parked = by_name["nobody-is-there-to-ask-so-the-run-parks-at-the-decision"]
    assert parked["halted"] == "parked" and parked["parked-at"] == "where" and parked["question"] == "which-desk"
