"""CodeAct: a stage where the model writes the code and the room runs it (P8/8).

`docs/30-FRD.md` FR-6.1.5 requires six loop patterns and names CodeAct among
them; AC-5.2 repeats it. It has never been shippable, for a reason that was
correct: there was nowhere to run anything. R16 separately refuses *orchestration
code the model writes while it runs* — Eve's fan-out tool — because it "cannot be
reviewed before it runs, cannot be diffed, cannot be signed, and is not the same
twice", and D22/D23 require structural change to pass a person first.

**This is not that, and the difference is authority.** R16's subject is code that
decides TOPOLOGY: which agents exist, who is asked, what the shape of the run is.
A CodeAct snippet has none of that. It is an ACTION inside one step — the same
standing as a tool call the model asked for — and it:

  * runs in the locked room, under the sandbox's deny-by-default egress and the
    stage's own fuel, so it can reach nothing the author did not grant;
  * has no structural authority whatsoever: it cannot add an agent, edit the
    tree, change a limit, or reach a teammate;
  * lands in the transcript verbatim, so what it did is reviewable AFTER the
    fact exactly as every other model output is — which is the standard the
    model's own prose already meets, not a lower one.

The line R16 draws is `meta-depth = 1` (AD-83): no run-created thing holds
topology-authoring authority. A snippet that computes a number holds none.

It is expert tier and excluded from the `no-code` badge, and it requires a
sandbox at check time — a `does: run-code` stage in a workspace with no locked
room is refused before anything runs, rather than discovered on the first step.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.loops import Does, Loop  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

CODEACT = {
    "resources": {
        "local-sandbox": {
            "resource-kind": "sandbox",
            "description": "The machine-local executor.",
            "engines": ["python"],
        }
    },
    "loops": {
        "works-it-out": {
            "description": "Write the working, run it, then answer.",
            "starts-at": "work",
            "steps": {
                "work": {"does": "run-code", "then": {"answered": "reply"}},
                "reply": {"does": "answer", "then": {"answered": "done"}},
            },
        }
    },
    "agents": {
        "desk": {
            "description": "Works out refund arithmetic.",
            "instructions": "Write the working out as code, then give the answer.",
            "loop": "works-it-out",
            "limits": {"steps-at-most": 4, "when-it-runs-out": "stop-and-say-so"},
        }
    },
}


def _script() -> Script:
    return Script([
        Turn("total = 40.00 + 5.00\nprint(total)"),
        Turn("The refund is 45.00 USD."),
    ])


def _run(**kw):
    return asyncio.run(
        run(AgentSpec.from_document(CODEACT, "desk"), ReferenceTransport(_script()),
            "how much do we refund?", {}, **kw)
    )


# ──────────────────────────────────────────────────────────── the stage exists


def test_run_code_is_a_stage_kind() -> None:
    assert Does.RUN_CODE.value == "run-code"
    loop = Loop.from_mapping("works-it-out", CODEACT["loops"]["works-it-out"])
    assert loop.steps["work"].does is Does.RUN_CODE


def test_what_the_model_wrote_is_run_and_the_answer_comes_back() -> None:
    """The snippet goes to the locked room and its output is the step's result."""
    seen: list[str] = []

    def sandbox(name: str, args: dict) -> str:
        seen.append(args["code"])
        return "45.0"

    result = _run(run_program=sandbox)
    assert seen and "40.00 + 5.00" in seen[0]
    assert result.steps[0].tool_results == ("45.0",)


def test_the_snippet_is_in_the_transcript_verbatim() -> None:
    """Reviewable after the fact, exactly as the model's prose already is.

    R16's objection to model-written code is that it cannot be reviewed, diffed
    or signed. That is true of code which decides TOPOLOGY and unwritten
    anywhere; a snippet that lands in the transcript is as readable as the
    sentence beside it.
    """
    result = _run(run_program=lambda n, a: "45.0")
    assert "40.00 + 5.00" in json.dumps(result.trace())


# ───────────────────────────────────────────────── it holds no other authority


def test_a_snippet_reaches_no_tool_and_no_teammate() -> None:
    """The whole safety argument in one assertion.

    A CodeAct stage offers the model NOTHING but the room — no tools, no
    teammates — so a snippet cannot call a gated action, spend money, or ask an
    agent. It computes and answers.
    """
    offered: list[list[str]] = []

    class Watching(ReferenceTransport):
        async def model_call(self, system, history, tools):
            offered.append([t["name"] for t in tools])
            return await super().model_call(system, history, tools)

    asyncio.run(
        run(AgentSpec.from_document(CODEACT, "desk"), Watching(_script()),
            "how much?", {}, run_program=lambda n, a: "45.0")
    )
    assert offered[0] == [], f"a run-code stage offers nothing else: {offered[0]}"


# ────────────────────────────────────────────────────────── the honest absence


def test_a_run_code_stage_with_no_room_says_so() -> None:
    """Refused rather than quietly turning into a `think` stage."""
    result = _run()
    said = " ".join(result.unenforced) + str(result.output)
    assert "run-code" in said or "locked room" in said
