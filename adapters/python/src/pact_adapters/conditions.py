"""One condition grammar, read by one function (02W §2.6, F1 reopened).

An approval rule (`policy.ask-a-person[].when`), a routing rule
(`stage.by[].rules[].when`), a repeat's `until:` and a port's `only-when:` all
write the same `when-this` lines, and every one of them is answered here:

    is               equal to this
    is-one-of        equal to any of these
    more-than        above this
    less-than        below this
    contains-any-of  text or a list in which any of these words appears
    is-empty         missing, blank or an empty list (`yes`), or the opposite

The right-hand side is a **comparand** (02W §2.0): a figure written the way the
left-hand side is declared (`5000 USD`, `85%`, `0.85`, `enterprise`), or a map
with exactly one of `value: <binding>`, `now-plus: <duration>` and
`now-minus: <duration>`. There are no combinators: every line of a `when:` must
hold, and "or" is two rules. There is no arithmetic.

What the caller supplies, and nothing else:

* the left-hand value — an argument of the call for a policy (`arg:`), what a
  binding reads for every other position (`value:`), or [`ABSENT`];
* `read`, which answers a `{value: <binding>}` comparand (and, in [`all_hold`]
  and [`choose`], each line's own `value:`);
* `now`, the moment `now-plus:` and `now-minus:` count from. It is the caller's
  so a replay reads the journaled `now` and decides what the first pass decided;
* `zone`, the zone a date is read in (the value's `in-time-zone:` or the
  workspace's `time-zone:`). A length of time written in days moves the date in
  that zone — `{now-plus: 1 day}` is the same time tomorrow there, 23 or 25 hours
  away across a clock change — and one written in hours, minutes or seconds is
  that long on the clock.

Every answer is `True`, `False` or `None`. `None` means the line cannot be
decided — a figure that is no figure, two currencies, a `now-plus:` with no
`now`, a value that is there but null — and what that means is the caller's: a
gate stops the call and asks (a mistake must never become a disabled gate), a
rules rung stops deciding. A value that is not there ([`ABSENT`]: a call that
does not carry the argument) holds nothing but `is-empty: yes`; one that is
there as null is empty, and against every other word cannot be told, so a
refund whose `amount` is null is asked about rather than let through.

What is ordered: a figure (a number, a percentage, money; two currencies are
not compared), a date, a date and time, and a time of day (`14:30`, read as a
time, never by its hour). A date against a date and time compares dates in the
zone; a time of day compares with a time of day only.

`pact check` refuses the shapes that cannot compare where it can see both sides
(`loader/compared-in-the-wrong-shape`, WF-18); this module answers what is left
at run time, with the same reading on every position.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Iterable, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .limits import seconds
from .yes_no import said_yes

__all__ = [
    "ABSENT",
    "WORDS",
    "Chosen",
    "RouteRule",
    "Rung",
    "all_hold",
    "amount",
    "choose",
    "compares",
    "currency",
    "exact",
    "holds",
    "ordered_as",
]

#: The six condition words, in 03's order.
WORDS = ("is", "is-one-of", "more-than", "less-than", "contains-any-of", "is-empty")


class _Absent:
    """A value that is not there: a call that does not carry the argument, a
    binding that read nothing."""

    _one: "_Absent | None" = None

    def __new__(cls) -> "_Absent":
        if cls._one is None:
            cls._one = super().__new__(cls)
        return cls._one

    def __repr__(self) -> str:
        return "ABSENT"


ABSENT: Any = _Absent()

#: How a `{value: <binding>}` is read: the value, or [`ABSENT`].
Read = Callable[[str], Any]


def compares(line: Mapping[str, Any]) -> bool:
    """Whether this line compares anything (one of the six words is written)."""
    return any(word in line for word in WORDS)


def holds(
    line: Mapping[str, Any],
    value: Any = ABSENT,
    *,
    read: Read | None = None,
    now: _dt.datetime | None = None,
    zone: str | None = None,
) -> bool | None:
    """Does `value` meet this line's comparison? `None` when it cannot be told.

    A line with no comparison word holds: it is about the call (a policy's
    `tool:` alone) and says nothing about a value."""
    for word in WORDS:
        if word not in line:
            continue
        written = line[word]
        if word == "is-empty":
            return _empty(value) == said_yes(written)
        if value is ABSENT:
            return False
        if value is None:
            return None
        if word == "contains-any-of":
            return _contains(value, written)
        if word == "is-one-of":
            wanted = written if isinstance(written, (list, tuple)) else [written]
            answers = [_equal(value, _comparand(w, read, now, zone), zone) for w in wanted]
            if any(a is True for a in answers):
                return True
            return None if any(a is None for a in answers) else False
        against = _comparand(written, read, now, zone)
        if word == "is":
            return _equal(value, against, zone)
        order = _order(value, against, zone)
        if order is None:
            return None
        return order > 0 if word == "more-than" else order < 0
    return True


def all_hold(
    lines: Iterable[Mapping[str, Any]],
    read: Read,
    *,
    now: _dt.datetime | None = None,
    zone: str | None = None,
) -> bool | None:
    """Every `value:` line holds (a route rule's `when:`, an `until:`, an
    `only-when:`). One line that fails decides it; else one that cannot be told
    leaves it undecided."""
    undecided = False
    for line in lines:
        said = line.get("value")
        value = read(str(said).strip()) if said is not None else ABSENT
        answer = holds(line, value, read=read, now=now, zone=zone)
        if answer is False:
            return False
        undecided |= answer is None
    return None if undecided else True


# ── decide by written rules (02W §2.5) ───────────────────────────────────────


@dataclass(frozen=True)
class RouteRule:
    """One routing rule: its conditions (every one must hold), its label, why."""

    choose: str
    when: tuple[Mapping[str, Any], ...] = ()
    because: str = ""

    @staticmethod
    def from_written(raw: Mapping[str, Any]) -> "RouteRule":
        return RouteRule(
            choose=str(raw.get("choose") or "").strip(),
            when=tuple(w for w in raw.get("when") or () if isinstance(w, Mapping)),
            because=str(raw.get("because") or "").strip(),
        )


@dataclass(frozen=True)
class Rung:
    """One way of deciding, tried in order (`stage.by:`). Written rules only,
    until the model and person rungs arrive."""

    rules: tuple[RouteRule, ...] = ()

    @staticmethod
    def from_written(raw: Mapping[str, Any]) -> "Rung":
        return Rung(rules=tuple(RouteRule.from_written(r) for r in raw.get("rules") or () if isinstance(r, Mapping)))


@dataclass(frozen=True)
class Chosen:
    """What a rules rung decided: a label and its `because:`, or no label —
    none held (`undecided` empty: the decision passes to the next rung), or a
    rule could not be read (`undecided` says which, and the rung decides
    nothing rather than skip a rule it could not read)."""

    label: str | None
    because: str = ""
    undecided: str = ""


def choose(
    rules: Iterable[RouteRule],
    read: Read,
    *,
    now: _dt.datetime | None = None,
    zone: str | None = None,
) -> Chosen:
    """The first rule whose conditions all hold picks its label."""
    for rule in rules:
        answer = all_hold(rule.when, read, now=now, zone=zone)
        if answer is True:
            return Chosen(rule.choose, rule.because)
        if answer is None:
            return Chosen(
                None,
                undecided=f"the rule choosing '{rule.choose}' could not be read against "
                "these values, so the rules decide nothing here",
            )
    return Chosen(None)


# ── reading a value ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Moment:
    """`now` plus or minus a length of time, in the zone it is read in."""

    at: _dt.datetime


def _comparand(written: Any, read: Read | None, now: _dt.datetime | None, zone: str | None) -> Any:
    """The right-hand side, read: a binding's value, a moment, or as written.
    [`ABSENT`] when it names a value nobody can read here."""
    if not isinstance(written, Mapping):
        return written
    if "value" in written:
        return read(str(written["value"]).strip()) if read is not None else ABSENT
    for key, sign in (("now-plus", 1), ("now-minus", -1)):
        if key in written:
            if now is None:
                return ABSENT
            return _Moment(_moved(now, written[key], sign, zone))
    return ABSENT


#: A length of time written in days alone: it moves the date, not the clock.
_DAYS = re.compile(r"^\s*(\d+)\s*(?:d|day|days)\s*$", re.IGNORECASE)


def _moved(now: _dt.datetime, length: Any, sign: int, zone: str | None) -> _dt.datetime:
    here = _in_zone(now if now.tzinfo else now.replace(tzinfo=_dt.UTC), zone)
    days = _DAYS.match(str(length))
    if days:
        wall = here.replace(tzinfo=None) + _dt.timedelta(days=sign * int(days.group(1)))
        return wall.replace(tzinfo=here.tzinfo)
    span = seconds(length)
    if span is None:
        raise ValueError(f"'{length}' is not a length of time")
    # On the clock: Python adds a timedelta to an aware time as wall time, which
    # is the calendar reading above; an hour is an hour only in UTC.
    return (here.astimezone(_dt.UTC) + _dt.timedelta(seconds=sign * span)).astimezone(here.tzinfo)


def _zone(zone: str | None) -> _dt.tzinfo | None:
    if not zone:
        return None
    try:
        return ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _in_zone(moment: _dt.datetime, zone: str | None) -> _dt.datetime:
    tz = _zone(zone)
    return moment.astimezone(tz) if tz is not None else moment


#: A date as ISO 8601 begins (`2026-10-09`, `2026-10-09T14:30:00-05:00`).
_DATE = re.compile(r"^\s*\d{4}-\d{2}-\d{2}")
#: A time of day (`14:30`, `9:05`, `14:30:15`): the spelling the loader reads
#: as one (`pact_loader::conditions::looks_like_a_time`), and the fractional
#: seconds a value read through `Shape` may carry (`14:30:00.500000`).
_TIME = re.compile(r"^\s*(\d{1,2})(:\d{2}(?::\d{2}(?:\.\d+)?)?)\s*$")


def _when(value: Any, zone: str | None) -> _dt.date | _dt.datetime | _dt.time | None:
    """A date, a date and time (an aware moment), or a time of day. A date and
    time written with no zone is read in `zone`, and is no moment without one."""
    if isinstance(value, _Moment):
        return value.at
    if isinstance(value, _dt.time):
        return value.replace(tzinfo=None)
    if isinstance(value, str) and (clock := _TIME.match(value)):
        try:
            return _dt.time.fromisoformat(clock.group(1).zfill(2) + clock.group(2))
        except ValueError:
            return None
    if isinstance(value, _dt.datetime):
        moment = value
    elif isinstance(value, _dt.date):
        return value
    elif isinstance(value, str) and _DATE.match(value):
        text = value.strip().replace("Z", "+00:00")
        try:
            if len(text) == 10:
                return _dt.date.fromisoformat(text)
            moment = _dt.datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    if moment.tzinfo is None:
        tz = _zone(zone)
        if tz is None:
            return None
        moment = moment.replace(tzinfo=tz)
    return moment


def ordered_as(value: Any, zone: str | None = None) -> tuple[str, Any] | None:
    """What `value` is ordered as, and the thing to order it by: `("date", d)`,
    `("moment", aware datetime)`, `("time", t)`, or `("<currency>", number)` for
    a figure (`""` for a number or a percentage). `None` for a value with no
    order: no figure, or a date or time that cannot be read here (a date and
    time with no zone and no `zone`), which is never read by its year.

    The one reading of order: `more-than:`/`less-than:` and `top <n> ... by`
    (`combine`) both go through it."""
    when = _when(value, zone)
    if isinstance(when, _dt.datetime):
        return ("moment", when)
    if isinstance(when, _dt.date):
        return ("date", when)
    if isinstance(when, _dt.time):
        return ("time", when)
    if isinstance(value, str) and (_DATE.match(value) or _TIME.match(value)):
        return None
    figure = _figure(value)
    return None if figure is None else (figure[1], figure[0])


def _order(value: Any, against: Any, zone: str | None) -> int | None:
    """-1, 0 or 1 for `value` against `against`, in the value's own shape."""
    if against is ABSENT or against is None:
        return None
    left, right = ordered_as(value, zone), ordered_as(against, zone)
    if left is None or right is None:
        return None
    (lk, lv), (rk, rv) = left, right
    if {lk, rk} == {"date", "moment"}:
        # A date against a moment: compared by the date, in the zone.
        lv = _in_zone(lv, zone).date() if lk == "moment" else lv
        rv = _in_zone(rv, zone).date() if rk == "moment" else rv
    elif _TEMPORAL & {lk, rk} and lk != rk:
        return None  # a time of day against a date, a figure against either
    elif lk and rk and lk != rk:
        return None  # two currencies: nothing here converts one into the other
    return (lv > rv) - (lv < rv)


