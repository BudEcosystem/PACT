"""`needs.accept-when:` — which models an agent will accept, figure by figure (96 §B4).

    needs:
      accept-when:
        - mmlu.score > 50
        - terminal-bench.score >= 40
        - refund-tone.score >= 0.8
        - pass-rate >= 90%
        - cost < 0.05 USD

One comparison per line, and every line has to hold. This module is the ONE
copy of what a line means — read by the reference resolver here and by any
runtime that binds models (Bud Agent Flow's catalogue and its `choose-model`),
so a line is never decided two ways. `crates/pact-loader/src/accept.rs` refuses
what this cannot read, and `spec/accept-when.yaml` holds the two to one table.

## What a line may name, and when it is known

| Measure | Unit | Known |
|---|---|---|
| a benchmark the catalogue declares (`mmlu`, `terminal-bench`, …) | its `scale:` — `percent` (out of 100) or `fraction` | before anything runs: the row's `benchmarks:` |
| a metric of the suite, by its `name:` (`refund-tone`) — `.score` (mean) or `.pass-rate` | fraction | after the candidate has run the suite |
| `pass-rate` | fraction | after |
| `cost` — money spent per case, on average | money | after |
| `input-price`, `output-price` — per million tokens | money | before: the row's `cost:` |
| `context-window` | size | before |
| `first-words-within` | duration | before: the row's `speed:` |

A figure nobody recorded does not hold: a model with no `mmlu` score is not
accepted by `mmlu.score > 50`, an unpriced one by `input-price < 3 USD`, one
whose cost was never metered by `cost < 0.05 USD`. Each says why, so the
author can record the figure (`benchmarks.record`) rather than guess.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "AFTER",
    "BEFORE",
    "Line",
    "Unreadable",
    "benchmarks_of",
    "held_after",
    "held_before",
    "measured",
    "parse",
    "parse_all",
]

#: The figures every model has, and the unit each is written in.
BEFORE: dict[str, str] = {
    "input-price": "money",
    "output-price": "money",
    "context-window": "size",
    "first-words-within": "duration",
}
AFTER: dict[str, str] = {"pass-rate": "fraction", "cost": "money"}

_OPS = (">=", "<=", "==", ">", "<", "=")
_LINE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9 _.()+-]*?)\s*(>=|<=|==|>|<|=)\s*(.+?)\s*$")


class Unreadable(ValueError):
    """A line that is not a comparison this format can decide, and why."""


@dataclass(frozen=True)
class Line:
    """One `accept-when:` line, read."""

    written: str
    #: The canonical name — a benchmark's own key, a metric's `name:`, or one
    #: of `BEFORE`/`AFTER`.
    measure: str
    #: `benchmark`, `metric` or `figure`.
    kind: str
    #: `score` or `pass-rate` for a metric; `score` for a benchmark; `""` else.
    part: str
    op: str
    #: In the measure's own unit: points for a `percent` benchmark, 0–1 for a
    #: fraction, USD, tokens, or seconds.
    value: float
    unit: str

    @property
    def before(self) -> bool:
        """Known from the catalogue alone, so it narrows candidates for free."""
        return self.kind == "benchmark" or self.measure in BEFORE

    def holds(self, have: float) -> bool:
        from .resolve import _HOLDS

        return _HOLDS["=" if self.op == "==" else self.op](have, self.value)


def benchmarks_of(document: Mapping[str, Any] | None = None) -> dict[str, tuple[str, str]]:
    """Every benchmark name and alias, lower-cased, to `(its key, its scale)`.

    The distribution's catalogue first, then the workspace's own `benchmarks:`
    over it — the same layering `resolve.load_catalogue` uses for rows.
    """
    import yaml

    from .resolve import BUILTIN_CATALOGUE

    out: dict[str, tuple[str, str]] = {}
    layers = [yaml.safe_load(Path(BUILTIN_CATALOGUE).read_text(encoding="utf-8")) or {}]
    if document:
        layers.append(document.get("models") or {})
    for layer in layers:
        for key, entry in ((layer or {}).get("benchmarks") or {}).items():
            entry = entry if isinstance(entry, Mapping) else {}
            scale = str(entry.get("scale") or "percent").strip()
            for name in [key, *(entry.get("also-known-as") or [])]:
                out[str(name).strip().lower()] = (str(key), scale)
    return out


def metric_names(document: Mapping[str, Any]) -> set[str]:
    """The names a suite's `metrics:` are called by, lower-cased."""
    from .providers import MetricSpec

    metrics = ((document.get("evals") or {}).get("metrics") or []) if document else []
    return {MetricSpec.parse(m).name for m in metrics if MetricSpec.parse(m).name}


