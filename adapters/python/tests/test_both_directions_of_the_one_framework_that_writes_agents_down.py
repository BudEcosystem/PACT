"""Pydantic AI crosses in both directions, and neither crossing lies about itself.

`test_importing_reports_every_drop.py` opens with the sentence this file exists
to amend:

> Every framework in this repository defines its agents in code, and importing
> code means either executing it — which D17 and D23 forbid outright — or
> parsing it, which is a different project.

That was true of all seven targets and is no longer true of one. Pydantic AI
ships `AgentSpec`: a YAML/JSON agent definition loaded by `Agent.from_file()`.
It is a config file, so reading one executes nothing, and it carries a model,
instructions, settings, an output schema and capabilities — which makes it the
first source here that is an agent SPECIFICATION rather than a facade (an A2A
card) or a single exchange (an Anthropic request).

So there are three crossings to hold, and each has a different thing that could
go wrong:

* **a spec file in** — the ordinary import, held to zero silent drops like the
  other two;
* **a live `Agent` in** — the door that covers the agents defined in Python,
  which is most of them. The risk here is claiming more than an OBJECT knows:
  a `@agent.instructions` function has no text until a run exists;
* **a PACT agent out** — the risk here is the opposite, and it is the one that
  matters most. An `AgentSpec` has no field for ceilings, policy, tools, the
  loop or the team. An export that emitted a `.yaml` and said nothing would hand
  somebody a file that looks like their governed agent and is not.

The last group of tests is the one worth reading first: it runs a real PACT
agent under Pydantic AI's own loop and checks that the author's approval policy
still stops the call.
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.pydantic_ai_interop import (  # noqa: E402
    build_agent,
    from_pydantic_ai_agent,
    from_pydantic_ai_spec,
    pydantic_ai_model_id,
    resource_file_for,
    shape_as_json_schema,
    shape_from_json_schema,
    to_pydantic_ai_spec,
    tool_files_for,
    usage_limits_for,
)
from pact_adapters.questions import Shape  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"

pydantic_ai = pytest.importorskip("pydantic_ai")


@pytest.fixture(scope="module")
def document() -> dict:
    """The worked example, loaded the only way an adapter may load one (P-1)."""
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(PACT_BIN), "show", str(EXAMPLE)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


@pytest.fixture(scope="module")
def spec(document: dict) -> AgentSpec:
    return AgentSpec.from_document(document, "refund-desk", str(EXAMPLE))


# ───────────────────────────────── the shapes, which both directions ride on


ROUND_TRIPS = [
    "text",
    "yes-or-no",
    "number",
    "whole-number",
    "one of approved, declined",
]


@pytest.mark.parametrize("written", ROUND_TRIPS)
def test_an_answer_shape_survives_the_round_trip(written: str) -> None:
    """A shape becomes JSON Schema and comes back as the same shape.

    The five that round-trip are the five a JSON Schema can say without losing
    anything. `money`, `images`, `audio` and `file` deliberately do NOT come
    back — they are tested below for why.
    """
    there = shape_as_json_schema(Shape.parse(written))
    back = shape_from_json_schema(there)
    assert back is not None, f"{written} did not come back at all"
    assert back.written() == Shape.parse(written).written()


@pytest.mark.parametrize("written", ["money", "images", "audio", "file"])
def test_the_four_shapes_json_schema_cannot_say_are_not_claimed_back(written: str) -> None:
    """The asymmetric four, which is a decision and not an omission.

    `money` is `{"type": "string"}` with its currency in the description, and
    the three attachment shapes are arrays of references. Reading those back as
    `money` or `images` would mean claiming every string is an amount and every
    list of strings is a set of pictures — so they come back as their honest
    JSON meaning (`text`, or nothing) and the report names the loss.

    Asserted rather than left implicit because the tempting "fix" is to make the
    round trip total, and doing so would silently retype half of everybody's
    schemas.
    """
    there = shape_as_json_schema(Shape.parse(written))
    back = shape_from_json_schema(there)
    assert back is None or back.written() != written


def test_a_yaml_enum_of_yes_and_no_is_a_yes_or_no_and_not_a_sentence() -> None:
    """`enum: [yes, no]` is booleans by the time YAML has finished with it.

    YAML 1.1 reads `yes` and `no` as booleans and `AgentSpec.from_file` uses
    `yaml.safe_load`, so the commonest way anybody writes a two-way choice
    arrives as `[True, False]`. Read as an unrecognised enum it fell through to
    the property's `type` and became `text` — the constraint lost INSIDE a key
    the report had already called mapped, which is the one kind of loss
    `silent_drops` cannot see, because it counts keys and this one was carried.
    """
    assert shape_from_json_schema({"enum": [True, False]}).written() == "yes-or-no"
    assert shape_from_json_schema({"enum": [False, True]}).written() == "yes-or-no"
    # A quoted pair is genuinely two words and stays two words.
    assert shape_from_json_schema({"enum": ["yes", "no"]}).written() == "one of yes, no"


def test_an_enum_with_no_pact_spelling_comes_back_as_nothing() -> None:
    """A mixed or structured enum has no shape, and says so rather than narrowing."""
    assert shape_from_json_schema({"enum": [1, "a", {"b": 2}]}) is None
    assert shape_from_json_schema({"type": "object"}) is None
    assert shape_from_json_schema({"type": "array", "items": {"type": "object"}}) is None


# ──────────────────────────────────────── a spec file in


SPEC_FIXTURE = {
    "model": "anthropic:claude-opus-4-6",
    "name": "Research Desk",
    "description": "answers research questions",
    "instructions": ["You are a research assistant.", "Cite your sources."],
    "model_settings": {
        "max_tokens": 8192,
        "temperature": 0.2,
        "timeout": 30,
        "logit_bias": {"123": 5},
    },
    "capabilities": [{"Thinking": {"effort": "high"}}, "WebSearch", "Instrumentation"],
    "output_schema": {
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "confidence": {"type": "number"},
            "address": {"type": "object"},
        },
    },
    "deps_schema": {"type": "object", "properties": {"user_name": {"type": "string"}}},
    "end_strategy": "exhaustive",
    "retries": 3,
}


def test_a_spec_file_imports_with_no_silent_drops() -> None:
    """The criterion, on the first source here that is a real specification."""
    _, report = from_pydantic_ai_spec(SPEC_FIXTURE)
    assert report.silent_drops == ()


def test_what_a_spec_file_actually_carries() -> None:
    """The half that works, asserted as values rather than as a count.

    A test that only checked `silent_drops` would pass on an importer that
    reported every key as not-understood and produced an empty agent.
    """
    agent, _ = from_pydantic_ai_spec(SPEC_FIXTURE)
    assert agent["model"] == "anthropic:claude-opus-4-6"
    assert agent["name"] == "Research Desk"
    # A list of instructions joins the way `ir._text` joins a folder of them, so
    # a spec with three strings and a PACT tree with three files agree.
    assert agent["instructions"] == "You are a research assistant.\n\nCite your sources."
    assert agent["settings"]["max-tokens"] == 8192
    assert agent["settings"]["thinking"] == "high"
    assert agent["answers-with"] == {"answer": "text", "confidence": "number"}
    assert agent["run-inputs"] == {"user_name": "text"}
    assert agent["uses"] == ["web-search"]


def test_the_four_model_settings_pact_has_no_key_for_are_named() -> None:
    """`ModelSettings` is wider than PACT's closed `settings:` group.

    The transport's `_SETTINGS` names twelve; this SDK's `ModelSettings` carries
    sixteen. The other four are reported by name, and `logit_bias` carries the
    reason that makes the refusal a decision rather than a gap: its keys are
    tokeniser ids, so the same block means something different on the next model
    — it is not portable by construction.
    """
    _, report = from_pydantic_ai_spec(SPEC_FIXTURE)
    assert "model_settings.timeout" in report.not_portable
    assert "model_settings.logit_bias" in report.not_portable
    assert "tokeniser" in report.not_portable["model_settings.logit_bias"]


def test_a_property_with_no_pact_shape_is_named_and_not_flattened() -> None:
    """The nested `address` is reported, not quietly turned into a sentence."""
    agent, report = from_pydantic_ai_spec(SPEC_FIXTURE)
    assert "address" not in agent["answers-with"]
    assert "output_schema.address" in report.unmapped


def test_the_mode_the_source_left_to_the_model_is_not_pinned() -> None:
    """`output_schema` builds a `StructuredDict`, whose mode is `auto`.

    Pydantic AI resolves it per model from
    `ModelProfile.default_structured_output_mode`. Writing
    `answers-with-mode: native-json-schema` here would pin, on every model, a
    decision the source deliberately left open.
    """
    agent, _ = from_pydantic_ai_spec(SPEC_FIXTURE)
    assert "answers-with-mode" not in agent


def test_the_loop_words_are_refused_rather_than_copied() -> None:
    """`end_strategy` and `retries` name Pydantic AI's loop, which PACT owns itself."""
    _, report = from_pydantic_ai_spec(SPEC_FIXTURE)
    assert "end_strategy" in report.not_portable
    assert "retries" in report.not_portable