#: The kinds [`ordered_as`] gives a date or a time; every other kind is a figure.
_TEMPORAL = frozenset({"date", "moment", "time"})


def _equal(value: Any, against: Any, zone: str | None) -> bool | None:
    if against is ABSENT:
        return None
    if isinstance(value, bool) or isinstance(against, bool):
        return said_yes(value) == said_yes(against)
    if _when(value, zone) is not None and _when(against, zone) is not None:
        order = _order(value, against, zone)
        return None if order is None else order == 0
    have, want = _strict_figure(value), _strict_figure(against)
    if have is not None and want is not None:
        if have[1] and want[1] and have[1] != want[1]:
            return False
        return have[0] == want[0]
    return _text(value) == _text(against)


def _contains(value: Any, words: Any) -> bool | None:
    wanted = [_text(w) for w in (words if isinstance(words, (list, tuple)) else [words])]
    if isinstance(value, (list, tuple)):
        return any(_text(item) in wanted for item in value)
    if isinstance(value, str):
        said = value.lower()
        return any(w and w in said for w in wanted)
    return None


def _empty(value: Any) -> bool:
    if value is ABSENT or value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, Mapping, set)):
        return len(value) == 0
    return False


def _text(value: Any) -> str:
    if isinstance(value, (Mapping, list, tuple)):
        return json.dumps(value, sort_keys=True, default=str)
    return str(value).strip().lower()


