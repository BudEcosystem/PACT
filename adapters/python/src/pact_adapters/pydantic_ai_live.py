"""A live Pydantic AI `Agent` as a PACT agent, its tool files, and the report (02P A1-A26, T1-T14).

`from_pydantic_ai_agent` is the door `pydantic_ai_interop` documents: the caller
has already built the object in their own process, and PACT executes nothing of
theirs beyond what any run of the agent does (one probe request to a
`FunctionModel`, no tool executed, and each toolset's `get_tools`). Everything
it reads is public: `pydantic_ai_reading` says how, and why no private
attribute is touched. What has no public read is one named loss, `not_shown`,
on every import: a report cannot say an agent has no output validator when
nothing it may read could tell it.

**Tools keep the names a model was shown.** A Python tool (a `FunctionToolset`'s
or an `ExternalToolset`'s) becomes `tools/<name>.yaml` named as the model was
shown it (prefixes and renames applied), with one action of the same name, which
both PACT's own path and budflow-core offer under that name; `connect:` names
the one server the host serves the functions from. An MCP server becomes one
file named for its prefix (else its `id`), whose actions are the server's own
tool names, so a model is shown `<file>_<action>`: exactly the prefixed name
Pydantic AI showed (02P T12), the file says `connect: <its name>`, and
`resources/<its name>.yaml` is written beside it. A name such a file cannot keep
(an MCP server with no prefix, or a renamed MCP tool) is a named loss,
`toolsets.names`, listing each.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping

from .importing import ImportReport
from .openapi import NotImported
from .pydantic_ai_interop import (
    _MCP_SHAPE,
    _REGISTRY,
    _SPEC_MAPS,
    _schema_to_answers,
    _settings_to_pact,
    _still_to_write,
    _thinking,
    catalogue_row_for,
    shapes_owed,
    shape_from_json_schema,
)
from .pydantic_ai_reading import Leaf, Read, read_agent

__all__ = ["Found", "from_pydantic_ai_agent", "imported", "tool_files_for", "resource_file_for"]

#: What each public attribute of a live `Agent` becomes (the registry's `agent.` door).
_AGENT_MAPS: dict[str, str] = {k: r.pact for k, r in _REGISTRY.through("agent").items() if r.pact}
#: Why each one that does not cross does not.
_AGENT_NOT_PORTABLE: dict[str, str] = {k: r.why for k, r in _REGISTRY.through("agent").items() if r.why}

def from_pydantic_ai_agent(agent: Any, *, connect: str = "") -> tuple[dict[str, Any], ImportReport]:
    """One live Pydantic AI `Agent` as a PACT agent block, and everything it could not say.

    `connect` names the one MCP server the host serves the agent's Python
    functions from: every function tool file then says `connect: <connect>` and
    `still_to_write` asks only for that server's address.
    """
    found = imported(agent, connect=connect)
    if found.shapes:  # `pydantic_ai_trees.imported_agent` writes them; this door has nowhere to
        found.report.still_to_write += (shapes_owed(found.shapes),)
    return found.agent, found.report


@dataclass
class Found:
    """Everything one live agent becomes: its block, its tool files, the servers they reach."""

    agent: dict[str, Any]
    #: `{name: body}` of each `tools/<name>.yaml`.
    tools: dict[str, dict[str, Any]]
    #: The MCP servers those reach, each a `resources/<name>.yaml` to write.
    servers: tuple[str, ...]
    report: ImportReport
    #: The shapes with parts its answer names (`{name: {part: line}}`), for `workspace.yaml`.
    shapes: dict[str, dict[str, str]]


def imported(agent: Any, *, connect: str = "") -> Found:
    """`agent` read once (`pydantic_ai_reading.read_agent`), as a PACT agent and its tool files."""
    read = read_agent(agent)
    connect = str(connect or "").strip()
    report = ImportReport(kind="a live Pydantic AI Agent", seen=_what_it_carries(agent, read))
    out: dict[str, Any] = {}
    settings: dict[str, Any] = {}

    model = getattr(agent, "model", None)
    if model is not None:
        from pydantic_ai.models.fallback import FallbackModel

        # 02P A2: a `FallbackModel` is PACT's `model: [a, b]`, in its order (`FallbackModel.models`).
        chain = [catalogue_row_for(_model_id(m)) for m in (model.models if isinstance(model, FallbackModel) else [model])]
        named = chain[0] if len(chain) == 1 else (chain if all(chain) else "")
        from pydantic_ai.models.wrapper import WrapperModel

        if wrapped := [type(m).__name__ for m in getattr(model, "models", [model]) if isinstance(m, WrapperModel)]:
            # 02P M7: what a wrapper adds (spans, a limit on calls at once) is the host's, not the agent's.
            report.not_portable["model.wrapper"] = (
                f"{', '.join(f'a `{w}`' for w in wrapped)} around the model: what it adds (spans, a limit on "
                "calls at once, ...) is the host's to set, so only the model inside is carried"
            )
        if named:
            out["model"] = named
            report.mapped["model"] = _AGENT_MAPS["model"]
        else:
            report.unmapped["model"] = (
                f"a {type(model).__name__} whose provider and model name could not be read; write `model:` by hand"
            )
    for key in ("name", "description"):
        if said := str(getattr(agent, key, None) or "").strip():
            out[key] = said
            report.mapped[key] = _AGENT_MAPS[key]

    if told := "\n\n".join(read.instructions + read.system_prompts):
        out["instructions"] = told
    if read.instructions:
        report.mapped["instructions"] = _AGENT_MAPS["instructions"]
    if read.system_prompts:
        report.mapped["system_prompts"] = _AGENT_MAPS["system_prompts"]
        report.not_portable["system_prompts.maybe-made-by-code"] = (
            "carried as one run wrote them: an `@agent.system_prompt` function not marked dynamic writes "
            "its text once per run, and Pydantic AI shows that text as it shows a written string, so a "
            "function's output (today's date, a value read from the deps this importer built) may be in "
            "`instructions:` as fixed words. Check them, and write a value the run supplies as a "
            "`{{run-inputs.<name>}}` blank"
        )
    if read.dynamic:
        report.not_portable["instructions.made-at-run-time"] = (
            f"{read.dynamic} part(s) of the instructions are made by code each run (an `@agent.instructions` "
            "or `system_prompt` function, or a template), and code does not cross. Write each as text in "
            "`instructions:`, with a `{{run-inputs.<name>}}` blank for a value the run supplies"
        )
    added = []
    if read.added:
        added.append(
            f"{read.added} part(s) of what a model is sent are not the agent's own instructions: its "
            "capabilities or toolsets add them (a capability's own instructions, an MCP server's when "
            "`include_instructions=True`, a `FunctionToolset(instructions=...)`), so they are not carried "
            "as the author's words"
        )
    if read.added_unread:
        added.append(
            f"what {'else ' if read.added else ''}its capabilities and toolsets add to what a model is sent "
            "(a capability's own instructions, an MCP server's, a `FunctionToolset(instructions=...)`) could "
            f"not be read: it failed on the deps this importer built ({read.added_unread}). Only the agent's "
            "own instructions are carried"
        )
    if added:
        report.not_portable["instructions.added-by-capabilities-or-toolsets"] = (
            "; and ".join(added) + ". A capability PACT carries brings its own; for any other, write what the "
            "model needs to know in `instructions:`, naming only tools this agent has"
        )
    if read.unread:
        report.not_portable["instructions"] = (
            f"could not be read: an instruction function failed on the deps this importer built "
            f"({read.unread}). Write `instructions:` yourself"
        )

    said = getattr(agent, "model_settings", None)
    if callable(said):
        report.not_portable["model_settings"] = (
            "a callable: Pydantic AI re-evaluates it before every model request, and PACT's `settings:` is "
            "one block for the run, so there is no value here to carry"
        )
    elif isinstance(said, Mapping):
        settings.update(_settings_to_pact(said, report, "model_settings"))
        report.mapped.setdefault("model_settings", _AGENT_MAPS["model_settings"])

    shapes: dict[str, Any] = {}
    answers, refused, mode, loss = _output_type_to_answers(agent, shapes)
    if answers:
        out["answers-with"] = answers
        report.mapped["output_type"] = _AGENT_MAPS["output_type"]
    if mode:
        out["answers-with-mode"] = mode
    if loss:
        report.not_portable["output_type"] = loss
    if _prompted_template(agent) is not None:
        report.not_portable["output_type.template"] = (
            "its own words for asking for the answer (`PromptedOutput(template=...)` or "
            "`NativeOutput(template=...)`): PACT's `answers-with-mode:` asks in its own words, with the "
            "answer's shape, so this template is not used. Write the wording the model needs in `instructions:`"
        )
    report.unmapped.update(refused)

    files, kept, servers = _tool_files(read, connect, report, shapes)
    uses = sorted(files)
    if uses:
        report.mapped["toolsets"] = _AGENT_MAPS["toolsets"]
    elif read.losses or read.unknown:
        report.not_portable["toolsets"] = (
            "none of its toolsets can be read without starting a run, so no tool was carried"
        )
    if any(leaf.needs_a_person for leaf in read.leaves):
        report.mapped["requires_approval"] = "`needs-a-person: yes` on the action, in each tool's own file"
    if names := [f"`{shown}` is offered as `{as_pact}`" for shown, as_pact in kept if shown != as_pact]:
        report.not_portable["toolsets.names"] = (
            "a PACT tool is shown to a model as its file's name and its action's, so these names change: "
            + "; ".join(names)
            + ". Give the toolset a prefix in Pydantic AI (`PrefixedToolset`) to keep a name exactly"
        )
    report.not_portable.update(read.losses)
    report.unmapped.update(read.unknown)

    if capabilities := _authored_capabilities(agent):
        uses = sorted(set(uses) | set(_live_capabilities(capabilities, settings, report)))
    if uses:
        out["uses"] = uses
    if settings:
        out["settings"] = settings

    for key, why in _AGENT_NOT_PORTABLE.items():
        if key in report.seen and key not in report.mapped and key not in report.unmapped:
            report.not_portable[key] = why + _which(key, read)

    report.still_to_write = _still_to_write(
        out,
        tools_named=bool(uses),
        has_policy=bool(report.mapped.get("requires_approval")),
        connect=connect,
        servers=servers,
    )
    return Found(out, files, servers, report, shapes)


def _which(key: str, read: Read) -> str:
    """The tools a per-tool loss is about, named after its reason."""
    named = {"tool_timeout": read.timeouts, "retries": read.retries, "prepare": dict.fromkeys(read.prepared)}
    return f" (here: {', '.join(f'`{n}`' for n in sorted(named[key]))})" if named.get(key) else ""


def _what_it_carries(agent: Any, read: Read) -> tuple[str, ...]:
    """Every part of this `Agent` that holds something an author chose (S1's `seen`).

    A constructor default is not the author's (`end_strategy='graceful'`, `output_type=str`,
    no deps), so it is not listed: reporting Pydantic AI's own defaults as losses is the
    same failure as staying quiet about a real one. `not_shown` is always listed: it is
    what no public read can rule out.
    """
    said = ["not_shown"]

    def carries(key: str, value: Any, default: Any = None) -> None:
        if value and value != default:
            said.append(key)

    for key in ("model", "name", "description", "model_settings", "event_stream_handler", "instrument"):
        carries(key, getattr(agent, key, None))
    carries("instructions", read.instructions or read.unread)
    carries("instructions.made-at-run-time", read.dynamic)
    carries("instructions.added-by-capabilities-or-toolsets", read.added or read.added_unread)
    carries("system_prompts", read.system_prompts)
    carries("output_type", getattr(agent, "output_type", str), default=str)
    carries("output_type.template", _prompted_template(agent) is not None)
    carries("end_strategy", getattr(agent, "end_strategy", "graceful"), default="graceful")
    carries("deps_type", getattr(agent, "deps_type", object), default=object)
    carries("validation_context", getattr(agent, "validation_context", None))
    carries("tool_timeout", read.timeouts)
    carries("retries", read.retries)
    carries("prepare", read.prepared)
    carries("toolsets", [leaf for leaf in read.leaves if leaf.tools] or read.losses or read.unknown)
    carries("requires_approval", [leaf for leaf in read.leaves if leaf.needs_a_person])
    carries("capabilities", _authored_capabilities(agent))
    return tuple(sorted(set(said)))


def tool_files_for(agent: Any, *, connect: str = "") -> dict[str, dict[str, Any]]:
    """`{name: body}` of each `tools/<name>.yaml` the agent's toolsets become (module docstring)."""
    return imported(agent, connect=connect).tools


