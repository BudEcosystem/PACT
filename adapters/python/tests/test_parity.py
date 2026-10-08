"""02P §6: the parity suite, one folder per row of the 02P matrix.

`tests/parity/<row>/` holds a fixture and `expect.yaml`. The fixture is a PACT
tree (`tree/`, read through the real loader and built by PACT's own Pydantic AI
path, `build_agent`) or a Pydantic AI `AgentSpec` file (`spec.yaml`, read by the
spec importer). `expect.yaml` says what each check must find.

Three standard checks (02P §6), and the behaviour of each row:

* **S1, import.** The agent the fixture becomes is imported back through
  `from_pydantic_ai_agent` (a tree) or `from_pydantic_ai_spec` (a spec file):
  no silent drops, nothing unmapped, and the `mapped` and `not-portable` keys
  are exactly the ones `expect.yaml` lists under `import:`.
* **S4, completeness.** Every name the installed Pydantic AI and pydantic-graph
  have, through every door, has a registry row (`pydantic_ai_registry.yaml`), so
  moving the pin is a test run. One test, `test_s4_*`.
* **S5, plain words.** The import report a person reads uses none of the words
  the product's vocabulary bans (`docs/04-UX-DASHBOARD.md` §14.2 in Bud Flow).
* **Behaviour.** The tree's agent runs on a scripted `FunctionModel` with the
  turns `expect.yaml` gives under `model:`, and what the row's 02P test column
  asks for holds (`expect:`).

**Which rows.** `PHASE_1` is the set Phase 1 compiles: the 02P rows whose Change
is `—`, A1, A2 or A4, or a field 02P §3.1 builds in Phase 1 (`answers-with:`,
`checked-by:` with `checks-at-most:`, edited answers, memory), on PACT's own
Pydantic AI path. Rows that path does not compile wait for the phase that
builds them: F1 (the files a run takes in are the host's prompt), O3 (answer
alternatives, Phase 3), T10 and E3/E6 (a tool file to write, and the eval
runner, not the agent), and every row whose Change is runtime work (R2 to R10).
"""

from __future__ import annotations

import asyncio
import inspect
import json
import re
import sys
import typing
from dataclasses import fields as dataclass_fields
from pathlib import Path
from typing import Any

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.pydantic_ai_interop import (  # noqa: E402
    build_agent,
    from_pydantic_ai_agent,
    from_pydantic_ai_spec,
    pydantic_ai_model_id,
    return_schema_for,
    to_pydantic_ai_spec,
    usage_limits_for,
)
from pact_adapters.pydantic_ai_registry import registry  # noqa: E402
from trees import shown  # noqa: E402

pydantic_ai = pytest.importorskip("pydantic_ai")

