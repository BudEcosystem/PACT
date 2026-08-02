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

from dataclasses import dataclass
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
    #: the line the author actually wrote.
    wall_clock_field: str = "runs-for-at-most"
    cost_per_request_under: float | None = None
    #: Which currency the spend cap was written in — `USD` for
    #: `cost-per-request-under: 0.05 USD`. Kept beside the amount for the same
    #: reason `wall_clock_field` is kept beside the seconds: the report has to be
    #: able to quote the line the author actually wrote. Empty means a bare
    #: number, which only a spec built in code can carry — see [`Ceiling.unit`].
    cost_currency: str = ""
    tokens_at_most: int | None = None
    when_it_runs_out: Action = Action.STOP
    #: The named question to put to a person when the action is `ask-a-person`.
    asks: str = ""

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
        # Both halves of the cap, off one read. Two reads would be two chances
        # for the amount and the currency to come from different lines.
        cap = money(m.get("cost-per-request-under"))
        return Limits(
            tool_calls_at_most=whole(m.get("tool-calls-at-most")),
            wall_clock_s=wall,
            wall_clock_field=wall_field,
            cost_per_request_under=None if cap is None else cap[0],
            cost_currency="" if cap is None else cap[1],
            tokens_at_most=whole(m.get("tokens-at-most")),
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

    Mirrors the Rust coercer rather than approximating it: an author who writes
    `1m30s` and gets 1.0 back would have a ceiling ninety times tighter than the
    one they wrote, and nothing would say so.
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
    for ch in text + " ":
        if ch.isdigit() or ch == ".":
            if unit:
                if (part := _part(num, unit, units)) is None:
                    return None
                total, num, unit, any_part = total + part, "", "", True
            num += ch
        elif ch.isalpha():
            unit += ch
        elif ch.isspace():
            continue
        else:
            return None
    if num:
        if (part := _part(num, unit, units)) is None:
            return None
        total, any_part = total + part, True
    elif unit:
        return None
    return total if any_part else None


def _part(num: str, unit: str, units: dict[str, float]) -> float | None:
    mult = units.get(unit)
    if mult is None:
        return None
    try:
        return float(num) * mult
    except ValueError:
        return None


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
    """
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return (float(raw), "")
    amount: float | None = None
    currency = ""
    for part in str(raw).replace("$", " USD ").split():
        if amount is None:
            try:
                amount = float(part)
                continue
            except ValueError:
                pass
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