def _tool_files(
    read: Read, connect: str, report: ImportReport, shapes: "dict[str, Any] | None" = None
) -> tuple[dict[str, dict[str, Any]], list[tuple[str, str]], tuple[str, ...]]:
    """The tool files; `(the name Pydantic AI showed, the name a PACT runtime shows)` per tool; and
    the MCP servers they reach, each a `resources/<name>.yaml` to write."""
    files: dict[str, dict[str, Any]] = {}
    whose: dict[str, str] = {}
    kept: list[tuple[str, str]] = []
    servers: list[str] = []

    def write(name: str, body: dict[str, Any], said: str) -> None:
        if name in files:  # one file name for two of the agent's toolsets: one would be lost
            raise NotImported(
                f"{whose[name]} and {said} would both be `tools/{name}.yaml`. Fix: give one of their "
                "toolsets a prefix of its own in Pydantic AI (`PrefixedToolset`), or rename the tool"
            )
        files[name], whose[name] = body, said

    for leaf in read.leaves:
        if not leaf.tools:
            continue
        if leaf.kind != "mcp":
            # One file per tool, named as the model was shown it, with one action of the same
            # name: offered under that name on PACT's own path and on budflow-core's alike.
            for tool, td in sorted(leaf.tools.items()):
                name = leaf.shown_as.get(tool, tool)
                action = _action(leaf, tool, td, f"tools.{name}", report, shapes)
                # The tool's own words describe the file, once: a model is shown the file's and
                # the action's together (budflow-core's `tools.py`), so not twice.
                body: dict[str, Any] = {"description": action.pop("description", "") or f"The {name} tool."}
                if connect:
                    body["connect"] = connect
                body["actions"] = {name: action}
                write(name, body, f"the Python tool `{name}`")
            continue
        name = leaf.name or f"mcp-{len(servers) + 1}"
        servers.append(name)
        actions = {
            tool: _action(leaf, tool, td, f"tools.{name}.{tool}", report, shapes)
            for tool, td in sorted(leaf.tools.items())
        }
        body = {
            "description": f"The tools of the {name} server, as a Pydantic AI agent was given them.",
            "connect": name,
            "actions": actions,
        }
        write(name, body, f"the MCP server `{name}`")
        # As budflow-core offers an action (`tools.offered_as`): `<file>_<action>`, or the file's own
        # name when its one action is named like it.
        kept += [
            (leaf.shown_as.get(tool, tool), name if list(actions) == [name] else f"{name}_{tool}")
            for tool in sorted(leaf.tools)
        ]
        report.not_portable[f"tools.{name}.wire-shape"] = _MCP_SHAPE
    return files, kept, tuple(servers)