from pydantic_ai import DeferredToolRequests, DeferredToolResults, ToolApproved, ToolDenied  # noqa: E402
from pydantic_ai.messages import (  # noqa: E402
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.fallback import FallbackModel  # noqa: E402
from pydantic_ai.models.function import AgentInfo, FunctionModel  # noqa: E402
from pydantic_ai.usage import UsageLimits  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
PARITY = REPO / "tests" / "parity"

#: The rows Phase 1 compiles (see the module docstring for the rule).
PHASE_1 = (
    "A1", "A2", "A3", "A4", "A8", "A14", "C6", "C8", "C10", "C12", "H1", "H3",
    "M1", "M3", "N1", "N3", "O1", "O2", "O7", "P1", "T1", "T2", "T11",
)

ROWS = sorted(p.name for p in PARITY.iterdir() if p.is_dir()) if PARITY.is_dir() else []


def _expect(row: str) -> dict[str, Any]:
    return yaml.safe_load((PARITY / row / "expect.yaml").read_text(encoding="utf-8"))


def _spec(row: str, said: dict[str, Any]) -> AgentSpec:
    document = shown(PARITY / row / "tree")
    return AgentSpec.from_document(document, said.get("agent", "desk"))


def _document(row: str) -> dict[str, Any]:
    return shown(PARITY / row / "tree")


# ───────────────────────────────────────────────────────────── the row set


def test_every_phase_1_row_has_a_folder_and_nothing_else_does() -> None:
    assert ROWS, f"{PARITY} has no rows"
    assert set(ROWS) == set(PHASE_1), (
        f"missing: {sorted(set(PHASE_1) - set(ROWS))}; not a Phase 1 row: {sorted(set(ROWS) - set(PHASE_1))}"
    )
    for row in ROWS:
        said = _expect(row)
        assert said.get("row") == row, f"{row}/expect.yaml says it is row {said.get('row')!r}"
        has = {p.name for p in (PARITY / row).iterdir()}
        assert has & {"tree", "spec.yaml"}, f"{row} has no fixture (`tree/` or `spec.yaml`)"


# ──────────────────────────────────────────────────────────────── S1, S5


def _imported(row: str, said: dict[str, Any]) -> Any:
    """The fixture as Pydantic AI has it, imported back: the `ImportReport`."""
    if (PARITY / row / "spec.yaml").is_file():
        spec_file = yaml.safe_load((PARITY / row / "spec.yaml").read_text(encoding="utf-8"))
        return from_pydantic_ai_spec(spec_file)[1]
    spec = _spec(row, said)
    agent = build_agent(
        spec,
        call_tool=lambda name, args: "done",
        run_inputs=said.get("inputs"),
        remembered=said.get("remembered"),
    )
    return from_pydantic_ai_agent(agent)[1]


@pytest.mark.parametrize("row", ROWS)
def test_s1_the_import_accounts_for_every_key(row: str) -> None:
    said = _expect(row)
    report = _imported(row, said)
    assert report.silent_drops == (), f"{row}: dropped in silence: {report.silent_drops}"
    assert report.unmapped == {}, f"{row}: not understood: {report.unmapped}"
    wanted = said.get("import") or {}
    assert sorted(report.mapped) == sorted(wanted.get("mapped") or []), report.in_words()
    assert sorted(report.not_portable) == sorted(wanted.get("not-portable") or []), report.in_words()


#: 04 §14.2: never in a screen, a card or a reply unless technical details are on.
BANNED = (
    "node", "graph", "workflow", "reducer", "carry", "state", "scope", "schema", "token",
    "webhook", "payload", "trigger", "channel", "endpoint", "API", "JSON", "YAML", "CEL",
    "expression", "variable", "prompt", "system prompt", "temperature", "model ID",
    "embedding", "vector", "index", "RAG", "retriever", "HITL", "deferred", "saga",
    "compensation", "idempotency", "digest", "canary", "shadow traffic", "MCP", "A2A",
    "OAuth", "tenant", "SKILL.md", "spec", "adaptive card", "decision model",
    "trained model", "orchestrator", "sub-agent", "runtime", "journal", "Dapr", "PACT",
    "Publisher",
)


def _banned_in(text: str) -> list[str]:
    # "carry on" is allowed (§14.2 says so); every other word is matched whole.
    text = re.sub(r"\bcarry on\b", "", text, flags=re.IGNORECASE)
    return [w for w in BANNED if re.search(rf"(?<![\w.-]){re.escape(w)}(?![\w-])", text, re.IGNORECASE)]


@pytest.mark.parametrize("row", ROWS)
def test_s5_the_import_report_a_person_reads_uses_plain_words(row: str) -> None:
    said = _imported(row, _expect(row)).in_plain_words()
    assert not _banned_in(said), f"{row}: {_banned_in(said)} in {said!r}"


def test_s5_the_banned_word_check_finds_a_banned_word() -> None:
    """The control: the check is not passing because it can find nothing."""
    assert _banned_in("3 things came across from the system prompt") == ["prompt", "system prompt"]
    assert _banned_in("carry on with a value") == []


# ──────────────────────────────────────────────────────────────────── S4


def _members(alias: Any) -> list[type]:
    """The classes a type alias (`X = A | B`, `Annotated[...]`) names, recursively."""
    while hasattr(alias, "__value__"):
        alias = alias.__value__
    if typing.get_origin(alias) is typing.Annotated:
        return _members(typing.get_args(alias)[0])
    if inspect.isclass(alias):
        return [alias]
    return [c for arg in typing.get_args(alias) for c in _members(arg)]


def installed_names() -> dict[str, set[str]]:
    """Every name the installed packages have, by the registry door it goes through.

    Read by introspecting public module members only, so moving the pin is a
    test run: a new capability, setting, part, event, tool field or graph method
    shows up here and has no row.
    """
    from pydantic_ai import capabilities, messages, settings, tools
    from pydantic_ai.agent.spec import AgentSpec as PydanticAgentSpec
    from pydantic_graph import GraphBuilder

    from pact_adapters.transports.pydantic_ai_transport import _SETTINGS

    shipped = {
        name
        for name, value in vars(capabilities).items()
        if inspect.isclass(value) and issubclass(value, capabilities.AbstractCapability)
    } | set(getattr(capabilities, "CAPABILITY_TYPES", {}))
    return {
        "capability": shipped,
        "spec": set(PydanticAgentSpec.model_fields),
        # The twelve `settings:` keys are the transport's table; the rest are names.
        "settings": set(settings.ModelSettings.__annotations__) - set(_SETTINGS.values()),
        "part": {c.__name__ for c in _members(messages.ModelRequestPart) + _members(messages.ModelResponsePart)},
        "event": {c.__name__ for c in _members(messages.AgentStreamEvent)},
        "tool-definition": {f.name for f in dataclass_fields(tools.ToolDefinition)},
        "graph": {n for n, _ in inspect.getmembers(GraphBuilder) if not n.startswith("_")},
    }


def unaccounted() -> dict[str, list[str]]:
    """Names the installed packages have and the registry has never heard of."""
    reg = registry()
    out: dict[str, list[str]] = {}
    for door, names in installed_names().items():
        known = set(reg.capabilities) if door == "capability" else set(reg.through(door))
        if missing := sorted(names - known):
            out[door] = missing
    return out


def test_s4_every_name_the_installed_packages_have_has_a_registry_row() -> None:
    missing = unaccounted()
    assert not missing, (
        f"{missing} are in the installed Pydantic AI and not in pydantic_ai_registry.yaml.\n"
        "  fix: add each with its outcome and its 02P row (`capabilities:` for a "
        "capability, `names:` as `<door>.<name>` for the rest)."
    )


def test_s4_a_capability_nobody_has_seen_fails_it(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic_ai import capabilities

    class SomebodysNewCapability(capabilities.AbstractCapability):
        pass

    monkeypatch.setattr(capabilities, "SomebodysNewCapability", SomebodysNewCapability, raising=False)
    assert unaccounted() == {"capability": ["SomebodysNewCapability"]}


def test_s4_every_door_finds_something() -> None:
    """A door whose introspection finds nothing would pass while checking nothing."""
    empty = sorted(door for door, names in installed_names().items() if not names)
    assert not empty, f"introspection found no names through {empty}"


# ─────────────────────────────────────────────────────────────── behaviour


def _reply(turn: dict[str, Any], info: AgentInfo) -> ModelResponse:
    """One scripted turn: `say:` an answer (text, or a mapping for a shaped one),
    or `call:` a tool with `args:`."""
    if "call" in turn:
        return ModelResponse(parts=[ToolCallPart(turn["call"], turn.get("args") or {})])
    said = turn["say"]
    if isinstance(said, dict) and info.output_tools:
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, said)])
    return ModelResponse(parts=[TextPart(said if isinstance(said, str) else json.dumps(said))])


