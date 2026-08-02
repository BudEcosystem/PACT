"""The number on the front page is the number the suites run.

`README.md` opens with *"851 tests (346 Rust + 505 adapter)"* in the status table
and repeats it in the one command it tells a reader to type. Both were wrong by
more than a hundred and fifty, because nothing recomputed them: a headline count
is a claim about the repository, and a claim about the repository that no test
reads goes stale on the round after the one that wrote it. This is the same
defect, and the same repair, as
`the_number_the_front_page_quotes_is_the_number_the_binary_prints` — which holds
the settings count in the very first code block, after it had gone stale in three
separate documents.

Why the count lives here rather than in a Rust test beside that one. The adapter
half is only knowable by collecting it: twenty-two `parametrize` marks expand one
written function into several run cases, so counting `def test_` in the source
undercounts by tens, and pytest is the only thing that can say the real number.
`request.session.items` is that number, for free, in the session that is already
running — no subprocess, no second collection pass, nothing to keep in step.

The Rust half is counted from source instead, and can be: Rust has no
parametrisation, this workspace has no `#[ignore]` and no feature-gated test
module, so `#[test]` and `#[tokio::test]` attributes are exactly the tests
`cargo test` runs. Both of those preconditions are asserted rather than assumed —
see `_rust_tests` — because the day one of them stops holding is the day this
count silently overstates.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TESTS = Path(__file__).resolve().parent
README = REPO / "README.md"
CRATES = REPO / "crates"

#: `#[test]` or `#[tokio::test]`, alone on its line.
_ATTR = re.compile(r"^\s*#\[(?:tokio::)?test\]\s*$")
#: The function that must follow one. A `#[test]` attribute anywhere else would
#: be inside a fixture string, and counting it would inflate the headline.
_FN = re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s")


def _rust_tests() -> int:
    """Every test `cargo test` runs over `crates/`, counted from the source.

    Two preconditions make source counting equal to running:

    * no `#[ignore]` anywhere — an ignored test is written and not run, so it
      would be counted and never reported;
    * every attribute is immediately followed by an `fn` — an attribute inside a
      raw-string fixture is text, not a test, and this repository writes a lot of
      YAML and Rust inside raw strings.

    Both are checked here rather than trusted, with the file and line, because a
    counter that quietly starts over-counting turns the repair into the defect.
    """
    total = 0
    for path in sorted(CRATES.rglob("*.rs")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for n, line in enumerate(lines):
            if "#[ignore" in line:
                pytest.fail(
                    f"{path.relative_to(REPO)}:{n + 1} is `#[ignore]`d, and this counter "
                    "assumes every declared test runs.\n"
                    "  fix: delete the attribute, or teach `_rust_tests` to subtract it — "
                    "an ignored test counted as a passing one is a headline that overstates."
                )
            if not _ATTR.match(line):
                continue
            nxt = lines[n + 1] if n + 1 < len(lines) else ""
            if not _FN.match(nxt):
                pytest.fail(
                    f"{path.relative_to(REPO)}:{n + 1} has a `#[test]` attribute that no "
                    f"function follows (the next line is {nxt.strip()!r}).\n"
                    "  fix: if it is inside a fixture string, this counter has to skip "
                    "strings; if it is real code, `cargo test` is not running it."
                )
            total += 1
    assert total > 100, f"only {total} Rust tests found — the walk is wrong, not the workspace"
    return total


def _quoted(text: str) -> tuple[int, int, int]:
    """`(total, rust, adapter)` as `README.md` states them, from both places.

    Two places, because the table and the command block each carry the total and
    they drifted together last time — which is what a copy is for. A reader who
    types the command and a reader who skims the table must be told the same
    thing.
    """
    table = re.search(r"\*\*([\d,]+) tests \(([\d,]+) Rust \+ ([\d,]+) adapter\)", text)
    assert table, (
        "README.md's status table no longer states the test count in the form this test "
        "reads.\n"
        "  fix: write it as `**1234 tests (500 Rust + 734 adapter), clippy clean, ...**` in "
        "the **Code** row."
    )
    command = re.search(r"\./scripts/test-all\.sh\s+# ([\d,]+) tests", text)
    assert command, (
        "README.md's `./scripts/test-all.sh` block no longer states a test count.\n"
        "  fix: write it as `./scripts/test-all.sh          # 1234 tests, Rust + 7 adapters, "
        "fully offline`."
    )
    total, rust, adapter = (int(g.replace(",", "")) for g in table.groups())
    assert int(command.group(1).replace(",", "")) == total, (
        f"README.md says {total} tests in its status table and "
        f"{command.group(1)} beside the command that runs them.\n"
        f"  fix: make both {total}."
    )
    return total, rust, adapter


def test_the_headline_test_count_on_the_front_page_is_the_number_the_suites_run(request) -> None:
    """A count the front page quotes and nothing recomputes.

    It is asserted against the CURRENT session, so the number moves the moment
    anybody adds a test — which is the point. The failure names the three
    numbers to type, so the fix is one line of editing and never an
    investigation.
    """
    on_disk = {p.name for p in TESTS.glob("test_*.py")}
    collected = {Path(item.nodeid.split("::")[0]).name for item in request.session.items}
    if collected != on_disk:
        # A partial run cannot know the adapter total, and guessing it would
        # make `pytest -k something` rewrite the front page's arithmetic.
        pytest.skip(
            "this checks the whole adapter suite's size; run `uv run pytest tests/ -q`. "
            f"Collected {len(collected)} of {len(on_disk)} test files."
        )

    adapter = len(request.session.items)
    rust = _rust_tests()
    total, said_rust, said_adapter = _quoted(README.read_text(encoding="utf-8"))

    wrong = []
    if said_rust != rust:
        wrong.append(f"Rust: README.md says {said_rust}, `crates/` declares {rust}")
    if said_adapter != adapter:
        wrong.append(f"adapter: README.md says {said_adapter}, pytest collected {adapter}")
    if total != said_rust + said_adapter:
        wrong.append(
            f"the total does not add up: README.md says {total}, "
            f"and {said_rust} + {said_adapter} is {said_rust + said_adapter}"
        )
    assert not wrong, (
        "README.md quotes a test count the repository does not have:\n  "
        + "\n  ".join(wrong)
        + f"\n  fix: in README.md, write `**{rust + adapter} tests ({rust} Rust + "
        f"{adapter} adapter), clippy clean, TypeScript type-checked**` in the **Code** row "
        f"of the status table, and `# {rust + adapter} tests` beside `./scripts/test-all.sh` "
        "a few lines below. Both places, or the next reader gets whichever they looked at "
        "first."
    )
