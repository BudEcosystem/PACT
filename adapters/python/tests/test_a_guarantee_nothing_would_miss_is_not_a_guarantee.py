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
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
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


def _run(tests: tuple[str, ...]) -> int:
    done = subprocess.run(
        [str(PY), "-m", "pytest", *[f"tests/{t}" for t in tests], "-q", "-x", "--no-header"],
        cwd=HERE.parent,
        capture_output=True,
        text=True,
        timeout=600,
    )
    return done.returncode


@pytest.mark.skipif(not PY.exists(), reason="needs the project venv to run a subprocess")
@pytest.mark.parametrize("name,module,find,replace,tests,why", CASES, ids=[c[0] for c in CASES])
def test_breaking_this_line_is_something_the_suite_notices(
    name: str, module: str, find: str, replace: str, tests: tuple[str, ...], why: str
) -> None:
    """One guarantee, broken on purpose, and the suite has to fail."""
    path = SRC / module
    original = path.read_text()
    before = hashlib.sha256(original.encode()).hexdigest()

    assert original.count(find) == 1, (
        f"`{find}` appears {original.count(find)} times in {module}, not once. "
        "This case can no longer aim at the line it was written for — fix the "
        "case rather than deleting it, because an unaimed mutation reports green."
    )

    try:
        path.write_text(original.replace(find, replace + find, 1) if replace.startswith("pass")
                        else original.replace(find, replace, 1))
        assert _run(tests) != 0, (
            f"{module} was broken — {name} — and {list(tests)} still passed.\n"
            f"WHY IT MATTERS: {why}\n"
            "A guarantee nothing would miss is not a guarantee. Write the "
            "assertion that catches this before adding to these files again."
        )
    finally:
        path.write_text(original)

    assert hashlib.sha256(path.read_text().encode()).hexdigest() == before, (
        f"{module} was not restored byte-for-byte. A mutation left behind is how "
        "`crates/pact-schema/src/lib.rs` spent an afternoon with the NaN spend-cap "
        "refusal disabled, invisible to pytest because Python tests run against a "
        "prebuilt loader binary."
    )


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
