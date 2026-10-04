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
* `from_pydantic_ai_agent()` — a LIVE `Agent` object becomes a PACT agent. The
  caller has already imported their own module in their own process; PACT
  executes nothing of theirs and never reads their source. This is what covers
  the agents that are defined in code, which is most of them. What it can see
  is what the OBJECT holds, which is strictly less than what the CODE says —
  a `@agent.instructions` function is a callable, not a sentence, and the report
  says so rather than calling the agent instruction-less.
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

from typing import Any, Mapping

from .exporting import ExportReport
from .importing import ImportReport
from .ir import AgentSpec as PactAgentSpec
from .loader import FIX as LOADER_FIX
from .loader import pact_binary
from .pydantic_ai_registry import registry
from .questions import Shape
from .transports.pydantic_ai_transport import _SETTINGS, _translated
from .yes_no import said_yes

__all__ = [
    "shape_as_json_schema",
    "shape_from_json_schema",
    "return_schema_for",
    "from_pydantic_ai_spec",
    "from_pydantic_ai_agent",
    "to_pydantic_ai_spec",
    "usage_limits_for",
    "build_agent",
]


# ───────────────────────────── the answer shapes, as JSON Schema and back


#: One PACT answer shape, as the JSON Schema fragment that means the same thing.
#:
#: Built on `questions.Shape` rather than beside it, because the vocabulary is
#: closed and held in ONE place — `spec/schema.yaml` anchors it as
#: `&the-answer-shapes` and `Shape.parse` is the only reader. A second table
#: here would be the `same-setting-twice` mistake the validator exists to catch,
#: and it would go stale the first time a ninth shape is added.
_SHAPE_SCHEMAS: dict[str, dict[str, Any]] = {
    "text": {"type": "string"},
    "yes-or-no": {"type": "boolean"},
    "number": {"type": "number"},
    "whole-number": {"type": "integer"},
    # Money is a string and not a number, and the reason is `limits.py`'s: a
    # ceiling carries a CURRENCY (`40 USD`), `Ty::Money` refuses a bare `0.05`,
    # and a JSON Schema that said `number` would invite a model to answer `40`
    # for a field whose own parser rejects it. The description carries the
    # currency requirement to the model, which is the only place it can be said.
    "money": {"type": "string", "description": "an amount of money with its currency, e.g. `40 USD`"},
    # The three attachment shapes. A model returns a REFERENCE to one of these,
    # never the bytes, so the schema says so — and `shape_from_json_schema`
    # deliberately does not invert them, because `array of string` is far too
    # common a shape to claim back as `images`.
    "images": {"type": "array", "items": {"type": "string"}, "description": "references to images"},
    "audio": {"type": "array", "items": {"type": "string"}, "description": "references to audio"},
    "file": {"type": "array", "items": {"type": "string"}, "description": "references to files"},
    "agent": {"type": "string", "description": "the name of one of this workspace's agents"},
}


def shape_as_json_schema(shape: Shape) -> dict[str, Any]:
    """One `answers-with:` line as the JSON Schema fragment that means it.

    `one of approved, declined` becomes an `enum`, which is the only one of the
    ten that a model can be CONSTRAINED to rather than merely asked for — and
    it is also the shape PACT's own worked example uses, so getting it wrong
    would be visible in the first document anybody exports.
    """
    if shape.kind == "one-of":
        return {"type": "string", "enum": list(shape.choices)}
    return dict(_SHAPE_SCHEMAS[shape.kind])


def shape_from_json_schema(schema: Mapping[str, Any]) -> "Shape | None":
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


def _answers_with_schema(answers: Mapping[str, str]) -> "dict[str, Any] | None":
    """A PACT `answers-with:` block as one `output_schema` object.

    Every property is `required`, and that is not a default anybody fell into:
    PACT's answer shapes have no optionality marker at all, so a property left
    out of `required` would be claiming an authored line was optional when the
    document has no way to say it.
    """
    if not answers:
        return None
    properties: dict[str, Any] = {}
    for name, written in answers.items():
        properties[str(name)] = shape_as_json_schema(Shape.parse(written))
    return {
        "type": "object",
        "properties": properties,
        "required": sorted(properties),
        "additionalProperties": False,
    }


def return_schema_for(tool: Any, action: str) -> "dict[str, Any] | None":
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
    return _answers_with_schema(getattr(tool, "answers_with", {}).get(action) or {})


# ─────────────────────────────────────── Pydantic AI  →  PACT


#: What PACT can say of each capability, and the sentence for one it cannot —
#: one table (`pydantic_ai_registry.yaml`, 02P §4) that both importers and the
#: exporter read, so a capability cannot read as one thing through the spec door
#: and another through the live one.
_REGISTRY = registry()


#: What each `AgentSpec` key becomes, in PACT's own words.
_SPEC_MAPS: dict[str, str] = {
    "model": "agent `model:`",
    "name": "agent `name:`",
    "description": "agent `description:`",
    "instructions": "agent `instructions:`",
    "model_settings": "`settings:`",
    "output_schema": "`answers-with:`",
    "deps_schema": "`run-inputs:`",
    "capabilities": "`settings.thinking:` and `uses:`, per capability",
}

#: `AgentSpec` keys that are facts about Pydantic AI's own loop or tooling, which
#: PACT deliberately does not own. Written out one at a time rather than
#: defaulted to "unsupported", for the reason `exporting._RECORD_CANNOT_TAKE`
#: gives: WHICH KIND of thing it is decides whether losing it matters.
_SPEC_NOT_PORTABLE: dict[str, str] = {
    "end_strategy": (
        "`early`/`graceful`/`exhaustive` — what Pydantic AI does with tool calls "
        "the model requested alongside a final result. That is a property of "
        "`_agent_graph`'s loop, and PACT owns loop semantics itself (`loop:`), so "
        "copying the word across would claim a stage vocabulary PACT never ran"
    ),
    "retries": (
        "how many times Pydantic AI re-asks the model after a tool or output "
        "validation failure. PACT has no retry budget: a failure is a `limits:` "
        "question (`when-it-runs-out:`), decided per ceiling and not per category"
    ),
    "tool_timeout": (
        "how long one tool call may take before Pydantic AI returns a retry "
        "prompt. PACT bounds the RUN (`runs-for-at-most:`), not the call, and a "
        "per-call ceiling written as a run ceiling would stop the wrong thing"
    ),
    "metadata": (
        "whatever the caller tags each run with, for their traces. A fact about "
        "one deployment's observability, not about the agent"
    ),
    "instrument": "whether Logfire is on. A deployment choice, like `metadata`",
    "json_schema_path": (
        "`$schema` — which JSON Schema file an editor should autocomplete this "
        "spec against. A fact about the file, not about the agent"
    ),
}

