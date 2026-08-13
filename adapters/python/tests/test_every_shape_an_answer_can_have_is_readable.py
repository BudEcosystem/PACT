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
