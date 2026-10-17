"""WP-38: a live Pydantic AI `Agent` is read through its public API only.

`pydantic_ai_reading` runs one probe request to a `FunctionModel` and reads each
toolset's `get_tools`; these hold what that means: no tool runs, deps nobody
can build still let the author's words through, wrappers are applied as
Pydantic AI applies them, and a name PACT cannot keep is named. The spec door's
templates (02P A4) and the files an import writes are here too.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

pytest.importorskip("pydantic_ai")

from pydantic_ai import Agent, RunContext  # noqa: E402
from pydantic_ai.toolsets import FunctionToolset, PrefixedToolset  # noqa: E402

from pact_adapters.pydantic_ai_interop import (  # noqa: E402
    catalogue_row_for,
    from_pydantic_ai_spec,
    pydantic_ai_model_id,
    to_pydantic_ai_spec,
)
from pact_adapters.pydantic_ai_live import from_pydantic_ai_agent, tool_files_for  # noqa: E402
from pact_adapters.pydantic_ai_reading import read_agent  # noqa: E402
from pact_adapters.pydantic_ai_trees import imported_agent  # noqa: E402


@dataclass
class Bank:
    customer_id: int
    connection: object


def test_the_probe_runs_no_tool_and_asks_no_real_model() -> None:
    ran: list[str] = []
    agent = Agent("openai:gpt-5.2", defer_model_check=True, instructions="Answer briefly.")

    @agent.tool_plain
    def refund(order_number: str) -> str:
        """Refund an order."""
        ran.append(order_number)
        return "refunded"

    read = read_agent(agent)
    assert read.instructions == ["Answer briefly."] and read.unread == ""
    assert ran == [], "the probe ran a tool"
    assert [sorted(leaf.tools) for leaf in read.leaves] == [["refund"]]


def test_deps_nobody_can_build_still_let_the_authors_words_through() -> None:
    """`bank_support`'s shape: a deps type with no defaults and an instruction that awaits a
    database through it. The stand-in deps answer it with nothing, so the static words are
    read and the function's text is counted, never carried."""
    agent = Agent(deps_type=Bank, instructions="You are a support agent in our bank.")

    @agent.instructions
    async def name(ctx: RunContext[Bank]) -> str:
        found = await ctx.deps.connection.customer_name(id=ctx.deps.customer_id)
        return f"The customer's name is {found!r}"

    @agent.system_prompt
    async def balance(ctx: RunContext[Bank]) -> str:  # not marked dynamic, and made from deps all the same
        return f"Their balance is {await ctx.deps.connection.balance(id=ctx.deps.customer_id)}"

    block, report = from_pydantic_ai_agent(agent)
    assert block["instructions"] == "You are a support agent in our bank."
    assert "2 part(s)" in report.not_portable["instructions.made-at-run-time"]
    assert "deps_type" in report.not_portable and report.silent_drops == ()


@dataclass
class Shop:
    customer: str = "nobody"


def test_a_system_prompt_a_function_wrote_is_carried_as_one_run_wrote_it_and_said() -> None:
    """No public read tells an `@agent.system_prompt` function not marked dynamic from a written
    string (both are a plain `SystemPromptPart`): deps that build from defaults and a function
    that reads none leave no marker. So the words are carried as the run wrote them, and the
    report says they may be a function's output."""
    from datetime import date

    agent = Agent(deps_type=Shop, system_prompt="You serve our shop.")

    @agent.system_prompt
    def customer(ctx: RunContext[Shop]) -> str:
        return f"The customer is {ctx.deps.customer}."

    @agent.system_prompt
    def today() -> str:
        return f"Today is {date.today()}."

    block, report = from_pydantic_ai_agent(agent)
    assert block["instructions"].startswith("You serve our shop.\n\nThe customer is nobody.")
    assert "`@agent.system_prompt`" in report.not_portable["system_prompts.maybe-made-by-code"]
    assert report.silent_drops == ()


