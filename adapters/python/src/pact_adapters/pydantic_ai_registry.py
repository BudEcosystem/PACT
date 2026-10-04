"""PACT and Pydantic AI, one table (02P §4).

`pydantic_ai_registry.yaml` beside this file says, once, what every PACT agent,
tool and action field becomes in Pydantic AI, and what PACT can say of every
capability Pydantic AI ships, and of every other name on Pydantic AI's side
(an `AgentSpec` key, a live `Agent` attribute, a `ModelSettings` key). It
replaces the tables `pydantic_ai_interop.py` kept by hand (`_CAPABILITY_MAPS`,
`_TOOL_NAMES`, `_middleware_reason`'s sentence, and the field tables of both
importers and the exporter), so the spec importer, the live importer and the
exporter read one answer, and a host compiling PACT to Pydantic AI reads the
same one.

This module imports no agent framework: the table is data, read with `yaml`, so
anything that only needs to know the mapping can know it without Pydantic AI
installed. `pact-mapping` writes it out as a page.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import yaml

#: The registry file, shipped inside the package.
PATH = Path(__file__).with_name("pydantic_ai_registry.yaml")

#: The three outcomes (02P §1). There is no fourth.
OUTCOMES = ("carried", "mapped", "loss")

#: The kinds whose fields the registry must cover, in the order a page lists them.
KINDS = ("agent", "tool", "action")


@dataclass(frozen=True)
class FieldRow:
    """One PACT field and the Pydantic AI construct it becomes."""

    field: str  # `agent.instructions`
    construct: str
    outcome: str
    rows: tuple[str, ...]
    how: str = ""
    #: Why an `AgentSpec` FILE has no field for it, when it has none. Empty for
    #: a field the exporter writes into the file (or one never exported).
    spec_file: str = ""


@dataclass(frozen=True)
class CapabilityRow:
    """One Pydantic AI capability and what PACT can say of it."""

    name: str
    outcome: str
    rows: tuple[str, ...]
    #: PACT's spelling, for one that crosses.
    pact: str = ""
    #: The name it takes on `uses:`, for a provider-adaptive tool.
    tool: str = ""
    #: The named loss, when it is not the middleware sentence.
    why: str = ""


#: The doors a Pydantic AI name comes through: an `AgentSpec` file's key, a live
#: `Agent`'s attribute, or a `ModelSettings` key.
DOORS = ("spec", "agent", "settings")


@dataclass(frozen=True)
class NameRow:
    """One Pydantic AI name that is not a capability, and what PACT says of it."""

    name: str  # `spec.end_strategy`
    outcome: str
    rows: tuple[str, ...]
    #: PACT's spelling, for one that crosses.
    pact: str = ""
    #: The named loss.
    why: str = ""
    #: What an export leaves to Pydantic AI's own default, and why.
    left: str = ""


@dataclass(frozen=True)
class Registry:
    pydantic_ai: str
    fields: Mapping[str, FieldRow]
    capabilities: Mapping[str, CapabilityRow]
    middleware: str
    names: Mapping[str, NameRow]

    def through(self, door: str) -> dict[str, NameRow]:
        """The names one door carries, keyed by the bare name, in file order."""
        prefix = f"{door}."
        return {k[len(prefix):]: row for k, row in self.names.items() if k.startswith(prefix)}

    def capability(self, name: str) -> CapabilityRow | None:
        return self.capabilities.get(name)

    def crosses(self, name: str) -> bool:
        """Whether a capability has a PACT spelling (`carried` or `mapped`)."""
        row = self.capabilities.get(name)
        return row is not None and row.outcome != "loss"

    def why_not_portable(self, name: str) -> str:
        """The named loss for a capability with no PACT spelling.

        A name the registry has never seen gets the middleware sentence too: it
        is a capability, and every capability is middleware unless a row says
        otherwise. The completeness test is what keeps that case to a
        customer's own capability or a newer SDK.
        """
        row = self.capabilities.get(name)
        if row is not None and row.why:
            return row.why
        return self.middleware.format(name=name)


class RegistryError(ValueError):
    """The registry file says something the three outcomes cannot mean."""


def _rows(entry: Mapping[str, Any], where: str) -> tuple[str, ...]:
    rows = entry.get("rows")
    if not isinstance(rows, list) or not rows or not all(isinstance(r, str) for r in rows):
        raise RegistryError(f"{where}: `rows:` names the 02P rows that own this mapping")
    return tuple(rows)


def _outcome(entry: Mapping[str, Any], where: str) -> str:
    said = entry.get("outcome")
    if said not in OUTCOMES:
        raise RegistryError(f"{where}: outcome {said!r} is not one of {', '.join(OUTCOMES)}")
    return str(said)


def _crossing(entry: Any, where: str) -> tuple[str, tuple[str, ...], str, str]:
    """`outcome`, `rows`, `pact` and `why` of an entry that crosses or is lost.

    One that crosses says its PACT spelling; a loss has none and may say why.
    """
    if not isinstance(entry, Mapping):
        raise RegistryError(f"{where}: an entry is a mapping")
    outcome, rows = _outcome(entry, where), _rows(entry, where)
    pact, why = str(entry.get("pact") or ""), str(entry.get("why") or "")
    if outcome != "loss" and not pact:
        raise RegistryError(f"{where}: a name that crosses says its PACT spelling in `pact:`")
    if outcome == "loss" and (pact or entry.get("tool")):
        raise RegistryError(f"{where}: a loss has no PACT spelling")
    return outcome, rows, pact, why


def parse(document: Mapping[str, Any]) -> Registry:
    """A registry from its YAML document, refusing anything malformed."""
    fields: dict[str, FieldRow] = {}
    for key, entry in (document.get("fields") or {}).items():
        where = f"fields.{key}"
        if not isinstance(entry, Mapping) or not entry.get("construct"):
            raise RegistryError(f"{where}: every field names a `construct:`")
        fields[str(key)] = FieldRow(
            field=str(key),
            construct=str(entry["construct"]),
            outcome=_outcome(entry, where),
            rows=_rows(entry, where),
            how=str(entry.get("how") or ""),
            spec_file=str(entry.get("spec-file") or ""),
        )
    capabilities: dict[str, CapabilityRow] = {}
    for name, entry in (document.get("capabilities") or {}).items():
        outcome, rows, pact, why = _crossing(entry, f"capabilities.{name}")
        capabilities[str(name)] = CapabilityRow(
            name=str(name), outcome=outcome, rows=rows, pact=pact,
            tool=str(entry.get("tool") or ""), why=why,
        )
    names: dict[str, NameRow] = {}
    for name, entry in (document.get("names") or {}).items():
        where = f"names.{name}"
        if str(name).split(".", 1)[0] not in DOORS:
            raise RegistryError(f"{where}: a name starts with one of {', '.join(DOORS)}")
        outcome, rows, pact, why = _crossing(entry, where)
        names[str(name)] = NameRow(
            name=str(name), outcome=outcome, rows=rows, pact=pact, why=why,
            left=str(entry.get("left") or ""),
        )
    middleware = str(document.get("middleware") or "")
    if "{name}" not in middleware:
        raise RegistryError("`middleware:` is one sentence with a `{name}` in it")
    return Registry(
        pydantic_ai=str(document.get("pydantic-ai") or ""),
        fields=fields,
        capabilities=capabilities,
        middleware=" ".join(middleware.split()),
        names=names,
    )


@cache
def registry() -> Registry:
    """The shipped registry, read once per process."""
    return parse(yaml.safe_load(PATH.read_text(encoding="utf-8")))


# ─────────────────────────────────────────────────────────────── the page


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _settings_rows() -> list[tuple[str, str]]:
    """`settings:` keys and their `ModelSettings` names, from the transport's table.

    Read from `pydantic_ai_transport._SETTINGS`, the one authority for the
    twelve keys, rather than restated here. Imported only when a page is
    written, because that module imports Pydantic AI.
    """
    from .transports.pydantic_ai_transport import _SETTINGS

    return sorted(_SETTINGS.items())


def markdown(reg: Registry | None = None) -> str:
    """The registry as a page a person reads."""
    reg = reg or registry()
    out = [
        "# PACT to Pydantic AI mapping",
        "",
        f"*Generated by `pact-mapping` from `pact_adapters/pydantic_ai_registry.yaml` "
        f"(Pydantic AI {reg.pydantic_ai}). Do not edit by hand: change the registry and "
        "run `pact-mapping <this file>`.*",
        "",
        "Outcomes: **carried** (a Pydantic AI construct means the same thing), "
        "**mapped** (built by the adapter from Pydantic AI's public pieces), "
        "**loss** (Pydantic AI has nothing that means it; PACT or the host holds it). "
        "Row ids point at `docs/02-PACT-PYDANTIC-AI-PARITY.md` §2.",
    ]
    for kind in KINDS:
        out += ["", f"## `{kind}` fields", "", "| PACT field | Pydantic AI | Outcome | Rows | Note |",
                "|---|---|---|---|---|"]
        for key, row in sorted(reg.fields.items()):
            if key.split(".", 1)[0] != kind:
                continue
            note = row.how + (f" *Not in an `AgentSpec` file:* {row.spec_file}." if row.spec_file else "")
            out.append(
                f"| `{key.split('.', 1)[1]}:` | {_cell(row.construct)} | {row.outcome} | "
                f"{', '.join(row.rows)} | {_cell(note.strip())} |"
            )
    out += ["", "## `settings:` keys", "", "| PACT | `ModelSettings` |", "|---|---|"]
    out += [f"| `{pact}` | `{ours}` |" for pact, ours in _settings_rows()]
    out += ["", "## Capabilities", "", "| Pydantic AI | Outcome | Rows | PACT |", "|---|---|---|---|"]
    for name, row in sorted(reg.capabilities.items()):
        said = row.pact or row.why or "middleware (below)"
        out.append(f"| `{name}` | {row.outcome} | {', '.join(row.rows)} | {_cell(said)} |")
    out += ["", "**Middleware.** " + reg.middleware.format(name="<name>") + "."]
    out += ["", "## Other Pydantic AI names", "",
            "`spec.` is an `AgentSpec` file key, `agent.` a live `Agent` attribute, "
            "`settings.` a `ModelSettings` key outside the table above.", "",
            "| Pydantic AI | Outcome | Rows | PACT |", "|---|---|---|---|"]
    for name, row in reg.names.items():
        out.append(f"| `{name}` | {row.outcome} | {', '.join(row.rows)} | {_cell(row.pact or row.why)} |")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    """`pact-mapping PATH` writes the page; `--check` fails when it is stale."""
    parser = argparse.ArgumentParser(prog="pact-mapping", description=main.__doc__)
    parser.add_argument("path", type=Path, help="the page to write, e.g. docs/impl/MAPPING.md")
    parser.add_argument("--check", action="store_true", help="exit 1 if the page differs")
    args = parser.parse_args(argv)
    page = markdown()
    if args.check:
        current = args.path.read_text(encoding="utf-8") if args.path.exists() else ""
        if current != page:
            parser.exit(1, f"{args.path} is stale.\n  fix: pact-mapping {args.path}\n")
        return 0
    args.path.parent.mkdir(parents=True, exist_ok=True)
    args.path.write_text(page, encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
