"""A PACT agent held by Pydantic AI is still a PACT agent, and says so member by member.

`pydantic_ai_interop.build_agent()` is one door: it hands somebody a real
`pydantic_ai.Agent` — their stack, their loop — and its own docstring names
everything that stops being enforced on the way over (`loop:`, `interceptors:`,
`teamwork:`, `context-policy:`, `when-it-runs-out:`).

`PactAgent` is the other shape of the same wish, and it is the one that keeps
the guarantees. The OBJECT is a `pydantic_ai.agent.abstract.AbstractAgent`, so
it goes wherever an `Agent` goes; the LOOP is still PACT's (decision D12 /
FR-4.1.1), because `run()` lowers to `harness.run(spec,
PydanticAITransport(...))` and Pydantic AI is only the model transport.

That trade buys a *surface*, and a surface is exactly where a shim can lie. This
SDK asks eleven abstract members what the agent is, believes every answer, and
shows them to people: `model` decides which provider is dialled, `name` reaches
the traces, `output_type` decides what the model is shown, `toolsets` is what
`from_pydantic_ai_agent` reads back out. A member answered with this SDK's
default instead of the author's document is a silent divergence between what
`pact check` printed OK for and what a caller sees.

Two members cannot be answered from a PACT document at all, and the rule for
both is the repository's own: **translate or nothing**, said out loud.

* `iter()` hands out a live handle onto `_agent_graph`'s node stream. PACT's
  loop is `harness.run` — stages, an interceptor chain, a gate, ceilings — and
  has no node stream to hand back.
* a caller-supplied `usage_limits=` would be a SECOND enforcer of ceilings
  `limits.py` already enforces, and the second one wins by raising.

Both must refuse with the reason. A refusal with no reason is the same defect as
a silent drop: the caller's next move depends entirely on why.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.ir import AgentSpec, SkillSpec  # noqa: E402
from pact_adapters.loops import STANDARD, Loop  # noqa: E402
from pact_adapters.pydantic_ai_interop import (  # noqa: E402
    _output_type_for,
    _takes_as_schema,
    _toolsets_to_pact,
    build_agent,
    pydantic_ai_model_id,
)
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.pydantic_ai_transport import (  # noqa: E402
    PydanticAITransport,
)

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"

pydantic_ai = pytest.importorskip("pydantic_ai")

from pydantic_ai.exceptions import UserError  # noqa: E402

#: What a refusal is allowed to be. Three types rather than one, because WHICH
#: exception a shim raises is a matter of taste and WHAT IT SAYS is not — every
#: test below reads the message. `TypeError` is deliberately absent: a signature
#: that does not accept `usage_limits=` at all raises one, and that would let a
#: shim pass the refusal tests by not having the argument.
REFUSALS = (NotImplementedError, UserError, ValueError)

#: The prompt every run below is given. A real sentence rather than `"hi"`,
#: because two of these tests refuse BEFORE anything runs and a reader has to be
#: able to tell that the refusal is not about the prompt.
ASK = "refund order A-1"

#: What a run that answers properly says: the author's three `answers-with:`
#: fields as JSON, which is what the unset mode (`prompted`) asks the model for.
ANSWERED = json.dumps(
    {"decision": "approved", "reason": "the item arrived faulty", "amount": "40 USD"}
)


class Watching(PydanticAITransport):
    """The scripted transport, keeping what each model call was handed.

    The same shim `test_portability.py` puts around a transport, and it is here
    for the one claim a run's own result cannot make: what the model was SHOWN.
    A member of this class that answers from this SDK's default instead of the
    author's document is invisible in the answer — the script says the same
    thing whatever it is told — and visible only in the system text and the tool
    list that reached the call.
    """

    def __init__(self, script: Script) -> None:
        super().__init__(script)
        self.systems: list[str] = []
        self.offered: list[list[str]] = []

    async def model_call(self, system: Any, history: Any, tools: Any) -> Any:
        self.systems.append(system)
        self.offered.append(sorted(str(t.get("name", "")) for t in (tools or ())))
        return await super().model_call(system, history, tools)


def answering(spec: AgentSpec, **how: Any) -> Any:
    """One agent over the standard loop, driven by a script that answers at once.

    `pact:loop/standard` rather than the document's own `careful`, because every
    test that uses this is about a member or an argument rather than about the
    stages — and the four-stage loop would make each of them spend four turns
    proving something the first turn already showed.
    """
    return held(
        dataclasses.replace(spec, loop=Loop.from_library(STANDARD)),
        transport=Watching(Script([Turn(ANSWERED)])),
        tool_impls={"zendesk": lambda args: "T-1: lamp, broken", "payments": lambda a: "ok"},
        **how,
    )


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


def held(spec: AgentSpec, **how: Any) -> Any:
    """One PACT agent, as an object this SDK can hold.

    Imported here and not at the top of the file so that each test fails on its
    own name. A module-level import of a module that does not exist yet collapses
    the whole file into a single collection error, and a suite written before the
    code is a list of the things that are missing — one line per missing thing.

    **Nothing but the spec is required to HOLD one**, which is the same rule
    `build_agent` follows and for the reason its `defer_model_check=True` comment
    gives: a caller inspecting what a PACT document became — which tools, which
    answer shape, which model id — needs no endpoint and no credentials, and
    asking for a transport here would make every one of those inspections a
    deployment question.
    """
    from pact_adapters.pact_agent import PactAgent

    return PactAgent.for_spec(spec, **how)


def _marker(output_type: Any) -> Any:
    """The class that says HOW the shape is put to the model.

    `_output_type_for` returns either a bare `str` or an instance of one of three
    marker classes, and the markers do not compare equal to one another by value
    (`PromptedOutput(...) == PromptedOutput(...)` is False on 2.21), so the
    comparable thing is the class.
    """
    return output_type if isinstance(output_type, type) else type(output_type)


def _asked(agent: Any, entry: str, **how: Any) -> Any:
    """One run, through whichever of the two entry points is under test.

    Both are covered because `run_sync` is concrete on `AbstractAgent` and
    delegates to `self.run` — which is true today and is a fact about the SDK, not
    about this shim. A refusal implemented on `run` alone would stop covering
    `run_sync` the release that stops delegating, and nothing would say so.
    """
    if entry == "run_sync":
        return agent.run_sync(ASK, **how)
    return asyncio.run(agent.run(ASK, **how))


# ───────────────────────────────────────── it is an agent, not a look-alike


def test_a_pact_agent_is_one_this_sdk_can_hold_and_not_a_look_alike(spec: AgentSpec) -> None:
    """An unanswered member fails at construction, in somebody else's code.

    `AbstractAgent` has eleven abstract members on pydantic-ai-slim 2.21 and
    Python refuses to instantiate a subclass missing any one of them. So the
    failure does not arrive where the missing member is read — it arrives at
    `for_spec()`, as `TypeError: Can't instantiate abstract class`, naming a
    member the caller never asked for and giving no reason at all.

    And being a real subclass rather than a duck-typed twin is the whole point of
    the class: everything typed against `AbstractAgent` (`to_cli`, a router
    holding a mix of agents, a host's own annotations) refuses an object that
    merely has the same method names.

    The seven data members are then READ, because `root_capability` on this same
    class is the shape of the bug this catches: a concrete property that raises
    `NotImplementedError`, which satisfies `__abstractmethods__` and explodes the
    first time anybody looks at it.
    """
    from pydantic_ai.agent.abstract import AbstractAgent

    agent = held(spec)
    assert isinstance(agent, AbstractAgent), (
        "a look-alike is refused by everything typed against AbstractAgent"
    )
    assert type(agent).__abstractmethods__ == frozenset(), (
        "an abstract member left over is a TypeError at for_spec(), not at the read"
    )
    for member in sorted(
        AbstractAgent.__abstractmethods__ - {"iter", "override", "__aenter__", "__aexit__"}
    ):
        getattr(agent, member)


# ───────────────────────────────────────────────── what each member answers


@pytest.mark.parametrize(
    "row,said",
    [
        ("qwen2.5-7b-instruct", "ollama:qwen2.5:7b-instruct"),
        ("claude-opus-5", "anthropic:claude-opus-5"),
    ],
)
def test_the_model_is_the_catalogue_row_in_this_sdks_own_id_scheme(
    spec: AgentSpec, row: str, said: str
) -> None:
    """A copied catalogue name loads and then kills every run.

    Measured on a real round trip and recorded in `pydantic_ai_model_id`'s own
    docstring: a `model:` copied across produced a document whose every run died
    on `UserError: Unknown model: qwen2.5-7b-instruct`. The two id schemes are
    not the same thing — PACT binds a catalogue ROW (a name with a window, a
    price and a provenance beside it) and this SDK binds `provider:name` — and
    the row already holds both halves in `served-by:` and `also-known-as:`, so
    this is a lookup and never a guess.

    Asserted on the PROPERTY and not only on what a run dials, because a caller
    who prints `agent.model` to decide whether to run is entitled to the id that
    would actually be used.
    """
    pinned = dataclasses.replace(spec, model=row)
    agent = held(pinned)
    assert agent.model == said
    assert agent.model == pydantic_ai_model_id(row, spec.workspace)[0]
    # The other door into this SDK translates the same row the same way. Two
    # doors that disagree about which model a document names is one document
    # running on two models, which is the divergence this repository exists to
    # remove.
    assert agent.model == build_agent(pinned).model


@pytest.mark.parametrize("row", ["not-a-row-anywhere", ""])
def test_a_model_this_sdk_has_no_id_for_is_none_rather_than_a_name_that_fails_later(
    spec: AgentSpec, row: str
) -> None:
    """`None` is a caller who still has options; a bad id is a dead run.

    The worked example pins no `model:` at all, and `ir.AgentSpec.model` records
    that this is a different fact from choosing the default: PACT resolves one
    from `models/catalog.yaml` against `needs:`. Answering either the unpinned or
    the untranslatable case with a STRING would put a name into `agent.model`
    that `infer_model` rejects, and a reader of that property has no way to tell
    it from a working one — `Agent(None)` is legal and defers the choice to
    `run(model=...)`, which is a caller who can still fix it.
    """
    agent = held(dataclasses.replace(spec, model=row))
    assert agent.model is None


def test_the_name_and_description_are_the_authors_own_words(spec: AgentSpec) -> None:
    """Left unanswered, this SDK names the agent after the caller's local variable.

    `AbstractAgent._infer_name` walks the calling frame and takes the name the
    object was assigned to, so an agent whose author wrote `name: Refund Desk`
    turns up in somebody's traces as `a` or `bot`. The key is the other wrong
    answer: `refund-desk` is a FOLDER, and `ir.AgentSpec.key` exists precisely
    because the two are not the same string — one is what a diagnostic has to
    name, the other is what a person reads.
    """
    agent = held(spec)
    assert agent.name == spec.name == "Refund Desk"
    assert agent.name != spec.key, "the folder name is not the agent's name"
    assert agent.description == spec.description
    other = build_agent(spec)
    assert (agent.name, agent.description) == (other.name, other.description), (
        "two doors into this SDK, two names for one document"
    )


def test_the_deps_type_is_the_run_inputs_mapping_and_not_a_class_invented_here(
    spec: AgentSpec,
) -> None:
    """What the surrounding system supplies is a mapping the author named the keys of.

    `harness.run` takes `run_inputs` as a `Mapping[str, Any]` keyed by the
    author's own `run-inputs:` names, so `dict` is what a caller passes as `deps=`
    and `dict` is what this must say. The two wrong answers are wrong in opposite
    directions:

    * `object` — this SDK's own default, and what `build_agent` leaves behind —
      tells a caller nothing at all, so nobody passes anything. The measured
      shape of that is in `harness.run`'s docstring: the payments tool received
      `{order-number, amount, action}` and never `customer-id`, so *whose order*
      went on being something nobody supplied.
    * a class synthesised from the run-input names is what
      `_AGENT_NOT_PORTABLE['deps_type']` refuses in the other direction, in one
      sentence: PACT's `run-inputs:` names what is supplied and the shape of
      each, and *does not name a class, because a class is not portable to
      another language*. Inventing one here would put the untranslatable thing
      back on the agent.
    """
    agent = held(spec)
    assert spec.run_inputs == ("customer-id",), "the example declares one run input"
    assert agent.deps_type is dict
    assert isinstance(agent.deps_type, type), "the SDK annotates this `-> type`"


MODES = ["", "prompted", "native-json-schema", "tool", "text"]


@pytest.mark.parametrize("mode", MODES)
def test_the_answer_shape_is_the_one_this_repository_already_decided(
    spec: AgentSpec, mode: str
) -> None:
    """A second mode table is how one document comes to answer in two shapes.

    `_output_type_for` is where PACT's four `answers-with-mode:` words map onto
    `str`, `PromptedOutput`, `NativeOutput` and `ToolOutput` — and it carries the
    line that a re-implementation would get wrong without noticing: **unset is
    `prompted`, not `auto`**. `auto` is resolved per model from
    `ModelProfile.default_structured_output_mode`, so an agent built that way
    answers one shape under PACT's harness and another here, from the same file,
    for a reason that has nothing to do with the agent.

    Both halves are checked because either alone passes a broken shim: the marker
    class says HOW the shape is put, and `output_json_schema()` says WHAT the
    model is actually shown.
    """
    said = dataclasses.replace(spec, answers_with_mode=mode)
    agent = held(said)
    assert _marker(agent.output_type) is _marker(_output_type_for(said)), (
        f"`answers-with-mode: {mode or '(unset)'}` was decided a second time"
    )
    assert agent.output_json_schema() == build_agent(said).output_json_schema()


def test_the_toolsets_name_the_authors_tools_and_can_be_read_without_a_run(
    spec: AgentSpec,
) -> None:
    """Read back by the importer this repository already has, because that is who reads it.

    `_toolsets_to_pact` is what `from_pydantic_ai_agent` uses to see what a live
    agent holds, and it is deliberately STATIC: a toolset whose tools are
    resolved per run against a `RunContext` has no list to read, and it reports
    that rather than carrying four of nine tools. So a `PactAgent` whose tools
    are only knowable inside a run imports back as a PACT document with no
    `uses:` at all — the tools the author wrote, gone, through the one class
    whose entire claim is that the document survives being held.

    The `takes:` block is checked against `_takes_as_schema` for the same reason
    the mode table is checked against `_output_type_for`: it is the schema the
    model is shown, and two builders of it is two things the model is shown.
    """
    agent = held(spec)
    uses, tools, notes = _toolsets_to_pact(agent)
    assert uses == sorted(t.name for t in spec.tools) == ["payments", "zendesk"]
    assert notes == {}, "a tool nobody can see without a run is a tool that imports back as nothing"
    for tool in spec.tools:
        assert tools[tool.name]["description"] == tool.description
        assert tools[tool.name]["parameters"] == _takes_as_schema(tool.parameters)


def test_an_event_stream_handler_is_the_callers_own_and_none_when_nobody_passed_one(
    spec: AgentSpec,
) -> None:
    """A dropped handler is a caller watching a stream that was never going to arrive.

    `event_stream_handler` is how a Pydantic AI caller watches a run as it
    happens. PACT's own events go to `events.Bus`, which this SDK's callers do
    not hold and have no way to subscribe to — so this property is the entire
    bridge, and a shim that answered `None` regardless would leave somebody's UI
    blank with no error anywhere, because the SDK asks the property once and
    believes the answer.

    Identity and not equality: a handler is a callable the caller owns, and
    wrapping it in something built here would mean the object they can compare
    against is not the object that runs.
    """

    async def watch(ctx: Any, stream: Any) -> None:  # pragma: no cover - never called here
        return None

    assert held(spec).event_stream_handler is None, "nobody passed one"
    assert held(spec, event_stream_handler=watch).event_stream_handler is watch


def test_the_toolset_is_named_and_a_document_with_no_tools_offers_none(
    spec: AgentSpec,
) -> None:
    """A toolset with no id, or one invented per run, imports back as nothing.

    `_toolsets_to_pact` reads a live agent's toolsets by walking them and
    reporting the ones it cannot; the id is how a reader of a mixed agent tells
    the tools that came out of a PACT document from the ones a host bound
    itself. And an agent whose author wrote no `uses:` at all must offer NO
    toolset rather than an empty one: an empty `ExternalToolset` is a claim that
    this agent has tools and none of them are visible, which is the exact report
    `_toolsets_to_pact` reserves for a toolset it could not read.
    """
    agent = held(spec)
    assert [getattr(t, "id", None) for t in agent.toolsets] == ["pact"]
    assert sum(len(t.tool_defs) for t in agent.toolsets) == len(spec.tools) == 2
    assert held(dataclasses.replace(spec, tools=())).toolsets == (), (
        "a document with no tools produced a toolset anyway"
    )


def test_the_system_text_is_the_one_the_first_stage_is_actually_given(
    spec: AgentSpec,
) -> None:
    """The inherited answer is `[]`, and it is the answer nobody would notice.

    `AbstractAgent.system_prompt_parts` returns an empty list with a `# pragma:
    no cover` beside it, so an agent that does not override it claims to have no
    system prompt at all — and this method is what a UI adapter, a history
    reconstruction or a `to_cli` session reads to show a person what the agent
    was told.

    Asserted against the string that reached the MODEL rather than against a
    copy written here, because the two are one thing or they are two: the
    instructions, the stage's own line, the skills that stage may read and the
    author's `answers-with:` arrive in one order and not two. Both halves of
    that text are then named on their own, since a system prompt missing its
    skill and a system prompt missing its answer shape are the same length as
    one that has neither.
    """
    agent = answering(spec)
    agent.run_sync(ASK)
    said = asyncio.run(agent.system_prompt_parts())

    assert [part.content for part in said] == [agent._transport.systems[0]], (
        "what this method reports is not what the run's first step was given"
    )
    assert spec.skills and spec.skills[0].name in said[0].content, (
        "the skills this stage may read did not reach the system text, so the "
        "agent is answering a refund question with the refund policy withheld"
    )
    for field, shape in spec.answers_with.items():
        assert f"{field}: {shape}" in said[0].content, (
            f"the author's `answers-with:` names {field!r} as {shape!r} and the "
            f"model is never asked for it"
        )


def test_an_agent_told_nothing_says_it_was_told_nothing(spec: AgentSpec) -> None:
    """An empty system prompt is `[]`, not one part carrying an empty string.

    The other half of the method above, and the reason it is a separate test: a
    `SystemPromptPart(content="")` is a message this crossing invented. It
    reaches a provider as an empty system turn, and everything that counts
    messages — a context policy, a token ceiling, a UI showing what the agent
    was told — counts one that nobody wrote.
    """
    bare = dataclasses.replace(
        spec, instructions="", skills=(), answers_with={}, answers_with_mode="text"
    )
    assert asyncio.run(held(bare).system_prompt_parts()) == []


def test_the_answer_shape_reaches_the_system_text_only_when_the_author_asked(
    spec: AgentSpec,
) -> None:
    """`answers-with-mode: text` is an author saying *do not ask for a shape*.

    Unset means `prompted` — the shape is put to the model in words — and `text`
    means it is not put to the model at all. One mode table decides both
    (`_output_type_for`), and a system prompt that names the fields anyway is
    that decision made a second time in the one place a reader cannot see it:
    the model is asked for JSON while the declared output type says a string.
    """
    written = asyncio.run(held(spec).system_prompt_parts())[0].content
    unshaped = asyncio.run(
        held(dataclasses.replace(spec, answers_with_mode="text")).system_prompt_parts()
    )[0].content

    asked_for = [f"{field}: {shape}" for field, shape in spec.answers_with.items()]
    assert all(line in written for line in asked_for)
    assert not any(line in unshaped for line in asked_for), (
        "an author who asked for text was still asked for a shape"
    )
    assert unshaped and unshaped in written, (
        "the two system texts differ by more than the answer shape"
    )


def test_the_name_this_sdk_writes_back_is_the_name_it_reads(spec: AgentSpec) -> None:
    """`_infer_name` ASSIGNS, and a setter that drops the value loses the run.

    `AbstractAgent._infer_name` walks the calling frame when a run starts on an
    agent with no name and writes what it finds through the name setter — and
    `to_cli` and several of this SDK's own helpers set both members directly. A
    setter that keeps nothing leaves the object reporting the old value while
    the caller believes they renamed it, and the agent is then unfindable in
    whatever traced it under the name they chose.
    """
    agent = held(spec)
    agent.name = "the desk on the second floor"
    agent.description = "what it does now"
    assert agent.name == "the desk on the second floor"
    assert agent.description == "what it does now"
    assert held(spec).name == spec.name, "the setter wrote onto every agent at once"


def test_the_model_the_document_pins_is_the_one_the_run_is_priced_on(
    spec: AgentSpec,
) -> None:
    """A transport built without the pin runs a document on somebody else's row.

    `for_spec(spec, script=…)` is the door that builds the transport itself, so
    the model binding is this class's to get right: the row comes from `model:`
    (or, unpinned, from `needs:` against the catalogue), and the WORKSPACE goes
    with it because a row a workspace added to its own `models/catalog.yaml`
    prices and sizes nothing otherwise.

    Priced and not merely named, because the id is a string nobody checks until
    a bill arrives: `cost-per-request-under:` is measured against the catalogue
    price of the bound row, so an agent built on the wrong row reports a spend
    of zero and a ceiling that can never fire — which this example's own
    `never_reached` sentence says out loud for the free row it resolves by
    default.
    """
    pinned = dataclasses.replace(
        spec, model="claude-opus-5", loop=Loop.from_library(STANDARD)
    )
    priced = held(pinned, script=Script([Turn(ANSWERED)])).run_sync(ASK)
    assert priced.pact.used is not None and priced.pact.used.money > 0, (
        "the run was priced at nothing, so the author's spend cap is measured "
        "against a model nobody bound"
    )
    assert priced.pact.never_reached == (), (
        "a ceiling reported unreachable on a priced row means the row did not "
        "reach the transport"
    )
    free = held(
        dataclasses.replace(spec, loop=Loop.from_library(STANDARD)),
        script=Script([Turn(ANSWERED)]),
    ).run_sync(ASK)
    assert free.pact.used is not None and free.pact.used.money == 0, (
        "this document resolves a row this machine serves for nothing, so a "
        "price here means the pin above proved nothing"
    )


#: A row no distribution has ever heard of, written the way §4.2 says a
#: workspace writes one: `models/catalog.yaml` beside `workspace.yaml`, layered
#: over the distribution's rows one row at a time.
A_ROW_ONLY_THIS_BOX_HAS = """
models:
  the-box-in-the-corner:
    family: local
    tier: mid
    served-by:
      - { runtime: ollama, endpoint: local }
    capabilities:
      tool-calling: parallel
      modality-in: [text]
      modality-out: [text]
      context-window:
        value: 8192
        provenance:
          source: the serving configuration on this machine
          date: 2026-08-06
          as-of: 2026-08-06
          recorded-by: nobody@example.com
    cost: { input-per-mtok: 3 USD, output-per-mtok: 15 USD }
"""


def test_a_row_this_workspace_added_itself_is_the_row_the_run_is_priced_on(
    spec: AgentSpec, tmp_path: Path
) -> None:
    """The workspace goes to the transport with the model, or the override layer is dead.

    A workspace-local `models/catalog.yaml` is what an author on an air-gapped
    box serving a model this distribution has never heard of writes — §4.2 makes
    it normative and `load_catalogue` layers it row by row. It is reachable only
    if whoever builds the transport passes the workspace along with the model
    id: without it the row is unknown, `can_price` says no, and the author's
    `cost-per-request-under:` lands on `RunResult.unmetered` — a spend cap they
    wrote, measured by nothing, on a machine whose whole reason for the override
    layer was that this is the only way out.
    """
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "catalog.yaml").write_text(A_ROW_ONLY_THIS_BOX_HAS)
    local = dataclasses.replace(
        spec,
        loop=Loop.from_library(STANDARD),
        model="the-box-in-the-corner",
        workspace=str(tmp_path),
    )
    result = held(local, script=Script([Turn(ANSWERED)])).run_sync(ASK)

    assert result.pact.used is not None and result.pact.used.money > 0, (
        "the workspace's own row never reached the transport, so this run was "
        "priced by nothing"
    )
    assert "cost-per-request-under" not in " ".join(result.pact.unmetered), (
        f"the author's spend cap was reported unmeasurable on a row their own "
        f"workspace priced: {result.pact.unmetered}"
    )


# ────────────────────────────── the two that must refuse, with the reason


def test_iter_refuses_with_the_reason_and_not_a_bare_not_implemented(spec: AgentSpec) -> None:
    """There is no graph to iterate, and the caller's next move depends on knowing why.

    `iter()` hands back an `AgentRun`: a live handle onto `_agent_graph`'s node
    stream, with `next()`, `.result`, `.usage()` and the node vocabulary
    (`is_model_request_node` and the rest). A `PactAgent` runs PACT's harness —
    named stages, an interceptor chain, a gate, the author's ceilings — and has
    no node stream of that shape to hand back. Emulating one would mean inventing
    node boundaries PACT does not have, which is the opaque wrapping *translate
    or nothing* forbids.

    A bare `NotImplementedError` has an EMPTY `str()`. A caller who meets one
    learns only that the method exists and does nothing — where the two real next
    moves are opposite: use `run()`, which is the same loop and the same
    guarantees, or use `build_agent()` and accept that the loop stops being
    PACT's. Nothing but the reason distinguishes them.

    `run_stream` and `run_stream_sync` bottom out here too, so this message is
    what a caller who asked to stream will read.
    """
    agent = held(spec)

    async def iterate() -> None:
        async with agent.iter(ASK):
            pass  # pragma: no cover - reaching the body is the failure

    with pytest.raises(REFUSALS) as trouble:
        asyncio.run(iterate())

    said = str(trouble.value)
    assert said.strip(), "a bare NotImplementedError carries no message at all"
    assert "_agent_graph" in said, "name the thing that does not exist here"
    assert "harness" in said, "name whose loop this is instead"
    assert "run" in said, "name what to call instead"


@pytest.mark.parametrize("entry", ["run", "run_sync"])
def test_a_caller_supplied_usage_limits_is_refused_rather_than_enforced_twice(
    spec: AgentSpec, entry: str
) -> None:
    """Two enforcers of one ceiling, and this SDK's wins by raising.

    `UsageLimits` has exactly one behaviour: raise `UsageLimitExceeded`. Every
    PACT ceiling carries the author's own `when-it-runs-out:`, and the worked
    example's is `ask-a-person` — so a run that reached the step ceiling under a
    caller-supplied `UsageLimits` would die with a traceback at precisely the
    point the document says to park and ask somebody. The author's line is not
    degraded, it is discarded, and nothing records that it was.

    `usage_limits_for()` exists for the OTHER door — the host that called
    `build_agent()` and drives `Agent.run` itself — and the reason filed beside
    it says why it has no business here: *PACT's own runs enforce these ceilings
    in `limits.py`, which is why this is not a second enforcer.* Accepting the
    argument on this class would make it one.

    Refused before anything runs, so no model is dialled and no money is spent
    finding out that the ceiling belongs to somebody else.
    """
    from pydantic_ai.usage import UsageLimits

    agent = held(spec)
    assert spec.limits.when_it_runs_out.value == "ask-a-person", (
        "the example's ceiling parks for a person, which is what UsageLimits cannot do"
    )

    with pytest.raises(REFUSALS) as trouble:
        _asked(agent, entry, usage_limits=UsageLimits(request_limit=1))

    said = str(trouble.value)
    assert "usage_limits" in said, "name the argument that was refused"
    assert "when-it-runs-out" in said, "name what a second enforcer discards"
    assert "UsageLimitExceeded" in said, "name how it discards it"


#: The arguments this SDK's `run()` takes that a PACT run cannot honour, each
#: with a phrase only ITS OWN reason contains.
#:
#: The phrases are the point. Every one of these is refused by the same `raise`,
#: and a generic sentence naming the argument would pass a test that only
#: checked the argument's name — while telling a caller who asked for
#: `model_settings=` the same thing as one who asked for `capabilities=`, which
#: is *this argument is not ours* and nothing about what to do instead. What
#: makes a refusal usable is the line to type, and that line is different for
#: every row here.
_CANNOT_HONOUR = [
    ("output_type", "answers-with-mode"),
    ("model", "models/catalog.yaml"),
    ("toolsets", "tools/<name>.yaml"),
    ("instructions", "instructions.md"),
    ("model_settings", "`settings:`"),
    ("retries", "if-someone-fails:"),
    ("deferred_tool_results", "correlation key"),
    ("usage", "fresh budget"),
    ("capabilities", "durability"),
    ("spec", "from_pydantic_ai_spec"),
    ("metadata", "AgentRunResult.pact"),
]


@pytest.mark.parametrize("named,reason", _CANNOT_HONOUR, ids=[n for n, _ in _CANNOT_HONOUR])
def test_every_argument_a_pact_run_cannot_honour_is_refused_in_its_own_words(
    spec: AgentSpec, named: str, reason: str
) -> None:
    """Refused rather than ignored, and refused with the line to type.

    A silently dropped argument is a caller who believes a ceiling holds, a
    shape is enforced, a model is bound or a run is being recorded, and none of
    it is happening — this file's own rule one door along, where `usage_limits=`
    is refused because the second enforcer wins by raising.

    Each is checked for a phrase only its own reason carries, because the
    failure this catches is not the missing refusal: it is the refusal that has
    become generic. `model=` and `instructions=` have opposite fixes — add a row
    to the catalogue, or write a `skills/` document — and a sentence that names
    neither sends the caller to read this file's source.
    """
    agent = held(spec, transport=PydanticAITransport(Script([Turn(ANSWERED)])))
    with pytest.raises(REFUSALS) as trouble:
        asyncio.run(agent.run(ASK, **{named: object()}))

    said = str(trouble.value)
    assert named in said, "name the argument that was refused"
    assert reason in said, (
        f"`{named}=` was refused with somebody else's sentence, which names "
        f"nothing this caller can act on"
    )


def test_an_argument_this_sdk_grows_later_is_refused_by_name_and_a_None_is_not(
    spec: AgentSpec,
) -> None:
    """The table above is not the list that decides — the `**` is.

    An argument added to this SDK after this class was written is exactly the
    one nobody remembered, so an unknown keyword is refused too, in a sentence
    that names it. And it is refused only when it carries something: this SDK's
    own concrete methods pass their whole signature down, so refusing a `None`
    would make `run_stream_events` — the inherited method this class gets for
    free — fail on arguments nobody set.
    """
    agent = held(spec, transport=PydanticAITransport(Script([Turn(ANSWERED)])))
    with pytest.raises(REFUSALS) as trouble:
        asyncio.run(agent.run(ASK, marmalade=object()))

    said = str(trouble.value)
    assert "`marmalade=`" in said, (
        "an argument nobody wrote a sentence for was refused without naming it"
    )
    assert "build_agent" in said, "name the door where this SDK owns the loop"
    assert asyncio.run(agent.run(ASK, marmalade=None)).pact.halted == "final", (
        "an argument nobody set failed the run"
    )


def test_a_run_needs_a_transport_and_says_so_rather_than_failing_inside(
    spec: AgentSpec,
) -> None:
    """Holding one needs nothing; running one needs somewhere to send a call.

    `for_spec(spec)` alone is the inspection door — which tools, which answer
    shape, which model id — and that has to work with no endpoint and no
    credentials, or every one of those inspections becomes a deployment
    question. Running such an agent has to fail HERE, naming both ways to give
    it a transport: the alternative is an `AttributeError` on `None` from inside
    `harness.run`, which reads as a bug in the harness.
    """
    with pytest.raises(REFUSALS) as trouble:
        held(spec).run_sync(ASK)

    said = str(trouble.value)
    assert "transport=" in said and "script=" in said, "name both ways to give it one"


def test_override_refuses_with_the_reason_and_names_what_to_do_instead(
    spec: AgentSpec,
) -> None:
    """Everything `override()` replaces is a line in the author's tree.

    The model, the tools, the instructions and the retries are all written down,
    and this class exists to run what is written down — overriding one here
    would make `pact check` a statement about a document nobody ran. Like
    `iter()` one method up, the message is the whole value of the refusal: a
    bare `NotImplementedError` has an empty `str()`, and the caller cannot tell
    *not supported yet* from *never, and here is the other way*.
    """
    with pytest.raises(REFUSALS) as trouble:
        held(spec).override(model="anthropic:claude-opus-5")

    said = str(trouble.value)
    assert said.strip(), "a bare refusal carries no message at all"
    assert "document" in said, "name whose lines these are"
    assert "dataclasses.replace" in said, "name the way to build the spec you want"


def test_every_refusal_this_facade_gives_is_the_one_type_a_host_already_catches(
    spec: AgentSpec,
) -> None:
    """`REFUSALS` is three types because the MESSAGE is what those tests read.

    Which type is a matter of taste right up until somebody catches one. This
    SDK has exactly one word for *you asked this object for something it cannot
    give you* — `UserError` — and it is the word its own `Agent` uses, including
    for the failure this file's facade quotes back at a caller (`stream_text()
    can only be used with text responses`). So a host holding a mix of agents
    behind `AbstractAgent` and wrapping the call in `except UserError:` to render
    a message is doing the documented thing, and it is the only thing it CAN do:
    the refusal is the whole of what these doors return.

    A `NotImplementedError` from one door escapes that handler as a traceback,
    and it says something different besides — *not implemented*, which on an
    abstract base reads as *not yet* rather than *never, and here is the other
    door*. `TypeError` is worse again: an argument the signature never accepted
    raises one, so a shim could pass every refusal test in this file by simply
    not having the argument.

    Every door in one test, because the failure being prevented is drift: the
    file is unanimous today, and one door changed by somebody adding a method is
    exactly the silent divergence between what `pact check` printed OK for and
    what a caller meets.
    """
    from pydantic_ai.messages import ModelRequest, UserPromptPart

    from pact_adapters.pact_agent import PactAgent

    unbound = held(spec)
    running = answering(spec)
    # A real conversation and not `[1]`: the refusal is about `message_history=`
    # being a shape PACT's harness has nowhere to put, which it has to reach in
    # order to say. Handing it non-messages measures `dataclasses.fields`.
    earlier = [ModelRequest(parts=[UserPromptPart(content="Can I get a refund?")])]

    async def iterating() -> None:
        async with unbound.iter(ASK):
            pass  # pragma: no cover - reaching the body is the failure

    doors: list[tuple[str, Any]] = [
        ("iter", lambda: asyncio.run(iterating())),
        ("override", lambda: unbound.override(model="anthropic:claude-opus-5")),
        ("run_stream", lambda: running.run_stream(ASK)),
        ("run_stream_sync", lambda: running.run_stream_sync(ASK)),
        ("run(no transport)", lambda: unbound.run_sync(ASK)),
        ("run(usage_limits=)", lambda: running.run_sync(ASK, usage_limits=object())),
        # Through `run` and not `run_sync`: `AbstractAgent.run_sync` is a CLOSED
        # signature, so an argument this SDK has never heard of dies there as a
        # `TypeError` before this class sees it. The `**not_ours` sweep that
        # refuses it in this file's own words is on `run`.
        ("run(unknown=)", lambda: asyncio.run(running.run(ASK, no_such_argument="x"))),
        ("run(deps=)", lambda: running.run_sync(ASK, deps=["not a mapping"])),
        ("run(message_history=)", lambda: running.run_sync(ASK, message_history=earlier)),
    ]
    for named, knock in doors:
        with pytest.raises(REFUSALS) as trouble:
            knock()
        assert isinstance(trouble.value, UserError), (
            f"`{named}` refuses with `{type(trouble.value).__name__}`, which the "
            f"`except UserError:` a host wraps this SDK's agents in does not "
            f"catch — every other door on this class raises `UserError`"
        )
        assert str(trouble.value).strip(), f"`{named}` refuses with no reason at all"

    assert all(
        isinstance(getattr(PactAgent, door).__doc__ or "", str)
        for door in ("iter", "override", "run_stream", "run_stream_sync")
    )


def test_the_context_manager_holds_nothing_open_and_hides_nothing_that_went_wrong(
    spec: AgentSpec,
) -> None:
    """`__aexit__` answering `True` is a swallowed exception, silently.

    `Agent.__aenter__` starts the toolsets that need a connection and `__aexit__`
    closes them. PACT's tools are the host's `tool_impls` and its transports are
    constructed ready, so both are answered here rather than inherited — the base
    is abstract and a subclass without them cannot be instantiated at all.

    Answering `__aexit__` is therefore a formality with exactly one way to go
    wrong, and it is not a small one: a truthy return SUPPRESSES whatever was
    raised inside the block. `async with agent:` around a run that hit the
    author's ceiling, a park nobody answered, or a `PactSuspended` — the one
    outcome this facade raises precisely because a caller cannot fail to notice
    it — would come out the other side looking like a block that finished. The
    whole point of raising a park is undone by a context manager that eats it.
    """
    agent = answering(spec)

    async def opened_and_raised() -> None:
        async with agent as entered:
            assert entered is agent, "`__aenter__` handed back something else"
            raise RuntimeError("the thing that went wrong inside the block")

    with pytest.raises(RuntimeError, match="went wrong inside the block"):
        asyncio.run(opened_and_raised())


def test_deps_is_the_authors_run_inputs_and_reaches_the_document(spec: AgentSpec) -> None:
    """A `deps=` that is not a mapping used to become `None` in silence.

    `run_inputs` is what fills the author's `bind:` lines, and the measured
    shape of dropping it is in `harness.run`'s own docstring: the payments tool
    received `{order-number, amount, action}` and never `customer-id`, so *whose
    order* went on being something nobody supplied. So the wrong shape is
    refused by name — and the right shape has to actually arrive, which is what
    the second half measures: every `bind:` line the run could not fill is a
    sentence on `unenforced`, and supplying the value makes those sentences go
    away. Asserting only the refusal would pass on a class that refuses the
    wrong shape and then drops the right one.
    """
    agent = answering(spec)
    with pytest.raises(REFUSALS) as trouble:
        agent.run_sync(ASK, deps=["customer-id"])
    said = str(trouble.value)
    assert "run-inputs" in said and "bind:" in said
    assert "list" in said, "name the shape that was handed in"

    nothing_supplied = answering(spec).run_sync(ASK)
    supplied = answering(spec).run_sync(ASK, deps={"customer-id": "C-1"})
    unfilled = [s for s in nothing_supplied.pact.unenforced if "customer-id" in s]
    assert unfilled, (
        "this document no longer binds `customer-id` into a tool, so a run that "
        "supplied it and one that did not report the same thing"
    )
    assert not [s for s in supplied.pact.unenforced if "customer-id" in s], (
        f"the run-inputs never reached the run: {supplied.pact.unenforced}"
    )


def test_a_message_history_is_refused_with_what_that_conversation_would_cost(
    spec: AgentSpec,
) -> None:
    """`harness.run` has nowhere to put a bare list of turns, and says where they go.

    A conversation continues through a `Suspension` — the park record carrying
    the history, the meter, the permissions already granted and the stage it had
    reached — so accepting a message list would put turns in front of the model
    that the author's `context-policy:` never measured and their ceilings never
    counted. The refusal carries the crossing's own report rather than a
    shrug: the caller learns that these turns DO cross, what this particular
    conversation would lose on the way, and which two functions do it.
    """
    from pydantic_ai.messages import ModelRequest, UserPromptPart

    from pact_adapters.pact_agent import to_pact_history

    history = [
        ModelRequest(
            parts=[UserPromptPart(content="and the replacement?")],
            instructions="You are somebody else's agent.",
        )
    ]
    with pytest.raises(REFUSALS) as trouble:
        answering(spec).run_sync(ASK, message_history=history)

    said = str(trouble.value)
    _, lost = to_pact_history(history)
    assert "to_model_messages" in said and "to_pact_history" in said
    assert "Suspension" in said, "name the record a conversation really continues through"
    assert f"(this history would lose {', '.join(sorted(lost.not_carried))})" in said, (
        "the caller is told turns cross cleanly and not what this one loses"
    )
    assert "ModelRequest.instructions" in said, (
        "the foreign system prompt in that history went unnamed"
    )


@pytest.mark.parametrize("where", ["on the agent", "on the run"])
def test_a_handler_that_can_never_be_called_is_reported_rather_than_dropped(
    spec: AgentSpec, where: str
) -> None:
    """A held handler and a run nothing happened in look identical from outside.

    `event_stream_handler=` cannot be refused — `AbstractAgent.run_stream_events`
    passes one into `self.run` itself, so refusing it would break the inherited
    method this class says it gets for free — and it cannot be honoured either:
    PACT's transport seam is one whole model call, which is what
    `PydanticAITransport.lattice()` already declares as `streaming: emulated`.
    What is left is saying so, on the channel whose own line is *a rule the
    author wrote that this run could not decide*.

    Both places a handler can arrive are driven, because the two are read in one
    expression and either can be lost without the other noticing — and a caller
    who passed one to the constructor watches exactly the same blank screen.
    """

    async def watch(ctx: Any, stream: Any) -> None:  # pragma: no cover - never called
        return None

    if where == "on the agent":
        result = answering(spec, event_stream_handler=watch).run_sync(ASK)
    else:
        result = answering(spec).run_sync(ASK, event_stream_handler=watch)

    named = [s for s in result.pact.unenforced if "event_stream_handler" in s]
    assert named, (
        f"a handler was held and never called and nothing said so: "
        f"{result.pact.unenforced}"
    )
    assert "streaming" in named[0] and "build_agent" in named[0], (
        "name why nothing streamed, and the door where something would"
    )
    assert not [
        s for s in answering(spec).run_sync(ASK).pact.unenforced
        if "event_stream_handler" in s
    ], "a run nobody gave a handler reported one anyway"


def test_a_prompt_that_did_not_all_reach_the_model_says_what_stayed_behind(
    spec: AgentSpec,
) -> None:
    """The words are used and the picture is not, and a run must not hide that.

    A `Sequence[UserContent]` is this SDK's multimodal prompt and PACT's harness
    takes one string. Refusing it would fail an otherwise ordinary question
    because a screenshot rode along with it, which is the worse trade — but a
    run that answered a question it never fully saw is byte-identical to one
    that did, which is the same shape as the `stage-limit` answer that parses as
    the declared output one door along.
    """
    agent = answering(spec)
    result = agent.run_sync(["please refund this", {"receipt": "torn-jacket.png"}])

    assert result.pact.asked == "please refund this", (
        "the text of the prompt is what `harness.run` was given"
    )
    said = [s for s in result.pact.unenforced if "user_prompt" in s]
    assert said, f"the picture reached nothing and nothing said so: {result.pact.unenforced}"
    assert "images" in said[0], "name what stayed behind"
    assert "tools/<name>.yaml" in said[0], "name what a run can do about it"
    assert not [
        s for s in answering(spec).run_sync(ASK).pact.unenforced if "user_prompt" in s
    ], "an ordinary question was reported as one the model could not see"


def test_a_run_with_no_prompt_at_all_asks_nothing_rather_than_the_word_null(
    spec: AgentSpec,
) -> None:
    """`run()` with no prompt is how a resumed run is entered, and it must be silent.

    `run_sync(resume=…, answer=…)` passes no `user_prompt`, so anything invented
    here becomes a customer turn in a conversation that already has one — and
    the lazy way to invent it is `json.dumps(None)`, which puts the four letters
    `null` in front of the model as the thing the person said.
    """
    from pact_adapters.pact_agent import to_pact_history

    result = answering(spec).run_sync()
    assert result.pact.asked == ""
    spoken, _ = to_pact_history(result.all_messages())
    assert not [entry for entry in spoken if entry["role"] == "user"], (
        f"a conversation nobody opened begins with somebody saying nothing: "
        f"{spoken}"
    )


def test_the_agent_can_be_entered_the_way_this_sdk_enters_an_agent(spec: AgentSpec) -> None:
    """`async with agent:` is how this SDK's callers hold one, and it must hand back the agent.

    `Agent.__aenter__` starts the toolsets that need a connection and returns
    the agent itself, so `async with build_agent(spec) as a: await a.run(…)` is
    the shape every example in that SDK's own documentation uses. PACT's tools
    are the host's `tool_impls` and its transports are constructed ready, so
    there is no lifecycle to hold open here — but a context manager that hands
    back `None` turns the documented shape into `AttributeError: 'NoneType'
    object has no attribute 'run'`, which reads as a bug in the caller's code.
    """

    async def entered() -> Any:
        agent = held(spec)
        async with agent as inside:
            return agent, inside

    agent, inside = asyncio.run(entered())
    assert inside is agent


# ─────────────── three answers a member gives from somewhere other than the file


def test_the_model_id_a_reader_is_shown_comes_from_this_workspaces_own_catalogue(
    spec: AgentSpec, tmp_path: Path
) -> None:
    """`model` is a lookup, and the table it looks in has the workspace layered on.

    The override layer is not only the transport's. A caller HOLDING this agent
    reads `.model` to find out what it runs on — a router choosing between two,
    `to_cli` printing it, a host logging which row a decision was made on — and
    a row that exists only in this workspace's `models/catalog.yaml` is
    invisible to a lookup made without the workspace. What comes back then is
    `None`, which this property's own docstring reserves for a row with no
    Pydantic AI id at all: an author on an air-gapped box is told their model is
    unbound on the one machine that serves it, and told it in the shape that
    means "you still have options".
    """
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "catalog.yaml").write_text(A_ROW_ONLY_THIS_BOX_HAS)
    layered, why = pydantic_ai_model_id("the-box-in-the-corner", str(tmp_path))
    assert layered and not why, f"the workspace row stopped resolving: {why}"
    assert pydantic_ai_model_id("the-box-in-the-corner")[0] == "", (
        "the row is in the distribution's own catalogue, so this proves nothing"
    )

    local = held(
        dataclasses.replace(
            spec, model="the-box-in-the-corner", workspace=str(tmp_path)
        )
    )
    assert local.model == layered, (
        f"a row this workspace added itself is read back as {local.model!r}, so "
        f"the one machine that serves this model is the one that cannot name it"
    )


#: Two written procedures, both synthetic, because the claim is about which of
#: them a stage may read and the shipped example has exactly one — with one
#: skill, offering all of them and offering the right one are the same answer.
_THE_ONE_THIS_STAGE_MAY_READ = SkillSpec(
    name="refund-policy",
    description="When a refund is allowed.",
    content="MARKER-THE-STAGE-MAY-READ-THIS: anything faulty inside 30 days.",
)
_THE_ONE_IT_MAY_NOT = SkillSpec(
    name="escalation-ladder",
    description="Who a refund goes to when it is over the line.",
    content="MARKER-NOT-IN-THIS-STAGE: over 500 USD goes to the duty manager.",
)


def test_the_opening_stage_reads_the_procedures_its_own_line_offers_it_and_no_others(
    spec: AgentSpec,
) -> None:
    """`may-use:` narrows the written procedures, and this member has to narrow with it.

    `Phase.skills_offered` is what decides which of the agent's `skills/`
    documents a stage is shown, and the harness calls it on every step. A member
    that reads this SDK's idea of the system prompt from the whole set instead
    answers with a document the run will never put in front of the model at the
    stage it names — so a UI adapter or a history reconstruction shows a person
    rules that stage does not follow, and `pact check` printed OK for a file
    that says otherwise.

    Both directions matter and only one of them is visible with a single skill:
    the offered document has to be there, and the withheld one has to be absent.
    """
    narrowed = Loop.from_mapping(
        "one-stage-that-reads-one-procedure",
        {
            "description": "One stage, offered one of the two written procedures.",
            "starts-at": "work",
            "steps": {
                "work": {
                    "does": "use-tools",
                    "may-use": ["refund-policy"],
                    "then": {"used-a-tool": "work", "answered": "done"},
                }
            },
        },
    )
    agent = held(
        dataclasses.replace(
            spec,
            loop=narrowed,
            skills=(_THE_ONE_THIS_STAGE_MAY_READ, _THE_ONE_IT_MAY_NOT),
        )
    )
    written = asyncio.run(agent.system_prompt_parts())
    assert written, "the opening stage was given no system text at all"
    said = written[0].content
    assert "MARKER-THE-STAGE-MAY-READ-THIS" in said, (
        "the procedure the stage's own `may-use:` names never reached the text"
    )
    assert "MARKER-NOT-IN-THIS-STAGE" not in said, (
        "a stage was shown a written procedure its own line withholds, so this "
        "member describes a run that does not happen"
    )


def test_the_refusal_of_a_message_history_counts_the_turns_it_actually_crossed(
    spec: AgentSpec,
) -> None:
    """The refusal offers `to_pact_history()` as the way through, so its count is a claim.

    `message_history=` is refused because `harness.run` has nowhere to put a
    bare message list — but the sentence does not stop at no. It says these
    turns cross into PACT's dialect cleanly enough, names the function that
    crosses them, and gives a NUMBER. A caller reading that number decides
    whether the crossing is worth making, and a number that is not the count of
    what would cross is the same defect as a silent drop with the sentence
    attached: the reader's next move depends on it and it is not true.
    """
    from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

    history = [
        ModelRequest(parts=[UserPromptPart(content="refund order A-1")]),
        ModelResponse(parts=[TextPart(content="looking the ticket up")]),
        ModelRequest(parts=[UserPromptPart(content="any news?")]),
    ]
    with pytest.raises(REFUSALS) as refused:
        answering(spec).run_sync(ASK, message_history=history)

    said = str(refused.value)
    assert "3 turn(s)" in said, (
        f"three turns cross into PACT's dialect and the refusal names a "
        f"different number: {said}"
    )
    assert "to_pact_history" in said and "resume=" in said, (
        "a refusal with no way through is the dead end every other one here "
        "exists to avoid"
    )


def test_a_run_given_no_question_reports_nothing_it_failed_to_carry(
    spec: AgentSpec,
) -> None:
    """`unenforced` is what was asked for and not done, so an empty ask asks nothing.

    A run entered with no `user_prompt` at all is ordinary — it is what
    `run_sync(resume=…, answer=…)` does on the way back into a park, and what a
    document driven entirely by `run-inputs:` does every time. Nothing was
    handed over, so nothing was left behind, and a sentence saying *the rest of
    the prompt reached nothing* sends the caller looking for a picture that was
    never there. `unenforced` is the channel a person reads when a run did less
    than the document asked for; noise on it is how a real entry there stops
    being read.
    """
    result = answering(spec).run_sync()
    assert result.pact.halted == "final", result.pact.halted
    assert result.pact.asked == ""
    assert not [said for said in result.pact.unenforced if "user_prompt=" in said], (
        f"a run nobody asked anything was told part of the question did not "
        f"reach the model: {result.pact.unenforced}"
    )