def _action(
    leaf: Leaf, tool: str, td: Any, where: str, report: ImportReport, shapes: "dict[str, Any] | None"
) -> dict[str, Any]:
    """One tool as an action: its description, `takes:` from its argument schema, `answers-with:`
    from its return type (whole, or not at all: PACT's shapes are closed, so half a shape would
    refuse every answer the tool gives), the gate."""
    action: dict[str, Any] = {}
    if described := " ".join(str(td.description or "").split()):
        action["description"] = described
    schema = td.parameters_json_schema or {}
    required = set(schema.get("required") or ())
    takes: dict[str, str] = {}
    for arg, prop in (schema.get("properties") or {}).items():
        shape = shape_from_json_schema(prop if isinstance(prop, Mapping) else {}, schema.get("$defs"))
        if shape is None:
            report.not_portable[f"{where}.{arg}"] = (
                "an argument PACT's shapes cannot say (a nested object, or a list of them), so it is taken "
                "as `text`: the tool is sent what the model writes there"
            )
        line = shape.written() if shape else "text"
        takes[str(arg)] = line if arg in required or line.endswith(", optional") else f"{line}, optional"
    if takes:
        action["takes"] = takes
    returns = leaf.returns.get(tool) or {}
    if returns.get("anyOf") or returns.get("oneOf"):
        report.not_portable[f"{where}.returns"] = (
            "it returns one of several shapes, which `answers-with:` cannot say yet, so the action declares "
            "none and its result is read as it comes"
        )
    if returns.get("type") == "object":
        answers, refused = _schema_to_answers(returns, shapes)
        if answers and not refused:
            action["answers-with"] = answers
        elif refused:
            report.not_portable[f"{where}.returns"] = (
                f"what it returns has parts PACT's shapes cannot say ({', '.join(sorted(refused))}), so "
                "the action declares no `answers-with:` and its result is read as it comes"
            )
    if tool in leaf.needs_a_person:
        action["needs-a-person"] = "yes"
    if leaf.kind != "mcp" and td.metadata:  # an MCP tool's is the server's annotations
        report.not_portable[f"{where}.metadata"] = (
            "metadata on the tool's definition, for the host's own code to read; PACT has no field for it"
        )
    return action


