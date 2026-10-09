"""The refusal of a shape names only spellings `Shape.parse` accepts.

A model or a person told what to write instead writes what it was told. The
refusal used to list the shapes' descriptions — "an amount of money, like
`25.00 USD`", "one or more pictures", "the name of one of this workspace's
agents" — none of which parse, and the one value in backticks was an example
answer, not a shape. Found live in Bud Flow (complex scenario 64): a helper's
`answers-with: {estimate: USD}` was refused, the model wrote `25.00 USD` as
the fix said, and six retries passed before a helper could be built.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.questions import Rejected, Shape  # noqa: E402


def _refusal(written: str) -> str:
    with pytest.raises(Rejected) as refused:
        Shape.parse(written)
    return str(refused.value)


@pytest.mark.parametrize("written", ["USD", "a price", "list of prices", "a price, optional"])
def test_every_shape_the_refusal_offers_parses(written: str) -> None:
    said = _refusal(written)
    listed = said.split("Use one of: ", 1)[1].split(" — or ", 1)[0]
    offered = [o.strip() for o in listed.split(",")]
    assert offered, said
    for option in offered:
        Shape.parse(option)  # raises if the refusal names something that does not parse
    choice = re.search(r"`(one of [^`]+)`", said)
    assert choice is not None, said
    assert Shape.parse(choice.group(1)).kind == "one-of"


def test_the_example_answer_is_not_offered_as_a_shape() -> None:
    said = _refusal("USD")
    listed = said.split("Use one of: ", 1)[1].split(" — or ", 1)[0]
    assert "25.00 USD" not in listed
    assert "`money`" in said, "the refusal must say which shape an amount of money is"
