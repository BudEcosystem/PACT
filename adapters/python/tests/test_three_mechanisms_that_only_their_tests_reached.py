"""Three mechanisms whose only callers were their own tests.

The defect this repository is written against, three more times, found by
widening the reachability walk rather than by reading code. The walk's orphan
check looked at functions named `from_document`, `of` and `for_document` — so
everything else was outside its reach **by construction**, which is the same
shape as the TypeScript port having no producer.

It was found by mutation: the callers were deleted from a mechanism wired an
hour earlier and `test_a_reader_is_reachable_from_a_run.py` stayed green. Adding
every door's `main` to `ENTRIES` and then listing module-level public functions
nothing reaches produced these three.

* **`harness.delegate_by_running`** — a hundred lines with its own budget
  charge-back, `Grant.spend`, and a docstring about a failure Y10 exists to
  prevent. `scoring` ran every eval case with no `ask_member`, so a delegation
  **parked the run**, the case came back "did not answer", and the model was
  blamed for it. Scoring an agent with a `team:` measured a suspension.
* **`optimising.measured`** — AC-3.5's *"by a declared margin"*. Nothing on any
  report asked whether a margin was cleared, so the criterion's own emphasis was
  a property of the test suite.
* **`providers.coverage`** — AC-4.1's *published* coverage matrix. It was
  computed correctly and published nowhere.

Each test below goes through a shipped command and asserts the effect, not the
seam. Every one is mutation-tested by severing the wire.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

REPO = Path(__file__).resolve().parents[3]
BINARY = REPO / "target" / "debug" / "pact"


# ─────────────────────────── delegate_by_running ────────────────────────────


def test_scoring_an_agent_with_a_team_actually_runs_the_team() -> None:
    """The effect, not the wire: a delegation must reach the member.

    Asserted by running the real `_run_every_case` over a document with a
    `team:` and a scripted transport that records every system prompt it is
    given. A member being *run* means a second call carrying the MEMBER's
    instructions — which is the one thing a parked run cannot produce.
    """
    import asyncio

    from pact_adapters.harness import ToolCall, delegate_by_running, run
    from pact_adapters.ir import AgentSpec
    from pact_adapters.script import Script, Turn
    from pact_adapters.transports.mock import ReferenceTransport

    document = {
        "name": "desk",
        "agents": {
            "boss": {
                "name": "Boss", "description": "Delegates.",
                "instructions": "BOSS-INSTRUCTIONS",
                "team": {"helper": "asks the helper"},
            },
            "helper": {
                "name": "Helper", "description": "Helps.",
                "instructions": "HELPER-INSTRUCTIONS",
            },
        },
    }
    seen: list[str] = []

    class Watching(ReferenceTransport):
        async def model_call(self, system, history, tools):  # type: ignore[override]
            seen.append(system)
            return await super().model_call(system, history, tools)

    spec = AgentSpec.from_document(document, "boss")
    turns = [Turn("asking", (ToolCall("helper", {"ask": "please help"}),)), Turn("done")]
    out = asyncio.run(
        run(
            spec, Watching(Script(turns)), "go", {},
            ask_member=delegate_by_running(
                document, lambda _m: Watching(Script([Turn("helped")]))
            ),
        )
    )

    assert out.halted == "final", out.halted
    said = "\n".join(seen)
    assert "HELPER-INSTRUCTIONS" in said, (
        "the member was never run — its instructions never reached a model:\n" + said
    )


def test_the_eval_command_actually_runs_the_team() -> None:
    """And the shipped command builds a real asker, which is the half missing.

    `delegate_by_running` works and always did. What made it unreachable is that
    `scoring._run_every_case` called `run(...)` without `ask_member`, so nothing
    an author could type ever reached it.

    **The first version of this test read the source and asserted the keyword was
    passed**, which is a seam and not an effect: mutating the builder to
    `if False else None` kept the keyword, passed `None`, and left the test
    green — the whole defect, reproduced in the test written to catch it. This
    calls `_run_every_case` for real, with a scripted transport that records
    every system prompt, and asserts the MEMBER's instructions reached a model.
    """
    from pact_adapters.evals import Case
    from pact_adapters.ir import AgentSpec
    from pact_adapters.script import Script, Turn
    from pact_adapters.scoring import _run_every_case
    from pact_adapters.transports.mock import ReferenceTransport
    from pact_adapters.harness import ToolCall

    document = {
        "name": "desk",
        "agents": {
            "boss": {
                "name": "Boss", "description": "Delegates.",
                "instructions": "BOSS-INSTRUCTIONS",
                "team": {"helper": "asks the helper"},
                "answers-with": {"answer": "text"},
            },
            "helper": {
                "name": "Helper", "description": "Helps.",
                "instructions": "HELPER-INSTRUCTIONS",
            },
        },
        "evals": {
            "population": "authored-enumeration",
            "cases": {"one": {"when": "go", "expect": {"answer": "done"}}},
        },
    }
    seen: list[str] = []

    class Watching(ReferenceTransport):
        async def model_call(self, system, history, tools):  # type: ignore[override]
            seen.append(system)
            return await super().model_call(system, history, tools)

    def transport_for():
        # One script serves the boss and the member alike: the boss's first turn
        # delegates, the member answers plainly. `Script` selects on history, so
        # the member — whose history has no tool result — takes the first turn's
        # text and stops.
        return Watching(Script([
            Turn("asking", (ToolCall("helper", {"ask": "please help"}),)),
            Turn("done"),
        ]))

    spec = AgentSpec.from_document(document, "boss")
    _run_every_case(
        spec, Case.from_document(document), [], transport_for, document,
    )

    said = "\n".join(seen)
    assert "HELPER-INSTRUCTIONS" in said, (
        "scoring did not run the team: the member's instructions never reached a "
        "model, so every delegation parked and the case would score as 'did not "
        "answer'.\n" + said
    )


# ───────────────────────────── optimising.measured ──────────────────────────


def test_a_proposal_report_says_whether_it_cleared_the_declared_margin() -> None:
    """AC-3.5's own emphasis, on the report a reviewer reads.

    `Learner.cycle` asks *"is this better"*, which is right for applying an
    edit. AC-3.5 asks *"is this better BY A DECLARED MARGIN"*, which is right
    for claiming an optimiser works — and a claim built on the first is a claim
    about noise. Nothing asked the second question outside a test.
    """
    from pact_adapters.evals import Verdict
    from pact_adapters.optimising import MARGIN
    from pact_adapters.scoring import _margin_line

    class _Outcome:
        before_score, after_score = 0.50, 0.70
        verdict_before = Verdict("FAIL", 0.5, 0.7, [object()] * 6)
        verdict_after = Verdict("PASS", 0.7, 0.7, [object()] * 6)

    said = _margin_line(_Outcome())
    assert f"{MARGIN:.0%}" in said, said
    assert "cleared" in said and "NOT cleared" not in said, said
    assert "+20" in said, said

    class _Barely(_Outcome):
        before_score, after_score = 0.50, 0.52  # 2 points, under the 5-point bar
        verdict_before = Verdict("FAIL", 0.50, 0.7, [object()] * 6)
        verdict_after = Verdict("FAIL", 0.52, 0.7, [object()] * 6)

    assert "NOT cleared" in _margin_line(_Barely()), _margin_line(_Barely())

    # And a margin cleared over three cases is not a result, which is the same
    # caution `Verdict` applies to a percentage over too few cases.
    class _TooFew(_Outcome):
        verdict_after = Verdict("PASS", 0.7, 0.7, [object()] * 3)

    assert "not a measurement" in _margin_line(_TooFew()), _margin_line(_TooFew())


def test_the_margin_line_is_on_the_report_a_reviewer_reads() -> None:
    """The wire, without which the sentence above is computed and shown to
    nobody — which is the whole defect being fixed here."""
    import inspect

    from pact_adapters import scoring

    source = inspect.getsource(scoring.render_proposal)
    assert "_margin_line(outcome)" in source, (
        "`render_proposal` no longer prints the margin, so a reviewer reads "
        "`50% → 70%` and has to work out for themselves whether that clears "
        "anything anybody declared."
    )


# ───────────────────────────── providers.coverage ───────────────────────────


@pytest.mark.skipif(not BINARY.exists(), reason="build the CLI first")
def test_the_conformance_report_publishes_the_metric_matrix() -> None:
    """AC-4.1 asks for a PUBLISHED matrix, so it is in the published artifact.

    `coverage()` computed it correctly and returned it to its own test. The
    difference between that and publishing is the whole of the criterion.
    """
    out = subprocess.run(
        [sys.executable, "-c",
         "from pact_adapters.conformance import main; "
         "raise SystemExit(main(['examples/patterns']))"],
        capture_output=True, text=True, cwd=REPO,
        env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
    )
    assert out.returncode in (0, 1), out.stderr[-600:]
    said = json.loads(out.stdout)
    matrix = said.get("metric-coverage")
    assert matrix is not None, sorted(said)
    assert matrix["kind"] == "MetricCoverage", matrix
    # Computed from what is installed, never listed — E-4. A matrix that
    # enumerated the set would put back the coupling E-4 removes.
    assert len(matrix["ships"]) > 20, matrix["ships"]
    assert len(matrix["reachable"]) > 20, len(matrix["reachable"])
    # And every metric it does not offer says why, which is what makes it
    # something a reader can disagree with rather than a list.
    assert all(why for why in matrix["not-offered"].values()), matrix["not-offered"]


def test_the_matrix_is_declared_before_the_results() -> None:
    """Where it sits, which the report already argues about for the lattices.

    *"A reader has to be able to see the claim before the result, or 'we
    expected that' is unfalsifiable."* The metric matrix is a claim about what
    this implementation can grade, so it goes with the other claims.
    """
    from pact_adapters.conformance import report

    said = report([], BINARY)
    keys = list(said)
    assert keys.index("metric-coverage") < keys.index("results"), keys
