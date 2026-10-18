"""A suite scores the runs it says it scores, with the checks it names (02W §2.13).

The four ready-made checks (`library:`) hold an answer to what the run was given
and what its tools returned, a carried `pure` program (`program:`) passes or
fails it with its reason, and both are decided in the deterministic pass, before
any judge. `populations` says which runs a suite is a score of: the window of
`past-runs`, the share of `sampled-frame` (decided by each run's own id), and the
score broken down by `sliced-by:`.
"""

from __future__ import annotations

import json

import pytest

from pact_adapters.evals import (
    LIBRARY_RULE,
    PROGRAM_RULE,
    Case,
    CaseOutcome,
    Rule,
    check,
    first_broken,
    rules_of,
)
from pact_adapters.harness import RunResult, Step, ToolCall
from pact_adapters.library_checks import LIBRARY, broken
from pact_adapters.populations import NOT_GIVEN, PAST_RUNS, SAMPLED, Population, in_sample, slices


def ran(output, *, given=None, asked="", returned=()):
    steps = [Step(1, "", (ToolCall("reader/read", {}),), tuple(returned))] if returned else []
    return RunResult(output=output if isinstance(output, str) else json.dumps(output), steps=steps,
                     given=given or {}, asked=asked)


# ── the four ready-made checks ──────────────────────────────────────────────


def test_every_number_the_answer_states_is_one_it_was_given_or_read():
    returned = ['{"total": "1,200.00 USD", "lines": 3}']
    ok = ran({"total": 1200, "lines": 3, "vendor": "Acme"}, returned=returned)
    assert first_broken([Rule(LIBRARY_RULE, ("numbers-come-from-the-source",))], ok) == ""
    made_up = ran({"total": 1250, "lines": 3}, returned=returned)
    why = first_broken([Rule(LIBRARY_RULE, ("numbers-come-from-the-source",))], made_up)
    assert why.startswith("states 1250, which nothing it was given or read says")
    # A number written into a word is a name, not a figure; a given value counts as read.
    assert broken("numbers-come-from-the-source", "Coded ICD10 for 2 visits", given={"visits": 2}) == ""
    # How sure the answer is, is its own word, not a figure it read (02W §5.2's reader).
    read = json.dumps({"invoice": {"total": "866.00 USD", "lowest-confidence": 0.97}})
    assert broken("numbers-come-from-the-source", read, asked="Total 866.00 USD") == ""


def test_every_quoted_passage_is_word_for_word_in_the_source():
    source = "We run after-school mural and music studios for 140 teenagers.   Led by alumni."
    good = ran({"quotes": ["we run after-school mural and music studios for 140 teenagers"],
                "summary": 'It says "led by alumni".'}, asked=source)
    assert broken("quotes-are-word-for-word", good.output, asked=source) == ""
    bad = 'The narrative says "led by former students".'
    assert "quotes 'led by former students'" in broken("quotes-are-word-for-word", bad, asked=source)


def test_an_answer_cites_something_and_only_what_it_was_given():
    read = ["Handbook section 4.2: refunds within 30 days. https://example.org/handbook"]
    assert broken("cites-its-sources", "Refunds take 30 days [Handbook section 4.2].", returned=read) == ""
    assert broken("cites-its-sources", json.dumps({"sources": ["https://example.org/handbook"]}), returned=read) == ""
    assert broken("cites-its-sources", "Refunds take 30 days.", returned=read) == "cites nothing"
    assert "cites 'Policy 9'" in broken("cites-its-sources", "As [Policy 9] says.", returned=read)


def test_no_number_it_was_given_comes_back_lower_under_its_name():
    assert broken("only-goes-up", json.dumps({"version": 4, "best": 0.8}), given={"version": 3, "best": 0.8}) == ""
    said = broken("only-goes-up", json.dumps({"version": 2}), given={"version": 3})
    assert said == "gives version as 2, lower than the 3 it was given"


def test_a_ready_made_check_is_read_by_name_and_an_unknown_one_is_reported():
    doc = {"evals": {"rules": [{"library": name} for name in LIBRARY] + [{"library": "numbers-are-right"}]}}
    assert [r.sentence for r in rules_of(doc)] == list(LIBRARY)
    case = Case.from_document({"evals": {"cases": {"c": {"when": "x", "must-also": [{"library": "nope"}]}}}})[0]
    assert case.must_also == () and "`library:` (one of numbers-come-from-the-source" in case.unenforced[0]


# ── a program that grades ───────────────────────────────────────────────────


def test_a_program_passes_or_fails_the_answer_with_its_reason():
    asked = []

    def run_program(name, inputs):
        asked.append((name, inputs))
        return "ok" if "approved" in inputs["answer"] else "the decision is missing"

    rule = Rule(PROGRAM_RULE, ("decision-present",))
    assert first_broken([rule], ran("approved", given={"amount": 5}), run_program=run_program) == ""
    assert asked[0] == ("decision-present", {"answer": "approved", "given": {"amount": 5}, "asked": "", "returned": []})
    why = first_broken([rule], ran("hmm"), run_program=run_program)
    assert why == "`program: decision-present` says: the decision is missing"