def test_instructions_all_made_by_code_are_named_and_nothing_is_left_out() -> None:
    agent = Agent("openai:gpt-5.2", defer_model_check=True, deps_type=str)

    @agent.instructions
    def helping(ctx: RunContext[str]) -> str:
        return f"Help {ctx.deps}."

    block, report = from_pydantic_ai_agent(agent)
    assert "instructions" not in block and "1 part(s)" in report.not_portable["instructions.made-at-run-time"]
    assert report.silent_drops == (), report.in_plain_words()


def test_the_words_pydantic_ai_adds_for_a_prompted_answer_are_not_the_authors() -> None:
    from pydantic import BaseModel
    from pydantic_ai import PromptedOutput

    class Status(BaseModel):
        status: str

    agent = Agent(name="desk", description="Answers.", instructions="Be brief.", output_type=PromptedOutput(Status))
    block, report = from_pydantic_ai_agent(agent)
    assert block["instructions"] == "Be brief." and block["answers-with-mode"] == "prompted"
    assert block["answers-with"] == {"status": "text"} and report.silent_drops == ()
    assert "output_type.template" not in report.seen, "Pydantic AI's own template was called the author's"


@pytest.mark.parametrize("template", ["Reply ONLY as the Acme JSON envelope, schema: {schema}", False])
@pytest.mark.parametrize("marker, mode", [("PromptedOutput", "prompted"), ("NativeOutput", "native-json-schema")])
def test_an_authors_own_template_for_a_prompted_answer_is_named_not_dropped(
    template: "str | bool", marker: str, mode: str
) -> None:
    """`PromptedOutput(template=...)` and `NativeOutput(template=...)` are the author's choice of words
    (or, `False`, of none); PACT's mode writes its own, so the template is a named loss, never a silent one."""
    import pydantic_ai
    from pydantic import BaseModel

    class Status(BaseModel):
        status: str

    output = getattr(pydantic_ai, marker)(Status, template=template)
    block, report = from_pydantic_ai_agent(Agent(name="desk", instructions="Be brief.", output_type=output))
    assert block["instructions"] == "Be brief." and block["answers-with-mode"] == mode
    assert "`instructions:`" in report.not_portable["output_type.template"] and report.silent_drops == ()


def test_the_words_a_capability_or_a_toolset_adds_are_not_the_authors() -> None:
    """A capability's own instructions (the harness's `AskUser` tells the model to call its
    `ask_user_question`) and a `FunctionToolset(instructions=...)` are static parts of the
    request like the author's words: carried as the author's, a model on the PACT side would
    be told to call a tool it does not have. Only the author's words are carried; the rest is
    counted and named."""
    from pydantic_ai_harness.ask_user import AskUser

    desk = FunctionToolset(instructions="Use the refund tool carefully.")

    @desk.tool_plain
    def refund(order_number: str) -> str:
        """Refund an order."""
        return order_number

    agent = Agent(
        name="desk", instructions="Be kind.", capabilities=[AskUser(answerer=lambda *a, **k: None)], toolsets=[desk]
    )
    block, report = from_pydantic_ai_agent(agent)
    assert block["instructions"] == "Be kind."
    assert "2 part(s)" in report.not_portable["instructions.added-by-capabilities-or-toolsets"]
    assert "capabilities.AskUser" in report.not_portable and report.silent_drops == ()


def test_what_capabilities_and_toolsets_add_is_named_when_only_the_full_run_fails() -> None:
    """A capability whose instruction function fails on the stand-in deps stops the agent run as it
    is, while the bare run still reads the author's words. What the capabilities add then cannot
    be read, so that loss is named with what failed, never dropped; the toolset's own instructions
    (its refund limit), read from the run with the tools and without the capabilities, are counted."""
    from pydantic_ai.capabilities import Capability

    desk = FunctionToolset(instructions="Only refund orders under 100 EUR.")

    @desk.tool_plain
    def refund(order_number: str) -> str:
        """Refund an order."""
        return order_number

    failing = Capability(instructions=lambda ctx: str(ctx.deps.level + 1))
    agent = Agent(name="desk", deps_type=Clerk, instructions="Be kind.", toolsets=[desk], capabilities=[failing])
    read = read_agent(agent)
    assert read.added == 1 and read.unread == "" and "TypeError" in read.added_unread
    block, report = from_pydantic_ai_agent(agent)
    assert block["instructions"] == "Be kind."
    said = report.not_portable["instructions.added-by-capabilities-or-toolsets"]
    assert "1 part(s)" in said and "TypeError" in said
    assert report.silent_drops == (), report.in_plain_words()