# ── figures ──────────────────────────────────────────────────────────────────

#: Every way a figure is written, INCLUDING the ones with nothing before the
#: decimal point.
#:
#: The first version was `-?\d+(?:\.\d+)?`, which requires a digit in front of
#: the dot — and because [`_GROUPING`] strips the space first, `'.50 USD'`
#: became `'.50USD'` and the first thing that matched was `50`. So a gate an
#: author wrote at fifty cents was read at fifty dollars and did not fire on a
#: 40 USD refund. MEASURED, before this:
#:
#:     '$.50'    -> 50.0        '$0.50'    -> 0.5
#:     '.50 USD' -> 50.0        '0.50 USD' -> 0.5
#:     '-.5 USD' -> 5.0         '-5 USD'   -> -5.0
#:     '1e5 USD' -> 1.0
#:
#: with `pact check` and `pact show` passing every one of them cleanly. Three
#: separate wrong figures out of one missing alternative: off by 100x, sign
#: flipped (the `-?` cannot start at a `-` it is not allowed to reach), and an
#: exponent dropped. The sign one is the sharpest, because
#: `a_gate_that_stops_for_a_person_on_any_spend_at_all_is_left_alone` DECIDES
#: that a negative threshold is legal — "a gate is not a ceiling" — so
#: `more-than: -.5 USD` is a gate deliberately written to stop on every refund
#: there is, and it stopped none under five dollars.
#:
#: This is the half `crates/pact-loader/src/money.rs` cannot reach: those are
#: all figures, so no "that is not a figure" refusal could ever have caught
#: them. The two grammars are held together by
#: `tests/test_a_spend_cap_that_can_never_be_reached.py`, which asserts that for
#: every threshold the checker lets through, the figure read back here is the
#: figure that was written.
_NUMBER = re.compile(r"-?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?")

