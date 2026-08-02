"""The loop as a document (G1): the shape of the thinking, in a file you can edit.

Every framework has a loop and almost none of them let you see it. Eve is the
honest extreme — `stopWhen: isStepCount(1)` is the only stop condition in
171,782 lines and whether to go round again is one hardcoded boolean — so you
can change an Eve agent's tools and its wording but never the shape of its
thinking, because the shape is not written down anywhere an author can reach.

`loops.py` makes a two-sided claim about itself (module docstring, lines 15-19)
and nothing checked either half. Both are below:

* **the regression half** — running `pact:loop/standard` must produce exactly
  what the harness produced before loops existed. A mechanism that changes
  behaviour when you have not asked for it is not a mechanism.
* **the not-decoration half** — changing nothing but the loop document must
  change a *measured* outcome. A mechanism that changes nothing when you do ask
  is decoration.

Then: that the two copies of the shipped shapes have not drifted, that every
mistake a loop document can contain is named with a line to type, and the
behaviours that exist only because the loop is data.

Each test is named as the guarantee it holds.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.events import Bus  # noqa: E402
from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec, ToolSpec  # noqa: E402
from pact_adapters.loops import (  # noqa: F401
    ANSWER_MORE_THAN_ONCE, DONE, REACT, REFLEXION, TREE_OF_THOUGHT,  # noqa: E402
    LIBRARY,
    OUTCOMES,
    PLAN_THEN_DO,
    STANDARD,
    Does,
    Loop,
    LoopError,
)
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.questions import questions_for  # noqa: E402
from pact_adapters.suspension import Resumption, WrongAnswer  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

#: The shapes the specification ships. `loops.LIBRARY` is a second copy of these
#: — see `test_the_two_copies_of_a_shipped_shape_have_not_drifted`.
SHIPPED = REPO / "spec" / "loops"


# ─────────────────────────────────────────────────────────────────── fixtures


SPEC = AgentSpec(
    name="Refund Desk",
    description="Decides refunds",
    instructions="Decide, then issue the refund.",
    tools=(ToolSpec("zendesk", "read the ticket"), ToolSpec("payments", "issue a refund")),
    max_steps=10,
)
TOOLS = {"zendesk": lambda a: "lamp, broken", "payments": lambda a: "refunded"}


def looks_then_answers() -> Script:
    """One tool call, then an answer — the ordinary shape of a finished job."""
    return Script([Turn("checking", (ToolCall("zendesk", {}),)), Turn("Approved.")])


def never_finishes() -> Script:
    """A model that keeps calling a tool, so a stage ceiling has something to
    bite on."""
    return Script([Turn("still working", (ToolCall("zendesk", {}),))])


class Watching(ReferenceTransport):
    """Records what each stage actually put in front of the model.

    `may-use:` is a claim about what the model can see and `says:` is a claim
    about what it was told, so the only honest way to check either is to look at
    what arrived. Without this the tests could only compare labels.
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


class Cornered(ReferenceTransport):
    """Calls a tool while it has one, and answers when it has none.

    This is what withholding tools actually does to a model, and it is what
    makes a stage that offers nothing a real behaviour rather than a relabelled
    one. Borrowed from `test_termination.py`, where it does the same job for
    `answer-with-what-it-has`.
    """

    name = "cornered"

    async def model_call(self, system, history, tools):
        if not tools:
            return "Best I can say from the ticket: the lamp arrived broken.", []
        return "still working", [ToolCall("zendesk", {})]


def written(doc: dict[str, Any], name: str = "careful") -> Loop:
    """A loop document, as an author would write `loops/careful.yaml`."""
    return Loop.from_mapping(name, doc)


def refused(doc: Any, name: str = "careful") -> str:
    """What an author is told about a loop document that cannot run."""
    with pytest.raises(LoopError) as caught:
        Loop.from_mapping(name, doc)
    return str(caught.value)


def on_disk(filename: str) -> Loop:
    """A shipped shape, read from the specification through the same door an
    author's own file goes through (`from_mapping` is the only path in)."""
    return Loop.from_mapping(filename, yaml.safe_load((SHIPPED / filename).read_text()))


# ───────────────────────────────────── the regression half: standard is the past


def test_naming_the_standard_shape_runs_exactly_what_naming_nothing_runs() -> None:
    """The half that keeps "the loop is data" from being a behaviour change
    dressed up as a feature. `AgentSpec.loop` already defaults to
    `pact:loop/standard`, so these two agents differ by one line of YAML that
    says out loud what was already true — and the traces must not notice.
    """
    silent = asyncio.run(
        run(SPEC, ReferenceTransport(looks_then_answers()), "refund?", TOOLS)
    )
    named = asyncio.run(
        run(
            replace(SPEC, loop=Loop.from_library(STANDARD)),
            ReferenceTransport(looks_then_answers()),
            "refund?",
            TOOLS,
        )
    )
    assert silent.trace() == named.trace()
    assert (silent.halted, silent.output) == (named.halted, named.output)
    assert silent.phases == named.phases == ["work", "work"]


def test_handing_the_standard_shape_to_the_run_is_the_same_as_the_agent_carrying_it() -> None:
    """Two doors into the same shape: `spec.loop` and the `loop=` argument. A
    difference between them would mean the document an agent carries and the
    document a caller passes are not the same kind of thing."""
    carried = asyncio.run(
        run(
            replace(SPEC, loop=Loop.from_library(STANDARD)),
            ReferenceTransport(looks_then_answers()), "refund?", TOOLS,
        )
    )
    passed = asyncio.run(
        run(SPEC, ReferenceTransport(looks_then_answers()), "refund?", TOOLS,
            loop=Loop.from_library(STANDARD))
    )
    assert carried.trace() == passed.trace()
    assert carried.phases == passed.phases


def test_the_standard_shape_adds_no_wording_and_withholds_no_tool() -> None:
    """*Why* the sameness above holds, rather than it being a coincidence of one
    script. `use-tools` is the one kind of stage that offers everything when it
    names nothing, and its built-in wording is the empty string — so the system
    text the model sees is the agent's own instructions, unchanged.
    """
    t = Watching(looks_then_answers())
    asyncio.run(run(SPEC, t, "refund?", TOOLS, loop=Loop.from_library(STANDARD)))
    assert t.offered == [["zendesk", "payments"], ["zendesk", "payments"]]
    assert set(t.told) == {SPEC.instructions}, "the stage added words to the prompt"


