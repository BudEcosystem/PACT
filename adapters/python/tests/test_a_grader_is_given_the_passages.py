"""The retrieval parameter that had no author (A2).

`providers.evaluate_metric` has declared `retrieval_context` since it was
written, and forwards it into `LLMTestCase`. Its one caller — `evals.py` — passed
five arguments and never it. So `deepeval:faithfulness` was accepted by name,
loaded cleanly, and could never return a score.

That is the reader-table defect running the other way. `test_every_field_has_a_reader`
asks whether a field an author writes reaches a runtime; this is a PARAMETER a
runtime reads that no author could reach.

The fix is two things, not one. An authored gold context is a decision — the
passages the answer was *supposed* to come from — and what a run retrieved is a
measurement. Three of the four canonical retrieval metrics never read the answer
at all, so grading them against a constant the author typed scores the author's
own typing: the number is identical whether the runtime fetched the right
passage, the wrong one, or nothing.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters import evals as evals_mod  # noqa: E402
from pact_adapters.evals import Case  # noqa: E402
from pact_adapters.harness import RunResult  # noqa: E402
from pact_adapters.providers import evaluate_metric  # noqa: E402

REPO = Path(__file__).resolve().parents[3]


def test_the_parameter_the_runtime_reads_is_one_an_author_can_reach() -> None:
    """The whole test, in one line: `evaluate_metric` takes it, so something
    has to pass it, so an author has to be able to say it."""
    assert "retrieval_context" in inspect.signature(evaluate_metric).parameters
    source = (REPO / "adapters/python/src/pact_adapters/evals.py").read_text()
    assert "retrieval_context=" in source, (
        "the one caller of `evaluate_metric` still does not pass it"
    )


def test_an_author_can_write_the_passages_on_a_case() -> None:
    schema = yaml.safe_load((REPO / "spec/schema.yaml").read_text())["groups"]
    field = schema["case"]["fields"].get("from-these-passages")
    assert field is not None, "there is no line an author can write"
    assert field["type"] == "list of text"
    assert field["surface"] == "S-GOV"


def test_what_the_author_wrote_reaches_the_case() -> None:
    cases = Case.from_document(
        {
            "evals": {
                "cases": {
                    "grounded": {
                        "when": "Where is my refund?",
                        "expect": {"answer": "in 3 days"},
                        "from-these-passages": ["Refunds take 3 days.", "We email you."],
                    }
                }
            }
        }
    )
    assert len(cases) == 1
    assert cases[0].from_these_passages == ("Refunds take 3 days.", "We email you.")


def test_a_run_reports_what_it_retrieved_and_an_author_does_not_type_it() -> None:
    """A fact about the run belongs on the run. If the author had to write it,
    every retrieval metric would be scoring a constant they chose."""
    assert "retrieved" in RunResult.__dataclass_fields__
    assert RunResult(output="x").retrieved == ()
    schema = yaml.safe_load((REPO / "spec/schema.yaml").read_text())["groups"]
    for group in schema.values():
        assert "retrieved" not in (group.get("fields") or {}), (
            "`retrieved` is something a run measures, not something an author types"
        )


def test_the_authored_passages_win_over_the_observed_ones() -> None:
    """A written-down gold context is a decision and an observed one is a
    measurement. A grader asked whether an answer is grounded in its sources
    should be handed the sources the author meant."""
    source = (REPO / "adapters/python/src/pact_adapters/evals.py").read_text()
    at = source.index("retrieval_context=")
    passed = source[at : at + 200]
    assert "from_these_passages" in passed, passed
    assert passed.index("from_these_passages") < passed.index("retrieved"), (
        "the authored passages have to be tried first: " + passed
    )
