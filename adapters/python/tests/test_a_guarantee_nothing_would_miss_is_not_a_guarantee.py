"""The tests for this crossing die when the code they protect is broken.

**This file exists because the suite once passed with the code disabled.** The
first green gate for `pact_agent.py` was 1621 passing tests, and a mutation
campaign against it killed 0 of 39: replacing

    if ran.suspension is not None and ran.suspension.awaiting:

with `if False:` — which deletes the entire park path — changed nothing. The
tests asserted what a *scripted model said*, and a scripted model says the same
thing whatever you tell it, so what they compared was the script.

That is not a new mistake here. `test_the_golden_set_runs_everywhere.py` lines
114-130 record the same one, twice, in its own words: *"two mutations proved that
worthless … That is the 'seam, not effect' mistake this round has now produced
three times."* It went on to produce it a fourth.

The repair was a hundred-odd assertions about what the code DID rather than what
it returned, and a mutation run to prove they bite. But a repair measured once is
a repair that decays: the next test added to those files can be as decorative as
the first set was, and nothing would say so. **A kill rate that is not asserted
is not a property of the suite.**

So this asserts it. Each case below breaks one load-bearing line and requires the
suite to notice. It is deliberately small and fast — a full campaign belongs in a
tool, not in the gate — but it is anchored to the specific guarantees that were
found undefended, so a regression in the defence fails here rather than in a
future audit nobody schedules.

**What it is not.** It cannot prove the tests are good, only that these lines are
covered by something that fails. A mutation that survives is proof of a hole; a
mutation that dies is only evidence against one. That asymmetry is why the cases
are named after the guarantee rather than the line, and why the reason each one
matters is written beside it.

**It breaks a copy, never the source.** Each case used to write the mutant over
the real `src/pact_adapters/<module>` and restore it in a `finally`, for about
a minute a run. That directory is what an editable install imports, so any
other process started in the window (a host's own suite, a worker) ran with the
park path or the quarantine check disabled, and a kill in the window left the
mutation on disk. The mutant now goes into a throwaway copy of
`adapters/python/{src,tests}` with the rest of the checkout linked beside it,
and the subset runs there. `test_the_real_source_is_untouched_while_a_copy_is_broken`
watches the real directory for the whole of a run.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "src" / "pact_adapters"
PY = HERE.parent / ".venv" / "bin" / "python"

pytest.importorskip("pydantic_ai")


#: The tests each mutation is checked against. Deliberately a SUBSET: the whole
#: suite takes two minutes and this file applies one mutation per case, so a
#: full run per case would put a quarter of an hour into the gate to answer a
#: question a focused run answers identically. The subset is the files that
#: exist to defend these lines, which is the honest scope — a mutation these
#: cannot see is one their own authors missed.
FACADE_TESTS = (
    "test_a_pact_agent_is_an_agent_pydantic_ai_can_hold.py",
    "test_a_halted_run_does_not_pretend_to_be_an_answer.py",
    "test_the_same_document_is_the_same_run_through_the_facade.py",
)
#: The AD-71 fence is defended by the file that stages the attack, not by the
#: one that proves the client speaks the right protocol. Naming the wrong oracle
#: is itself a way to report green — this list was wrong on the first run and
#: this file failed rather than passing, which is the behaviour it is for.
FENCE_TESTS = (
    "test_a_server_that_writes_itself_a_permission_is_quoted_not_obeyed.py",
    "test_a_connect_line_reaches_a_server_without_a_handshake.py",
)


#: `(name, module, find, replace, tests, why)`. `find` must appear EXACTLY once
#: in the module — asserted per case, so a refactor that moves or duplicates the
#: line fails here loudly instead of silently mutating nothing and reporting the
#: suite green, which is the failure mode this whole file is about.
CASES = [
    (
        "a park is raised rather than returned",
        "pact_agent.py",
        "raise PactSuspended(",
        "pass  # mutated: ",
        FACADE_TESTS,
        "Three park reasons carry no pending tool call. If the door returns "
        "instead of raising, a caller reads `.output`, gets the model's last "
        "words, and believes a waiting run answered.",
    ),
    (
        "only the three parks with nothing pending raise",
        "pact_agent.py",
        "ran.suspension.reason in _PARKS_WITH_NOTHING_PENDING",
        "False",
        FACADE_TESTS,
        "The exact line that survived the first campaign. Neutering it turns "
        "every park back into a returned value.",
    ),
    (
        "external prose must be fenced before it reaches a model",
        "mcp_bridge.py",
        "if not is_quarantined(region):",
        "if False:",
        FENCE_TESTS,
        "AD-71. Unfenced server prose reaching a model unlabelled is the "
        "injection the whole quarantine exists to stop, and a server upgrade "
        "is enough to deliver it.",
    ),
]


def _copy_of_the_checkout(root: Path) -> Path:
    """`adapters/python` in a throwaway checkout: `src` and `tests` copied, the rest linked.

    Copied, because `src` is what gets broken and the tests find the checkout
    from their own resolved path (`parents[3]`), so a linked `tests` would walk
    straight back to the real one. Linked, for everything they then read from
    it: the examples, the built loader, the schema.
    """
    repo = HERE.parents[2]
    python = root / "adapters" / "python"
    python.mkdir(parents=True)
    quiet = shutil.ignore_patterns("__pycache__", ".pytest_cache")
    for folder in ("src", "tests"):
        shutil.copytree(HERE.parent / folder, python / folder, ignore=quiet)
    for real, copy in ((repo, root), (repo / "adapters", root / "adapters"), (HERE.parent, python)):
        for entry in real.iterdir():
            if not (copy / entry.name).exists() and entry.name not in ("__pycache__", ".pytest_cache"):
                (copy / entry.name).symlink_to(entry)
    return python


def _run(python: Path, tests: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    """The subset, run in the copy and importing the copy's `pact_adapters`."""
    return subprocess.run(
        [str(PY), "-m", "pytest", *[f"tests/{t}" for t in tests], "-q", "-x", "--no-header",
         "-p", "no:cacheprovider"],
        cwd=python,
        # Ahead of the venv's editable install, which names the real `src`.
        env={**os.environ, "PYTHONPATH": str(python / "src"), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=600,
    )


@pytest.fixture(scope="module")
def copy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The throwaway `adapters/python`, proven to pass before anything is broken.

    Without the control a copy that cannot run at all (a missing link, a wrong
    interpreter) fails every subset, and every mutation "dies": green for the
    reason this file exists to rule out.
    """
    python = _copy_of_the_checkout(tmp_path_factory.mktemp("mutation") / "repo")
    control = _run(python, FACADE_TESTS + FENCE_TESTS)
    assert control.returncode == 0, (
        "the unbroken copy does not pass, so a failure in it says nothing about a "
        f"mutation:\n{control.stdout[-3000:]}{control.stderr[-1000:]}"
    )
    return python


def _digest(folder: Path) -> str:
    """Every source file under `folder`, by name and content."""
    seen = hashlib.sha256()
    for path in sorted(folder.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            seen.update(str(path.relative_to(folder)).encode() + b"\0" + path.read_bytes())
    return seen.hexdigest()


@contextmanager
def _watching(folder: Path) -> Iterator[set[str]]:
    """Every state `folder` is seen in while the block runs, hashed in a thread."""
    seen = {_digest(folder)}
    done = threading.Event()

    def watch() -> None:
        while not done.wait(0.05):
            seen.add(_digest(folder))

    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    try:
        yield seen
    finally:
        done.set()
        watcher.join()
        seen.add(_digest(folder))


def _broken(copy: Path, module: str, find: str, replace: str, tests: tuple[str, ...]) -> int:
    """What the subset returns with one line of the COPY's `module` broken."""
    path = copy / "src" / "pact_adapters" / module
    original = path.read_text()
    assert original.count(find) == 1, (
        f"`{find}` appears {original.count(find)} times in {module}, not once. "
        "This case can no longer aim at the line it was written for — fix the "
        "case rather than deleting it, because an unaimed mutation reports green."
    )
    try:
        path.write_text(original.replace(find, replace + find, 1) if replace.startswith("pass")
                        else original.replace(find, replace, 1))
        return _run(copy, tests).returncode
    finally:
        path.write_text(original)  # the next case breaks one line, not two


@pytest.mark.skipif(not PY.exists(), reason="needs the project venv to run a subprocess")
@pytest.mark.parametrize("name,module,find,replace,tests,why", CASES, ids=[c[0] for c in CASES])
def test_breaking_this_line_is_something_the_suite_notices(
    copy: Path, name: str, module: str, find: str, replace: str, tests: tuple[str, ...], why: str
) -> None:
    """One guarantee, broken on purpose, and the suite has to fail."""
    assert (SRC / module).read_text() == (copy / "src" / "pact_adapters" / module).read_text(), (
        f"the copy's {module} is not the source's, so breaking it tests nothing here"
    )
    assert _broken(copy, module, find, replace, tests) != 0, (
        f"{module} was broken — {name} — and {list(tests)} still passed.\n"
        f"WHY IT MATTERS: {why}\n"
        "A guarantee nothing would miss is not a guarantee. Write the "
        "assertion that catches this before adding to these files again."
    )


@pytest.mark.skipif(not PY.exists(), reason="needs the project venv to run a subprocess")
def test_the_real_source_is_untouched_while_a_copy_is_broken(copy: Path) -> None:
    """The source an editable install imports is never the thing that is broken.

    Watched for the whole of one mutation run, not compared before and after: a
    file written and restored is byte-identical afterwards, and that is exactly
    what the old `finally` did while every other process importing the package
    got a module with its park path disabled. A mutation left behind by a kill
    is how `crates/pact-schema/src/lib.rs` spent an afternoon with the NaN
    spend-cap refusal off.
    """
    name, module, find, replace, tests, _why = CASES[0]
    with _watching(SRC) as seen:
        assert _broken(copy, module, find, replace, tests) != 0, name
    assert len(seen) == 1, (
        f"src/pact_adapters changed while a mutation ran ({len(seen)} states seen): "
        "the mutant was written over the source other processes import"
    )


def test_a_write_that_is_put_back_is_still_something_the_watch_sees(tmp_path: Path) -> None:
    """The oracle above, shown to bite: what the old test did to the real
    source (write the mutant, run, restore), done to a scratch folder."""
    import time

    module = tmp_path / "module.py"
    module.write_text("if parked:\n    raise Suspended()\n")
    with _watching(tmp_path) as seen:
        module.write_text("if False:\n    raise Suspended()\n")
        time.sleep(0.3)
        module.write_text("if parked:\n    raise Suspended()\n")
    assert len(seen) == 2, seen


def test_nothing_in_the_tree_is_carrying_a_mutation_right_now() -> None:
    """The sweep that would have caught the one that got out.

    A mutation agent left `if false && (!amount.is_finite() || *amount <= 0.0)`
    in the Rust schema crate, disabling PACT's refusal of NaN and infinite spend
    caps. `pytest tests/ -q` passed 1742 twice over it, because Python tests
    shell out to a **prebuilt** `target/debug/pact` and never rebuild — only
    `scripts/test-all.sh` (cargo test first) surfaced it, once as thirteen
    failures and once as a clippy error.

    Cheap, total, and it runs in the suite that could not see the problem, which
    is the point: the check belongs where the blind spot is.
    """
    repo = HERE.parents[2]
    roots = [
        repo / "crates",
        repo / "adapters" / "python" / "src",
        repo / "adapters" / "typescript" / "src",
    ]
    suspects: list[str] = []
    for root in roots:
        if not root.exists():  # pragma: no cover - a partial checkout
            continue
        for path in list(root.rglob("*.rs")) + list(root.rglob("*.py")) + list(root.rglob("*.ts")):
            if "__pycache__" in path.parts or "target" in path.parts:
                continue
            for number, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
                bare = line.strip()
                if bare.startswith("#") or bare.startswith("//"):
                    continue
                for shape in ("if false", "if true", "if False:", "if True:"):
                    if shape in bare:
                        suspects.append(f"{path.relative_to(repo)}:{number}: {bare[:90]}")
    assert not suspects, (
        "a constant condition is in shipped source, which is what a mutation "
        "left behind looks like:\n  " + "\n  ".join(suspects)
    )