def resource_file_for(name: str, endpoint: str, *, asks_to_connect: str = "") -> dict[str, Any]:
    """The body of one `resources/<name>.yaml`: the server the tools that say `connect: <name>` reach.

    `endpoint` is a name the platform team publishes for the server, never an
    address with a secret in it and never a command, so it is an argument and is
    refused when empty (a blank `endpoint:` loads and goes nowhere). `auth:` is not
    written: a guessed credential reference loads clean and cannot connect.
    `asks_to_connect` names the question a person is asked the first time a run
    reaches the server (`questions/<that>.yaml` is then owed).
    """
    called = str(name or "").strip()
    reaches = str(endpoint or "").strip()
    if not reaches:
        raise ValueError(
            f"`{called or 'this server'}` needs an endpoint: a name your platform team publishes for this MCP "
            "server. It is their list, not a file in here, and not a URL with a credential in it"
        )
    body: dict[str, Any] = {"resource-kind": "mcp-server", "endpoint": reaches}
    if asked := str(asks_to_connect or "").strip():
        body["asks-to-connect"] = asked
    body["description"] = f"{called}, as the host publishes it."
    return body


# ─────────────────────────────────────────────────── capabilities, models, output


def _live_capabilities(capabilities: list[Any], settings: dict[str, Any], report: ImportReport) -> list[str]:
    """The author's capability objects as what PACT can say of them (the live twin of
    `pydantic_ai_interop._read_capabilities`, keyed by `get_serialization_name()` so
    the two doors agree): `Thinking` is `settings.thinking:`, a crossing one a name
    on `uses:`, any other a named loss from the registry."""
    named: list[str] = []
    for capability in capabilities:
        kind = type(capability)
        try:
            name = kind.get_serialization_name() or kind.__name__
        except Exception:  # pragma: no cover - a custom capability may not have one
            name = kind.__name__
        where = f"capabilities.{name}"
        if name == "Thinking":
            said = _thinking(getattr(capability, "effort", True), where, report)
            if said is None:
                continue
            settings["thinking"] = said
            report.mapped[where] = _REGISTRY.capability("Thinking").pact
        elif _REGISTRY.crosses(name):
            row = _REGISTRY.capability(name)
            named.append(row.tool)
            report.mapped[where] = row.pact
            if name == "MCP":
                report.not_portable[f"{where}.wire-shape"] = _MCP_SHAPE
        else:
            report.not_portable[where] = _REGISTRY.why_not_portable(name)
    if any(k.startswith("capabilities.") for k in report.mapped):
        report.mapped["capabilities"] = _SPEC_MAPS["capabilities"]
    return named