def test_a_breakage_in_this_importer_is_measurable() -> None:
    """The measurement can fail, which is what makes the passing runs mean anything.

    The same proof `test_importing_reports_every_drop.py` makes: a key the
    importer does not account for lands in `silent_drops` without anybody
    maintaining a list of known drops.
    """
    _, report = from_pydantic_ai_spec({**SPEC_FIXTURE, "a_key_nobody_reads": 1})
    assert "a_key_nobody_reads" not in report.silent_drops, (
        "the catch-all sweep should account for unknown keys as unmapped"
    )
    # And the sweep itself is what does it — remove a key from every bucket and
    # the property that finds it is `seen`, not a maintained list.
    report.unmapped.pop("a_key_nobody_reads")
    assert report.silent_drops == ("a_key_nobody_reads",)


# ──────────────────────────────────────── a live Agent in


def _live_agent():
    """An agent built the way Pydantic AI's own docs build one — in Python."""
    from pydantic import BaseModel
    from pydantic_ai import Agent, RunContext
    from pydantic_ai.capabilities import Thinking
    from pydantic_ai.models.test import TestModel

    class Verdict(BaseModel):
        decision: str
        escalate: bool

    agent = Agent(
        TestModel(),
        name="support-desk",
        description="answers support tickets",
        instructions="Be concise and kind.",
        output_type=Verdict,
        model_settings={"temperature": 0.1},
        capabilities=[Thinking(effort="high")],
        metadata={"team": "cx"},
    )

    @agent.instructions
    def whoami(ctx: RunContext) -> str:  # pragma: no cover - never called here
        return "you are helping a customer"

    @agent.tool_plain(requires_approval=True)
    def refund(order_id: str) -> str:
        """Refund an order."""
        return "ok"  # pragma: no cover

    return agent


def test_a_live_agent_imports_with_no_silent_drops() -> None:
    _, report = from_pydantic_ai_agent(_live_agent())
    assert report.silent_drops == ()


def test_an_agent_that_was_given_nothing_reports_no_losses() -> None:
    """A bare agent is a clean import, and must not print a BUG banner.

    This is the case that shipped broken. `seen` listed every attribute a live
    `Agent` has, so `Agent('openai:gpt-5.2')` — an agent with no system prompt,
    no tools and no capabilities — reported `system_prompts` and `toolsets` as
    silent drops and printed *BUG IN THIS IMPORTER* on a correct import.

    A reader who sees that banner on a clean run learns to ignore the banner,
    which costs the whole mechanism the one thing it is for. So `seen` holds
    what the object CARRIES, and an agent carrying nothing loses nothing.
    """
    from pydantic_ai import Agent
    from pydantic_ai.models.test import TestModel

    _, report = from_pydantic_ai_agent(Agent(TestModel()))
    assert report.silent_drops == ()
    assert "system_prompts" not in report.seen
    assert "toolsets" not in report.seen
    # And the capabilities Pydantic AI injects into every agent are not losses
    # the author can act on, so they are not reported as any.
    assert "capabilities" not in report.seen


def test_instructions_that_only_exist_during_a_run_are_reported_not_invented() -> None:
    """What an OBJECT knows is less than what the CODE says.

    `@agent.instructions` registers a callable whose text is produced from a
    `RunContext`; there is no sentence on the object to carry. Reporting it is
    the difference between a PACT tree missing the instructions that actually
    govern the agent and one that says which are missing.
    """
    agent, report = from_pydantic_ai_agent(_live_agent())
    assert agent["instructions"] == "Be concise and kind."
    assert "instructions" in report.unmapped
    assert "RunContext" in report.unmapped["instructions"]


