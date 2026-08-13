"""Importing framework-native artifacts, with zero silent drops (AC-2.4, AC-6.4).

> Framework-native fixtures import with an `ImportReport`; every unmapped
> construct appears in the report — measured coverage: **zero silent drops**
> across the fixture set.

The whole value is in the second half. An importer that maps what it recognises
and quietly discards the rest produces a PACT tree that looks complete and is
not — which is the same defect as a field that loads and reaches nothing, arriving
from outside instead of from within.

So every importer here returns `(document, ImportReport)` and the report accounts
for **every key in the source**, one of three ways:

* **mapped** — it became something in the PACT document, named on both sides;
* **unmapped** — this importer does not know it, said with what it was;
* **not-portable** — it is a fact about one runtime that PACT deliberately has no
  home for, said with why.

`ImportReport.silent_drops` is what a test asserts on, and it is computed from the
source rather than from a list somebody maintains: a key in none of the three
buckets is a silent drop by definition.

**Translate or nothing.** No importer here wraps a framework artifact in an opaque
carrier and calls it imported. A construct that cannot be translated is reported,
and the author is told what to write by hand — which is a worse experience and an
honest one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


@dataclass
class ImportReport:
    """What an import made of a framework's own artifact.

    Three buckets and a computed fourth. The fourth is the one with teeth: it is
    derived from the source, so a key nobody thought about lands in it without
    anybody having to remember.
    """

    #: What this import was of, in the source's own words.
    kind: str
    #: Every key in the source artifact, before anything was decided about it.
    seen: tuple[str, ...] = ()
    #: `{source key: what it became}`.
    mapped: dict[str, str] = field(default_factory=dict)
    #: `{source key: what it was}` — recognised as present, not understood.
    unmapped: dict[str, str] = field(default_factory=dict)
    #: `{source key: why PACT has no home for it}`.
    not_portable: dict[str, str] = field(default_factory=dict)
    #: What PACT needs and the source could not supply, so the author must.
    still_to_write: tuple[str, ...] = ()

    @property
    def silent_drops(self) -> tuple[str, ...]:
        """Keys in the source that nothing accounted for.

        Computed, never maintained. A list of known drops is a list somebody has
        to remember to extend, and the whole criterion is about the one nobody
        remembered.
        """
        said = set(self.mapped) | set(self.unmapped) | set(self.not_portable)
        return tuple(sorted(k for k in self.seen if k not in said))

    def in_words(self) -> str:
        """The report a person reads after importing something."""
        lines = [f"Imported {self.kind}.", ""]
        if self.mapped:
            lines.append(f"Carried over ({len(self.mapped)}):")
            lines += [f"  {k} → {v}" for k, v in sorted(self.mapped.items())]
            lines.append("")
        if self.unmapped:
            lines.append(f"NOT UNDERSTOOD ({len(self.unmapped)}) — nothing was done with these:")
            lines += [f"  {k}: {v}" for k, v in sorted(self.unmapped.items())]
            lines.append("")
        if self.not_portable:
            lines.append(f"NOT PORTABLE ({len(self.not_portable)}) — PACT has no home for these:")
            lines += [f"  {k}: {v}" for k, v in sorted(self.not_portable.items())]
            lines.append("")
        if self.still_to_write:
            lines.append("YOU STILL HAVE TO WRITE:")
            lines += [f"  {s}" for s in self.still_to_write]
            lines.append("")
        if self.silent_drops:
            lines.append(
                "BUG IN THIS IMPORTER — these were in the source and nothing "
                f"above accounts for them: {', '.join(self.silent_drops)}"
            )
        return "\n".join(lines)


# ───────────────────────────────────────────────────── an A2A Agent Card


#: What a card key becomes, and what PACT calls it.
_CARD_MAPS: dict[str, str] = {
    "name": "agent `name:`",
    "description": "agent `description:`",
    "skills": "`uses:` for tools, and `team:` for entries tagged `handoff`",
}

#: Card keys that describe a deployment rather than an agent.
_CARD_NOT_PORTABLE: dict[str, str] = {
    "url": (
        "where one deployment answers. A PACT tree is not deployed anywhere — a "
        "runtime decides that, which is what makes the same tree runnable in two "
        "places"
    ),
    "protocolVersion": (
        "which version of A2A the card speaks. PACT's own version is "
        "`pact-version:`, and copying one across would claim the tree was written "
        "for a protocol it has never heard of"
    ),
    "provider": "who hosts it — a deployment fact, like `url`",
    "version": "the deployment's version, not the document's",
    "documentationUrl": "where the humans read about it; not something a run uses",
}


def from_a2a_card(card: Mapping[str, Any]) -> tuple[dict[str, Any], ImportReport]:
    """One A2A Agent Card as a PACT agent, and everything it could not say.

    **A card is a facade, and the report is where that becomes visible.** PACT
    exports one (`pact card`) and it carries a name, a description, a URL and a
    list of skills — so importing one back gives a stub with no instructions, no
    ceilings, no loop and no policy. That is not a failure of this function; it
    is what a card is. What would be a failure is producing that stub and letting
    somebody believe they had imported an agent.
    """
    report = ImportReport(kind="an A2A Agent Card", seen=tuple(sorted(card)))
    agent: dict[str, Any] = {}

    if name := str(card.get("name") or "").strip():
        agent["name"] = name
        report.mapped["name"] = _CARD_MAPS["name"]
    if described := str(card.get("description") or "").strip():
        agent["description"] = described
        report.mapped["description"] = _CARD_MAPS["description"]

    uses: list[str] = []
    team: dict[str, str] = {}
    for skill in card.get("skills") or ():
        if not isinstance(skill, Mapping):
            continue
        tags = [str(t) for t in (skill.get("tags") or ())]
        who = str(skill.get("name") or "").strip()
        if not who:
            continue
        if "handoff" in tags:
            team[who] = str(skill.get("description") or "").strip() or f"helps with {who}"
        else:
            uses.append(who)
    if uses:
        agent["uses"] = uses
    if team:
        agent["team"] = team
    if uses or team:
        report.mapped["skills"] = _CARD_MAPS["skills"]

    for key, why in _CARD_NOT_PORTABLE.items():
        if key in card:
            report.not_portable[key] = why

    for key in card:
        if key not in report.mapped and key not in report.not_portable:
            report.unmapped[key] = f"a {type(card[key]).__name__} this importer does not read"

    # What a card cannot carry and a PACT agent needs. Said as a list of things
    # to write rather than as an error, because the import DID work — it just did
    # not produce a complete agent, and cannot.
    owed = ["`instructions:` — a card carries no instructions at all"]
    if not uses:
        owed.append("`uses:` — the card named no tools")
    owed += [
        "`limits:` — a card says nothing about when a run should stop",
        "`loop:` — a card says nothing about the shape of the thinking",
        "`policy:` — a card says nothing about what needs a person",
    ]
    report.still_to_write = tuple(owed)
    return agent, report


# ────────────────────────────────────── an Anthropic Messages API request


_REQUEST_MAPS: dict[str, str] = {
    "system": "agent `instructions:`",
    "tools": "`uses:`, and one `tools/<name>.yaml` per entry",
    "max_tokens": "`settings.max-tokens:`",
    "temperature": "`settings.temperature:`",
    "top_p": "`settings.top-p:`",
    "top_k": "`settings.top-k:`",
    "stop_sequences": "`settings.stop-sequences:`",
    "model": "agent `model:`",
    "tool_choice": "`settings.tool-choice:`",
}

_REQUEST_NOT_PORTABLE: dict[str, str] = {
    "messages": (
        "one conversation. A PACT agent is the thing that HAS conversations, not "
        "a transcript of one — importing these would freeze a single exchange "
        "into the specification"
    ),
    "stream": (
        "how this one call is delivered. A property of the call, decided by the "
        "runtime, not of the agent"
    ),
    "metadata": "whatever the caller attached to this request; not a fact about the agent",
    "service_tier": "a billing choice about one call",
}


def from_anthropic_request(
    request: Mapping[str, Any],
) -> tuple[dict[str, Any], ImportReport]:
    """One Messages API request body as a PACT agent, and what it could not say.

    A request is the most framework-native artifact there is that is also
    declarative — every other target in this repository defines its agents in
    code, and importing code means either executing it (which D17/D23 forbid) or
    parsing it (which is a different project). A request body is what a framework
    ends up sending, so it is the one place a framework's intent is written down
    rather than computed.
    """
    report = ImportReport(
        kind="an Anthropic Messages request", seen=tuple(sorted(request))
    )
    agent: dict[str, Any] = {}
    settings: dict[str, Any] = {}

    if system := request.get("system"):
        agent["instructions"] = (
            system if isinstance(system, str)
            else "\n\n".join(
                str(b.get("text", "")) for b in system if isinstance(b, Mapping)
            )
        )
        report.mapped["system"] = _REQUEST_MAPS["system"]
    if model := str(request.get("model") or "").strip():
        agent["model"] = model
        report.mapped["model"] = _REQUEST_MAPS["model"]

    tools: list[str] = []
    for tool in request.get("tools") or ():
        if isinstance(tool, Mapping) and (n := str(tool.get("name") or "").strip()):
            tools.append(n)
    if tools:
        agent["uses"] = tools
        report.mapped["tools"] = _REQUEST_MAPS["tools"]

    for wire, authored in (
        ("max_tokens", "max-tokens"), ("temperature", "temperature"),
        ("top_p", "top-p"), ("top_k", "top-k"),
        ("stop_sequences", "stop-sequences"),
    ):
        if wire in request:
            settings[authored] = request[wire]
            report.mapped[wire] = _REQUEST_MAPS[wire]
    if "tool_choice" in request:
        choice = request["tool_choice"]
        kind = str(choice.get("type") or "") if isinstance(choice, Mapping) else ""
        settings["tool-choice"] = {
            "auto": "auto", "any": "required", "none": "none",
        }.get(kind, str(choice.get("name", "")) if isinstance(choice, Mapping) else "")
        report.mapped["tool_choice"] = _REQUEST_MAPS["tool_choice"]
    if settings:
        agent["settings"] = settings

    for key, why in _REQUEST_NOT_PORTABLE.items():
        if key in request:
            report.not_portable[key] = why

    for key in request:
        if key not in report.mapped and key not in report.not_portable:
            report.unmapped[key] = (
                f"a {type(request[key]).__name__} this importer does not read"
            )

    owed = []
    if "system" not in request:
        owed.append("`instructions:` — the request carried no system prompt")
    owed += [
        "`description:` — a request has no place to say what the agent is for",
        "`limits:` — a request bounds one call, not a run",
        "`evals:` — nothing in a request says how you would know it works",
    ]
    report.still_to_write = tuple(owed)
    return agent, report


USAGE = """\
pact-import — turn a framework's own artifact into a PACT agent

