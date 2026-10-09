"""The six combine rules, each meaning one thing (02W §2.0, P §3.1, F3).

Whenever several results must become one — the items of an `each`, the
branches of a `together`, the rounds of a `repeat` remembering a value — the
same closed list is used, one rule per field:

    keep-all          every result, in input order
    keep-the-latest   the newest replaces the old (the last in input order)
    merge             one record built up field by field; a later item's field
                      replaces an earlier one's
    add-up            numbers, or money in one currency, summed exactly: the
                      total keeps the most decimal places any item was written
                      with (`0.004 USD` twice is `0.008 USD`); two currencies,
                      or money with a bare number, are refused
    vote              the most common answer, with the share that agreed;
                      `vote, everyone agreeing` has an answer only when all agree
    top-n             the n best by a field, highest or lowest; top 1 is the item.
                      Ranked as a condition orders (`conditions.ordered_as`): a
                      date as a date, a time as a time, money as its figure

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

from .conditions import currency, exact, ordered_as
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
    #: top-n: the time zone a date and time written with none is read in (a
    #: workflow's `time-zone:`); with none, such a value has no order.
    zone: str | None = None

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
            # total, what is added (None: nothing yet; "" a bare number; else
            # the currency), the most decimal places written, all whole numbers.
            "add-up": (Fraction(0), None, 0, True),
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
            figure = exact(item)
            if figure is None:
                raise Rejected([f"`add up` sums figures, and {_shown(item)} is not one."])
            whole = isinstance(item, int) and not isinstance(item, bool)
            places = max(0, -int(figure.as_tuple().exponent))
            return (Fraction(figure), currency(item), places, whole)
        if self.rule == "vote":
            return ((_key(item), item, 1),)
        ranked = self._rank_of(item)
        return () if ranked is None else ((ranked, item),)

    def join(self, earlier: Any, later: Any) -> Any:
        """Two partial values, `earlier`'s items before `later`'s."""
        if self.rule == "keep-all":
            return tuple(earlier) + tuple(later)
        if self.rule == "keep-the-latest":
            return later or earlier
        if self.rule == "merge":
            return {**earlier, **later}
        if self.rule == "add-up":
            (a, ak, ap, aw), (b, bk, bp, bw) = earlier, later
            if ak is not None and bk is not None and ak != bk:
                if ak and bk:
                    raise Rejected([f"`add up` cannot add {ak} to {bk}: nothing here converts one into the other."])
                raise Rejected([
                    f"`add up` cannot add an amount in {ak or bk} to a bare number: write every "
                    f"figure with its currency, like `2 {ak or bk}`."
                ])
            return (a + b, bk if ak is None else ak, max(ap, bp), aw and bw)
        if self.rule == "vote":
            counts = {key: [value, count] for key, value, count in earlier}
            for key, value, count in later:
                counts.setdefault(key, [value, 0])[1] += count
            return tuple((key, value, count) for key, (value, count) in counts.items())
        return tuple(self._best_first((*earlier, *later), f"`top {self.n}`")[: self.n])

    def ranked(self, items: Iterable[Any], asked_by: str = "") -> list[Any]:
        """Every item, best first by `by` as `top-n` ranks them (the earliest of
        equals first), then, in input order, every item with nothing to rank it
        by: a list worked through in order (`ordered-by:` on an `each`), where
        no item is left out. `asked_by` names what asked, in a refusal (the
        rule's own words, `top <n>`, when unwritten)."""
        items = list(items)
        lifted = [(self._rank_of(item), item) for item in items]
        best = self._best_first([p for p in lifted if p[0] is not None], asked_by or f"`top {self.n}`")
        return [item for _, item in best] + [item for rank, item in lifted if rank is None]

    def _rank_of(self, item: Any) -> tuple[str, Any] | None:
        return ordered_as(item.get(self.by) if isinstance(item, Mapping) else item, self.zone)

    def _best_first(self, ranked: Iterable[tuple[Any, Any]], said_by: str) -> list[tuple[Any, Any]]:
        """`ranked` (rank, item) pairs best first, refused when they have no order
        between them (two kinds, or money in two currencies)."""
        ranked = list(ranked)
        kinds = sorted({kind for (kind, _), _ in ranked})
        currencies = {k for k in kinds if k not in _TIMES} - {""}
        if len({_ranks_as(k) for k in kinds}) > 1 or len(currencies) > 1:
            said = " against ".join(_said(k) for k in kinds)
            raise Rejected([f"{said_by} cannot rank {said} by `{self.by}`: they have no order between them."])
        # sorted() is stable both ways round: the earliest of equals stays first.
        return sorted(ranked, key=lambda p: p[0][1], reverse=not self.lowest)

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
            total, kind, places, whole = partial
            if kind:
                return f"{_decimal(total, places)} {kind}"
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


#: What [`ordered_as`] calls a date or a time; any other kind is a figure's.
_TIMES = ("date", "moment", "time")


def _ranks_as(kind: str) -> str:
    """A date, a moment and a time rank only among their own kind; every figure
    (money and bare numbers, as a condition compares them) among figures."""
    return kind if kind in _TIMES else "figure"


def _said(kind: str) -> str:
    return {"date": "a date", "moment": "a date and time", "time": "a time of day", "": "a number"}.get(
        kind, f"money in {kind}"
    )


def _decimal(total: Fraction, places: int) -> str:
    """`total` written with `places` decimals, exactly: every item had at most
    that many, so their sum has too."""
    scaled = total * 10**places
    assert scaled.denominator == 1, (total, places)
    digits = str(abs(scaled.numerator)).rjust(places + 1, "0")
    sign = "-" if scaled < 0 else ""
    return f"{sign}{digits[:-places]}.{digits[-places:]}" if places else f"{sign}{digits}"


def _key(value: Any) -> str:
    """Two answers are the same answer when they are the same value."""
    return json.dumps(value, sort_keys=True, default=str)


def _shown(item: Any) -> str:
    text = json.dumps(item, default=str)
    return f"'{text[:60]}…'" if len(text) > 60 else f"'{text}'"