def test_a_tool_that_requires_approval_becomes_a_gate_on_that_tools_action() -> None:
    """The one governance line that crosses intact, in this direction.

    `requires_approval=True` shows on the resolved `ToolDefinition` as
    `kind='unapproved'`, and PACT's one-line spelling of the same thing is
    `needs-a-person: yes` on the action.

    It lands on the TOOL FILE and not on the agent, and `pact check` is what
    taught that: `agent.policy:` is a NAME (`names: policies` in the schema), so
    the prose this wrote for a round — `policy: Ask a person before refund.` —
    was refused with `schema/no-such-name`. The fix is not a policy file:
    `action.needs-a-person` exists precisely because gating one action otherwise
    costs a question, a policy and a rule inside it, and it desugars to exactly
    that rule against `pact:question/is-this-ok`.
    """
    agent, report = from_pydantic_ai_agent(_live_agent())
    # Nothing prose-shaped on the agent, because that would not load.
    assert "policy" not in agent
    assert "requires_approval" in report.mapped

    files = tool_files_for(_live_agent())
    assert files["refund"]["actions"]["call"]["needs-a-person"] == "yes"
    # And only the tool the author actually guarded.
    plain = tool_files_for(_live_agent_without_approval())
    assert "needs-a-person" not in plain["refund"]["actions"]["call"]

    # An author whose approval already crossed is not told to write a policy.
    assert not any(s.startswith("`policy:`") for s in report.still_to_write)


def _live_agent_without_approval():
    """The same tool, ungated — so the assertion above cannot pass by accident."""
    from pydantic_ai import Agent
    from pydantic_ai.models.test import TestModel

    agent = Agent(TestModel(), name="x")

    @agent.tool_plain
    def refund(order_id: str) -> str:
        """Refund an order."""
        return "ok"  # pragma: no cover

    return agent


def test_the_two_doors_give_the_same_answer_for_the_same_capability() -> None:
    """`Thinking(effort='high')` is `thinking: high` whichever way it arrived.

    The spec reader sees `{'Thinking': {'effort': 'high'}}` and the live reader
    sees a `Thinking` instance — genuinely different shapes, which is why there
    are two readers. What they must not differ on is the ANSWER: an agent that
    imported one way in YAML and another way in Python would be portability that
    is technically true and useless.
    """
    from pydantic_ai import Agent
    from pydantic_ai.capabilities import Thinking, WebSearch
    from pydantic_ai.models.test import TestModel

    live, _ = from_pydantic_ai_agent(
        Agent(TestModel(), capabilities=[Thinking(effort="high"), WebSearch()])
    )
    filed, _ = from_pydantic_ai_spec(
        {"model": "test", "capabilities": [{"Thinking": {"effort": "high"}}, "WebSearch"]}
    )
    assert live.get("settings") == filed.get("settings") == {"thinking": "high"}
    assert live.get("uses") == filed.get("uses") == ["web-search"]


def test_a_capability_the_author_configured_is_not_mistaken_for_an_injected_one() -> None:
    """`ToolSearch` is auto-injected AND writable, which is the trap.

    `_inject_auto_capabilities` adds `ToolSearch()` to every agent, so the
    importer has to filter it or every bare agent reports a capability nobody
    wrote. Filtering by TYPE does that — and also drops
    `ToolSearch(max_results=20)`, which is an author's only configured
    capability, silently, under the one mechanism whose entire purpose is that
    nothing is dropped silently.

    So the filter is by VALUE: injected means equal to a default-constructed
    instance. A configured one differs and is reported.
    """
    from pydantic_ai import Agent
    from pydantic_ai.capabilities import ToolSearch
    from pydantic_ai.models.test import TestModel

    _, plain = from_pydantic_ai_agent(Agent(TestModel(), capabilities=[ToolSearch()]))
    assert "capabilities" not in plain.seen, "a default ToolSearch is the injected one"

    _, configured = from_pydantic_ai_agent(
        Agent(TestModel(), capabilities=[ToolSearch(max_results=20)])
    )
    assert "capabilities" in configured.seen
    assert "capabilities.ToolSearch" in configured.not_portable
    assert configured.silent_drops == ()


def test_a_toolset_with_nothing_readable_without_a_run_is_reported() -> None:
    """A toolset resolved per run has no list to read, and that is said.

    The alternative is an agent imported with four of its nine tools and nothing
    anywhere recording that five are missing.
    """
    from pydantic_ai import Agent
    from pydantic_ai.models.test import TestModel
    from pydantic_ai.toolsets import FunctionToolset

    def build(ctx):  # pragma: no cover - never run
        return FunctionToolset([])

    _, report = from_pydantic_ai_agent(Agent(TestModel(), toolsets=[build]))
    assert any(k.startswith("toolsets[") for k in report.unmapped)
    assert report.silent_drops == ()


# ──────────────────────────────────────── a PACT agent out


def test_a_pact_agent_exports_with_no_silent_losses(document: dict) -> None:
    _, report = to_pydantic_ai_spec(document, "refund-desk")
    assert report.silent_losses == ()


def test_the_exported_spec_is_one_pydantic_ai_will_load(document: dict) -> None:
    """Not a shape invented here: `AgentSpec` itself must validate it.

    An exporter written against a guessed schema produces a file that loads
    nowhere, dressed as an integration — which is the failure `exporting.py`
    calls out for OSSA and refuses to commit.
    """
    from pydantic_ai.agent import AgentSpec as PydanticAgentSpec

    written, _ = to_pydantic_ai_spec(document, "refund-desk")
    loaded = PydanticAgentSpec.model_validate(written)
    assert loaded.name == "Refund Desk"
    assert loaded.output_schema is not None


def test_the_authors_answer_shape_reaches_the_model_as_a_schema(document: dict) -> None:
    """`decision: one of approved, declined` becomes an enum the model is shown.

    `ir.AgentSpec.answers_with` records that this field was `tier: core`, in the
    worked example, and read by NOTHING for a round — every scripted answer in
    the suite hand-wrote the format the document already specified. This is the
    field arriving somewhere it is enforced.
    """
    written, report = to_pydantic_ai_spec(document, "refund-desk")
    properties = written["output_schema"]["properties"]
    assert properties["decision"] == {"type": "string", "enum": ["approved", "declined"]}
    assert set(written["output_schema"]["required"]) == set(properties)
    assert "answers-with" in report.carried


def test_everything_a_spec_file_cannot_hold_is_named_with_what_stops_holding(
    document: dict,
) -> None:
    """The half that matters, and the reason this export has a report at all.

    A Pydantic AI `AgentSpec` has no field for ceilings, policy, tools, the loop
    or the team. Each is named, and the two that are governance say what stops
    being enforced rather than only that a field is absent — a reader deciding
    whether to ship this file needs the consequence, not the gap.
    """
    _, report = to_pydantic_ai_spec(document, "refund-desk")
    for missing in ("limits", "policy", "loop", "uses", "team", "interceptors"):
        assert missing in report.not_carried, f"{missing} was lost without being named"
    assert "UsageLimits" in report.not_carried["limits"]
    assert "requires_approval" in report.not_carried["policy"]