#: Every way a person or a model writes a thousands separator. Stripped before
#: the number is read, because the pattern above stops at one — so
#: `'1,500.00 USD'` read as **1.0** and slipped under a 200 USD approval
#: threshold. Measured end to end on the worked example: the payments call ran,
#: the tool was invoked, and `RunResult.halted == 'final'` — money moved with
#: nobody asked, on an argument the MODEL chooses. Both sides of every comparison
#: come through here, so one strip covers rule thresholds and call arguments.
_GROUPING = str.maketrans("", "", ",_ ")

#: A currency written beside a figure: three letters at either end, or `$`.
_CURRENCY = re.compile(r"(?:^\s*([A-Za-z]{3})\s)|(?:\s([A-Za-z]{3})\s*$)")


def amount(value: Any) -> float | None:
    """The number inside `200 USD`, `$25`, `40.00 USD`, `1,500.00 USD`, `85%` or `12`.

    One reader for both sides of every comparison, so a rule written `200 USD`
    and an argument the model wrote as `$210` are compared as numbers rather
    than as strings — which is how `"210.00 USD" > "200 USD"` would quietly be
    false.

    A number that is not a finite one is not a figure, and is read as no figure
    at all. THE TWO SPELLINGS USED TO LAND ON OPPOSITE SIDES OF THE GATE, which
    was the one genuinely fail-OPEN path in this whole area: `'NaN USD'` is text,
    finds no digits, returns `None`, and a gate then stops the call — but a float
    `nan` arriving from a spec built in code came back as `nan`, and
    `nan > anything` is `False`, so the gate silently never fired. FR-8.1.1 (T7):
    *"No lossy operation anywhere may proceed silently; each MUST emit a report
    entry and be fail-closed by default."* The guard is on the VALUE and not on
    any one reader (`docs/70-PRODUCTION-GAP-REGISTER.md`, *"The guard is on the
    VALUE, not on a reader"*): both spellings return `None`, and `None` is the
    case every caller already handles by stopping.
    """
    figure = exact(value)
    return None if figure is None else float(figure)