def test_the_stage_path_is_recorded_but_never_reaches_the_cross_runtime_trace() -> None:
    """`phases` is how you see the document did something; `trace()` is what
    seven transports and a second language are held to byte-for-byte. A field
    only one of them can produce would quietly weaken that contract, so the two
    are deliberately separate (harness.py:81-86)."""
    r = asyncio.run(
        run(SPEC, ReferenceTransport(looks_then_answers()), "refund?", TOOLS,
            loop=Loop.from_library(PLAN_THEN_DO))
    )
    assert r.phases == ["plan", "do"]
    assert all(sorted(step) == ["index", "results", "text", "tools"] for step in r.trace())


# ───────────────────────────── the not-decoration half: one document, measured


def test_changing_only_the_loop_document_changes_what_the_run_actually_did() -> None:
    """The plan's explicit G1 bar, and the reason this item comes first.

    One `AgentSpec`, one transport class, one scripted set of replies. The only
    thing that differs between the two runs is which document was named, and the
    difference has to show up in something measured rather than in a label.

    Eve cannot express this comparison at all: its tool set is resolved once per
    run, so there is no such thing there as a step that sees fewer tools.
    """
    plain, planning = Watching(looks_then_answers()), Watching(looks_then_answers())
    standard = asyncio.run(
        run(SPEC, plain, "refund?", TOOLS, loop=Loop.from_library(STANDARD))
    )
    plan_then_do = asyncio.run(
        run(SPEC, planning, "refund?", TOOLS, loop=Loop.from_library(PLAN_THEN_DO))
    )

    assert standard.phases == ["work", "work"]
    assert plan_then_do.phases == ["plan", "do"]
    assert standard.trace() != plan_then_do.trace()

    # The measurement, not the label: what each first stage was handed.
    assert planning.offered[0] == [], "the plan stage was handed a tool"
    assert plain.offered[0] == ["zendesk", "payments"]

    # And the tool call the model made in `plan` was refused rather than run —
    # the refusal is in the trace, so no action the model took went unrecorded.
    assert standard.steps[0].tool_results == ("lamp, broken",)
    assert plan_then_do.steps[0].tool_results == (
        "error: 'zendesk' is not available in the 'plan' stage",
    )


def test_a_planning_stage_is_told_something_the_working_stage_is_not() -> None:
    """`says:` is per stage and the agent's own instructions stay first and
    unchanged. Eve resolves one system prompt for the whole run, which is why a
    planning step there reads exactly the same words as an answering one."""
    t = Watching(looks_then_answers())
    asyncio.run(run(SPEC, t, "refund?", TOOLS, loop=Loop.from_library(PLAN_THEN_DO)))
    assert t.told[0].startswith(SPEC.instructions)
    assert "Do not do any of it yet." in t.told[0]
    assert t.told[1] == SPEC.instructions, "the `do` stage inherited plan's wording"


def test_the_refusal_a_stage_gives_is_not_the_refusal_a_missing_tool_gives() -> None:
    """They call for opposite fixes: a name the agent never had is a typo to
    correct, while one the stage withholds is a `may-use:` line to widen.
    Reporting both alike would send an author editing the loop to add a tool
    that was never spelled right in the first place."""
    lp = written({
        "starts-at": "plan",
        "steps": {"plan": {"does": "think", "then": {"used-a-tool": "done"}}},
    })
    misspelt = Script([Turn("planning", (ToolCall("zendeks", {}),))])
    withheld = Script([Turn("planning", (ToolCall("zendesk", {}),))])

    a = asyncio.run(run(SPEC, ReferenceTransport(misspelt), "refund?", TOOLS, loop=lp))
    b = asyncio.run(run(SPEC, ReferenceTransport(withheld), "refund?", TOOLS, loop=lp))
    assert a.steps[0].tool_results == ("error: no tool named 'zendeks'",)
    assert b.steps[0].tool_results == (
        "error: 'zendesk' is not available in the 'plan' stage",
    )


# ───────────────────────────────────── the two copies of the shipped shapes


@pytest.mark.parametrize(
    "filename,ref",
    # DERIVED from the directory, not a hand-written pair. It was
    # `[("standard.yaml", STANDARD), ("plan-then-do.yaml", PLAN_THEN_DO)]`, and
    # four shapes were added to `spec/loops/` without joining it — so the check
    # that exists to stop the two copies drifting covered a third of them and
    # said nothing. A check whose scope is a list somebody has to remember to
    # extend is the defect this repository keeps producing, one level up.
    sorted((p.name, f"pact:loop/{p.stem}") for p in SHIPPED.glob("*.yaml")),
)
def test_the_two_copies_of_a_shipped_shape_have_not_drifted(filename: str, ref: str) -> None:
    """`loops.LIBRARY` says it mirrors `spec/loops/*.yaml` "byte for byte in
    meaning" and cites a test file (`test_loop_as_data.py`) that has never
    existed on disk. This is that test.

    If it fails, **the two copies have drifted**: `spec/loops/<file>` is the
    specification an author reads and forks, while `LIBRARY` in
    `adapters/python/src/pact_adapters/loops.py` is the copy every adapter
    actually executes. Whichever one changed, the other must be changed to
    match — a shape that documents one thing and runs another is the compiled
    manifest problem PACT exists to avoid.
    """
    here, there = on_disk(filename), Loop.from_library(ref)
    assert here.starts_at == there.starts_at, (
        f"spec/loops/{filename} starts at {here.starts_at!r}; "
        f"loops.LIBRARY[{ref!r}] starts at {there.starts_at!r}"
    )
    assert sorted(here.steps) == sorted(there.steps), (
        f"spec/loops/{filename} has stages {sorted(here.steps)}; "
        f"loops.LIBRARY[{ref!r}] has {sorted(there.steps)}"
    )
    for stage in sorted(there.steps):
        mine, theirs = here.steps[stage], there.steps[stage]
        assert mine == theirs, (
            f"stage {stage!r} differs between the two copies of {ref!r}.\n"
            f"  spec/loops/{filename}: {mine}\n"
            f"  loops.LIBRARY:          {theirs}"
        )
    assert here.description == there.description, (
        f"the sentence describing {ref!r} differs between the two copies.\n"
        f"  spec/loops/{filename}: {here.description!r}\n"
        f"  loops.LIBRARY:          {there.description!r}"
    )


