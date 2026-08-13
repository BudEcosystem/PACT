"""`= 80` has to mean the same thing here as it does in the checker.

An author writes one line — `needs: scores: MMLU: "= 80"` — and two pieces of
code decide it. `crates/pact-schema/src/coerce.rs` parses it and answers it
(`Op::holds`); this port parses it again (`_threshold`) and answers it again
(`_HOLDS`). `resolve.py` has carried a comment for as long as `_HOLDS` has
existed saying it "mirrors `Op::holds`" and that "a difference between the two is
a model bound on a rule the checker read differently". It was not a mirror:

    Op::holds     Op::Eq => (lhs - rhs).abs() < f64::EPSILON   ~2.2e-16
    _HOLDS["="]   abs(have - want) < 1e-12                     ~1e-12

Four orders of magnitude apart, and neither figure was chosen for a benchmark
score. A catalogue publishing 80.0000000001 met `= 80` for the checker and did
not for the resolver; one publishing 79.999999999999 met it for the resolver and
not for the checker. Both now read `SCORE_TOLERANCE`, a billionth, and both are
held to `spec/comparisons.yaml` — one table, checked from both languages, so the
comment is an assertion instead of an aspiration.

The rows go through `ModelEntry.satisfies` rather than `_HOLDS` directly,
because `satisfies` is the door a real recommendation goes through: a threshold
this port reads differently is a model this port BINDS differently, and that is
the thing worth pinning.

The Rust half is
`crates/pact-schema/tests/a_comparison_means_the_same_thing_in_both_ports.rs`.
Neither file can be made to pass by editing one port.

Mutation: restore `abs(have - want) < 1e-12` in `resolve._HOLDS["="]`. The
`= 80` / `80.0000000001` row goes red here and nothing else in either suite
moves. Setting `SCORE_TOLERANCE` to `f64::EPSILON`'s value (`2.220446049250313e-16`)
instead fails the `= 80` / `79.999999999999` row — the same defect measured from
the checker's side. Widening it to `1e-6` fails the `80.00000001` row, which is
what stops the tolerance growing until it calls `79.99` a score of 80.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.resolve import SCORE_TOLERANCE, ModelEntry  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
TABLE = yaml.safe_load((REPO / "spec" / "comparisons.yaml").read_text())
CASES = TABLE["cases"]
NOT_COMPARISONS = TABLE["not-comparisons"]


def test_the_tolerance_is_the_one_the_specification_states() -> None:
    """One figure, in one file, read by both ports."""
    stated = float(TABLE["tolerance"])
    assert SCORE_TOLERANCE == stated, (
        f"the resolver allows {SCORE_TOLERANCE:e} and spec/comparisons.yaml says "
        f"{stated:e}. The checker reads that file too, so the two ports are now "
        f"deciding `= 80` differently and only one of them is wrong about it."
    )


def test_the_table_still_holds_the_rows_it_was_written_with() -> None:
    """A pin that can be emptied is not a pin."""
    assert len(CASES) >= 10, (
        f"spec/comparisons.yaml carries {len(CASES)} rows; it had fourteen, and a "
        f"table that shrinks is a mirror that stopped being checked"
    )


@pytest.mark.parametrize(
    "case",
    CASES,
    ids=[f"{c['written']} vs {c['published']}" for c in CASES],
)
def test_every_comparison_in_the_table_binds_the_way_the_table_says(
    case: dict[str, str],
) -> None:
    """The whole distance from the author's line to the model being offered.

    `satisfies` reads the author's `needs.scores:` entry exactly as written and
    the catalogue's published figure exactly as published, and answers whether
    this row may be bound. The table says what that answer is.
    """
    published = float(case["published"])
    entry = ModelEntry(
        name="catalogue-row",
        tier="mid",
        cost=None,
        scores={"MMLU": published},
    )

    bound, why = entry.satisfies({"scores": {"MMLU": case["written"]}})

    expected = case["holds"] == "yes"
    assert bound is expected, (
        f"a model publishing MMLU {published} against an author's "
        f"`MMLU: \"{case['written']}\"`: the resolver "
        f"{'binds' if bound else f'refuses it — {why!r}'} and "
        f"spec/comparisons.yaml says it should "
        f"{'bind' if expected else 'be refused'} — {case['because']}"
    )


# ───────────────── and the other half: what neither port may read as a comparison


@pytest.mark.parametrize(
    "row", NOT_COMPARISONS, ids=[r["written"] for r in NOT_COMPARISONS]
)
def test_nothing_the_table_calls_unreadable_binds_a_model_here(
    row: dict[str, str],
) -> None:
    """The rows both ports must REFUSE — the half of the agreement that had come
    apart.

    `coerce::threshold` has always answered `None` to a bare number ("a bare
    number states no comparison"), and `resolve._threshold` read `MMLU: 80` as
    `> 80`. Neither port could reach the other's answer, because `pact check`
    refuses `MMLU: 80` at the author's own line before this port sees the
    document — so it was an unreachable disagreement, not a live one, and that is
    exactly the kind that survives for years because nothing goes red.

    It is refused in both now rather than written down as deliberate, because the
    guess was not obviously right: `< 5` is a real bar on latency or a
    hallucination rate, and there an assumed `>` binds the models the author wrote
    the line to keep out.

    A refusal, not a crash and not a silent pass: the model is not bound, and the
    reason names the field and shows the shape to write. That sentence is the
    whole value of refusing.

    Mutation, run: put `if isinstance(written, (int, float)) ...: return ">",
    float(written)` back at the top of `resolve._threshold`, and the `float(said)`
    fall-through at the bottom. The `80` and `0.8` rows go red here — *"bound a
    model publishing 80"* — and the Rust twin stays green, which is the shape of
    the original defect measured from the side that had it. Dropping the
    `has_a_digit` guard instead reddens the `> inf` row alone: that one is the
    divergence this table found going the OTHER way, where Python read a
    threshold the checker calls `schema/wrong-type`.
    """
    entry = ModelEntry(
        name="catalogue-row", tier="mid", cost=None, scores={"MMLU": 80.0}
    )

    bound, why = entry.satisfies({"scores": {"MMLU": row["written"]}})

    assert bound is False, (
        f"`MMLU: {row['written']!r}` bound a model publishing 80. "
        f"spec/comparisons.yaml says neither port may read it — {row['because']}"
    )
    assert "not a threshold this can read" in why, (
        f"refused for the wrong reason: {why!r}. It has to say the line cannot be "
        f"read, not that the figure fell short — those send an author to different "
        f"places."
    )
    assert "> 80" in why, "and it must show the shape to write instead"


def test_a_bare_number_reaches_neither_port_because_the_checker_stops_it() -> None:
    """Why the row above is a latent defect closed rather than a live one fixed.

    The claim `spec/comparisons.yaml` makes about `80` is only worth making if the
    checker is where an author actually meets it. It is: this is the shipped
    binary, on a real tree, printing the sentence the table quotes.
    """
    import json
    import shutil
    import subprocess

    binary = REPO / "target" / "debug" / "pact"
    if not binary.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "refund-desk"
        shutil.copytree(REPO / "examples" / "refund-desk", root)
        needs = root / "agents" / "refund-desk" / "needs.yaml"
        needs.write_text(needs.read_text() + "scores:\n  MMLU: 80\n")

        refused = subprocess.run(
            [str(binary), "check", str(root)], capture_output=True, text=True
        )
        assert refused.returncode != 0, "`MMLU: 80` must not load"
        assert "should be a comparison" in refused.stdout, refused.stdout
        assert "Write it like `> 80` or `>= 0.8`." in refused.stdout, (
            "the refusal has to show BOTH shapes — a floor and a ceiling — because "
            "which one the author meant is the thing the old guess got wrong"
        )

        # And with the line written properly it loads, so the refusal above is
        # about the shape and not about the field existing at all.
        needs.write_text(needs.read_text().replace("MMLU: 80", 'MMLU: "> 80"'))
        accepted = subprocess.run(
            [str(binary), "check", str(root)], capture_output=True, text=True
        )
        assert accepted.returncode == 0, accepted.stdout + accepted.stderr
        shown = subprocess.run(
            [str(binary), "show", str(root)], capture_output=True, text=True, check=True
        )
        doc = json.loads(shown.stdout)
        assert doc["agents"]["refund-desk"]["needs"]["scores"]["MMLU"] == "> 80", (
            "and it reaches this port as the author's own text, which is what "
            "`_threshold` is handed"
        )