def _fails(messages: list[Any], info: AgentInfo) -> ModelResponse:
    from pydantic_ai.exceptions import ModelHTTPError

    raise ModelHTTPError(503, "first-model", "unavailable")


class _Run:
    """One row's run: the scripted model, the host's executor, what each saw."""

    def __init__(self, said: dict[str, Any]) -> None:
        self.turns = list(said.get("model") or [{"say": "done"}])
        self.requests: list[tuple[list[Any], AgentInfo]] = []
        self.calls: list[dict[str, Any]] = []
        self.returns = said.get("tool-returns") or {}

    def respond(self, messages: list[Any], info: AgentInfo) -> ModelResponse:
        self.requests.append((messages, info))
        return _reply(self.turns[min(len(self.requests), len(self.turns)) - 1], info)

    def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        self.calls.append({name: args})
        return self.returns.get(name, "done")


def _approvals(answers: dict[str, Any], waiting: DeferredToolRequests) -> DeferredToolResults:
    by_name = {c.tool_name: c.tool_call_id for c in waiting.approvals}
    out: dict[str, Any] = {}
    for name, answer in answers.items():
        if answer is True:
            out[by_name[name]] = True
        elif "edit" in answer:
            out[by_name[name]] = ToolApproved(override_args=answer["edit"])
        else:
            out[by_name[name]] = ToolDenied(answer["no"])
    return DeferredToolResults(approvals=out)


def _texts(messages: list[Any]) -> str:
    """Everything a request put in front of the model, as one string."""
    out: list[str] = []
    for m in messages:
        if isinstance(m, ModelRequest):
            out.append(m.instructions or "")
            out += [str(getattr(p, "content", "")) for p in m.parts]
    return "\n".join(out)


