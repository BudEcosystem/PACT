"""Run-time holes in an agent's words (02P §3.2 A1).

`{{run-inputs.<name>}}` and `{{remembers.<name>}}` in `instructions:` or
`description:` (and in a variant's `instructions:` or `says:`) are filled by the
host when a run starts; the model never fills them. They name the same two
addresses `bind:` already takes, so there is no new address grammar, and
`pact check` (`crates/pact-loader/src/holes.rs`) has already refused any hole
naming something the agent does not declare.

What a hole is, written once on this side and the same as the loader's scan:
`{{`, optional whitespace, a name made of ASCII letters, digits, `-`, `_` and
`.`, optional whitespace, `}}`, naming one of the two namespaces. Anything else
between double braces (a Handlebars helper such as `{{#each}}`, an example of
JSON, a name in neither namespace such as the `{{first_name}}` of a template the
model is asked to write) is text, and it reaches the model as text. The scan is
the loader's scan — leftmost `{{`, first `}}` after it, and on a non-name step
past the `{{` only — rather than a regular expression, because the two disagree
on inputs like `{{{run-inputs.x}}}` and a hole the checker never saw must not
be one the runtime fills.

One escape: a backslash before the braces. `\\{{run-inputs.brand}}` is the
author's own braces, never a hole, and `fill` sends it without the backslash.

Filling is strict: a hole with no value is an error, never an empty string and
never literal braces, because either would reach the model as something the
author did not write.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

#: The two namespaces a hole may name — the `bind:` addresses.
RUN_INPUTS = "run-inputs"
REMEMBERS = "remembers"

_NAME_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")


@dataclass(frozen=True)
class Hole:
    """One hole: `{{run-inputs.brand}}` is `Hole("run-inputs", "brand")`."""

    namespace: str
    name: str

    @property
    def address(self) -> str:
        """`run-inputs.brand` — the address as `bind:` writes it."""
        return f"{self.namespace}.{self.name}"


class Unfilled(KeyError):
    """A hole the run has no value for.

    A `KeyError` because it is one: the address is the missing key. The message
    names the hole and where the value comes from, so a host knows which input
    to pass.
    """

    def __init__(self, hole: Hole) -> None:
        self.hole = hole
        where = "run_inputs" if hole.namespace == RUN_INPUTS else "what the agent remembers"
        super().__init__(
            f"{{{{{hole.address}}}}} has no value for this run; pass {hole.name!r} in {where}"
        )

    def __str__(self) -> str:  # KeyError quotes its argument; this is a sentence.
        return str(self.args[0])


def _spans(text: str) -> list[tuple[int, int, Hole | None]]:
    """`(start, end, hole)` for every hole, and `(start, end, None)` for every
    escaped `\\{{` (from its backslash to the end of its braces), in order.

    The loader's scan, step for step (`holes.rs::scan`).
    """
    out: list[tuple[int, int, Hole | None]] = []
    at = 0
    while (open_ := text.find("{{", at)) != -1:
        if open_ > 0 and text[open_ - 1] == "\\":
            out.append((open_ - 1, open_ + 2, None))
            at = open_ + 2
            continue
        close = text.find("}}", open_ + 2)
        if close == -1:
            break
        inner = text[open_ + 2 : close].strip()
        if inner and all(c in _NAME_CHARS for c in inner):
            namespace, _, name = inner.partition(".")
            # A name in neither namespace is the author's own braces: text.
            if namespace in (RUN_INPUTS, REMEMBERS):
                out.append((open_, close + 2, Hole(namespace, name)))
            at = close + 2
        else:
            at = open_ + 2
    return out


def holes_in(text: str) -> tuple[Hole, ...]:
    """Every hole in `text`, in order, each once: what a run must have a value for."""
    seen: dict[Hole, None] = {}
    for _, _, hole in _spans(text):
        if hole is not None:
            seen.setdefault(hole, None)
    return tuple(seen)


def fill(
    text: str,
    *,
    run_inputs: Mapping[str, Any] | None = None,
    remembers: Mapping[str, Any] | None = None,
) -> str:
    """`text` with every hole replaced by its value, and every escaped `\\{{` as `{{`.

    Text goes in as written; any other value as JSON, so a list of examples
    reads as a list rather than as a Python repr. Raises `Unfilled` for a hole
    with no value, absent or `None`.
    """
    sources = {RUN_INPUTS: run_inputs or {}, REMEMBERS: remembers or {}}
    parts: list[str] = []
    at = 0
    for start, end, hole in _spans(text):
        parts.append(text[at:start])
        at = end
        if hole is None:
            parts.append("{{")
            continue
        value = sources[hole.namespace].get(hole.name)
        if value is None:
            raise Unfilled(hole)
        parts.append(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))
    parts.append(text[at:])
    return "".join(parts)