def _authored_capabilities(agent: Any) -> list[Any]:
    """The capabilities somebody passed, without those every agent is given.

    Read off the public `root_capability`, and compared BY VALUE with the ones a
    bare agent carries (`_what_every_agent_carries`): Pydantic AI adds a
    default-constructed instance of each only when the author passed none, so an
    author's configured `ToolSearch(max_results=20)` differs from the injected one
    and is kept, and a bare `ToolSearch()` is byte-identical and is not.
    """
    root = getattr(agent, "root_capability", None)
    if root is None:
        return []
    automatic = _what_every_agent_carries()

    def injected(capability: Any) -> bool:
        for kind in automatic:
            if type(capability) is kind:
                try:
                    return bool(capability == kind())
                except Exception:  # pragma: no cover - a capability that will not compare
                    return True
        return False

    return [c for c in (getattr(root, "capabilities", ()) or ()) if not injected(c)]


@lru_cache(maxsize=1)
def _what_every_agent_carries() -> tuple[type, ...]:
    """The kinds of capability an agent has before its author gives it any: a bare agent's."""
    from pydantic_ai import Agent

    bare = Agent(defer_model_check=True)
    return tuple(type(c) for c in (getattr(bare.root_capability, "capabilities", ()) or ()))


def _model_id(model: Any) -> str:
    """The catalogue-shaped id of a bound model, `provider:name` (`Model.system`, `Model.model_name`)."""
    if isinstance(model, str):
        return model.strip()
    system = str(getattr(model, "system", "") or "").strip()
    named = str(getattr(model, "model_name", "") or "").strip()
    return f"{system}:{named}" if system and named else named