async def _behave(row: str, said: dict[str, Any]) -> None:
    spec = _spec(row, said)
    want = said.get("expect") or {}
    run = _Run(said)
    model: Any = FunctionModel(run.respond)
    if said.get("fallback"):
        model = FallbackModel(FunctionModel(_fails), model)
    agent = build_agent(
        spec,
        call_tool=None if said.get("executor") is False else run.call_tool,
        model=model,
        run_inputs=said.get("inputs"),
        remembered=said.get("remembered"),
    )
    # No ceiling nobody wrote: `UsageLimits()` alone caps requests at 50.
    limits = usage_limits_for(spec) if said.get("limits") else UsageLimits(request_limit=None)
    # A run that may end waiting (a gate, or tools with no executor) says so in its output type.
    waits = "answers" in said or "waiting" in want or "deferred-calls" in want
    output_type = [agent.output_type, DeferredToolRequests] if waits else None

    if "raises" in want:
        with pytest.raises(Exception) as raised:
            await agent.run(said.get("prompt", "go"), usage_limits=limits, output_type=output_type)
        assert type(raised.value).__name__ == want["raises"], raised.value
        result = None
    else:
        result = await agent.run(said.get("prompt", "go"), usage_limits=limits, output_type=output_type)
        if "answers" in said:
            assert isinstance(result.output, DeferredToolRequests), result.output
            if "waiting" in want:
                assert sorted(c.tool_name for c in result.output.approvals) == sorted(want["waiting"])
            result = await agent.run(
                message_history=result.all_messages(),
                deferred_tool_results=_approvals(said["answers"], result.output),
                usage_limits=limits,
                output_type=output_type,
            )

    if "output" in want:
        assert result.output == want["output"], result.output
    for text in want.get("output-has") or ():
        assert text in str(result.output), result.output
    if "waiting" in want and "answers" not in said:
        assert isinstance(result.output, DeferredToolRequests), result.output
        assert sorted(c.tool_name for c in result.output.approvals) == sorted(want["waiting"])
    if "deferred-calls" in want:
        assert isinstance(result.output, DeferredToolRequests), result.output
        assert sorted(c.tool_name for c in result.output.calls) == sorted(want["deferred-calls"])
    if "calls" in want:
        assert run.calls == want["calls"], run.calls
    if "requests" in want:
        assert result.usage.requests == want["requests"], result.usage
    if "description" in want:
        assert agent.description == want["description"], agent.description
    for text in want.get("instructions-have") or ():
        first = [m for m in run.requests[0][0] if isinstance(m, ModelRequest)][-1]
        assert text in (first.instructions or ""), first.instructions
    if want.get("every-request-has-instructions"):
        assert len(run.requests) > 1, "the row needs two requests to show it"
        for messages, _ in run.requests:
            last = [m for m in messages if isinstance(m, ModelRequest)][-1]
            assert last.instructions, f"a request went without the instructions: {last}"
    for text in want.get("model-saw") or ():
        assert text in _texts(run.requests[-1][0]), _texts(run.requests[-1][0])
    if "settings" in want:
        given = dict(run.requests[0][1].model_settings or {})
        assert {k: given.get(k) for k in want["settings"]} == want["settings"], given
    for tool, params in (want.get("offered") or {}).items():
        offered = {t.name: t for t in run.requests[0][1].function_tools}
        assert tool in offered, sorted(offered)
        assert sorted(offered[tool].parameters_json_schema["properties"]) == sorted(params)
    for where, required in (want.get("returns") or {}).items():
        tool, action = where.split("/")
        (found,) = [t for t in spec.tools if t.name == tool]
        schema = return_schema_for(found, action)
        assert schema is not None and sorted(schema["required"]) == sorted(required), schema
    if "model-id" in want:
        assert pydantic_ai_model_id(spec.model, spec.workspace)[0] == want["model-id"]
    if "usage-limits" in want:
        made = usage_limits_for(spec)
        assert {k: getattr(made, k) for k in want["usage-limits"]} == want["usage-limits"], made
    if "export-not-carried" in want:
        _, report = to_pydantic_ai_spec(_document(row), said.get("agent", "desk"))
        for key in want["export-not-carried"]:
            assert key in report.not_carried, sorted(report.not_carried)


BEHAVING = [r for r in ROWS if (PARITY / r / "tree").is_dir()]


@pytest.mark.parametrize("row", BEHAVING)
def test_behaviour_on_pacts_own_pydantic_ai_path(row: str) -> None:
    said = _expect(row)
    assert said.get("expect"), f"{row}/expect.yaml says nothing a run must show"
    asyncio.run(_behave(row, said))
