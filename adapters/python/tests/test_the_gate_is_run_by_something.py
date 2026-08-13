"""C7 — the suite is green because something other than a person ran it.

The register's finding was one sentence: *"the suite is green because it is run
by hand"*. Everything needed already existed — `scripts/test-all.sh` has been the
one command for a long time — and nothing ran it on a change nobody thought to
check.

What this file holds is the property that makes CI worth having rather than
worse than none: **the gate in CI and the gate a contributor runs are the same
gate.** A workflow that re-lists `cargo test`, then `clippy`, then `pytest` is a
second copy, and two copies drift — the interesting failures become the ones only
one of them catches, and nobody knows which.

It also holds the hole found while writing it: `test-all.sh` ran the adapter
suite whether or not the CLI had been built, dozens of test files load the worked
example through that binary, and the script exited 0 regardless. A gate that
reports green over a suite that has quietly stopped checking invariant P-1 is the
same defect as everything else in this register, wearing the gate's own clothes.

**How many files, and how many tests, are not written in this docstring** — for
the reason `test_the_gate_refuses_to_run_the_suite_without_the_loader` gives
below about the same two numbers. This paragraph said "forty-two test files" and
"nineteen tests skip" while the assertion twenty lines down was holding the
script to a different figure, so the file both stated the count and forbade
stating it. The script states it once and that test holds it there.
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
GATE = REPO / "scripts" / "test-all.sh"
WORKFLOW = REPO / ".github" / "workflows" / "gate.yml"


def test_there_is_a_gate_and_something_runs_it() -> None:
    assert GATE.exists(), "scripts/test-all.sh is the one command; it is gone"
    assert WORKFLOW.exists(), (
        "nothing in the tree runs the suite — it is green because somebody "
        "remembered to, which is register row C7"
    )


def test_the_workflow_runs_the_script_rather_than_a_copy_of_it() -> None:
    """The property that makes this worth having.

    A workflow spelling out the steps is a second gate. The copy in CI drifts
    from the copy a contributor runs, and then a failure means different things
    depending on where it happened.
    """
    said = WORKFLOW.read_text()
    assert "./scripts/test-all.sh" in said, (
        "the workflow does not run the gate script"
    )
    # And it does not re-run the pieces itself. `cargo` appears only inside
    # commentary; the steps must not.
    steps = [
        line for line in said.splitlines()
        if re.match(r"^\s+run:\s", line) or re.match(r"^\s{8,}\S", line)
    ]
    body = "\n".join(s for s in steps if not s.lstrip().startswith("#"))
    for duplicated in ("cargo test", "cargo clippy", "pytest"):
        assert duplicated not in body, (
            f"the workflow runs `{duplicated}` itself as well as running the "
            f"gate script — two copies of one gate, which is how they come to "
            f"disagree"
        )


def test_the_gate_refuses_to_run_the_suite_without_the_loader() -> None:
    """Dozens of adapter test files read the worked example through
    `target/debug/pact` and skip when it is absent.

    The exact number is deliberately NOT repeated here. It was "Forty-two" for
    four revisions after the script had moved on, and a stale figure beside a
    live assertion reads as though the assertion were stale too. The script
    states it once and the assertion below holds the script to it.

    So the suite could report green having quietly stopped checking the thing
    invariant P-1 is about. The script asserts the binary is there rather than
    trusting that an earlier step built it.
    """
    said = GATE.read_text()
    assert "target/debug/pact" in said, said
    assert re.search(r"if \[ ! -x target/debug/pact \]", said), (
        "the gate does not check that the loader was actually built"
    )
    assert "exit 1" in said, "and it must FAIL rather than warn"

    # The number in the comment is a measurement, so it has to stay true.
    # Files that actually SKIP on it, not files that mention it — this file
    # mentions it, and counting mentions counted this file. Mention is not use,
    # which is the same distinction that made a grep for `remembers` report a
    # reader that nothing called.
    counted = len([
        p for p in (REPO / "adapters/python/tests").glob("*.py")
        if 'pytest.skip("build the CLI first' in p.read_text()
    ])
    stated = re.search(r"(\d+) (?:adapter )?test files", said)
    assert stated, "the gate's comment no longer states how many files depend on it"
    assert int(stated.group(1)) == counted, (
        f"the gate says {stated.group(1)} test files need the loader and "
        f"{counted} do"
    )


def test_the_type_check_is_not_skipped_where_a_skip_would_be_a_hole() -> None:
    """`test-all.sh` skips the TypeScript type check when node_modules is absent,
    on purpose — a contributor without node still gets a useful run.

    In CI that skip is a hole, so the workflow installs them and the skip never
    fires. The two behaviours are correct in their own places, which is exactly
    why the workflow has to say so rather than inheriting silence.
    """
    gate = GATE.read_text()
    assert "skipped: run" in gate, "the local skip is gone — was that deliberate?"
    workflow = WORKFLOW.read_text()
    assert "npm ci" in workflow or "npm install" in workflow, (
        "CI does not install the TypeScript dev dependencies, so the type check "
        "skips there too and 1,238 lines of the second port go unchecked"
    )


def test_the_workflow_does_not_pin_a_toolchain_the_tree_already_chooses() -> None:
    """`rust-toolchain.toml` is in the tree. A workflow pinning its own version
    is a second place the toolchain is decided from, and the two disagree the
    first time somebody bumps one."""
    assert (REPO / "rust-toolchain.toml").exists()
    said = WORKFLOW.read_text()
    assert not re.search(r"toolchain:\s*\d", said), (
        "the workflow pins a Rust version; `rust-toolchain.toml` already does"
    )


# ───────────────────────── C6: there is a way to install this


def test_the_adapter_is_a_package_that_can_be_installed() -> None:
    """Register row C6: everything was `cargo run` or `PYTHONPATH=… python -m`
    from a checkout.

    Without a `[build-system]` this project is not a package at all — `uv`
    refuses to install its entry points and `pip install` cannot work. That was
    the whole of the Python half.
    """
    import tomllib

    p = REPO / "adapters/python/pyproject.toml"
    spec = tomllib.loads(p.read_text())
    assert "build-system" in spec, (
        "no `[build-system]`, so this is not a package and cannot be installed"
    )
    assert spec["project"]["scripts"], "an installed package with no commands"
    for command in ("pact-eval", "pact-conformance"):
        assert command in spec["project"]["scripts"], command

    # And the metadata says something. `uv init` leaves
    # `description = "Add your description here"`, which shipped for a while.
    described = spec["project"]["description"]
    assert "Add your description here" not in described, described
    assert len(described) > 40, described

    # `dependencies` must not have been swallowed by a table declared above it.
    # A TOML table consumes every key after it, and putting `[project.scripts]`
    # before the array made `dependencies` a key of it — which hatchling reported
    # as a type error rather than as the ordering mistake it was.
    assert isinstance(spec["project"]["dependencies"], list), (
        "`dependencies` is not a list — a table above it has swallowed it"
    )
    assert len(spec["project"]["dependencies"]) > 5


def test_the_rust_crates_carry_what_publishing_needs() -> None:
    """`cargo package` refused twice: path dependencies with no version, and a
    manifest with no description. Neither is publishable, and `cargo install
    --path` is the only reason the tree worked at all."""
    import tomllib

    workspace = tomllib.loads((REPO / "Cargo.toml").read_text())
    deps = workspace["workspace"]["dependencies"]
    for sibling in ("pact-diag", "pact-doc", "pact-loader", "pact-schema"):
        assert "version" in deps[sibling], (
            f"`{sibling}` is a path dependency with no version, so nothing that "
            f"depends on it can be packaged"
        )
    assert workspace["workspace"]["package"]["description"], "no description"

    for crate in ("pact-diag", "pact-doc", "pact-loader", "pact-schema", "pact-cli"):
        got = tomllib.loads((REPO / "crates" / crate / "Cargo.toml").read_text())
        assert "description" in got["package"], f"{crate} has no description"


def test_the_gate_checks_the_build_people_actually_install() -> None:
    """`--all-targets` builds with debug assertions ON, so anything
    `#[cfg(debug_assertions)]` gates is live there and its warnings never appear.

    `SpecSource::Unsafe` is deliberately unconstructible in a release binary —
    that is what stops `PACT_SPEC` deciding the governance columns in something
    somebody installed — and the `dead_code` warning that follows was invisible
    to the gate until the first `cargo install`.
    """
    said = GATE.read_text()
    assert "clippy --release" in said, (
        "the gate never checks the profile people install, so a warning that "
        "only appears there is found by a user rather than by the suite"
    )
    assert "-D warnings" in said, "and it must fail on one rather than print it"


# ─────────────────────── and every door actually opens


#: Each door, with arguments that reach PAST argument parsing into its real work.
#:
#: `--help` is not enough and that took a mutation to notice. `pact-import`
#: shipped with `Path` used in `main` and imported nowhere; removing that import
#: again left a `--help`-only test green, because `--help` returns before the
#: line that was broken. A door that opens and does nothing is the same seam-not-
#: effect mistake this suite has now made four times.
#:
#: Several of these EXIT NON-ZERO here — no model is served, a file does not
#: exist — and that is fine and is the point: what is asserted is that the door
#: reaches its own refusal rather than a traceback.
#: Where a door that WRITES is pointed. Outside the repository, on purpose.
_SOMEWHERE_ELSE = str(Path(tempfile.gettempdir()) / "pact-doors-out")

DOORS_AND_ARGS: dict[str, list[str]] = {
    "pact_adapters.scoring": ["examples/refund-desk", "--from-trace", "no-such.json",
                              "--called", "x"],
    "pact_adapters.conformance": ["examples/patterns/quorum"],
    "pact_adapters.pipeline": ["examples/patterns/quorum",
                               "--serving-at", "http://127.0.0.1:9/v1"],
    # The output path is a TEMP directory and not a name under the repository.
    # It was `no-such-dir/out`, and `exploding` does what it says — so running
    # the suite wrote an expanded workspace into the repository root and left it
    # there. A test that dirties the tree it is testing is a test that makes
    # `git status` lie about what somebody changed.
    "pact_adapters.exploding": ["examples/patterns/quorum", _SOMEWHERE_ELSE],
    "pact_adapters.importing": ["no-such-card.json", "--as", "a2a-card"],
    "pact_adapters.exporting": ["examples/patterns/quorum", "referee"],
    "pact_adapters.optimising": ["examples/patterns/quorum",
                                 "--serving-at", "http://127.0.0.1:9/v1"],
}


@pytest.mark.parametrize("module", sorted(DOORS_AND_ARGS))
def test_every_door_runs_when_somebody_opens_it(module: str) -> None:
    """A door registered and never opened.

    `pact-import` used `Path` in its `main` and imported it nowhere. Every
    library test passed — `from_a2a_card` was covered eight ways — because
    nothing had ever invoked the command. A `main` that has never been run is a
    `main` nobody has tested, and registering it as a console script makes that
    somebody else's crash.
    """
    import subprocess

    # Through `main`, which is what the console script calls — NOT `python -m`.
    # `scoring`'s `__main__` guard deliberately does NOT run the scorer: its
    # documented `-m` door is `pact_adapters.evals`, which imports `scoring.main`
    # under its own guard, and executing this file as `__main__` would build a
    # second copy of every class `resolve.py` and `learning.py` share with it.
    # So `-m pact_adapters.scoring` reaches that refusal rather than the door,
    # and a test using it here would be about the refusal instead. The guard
    # exists because with none at all the command printed nothing and exited 0 —
    # register row C4, held by
    # `test_no_plausible_command_at_this_package_answers_with_silence.py`.
    args = ", ".join(repr(a) for a in DOORS_AND_ARGS[module])
    out = subprocess.run(
        [
            sys.executable, "-c",
            f"from {module} import main; raise SystemExit(main([{args}]))",
        ],
        capture_output=True, text=True, cwd=REPO,
        env={
            "PYTHONPATH": str(REPO / "adapters/python/src"),
            "PATH": "/usr/bin:/bin",
        },
    )
    assert "Traceback" not in out.stderr, (
        f"`{module}.main(--help)` raised:\n{out.stderr[-1500:]}"
    )
    # NOT `returncode == 0`. Several of these refuse — no model served, no such
    # file — and a refusal is the door working. What must never happen is a
    # traceback, which is a door that did not reach its own error path.
    assert out.stdout.strip() or out.stderr.strip(), (
        f"{module} did its work and said nothing at all"
    )
    # And a refusal is a sentence, not a stack. `error:` is how every diagnostic
    # in this project opens.
    if out.returncode != 0:
        assert "error" in (out.stdout + out.stderr).lower(), (
            f"{module} failed and did not say why:\n{out.stdout}{out.stderr}"
        )


@pytest.mark.parametrize("module", sorted(DOORS_AND_ARGS))
def test_every_door_prints_usage_when_asked(module: str) -> None:
    """And `--help` works too, which is the other invocation every door has."""
    import subprocess

    out = subprocess.run(
        [sys.executable, "-c",
         f"from {module} import main; raise SystemExit(main(['--help']))"],
        capture_output=True, text=True, cwd=REPO,
        env={"PYTHONPATH": str(REPO / "adapters/python/src"), "PATH": "/usr/bin:/bin"},
    )
    assert out.returncode == 0, out.stderr[-800:]
    assert "pact" in out.stdout.split("\n")[0].lower(), out.stdout.split("\n")[0]