def test_every_shape_the_specification_ships_is_one_an_adapter_can_run() -> None:
    """A third file added to `spec/loops/` and not to `LIBRARY` would be a shape
    the specification promises and no adapter can resolve — which reads to an
    author as a typo in their own file."""
    published = {f"pact:loop/{p.stem}" for p in SHIPPED.glob("*.yaml")}
    assert published == set(LIBRARY), (
        f"spec/loops/ ships {sorted(published)}; loops.LIBRARY has {sorted(LIBRARY)}"
    )


def test_a_shipped_shape_is_read_through_the_same_door_an_authors_own_shape_is() -> None:
    """A library shape loaded by privileged code would not be a shape an author
    can fork, which is exactly the objection to Eve's compiled manifest. So the
    document from `spec/loops/` and the one from `LIBRARY` are both built by
    `from_mapping`, and a mistake in either is reported the same way."""
    forked = dict(LIBRARY[PLAN_THEN_DO])
    forked["starts-at"] = "planning"
    said = refused(forked, name="my-copy")
    assert "'my-copy'" in said and "'planning'" in said
    assert "Its stages are: do, plan" in said


# ─────────────────────────────── every mistake is named, with a line to type


def test_a_starts_at_that_names_no_stage_lists_the_stages_there_are() -> None:
    said = refused({
        "starts-at": "planning",
        "steps": {"work": {"does": "use-tools", "then": {"answered": "done"}}},
    })
    assert "loop 'careful'" in said
    assert "'planning'" in said and "no stage called that" in said
    assert "Its stages are: work" in said
    assert "`starts-at:`" in said


def test_a_then_that_points_at_no_stage_says_which_names_would_work() -> None:
    said = refused({
        "starts-at": "work",
        "steps": {"work": {"does": "use-tools", "then": {"used-a-tool": "reviewe"}}},
    })
    assert "stage 'work' of loop 'careful'" in said
    assert "'reviewe'" in said and "which is not a stage" in said
    assert "Its stages are: work" in said and "'done' to finish" in said


def test_a_then_keyed_on_something_a_stage_cannot_end_in_lists_the_three() -> None:
    """The vocabulary is closed on purpose (loops.py:21-27): a predicate
    language here would be the fourth place in this project where an author can
    write a condition, and D13's bar is a support lead editing YAML."""
    said = refused({
        "starts-at": "work",
        "steps": {"work": {"does": "use-tools", "then": {"finished": "done"}}},
    })
    assert "stage 'work' of loop 'careful'" in said
    assert "'finished'" in said and "not something a stage can end in" in said
    for outcome in OUTCOMES:
        assert outcome in said


def test_a_then_written_as_a_list_is_a_diagnostic_and_not_a_type_error() -> None:
    """Three ordinary YAML slips used to reach Python's own type errors:
    `then:` as a list of one-item maps, `steps:` as a list, and `at-most: two`.
    LoopError promises that every message names the loop, the stage, what is
    wrong and a line to type — a promise a raw AttributeError does not keep, and
    one that only bites a host reading the tree natively, which D2 requires to
    be possible and `gaia-ai-runtime` is specified to do."""
    said = refused({
        "starts-at": "work",
        "steps": {"work": {"does": "use-tools", "then": [{"answered": "done"}]}},
    })
    assert "stage 'work' of loop 'careful'" in said
    assert "one line per outcome" in said
    assert "`then:`" in said and "not a list" in said


def test_steps_written_as_a_list_is_a_diagnostic_and_not_a_type_error() -> None:
    said = refused({
        "starts-at": "work",
        "steps": [{"work": {"does": "use-tools", "then": {"answered": "done"}}}],
    })
    assert "loop 'careful'" in said
    assert "one named stage per line" in said
    assert "not a list" in said


def test_an_at_most_that_is_not_a_number_says_what_to_write_instead() -> None:
    said = refused({
        "starts-at": "work",
        "steps": {
            "work": {"does": "use-tools", "then": {"answered": "done"}, "at-most": "two"},
        },
    })
    assert "stage 'work' of loop 'careful'" in said
    assert "'two'" in said and "not a number" in said
    assert "`at-most: 2`" in said


def test_a_stage_named_after_the_finish_line_is_refused() -> None:
    said = refused({
        "starts-at": "work",
        "steps": {
            "work": {"does": "use-tools", "then": {"answered": "done"}},
            "done": {"does": "answer", "then": {}},
        },
    })
    assert "loop 'careful'" in said
    assert "a stage called 'done'" in said and "the finish line" in said
    assert "rename that stage" in said


def test_a_loop_with_no_stages_is_told_the_two_ways_to_get_some() -> None:
    said = refused({"starts-at": "work"})
    assert "loop 'careful' has no stages" in said
    assert "`steps:`" in said
    assert f"`based-on: {STANDARD}`" in said


def test_a_loop_that_does_not_say_which_stage_runs_first_is_offered_one() -> None:
    """The fix names a stage the author already wrote, so it is a line they can
    paste rather than a rule they have to apply."""
    said = refused({
        "steps": {"work": {"does": "use-tools", "then": {"answered": "done"}}},
    })
    assert "loop 'careful' does not say which stage runs first" in said
    assert "`starts-at: work`" in said


def test_a_stage_that_may_run_at_most_zero_times_is_refused_as_meaning_never() -> None:
    said = refused({
        "starts-at": "work",
        "steps": {"work": {"does": "use-tools", "at-most": 0, "then": {}}},
    })
    assert "stage 'work' of loop 'careful'" in said
    assert "at most 0 times, which means never" in said
    assert "`at-most: 1`" in said


def test_a_stage_that_does_something_no_stage_can_do_lists_the_five() -> None:
    said = refused({
        "starts-at": "work",
        "steps": {"work": {"does": "ponder", "then": {}}},
    })
    assert "stage 'work' of loop 'careful'" in said
    assert "'ponder'" in said and "not something a stage can do" in said
    for kind in Does:
        assert kind.value in said


