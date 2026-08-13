"""C4 — `python -m pact_adapters.scoring <folder>` printed nothing and exited 0.

`scoring.py` is where the scorer lives, so it is the module name a person
reaches for. It was also the one module carrying a `main` and no `__main__`
guard, so running it did exactly nothing and said so with a success code —
which a reader takes as *"it scored, and there was nothing to report"*. Measured
before the fix: zero bytes on either stream, exit 0.

The guard that answers now does NOT run the scorer, and that is deliberate. The
`-m` door is `pact_adapters.evals`, which imports `scoring.main` under its own
guard so one copy of `Case` exists rather than two. What the guard does is refuse
and say where the door is — silence is the one answer a command must never give.

**And the site was where the wrong name came from.** `site-docs/guide/evals.md`
and `site-docs/reference/cli.md` both taught `python -m pact_adapters.scoring
<PATH>` under "Running it" and "Scoring an eval suite" — so this guard's first
effect was to make the command the documentation tells you to type exit 3. Both
pages now name `./scripts/pact-eval` and `python -m pact_adapters.evals`, and
`test_the_documentation_site_tells_the_truth.py::test_every_python_module_the
_site_tells_you_to_run_is_one_that_runs` runs every `python -m` line the site
quotes so the two cannot drift apart again. A guard that refuses the documented
command is not a fix; it is the lie moved from silence into a sentence.

Mutation: delete the `if __name__ == "__main__":` block at the foot of
`scoring.py`. Without it the module runs as `__main__`, defines its functions,
calls none of them and exits 0, and `test_the_module_a_person_reaches_for_says
_something` goes red on empty output — the shape the defect had.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "adapters/python/src"
WORKSPACE = "examples/refund-desk"

def _doors() -> tuple[str, ...]:
    """Every module that carries a `main`, read off the package rather than typed.

    Which is the point. The first version of this list was seven names written
    out by hand, and a hand-written list is a property that holds until somebody
    adds the eighth module — the same shape as the defect this file exists for,
    where one module out of eight had no guard and nothing noticed. There are two
    other hand-kept copies of roughly this list in the suite; this one is
    derived, so the eighth door is covered on the day it is written.

    `def main(` in the source is the test: a module with one is a module a person
    can plausibly type after `python -m`.
    """
    found = []
    for path in sorted((SRC / "pact_adapters").glob("*.py")):
        if path.name.startswith("_"):
            continue
        if "\ndef main(" in path.read_text():
            found.append(f"pact_adapters.{path.stem}")
    return tuple(found)


#: `scoring` is in here like any other door: what is asserted is the effect —
#: something was said — and not which mechanism said it.
DOORS = _doors()


def _run(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", *args],
        capture_output=True, text=True, cwd=REPO, timeout=timeout,
        env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
    )


def test_the_module_a_person_reaches_for_says_something() -> None:
    """The defect itself, on a real workspace.

    Asserted on the EFFECT: bytes came back and the exit code is not the one
    that means *"done, nothing to report"*. Nothing here looks for a guard —
    a refusal, a usage dump or a scored suite would each satisfy this, and the
    only thing that cannot is what the command used to do.
    """
    assert (REPO / WORKSPACE).is_dir(), f"{WORKSPACE} is not in the tree any more"
    out = _run(["pact_adapters.scoring", WORKSPACE])

    said = out.stdout + out.stderr
    assert said.strip(), (
        "`python -m pact_adapters.scoring examples/refund-desk` printed nothing "
        f"at all and exited {out.returncode} — which reads as a suite that "
        "scored and had nothing to say"
    )
    assert "Traceback" not in out.stderr, out.stderr[-1500:]
    assert out.returncode != 0, (
        "it said something, but exited 0 while doing none of the work the name "
        f"promises:\n{said}"
    )
    # And a refusal is a sentence a non-technical author can act on, in the
    # four-part form every other diagnostic in this project uses.
    assert "error" in said.lower(), said
    assert "fix:" in said.lower(), said


def test_it_names_the_command_that_does_score() -> None:
    """A refusal that does not say what to type instead is D11's own failure —
    gating without recommending — on the command line."""
    out = _run(["pact_adapters.scoring", WORKSPACE])
    said = out.stdout + out.stderr
    assert "pact_adapters.evals" in said, (
        "it refused and did not name the door that works:\n" + said
    )
    assert WORKSPACE in said, (
        "it did not put the folder the person typed into the line they are "
        "meant to retype:\n" + said
    )


@pytest.mark.parametrize("module", DOORS)
def test_no_door_run_as_a_module_answers_with_nothing(module: str) -> None:
    """The general property, over every module carrying a `main`.

    `--help` because it is the cheapest thing a person types at an unfamiliar
    command and it reaches no model. What is asserted is only that bytes came
    back: a door that prints usage and a door that refuses and redirects are
    both fine, and silence is not.
    """
    assert "pact_adapters.scoring" in DOORS, (
        "the derivation stopped finding the module this file is about: " + str(DOORS)
    )
    out = _run([module, "--help"])
    assert out.stdout.strip() or out.stderr.strip(), (
        f"`python -m {module} --help` printed nothing at all and exited "
        f"{out.returncode}"
    )
    assert "Traceback" not in out.stderr, out.stderr[-1500:]
