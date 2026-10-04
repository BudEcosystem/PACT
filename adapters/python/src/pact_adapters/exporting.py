"""Exporting a PACT agent, with a loss report (AC-6.3).

> Export to Bud `AgentRecord`, A2A Agent Card, and OSSA each produce a loss
> report consistent with the in-repo `ExportReport` shape.

The loss report is the whole thing. Every target format here is **smaller than a
PACT agent** — that is why they are facades and registry records rather than
specifications — so an export that just emits the target and says nothing hands
somebody a file that looks like their agent and is not.

`ExportReport` is the mirror of `ImportReport` in `importing.py`, and shares its
one structural idea: **what is lost is computed, not maintained.** Every field of
the source agent goes into `carried` or `not_carried`, and a field in neither is
`silent_losses` — found whether or not anybody expected it.

A third bucket exists here that has no import equivalent:
`supplied_by_the_runtime`. A `BudAgentRecord` has `version`, `revision`,
`status`, `registryKind`, `runtimeBackend` and an `invocation.url`, and **PACT
deliberately owns none of them.** They are registry and deployment facts; the
runtime decides them, which is what lets one tree run in two places. Emitting
invented values for them would be the export quietly claiming authority it does
not have, so they are left empty and named.

**OSSA is not here, and that is a refusal rather than an omission.** The thesis
names OSSA/OASF (AGNTCY) as a packaging manifest, and no schema for it exists in
this repository or in `gaia-ai-runtime` — the only matches are Italian
translation strings. Writing an exporter against a format nobody can check would
produce exactly the artifact this project keeps finding: something that looks
like coverage. It is recorded as blocked, with the fixture it needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .importing import ImportReport  # noqa: F401  (kept adjacent on purpose)
from .loader import FIX as LOADER_FIX
from .loader import pact_binary


@dataclass
class ExportReport:
    """What a target format could and could not take from a PACT agent."""

    #: What this was exported to.
    kind: str
    #: Every field the source agent carried, before anything was decided.
    seen: tuple[str, ...] = ()
    #: `{PACT field: where it went}`.
    carried: dict[str, str] = field(default_factory=dict)
    #: `{PACT field: why this format has no home for it}`.
    not_carried: dict[str, str] = field(default_factory=dict)
    #: Target fields PACT deliberately does not own, left for the runtime.
    supplied_by_the_runtime: dict[str, str] = field(default_factory=dict)

    @property
    def silent_losses(self) -> tuple[str, ...]:
        """Fields of the agent that nothing accounted for.

        Computed from `seen`, exactly as `ImportReport.silent_drops` is. A
        maintained list of known losses is a list somebody has to remember to
        extend, and the loss that matters is always the one nobody remembered.
        """
        said = set(self.carried) | set(self.not_carried)
        return tuple(sorted(k for k in self.seen if k not in said))

    def in_words(self) -> str:
        lines = [f"Exported to {self.kind}.", ""]
        if self.carried:
            lines.append(f"Carried over ({len(self.carried)}):")
            lines += [f"  {k} → {v}" for k, v in sorted(self.carried.items())]
            lines.append("")
        if self.not_carried:
            lines.append(f"LOST ({len(self.not_carried)}) — this format has no home for:")
            lines += [f"  {k}: {v}" for k, v in sorted(self.not_carried.items())]
            lines.append("")
        if self.supplied_by_the_runtime:
            lines.append("LEFT FOR THE RUNTIME — PACT does not own these:")
            lines += [
                f"  {k}: {v}" for k, v in sorted(self.supplied_by_the_runtime.items())
            ]
            lines.append("")
        if self.silent_losses:
            lines.append(
                "BUG IN THIS EXPORTER — the agent carries these and nothing above "
                f"accounts for them: {', '.join(self.silent_losses)}"
            )
        return "\n".join(lines)


#: Why each PACT field has nowhere to go in a registry record. Written out rather
#: than defaulted to "unsupported", because *which kind of thing it is* decides
#: whether losing it matters — a registry losing `instructions:` is expected; a
#: registry losing `policy:` means an index that cannot tell a governed agent from
#: an ungoverned one, which is worth a reader knowing.
_RECORD_CANNOT_TAKE: dict[str, str] = {
    "instructions": (
        "a registry record indexes agents; it does not carry what they are told. "
        "The tree remains the specification"
    ),
    "limits": "no field for ceilings — nothing here says when a run should stop",
    "loop": "no field for the shape of the thinking",
    "policy": (
        "no field for what needs a person. An index built from these records "
        "cannot tell a governed agent from an ungoverned one"
    ),
    "interceptors": "no field for rules that hide, stop or redirect",
    "teamwork": "no field for how a team's answers are waited for",
    "context-policy": "no field for how a long conversation is kept",
    "evals": "no field for how you would know it works",
    "learning": "no field for whether it may improve itself",
    "remembers": (
        "no field for what an agent remembers between turns — nor for the flag "
        "saying which of it a summary must put back, nor for `bind: remembers.<n>` "
        "and `remember-as:`, which read and write it"
    ),
    "answers-with": "no field for the shape of the answer",
    "answers-with-mode": "no field for how that shape is put to the model",
    "run-inputs": "no field for what the surrounding system supplies",
    "accepts": "no field for the shapes it takes in",
    "needs": "no field for what the model behind it has to be capable of",
    "variants": "no field for model-portability strategies",
    "model": (
        "a record names a `runtimeBackend`, not a model. Which model serves an "
        "agent is a runtime decision here"
    ),
    "model-for-checking": "no field for a second model on the checking stages",
    "settings": "no field for provider request parameters",
    "pauses": "no field for what happens while a run is stopped",
    "description": "",   # carried; present so the loop below can see every key
    "name": "",
    "uses": "",
    "team": "",
}

#: What a `BudAgentRecord` needs that PACT does not decide. Left empty and named,
#: because inventing them is the export claiming authority it does not have.
_RUNTIME_SUPPLIES: dict[str, str] = {
    "version": "the registry's version of this agent, not the document's",
    "revision": "which revision the registry is holding",
    "status": "whether the registry considers it live",
    "registryKind": "which registry this record belongs to",
    "runtimeBackend": "which runtime is serving it",
    "invocation.url": (
        "where this deployment answers. A PACT tree is not deployed anywhere — "
        "that is what makes the same tree runnable in two places"
    ),
}


def to_bud_agent_record(
    document: Mapping[str, Any], agent: str
) -> tuple[dict[str, Any], ExportReport]:
    """One PACT agent as a Bud `AgentRecord`, and everything it could not say.

    The shape is the real one, read off
    `gaia-ai-runtime/goose/ui/desktop/src/acp/bud.ts` rather than guessed — an
    exporter written against an invented schema is a file that will not load
    anywhere, dressed as an integration.

    Six of its fields are left EMPTY on purpose and named in the report:
    `version`, `revision`, `status`, `registryKind`, `runtimeBackend` and
    `invocation.url`. All six are registry or deployment facts, and PACT owning
    them would be the specification deciding where it runs.
    """
    block = dict((document.get("agents") or {}).get(agent) or {})
    report = ExportReport(kind="a Bud AgentRecord", seen=tuple(sorted(block)))

    named = [str(u) for u in (block.get("uses") or [])]
    # `uses:` names four collections and the record has a field for one of them.
    # A registry's `skills:` means WRITTEN PROCEDURES this agent consults — a
    # person opens one and reads it. A carried program is the opposite: a
    # compiled body with an engine, a determinism promise and a fuel ceiling,
    # which nothing opens and no one reads. Measured on the shipped fixture, the
    # record said `"skills": ["check-window"]` of a WebAssembly body, and a
    # consumer indexing that would believe this agent holds a procedure by that
    # name. It goes in the ledger instead, which is where a thing the target
    # format has no field for belongs.
    carried = set(document.get("programs") or {})
    uses = [u for u in named if u not in carried]
    reached = [u for u in named if u in carried]
    team = list((block.get("team") or {}))
    record: dict[str, Any] = {
        "apiVersion": "pact.dev/v1",
        "kind": "AgentRecord",
        "id": agent,
        "name": str(block.get("name") or agent),
        "description": str(block.get("description") or ""),
        # Left for the runtime. Empty rather than absent, so a consumer sees the
        # field and its emptiness rather than wondering whether we forgot.
        "version": "",
        "revision": "",
        "status": "",
        "registryKind": "",
        "runtimeBackend": "",
        "aliases": [],
        "skills": uses,
        # Teammates are a CAPABILITY of this agent from a registry's point of
        # view — "it can hand off to these" — and not skills of its own. Folding
        # them into `skills` would make an index think the supervisor owns what
        # its colleagues do.
        "capabilities": [f"handoff:{who}" for who in team],
        "invocation": {
            "protocol": "a2a",
            "url": "",
            "selector": {"id": agent, "version": "", "revision": ""},
        },
    }

    if reached:
        report.not_carried["programs"] = (
            "no field for a carried program — a compiled body with an engine, a "
            "determinism promise and a fuel ceiling is not a written procedure, and "
            f"putting {', '.join(sorted(reached))} in `skills:` would tell an index "
            "this agent holds something a person can read"
        )
    for present, where in (
        ("name", "`name`"), ("description", "`description`"),
        ("uses", "`skills`"), ("team", "`capabilities`, as `handoff:<name>`"),
    ):
        if present in block:
            report.carried[present] = where
    for key in block:
        if key in report.carried:
            continue
        report.not_carried[key] = _RECORD_CANNOT_TAKE.get(key) or (
            "no field in a registry record for this"
        )
    report.supplied_by_the_runtime = dict(_RUNTIME_SUPPLIES)
    return record, report


USAGE = """\
pact-export — a PACT agent as a registry record, with a loss report

USAGE:
    pact-export PATH AGENT

Prints the Bud `AgentRecord` as JSON, and the ExportReport underneath it. Six
fields come back EMPTY on purpose — `version`, `revision`, `status`,
`registryKind`, `runtimeBackend` and `invocation.url` — because they are registry
and deployment facts, and a specification that decided where it runs would stop
being runnable in two places.

The A2A card is `pact card`, in the Rust CLI. OSSA is not here: no schema for it
exists in reach, and an exporter written against an invented format is a file
that loads nowhere.
"""


def main(argv: "list[str] | None" = None) -> int:
    import json
    import subprocess
    import sys

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
    shown = subprocess.run(
        [str(binary), "show", args[0]], capture_output=True, text=True
    )
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

    record, report = to_bud_agent_record(document, args[1])
    sys.stdout.write(json.dumps(record, indent=2) + "\n\n")
    sys.stdout.write(report.in_words() + "\n")
    return 1 if report.silent_losses else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