def test_a_may_use_naming_a_tool_the_agent_has_not_got_lists_the_ones_it_has() -> None:
    lp = written({
        "starts-at": "work",
        "steps": {"work": {"does": "use-tools", "may-use": ["stripe"], "then": {}}},
    })
    with pytest.raises(LoopError) as caught:
        lp.check_against(("zendesk", "payments"))
    said = str(caught.value)
    assert "stage 'work' of loop 'careful'" in said
    assert "may use 'stripe', which this agent does not have" in said
    assert "It has: payments, zendesk" in said
    assert "`uses:`" in said and "`may-use:`" in said


def test_an_agent_with_no_tools_at_all_is_told_that_in_words_not_as_an_empty_list() -> None:
    """`It has: ` followed by nothing is a message that reads like a bug."""
    lp = written({
        "starts-at": "work",
        "steps": {"work": {"does": "use-tools", "may-use": ["stripe"], "then": {}}},
    })
    with pytest.raises(LoopError, match="It has: no tools"):
        lp.check_against(())


def test_naming_a_loop_this_workspace_does_not_have_lists_what_it_does_have() -> None:
    with pytest.raises(LoopError) as caught:
        Loop.resolve({"loops": {"careful": {}}}, "carefull")
    said = str(caught.value)
    assert "no loop called 'carefull'" in said
    assert "This workspace declares: careful" in said
    assert f"`loop: {STANDARD}`" in said
    assert "`loops/carefull.yaml`" in said


def test_naming_a_ready_made_shape_pact_does_not_ship_lists_the_ones_it_does() -> None:
    with pytest.raises(LoopError) as caught:
        Loop.from_library("pact:loop/plan-first")
    said = str(caught.value)
    assert "no ready-made shape called 'pact:loop/plan-first'" in said
    assert STANDARD in said and PLAN_THEN_DO in said
    assert "`loops/`" in said


def test_a_based_on_that_names_no_shape_says_which_loop_asked_for_it() -> None:
    """Without the asker, an author with six loop files is told a shape is
    missing and not which of their files wants it."""
    said = refused({"based-on": "pact:loop/plan-first", "steps": {}}, name="careful")
    assert "asked for by loop 'careful'" in said
    assert STANDARD in said


def test_asking_a_loop_for_a_stage_it_has_not_got_offers_both_repairs() -> None:
    """Either the name is wrong or the stage is missing, and the author is the
    only one who knows which — so the message offers both rather than picking."""
    with pytest.raises(LoopError) as caught:
        Loop.from_library(STANDARD).phase("plan")
    said = str(caught.value)
    assert f"loop '{STANDARD}' has no stage called 'plan'" in said
    assert "Its stages are: work" in said
    assert "`plan:` stage under `steps:`" in said


def test_an_outcome_with_nowhere_to_go_names_the_exact_line_to_add() -> None:
    standard = Loop.from_library(STANDARD)
    with pytest.raises(LoopError) as caught:
        standard.route(standard.phase("work"), "too-many-times")
    said = str(caught.value)
    assert f"stage 'work' of loop '{STANDARD}'" in said
    assert "ended with 'too-many-times' and does not say where to go" in said
    assert "`too-many-times: done`" in said


def test_a_loop_that_is_not_a_set_of_settings_is_told_what_shape_to_be() -> None:
    said = refused(["work", "review"])
    assert "loop 'careful' should be a set of settings, not list" in said
    assert "`starts-at:`" in said and "`steps:`" in said


def test_a_stage_that_is_not_a_set_of_settings_is_told_what_shape_to_be() -> None:
    """The commonest YAML slip in this shape: writing `work: use-tools` because
    that is how the rest of the line reads out loud."""
    said = refused({"starts-at": "work", "steps": {"work": "use-tools"}})
    assert "stage 'work' of loop 'careful' should be a set of settings" in said
    assert "`does: use-tools`" in said and "`then:`" in said


# ────────────────────────────────── the behaviours that only a loop has: at-most


def test_a_stage_that_has_used_up_its_at_most_never_spends_another_model_call() -> None:
    """Routed *past* rather than entered and then refused. Entering it would pay
    for a model call to discover a ceiling the author had already written down.
    """
    t = Watching(never_finishes())
    lp = written({
        "starts-at": "work",
        "steps": {
            "work": {"does": "use-tools", "at-most": 2,
                     "then": {"used-a-tool": "work", "answered": "wrap-up"}},
            "wrap-up": {"does": "answer", "then": {"answered": "done"}},
        },
    })
    r = asyncio.run(run(SPEC, t, "refund?", TOOLS, loop=lp))
    assert r.phases == ["work", "work", "wrap-up"], r.phases
    assert len(t.offered) == 3, "a spent stage was entered and paid for"


def test_a_stage_ceiling_sends_the_run_onward_rather_than_stopping_it_dead() -> None:
    """The difference from a step limit. `steps-at-most` ends a run; `at-most`
    on a stage is a routing decision the author gets to make, so the agent still
    produces an answer."""
    lp = written({
        "starts-at": "work",
        "steps": {
            "work": {"does": "use-tools", "at-most": 2,
                     "then": {"used-a-tool": "work", "answered": "wrap-up"}},
            "wrap-up": {"does": "answer", "then": {"answered": "done"}},
        },
    })
    r = asyncio.run(run(SPEC, Cornered(never_finishes()), "refund?", TOOLS, loop=lp))
    assert r.halted == "final"
    assert "lamp arrived broken" in r.output, "it really answered"
    assert r.stopped_by is None, "a stage ceiling is not one of the run's ceilings"


def test_a_stage_that_has_run_its_at_most_times_goes_where_too_many_times_says() -> None:
    """The outcome the author was promised. Routing a spent stage on `answered`
    is not only a different line: it says the model answered when what actually
    happened is that the stage ran out of turns, so an author reading the path
    afterwards is told something untrue."""
    lp = written({
        "starts-at": "work",
        "steps": {
            "work": {"does": "use-tools", "at-most": 2,
                     "then": {"used-a-tool": "work", "too-many-times": "wrap-up"}},
            "wrap-up": {"does": "answer", "then": {"answered": "done"}},
        },
    })
    r = asyncio.run(run(SPEC, Cornered(never_finishes()), "refund?", TOOLS, loop=lp))
    assert r.phases == ["work", "work", "wrap-up"], (
        "`too-many-times:` was written down and the run finished without it"
    )
    assert "lamp arrived broken" in r.output