@pytest.mark.parametrize("choice", ["required", "payments"])
def test_a_tool_choice_this_sdk_refuses_on_an_agent_is_not_written_into_one(
    choice: str,
) -> None:
    """The two `tool-choice:` values that load and then kill the first run.

    `required` and a named tool both exclude the output tools, so an agent
    carrying either could never produce a final response — `Agent.run` raises
    `UserError` instead of looping. Writing one into `model_settings` produces a
    spec file that VALIDATES, loads, and dies on first use with a traceback
    about output tools: worse than a named loss, for a line `pact check` printed
    OK for.

    This is the sharpest case for decision 5.
    `transports/pydantic_ai_transport.py` carries all four values, because
    `direct.model_request` makes one call and has no loop to strand — PACT's
    harness is what comes back for the next step. Hand the loop to the framework
    and two of the author's twelve settings stop being expressible at all.
    """
    from pydantic_ai.agent import AgentSpec as PydanticAgentSpec

    document = {
        "agents": {"a": {"name": "A", "settings": {"tool-choice": choice, "top-p": 0.9}}}
    }
    written, report = to_pydantic_ai_spec(document, "a")
    assert "tool_choice" not in (written.get("model_settings") or {})
    # The rest of the block still crosses — one refused value does not cost the
    # other eleven.
    assert written["model_settings"]["top_p"] == 0.9
    # And the loss is named with its consequence, not merely listed.
    assert "tool-choice" in report.carried["settings"]
    assert "final response" in report.carried["settings"]
    assert report.silent_losses == ()
    PydanticAgentSpec.model_validate(written)


@pytest.mark.parametrize("choice", ["auto", "none"])
def test_the_two_tool_choice_values_an_agent_can_hold_are_carried(choice: str) -> None:
    """The refusal above is narrow, and this is what stops it widening.

    A guard written one degree too broad would drop every `tool-choice:` and
    look just as green.
    """
    document = {"agents": {"a": {"name": "A", "settings": {"tool-choice": choice}}}}
    written, _ = to_pydantic_ai_spec(document, "a")
    assert written["model_settings"]["tool_choice"] == choice


def test_an_agent_that_pinned_no_model_says_so_rather_than_failing_later(
    document: dict,
) -> None:
    """The worked example pins none, so the file does not load on its own.

    `Agent.from_spec` raises `UserError('model must be provided either in the
    spec or as a keyword argument')`. A reader told nothing meets that as a
    traceback instead of as the one line of the report that would have prevented
    it.
    """
    written, report = to_pydantic_ai_spec(document, "refund-desk")
    assert "model" not in written
    assert "model" in report.supplied_by_the_runtime


def test_the_ceilings_that_translate_are_carried_and_the_two_that_do_not_are_not(
    spec: AgentSpec,
) -> None:
    """`UsageLimits` is not a superset of PACT's ceilings, and pretending costs money.

    Three translate exactly. The two that do not are left out on purpose:

    * `cost-per-request-under:` bounds ONE request; `cost_limit` bounds the run.
      Setting one from the other is wrong in both directions — a per-request cap
      of $0.05 would stop a ten-step run at step one, or a run cap of $0.05
      would pass ten requests that each broke the author's rule.
    * `runs-for-at-most:` is wall-clock, and `UsageLimits` has no time field.
    """
    limits = usage_limits_for(spec)
    assert limits.request_limit == spec.max_steps
    assert limits.tool_calls_limit == spec.limits.tool_calls_at_most
    assert limits.total_tokens_limit == spec.limits.tokens_at_most
    # `getattr`, because `cost_limit` does not exist on every version of this
    # SDK that this adapter supports — it arrived after the pinned 2.18 floor.
    # Asserting the attribute directly would make this test a version check
    # rather than the behavioural claim it is: whatever the field is called on
    # the installed version, PACT's per-REQUEST money ceiling is not written
    # into a per-RUN one.
    assert getattr(limits, "cost_limit", None) is None


# ─────────────────────── the crossing that matters: it actually runs


def test_a_pact_agent_runs_under_pydantic_ais_own_loop(spec: AgentSpec) -> None:
    """The whole point, end to end: the author's tools reach the model.

    A PACT `tools/<name>.yaml` has a name, a description and a `takes:` block
    and no Python behind it, which is exactly what `Tool.from_schema` accepts.
    Without this the export is a config file nobody can run.
    """
    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models.function import AgentInfo, FunctionModel

    offered: list[str] = []

    def respond(messages, info: AgentInfo) -> ModelResponse:
        offered.extend(t.name for t in info.function_tools)
        return ModelResponse(parts=[TextPart(content="{}")])

    agent = build_agent(spec, call_tool=lambda n, a: "ok", model=FunctionModel(respond))
    agent.run_sync("refund order A-1", output_type=str)
    assert sorted(offered) == sorted(t.name for t in spec.tools)


def test_the_authors_approval_policy_still_stops_the_call(spec: AgentSpec) -> None:
    """The one PACT guarantee that survives the crossing intact — proved, not asserted.

    `examples/refund-desk/policies/approvals.yaml` gates `payments/issue-refund`
    over 200 USD and every `zendesk/reply`, and its own comment says *"This is
    enforcement, not a note in the instructions."*

    Both systems stop the same call and wait for the same person, so this is the
    one governance line that does not degrade on the way over: the tool must not
    execute before a person answers, and must execute after. Both halves are
    checked, because a guard that never releases is as wrong as one that never
    stops.
    """
    from pydantic_ai import DeferredToolRequests, DeferredToolResults
    from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
    from pydantic_ai.models.function import AgentInfo, FunctionModel

    turns: list[int] = []

    def respond(messages, info: AgentInfo) -> ModelResponse:
        turns.append(1)
        if len(turns) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="payments",
                        args={
                            "order-number": "A-1",
                            "amount": "40 USD",
                            "action": "issue-refund",
                        },
                        tool_call_id="c1",
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(content="done")])

    ran: list[tuple[str, dict]] = []
    agent = build_agent(
        spec,
        call_tool=lambda n, a: ran.append((n, a)) or "refunded",
        model=FunctionModel(respond),
    )

    parked = agent.run_sync(
        "refund order A-1",
        output_type=[str, DeferredToolRequests],
        usage_limits=usage_limits_for(spec),
    )
    assert isinstance(parked.output, DeferredToolRequests)
    assert [c.tool_name for c in parked.output.approvals] == ["payments"]
    assert ran == [], "the money moved before anybody approved it"

    said_yes = DeferredToolResults(
        approvals={c.tool_call_id: True for c in parked.output.approvals}
    )
    agent.run_sync(
        message_history=parked.all_messages(),
        deferred_tool_results=said_yes,
        output_type=[str, DeferredToolRequests],
        usage_limits=usage_limits_for(spec),
    )
    assert [name for name, _ in ran] == ["payments"], "approval never released the call"


