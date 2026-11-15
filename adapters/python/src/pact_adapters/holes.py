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
from decimal import Decimal
from collections.abc import Callable, Iterator, Mapping
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


def _scan(text: str) -> Iterator[tuple[int, int, "str | None"]]:
    """The loader's scan, step for step (`holes.rs::scan`), and the one scan here.

    Yields `(start, end, name)` for every `{{name}}` (a name of the characters a hole's
    name may hold, in either namespace or none), `(start, end, None)` for every escaped
    `\\{{` (from its backslash to the end of its braces), and `(start, end, "")` for a
    `{{...}}` whose inside is no name (a Handlebars helper, a JSON example), past whose
    `{{` only the scan goes on, as the loader's does.
    """
    at = 0
    while (open_ := text.find("{{", at)) != -1:
        if open_ > 0 and text[open_ - 1] == "\\":
            yield open_ - 1, open_ + 2, None
            at = open_ + 2
            continue
        close = text.find("}}", open_ + 2)
        if close == -1:
            return
        inner = text[open_ + 2 : close].strip()
        if inner and all(c in _NAME_CHARS for c in inner):
            yield open_, close + 2, inner
            at = close + 2
        else:
            yield open_, close + 2, ""
            at = open_ + 2


def _hole(name: str) -> "Hole | None":
    namespace, _, rest = name.partition(".")
    # A name in neither namespace is the author's own braces: text.
    return Hole(namespace, rest) if namespace in (RUN_INPUTS, REMEMBERS) else None


def _spans(text: str) -> list[tuple[int, int, Hole | None]]:
    """`(start, end, hole)` for every hole, and `(start, end, None)` for every
    escaped `\\{{`, in order (`_scan`)."""
    out: list[tuple[int, int, Hole | None]] = []
    for start, end, name in _scan(text):
        if name is None:
            out.append((start, end, None))
        elif name and (hole := _hole(name)) is not None:
            out.append((start, end, hole))
    return out


def rewritten(text: str, swap: "Callable[[str], str | None]") -> str:
    """`text` with each `{{<name>}}` (a name of the characters a hole's name may hold, in
    either namespace or none) replaced by `swap(name)`, or left as written when it gives
    `None`; an escaped `\\{{` is left as written. The scan is the loader's (`_scan`), so a
    template whose braces cross the two dialects (`{{brand}}` in a Pydantic AI spec,
    `{{run-inputs.brand}}` in PACT) is rewritten exactly where a hole would be read."""
    parts: list[str] = []
    at = 0
    for start, end, name in _scan(text):
        if name and (said := swap(name)) is not None:
            parts.append(text[at:start] + said)
            at = end
    parts.append(text[at:])
    return "".join(parts)


def templates_in(text: str) -> tuple[str, ...]:
    """Every `{{...}}` in `text` that is neither a hole nor escaped, as written, in order, each
    once: braces a template language would fill, which reach a PACT model as text."""
    found = (text[start:end] for start, end, name in _scan(text) if name == "" or (name and not _hole(name)))
    return tuple(dict.fromkeys(found))


def holes_in(text: str) -> tuple[Hole, ...]:
    """Every hole in `text`, in order, each once: what a run must have a value for."""
    seen: dict[Hole, None] = {}
    for _, _, hole in _spans(text):
        if hole is not None:
            seen.setdefault(hole, None)
    return tuple(seen)


#: 96 §C. The filters and tests `template-language: jinja` may use: the ones
#: Jinja2 and MiniJinja both ship with one meaning. The SAME two lists as
#: `crates/pact-loader/src/jinja.rs`, which refuses anything else at check time;
#: `tests/test_a_template_is_rendered_as_it_was_checked.py` holds them equal.
JINJA_FILTERS: frozenset[str] = frozenset({
    "abs", "capitalize", "count", "d", "default", "first", "float", "indent", "int",
    "items", "join", "last", "length", "list", "lower", "max", "min", "replace",
    "reverse", "round", "sort", "string", "sum", "title", "trim", "unique", "upper",
})
JINJA_TESTS: frozenset[str] = frozenset({
    "defined", "undefined", "none", "number", "string", "sequence", "mapping", "even", "odd",
})


def _template_names(values: Mapping[str, Any]) -> dict[str, Any]:
    """`brand-voice` as a template writes it: `brand_voice`."""
    return {str(k).replace("-", "_"): v for k, v in (values or {}).items()}


