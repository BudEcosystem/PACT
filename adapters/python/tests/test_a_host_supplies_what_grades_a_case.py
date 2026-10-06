"""What a host hands `evals.check` reaches the measurement it is for.

Two seams, both written into PACT and both unreachable from its one grader:

* `providers.evaluate_metric` has taken `run_program` since `program:` metrics
  shipped, and `evals.check` — the only path a suite is scored through — never
  passed it. So a `program:` score went to `unenforced` saying "nothing runs
  programs" on a host that runs them (budflow, WP9).
* The schema says a case's `because:` is "what a grader reads", and
  `from-these-passages:` is "what a grader reads when it asks whether the answer
  is actually grounded in them". The judge was shown neither: `Judge.grade` got
  the rule and the answer only, so a rule like *"only says what the passages
  support"* was put to a reader who had never seen the passages.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.evals import Case, Rule, check  # noqa: E402
from pact_adapters.harness import RunResult  # noqa: E402
from pact_adapters.judge import Judge  # noqa: E402
from pact_adapters.providers import MetricSpec  # noqa: E402


def test_a_program_metric_is_scored_by_the_runner_the_host_hands_check() -> None:
    asked: list[tuple[str, dict]] = []

    def run_program(name: str, inputs: dict) -> str:
        asked.append((name, inputs))
        return "0.25" if "maybe" in inputs["actual"] else "1.0"

    metric = MetricSpec.parse({"uri": "program:exact-amount", "threshold": 0.9, "with": {"unit": "USD"}})
    case = Case("c1", "refund the lamp", {"answer": "40 USD"})

    good = check(case, RunResult(output="40 USD"), [], metrics=[metric], run_program=run_program)
    bad = check(case, RunResult(output="maybe 40 USD"), [], metrics=[metric], run_program=run_program)

    assert good.passed and not good.unenforced
    assert not bad.passed and "program:exact-amount" in bad.why
    assert asked[0] == ("exact-amount", {"actual": "40 USD", "expected": "40 USD", "asked": "refund the lamp", "unit": "USD"})


def test_a_carried_grader_is_not_run_for_a_case_a_plain_rule_already_settled() -> None:
    """The negative half: the runner is the last thing reached, never the first.
    A case a string check failed is failed by that check, and no program runs."""
    asked: list[str] = []

    def run_program(name: str, inputs: dict) -> str:
        asked.append(name)
        return "1.0"

    metric = MetricSpec.parse({"uri": "program:exact-amount", "threshold": 0.9})
    rule = Rule("must-contain", ("refund",))
    settled = check(Case("c1", "x", {}), RunResult(output="no"), [rule], metrics=[metric], run_program=run_program)
    assert not settled.passed and "refund" in settled.why and asked == []
    # And a score below the author's bar fails the case, with the runner's own figure.
    low = check(
        Case("c2", "x", {}), RunResult(output="a refund"), [rule], metrics=[metric], run_program=lambda n, i: "0.5"
    )
    assert not low.passed and "program:exact-amount" in low.why


def test_without_a_runner_a_program_metric_is_still_reported_not_scored() -> None:
    metric = MetricSpec.parse({"uri": "program:exact-amount"})
    outcome = check(Case("c1", "x", {}), RunResult(output="40 USD"), [], metrics=[metric])
    assert outcome.passed and outcome.unenforced, "nothing ran it, and the report says so"


def test_the_judge_reads_the_cases_passages_and_why_its_answer_is_right() -> None:
    seen: list[str] = []

    def ask(system: str, user: str) -> str:
        seen.append(user)
        return "PASS\nit only says what the passage says"

    rule = Rule("judged", ("only says what the passages support",))
    case = Case(
        "grounded",
        "how long is the window?",
        {},
        because="the policy page says 30 days",
        from_these_passages=("Refunds are accepted within 30 days.",),
    )
    outcome = check(case, RunResult(output="30 days."), [rule], judge=Judge("grader", ask))

    assert outcome.passed
    (prompt,) = seen
    assert "Refunds are accepted within 30 days." in prompt
    assert "WHY THE EXPECTED ANSWER IS RIGHT: the policy page says 30 days" in prompt


def test_a_case_that_wrote_neither_asks_the_judge_exactly_what_it_asked_before() -> None:
    seen: list[str] = []
    judge = Judge("grader", lambda system, user: seen.append(user) or "PASS\nfine")
    check(Case("c", "x", {}), RunResult(output="ok"), [Rule("judged", ("is polite",))], judge=judge)
    assert seen == ["RULE: is polite\n\nANSWER:\nok"]
