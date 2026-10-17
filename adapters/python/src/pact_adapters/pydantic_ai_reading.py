"""A live Pydantic AI `Agent`, read through its public API only (02P A3, A5, T12).

`from_pydantic_ai_agent` used to read nine private attributes of `Agent`
(`_instructions`, `_system_prompts`, `_tool_timeout`, ...): names a release may
move without notice, and a host that forbids private upstream reads could not
use the importer at all. This module reads the same agent the way any caller
of Pydantic AI can.

**Instructions and system prompts: a probe request.** The agent is run under
`Agent.override(model=FunctionModel(...))` with model requests switched off
(`models.override_allow_model_requests(False)`), so the only "model" it can
reach is the function here, which records what it was sent and stops the run
before anything answers: no tool is executed, nothing is validated. What it
was sent is exactly what a model would be sent: `ModelRequestParameters.
instruction_parts` (`PA/models/__init__.py:231`), each marked `dynamic` when a
function, a template or a toolset made it (`PA/messages.py:1993`), and the
request's `SystemPromptPart`s, each with a `dynamic_ref` when it is re-made per
request (`PA/messages.py:223`). It is run at least twice: bare (its capabilities
replaced by one that adds nothing, no toolsets, no tools), whose static parts
are the author's words, and as it is, whose further parts its capabilities
and toolsets added (a capability's own instructions, an MCP server's, a
`FunctionToolset(instructions=...)`): counted and named, never carried as the
author's. When the full run fails, its capabilities and its tools are run
apart, and only a failure of what can add a part (a capability, a toolset's
instructions) makes what they add a named loss: a tool's `prepare=` or a
filter that fails adds nothing, and the toolset walk names it. A
dynamic part is code (02P §1 rule 3), and is counted, never carried. Pydantic
AI's own template for a prompted answer is a static part
(`PA/models/__init__.py:836-838`) and is dropped, being exactly the request's
`prompted_output_instructions` (an author's own `PromptedOutput(template=...)`
or `NativeOutput(template=...)` is named by `pydantic_ai_live`); and an
`@agent.system_prompt` function not marked dynamic writes a plain
`SystemPromptPart`, which nothing public tells from a written string, so
`pydantic_ai_live` names that loss whenever system prompts are carried.

The run needs deps of the agent's own `deps_type`. The importer builds them:
`None` for an agent with none, `deps_type()` when every field has a default,
and otherwise a stand-in that answers every attribute, call, item and await
with itself and reads as a marker. A part whose text holds the marker was made
from deps, so it is dynamic whatever it was declared as. A function that still
fails is reported with what it raised, and the instructions are then a named
loss as a whole.

**Tools: `agent.toolsets` and each toolset's `get_tools`.** Every wrapper
(`CombinedToolset`, `PrefixedToolset`, `RenamedToolset`, `FilteredToolset`,
`ApprovalRequiredToolset`, `PreparedToolset`, `SetMetadataToolset`, ...) is
walked through its public attributes down to the toolsets that hold tools,
whose `get_tools` (with a `RunContext` built here) says what each publishes. A
prefix becomes the leaf's name, a rename the name its tools are shown as, a
filter keeps what its `get_tools` keeps and is reported as code (one that
fails on the deps built here is named, and keeps everything), an approval
wrapper marks its tools as needing a person. An MCP server is opened to list
its tools, as every run of the agent opens it; one that cannot be opened
refuses the import (`openapi.NotImported`), since only it knows its tools.
"""

from __future__ import annotations

import asyncio
import dataclasses
import re
import threading
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

__all__ = ["Leaf", "Read", "read_agent", "MARK"]

#: What the stand-in deps read as. A part holding it was made from deps.
MARK = "⁣deps⁣"


@dataclass
class Leaf:
    """One toolset that holds tools, as the agent shows them to a model."""

    #: `function` (a `FunctionToolset`), `external` (an `ExternalToolset`) or `mcp`.
    kind: str
    #: The leaf's prefix (outermost first, joined by `_`), else its `id`, else "".
    name: str
    #: `{the name the leaf publishes: ToolDefinition}`, after its filters.
    tools: dict[str, Any] = field(default_factory=dict)
    #: `{the name the leaf publishes: the name a model is shown}`.
    shown_as: dict[str, str] = field(default_factory=dict)
    #: The names (as the leaf publishes them) whose every call waits for a person.
    needs_a_person: set[str] = field(default_factory=set)
    #: `{tool name: what its return schema is}`, for `answers-with:`.
    returns: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: The toolset itself, asked for its instructions when the agent's run with it fails.
    toolset: Any = field(default=None, repr=False, compare=False)