#: The `ModelSettings` keys `pydantic_ai_transport._SETTINGS` does NOT name, and
#: why PACT has no home for each. The transport's table is the authority on the
#: twelve that DO map; this is its complement, and it is derived from
#: `ModelSettings.__annotations__` at import time so a thirteenth key added by an
#: SDK upgrade lands in the report rather than in silence.
_SETTINGS_NOT_PORTABLE: dict[str, str] = {
    "timeout": (
        "the HTTP timeout for one request. A transport-level knob the surrounding "
        "system owns; PACT's `finishes-within:` is a promise about the RUN"
    ),
    "logit_bias": (
        "per-token probability nudges, keyed by the tokeniser's own token ids. "
        "Those ids differ per model, so the setting is not portable by "
        "construction — the same block means something else on the next model"
    ),
    "extra_headers": "raw HTTP headers for one provider. Not a fact about the agent",
    "extra_body": "raw request-body fields for one provider. Not a fact about the agent",
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
            said = _THINKING_BACK.get(value if isinstance(value, bool) else str(value))
            if said is None:
                report.unmapped[f"{where}.thinking"] = (
                    f"`{value}` is a Pydantic AI thinking level PACT has no word "
                    "for — its `thinking:` is `none`, `low`, `medium`, `high`"
                )
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
            said = _THINKING_BACK.get(effort if isinstance(effort, bool) else str(effort))
            if said is None:
                report.unmapped[where] = (
                    f"`Thinking(effort={effort!r})` — PACT's `thinking:` is "
                    "`none`, `low`, `medium`, `high`"
                )
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


def from_pydantic_ai_spec(spec: Mapping[str, Any]) -> tuple[dict[str, Any], ImportReport]:
    """One Pydantic AI `AgentSpec` as a PACT agent, and everything it could not say.

    The first importer here whose source is a real agent SPECIFICATION rather
    than a facade or a single request. An A2A card carries a name and a URL; an
    Anthropic request carries one exchange. This carries the model, the
    instructions, the settings, the output shape and the capabilities — so the
    stub that comes back is a working agent short of its ceilings, its policy
    and its tools, rather than a name with nothing behind it.

    Nothing is executed. A spec is YAML; `Agent.from_file` is what runs it, and
    this is not that.
    """
    report = ImportReport(kind="a Pydantic AI agent spec", seen=tuple(sorted(spec)))
    agent: dict[str, Any] = {}
    settings: dict[str, Any] = {}

    if model := str(spec.get("model") or "").strip():
        agent["model"] = model
        report.mapped["model"] = _SPEC_MAPS["model"]
    if name := str(spec.get("name") or "").strip():
        agent["name"] = name
        report.mapped["name"] = _SPEC_MAPS["name"]
    if described := str(spec.get("description") or "").strip():
        agent["description"] = described
        report.mapped["description"] = _SPEC_MAPS["description"]
    if told := _instructions_text(spec.get("instructions")):
        agent["instructions"] = told
        report.mapped["instructions"] = _SPEC_MAPS["instructions"]

    if isinstance(spec.get("model_settings"), Mapping):
        settings.update(_settings_to_pact(spec["model_settings"], report, "model_settings"))
        if "model_settings" not in report.mapped:
            # Every key inside went to `unmapped`/`not_portable` under its own
            # name, but the OUTER key is what `seen` holds, and a key nothing
            # accounts for is a silent drop by definition.
            report.mapped["model_settings"] = _SPEC_MAPS["model_settings"]

    if isinstance(spec.get("output_schema"), Mapping):
        answers, refused = _schema_to_answers(spec["output_schema"])
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
        inputs, refused = _schema_to_answers(spec["deps_schema"])
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
    return agent, report


def _schema_to_answers(
    schema: Mapping[str, Any],
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
    for name, prop in properties.items():
        shape = shape_from_json_schema(prop if isinstance(prop, Mapping) else {})
        if shape is None:
            said = prop.get("type") if isinstance(prop, Mapping) else None
            refused[str(name)] = (
                f"a `{said or 'schema-less'}` property. PACT's answer shapes are "
                "text, yes-or-no, money, number, whole-number, images, audio, "
                "file, or `one of a, b, c` — a nested object or a list of them "
                "has no spelling, so this field is not carried"
            )
            continue
        lines[str(name)] = shape.written()
    return lines, refused


def _still_to_write(
    agent: Mapping[str, Any], *, tools_named: bool, has_policy: bool = False, connect: str = ""
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
    if not tools_named:
        owed.append("`uses:` — no tools were named")
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
            f"reach `{connect}`, and an endpoint is a name your platform team "
            "publishes rather than anything a Pydantic AI agent carries (add "
            "`auth: {by-reference: ...}` beside it if that server needs a "
            "credential). `resource_file_for()` writes the file once you have "
            "the name"
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


#: What each attribute of a live `Agent` becomes. Keyed by the name this importer
#: REPORTS, which is the public attribute where there is one — a reader of the
#: report should be able to find the thing named on the object they passed in.
_AGENT_MAPS: dict[str, str] = {
    "model": "agent `model:`",
    "name": "agent `name:`",
    "description": "agent `description:`",
    "instructions": "agent `instructions:`",
    "system_prompts": "agent `instructions:`, appended",
    "model_settings": "`settings:`",
    "output_type": "`answers-with:`",
    "toolsets": "`uses:`, and one `tools/<name>.yaml` per tool",
}


def from_pydantic_ai_agent(
    agent: Any, *, connect: str = ""
) -> tuple[dict[str, Any], ImportReport]:
    """One live Pydantic AI `Agent` as a PACT agent, and everything it could not say.

    **PACT executes nothing here.** The caller has already built the object, in
    their own process, by importing their own module — which is a thing they were
    always going to do and is not a thing this repository does to them. D17 and
    D23 forbid PACT running an author's code to find out what their agent is;
    they do not forbid PACT reading an object it was handed. That distinction is
    the whole reason this function takes an `Agent` and not a path.

    **What an object knows is less than what the code says, and the report says
    which.** `@agent.instructions`-decorated functions are callables: their text
    exists only once a `RunContext` exists, so they are reported as unmapped
    rather than invented. The same is true of a `prepare` on a tool, a dynamic
    `model_settings` callable, and a toolset built by a `ToolsetFunc`. An
    importer that quietly dropped those would produce a PACT tree missing the
    instructions that actually govern the agent.

    **`connect=` is the host answering the one question this source cannot.** A
    Pydantic AI tool is a Python function, so an imported tree used to arrive
    with every tool refused by `loader/tool-reaches-nowhere` — the largest entry
    on `still_to_write` and the one an author is least able to act on. A host
    that has wrapped those same functions as one MCP server already knows the
    answer, and naming the server here says it once: pass the SAME name to
    `tool_files_for(connect=...)`, which writes the line into every tool file,
    and to `resource_file_for()`, which writes the server's own file. It is
    taken here as well as there because this is what produces the REPORT, and a
    checklist that still demands a line the host has already written is a
    checklist people stop reading.
    """
    report = ImportReport(kind="a live Pydantic AI Agent", seen=_what_it_carries(agent))
    out: dict[str, Any] = {}
    settings: dict[str, Any] = {}

    model = getattr(agent, "model", None)
    if model is not None:
        # A `Model` object, not a string, once `defer_model_check` is off — and
        # its `model_name`/`system` are what a catalogue row is keyed on. A
        # `str()` of the object would carry a repr into `model:`.
        from pydantic_ai.models.fallback import FallbackModel

        # 02P A2: a `FallbackModel` is PACT's `model: [a, b]`, in its order
        # (`FallbackModel.models` is public, pydantic_ai/models/fallback.py:96).
        chain = (
            [_model_id(m) for m in model.models]
            if isinstance(model, FallbackModel)
            else [_model_id(model)]
        )
        named = chain[0] if len(chain) == 1 else (chain if all(chain) else "")
        if named:
            out["model"] = named
            report.mapped["model"] = _AGENT_MAPS["model"]
        else:
            report.unmapped["model"] = (
                f"a {type(model).__name__} whose provider and model name could "
                "not be read; write `model:` by hand"
            )
    if name := str(getattr(agent, "name", None) or "").strip():
        out["name"] = name
        report.mapped["name"] = _AGENT_MAPS["name"]
    if described := str(getattr(agent, "description", None) or "").strip():
        out["description"] = described
        report.mapped["description"] = _AGENT_MAPS["description"]

    told, dynamic = _static_instructions(agent)
    if told:
        out["instructions"] = told
        report.mapped["instructions"] = _AGENT_MAPS["instructions"]
    if dynamic:
        report.unmapped["instructions"] = (
            f"{dynamic} instruction/system-prompt function(s). Their text is "
            "produced from a `RunContext` at run time and does not exist on the "
            "object, so it is not carried — read them and write the sentences "
            "into `instructions:` yourself"
        )
    if getattr(agent, "_system_prompts", ()):
        report.mapped["system_prompts"] = _AGENT_MAPS["system_prompts"]

    said = getattr(agent, "model_settings", None)
    if callable(said):
        report.not_portable["model_settings"] = (
            "a callable — Pydantic AI re-evaluates it before every model request "
            "so settings can vary per step. PACT's `settings:` is one block for "
            "the run, so there is no value here to carry"
        )
    elif isinstance(said, Mapping):
        settings.update(_settings_to_pact(said, report, "model_settings"))
        if "model_settings" not in report.mapped:
            report.mapped["model_settings"] = _AGENT_MAPS["model_settings"]

    answers, refused = _output_type_to_answers(agent)
    if answers:
        out["answers-with"] = answers
        report.mapped["output_type"] = _AGENT_MAPS["output_type"]
    for where, why in refused.items():
        report.unmapped[where] = why

    uses, tools, tool_notes = _toolsets_to_pact(agent)
    if uses:
        out["uses"] = uses
        report.mapped["toolsets"] = _AGENT_MAPS["toolsets"]
    elif tool_notes:
        # Every toolset was unreadable, so nothing was carried and the OUTER key
        # is what `seen` holds. Naming only the `toolsets[0]` entries left
        # `toolsets` itself in no bucket at all — a silent drop, on the one agent
        # shape where the drop is the whole story: an agent all of whose tools
        # are built per run imported as an agent with no tools, and said so
        # nowhere a `silent_drops` check would find.
        report.unmapped["toolsets"] = (
            f"{len(tool_notes)} toolset(s), none of which can be read without "
            "starting a run — so no tool names were carried"
        )
    for where, why in tool_notes.items():
        report.unmapped[where] = why

    # Approval is the one place the two systems say the same thing, so it is
    # carried rather than reported: a tool whose `ToolDefinition.kind` is
    # `unapproved` is `requires_approval=True`, which is PACT's
    # `needs-a-person: yes` about that action and nothing else.
    #
    # It lands on the TOOL FILE and not on the agent, and that took a `pact
    # check` to learn. `agent.policy:` is a NAME — `names: policies` in the
    # schema — so the prose this wrote for a round (`policy: Ask a person before
    # refund.`) was refused with `schema/no-such-name`, and the fix is not to
    # write a policy file: `action.needs-a-person` is the shorthand the schema
    # added for exactly this case, and its own comment says gating one action
    # otherwise costs three files and thirteen lines. It desugars to `when:
    # [{tool: <tool>/<action>}]` against `pact:question/is-this-ok` — which is
    # precisely the rule `_tools_needing_approval` reads back on the way out, so
    # the two directions are symmetric by construction.
    #
    # Reported under `requires_approval` and NOT under `capabilities`, which is
    # where it was for a round. The two are different things and conflating them
    # cost the report its point twice over: `capabilities` was marked mapped, so
    # the middleware this importer genuinely cannot translate stopped being
    # named as not-portable — an agent with a guardrail capability imported
    # clean and silent.
    needs_person = [t for t, meta in tools.items() if meta.get("approval")]
    if needs_person:
        report.mapped["requires_approval"] = (
            "`needs-a-person: yes` on the action, in each tool's own file — see "
            "`tool_files_for()`, which is what writes them"
        )

    if capabilities := _authored_capabilities(agent):
        for name in _live_capabilities(capabilities, settings, uses, report):
            uses.append(name)
        uses[:] = sorted(set(uses))
        if uses:
            out["uses"] = uses

    if settings:
        out["settings"] = settings

    for key, why in _AGENT_NOT_PORTABLE.items():
        if key in report.seen and key not in report.mapped and key not in report.unmapped:
            report.not_portable[key] = why

    report.still_to_write = _still_to_write(
        out,
        tools_named=bool(uses),
        has_policy=bool(needs_person),
        connect=str(connect or "").strip(),
    )
    return out, report


def _what_it_carries(agent: Any) -> tuple[str, ...]:
    """Every part of this `Agent` that actually holds something.

    `seen` is what `silent_drops` is computed against, so what goes in it decides
    what a bug in this importer looks like. The two card readers set it to
    `tuple(sorted(card))` — the keys the source ACTUALLY HAS — and a live object
    has no such list: every attribute exists, most of them holding a default
    nobody chose.

    Listing them all unconditionally is what shipped first, and it was wrong in
    the direction that matters. An agent with no `system_prompt=` reported
    `system_prompts` as a silent drop — a BUG IN THIS IMPORTER banner, on a
    correct import, for a field the author never wrote. A reader who sees that
    banner on a clean run learns to ignore it, which costs the mechanism the one
    thing it is for.

    So an attribute is `seen` when it holds something: a non-empty value, or a
    number the author had to type. `end_strategy` is in the list only when it is
    not `graceful`, and `retries` only when it is not 1, because those are the
    constructor defaults — carried into the report they would be this importer
    reporting Pydantic AI's own defaults as the author's losses.
    """
    said: list[str] = []

    def carries(key: str, value: Any, default: Any = None) -> None:
        # Falsy IS absent for every attribute below — an empty list, an empty
        # tuple, an empty dict, `None`, `''`. Written as `not value` and not as a
        # chain of `!= () and != {}`, which is what it was and which let `[]`
        # through: `[] != ()` is True in Python, so a bare agent's empty
        # `_instructions` counted as carried and then reported itself a silent
        # drop. None of these fields has a meaningful falsy value.
        if not value or value == default:
            return
        said.append(key)

    carries("model", getattr(agent, "model", None))
    carries("name", getattr(agent, "name", None))
    carries("description", getattr(agent, "description", None))
    carries("instructions", _authored_instructions(agent))
    carries("system_prompts", tuple(getattr(agent, "_system_prompts", ()) or ()))
    carries("model_settings", getattr(agent, "model_settings", None))
    # `str` is `Agent`'s default output type and means the author declared no
    # shape — see `_output_type_to_answers` for why that carries nothing.
    carries("output_type", getattr(agent, "output_type", str), default=str)
    carries("end_strategy", getattr(agent, "end_strategy", "graceful"), default="graceful")
    carries("tool_timeout", getattr(agent, "_tool_timeout", None))
    carries("metadata", getattr(agent, "_metadata", None))
    carries("deps_type", getattr(agent, "deps_type", None), default=object)
    carries("output_validators", list(getattr(agent, "_output_validators", ()) or ()))
    if getattr(agent, "_max_tool_retries", 1) != 1 or getattr(agent, "_max_output_retries", 1) != 1:
        said.append("retries")

    # Toolsets by what is IN them, not by how many there are. Every agent has an
    # `_AgentFunctionToolset` whether or not anybody registered a tool, so
    # counting the list made a bare agent carry `toolsets` and then drop it.
    uses, tools, notes = _toolsets_to_pact(agent)
    if uses or notes:
        said.append("toolsets")
    if any(meta.get("approval") for meta in tools.values()):
        said.append("requires_approval")

    if _authored_capabilities(agent):
        said.append("capabilities")
    return tuple(sorted(said))


def _live_capabilities(
    capabilities: list[Any], settings: dict[str, Any], uses: list[str], report: ImportReport
) -> list[str]:
    """The author's capability OBJECTS, as whatever PACT can say of them.

    The live twin of `_read_capabilities`, and it exists because the two sources
    are genuinely different shapes: a spec entry is `{'Thinking': {'effort':
    'high'}}` and a live one is a `Thinking` instance with an `effort`
    attribute. Sharing one reader would mean guessing which it had.

    What they must NOT differ on is the answer. `Thinking(effort='high')` has to
    become `settings.thinking: high` whichever door it came through — otherwise
    the same agent imports two ways depending on whether its author wrote YAML
    or Python, which is the portability being merely technically true.

    Keyed on `get_serialization_name()`, the SDK's own name for a capability in
    a spec file, so the two readers agree by construction rather than by two
    tables being kept in step.
    """
    named: list[str] = []
    for capability in capabilities:
        kind = type(capability)
        try:
            name = kind.get_serialization_name() or kind.__name__
        except Exception:  # pragma: no cover - a custom capability may not have one
            name = kind.__name__
        where = f"capabilities.{name}"
        if name == "Thinking":
            effort = getattr(capability, "effort", True)
            said = _THINKING_BACK.get(effort if isinstance(effort, bool) else str(effort))
            if said is None:
                report.unmapped[where] = (
                    f"`Thinking(effort={effort!r})` — PACT's `thinking:` is "
                    "`none`, `low`, `medium`, `high`"
                )
                continue
            settings["thinking"] = said
            report.mapped[where] = _REGISTRY.capability("Thinking").pact
        elif _REGISTRY.crosses(name):
            row = _REGISTRY.capability(name)
            named.append(row.tool)
            report.mapped[where] = row.pact
            if name == "MCP":
                # The live twin of the same sentence, from the same constant, so
                # the two doors cannot tell an author two different things about
                # the one protocol.
                report.not_portable[f"{where}.wire-shape"] = _MCP_SHAPE
        else:
            report.not_portable[where] = _REGISTRY.why_not_portable(name)
    # The outer key only counts as accounted-for when at least one capability
    # was: otherwise `capabilities` falls through to `_AGENT_NOT_PORTABLE` and is
    # named there, which is the honest answer for an agent whose only
    # capabilities are middleware.
    if any(k.startswith("capabilities.") for k in report.mapped):
        report.mapped["capabilities"] = _SPEC_MAPS["capabilities"]
    return named


def _authored_capabilities(agent: Any) -> list[Any]:
    """The capabilities somebody actually passed, without the infrastructure.

    `Agent.__init__` calls `_inject_auto_capabilities`, which appends every type
    in `_AUTO_INJECT_CAPABILITY_TYPES` that is not already there — `ToolSearch`
    and `PendingMessageDrainCapability` on 2.21. They are on EVERY agent,
    including one constructed as `Agent('openai:gpt-5.2')` and nothing else.

    Counting them made every bare agent report a capability its author never
    wrote, under a heading that says PACT cannot translate it. A report that
    cries loss on an agent with no losses is the same failure as one that stays
    quiet on an agent with them.

    The list is read from the SDK rather than written here, so an upgrade that
    injects a third does not silently start reporting it. If that private name
    ever goes, the fallback is to name none of them — which fails towards
    reporting too much, and a reader can see a capability they did not write far
    more easily than they can see one that was never mentioned.

    **By value and not by type**, which is the difference between filtering the
    injected one and filtering the author's. `_inject_auto_capabilities` appends
    `cap_type()` — a DEFAULT-constructed instance — and only when the type is not
    already there. So an author who writes `ToolSearch(max_results=20)` gets
    theirs and no injected one, and a filter keyed on the TYPE would drop the
    only capability they configured, silently, under a mechanism whose whole
    purpose is that nothing is dropped silently.

    Capabilities are `@dataclass`es (the spec registry refuses one that is not),
    so `==` is a field comparison and a configured instance differs from a
    default one. An author who passes a bare `ToolSearch()` is filtered — and
    should be: it is byte-identical to the injected one, so there is nothing
    about it to report.
    """
    root = getattr(agent, "root_capability", None)
    if root is None:
        return []
    try:
        from pydantic_ai.agent import _AUTO_INJECT_CAPABILITY_TYPES  # type: ignore[attr-defined]

        automatic = tuple(_AUTO_INJECT_CAPABILITY_TYPES)
    except (ImportError, AttributeError):  # pragma: no cover - SDK rename
        automatic = ()

    def injected(capability: Any) -> bool:
        for kind in automatic:
            if type(capability) is not kind:
                continue
            try:
                return bool(capability == kind())
            except Exception:  # pragma: no cover - a capability that will not compare
                return True
        return False

    return [c for c in (getattr(root, "capabilities", ()) or ()) if not injected(c)]


#: What a live `Agent` carries that PACT does not. The spec-file reasons hold
#: word for word, plus the two an object has and a file cannot.
_AGENT_NOT_PORTABLE: dict[str, str] = dict(
    _SPEC_NOT_PORTABLE,
    deps_type=(
        "the Python type dependencies are injected as. PACT's `run-inputs:` names "
        "what the surrounding system supplies and the shape of each; it does not "
        "name a class, because a class is not portable to another language"
    ),
    output_validators=(
        "`@agent.output_validator` functions — Python that inspects an output and "
        "may raise `ModelRetry`. PACT's equivalent is an eval or a judged rule, "
        "which is an authored sentence rather than a callable"
    ),
    capabilities=(
        "Pydantic AI middleware around `_agent_graph`. See `interceptors:` — the "
        "shapes do not correspond, so nothing is claimed"
    ),
)
_AGENT_NOT_PORTABLE.pop("json_schema_path", None)


def _model_id(model: Any) -> str:
    """The catalogue-shaped id of a bound model — `provider:name`.

    A string was passed straight through by `Agent.__init__` only when
    `defer_model_check=True`; otherwise `models.infer_model` has already turned it
    into a `Model`, whose `system` and `model_name` are the two halves the
    catalogue keys on. Reading `str(model)` instead would put a repr in `model:`.
    """
    if isinstance(model, str):
        return model.strip()
    system = str(getattr(model, "system", "") or "").strip()
    named = str(getattr(model, "model_name", "") or "").strip()
    if system and named:
        return f"{system}:{named}"
    return named


def _authored_instructions(agent: Any) -> list[Any]:
    """`Agent(instructions=...)` entries as the author passed them.

    There is no public read of an agent's own instructions, so this reads
    `Agent._instructions`, the one private attribute it has to (2.54:
    agent/__init__.py:757). Since 2.54 each entry is a `SourcedInstruction`
    holding the author's value under `.instruction` (_instructions.py:46); 2.21
    held the values bare. Both shapes read the same, and a static
    `InstructionPart` reads as its text, so the same agent imports the same way
    on either pin.
    """
    out: list[Any] = []
    for entry in getattr(agent, "_instructions", ()) or ():
        value = getattr(entry, "instruction", entry)
        text = getattr(value, "content", None)
        if not isinstance(value, str) and isinstance(text, str) and not getattr(value, "dynamic", True):
            value = text
        out.append(value)
    return out


def _static_instructions(agent: Any) -> tuple[str, int]:
    """The instruction text that exists WITHOUT a run, and how much does not.

    `Agent._instructions` holds a mixed list — strings the author wrote and
    functions they decorated — and `_system_prompts` holds the static half of the
    older `system_prompt=` surface. Both reach the model as one system message,
    which is exactly `instructions:`, so both are joined here in that order.
    """
    said: list[str] = []
    dynamic = 0
    for entry in _authored_instructions(agent):
        if isinstance(entry, str):
            said.append(entry.strip())
        else:
            dynamic += 1
    said += [str(s).strip() for s in getattr(agent, "_system_prompts", ()) or ()]
    dynamic += len(getattr(agent, "_system_prompt_functions", ()) or ())
    dynamic += len(getattr(agent, "_system_prompt_dynamic_functions", {}) or {})
    return "\n\n".join(s for s in said if s), dynamic


def _output_type_to_answers(agent: Any) -> tuple[dict[str, str], dict[str, str]]:
    """A live agent's output type as `answers-with:` lines.

    Read through `agent.output_json_schema()`, which is public and is the same
    schema the SDK itself sends — rather than by unwrapping `ToolOutput`,
    `NativeOutput`, `PromptedOutput` and the bare-type case one at a time, which
    would be four chances to disagree with what the model is actually told.

    A plain `str` output type produces `{"type": "string"}` and NOT an object,
    and that is not an answer shape map: PACT's `answers-with:` is a set of named
    fields. `str` is the default and means the author declared no shape, so it
    carries nothing and reports nothing — an `answers-with: {answer: text}`
    nobody wrote would be this importer inventing a contract.
    """
    refused: dict[str, str] = {}
    try:
        schema = agent.output_json_schema()
    except Exception as trouble:  # pragma: no cover - depends on the user's type
        return {}, {"output_type": f"its JSON schema could not be built: {trouble}"}
    if not isinstance(schema, Mapping) or schema.get("type") != "object":
        return {}, refused
    return _schema_to_answers(schema)


def _toolsets_to_pact(agent: Any) -> tuple[list[str], dict[str, dict[str, Any]], dict[str, str]]:
    """Every tool the agent holds statically, by name.

    "Statically" is the load-bearing word and it is why this returns notes. A
    `FunctionToolset` holds its tools in a public dict and an `ExternalToolset`
    holds `ToolDefinition`s, so both can be read with no run. A toolset built by
    a `ToolsetFunc`, an MCP server that has not been connected, and anything
    behind a `prepare` are all resolved per RUN against a `RunContext` — there is
    no list to read, and reporting that is the difference between an agent
    imported with four of its nine tools and an agent that says so.
    """
    uses: list[str] = []
    tools: dict[str, dict[str, Any]] = {}
    notes: dict[str, str] = {}
    for i, toolset in enumerate(getattr(agent, "toolsets", ()) or ()):
        kind = type(toolset).__name__
        holder = getattr(toolset, "tools", None)
        defs = getattr(toolset, "tool_defs", None)
        if isinstance(holder, Mapping):
            for name, tool in holder.items():
                td = getattr(tool, "tool_def", None)
                tools[str(name)] = {
                    "description": str(getattr(td, "description", "") or ""),
                    "parameters": dict(getattr(td, "parameters_json_schema", {}) or {}),
                    "approval": getattr(td, "kind", "") == "unapproved",
                }
                uses.append(str(name))
        elif isinstance(defs, list):
            for td in defs:
                name = str(getattr(td, "name", "") or "")
                if not name:
                    continue
                tools[name] = {
                    "description": str(getattr(td, "description", "") or ""),
                    "parameters": dict(getattr(td, "parameters_json_schema", {}) or {}),
                    "approval": getattr(td, "kind", "") == "unapproved",
                }
                uses.append(name)
        else:
            notes[f"toolsets[{i}]"] = (
                f"a {kind} whose tools are resolved per run against a "
                "`RunContext` — there is no list to read without starting one, "
                "so its tools are not carried"
            )
    return sorted(set(uses)), tools, notes


def tool_files_for(agent: Any, *, connect: str = "") -> dict[str, dict[str, Any]]:
    """One `tools/<name>.yaml` body per tool the agent holds.

    Separate from `from_pydantic_ai_agent` because it writes a different FILE.
    The agent block names tools on `uses:`; each tool is its own document, and a
    `takes:` block is the one part of it this can fill in — from the tool's own
    `parameters_json_schema`, which is the same schema the model is shown.

    `spends-money:` is deliberately absent from what this produces. Nothing in a
    Pydantic AI tool says whether it moves money, and `crates/pact-loader/src/
    money.rs` refuses a spending action no approval rule names — so a guess
    either way would be a guess about governance.

    **The line that says where the tool reaches is the one this cannot guess**,
    and it stops the file loading rather than merely weakening it. `pact check`
    refuses a tool with no `connect:`, `url:` or `says:`
    (`loader/tool-reaches-nowhere`), and its own message gives the reason: the
    model is still offered the tool and every call comes back `error: no tool
    named ...`. A Pydantic AI tool is a Python function in the author's process,
    and *call this Python function* is not something a portable document can say
    to a second runtime — which is the rule working, not a gap in it.

    `connect=` is where the answer comes from, and it comes from the HOST rather
    than from the agent. The commonest way to make these functions reachable by a
    second runtime is to serve them — one MCP server carrying all of them — and a
    host that has done that knows the server's name and PACT does not. Given it,
    every tool file here says `connect: <that server>`, `resource_file_for()`
    writes the server's own file, and the tree that comes out is COMPLETE: `pact
    check` exits 0 with nothing left to add by hand. Without it the files are the
    same minus that line, and `from_pydantic_ai_agent`'s `still_to_write` names
    the line and where to put it.

    One name for all of them, and deliberately not a name per tool. The claim
    being made is *these functions are now behind that server*, which is either
    true of the set or not true at all; a per-tool map would let a caller wire
    half a toolset to a server that does not serve it, and the loader cannot
    catch that — `names: resources` only checks the server EXISTS.
    """
    named = str(connect or "").strip()
    _, tools, _ = _toolsets_to_pact(agent)
    files: dict[str, dict[str, Any]] = {}
    for name, meta in sorted(tools.items()):
        takes: dict[str, str] = {}
        properties = (meta.get("parameters") or {}).get("properties")
        if isinstance(properties, Mapping):
            for arg, prop in properties.items():
                shape = shape_from_json_schema(prop if isinstance(prop, Mapping) else {})
                takes[str(arg)] = shape.written() if shape else "text"
        action: dict[str, Any] = {}
        if takes:
            action["takes"] = takes
        if meta.get("approval"):
            # `requires_approval=True`, in PACT's one-line spelling. The schema
            # added this shorthand because gating one action otherwise costs a
            # question, a policy file and a rule inside it — and it desugars to
            # exactly that rule, so nothing about the guarantee is weaker.
            action["needs-a-person"] = "yes"
        body: dict[str, Any] = {
            "description": meta.get("description") or f"the {name} tool",
        }
        if named:
            # Written between `description:` and `actions:`, which is where the
            # worked example puts it — a tool file is read top to bottom by a
            # person, and *what this is* then *where it goes* then *what it can
            # do* is the order the questions occur to them.
            body["connect"] = named
        body["actions"] = {"call": action}
        files[name] = body
    return files


def resource_file_for(
    name: str, endpoint: str, *, asks_to_connect: str = ""
) -> dict[str, Any]:
    """The body of one `resources/<name>.yaml` — the server those tools reach.

    The other half of `tool_files_for(connect=...)`, and the reason the pair
    exists: `connect:` names a server, `names: resources` holds it to naming one
    that is really there, and until this function there was no way to emit that
    file at all — so an imported tree could satisfy `reach.rs` only by having a
    person hand-write a document PACT knew the shape of perfectly well.

    **Four lines, and none of them is a value.** `endpoint:` and `auth:` are
    both REFERENCES the host resolves — never an address with a secret in it,
    never a command, never arguments — because honouring a command here would
    make reviewing an untrusted workspace an act of running its code (§11.5).
    That is why `endpoint` is an argument rather than something guessed from the
    agent: it is a name the platform team publishes, and there is nothing in a
    Pydantic AI `Agent` that could supply it.

    **`auth:` is deliberately not written.** A credential reference is that same
    platform team's name for a secret, and a guess at one would produce a file
    that loads clean and cannot connect — `pact check` does not require the
    field, so nothing downstream would catch it. `still_to_write` says to add it
    beside the endpoint when the server needs one.

    `asks_to_connect` names the question a person is asked the first time a run
    reaches this server, and it is a NAME: `names: questions` means the
    workspace must carry `questions/<that>.yaml`, so passing one owes a question
    file. Left out, the connection is taken as already allowed — which is the
    honest default for a server the host has just stood up itself.
    """
    called = str(name or "").strip()
    reaches = str(endpoint or "").strip()
    if not reaches:
        # A blank endpoint is the one mistake this function could make that
        # nothing downstream would catch: `endpoint:` is not `required:` in the
        # schema, so `endpoint: ''` loads clean and the tools that name this
        # server reach a server that goes nowhere — the exact
        # "loads and does nothing" failure `reach.rs` was written against, one
        # hop further along.
        raise ValueError(
            f"`{called or 'this server'}` needs an endpoint: a name your "
            "platform team publishes for this MCP server. It is their list, not "
            "a file in here, and not a URL with a credential in it"
        )
    body: dict[str, Any] = {"resource-kind": "mcp-server", "endpoint": reaches}
    if asked := str(asks_to_connect or "").strip():
        body["asks-to-connect"] = asked
    body["description"] = f"{called}, as the host publishes it."
    return body


# ─────────────────────────────────────── PACT  →  Pydantic AI


#: Why each PACT agent field has nowhere to go in an `AgentSpec`. Written out one
#: at a time for `exporting._RECORD_CANNOT_TAKE`'s reason: which KIND of thing is
#: lost decides whether losing it matters, and half of these are the difference
#: between a governed agent and an ungoverned one.
_SPEC_CANNOT_TAKE: dict[str, str] = {
    "uses": (
        "an `AgentSpec` has no `tools:` field — its only tool-bearing field is "
        "`capabilities:`, which names Pydantic AI's own provider-adaptive tools "
        "and not an author's. The names are carried in the companion report and "
        "`build_agent()` binds them; a spec file alone cannot"
    ),
    "team": (
        "no field for who helps. Pydantic AI does delegation by calling one "
        "`Agent` from inside another's tool function, which is Python, not spec"
    ),
    "teamwork": "no field for how a team's answers are waited for or how a budget is shared",
    "limits": (
        "no field for ceilings. `UsageLimits` is an argument to `run()`, not part "
        "of an agent — so a spec file cannot stop a run, and until something "
        "passes `usage_limits=` the ceilings the author wrote are not enforced. "
        "`usage_limits_for()` builds the ones that translate"
    ),
    "loop": (
        "no field for the shape of the thinking. Pydantic AI's loop is "
        "`_agent_graph`'s and has no stage vocabulary — `may-use:`, "
        "`does: ask-someone` and the rest have nothing to become"
    ),
    "policy": (
        "no field for what needs a person. `requires_approval=True` is a "
        "per-tool Python argument, so an approval rule survives only through "
        "`build_agent()`, which sets it on the tools the policy names. A spec "
        "file alone carries no policy, and an index built from these could not "
        "tell a governed agent from an ungoverned one"
    ),
    "interceptors": (
        "no field for rules that hide, stop or redirect. Pydantic AI's nearest "
        "shape is a capability, which is a Python object and not a sentence"
    ),
    "context-policy": (
        "no field for how a long conversation is kept. Pydantic AI compacts with "
        "a history processor wrapped in `ProcessHistory`, which takes a callable "
        "and is therefore marked spec-unusable by its own docs"
    ),
    "evals": "no field for how you would know it works — that is `pydantic_evals`, a separate document",
    "learning": "no field for whether it may improve itself",
    "remembers": "no field for what survives a summary",
    "answers-with-mode": (
        "no field in the SPEC for how the shape is put to the model — "
        "`output_schema` builds a `StructuredDict`, whose mode is `auto`, "
        "decided per model from `ModelProfile.default_structured_output_mode`, "
        "so an author who wrote `native-json-schema` gets whatever their model "
        "prefers instead. `build_agent()` DOES honour it: the four words map "
        "exactly onto `str`, `PromptedOutput`, `NativeOutput` and `ToolOutput`. "
        "This is the clearest single reason the export has two halves"
    ),
    "accepts": "no field for the shapes it takes in",
    "needs": "no field for what the model behind it has to be capable of",
    "variants": "no field for model-portability strategies",
    "model-for-checking": "no field for a second model on the checking stages",
    "pauses": (
        "no field for what happens while a run is stopped. Pydantic AI parks on "
        "`DeferredToolRequests` and resumes from `deferred_tool_results=`, which "
        "is the same shape — but it is a calling convention, not configuration"
    ),
    "run-inputs": "",   # carried, as `deps_schema`
    "name": "",
    "description": "",
    "instructions": "",
    "model": "",
    "settings": "",
    "answers-with": "",
}

#: `AgentSpec` fields PACT deliberately does not decide, left unset and named.
_SPEC_SUPPLIES: dict[str, str] = {
    "end_strategy": (
        "what to do with tool calls the model requested alongside a final "
        "result. PACT owns loop semantics and has no word for this, so Pydantic "
        "AI's own default (`graceful`) stands"
    ),
    "retries": "how often to re-ask after a tool or output failure — a Pydantic AI budget",
    "tool_timeout": "how long one tool call may take — a Pydantic AI ceiling, not a PACT one",
    "metadata": "whatever the deployment tags its runs with",
    "instrument": "whether Logfire is on, which is the deployment's choice",
}

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
        # `build_agent(..., model=FallbackModel(...))` is where they go.
        report.not_carried["model.fallbacks"] = (
            f"`model:` lists {len(chain)} models and a Pydantic AI spec file holds "
            f"one, so only `{chain[0]}` is carried and the fallbacks "
            + ", ".join(f"`{m}`" for m in chain[1:])
            + " are not tried when it fails. fix: build the agent with "
            "`model=FallbackModel(...)` over the same models, in this order"
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
        schema = _answers_with_schema(answers)
        if schema:
            spec["output_schema"] = schema
            report.carried["answers-with"] = "`output_schema`, as a JSON Schema object" + (
                _one_way_shapes(answers)
            )

    if isinstance(block.get("run-inputs"), Mapping) and block["run-inputs"]:
        schema = _answers_with_schema({k: str(v) for k, v in block["run-inputs"].items()})
        if schema:
            spec["deps_schema"] = schema
            report.carried["run-inputs"] = "`deps_schema`"

    for key in block:
        if key in report.carried:
            continue
        report.not_carried[key] = _SPEC_CANNOT_TAKE.get(key) or (
            "no field in a Pydantic AI agent spec for this"
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
    `tool_calls_limit`, `tokens-at-most` is `total_tokens_limit`.

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
        request_limit=spec.max_steps,
        tool_calls_limit=limits.tool_calls_at_most,
        total_tokens_limit=limits.tokens_at_most,
    )


def build_agent(
    spec: PactAgentSpec,
    *,
    call_tool: Any = None,
    model: Any = None,
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
                            parameters_json_schema=_takes_as_schema(t.parameters),
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
                        json_schema=_takes_as_schema(t.parameters),
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
    # A fallback list (`spec.models`, 02P A2) binds its FIRST model here and
    # nothing more: `FallbackModel.__init__` calls `infer_model` on every entry
    # at construction (pydantic_ai/models/fallback.py:131), which is exactly the
    # credentials check `defer_model_check=True` below exists to put off. A host
    # that wants the chain passes `model=FallbackModel(...)` itself.
    bound: Any = model
    if bound is None and spec.model:
        said, _ = pydantic_ai_model_id(spec.model, spec.workspace)
        bound = said or None

    return Agent(
        bound,
        name=spec.name or spec.key or None,
        description=spec.description or None,
        instructions=_instructions_with_skills(spec) or None,
        model_settings=settings or None,
        output_type=_output_type_for(spec),
        toolsets=toolsets or None,
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

    answers = _answers_with_schema(spec.answers_with)
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


def _takes_as_schema(takes: Mapping[str, Any]) -> dict[str, Any]:
    """A PACT tool's `takes:` block as the JSON schema the model is shown.

    Every argument required, for `_answers_with_schema`'s reason: PACT's shape
    vocabulary has no optionality marker, so leaving one out of `required` would
    invent a permission the document does not grant.
    """
    properties: dict[str, Any] = {}
    for arg, written in (takes or {}).items():
        try:
            properties[str(arg)] = shape_as_json_schema(Shape.parse(written))
        except Exception:
            # `action: one of refund, check` parses; a free-text shape an author
            # wrote loosely does not, and a tool argument is not the place to
            # fail a run — the model is shown a string and the tool's own
            # validation is what refuses a bad value.
            properties[str(arg)] = {"type": "string", "description": str(written)}
    return {
        "type": "object",
        "properties": properties,
        "required": sorted(properties),
        "additionalProperties": False,
    }


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
    pact-pydantic-ai PATH AGENT

Prints the `AgentSpec` as YAML, and the ExportReport underneath it.

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
    if len(args) != 2 or args[0] in ("-h", "--help"):
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
    return 1 if report.silent_losses else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
