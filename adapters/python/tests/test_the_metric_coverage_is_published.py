"""AC-4.1 — a published coverage matrix of every DeepEval metric.

> Published coverage matrix of every DeepEval metric.

The metrics worked; nothing published what was covered. `available_deepeval_metrics()`
answers *"what can I write"*; a matrix is an artifact somebody can read, diff and
disagree with — and the difference matters, because a claim nobody can check is
the thing this register keeps finding.

**Computed from the installed DeepEval, never listed.** A hand-written matrix is
a second copy of somebody else's release notes and is wrong the first time they
ship a metric. That is invariant E-4 — the provider resolves by string, so adding
a metric is a YAML edit — and enumerating the set here would put back the exact
coupling E-4 removes.

The one row that must never appear is *"shipped by DeepEval and not reachable
from config"*. Two exclusions are decisions (`Base*` are abstract, `Ragas*` bring
their own model plumbing and would take grading away from the author's
`graded-by:` line); anything else in that bucket is a defect, and the matrix is
where it shows.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.providers import DEEPEVAL, available_deepeval_metrics, coverage  # noqa: E402


def test_the_matrix_is_an_artifact_with_a_kind() -> None:
    said = coverage()
    assert said["kind"] == "MetricCoverage"
    assert said["apiVersion"] == "pact.dev/v1"
    assert said["provider"] == DEEPEVAL


def test_an_absent_provider_is_reported_rather_than_shown_as_empty() -> None:
    """DeepEval not being installed is a different fact from "there are no
    metrics", and a matrix that showed zero would be the second one."""
    said = coverage()
    if said["installed"]:
        pytest.skip("DeepEval is installed here; the absent case is the other branch")
    assert said["ships"] == [] and said["reachable"] == []
    assert "not on this machine" in said["why"]


def test_every_metric_deepeval_ships_is_reachable_or_explained() -> None:
    """The property the criterion is about. A metric in neither bucket would be
    one PACT silently does not offer."""
    said = coverage()
    if not said["installed"]:
        pytest.skip("DeepEval is not installed here")

    offered = {u.split(":", 1)[1] for u in said["reachable"]}
    assert len(offered) == len(said["reachable"]), "two URIs collided"
    accounted = len(said["reachable"]) + len(said["not-offered"])
    assert accounted == len(said["ships"]), (
        f"DeepEval ships {len(said['ships'])} and the matrix accounts for "
        f"{accounted}"
    )
    assert said["counted"]["ships"] == len(said["ships"])


def test_nothing_is_missing_for_a_reason_that_is_not_a_reason() -> None:
    """The row that must never appear. `Base*` and `Ragas*` are decisions;
    anything else in that bucket is a defect and this is where it shows."""
    said = coverage()
    if not said["installed"]:
        pytest.skip("DeepEval is not installed here")
    defects = {
        name: why for name, why in said["not-offered"].items()
        if "defect" in why
    }
    assert not defects, (
        "DeepEval ships these and no author can name them:\n  "
        + "\n  ".join(sorted(defects))
    )
    for name, why in said["not-offered"].items():
        assert name.startswith(("Base", "Ragas")), (
            f"{name} is excluded and is neither an abstract base nor a Ragas "
            f"metric: {why}"
        )


def test_the_matrix_and_the_thing_an_author_writes_agree() -> None:
    """Two answers to one question drift. The matrix reports what
    `available_deepeval_metrics()` returns rather than recomputing it."""
    said = coverage()
    if not said["installed"]:
        pytest.skip("DeepEval is not installed here")
    assert said["reachable"] == available_deepeval_metrics()
    for uri in said["reachable"]:
        assert uri.startswith(f"{DEEPEVAL}:"), uri


def test_the_matrix_is_big_enough_to_be_one() -> None:
    said = coverage()
    if not said["installed"]:
        pytest.skip("DeepEval is not installed here")
    assert len(said["reachable"]) > 20, (
        f"only {len(said['reachable'])} metrics reachable — the walk is broken"
    )