@dataclass
class Read:
    """Everything a live `Agent` shows of itself through public names."""

    instructions: list[str] = field(default_factory=list)
    system_prompts: list[str] = field(default_factory=list)
    #: How many instruction or system-prompt parts were made by code at run time.
    dynamic: int = 0
    #: How many instruction parts the agent's capabilities and toolsets add (not the author's).
    added: int = 0
    #: Why no instruction could be read at all ("" when the probe ran).
    unread: str = ""
    #: Why what the capabilities and toolsets add could not be read: a capability, a toolset's
    #: instructions, or the two together failed where the bare run did not ("" when nothing that
    #: could add a part failed, or `unread` already says why).
    added_unread: str = ""
    leaves: list[Leaf] = field(default_factory=list)
    #: `{report key: why}`: what the walk found that is code, or a toolset it cannot read.
    losses: dict[str, str] = field(default_factory=dict)
    #: `{report key: what it was}`: a toolset kind the walk has never seen.
    unknown: dict[str, str] = field(default_factory=dict)
    #: The timeouts the agent's own tools carry (`Tool.timeout`, or the toolset's).
    timeouts: dict[str, float] = field(default_factory=dict)
    #: The retry budgets its own tools carry (`Tool.max_retries`, or the toolset's).
    retries: dict[str, int] = field(default_factory=dict)
    #: The tools whose definition a `prepare=` function makes per step.
    prepared: list[str] = field(default_factory=list)


def read_agent(agent: Any) -> Read:
    """`agent` read through its public API: its own run of the probe and of each toolset.

    Run on a thread of its own with its own event loop, so it can be called from
    sync code and from inside a running loop (a CLI or an MCP server) alike.
    """
    box: dict[str, Any] = {}

    def run() -> None:
        try:
            box["read"] = asyncio.run(_read(agent))
        except BaseException as exc:  # handed back to the caller's thread
            box["error"] = exc

    worker = threading.Thread(target=run, name="pact-read-agent")
    worker.start()
    worker.join()
    if "error" in box:
        raise box["error"]
    return box["read"]


async def _read(agent: Any) -> Read:
    from pydantic_ai import RunContext
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.usage import RunUsage

    read = Read()
    deps = _deps_for(getattr(agent, "deps_type", None))
    left_to_ask = await _probe(agent, deps, read)
    ctx = RunContext(deps=deps, model=FunctionModel(_never), usage=RunUsage())
    for i, toolset in enumerate(getattr(agent, "toolsets", ()) or ()):
        for shown, (leaf, name) in (await _walk(toolset, ctx, read, f"toolsets[{i}]")).items():
            leaf.shown_as[name] = shown
    for leaf in read.leaves:  # a filter's leftovers: nothing shows them
        leaf.tools = {n: td for n, td in leaf.tools.items() if n in leaf.shown_as}
    if left_to_ask:
        await _what_the_toolsets_say(read, ctx, left_to_ask)
    return read


def _never(messages: Any, info: Any) -> Any:  # pragma: no cover - the walk makes no request
    raise RuntimeError("the importer asks no model anything")


#: Every kind of answer a model can be asked for, so the probe is refused by no output type.
_ANY_ANSWER = {
    "supports_tools": True,
    "supports_json_schema_output": True,
    "supports_json_object_output": True,
    "supports_image_output": True,
}


class _Probed(Exception):
    """The probe saw the request; the run stops here."""


#: The agent with nothing a capability or a toolset adds: its capabilities replaced (`Agent.override(
#: spec=...)`, `PA/agent/__init__.py:2202`) by one that changes nothing in a first request
#: (`ReinjectSystemPrompt` re-sends the system prompt on later ones), and no toolsets or tools.
_BARE = {"spec": {"capabilities": ["ReinjectSystemPrompt"]}, "toolsets": [], "tools": []}
#: The agent with its capabilities and none of its toolsets or tools.
_CAPABILITIES_ONLY = {"toolsets": [], "tools": []}
#: The agent with its toolsets and tools and none of its capabilities.
_TOOLS_ONLY = {"spec": {"capabilities": ["ReinjectSystemPrompt"]}}