def test_stages_that_have_all_run_out_and_lead_only_to_each_other_say_which_ring() -> None:
    """The one shape that would otherwise spin forever. Naming the ring is what
    makes it fixable — `raise one of those numbers` is useless without knowing
    which stages are in it."""
    bus = Bus()
    lp = written({
        "starts-at": "look",
        "steps": {
            "look": {"does": "use-tools", "at-most": 1,
                     "then": {"used-a-tool": "look", "answered": "check"}},
            "check": {"does": "check-its-work", "at-most": 1,
                      "then": {"used-a-tool": "check", "answered": "look"}},
        },
    })
    r = asyncio.run(run(SPEC, ReferenceTransport(never_finishes()), "refund?", TOOLS,
                        loop=lp, bus=bus))
    assert r.halted == "stage-limit"
    said = "".join(str(e.payload.get("reason", "")) for e in bus.seen("turn.run.failed"))
    assert "→" in said and "look" in said and "check" in said
    assert "`at-most:`" in said and "`done`" in said


# ─────────────────────── the behaviours that only a loop has: based-on


def test_a_stage_written_locally_replaces_the_inherited_one_outright() -> None:
    """loops.py:204-209 makes this an explicit design choice rather than an
    accident, so it needs a test. Merging field-by-field would mean an author
    who deleted `says:` from their copy still gets the inherited wording — which
    is invisible inheritance, exactly what the Expansion Rule exists to avoid.
    """
    inherited = Loop.from_library(PLAN_THEN_DO)
    assert inherited.steps["plan"].says.startswith("Say what you plan to do")

    mine = written({
        "based-on": PLAN_THEN_DO,
        "steps": {
            "plan": {"does": "use-tools", "then": {"used-a-tool": "do", "answered": "do"}}
        },
    })
    assert mine.steps["plan"].says == "", "the inherited wording survived a rewrite"
    assert mine.steps["plan"].does is Does.USE_TOOLS
    assert mine.steps["plan"].may_use is None


def test_a_stage_the_author_did_not_rewrite_is_inherited_whole() -> None:
    """The other half of the same choice: replacement is per stage, not per
    document, so forking a shape to change one stage costs one stage."""
    mine = written({
        "based-on": PLAN_THEN_DO,
        "steps": {
            "plan": {"does": "use-tools", "then": {"used-a-tool": "do", "answered": "do"}}
        },
    })
    inherited = Loop.from_library(PLAN_THEN_DO)
    assert sorted(mine.steps) == ["do", "plan"]
    assert mine.steps["do"] == inherited.steps["do"]
    assert mine.starts_at == inherited.starts_at == "plan"
    assert mine.description == inherited.description, "the sentence came along too"


def test_a_fork_that_only_adds_a_stage_keeps_every_stage_it_did_not_mention() -> None:
    mine = written({
        "based-on": STANDARD,
        "starts-at": "check",
        "steps": {
            "check": {"does": "check-its-work", "then": {"answered": "work"}},
        },
    })
    assert sorted(mine.steps) == ["check", "work"]
    assert mine.steps["work"] == Loop.from_library(STANDARD).steps["work"]
    assert mine.starts_at == "check", "`starts-at:` overrides the inherited one"


def test_rewriting_the_planning_stage_to_use_tools_makes_the_run_behave_that_way() -> None:
    """Inheritance that changed the document but not the run would be the same
    decoration the not-decoration half rules out, one level down."""
    t = Watching(looks_then_answers())
    mine = written({
        "based-on": PLAN_THEN_DO,
        "steps": {
            "plan": {"does": "use-tools", "then": {"used-a-tool": "do", "answered": "do"}}
        },
    })
    r = asyncio.run(run(SPEC, t, "refund?", TOOLS, loop=mine))
    assert r.phases == ["plan", "do"], "the shape is still plan-then-do"
    assert t.offered[0] == ["zendesk", "payments"], "the rewritten stage still had no tools"
    assert r.steps[0].tool_results == ("lamp, broken",), "the call was refused"


# ─────────────────── the behaviours that only a loop has: unrouted outcomes


def test_a_stage_that_answers_and_says_nothing_about_where_to_go_has_finished() -> None:
    """The one outcome with an unarguable terminal reading: an agent that has
    produced its answer and has no further instruction is done, not broken."""
    lp = written({
        "starts-at": "work",
        "steps": {"work": {"does": "use-tools", "then": {"used-a-tool": "work"}}},
    })
    r = asyncio.run(
        run(SPEC, ReferenceTransport(Script([Turn("Approved.")])), "refund?", TOOLS, loop=lp)
    )
    assert r.halted == "final"
    assert r.output == "Approved."
    assert r.phases == ["work"]


def test_any_other_unrouted_outcome_halts_the_run_and_names_the_line_to_add() -> None:
    """Finishing there too would hide a typo in `then:`, which is the whole
    reason `answered` is the only outcome allowed to end a run by omission."""
    lp = written({
        "starts-at": "work",
        "steps": {"work": {"does": "use-tools", "then": {"answered": "done"}}},
    })
    r = asyncio.run(run(SPEC, ReferenceTransport(never_finishes()), "refund?", TOOLS, loop=lp))
    assert r.halted == "loop-error"
    assert "stage 'work' of loop 'careful'" in r.output
    assert "ended with 'used-a-tool'" in r.output
    assert "`used-a-tool: done`" in r.output


def test_the_steps_taken_before_an_unrouted_outcome_stay_on_the_result() -> None:
    """A run that got eight steps in before meeting a missing `then:` should
    still show those eight — which is why `_where_next` returns rather than
    raising (harness.py:1214-1231)."""
    lp = written({
        "starts-at": "work",
        "steps": {"work": {"does": "use-tools", "then": {"answered": "done"}}},
    })
    r = asyncio.run(run(SPEC, ReferenceTransport(never_finishes()), "refund?", TOOLS, loop=lp))
    assert len(r.steps) == 1 and r.phases == ["work"]
    assert r.steps[0].tool_results == ("lamp, broken",), "the tool really ran"


