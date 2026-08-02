"""Config-only evaluation and runtime SLO enforcement."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.providers import (  # noqa: E402
    MetricSpec, available_deepeval_metrics, evaluate_metric,
)
from pact_adapters.slo import FEELS, Slo  # noqa: E402

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session")
def document() -> dict:
    if not (REPO / "target/debug/pact").exists():
        pytest.skip("build the CLI first")
    out = subprocess.run([str(REPO / "target/debug/pact"), "show",
                          str(REPO / "examples/refund-desk")],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


# ------------------------------------------------------------------ evals


def test_the_whole_deepeval_metric_surface_is_reachable_from_config() -> None:
    """AC-4.1. Every metric an author can name is a URI, not an import."""
    metrics = available_deepeval_metrics()
    assert len(metrics) >= 45, f"only {len(metrics)} reachable"
    for expected in ["deepeval:answer_relevancy", "deepeval:faithfulness",
                     "deepeval:hallucination", "deepeval:toxicity", "deepeval:g_eval"]:
        assert expected in metrics, f"{expected} missing from {len(metrics)} metrics"


def test_the_excluded_metrics_are_excluded_deliberately() -> None:
    """The six legacy RAGAS wrappers hard-import `ragas` + HF `datasets` and
    need a LangChain embeddings object. Letting them through this provider would
    make an air-gapped install fail at eval time instead of at config time."""
    assert not [m for m in available_deepeval_metrics() if "ragas" in m]


def test_deterministic_checks_need_no_model_at_all() -> None:
    """AC-4.5, and the reason the suite runs air-gapped."""
    r = evaluate_metric(MetricSpec.parse("pact:contains"), "Approved: refund 40 USD", "40 USD")
    assert r.passed and r.deterministic and r.score == 1.0


def test_a_forbidden_phrase_is_caught_deterministically() -> None:
    """This is a real failure observed from a real 1B model, which answered
    'you will receive a full refund within the next 3-5 business days' — the one
    thing the agent's instructions forbid it to promise."""
    r = evaluate_metric(
        MetricSpec.parse("pact:absent"),
        "You will receive a full refund within the next 3-5 business days.",
        "business days",
    )
    assert not r.passed and r.deterministic


def test_a_metric_is_declared_entirely_in_config() -> None:
    spec = MetricSpec.parse({"uri": "deepeval:answer_relevancy", "threshold": 0.8,
                             "with": {"include_reason": False}})
    assert spec.scheme == "deepeval" and spec.metric == "answer_relevancy"
    assert spec.threshold == 0.8 and spec.with_ == {"include_reason": False}


def test_an_unknown_metric_fails_closed_with_its_name() -> None:
    r = evaluate_metric(MetricSpec.parse("deepeval:not_a_real_metric"), "x")
    assert not r.passed and "not_a_real_metric" in r.reason
    r2 = evaluate_metric(MetricSpec.parse("nosuchprovider:thing"), "x")
    assert not r2.passed and "nosuchprovider" in r2.reason


# -------------------------------------------------------------------- SLO


def test_slos_are_read_from_the_authors_yaml(document: dict) -> None:
    agent = (document.get("agents") or {})["refund-desk"]
    slo = Slo.from_mapping(agent.get("limits") or {})
    assert slo.finishes_within_s == 30.0
    assert slo.cost_per_request_under == 0.05
    assert slo.measured_at == "p95"


def test_the_ceilings_have_exactly_one_enforcer_and_it_is_not_this_module() -> None:
    """`slo.py` used to carry a `Budget` that stopped a run — `check_elapsed`,
    `add_cost`, `note_first_token`, all raising `SloBreach` — and nothing in
    `src/` ever constructed one. The only import in the repository was this
    file. So `finishes-within` and `cost-per-request-under` were enforced by
    `Limits` and by nothing else, while a reader of `slo.py` believed there were
    two enforcers. It is deleted rather than wired: a second mechanism for one
    ceiling is how one ceiling comes to mean two things."""
    import pact_adapters.slo as slo

    for gone in ("Budget", "SloBreach"):
        assert not hasattr(slo, gone), f"{gone} overlaps `Limits` and must not come back"


def test_a_latency_promise_nothing_measures_is_reported_rather_than_assumed() -> None:
    """`first-reply-within` and `per-word-under` are held by no run: measuring a
    first token needs the transport to say when one arrived, and none of the
    seven does. An author who wrote one is told so, through the same door every
    other unenforceable line leaves by."""
    assert Slo.from_mapping({"first-reply-within": "2s"}).unmetered() == ("first-reply-within",)
    assert Slo.from_mapping({"per-word-under": "50ms"}).unmetered() == ("per-word-under",)
    assert Slo.from_mapping({"finishes-within": "30s"}).unmetered() == ()


