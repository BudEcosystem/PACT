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

FILES = ("reactions.json", "workflows.json")


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

    parked = by_name["nobody-is-there-to-ask-so-the-run-parks-at-the-decision"]
    assert parked["halted"] == "parked" and parked["parked-at"] == "where" and parked["question"] == "which-desk"
