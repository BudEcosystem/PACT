"""Two things a runtime other than the harness needs from the termination algebra.

* `feel:` is a latency band and never a stop. For a while it became a
  wall-clock ceiling whenever ANY ceiling wrote `when-it-runs-out:`, so
  `feel: voice` beside `tool-calls-at-most: 40` ended the run after five
  seconds, a figure the author never wrote. A stop is a written figure:
  `finishes-within:` or `runs-for-at-most:`.
* `Limits.kept_going` is the one answer to "a person said keep going": a fresh
  budget of the written size, from where the run is, for every ceiling — so a
  runtime that replays a journal (budflow) reads the same grant the harness
  would, instead of inventing one.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.limits import Action, Limits, Meter  # noqa: E402
from pact_adapters.slo import FEELS, Slo  # noqa: E402


def test_feel_beside_another_ceiling_is_not_a_wall_clock_nobody_wrote() -> None:
    limits = Limits.from_mapping(
        {"feel": "voice", "tool-calls-at-most": 40, "when-it-runs-out": "stop-and-say-so"}
    )
    assert limits.wall_clock_s is None
    assert [c.field for c in limits.ceilings()] == ["tool-calls-at-most"]
    assert limits.reached(Meter(carried=FEELS["voice"][1] + 1), 0.0) is None


def test_feel_is_still_the_latency_band_a_report_measures_against() -> None:
    slo = Slo.from_mapping({"feel": "voice", "when-it-runs-out": "stop-and-say-so"})
    assert (slo.first_reply_within_s, slo.finishes_within_s) == FEELS["voice"]


def test_feel_alone_stops_nothing() -> None:
    assert Limits.from_mapping({"feel": "batch"}).ceilings() == ()


def test_what_the_author_wrote_wins_over_feel() -> None:
    written = Limits.from_mapping(
        {"feel": "batch", "finishes-within": "45s", "when-it-runs-out": "stop-and-say-so"}
    )
    assert (written.wall_clock_s, written.wall_clock_field) == (45.0, "finishes-within")
    run_for = Limits.from_mapping(
        {"feel": "batch", "runs-for-at-most": "5s", "when-it-runs-out": "stop-and-say-so"}
    )
    assert (run_for.wall_clock_s, run_for.wall_clock_field) == (5.0, "runs-for-at-most")


def test_keeping_going_grants_every_ceiling_its_written_size_again_from_where_the_run_is() -> None:
    written = Limits.from_mapping(
        {
            "tool-calls-at-most": 3,
            "runs-for-at-most": "10s",
            "tokens-at-most": 1000,
            "cost-per-request-under": "0.05 USD",
            "steps-at-most": 4,
            "when-it-runs-out": "ask-a-person",
            "asks": "keep-going",
        }
    )
    meter = Meter(steps=2, tool_calls=3, tokens=400, money=0.01, carried=4.0)
    more, steps = written.kept_going(meter, 0.0, 4)
    assert (more.tool_calls_at_most, more.tokens_at_most, steps) == (6, 1400, 6)
    assert more.wall_clock_s == 14.0 and abs(more.cost_per_request_under - 0.06) < 1e-9
    assert more.when_it_runs_out is Action.ASK and more.cost_currency == "USD"
    # The ceiling that stopped the run no longer stops it at the same reading.
    assert written.reached(meter, 0.0, 4) is not None
    assert more.reached(meter, 0.0, steps) is None


def test_a_second_continuation_is_the_same_size_again_not_double() -> None:
    written = Limits(tool_calls_at_most=5, when_it_runs_out=Action.ASK, asks="keep-going")
    first, _ = written.kept_going(Meter(tool_calls=5), 0.0)
    second, _ = written.kept_going(Meter(tool_calls=first.tool_calls_at_most), 0.0)
    assert (first.tool_calls_at_most, second.tool_calls_at_most) == (10, 15)


def test_a_ceiling_nothing_can_reach_is_not_granted_into_one() -> None:
    held = Limits(cost_per_request_under=float("nan"), cost_currency="USD", when_it_runs_out=Action.ASK)
    more, steps = held.kept_going(Meter(money=1.0), 0.0)
    assert more.cost_per_request_under is None and more.nothing_can_reach == ("cost-per-request-under",)
    assert steps is None