def test_one_word_of_feel_supplies_the_latency_figures_nobody_wrote() -> None:
    """`feel:`'s own help says it "sets the latency band and the give-up time
    from the built-in defaults", and for a round it appeared in the schema, in
    the worked example, and in two tests asserting it is PRESENT — and in no code
    that acted on it. A `tier: core` field making a behavioural claim nothing
    keeps is the failure this project is written against."""
    interactive = Slo.from_mapping({"feel": "interactive"})
    assert (interactive.first_reply_within_s, interactive.finishes_within_s) == FEELS["interactive"]
    # A voice agent and a batch agent cannot be governed by the same numbers.
    assert Slo.from_mapping({"feel": "voice"}).first_reply_within_s < interactive.first_reply_within_s
    assert Slo.from_mapping({"feel": "batch"}).finishes_within_s > interactive.finishes_within_s
    # And anything the author wrote wins over the band.
    assert Slo.from_mapping({"feel": "voice", "finishes-within": "45s"}).finishes_within_s == 45.0


def test_a_percentile_claim_over_too_few_samples_is_refused() -> None:
    """Same failure as a pass bar over three eval cases: a number that reads
    like evidence and is not."""
    slo = Slo(finishes_within_s=10.0, measured_at="p95")
    assert slo.assess([1.0, 2.0, 3.0], "e2e").startswith("UNDECIDED")
    assert slo.assess([1.0] * 20, "e2e").startswith("PASS")
    assert slo.assess([50.0] * 20, "e2e").startswith("FAIL")


def test_an_ungoverned_metric_is_reported_as_ungoverned_not_as_passing() -> None:
    assert Slo().assess([1.0] * 50, "ttft") == "UNGOVERNED"


# ------------------------------------------- AD-58a: the money-moving subset


def test_a_money_moving_failure_cannot_hide_inside_a_good_average() -> None:
    """ADR AD-58a, resolving EDIT-1.

    The previous rule raised the whole suite bar to 90% for any agent with an
    approval gate. That made the flagship uncertifiable AND was weaker where it
    mattered: one wrongly-approved refund could sit inside a 90% average and
    still pass. Consequential assertions are correctness invariants, not a rate.
    """
    from pact_adapters.evals import CaseOutcome, consequential_verdict, verdict

    results = [
        CaseOutcome("issue-refund", False, "approved outside the 30-day window"),
        *[CaseOutcome(f"ok{i}", True, "") for i in range(9)],
    ]
    # 90% overall — comfortably over any suite bar.
    assert verdict(results, bar=0.9).outcome == "PASS"
    # And still refused, because the one that failed moves money.
    strict = consequential_verdict(results, {"issue-refund"})
    assert strict.outcome == "FAIL"
    assert "average cannot excuse" in strict.note


def test_the_suite_bar_is_untouched_by_the_consequential_rule() -> None:
    """The flagship stays certifiable at the bar `pact init` chose — the floor
    applies to the assertion subset, not the suite."""
    from pact_adapters.evals import CaseOutcome, consequential_verdict

    results = [CaseOutcome(f"c{i}", True, "") for i in range(6)]
    assert consequential_verdict(results, {"c0"}).outcome == "PASS"
    assert consequential_verdict(results, set()).outcome == "PASS"


def test_the_grader_scores_the_decision_not_the_wording() -> None:
    """Found on real weights: `qwen2.5:7b-instruct` answered *"Yes, a refund is
    appropriate in this case"* — substantively correct — and a literal
    `"approved" in text` check failed it. Grading wording instead of decision
    makes the oracle measure the wrong thing, and every claim built on it
    inherits the error."""
    from pact_adapters.evals import Case, check
    from pact_adapters.harness import RunResult, Step

    case = Case("clear-approve", "lamp arrived cracked", {"decision": "approved"})

    def outcome(text: str):
        return check(case, RunResult(output=text, steps=[Step(0, text)]), [])

    assert outcome("Yes, a refund is appropriate in this case.").passed
    assert outcome("DECISION: approved").passed
    assert outcome("The customer is eligible for a refund.").passed
    # And it must still catch a genuinely wrong decision.
    assert not outcome("DECISION: declined").passed
    assert not outcome("No refund is possible here.").passed