def _number(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise Unreadable(f"`{text}` is not a figure") from None
    if not math.isfinite(value):
        raise Unreadable(f"`{text}` is not a figure")
    return value


def _value(text: str, unit: str) -> float:
    text = text.strip()
    if unit == "percent":
        return _number(text.removesuffix("%").strip())
    if unit == "fraction":
        if text.endswith("%"):
            return _number(text[:-1].strip()) / 100.0
        value = _number(text)
        if value > 1:
            raise Unreadable(
                f"a share is out of one, so `{text}` cannot be one: write `{text}%` or "
                f"`{value / 100:g}`"
            )
        return value
    if unit == "money":
        parts = text.split()
        if len(parts) != 2:
            raise Unreadable(f"`{text}` is an amount with no currency: write it like `0.05 USD`")
        amount, currency = parts
        if currency.upper() != "USD":
            raise Unreadable(
                f"the catalogue prices every model in USD, so `{text}` cannot be compared with "
                f"one: write it in USD"
            )
        return _number(amount)
    if unit == "size":
        from .resolve import _tokens

        size = _tokens(text)
        if size is None:
            raise Unreadable(f"`{text}` is not a size: write it like `32k` or `128000`")
        return float(size)
    if unit == "duration":
        from .limits import seconds

        try:
            found = seconds(text)
        except (TypeError, ValueError):
            found = None
        if found is None:
            raise Unreadable(f"`{text}` is not a length of time: write it like `500ms` or `2s`")
        return float(found)
    raise Unreadable(f"no unit called {unit!r}")  # pragma: no cover - a bug here


def parse(
    written: str,
    *,
    benchmarks: Mapping[str, tuple[str, str]],
    metrics: "set[str] | frozenset[str]" = frozenset(),
) -> Line:
    """One line, or `Unreadable` saying why it is not one."""
    found = _LINE.match(str(written))
    if found is None:
        raise Unreadable(
            f"`{written}` is not a comparison: write a name, then `>`, `>=`, `<`, `<=` or `=`, "
            f"then a figure — `mmlu.score > 50`"
        )
    name, op, rest = found.group(1).strip(), found.group(2), found.group(3)
    head, _, part = name.lower().partition(".")
    if head in BEFORE or head in AFTER:
        if part:
            raise Unreadable(f"`{head}` is one figure and has no `.{part}`")
        unit = {**BEFORE, **AFTER}[head]
        return Line(written, head, "figure", "", op, _value(rest, unit), unit)
    whole = name.lower()
    if whole in benchmarks or head in benchmarks:
        key, scale = benchmarks.get(whole) or benchmarks[head]
        part = "" if whole in benchmarks else part
        if part not in ("", "score"):
            raise Unreadable(f"a benchmark has a `.score` and nothing else, so not `.{part}`")
        return Line(written, key, "benchmark", "score", op, _value(rest, scale), scale)
    if head in metrics:
        part = part or "score"
        if part not in ("score", "pass-rate"):
            raise Unreadable(
                f"a metric has a `.score` (its mean) and a `.pass-rate`, so not `.{part}`"
            )
        return Line(written, head, "metric", part, op, _value(rest, "fraction"), "fraction")
    raise Unreadable(
        f"nothing is called `{head}`: name a benchmark the catalogue declares, a metric of "
        f"your suite by its `name:`, or one of {', '.join(sorted({**BEFORE, **AFTER}))}"
    )


def parse_all(document: Mapping[str, Any], written: Sequence[Any]) -> tuple[list[Line], list[str]]:
    """Every line an agent wrote: the ones read, and why each other one was not."""
    benchmarks, metrics = benchmarks_of(document), metric_names(document)
    lines, unreadable = [], []
    for raw in written or ():
        try:
            lines.append(parse(str(raw), benchmarks=benchmarks, metrics=metrics))
        except Unreadable as why:
            unreadable.append(f"`accept-when: {raw}` — {why}")
    return lines, unreadable


def held_before(line: Line, entry: Any) -> "tuple[bool, str]":
    """Whether a catalogue row reaches one line known before anything runs."""
    if line.kind == "benchmark":
        have = (entry.scores or {}).get(line.measure)
        noun = f"no recorded {line.measure} score"
    elif line.measure == "input-price":
        have = None if entry.cost is None else entry.cost * 1000.0
        noun = "no published input price"
    elif line.measure == "output-price":
        have = None if entry.output_cost is None else entry.output_cost * 1000.0
        noun = "no published output price"
    elif line.measure == "context-window":
        have = entry.context_window
        noun = "no recorded context window"
    elif line.measure == "first-words-within":
        have = None if entry.first_words_ms is None else entry.first_words_ms / 1000.0
        noun = "no recorded speed"
    else:
        return True, ""
    if have is None:
        return False, f"has {noun}, so `{line.written}` cannot be shown to hold"
    if line.holds(float(have)):
        return True, ""
    return False, f"has {line.measure} {have:g}, so `{line.written}` does not hold"


def measured(outcomes: Sequence[Any], spent: "Sequence[float | None]" = ()) -> dict[str, float]:
    """What a candidate scored and spent on the suite: the figures `AFTER` lines read.

    `pass-rate` over every case; each metric's `score` (its mean) and
    `pass-rate` over the cases it was taken on — a case that failed earlier is
    not scored again, so its count is `<name>.cases`; `cost` the mean over the
    cases whose spend was metered, absent when none was.
    """
    out: dict[str, float] = {}
    if outcomes:
        out["pass-rate"] = sum(1 for o in outcomes if o.passed) / len(outcomes)
    per: dict[str, list[float]] = {}
    for o in outcomes:
        for name, score in (getattr(o, "scores", None) or {}).items():
            per.setdefault(name, []).append(float(score))
    for name, scores in per.items():
        out[f"{name}.score"] = sum(scores) / len(scores)
        out[f"{name}.cases"] = float(len(scores))
    metered = [s for s in spent if s is not None]
    if metered:
        out["cost"] = sum(metered) / len(metered)
    return out


def held_after(line: Line, figures: Mapping[str, float], thresholds: Mapping[str, float] | None = None, outcomes: Sequence[Any] = ()) -> "tuple[bool, str]":
    """Whether what a candidate scored and spent on the suite reaches one line."""
    if line.before:
        return True, ""
    if line.kind == "metric" and line.part == "pass-rate":
        bar = (thresholds or {}).get(line.measure)
        taken = [o.scores[line.measure] for o in outcomes if line.measure in (getattr(o, "scores", None) or {})]
        have = None if bar is None or not taken else sum(1 for s in taken if s >= bar) / len(taken)
    else:
        key = f"{line.measure}.score" if line.kind == "metric" else line.measure
        have = figures.get(key)
    if have is None:
        what = "was never metered" if line.measure == "cost" else "was never taken"
        return False, f"`{line.measure}` {what} on these cases, so `{line.written}` cannot be shown to hold"
    if line.holds(float(have)):
        return True, ""
    return False, f"scored {have:g} on {line.measure}, so `{line.written}` does not hold"