def test_a_prepare_that_fails_does_not_make_the_toolsets_words_a_loss() -> None:
    """A tool's `prepare=` that fails on the stand-in deps stops the agent run as it is, but it can
    add no instruction, and the toolset walk names it. With nothing that adds a part, what the
    capabilities and toolsets add is no loss; a toolset's own words are still counted, and its
    instruction function failing too is named with what it raised."""

    def only_some(ctx: RunContext[Clerk], tool_def):
        return tool_def if ctx.deps.level + 1 > 2 else None

    def with_a_prepare(**kw: Any) -> Agent:
        agent = Agent(name="desk", deps_type=Clerk, instructions="Be kind.", **kw)

        @agent.tool_plain(prepare=only_some)
        def refund(order_number: str) -> str:
            """Refund an order."""
            return order_number

        return agent

    read = read_agent(with_a_prepare())
    assert (read.instructions, read.added, read.added_unread) == (["Be kind."], 0, "")
    block, report = from_pydantic_ai_agent(with_a_prepare())
    assert "instructions.added-by-capabilities-or-toolsets" not in report.not_portable
    assert "instructions.added-by-capabilities-or-toolsets" not in report.seen
    assert report.silent_drops == (), report.in_plain_words()

    worded = FunctionToolset(instructions="Use the lookup tool first.")
    failing = FunctionToolset()

    @failing.instructions
    def limit(ctx: RunContext[Clerk]) -> str:
        return f"Refund at most {ctx.deps.level + 1} orders."

    for toolset in (worded, failing):

        @toolset.tool_plain
        def lookup(order_number: str) -> str:
            """Look an order up."""
            return "shipped"

    read = read_agent(with_a_prepare(toolsets=[worded]))
    assert (read.added, read.added_unread) == (1, "")
    read = read_agent(with_a_prepare(toolsets=[failing]))
    assert read.added == 0 and "TypeError" in read.added_unread


@dataclass
class Clerk:
    level: int


def test_a_filter_or_prepare_that_fails_on_the_deps_built_is_named_and_its_tools_carried() -> None:
    """A filter a function decides, and a tool's `prepare=`, run on the deps the importer built;
    one that fails there (a comparison on the stand-in) is named, and the tools are carried as
    their functions declare them, rather than the import failing with the author's error."""
    crm = FunctionToolset()

    @crm.tool_plain
    def lookup(order_number: str) -> str:
        """Look an order up."""
        return "shipped"

    def only_for_seniors(ctx: RunContext[Clerk], tool_def):
        return tool_def if ctx.deps.level >= 2 else None

    agent = Agent(
        "openai:gpt-5.2", defer_model_check=True, deps_type=Clerk, instructions="Answer briefly.",
        toolsets=[crm.filtered(lambda ctx, td: ctx.deps.level >= 2)],
    )

    @agent.tool_plain(prepare=only_for_seniors)
    def refund(order_number: str) -> str:
        """Refund an order."""
        return "refunded"

    block, report = from_pydantic_ai_agent(agent)
    assert block["instructions"] == "Answer briefly.", "a failing filter cost the author's words"
    assert {"lookup", "refund"} <= set(block["uses"])
    assert any(k.endswith(".filter") and "failed on the deps" in v for k, v in report.not_portable.items())
    assert any("before any `prepare=` function" in v for v in report.not_portable.values())
    assert "instructions.added-by-capabilities-or-toolsets" not in report.not_portable, (
        "no capability or toolset adds instructions; a failing filter or prepare is no such loss"
    )
    assert report.silent_drops == () and report.unmapped == {}


def test_an_instruction_that_fails_on_any_deps_is_a_named_loss_not_a_crash() -> None:
    agent = Agent(deps_type=Bank, instructions="Static words.")

    @agent.instructions
    def broken(ctx: RunContext[Bank]) -> str:
        return str(1 / len(ctx.deps.connection))

    block, report = from_pydantic_ai_agent(agent)
    assert "ZeroDivisionError" in report.not_portable["instructions"]
    assert "instructions" not in block and report.silent_drops == ()


