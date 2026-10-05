"""The termination algebra — every way a run is allowed to end, as data.

Eve bounds a run in exactly one way: a token budget on the session. It has no
step limit, no turn limit, no wall-clock limit and no spend cap anywhere, and
`stopWhen: isStepCount(1)` is the only stop condition in the package. A confused
agent therefore loops until it has spent 40M tokens, and the only thing that
notices is the bill.

Here every ceiling is a row in one table — what it counts, what the author
wrote, and which meter it reads — so adding a dimension is a row plus a schema
field rather than a new branch in the loop. That is why `tokens-at-most` (Eve's
only limit) costs exactly what `runs-for-at-most` costs (a limit Eve cannot
express at all).

Three properties the algebra has to have, and none of them is free:

* **The action is declared, never implied.** Stopping silently, asking a person,
  and answering as if finished are three different governance decisions, and a
  system that picks one for you has made that decision on your behalf. The
  schema refuses a ceiling with no `when-it-runs-out`, so this module never has
  to guess and never has a "sensible default" that quietly becomes policy.
* **Reaching a ceiling is not finishing.** A run that answered because it ran out
  of budget reports the ceiling it hit even when the answer looks fine. Eve's
  own docs describe stopping at a token limit as the session "ending"; reporting
  the two alike is the silent degradation T7 forbids, and it is the only reason
  `answer-with-what-it-has` is safe to offer at all.
* **Which ceiling tripped is deterministic.** Two runs of the same trace name the
  same ceiling, because they are checked in one fixed order rather than in
  whatever order a dictionary happened to iterate.

The step ceiling deliberately does NOT live here: it is `AgentSpec.max_steps`,
which is also the loop bound every transport and the TypeScript port already
speak. A second copy of it would be the `same-setting-twice` mistake the
validator exists to catch, so `steps_at_most` is passed in instead.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any


class Action(str, Enum):
    """What to do on reaching a ceiling. The author writes exactly one of these;
    there is no fourth behaviour available to the harness."""

    STOP = "stop-and-say-so"
    ASK = "ask-a-person"
    ANSWER = "answer-with-what-it-has"


@dataclass(frozen=True)
class Ceiling:
    """One row of the algebra."""

    #: Exactly what the author typed in `limits.yaml`. Diagnostics quote this,
    #: never an internal name, because the reader has to be able to find it.
    field: str
    #: Which meter it is compared against.
    reads: str
    limit: float
    #: The noun a person reads back: "steps", "tool calls", "seconds" — and, for
    #: a money row, THE CURRENCY THE AUTHOR WROTE.
    #:
    #: It was the literal string `"USD"` for every money ceiling, whatever the
    #: file said, because `money()` returned the first parseable float and threw
    #: the currency away. So `cost-per-request-under: 500 JPY` loaded, ran, and
    #: reported *"(501 of 500 USD)"* — naming a currency the author had never
    #: typed, after a comparison that had already treated 500 JPY and 500 USD as
    #: the same money. `Ty::Money`'s own doc comment says silently normalising a
    #: currency is a correctness bug and FR-1.4.5 says it normatively; this is
    #: the reader that stopped doing it.
    #:
    #: Empty means no currency was written — a spec built in code with a bare
    #: number. `pact check` refuses a bare number in the file (`Ty::Money` does
    #: not coerce one), so the sentence simply leaves the noun out rather than
    #: supplying a currency nobody chose.
    unit: str
    #: The short tag reported as `RunResult.halted`.
    halted: str


@dataclass(frozen=True)
class Reached:
    """A ceiling that has been reached, and what was done about it."""

    ceiling: Ceiling
    at: float
    action: Action

    @property
    def what(self) -> str:
        """The setting and both numbers: ``` `steps-at-most` (2 of 2 steps) ```.

        Named because two readers want it. The run report puts it in a sentence
        below, and a `keep-going` question shows it to the person being asked
        whether to spend more (`shows: [which-limit]`). Two spellings of one
        stop is how the person deciding and the person reading afterwards come
        to be told different things about the same run.
        """
        # The unit is appended rather than interpolated, because a money row
        # whose currency nobody wrote has no noun to print and `"(0.06 of 0.05
        # )"` would be a stray space where a currency should be.
        figures = f"{_round(self.at)} of {_round(self.ceiling.limit)}"
        if self.ceiling.unit:
            figures = f"{figures} {self.ceiling.unit}"
        return f"`{self.ceiling.field}` ({figures})"

    def sentence(self) -> str:
        """What a person is told. Names the setting, both numbers, and what
        happened — a message saying only "limit exceeded" leaves the reader with
        nowhere to go, which is the failure D13 rules out."""
        what = self.what
        if self.action is Action.ASK:
            return f"Waiting for a person: this run reached the limit you set with {what}."
        if self.action is Action.ANSWER:
            return (
                f"This run reached the limit you set with {what}, so it answered "
                f"with what it had rather than finishing the work."
            )
        return f"Stopped before finishing: this run reached the limit you set with {what}."


@dataclass
class Meter:
    """What a run has spent so far. Carried across a park, so a run that was
    interrupted for a person cannot get a fresh budget by being resumed."""

    started: float = 0.0
    #: Seconds already worked before this process started, from an earlier leg.
    carried: float = 0.0
    steps: int = 0
    tool_calls: int = 0
    tokens: int = 0
    money: float = 0.0

    def seconds(self, now: float) -> float:
        """Time spent WORKING. Time parked for a person is excluded on resume,
        so nobody fails a deadline because the approver went to lunch."""
        return self.carried + (now - self.started)

    def reading(self, reads: str, now: float) -> float:
        return self.seconds(now) if reads == "seconds" else float(getattr(self, reads))

    def as_dict(self, now: float) -> dict[str, float]:
        """The shape that crosses a process boundary inside a pause."""
        return {
            "seconds": self.seconds(now),
            "steps": float(self.steps),
            "tool_calls": float(self.tool_calls),
            "tokens": float(self.tokens),
            "money": self.money,
        }

    @staticmethod
    def restored(used: dict[str, float], now: float, steps: int) -> "Meter":
        """Rebuild a meter from a pause. `steps` is the fallback for a pause
        written before meters existed — a resumed run must never restart its
        counters at zero, whatever wrote the pause."""
        return Meter(
            started=now,
            carried=float(used.get("seconds", 0.0)),
            steps=int(used.get("steps", steps)),
            tool_calls=int(used.get("tool_calls", 0)),
            tokens=int(used.get("tokens", 0)),
            money=float(used.get("money", 0.0)),
        )


#: Every ceiling a `Limits` carries, in `ceilings()` order, as
#: `(the attribute, the authored line, what the row would read)`.
#:
#: A TABLE and not a hand-kept pair of field names, because the pair was wrong
#: twice. `__post_init__` walked `cost_per_request_under` alone for a round, and
#: `wall_clock_s` carried the identical pathology in silence; it then walked the
#: two floats, and `tokens_at_most` and `tool_calls_at_most` carried it in
#: silence. Measured on the six-step 1000-USD-a-call harness, with the two-float
#: guard in place and no other edit::
#:
#:     Limits(tokens_at_most=inf)     halted='final' spent=1000.0
#:                                    unmetered=() rows=['tokens-at-most']
#:     Limits(tool_calls_at_most=inf) halted='final' spent=1000.0
#:                                    unmetered=() rows=['tool-calls-at-most']
#:
#: — a row built, `reached()` answering `None` with the meter holding 1e12 of
#: each, and every honesty channel empty. That is the before-picture verbatim,
#: two fields over, and it was reachable because the guard was enumerated over
#: FIELDS when the thing being guarded against is a property of the FIGURE. The
#: authored route is shut on all four (`whole('1e999') is None`,
#: `seconds('inf') is None`, and `Schema::check_floor` refuses a money figure
#: below the floor before this module ever sees it), so the constructor is the
#: only door — which is the door this whole guard exists for.
#:
#: `None` for the authored line means "ask `wall_clock_field`": that ceiling can
#: have come off either `runs-for-at-most` or `finishes-within`, and the report
#: has to quote the line the author actually wrote.
#:
#: `steps-at-most` is deliberately absent, because it is not a field of this
#: object — `ceilings()` takes it as an argument, from `AgentSpec.max_steps`,
#: and the module docstring says why it lives there and not here.
_CEILING_FIELDS: tuple[tuple[str, str | None, str], ...] = (
    ("tool_calls_at_most", "tool-calls-at-most", "tool_calls"),
    ("wall_clock_s", None, "seconds"),
    ("cost_per_request_under", "cost-per-request-under", "money"),
    ("tokens_at_most", "tokens-at-most", "tokens"),
)

#: The only two authored lines a wall-clock ceiling can have come off.
#:
#: A CLOSED vocabulary, and not tidiness. `held_nothing()` reports
#: `wall_clock_field` verbatim into an author's report, and that field is a
#: free-form constructor string — so an ARBITRARY name could be forged into it.
#: Measured on the tree before this, no other edit::
#:
#:     Limits(wall_nothing_can_reach=inf,
#:            wall_clock_field='anything-the-caller-likes').held_nothing()
#:       -> (('anything-the-caller-likes', 'seconds'),)
#:     -> "these ceilings held nothing … : anything-the-caller-likes.
#:         fix: write a length of time on that line, like `runs-for-at-most: 30s`."
#:
#: a report sending an author to a line that appears nowhere in their document.
#: `from_mapping` sets one of these two and nothing else ever should.
#:
#: `feel` is the third, and it is a line the author wrote: `feel: interactive`
#: supplies `finishes-within:` when nobody wrote one (`slo.FEELS`), and a
#: `finishes-within:` is a stop. Reported as `feel`, because that is the line
#: in the file; quoting `finishes-within` would send the author to a line that
#: is not there.
_WALL_CLOCK_FIELDS: tuple[str, ...] = ("runs-for-at-most", "finishes-within", "feel")


@dataclass(frozen=True)
class _HeldNothing:
    """The ceiling figures a `Limits` was handed that nothing can be at or above.

    **PRIVATE, and that is the whole of its job.** The claim *"this ceiling held
    nothing"* used to be spellable at the constructor: `cap_nothing_can_reach`
    and `wall_nothing_can_reach` were ordinary public fields of the frozen
    dataclass, and `__post_init__` refused only a record its own predicate
    disagreed with — so ANY figure the predicate agrees with was accepted on
    trust, with no evidence this object had ever held it. Measured on the tree
    before this, no edits::

        Limits(cap_nothing_can_reach=inf).nothing_can_reach
          -> ('cost-per-request-under',)        <- and no cost line anywhere
        Limits(tool_calls_at_most=1, wall_nothing_can_reach=inf,
               wall_clock_field='tool-calls-at-most')
          -> halted='tool-call-limit'  unmetered=('tool-calls-at-most',)
             "these ceilings held nothing, because no length of time can ever be
              at or above the figure written: tool-calls-at-most.
              fix: write a length of time on that line …"

    which is the ORIGINAL wrong-diagnosis defect verbatim — a ceiling that
    demonstrably STOPPED the run, named on the channel whose wording is *"cannot
    promise"*, with a remedy for a line that has no length of time on it —
    reached through the very field the redesign added in order to remove it.
    Both docstrings claimed *"there is no constructor argument that spells this
    claim"*, and that sentence was false where nothing looked.

    It is true now, and by TYPE rather than by predicate: this class is module
    private, `__post_init__` answers anything else in that slot with a
    `TypeError`, and it refuses a row naming a line no ceiling of this object
    could have come off. A caller cannot forge a claim they cannot name.

    `dataclasses.replace` still carries it, which is required rather than
    tolerated: `harness._delegating` replaces ONE field of a member's `Limits`
    and every other field has to survive that untouched. A field declared
    `init=False` would not — `replace` does not copy those — and the figure has
    by then been moved off its ceiling field, so the record would be silently
    lost and the run would go quiet again on the very path this guard is for.

    The FIGURE is stored and not merely the name, for the reason the record
    exists at all: a name is an assertion carrying nothing to check it against,
    and the figure the author wrote is the only thing that can justify the
    report made about it.
    """

    #: `(the authored line, what the row would have read, the figure written)`,
    #: in `ceilings()` order — the order the rows themselves would have come in,
    #: so a report naming them is not a second ordering to keep straight.
    rows: tuple[tuple[str, str, float], ...] = ()


@dataclass(frozen=True)
class Limits:
    """The ceilings one agent declared, and the one action they share.

    `when_it_runs_out` defaults to `stop-and-say-so` for a spec built in code
    with no ceilings at all. It is never a default for an authored file: the
    schema refuses a ceiling that does not say what happens at it.
    """

    tool_calls_at_most: int | None = None
    wall_clock_s: float | None = None
    #: Which setting the wall-clock ceiling came from, so the report can quote
    #: the line the author actually wrote. One of `_WALL_CLOCK_FIELDS`, checked
    #: in `__post_init__` — this string is reported verbatim to an author, and
    #: while it was free-form an arbitrary name could be forged into their
    #: report. The measurement is on `_WALL_CLOCK_FIELDS`.
    wall_clock_field: str = "runs-for-at-most"
    cost_per_request_under: float | None = None
    #: Which currency the spend cap was written in — `USD` for
    #: `cost-per-request-under: 0.05 USD`. Kept beside the amount for the same
    #: reason `wall_clock_field` is kept beside the seconds: the report has to be
    #: able to quote the line the author actually wrote. Empty means a bare
    #: number, which only a spec built in code can carry — see [`Ceiling.unit`].
    cost_currency: str = ""
    tokens_at_most: int | None = None
    #: how many times one request may put this agent to work, counting the
    #: first. Not a Ceiling row — like `steps-at-most`, it bounds the shape of
    #: the run, and `delegate` is where it is spent.
    asks_itself_at_most: int | None = None
    when_it_runs_out: Action = Action.STOP
    #: The named question to put to a person when the action is `ask-a-person`.
    asks: str = ""
    #: The ceilings this object was handed that no reading can ever be at or
    #: above — `cost-per-request-under: NaN USD`, `runs-for-at-most: inf`,
    #: `tokens-at-most: inf`. The FIGURES, moved off the ceiling fields rather
    #: than deleted, because the figure is the only thing that can justify the
    #: report made about it.
    #:
    #: ONE private record and not one public float per ceiling, and both halves
    #: of that matter. Private, because the two public slots this replaces were
    #: forgeable — see `_HeldNothing`, which carries the measurement. One,
    #: because there are four ceiling fields and the hand-kept list of them was
    #: wrong twice; `_CEILING_FIELDS` is the list now, and it carries the two
    #: fields that were silent under the previous shape.
    #:
    #: It was a tuple of FIELD NAMES before it was a figure, and that shape could
    #: be forged too. Its own comment said *"DERIVED, not accepted … passing it
    #: in by hand does not make it true"*, and measured against that claim::
    #:
    #:     Limits(tool_calls_at_most=1, nothing_can_reach=('tool-calls-at-most',))
    #:       -> ceilings=['tool-calls-at-most']  halted='tool-call-limit'
    #:          unmetered=('tool-calls-at-most',)
    #:          "these ceilings held nothing, because no amount of money can ever
    #:           be at or above the figure written: tool-calls-at-most.
    #:           fix: write an amount of money on that line …"
    #:
    #: — a ceiling that demonstrably STOPPED the run, reported on the channel
    #: whose wording is *"cannot promise"*, with a money remedy for a tool-call
    #: ceiling. That is the wrong-diagnosis failure `scoring._unmetered_caveats`
    #: was written to remove, reintroduced by the field that was meant to remove
    #: it. A name is an assertion about a figure and carries no figure, so
    #: nothing could check it.
    #:
    #: B10 owns the rest of that family — a meter poisoned by a remote agent's
    #: `"cost": NaN`, a price list resolving to `nan`, a resume through
    #: `Meter.restored`. None of those is a figure inside a `Limits`, so none of
    #: them meets here; the four ceiling fields do, and are the whole of what did.
    _held_nothing: "_HeldNothing | None" = None

    def __post_init__(self) -> None:
        """A ceiling nothing can be at or above is not carried, HOWEVER it arrived.

        This lives on the VALUE and not on the reader, and that is the whole
        point of it being here rather than in `from_mapping`. `from_mapping` is
        one of the ways a `Limits` comes to exist and it is not the common one
        in code: `Limits(cost_per_request_under=0.05)` is written directly at
        twenty-one sites in `adapters/python/tests` alone, and `harness` itself
        reaches for `dataclasses.replace` when a join policy grants a member its
        share. Guarding the parser left the identical hole open on both — measured
        after the parser-only guard, with a transport pricing every call at 1000
        USD::

            Limits(cost_per_request_under=float('nan'), cost_currency='USD')
                -> spent=6000.0 halted='step-limit' unmetered=()
                   ceilings=['cost-per-request-under']
            replace(parsed_005, cost_per_request_under=float('inf'))
                -> cap=inf  nothing_can_reach=()  money rows=['cost-per-request-under']

        which is the before-picture verbatim, reached by a different door. A
        `Limits` is frozen, so there is exactly one moment at which every route
        into it meets, and this is it.

        **EVERY CEILING THIS OBJECT CARRIES, off `_CEILING_FIELDS`, and not a
        hand-kept list of the fields somebody remembered.** That list was wrong
        twice, and the second time was inside the fix for the first: for a round
        this walked the money field only and `wall_clock_s` was silent, and then
        it walked the two floats and `tokens_at_most` and `tool_calls_at_most`
        were silent — measured, `Limits(tokens_at_most=inf)` building a row,
        `reached()` answering `None` at 1e12 tokens, and every honesty channel
        empty. The defect is a property of the FIGURE and enumerating FIELDS is
        how it kept escaping; `_CEILING_FIELDS` carries the measurement.

        Three directions per ceiling, because a record that only ever goes ON is
        a record that outlives what it describes and a record nothing checks is
        one anybody can write:

        * a figure nothing can reach is MOVED off the ceiling field onto the
          record, so no row is built for it and the figure that justifies the
          report is still there to be pointed at;
        * a real figure arriving where an unreachable one was CLEARS that
          ceiling's row — it is simply not carried forward. `harness._delegating`
          does exactly this: a member whose own cap is `NaN USD` is handed the
          join policy's share with `replace(member.limits,
          cost_per_request_under=allowed)`, and `replace` copies every field it
          is not given across untouched. That member then enforced a real
          `0.10 USD` ceiling and reported `cost-per-request-under` as a cap it
          could not promise — a run that can halt at `cost-limit` on the very
          field it just said held nothing;
        * a row whose ceiling field is still empty is CARRIED, and that direction
          is as load-bearing as the other two. `replace(l, cost_currency='EUR')`
          on an object whose `NaN USD` has already been moved onto the record
          must still say what it said — the figures are gone from the ceiling
          fields by then, so a rebuild from the figures alone would lose the
          claim and the run would go quiet again. The row is only carried when
          it names the same ceiling, reads the same meter, and is still a figure
          `_nothing_can_reach` agrees with.

        The record's TYPE is what makes it unforgeable, and the predicate never
        was: `cap_nothing_can_reach` and `wall_nothing_can_reach` were public
        floats, so any figure the predicate agreed with was believed —
        `Limits(cap_nothing_can_reach=inf)` reported `cost-per-request-under` on
        `unmetered` for an object with no cost line anywhere. `_HeldNothing`
        carries that measurement and the reasoning.

        THE CURRENCY IS NOT DESTROYED, and it used to be. `cost_currency` is the
        half of the authored line that parsed perfectly, and clearing it lost
        information the clearing arm above then could not give back — measured on
        this guard's own motivating path, reconstructing `_delegating` with
        `allowed=0.10`::

            member wrote 'NaN USD'  -> cap=0.1 currency=''    `cost-per-request-under` (0.11 of 0.1)
            member wrote '0.50 USD' -> cap=0.1 currency='USD' `cost-per-request-under` (0.11 of 0.1 USD)

        Two members in the same team, handed the same share by the same policy,
        stopped by the same ceiling, printing different sentences — and the
        second port keeps the currency through the same spread (`spend("NaN USD")
        -> amount=NaN currency="USD"`), so this was also the two ports printing
        different `stoppedBy.unit`, which is the pair `run-trace.ts` projects in
        order to be compared. Nothing reads a currency without an amount:
        `ceilings()` builds a money row only when the amount is there.

        `object.__setattr__` is what a frozen dataclass gives `__post_init__`;
        there is no other way to normalise one at construction.
        """
        if self.wall_clock_field not in _WALL_CLOCK_FIELDS:
            raise ValueError(
                f"a wall-clock ceiling comes off one of "
                f"{', '.join(_WALL_CLOCK_FIELDS)}, and this one says "
                f"{self.wall_clock_field!r} — which would be reported to an "
                f"author as a line to go and fix in a document that has no such "
                f"line in it"
            )
        if self._held_nothing is not None and not isinstance(
            self._held_nothing, _HeldNothing
        ):
            raise TypeError(
                "`_held_nothing` is the record this object writes about figures "
                "it was handed, not a claim a caller can hand in: "
                f"{self._held_nothing!r}"
            )
        carried = {} if self._held_nothing is None else {
            field: (field, reads, figure)
            for field, reads, figure in self._held_nothing.rows
        }
        rows: list[tuple[str, str, float]] = []
        for attr, line, reads in _CEILING_FIELDS:
            named = self.wall_clock_field if line is None else line
            figure = getattr(self, attr)
            if figure is not None and _nothing_can_reach(float(figure)):
                object.__setattr__(self, attr, None)
                rows.append((named, reads, float(figure)))
            elif figure is None and named in carried:
                # Carried, so that `replace(l, cost_currency='EUR')` on an object
                # whose figure has already been moved off keeps saying what it
                # said. `harness._delegating` replaces one field and nothing else.
                held = carried[named]
                if held[1] == reads and _nothing_can_reach(held[2]):
                    rows.append(held)
        object.__setattr__(
            self, "_held_nothing", _HeldNothing(tuple(rows)) if rows else None
        )

    def held_nothing(self) -> tuple[tuple[str, str], ...]:
        """The ceilings this object was handed that nothing can ever be at or
        above, as `(the line the author wrote, what it counts)`.

        Two readers want two different things and one of them is a SENTENCE.
        `harness` wants the names, for `RunResult.unmetered`; `scoring` wants to
        know whether the remedy to print is *"write an amount of money on that
        line"* or *"write a length of time on that line"*, and a list of bare
        names cannot answer that. The second element is `Ceiling.reads` — the
        same word the row would have carried had one been built — so the two can
        never fall out of step. Four values reach here and not two, because four
        ceilings can carry a figure nothing reaches: `scoring._unmetered_caveats`
        has a remedy for each, and a `reads` with no remedy there falls through
        to *"nothing to type"*, which is the wrong-diagnosis failure this pair of
        elements exists to prevent.

        In `ceilings()` order, because these are the rows that order would have
        held and a report that names them in a different sequence than the live
        ones is a second ordering to keep straight.
        """
        record = self._held_nothing
        if record is None:
            return ()
        return tuple((field, reads) for field, reads, _ in record.rows)

    @property
    def nothing_can_reach(self) -> tuple[str, ...]:
        """Just the field names, for `RunResult.unmetered`.

        A read-only view and not a field, which is the point: there is no
        constructor argument that spells this claim, so `Limits(...,
        nothing_can_reach=('tool-calls-at-most',))` is a `TypeError` at the call
        site rather than a lie that reaches an author's report.

        The two public float slots this used to be a view over were the same
        lie one level down — `Limits(cap_nothing_can_reach=inf)` came back
        `('cost-per-request-under',)` for an object with no cost line anywhere —
        and the record is a private type for that reason. `_HeldNothing` carries
        the measurement.
        """
        return tuple(field for field, _ in self.held_nothing())

    @staticmethod
    def from_mapping(m: dict[str, Any]) -> "Limits":
        # `finishes-within` is a promise to whoever is waiting. With no
        # `runs-for-at-most` written it is also the stop, because a promise the
        # system will not enforce is worse than no promise: the author believes
        # they capped it (this is exactly the hole architecture note Y10
        # describes, one field up).
        wall, wall_field = seconds(m.get("runs-for-at-most")), "runs-for-at-most"
        if wall is None:
            wall, wall_field = seconds(m.get("finishes-within")), "finishes-within"
        # `feel:` supplies `finishes-within:` when neither line is written —
        # its help says so, and `finishes-within:`'s says that is a stop — but
        # only where the author has said what happens at the stop. The schema
        # makes every written ceiling carry `when-it-runs-out:` so that this
        # module never picks the action; `feel:` carries no such requirement,
        # so a `feel:` with no `when-it-runs-out:` beside it stays a latency
        # band (`Slo`) and stops nothing, rather than stopping on an action
        # nobody chose.
        if wall is None and m.get("when-it-runs-out") is not None:
            from .slo import FEELS  # `slo` reads its figures through this module

            band = FEELS.get(str(m.get("feel") or "").strip())
            if band is not None:
                wall, wall_field = band[1], "feel"
        # Both halves of the cap, off one read. Two reads would be two chances
        # for the amount and the currency to come from different lines.
        cap = money(m.get("cost-per-request-under"))
        # The figure also has to be one a run can actually spend up to — and
        # that check is NOT here. It is on the value, in `__post_init__`, which
        # every route into a `Limits` goes through and this one does not: guarding
        # the reader left `Limits(cost_per_request_under=float('nan'))` and
        # `dataclasses.replace(..., cost_per_request_under=float('inf'))` running
        # six thousand dollars out under `unmetered=()`, which is the same
        # before-picture through a different door. See `__post_init__` for the
        # measurement and `_nothing_can_reach` for which figures qualify.
        return Limits(
            tool_calls_at_most=whole(m.get("tool-calls-at-most")),
            wall_clock_s=wall,
            wall_clock_field=wall_field,
            cost_per_request_under=None if cap is None else cap[0],
            cost_currency="" if cap is None else cap[1],
            tokens_at_most=whole(m.get("tokens-at-most")),
            asks_itself_at_most=whole(m.get("asks-itself-at-most")),
            when_it_runs_out=action(m.get("when-it-runs-out")),
            asks=str(m.get("asks") or ""),
        )

    def ceilings(self, steps_at_most: int | None = None) -> tuple[Ceiling, ...]:
        """Every ceiling in force, in a FIXED order.

        The order is the report's tie-break: when a step and a cost ceiling are
        reached by the same step, the same one is named every time. An arbitrary
        order would make the same trace produce two different explanations,
        which is the kind of instability that stops people trusting the report.
        """
        rows: list[Ceiling] = []
        if steps_at_most is not None:
            rows.append(step_ceiling(steps_at_most))
        if self.tool_calls_at_most is not None:
            rows.append(
                Ceiling(
                    "tool-calls-at-most", "tool_calls", self.tool_calls_at_most,
                    "tool calls", "tool-call-limit",
                )
            )
        if self.wall_clock_s is not None:
            rows.append(
                Ceiling(self.wall_clock_field, "seconds", self.wall_clock_s, "seconds", "time-limit")
            )
        if self.cost_per_request_under is not None:
            rows.append(
                Ceiling(
                    "cost-per-request-under", "money", self.cost_per_request_under,
                    # The author's currency, not this file's favourite one.
                    self.cost_currency, "cost-limit",
                )
            )
        if self.tokens_at_most is not None:
            rows.append(
                Ceiling("tokens-at-most", "tokens", self.tokens_at_most, "tokens", "token-limit")
            )
        return tuple(rows)

    def reached(
        self, meter: Meter, now: float, steps_at_most: int | None = None
    ) -> Reached | None:
        """The first ceiling this run has reached, or `None`."""
        for c in self.ceilings(steps_at_most):
            at = meter.reading(c.reads, now)
            if at >= c.limit:
                return Reached(c, at, self.when_it_runs_out)
        return None

    def kept_going(
        self, meter: Meter, now: float, steps_at_most: int | None = None
    ) -> "tuple[Limits, int | None]":
        """The ceilings after a person said to keep going: a fresh budget of the
        same size as the one written, from where the run is now.

        The harness has granted exactly this for the step ceiling since
        `ask-a-person` existed (`limit = start + spec.max_steps`), and only for
        that one: every other ceiling kept its figure while the meter kept its
        reading, so a run that reached `tool-calls-at-most` and was told to
        keep going reached it again at once, at the same place, and asked the
        same question under the same key. Every row is granted the same way
        here, so one answer buys one more of everything the author budgeted and
        a second continuation is a second decision.

        Called on the limits AS WRITTEN, never on the ones a previous answer
        produced: "the same size" is the author's figure, and growing it from a
        figure already grown would double the budget at every answer.

        Returns the new limits and the new step ceiling (`None` when no step
        ceiling is in force), because the step ceiling lives on
        `AgentSpec.max_steps` rather than here (see the module docstring).
        """
        grant: dict[str, Any] = {}
        for attr, _line, reads in _CEILING_FIELDS:
            figure = getattr(self, attr)
            if figure is None:
                continue
            more = meter.reading(reads, now) + figure
            grant[attr] = int(math.ceil(more)) if isinstance(figure, int) else more
        steps = None if steps_at_most is None else meter.steps + steps_at_most
        return replace(self, **grant), steps

    def unmeterable(
        self, counts_tokens: bool, prices_money: "bool | None" = None
    ) -> tuple[str, ...]:
        """Ceilings that cannot be enforced against this transport.

        Steps, tool calls and the clock are counted by the harness itself and
        always work. The other two are **two separate questions**, and running
        them together cost an author a ceiling they had written:

        * `counts_tokens` — does this transport say how many tokens a call
          carried? A live provider returns them, a scripted seam counts what it
          built, and a stand-in bound to no model at all cannot.
        * `prices_money` — does the catalogue publish a price for the bound
          model? A locally-served row may publish a window and no `cost:` block,
          which is exactly what a workspace on an air-gapped box writes.

        For a round these were one boolean, because `can_price` decided whether
        `usage()` existed at all. So a model with a known window and no price
        lost `tokens-at-most` as a side effect — contradicting that field's own
        help text, which promises *"This is the only ceiling that still bites
        when there is no price list: a model running on your own machine costs
        nothing per word, so a money cap cannot bound it and this can."* It
        landed on precisely the D17 author the workspace override layer exists
        for.

        `prices_money=None` means "the same as `counts_tokens`", which is what a
        caller that only knows one thing about a transport is honestly saying —
        a stand-in with no `usage()` can do neither.

        Quietly not enforcing a ceiling the author wrote is the failure T7 exists
        to name, so whatever is left over is reported rather than dropped: the
        author believing they capped their spend is precisely the situation a
        spend cap is for.

        What comes back is *"this run could not promise to hold these"*, which is
        not quite *"these held nothing"*. A transport bound to an AGENT rather
        than a model — `A2ATransport`, `prices_money=False`, because no
        catalogue row can price somebody else's agent — may still be TOLD a cost
        by that agent, and `harness._meter_usage` adds what it is told. So a
        money ceiling named here can also be the one that stopped the run. That
        pair is argued in full at `harness.RunResult.unmetered` and pinned by a
        test; the distinction matters because collapsing it in either direction
        loses something true.
        """
        if prices_money is None:
            prices_money = counts_tokens
        out = []
        for c in self.ceilings():
            if c.reads == "tokens" and not counts_tokens:
                out.append(c.field)
            elif c.reads == "money" and not prices_money:
                out.append(c.field)
        return tuple(out)

    def priced_at_nothing(self, per_million: "float | None") -> tuple[str, ...]:
        """Money ceilings that can never be reached, because the model is free.

        A ceiling nobody can measure and a ceiling that measures a genuine zero
        are different facts and only one of them is `unmeterable`. This is the
        second: `models/catalog.yaml` publishes five rows at
        `input-per-mtok: 0 USD / output-per-mtok: 0 USD` — a SOURCED zero, for
        weights this machine serves — so `can_price` says yes, `usage()` exists,
        and `unmeterable` is empty. The author is then told their `0.05 USD` cap
        is enforced against a meter that reads 0.00 on every call for the life of
        the workspace.

        `models/catalog.yaml` names this outcome as the thing to avoid — *"a
        spend cap that can never be reached, under an author who believes they
        capped their spend"* — and it arrives here from the other direction,
        through a genuinely-zero price rather than an unsourced one. It is a
        fact about the BINDING and not about the file, so it is reported at run
        time, where the bound model is known.

        `per_million` is what the catalogue charges for a million tokens in and
        a million out. `None` means unpriced, which is `unmeterable`'s business
        and not this one.
        """
        if per_million is None or per_million > 0.0:
            return ()
        return tuple(c.field for c in self.ceilings() if c.reads == "money")


def _nothing_can_reach(cap: float) -> bool:
    """Is this a ceiling NO reading can ever be at or above?

    Written for a money cap and true of every ceiling in the table, because the
    comparison is one comparison: `wall_clock_s` reads elapsed seconds through
    the same `at >= c.limit` and fails on `nan` and `inf` for exactly the same
    two arithmetic reasons. `Limits.__post_init__` therefore asks it about both
    float ceilings, and `learning.Permissions` asks it about a monthly spend.

    Every ceiling is compared as `spent >= limit`, so there are exactly two such
    figures and they fail for different arithmetic reasons:

    * `nan` — every comparison against a NaN is false, so the row is skipped at
      every spend there is, including `inf`;
    * `inf` — the comparison works perfectly and nothing can be larger.

    **`-inf` is deliberately not one of them, and this is a test rather than
    `not math.isfinite`.** `spent >= -inf` is true of every spend, so a cap of
    `-inf USD` fires on the FIRST step and stops the run loudly at
    `(0 of -inf USD)`. That is a wrong ceiling, not an absent one, and
    `tests/test_both_ports_read_every_way_a_spend_cap_is_written.py` pins it as
    *"the one non-finite cap a run can reach"* and compares that sentence across
    the two ports byte for byte. Dropping it here would delete the only value
    that exercises the non-finite arm of both reporters. All three are refused
    where an author writes one: `Schema::check_floor` puts a floor under money.
    """
    return math.isnan(cap) or cap == math.inf


def step_ceiling(limit: int) -> Ceiling:
    """The step ceiling as a row of the algebra.

    It is enforced by the loop's own bound rather than by `reached`, but it ends
    a run through the same door as every other ceiling — otherwise `steps-at-most`
    and `cost-per-request-under` drift into behaving differently, which is what
    happens whenever each limit is given its own ending.
    """
    return Ceiling("steps-at-most", "steps", float(limit), "steps", "step-limit")


#: Every way `RunResult.halted` can say "a ceiling ended this". A caller that
#: wants "did it finish?" asks about `final`; a caller that wants "did it run
#: out?" asks about these. Neither has to know the five names.
RAN_OUT: frozenset[str] = frozenset(
    {"step-limit", "tool-call-limit", "time-limit", "cost-limit", "token-limit"}
)


# ---------------------------------------------------------------- from config


def action(raw: Any) -> Action:
    """What the author wrote, or the safest of the three.

    The fallback is `stop-and-say-so` and it is reached in exactly two cases: a
    document with no ceilings at all, and a word `pact check` has already
    refused. It is the safe one because it is the only action that neither
    invents an answer nor spends anything further — falling back to
    `answer-with-what-it-has` would mean a typo silently buying a half-informed
    answer, which is the decision this whole field exists to keep with a person.
    """
    if isinstance(raw, str):
        try:
            return Action(raw.strip().lower())
        except ValueError:
            pass
    return Action.STOP


def steps_at_most(m: dict[str, Any], default: int) -> int:
    """The step ceiling. It lives on `AgentSpec.max_steps` rather than in
    `Limits` — see the module docstring for why there is only one copy.

    Written out rather than `whole(...) or default`, because `steps-at-most: 0`
    is falsy and would have silently become the default. A ceiling the author
    wrote and the system replaced is worse than one it refused.
    """
    written = whole(m.get("steps-at-most"))
    return default if written is None else written


def whole(raw: Any) -> int | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return int(str(raw).strip())
    except ValueError:
        return None


def seconds(raw: Any) -> float | None:
    """`30s`, `500ms`, `1m30s`, `2 minutes`, or a bare number of seconds.

    Reads the same SPELLINGS as the Rust coercer rather than approximating
    them: an author who writes `1m30s` and gets 1.0 back would have a ceiling
    ninety times tighter than the one they wrote, and nothing would say so.

    The two do not accept the same SET, and the difference runs one way only:
    the Rust side is stricter at both ends. It refuses a bare `90` as
    `schema/wrong-type` (ninety what?) and a length of time past the
    milliseconds it counts in as `schema/too-long-to-count`; this counts in
    Python floats, has no such end, and takes both. That is safe in the
    direction it runs — `pact check` is the gate, and nothing it refuses ever
    reaches a run — but it is a deliberate parting and not an oversight, so
    read this as "every spelling that gets through is read the same way here",
    not as "these two agree on what gets through".
    """
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip().lower()
    if not text:
        return None
    units = {
        "ms": 0.001, "millisecond": 0.001, "milliseconds": 0.001,
        "s": 1.0, "sec": 1.0, "secs": 1.0, "second": 1.0, "seconds": 1.0, "": 1.0,
        "m": 60.0, "min": 60.0, "mins": 60.0, "minute": 60.0, "minutes": 60.0,
        "h": 3600.0, "hr": 3600.0, "hrs": 3600.0, "hour": 3600.0, "hours": 3600.0,
        "d": 86400.0, "day": 86400.0, "days": 86400.0,
    }
    total, num, unit, any_part = 0.0, "", "", False
    chars = text + " "
    i = 0
    while i < len(chars):
        ch = chars[i]
        if ch.isdigit() or ch == ".":
            if unit:
                if (part := _part(num, unit, units)) is None:
                    return None
                total, num, unit, any_part = total + part, "", "", True
            num += ch
        elif _exponent_at(chars, i, num, unit):
            # `1e6s` — the `e` belongs to the figure, not to a unit called `e`.
            # Both readers took the other view for a round and both refused the
            # whole line for it; the Rust coercer takes this one now, so this
            # one does too, or a spelling `pact check` passes would be read here
            # as no ceiling at all.
            num += "e"
            if chars[i + 1] in "+-":
                i += 1
                num += chars[i]
        elif ch.isalpha():
            unit += ch
        elif ch.isspace():
            pass
        else:
            return None
        i += 1
    if num:
        if (part := _part(num, unit, units)) is None:
            return None
        total, any_part = total + part, True
    elif unit:
        return None
    return total if any_part else None


def _exponent_at(chars: str, i: int, num: str, unit: str) -> bool:
    """Whether `chars[i]` is the `e` of an exponent rather than a unit's first
    letter. `coerce::is_exponent_at`'s rule, in the same words: a figure has
    been written, no unit has started, and digits (with an optional sign)
    follow. No unit read here begins with `e`, so `2 seconds` is untouched —
    its unit starts at the `s`."""
    if i >= len(chars) or chars[i] != "e" or not num or unit:
        return False
    j = i + 1
    if j < len(chars) and chars[j] in "+-":
        j += 1
    return j < len(chars) and chars[j].isdigit()


def _part(num: str, unit: str, units: dict[str, float]) -> float | None:
    mult = units.get(unit)
    if mult is None:
        return None
    try:
        return float(num) * mult
    except ValueError:
        return None


# What separates the amount from the currency, and what counts as a number.
# Both are `coerce::money`'s, spelled out, because for a round this function read
# a WIDER language than the validator and the TypeScript port read a NARROWER
# one, so a string could be a ceiling here, no ceiling there, and no document at
# all — three answers to one line.
#
# `str.split()` and `float()` were the reference before, and each is one class
# too wide:
#
#   * `str.split()` splits on `U+001C`–`U+001F`, which `char::is_whitespace` does
#     not, so `5<US>USD` was five dollars here and a type error at the gate. This
#     set is `char::is_whitespace` exactly — measured: `0.05<NEL>USD` and
#     `0.05<NBSP>USD` both give `pact check` rc=0, `0.05<US>USD` and
#     `0.05<BOM>USD` both give rc=1 `schema/wrong-type`.
#   * `float()` takes digit-group underscores and any Unicode decimal digit —
#     `1_0` is ten, `١٢` and `１２` are twelve — and `parse::<f64>()` takes none
#     of them. Measured, each was a cap here and no cap in the TypeScript port,
#     and `pact check` refuses all three (`1_0 USD`, `０.05 USD`, `٠.05 USD` ->
#     rc=1 `schema/wrong-type`).
#
# The rule is therefore stated ONCE and in one direction: both readers read what
# `coerce::money` reads. Where they are still deliberately looser, `money` says
# so by name below.
_SEPARATOR = re.compile(
    "[\t\n\v\f\r\u0020\u0085\u00a0\u1680\u2000-\u200a"
    "\u2028\u2029\u202f\u205f\u3000]+"
)

#: A whole token `parse::<f64>()` reads as a number, and nothing else. `[0-9]`
#: rather than `\d`, because Python's `\d` is every Unicode decimal digit and
#: that is one of the two widenings this exists to have closed.
_FIGURE = re.compile(
    r"[+-]?(?:(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:e[+-]?[0-9]+)?|inf(?:inity)?|nan)",
    re.IGNORECASE,
)


def _figure(token: str) -> "float | None":
    """The token as a number, or `None` — never a prefix of it.

    `float(token)` after the pattern has passed is safe and gives the same
    double `parse::<f64>()` gives: both are correctly rounded, and every form
    the pattern admits is one `float()` also reads.
    """
    return float(token) if _FIGURE.fullmatch(token) else None


def money(raw: Any) -> "tuple[float, str] | None":
    """`0.05 USD`, `USD 0.05`, `$0.05` — the amount AND the currency it is in.

    Both halves come back together because for a round only the first half did.
    This returned the first parseable float and dropped every other token on the
    line, so `500 JPY` and `500 USD` were one value here, and the only place the
    currency could still have been recovered — `Ceiling.unit` — held the literal
    string `"USD"` whatever the file said. Measured: `cost-per-request-under: 500
    JPY` in the worked example ran against a meter priced in USD and reported
    *"(501 of 500 USD)"*. `Ty::Money` keeps its currency on the Rust side and
    FR-1.4.5 forbids converting or defaulting one; a reader that discards it
    breaks that promise in the one place a person reads the number.

    **The currency is still not converted.** Nothing here turns JPY into USD and
    nothing should: `pact check` refuses a money figure written in a currency the
    workspace's price list cannot charge in (`loader/currency-nothing-can-price`),
    which is what makes the comparison downstream sound. This half is the other
    one — saying, in the sentence a person reads, which currency they wrote.

    An empty currency means none was written. Only a spec built in code reaches
    that: `Ty::Money` does not coerce a bare `0.05`, so `pact check` refuses it in
    a file. It is empty rather than `USD` because inventing one is exactly the
    defaulting FR-1.4.5 rules out — and a run that quietly names a currency the
    author never chose is how this began.

    **Where this reader is looser than `coerce::money`, and where it is not.**
    The line above is the whole of it, and it is worth being exact, because a
    comment claiming this reader takes *"exactly what the gate lets through"*
    was measurably false in five directions at once. This reads what
    `coerce::money` reads — the same separators, the same number grammar, at
    most two tokens, `$` as a PREFIX and not as a character that may appear
    anywhere — with exactly two deliberate widenings, each of which costs the
    CURRENCY and never invents one:

    * a bare number is a cap with no currency, which is the paragraph above;
    * a second token that is not three ASCII letters is dropped rather than
      refusing the line, so `0 DOLLARS` is zero of nothing rather than no
      ceiling at all. `coerce::money` refuses the whole value there.

    Everything else the validator refuses is refused here, in both ports and for
    the same reason: a ceiling the gate would not accept, enforced silently by
    the run, is the silent degradation T7 forbids — and the `$` substitution
    that used to be global was that defect exactly. Measured through the shipped
    binary, all of these are `pact check` rc=1 `schema/wrong-type`, and all of
    them are now `None` in both ports: `0.05$`, `5 U$D`, `$0.05 USD`,
    `5 USD 7`, `0.1 usd 0.2`, `0.05 USD JPY`, `1_0 USD`, `０.05 USD`,
    `٠.05 USD`, `0.05<US>USD`.
    """
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return (float(raw), "")
    tokens = [t for t in _SEPARATOR.split(str(raw)) if t]
    # `$` is a PREFIX and the rest of the line must be one whole number —
    # `s.strip_prefix('$')` then `rest.trim().parse::<f64>().ok()?`, mirrored.
    # A global `replace("$", " USD ")` was here instead, and it invented a
    # currency out of a dollar sign anywhere in the string: `0.05$` and `5 U$D`
    # both came back as USD, and `$0.05 USD` — which the validator refuses
    # outright — came back as five pence. Splitting on the first token is enough
    # to find the prefix, because the first token starts at the first character
    # `trim()` would have kept.
    if tokens and tokens[0].startswith("$"):
        rest = [t for t in (tokens[0][1:], *tokens[1:]) if t]
        if len(rest) != 1:
            return None
        amount = _figure(rest[0])
        return None if amount is None else (amount, "USD")
    # Two tokens at most: `coerce::money` returns `None` on a third, and a
    # reader that dropped the surplus in silence enforced a ceiling the gate had
    # already refused — `5 USD 7` was five dollars in both ports.
    if not tokens or len(tokens) > 2:
        return None
    amount: float | None = None
    currency = ""
    for part in tokens:
        if amount is None:
            found = _figure(part)
            if found is not None:
                amount = found
                continue
        # Three ASCII letters is what the validator accepts as a currency
        # (`coerce::money` refuses anything else), so it is what is looked for
        # here. Reading it lexically rather than positionally is what lets one
        # reader take `0.05 USD`, `USD 0.05` and `$0.05` — the three spellings
        # the schema's own help offers — without three branches.
        if not currency and len(part) == 3 and part.isascii() and part.isalpha():
            currency = part.upper()
    return None if amount is None else (amount, currency)


def _round(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:.4g}"
