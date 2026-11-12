"""An agent that decides is given what the stage binds for it (`bind:` on a `decide`).

An agent on a `decide`'s rung was handed the workflow's input and the item it
was inside a `for each` of, and that was all there was to hand it: a `decide`
could not write `bind:` (`loader/a-line-this-stage-never-reads`). So an agent
asked to judge what an EARLIER STAGE found — which team takes a defect that
triage has just classified — was given nothing, and a scripted agent answered
all the same. Bud Agent Flow found it in two of its own workspaces, on its
runtime and on this one.

A `decide` now writes `bind:` as a `call` does, and in the language `decide
with kind: triage.kind`. What is held here, in the order `given_to` does it:

* the stage's `bind:` is laid over the item's fields over the workflow's input;
* a name the stage binds is the binding's alone — where the binding reads
  nothing, the agent is given nothing under that name;
* each agent on a rung is still given only what IT accepts;
* the stage's `says:` is the start of the `message`, a bound one included;
* a one-value item goes where the stage binds it, and nothing is reported.

The first three and the last are also shared cases
(`tests/conformance/workflows.json`), so a second runtime is held to them.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters.ir import WorkflowSpec  # noqa: E402
from pact_adapters.workflow_runtime import Callers, run_workflow  # noqa: E402
from trees import shown  # noqa: E402

WORKSPACE = """\
workspace "Second opinions"
  description: A claim is read, and then two agents in turn say where it goes.

agent reader
  description: Reads a claim.
  takes claim: text
  gives amount: number, gist: text, optional
  instructions: Read the claim.

agent quick
  description: Sorts the easy ones, by the amount alone.
  takes amount: number
  gives lane: one of fast, slow, not-sure
  instructions: Say which lane, or that you are not sure.

agent careful
  description: Sorts the rest, reading what the claim says.
  takes message: text, amount: number, gist: text, optional
  gives lane: one of fast, slow
  instructions: Say which lane.

workflow place
  description: Read one claim and say which lane it goes in.
  takes claim: text, amount: number, gist: text
  read = call reader with claim: input.claim
  where = decide with amount: read.amount, gist: read.gist, message: input.claim
    says: Say which lane this claim goes in.
    by:
      - { agent: quick }
      - { agent: careful }
    if fast: done
    if slow: done
"""


def place(tmp_path: Path, read: dict[str, Any], quick: str = "not-sure"):
    (tmp_path / "second-opinions.pact").write_text(WORKSPACE, encoding="utf-8")
    doc = shown(tmp_path)
    asked: list[tuple[str, dict[str, Any]]] = []

    def agent(name: str, inputs: dict[str, Any]) -> dict[str, Any]:
        asked.append((name, dict(inputs)))
        return {"reader": read, "quick": {"lane": quick}, "careful": {"lane": "slow"}}[name]

    spec = WorkflowSpec.from_workflow(doc, "place")
    inputs = {"claim": "Water damage, kitchen.", "amount": 1, "gist": "what the claimant wrote"}
    out = asyncio.run(run_workflow(spec, inputs, Callers(agent=agent), document=doc))
    assert out.halted == "final", out.said
    return out, dict(asked[1:])


def test_what_an_earlier_stage_found_is_what_each_agent_is_given_and_only_what_it_accepts(
    tmp_path: Path,
) -> None:
    out, given = place(tmp_path, {"amount": 900, "gist": "A burst pipe."})
    # `amount: read.amount` — the reader's 900, not the 1 the input came with.
    assert given["quick"] == {"amount": 900}
    # The second rung is asked about the same thing, and accepts more of it.
    assert given["careful"]["amount"] == 900
    assert given["careful"]["gist"] == "A burst pipe."
    # Neither is given the claim's own words under a name it did not accept.
    assert "claim" not in given["quick"] and "claim" not in given["careful"]


def test_the_stages_says_goes_in_front_of_a_message_the_stage_binds(tmp_path: Path) -> None:
    _, given = place(tmp_path, {"amount": 900, "gist": "A burst pipe."})
    assert given["careful"]["message"] == (
        "Say which lane this claim goes in.\n\nWater damage, kitchen."
    )
    # `quick` accepts no `message`, so the stage's instruction could not reach
    # it — said once, by name, and not passed off as done.
    out, _ = place(tmp_path, {"amount": 900})
    assert [u for u in out.unenforced if "'quick' accepts no `message`" in u], out.unenforced


def test_a_name_the_stage_binds_is_never_filled_from_the_input_instead(tmp_path: Path) -> None:
    # The reader gave no `gist`. The workflow's input has one, written by the
    # claimant; the stage said `gist` comes from the reader, so it is not given.
    _, given = place(tmp_path, {"amount": 900})
    assert "gist" not in given["careful"]
    assert given["careful"]["amount"] == 900


def test_the_first_agent_that_is_sure_decides_and_the_next_is_not_asked(tmp_path: Path) -> None:
    out, given = place(tmp_path, {"amount": 5}, quick="fast")
    assert list(given) == ["quick"]
    assert out.steps["where"] == {"label": "fast", "by": "quick"}