USAGE:
    pact-import FILE [--as a2a-card|anthropic-request|pydantic-ai-spec]

Prints the agent as YAML, and the ImportReport underneath it. Nothing is
written: what comes back is a STUB, because these formats carry less than a PACT
agent does, and the report says exactly what you still have to write.

`pydantic-ai-spec` reads a Pydantic AI agent spec — the YAML or JSON that
`Agent.from_file()` loads. It is the one source here that is a real agent
SPECIFICATION rather than a facade or a single request, so what comes back is a
working agent short of its ceilings, policy and tools. A Pydantic AI agent
defined in Python instead has no file to read: hand the live object to
`pact_adapters.pydantic_ai_interop.from_pydantic_ai_agent()` from your own
process, which reads the object and still executes nothing of yours.
"""


def _from_pydantic_ai_spec(
    artifact: Mapping[str, Any],
) -> tuple[dict[str, Any], "ImportReport"]:
    """`pydantic_ai_interop.from_pydantic_ai_spec`, imported where it is used.

    Deferred rather than imported at module top for one reason: this module is
    what `pact-import` runs, and two of its three readers need nothing installed.
    A top-level `from .pydantic_ai_interop import ...` would make reading an A2A
    card fail on a machine with no Pydantic AI, which is the dependency creep
    that turns an offline tool into an online one (constraint 2).
    """
    from .pydantic_ai_interop import from_pydantic_ai_spec

    return from_pydantic_ai_spec(artifact)


#: What each `--as` reads, so the refusal can name them.
READERS = {
    "a2a-card": from_a2a_card,
    "anthropic-request": from_anthropic_request,
    "pydantic-ai-spec": _from_pydantic_ai_spec,
}


def main(argv: "list[str] | None" = None) -> int:
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        sys.stdout.write(USAGE)
        return 0

    kind = "a2a-card"
    if "--as" in args:
        at = args.index("--as")
        kind = args[at + 1] if at + 1 < len(args) else ""
        del args[at : at + 2]
    if kind not in READERS:
        sys.stderr.write(
            f"error: `{kind}` is not something this can read.\n"
            f"  fix: use one of: {', '.join(sorted(READERS))}\n"
        )
        return 1
    if not args:
        sys.stderr.write("error: no file was given\n  fix: name one\n")
        return 1

    import yaml

    try:
        # `yaml.safe_load` and not `json.loads`, because JSON is a subset of YAML
        # and one of the three sources is written in YAML far more often than in
        # JSON: `Agent.from_file()` infers the format from the extension and
        # every example in `agent-spec.md` is a `.yaml`. Reading only JSON here
        # would refuse the commonest spelling of the one artifact this reader
        # exists for, with a parse error that named the wrong problem.
        artifact = yaml.safe_load(Path(args[0]).read_text())
    except (OSError, ValueError, yaml.YAMLError) as trouble:
        sys.stderr.write(f"error: {args[0]} could not be read: {trouble}\n")
        return 1
    if not isinstance(artifact, Mapping):
        sys.stderr.write(
            f"error: {args[0]} is not an object — it parsed to a "
            f"{type(artifact).__name__}.\n  fix: an agent artifact is a mapping "
            "at the top level\n"
        )
        return 1

    agent, report = READERS[kind](artifact)

    sys.stdout.write(yaml.safe_dump(agent, sort_keys=False, allow_unicode=True))
    sys.stdout.write("\n" + report.in_words() + "\n")
    return 1 if report.silent_drops else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