MODES = [
    ("", "PromptedOutput"),
    ("prompted", "PromptedOutput"),
    ("native-json-schema", "NativeOutput"),
    ("tool", "ToolOutput"),
]


@pytest.mark.parametrize("written,marker", MODES)
def test_the_way_the_author_asked_for_the_answer_is_honoured(
    written: str, marker: str
) -> None:
    """`answers-with-mode:` is the one PACT field with a total counterpart here.

    Four words, four marker classes, and the correspondence is exact — which is
    why it is honoured rather than reported. A spec FILE cannot carry it
    (`AgentSpec` has only `output_schema`, whose mode is `auto`), so this is the
    single clearest case for the export having two halves.
    """
    import dataclasses

    from pydantic_ai.models.test import TestModel

    spec = AgentSpec(
        name="a",
        description="d",
        instructions="i",
        answers_with={"decision": "one of approved, declined"},
        answers_with_mode=written,
    )
    agent = build_agent(dataclasses.replace(spec), model=TestModel())
    assert type(agent.output_type).__name__ == marker
    assert agent.output_json_schema()["properties"]["decision"]["enum"] == [
        "approved",
        "declined",
    ]


def test_an_unset_mode_is_pacts_own_pick_and_not_the_frameworks() -> None:
    """Unset is `prompted`, because that is what PACT itself picks.

    `ir.AgentSpec.answers_with_mode` records the reason: *prompted, because that
    is the one mode every one of the seven transports can honour and the only
    one that works on a machine with no network.* Letting the model profile
    decide (`auto`) would answer the same document in one shape under PACT's
    harness and another under this agent — a divergence with nothing to do with
    the agent, which is exactly what PACT exists to remove.
    """
    import dataclasses

    from pydantic_ai.models.test import TestModel
    from pydantic_ai.output import PromptedOutput

    spec = AgentSpec(name="a", description="d", instructions="i", answers_with={"x": "text"})
    agent = build_agent(dataclasses.replace(spec), model=TestModel())
    assert isinstance(agent.output_type, PromptedOutput)


def test_a_mode_of_text_leaves_the_answer_unconstrained() -> None:
    """`text` means the author asked for the shape NOT to be put on the wire."""
    import dataclasses

    from pydantic_ai.models.test import TestModel

    spec = AgentSpec(
        name="a",
        description="d",
        instructions="i",
        answers_with={"x": "text"},
        answers_with_mode="text",
    )
    assert build_agent(dataclasses.replace(spec), model=TestModel()).output_type is str


def test_a_mode_with_no_shape_to_put_is_still_text() -> None:
    """A mode is how a SHAPE is put to the model, and there is no shape.

    Without this the `tool` branch would build a `ToolOutput` around an empty
    schema, which `_output.OutputSchema.build` refuses outright — an agent that
    fails to construct for a mode line the author was entitled to write.
    """
    import dataclasses

    from pydantic_ai.models.test import TestModel

    spec = AgentSpec(
        name="a", description="d", instructions="i", answers_with={}, answers_with_mode="tool"
    )
    assert build_agent(dataclasses.replace(spec), model=TestModel()).output_type is str


def test_only_the_tools_the_author_gated_require_approval(spec: AgentSpec) -> None:
    """A `Gate` holds rules from four sources and only one of them stops a call.

    `Rule.gates` is True only for `policy.ask-a-person`; the rules read off
    `limits.asks`, a context policy and a `teamwork:` block supply the WORDING
    for a wait the run has already entered for some other reason. Its own
    docstring says turning those into gates would "park a run on the mere
    existence of a question" — which here would be `requires_approval=True` on a
    tool nobody asked to guard, stopping a run PACT's own harness lets through.

    The worked example is the case that proves it: six things carry rules and
    exactly two are gates.
    """
    from pydantic_ai.toolsets import FunctionToolset

    agent = build_agent(spec, call_tool=lambda n, a: "ok")
    guarded = {
        name
        for toolset in agent.toolsets
        if isinstance(toolset, FunctionToolset)
        for name, tool in toolset.tools.items()
        if tool.requires_approval
    }
    gated_things = {
        thing for thing, rules in spec.asking.rules.items() if any(r.gates for r in rules)
    }
    assert guarded == {"payments", "zendesk"}
    assert guarded == gated_things & {t.name for t in spec.tools}
    # The four wording-only rules must not have become guards.
    assert not guarded & {"decision", "conversation", "policy-checker", "fraud-checker"}


def test_without_a_tool_runtime_the_tools_defer_rather_than_pretend(spec: AgentSpec) -> None:
    """No executor means an `ExternalToolset`, not a tool that lies about running.

    A PACT tree is not deployed anywhere — that is what makes the same tree
    runnable in two places — so an agent exported to somebody else's stack may
    well arrive where PACT's tool runtime is not. The honest answer is for the
    run to end with `DeferredToolRequests` and let the caller fulfil them.
    """
    from pydantic_ai.toolsets.external import ExternalToolset

    agent = build_agent(spec, call_tool=None)
    external = [t for t in agent.toolsets if isinstance(t, ExternalToolset)]
    assert external, "tools with no executor should defer, not vanish"
    assert sorted(d.name for d in external[0].tool_defs) == sorted(
        t.name for t in spec.tools
    )


@pytest.mark.parametrize(
    "catalogue_name,expected",
    [
        ("claude-sonnet-5", "anthropic:claude-sonnet-5"),
        ("gpt-5.4", "openai:gpt-5.4"),
        ("gemini-3.5-flash", "google:gemini-3.5-flash"),
        ("grok-4.5", "xai:grok-4.5"),
        # The one where the two id schemes genuinely differ: Ollama tags the
        # same weights with a colon, which is why the catalogue carries
        # `also-known-as:` at all.
        ("qwen2.5-7b-instruct", "ollama:qwen2.5:7b-instruct"),
    ],
)
def test_a_catalogue_row_becomes_an_id_this_sdk_can_bind(
    catalogue_name: str, expected: str
) -> None:
    """PACT binds a catalogue ROW; Pydantic AI binds `provider:name`.

    Copying one into the other is what shipped first, and the round trip through
    a real tree is what caught it: every run of the exported agent died on
    `UserError: Unknown model: qwen2.5-7b-instruct`. The row already holds both
    halves — `served-by:` names the runtime and `also-known-as:` says what that
    runtime calls the model — so this is a lookup, not a guess.
    """
    said, why = pydantic_ai_model_id(catalogue_name)
    assert said == expected, why


