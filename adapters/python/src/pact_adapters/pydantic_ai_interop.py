"""PACT and Pydantic AI, in both directions.

Every other framework in this repository defines its agents in **code**, and
`importing.py` says why that stops an importer existing: importing code means
either executing it (D17 and D23 forbid it) or parsing it (a different project).
That sentence was true of all seven targets and is no longer true of this one.

**Pydantic AI ships a declarative agent format.** `pydantic_ai.agent.AgentSpec`
is a YAML/JSON document with `model:`, `instructions:`, `model_settings:`,
`output_schema:`, `deps_schema:` and `capabilities:`, loaded by
`Agent.from_file()`. It is a config file, exactly like an Anthropic Messages
request, so reading one executes nothing. That makes Pydantic AI the first
target here that can be imported *as a specification* rather than as a facade.

So there are three doors, and they are different sizes on purpose.

* `from_pydantic_ai_spec()` — a spec FILE becomes a PACT agent. Nothing runs.
  This is the door `pact-import --as pydantic-ai-spec` opens.
* `pydantic_ai_live.from_pydantic_ai_agent()` — a LIVE `Agent` object becomes a
  PACT agent. The caller has already imported their own module in their own
  process; PACT never reads their source, and reads the object through Pydantic
  AI's public API only (`pydantic_ai_reading`: one probe request to a
  `FunctionModel`, which runs no tool, and each toolset's `get_tools`). This is
  what covers the agents that are defined in code, which is most of them. What
  it can see is what the OBJECT shows, which is less than what the CODE says —
  a `@agent.instructions` function's text is made per run, not a sentence the
  author wrote, and the report says so rather than inventing one.
  `pydantic_ai_trees.imported_agent()` writes either door's result as a tree's
  files.
* `to_pydantic_ai_spec()` — a PACT agent becomes a spec file plus a loss report.

## The one thing this module must not be read as claiming

Decision #5 is *harness lowering is mandatory: PACT owns loop semantics;
frameworks are model/tool transports*. `transports/pydantic_ai_transport.py` is
that: PACT drives, `direct.model_request` carries one model call, and the
authored `loop:`, `policy:`, `interceptors:` and ceilings are enforced by PACT's
own harness on every target identically.

`to_pydantic_ai_spec()` is the OTHER thing, and it is the thing a Pydantic AI
user actually wants: their stack, their `Agent`, their loop. The moment the loop
is Pydantic AI's, PACT's loop guarantees stop holding — not partially, not
approximately: `_agent_graph` has no stage vocabulary, no interceptor chain and
no gate. An export that emitted a `.yaml` and said nothing would be handing
somebody a file that looks like their governed agent and is not, which is the
exact defect `ExportReport` exists to make impossible. So every one of those
fields is named in `not_carried` with what stops being enforced.

Both doors are honest. Neither is the other.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import replace
from functools import lru_cache
from typing import Any, Mapping

from .exporting import ExportReport
from .holes import RUN_INPUTS, holes_in, rewritten, templates_in
from .importing import ImportReport
from .ir import AgentSpec as PactAgentSpec
from .loader import FIX as LOADER_FIX
from .loader import pact_binary
from .pydantic_ai_registry import registry
from .questions import Shape, object_schema
from .transports.pydantic_ai_transport import _SETTINGS, _translated
from .yes_no import said_yes

__all__ = [
    "shape_as_json_schema",
    "shape_from_json_schema",
    "return_schema_for",
    "from_pydantic_ai_spec",
    "to_pydantic_ai_spec",
    "usage_limits_for",
    "build_agent",
]


# ───────────────────────────── the answer shapes, as JSON Schema and back


def shape_as_json_schema(shape: Shape) -> dict[str, Any]:
    """One `answers-with:` line as the JSON Schema fragment that means it.

    Read off `questions.Shape` (`Shape.json_schema`), whose one table holds each
    shape's spellings, words and fragment: the vocabulary is closed and held in
    ONE place, so this module keeps no second table that would go stale the
    first time a shape is added.
    """
    return shape.json_schema()


def shape_from_json_schema(
    schema: Mapping[str, Any],
    defs: "Mapping[str, Any] | None" = None,
    named: "dict[str, Any] | None" = None,
    hint: str = "",
) -> "Shape | None":
    """One JSON Schema property as a PACT answer shape, or nothing.

    `None` is a real answer and is the important one. PACT's answer shapes are a
    closed set of eight plus `one of`; JSON Schema is not closed at all, so a
    nested object, an array of objects, a `oneOf` or an untyped property has no
    PACT spelling. Returning `None` is what puts it in the report instead of
    letting it be flattened to `text` — which would load, and would tell the
    author their nested `address` survived as a sentence.
    """
    if not isinstance(schema, Mapping):
        return None
    # 02P O2: what a Pydantic model's schema says of a field. A `$ref` into the
    # document's own `$defs` is read where it points (an `Enum` class is one); a
    # field that may be `null` (`X | None`, `anyOf: [X, null]`, `type: [x, null]`)
    # is `, optional`; a list of one shape is `list of` it; a string's `format`
    # says a date or a time. Anything else stays `None`, and is reported.
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        key = ref[len("#/$defs/"):]
        return shape_from_json_schema((defs or {}).get(key) or {}, defs, named, key)
    either = schema.get("anyOf") or schema.get("oneOf")
    if isinstance(either, list):
        kept = [x for x in either if not (isinstance(x, Mapping) and x.get("type") == "null")]
        one = shape_from_json_schema(kept[0], defs, named, hint) if len(kept) == 1 < len(either) else None
        return replace(one, optional=True) if one else None
    if isinstance(schema.get("type"), list):
        kinds = [t for t in schema["type"] if t != "null"]
        one = shape_from_json_schema({**schema, "type": kinds[0]}, defs, named, hint) if len(kinds) == 1 else None
        return replace(one, optional=True) if one and len(kinds) < len(schema["type"]) else one
    if schema.get("type") == "array" and isinstance(schema.get("items"), Mapping):
        each = shape_from_json_schema(schema["items"], defs, named, hint)
        return Shape("list", of=each) if each is not None and not each.optional else None
    if named is not None and schema.get("type") == "object" and isinstance(schema.get("properties"), Mapping):
        return _named_shape(schema, defs, named, hint)
    if schema.get("type") == "string" and schema.get("format") in _FORMATS:
        return Shape(_FORMATS[schema["format"]])
    # `enum` first: a property can carry both `type: string` and an `enum`, and
    # the enum is the stronger statement of the two. Dropping to the `type` when
    # an enum is present would lose the constraint INSIDE a property the report
    # has already called mapped — a loss `silent_drops` cannot see, because it
    # only counts keys and this one is carried.
    choices = schema.get("enum")
    if isinstance(choices, list) and choices:
        # `enum: [yes, no]` is the shape an author writes, and YAML hands it back
        # as `[True, False]` — `yes`/`no`/`on`/`off` are booleans in YAML 1.1 and
        # `AgentSpec.from_file` uses `yaml.safe_load`. So a two-value boolean
        # enum is `yes-or-no`, which is what the author meant and what PACT's own
        # vocabulary calls it. Checked as a SET so `[no, yes]` reads the same.
        if all(isinstance(c, bool) for c in choices) and set(choices) <= {True, False}:
            return Shape("yes-or-no")
        # Numbers and strings both become words: PACT's `one of` is a list of
        # literals and `one of 1, 2, 3` is a thing an author writes. `bool` is
        # excluded because it is an `int` subclass in Python and would otherwise
        # arrive here as `one of True, False`.
        if all(isinstance(c, (str, int, float)) and not isinstance(c, bool) for c in choices):
            return Shape("one-of", tuple(str(c) for c in choices))
        # A mixed enum, or one holding objects or lists. There is no PACT
        # spelling, and returning the bare `type` here would be the silent
        # narrowing this branch exists to prevent.
        return None
    said = schema.get("type")
    if said == "boolean":
        return Shape("yes-or-no")
    if said == "integer":
        return Shape("whole-number")
    if said == "number":
        return Shape("number")
    if said == "string":
        return Shape("text")
    return None


#: The string `format`s PACT has a shape for (`questions._KINDS`).
_FORMATS = {"date": "date", "time": "time", "date-time": "date-and-time"}


def _answers_with_schema(
    answers: Mapping[str, str], shapes: "Mapping[str, Any] | None" = None
) -> "dict[str, Any] | None":
    """A PACT `answers-with:` block as one `output_schema` object.

    Every property is `required` unless its line says `, optional` (02W §2.15),
    and that is not a default anybody fell into: a property left out of
    `required` with no such word would be claiming an authored line was
    optional when the document does not say so. `shapes` is the workspace's
    `shapes:`, so a line naming one is an object with its parts.
    """
    if not answers:
        return None
    return object_schema({str(k): Shape.parse(w, shapes) for k, w in answers.items()})


def return_schema_for(
    tool: Any, action: str, shapes: "Mapping[str, Any] | None" = None
) -> "dict[str, Any] | None":
    """What one action hands back (02P A4), as a `ToolDefinition.return_schema`.

    `tool` is an `ir.ToolSpec`; `action` is one of its `actions:` names, which
    for an MCP tool is the server's own tool name. `None` when the action
    declares no `answers-with:` — an absent return type, never an empty object,
    because `{}` would claim the action hands back nothing at all.

    The same builder as an agent's `output_schema`, so an action's result and an
    agent's answer that are written alike are checked alike. A host sets it on
    the tool's definition (`include_return_schema=True`, tools.py:735, or the
    `IncludeToolReturnSchemas` capability) to show it to the model, and checks
    the call's result against it itself: Pydantic AI only shows or clears a
    `return_schema` (models/__init__.py:2181) and never validates a result
    against it. An MCP server's own `outputSchema` arrives in the same field
    (mcp.py:1322), so the two can be compared before a run.
    """
    return _answers_with_schema(getattr(tool, "answers_with", {}).get(action) or {}, shapes)


# ─────────────────────────────────────── Pydantic AI  →  PACT


#: What PACT can say of each capability, and the sentence for one it cannot —
#: one table (`pydantic_ai_registry.yaml`, 02P §4) that both importers and the
#: exporter read, so a capability cannot read as one thing through the spec door
#: and another through the live one.
_REGISTRY = registry()


#: What each `AgentSpec` key becomes in PACT's words (`_SPEC_MAPS`), and the
#: keys that are facts about Pydantic AI's own loop or tooling, which PACT
#: deliberately does not own (`_SPEC_NOT_PORTABLE`) — each written out in the
#: registry rather than defaulted to "unsupported", for the reason
#: `exporting._RECORD_CANNOT_TAKE` gives: WHICH KIND of thing it is decides
#: whether losing it matters. Views over `_REGISTRY`, not copies.
_SPEC_MAPS: dict[str, str] = {k: r.pact for k, r in _REGISTRY.through("spec").items() if r.pact}
_SPEC_NOT_PORTABLE: dict[str, str] = {
    k: r.why for k, r in _REGISTRY.through("spec").items() if r.why
}

#: The `ModelSettings` keys `pydantic_ai_transport._SETTINGS` does NOT name, and
#: why PACT has no home for each. The transport's table is the authority on the
#: twelve that DO map; a key in neither (a thirteenth added by an SDK upgrade)
#: lands in the report as unmapped rather than in silence.
_SETTINGS_NOT_PORTABLE: dict[str, str] = {
    k: r.why for k, r in _REGISTRY.through("settings").items() if r.why
}

#: `Thinking(effort=...)` and PACT's `thinking:`. Pydantic AI's `ThinkingLevel`
#: is `bool | 'minimal'|'low'|'medium'|'high'|'xhigh'`; PACT's is four words.
#: `_translated` already goes one way; this is the inverse, and the two spellings
#: that have no PACT word come back reported rather than rounded.
_THINKING_BACK: dict[Any, str] = {
    True: "medium",
    False: "none",
    "low": "low",
    "medium": "medium",
    "high": "high",
}


#: 02P A11: the two Pydantic AI thinking levels PACT has no word for, as the nearest it has.
_ROUNDED: dict[str, str] = {"minimal": "low", "xhigh": "high"}


def _thinking(effort: Any, where: str, report: ImportReport) -> "str | None":
    """One Pydantic AI thinking level as PACT's `thinking:` word; `minimal` and `xhigh` are
    rounded to the nearest and the rounding is named, anything else unknown is unmapped."""
    key = effort if isinstance(effort, bool) else str(effort)
    if key in _ROUNDED:
        report.not_portable[f"{where}.rounded"] = (
            f"`{key}` is a thinking level PACT has no word for, so it is `{_ROUNDED[key]}`, the nearest "
            "of PACT's `none`, `low`, `medium`, `high`"
        )
        return _ROUNDED[key]
    said = _THINKING_BACK.get(key)
    if said is None:
        report.unmapped[where] = (
            f"`{effort}` is a Pydantic AI thinking level PACT has no word for — its `thinking:` is "
            "`none`, `low`, `medium`, `high`"
        )
    return said


def _settings_to_pact(
    settings: Mapping[str, Any], report: ImportReport, where: str
) -> dict[str, Any]:
    """One `ModelSettings` block as a PACT `settings:` block.

    The inverse of `pydantic_ai_transport._SETTINGS`, built by inverting that
    table rather than by writing a second one — so the two can never disagree
    about which twelve keys cross, which is the whole reason the transport's
    table is a module constant instead of a literal inside a method.
    """
    back = {v: k for k, v in _SETTINGS.items()}
    out: dict[str, Any] = {}
    for key, value in settings.items():
        authored = back.get(str(key))
        if authored is None:
            why = _SETTINGS_NOT_PORTABLE.get(str(key))
            if why:
                report.not_portable[f"{where}.{key}"] = why
            else:
                report.unmapped[f"{where}.{key}"] = (
                    f"a {type(value).__name__} `{key}` this SDK accepts and "
                    "PACT's closed `settings:` group has no key for"
                )
            continue
        if authored == "thinking":
            said = _thinking(value, f"{where}.thinking", report)
            if said is None:
                continue
            out["thinking"] = said
        elif authored == "tool-choice":
            said = _tool_choice_to_pact(value)
            if said is None:
                report.not_portable[f"{where}.tool_choice"] = (
                    "a `ToolOrOutput(...)` — *these function tools, plus the "
                    "output tool*. PACT's `tool-choice:` is `auto`, `required`, "
                    "`none` or one tool name, and has no way to say `plus the "
                    "output tool`, which is a fact about how this SDK ends a run"
                )
                continue
            out["tool-choice"] = said
        else:
            out[authored] = value
        report.mapped[f"{where}.{key}"] = f"`settings.{authored}:`"
    return out


def _tool_choice_to_pact(value: Any) -> "str | None":
    """One `ToolChoice` as PACT's `tool-choice:`, or nothing.

    `_translated` turns a bare tool name into `[name]` on the way out, because
    that is what `models._tool_choice.resolve_tool_choice` reads. Coming back, a
    one-entry list is that same name; a longer list is *these several tools*,
    which PACT cannot say and which is therefore reported rather than truncated
    to its first entry.
    """
    if isinstance(value, str):
        return value if value in ("auto", "required", "none") else None
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], str):
        return str(value[0])
    return None


def _instructions_text(written: Any) -> str:
    """An `AgentSpec.instructions` as one PACT `instructions:` field.

    A list is joined with a blank line between entries, which is the same shape
    `ir._text` produces for an author who wrote `instructions/` as a FOLDER —
    so a spec with three instruction strings and a PACT tree with three
    instruction files reach the model as the same bytes.
    """
    if isinstance(written, str):
        return written.strip()
    if isinstance(written, (list, tuple)):
        return "\n\n".join(str(x).strip() for x in written if str(x).strip())
    return ""


def _capability_name(entry: Any) -> tuple[str, Any]:
    """One `capabilities:` entry as `(name, argument)`.

    `agent-spec.md` gives three forms and this reads all three: `'Thinking'`,
    `{'Thinking': 'high'}` and `{'Thinking': {'effort': 'high'}}`. A reader that
    knew only the mapping form would report every bare-string capability as not
    understood, which is the form the docs use for the simplest cases.
    """
    if isinstance(entry, str):
        return entry, None
    if isinstance(entry, Mapping) and len(entry) == 1:
        (name, argument), = entry.items()
        return str(name), argument
    return "", None


def _read_capabilities(
    capabilities: Any, settings: dict[str, Any], report: ImportReport
) -> list[str]:
    """The `capabilities:` list, as whatever PACT can say of it.

    Returns the tool names to put on `uses:`. `Thinking` is the one capability
    that is pure configuration on both sides, so it lands in `settings:`; the
    five provider-adaptive tool capabilities become names on `uses:` and a
    `still_to_write` entry, because PACT will not invent a `tools/` file whose
    `takes:` and `spends-money:` nobody wrote.
    """
    uses: list[str] = []
    for i, entry in enumerate(capabilities or ()):
        name, argument = _capability_name(entry)
        if not name:
            report.unmapped[f"capabilities[{i}]"] = (
                f"a {type(entry).__name__} that is not one of the three spec "
                "forms (a name, `{name: value}`, or `{name: {kwargs}}`)"
            )
            continue
        where = f"capabilities.{name}"
        if name == "Thinking":
            effort: Any = True
            if isinstance(argument, Mapping):
                effort = argument.get("effort", True)
            elif argument is not None:
                effort = argument
            said = _thinking(effort, where, report)
            if said is None:
                continue
            settings["thinking"] = said
            report.mapped[where] = _REGISTRY.capability("Thinking").pact
        elif _REGISTRY.crosses(name):
            row = _REGISTRY.capability(name)
            uses.append(row.tool)
            report.mapped[where] = row.pact
            if name == "MCP":
                # The capability crosses; the PROTOCOL it will be spoken over
                # does not, and PACT has no field to record which shape it was.
                # Said on the way IN as well as out, because the author of an
                # imported agent is the person who will run it.
                report.not_portable[f"{where}.wire-shape"] = _MCP_SHAPE
        else:
            report.not_portable[where] = _REGISTRY.why_not_portable(name)
    return uses


#: The MCP wire shape this path speaks, and the two identifiers a reader has to
#: be handed before they ship anything over it.
#:
#: Written ONCE and reached by all three doors — both importers and the exporter
#: — for the registry's reason: a caveat that read one way through the
#: spec door and another through the live one is a caveat nobody believes.
#:
#: **Why it is here at all.** `docs/30-FRD.md` FR-4.1.14 does not merely prefer
#: the `2026-07-28` MCP shape, it REQUIRES it, and names `2025-11-25` as the
#: corpus shape not to target. RE-READ ON THE MOVE TO 2.54, when the pin this
#: paragraph quoted moved: the `mcp` extra of `pydantic-ai-slim` 2.54 pins
#: `fastmcp-slim[client]>=3.3.0,<5` (its pyproject.toml), which admits BOTH eras.
#: FastMCP 4 is built on MCP SDK v2, whose `mcp.types.LATEST_PROTOCOL_VERSION` is
#: `"2026-07-28"`, and `MCPToolset.__aenter__` opens a modern session with no
#: `initialize` handshake when `client.initialize_result` is `None` (mcp.py:1177).
#: FastMCP 3 is MCP SDK v1 (`"2025-11-25"`), and the same `__aenter__` awaits
#: `client.initialize_result` — the handshake era verbatim. So which shape a run
#: speaks is decided by which FastMCP the HOST installed, and the sentence now
#: says that instead of naming one shape for every install.
#:
#: **Why it is tolerable rather than a defect.** Pydantic AI owns the connection
#: on this path. The handshake happens in the author's process, on the author's
#: pin, through code PACT does not ship — the same reason `to_pydantic_ai_spec`
#: may hand over the loop at all. What would NOT be tolerable is a PACT-owned MCP
#: client built to this shape, and the sentence says so, because "we already do
#: this in the Pydantic AI bridge" is exactly how a forbidden shape becomes the
#: house default.
#:
#: **And why AD-71 gets its own half.** RE-DECIDED IN M5 W3, when the tripwire
#: that forces this paragraph to be re-read went off: the snapshot AD-71 asks for
#: now EXISTS. `resources/<server>.yaml` carries `tool-snapshot-digest:`,
#: `tool-snapshot-taken-at:` and `tool-snapshot-max-age:`; `mcp_bridge.digest_of`
#: takes a digest over the server's prose as well as its shapes, so AD-71's own
#: worked injection — a sentence rewritten under a byte-identical `tools/list` —
#: moves it; and `mcp_bridge.quarantined` is the fence `harness._system_for`
#: refuses external text without.
#:
#: The verdict on THIS path did not change, and the reason it did not is now a
#: different and narrower one, which is why the sentence is rewritten rather than
#: deleted. The export hands the loop to Pydantic AI. Nothing downstream of it
#: builds a system message through `_system_for`, so nothing fences; nothing
#: calls `check_snapshot`, so nothing pins. `MCPToolset(include_instructions=True)`
#: takes the server's `initialize` instructions and returns them as an
#: `InstructionPart` — unpinned, unfenced, unlabelled — and PACT is not in that
#: loop to say otherwise. `mcp_bridge.check_against_authored` is the one check
#: that does travel with the exported agent, and it is named here with its edge
#: rather than cited as the answer: it holds the server's tool NAMES and ARGUMENT
#: SCHEMAS against the authored ones and leaves prose entirely. Reported as
#: PARTIAL, because a mitigation reported without its limit is one nobody looks
#: at twice — and now with the two calls that close the gap, because a limit a
#: reader cannot act on is one they read past.
_MCP_SHAPE: str = (
    "the MCP wire shape, which is decided by the FastMCP the host installs, and "
    "one of the two it may be is one PACT's own FRD forbids. FR-4.1.14 requires "
    "the `2026-07-28` shape — stateless, no `initialize` handshake, no sessions, "
    "an MRTR `input_required` retry in place of server-initiated requests. "
    "`pydantic-ai-slim[mcp]` 2.54 pins `fastmcp-slim[client]>=3.3.0,<5`, which "
    "admits both eras: FastMCP 4, over MCP SDK v2 (whose "
    "`mcp.types.LATEST_PROTOCOL_VERSION` is `2026-07-28`), opens a modern session "
    "with no `initialize` handshake against a server that speaks it, and meets "
    "FR-4.1.14; FastMCP 3, over MCP SDK v1 (`2025-11-25`, the corpus shape "
    "FR-4.1.14 names as the wrong one), opens a session and awaits "
    "`client.initialize_result`, and does not. "
    "TOLERABLE ON THIS PATH ONLY, "
    "because Pydantic AI owns the connection: the handshake is theirs, in their "
    "process, on their pin, and PACT's harness makes no MCP call and ships no "
    "client. It is not a precedent — a PACT-owned MCP client built to the "
    "handshake shape would break FR-4.1.14 outright; install "
    "`fastmcp-slim[client]>=4` beside the exported agent so the modern shape is "
    "the one it can open. "
"AD-71 is NOT HELD here either, and since M5 W3 that is a statement about "
    "THIS PATH rather than about PACT. The snapshot AD-71 asks for now exists: "
    "`resources/<server>.yaml` carries `tool-snapshot-digest`, "
    "`tool-snapshot-taken-at` and `tool-snapshot-max-age`, `mcp_bridge.digest_of` "
    "covers the server's prose as well as its shapes, and `mcp_bridge.quarantined` "
    "is the fence `harness._system_for` refuses external text without. None of it "
    "reaches an exported agent: the export hands the loop to Pydantic AI, so no "
    "system message is built by `_system_for` and nothing calls "
    "`mcp_bridge.check_snapshot`, while "
    "`MCPToolset(include_instructions=True)` folds the server's `initialize` "
    "instructions into the agent's instruction set as an `InstructionPart` — "
    "unpinned, unfenced, unlabelled. So the drift check that does travel with the "
    "exported agent, "
    "`mcp_bridge.check_against_authored`, is PARTIAL mitigation and not AD-71: "
    "it compares tool NAMES and ARGUMENT SCHEMAS, so it sees a tool that "
    "appeared, vanished or moved an argument's type, and it does not see a "
    "description or an `initialize` instructions string the server rewrote under "
    "an unchanged tool list — which is the injection AD-71 was written from. "
    "fix: run this agent on `harness.run`, which fences server prose and places "
    "it after everything a person wrote, or call "
    "`mcp_bridge.check_snapshot(resource, published, instructions)` yourself "
    "before you use the exported agent"
)


def from_pydantic_ai_spec(
    spec: Mapping[str, Any], shapes: "dict[str, Any] | None" = None
) -> tuple[dict[str, Any], ImportReport]:
    """One Pydantic AI `AgentSpec` as a PACT agent, and everything it could not say.

    The first importer here whose source is a real agent SPECIFICATION rather
    than a facade or a single request. An A2A card carries a name and a URL; an
    Anthropic request carries one exchange. This carries the model, the
    instructions, the settings, the output shape and the capabilities — so the
    stub that comes back is a working agent short of its ceilings, its policy
    and its tools, rather than a name with nothing behind it.

    Nothing is executed. A spec is YAML; `Agent.from_file` is what runs it, and
    this is not that.

    A nested object of the output or deps schema is a shape with parts (02P O2),
    collected into `shapes` (`{name: {part: line}}`, for `workspace.yaml`'s
    `shapes:`) when the caller gives it, as an import into a tree does; otherwise
    `still_to_write` says which shapes to write.
    """
    report = ImportReport(kind="a Pydantic AI agent spec", seen=tuple(sorted(spec)))
    owed_shapes = shapes is None
    shapes = {} if shapes is None else shapes
    agent: dict[str, Any] = {}
    settings: dict[str, Any] = {}

    if model := str(spec.get("model") or "").strip():
        agent["model"] = catalogue_row_for(model)
        report.mapped["model"] = _SPEC_MAPS["model"]
    if name := str(spec.get("name") or "").strip():
        agent["name"] = name
        report.mapped["name"] = _SPEC_MAPS["name"]
    deps = spec.get("deps_schema") if isinstance(spec.get("deps_schema"), Mapping) else {}
    declared = set((deps.get("properties") or {}) if isinstance(deps.get("properties"), Mapping) else ())
    for key, said in (("description", str(spec.get("description") or "").strip()),
                      ("instructions", _instructions_text(spec.get("instructions")))):
        if said:
            agent[key] = _as_holes(said, declared, key, report)
            report.mapped[key] = _SPEC_MAPS[key]

    if isinstance(spec.get("model_settings"), Mapping):
        settings.update(_settings_to_pact(spec["model_settings"], report, "model_settings"))
        if "model_settings" not in report.mapped:
            # Every key inside went to `unmapped`/`not_portable` under its own
            # name, but the OUTER key is what `seen` holds, and a key nothing
            # accounts for is a silent drop by definition.
            report.mapped["model_settings"] = _SPEC_MAPS["model_settings"]

    if isinstance(spec.get("output_schema"), Mapping):
        answers, refused = _schema_to_answers(spec["output_schema"], shapes)
        if answers:
            agent["answers-with"] = answers
            # The MODE is deliberately not set. `AgentSpec.output_schema` builds a
            # `StructuredDict`, whose mode is `auto` — resolved per model from
            # `ModelProfile.default_structured_output_mode`. Writing
            # `answers-with-mode: native-json-schema` here would pin a decision
            # the source left to the model, on every model.
            report.mapped["output_schema"] = _SPEC_MAPS["output_schema"]
        for name, why in refused.items():
            report.unmapped[f"output_schema.{name}"] = why
        if not answers and not refused:
            report.unmapped["output_schema"] = "an object schema with no properties"

    if isinstance(spec.get("deps_schema"), Mapping):
        inputs, refused = _schema_to_answers(spec["deps_schema"], shapes)
        if inputs:
            agent["run-inputs"] = inputs
            report.mapped["deps_schema"] = _SPEC_MAPS["deps_schema"]
        for name, why in refused.items():
            report.unmapped[f"deps_schema.{name}"] = why

    if spec.get("capabilities"):
        uses = _read_capabilities(spec["capabilities"], settings, report)
        if uses:
            agent["uses"] = uses
        if "capabilities" not in report.mapped:
            report.mapped["capabilities"] = _SPEC_MAPS["capabilities"]

    if settings:
        agent["settings"] = settings

    for key, why in _SPEC_NOT_PORTABLE.items():
        if key in spec or (key == "json_schema_path" and "$schema" in spec):
            report.not_portable[key] = why
    if "$schema" in spec:
        report.not_portable["$schema"] = _SPEC_NOT_PORTABLE["json_schema_path"]

    for key in spec:
        if key not in report.mapped and key not in report.not_portable:
            report.unmapped[key] = (
                f"a {type(spec[key]).__name__} this importer does not read"
            )

    report.still_to_write = _still_to_write(agent, tools_named=bool(agent.get("uses")))
    if owed_shapes and shapes:
        report.still_to_write += (shapes_owed(shapes),)
    return agent, report


def _as_template(text: str, inputs: set[str]) -> str:
    """PACT words as a Pydantic AI template: each `{{run-inputs.<name>}}` hole of a declared
    input is `{{<name>}}`, filled from deps; every other pair of braces is escaped (`\\{{`), so
    Handlebars reads it as the text it is in PACT (a `{{remembers.x}}` hole, `{{#each}}`, a
    JSON example) and `Agent.from_spec` compiles the words without a template error."""
    mark = "\x00"
    said = rewritten(
        text,
        lambda n: f"{mark}{n.split('.', 1)[1]}{mark}"
        if n.startswith(f"{RUN_INPUTS}.") and n.split(".", 1)[1] in inputs else None,
    )
    said = said.replace("\\{{", "\x01").replace("{{", "\\{{").replace("\x01", "\\{{")
    return re.sub(f"{mark}(.*?){mark}", r"{{\1}}", said)


def _as_holes(text: str, declared: set[str], where: str, report: ImportReport) -> str:
    """02P A4: a spec's `{{name}}` template, filled by Pydantic AI from deps, as PACT's
    `{{run-inputs.name}}` hole when `deps_schema` declares `name` (so `run-inputs:` does);
    any other template part (a name nothing declares, a path, a Handlebars helper) is named,
    since PACT has no blank for it and it would reach the model as literal braces."""
    said = rewritten(text, lambda n: f"{{{{{RUN_INPUTS}.{n}}}}}" if n in declared else None)
    if left := templates_in(said):
        report.not_portable[f"{where}.templates"] = (
            ", ".join(f"`{t}`" for t in left) + " Pydantic AI fills from the run's deps, and PACT has no "
            "blank for it, so it is carried as written and the model reads the braces. Declare the value "
            "under `run-inputs:` and write `{{run-inputs.<name>}}`, or write the words out"
        )
    return said


def _named_shape(
    schema: Mapping[str, Any], defs: "Mapping[str, Any] | None", named: dict[str, Any], hint: str
) -> "Shape | None":
    """A nested object as a shape with parts, named for its `title` (else its `$defs` key) in
    kebab case and added to `named` (the workspace's `shapes:` an import writes); `None` when a
    part has no spelling or the object contains itself (a shape is a fixed set of parts)."""
    from .openapi_shapes import kebab

    called = kebab(str(schema.get("title") or hint or "part")) or "part"
    if named.get(called, {}) is None:  # being read further up: it contains itself
        return None
    named.setdefault(called, None)
    parts, refused = _schema_to_answers(schema, named, defs)
    if named.get(called) is None:
        del named[called]
    if refused or not parts:
        return None
    name, n = called, 1
    while named.get(name) not in (None, parts):
        n += 1
        name = f"{called}-{n}"
    named[name] = parts
    return Shape("named", name=name)


def _schema_to_answers(
    schema: Mapping[str, Any],
    named: "dict[str, Any] | None" = None,
    defs: "Mapping[str, Any] | None" = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """A JSON Schema object as PACT answer-shape lines, and what would not go.

    Two returns rather than one, because a property with no PACT spelling must
    be NAMED — a nested `address` object silently becoming nothing is the drop
    the report exists to catch, and `silent_drops` cannot see inside a key it was
    told was mapped.
    """
    lines: dict[str, str] = {}
    refused: dict[str, str] = {}
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        return lines, refused
    required = set(schema.get("required") or ())
    defs = schema.get("$defs") if isinstance(schema.get("$defs"), Mapping) else (defs or {})
    for name, prop in properties.items():
        shape = shape_from_json_schema(prop if isinstance(prop, Mapping) else {}, defs, named, str(name))
        if shape is not None and name not in required:
            shape = replace(shape, optional=True)
        if shape is None:
            said = prop.get("type") if isinstance(prop, Mapping) else None
            refused[str(name)] = (
                f"a `{said or 'schema-less'}` property. PACT's answer shapes are "
                "text, yes-or-no, money, number, whole-number, a date or a time, "
                "`one of a, b, c`, `list of` one of those, or a shape with parts "
                "named under `shapes:` (which an import into a tree writes); this "
                "one has none of those spellings, so this field is not carried"
            )
            continue
        lines[str(name)] = shape.written()
    return lines, refused


def shapes_owed(shapes: Mapping[str, Mapping[str, str]]) -> str:
    """The `still_to_write` line for the shapes with parts an imported answer names, for a door
    that writes no `workspace.yaml` of its own."""
    return "`shapes:` in `workspace.yaml`, the shapes with parts its answer names: " + "; ".join(
        f"`{n}` ({', '.join(f'{k}: {v}' for k, v in parts.items())})" for n, parts in shapes.items()
    )


def _still_to_write(
    agent: Mapping[str, Any],
    *,
    tools_named: bool,
    has_policy: bool = False,
    connect: str = "",
    servers: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """What PACT needs that this Pydantic AI source did not supply.

    Said as a list of things to write rather than as an error, because the import
    DID work — the same shape `from_a2a_card` uses. Every entry is `tier: core`,
    which is to say a no-code author is expected to write it and this is the list
    they work through.

    `has_policy` exists because one of them can already be answered. A live agent
    whose tools carry `requires_approval=True` HAS an approval policy and it was
    carried, so telling that author to write one would be this list demanding
    work already done — and a checklist that asks for things you have is a
    checklist people stop reading.

    `connect` is the same argument about the biggest entry on the list. A host
    that wrapped its tool functions as ONE MCP server has already answered *where
    does this tool reach*, and `tool_files_for(connect=...)` writes the line — so
    demanding it again would be this checklist asking for the work it just did.
    What is genuinely still owed then is smaller and different: the server's
    ENDPOINT, which is a name the platform team publishes and nothing in a
    Pydantic AI agent carries.
    """
    owed: list[str] = []
    if not agent.get("instructions"):
        owed.append("`instructions:` — the source carried none")
    if not agent.get("description"):
        owed.append("`description:` — PACT requires one and the source had no field for it")
    functions = tools_named and set(agent.get("uses") or ()) - set(servers)
    if not tools_named:
        owed.append("`uses:` — no tools were named")
    elif not functions:
        pass  # every tool reaches an MCP server the agent named; `servers` below
    elif not connect:
        # Measured, not guessed: `pact check` on a tree built from a real import
        # refused every tool with `loader/tool-reaches-nowhere`. A Pydantic AI
        # tool is a Python function, and "call this Python function" is not a
        # thing a portable document can say — which is the point of the rule.
        # `tool_files_for()` fills in the description and the `takes:` block and
        # cannot fill in this line unless it is told where, so the author is told
        # which line and where.
        owed.append(
            "`connect:`, `url:` or `says:` in each `tools/<name>.yaml` — a PACT "
            "tool has to say WHERE it reaches, and a Python function is not "
            "somewhere a second runtime can reach. Without it `pact check` "
            "refuses the tool (`loader/tool-reaches-nowhere`)"
        )
    else:
        # The line is written, so what remains is the one fact that genuinely
        # came from outside this agent. `endpoint:` and `auth:` are both
        # REFERENCES the host resolves — never values, never a command — so this
        # asks for the two names rather than for a connection.
        owed.append(
            f"`endpoint:` in `resources/{connect}.yaml` — the tools now say they "
            f"reach `{connect}`, the server your host serves these functions from, "
            "and an endpoint is a name your platform team publishes rather than "
            "anything a Pydantic AI agent carries (add `auth: {by-reference: ...}` "
            "beside it if that server needs a credential), or the host binds "
            f"`{connect}` itself"
        )
    for server in servers:
        # An MCP server the agent held: its tools are written and say `connect:`
        # it, so what is owed is the host's binding of that name to the server.
        owed.append(
            f"the address of `{server}`: bind the name to its MCP server on the host that runs the "
            f"tree (`endpoint:` in `resources/{server}.yaml`, or the host's own binding of `{server}`)"
        )
    owed.append(
        "`limits:` with `steps-at-most:` AND `when-it-runs-out:` — Pydantic AI "
        "bounds a run with `UsageLimits` at CALL time, so no agent carries a "
        "ceiling of its own. The two go together: set a ceiling without saying "
        "what to do at it and `pact check` refuses the pair"
    )
    if not has_policy:
        owed.append("`policy:` — nothing in the source says what needs a person")
    owed += [
        "`loop:` — nothing in the source says the shape of the thinking",
        "`evals:` — nothing in the source says how you would know it works",
    ]
    if agent.get("model"):
        # A Pydantic AI model id is whatever its provider calls it; PACT binds
        # against `models/catalog.yaml`, which is local-first and air-gapped
        # (constraint 2) and will not have every name. Refused at check time with
        # `schema/no-such-name`, which is a confusing error to meet if nothing
        # warned that the id came from somewhere else.
        owed.append(
            f"a catalogue row for `{agent['model']}` — the id came from the "
            "source, and PACT binds models against `models/catalog.yaml`. If it "
            "is not there, add a row saying how much it can hold and where that "
            "number came from, or pick a name the catalogue already has"
        )
    return tuple(owed)


# ─────────────────────────── Pydantic AI (a live object)  →  PACT
#
# `from_pydantic_ai_agent`, `tool_files_for` and `resource_file_for` are in
# `pydantic_ai_live`, over `pydantic_ai_reading`'s public-only reads.


# ─────────────────────────────────────── PACT  →  Pydantic AI


#: Why each PACT agent field has nowhere to go in an `AgentSpec` file (the
#: registry's `spec-file:`), and the `AgentSpec` fields PACT deliberately does not
#: decide, left unset and named (its `left:`). Which KIND of thing is lost
#: decides whether losing it matters, and half of these are the difference
#: between a governed agent and an ungoverned one.
_SPEC_CANNOT_TAKE: dict[str, str] = {
    key.split(".", 1)[1]: row.spec_file
    for key, row in _REGISTRY.fields.items()
    if key.startswith("agent.") and row.spec_file
}
_SPEC_SUPPLIES: dict[str, str] = {k: r.left for k, r in _REGISTRY.through("spec").items() if r.left}

#: The report key the MCP shape is named under. Not an agent field — `seen` is
#: the agent block and this is a fact about what the tools on `uses:` REACH — so
#: it is spelt as the document construct it comes from, rather than borrowed from
#: a field name a reader would then go looking for on the agent and not find.
_MCP_REPORT_KEY: str = "resources (resource-kind: mcp-server)"


def _mcp_servers_reached(
    document: Mapping[str, Any], block: Mapping[str, Any]
) -> list[str]:
    """The `mcp-server` resources this agent's tools connect to, by name.

    Walked rather than assumed, because the report has to be about THIS agent.
    A workspace may hold MCP servers no agent on it reaches — `policy-checker` in
    the worked example uses one skill and no tool — and printing a protocol
    caveat over an export that opens no MCP connection is the noise that teaches
    readers to skip the report, which costs the caveat that matters.

    Three hops, all of them the loader's own: `uses:` names a tool OR a skill, a
    tool's `connect:` names one entry in `resources:` (`spec/schema.yaml` gives
    it `names: resources`, so a name that is not there is refused at check time),
    and `resource-kind:` is the only field that says an entry is an MCP server.
    """
    tools = document.get("tools") or {}
    resources = document.get("resources") or {}
    if not isinstance(tools, Mapping) or not isinstance(resources, Mapping):
        return []
    reached: set[str] = set()
    for used in block.get("uses") or ():
        tool = tools.get(str(used))
        if not isinstance(tool, Mapping):
            continue   # a skill, not a tool — `uses:` carries both
        server = resources.get(str(tool.get("connect") or ""))
        if isinstance(server, Mapping) and server.get("resource-kind") == "mcp-server":
            reached.add(str(tool["connect"]))
    return sorted(reached)


def to_pydantic_ai_spec(
    document: Mapping[str, Any], agent: str, workspace: str = ""
) -> tuple[dict[str, Any], ExportReport]:
    """One PACT agent as a Pydantic AI `AgentSpec`, and everything it could not say.

    The file that comes back loads with `Agent.from_file()` and is a real
    Pydantic AI agent: model, instructions, settings and output shape all
    survive, because Pydantic AI's own vocabulary for those is a superset of
    PACT's. What does not survive is everything that makes it a PACT agent —
    the ceilings, the policy, the loop, the interceptors and the team — and the
    report names each one with what stops being enforced.

    `build_agent()` is the other half: it binds the tools and the ceilings a spec
    file has no field for. Neither alone is the whole agent, and the report is
    what stops somebody believing the file is.

    `workspace` is the tree, when the caller has one. It is optional because
    invariant P-1 says an adapter may be handed only the loaded document — and
    it buys exactly one thing: a workspace may add rows to its own
    `models/catalog.yaml`, and translating `model:` into this SDK's id scheme is
    a catalogue lookup. Without it the distribution catalogue alone is consulted.
    """
    block = dict((document.get("agents") or {}).get(agent) or {})
    report = ExportReport(kind="a Pydantic AI agent spec", seen=tuple(sorted(block)))
    spec: dict[str, Any] = {}

    written = block.get("model")
    chain = [str(m).strip() for m in (written if isinstance(written, list) else [written]) if m]
    if len(chain) > 1:
        # 02P A2. `AgentSpec.model` is `str | None` (pydantic_ai/agent/spec.py:38),
        # so a spec file holds one model and the fallbacks cannot ride in it.
        # `build_agent(..., models={...})` is where they go.
        report.not_carried["model.fallbacks"] = (
            f"`model:` lists {len(chain)} models and a Pydantic AI spec file holds "
            f"one, so only `{chain[0]}` is carried and the fallbacks "
            + ", ".join(f"`{m}`" for m in chain[1:])
            + " are not tried when it fails. fix: build the agent with "
            "`build_agent(..., models={id: model, ...})`, which makes the "
            "`FallbackModel` over them in this order"
        )
    if model := (chain[0] if chain else ""):
        # Translated through the catalogue, not copied. A PACT `model:` is a
        # catalogue ROW and a Pydantic AI `model:` is `provider:name`, so copying
        # produced a spec whose every run died on `UserError: Unknown model:
        # qwen2.5-7b-instruct` — measured on a real round trip, not supposed.
        said, why = pydantic_ai_model_id(model, workspace)
        if said:
            spec["model"] = said
            report.carried["model"] = f"`model`, as `{said}`" + (
                "" if said == model else f" (the catalogue's `{model}`, in this SDK's id scheme)"
            )
        else:
            report.not_carried["model"] = (
                f"`{model}` has no Pydantic AI id: {why}. Left out rather than "
                "copied, because a copied catalogue name loads and then fails "
                "every run with `UserError: Unknown model` — pass "
                "`Agent.from_file(path, model=...)` with a model object you have "
                "configured"
            )
    if name := str(block.get("name") or "").strip():
        spec["name"] = name
        report.carried["name"] = "`name`"
    if described := str(block.get("description") or "").strip():
        spec["description"] = described
        report.carried["description"] = "`description`"
    if told := _field_text(block.get("instructions")):
        spec["instructions"] = told
        report.carried["instructions"] = "`instructions`"
    # 02P A1, A4. A `{{run-inputs.brand}}` hole is Pydantic AI's `{{brand}}` template,
    # filled from the run's deps, which `deps_schema` (the agent's `run-inputs:`,
    # below) declares: `Agent.from_spec` makes it a `TemplateStr` and the model reads
    # the filled words. A `{{remembers.x}}` hole has no deps to come from, so it is
    # carried as written and the model reads the braces: said (`exporting`: every loss).
    inputs = set(block.get("run-inputs") or {}) if isinstance(block.get("run-inputs"), Mapping) else set()
    for words in ("description", "instructions"):
        if not spec.get(words):
            continue
        written = spec[words]
        spec[words] = _as_template(written, inputs)
        if holes_in(written) and any(h.namespace == RUN_INPUTS for h in holes_in(written)):
            report.carried[words] = (
                f"`{words}`, each `{{{{run-inputs.<name>}}}}` blank as Pydantic AI's `{{{{<name>}}}}` "
                "template, filled from the run's deps (`deps_schema`); `Agent.from_file` reads a "
                "template with `pydantic-ai-slim[spec]` installed"
            )
        if unfilled := [h for h in holes_in(written) if h.namespace != RUN_INPUTS or h.name not in inputs]:
            report.not_carried[f"{words}.holes"] = (
                f"`{words}:` has "
                + ", ".join(f"`{{{{{h.address}}}}}`" for h in unfilled)
                + ", which PACT fills when a run starts from what the agent remembers, and "
                "a spec file has nothing to fill it from, so the braces are carried as "
                "written and reach the model unfilled. fix: build the agent with "
                "`build_agent(spec, run_inputs=..., remembered=...)`, which fills them"
            )

    if isinstance(block.get("settings"), Mapping) and block["settings"]:
        wire, dropped = _pact_settings_to_model_settings(block["settings"])
        if wire:
            spec["model_settings"] = wire
        report.carried["settings"] = "`model_settings`" + (
            ""
            if not dropped
            else ". NOT carried: "
            + "; ".join(f"`{k}` — {why}" for k, why in sorted(dropped.items()))
        )

    if isinstance(block.get("answers-with"), Mapping) and block["answers-with"]:
        answers = {k: str(v) for k, v in block["answers-with"].items()}
        schema = _answers_with_schema(answers, document.get("shapes"))
        if schema:
            spec["output_schema"] = schema
            report.carried["answers-with"] = "`output_schema`, as a JSON Schema object" + (
                _one_way_shapes(answers)
            )

    if isinstance(block.get("run-inputs"), Mapping) and block["run-inputs"]:
        schema = _answers_with_schema(
            {k: str(v) for k, v in block["run-inputs"].items()}, document.get("shapes")
        )
        if schema:
            spec["deps_schema"] = schema
            report.carried["run-inputs"] = "`deps_schema`"

    for key in block:
        if key in report.carried:
            continue
        report.not_carried[key] = _SPEC_CANNOT_TAKE.get(key) or (
            "no field in a Pydantic AI agent spec for this"
        )
    # 02P C10: the report names EACH ceiling, so a reader sees which of theirs
    # stop being enforced, not only that a block called `limits` did.
    if "limits" in report.not_carried and isinstance(block.get("limits"), Mapping):
        written = "; ".join(f"`{k}: {v}`" for k, v in block["limits"].items())
        report.not_carried["limits"] += (
            f". Not enforced by this file: {written}. Of these, `cost-per-request-under`, "
            "`runs-for-at-most` and a `when-it-runs-out:` other than stopping have no "
            "Pydantic AI counterpart at all"
        )

    # The tools on `uses:` are already reported as not carried; WHERE they reach
    # is the half that sentence does not cover, and for an `mcp-server` it is the
    # half a reader needs most. FR-4.1.14 forbids the shape this SDK's pin can
    # only speak, and AD-71's snapshot does not exist yet — an export that named
    # neither would be handing somebody a file that opens a connection PACT's own
    # requirements rule out, with the report that exists to prevent exactly that
    # silence sitting underneath it saying nothing.
    if servers := _mcp_servers_reached(document, block):
        report.not_carried[_MCP_REPORT_KEY] = (
            f"`{'`, `'.join(servers)}` — {_MCP_SHAPE}"
        )

    report.supplied_by_the_runtime = dict(_SPEC_SUPPLIES)
    if "model" not in spec:
        # The author pinned none, which `ir.AgentSpec.model` documents as a
        # different fact from "chose the default": PACT resolves one from the
        # catalogue per `needs:`, which is the whole of decision 4.
        #
        # Said here because the consequence is immediate and otherwise silent at
        # the wrong moment: `Agent.from_spec` raises `UserError('model must be
        # provided either in the spec or as a keyword argument')`, so this file
        # does not load at all. A reader who is told nothing finds that out from
        # a traceback rather than from the report that exists to tell them.
        report.supplied_by_the_runtime["model"] = (
            "the author pinned no `model:`, so none is written here. PACT picks "
            "one from `models/catalog.yaml` against `needs:`; Pydantic AI has no "
            "resolver, so pass `Agent.from_file(path, model=...)` or this spec "
            "will not load"
        )
    return spec, report


#: The four answer shapes JSON Schema has no word for, and what each becomes.
#: They reach the MODEL intact — the meaning is in the property's `description`,
#: which is the only place a schema can put it — but they do not come BACK: a
#: reader cannot claim every string is an amount of money or every list of
#: strings a set of pictures. See `shape_from_json_schema` for the refusal.
_ONE_WAY: dict[str, str] = {
    "money": "a string carrying its currency in the description",
    "images": "an array of references",
    "audio": "an array of references",
    "file": "an array of references",
}


def _one_way_shapes(answers: Mapping[str, str]) -> str:
    """The note on shapes that survive the crossing but not the return.

    Said because `carried` otherwise reads as a clean carry, and for these four
    it is clean in one direction only. Somebody round-tripping a document —
    export, edit in Pydantic AI, import back — gets `amount: text` where they
    wrote `amount: money`, and the place to learn that is here rather than by
    diffing two trees.
    """
    downgraded: list[str] = []
    for name, written in answers.items():
        try:
            kind = Shape.parse(written).kind
        except Exception:
            continue
        if kind in _ONE_WAY:
            downgraded.append(f"`{name}` ({kind} → {_ONE_WAY[kind]})")
    if not downgraded:
        return ""
    return (
        ". One-way: " + ", ".join(sorted(downgraded)) + " — the meaning reaches "
        "the model in the property description, but importing this schema back "
        "cannot recover the shape, so it returns as `text`"
    )


def _field_text(written: Any) -> str:
    """One PACT text field, whether the author wrote a file or a folder.

    The same rule `ir._text` holds and for the same reason — *a directory is a
    field* is the headline rule of both READMEs, and an exporter that read only
    the string form would emit an empty `instructions:` for every document whose
    instructions grew past one file.
    """
    if isinstance(written, str):
        return written.strip()
    if isinstance(written, Mapping) and written:
        return "\n\n".join(str(v).strip() for v in written.values() if str(v).strip())
    return ""


def _pact_settings_to_model_settings(
    settings: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """A PACT `settings:` block in this SDK's shape, and the keys that did not go.

    Straight through `pydantic_ai_transport._SETTINGS` and `_translated`, which
    is the one mapping table for this target — the transport already had to
    decide `thinking: none` is `False` and a bare tool name is `[name]`, and a
    second opinion here is how the exported file and the executed run come to
    disagree about what the author wrote.
    """
    wire: dict[str, Any] = {}
    dropped: dict[str, str] = {}
    for key, value in settings.items():
        wire_key = _SETTINGS.get(str(key))
        if wire_key is None:
            dropped[str(key)] = "not a key this SDK's `ModelSettings` has"
            continue
        if str(key) == "tool-choice" and not _settable_statically(value):
            # `required`, and naming one tool, are the two `tool-choice:` values
            # this SDK REFUSES on a configured agent: both exclude the output
            # tools, so the agent could never produce a final response, and
            # `Agent.run` raises `UserError` rather than looping forever.
            #
            # Left out rather than posted, because posting it does not degrade —
            # it produces a spec file that loads and then kills the first run
            # with a traceback about output tools, which is a worse outcome than
            # a named loss for a document that `pact check` printed OK for.
            #
            # This is the sharpest illustration of why decision 5 exists.
            # `transports/pydantic_ai_transport.py` carries all twelve settings
            # including these two, because `direct.model_request` makes ONE call
            # and has no loop to strand — PACT's harness is what comes back for
            # the next step. Hand the loop to the framework and two of the
            # author's settings stop being expressible at all.
            dropped[str(key)] = (
                f"`{value}` excludes the output tools, so an agent configured "
                "with it could never produce a final response — this SDK raises "
                "`UserError` rather than accepting it. Only `auto` and `none` "
                "can sit on an agent; PACT's own harness carries all four"
            )
            continue
        said = value
        if str(key) == "parallel-tool-calls":
            # `ir.TICKS_IN_SETTINGS` has already turned the author's word into a
            # bool by the time a spec is built, but a raw document has not been
            # through that, and `ModelSettings` is a `TypedDict` that validates
            # nothing — the transport's own docstring records `"no"` reaching a
            # provider as a truthy string. Held here too, on the raw path.
            said = said_yes(value)
        else:
            said = _translated(str(key), value)
        wire[wire_key] = said
    return wire, dropped


#: A PACT `served-by.runtime:` and the Pydantic AI provider that speaks it.
#:
#: The two vocabularies genuinely differ, and neither is wrong: PACT names the
#: thing that RUNS the weights (§4.2 keys the catalogue on model, provider and
#: runtime, because the same weights carry different ids on different runtimes),
#: while a Pydantic AI model id names the provider whose API shape is spoken.
#: For the hosted four they coincide once the `-api` suffix is dropped.
#:
#: `vllm` is deliberately absent and that is the interesting entry. vLLM serves
#: an OpenAI-COMPATIBLE API, so it would be `openai` with a `base_url` — and a
#: base URL is exactly what a catalogue row does not carry (`endpoint: local` is
#: a yes-or-no about egress, not an address). Emitting `openai:qwen2.5-7b-instruct`
#: for a vLLM row would name a model OpenAI does not serve, and the run would
#: fail against the wrong host with an authentication error. Reported instead.
_RUNTIME_PROVIDERS: dict[str, str] = {
    "anthropic-api": "anthropic",
    "openai-api": "openai",
    "google-api": "google",
    "xai-api": "xai",
    "ollama": "ollama",
}


def catalogue_row_for(model_id: str) -> str:
    """The distribution catalogue's row a Pydantic AI model id names, or the id as it is.

    The inverse of `pydantic_ai_model_id`, so an agent exported with
    `ollama:qwen2.5:14b-instruct` imports back as the row `qwen2.5-14b-instruct`
    it was exported from (02P S3: the same `pact show` digest). An id two rows
    share, or none, is kept as written: `still_to_write` then asks for a row.
    """
    rows = _rows_by_id().get(str(model_id or "").strip(), ())
    return rows[0] if len(rows) == 1 else str(model_id or "").strip()


@lru_cache(maxsize=1)
def _rows_by_id() -> dict[str, tuple[str, ...]]:
    from .resolve import load_catalogue

    by: dict[str, list[str]] = {}
    for entry in load_catalogue().entries:
        said, _ = pydantic_ai_model_id(entry.name)
        if said:
            by.setdefault(said, []).append(entry.name)
    return {k: tuple(v) for k, v in by.items()}


def pydantic_ai_model_id(model: str, workspace: str = "") -> tuple[str, str]:
    """A PACT catalogue name as a Pydantic AI model id, or nothing and why.

    Returns `(id, "")` or `("", reason)`.

    The two id schemes are not the same and a document that crossed without this
    produced a spec whose every run died on `UserError: Unknown model:
    qwen2.5-7b-instruct` — measured, on the round trip through a real tree. PACT
    binds a CATALOGUE ROW (`qwen2.5-7b-instruct`, a name with a window and a
    price and a provenance beside it); Pydantic AI binds `provider:name`.

    The row already holds both halves. `served-by:` says which runtimes serve
    these weights and `also-known-as:` says what each of them calls the model —
    the catalogue's own comment gives the reason it is shaped that way: *the same
    weights carry different ids on different runtimes*. So this is a lookup, not
    a guess.

    Offline, like everything else here (constraint 2): `load_catalogue` reads a
    file the distribution ships, with the workspace's own overrides layered on
    top when there are any.
    """
    from .resolve import load_catalogue

    said = str(model or "").strip()
    if not said:
        return "", "no model was pinned"
    entry = load_catalogue(workspace=workspace or None).get(said)
    if entry is None:
        return "", (
            f"`{said}` is not a row in `models/catalog.yaml`, so nothing here "
            "knows which provider serves it"
        )
    runtimes = sorted(getattr(entry, "runtimes", ()) or ())
    for runtime in runtimes:
        provider = _RUNTIME_PROVIDERS.get(runtime)
        if provider is None:
            continue
        return f"{provider}:{_id_for(runtime, entry)}", ""
    return "", (
        f"`{said}` is served by {', '.join(runtimes) or 'nothing the catalogue names'}, "
        "and none of those is a provider this SDK has. A vLLM row is the common "
        "case: it speaks OpenAI's API shape but needs a base URL, which a "
        "catalogue row does not carry — pass a configured `Model` object instead"
    )


def _id_for(runtime: str, entry: Any) -> str:
    """What this runtime calls these weights.

    `also-known-as:` is one flat list across every runtime, so there is no field
    saying which alias belongs to which. For the only runtime where it matters
    the convention is unambiguous and is the catalogue's own example: Ollama tags
    a model `qwen2.5:7b-instruct`, with a colon, and the hosted APIs do not use
    one. So the colon picks it, and every other runtime takes the row's own name.

    Narrow on purpose. A cleverer matcher would start guessing between two
    plausible aliases, and a wrong model id fails at the provider rather than
    here — which is the far more expensive place to find out.
    """
    if runtime == "ollama":
        for alias in sorted(getattr(entry, "aliases", ()) or ()):
            if ":" in alias:
                return alias
    return entry.name


def _settable_statically(value: Any) -> bool:
    """Whether this `tool-choice:` can sit on a configured agent at all.

    `auto` and `none` can. `required` and a named tool cannot: both exclude the
    output tools, so an agent carrying one could never finish, and `Agent.run`
    raises `UserError` instead of looping. Measured on pydantic-ai-slim 2.21 —
    the message names the reason: *"prevents the agent from producing a final
    response because output tools are excluded"*.

    The SDK's own escape hatch is a capability returning per-step settings, which
    is a Python object and therefore not something a spec file can carry. So on
    this path the two values have no expression, which is what the export report
    says rather than what the exported file discovers.
    """
    return str(value).strip() in ("auto", "none")


def usage_limits_for(spec: PactAgentSpec) -> Any:
    """The author's ceilings as a `UsageLimits`, for the ones that translate.

    Three of PACT's ceilings have an exact counterpart and are carried:
    `steps-at-most` is `request_limit`, `tool-calls-at-most` is
    `tool_calls_limit`, `tokens-at-most` is `total_tokens_limit`. One the
    author did not write is `None` — no ceiling — including `request_limit`,
    whose own default (50) would otherwise stop a run nobody limited.

    Two do NOT translate and are deliberately left out rather than approximated:

    * `cost-per-request-under:` is a ceiling on ONE request. `UsageLimits
      .cost_limit` caps `RunUsage.cost`, which is the whole run. Setting one from
      the other would make a per-request cap of $0.05 stop a ten-step run at the
      first step, or a run cap of $0.05 pass ten requests that each broke the
      author's rule — wrong in both directions, silently.
    * `runs-for-at-most:` is wall-clock. `UsageLimits` has no time field at all;
      time is the caller's `asyncio.timeout`.

    And `when-it-runs-out:` cannot be carried by any of them: `UsageLimits` has
    exactly one behaviour, which is to raise `UsageLimitExceeded`. That is PACT's
    `stop`. An author who wrote `ask-a-person` or `carry-on` gets `stop` here, so
    `to_pydantic_ai_spec`'s report names `limits` as not carried in full and
    `build_agent()` refuses to pretend otherwise.
    """
    from pydantic_ai.usage import UsageLimits

    limits = spec.limits
    return UsageLimits(
        # Only a ceiling the AUTHOR wrote. `max_steps` falls back to this port's
        # own loop bound when `steps-at-most` is absent, and that bound is PACT's
        # harness, not the document; and `None` is passed rather than left out,
        # because `UsageLimits` otherwise caps at `request_limit=50`
        # (pydantic_ai/usage.py:482) — a ceiling nobody wrote either.
        request_limit=spec.max_steps if spec.steps_written else None,
        tool_calls_limit=limits.tool_calls_at_most,
        total_tokens_limit=limits.tokens_at_most,
    )


def build_agent(
    spec: PactAgentSpec,
    *,
    call_tool: Any = None,
    model: Any = None,
    models: "Mapping[str, Any] | None" = None,
    run_inputs: "Mapping[str, Any] | None" = None,
    remembered: "Mapping[str, Any] | None" = None,
    judge: Any = None,
) -> Any:
    """One PACT agent as a live Pydantic AI `Agent`, tools and approvals bound.

    This is what a spec FILE cannot be. `to_pydantic_ai_spec()` emits everything
    `AgentSpec` has a field for; this adds the two things it has no field for and
    that an agent is not an agent without:

    * **the tools**, as a `FunctionToolset` built with `Tool.from_schema` — the
      one entry point in this SDK that takes a name, a description and a JSON
      schema with no Python function behind them, which is exactly what a PACT
      `tools/<name>.yaml` is. `call_tool` is the host's executor and receives
      `(name, arguments)`. Given none, the tools become an `ExternalToolset`
      instead, so the run ends with `DeferredToolRequests` and the caller
      fulfils them — which is honest, and is how a PACT agent runs somewhere its
      tool runtime is not.
    * **the approvals**, from the author's `policy.ask-a-person`. A tool the gate
      names is registered with `requires_approval=True`, so Pydantic AI parks the
      run on `DeferredToolRequests.approvals` exactly where PACT's own harness
      would park it. This is the one governance line that survives the crossing
      intact, because both systems stop the same call and wait for the same
      person.

    **The words are filled when the agent is built.** An agent built here is
    built for one run's values: `run_inputs` and `remembered` fill the
    `{{run-inputs.<n>}}` and `{{remembers.<n>}}` holes in its instructions and
    description (`holes.fill`), and a hole with no value raises `holes.Unfilled`
    naming it. They used to reach the model as literal braces.

    **Its answer is held to `checked-by:`, or the build is refused.** Each rule
    is decided by `evals.first_broken`, `checks-at-most:` attempts in all. A
    `judged:` rule needs something to grade it: pass `judge=` (an
    `evals`-style grader, `judge.Judge`), or the build raises, because skipping
    the rule would return an answer nobody held to it.

    **What is still not enforced, and must be said out loud.** The loop is
    Pydantic AI's. `loop:` stages, `interceptors:`, `teamwork:`,
    `context-policy:`, `remembers:` and `when-it-runs-out:` are PACT harness
    behaviour and this agent has none of them. Use
    `transports/pydantic_ai_transport.py` when the contract has to hold; use this
    when the point is to hand somebody a working Pydantic AI agent.
    """
    from pydantic_ai import Agent
    from pydantic_ai.tools import Tool
    from pydantic_ai.toolsets import FunctionToolset
    from pydantic_ai.toolsets.external import ExternalToolset
    from pydantic_ai.tools import ToolDefinition

    from .evals import JUDGED
    from .holes import fill

    ungraded = [r.sentence for r in spec.checked_by if r.kind == JUDGED] if judge is None else []
    if ungraded:
        raise ValueError(
            f"{spec.key or 'this agent'}'s `checked-by:` says `judged: {ungraded[0]}`, "
            "and nothing here can grade it, so the answer would be returned without "
            "that rule being applied. fix: pass `judge=` (for a workspace, "
            "`judge.judge_of(...)`), or take the `judged:` line off `checked-by:`."
        )
    filled = {"run_inputs": run_inputs, "remembers": remembered}

    needs_person = _tools_needing_approval(spec)

    toolsets: list[Any] = []
    if spec.tools:
        if call_tool is None:
            toolsets.append(
                ExternalToolset(
                    [
                        ToolDefinition(
                            name=t.name,
                            description=t.description,
                            parameters_json_schema=_takes_as_schema(t.parameters, spec.shapes),
                        )
                        for t in spec.tools
                    ],
                    id="pact",
                )
            )
        else:
            built: list[Any] = []
            for t in spec.tools:
                built.append(
                    Tool.from_schema(
                        _executor(call_tool, t.name),
                        name=t.name,
                        description=t.description,
                        json_schema=_takes_as_schema(t.parameters, spec.shapes),
                    )
                )
                built[-1].requires_approval = t.name in needs_person
            toolsets.append(FunctionToolset(built, id="pact"))

    settings, _ = _pact_settings_to_model_settings(spec.settings)

    # An explicit `model=` wins untouched — a caller handing over a configured
    # `Model` object is the documented way past a row this cannot translate (a
    # vLLM endpoint, a gateway). Otherwise the author's pin goes through the
    # catalogue, because `spec.model` is a catalogue row and this SDK wants
    # `provider:name`. A row with no Pydantic AI id leaves the model unset rather
    # than passing a name `infer_model` will reject: `Agent(None)` is legal and
    # defers the choice to `run(model=...)`, which is a caller who still has
    # options, where a bad id is a `UserError` at construction.
    # `models` is the host's model for each id the author wrote (a configured
    # `Model` or a Pydantic AI id), and with it `model: [a, b]` is a
    # `FallbackModel` over them in the author's order (02P A2, M3), falling over
    # on a provider error only (`ModelAPIError`, the class's own default made
    # explicit: pydantic_ai/models/fallback.py:111): never because an answer was
    # wrong. Without `models`, a list binds its FIRST model through the
    # catalogue and nothing more: `FallbackModel.__init__` calls `infer_model`
    # on every entry at construction (fallback.py:131), which is the
    # credentials check `defer_model_check=True` below exists to put off.
    bound: Any = model
    if bound is None and models is not None:
        bound = _chain_of(spec, models)
    if bound is None and spec.model:
        said, _ = pydantic_ai_model_id(spec.model, spec.workspace)
        bound = said or None

    agent = Agent(
        bound,
        name=spec.name or spec.key or None,
        description=fill(spec.description, **filled) or None,
        # The agent's own words are filled; a skill is a document to read, and
        # braces in one are that document's.
        instructions=_instructions_with_skills(
            replace(spec, instructions=fill(spec.instructions, **filled))
        )
        or None,
        model_settings=settings or None,
        output_type=_output_type_for(spec),
        toolsets=toolsets or None,
        # `checks-at-most:` is counted by the check itself (`_answer_checks`).
        # Pydantic AI's own output budget is 1 retry unless told otherwise
        # (`Agent(retries=)`, `{'tools': 1, 'output': 1}`), so `checks-at-most:
        # 3` ended at the second failed answer with "Exceeded maximum output
        # retries (1)": a ceiling nobody wrote, ahead of the one the author did.
        retries={"output": sys.maxsize} if spec.checked_by else None,
        # Building an agent must not require the credentials to RUN it.
        # `Agent.__init__` otherwise calls `models.infer_model`, which constructs
        # the provider and performs its environment checks then and there — so
        # `ollama:qwen2.5:7b-instruct` raised `UserError: Set the
        # OLLAMA_BASE_URL environment variable` at construction, before anybody
        # asked for a model call.
        #
        # That is the wrong moment on this path twice over. A caller inspecting
        # what a PACT document became — which tools, which approvals, which
        # output shape — needs no endpoint at all; and *where the model is
        # served* is deployment, which PACT deliberately does not own (it is
        # what makes one tree runnable in two places). Deferred, the check
        # happens at the first run, where the caller has genuinely asked to talk
        # to a provider.
        defer_model_check=True,
    )
    if spec.checked_by:
        agent.output_validator(_answer_checks(spec, judge))
    return agent


def _chain_of(spec: PactAgentSpec, models: Mapping[str, Any]) -> Any:
    """The author's `model:` (one id or a fallback list) as the host's models."""
    from pydantic_ai.exceptions import ModelAPIError
    from pydantic_ai.models.fallback import FallbackModel

    written = spec.models or ((spec.model,) if spec.model else ())
    if not written:
        return None
    missing = [m for m in written if m not in models]
    if missing:
        raise ValueError(
            f"{spec.key or 'this agent'}'s `model:` names `{missing[0]}`, and `models=` "
            f"has no model for it. fix: pass `models={{{missing[0]!r}: <a Model or a "
            "Pydantic AI id>, ...}}` with one entry for each model `model:` names."
        )
    chain = [models[m] for m in written]
    if len(chain) == 1:
        return chain[0]
    return FallbackModel(chain[0], *chain[1:], fallback_on=(ModelAPIError,))


#: How a failed `checked-by:` check opens its retry prompt, and how earlier ones are counted.
CHECK_FAILED = "Your answer breaks a rule it must keep: "


def _answer_checks(spec: PactAgentSpec, judge: Any = None) -> Any:
    """`checked-by:` / `checks-at-most:` (02P O7, A14) as an output validator.

    Each answer is held to the rules by `evals.first_broken`, the door `evals:`
    uses; a broken one is sent back with the rule's words (`ModelRetry`). The
    attempts are counted from the conversation itself (the retry prompts this
    wrote), not by Pydantic AI's output budget, which empty and thinking-only
    replies spend as well — `checks-at-most:` counts attempts at the checks. The
    last attempt that still breaks a rule ends the run saying which.

    `must-call-before:` reads what the run DID, so the calls the model asked for
    are read off the conversation and handed to the rule with the answer. A
    `judged:` rule is graded by `judge`, off the event loop: a grader is a model
    call, and `evals` makes it a blocking one.
    """
    import asyncio

    from pydantic_ai import ModelRetry
    from pydantic_ai.exceptions import UnexpectedModelBehavior
    from pydantic_ai.messages import ModelRequest, ModelResponse, RetryPromptPart, ToolCallPart

    from .evals import first_broken
    from .harness import RunResult, Step, ToolCall

    async def checked(ctx: Any, output: Any) -> Any:
        if getattr(ctx, "partial_output", False):
            return output
        said = output if isinstance(output, str) else json.dumps(_plain(output), sort_keys=True)
        steps = [
            Step(
                index=i,
                text="",
                tool_calls=tuple(
                    ToolCall(p.tool_name, p.args_as_dict()) for p in m.parts if isinstance(p, ToolCallPart)
                ),
            )
            for i, m in enumerate(ctx.messages)
            if isinstance(m, ModelResponse)
        ]
        answered = RunResult(output=said, steps=steps)
        if judge is None:
            broken = first_broken(spec.checked_by, answered)
        else:
            broken = await asyncio.to_thread(first_broken, spec.checked_by, answered, judge)
        if not broken:
            return output
        failed = sum(
            1
            for m in ctx.messages
            if isinstance(m, ModelRequest)
            for p in m.parts
            if isinstance(p, RetryPromptPart)
            and isinstance(p.content, str)
            and p.content.startswith(CHECK_FAILED)
        )
        if failed + 1 >= spec.checks_at_most:
            raise UnexpectedModelBehavior(
                f"after {spec.checks_at_most} attempt(s) the answer still breaks a "
                f"`checked-by:` rule: {broken}"
            )
        raise ModelRetry(f"{CHECK_FAILED}{broken}. Answer again so that it keeps every rule.")

    return checked


def _plain(value: Any) -> Any:
    """A structured answer as plain JSON values, for the rules to read as text."""
    dump = getattr(value, "model_dump", None)
    return dump(mode="json") if callable(dump) else value


def _output_type_for(spec: PactAgentSpec) -> Any:
    """The author's answer shape AND the way they asked for it to be put.

    `answers-with-mode:` is the one PACT field with an exact counterpart in this
    SDK, and the correspondence is total — four words, four marker classes:

    | PACT                 | Pydantic AI       |
    |----------------------|-------------------|
    | `text`               | `str`             |
    | `prompted`           | `PromptedOutput`  |
    | `native-json-schema` | `NativeOutput`    |
    | `tool`               | `ToolOutput`      |

    A spec FILE cannot carry it — `AgentSpec` has only `output_schema`, which
    builds a `StructuredDict` whose mode is `auto`, resolved per model from
    `ModelProfile.default_structured_output_mode`. So `to_pydantic_ai_spec`
    names it as not carried and this is where it is honoured, which is the
    clearest single case of why the export has two halves.

    **Unset is `prompted` and not `auto`, deliberately.** `ir.AgentSpec
    .answers_with_mode` documents PACT's own pick when the author leaves it out:
    *prompted, because that is the one mode every one of the seven transports
    can honour and the only one that works on a machine with no network.*
    Letting `auto` decide here would mean the same document answered in one
    shape under PACT's harness and another under this agent — a divergence with
    nothing to do with the agent, which is the whole thing PACT exists to
    remove, and decision 5 settles the tie: fidelity beats idiomatic.
    """
    from pydantic_ai.output import NativeOutput, PromptedOutput, StructuredDict, ToolOutput

    answers = _answers_with_schema(spec.answers_with, spec.shapes)
    if not answers:
        # No declared shape is `str`, whatever the mode says. A mode is how a
        # shape is put to the model, and there is no shape.
        return str
    said = (spec.answers_with_mode or "").strip()
    if said == "text":
        # The author declared a shape and asked for it NOT to be constrained on
        # the wire. `str` is that, and the shape still reaches the model: it is
        # in `answers-with:` in the instructions the author wrote around it.
        return str
    shaped = StructuredDict(answers)
    if said == "native-json-schema":
        return NativeOutput(shaped)
    if said == "tool":
        return ToolOutput(shaped)
    return PromptedOutput(shaped)


def _instructions_with_skills(spec: PactAgentSpec) -> str:
    """The system message this agent gets: its instructions, then its skills.

    `SkillSpec.in_words()` rather than a shape invented here, for the reason that
    class's own docstring gives — a skill is a document to READ, it reaches the
    model as text in the system message, and two ports producing different bytes
    for the same skill is the divergence the one method exists to stop.
    """
    said = [spec.instructions] if spec.instructions else []
    said += [s.in_words() for s in spec.skills]
    return "\n\n".join(x for x in said if x)


def _tools_needing_approval(spec: PactAgentSpec) -> set[str]:
    """The tools the author's gate STOPS, by name.

    Read off the resolved `Gate` rather than re-parsed from `policy:`, because
    `questions_for()` already compiled those sentences at spec-build time and a
    second parser here would be a second opinion about what the author wrote —
    the `same-setting-twice` mistake, arriving as a governance bug.

    `Rule.gates` is the whole filter and it is not an optimisation. A `Gate`
    holds rules from four sources, and only `policy.ask-a-person` MAKES a call
    wait; the ones read off `limits.asks`, a context policy and a `teamwork:`
    block supply the WORDING for a wait the run has already entered for some
    other reason. Its own docstring says turning those into gates would "park a
    run on the mere existence of a question" — and on this side of the crossing
    that is `requires_approval=True` on a tool nobody asked to guard, which
    stops a run that PACT's own harness would have let through.

    The head name, because a gate may be written per action (`payments/refund`)
    and `requires_approval` is per TOOL here — this SDK has no action vocabulary
    to narrow it with. That widens the guard, which is the safe direction and is
    the direction `Gate.for_call` already chooses for an atom it cannot evaluate.
    """
    return {
        str(thing).split("/")[0].strip()
        for thing, rules in (getattr(spec.asking, "rules", {}) or {}).items()
        if any(getattr(r, "gates", False) for r in rules)
        and str(thing).split("/")[0].strip()
    }


def _takes_as_schema(
    takes: Mapping[str, Any], shapes: "Mapping[str, Any] | None" = None
) -> dict[str, Any]:
    """A PACT tool's `takes:` block as the JSON schema the model is shown.

    Every argument required unless its line says `, optional`, for
    `_answers_with_schema`'s reason: leaving one out of `required` otherwise
    would invent a permission the document does not grant.
    """
    parts: dict[str, Shape] = {}
    loose: dict[str, Any] = {}
    for arg, written in (takes or {}).items():
        try:
            parts[str(arg)] = Shape.parse(written, shapes)
        except Exception:
            # `action: one of refund, check` parses; a free-text shape an author
            # wrote loosely does not, and a tool argument is not the place to
            # fail a run — the model is shown a string and the tool's own
            # validation is what refuses a bad value.
            loose[str(arg)] = {"type": "string", "description": str(written)}
    schema = object_schema(parts)
    schema["properties"].update(loose)
    schema["required"] = sorted([*schema["required"], *loose])
    return schema


def _executor(call_tool: Any, name: str) -> Any:
    """One PACT tool as the callable `Tool.from_schema` binds.

    Keyword-only, because `Tool.from_schema` documents that the function "will be
    called with keywords only" — a positional signature would bind and then fail
    at the first call, which is the shape of bug that reaches production.
    """

    def run(**arguments: Any) -> Any:
        return call_tool(name, arguments)

    run.__name__ = name.replace("-", "_")
    run.__doc__ = f"the PACT tool `{name}`"
    return run


# ────────────────────────────────────────────────────────── the commands


USAGE = """\
pact-pydantic-ai — a PACT agent as a Pydantic AI spec, with a loss report

