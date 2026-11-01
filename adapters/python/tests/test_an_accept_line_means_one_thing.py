"""`needs.accept-when:` — one table, read by both ports (96 §B4).

`spec/accept-when.yaml` is read here by `selection.parse` and in Rust by
`accept::read` (`every_line_in_the_shared_table_is_read_as_it_says`); a row
either reader disagrees with fails in that reader's own suite.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters import benchmarks, resolve, selection  # noqa: E402
from pact_adapters.evals import CaseOutcome, Verdict  # noqa: E402
from trees import REPO, shown  # noqa: E402

TABLE = yaml.safe_load((REPO / "spec/accept-when.yaml").read_text(encoding="utf-8"))
BENCH = {name: (name, scale) for name, scale in TABLE["benchmarks"].items()}
METRICS = set(TABLE["metrics"])
TREE = REPO / "tests/trees/a-desk-that-listens-reads-and-chooses"

_RULE_IS = {
    "loader/not-a-comparison": ("is not a comparison",),
    "loader/no-such-measure": ("nothing is called",),
    "loader/a-part-a-measure-does-not-have": ("so not `.", "has no `."),
}


@pytest.mark.parametrize("row", TABLE["lines"], ids=lambda r: r["written"])
def test_every_line_is_read_as_the_table_says(row: dict) -> None:
    line = selection.parse(row["written"], benchmarks=BENCH, metrics=METRICS)
    assert (line.measure, line.kind, line.part, line.op, line.unit) == (
        row["measure"], row["kind"], row["part"], row["op"], row["unit"],
    )
    assert line.value == pytest.approx(float(row["value"]))


@pytest.mark.parametrize("row", TABLE["not-lines"], ids=lambda r: r["written"])
def test_every_line_the_checker_refuses_is_refused_here_too(row: dict) -> None:
    with pytest.raises(selection.Unreadable) as why:
        selection.parse(row["written"], benchmarks=BENCH, metrics=METRICS)
    said = _RULE_IS.get(row["rule"], ())
    assert not said or any(s in str(why.value) for s in said), str(why.value)


def _entry(**kw) -> resolve.ModelEntry:
    return resolve.ModelEntry(**{"name": "m", "tier": "mid", "cost": 0.001, "scores": {}, **kw})


def _line(text: str) -> selection.Line:
    return selection.parse(text, benchmarks=BENCH, metrics=METRICS)


def test_a_catalogue_line_is_held_before_anything_runs() -> None:
    needs = {"accept-when": (_line("mmlu.score > 50"), _line("input-price <= 3 USD"))}
    assert _entry(scores={"mmlu": 81.0}).satisfies(needs) == (True, "")
    ok, why = _entry(scores={"mmlu": 41.0}).satisfies(needs)
    assert not ok and "does not hold" in why
    ok, why = _entry().satisfies(needs)
    assert not ok and "no recorded mmlu score" in why
    ok, why = _entry(scores={"mmlu": 81.0}, cost=None).satisfies(needs)
    assert not ok and "no published input price" in why


def test_a_line_nobody_can_read_accepts_no_model() -> None:
    ok, why = _entry().satisfies({"accept-when-unread": ("`accept-when: cost > 0.05` — no currency",)})
    assert not ok and "no currency" in why


def test_what_a_model_scored_and_spent_on_the_suite_is_held_after_it_passes() -> None:
    outcomes = [
        CaseOutcome("a", True, "", (), {"refund-tone": 0.9}),
        CaseOutcome("b", True, "", (), {"refund-tone": 0.7}),
        CaseOutcome("c", False, "late", (), {}),
    ]
    figures = selection.measured(outcomes, [0.02, 0.04, None])
    assert figures["pass-rate"] == pytest.approx(2 / 3)
    assert figures["refund-tone.score"] == pytest.approx(0.8)
    assert figures["refund-tone.cases"] == 2
    assert figures["cost"] == pytest.approx(0.03)
    v = Verdict("PASS", 2 / 3, 0.5, outcomes, measured=figures)
    doc = shown(TREE)
    held = lambda text: resolve._short_of({"accept-when": (_line(text),)}, v, doc)  # noqa: E731
    assert held("refund-tone.score >= 0.8") == ""
    assert "does not hold" in held("refund-tone.score >= 0.85")
    assert held("cost < 0.05 USD") == ""
    assert "does not hold" in held("pass-rate >= 90%")
    unmetered = Verdict("PASS", 1.0, 0.5, outcomes, measured=selection.measured(outcomes, [None] * 3))
    assert "never metered" in resolve._short_of({"accept-when": (_line("cost < 0.05 USD"),)}, unmetered, doc)


def test_the_desk_reads_its_own_lines_and_its_named_metric() -> None:
    doc = shown(TREE)
    needs = resolve.needs_of(doc, "front-desk")
    assert [l.measure for l in needs["accept-when"]] == ["mmmu", "refund-tone", "pass-rate", "cost"]
    assert needs["accept-when-unread"] == ()
    rows = {e.name: e for e in resolve.load_catalogue(workspace=TREE).entries}
    assert rows["qwen2.5-vl-7b-instruct"].satisfies(needs)[0]
    assert not rows["qwen2.5-7b-instruct"].satisfies(needs)[0]


def test_a_figure_is_recorded_with_where_it_came_from(tmp_path: Path) -> None:
    path = benchmarks.record(
        tmp_path, "qwen2.5-14b-instruct", "Terminal-Bench", 31.5,
        source="tb run on this machine", harness="terminal-bench-core 0.2",
        as_of=dt.date(2026, 10, 28),
    )
    row = yaml.safe_load(path.read_text())["models"]["qwen2.5-14b-instruct"]
    figure = row["benchmarks"]["terminal-bench"]
    assert figure["value"] == "31.5"
    assert figure["provenance"] == {
        "source": "tb run on this machine", "harness": "terminal-bench-core 0.2", "as-of": "2026-10-28",
    }
    rows = {e.name: e for e in resolve.load_catalogue(workspace=tmp_path).entries}
    assert rows["qwen2.5-14b-instruct"].scores["terminal-bench"] == pytest.approx(31.5)


@pytest.mark.parametrize(
    "benchmark, value, source, said",
    [
        ("banana-bench", 10.0, "x", "no benchmark is called"),
        ("mmlu", 140.0, "x", "out of 100"),
        ("mmlu", 70.0, " ", "say where the figure came from"),
    ],
)
def test_a_figure_that_cannot_be_traced_or_placed_is_refused(tmp_path, benchmark, value, source, said) -> None:
    with pytest.raises(benchmarks.Unrecordable) as why:
        benchmarks.record(tmp_path, "m", benchmark, value, source=source)
    assert said in str(why.value)


def test_a_catalogue_with_comments_is_never_rewritten(tmp_path: Path) -> None:
    (tmp_path / "models").mkdir()
    kept = "# ours\nversion: 1\nmodels: {}\n"
    (tmp_path / "models/catalog.yaml").write_text(kept)
    with pytest.raises(benchmarks.Unrecordable) as why:
        benchmarks.record(tmp_path, "m", "mmlu", 70.0, source="model card")
    assert "lines under the model's own row" in str(why.value)
    assert (tmp_path / "models/catalog.yaml").read_text() == kept


def test_the_shipped_benchmarks_say_how_each_is_measured() -> None:
    known = benchmarks.known()
    assert known["mmlu"].runner == "deepeval" and known["terminal-bench"].runner == "host"
    import os

    os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
    import deepeval.benchmarks as shipped

    for b in known.values():
        if b.runner == "deepeval":
            assert hasattr(shipped, b.runs.split(":", 1)[1]), b.name


def test_a_bound_model_says_which_of_an_agents_settings_it_would_throw_away() -> None:
    """96 §B5: the same reading `pact check` gives a pinned model, for whatever a host binds."""
    rows = {e.name: e for e in resolve.load_catalogue().entries}
    gpt = rows["gpt-5.5"]
    assert gpt.thinks_unless_told and "top-k" in gpt.ignores
    assert len(gpt.ignored_settings({"temperature": 0.2, "top-k": 40})) == 2
    assert gpt.ignored_settings({"thinking": "none", "temperature": 0.2}) == []
    assert rows["gpt-5.4"].ignored_settings({"temperature": 0.2}) == []
    assert rows["gpt-5.4"].ignored_settings({"thinking": "high", "temperature": 0.2})
    assert "at all" in rows["claude-opus-5"].ignored_settings({"temperature": 0.2})[0]
    assert rows["qwen2.5-7b-instruct"].ignored_settings({"top-k": 40}) == []