# ───────────────────────── the behaviours that only a loop has: per-stage tools


def test_a_stage_can_narrow_the_tools_the_agent_has_and_the_model_sees_it() -> None:
    """Narrowing tools per stage is the cheapest accuracy win there is on a
    smaller model, and it is the thing Eve cannot express — its tool set is
    resolved once per run, so a planning step there sees the payment tool."""
    t = Watching(Script([
        Turn("looking", (ToolCall("zendesk", {}),)),
        Turn("paying", (ToolCall("payments", {}),)),
        Turn("Approved."),
    ]))
    lp = written({
        "starts-at": "look",
        "steps": {
            "look": {"does": "use-tools", "may-use": ["zendesk"],
                     "then": {"used-a-tool": "pay", "answered": "done"}},
            "pay": {"does": "use-tools", "may-use": ["payments"],
                    "then": {"used-a-tool": "pay", "answered": "done"}},
        },
    })
    r = asyncio.run(run(SPEC, t, "refund?", TOOLS, loop=lp))
    assert t.offered == [["zendesk"], ["payments"], ["payments"]]
    assert r.phases == ["look", "pay", "pay"]
    assert r.halted == "final"


def test_a_may_use_typo_in_a_branch_nobody_takes_fails_before_the_first_call() -> None:
    """Checked once, before the first model call, so a typo in a rarely-taken
    branch fails at the start of the run instead of forty steps in."""
    t = Watching(looks_then_answers())
    lp = written({
        "starts-at": "work",
        "steps": {
            "work": {"does": "use-tools", "then": {"used-a-tool": "work", "answered": "done"}},
            "escalate": {"does": "use-tools", "may-use": ["stripe"],
                         "then": {"answered": "done"}},
        },
    })
    with pytest.raises(LoopError, match="stripe"):
        asyncio.run(run(SPEC, t, "refund?", TOOLS, loop=lp))
    assert t.offered == [], "the run reached the model before checking the loop"


def test_a_stage_may_name_a_teammate_the_same_way_it_names_a_tool() -> None:
    """Asking somebody is a call like any other here, so `may-use:` needs no
    second field for it. Eve has a bespoke path for delegation, which is why
    nothing there can restrict it to one step of the loop."""
    spec = replace(SPEC, team={"fraud-checker": "checks for fraud signals"})
    lp = written({
        "starts-at": "ask",
        "steps": {
            "ask": {"does": "use-tools", "may-use": ["fraud-checker"],
                    "then": {"used-a-tool": "work", "answered": "done"}},
            "work": {"does": "use-tools", "then": {"used-a-tool": "work", "answered": "done"}},
        },
    })
    lp.check_against(tuple(t.name for t in spec.tools) + tuple(spec.team))
    t = Watching(Script([Turn("asking", (ToolCall("fraud-checker", {}),)), Turn("Approved.")]))
    r = asyncio.run(run(spec, t, "refund?", TOOLS, loop=lp, ask_member=_says_no_fraud))
    assert t.offered[0] == ["fraud-checker"], (
        f"the `ask` stage narrowed to one teammate and was shown {t.offered[0]}"
    )
    assert t.offered[1] == ["zendesk", "payments", "fraud-checker"], (
        "the `work` stage, which narrows nothing, lost the teammate"
    )
    assert r.phases == ["ask", "work"] and r.halted == "final"
    assert r.steps[0].tool_results == ("no fraud signals",), "the teammate was really asked"


async def _says_no_fraud(grant) -> str:
    """A teammate, answered locally. Air-gapped (D17): the point under test is
    which stage may ask, not what the teammate says."""
    return "no fraud signals"


# ───────────────────── the behaviours that only a loop has: a stage that asks


def test_a_stage_that_asks_a_person_parks_without_spending_a_model_call() -> None:
    """`does: ask-someone` is a stage with no model call at all. It parks
    through the same suspension every other wait uses, under one more `x-`
    reason — the claim `suspension.py` makes about itself being spent rather
    than restated."""
    t = Watching(Script([Turn("Approved.")]))
    lp = written({
        "starts-at": "ask",
        "steps": {
            "ask": {"does": "ask-someone", "says": "Is this refund within policy?",
                    "then": {"answered": "work"}},
            "work": {"does": "use-tools", "then": {"used-a-tool": "work", "answered": "done"}},
        },
    })
    parked = asyncio.run(run(SPEC, t, "refund?", TOOLS, loop=lp))
    assert parked.halted == "suspended"
    assert t.offered == [], "an ask-someone stage called the model"
    assert parked.suspension is not None
    assert parked.suspension.phase == "ask", "the stage it stopped in is on the record"
    assert parked.suspension.asks[0].means == "Is this refund within policy?"


def test_the_answer_a_person_gives_a_stage_becomes_that_stage_s_step() -> None:
    """What the person said is what the run carries forward, so the next stage
    reads it the way it would read anything else in the conversation."""
    lp = written({
        "starts-at": "ask",
        "steps": {
            "ask": {"does": "ask-someone", "says": "Is this refund within policy?",
                    "then": {"answered": "work"}},
            "work": {"does": "use-tools", "then": {"used-a-tool": "work", "answered": "done"}},
        },
    })
    parked = asyncio.run(
        run(SPEC, ReferenceTransport(Script([Turn("Approved.")])), "refund?", TOOLS, loop=lp)
    )
    assert parked.suspension is not None
    (asked,) = parked.suspension.asks
    said = Resumption(
        correlation_key=parked.suspension.correlation_key,
        values={asked.name: "Yes — it is 6 days old and the item arrived broken."},
    )
    out = asyncio.run(
        run(SPEC, ReferenceTransport(Script([Turn("Approved.")])), "", TOOLS,
            loop=lp, resume=parked.suspension, answer=said)
    )
    assert out.halted == "final"
    assert out.phases == ["ask", "work"]
    assert out.steps[0].text == "Yes — it is 6 days old and the item arrived broken."
    assert out.output == "Approved."


# ───────────────────────── the wording of a stage is the author's, or built in