async def _probe(agent: Any, deps: Any, read: Read) -> str:
    """The author's words, from the agent run bare; and what its capabilities and toolsets add,
    from the agent run as it is (when that run reaches a model).

    Only the bare run shows what the author wrote as the agent's instructions: a capability adds
    its own (`get_instructions()`, such as the harness's `AskUser`), an MCP server its server's
    (`include_instructions=True`, `PA/mcp.py:1280`) and a `FunctionToolset(instructions=...)` its
    own (`toolsets/function.py:619`), each a part not marked dynamic. A part the full run has and
    the bare one does not is theirs, counted in `added`.

    When the full run fails, the two halves are run apart: the capabilities without the tools, and
    the tools and toolsets without the capabilities. A capability that fails (its instruction
    function on the deps built here) leaves what the capabilities add unknown, and `added_unread`
    says why. The tools' half also fails on a tool's `prepare=` or a toolset's filter, which can add
    no instruction and which the toolset walk names; so when only that half fails, what the
    toolsets add is asked of each of them after the walk (`_what_the_toolsets_say`), and this
    returns why their half failed. It returns "" when nothing is left to ask.
    """
    from pydantic_ai.messages import ModelRequest, SystemPromptPart

    full = await _ask(agent, deps, {})
    bare = await _ask(agent, deps, _BARE)
    if isinstance(bare, str):
        read.unread = bare
        return ""
    static, read.dynamic = _parts(bare)
    read.instructions = list(static)
    left_to_ask = ""
    if not isinstance(full, str):
        read.added += _more_than(full, static, read.dynamic)
    else:
        capabilities = await _ask(agent, deps, _CAPABILITIES_ONLY)
        tools = await _ask(agent, deps, _TOOLS_ONLY)
        for half in (capabilities, tools):
            if not isinstance(half, str):
                read.added += _more_than(half, static, read.dynamic)
        if isinstance(capabilities, str):
            read.added_unread = _without_addresses(capabilities)
        elif not isinstance(tools, str):  # each half runs and the two together do not
            read.added_unread = _without_addresses(full)
        if isinstance(tools, str):
            left_to_ask = _without_addresses(tools)
    for message in bare[0]:
        for part in message.parts if isinstance(message, ModelRequest) else ():
            if not isinstance(part, SystemPromptPart):
                continue
            if part.dynamic_ref is not None or MARK in part.content:
                read.dynamic += 1
            elif text := part.content.strip():
                read.system_prompts.append(text)
    return left_to_ask


def _more_than(asked: tuple[list[Any], Any], static: list[str], dynamic: int) -> int:
    """How many instruction parts a probed request has beyond the bare run's (`static`, `dynamic`)."""
    in_it, its_dynamic = _parts(asked)
    left = list(static)
    more = 0
    for text in in_it:
        if text in left:
            left.remove(text)
        else:
            more += 1
    return more + max(0, its_dynamic - dynamic)


async def _what_the_toolsets_say(read: Read, ctx: Any, why: str) -> None:
    """What the agent's toolsets add to the instructions, asked of each toolset that holds tools
    (its public `get_instructions`, an MCP server's inside `async with`, as a run opens it), when
    the run with them failed (`why`) before any request was made. A toolset the walk could not
    list (one a function builds per run, or a kind it does not read) may add some too, so what
    they add is then unknown, as it is when one of them fails here."""
    if read.unknown or any(text == _BUILT_PER_RUN for text in read.losses.values()):
        read.added_unread = read.added_unread or why
        return
    for leaf in read.leaves:
        try:
            if leaf.kind == "mcp":
                async with leaf.toolset:
                    said = await leaf.toolset.get_instructions(ctx)
            else:
                said = await leaf.toolset.get_instructions(ctx)
        except Exception as exc:  # the author's instruction function failed on the deps built here
            read.added_unread = read.added_unread or _without_addresses(_said(exc))
            return
        if said is None:
            continue
        parts = [said] if isinstance(said, str) or not isinstance(said, (list, tuple)) else said
        read.added += sum(1 for part in parts if str(getattr(part, "content", part)).strip())


