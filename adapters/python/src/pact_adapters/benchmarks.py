"""Named benchmarks: where a model's `mmlu` or `terminal-bench` figure comes from (96 §B4).

An agent's `needs.accept-when: - mmlu.score > 50` is decided against the score
a catalogue row records under `benchmarks:`. This module is the one way such a
score gets there, and it always arrives with where it came from:

* `record` writes a figure somebody measured or read — a Terminal-Bench run
  on their own harness, a leaderboard — into the workspace's
  `models/catalog.yaml`, with `provenance:` saying so. That is the path for
  every `runs: host:<name>` benchmark, and for a published figure of any.
* `run_deepeval` measures one of the benchmarks DeepEval ships
  (`runs: deepeval:MMLU`) against a model, asked through the same
  `(system, user) -> answer` seam a `graded-by:` judge uses, and answers the
  figure on the benchmark's own scale.

PACT runs nothing on its own: a runtime that serves models (Bud Agent Flow's
`budflow benchmark`) calls these. And nothing is fetched by this module — a
DeepEval benchmark downloads its own dataset, which is that library's act and
says so when it cannot.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .providers import AskModel
from .selection import benchmarks_of

__all__ = ["Benchmark", "Unrecordable", "known", "record", "run_deepeval"]


class Unrecordable(ValueError):
    """A figure that cannot be written down as it stands, and why."""


@dataclass(frozen=True)
class Benchmark:
    """One entry of a catalogue's `benchmarks:`."""

    name: str
    description: str = ""
    scale: str = "percent"
    runs: str = ""
    with_: Mapping[str, Any] | None = None

    @property
    def runner(self) -> str:
        """`deepeval`, `host`, or `""` for a benchmark whose figures are only published."""
        return self.runs.split(":", 1)[0].strip() if ":" in self.runs else ""


def known(document: Mapping[str, Any] | None = None) -> dict[str, Benchmark]:
    """Every benchmark the distribution's catalogue and the workspace's own declare."""
    from .resolve import BUILTIN_CATALOGUE

    out: dict[str, Benchmark] = {}
    layers = [yaml.safe_load(Path(BUILTIN_CATALOGUE).read_text(encoding="utf-8")) or {}]
    if document:
        layers.append(document.get("models") or {})
    for layer in layers:
        for key, entry in ((layer or {}).get("benchmarks") or {}).items():
            entry = entry if isinstance(entry, Mapping) else {}
            out[str(key)] = Benchmark(
                name=str(key),
                description=str(entry.get("description") or ""),
                scale=str(entry.get("scale") or "percent"),
                runs=str(entry.get("runs") or ""),
                with_=dict(entry.get("with") or {}),
            )
    return out


def record(
    workspace: Path,
    model: str,
    benchmark: str,
    value: float,
    *,
    source: str,
    harness: str = "",
    recorded_by: str = "",
    as_of: "_dt.date | None" = None,
    document: Mapping[str, Any] | None = None,
) -> Path:
    """Write one figure into `<workspace>/models/catalog.yaml`, with its provenance.

    The benchmark must be one the catalogue declares (by name or alias, written
    under its own key), the figure must be on its scale, and `source` must say
    where it came from — a figure nobody can trace is the one Y12 forbids. A
    catalogue with comments in it is not rewritten: a YAML round trip would drop
    them, and a person's comment is not this command's to lose. Instead the
    lines to paste are in the error.
    """
    names = benchmarks_of(document or {})
    found = names.get(benchmark.strip().lower())
    if found is None:
        raise Unrecordable(
            f"no benchmark is called {benchmark!r}. Name one the catalogue declares under "
            f"`benchmarks:`, or add your own there first."
        )
    key, scale = found
    top = 100.0 if scale == "percent" else 1.0
    if not 0.0 <= float(value) <= top:
        raise Unrecordable(
            f"{key} is written out of {top:g}, so {value:g} is not a score on it"
        )
    if not source.strip():
        raise Unrecordable("say where the figure came from: a run you did, or a published table")
    figure: dict[str, Any] = {
        "value": f"{float(value):g}",
        "provenance": {
            "source": source.strip(),
            **({"harness": harness.strip()} if harness.strip() else {}),
            "as-of": (as_of or _dt.date.today()).isoformat(),
            **({"recorded-by": recorded_by.strip()} if recorded_by.strip() else {}),
        },
    }
    path = Path(workspace) / "models" / "catalog.yaml"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if any(line.lstrip().startswith("#") for line in text.splitlines()):
        paste = yaml.safe_dump(
            {"models": {model: {"benchmarks": {key: figure}}}}, sort_keys=False, allow_unicode=True
        )
        raise Unrecordable(
            f"{path} has comments in it, and writing the figure would drop them. Add these "
            f"lines under the model's own row instead:\n{paste}"
        )
    data = yaml.safe_load(text) if text.strip() else {}
    data = data if isinstance(data, dict) else {}
    data.setdefault("version", 1)
    rows = data.setdefault("models", {})
    if model not in rows:
        # A workspace row REPLACES the distribution's row of the same name — the catalogue is
        # layered row by row (`resolve._layer`) — so a row holding only this figure would lose
        # where the model is served, its price and its window. The distribution's row is copied
        # first, and the reviewer reads all of it in the diff.
        rows[model] = _shipped_row(model)
    row = rows[model]
    row.setdefault("benchmarks", {})[key] = figure
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def _shipped_row(model: str) -> dict[str, Any]:
    """The distribution's own row for `model` (under its id or any alias), or a new empty one."""
    from .resolve import BUILTIN_CATALOGUE

    shipped = (yaml.safe_load(Path(BUILTIN_CATALOGUE).read_text(encoding="utf-8")) or {}).get("models") or {}
    for name, row in shipped.items():
        if name == model or model in (row or {}).get("also-known-as", []):
            return dict(row or {})
    return {}


def run_deepeval(
    benchmark: Benchmark, model: str, ask: Callable[[str, str], str]
) -> float:  # pragma: no cover - downloads a dataset and asks a live model
    """Measure one of DeepEval's own benchmarks against `model`, on the benchmark's scale."""
    if benchmark.runner != "deepeval":
        raise Unrecordable(
            f"{benchmark.name} is run by `{benchmark.runs or 'nobody here'}`, not by DeepEval: "
            f"record its figure from wherever it was measured"
        )
    try:
        import deepeval.benchmarks as shipped
    except ImportError as missing:
        raise Unrecordable(f"DeepEval is not installed here ({missing}): `pip install deepeval`") from missing
    class_name = benchmark.runs.split(":", 1)[1].strip()
    cls = getattr(shipped, class_name, None)
    if cls is None:
        raise Unrecordable(f"DeepEval has no benchmark called {class_name!r}")
    result = cls(**dict(benchmark.with_ or {})).evaluate(model=AskModel(model, ask))
    accuracy = float(getattr(result, "overall_accuracy", result))
    return accuracy * 100.0 if benchmark.scale == "percent" else accuracy
