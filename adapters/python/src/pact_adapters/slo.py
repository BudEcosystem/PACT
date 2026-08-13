"""The latency promises, and what `feel:` supplies when nobody wrote them.

**This module reports; it does not stop a run.** That is still true of
`against_the_catalogue`, added for AC-3.6's resolve-time clause: it compares two
ceilings the author wrote against a price the catalogue published and names the
one that governs nothing. It refuses nothing and stops nothing.

**This module reports; it does not stop a run.** It used to look as though it
did — it carried a `Budget` with `note_first_token`, `check_elapsed` and
`add_cost`, all raising `SloBreach` mid-run — and nothing in `src/` ever built
one. The only import in the repository was this module's own test, so
`finishes-within` and `cost-per-request-under` were enforced by `Limits` and by
nothing else, while a reader of this file believed there were two enforcers.
That construct is deleted rather than wired: `Limits.reached` already stops a run
on both of those ceilings, and a second overlapping mechanism is how one ceiling
comes to mean two things.

What is left is the half `Limits` genuinely does not do:

* **TTFT means the first token, not the first step.** If the first thing an
  agent does is call a tool, time-to-first-token has not happened yet. Measuring
  it as "time to first step" makes a tool-using agent look slower than it is,
  and the four surveyed systems each defined this differently. Nothing here
  measures it — `first-reply-within` and `per-word-under` come back on
  `RunResult.unmetered`, so an author who wrote a latency promise is told it is
  holding nothing rather than left to assume it is.
* **Percentiles need a sample size.** A p95 claim over three runs is not a
  measurement. `Slo.assess` refuses rather than reporting a number that reads
  like evidence, and `measured-at:` is the field that governs it.
* **`feel:` is a default, not a decoration.** One word supplies the two latency
  figures for the common case. Its help promised exactly that and nothing read
  it; now the numbers come from here and anything the author wrote wins.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .limits import _HeldNothing, _nothing_can_reach, money, seconds


@dataclass(frozen=True)
class Slo:
    """Budgets for one run. `None` means the metric is not governed.

    FROZEN, and that is load-bearing rather than tidiness. `__post_init__` below
    argues that a cap nothing can reach is caught *"on construction, where every
    route in meets"* — the argument `Limits` earns by being frozen. This class
    was a bare `@dataclass` while making that claim, and the claim was measured
    false::

        s = Slo.from_mapping({'cost-per-request-under': '0.05 USD'})
        s.cost_per_request_under = float('nan')
        -> cap=nan  unmetered()=()

    The same assignment on a `Limits` raises `FrozenInstanceError`. No writer
    existed in `src/` (`Slo(` appears at one site, `from_mapping` below), so this
    was latent rather than live — and a guarantee that holds only while nobody
    writes the line is not the guarantee the docstring was making. `assess` and
    `against_the_catalogue` only read, so freezing costs nothing.
    """

    first_reply_within_s: float | None = None   # TTFT
    finishes_within_s: float | None = None      # end-to-end
    cost_per_request_under: float | None = None
    #: The currency the cap was written in, carried for the same reason
    #: `Limits.cost_currency` is: a budget reported back in a currency the author
    #: never typed is a figure they cannot check against their own file.
    cost_currency: str = ""
    per_word_under_s: float | None = None       # TPOT
    measured_at: str = "p95"
    #: Which of these the AUTHOR typed, as opposed to which `feel:` supplied.
    #: Only a promise somebody made is worth reporting as unheld — telling a
    #: reader their `feel: interactive` default is unenforced is noise, and noise
    #: is what makes a report stop being read.
    written: tuple[str, ...] = ()
    #: The spend cap the author wrote WHEN no amount of money can ever be at or
    #: above it. The figure, moved off `cost_per_request_under` and not deleted,
    #: exactly as `Limits.cap_nothing_can_reach` carries it and for the same two
    #: reasons: the figure is what justifies the report, and a record made of a
    #: figure is one `__post_init__` can check rather than take on trust.
    #:
    #: This is the REPORTING half, and for a round the drop shipped without it.
    #: Measured through the real harness with `limits=Limits()` so the two
    #: readers are decoupled — a transport pricing every call at 1000 USD, six
    #: steps::
    #:
    #:     Slo(cost_per_request_under=nan) -> cap=None unmetered=() spent=6000.0
    #:     Slo(cost_per_request_under=inf) -> cap=None unmetered=() spent=6000.0
    #:
    #: Six thousand dollars under a cap the author typed and this object had
    #: silently deleted, with every honesty channel empty. `cost-per-request-under`
    #: is `surface: S-GOV, tier: core` in `spec/schema.yaml`, and T7 and FR-8.1.1
    #: say a lossy operation MUST emit a report entry — so the drop and the report
    #: are one change, the way `Limits.__post_init__` pairs them and the way
    #: `learning.Permissions` pairs `per_month()` with `per_month_holds_nothing()`.
    #: `unmetered()` below is where it comes out; `harness` reads that.
    #:
    #: A PRIVATE record and not a public float, for the reason `_HeldNothing`
    #: gives at length: while this was `cap_nothing_can_reach: float | None`, the
    #: claim was spellable at the constructor, and the predicate was no gate on
    #: it because a forger simply passes a figure the predicate agrees with.
    #: Measured on the tree before this, no edits::
    #:
    #:     Slo(cap_nothing_can_reach=float('inf')).unmetered()
    #:       -> ('cost-per-request-under',)     <- no cost line anywhere
    #:     Slo(cap_nothing_can_reach=30.0).unmetered()
    #:       -> ()                              <- the only case the test saw
    #:
    #: — a report telling an author to go and fix a line they never wrote, which
    #: is the wrong-diagnosis failure this whole guard exists to remove.
    #: `cap_nothing_can_reach` below is a read-only view over it, so the readers
    #: that ask *"was a figure recorded?"* (`harness.run`,
    #: `scoring._unmetered_caveats`) are unchanged and the writers are gone.
    _held_nothing: "_HeldNothing | None" = None

    def __post_init__(self) -> None:
        """A spend cap no run can be at or above is not one, here either.

        The THIRD reader of `cost-per-request-under:` — `Limits.from_mapping`,
        `limitsFrom` in the TypeScript port, and this — and for a round the
        guard was a property of the first two readers rather than of the cap.
        That is the same mistake one level up from guarding `from_mapping`
        instead of the value, so it is fixed the same way and in the same place:
        on construction, where every route in meets.

        `NaN USD` went silent here rather than wrong — `against_the_catalogue`
        short-circuits on it, because `cheapest > nan` and `dearest < nan` are
        both false. `inf USD` did not. Measured before this guard, with
        `tokens-at-most: 1000` and a priced model::

            `cost-per-request-under: inf USD` cannot be reached on a-model. The
            whole of `tokens-at-most: 1000` costs at most 0.0010 at the published
            price, so the run always stops on tokens and the money cap never binds.

        which is a true sentence with the WRONG REASON in it: the cap is
        unreachable because it is infinity, not because a thousand tokens are
        cheap, and that sentence reads identically for a perfectly sensible cap
        of 1.00 USD. An author sent to *"lower `cost-per-request-under` below
        0.0010"* has been pointed at the wrong line. Moved onto
        `cap_nothing_can_reach` instead, so the one thing said about it is the
        true one, on `RunResult.unmetered` — and that sentence used to be FALSE
        of this object. The drop shipped without the report: `unmetered()`
        returned `self.written`, which is built from `first-reply-within` and
        `per-word-under` only and could never carry this name, so the figure was
        discarded and nothing anywhere said so. See `cap_nothing_can_reach` for
        the six thousand dollars that measured it.

        Three arms, mirroring `Limits.__post_init__` line for line: a figure
        nothing can reach is moved onto the record; a real figure arriving
        clears the record; and a record with no figure beside it is CARRIED, so
        `replace(slo, measured_at='p99')` on an object whose cap has already
        been moved off still says what it said.

        Being handed a claim from outside is refused by TYPE and not by the
        predicate, and this is where that mattered: the third arm used to drop a
        record the predicate disagreed with, which let every record it AGREED
        with through — `Slo(cap_nothing_can_reach=float('inf'))` reporting
        `cost-per-request-under` for an object with no cost line. `_held_nothing`
        above carries the measurement.

        THE CURRENCY IS KEPT, and it used to be cleared. It is the half of the
        authored line that parsed, `CeilingsDisagree.currency` is the only reader
        and `against_the_catalogue` returns before reaching it when the amount is
        gone — so clearing it destroyed something true and bought nothing.
        `Limits.__post_init__` gives the measurement that made this matter there.

        `_nothing_can_reach` says which figures qualify and why `-inf` is not
        one of them.
        """
        if self._held_nothing is not None and not isinstance(
            self._held_nothing, _HeldNothing
        ):
            raise TypeError(
                "`_held_nothing` is the record this object writes about a figure "
                "it was handed, not a claim a caller can hand in: "
                f"{self._held_nothing!r}"
            )
        cap = self.cost_per_request_under
        if cap is not None and _nothing_can_reach(cap):
            object.__setattr__(self, "cost_per_request_under", None)
            object.__setattr__(
                self,
                "_held_nothing",
                _HeldNothing((("cost-per-request-under", "money", cap),)),
            )
        elif cap is not None:
            object.__setattr__(self, "_held_nothing", None)
        elif self._held_nothing is not None:
            kept = tuple(
                row
                for row in self._held_nothing.rows
                if row[0] == "cost-per-request-under"
                and row[1] == "money"
                and _nothing_can_reach(row[2])
            )
            object.__setattr__(
                self, "_held_nothing", _HeldNothing(kept) if kept else None
            )

    @property
    def cap_nothing_can_reach(self) -> float | None:
        """The figure this object was handed that no spend can be at or above.

        A read-only view over `_held_nothing`, so `harness.run` and
        `scoring._unmetered_caveats` go on asking the question they asked and
        there is no longer a constructor argument that answers it.
        """
        record = self._held_nothing
        return None if record is None else record.rows[0][2]

    @staticmethod
    def from_mapping(limits: dict[str, Any]) -> "Slo":
        band = FEELS.get(str(limits.get("feel") or "").strip())
        # One read for both halves of the cap, exactly as `Limits.from_mapping`
        # takes it — two reads is how the amount and the currency come to be
        # taken from different lines.
        cap = _money(limits.get("cost-per-request-under"))
        return Slo(
            # `feel:` supplies what the author did not write, and never overrides
            # what they did. Its own help says this one word "sets the latency
            # band and the give-up time from the built-in defaults" — and for a
            # round `feel` appeared in the schema, in the worked example and in
            # two tests that assert it is PRESENT, and in no code that acted on
            # it. A `tier: core` field making a behavioural claim nothing keeps
            # is the failure this project is written against.
            first_reply_within_s=_seconds(limits.get("first-reply-within"))
            or (band[0] if band else None),
            finishes_within_s=_seconds(limits.get("finishes-within"))
            or (band[1] if band else None),
            cost_per_request_under=None if cap is None else cap[0],
            cost_currency="" if cap is None else cap[1],
            per_word_under_s=_seconds(limits.get("per-word-under")),
            measured_at=str(limits.get("measured-at") or "p95"),
            written=tuple(
                f for f in ("first-reply-within", "per-word-under")
                if _seconds(limits.get(f)) is not None
            ),
        )

    def unmetered(self) -> tuple[str, ...]:
        """The promises nothing on this run measures, and the cap this object
        could not carry.

        Reported rather than dropped, the same door every other unenforceable
        line leaves by. Measuring a first token needs the transport to say when
        one arrived, and none of the seven does; measuring the gap between words
        needs a token stream, and the harness has whole answers.

        `cost-per-request-under` joins them when the figure written was one no
        spend can be at or above. It is NOT enough that `Limits` reports the same
        name: the two objects usually take the same authored `limits:` block, and
        that coupling is the only reason the silence here was invisible. Built in
        code they come apart — `AgentSpec(slo=Slo(cost_per_request_under=nan),
        limits=Limits())` measured `unmetered=()` with 6000 USD spent — and this
        is the object that read the line, so this is the object that has to
        answer for it. `harness` unions the two lists and drops the duplicate.
        """
        held = ("cost-per-request-under",) if self.cap_nothing_can_reach is not None else ()
        return self.written + held


    def assess(self, samples: list[float], metric: str, min_samples: int = 20) -> str:
        """Percentile verdict, or a refusal to give one.

        Reporting a p95 over a handful of runs would be the same failure as an
        eval bar over three cases: a number that reads like evidence and is not.
        """
        budget = getattr(self, {"e2e": "finishes_within_s", "ttft": "first_reply_within_s"}[metric])
        if budget is None:
            return "UNGOVERNED"
        if len(samples) < min_samples:
            return f"UNDECIDED ({len(samples)} samples, need {min_samples} for {self.measured_at})"
        ordered = sorted(samples)
        # `mean` and `max` are two of the six values `measured-at:` accepts, and
        # neither is a percentile. They fell to this dict's DEFAULT of 0.95 and
        # were then printed under the author's own word — MEASURED over samples
        # 1..100, `measured-at: max` reported `max=95.00s` when the true maximum
        # is 100.0, and `mean` reported `mean=95.00s` when the true mean is 50.5.
        #
        # An S-GOV verdict labelled with a word it does not mean is worse than no
        # verdict: the label is the whole reason somebody chose `max` — they
        # wanted the worst case, and were shown a number that hides it.
        if self.measured_at == "mean":
            value = sum(ordered) / len(ordered)
        elif self.measured_at == "max":
            value = ordered[-1]
        else:
            q = {"p50": 0.50, "p90": 0.90, "p95": 0.95, "p99": 0.99}.get(self.measured_at, 0.95)
            value = ordered[max(0, int(len(ordered) * q) - 1)]
        return f"{'PASS' if value <= budget else 'FAIL'} ({self.measured_at}={value:.2f}s vs {budget:.2f}s)"

@dataclass(frozen=True)
class CeilingsDisagree:
    """Two ceilings the author wrote that cannot both mean what they say.

    The typed, actionable half of AC-3.6's **resolve-time** clause, and the only
    half this repository can honestly hold. `tokens-at-most` and
    `cost-per-request-under` are both ceilings on one request, and the catalogue
    knows the exchange rate between them — so before a single call is made it is
    decidable which of the two actually stops a run, and whether the other was
    ever capable of it.

    Not a refusal. Both spellings are legal and neither is a mistake in itself;
    what is worth saying is that ONE OF THEM IS DEAD, because an author who wrote
    two ceilings believes they have two.
    """

    #: `"cost"` if the money cap bites first and the token ceiling is unreachable,
    #: `"tokens"` if the token ceiling bites first and the money cap never binds.
    #:
    #: There is no `"currency"` answer, and finding out why is the most useful
    #: thing this check did. Mutating `USD` out of the sentence below left the
    #: suite green, which exposed that `resolve._cost` reads `raw.split()[0]` and
    #: discards the currency word — so a cap in JPY would be compared against a
    #: price in USD as a plain number. A third branch was written for it, and
    #: then the loader turned out to refuse the case already, in better words:
    #: `loader/currency-nothing-can-price` says *"PACT never turns one currency
    #: into another, so this figure would be compared with a USD one as a plain
    #: number — and 1000 JPY is not 1000 USD"*. The branch was deleted rather than
    #: kept, because a second enforcer of a rule already enforced is precisely how
    #: one ceiling comes to mean two things — this module's own argument, applied
    #: to this module. `test_the_loader_refuses_a_cap_nothing_can_price` pins it.
    bites: str
    cap: float
    currency: str
    tokens: int
    #: What the token ceiling costs at this model's published price, at the
    #: cheapest possible split of those tokens (all input).
    at_least: float
    #: And at the dearest (all output). Both, because a range is the honest shape:
    #: how a run splits its budget is not knowable here.
    at_most: float
    model: str

    def __str__(self) -> str:
        if self.bites == "cost":
            return (
                f"`tokens-at-most: {self.tokens}` cannot be reached on {self.model}. "
                f"Those tokens cost {self.at_least:.4f}–{self.at_most:.4f} "
                f"{self.currency or 'USD'} at the published price, and "
                f"`cost-per-request-under` stops the run at {self.cap} — so the "
                f"money cap always bites first and the token ceiling governs "
                f"nothing.\n  fix: raise `cost-per-request-under` above "
                f"{self.at_most:.4f}, or lower `tokens-at-most` to what you meant "
                f"to allow."
            )
        return (
            f"`cost-per-request-under: {self.cap} {self.currency or 'USD'}` cannot "
            f"be reached on {self.model}. The whole of `tokens-at-most: "
            f"{self.tokens}` costs at most {self.at_most:.4f} at the published "
            f"price, so the run always stops on tokens and the money cap never "
            f"binds.\n  fix: lower `cost-per-request-under` below "
            f"{self.at_least:.4f} if you meant it to govern, or delete it — a "
            f"ceiling nothing can reach reads like a control and is not one."
        )


def against_the_catalogue(
    slo: "Slo",
    tokens_at_most: "int | None",
    model: str,
    price_of: "Any",
) -> "CeilingsDisagree | None":
    """Do the author's two request ceilings agree, at this model's price?

    **This is resolve time, and it is deliberately not a second enforcer.**
    `slo.py` records why a run-time SLO mechanism was deleted rather than wired:
    `Limits.reached` already stops a run on `finishes-within` and
    `cost-per-request-under`, and *"a second overlapping mechanism is how one
    ceiling comes to mean two things"*. Nothing here stops anything. It reads two
    numbers an author typed and one the catalogue published, and reports a
    contradiction between them **before** it costs anybody a run to find.

    `price_of` is handed in — `(in_tokens, out_tokens) -> float | None` — for the
    reason every other callable in this package is: `slo` is on the run path and
    the price list is on a disk (P-1). `None` back from it means this
    distribution cannot source the model's price, and an unpriced row produces no
    finding at all rather than a finding computed from a zero.

    **There is no latency half, and that is a finding rather than a gap.** The
    criterion asks for TTFT/TPOT *"against catalogue estimates"*, and a catalogue
    latency figure is not a property of a model: the same weights answer in
    200 ms on an H100 and 8 s on a laptop. Publishing one would be the exact
    substitution `models/catalog.yaml` refuses for price — *"a number nobody
    published, given to an author as though somebody had"* — and would hand out
    resolve-time verdicts that are wrong on most machines. So the catalogue
    publishes no latency, `first-reply-within` and `per-word-under` come back on
    `RunResult.unmetered`, and the author is told nothing measures them.
    """
    if slo.cost_per_request_under is None or not tokens_at_most:
        return None
    cheapest = price_of(tokens_at_most, 0)
    dearest = price_of(0, tokens_at_most)
    if cheapest is None or dearest is None:
        return None

    cap = slo.cost_per_request_under
    # The two are known to be in the same currency, and not by assumption: the
    # loader refuses a workspace whose cap names money its price list does not
    # deal in (`loader/currency-nothing-can-price`), so a document that reaches
    # here has already been held to it. Checking again would be a second
    # enforcer, which is the thing this module deleted a `Budget` to avoid.
    if cheapest > cap:
        # Every way of spending the token allowance costs more than the money
        # cap, so the run stops on money first, always.
        bites = "cost"
    elif dearest < cap:
        # No way of spending it reaches the money cap, so the run stops on
        # tokens first, always.
        bites = "tokens"
    else:
        # The ranges overlap: which ceiling stops a given run depends on how that
        # run split its budget, and both are live. Nothing to report.
        return None
    return CeilingsDisagree(
        bites=bites, cap=cap, currency=slo.cost_currency,
        tokens=tokens_at_most, at_least=cheapest, at_most=dearest, model=model,
    )


#: What one word of `feel:` means, as `(first reply, whole thing)` in seconds.
#:
#: Written here rather than in the schema because they are DEFAULTS a runtime
#: applies, not values an author typed — a number in `spec/schema.yaml` would
#: read as something they had chosen. A host with different hardware overrides
#: the two fields directly, which is what they are for.
FEELS: dict[str, tuple[float, float]] = {
    "voice": (0.3, 5.0),
    "interactive": (1.0, 30.0),
    "conversational": (2.0, 60.0),
    "background": (10.0, 600.0),
    "batch": (60.0, 3600.0),
}


# One reader for `30s` and `0.05 USD`, shared with the termination algebra that
# enforces them. Two readers is how `finishes-within` comes to mean one thing to
# the report and another to the run that is supposed to be held to it.
_seconds = seconds
_money = money