def test_a_prefixed_toolset_keeps_its_names_and_its_approval() -> None:
    crm = FunctionToolset()

    @crm.tool_plain
    def lookup(order_number: str, note: str = "") -> str:
        """Look an order up."""
        return "shipped"

    agent = Agent(name="desk", toolsets=[PrefixedToolset(crm, prefix="crm").approval_required()])
    files = tool_files_for(agent, connect="desk-tools")
    assert files == {
        "crm_lookup": {
            "description": "Look an order up.",
            "connect": "desk-tools",
            "actions": {
                "crm_lookup": {
                    "takes": {"order_number": "text", "note": "text, optional"},
                    "needs-a-person": "yes",
                }
            },
        }
    }
    _, report = from_pydantic_ai_agent(agent, connect="desk-tools")
    assert "toolsets.names" not in report.not_portable, "a prefixed name was said to change"


def test_the_tools_a_capability_brings_are_not_the_authors() -> None:
    from pydantic_ai_harness.planning import Planning

    block, report = from_pydantic_ai_agent(Agent(name="desk", capabilities=[Planning()]))
    assert "uses" not in block, "the planning capability's own tools came across as the author's"
    assert "capabilities.Planning" in report.not_portable and report.unmapped == {}


@pytest.mark.parametrize(
    ("effort", "word"), [("minimal", "low"), ("xhigh", "high")]
)
def test_a_thinking_level_pact_has_no_word_for_is_rounded_and_said(effort: str, word: str) -> None:
    block, report = from_pydantic_ai_spec({"name": "desk", "capabilities": [{"Thinking": effort}]})
    assert block["settings"] == {"thinking": word}
    assert f"`{effort}`" in report.not_portable["capabilities.Thinking.rounded"]
    assert report.unmapped == {}


def test_a_models_field_shapes_come_across_as_pact_spells_them() -> None:
    """02P O2: lists, `X | None`, an `Enum` behind a `$ref`, a default, and a date."""
    from datetime import date
    from enum import Enum

    from pydantic import BaseModel

    class Specialty(str, Enum):
        general = "general"
        cardiology = "cardiology"

    class Plan(BaseModel):
        tests: list[str]
        refer_to: Specialty | None
        follow_up_days: int = 7
        seen_on: date

    block, report = from_pydantic_ai_agent(Agent(name="desk", output_type=Plan))
    assert block["answers-with"] == {
        "tests": "list of text",
        "refer_to": "one of general, cardiology, optional",
        "follow_up_days": "whole-number, optional",
        "seen_on": "date",
    }
    assert report.unmapped == {}


@pytest.mark.parametrize("output", [bool, int])
def test_a_bare_answer_is_named_with_the_line_to_write(output: type) -> None:
    block, report = from_pydantic_ai_agent(Agent(name="desk", output_type=output))
    assert "answers-with" not in block
    assert "`answers-with:`" in report.not_portable["output_type"] and report.silent_drops == ()