def test_a_row_with_no_provider_this_sdk_has_is_refused_rather_than_guessed() -> None:
    """A name that loads and then fails every run is worse than a named loss.

    The vLLM case is the real one: it speaks OpenAI's API shape but needs a base
    URL, and a catalogue row does not carry an address (`endpoint: local` is a
    yes-or-no about egress). Emitting `openai:<name>` would point at OpenAI for a
    model OpenAI does not serve.
    """
    said, why = pydantic_ai_model_id("not-a-row-anybody-published")
    assert said == ""
    assert "models/catalog.yaml" in why

    document = {"agents": {"a": {"name": "A", "model": "not-a-row-anybody-published"}}}
    written, report = to_pydantic_ai_spec(document, "a")
    assert "model" not in written
    assert "model" in report.not_carried
    assert report.silent_losses == ()


def test_building_an_agent_does_not_require_the_credentials_to_run_it() -> None:
    """Inspecting what a document became must not need a provider endpoint.

    `Agent.__init__` otherwise calls `models.infer_model`, which constructs the
    provider and runs its environment checks then and there — so a locally-served
    row raised `UserError: Set the OLLAMA_BASE_URL environment variable` at
    CONSTRUCTION, before anybody asked for a model call. Where a model is served
    is deployment, which PACT does not own; the check belongs at the first run.
    """
    import dataclasses

    spec = AgentSpec(
        name="a", description="d", instructions="i", model="qwen2.5-7b-instruct"
    )
    agent = build_agent(dataclasses.replace(spec))
    assert agent.model == "ollama:qwen2.5:7b-instruct"


#: The name the host gives the one MCP server it wrapped its tool functions as.
#: Spelled differently from every tool, deliberately — `connect:` names a SERVER
#: and `uses:` names a TOOL, and the worked example's own comment records what it
#: cost to have those two coincide.
SERVER = "support-desk-mcp"


def _served_agent():
    """The agent the import tests below build a whole tree from.

    Two tools, one gated — the smallest shape that can tell "every tool got the
    line" from "the first one did", and "only the gated tool is gated" from
    "everything is".
    """
    from pydantic import BaseModel
    from pydantic_ai import Agent
    from pydantic_ai.models.test import TestModel

    class Verdict(BaseModel):
        decision: str
        escalate: bool

    source = Agent(
        TestModel(),
        name="Support Desk",
        description="answers support tickets",
        instructions="Be concise and kind.",
        output_type=Verdict,
    )

    @source.tool_plain(requires_approval=True)
    def refund(order_id: str, amount: float) -> str:
        """Refund an order."""
        return "ok"  # pragma: no cover

    @source.tool_plain
    def lookup(order_id: str) -> str:
        """Look up an order."""
        return "ok"  # pragma: no cover

    return source


