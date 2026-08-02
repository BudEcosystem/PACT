"""AC-7.3 — validate → resolve → build → eval → report, offline.

> The full pipeline (`validate → resolve → build → eval → report`) runs offline
> against a local model, with no network dependency in the core.

Every stage already existed and **nothing composed them**, which is why the
register recorded `resolve` and `build` as *"not stages on any shipped path"*.
They were reachable — `--choose-model` reaches the resolver, `pact show` produces
the built document — but only as separate things somebody had to know to run in
order, which is not a pipeline.

Two properties matter more than the composition:

* **A stage that cannot be attempted does not fail the run.** A machine with no
  model served still gets a validated, resolved, built tree — the four fifths
  that need nothing but the tree, and what somebody fixing a document needs long
  before they have weights. Failing there would answer a question they did not
  ask.
* **A stage that is REFUSED stops everything downstream.** Nothing said about a
  tree the checker rejected can mean anything, so the later stages are marked
  not-attempted rather than run against a document known to be wrong.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.pipeline import (  # noqa: E402
    NOT_ATTEMPTED,
    RAN,
    REFUSED,
    STAGES,
    run_pipeline,
)

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"


@pytest.fixture(autouse=True)
def _needs_the_loader() -> None:
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")


def test_the_five_stages_are_the_ones_the_criterion_names() -> None:
    assert STAGES == ("validate", "resolve", "build", "eval", "report")


def test_the_worked_example_reaches_every_stage_that_can_run() -> None:
    """`validate`, `resolve` and `build` need nothing but the tree, so they run
    on any machine. `eval` needs a model somebody is serving."""
    out = run_pipeline(EXAMPLE)
    by_name = {s.name: s for s in out.stages}
    assert set(by_name) == set(STAGES), sorted(by_name)

    for offline in ("validate", "resolve", "build"):
        assert by_name[offline].outcome == RAN, (
            f"{offline} needs nothing but the tree and did not run: "
            f"{by_name[offline].said}"
        )
    assert by_name["build"].gave, "the build stage produced no document"
    assert "digest" in by_name["build"].said, by_name["build"].said

    # `eval` either ran or could not be attempted — never refused on a tree the
    # checker accepted.
    assert by_name["eval"].outcome in (RAN, NOT_ATTEMPTED), by_name["eval"].said


def test_a_machine_with_no_model_still_gets_four_fifths_of_it() -> None:
    """The property that decides whether this is usable.

    Pointed at an address nothing answers on, the eval stage is `not-attempted`
    with the line to type — not a refusal, not a network error, and not a
    traceback. Somebody fixing a document has the four stages they need.
    """
    out = run_pipeline(EXAMPLE, serving_at="http://127.0.0.1:9/v1")
    by_name = {s.name: s for s in out.stages}
    assert by_name["eval"].outcome == NOT_ATTEMPTED, by_name["eval"].said
    assert by_name["eval"].said, "it must say why"
    assert out.exit_code == 0, (
        "a machine with no model served is not a broken workspace, and the exit "
        "code must not say it is"
    )
    for offline in ("validate", "resolve", "build"):
        assert by_name[offline].outcome == RAN


def test_a_tree_the_checker_refuses_stops_everything_downstream(
    tmp_path: Path,
) -> None:
    """Nothing said about a tree the checker rejected can mean anything. The
    later stages are marked not-attempted rather than run against a document
    already known to be wrong."""
    root = tmp_path / "refund-desk"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns(".pact"))
    (root / "workspace.yaml").write_text(
        (root / "workspace.yaml").read_text() + "\nnonsense-key: 1\n"
    )

    out = run_pipeline(root)
    by_name = {s.name: s for s in out.stages}
    assert by_name["validate"].outcome == REFUSED, by_name["validate"].said
    for later in STAGES[1:]:
        assert by_name[later].outcome == NOT_ATTEMPTED, (
            f"{later} ran against a tree the checker had already refused"
        )
        assert "did not validate" in by_name[later].said
    assert out.exit_code == 1


def test_the_report_names_every_stage_and_says_what_happened() -> None:
    """A pipeline whose output a person cannot read is five commands with extra
    steps."""
    said = run_pipeline(EXAMPLE).render()
    for stage in STAGES:
        assert stage in said, f"{stage} is missing from the report"
    assert "Every stage that could run, ran." in said or "did not complete" in said


def test_it_has_a_door_a_person_can_type() -> None:
    out = subprocess.run(
        [sys.executable, "-m", "pact_adapters.pipeline", str(EXAMPLE)],
        capture_output=True, text=True, cwd=REPO,
        env={"PYTHONPATH": str(REPO / "adapters/python/src"), "PATH": "/usr/bin:/bin"},
    )
    assert out.returncode == 0, out.stdout + out.stderr
    for stage in STAGES:
        assert stage in out.stdout, out.stdout


def test_the_command_is_installed_with_the_others() -> None:
    """`pact-eval` and `pact-conformance` are console scripts; a pipeline nobody
    can run without knowing where the source lives is register row C6 again."""
    import tomllib

    spec = tomllib.loads((REPO / "adapters/python/pyproject.toml").read_text())
    assert "pact-pipeline" in spec["project"]["scripts"], spec["project"]["scripts"]
