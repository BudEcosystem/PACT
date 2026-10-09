"""The six combine rules, each meaning one thing (02W §2.0, P §3.1, F3).

Whenever several results must become one — the items of an `each`, the
branches of a `together`, the rounds of a `repeat` remembering a value — the
same closed list is used, one rule per field:

    keep-all          every result, in input order
    keep-the-latest   the newest replaces the old (the last in input order)
    merge             one record built up field by field; a later item's field
                      replaces an earlier one's
    add-up            numbers (or money in one currency) summed
    vote              the most common answer, with the share that agreed;
                      `vote, everyone agreeing` has an answer only when all agree
    top-n             the n best by a field, highest or lowest; top 1 is the item

**The tie rule is the earliest item wins**: two answers with as many votes, two
items with the same figure — the one that came first in input order is chosen.

**A rule gives the same result however the items were split.** Each rule is a
fold with a partial value: `start()`, `add(partial, item)`, `join(earlier,
later)`, `result(partial)`. `join` is associative and respects input order, so
items combined inside a segment and segments combined by a parent come to what
combining every item at once comes to, ties included
(`combine_rules_mean_one_thing`). The engine wraps these as its reducers; it
does not write a seventh.

The spellings are read from `spec/schema.yaml`'s `combine-rules:` — the one
copy the checker reads too — so a rule `pact check` passed is a rule this
reads. Which items count (a failed item is kept, marked failed, by `keep-all`)
is the engine's: these functions combine the values they are given.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache, reduce
from typing import Any, Iterable, Mapping

import yaml

from .conditions import _currency, amount
from .loader import schema_path
from .questions import Rejected

__all__ = ["Combine", "spellings"]


@lru_cache(maxsize=1)
def spellings() -> dict[str, tuple[str, ...]]:
    """Every spelling of every rule, from the schema's one copy."""
    groups = yaml.safe_load(schema_path().read_text(encoding="utf-8"))["groups"]
    written = groups["stage"]["fields"]["combines-by"]["combine-rules"]
    return {str(rule): tuple(str(s) for s in said) for rule, said in written.items()}


def _spelt_as(written: str, spelling: str) -> dict[str, str] | None:
    """The author's words for `<n>` and `<field>` when `written` is `spelling`
    word for word (case aside), as the checker's `spelt_as` reads it."""
    said, want = written.split(), spelling.split()
    if len(said) != len(want):
        return None
    filled: dict[str, str] = {}
    for s, w in zip(said, want):
        if w == "<n>":
            if not s.isdigit() or int(s) < 1:
                return None
            filled["n"] = s
        elif w.startswith("<") and w.endswith(">"):
            filled[w[1:-1]] = s
        elif s.lower() != w.lower():
            return None
        else:
            filled.setdefault("words", "")
            filled["words"] += f" {w.lower()}"
    return filled


@dataclass(frozen=True)
class Combine:
    """One combine rule, read from what the author wrote."""

    rule: str
    #: top-n: how many, by which field, lowest first or highest.
    n: int = 0
    by: str = ""
    lowest: bool = False
    #: vote: only an answer everyone agreed on counts.
    everyone: bool = False

    @staticmethod
    def parse(written: str) -> "Combine":
        text = str(written).strip()
        for rule, said in spellings().items():
            for spelling in said:
                filled = _spelt_as(text, spelling)
                if filled is None:
                    continue
                words = filled.get("words", "")
                return Combine(
                    rule=rule,
                    n=int(filled.get("n", 0)),
                    by=filled.get("field", ""),
                    lowest=" lowest" in words,
                    everyone=" everyone" in words,
                )
        firsts = ", ".join(f"`{s[0]}`" for s in spellings().values())
        raise Rejected([f"'{text}' is not a way of combining answers. Write one of: {firsts}."])

    # ── the fold ──────────────────────────────────────────────────────────

    def start(self) -> Any:
        """The partial value of no items."""
        return {
            "keep-all": (),
            "keep-the-latest": (),
            "merge": {},
            "add-up": (Fraction(0), "", True),
            "vote": (),
            "top-n": (),
        }[self.rule]

    def lift(self, item: Any) -> Any:
        """The partial value of one item."""
        if self.rule in ("keep-all", "keep-the-latest"):
            return (item,)
        if self.rule == "merge":
            if not isinstance(item, Mapping):
                raise Rejected([f"`merge` builds one record from records, and {_shown(item)} is not one."])
            return dict(item)
        if self.rule == "add-up":
            figure = amount(item)
            if figure is None:
                raise Rejected([f"`add up` sums figures, and {_shown(item)} is not one."])
            whole = isinstance(item, int) and not isinstance(item, bool)
            return (Fraction(figure) if not whole else Fraction(item), _currency(item), whole)
        if self.rule == "vote":
            return ((_key(item), item, 1),)
        figure = amount(item.get(self.by) if isinstance(item, Mapping) else item)
        return () if figure is None else ((figure, item),)

    def join(self, earlier: Any, later: Any) -> Any:
        """Two partial values, `earlier`'s items before `later`'s."""
        if self.rule == "keep-all":
            return tuple(earlier) + tuple(later)
        if self.rule == "keep-the-latest":
            return later or earlier
        if self.rule == "merge":
            return {**earlier, **later}
        if self.rule == "add-up":
            (a, ac, aw), (b, bc, bw) = earlier, later
            if ac and bc and ac != bc:
                raise Rejected([f"`add up` cannot add {ac} to {bc}: nothing here converts one into the other."])
            return (a + b, ac or bc, aw and bw)
        if self.rule == "vote":
            counts = {key: [value, count] for key, value, count in earlier}
            for key, value, count in later:
                counts.setdefault(key, [value, 0])[1] += count
            return tuple((key, value, count) for key, (value, count) in counts.items())
        ranked = sorted((*earlier, *later), key=lambda p: p[0] if self.lowest else -p[0])
        return tuple(ranked[: self.n])

    def add(self, partial: Any, item: Any) -> Any:
        return self.join(partial, self.lift(item))

    def result(self, partial: Any) -> Any:
        """What the items come to."""
        if self.rule == "keep-all":
            return list(partial)
        if self.rule == "keep-the-latest":
            return partial[0] if partial else None
        if self.rule == "merge":
            return dict(partial)
        if self.rule == "add-up":
            total, currency, whole = partial
            if currency:
                return f"{float(total):.2f} {currency}"
            return int(total) if whole else float(total)
        if self.rule == "vote":
            cast = sum(count for _, _, count in partial)
            if not cast:
                return {"answer": None, "share": 0.0}
            # max() keeps the first of equals: the earliest answer wins a tie.
            _, value, count = max(partial, key=lambda e: e[2])
            if self.everyone and count != cast:
                value = None
            return {"answer": value, "share": count / cast}
        best = [item for _, item in partial]
        if self.n == 1:
            return best[0] if best else None
        return best

    def combined(self, items: Iterable[Any]) -> Any:
        """Every item at once, in input order."""
        return self.result(reduce(self.add, items, self.start()))


def _key(value: Any) -> str:
    """Two answers are the same answer when they are the same value."""
    return json.dumps(value, sort_keys=True, default=str)


def _shown(item: Any) -> str:
    text = json.dumps(item, default=str)
    return f"'{text[:60]}…'" if len(text) > 60 else f"'{text}'"
