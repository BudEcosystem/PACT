"""A pydantic-evals dataset file as a PACT tree's eval suite (02P E1-E10).

`from_pydantic_evals` reads the YAML or JSON a `Dataset.to_file` writes (and
`Dataset.from_file` loads) as data: the `pydantic_evals` package is never
imported, and no evaluator is built or run. What it writes is `evals/suite.yaml`
and one `evals/cases/<name>.yaml` per case, in the tree's own words:

- a case's `inputs` are its `when:` (text) or its `with:` (fields, the case's
  name then being its `when:`), its `expected_output` its `expect:`, and its
  `metadata` a named loss (E1): PACT's cases have no field for it;
- each evaluator, the dataset's for every case (`rules:`) or a case's own
  (`must-also:`), is what `pydantic_ai_registry.yaml` says of it (door
  `evaluator.`): `EqualsExpected` is the `expect:` every case is held to,
  `Equals` `must-say-one-of:`, `Contains` `must-contain:` (E2), `IsInstance` the
  `answers-with:` every run is validated against (E3), `MaxDuration` the
  `limits.finishes-within:` line to write on what the suite tests (E4),
  `LLMJudge` a `judged:` rule graded by `graded-by:` (E6), and the rest named
  losses each saying what to write (`HasMatchingSpan`, E5, names the
  `must-call-before:` line for a span of a tool call); an evaluator pydantic-evals
  does not ship is the author's own code (E7), named the same way;
- `report_evaluators` score the whole run in code (E7), and `$schema` is where
  an editor finds the file's JSON Schema: both named.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import yaml

from .importing import ImportReport
from .openapi import Imported, NotImported
from .openapi_shapes import kebab

__all__ = ["from_pydantic_evals"]

#: The field a one-argument evaluator (`{Name: value}`) passes its value as.
_FIRST = {
    "Equals": "value", "Contains": "value", "IsInstance": "type_name", "MaxDuration": "seconds",
    "LLMJudge": "rubric", "HasMatchingSpan": "query", "GEval": "criteria",
}
#: `LLMJudge`'s options a PACT `judged:` rule has no word for, and why.
_JUDGE_LOSSES = {
    "include_input": "PACT's grader is shown the case's `because:` and `from-these-passages:`, not its inputs",
    "include_expected_output": "PACT's grader is shown the case's `because:`, not its `expect:`",
    "model_settings": "the grader's settings are its catalogue row's",
    "score": "a `judged:` rule passes or fails; it gives no score",
    "assertion": "a `judged:` rule is always a pass or a fail",
    "evaluation_name": "a rule is named by what it says",
}


def from_pydantic_evals(document: Mapping[str, Any]) -> Imported:
    """A dataset file's mapping as `evals/suite.yaml` and `evals/cases/<name>.yaml`."""
    cases = document.get("cases")
    if not isinstance(cases, list):
        raise NotImported(
            "this is not a pydantic-evals dataset: it holds no `cases:` list. Fix: give the file "
            "`Dataset.to_file` writes (YAML or JSON)."
        )
    report = ImportReport(kind="a pydantic-evals dataset" + (f" ({document['name']})" if document.get("name") else ""))
    read = _Reading(report)
    suite: dict[str, Any] = {"population": "authored-enumeration"}
    for key, value in document.items():
        report.seen += (key,)
        if key == "name":
            suite = {"description": f"The cases of the pydantic-evals dataset {value}.", **suite}
            report.mapped[key] = "the suite's `description:`"
        elif key == "$schema":
            report.not_portable[key] = "where an editor finds the file's JSON Schema; `pact check` reads the suite"
        elif key == "cases":
            report.mapped[key] = "one `evals/cases/<name>.yaml` per case, written by the people who wrote them"
        elif key == "evaluators":
            report.mapped[key] = "the suite's `rules:`, held on every case"
            if rules := read.rules(value or [], "evaluators"):
                suite["rules"] = rules
        elif key == "report_evaluators":
            report.not_portable[key] = "scores of the dataset's whole run, worked out in code; each is named"
            for name, _ in (_named(e) for e in value or []):
                read.lost(f"report_evaluators.{name}", read.why(name))
        else:
            report.unmapped[key] = f"`{key}`, which a pydantic-evals dataset does not have"
    if "description" not in suite:
        suite = {"description": "Cases brought in from a pydantic-evals dataset.", **suite}
    if read.graded_by:
        suite["graded-by"] = read.graded_by
    files = {"evals/suite.yaml": _text(suite)}
    names: set[str] = set()
    for n, case in enumerate(cases, 1):
        if not isinstance(case, Mapping):
            raise NotImported(f"case {n} of the dataset is not a mapping. Fix: write each case as `- inputs: ...`.")
        called = kebab(str(case.get("name") or "")) or f"case-{n}"
        while called in names:
            called += f"-{n}"
        names.add(called)
        files[f"evals/cases/{called}.yaml"] = _text(read.case(case, called))
    report.still_to_write = (
        "`evals: evals` on the agent or workflow these cases test",
        *read.owed,
    )
    return Imported(api="", files=files, shapes={}, report=report)


