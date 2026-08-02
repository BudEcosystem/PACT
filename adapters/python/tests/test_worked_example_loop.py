"""The worked example's own shape of thinking, *executed* (G1).

`examples/refund-desk/loops/careful.yaml` argues at length for a stage that
re-reads a refund decision against the policy before the customer sees it, and
for that stage not being able to reach the payment system. Until now that
argument was only ever checked against the *file*:
`crates/pact-loader/tests/worked_example_loop.rs` reads the document and asserts
things about the YAML, and `tests/test_portability.py` deliberately swaps
`Loop.from_library(STANDARD)` in for the example's own choice (see its comment
at lines 73-79 — that module asks whether seven transports agree on ONE loop, so
letting the example's choice leak in would make an edit to it look like a
transport divergence).

So the example's central safety claim — *the stage whose whole purpose is doubt
must not be the stage that can spend the money* — was a property of a document
and never a property of a run. A `may-use:` line that loads, validates, and is
then ignored by the harness would satisfy every check that existed. This module
is the other half: the same folder, loaded by the same Rust loader, driven
through the reference harness, with what actually reached the model recorded per
stage.

Eve cannot express the comparison at all. Its tool set is resolved once per run,
so there is no such thing there as a step that sees fewer tools — a checking
step reads the same tool list, and the same system prompt, as the step that
issues the refund.

Nothing here is written as a literal it can derive from the loaded document. The
stage that checks is found by `does: check-its-work`, the tool that spends money
by `spends-money:` on one of its actions, and the order of stages by walking the
document's own `then:` lines. An edit to the example changes what these expect,
so it fails loudly rather than passing against a stale copy.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import RunResult, ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.loops import DONE, Does, Loop  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"

#: The agent whose `loop:` line points at `careful`. Named once, here, because
#: everything below asks the document which stages that shape has.
AGENT = "refund-desk"


# ─────────────────────────────────────────────────────────────────── fixtures


@pytest.fixture(scope="session")
def document() -> dict[str, Any]:
    """The example tree, loaded by the real Rust loader.

    The same door `test_portability.py` uses, for the same reason: a Python
    re-implementation of the Expansion Rule would be a second loader, and the
    two would drift (invariant P-1 — adapters consume the loaded document only).
    """
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(PACT_BIN), "show", str(EXAMPLE)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


@pytest.fixture(scope="session")
def spec(document: dict[str, Any]) -> AgentSpec:
    """The refund desk, carrying the shape of thinking its own file names.

    No `replace(..., loop=...)` here — that substitution is exactly what
    `test_portability.py` does and exactly what leaves this untested. `from_document`
    already calls `Loop.resolve` (ir.py:107), so the example's `loop: careful`
    arrives without any wiring of ours.
    """
    return AgentSpec.from_document(document, AGENT)


class Watching(ReferenceTransport):
    """Records what each stage actually put in front of the model.

    `may-use:` is a claim about what the model can see and `says:` is a claim
    about what it was told, so the only honest way to check either is to look at
    what arrived. The idiom is borrowed from `test_loops.py:87-105`, where it
    does the same job for hand-written loop documents; here it is pointed at the
    one loop an author wrote.

    Note the items in `tools` are plain dicts, not `ToolSpec` — this is the
    model-facing tool list the harness builds, after the stage has narrowed it.
    """

    name = "watching"

    def __init__(self, script: Script) -> None:
        super().__init__(script)
        self.offered: list[list[str]] = []
        self.told: list[str] = []

    async def model_call(self, system, history, tools):
        self.offered.append([t["name"] for t in tools])
        self.told.append(system)
        return await super().model_call(system, history, tools)


def a_refund_worth_checking() -> Script:
    """Look the ticket up, then three plain answers.

    One per remaining stage: the second `gather` turn that ends the looking-up,
    the `re-read` turn that checks the decision, and the `reply` turn the
    customer sees. Scripted rather than sampled, because the point under test is
    which stage was handed what — a live model would measure sampling noise
    instead (see `script.py`, and D17: this runs air-gapped).
    """
    return Script([
        Turn("Checking the ticket.", (ToolCall("zendesk", {"ticket": "T-1"}),)),
        Turn("The ticket says the lamp arrived broken 6 days ago."),
        Turn("Rule 2 applies: faulty on arrival, and 6 days is inside the window."),
        Turn("Approved: the item arrived damaged within 30 days."),
    ])


#: Answered locally for the same reason the script is: the claim is about which
#: stage may reach `payments`, not about what `payments` says back.
TOOLS = {
    "zendesk": lambda a: f"ticket {a.get('ticket')}: lamp, 6 days ago, broken",
    "payments": lambda a: "refunded",
}


def executed(spec: AgentSpec) -> tuple[RunResult, Watching]:
    """One run of the worked example, and the record of what reached the model."""
    seen = Watching(a_refund_worth_checking())
    return asyncio.run(run(spec, seen, "Can I get a refund?", TOOLS)), seen


# ───────────────────────────────────────────── reading the example, not us


def shape(document: dict[str, Any]) -> dict[str, Any]:
    """The loop document the agent's own `loop:` line names.

    Read from the raw loaded tree rather than from `spec.loop`, so the
    expectations below come from the YAML an author edits and not from the
    object the harness executes. Two copies of one fact that must agree is the
    only way this catches a harness that ignores the file.
    """
    named = document["agents"][AGENT].get("loop")
    assert named, (
        f"agent {AGENT!r} names no loop, so this module has nothing to run. "
        f"fix: restore `loop: careful` in "
        f"examples/refund-desk/agents/{AGENT}/agent.yaml, or delete this module"
    )
    loops = document.get("loops") or {}
    assert named in loops, (
        f"agent {AGENT!r} thinks in a shape called {named!r}, which is not one this "
        f"workspace writes down. It declares: {sorted(loops)}. Every guarantee in this "
        f"module is about the example's OWN shape, so a shape PACT ships is not a "
        f"substitute — `test_loops.py` holds those. fix: restore `loop: careful` in "
        f"examples/refund-desk/agents/{AGENT}/agent.yaml"
    )
    return loops[named]


def the_one_stage_that(document: dict[str, Any], does: Does) -> str:
    """The single stage of the example's loop with this kind of body.

    Named by what it does rather than by what it is called, the way
    `worked_example_loop.rs::the_stage_that_checks_a_refund_cannot_be_the_stage_that_issues_one`
    is — so renaming `re-read` to something else does not quietly retire the
    guarantee.
    """
    steps = shape(document)["steps"]
    found = [n for n, s in steps.items() if s.get("does") == does.value]
    assert len(found) == 1, (
        f"expected exactly one `does: {does.value}` stage in the example's loop and "
        f"found {found}. The guarantees below are about that one stage; with two of "
        f"them, this test no longer says which"
    )
    return found[0]


def the_tool_that_spends_money(document: dict[str, Any]) -> str:
    """The tool the example marks as able to move money.

    Derived from `spends-money:` in `tools/`, not written down here as
    `payments`. The safety claim is "whatever spends money is out of reach of
    whatever checks", so the thing that spends money has to be looked up.
    """
    spenders = [
        name
        for name, tool in (document.get("tools") or {}).items()
        if any(
            str(action.get("spends-money", "")).lower() in {"yes", "true"}
            for action in (tool.get("actions") or {}).values()
        )
    ]
    assert len(spenders) == 1, (
        f"expected exactly one tool marked `spends-money: yes` and found {spenders}. "
        f"Every one of them has to be kept out of the checking stage, so add the "
        f"others to this check rather than leaving them unasserted"
    )
    return spenders[0]


def everything_the_agent_has(document: dict[str, Any]) -> set[str]:
    """What a stage that narrows nothing is handed.

    The agent's `uses:` filtered to entries that are actually tools, plus its
    teammates. The filter is the trap `worked_example_loop.rs:143-154` names:
    `uses:` also carries SKILLS, and `refund-policy` reads exactly like
    something a stage could be offered but never reaches the tool set.
    """
    agent = document["agents"][AGENT]
    tools = document.get("tools") or {}
    uses = agent.get("uses") or []
    return {u for u in uses if u in tools} | set(agent.get("team") or {})


def routed_path(document: dict[str, Any], outcomes: list[str]) -> list[str]:
    """Where the document sends a run that ends its stages this way.

    An independent walk of the example's own `then:` lines, so that comparing it
    with `result.phases` compares the file against the harness rather than the
    harness against itself. Deliberately tiny: it knows nothing about tools,
    ceilings or the model, only about arrows.
    """
    step = shape(document)
    at, path = step["starts-at"], []
    for outcome in outcomes:
        path.append(at)
        nxt = (step["steps"][at].get("then") or {}).get(outcome)
        assert nxt is not None, (
            f"stage {at!r} of the example's loop ended with {outcome!r} and says "
            f"nothing about where to go. fix: add `{outcome}: done` under its `then:`"
        )
        if nxt == DONE:
            break
        at = nxt
    return path


def how_each_step_ended(result: RunResult) -> list[str]:
    """The outcome of each step, read off the run rather than assumed.

    Two of the three outcomes in the closed vocabulary are visible from a step
    alone; `too-many-times` is a routing decision and never appears as a step,
    which is why a stage ceiling sends a run onward rather than ending it.
    """
    return ["used-a-tool" if s.tool_calls else "answered" for s in result.steps]


# ────────────────────────────────── the shape the example names is the one it runs


def test_the_shape_the_worked_example_names_is_the_shape_the_run_executes(
    document: dict[str, Any], spec: AgentSpec
) -> None:
    """Everything below rests on this, and nothing else asserts it in Python.

    `test_portability.py` substitutes the standard shape on purpose, so if
    `from_document` silently fell back to `pact:loop/standard` the whole Python
    suite would still be green and the example's `loop: careful` line would be
    decoration.
    """
    assert spec.loop.name == document["agents"][AGENT]["loop"]
    assert spec.loop.starts_at == shape(document)["starts-at"]
    assert sorted(spec.loop.steps) == sorted(shape(document)["steps"]), (
        "the stages the harness will run are not the stages the file describes"
    )


# ─────────────────────────── the runtime twin of the example's safety claim


def test_the_stage_that_checks_a_refund_is_never_handed_the_tool_that_issues_one(
    document: dict[str, Any], spec: AgentSpec
) -> None:
    """The runtime twin of
    `worked_example_loop.rs::the_stage_that_checks_a_refund_cannot_be_the_stage_that_issues_one`.

    That test reads the `may-use:` list in the file. This one reads the tool
    list that reached the model. They are different claims: a harness that
    loaded `may-use:` and then offered every tool anyway would pass the first
    and fail this one, and the file would still look right in review.

    Stated as "whatever checks is not handed whatever spends" rather than
    "`re-read` may not use `payments`", for the same reason the Rust test is —
    renaming the stage or the tool must not retire the guarantee.
    """
    checking = the_one_stage_that(document, Does.CHECK)
    spends = the_tool_that_spends_money(document)
    result, seen = executed(spec)

    assert len(seen.offered) == len(result.phases), (
        "every stage of this loop spends a model call, so the two records line up "
        "step for step. If a stage is added that does not call the model (a "
        "`does: ask-someone` stage), pair them by index instead"
    )
    by_stage = list(zip(result.phases, seen.offered))
    checks = [tools for stage, tools in by_stage if stage == checking]
    assert checks, f"the run never entered the {checking!r} stage; there is nothing to check"
    for tools in checks:
        assert spends not in tools, (
            f"the {checking!r} stage was handed {spends!r}. It exists to doubt a refund "
            f"decision and it can now issue one while it doubts. It was offered: {tools}. "
            f"fix: remove `{spends}` from `may-use:` under the {checking!r} stage in "
            f"examples/refund-desk/loops/careful.yaml"
        )

    # The other half, and the half that makes the first one mean something: the
    # tool is withheld from one stage, not missing from the agent. Without this,
    # deleting `payments` from `uses:` altogether would pass the assertion above.
    working = [
        (stage, tools) for stage, tools in by_stage
        if shape(document)["steps"][stage].get("does") == Does.USE_TOOLS.value
    ]
    assert working, "the loop has no working stage, so `payments` is reachable nowhere"
    for stage, tools in working:
        assert spends in tools, (
            f"the {stage!r} stage was not handed {spends!r}, so the run cannot issue a "
            f"refund at all and the narrowing on {checking!r} proves nothing. "
            f"It was offered: {tools}"
        )


def test_a_stage_that_narrows_nothing_is_handed_everything_the_agent_has(
    document: dict[str, Any], spec: AgentSpec
) -> None:
    """What `gather` gets, spelled out rather than assumed.

    The example's comment on that stage says "this stage names no tools, so it
    gets everything the agent has". Both halves matter: the teammates are in
    that list too, so a run can ask policy-checker and fraud-checker from there
    and only from there. Derived from the agent's `uses:` and `team:`, so adding
    a tool to the example changes what this expects.
    """
    result, seen = executed(spec)
    expected = everything_the_agent_has(document)
    steps = shape(document)["steps"]
    checked = 0
    for stage, tools in zip(result.phases, seen.offered):
        if steps[stage].get("may-use") is not None:
            continue
        if steps[stage].get("does") != Does.USE_TOOLS.value:
            continue
        checked += 1
        assert set(tools) == expected, (
            f"the {stage!r} stage names no tools, so it should be handed everything "
            f"the agent has: {sorted(expected)}. It was handed: {sorted(tools)}"
        )
    assert checked, (
        "no stage of the example's loop both works with tools and narrows nothing, so "
        "this test asserted nothing at all. fix: assert the narrowed lists instead, or "
        "delete this test — a green test that looked at no run is worse than neither"
    )


def test_the_stage_that_talks_to_the_customer_is_offered_no_tools_at_all(
    document: dict[str, Any], spec: AgentSpec
) -> None:
    """The asymmetry that makes an `answer` stage answer.

    Only `use-tools` offers everything when it names nothing (loops.py:82-86);
    every other kind offers nothing. So the stage the customer reads cannot
    reach for one more lookup, one more teammate, or the payment system on its
    way out — which is what the example means by keeping the reply separate from
    the check.
    """
    answering = the_one_stage_that(document, Does.ANSWER)
    result, seen = executed(spec)
    replies = [
        tools for stage, tools in zip(result.phases, seen.offered) if stage == answering
    ]
    assert replies, f"the run never reached the {answering!r} stage"
    for tools in replies:
        assert tools == [], (
            f"the {answering!r} stage writes what the customer reads and was handed "
            f"{tools}. A `does: answer` stage is offered nothing unless it names "
            f"something, so this is a `may-use:` line on that stage — remove it"
        )


# ──────────────────────────────── the wording on a stage is that stage's alone


def test_the_wording_written_on_the_checking_stage_reaches_that_stage_and_no_other(
    document: dict[str, Any], spec: AgentSpec
) -> None:
    """`says:` is per stage, and the agent's own instructions stay first.

    Eve resolves one system prompt for the whole run, which is why a checking
    step there reads exactly the same words as an answering one — there is no
    way to tell a model to doubt itself for one step. Here the sentence the
    author wrote on `re-read` is a claim about one stage, so it is worth
    nothing unless the other stages are shown not to carry it.
    """
    checking = the_one_stage_that(document, Does.CHECK)
    written = (shape(document)["steps"][checking].get("says") or "").strip()
    assert written, (
        f"the {checking!r} stage of examples/refund-desk/loops/careful.yaml has no "
        f"`says:` line, so this test would pass by finding nothing anywhere. Either "
        f"restore the wording or delete this test"
    )
    # The document keeps the folded block's line breaks; the prompt is one run of
    # text, so compare on the words rather than on the whitespace between them.
    words = " ".join(written.split())

    result, seen = executed(spec)
    for stage, system in zip(result.phases, seen.told):
        said = " ".join(system.split())
        assert said.startswith(" ".join(spec.instructions.split())), (
            f"the {stage!r} stage replaced the agent's own instructions instead of "
            f"adding to them"
        )
        if stage == checking:
            assert words in said, (
                f"the {checking!r} stage did not receive the wording written on it in "
                f"examples/refund-desk/loops/careful.yaml. It was told: {system!r}"
            )
        else:
            assert words not in said, (
                f"the {stage!r} stage was told to check the decision against the refund "
                f"policy, which is wording written on the {checking!r} stage only. A "
                f"`says:` line that leaks is one every stage is paying tokens for"
            )


# ─────────────────────────────────── the run goes where the document sends it


def test_the_run_visits_the_stages_in_the_order_the_document_routes_them(
    document: dict[str, Any], spec: AgentSpec
) -> None:
    """The path, walked twice: once by the harness, once by reading the arrows.

    `routed_path` follows the example's own `then:` lines and knows nothing else,
    so this compares the file with the run rather than the run with itself. Get
    the routing wrong — point `gather` straight at `reply`, or send `answered`
    back where it came from — and the two disagree here rather than in front of
    a customer.
    """
    result, _ = executed(spec)
    assert result.phases == routed_path(document, how_each_step_ended(result)), (
        f"the run took {result.phases}, and the arrows in "
        f"examples/refund-desk/loops/careful.yaml route it to "
        f"{routed_path(document, how_each_step_ended(result))}"
    )
    assert result.halted == "final", (
        f"the worked example did not finish; it stopped with {result.halted!r}"
    )
    assert set(result.phases) == set(shape(document)["steps"]), (
        f"the example ships stages nothing reaches: "
        f"{sorted(set(shape(document)['steps']) - set(result.phases))}. A stage no run "
        f"enters is a document, not a decision"
    )


def test_the_reply_the_customer_reads_is_written_after_the_check_and_not_with_it(
    document: dict[str, Any], spec: AgentSpec
) -> None:
    """Why `careful` costs two extra model turns, held as a fact about the run.

    The file argues that a decision and its reason written in the same breath as
    the last lookup are the two ways a refund desk gets it wrong. That argument
    is only paid for if the check really is a separate turn from the reply — so
    the words the customer receives must not be the words the check produced.
    """
    checking = the_one_stage_that(document, Does.CHECK)
    answering = the_one_stage_that(document, Does.ANSWER)
    result, _ = executed(spec)
    said = dict(zip(result.phases, (s.text for s in result.steps)))
    for stage in (checking, answering):
        assert stage in result.phases, (
            f"the run never entered the {stage!r} stage, so there is no separate turn "
            f"to compare. The run took: {result.phases}. fix: check the `then:` lines "
            f"in examples/refund-desk/loops/careful.yaml still route through it"
        )
    assert result.phases.index(checking) < result.phases.index(answering), (
        f"the customer was answered before the decision was read back: {result.phases}"
    )
    assert result.output == said[answering], (
        f"the run returned the {checking!r} stage's critique rather than the "
        f"{answering!r} stage's reply"
    )
    assert result.output != said[checking]


# ────────────────────────────── the file and the library are not the same door


def test_the_example_s_own_loop_is_read_through_the_door_a_shipped_shape_uses(
    document: dict[str, Any], spec: AgentSpec
) -> None:
    """A loop written by an author must be no more and no less privileged than
    one PACT ships.

    This is the objection to Eve's compiled manifest, stated as a test: if the
    example's file needed a different code path from `spec/loops/*.yaml`, then
    forking a shipped shape would not be an edit, it would be a request. Both go
    through `Loop.from_mapping`, so both are refused the same way and both run
    the same way.
    """
    again = Loop.from_mapping(document["agents"][AGENT]["loop"], shape(document))
    assert again.steps == spec.loop.steps
    assert again.starts_at == spec.loop.starts_at
    # And it is checked against the agent's tools before the first model call,
    # the same as any other loop — a `may-use:` typo in the example would fail at
    # the start of the run rather than on the branch that takes it.
    again.check_against(
        tuple(t.name for t in spec.tools) + tuple(spec.team),
        skill_names=spec.skill_names,
    )
