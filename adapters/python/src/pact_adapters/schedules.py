"""When a timer port fires: `every:` read once, into one form, and the next time it comes.

`port.every:` is *"plain words like `weekday mornings at 9`, or a cron line if you
know them"* (`spec/schema.yaml`), and for a round nothing read it: the loader
derives `kind: schedule` from it (`crates/pact-loader/src/ports.rs`) and no
runtime could say when that schedule fires. This is the one reader, so every
runtime that keeps a clock asks the same question of the same words.

**A closed grammar, refused by name.** The words are read by a small, auditable
table, never by a guess: a line this cannot read is refused with the forms that
work, because a timer that silently fires at the wrong time is worse than one
that refuses to start. What it reads:

* a cron line, five fields (`0 16 * * 5`) or six with seconds first;
* an interval: `every 10 minutes`, `every 2 seconds`, `every hour`;
* `hourly`, `daily`, `weekly` (Mondays at midnight), `monthly` (the 1st);
* days at a time: `Friday at 4pm`, `weekday mornings at 9`, `every day at
  16:30`, `Mondays and Thursdays at noon`, `weekends at 10am`.

**Two forms, so an interval is honest.** A calendar schedule is a six-field
cron line (seconds first). An interval is `@every <n>s`, counted from the Unix
epoch, because cron cannot say "every 7 seconds" (`*/7` fires at :56 and again
at :00) and a timer that claims an interval it does not keep is the silent kind
of wrong. Both forms have the same property a runtime needs for a durable run
id: the time a firing is FOR (its slot) is a pure function of the schedule and
the clock, so a restarted process names the same slot the same way.

**Clock-time, no zones.** The fields are read on whatever clock the runtime
hands `next_after` (its own `now`, UTC unless the host says otherwise). PACT
has no time-zone field; a host that needs one passes an aware datetime in it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

__all__ = ["Schedule", "Unreadable"]

#: How far ahead `next_after` looks before deciding a calendar line never fires
#: (`0 0 30 2 *` — the 30th of February). Long enough for any leap-year line.
_HORIZON_DAYS = 8 * 366

_DAYS = {
    "sun": 0, "sunday": 0, "mon": 1, "monday": 1, "tue": 2, "tues": 2, "tuesday": 2,
    "wed": 3, "wednesday": 3, "thu": 4, "thur": 4, "thurs": 4, "thursday": 4,
    "fri": 5, "friday": 5, "sat": 6, "saturday": 6,
}
_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
_UNITS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
#: Cron fields, seconds first: (name, lowest, highest, names it accepts).
_FIELDS = (
    ("second", 0, 59, {}), ("minute", 0, 59, {}), ("hour", 0, 23, {}),
    ("day of the month", 1, 31, {}), ("month", 1, 12, _MONTHS), ("day of the week", 0, 7, _DAYS),
)
_NAMED = {
    "hourly": "0 0 * * * *", "daily": "0 0 0 * * *", "every day": "0 0 0 * * *",
    "weekly": "0 0 0 * * 1", "monthly": "0 0 0 1 * *", "every hour": "@every 3600s",
    "every minute": "@every 60s", "every second": "@every 1s",
}
_PART_OF_DAY = {"morning": "am", "mornings": "am", "afternoon": "pm", "afternoons": "pm",
                "evening": "pm", "evenings": "pm", "night": "pm", "nights": "pm"}

FORMS = (
    "plain words like `Friday at 4pm`, `weekday mornings at 9`, `every 10 minutes` or "
    "`daily`, or a cron line such as `0 16 * * 5`"
)


class Unreadable(ValueError):
    """`every:` says something this reader cannot turn into a time; the message says what works."""


@dataclass(frozen=True)
class Schedule:
    """One `every:` line, read: the author's words and the one form a clock keeps."""

    #: What the author wrote.
    written: str
    #: `@every <n>s`, or a six-field cron line (seconds first).
    line: str

    @staticmethod
    def parse(written: str) -> "Schedule":
        text = " ".join(str(written or "").lower().replace(",", " , ").split())
        text = text.replace(" , ", ", ")
        if not text:
            raise Unreadable(f"`every:` is empty. Write when to run: {FORMS}.")
        try:
            line = _NAMED.get(text) or _interval(text) or _cron(text) or _calendar(text)
        except Unreadable as exc:  # a cron line with a field out of range
            raise Unreadable(f"`every: {written}` — {exc} Write {FORMS}.") from None
        if line is None:
            raise Unreadable(f"`every: {written}` is not a time PACT can read. Write {FORMS}.")
        found = Schedule(str(written).strip(), line)
        if found.next_after(datetime(2000, 1, 1, tzinfo=timezone.utc)) is None:
            raise Unreadable(f"`every: {written}` never comes round (no such day). Write {FORMS}.")
        return found

    @property
    def interval(self) -> int | None:
        """Seconds between firings, for an interval; None for a calendar line."""
        return int(self.line[len("@every "):-1]) if self.line.startswith("@every ") else None

    def next_after(self, when: datetime) -> datetime | None:
        """The first slot strictly after `when`, on `when`'s own clock; None if it never comes."""
        step = self.interval
        if step is not None:
            epoch = datetime(1970, 1, 1, tzinfo=when.tzinfo)
            gone = int((when - epoch).total_seconds() // step)
            return epoch + timedelta(seconds=(gone + 1) * step)
        sets = _sets(self.line)
        seconds, minutes, hours, doms, months, dows = sets
        dom_free, dow_free = self.line.split()[3] == "*", self.line.split()[5] == "*"
        start = when.replace(microsecond=0) + timedelta(seconds=1)
        day = start.replace(hour=0, minute=0, second=0)
        for _ in range(_HORIZON_DAYS):
            if day.month in months and _day_matches(day, doms, dows, dom_free, dow_free):
                floor = start if day.date() == start.date() else day
                for h in sorted(hours):
                    if h < floor.hour:
                        continue
                    for m in sorted(minutes):
                        if h == floor.hour and m < floor.minute:
                            continue
                        for s in sorted(seconds):
                            hit = day.replace(hour=h, minute=m, second=s)
                            if hit >= floor:
                                return hit
            day = (day + timedelta(days=1)).replace(hour=0, minute=0, second=0)
        return None


def _day_matches(day: datetime, doms: set[int], dows: set[int], dom_free: bool, dow_free: bool) -> bool:
    """Cron's rule: with both day fields restricted, either may match."""
    dow = (day.weekday() + 1) % 7
    in_dom, in_dow = day.day in doms, dow in dows or (dow == 0 and 7 in dows)
    if not dom_free and not dow_free:
        return in_dom or in_dow
    return in_dom and in_dow


def _interval(text: str) -> str | None:
    found = re.fullmatch(r"every (\d+) (second|minute|hour|day)s?", text)
    if not found:
        return None
    n = int(found.group(1)) * _UNITS[found.group(2)]
    return f"@every {n}s" if n > 0 else None


def _cron(text: str) -> str | None:
    fields = text.split()
    if len(fields) not in (5, 6) or not all(re.fullmatch(r"[\w*/,\-]+", f) for f in fields):
        return None
    fields = ["0", *fields] if len(fields) == 5 else fields
    try:
        for field, (name, low, high, names) in zip(fields, _FIELDS, strict=True):
            _values(field, low, high, names, name)
    except Unreadable:
        raise
    except ValueError:
        return None
    return " ".join(fields)


def _calendar(text: str) -> str | None:
    """`<days> [<part of day>] at <time>`, or `<days>` alone (at midnight)."""
    text = re.sub(r"^(on |every )", "", text)
    days_part, _, time_part = text.partition(" at ")
    words = days_part.replace(",", " ").split()
    part = ""
    if words and words[-1] in _PART_OF_DAY:
        part = _PART_OF_DAY[words.pop()]
    days = _days(words)
    if days is None:
        return None
    hour, minute = (0, 0) if not time_part else _time(time_part, part) or (-1, -1)
    if hour < 0:
        return None
    return f"0 {minute} {hour} * * {days}"


def _days(words: list[str]) -> str | None:
    if words in (["day"], ["days"], ["daily"], []):
        return "*"
    if words in (["weekday"], ["weekdays"]):
        return "1-5"
    if words in (["weekend"], ["weekends"]):
        return "0,6"
    named: list[int] = []
    for word in words:
        if word == "and":
            continue
        day = _DAYS.get(word.rstrip("s")) if word not in _DAYS else _DAYS[word]
        if day is None:
            return None
        named.append(day)
    return ",".join(str(d) for d in sorted(set(named))) if named else None


def _time(text: str, part: str) -> tuple[int, int] | None:
    text = text.strip()
    if text in ("noon", "midday"):
        return 12, 0
    if text == "midnight":
        return 0, 0
    found = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
    if not found:
        return None
    hour, minute = int(found.group(1)), int(found.group(2) or 0)
    meridiem = found.group(3) or part
    if meridiem:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if meridiem == "pm" else 0)
    return (hour, minute) if hour <= 23 and minute <= 59 else None


def _sets(line: str) -> list[set[int]]:
    return [_values(f, low, high, names, name) for f, (name, low, high, names) in
            zip(line.split(), _FIELDS, strict=True)]


def _values(field: str, low: int, high: int, names: dict[str, int], name: str) -> set[int]:
    out: set[int] = set()
    for item in field.split(","):
        body, _, step_text = item.partition("/")
        step = int(step_text) if step_text else 1
        if step < 1:
            raise ValueError(name)
        if body == "*":
            lo, hi = low, high
        else:
            first, _, last = body.partition("-")
            lo = names[first] if first in names else int(first)
            hi = (names[last] if last in names else int(last)) if last else (high if step_text else lo)
        if not (low <= lo <= hi <= high):
            raise Unreadable(f"`{field}` is outside {low}-{high}, the {name}s a cron line can name.")
        out.update(range(lo, hi + 1, step))
    return out
