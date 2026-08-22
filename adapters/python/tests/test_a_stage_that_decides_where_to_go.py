"""Routing that reads what was SAID, not only what kind of thing happened (P8/7).

A stage ends in one of three outcomes — `used-a-tool`, `answered`,
`too-many-times` — and the author says where each one goes. That table is
complete, readable by anybody, and deliberately blind: it knows what KIND of
thing happened and never what the answer said. So a checking stage can write "I
found a contradiction with the policy" and the loop still marches to `reply`,
because that is where `answered:` points. The correction is left to the model
noticing its own prose, which is the one thing this format never relies on
anywhere else.

`docs/remediation/F1` refuses a predicate over content, and that refusal stands
for the authored surface: a condition language would be a second programming
language inside the file meant to remove the first, and D14's reader would have
to learn it. What F1 leaves open is an ESCAPE — §5.5 lists `router` among the six
typed escapes, with "a `route` node with a declared label set" as its no-code
default.

`decided-by:` is that escape, realised with the `program` kind:

    then:
      decided-by: route-after-check
      may-go-to: [reply, gather, done]

Four things make it safe rather than a hole:

  * **The destinations are declared.** A program picks BETWEEN stops the author
    wrote down; it cannot invent one. `may-go-to:` is what a reader looks at to
    know where this loop can go, and reachability is computed from it.
  * **Fuel outranks routing.** Ceilings are checked before a stage runs and after
    every model call, and no program decision reopens a spent budget. Tested,
    because "the router said continue" must never mean "the money cap did not
    apply".
  * **It is expert tier and excluded from the `no-code` badge.** A support lead's
    loop stays the three-outcome table; this is the line somebody writes when
    they have decided they want it.
  * **The decision is in the transcript**, with the program that made it, so
    "why did it loop back?" is answerable by reading rather than re-running.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.loops import Loop, LoopError  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

#: A desk that checks its own decision and goes back to gathering when the check
#: found something, rather than replying with a contradiction in it.
DECIDES = {
    "programs": {
        "route-after-check": {
            "description": "Says whether a check found something worth going back for.",
            "engine": "wasm",
            "determinism": "pure",
            "takes": {"said": "text"},
            "answers-with": {"go-to": "text"},
            "fuel": {"instructions-at-most": "1m", "when-it-runs-out": "stop-and-say-so"},
        }
    },
    "loops": {
        "careful": {
            "description": "Gather, check, then reply — going back when the check finds something.",
            "starts-at": "gather",
            "steps": {
                "gather": {"does": "use-tools", "then": {"used-a-tool": "gather", "answered": "check"}},
                "check": {
                    "does": "check-its-work",
                    "then": {
                        "used-a-tool": "check",
                        "decided-by": "route-after-check",
                        "may-go-to": ["reply", "gather", "done"],
                    },
                },
                "reply": {"does": "answer", "then": {"answered": "done"}},
            },
        }
    },
    "agents": {
        "desk": {
            "description": "Decides refunds.",
            "instructions": "Decide, then check what you decided.",
            "loop": "careful",
            "limits": {"steps-at-most": 8, "when-it-runs-out": "stop-and-say-so"},
        }
    },
}


def _loop() -> Loop:
    return Loop.from_mapping("careful", DECIDES["loops"]["careful"])


# ────────────────────────────────────────────────────────── it decides, in range


@pytest.mark.parametrize("chosen", ["reply", "gather", "done"])
def test_the_program_picks_among_the_stops_the_author_declared(chosen: str) -> None:
    loop = _loop()
    where = loop.route(
        loop.steps["check"], "answered",
        run_program=lambda n, a: chosen,
    )
    assert where == chosen


def test_a_destination_outside_may_go_to_is_a_loop_error() -> None:
    """A program picks BETWEEN declared stops and may not invent one.

    Otherwise `may-go-to:` is decoration and a reader cannot tell where the loop
    can go by reading it — which is the whole reason the list is written.
    """
    loop = _loop()
    with pytest.raises(LoopError) as raised:
        loop.route(loop.steps["check"], "answered", run_program=lambda n, a: "somewhere-else")
    said = str(raised.value)
    assert "somewhere-else" in said
    assert "reply" in said and "gather" in said


def test_a_router_with_nothing_to_run_it_is_a_loop_error_and_not_a_guess() -> None:
    """Guessing a destination would be inventing control flow nobody wrote."""
    loop = _loop()
    with pytest.raises(LoopError) as raised:
        loop.route(loop.steps["check"], "answered")
    assert "route-after-check" in str(raised.value)


# ─────────────────────────────────────────────────────── fuel outranks routing


def test_a_spent_ceiling_stops_the_run_whatever_the_router_says() -> None:
    """THE ordering property. A router that always says "keep going" must not
    outlive the step ceiling — otherwise "the router said continue" would mean
    "the money cap did not apply", and every limit in the format would be
    advisory on any loop that uses one."""
    doc = json.loads(json.dumps(DECIDES))
    doc["agents"]["desk"]["limits"]["steps-at-most"] = 3
    spec = AgentSpec.from_document(doc, "desk")
    looping = Script([Turn("still checking", (ToolCall("nothing", {}),))])
    result = asyncio.run(
        run(spec, ReferenceTransport(looping), "refund?", {},
            run_program=lambda n, a: "check")
    )
    assert len(result.steps) == 3, result.trace()
    assert result.stopped_by is not None
    assert result.stopped_by.ceiling.field == "steps-at-most"


# ─────────────────────────────────────────────────────────────── nothing moved


def test_a_stage_with_an_ordinary_then_is_untouched() -> None:
    """Additive inertness: the three-outcome table behaves exactly as before."""
    loop = _loop()
    assert loop.route(loop.steps["gather"], "answered") == "check"
    assert loop.route(loop.steps["gather"], "used-a-tool") == "gather"
    assert loop.route(loop.steps["reply"], "answered") == "done"
