"""The Expansion Rule, for prose, over every spelling the format offers.

> Both produce the identical document.

PACT lets an author write a paragraph three ways, and the format's central claim
is that the three are one thing:

    instructions: Be kind.        a plain scalar
    instructions: |               a block scalar
      Be kind.
    instructions.md               a file beside the agent

For a round they produced **two** documents. `pact_doc::prose` trimmed the file
(Phase 3, which closed the divergence between the file and the inline form) and
nothing trimmed the block, so an author who pressed the pipe key got a different
digest from one who did not. It was found by building `explode` — writing a
document back out as a tree and watching the round trip come back one byte
longer.

**Why trimming is the right direction rather than keeping.** A plain scalar
*cannot* express a trailing newline; there is no spelling for it. A real file
*always* has one, because every editor writes it and POSIX defines a line as
ending in `\\n`. So if the trailing newline is content, the inline form and the
file form can never be equivalent and the Expansion Rule is false for prose
permanently. The only reading under which all three agree is that trailing
whitespace on a block is not part of what was written.

**What it costs, said plainly.** `|` and `|-` now mean the same thing, and `|+`
no longer keeps what it asked to keep. That is a real loss of expressiveness and
it is the right trade: an author who has to know that a pipe keeps a newline and
a pipe-minus strips it is being asked to learn YAML's chomping indicators in
order to write down what their agent should do, which is the no-code ceiling
failing.

**This moved every digest in the repository** for any document using a block
scalar, which is why it was recorded as an open decision rather than done
quietly.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
BINARY = REPO / "target" / "debug" / "pact"

#: Every way to write the same paragraph. The value each produces must be
#: byte-identical, and so must the digest over the whole document.
#:
#: `|+` is here and is the uncomfortable one: it explicitly asks YAML to KEEP
#: trailing newlines and it no longer does. Included rather than left out,
#: because a test that only covered the spellings the decision is comfortable
#: with would be describing a different decision.
SPELLINGS: dict[str, tuple[str, str]] = {
    "plain":         ("instructions: Be kind.\n", ""),
    "block":         ("instructions: |\n  Be kind.\n", ""),
    "block-strip":   ("instructions: |-\n  Be kind.\n", ""),
    "block-keep":    ("instructions: |+\n  Be kind.\n\n\n", ""),
    "folded":        ("instructions: >\n  Be kind.\n", ""),
    "quoted":        ('instructions: "Be kind."\n', ""),
    "file":          ("", "Be kind.\n"),
    "file-no-eol":   ("", "Be kind."),
    "file-blank-eol": ("", "Be kind.\n\n\n"),
}


def _workspace(root: Path, inline: str, beside: str) -> Path:
    (root / "agents" / "desk").mkdir(parents=True)
    (root / "workspace.yaml").write_text("name: prose\n")
    (root / "agents" / "desk" / "agent.yaml").write_text(
        "name: Desk\ndescription: A desk.\n" + inline
    )
    if beside:
        (root / "agents" / "desk" / "instructions.md").write_text(beside)
    return root


def _shown(root: Path) -> dict:
    out = subprocess.run(
        [str(BINARY), "show", str(root)], capture_output=True, text=True
    )
    assert out.returncode == 0, out.stdout + out.stderr
    return json.loads(out.stdout)


def _digest(root: Path) -> str:
    out = subprocess.run(
        [str(BINARY), "discover", str(root)], capture_output=True, text=True
    )
    assert out.returncode == 0, out.stdout + out.stderr
    found = json.loads(out.stdout)
    return (found[0] if isinstance(found, list) else found)["digest"]


@pytest.fixture(autouse=True)
def _needs_the_loader() -> None:
    if not BINARY.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")


def test_every_spelling_of_a_paragraph_gives_the_same_text(tmp_path: Path) -> None:
    """The value itself, before any digest. Nine spellings, one string.

    Asserted on the exact bytes rather than on `.strip()`-ed equality, because
    normalising before comparing is precisely how this divergence survived two
    tests for a round — one in `lib.rs` and one in `example_refund_desk.rs`, both
    of which trimmed both sides and could not see it.
    """
    said: dict[str, str] = {}
    for name, (inline, beside) in SPELLINGS.items():
        root = _workspace(tmp_path / name, inline, beside)
        said[name] = _shown(root)["agents"]["desk"]["instructions"]

    assert set(said.values()) == {"Be kind."}, (
        "the spellings disagree:\n  "
        + "\n  ".join(f"{k:<15} {v!r}" for k, v in sorted(said.items()))
    )


def test_every_spelling_of_a_paragraph_gives_the_same_digest(tmp_path: Path) -> None:
    """And the whole document, which is what a registry and a signature see.

    Two equal strings could still digest differently if the canonicaliser
    encoded them differently; this is the claim README makes on the front page,
    so it is checked as the front page states it.
    """
    digests = {
        name: _digest(_workspace(tmp_path / name, inline, beside))
        for name, (inline, beside) in SPELLINGS.items()
    }
    assert len(set(digests.values())) == 1, (
        "the spellings produce different documents:\n  "
        + "\n  ".join(f"{k:<15} {v}" for k, v in sorted(digests.items()))
    )


def test_a_paragraph_keeps_the_newlines_inside_it(tmp_path: Path) -> None:
    """The limit of the decision, without which the two above are satisfied by
    trimming everything.

    Only TRAILING whitespace goes. A blank line between two paragraphs is
    content — it is what makes them two paragraphs — and an indented first line
    is a Markdown code block, which is why `prose` trims the end and not the
    start.
    """
    root = _workspace(
        tmp_path / "para",
        "instructions: |\n  Be kind.\n\n  Then be quick.\n",
        "",
    )
    assert _shown(root)["agents"]["desk"]["instructions"] == (
        "Be kind.\n\nThen be quick."
    )


def test_a_quoted_string_that_asked_for_a_newline_still_gets_one(
    tmp_path: Path,
) -> None:
    """The other limit, and the one that keeps this honest.

    `"Be kind.\\n"` in double quotes is an author typing an escape sequence — a
    deliberate act, and not a spelling of a paragraph anybody reaches by
    accident. Block scalars are trimmed because a pipe is how a non-programmer
    writes several lines; an explicit `\\n` is not that, and trimming it would be
    ignoring something somebody clearly meant.
    """
    root = _workspace(tmp_path / "esc", 'instructions: "Be kind.\\n"\n', "")
    assert _shown(root)["agents"]["desk"]["instructions"] == "Be kind.\n"
