"""The four ready-made checks a rule names with `library:` (02W §2.13).

Each holds an answer to what the run was given and what its tools returned —
the SOURCE — and each is decided by looking, never by a model: they sit in the
deterministic band beside `must-contain:` (AC-4.5), so a suite written with
them is still decided air-gapped.

The source is everything the run had in front of it: what it was asked
(`RunResult.asked`), the values it was given (`RunResult.given`: a workflow
stage's bound inputs, an eval case's `with:`), every tool result of every step,
and anything it retrieved. An answer is read as the VALUE it is when its text is
JSON (a structured answer), since in JSON every string wears quotation marks and
a field's name is what says it holds a citation.

- **`numbers-come-from-the-source`**: every number the answer states is one the
  source states. `450.00` is `450`, `1,200` is `1200`; a number written into a
  word (`ICD10`, `10m`) is a name, not a figure, and a field whose name says
  `confidence` is the answer's own word on how sure it is, never a figure it
  read (02W §5.2's reader answers `lowest-confidence:` beside the invoice it
  read, and is held to its invoice's numbers). A total the run worked out
  itself is not in the source, and this check says so: write it as a program
  call's answer, which is in the source, or check it with a `program:`.
- **`quotes-are-word-for-word`**: every quoted passage is in the source exactly
  so, ignoring case, runs of spaces and a closing full stop. A quoted passage is
  text between double quotation marks (straight, curly, or « »), or the whole of
  a string under a field whose name says `quote`.
- **`cites-its-sources`**: the answer cites at least one thing, and everything
  it cites is in the source. A citation is a web address, a reference in square
  brackets, or the whole of a string under a field whose name begins `cite`,
  `citation`, `source` or `reference`.
- **`only-goes-up`**: no number the run was given comes back lower under the
  same name — a version, a running total, a best score carried round a repeat.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Iterator, Mapping, Sequence

#: The four, in the order `spec/schema.yaml` lists them.
LIBRARY = (
    "numbers-come-from-the-source",
    "quotes-are-word-for-word",
    "cites-its-sources",
    "only-goes-up",
)

#: A figure: digits, with `.` or `,` between groups, not written into a word.
_NUMBER = re.compile(r"(?<![A-Za-z_\d])\d+(?:[.,]\d+)*(?![A-Za-z_\d])")
#: Thousands written with commas: `1,200`, `12,000,000.50`.
_THOUSANDS = re.compile(r"^\d{1,3}(?:,\d{3})+(?:\.\d+)?$")
_QUOTED = re.compile(r'"([^"]+)"|“([^”]+)”|«([^»]+)»')
_URL = re.compile(r"https?://[^\s\"'<>\])]+")
_BRACKETED = re.compile(r"\[([^\[\]]+)\]")
_CITES = ("cite", "citation", "source", "reference")


def broken(
    name: str,
    output: str,
    *,
    asked: str = "",
    given: Mapping[str, Any] | None = None,
    returned: Sequence[str] = (),
) -> str:
    """Why `output` breaks the ready-made check `name`, or `""` if it does not."""
    given = dict(given or {})
    answer = _value(output)
    source = " \n ".join([asked, *(str(r) for r in returned), *_strings(given)])
    if name == "numbers-come-from-the-source":
        known = _figures(source) | {_figure(str(n)) for n in _numbers_in(given)}
        stray = [n for n in _numbers_said(answer) if _figure(n) not in known]
        return f"states {stray[0]}, which nothing it was given or read says" if stray else ""
    if name == "quotes-are-word-for-word":
        said = _plain(source)
        for quote in _quotes(answer):
            if _plain(quote) not in said:
                return f"quotes {quote!r}, which is not word for word in anything it was given or read"
        return ""
    if name == "cites-its-sources":
        cited = list(_citations(answer))
        if not cited:
            return "cites nothing"
        said = _plain(source)
        for cite in cited:
            if _plain(cite) not in said:
                return f"cites {cite!r}, which is nothing it was given or read"
        return ""
    if name == "only-goes-up":
        before = dict(_named_numbers(given))
        for key, now in _named_numbers(answer):
            was = before.get(key)
            if was is not None and now < was:
                return f"gives {key} as {_shown(now)}, lower than the {_shown(was)} it was given"
        return ""
    return f"`library: {name}` is not one of the ready-made checks ({', '.join(LIBRARY)})"


def _value(output: str) -> Any:
    """The answer as a value when its text is JSON, else the text itself."""
    text = output.strip()
    if text[:1] in "{[":
        try:
            return json.loads(text)
        except ValueError:
            pass
    return output


def _walk(value: Any, key: str = "") -> Iterator[tuple[str, Any]]:
    """Every leaf of a value, with the name of the field it is under."""
    if isinstance(value, Mapping):
        for k, v in value.items():
            yield from _walk(v, str(k))
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _walk(v, key)
    else:
        yield key, value


def _strings(value: Any) -> list[str]:
    return [str(v) for _, v in _walk(value) if v is not None and not isinstance(v, bool)]


def _numbers_in(value: Any) -> list[Any]:
    return [v for _, v in _walk(value) if isinstance(v, (int, float)) and not isinstance(v, bool)]


def _numbers_said(answer: Any) -> list[str]:
    """Every figure the answer states: its numbers, and the figures in its words."""
    if isinstance(answer, str):
        return _NUMBER.findall(answer)
    out: list[str] = []
    for key, v in _walk(answer):
        if isinstance(v, bool) or v is None or "confidence" in key.lower():
            continue
        out += [str(v)] if isinstance(v, (int, float)) else _NUMBER.findall(str(v))
    return out


def _figure(written: str) -> Decimal | str:
    """One figure as a number, so `450.00` and `450` are one figure."""
    text = written.replace(",", "") if _THOUSANDS.match(written) else written
    try:
        return Decimal(text).normalize()
    except InvalidOperation:
        return written


def _figures(text: str) -> set[Decimal | str]:
    out: set[Decimal | str] = set()
    for found in _NUMBER.findall(text):
        out.add(_figure(found))
        if not _THOUSANDS.match(found):  # `1,5` is two figures where it is not thousands
            out |= {_figure(p) for p in re.split(r",", found) if p}
    return out


def _plain(text: str) -> str:
    """Text compared word for word: case, runs of spaces, curly quotes and a final stop aside."""
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return " ".join(text.lower().split()).strip().rstrip(".")


def _quotes(answer: Any) -> Iterator[str]:
    for key, v in _walk(answer) if not isinstance(answer, str) else [("", answer)]:
        if not isinstance(v, str):
            continue
        if "quote" in key.lower():
            yield v
            continue
        for match in _QUOTED.finditer(v):
            yield next(g for g in match.groups() if g)


def _citations(answer: Any) -> Iterator[str]:
    for key, v in _walk(answer) if not isinstance(answer, str) else [("", answer)]:
        if not isinstance(v, str) or not v.strip():
            continue
        if key.lower().startswith(_CITES):
            yield v
            continue
        yield from _URL.findall(v)
        yield from _BRACKETED.findall(v)


def _named_numbers(value: Any) -> Iterator[tuple[str, float]]:
    if isinstance(value, str):
        return
    for key, v in _walk(value):
        if key and isinstance(v, (int, float)) and not isinstance(v, bool):
            yield key, float(v)


def _shown(n: float) -> str:
    return str(int(n)) if n == int(n) else str(n)