def test_a_template_in_a_spec_is_a_hole_and_goes_back_out_as_a_template_the_model_reads_filled() -> None:
    """02P A4, both ways: `{{brand}}` over `deps_schema` is `{{run-inputs.brand}}`; a helper
    PACT has no blank for is named; exported again, the hole is the template, and the model
    reads the filled words on Pydantic AI 2.54."""
    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models.function import FunctionModel

    spec = {
        "name": "desk",
        "instructions": "You answer for {{brand}}{{#if vip}} first{{/if}}.",
        "deps_schema": {"type": "object", "properties": {"brand": {"type": "string"}}, "required": ["brand"]},
    }
    block, report = from_pydantic_ai_spec(spec)
    assert block["instructions"] == "You answer for {{run-inputs.brand}}{{#if vip}} first{{/if}}."
    assert "`{{#if vip}}`" in report.not_portable["instructions.templates"]
    escaped, said = from_pydantic_ai_spec({**spec, "instructions": 'Reply as \\{{"ok": true}} for {{brand}}.'})
    assert escaped["instructions"] == 'Reply as \\{{"ok": true}} for {{run-inputs.brand}}.'
    assert "instructions.templates" not in said.not_portable, "an escaped brace was read as a template"

    document = {"agents": {"desk": {"description": "Answers.", "instructions": "You answer for {{run-inputs.brand}}.",
                                    "run-inputs": {"brand": "text"}}}}
    exported, export = to_pydantic_ai_spec(document, "desk")
    assert exported["instructions"] == "You answer for {{brand}}." and "instructions.holes" not in export.not_carried
    seen: list[str] = []

    def answer(messages, info):
        seen.append(info.instructions)
        return ModelResponse(parts=[TextPart("ok")])

    agent = Agent.from_spec({**exported, "model": "test"})
    with agent.override(model=FunctionModel(answer)):
        agent.run_sync("go", deps={"brand": "Lumen Lamps"})
    assert seen == ["You answer for Lumen Lamps."]


def test_a_model_id_comes_back_as_the_catalogue_row_it_was_exported_from() -> None:
    said, _ = pydantic_ai_model_id("qwen2.5-14b-instruct")
    assert said and catalogue_row_for(said) == "qwen2.5-14b-instruct"
    assert catalogue_row_for("openai:gpt-5.2") == "openai:gpt-5.2", "an id no row names is kept as written"


def test_an_imported_agent_is_written_into_a_tree_once(tmp_path: Path) -> None:
    """`pact-import --as pydantic-ai-spec --out DIR` writes the agent through `openapi.write_into`:
    the tree then checks, and importing again writes nothing."""
    spec = tmp_path / "desk.yaml"
    spec.write_text(yaml.safe_dump({"name": "Order desk", "description": "Answers order questions.",
                                    "instructions": "Answer briefly."}))
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "workspace.yaml").write_text("name: shop\nallow-egress: []\n")
    command = [sys.executable, "-m", "pact_adapters.importing", str(spec), "--as", "pydantic-ai-spec", "--out", str(tree)]
    env = {"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"), "PATH": "/usr/bin:/bin"}
    first = subprocess.run(command, capture_output=True, text=True, env=env)
    assert first.returncode == 0, first.stderr
    assert (tree / "agents" / "order-desk.yaml").is_file(), first.stdout
    again = subprocess.run(command, capture_output=True, text=True, env=env)
    assert "none new" in again.stdout, again.stdout
    assert imported_agent(yaml.safe_load(spec.read_text())).files.keys() == {"agents/order-desk.yaml"}


def test_a_nested_answer_is_written_as_shapes_with_parts_and_the_tree_checks(tmp_path: Path) -> None:
    """02P O2: a nested model is a shape with parts under `workspace.yaml`'s `shapes:`, named
    for its title, when the import writes a tree; the bare door, with nowhere to put it, says what to
    write."""
    from pydantic import BaseModel

    from pact_adapters.openapi import write_into

    class Report(BaseModel):
        diagnosis: list[str]
        minutes: int

    class Outcome(BaseModel):
        report: Report | None = None
        status: str

    agent = Agent(name="triage", description="Triages.", instructions="Triage.", output_type=Outcome)
    imported = imported_agent(agent)
    assert imported.shapes == {"report": {"diagnosis": "list of text", "minutes": "whole-number"}}
    block = yaml.safe_load(imported.files["agents/triage.yaml"])
    assert block["answers-with"] == {"report": "report, optional", "status": "text"}
    (tmp_path / "workspace.yaml").write_text("name: clinic\nallow-egress: []\n")
    assert sorted(write_into(tmp_path, imported)) == ["agents/triage.yaml", "workspace.yaml"]
    checked = subprocess.run(
        [str(Path(__file__).resolve().parents[3] / "target" / "debug" / "pact"), "check", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr
    _, bare = from_pydantic_ai_agent(agent)
    assert any(s.startswith("`shapes:` in `workspace.yaml`") and "`report` (diagnosis: list of text" in s
               for s in bare.still_to_write), "the bare door writes no workspace, so it says what to write"