def test_a_stage_with_no_wording_of_its_own_gets_the_built_in_wording_for_its_kind() -> None:
    """The wording is never something only we can change — the exact complaint
    against Eve's single private `COMPACTION_HEURISTICS` constant applies just
    as well to a prompt — but a stage that says nothing still has to say
    something, or `does: think` would be indistinguishable from `does:
    use-tools` with the tools removed."""
    lp = written({
        "starts-at": "plan",
        "steps": {
            "plan": {"does": "think", "then": {"answered": "check", "used-a-tool": "check"}},
            "check": {"does": "check-its-work", "then": {"answered": "done"}},
        },
    })
    assert lp.steps["plan"].instruction().startswith("Say what you plan to do")
    assert "check it against your instructions" in lp.steps["check"].instruction()


def test_wording_an_author_writes_replaces_the_built_in_wording_entirely() -> None:
    lp = written({
        "starts-at": "plan",
        "steps": {
            "plan": {"does": "think", "says": "List the three cheapest options.",
                     "then": {"answered": "done"}},
        },
    })
    assert lp.steps["plan"].instruction() == "List the three cheapest options."


def test_only_a_use_tools_stage_offers_everything_when_it_names_nothing() -> None:
    """The asymmetry that makes a `think` stage think instead of reaching for
    the first tool it recognises. Written as a table because it is a table: the
    behaviour is per kind of stage, and a new kind must decide which side it is
    on rather than inheriting one."""
    have = ("zendesk", "payments")
    for kind in Does:
        lp = written({
            "starts-at": "s",
            "steps": {"s": {"does": kind.value, "then": {"answered": "done"}}},
        })
        offered = lp.steps["s"].tools_offered(have)
        expected = have if kind is Does.USE_TOOLS else ()
        assert offered == expected, f"a {kind.value!r} stage offered {offered}"


# ───────────── a stage that asks names its question, like every other place


def _asking_workspace(stage: dict[str, Any]) -> dict[str, Any]:
    """One agent, one loop with an `ask-someone` stage, one written question."""
    return {
        "agents": {
            "desk": {"name": "Desk", "description": "d", "loop": "checked"},
        },
        "loops": {
            "checked": {
                "starts-at": "ask",
                "steps": {
                    "ask": {**{"does": "ask-someone"}, **stage,
                            "then": {"answered": "work"}},
                    "work": {"does": "use-tools",
                             "then": {"used-a-tool": "work", "answered": "done"}},
                },
            }
        },
        "questions": {
            "is-this-within-policy": {
                "description": "Whether a refund is inside the written policy.",
                "says": "Is this refund within the written policy?",
                "answer": {"approved": "yes or no", "because": "text"},
                "asked-of": ["support-leads"],
                "answer-within": "10m",
                "if-nobody-answers": "stop-and-say-so",
            }
        },
    }


def test_a_stage_that_asks_gets_the_audience_and_deadline_the_question_carries() -> None:
    """The hole this closes, measured against the real thing before it existed:
    an `ask-someone` stage parked with `who_can_answer=()`, `waits_for=None` and
    the default timeout action, because it was the ONE place in PACT that can
    stop and ask and could not name a question. The same agent's out-of-budget
    wait had all three. A wait with nobody named and no deadline is, from the
    outside, a hang — which is the thing the schema says at every other `asks:`
    must never happen."""
    doc = _asking_workspace({"asks": "is-this-within-policy"})
    spec = AgentSpec.from_document(doc, "desk")
    parked = asyncio.run(
        run(spec, ReferenceTransport(Script([Turn("Approved.")])), "refund?", TOOLS,
            asking=questions_for(doc, "desk"), now=0.0)
    )
    assert parked.halted == "suspended"
    s = parked.suspension
    assert s is not None
    assert s.who_can_answer == ("support-leads",)
    assert s.waits_for == 600.0
    assert s.if_nobody_answers == "stop-and-say-so"
    assert not s.expired(now=1.0) and s.expired(now=1_000.0)
    assert [e.name for e in s.asks] == ["approved", "because"], "the question's own shape"
    assert "Is this refund within the written policy?" in s.in_words


def test_a_stage_that_asks_and_names_nothing_is_refused_like_the_other_four() -> None:
    """`limits`, a context policy, teamwork and a resource are all refused for
    exactly this, in exactly these words. A fifth place that quietly parks with
    nothing to show would be the one hole the rule is stated to have none of."""
    doc = _asking_workspace({"says": "Is this within policy?"})
    with pytest.raises(WrongAnswer) as e:
        AgentSpec.from_document(doc, "desk")
    said = str(e.value)
    assert "stage 'ask'" in said and "does: ask-someone" in said
    assert "`asks: <the name of a file in questions/>`" in said


def test_two_stages_asking_different_questions_are_refused_rather_than_collapsed() -> None:
    """Only one rule survives per reason to wait, so a second stage naming a
    different question would silently borrow the first one's deadline, audience
    and answer shape. Refused rather than collapsed — that is the T7
    degradation, not a smaller version of the feature."""
    doc = _asking_workspace({"asks": "is-this-within-policy"})
    doc["questions"]["and-the-amount"] = dict(
        doc["questions"]["is-this-within-policy"], asks="How much?"
    )
    doc["loops"]["checked"]["steps"]["also"] = {
        "does": "ask-someone", "asks": "and-the-amount", "then": {"answered": "work"},
    }
    with pytest.raises(WrongAnswer) as e:
        AgentSpec.from_document(doc, "desk")
    assert "more than one stage that asks" in str(e.value)
    assert "and-the-amount" in str(e.value) and "is-this-within-policy" in str(e.value)


# ─────────────── AC-5.2: six shapes, and every one of them has to terminate


def test_the_specification_ships_the_six_loop_patterns_the_thesis_asks_for() -> None:
    """AC-5.2 requires **≥6 loop patterns**. Two shipped.

    The sixth name in that criterion is CodeAct, and it is deliberately absent:
    it means the agent writes code as its action, which is `runs-as: code` —
    refused in `docs/50-NOT-COPIED.md` because *a spec naming code to run makes
    `pact check` decide whether that code is safe*. Building it as a loop shape
    would be reintroducing a refusal through a side door, so the sixth is
    `answer-more-than-once` instead and the refusal stands.
    """
    assert len(LIBRARY) >= 6, sorted(LIBRARY)
    for ref in (STANDARD, PLAN_THEN_DO, REACT, REFLEXION, TREE_OF_THOUGHT,
                ANSWER_MORE_THAN_ONCE):
        assert ref in LIBRARY, f"{ref} is not shipped"
    # And the refusal has not quietly become a shape.
    assert not [k for k in LIBRARY if "code" in k], sorted(LIBRARY)


