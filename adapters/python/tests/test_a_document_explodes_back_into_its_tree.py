"""AC-1.2′ — `load(explode(D)) ≡ D`, and what it refuses.

> For every document whose field keys lie in the portable key alphabet …
> `load(explode(D)) ≡ D` up to canonicalisation. For any key outside it,
> `explode` MUST fail loudly naming the offending field and MUST NOT emit a tree.

The loader turns a tree into a document; this turns it back. The round trip is
what makes the Expansion Rule a property rather than a description — a format
whose two directions do not compose has one direction and a claim.

`load` here is the **real Rust CLI**. An `explode` checked against a Python
re-implementation of the loader would prove the two agreed with each other, which
is the failure this repository has found more than once.

**One residual, and it is a finding rather than a wart.** The round trip is exact
*up to trailing whitespace on prose*, because the three ways of writing the same
prose do not agree:

    instructions: Be kind.        → "Be kind."      (plain scalar)
    instructions.md               → "Be kind."      (trimmed at load)
    instructions: |               → "Be kind.\\n"    (clipped block scalar)
      Be kind.

`pact_doc::prose` trims the file form, which is what made the first two agree —
and building the inverse is what showed the third still does not. Which of the
two is correct is a design decision that moves every digest in the repository, so
it is recorded in `docs/70-PRODUCTION-GAP-REGISTER.md` rather than settled here.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.exploding import (  # noqa: E402
    CarriesPayloads,
    ExplodeRefused,
    explode,
    why_not_portable,
)

REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "examples"
PACT_BIN = REPO / "target" / "debug" / "pact"


@pytest.fixture(autouse=True)
def _needs_the_loader() -> None:
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")


def load(root: "str | Path") -> dict[str, Any]:
    out = subprocess.run(
        [str(PACT_BIN), "show", str(root)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


def _settled(node: Any) -> Any:
    """The document with trailing whitespace taken off every string.

    Named for what it does rather than hidden in a comparison: the residual above
    is real, and a test that quietly stripped it would be describing a property
    the format does not have.
    """
    if isinstance(node, str):
        return node.rstrip()
    if isinstance(node, dict):
        return {k: _settled(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_settled(v) for v in node]
    return node


# ─────────────────────────────────────────────── the round trip


@pytest.mark.parametrize(
    "workspace",
    sorted(p.parent.name for p in (EXAMPLES / "patterns").rglob("workspace.yaml")),
)
def test_every_payload_free_example_survives_the_round_trip(
    workspace: str, tmp_path: Path
) -> None:
    """`load(explode(D)) ≡ D` over eight real workspaces.

    The patterns are used rather than `refund-desk` because that one carries
    payloads — see the refusal test below, which is the reason it cannot.
    """
    original = load(EXAMPLES / "patterns" / workspace)
    said = explode(original, tmp_path / "exploded")
    assert said.wrote, "explode produced no files at all"

    accepted = subprocess.run(
        [str(PACT_BIN), "check", str(tmp_path / "exploded")],
        capture_output=True, text=True,
    )
    assert accepted.returncode == 0, (
        f"the exploded tree does not load:\n{accepted.stdout}{accepted.stderr}"
    )

    again = load(tmp_path / "exploded")
    assert _settled(again) == _settled(original), (
        "the document did not survive being written out and read back:\n"
        + json.dumps(
            {
                "only in the original": sorted(set(original) - set(again)),
                "only after the round trip": sorted(set(again) - set(original)),
            },
            indent=2,
        )
    )


def test_the_residual_is_exactly_trailing_whitespace_on_prose(
    tmp_path: Path,
) -> None:
    """The finding, asserted so it cannot quietly widen.

    If the round trip ever differs by anything OTHER than trailing whitespace,
    `_settled` above is hiding it — and this is the test that says so.
    """
    original = load(EXAMPLES / "patterns" / "quorum")
    explode(original, tmp_path / "exploded")
    again = load(tmp_path / "exploded")

    if again == original:
        pytest.skip("the residual is gone — delete this test and the register row")
    # Every difference must vanish under `rstrip`, and be a string.
    def _differences(a: Any, b: Any, at: str = "") -> list[str]:
        if isinstance(a, dict) and isinstance(b, dict):
            return [d for k in set(a) | set(b)
                    for d in _differences(a.get(k), b.get(k), f"{at}.{k}")]
        if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
            return [d for i, (x, y) in enumerate(zip(a, b))
                    for d in _differences(x, y, f"{at}[{i}]")]
        if a == b:
            return []
        both_text = isinstance(a, str) and isinstance(b, str)
        return [] if both_text and a.rstrip() == b.rstrip() else [f"{at}: {a!r} vs {b!r}"]

    other = _differences(original, again)
    assert not other, (
        "the round trip differs by something that is NOT trailing whitespace:\n  "
        + "\n  ".join(other)
    )


# ────────────────────────────────── and what it refuses, before writing


def test_a_key_outside_the_alphabet_is_refused_and_nothing_is_written(
    tmp_path: Path,
) -> None:
    """The criterion says `MUST NOT emit a tree`, and that is not fussiness: half
    a tree on disk is worse than none, because the half that wrote looks like it
    worked."""
    where = tmp_path / "never-written"
    for bad in ("Name", "a/b", "ends-in-a-dot.", "con", "x" * 65, "trailing "):
        with pytest.raises(ExplodeRefused) as refusal:
            explode({"name": "a", bad: "x"}, where)
        assert bad in str(refusal.value), str(refusal.value)
        assert not where.exists(), (
            f"a tree was written despite refusing `{bad}` — the criterion says "
            f"MUST NOT emit a tree"
        )


def test_the_refusal_says_why_each_key_cannot_be_a_name() -> None:
    """A refusal an author cannot act on is a crash with better manners."""
    assert "NFC" in why_not_portable("café")
    assert "64" in why_not_portable("x" * 65)
    assert "Windows" in why_not_portable("ends-in-a-dot.")
    assert "device" in why_not_portable("con")
    assert "alphabet" in why_not_portable("Name")
    assert why_not_portable("refund-desk") == ""
    assert why_not_portable("a.b_c-1") == ""


def test_a_document_carrying_payloads_is_refused_with_its_own_reason(
    tmp_path: Path,
) -> None:
    """The worked example cannot be exploded, and the reason is not "unportable".

    A payload is a directory the loader carried verbatim; what reaches the
    document is a REFERENCE — the path, the size, the type — and not the bytes.
    So the tree cannot be rebuilt from the document, and telling somebody their
    keys are unportable would send them renaming `$payload`, which is not theirs
    to rename.
    """
    where = tmp_path / "never-written"
    with pytest.raises(CarriesPayloads) as refusal:
        explode(load(EXAMPLES / "refund-desk"), where)
    said = str(refusal.value)
    assert "references payload files it does not contain" in said, said
    assert "skills" in said, said
    assert not where.exists()
    # And it is a distinct refusal, so a caller can tell the two apart.
    assert issubclass(CarriesPayloads, ExplodeRefused)


def test_it_produces_a_TREE_and_not_one_large_file(tmp_path: Path) -> None:
    """An explode that wrote everything into one YAML would satisfy every
    assertion above — the round trip would be exact, because the `.md` trimming
    that causes the residual never happens.

    Measured: setting `PROSE = frozenset()` leaves the round-trip test green and
    makes the residual test SKIP. That is a valid document-to-tree conversion and
    it is not an explosion, and the difference is the whole point of the word: a
    tree is what an author edits.
    """
    original = load(EXAMPLES / "patterns" / "quorum")
    said = explode(original, tmp_path / "exploded")
    root = tmp_path / "exploded"

    prose = sorted(p.relative_to(root).as_posix() for p in root.rglob("*.md"))
    assert prose, f"no prose file was written at all: {said.wrote}"
    assert any("instructions.md" in p for p in prose), prose

    # Each agent is its own directory, which is the Expansion Rule read
    # backwards — *a field may be a directory*.
    agents = root / "agents"
    assert agents.is_dir(), "agents did not become a folder"
    for name in original["agents"]:
        assert (agents / name).is_dir(), f"{name} did not become a directory"
        assert (agents / name / "instructions.md").exists(), name

    # And no single file holds the whole thing.
    biggest = max(p.stat().st_size for p in root.rglob("*") if p.is_file())
    whole = len(json.dumps(original))
    assert biggest < whole, (
        f"one file holds {biggest} bytes of a {whole}-byte document — that is a "
        f"conversion, not an explosion"
    )


def test_a_workspace_always_gets_a_workspace_file(tmp_path: Path) -> None:
    """Even when every top-level field turned out to be prose or a folder.

    The loader names this failure itself: a directory with an agent in it and no
    workspace around it *"is one nothing can find — `pact discover` returns none
    and `pact card` cannot publish it"*. So the top file is written regardless.

    The condition here used to be `settings or not said.wrote` — a GLOBAL
    question ("has anything been written anywhere yet") standing in for a local
    one. It gave the right answer for every valid document by accident, because
    the first thing written is always prose, and produced a workspace with no
    `workspace.yaml` for a document whose only top-level field was prose.
    """
    only_prose = tmp_path / "only-prose"
    explode({"instructions": "Answer the question."}, only_prose)
    assert (only_prose / "workspace.yaml").exists(), (
        "a tree with no workspace file is one nothing can find"
    )
    assert (only_prose / "instructions.md").exists()

    # And a nested directory with nothing but prose gets NO settings file, which
    # is the other half: `_index.yaml` holding `{}` beside an `instructions.md`
    # is a file that says nothing, and a tree an author reads should not have one.
    nested = tmp_path / "nested"
    explode(
        {"name": "w", "agents": {"a": {"instructions": "Answer.", "name": "A"}}},
        nested,
    )
    assert (nested / "agents" / "a" / "instructions.md").exists()
    assert (nested / "workspace.yaml").exists()
