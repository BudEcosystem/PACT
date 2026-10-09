"""The one time expression, read once (02W §2.0), and the reminders a wait
or a deadline carries on its clock (§2.8, §2.10).

A `moment` is written either as a bare length of time (`48h`, `3 days`: that
long after the stage starts) or as a group — `{at: input.starts-at, before:
24h, counted-in: business-days, in-time-zone: steps.tutor.zone}`. Every field
that takes a time takes this, and only this, so one reader serves a question's
`answer-within:`, a deadline's `finishes-within:`, a reminder's `at:`, a run's
`kept-for:` and an owner's `locked-until:`.

What a moment MEANS against a clock and a calendar — the value `at:` reads,
the zone, which days are working days — is the runtime's, at the time the
stage starts (the value is read then, and journaled). This reads what was
written, typed, and nothing more: the loader has already held it (`pact
check`: a group with both `after:` and `before:`, a `before:` with no `at:`,
a time read from a date with no zone anywhere — WF-30).
"""

from __future__ import annotations

import datetime as _dt
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .limits import seconds, whole
from .yes_no import said_yes

#: What an unwritten `counted-in:` means (the other word is `business-days`).
CALENDAR_DAYS = "calendar-days"

#: A length written in days alone moves the date, not the clock (the reading
#: `conditions.now-plus` gives a day: the same time tomorrow, in the zone).
_DAYS = re.compile(r"^\s*(\d+)\s*(?:d|day|days)\s*$", re.IGNORECASE)


def _text(v: Any) -> str:
    return "" if v is None else str(v).strip()


@dataclass(frozen=True)
class Moment:
    """One moment, as written: where it counts from, how far, in what days and
    which zone."""

    #: `at:` — the binding it counts from; empty for "when the stage starts".
    at: str = ""
    #: `after:` — or the whole of a moment written as a bare length of time.
    after: str = ""
    before: str = ""
    #: `counted-in:` — `calendar-days` (the default) or `business-days`.
    counted_in: str = CALENDAR_DAYS
    in_time_zone: str = ""

    @property
    def length(self) -> str:
        """The length of time written, after or before."""
        return self.after or self.before

    @property
    def sign(self) -> int:
        """+1 for a moment after `at:` (or the stage's start), -1 before it."""
        return -1 if self.before else 1

    @property
    def in_days(self) -> int | None:
        """The length as a whole number of days, when it is written in days
        alone (`20 days`); `None` when it is a length on the clock (`24h`)."""
        days = _DAYS.match(self.length)
        return int(days.group(1)) if days else None

    @property
    def offset(self) -> _dt.timedelta | None:
        """The signed length on the clock (`before: 24h` is minus a day), or
        `None` when nothing readable is written. Business days are not a
        length on the clock: counting them needs the calendar (`in_days`)."""
        days = self.in_days
        if days is not None:
            return _dt.timedelta(days=self.sign * days)
        span = seconds(self.length) if self.length else None
        return None if span is None else _dt.timedelta(seconds=self.sign * span)

    @property
    def from_stage(self) -> bool:
        """Whether it counts from when the stage (or a deadline's start) begins."""
        return not self.at

    @staticmethod
    def from_written(written: Any) -> "Moment | None":
        """A moment as `pact show` printed it, or `None` when nothing is written."""
        if written is None:
            return None
        if not isinstance(written, Mapping):
            return Moment(after=_text(written))
        return Moment(
            at=_text(written.get("at", "")),
            after=_text(written.get("after", "")),
            before=_text(written.get("before", "")),
            counted_in=_text(written.get("counted-in", "")) or CALENDAR_DAYS,
            in_time_zone=_text(written.get("in-time-zone", "")),
        )


@dataclass(frozen=True)
class Reminder:
    """One point on a wait's clock (`reminds-at:`) or a deadline's
    (`milestones:`) and the one thing it does then (WF-21)."""

    at: Moment
    #: Remind whoever is being asked.
    nudges: bool = False
    #: People to tell, without asking them anything.
    tells: tuple[str, ...] = ()
    #: Ask these people instead from now on (the question gets a new key).
    hands_over_to: tuple[str, ...] = ()
    #: A workflow to start with the run's data, not waited for.
    runs: str = ""

    @staticmethod
    def from_written(written: Mapping[str, Any]) -> "Reminder":
        return Reminder(
            at=Moment.from_written(written.get("at")) or Moment(),
            nudges=said_yes(written.get("nudges")),
            tells=_names(written.get("tells")),
            hands_over_to=_names(written.get("hands-over-to")),
            runs=_text(written.get("runs", "")),
        )