def number_text(number: float) -> str:
    """A finite number as ECMAScript's `Number::toString` writes it, as `fill.rs::number_text`
    does: the shortest digits that read back the same; positional from 1e-6 up to (not
    including) 1e21, with no fraction when there is none (`2`, not `2.0`); otherwise
    `<d>[.<digits>]e<sign><exp>`. A runtime in TypeScript holds no `2.0` apart from `2`, so
    the shared rule is the one it can keep."""
    if isinstance(number, int):
        return str(number)
    if number == 0:
        return "0"
    sign, digits_tuple, exponent = Decimal(repr(number)).normalize().as_tuple()
    digits = "".join(map(str, digits_tuple))
    k = len(digits)
    n = k + int(exponent)  # 10^(n-1) <= |number| < 10^n
    minus = "-" if sign else ""
    if k <= n <= 21:
        return f"{minus}{digits}{'0' * (n - k)}"
    if 0 < n <= 21:
        return f"{minus}{digits[:n]}.{digits[n:]}"
    if -6 < n <= 0:
        return f"{minus}0.{'0' * -n}{digits}"
    mantissa = f"{digits[0]}.{digits[1:]}" if k > 1 else digits
    return f"{minus}{mantissa}e{'-' if n - 1 < 0 else '+'}{abs(n - 1)}"


def json_text(value: Any) -> str:
    """`value` as JSON the way every port writes it into words (`fill.rs::json_text`): `, `
    between items, `: ` after a key, non-ASCII kept, and a number by `number_text`."""
    if value is None or isinstance(value, (bool, str)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float)):
        return number_text(value)
    if isinstance(value, Mapping):
        return "{" + ", ".join(f"{json.dumps(str(k), ensure_ascii=False)}: {json_text(v)}" for k, v in value.items()) + "}"
    return "[" + ", ".join(json_text(item) for item in value) + "]"


def _said(value: Any) -> Any:
    """What `{{ ... }}` prints, as a hole's value goes in: text as written, anything else
    as JSON (`json_text`), so `true`, `null`, `5` and a list read the same from every port
    (Jinja2 alone prints `True`, `None`, `5.0` and a Python list).
    An undefined value is handed back as it is, so printing it is still the error."""
    from jinja2 import Undefined

    if isinstance(value, (str, Undefined)):
        return value
    return json_text(value)


def _render_jinja(text: str, run_inputs: Mapping[str, Any], remembers: Mapping[str, Any]) -> str:
    """One authored template, rendered once, in the sandbox, from data.

    `SandboxedEnvironment` with no globals and only the shared filters and
    tests, so a template can reach nothing `pact check` did not allow; what it prints
    follows `_said`;
    `StrictUndefined`, so a value the run was not given is an error and never an
    empty string; no autoescape, because these are words for a model, not HTML.
    What is inserted is never rendered again — a customer who typed `{{ 7*7 }}`
    is quoted, not obeyed.
    """
    try:
        from jinja2 import StrictUndefined, TemplateError, UndefinedError
        from jinja2.sandbox import SandboxedEnvironment
    except ImportError as missing:  # pragma: no cover - depends on the machine
        raise ImportError(
            "this workspace says `template-language: jinja`, and Jinja2 is not installed "
            "here. fix: `pip install jinja2`, or write `template-language: holes`."
        ) from missing

    env = SandboxedEnvironment(
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
        finalize=_said,
    )
    env.globals.clear()
    env.filters = {k: v for k, v in env.filters.items() if k in JINJA_FILTERS}
    env.tests = {k: v for k, v in env.tests.items() if k in JINJA_TESTS}
    try:
        return env.from_string(text).render(
            run_inputs=_template_names(run_inputs), remembers=_template_names(remembers)
        )
    except UndefinedError as missing:
        raise Unfilled(Hole(RUN_INPUTS, str(missing))) from missing
    except TemplateError as broken:  # pragma: no cover - `pact check` refuses these first
        raise ValueError(f"this template cannot be rendered: {broken}") from broken


def fill(
    text: str,
    *,
    run_inputs: Mapping[str, Any] | None = None,
    remembers: Mapping[str, Any] | None = None,
    language: str = "holes",
) -> str:
    """`text` with every hole replaced by its value, and every escaped `\\{{` as `{{`.

    Text goes in as written; any other value as JSON (`json_text`), so a list
    of examples reads as a list rather than as a Python repr. Raises `Unfilled` for a hole
    with no value, absent or `None`.

    `language="jinja"` (the workspace's `template-language:`, 96 §C) renders
    `text` as a template instead, through `_render_jinja`.
    """
    if language == "jinja":
        return _render_jinja(text, run_inputs or {}, remembers or {})
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
        parts.append(value if isinstance(value, str) else json_text(value))
    parts.append(text[at:])
    return "".join(parts)