def _parts(asked: tuple[list[Any], Any]) -> tuple[list[str], int]:
    """A probed request's instruction parts: the static texts, and how many are dynamic.

    Pydantic AI's own words for a prompted answer (`PromptedOutput`) are added as a part that is
    not dynamic (`PA/models/__init__.py:836-838`): its template, not the author's, so not counted.
    """
    params = asked[1].model_request_parameters
    theirs = params.prompted_output_instructions
    static: list[str] = []
    dynamic = 0
    for part in params.instruction_parts or ():
        if theirs and part.content == theirs:
            continue
        if part.dynamic or MARK in part.content:
            dynamic += 1
        elif text := part.content.strip():
            static.append(text)
    return static, dynamic


async def _ask(agent: Any, deps: Any, how: dict[str, Any]) -> "tuple[list[Any], Any] | str":
    """The first request the agent makes under `how` (`Agent.override`): `(messages, info)`, or why
    it made none (the author's code failed before any request was made)."""
    from pydantic_ai.models import override_allow_model_requests
    from pydantic_ai.models.function import FunctionModel

    seen: dict[str, Any] = {}

    def capture(messages: list[Any], info: Any) -> Any:
        seen["asked"] = (messages, info)
        raise _Probed

    async def streamed(messages: list[Any], info: Any) -> Any:  # a run a capability streams
        capture(messages, info)
        yield ""  # pragma: no cover - never reached

    # A model that can be asked for every kind of answer, so no output type is refused before
    # the request is made (`ModelProfile`, `PA/profiles/__init__.py:54`).
    model = FunctionModel(capture, stream_function=streamed, profile=_ANY_ANSWER)
    try:
        with override_allow_model_requests(False), agent.override(model=model, **how):
            await agent.run("", deps=deps)
    except _Probed:
        return seen["asked"]
    except Exception as exc:
        return _said(exc)
    return "the agent ended its run without asking a model anything"  # pragma: no cover


def _deps_for(deps_type: Any) -> Any:
    """Deps of the agent's own type: none, its defaults, or the stand-in."""
    if deps_type in (None, type(None), object):
        return None
    try:
        return deps_type()
    except Exception:
        return _StandIn()


class _StandIn:
    """Deps nobody could build: every question about them is answered with nothing."""

    def __getattr__(self, name: str) -> "_StandIn":
        if name.startswith("__"):
            raise AttributeError(name)
        return self

    def __call__(self, *args: Any, **kwargs: Any) -> "_StandIn":
        return self

    def __getitem__(self, key: Any) -> "_StandIn":
        return self

    def __await__(self) -> Any:  # awaiting it gives itself, so its marker reaches the words
        return self
        yield  # pragma: no cover - makes this a generator

    def __iter__(self) -> Any:
        return iter(())

    def __bool__(self) -> bool:
        return False

    def __len__(self) -> int:
        return 0

    def __str__(self) -> str:
        return MARK

    __repr__ = __str__

    def __format__(self, spec: str) -> str:
        return MARK


# ─────────────────────────────────────────────────────────────── the toolset walk


