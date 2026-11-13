"""Which implementation does the work of an interface (96 §C; `chosen-by:`).

An agent writes `uses: [email]`. `email` is an interface (`interface: yes`):
a contract with no way to reach anything. `gmail` and `outlook` say
`implements: email`. The loader writes the contract into each of them, so every
check reads them in full — and then stops, because WHICH one runs is decided
for each run and is the runtime's to do, by the interface's own `chosen-by:`:

* `run-inputs.<name>` — a run input of the agent, written `one of` the names
  that implement it. Whoever starts the run says which.
* `the-host` — what an interface with no `chosen-by:` has. Whatever runs the
  agents picks, for each person, from the accounts they connected.

Only something that says `implements:` it can ever be picked, whoever picks.

Nothing in this package read `chosen-by:`. An agent that looks things up in an
interface was handed the interface itself — a set with no documents — and
looked things up in nothing, and every host worked the rule above out again for
itself. This is the one reading of it. It decides nothing a host has to decide:
it says what was chosen and why, or says in a sentence that nothing was, so the
run can refuse or report it rather than carry on with a contract nobody fills.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .yes_no import said_yes

__all__ = ["Choice", "chosen", "KINDS"]

#: The collections an interface can be in.
KINDS = ("tools", "skills", "knowledge")
THE_HOST = "the-host"


@dataclass(frozen=True)
class Choice:
    """One interface an agent uses, and what does its work in this run."""

    #: `tools`, `skills` or `knowledge`.
    kind: str
    #: The interface, as the agent's `uses:` names it.
    interface: str
    #: Everything that says `implements:` it, in name order.
    implementations: tuple[str, ...]
    #: `run-inputs.<name>` or `the-host`.
    chosen_by: str
    #: The implementation picked — `""` when none was.
    picked: str = ""
    #: Why none was, in a sentence for `unenforced` or a refusal — `""` when one was.
    why_not: str = ""


def _entries(document: Mapping[str, Any], kind: str) -> Mapping[str, Any]:
    found = document.get(kind)
    return found if isinstance(found, Mapping) else {}


def chosen(
    document: Mapping[str, Any],
    agent: str,
    run_inputs: "Mapping[str, Any] | None" = None,
    picked_by_the_host: "Mapping[str, str] | None" = None,
) -> tuple[Choice, ...]:
    """For each interface `agent` uses: what does its work, or why nothing does.

    `run_inputs` are the run's own. `picked_by_the_host` is `{interface: its
    implementation}`, for the interfaces a host chooses — it is consulted for a
    `run-inputs.<name>` interface as well, AFTER the run input, so a host that
    binds for a run that did not say is still heard. A pick that does not
    `implement:` the interface is never accepted, from either.
    """
    spec = _entries(document, "agents").get(agent)
    uses = [str(u) for u in (spec.get("uses") or ())] if isinstance(spec, Mapping) else []
    given = dict(run_inputs or {})
    host = dict(picked_by_the_host or {})
    out: list[Choice] = []
    for kind in KINDS:
        entries = _entries(document, kind)
        for name in uses:
            entry = entries.get(name)
            if not isinstance(entry, Mapping) or not said_yes(entry.get("interface")):
                continue
            able = tuple(sorted(
                str(k) for k, v in entries.items()
                if isinstance(v, Mapping) and str(v.get("implements") or "") == name
            ))
            by = str(entry.get("chosen-by") or THE_HOST).strip()
            asked: list[tuple[str, str]] = []  # (who said, what they said)
            if by.startswith("run-inputs."):
                field = by.removeprefix("run-inputs.")
                if str(given.get(field) or "").strip():
                    asked.append((f"the run input `{field}`", str(given[field]).strip()))
            if str(host.get(name) or "").strip():
                asked.append(("the host", str(host[name]).strip()))
            picked, why = "", ""
            for who, said in asked:
                if said in able:
                    picked = said
                    break
                why = (
                    f"{kind}: {name} is an interface, and {who} picked '{said}', which does "
                    f"not say `implements: {name}` — only {_listed(able)} can do its work"
                )
            if not picked and not why:
                wanted = (
                    f"the run input `{by.removeprefix('run-inputs.')}` was not given"
                    if by.startswith("run-inputs.")
                    else "it is the host's to pick (`chosen-by: the-host`) and the host picked nothing"
                )
                why = (
                    f"{kind}: {name} is an interface, and nothing was chosen to do its work — "
                    f"{wanted}. It can be {_listed(able)}"
                )
            out.append(Choice(kind, name, able, by, picked, "" if picked else why))
    return tuple(out)


def _listed(names: "tuple[str, ...]") -> str:
    if not names:
        return "nothing: no entry says `implements:` it"
    return ", ".join(f"`{n}`" for n in names[:-1]) + (" or " if len(names) > 1 else "") + f"`{names[-1]}`"