@pytest.mark.parametrize("ref", sorted(LIBRARY))
def test_every_shipped_shape_reaches_done_from_its_own_starting_stage(ref: str) -> None:
    """A shape that cannot terminate is unbounded spend wearing a pattern's name.

    Walked over the stage graph rather than run: every outcome a stage declares
    is followed, and `at-most` is treated as "this stage can also be skipped
    past", which is what `harness._stage_to_run` does. If no path reaches `done`,
    the shape is a trap whatever it is called.
    """
    loop = Loop.from_library(ref)
    seen: set[str] = set()
    stack = [loop.starts_at]
    reached_done = False
    while stack:
        name = stack.pop()
        if name == DONE:
            reached_done = True
            continue
        if name in seen:
            continue
        seen.add(name)
        phase = loop.phase(name)
        targets = set(phase.then.values())
        # A stage with `at-most:` can be routed PAST, which is an edge the
        # `then:` map alone does not show — and it is the edge that makes the
        # bounded rings in `reflexion` and `answer-more-than-once` safe.
        if phase.at_most is not None:
            targets.add(phase.then.get("too-many-times", phase.then.get("answered", DONE)))
        assert targets, f"stage {name!r} of {ref} goes nowhere"
        stack.extend(targets)
    assert reached_done, (
        f"no path through {ref} reaches `done` — every route loops, so a run "
        f"entering it stops only when a `limits:` ceiling fires, which is "
        f"unbounded spend with a pattern's name on it"
    )


@pytest.mark.parametrize("ref", sorted(LIBRARY))
def test_every_shape_that_can_loop_back_is_bounded_somewhere(ref: str) -> None:
    """`standard` loops on `used-a-tool` and is bounded by `steps-at-most`, which
    every agent has. A shape whose stages point at EACH OTHER needs more than
    that — one of them has to carry an `at-most:`, or the ring is only broken by
    a ceiling the author may not have written.

    `reflexion` is the case: `revise` and `critique` name each other, and it is
    `critique`'s `at-most: 2` that makes that safe.
    """
    loop = Loop.from_library(ref)
    for name, phase in loop.steps.items():
        mutual = [
            target for target in phase.then.values()
            if target != DONE and target != name
            and name in loop.steps[target].then.values()
        ]
        if not mutual:
            continue
        bounded = phase.at_most is not None or any(
            loop.steps[t].at_most is not None for t in mutual
        )
        assert bounded, (
            f"in {ref}, stage {name!r} and {mutual} point at each other and "
            f"neither carries an `at-most:` — nothing but a `limits:` ceiling "
            f"ends that ring"
        )


@pytest.mark.parametrize("ref", sorted(LIBRARY))
def test_every_shipped_shape_actually_runs_to_an_answer(ref: str) -> None:
    """The graph walk above says a path to `done` exists. This runs it.

    A scripted transport that always answers and never calls a tool, so what is
    under test is the shape rather than a model — and the assertion is that the
    run ENDS, with `halted == "final"`, rather than hitting a ceiling. A shape
    that only stops because `steps-at-most` fired is one whose stages route badly,
    and from the outside that is indistinguishable from a slow agent.
    """
    import asyncio

    from pact_adapters.harness import run
    from pact_adapters.ir import AgentSpec
    from pact_adapters.script import Script, Turn
    from pact_adapters.transports.mock import ReferenceTransport

    spec = AgentSpec(
        name="a", description="d", instructions="Decide.",
        loop=Loop.from_library(ref),
    )
    out = asyncio.run(
        run(spec, ReferenceTransport(Script([Turn("here is the answer")] * 40)), "hello")
    )
    assert out.halted == "final", (
        f"{ref} ended as {out.halted!r} rather than finishing — it stopped "
        f"because a ceiling fired, not because the shape reached `done`"
    )
    assert out.phases, f"{ref} recorded no stages at all"
    # Every stage it visited is one the shape declares — a typo in a `then:`
    # would route somewhere real or raise, never somewhere unnamed.
    assert set(out.phases) <= set(spec.loop.steps), out.phases


def test_the_shapes_differ_from_each_other_in_what_the_model_is_told() -> None:
    """Six names for one behaviour would be a library in the brochure sense.

    Each shape's first stage sends the model different words — that is the whole
    mechanism, and `plan-then-do`'s own header makes the claim explicitly: *"the
    measured difference from `standard` on the same model and the same question
    is a real difference in behaviour, not a different label on the same run."*
    """
    from pact_adapters.harness import _system_for

    said = {}
    for ref in LIBRARY:
        loop = Loop.from_library(ref)
        # EVERY stage, plus where each one goes. Comparing only the first stage
        # was wrong and this test found it: `reflexion` opens with
        # `does: use-tools` and no `says:`, which is byte-identical to
        # `standard`'s opening — `use-tools` adds nothing to the prompt, and that
        # is exactly what makes `standard` the same as having no loop at all. The
        # two diverge at the critique, not at the first call, and a shape is its
        # whole graph rather than its entry point.
        said[ref] = tuple(sorted(
            (name, _system_for("Decide.", phase), tuple(sorted(phase.then.items())))
            for name, phase in loop.steps.items()
        ))
    assert len(set(said.values())) == len(said), (
        "two shipped shapes tell the model the same things in the same order:\n"
        + "\n".join(f"  {k}: {len(v)} stages" for k, v in sorted(said.items()))
    )
    # And at least one stage of each new shape says something no other shape says,
    # so "different routing over identical words" is not what is being counted.
    wording = {
        ref: {text for _n, text, _t in stages} for ref, stages in said.items()
    }
    for ref in (REACT, REFLEXION, TREE_OF_THOUGHT, ANSWER_MORE_THAN_ONCE):
        others = set().union(*(w for r, w in wording.items() if r != ref))
        assert wording[ref] - others, (
            f"{ref} tells the model nothing that another shipped shape does not"
        )