async def _walk(toolset: Any, ctx: Any, read: Read, where: str, prefix: str = "") -> dict[str, tuple[Leaf, str]]:
    """One toolset, recursively: `{the name a model is shown: (its leaf, the leaf's own name)}`.

    Each wrapper is applied as Pydantic AI applies it, to the names the level
    below it shows (`PA/toolsets/prefixed.py:24`, `renamed.py:21`); a wrapper
    whose body is code keeps the names its own `get_tools` keeps. `prefix` is the
    prefixes above this level, outermost first, which name the leaves below.
    """
    from pydantic_ai import toolsets as ts
    from pydantic_ai.capabilities import AbstractCapability

    kind = type(toolset)
    MCPToolset = _mcp_toolset()
    if isinstance(toolset, ts.CombinedToolset):
        out: dict[str, tuple[Leaf, str]] = {}
        for i, inner in enumerate(toolset.toolsets):
            out.update(await _walk(inner, ctx, read, f"{where}[{i}]", prefix))
        return out
    if isinstance(toolset, ts.DynamicToolset):
        read.losses[where] = _BUILT_PER_RUN
        return {}
    if isinstance(getattr(toolset, "capability", None), AbstractCapability):
        # The tools a capability brings (`Planning`'s `write_plan`, ...) are that capability's,
        # and it is named in the report; they are not the author's to import as tool files. The
        # wrapper that binds them to it says so in its public `capability` field
        # (`PA/capabilities/combined.py:407`).
        return {}
    if isinstance(toolset, ts.WrapperToolset):
        if kind is ts.PrefixedToolset:
            below = f"{prefix}_{toolset.prefix}" if prefix else toolset.prefix
            inner = await _walk(toolset.wrapped, ctx, read, f"{where}.wrapped", below)
            return {f"{toolset.prefix}_{n}": v for n, v in inner.items()}
        inner = await _walk(toolset.wrapped, ctx, read, f"{where}.wrapped", prefix)
        if kind is ts.RenamedToolset:
            old_to_new = {old: new for new, old in toolset.name_map.items()}
            return {old_to_new.get(n, n): v for n, v in inner.items()}
        if kind is ts.ApprovalRequiredToolset:
            for leaf, name in inner.values():
                leaf.needs_a_person.add(name)
            if toolset.approval_required_func is not _default_approval():
                read.losses[f"{where}.approval"] = (
                    "a function decides which calls need a person, and code does not cross: every call of "
                    "these tools asks a person here (`needs-a-person: yes`). Write a policy rule that says "
                    "which calls to ask about, if not all"
                )
            return inner
        if kind in (ts.FilteredToolset, ts.PreparedToolset, ts.SetMetadataToolset):
            read.losses[f"{where}.{_word(kind)}"] = _WRAPPER_LOSS[_word(kind)]
            try:
                kept = set(await toolset.get_tools(ctx))
            except Exception as exc:  # the author's function failed on the deps built here
                read.losses[f"{where}.{_word(kind)}"] = (
                    f"a function that decides these tools ({_word(kind)}) failed on the deps this importer "
                    f"built ({_said(exc)}), so every tool below it is carried as it is. Write "
                    "`available-when:` on a tool for one that is offered only sometimes"
                )
                return inner
            for n, (leaf, name) in list(inner.items()):
                if n not in kept:
                    del inner[n]
                    leaf.tools.pop(name, None)
            return inner
        if kind not in (ts.WrapperToolset, ts.DeferredLoadingToolset, ts.IncludeReturnSchemasToolset):
            read.unknown[where] = f"a {kind.__name__}, a toolset wrapper this importer does not read"
        return inner
    if isinstance(toolset, (ts.FunctionToolset, ts.ExternalToolset, MCPToolset)):
        leaf = Leaf(
            kind="mcp" if isinstance(toolset, MCPToolset) else
            "external" if isinstance(toolset, ts.ExternalToolset) else "function",
            name=prefix or _own_id(toolset),
            toolset=toolset,
        )
        for name, tool in (await _tools_of(toolset, ctx, read, where, leaf.name)).items():
            leaf.tools[name] = tool.tool_def
            if tool.tool_def.kind == "unapproved":
                leaf.needs_a_person.add(name)
            if tool.tool_def.return_schema and not isinstance(toolset, MCPToolset):
                # An MCP server's own `outputSchema` is the server's to publish and PACT's drift
                # check reads it (`mcp_bridge`); only a Python tool's return type is the author's.
                leaf.returns[name] = dict(tool.tool_def.return_schema)
        if isinstance(toolset, ts.FunctionToolset):
            _own_tools(toolset, read)
        read.leaves.append(leaf)
        return {name: (leaf, name) for name in leaf.tools}
    read.unknown[where] = f"a {kind.__name__}, a kind of toolset this importer does not read"
    return {}