USAGE:
    pact-pydantic-ai PATH AGENT [--skills DIR]

Prints the `AgentSpec` as YAML, and the ExportReport underneath it. With
`--skills DIR`, the skills the agent uses are written there as a
pydantic-ai-harness Skills directory (`pydantic_ai_skills.skills_directory`),
which `Skills(DIR)` offers on demand, and their report follows.

The file loads with `Agent.from_file()`. It is NOT the whole agent: an
`AgentSpec` has no field for tools, ceilings, policy, the loop or the team, and
the report names every one of them. `pact_adapters.pydantic_ai_interop
.build_agent()` binds the tools and the approvals; `usage_limits_for()` builds
the ceilings that translate.

To go the other way, `pact-import --as pydantic-ai-spec FILE`.
"""


def main(argv: "list[str] | None" = None) -> int:
    import subprocess
    import sys

    import json
    import yaml

    args = list(sys.argv[1:] if argv is None else argv)
    skills_to = None
    if "--skills" in args:
        at = args.index("--skills")
        skills_to = args[at + 1] if at + 1 < len(args) else ""
        del args[at : at + 2]
    if len(args) != 2 or args[0] in ("-h", "--help") or skills_to == "":
        sys.stdout.write(USAGE)
        return 0 if args and args[0] in ("-h", "--help") else 1

    binary = pact_binary()
    if binary is None:
        sys.stderr.write(
            "error: the loader was not found, and a workspace is read through "
            f"it.\n  fix: {LOADER_FIX}\n"
        )
        return 3
    shown = subprocess.run([str(binary), "show", args[0]], capture_output=True, text=True)
    if shown.returncode != 0:
        sys.stderr.write(shown.stdout + shown.stderr)
        return 1

    document = json.loads(shown.stdout)
    if args[1] not in (document.get("agents") or {}):
        sys.stderr.write(
            f"error: there is no agent called `{args[1]}` in {args[0]}.\n"
            f"  fix: use one of: {', '.join(sorted(document.get('agents') or {}))}\n"
        )
        return 1

    spec, report = to_pydantic_ai_spec(document, args[1], workspace=args[0])
    sys.stdout.write(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True))
    sys.stdout.write("\n" + report.in_words() + "\n")
    if skills_to is not None:
        from pathlib import Path

        from .pydantic_ai_skills import skills_directory

        files, said = skills_directory(document, args[1], Path(args[0]))
        for name, body in files.items():
            (Path(skills_to) / name).parent.mkdir(parents=True, exist_ok=True)
            (Path(skills_to) / name).write_bytes(body)
        sys.stdout.write(f"\nWrote {len(files)} file(s) into {skills_to}.\n" + said.in_words() + "\n")
        return 1 if report.silent_losses or said.silent_losses else 0
    return 1 if report.silent_losses else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