def reminders(written: Any) -> tuple[Reminder, ...]:
    """A `reminds-at:` or `milestones:` list, in written order."""
    items = written if isinstance(written, (list, tuple)) else ([written] if written else [])
    return tuple(Reminder.from_written(r) for r in items if isinstance(r, Mapping))


def _names(v: Any) -> tuple[str, ...]:
    if isinstance(v, str):
        return (v.strip(),)
    if isinstance(v, (list, tuple)):
        return tuple(str(x).strip() for x in v if x is not None)
    return ()


@dataclass(frozen=True)
class RegionLimits:
    """The `limits:` lines only a workflow reads (02W §2.10), on a workflow or
    on one of its stages. The shared ceilings (`tokens-at-most`, ...) are
    `limits.Limits`; these are the deadline that may pause, start late and
    carry milestones, how many run at once, and the choice as written — a
    workflow has eight (`carry-on`, `wait-its-turn`, ...), where
    `Limits.when_it_runs_out` knows an agent's three."""

    #: `finishes-within:` — a moment (`{after: 60 days, counted-in: business-days}`).
    finishes_within: Moment | None = None
    #: `starts-from:` — the stage whose end starts that clock; empty for the start.
    starts_from: str = ""
    #: `paused-during:` — waits whose time does not count against it.
    paused_during: tuple[str, ...] = ()
    milestones: tuple[Reminder, ...] = ()
    #: `at-once-at-most:` — how many may run at the same time.
    at_once_at_most: int | None = None
    #: `when-it-runs-out:` as written.
    when_it_runs_out: str = ""

    @staticmethod
    def from_limits(written: Any) -> "RegionLimits":
        m = written if isinstance(written, Mapping) else {}
        return RegionLimits(
            finishes_within=Moment.from_written(m.get("finishes-within")),
            starts_from=_text(m.get("starts-from", "")),
            paused_during=_names(m.get("paused-during")),
            milestones=reminders(m.get("milestones")),
            at_once_at_most=whole(m.get("at-once-at-most")),
            when_it_runs_out=_text(m.get("when-it-runs-out", "")),
        )


@dataclass(frozen=True)
class FailurePlan:
    """A stage's `if-it-fails:` (02W §2.7, F2's one failure record): what happens
    once every attempt (`at-most:`) has failed, with the lines that choice needs.
    A `when-it-runs-out:` of `use-a-backup`, `wait-for-a-new-version` or `undo`
    on the same stage takes its companion from here (§2.10). The loader has held
    each companion to its choice and each name to what it names."""

    #: `use-a-backup`, `carry-on`, `ask-a-person`, `wait-for-a-new-version`,
    #: `undo` or `stop-and-say-so`.
    after_that: str = "stop-and-say-so"
    #: `gives-up-after:` — keep trying until this time rather than `at-most:` times.
    gives_up_after: Moment | None = None
    #: `backup:` — what to call instead, with the stage's own `bind:`.
    backup: str = ""
    #: `carry-on-with:` — the stage's answer to go on with, field by binding.
    carry_on_with: Mapping[str, str] = field(default_factory=dict)
    #: `asks:` — the question put to a person.
    asks: str = ""
    #: `new-version-of:` — the connection or workflow whose next version resumes it.
    new_version_of: str = ""
    #: `undo:` — the stage whose work is undone, newest first.
    undo: str = ""
    #: `undo-where:` — on an `each`, the items to undo, as `when-this` lines.
    undo_where: tuple[Mapping[str, Any], ...] = ()

    @staticmethod
    def from_written(written: Any) -> "FailurePlan | None":
        """The plan as written, or `None` when the stage writes none (it then
        stops and says so)."""
        if not isinstance(written, Mapping):
            return None
        return FailurePlan(
            after_that=_text(written.get("after-that", "")) or "stop-and-say-so",
            gives_up_after=Moment.from_written(written.get("gives-up-after")),
            backup=_text(written.get("backup", "")),
            carry_on_with={str(k): _text(v) for k, v in (written.get("carry-on-with") or {}).items()},
            asks=_text(written.get("asks", "")),
            new_version_of=_text(written.get("new-version-of", "")),
            undo=_text(written.get("undo", "")),
            undo_where=tuple(u for u in written.get("undo-where") or () if isinstance(u, Mapping)),
        )
