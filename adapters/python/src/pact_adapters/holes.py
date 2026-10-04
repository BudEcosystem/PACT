"""Run-time holes in an agent's words (02P §3.2 A1).

`{{run-inputs.<name>}}` and `{{remembers.<name>}}` in `instructions:` or
`description:` are filled by the host when a run starts; the model never fills
them. They name the same two addresses `bind:` already takes, so there is no new
address grammar, and `pact check` (`crates/pact-loader/src/holes.rs`) has
already refused any hole naming something the agent does not declare.

What a hole is, written once on this side and the same as the loader's
`holes_in`: `{{`, optional whitespace, a name made of ASCII letters, digits,
`-`, `_` and `.`, optional whitespace, `}}`. Anything else between double braces
(a Handlebars helper such as `{{#each}}`, an example of JSON) is text, and it
reaches the model as text. The scan is the loader's scan — leftmost `{{`, first
`}}` after it, and on a non-name step past the `{{` only — rather than a regular
expression, because the two disagree on inputs like `{{{run-inputs.x}}}` and a
hole the checker never saw must not be one the runtime fills.

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


def _spans(text: str) -> list[tuple[int, int, str]]:
    """`(start, end, inner)` for every hole-shaped `{{name}}`, in order.

    The loader's scan, step for step (`holes.rs::holes_in`).
    """
    out: list[tuple[int, int, str]] = []
    at = 0
    while (open_ := text.find("{{", at)) != -1:
        close = text.find("}}", open_ + 2)
        if close == -1:
            break
        inner = text[open_ + 2 : close].strip()
        if inner and all(c in _NAME_CHARS for c in inner):
            out.append((open_, close + 2, inner))
            at = close + 2
        else:
            at = open_ + 2
    return out


def _hole(inner: str) -> Hole:
    namespace, _, name = inner.partition(".")
    return Hole(namespace, name)


def holes_in(text: str) -> tuple[Hole, ...]:
    """Every hole in `text`, in order, each once.

    A name in neither namespace (`{{brand}}`) is returned too, with its
    namespace as written: the loader refuses those, so seeing one here means the
    document did not come through `pact check`.
    """
    seen: dict[Hole, None] = {}
    for _, _, inner in _spans(text):
        seen.setdefault(_hole(inner), None)
    return tuple(seen)


def fill(
    text: str,
    *,
    run_inputs: Mapping[str, Any] | None = None,
    remembers: Mapping[str, Any] | None = None,
) -> str:
    """`text` with every hole replaced by its value.

    Text goes in as written; any other value as JSON, so a list of examples
    reads as a list rather than as a Python repr. Raises `Unfilled` for a hole
    with no value — absent or `None` — including one naming a namespace other
    than the two (which the loader refuses).
    """
    sources = {RUN_INPUTS: run_inputs or {}, REMEMBERS: remembers or {}}
    parts: list[str] = []
    at = 0
    for start, end, inner in _spans(text):
        hole = _hole(inner)
        values = sources.get(hole.namespace)
        value = None if values is None else values.get(hole.name)
        if value is None:
            raise Unfilled(hole)
        parts.append(text[at:start])
        parts.append(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))
        at = end
    parts.append(text[at:])
    return "".join(parts)