async def _tools_of(toolset: Any, ctx: Any, read: Read, where: str, name: str) -> dict[str, Any]:
    """What a leaf publishes (`get_tools`). A function toolset whose `prepare=` functions fail on
    the deps built here is carried as its functions declare it (`FunctionToolset.tools`, each
    `Tool.tool_def`); an MCP server that cannot be opened refuses the import, since its tools
    are known only to it. The refusal names the server by its name, where it sits and the kind
    of its transport, never by its address: a server's URL or command line may carry a
    credential, and the refusal is printed."""
    try:
        return await toolset.get_tools(ctx)
    except Exception as exc:
        from pydantic_ai.toolsets import FunctionToolset

        from .openapi import NotImported

        if isinstance(toolset, FunctionToolset):
            read.losses[where] = (
                f"its tools' definitions could not be made with the deps this importer built "
                f"({_said(exc)}), so they are carried as their functions declare them, before any "
                "`prepare=` function. Narrow a stage with `may-use:` for a tool offered only sometimes"
            )
            return dict(toolset.tools)
        transport = getattr(getattr(toolset, "client", None), "transport", None)
        called = f"`{name}`, " if name else ""
        raise NotImported(
            f"the agent's MCP server {called}at `{where}` (a "
            f"{type(transport or toolset).__name__}) could not list its tools ({_without_addresses(_said(exc))}), "
            "and only it knows them. Fix: start the server, or import where it can be reached"
        ) from None


def _said(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {' '.join(str(exc).split())}"


def _without_addresses(text: str) -> str:
    """`text` with every URL in it cut to its scheme and host: an error from a transport may quote
    the address it failed on, and a path or query may carry a credential."""

    def host(found: "re.Match[str]") -> str:
        try:
            parts = urlsplit(found.group(0))
            return f"{parts.scheme}://{parts.hostname or ''}"
        except ValueError:
            return "<an address>"

    return re.sub(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s'\"<>)]+", host, text)


def _own_id(toolset: Any) -> str:
    """A toolset's `id`, when its author gave one: Pydantic AI names the agent's own tools `<agent>`."""
    said = str(getattr(toolset, "id", None) or "")
    return "" if said.startswith("<") else said


def _mcp_toolset() -> type:
    """`pydantic_ai.mcp.MCPToolset`, or a class nothing is an instance of when FastMCP is not
    installed (no agent can then hold an MCP server)."""
    try:
        from pydantic_ai.mcp import MCPToolset
    except ImportError:
        return type("NoMCPToolset", (), {})
    return MCPToolset


def _own_tools(toolset: Any, read: Read) -> None:
    """What a `FunctionToolset`'s own tools carry that their definitions do not show."""
    for name, tool in toolset.tools.items():
        if tool.prepare is not None:
            read.prepared.append(str(name))
        timeout = tool.timeout if tool.timeout is not None else toolset.timeout
        if timeout is not None:
            read.timeouts[str(name)] = float(timeout)
        retries = tool.max_retries if tool.max_retries is not None else toolset.max_retries
        if retries is not None:
            read.retries[str(name)] = int(retries)


def _default_approval() -> Any:
    """`ApprovalRequiredToolset`'s own default: every call needs a person (`dataclasses.fields`)."""
    from pydantic_ai.toolsets import ApprovalRequiredToolset

    (found,) = [f for f in dataclasses.fields(ApprovalRequiredToolset) if f.name == "approval_required_func"]
    return found.default


def _word(kind: type) -> str:
    return {"FilteredToolset": "filter", "PreparedToolset": "prepare", "SetMetadataToolset": "metadata"}[
        kind.__name__
    ]


#: What a toolset a function builds for each run becomes in the report.
_BUILT_PER_RUN = (
    "a toolset a function builds for each run (`@agent.toolset` or a `ToolsetFunc`): there is no "
    "list of its tools without starting a run, so none is carried. Write the tools it can return "
    "as tool files, with `available-when:` for the ones it picks"
)

#: What each wrapper whose body is code becomes in the report.
_WRAPPER_LOSS = {
    "filter": (
        "a function picks which of these tools are offered, and code does not cross: the tools it offered "
        "with the deps the importer built are carried. Write `available-when:` on a tool for one that is "
        "offered only sometimes"
    ),
    "prepare": (
        "a function rewrites these tools' definitions for each step, and code does not cross: the "
        "definitions it made with the deps the importer built are carried. Narrow a stage with `may-use:` "
        "instead"
    ),
    "metadata": (
        "metadata set on these tools' definitions, for the host's own code to read; PACT has no field for "
        "it"
    ),
}