#: `pydantic_ai.output`'s markers, and the `answers-with-mode:` each one is (02P O4).
_MODES = {"ToolOutput": "tool", "NativeOutput": "native-json-schema", "PromptedOutput": "prompted"}


def _prompted_template(agent: Any) -> "str | bool | None":
    """The author's own template for asking for the answer (the public `template` that
    `PromptedOutput` and `NativeOutput` both hold; `False` asks for none), or None when
    Pydantic AI's is used."""
    written = getattr(agent, "output_type", None)
    marked = type(written).__name__ in ("PromptedOutput", "NativeOutput")
    return getattr(written, "template", None) if marked else None


def _output_type_to_answers(
    agent: Any, shapes: "dict[str, Any] | None" = None
) -> tuple[dict[str, str], dict[str, str], str, str]:
    """The output type as `answers-with:` lines, the mode it is asked for in, and the named loss
    when it has no PACT spelling. Read through the public `output_type` and `output_json_schema()`,
    the schema the model is sent. `str` (the default) is no declared shape and carries nothing."""
    import inspect

    from pydantic_ai.messages import BinaryContent

    written = getattr(agent, "output_type", str)
    mode = _MODES.get(type(written).__name__, "")
    if inspect.isclass(written) and issubclass(written, BinaryContent):
        return {}, {}, "", (
            "an answer that is a file the model makes: PACT answers with named fields, so write "
            "`answers-with:` with one, such as `picture: images` or `report: file`"
        )
    if type(written).__name__ == "TextOutput" or inspect.isfunction(written):
        return {}, {}, "", (
            "an output function: Pydantic AI hands the answer to code, and code does not cross. Write "
            "`answers-with:` from the function's arguments, then a stage that calls the action it does"
        )
    try:
        schema = agent.output_json_schema()
    except Exception as trouble:  # pragma: no cover - depends on the user's type
        return {}, {"output_type": f"its schema could not be built: {trouble}"}, "", ""
    if not isinstance(schema, Mapping) or schema == {"type": "string"}:
        return {}, {}, "", ""
    if schema.get("type") != "object":
        many = schema.get("anyOf") or schema.get("oneOf")
        said = shape_from_json_schema(schema, schema.get("$defs"))
        return {}, {}, "", (
            f"a choice between {len(many)} answer shapes, which `answers-with:` cannot say yet: write the "
            "one this agent should answer with"
            if isinstance(many, list) else
            f"a bare {said.written() if said else 'value'} answer: PACT answers with named fields, so write "
            f"`answers-with:` with one, such as `answer: {said.written() if said else 'text'}`"
        )
    answers, refused = _schema_to_answers(schema, shapes)
    return answers, {f"output_type.{k}": v for k, v in refused.items()}, mode if answers else "", ""
