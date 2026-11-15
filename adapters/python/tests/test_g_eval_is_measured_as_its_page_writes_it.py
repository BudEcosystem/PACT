"""G-Eval, written in a suite the way DeepEval's own page writes it, is measured.

    metrics:
      - uri: deepeval:g_eval
        threshold: 0.5
        with:
          name: polite
          criteria: Is the answer polite to the customer?
          evaluation_params: [input, actual_output]

Measured on DeepEval 4.3.3 before this file existed, that line was reported
absent on every case: the two names reached G-Eval as strings, and G-Eval
reads `.value` off each one (*"'str' object has no attribute 'value'"*).
Writing no `evaluation_params:` does not help either: G-Eval then grades a
trace, and a case answer carries none. So the one DeepEval score an author
defines in their own words could not be written at all.

The judge here is scripted and offline; it is the same `AskModel` the eval
runner builds from `graded-by:`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

pytest.importorskip("deepeval")

from pact_adapters.providers import AskModel, MetricSpec, evaluate_metric  # noqa: E402


def _scripted(score: int) -> AskModel:
    """A judge that writes G-Eval's evaluation steps, then the given score out of 10."""

    def ask(_system: str, user: str) -> str:
        if '"steps"' in user:
            return json.dumps({"steps": ["Read the tone of the answer.", "Check it addresses the request."]})
        return json.dumps({"score": score, "reason": "scripted"})

    return AskModel("scripted", ask)


def _g_eval(**written: object) -> MetricSpec:
    return MetricSpec(
        uri="deepeval:g_eval",
        threshold=0.5,
        with_={"name": "polite", "criteria": "Is the answer polite to the customer?", **written},
    )


def test_evaluation_params_written_as_names_are_measured() -> None:
    taken = evaluate_metric(
        _g_eval(evaluation_params=["input", "actual_output"]),
        "Thanks for waiting; your lamp is refunded.",
        asked="Refund my lamp.",
        judge=_scripted(7),
    )
    assert taken.unenforced == ""
    assert taken.score == pytest.approx(0.7)
    assert taken.passed


def test_the_member_names_and_deepevals_own_spelling_mean_the_same_thing() -> None:
    lower = evaluate_metric(_g_eval(evaluation_params=["input", "actual_output"]), "Fine.", asked="Hi", judge=_scripted(3))
    upper = evaluate_metric(_g_eval(evaluation_params=["INPUT", "ACTUAL_OUTPUT"]), "Fine.", asked="Hi", judge=_scripted(3))
    assert lower.score == upper.score == pytest.approx(0.3)
    assert not lower.passed


def test_a_rubric_written_as_mappings_is_read_as_deepevals_rubric() -> None:
    taken = evaluate_metric(
        _g_eval(
            evaluation_params=["input", "actual_output"],
            rubric=[
                {"score-range": [0, 4], "expected-outcome": "curt or rude"},
                {"score_range": [5, 10], "expected_outcome": "polite and on the point"},
            ],
        ),
        "Thanks for waiting; your lamp is refunded.",
        asked="Refund my lamp.",
        judge=_scripted(8),
    )
    assert taken.unenforced == ""
    assert taken.score == pytest.approx(0.8)


def test_a_name_that_is_no_test_case_field_is_still_refused_by_g_eval_and_named() -> None:
    taken = evaluate_metric(
        _g_eval(evaluation_params=["input", "the_tone"]),
        "Fine.",
        asked="Hi",
        judge=_scripted(5),
    )
    assert taken.unenforced != ""
    assert "deepeval:g_eval" in taken.unenforced


def test_every_other_score_keeps_its_settings_as_written() -> None:
    from pact_adapters.providers import _as_deepeval_reads, _deepeval_classes

    classes = _deepeval_classes() or {}
    written = {"evaluation_params": ["input"], "rubric": [{"score-range": [0, 1]}]}
    assert _as_deepeval_reads(classes["answerrelevancy"], written) == written
