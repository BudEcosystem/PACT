"""Every shape `_SPELLINGS` accepts, `Shape.read` can read (A12).

Two hand-maintained lists in one class, held to each other by nothing.
`_SPELLINGS` accepted `images`, `audio` and `file`; `read` branched on
`yes-or-no`, `text`, `money`, `number`, `whole-number` and `one-of` and fell
through to `raise Rejected` for the other three.

`examples/refund-desk/agents/refund-desk/agent.yaml` declares
`photos: list of images`. **The flagship could not read its own declared
input** — and D16 names the four modalities as a headline capability.

The fix is not three more branches. It is deciding what one of these values IS
on the wire, once, for both ports: a path to a file inside this workspace,
written relative to its root. B19 is the same question about currency answered
four different ways in two ports, and this is where that repeats if nobody
decides.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.questions import _SPELLINGS, Rejected, Shape  # noqa: E402

REPO = Path(__file__).resolve().parents[3]


def shape_for(kind: str) -> Shape:
    return Shape(kind=kind, choices=("a", "b") if kind == "one-of" else ())


@pytest.mark.parametrize("kind", sorted(_SPELLINGS))
def test_every_shape_the_spellings_accept_can_be_read(kind: str) -> None:
    """The whole test. A shape an author can WRITE and nothing can READ is a
    promise the format cannot keep, and it shipped on the three modalities the
    project advertises."""
    value = {
        "yes-or-no": "yes",
        "text": "a sentence",
        "money": "25.00 USD",
        "number": "1.5",
        "whole-number": "3",
        "images": "evals/attachments/receipt.png",
        "audio": "evals/attachments/call.wav",
        "file": "evals/attachments/policy.pdf",
        "agent": "refund-desk",
    }[kind]
    assert shape_for(kind).read(value) is not None


def test_the_flagship_can_read_its_own_declared_input() -> None:
    """Not a synthetic shape: the line the worked example actually writes."""
    agent = yaml.safe_load(
        (REPO / "examples/refund-desk/agents/refund-desk/agent.yaml").read_text()
    )
    accepts = agent.get("accepts") or {}
    assert "photos" in accepts, "the worked example no longer declares `photos:`"
    written = str(accepts["photos"])
    kind = next((k for k, spellings in _SPELLINGS.items() if written in spellings), None)
    assert kind is not None, f"`{written}` is not a shape the spellings accept"
    assert shape_for(kind).read("evals/attachments/receipt.png")


@pytest.mark.parametrize(
    "climbing",
    ["/etc/passwd", "../../secrets.txt", "~/private.png", "https://elsewhere/x.png"],
)
def test_a_path_that_leaves_the_workspace_is_refused_with_what_to_type(climbing: str) -> None:
    """The same rule `file-name` already makes one level down. A portable folder
    whose answer names `/etc/passwd` is neither portable nor safe."""
    with pytest.raises(Rejected) as e:
        shape_for("file").read(climbing)
    assert "evals/attachments/receipt.png" in str(e.value), (
        "the refusal has to say what to type instead: " + str(e.value)
    )


def test_the_three_file_shapes_read_a_value_the_same_way() -> None:
    """One wire form. `images`, `audio` and `file` differ in what the model is
    TOLD the file is, not in how it is written down — and three spellings for
    one form is how the currency divergence happened one type over."""
    written = "evals/attachments/receipt.png"
    read = {kind: shape_for(kind).read(written) for kind in ("images", "audio", "file")}
    assert len(set(read.values())) == 1, read


def test_a_path_is_normalised_but_never_rewritten_into_something_else() -> None:
    assert shape_for("file").read("./evals//attachments/receipt.png") == (
        "evals/attachments/receipt.png"
    )
    assert shape_for("file").read("evals/attachments/receipt.png") == (
        "evals/attachments/receipt.png"
    )


# ───────────────────────── the line a person is told to type must be typeable


def test_no_shape_tells_a_person_to_type_a_name_from_another_workspace() -> None:
    """`Shape.example()` is not decoration — it is the line a person is told to
    type, word for word:

        'who-takes-it' has not been answered: 'who' is missing.
        Add `who: refund-desk`.

    Measured on a hospital workspace holding `triage` and `x-ray` and no refund
    desk of any kind. The `agent` shape's example was the literal string
    `refund-desk` — the flagship example's own agent — so every workspace on
    earth was told to type a name out of somebody else's tree.

    That is R56's defect exactly: *"the diagnostic hardcoded `allow-egress: []`,
    so a workspace saying `[judge]` was told its own file said something it does
    not, and an author who opens the file and sees otherwise stops believing the
    checker."* Here it is one layer worse, because the reader is not the author —
    it is a clinician with a patient waiting, being told to type a word that
    resolves to nothing.

    Every other row in that table is safe in a different way. `25.00 USD`, `3`
    and `yes` are literals anybody can type anywhere; `a sentence`, `a picture`
    and `a recording` read as descriptions of a kind. Only `agent` claimed to be
    a value and named one that a given workspace almost certainly has not got.
    """
    from pact_adapters.questions import _EXAMPLE

    workspaces = (REPO / "examples", REPO / "tests/trees")
    named = {
        p.parent.name
        for root in workspaces
        for p in root.rglob("agents/*/agent.yaml")
    }
    assert named, "the fixture workspaces should hold some agents"

    offenders = sorted(k for k, v in _EXAMPLE.items() if v in named)
    assert not offenders, (
        f"the example for {offenders} is the name of a real agent in a shipped "
        f"tree, and it is printed to a person answering in THEIR workspace.\n"
        f"  fix: make it read as the kind of thing wanted, the way `a sentence` "
        f"and `a recording` do — a placeholder that cannot be mistaken for a "
        f"name is better than one that names somebody else's agent."
    )


def test_every_shape_still_offers_something_to_type() -> None:
    """The control. Removing a misleading example must not leave an empty one:
    a fix line with nothing after the colon teaches less than a wrong one."""
    from pact_adapters.questions import _EXAMPLE, Shape

    for kind in _EXAMPLE:
        got = Shape(kind=kind).example()
        assert got and got.strip(), f"{kind} offers nothing to type"
