"""`combine_rules_mean_one_thing` (02W §8): the six combine rules give identical
results inside a segment and when a parent combines child results, ties
included (the earliest item wins).

Random lists, cut at random places: every cut is combined on its own (a child,
a segment) and the parents join the partial values, and the answer is held to
combining every item at once. The values are drawn from a small alphabet so
ties are the common case, not the rare one. `PACT_PROPERTY_EXAMPLES` sets how
many lists each rule is tried on (2,000 by default).

Mutation: make `Combine.join` for `top-n` sort `later` before `earlier`, or
`vote` count `later`'s answers first, and the tie rows fail here.
"""

from __future__ import annotations

import os
import random
import sys
from functools import reduce
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.combine import Combine, spellings  # noqa: E402
from pact_adapters.questions import Rejected  # noqa: E402

EXAMPLES = int(os.environ.get("PACT_PROPERTY_EXAMPLES", "2000"))

RULES = [
    "keep all",
    "keep the latest",
    "merge",
    "add up",
    "vote",
    "vote, everyone agreeing",
    "top 1 highest by score",
    "top 3 lowest by score",
]


def _item(rule: Combine, rng: random.Random) -> object:
    if rule.rule == "merge":
        return {rng.choice("abcd"): rng.randint(0, 3) for _ in range(rng.randint(0, 3))}
    if rule.rule == "add-up":
        return rng.choice([rng.randint(-5, 5), rng.randint(-50, 50) / 4])
    if rule.rule == "top-n":
        return {"score": rng.randint(0, 3), "id": rng.randint(0, 10**6)}
    return rng.choice(["yes", "no", "maybe", 1, [1, 2]])


def _cuts(items: list, rng: random.Random) -> list[list]:
    """`items` split into consecutive segments, some of them empty."""
    out, at = [], 0
    while at < len(items):
        step = rng.randint(0, len(items) - at)
        out.append(items[at : at + step])
        at += step
    return out + [[]]


@pytest.mark.parametrize("written", RULES)
def test_a_rule_gives_one_result_however_the_items_were_split(written: str) -> None:
    rule = Combine.parse(written)
    rng = random.Random(f"combine-{written}")
    for _ in range(EXAMPLES):
        items = [_item(rule, rng) for _ in range(rng.randint(0, 12))]
        whole = rule.combined(items)
        segments = [reduce(rule.add, seg, rule.start()) for seg in _cuts(items, rng)]
        # A parent joins its children's partial values, in input order, in any grouping.
        left = rule.result(reduce(rule.join, segments, rule.start()))
        right = rule.result(reduce(lambda acc, s: rule.join(s, acc), reversed(segments), rule.start()))
        assert left == whole == right, (written, items)


def test_the_earliest_item_wins_a_tie() -> None:
    vote = Combine.parse("vote")
    assert vote.combined(["no", "yes", "yes", "no"]) == {"answer": "no", "share": 0.5}
    first = {"score": 2, "id": "first"}
    second = {"score": 2, "id": "second"}
    assert Combine.parse("top 1 highest by score").combined([first, second]) is first
    assert Combine.parse("top 1 lowest by score").combined([first, second]) is first
    assert Combine.parse("top 2 highest by score").combined([{"score": 1}, second, first]) == [second, first]


def test_each_rule_means_what_the_primitives_say() -> None:
    assert Combine.parse("keep-all").combined([3, None, 1]) == [3, None, 1]
    assert Combine.parse("keep-the-latest").combined(["draft 1", "draft 2"]) == "draft 2"
    assert Combine.parse("keep the latest").combined([]) is None
    assert Combine.parse("merge").combined([{"a": 1, "b": 1}, {"b": 2}]) == {"a": 1, "b": 2}
    assert Combine.parse("add up").combined([1, 2, 3]) == 6
    assert Combine.parse("add-up").combined(["1.50 USD", "2 USD"]) == "3.50 USD"
    assert Combine.parse("vote").combined(["a", "b", "b"]) == {"answer": "b", "share": 2 / 3}
    assert Combine.parse("vote, everyone agreeing").combined(["a", "b"])["answer"] is None
    assert Combine.parse("vote, everyone agreeing").combined(["a", "a"]) == {"answer": "a", "share": 1.0}
    assert Combine.parse("top 1 lowest by confidence").combined([0.9, 0.4, 0.7]) == 0.4
    assert Combine.parse("top 2 highest by total").combined(
        [{"total": "10 USD"}, {"total": "30 USD"}, {"total": "20 USD"}]
    ) == [{"total": "30 USD"}, {"total": "20 USD"}]


def test_money_in_two_currencies_is_not_added_up() -> None:
    with pytest.raises(Rejected, match="cannot add USD to EUR"):
        Combine.parse("add up").combined(["1 USD", "2 EUR"])


def test_the_spellings_are_the_schemas_and_a_rule_outside_them_is_refused() -> None:
    """One copy: the checker's `combine-rules:` list."""
    assert set(spellings()) == {"keep-all", "keep-the-latest", "merge", "add-up", "vote", "top-n"}
    with pytest.raises(Rejected, match="is not a way of combining answers"):
        Combine.parse("median")
    with pytest.raises(Rejected):
        Combine.parse("top 0 highest by score")