def test_a_python_agent_becomes_a_tree_that_loads_and_comes_back_whole(
    tmp_path: Path,
) -> None:
    """The whole claim, both directions, through the real loader.

    A Pydantic AI agent defined in Python — the shape almost every existing one
    has — becomes a PACT tree that `pact check` accepts, and that tree becomes a
    Pydantic AI agent again with its tools, its approval and its answer shape
    intact.

    Everything this test adds by hand is something `ImportReport.still_to_write`
    named, and nothing else: the workspace file, a catalogue model, the
    `limits:` pair, and the server's endpoint. That is the measurement — if the
    report were wrong about what is owed, this would not load.

    The tool files and the resource file are written EXACTLY as the importer
    returned them. That is the part that changed: a tool file used to arrive
    with no `connect:`, `url:` or `says:`, so this test hand-wrote a `says:` line
    into every one of them — inventing a transport nobody chose, in the test that
    is supposed to be measuring what the importer produces.
    """
    import yaml
    from pydantic_ai.toolsets import FunctionToolset

    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")

    source = _served_agent()
    block, report = from_pydantic_ai_agent(source, connect=SERVER)
    assert report.silent_drops == ()

    (tmp_path / "agents" / "support-desk").mkdir(parents=True)
    (tmp_path / "tools").mkdir()
    (tmp_path / "resources").mkdir()
    (tmp_path / "workspace.yaml").write_text(
        yaml.safe_dump({"name": "Imported", "description": "from a Pydantic AI agent"})
    )
    block["model"] = "qwen2.5-7b-instruct"
    block["limits"] = {"steps-at-most": 8, "when-it-runs-out": "stop-and-say-so"}
    (tmp_path / "agents" / "support-desk" / "agent.yaml").write_text(
        yaml.safe_dump(block, sort_keys=False)
    )
    for name, body in tool_files_for(source, connect=SERVER).items():
        (tmp_path / "tools" / f"{name}.yaml").write_text(yaml.safe_dump(body, sort_keys=False))
    (tmp_path / "resources" / f"{SERVER}.yaml").write_text(
        yaml.safe_dump(resource_file_for(SERVER, "host/support-desk-mcp"), sort_keys=False)
    )

    checked = subprocess.run(
        [str(PACT_BIN), "check", str(tmp_path)], capture_output=True, text=True
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr

    # The approval did not merely survive the file — the loader agrees it gates.
    waits = json.loads(
        subprocess.run(
            [str(PACT_BIN), "waits", str(tmp_path)], capture_output=True, text=True, check=True
        ).stdout
    )
    assert [w["reason"] for w in waits["waits"]] == ["needs-approval"]
    assert waits["waits"][0]["question"] == "pact:question/is-this-ok"

    # And back again, with everything that crossed still on it.
    loaded = json.loads(
        subprocess.run(
            [str(PACT_BIN), "show", str(tmp_path)], capture_output=True, text=True, check=True
        ).stdout
    )
    returned = build_agent(
        AgentSpec.from_document(loaded, "support-desk", str(tmp_path)),
        call_tool=lambda n, a: "ok",
    )
    assert returned.model == "ollama:qwen2.5:7b-instruct"
    guarded = {
        name
        for toolset in returned.toolsets
        if isinstance(toolset, FunctionToolset)
        for name, tool in toolset.tools.items()
        if tool.requires_approval
    }
    assert guarded == {"refund"}
    assert set(returned.output_json_schema()["properties"]) == {"decision", "escalate"}


def test_the_tree_a_host_writes_needs_nothing_the_report_did_not_name(
    tmp_path: Path,
) -> None:
    """The import loop closes: every file comes from the importer, and it checks.

    This is the measurement the whole crossing is held to. A host imports a live
    Pydantic AI agent, writes the tree, and `pact check` exits 0 — and the ONLY
    keys it typed itself are the ones `ImportReport.still_to_write` asked for by
    name. Nothing here invents a transport, a description, an action or a shape.

    It used to be impossible. `tool_files_for` could not say where a tool
    reached, because a Pydantic AI tool is a Python function; every file it
    produced was refused with `loader/tool-reaches-nowhere`, and the only way to
    a green tree was for a person to hand-write a `says:`, `url:` or `connect:`
    into every tool file plus a `resources/` document PACT knew the shape of
    perfectly well. So the report's largest entry was the one an author was least
    equipped to act on.

    If the report is ever wrong about what is owed, this fails in one of two
    honest directions: `pact check` refuses (it asked for too little), or the
    subset assertion below fails (it asked for something already written).
    """
    import yaml

    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")

    source = _served_agent()
    block, report = from_pydantic_ai_agent(source, connect=SERVER)

    # ── everything typed by hand, in one place, each traced to its entry
    owed = "\n".join(report.still_to_write)
    by_hand = {
        # The workspace itself, which is the TREE and not the agent — no import
        # of one agent can know what the folder around it is called.
        "workspace.yaml": {"name": "Imported", "description": "from a Pydantic AI agent"},
        # "a catalogue row for `test:test` — the id came from the source"
        "model": "qwen2.5-7b-instruct",
        # "`limits:` with `steps-at-most:` AND `when-it-runs-out:`"
        "limits": {"steps-at-most": 8, "when-it-runs-out": "stop-and-say-so"},
        # "`endpoint:` in `resources/support-desk-mcp.yaml` — a name your
        # platform team publishes"
        "endpoint": "host/support-desk-mcp",
    }
    assert "catalogue row" in owed
    assert "`limits:` with `steps-at-most:` AND `when-it-runs-out:`" in owed
    assert f"`endpoint:` in `resources/{SERVER}.yaml`" in owed

    (tmp_path / "agents" / "support-desk").mkdir(parents=True)
    (tmp_path / "tools").mkdir()
    (tmp_path / "resources").mkdir()
    (tmp_path / "workspace.yaml").write_text(yaml.safe_dump(by_hand["workspace.yaml"]))
    block["model"] = by_hand["model"]
    block["limits"] = by_hand["limits"]
    (tmp_path / "agents" / "support-desk" / "agent.yaml").write_text(
        yaml.safe_dump(block, sort_keys=False)
    )

    # Not one key added to either kind of file. `dict(body)` is a copy, so a
    # test that started editing them again would be visible as an edit here.
    for name, body in tool_files_for(source, connect=SERVER).items():
        assert set(body) == {"description", "connect", "actions"}, (
            f"{name} is not the file the importer returned"
        )
        (tmp_path / "tools" / f"{name}.yaml").write_text(yaml.safe_dump(dict(body)))
    server = resource_file_for(SERVER, by_hand["endpoint"])
    (tmp_path / "resources" / f"{SERVER}.yaml").write_text(yaml.safe_dump(dict(server)))

    checked = subprocess.run(
        [str(PACT_BIN), "check", str(tmp_path)], capture_output=True, text=True
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr

    # And the report did not go on asking for the line the host had written. An
    # entry naming `tool-reaches-nowhere` here would be a checklist telling this
    # author to do the work they just did — which is how a checklist stops being
    # read at all.
    assert "tool-reaches-nowhere" not in owed


def test_the_line_a_tool_reaches_by_is_written_for_every_tool_or_for_none() -> None:
    """`connect=` is the host's answer, and it lands in each tool's own file.

    Both halves are load-bearing and each has its own failure. Written into no
    file, `pact check` refuses every tool with `loader/tool-reaches-nowhere` and
    the tree cannot load. Written into one file and not its sibling, the tree
    loads and the agent is offered a tool whose every call comes back `error: no
    tool named 'lookup'` — a partial import that looks complete, which is worse
    than the refusal.

    And absent when nothing was passed: a `connect:` PACT chose for itself would
    name a server nobody stood up, and `names: resources` would refuse it at the
    line the importer typed rather than at anything an author wrote.
    """
    source = _served_agent()

    served = tool_files_for(source, connect=SERVER)
    assert set(served) == {"lookup", "refund"}
    assert [body["connect"] for body in served.values()] == [SERVER, SERVER]

    bare = tool_files_for(source)
    for name, body in bare.items():
        assert "connect" not in body, f"{name} was wired to a server nobody named"
        assert "url" not in body and "says" not in body

    # The rest of the file is the same either way — `connect:` adds a line, it
    # does not change what the tool can do or who has to approve it.
    assert served["refund"]["actions"] == bare["refund"]["actions"]
    assert served["refund"]["actions"]["call"]["needs-a-person"] == "yes"


def test_a_host_that_answered_where_the_tools_reach_is_not_asked_again() -> None:
    """The checklist shrinks when the host answers, and names what is left.

    `still_to_write` is a list a no-code author works through, and its longest
    entry was the one they could do least about: *a PACT tool has to say WHERE it
    reaches, and a Python function is not somewhere a second runtime can reach*.
    A host that wrapped those functions as one MCP server has answered it, and
    the answer is in the files.

    What replaces the entry matters as much as its going. Silence would be a lie
    in the other direction: `resources/<server>.yaml` still needs an `endpoint:`,
    that endpoint is a name the platform team publishes, and nothing in a
    Pydantic AI agent carries it. So the entry does not disappear — it shrinks to
    the one fact that genuinely came from outside.
    """
    source = _served_agent()

    _, alone = from_pydantic_ai_agent(source)
    lonely = [s for s in alone.still_to_write if "tool-reaches-nowhere" in s]
    assert len(lonely) == 1, alone.still_to_write

    _, served = from_pydantic_ai_agent(source, connect=SERVER)
    assert not [s for s in served.still_to_write if "tool-reaches-nowhere" in s]
    named = [s for s in served.still_to_write if s.startswith("`endpoint:`")]
    assert len(named) == 1, served.still_to_write
    assert f"resources/{SERVER}.yaml" in named[0]
    # The credential is named as the author's to add and never guessed at, which
    # is the same sentence `resource_file_for` refuses to write for them.
    assert "by-reference" in named[0]

    # Nothing else on the list moved. The connection answer is about ONE entry,
    # and a shrink that quietly dropped `evals:` or the catalogue row would be
    # this mechanism hiding work rather than doing it.
    assert set(alone.still_to_write) - set(served.still_to_write) == set(lonely)
    assert set(served.still_to_write) - set(alone.still_to_write) == set(named)

    # An agent with no tools has no connection to declare, so it is told what it
    # is actually missing rather than being handed a server to point at nothing.
    from pydantic_ai import Agent
    from pydantic_ai.models.test import TestModel

    _, empty = from_pydantic_ai_agent(Agent(TestModel()), connect=SERVER)
    assert any(s.startswith("`uses:`") for s in empty.still_to_write)
    assert not [s for s in empty.still_to_write if s.startswith("`endpoint:`")]


def test_a_server_file_carries_two_references_and_never_a_credential() -> None:
    """`resources/<name>.yaml` is four lines, and none of them is a secret.

    `endpoint:` and `auth:` are both references the host resolves — never a
    value, never a command, never arguments — because honouring a command there
    would make reviewing an untrusted workspace an act of running its code
    (§11.5). So this writes the endpoint it was HANDED and does not invent an
    `auth:` line: a guessed credential reference produces a file that loads
    clean and cannot connect, and `pact check` does not require the field, so
    nothing downstream would ever catch it.
    """
    body = resource_file_for(SERVER, "host/support-desk-mcp")
    assert body["resource-kind"] == "mcp-server"
    assert body["endpoint"] == "host/support-desk-mcp"
    assert "auth" not in body
    assert "asks-to-connect" not in body
    assert SERVER in body["description"]


def test_a_server_that_reaches_nowhere_is_refused_rather_than_written() -> None:
    """An endpoint-less server would load clean and connect to nothing.

    `endpoint:` is not `required:` in the schema, so `endpoint: ''` passes `pact
    check` — and every tool that names this server then reaches a server that
    goes nowhere. That is `loader/tool-reaches-nowhere` one hop further along,
    where no rule is looking, so it is refused here where the caller can still
    see it. The message names what to ask for, because the endpoint is the
    platform team's word and not the caller's to make up.
    """
    with pytest.raises(ValueError) as refused:
        resource_file_for(SERVER, "   ")
    assert "platform team" in str(refused.value)
    assert SERVER in str(refused.value)


def test_the_connection_question_reaches_the_scheduler_as_a_wait(
    tmp_path: Path,
) -> None:
    """`asks-to-connect:` is a person's yes, and it must be on the list of waits.

    A run that will stop and ask before it may use a connection is a run
    something has to hold a timer for. `pact waits` is what a scheduler reads,
    and the loader reaches this question the way a RUN does — `uses:` names a
    tool, the tool's `connect:` names a server, the server carries the question.
    Every hop is one this importer now writes, so a wrong name in any of them
    would take a human consent gate off that list in silence.
    """
    import yaml

    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")

    source = _served_agent()
    block, _ = from_pydantic_ai_agent(source, connect=SERVER)
    block["model"] = "qwen2.5-7b-instruct"
    block["limits"] = {"steps-at-most": 8, "when-it-runs-out": "stop-and-say-so"}

    (tmp_path / "agents" / "support-desk").mkdir(parents=True)
    (tmp_path / "tools").mkdir()
    (tmp_path / "resources").mkdir()
    (tmp_path / "questions").mkdir()
    (tmp_path / "workspace.yaml").write_text(
        yaml.safe_dump({"name": "Imported", "description": "from a Pydantic AI agent"})
    )
    (tmp_path / "agents" / "support-desk" / "agent.yaml").write_text(
        yaml.safe_dump(block, sort_keys=False)
    )
    for name, body in tool_files_for(source, connect=SERVER).items():
        (tmp_path / "tools" / f"{name}.yaml").write_text(yaml.safe_dump(dict(body)))
    (tmp_path / "resources" / f"{SERVER}.yaml").write_text(
        yaml.safe_dump(
            resource_file_for(
                SERVER, "host/support-desk-mcp", asks_to_connect="may-we-connect"
            ),
            sort_keys=False,
        )
    )
    # The one file `asks_to_connect=` obliges its caller to write: the name is a
    # `names: questions` reference, so a workspace without it is refused with
    # `schema/no-such-name` rather than loading and asking nobody.
    (tmp_path / "questions" / "may-we-connect.yaml").write_text(
        yaml.safe_dump(
            {
                "description": "Asks a person to allow this desk to use the server.",
                "says": "May we use the support-desk connection for this?",
                "answer": {"approved": "yes or no"},
                "asked-of": ["support-leads"],
                "answer-within": "30m",
                "if-nobody-answers": "stop-and-say-so",
            }
        )
    )

    checked = subprocess.run(
        [str(PACT_BIN), "check", str(tmp_path)], capture_output=True, text=True
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr

    waits = json.loads(
        subprocess.run(
            [str(PACT_BIN), "waits", str(tmp_path)], capture_output=True, text=True, check=True
        ).stdout
    )
    asked = {(w["reason"], w["question"]) for w in waits["waits"]}
    assert ("needs-permission", "may-we-connect") in asked, waits
    # And the approval gate the import already carried is still on the list —
    # one wait taking another's place would be the same silence, reversed.
    assert ("needs-approval", "pact:question/is-this-ok") in asked, waits


def test_the_skills_the_author_wrote_reach_the_model(document: dict) -> None:
    """A skill is a document to READ, and it reaches the model as text.

    `SkillSpec.in_words()` is used rather than a shape invented here, for the
    reason that class's own docstring gives: two ports producing different bytes
    for the same skill is the divergence the one method exists to stop.
    """
    other = AgentSpec.from_document(document, "policy-checker", str(EXAMPLE))
    if not other.skills:
        pytest.skip("this agent names no skills")
    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models.function import FunctionModel

    agent = build_agent(other, call_tool=lambda n, a: "ok")
    # What the model is SENT, read through a model that keeps it — not off the
    # agent's private attributes, whose shape moved between 2.21 and 2.54.
    sent: list[str] = []

    def keep(messages, info):  # type: ignore[no-untyped-def]
        sent.append(messages[-1].instructions or "")
        return ModelResponse(parts=[TextPart("ok")])

    from pydantic_ai.exceptions import UnexpectedModelBehavior

    # The agent answers with a shape `ok` does not fit; what was SENT is the
    # question here, so the run ending in a refused answer is beside the point.
    with contextlib.suppress(UnexpectedModelBehavior):
        agent.run_sync("hello", model=FunctionModel(keep))
    said = "\n\n".join(sent)
    for skill in other.skills:
        assert skill.name in said, f"the skill {skill.name} never reached the model"
