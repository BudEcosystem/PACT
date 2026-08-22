"""A grader an author carries, run offline and never by a model (P8 wave 3).

`evals.metrics:` names a score by URI, and two schemes ship: `pact:` — the small
set this build takes on its own, with no model and nothing installed — and
`deepeval:`, which reaches every score that library has. What an author could not
do is bring a score of their own that is EXACT.

That is not a gap in the vocabulary; it is the gap the `program` kind exists to
close, one surface over. A refund amount, a checksum, a date window: these have a
right answer, and grading them today means either a `judged:` rule put to a
model — which costs money, needs a judge binding, and is not decidable offline —
or a `must-contain:` string match that grades the wording rather than the number.

`program:<name>` is the third scheme. It runs in the DETERMINISTIC-FIRST band
beside `pact:`, so a suite that can be fully decided still never invokes a model
(AC-4.5), and it is air-gapped by construction because the body is in the folder.

The rule it inherits: a program is run by the HOST. This port declares the
seam and reports honestly when nothing supplies one — a score that could not be
taken is named on the report with a line to type, never quietly skipped, which is
the same promise `evals.metrics:`'s own help already makes.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.providers import (  # noqa: E402
    PROGRAM,
    PROVIDERS,
    MetricSpec,
    evaluate_metric,
    why_unavailable,
)


def _spec(uri: str, threshold: float = 0.5) -> MetricSpec:
    return MetricSpec(uri=uri, threshold=threshold)


# ───────────────────────────────────────────────────────── the scheme is real


def test_the_scheme_is_one_of_the_ones_this_build_answers_to() -> None:
    """`PROVIDERS` is what every diagnostic offers, so a scheme absent from it is
    a scheme the author is told does not exist."""
    assert PROGRAM in PROVIDERS


def test_a_program_score_with_a_runner_is_measured() -> None:
    """The whole point: an exact grader, and no model anywhere near it."""
    spec = _spec("program:refund-is-right", threshold=0.5)

    def runner(name: str, args: dict) -> str:
        assert name == "refund-is-right"
        # The grader is handed what was answered and what was expected, and says
        # how right it was.
        return "1.0" if args["actual"] == args["expected"] else "0.0"

    right = evaluate_metric(
        spec, actual="45.00 USD", expected="45.00 USD", run_program=runner
    )
    assert right.passed
    assert right.score == 1.0

    wrong = evaluate_metric(
        spec, actual="40.00 USD", expected="45.00 USD", run_program=runner
    )
    assert not wrong.passed
    assert wrong.score == 0.0


def test_a_program_score_needs_no_judge() -> None:
    """The band this belongs in.

    A `deepeval:` score with no judge is a hard failure under D17. A carried
    grader has nothing to bind: it is arithmetic in the folder, so a suite that
    uses only these is decidable with no model and no network — which is what
    AC-4.5 asks of the deterministic-first band.
    """
    spec = _spec("program:refund-is-right")
    got = evaluate_metric(
        spec, actual="x", expected="x", judge=None, run_program=lambda n, a: "1.0"
    )
    assert got.passed


# ─────────────────────────────────────────────────────────── the honest absence


def test_a_program_score_with_nothing_to_run_it_says_so_before_the_suite() -> None:
    """`why_unavailable` is asked before anything is measured, so a score this
    machine cannot take is reported with a line to type rather than counted as a
    failure the agent caused."""
    said = why_unavailable(_spec("program:refund-is-right"))
    assert said, "a score nothing can run is not available"
    assert "refund-is-right" in said
    assert "program" in said.lower()


def test_a_program_score_is_available_when_a_runner_is_there() -> None:
    """The other half — the report must go away when the thing is present."""
    assert why_unavailable(_spec("program:refund-is-right"), can_run_programs=True) == ""


def test_a_uri_with_no_name_after_the_colon_is_refused() -> None:
    """`program:` alone names nothing, and guessing which program was meant is
    how a suite comes to measure something nobody asked for."""
    said = why_unavailable(_spec("program:"), can_run_programs=True)
    assert said
    assert "which program" in said.lower() or "names no" in said.lower()


# ────────────────────────────────────────────────────────────── nothing moved


def test_the_two_shipped_schemes_are_untouched() -> None:
    """Additive: `pact:` still needs no judge and `deepeval:` still refuses one
    that is missing."""
    assert why_unavailable(_spec("pact:contains")) == ""
    got = evaluate_metric(_spec("pact:contains"), actual="a refund of 45", expected="45")
    assert got.passed

    unknown = why_unavailable(_spec("wasm:whatever"))
    assert "nothing on this machine provides" in unknown
    # And the offer names all three now.
    assert "program:" in unknown


def test_an_unknown_program_metric_is_not_a_crash() -> None:
    """A runner that raises is that score's failure, not the suite's."""
    def angry(name: str, args: dict) -> str:
        raise RuntimeError("no such program here")

    got = evaluate_metric(
        _spec("program:missing"), actual="a", expected="a", run_program=angry
    )
    assert not got.passed
    assert "no such program here" in got.reason
    assert "could not run" in got.reason