def test_a_program_nothing_can_run_is_reported_and_one_that_fails_fails_the_answer():
    case = Case(key="c", when="x", expect={})
    rule = Rule(PROGRAM_RULE, ("grade",), where="evals/suite.yaml")
    outcome = check(case, ran("anything"), [rule])
    assert outcome.passed and "`program: grade` was not applied" in outcome.unenforced[0]

    def failing(name, inputs):
        raise RuntimeError("the room is gone")

    outcome = check(case, ran("anything"), [rule], run_program=failing)
    assert not outcome.passed and outcome.why == "`program: grade` could not grade it: the room is gone"


def test_program_and_library_rules_are_decided_before_any_judge():
    class Judge:
        model = "judge"

        def grade(self, *a, **k):  # pragma: no cover - must never be reached
            raise AssertionError("a judge was asked about a case a check already failed")

    case = Case(key="c", when="x", expect={})
    rules = [Rule("judged", ("is polite",)), Rule(LIBRARY_RULE, ("cites-its-sources",))]
    outcome = check(case, ran("no citation"), rules, judge=Judge())
    assert not outcome.passed and outcome.why.startswith("cites nothing")


# ── which runs a suite scores ───────────────────────────────────────────────


def test_the_population_lines_are_read_as_written():
    doc = {"evals": {"population": "sampled-frame", "sample": "5%", "reviewed-by": ["nurse-lead"],
                     "sliced-by": ["region", "school-type"], "runs-every": "nights at 2"}}
    p = Population.of(doc)
    assert (p.kind, p.sample, p.reviewed_by, p.sliced_by) == (SAMPLED, 0.05, ("nurse-lead",), ("region", "school-type"))
    assert p.schedule.next_after is not None
    replayed = Population.of({"evals": {"population": "past-runs", "from-the-last": "30 days"}})
    assert (replayed.kind, replayed.from_the_last, replayed.sample) == (PAST_RUNS, 30 * 86400.0, None)
    assert Population.of({}).kind == "authored-enumeration"


def test_a_run_is_in_the_sample_by_its_own_id_and_the_share_taken_is_the_share_written():
    ids = [f"port.inbox.msg-{i}" for i in range(20000)]
    first = [i for i in ids if in_sample(i, 0.1)]
    assert first == [i for i in reversed(ids) if in_sample(i, 0.1)][::-1]  # order never matters
    assert 0.09 < len(first) / len(ids) < 0.11
    assert set(first) <= {i for i in ids if in_sample(i, 0.5)}  # a larger share keeps the smaller one's runs
    assert not any(in_sample(i, 0) for i in ids[:100]) and all(in_sample(i, 1) for i in ids[:100])


def test_scores_are_broken_down_by_what_each_run_was_given():
    results = [CaseOutcome(f"r{i}", passed=i % 3 != 0, why="") for i in range(12)]
    given = {f"r{i}": {"region": "north" if i < 6 else "south", "urgent": i % 2 == 0} for i in range(11)}
    out = slices(results, given, ["region", "urgent"], 0.6)
    assert sorted(out["region"]) == [NOT_GIVEN, "north", "south"]
    north = out["region"]["north"]
    assert (north.outcome, round(north.score, 2), len(north.results)) == ("PASS", 0.67, 6)
    assert out["region"][NOT_GIVEN].outcome == "UNDECIDED"  # one run is too few for the bar
    assert sorted(out["urgent"]) == [NOT_GIVEN, "no", "yes"]
    assert sum(len(v.results) for v in out["urgent"].values()) == 12


@pytest.mark.parametrize("name", LIBRARY)
def test_each_ready_made_check_passes_an_answer_that_keeps_to_its_source(name):
    answer = json.dumps({"total": 5, "quote": "five apples", "source": "the order", "count": 5})
    assert broken(name, answer, asked="the order: five apples, total 5", given={"count": 5}) == ""


def test_pact_eval_prints_each_slice_beside_the_suites_verdict():
    from pact_adapters.evals import verdict
    from pact_adapters.scoring import Scored, render

    results = [CaseOutcome(f"c{i}", passed=i != 0, why="") for i in range(6)]
    groups = slices(results, {f"c{i}": {"region": "north" if i < 3 else "south"} for i in range(6)}, ["region"], 0.5)
    text = render(Scored(cases=6, bar=0.5, verdict=verdict(results, 0.5), slices=groups))
    assert "sliced by region: north — UNDECIDED (2 of 3)" in text
    assert "sliced by region: south — UNDECIDED (3 of 3)" in text