def exact(value: Any) -> Decimal | None:
    """The figure [`amount`] reads, exactly as written: `0.004 USD` is
    `Decimal('0.004')`, not the float nearest it, and `40.00 USD` keeps its two
    places. What `add up` sums, so a total is the sum of what was written."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(repr(value)) if math.isfinite(value) else None
    m = _NUMBER.search(str(value).translate(_GROUPING))
    return Decimal(m.group()) if m else None


def currency(value: Any) -> str:
    """The currency written beside a figure (`USD` for `$`), or `""`."""
    if not isinstance(value, str):
        return ""
    if value.strip().startswith("$"):
        return "USD"
    m = _CURRENCY.search(value)
    return (m.group(1) or m.group(2)).upper() if m else ""


def _figure(value: Any) -> tuple[float, str] | None:
    """A figure and its currency (empty for a number or a percentage)."""
    figure = amount(value)
    return None if figure is None else (figure, currency(value))


def _strict_figure(value: Any) -> tuple[float, str] | None:
    """A figure only when the value is nothing but one, for `is:` — `12` is a
    figure, `12 apples` is a word."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _figure(value)
    if not isinstance(value, str):
        return None
    bare = _CURRENCY.sub(" ", value).strip().lstrip("$").rstrip("%").translate(_GROUPING)
    if not bare or _NUMBER.fullmatch(bare) is None:
        return None
    return _figure(value)
