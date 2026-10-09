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

import datetime as dt
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

#: Each rule, and the kind of items it is tried on.
RULES = [
    ("keep all", ""),
    ("keep the latest", ""),
    ("merge", ""),
    ("add up", ""),
    ("add up", "money"),
    ("vote", ""),
    ("vote, everyone agreeing", ""),
    ("top 1 highest by score", ""),
    ("top 3 lowest by score", ""),
    ("top 1 highest by due", "dates"),
    ("top 2 lowest by at", "moments"),
]


def _item(rule: Combine, kind: str, rng: random.Random) -> object:
    if rule.rule == "merge":
        return {rng.choice("abcd"): rng.randint(0, 3) for _ in range(rng.randint(0, 3))}
    if rule.rule == "add-up":
        if kind == "money":
            # Sub-cent amounts, as a per-request model cost is written.
            return rng.choice([f"{rng.randint(0, 9) / 1000:.3f} USD", f"{rng.randint(-50, 50)} USD"])
        return rng.choice([rng.randint(-5, 5), rng.randint(-50, 50) / 4])
    if rule.rule == "top-n":
        if kind == "dates":
            # Every date in 2026: ranked by its year alone they would all tie.
            return {"due": (dt.date(2026, 1, 1) + dt.timedelta(days=rng.randint(0, 364))).isoformat()}
        if kind == "moments":
            day = dt.datetime(2026, 1, 1, tzinfo=dt.UTC) + dt.timedelta(hours=rng.randint(0, 24 * 90))
            return {"at": day.isoformat(), "id": rng.randint(0, 10**6)}
        return {"score": rng.randint(0, 3), "id": rng.randint(0, 10**6)}
    return rng.choice(["yes", "no", "maybe", 1, [1, 2]])


def _best(rule: Combine, items: list) -> object:
    """What `top n` means, written plainly: sort by the field as a date, earliest
    of equals first."""
    key = dt.datetime.fromisoformat if rule.by == "at" else dt.date.fromisoformat
    ranked = sorted(items, key=lambda i: key(i[rule.by]), reverse=not rule.lowest)[: rule.n]
    return (ranked[0] if ranked else None) if rule.n == 1 else ranked


def _cuts(items: list, rng: random.Random) -> list[list]:
    """`items` split into consecutive segments, some of them empty."""
    out, at = [], 0
    while at < len(items):
        step = rng.randint(0, len(items) - at)
        out.append(items[at : at + step])
        at += step
    return out + [[]]


@pytest.mark.parametrize(("written", "kind"), RULES)
def test_a_rule_gives_one_result_however_the_items_were_split(written: str, kind: str) -> None:
    rule = Combine.parse(written)
    rng = random.Random(f"combine-{written}-{kind}")
    for _ in range(EXAMPLES):
        items = [_item(rule, kind, rng) for _ in range(rng.randint(0, 12))]
        whole = rule.combined(items)
        if kind in ("dates", "moments"):
            assert whole == _best(rule, items), (written, items)
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


def test_money_with_a_bare_number_is_not_added_up() -> None:
    with pytest.raises(Rejected, match="cannot add an amount in USD to a bare number"):
        Combine.parse("add up").combined(["1 USD", 2])
    with pytest.raises(Rejected, match="cannot add an amount in USD to a bare number"):
        Combine.parse("add up").combined([2, "1 USD"])


def test_money_adds_up_exactly_to_the_places_it_was_written_in() -> None:
    """No fixed two decimals: a sub-cent cost, a three-decimal currency and one
    with none each keep what was written."""
    add = Combine.parse("add up")
    assert add.combined(["0.004 USD", "0.004 USD"]) == "0.008 USD"
    assert add.combined(["0.125 KWD", "0.001 KWD"]) == "0.126 KWD"
    assert add.combined(["1000 JPY", "1 JPY"]) == "1001 JPY"
    assert add.combined(["40.00 USD", "2.5 USD"]) == "42.50 USD"
    assert add.combined(["$0.10"] * 3) == "0.30 USD"
    assert add.combined(["-0.30 USD", "0.10 USD"]) == "-0.20 USD"
    assert add.combined([0.1, 0.2]) == 0.3


def test_top_n_ranks_a_date_as_a_date() -> None:
    """Not by its year: 30 December is later than 5 January 2026."""
    early, late = {"due": "2026-01-05"}, {"due": "2026-12-30"}
    assert Combine.parse("top 1 highest by due").combined([early, late]) is late
    march, january = {"at": "2026-03-01T09:00:00+00:00"}, {"at": "2026-01-01T09:00:00+00:00"}
    assert Combine.parse("top 1 lowest by at").combined([march, january]) is january
    assert Combine.parse("top 1 highest by at").combined([{"at": "09:30"}, {"at": "14:05"}]) == {"at": "14:05"}
    with pytest.raises(Rejected, match="cannot rank a number against a date"):
        Combine.parse("top 1 highest by due").combined([early, {"due": 3}])


def test_a_list_ranked_through_keeps_every_item_and_ranks_as_top_n_does() -> None:
    """`Combine.ranked`: best first as `top-n` ranks (the earliest of equals first),
    then every item with nothing to rank it by, in input order: none left out."""
    items = [{"id": "a", "s": 2}, {"id": "b"}, {"id": "c", "s": 5}, {"id": "d", "s": 2}, {"id": "e", "s": None}]
    high = Combine(rule="top-n", by="s")
    assert [i["id"] for i in high.ranked(items)] == ["c", "a", "d", "b", "e"]
    assert [i["id"] for i in Combine(rule="top-n", by="s", lowest=True).ranked(items)] == ["a", "d", "c", "b", "e"]
    assert high.ranked(items)[:1] == [Combine.parse("top 1 highest by s").combined(items)]
    with pytest.raises(Rejected, match="^`ordered-by: s` cannot rank a number against a date"):
        try:
            high.ranked([{"s": 1}, {"s": "2026-01-05"}], "`ordered-by: s`")
        except Rejected as exc:
            raise Rejected([" ".join(exc.problems)]) from None
    # A date and time with no zone has no order, unless the rule is told the zone it is read in.
    naive = [{"s": "2026-01-01T09:00:00"}, {"s": "2026-03-01T09:00:00"}]
    assert Combine(rule="top-n", by="s").ranked(naive) == naive
    assert Combine(rule="top-n", by="s", zone="Europe/London").ranked(naive) == naive[::-1]


def test_the_spellings_are_the_schemas_and_a_rule_outside_them_is_refused() -> None:
    """One copy: the checker's `combine-rules:` list."""
    assert set(spellings()) == {"keep-all", "keep-the-latest", "merge", "add-up", "vote", "top-n"}
    with pytest.raises(Rejected, match="is not a way of combining answers"):
        Combine.parse("median")
    with pytest.raises(Rejected):
        Combine.parse("top 0 highest by score")