class _Reading:
    def __init__(self, report: ImportReport) -> None:
        self.report = report
        self.owed: list[str] = []
        self.graded_by = ""

    def case(self, case: Mapping[str, Any], called: str) -> dict[str, Any]:
        where = f"cases.{case.get('name') or called}"
        self.report.seen += (where, *(f"{where}.{k}" for k in case))
        self.report.mapped[where] = f"`evals/cases/{called}.yaml`"
        out: dict[str, Any] = {}
        inputs = case.get("inputs")
        if isinstance(inputs, str):
            out["when"] = inputs
            self.report.mapped[f"{where}.inputs"] = "`when:`"
        else:
            out["when"] = f"The case {case.get('name') or called}."
            out["with"] = dict(inputs) if isinstance(inputs, Mapping) else {"inputs": inputs}
            self.report.mapped[f"{where}.inputs"] = "`with:`, the case's name its `when:`"
        if "expected_output" in case and case["expected_output"] is not None:
            out["expect"] = case["expected_output"]
            self.report.mapped[f"{where}.expected_output"] = "`expect:`"
        elif "expected_output" in case:
            self.report.mapped[f"{where}.expected_output"] = "no `expect:`: nothing was expected"
        for key in case:
            if key == "name":
                self.report.mapped[f"{where}.name"] = "the case's file name"
            elif key == "metadata":
                self.lost(f"{where}.metadata", "what the case's author attached to it; a PACT case has no field "
                          "for it. Say what matters in `because:`")
            elif key == "evaluators":
                self.report.mapped[f"{where}.evaluators"] = "the case's `must-also:`"
                if rules := self.rules(case[key] or [], f"{where}.evaluators"):
                    out["must-also"] = rules
            elif key not in ("inputs", "expected_output"):
                self.report.unmapped[f"{where}.{key}"] = f"`{key}`, which a pydantic-evals case does not have"
        if "expect" not in out and "must-also" not in out:
            self.owed.append(f"`expect:` (or a `must-also:` rule) in evals/cases/{called}.yaml: it checks nothing yet")
        return out

    def rules(self, evaluators: list[Any], where: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        times: dict[str, int] = {}
        for written in evaluators:
            name, args = _named(written)
            times[name] = times.get(name, 0) + 1
            key = f"{where}.{name}" + (f"#{times[name]}" if times[name] > 1 else "")
            self.report.seen += (key,)
            rule = self._rule(name, args, key)
            if rule is not None:
                out.append(rule)
        return out

    def _rule(self, name: str, args: dict[str, Any], key: str) -> dict[str, Any] | None:
        from .pydantic_ai_registry import registry

        row = registry().through("evaluator").get(name)
        if row is None or row.outcome == "loss":
            self.lost(key, self.why(name, args))
            return None
        self.report.mapped[key] = row.pact
        value = args.get(_FIRST.get(name, ""))
        if name == "Equals" and isinstance(value, (str, int, float, bool)):
            return {"must-say-one-of": [str(value).lower() if isinstance(value, bool) else str(value)]}
        if name == "Contains" and isinstance(value, (str, list)) and all(isinstance(v, str) for v in _many(value)):
            if args.get("case_sensitive", True):
                self.report.mapped[key] += "; PACT matches it whatever its case"
            return {"must-contain": list(_many(value))}
        if name in ("Equals", "Contains"):
            self.report.mapped.pop(key)
            self.lost(key, f"a `{name}` of a {type(value).__name__}, and PACT's rule compares words")
            return None
        if name == "MaxDuration":
            self.owed.append(f"`limits: {{finishes-within: {_seconds(value)}s, when-it-runs-out: stop-and-say-so}}` on what the suite tests")
        if name == "LLMJudge":
            return self._judged(args, key)
        return None

    def _judged(self, args: dict[str, Any], key: str) -> dict[str, Any]:
        from .pydantic_ai_interop import catalogue_row_for

        model = str(args.get("model") or "")
        row = catalogue_row_for(model) if model else ""
        if row and row != model:  # a catalogue row: the grader `graded-by:` names
            if self.graded_by and row != self.graded_by:
                self.lost(f"{key}.model", f"`{model}`, a second grader: a suite has one `graded-by:` ({self.graded_by})")
            else:
                self.graded_by = row
        else:
            self.owed.append(
                "`graded-by:` in evals/suite.yaml: the catalogue row of the model that grades `judged:`"
                + (f" (`{model}` is no catalogue row's)" if model else "")
            )
        for option, why in _JUDGE_LOSSES.items():
            if option in args and not (option == "assertion" and args[option] not in (False, None)):
                self.lost(f"{key}.{option}", why)
        return {"judged": " ".join(str(args.get("rubric") or "").split())}

    def why(self, name: str, args: Mapping[str, Any] | None = None) -> str:
        from .pydantic_ai_registry import registry

        row = registry().through("evaluator").get(name)
        if row is None:
            return (
                f"`{name}`, an evaluator pydantic-evals does not ship: the author's own code, which does "
                "not cross. Write what it measures as a `metrics:` line (`program:` names a carried program)"
            )
        tool = _tool_of((args or {}).get("query")) if name == "HasMatchingSpan" else ""
        return " ".join(row.why.split()) + (
            f". This one is the call of `{tool}`: `must-call-before: {{call: <the later call>, first: {tool}}}`" if tool else ""
        )

    def lost(self, key: str, why: str) -> None:
        self.report.seen += (key,)
        self.report.not_portable[key] = why


def _named(written: Any) -> tuple[str, dict[str, Any]]:
    """`Name`, `{Name: value}` or `{Name: {field: value}}` (pydantic-evals' `EvaluatorSpec`)."""
    if isinstance(written, str):
        return written, {}
    if isinstance(written, Mapping) and len(written) == 1:
        ((name, value),) = written.items()
        if isinstance(value, Mapping):
            return str(name), dict(value)
        return str(name), {_FIRST.get(str(name), "value"): value}
    raise NotImported(f"{written!r} is not an evaluator. Fix: write `Name`, `{{Name: value}}` or `{{Name: {{...}}}}`.")


def _many(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else [value]


def _seconds(value: Any) -> str:
    """`MaxDuration`'s `seconds`: a number, or the ISO 8601 duration (`PT2S`) `Dataset.to_file`
    writes for a `timedelta`, read as pydantic-evals reads it (`float | timedelta`)."""
    from datetime import timedelta

    from pydantic import TypeAdapter, ValidationError

    try:
        number = None if isinstance(value, bool) else TypeAdapter(timedelta).validate_python(value).total_seconds()
    except ValidationError:
        number = None
    if number is None:
        raise NotImported(
            f"`MaxDuration: {value!r}` is not a duration. Fix: give it seconds (`MaxDuration: 2`) or the "
            "ISO 8601 duration `Dataset.to_file` writes (`MaxDuration: PT2S`)."
        )
    return str(int(number)) if number == int(number) else str(number)


def _tool_of(query: Any) -> str:
    """The tool a span query names, when it is the span of one tool's call."""
    if not isinstance(query, Mapping):
        return ""
    named = (query.get("has_attributes") or {}).get("gen_ai.tool.name") if isinstance(query.get("has_attributes"), Mapping) else None
    if named:
        return str(named)
    said = str(query.get("name_equals") or "")
    return said.removeprefix("running tool: ") if said.startswith("running tool: ") else ""


def _text(body: Mapping[str, Any]) -> str:
    return yaml.safe_dump(dict(body), sort_keys=False, allow_unicode=True, width=100)
