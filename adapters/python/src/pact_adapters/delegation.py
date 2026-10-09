"""Join policy — how an agent waits for the team, and how it shares out what it
may spend on them.

Eve takes three decisions here in code and lets an author say none of them:

1. the parent is parked until **every** delegated child resolves — an
   all-or-nothing barrier;
2. the children are started **one after another**;
3. the parent's token budget is **split evenly** across them.

Each of those is a separate question with a different right answer per system,
and bundling them into one hardcoded behaviour has concrete costs. A five-way
"whoever answers first" waits for the slowest of the five. Four fifths of the
budget stays reserved for children whose answers are thrown away. A child that
fails takes the parent down even when two of its three siblings agreed.

So they are three separate authored fields here — `waits-for`, `starts`,
`divides-the-budget` — plus `if-someone-fails`, which is the axis Eve fixes at
"all-or-nothing" and never names.

**Why `if-someone-fails` rather than more join modes.** Restate ships four
combinators (`ALL_COMPLETED`, `ALL_SUCCEEDED_OR_FIRST_FAILED`, …) and the
architecture draft §7.3 listed `all` and `all-settled` as separate modes. They
are one mode and one failure rule: `everyone` + `carry-on` is all-settled,
`everyone` + `stop-the-others` is all-succeeded-or-first-failed. Two fields
covering six named combinations beats six names, and it lets the failure rule
apply to a quorum too — which no combinator vocabulary in the corpus can say.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Awaitable, Callable, Mapping, Sequence

from .events import Bus
from .limits import seconds

#: Floating-point slack when comparing spend against an allowance. Refusing a
#: charge that is over by 1e-15 would be arithmetic noise reported as a policy
#: breach.
_EPS = 1e-9


class Waits(str, Enum):
    """How much of the team has to come back before the parent carries on."""

    EVERYONE = "everyone"
    ANYONE = "anyone"
    ENOUGH = "enough-of-them"
    FIRST_GOOD = "the-first-good-answer"
    IN_TIME = "whoever-answers-in-time"


class Starts(str, Enum):
    #: Eve's behaviour is `ONE_AFTER_ANOTHER`, and it is the only one it has.
    ALL_AT_ONCE = "all-at-once"
    ONE_AFTER_ANOTHER = "one-after-another"


class Divides(str, Enum):
    EVENLY = "evenly"
    BY_SHARE = "by-share"
    AS_NEEDED = "as-needed"


class OnFailure(str, Enum):
    CARRY_ON = "carry-on"
    STOP_THE_OTHERS = "stop-the-others"
    ASK_A_PERSON = "ask-a-person"


class MayStart(str, Enum):
    """Who an agent may bring in while it runs, beyond its `team:` (02P §8.1).

    R16 narrowed to governed run-time composition: what can happen is reviewed
    (the catalogue a run draws from, the `uses:` a narrowed agent may inherit,
    the ceilings), and only order and composition inside those bounds are left
    to the model. Bounded by `limits.starts-at-most:` and
    `limits.nests-at-most:`, which `pact check` requires beside it (WF-33).
    """

    #: Any agent of the workspace that runs, picked by the model.
    CATALOGUE = "catalogue"
    #: An agent the model describes on the spot, with its starter's `uses:` or
    #: fewer, on its starter's model.
    NARROWED_NEW = "narrowed-new"


class BadTeamwork(ValueError):
    """A join policy that can never do what it says.

    Raised at load time, not mid-run: an author who wrote `enough-is: 4` for a
    two-person team should hear about it before a customer is waiting.

    "Load time" was a smaller claim than it sounded, though, and the two
    arithmetic rules below say why. It means the moment a RUN loads the
    document — in Python, in a process decision D13's author never starts. So a
    `shares:` block adding up to 150% of one pot reached the person who typed it
    only if they happened to run the harness; `pact check` printed
    `OK — … loaded cleanly (468 settings).` and exited 0.
    `crates/pact-loader/src/teamwork.rs` now holds both rules where the author
    is, and everything here is the second line of defence: a document handed
    straight to the harness, or built in memory by a test or a runtime, has not
    been through `pact check` and must still be refused rather than run.
    """


class OverBudget(RuntimeError):
    """A team member tried to spend past its share."""

    def __init__(self, member: str, allowance: float, asked: float, how: "Divides") -> None:
        fix = (
            "raise `cost-per-request-under` in the agent's limits, or set "
            "`divides-the-budget: as-needed` in its teamwork so the team draws "
            "from one pot instead of fixed shares"
            if how is not Divides.AS_NEEDED
            else "raise `cost-per-request-under` in the agent's limits"
        )
        super().__init__(
            f"{member} tried to spend {asked:.4g} but only {allowance:.4g} is left "
            f"for it. fix: {fix}."
        )
        self.member, self.allowance, self.asked = member, allowance, asked


# --------------------------------------------------------------------- outcomes


#: What happened to one member. `state` is deliberately five words rather than a
#: boolean: "did not answer in time" and "was not waited for" are different
#: facts about a run, and Eve's barrier can express neither.
ANSWERED = "answered"
FAILED = "failed"
CANCELLED = "not-waited-for"
OUT_OF_TIME = "out-of-time"
NOT_ASKED = "not-asked"


@dataclass(frozen=True)
class Answer:
    member: str
    text: str = ""
    ok: bool = False
    error: str = ""
    state: str = NOT_ASKED
    spent: float = 0.0


@dataclass
class Handoff:
    """The outcome of one join."""

    waits_for: Waits
    answers: tuple[Answer, ...]
    satisfied: bool
    why: str = ""
    #: Set when `if-someone-fails: ask-a-person` fired. Names who failed.
    needs_a_person: str = ""

    @property
    def good(self) -> tuple[Answer, ...]:
        return tuple(a for a in self.answers if a.ok)

    @property
    def unfinished(self) -> tuple[str, ...]:
        """Members with no answer — named, never silently dropped.

        Eve's barrier has no such category, because every child either resolves
        or the parent never wakes up.
        """
        return tuple(a.member for a in self.answers if a.state != ANSWERED)

    @property
    def spent(self) -> float:
        return sum(a.spent for a in self.answers)

    def said(self, member: str) -> str:
        """What goes into the transcript for one member.

        A member that did not answer still produces a line. The model must be
        able to tell "fraud-checker said nothing suspicious" from "fraud-checker
        was never waited for", and a silent gap reads as the former.
        """
        for a in self.answers:
            if a.member != member:
                continue
            if a.state == ANSWERED:
                return a.text
            if a.state == FAILED:
                return f"error: {member} could not answer: {a.error}"
            if a.state == OUT_OF_TIME:
                return f"(no answer: {member} did not reply in time)"
            if a.state == CANCELLED:
                return (
                    f"(no answer: {member} was stopped because {self.why})"
                    if self.why
                    else f"(no answer: {member} was still working when "
                    f"{self.waits_for.value} was met)"
                )
            return (
                f"(not asked: {self.why})"
                if self.why
                else f"(not asked: {self.waits_for.value} was already met)"
            )
        return f"(not asked: {member} is not on the team)"


# ----------------------------------------------------------------- the budget


class Pool:
    """The parent's budget while the team is working.

    The three policies differ in exactly one place — what a member is allowed to
    spend — so they are one class and not three.

    A total of zero (or less) means no budget was declared, and nothing is
    metered. That mirrors `Slo`, where an unset metric is ungoverned rather than
    zero: a limit nobody wrote must never become a limit of nothing.
    """

    def __init__(
        self,
        total: float,
        how: Divides,
        members: Sequence[str],
        shares: Mapping[str, float] | None = None,
    ) -> None:
        self.total = float(total)
        self.how = how
        self.members = tuple(members)
        self.shares = dict(shares or {})
        self._spent: dict[str, float] = {m: 0.0 for m in self.members}

    @property
    def metered(self) -> bool:
        return self.total > 0.0

    @property
    def spent_total(self) -> float:
        return sum(self._spent.values())

    def spent_by(self, member: str) -> float:
        return self._spent.get(member, 0.0)

    def allowance(self, member: str) -> float:
        """What this member may STILL spend — never the size of its share.

        All three policies answer the same question and so all three subtract
        what has already gone. The two fixed splits used to return the whole
        share every time, which was harmless while nothing ever charged and
        became a mis-statement the moment something did: a member on its second
        delegation was told it could spend 0.03 with 0.01 left, and
        `step.delegate.started` published that figure. Overstating a budget is
        the same class of silent wrongness as not enforcing one (T7).
        """
        if not self.metered:
            return math.inf
        if self.how is Divides.AS_NEEDED:
            # No reservation: what is left of the whole pot. This is the policy
            # that makes a race cheap — the four members that get cancelled
            # never held anything back from the one that answered.
            return max(0.0, self.total - self.spent_total)
        return max(0.0, self.share_of(member) - self._spent.get(member, 0.0))

    def share_of(self, member: str) -> float:
        """The size of this member's slice, before anything is taken out of it."""
        if not self.metered:
            return math.inf
        if self.how is Divides.AS_NEEDED:
            return self.total
        if self.how is Divides.BY_SHARE:
            return self.total * self.shares.get(member, 0.0)
        return self.total / max(1, len(self.members))

    def charge(self, member: str, amount: float) -> None:
        if amount < 0:
            raise ValueError("a member cannot spend a negative amount")
        if not self.metered:
            self._spent[member] = self._spent.get(member, 0.0) + amount
            return
        left = self.allowance(member)
        if amount > left + _EPS:
            raise OverBudget(member, left, amount, self.how)
        self._spent[member] = self._spent.get(member, 0.0) + amount


class Grant:
    """One member's slice of the parent's budget, plus what it was asked.

    `allowance` is read every time rather than captured, because under
    `as-needed` it genuinely changes while the team works.
    """

    def __init__(
        self,
        member: str,
        pool: Pool,
        request: str = "",
        so_far: tuple[Answer, ...] = (),
    ) -> None:
        self.member = member
        self.pool = pool
        self.request = request
        #: What earlier members said. Empty under `all-at-once` — nobody has
        #: finished yet — and the whole point of `one-after-another`.
        self.so_far = so_far
        self.spent = 0.0

    @property
    def allowance(self) -> float:
        return self.pool.allowance(self.member)

    def spend(self, amount: float) -> None:
        self.pool.charge(self.member, amount)
        self.spent += amount


#: What the harness supplies: something that can run one team member.
Asker = Callable[[Grant], Awaitable[str]]


# ------------------------------------------------------------- the policy itself


@dataclass(frozen=True)
class Teamwork:
    """The authored join policy.

    Defaults are PACT's answer, not Eve's: wait for everyone (same), but start
    them at the same time (Eve starts serially), split evenly (same), and report
    a failure rather than taking the parent down with it (Eve's barrier is
    all-or-nothing). Only the second and fourth differ, and both are strictly
    more useful with no configuration.
    """

    waits_for: Waits = Waits.EVERYONE
    enough_is: int = 0
    gives_up_after: float | None = None
    starts: Starts = Starts.ALL_AT_ONCE
    divides_the_budget: Divides = Divides.EVENLY
    shares: Mapping[str, float] = field(default_factory=dict)
    if_someone_fails: OnFailure = OnFailure.CARRY_ON
    #: Who may be brought in while the agent runs (`may-start:`); empty means
    #: nobody beyond `team:`, which is every document written before 02P §8.1.
    may_start: tuple[MayStart, ...] = ()

    # ---------------------------------------------------------------- authoring

    @staticmethod
    def from_document(doc: dict[str, Any], agent_key: str) -> "Teamwork":
        """Read the policy out of a loaded PACT document.

        Absent `teamwork:` is not an error — it is the default policy. An author
        with two helpers and no opinion should not have to have one.
        """
        agent = ((doc.get("agents") or {}).get(agent_key) or {})
        members = sorted((agent.get("team") or {}).keys())
        block = agent.get("teamwork") or {}
        # Named once, here, rather than threaded through every message below.
        # A reader who is told the agent has been told the folder, since the
        # teamwork of `refund-desk` is only ever under `agents/refund-desk/`.
        try:
            tw = Teamwork(
                waits_for=_word(block.get("waits-for"), Waits, "waits-for", Waits.EVERYONE),
                enough_is=_whole(block.get("enough-is"), "enough-is"),
                gives_up_after=_seconds(block.get("gives-up-after"), "gives-up-after"),
                starts=_word(block.get("starts"), Starts, "starts", Starts.ALL_AT_ONCE),
                divides_the_budget=_word(
                    block.get("divides-the-budget"), Divides, "divides-the-budget",
                    Divides.EVENLY,
                ),
                shares={k: _percent(v, k) for k, v in (block.get("shares") or {}).items()},
                if_someone_fails=_word(
                    block.get("if-someone-fails"), OnFailure, "if-someone-fails",
                    OnFailure.CARRY_ON,
                ),
                may_start=tuple(
                    dict.fromkeys(
                        _word(w, MayStart, "may-start", None)
                        for w in _listed(block.get("may-start"))
                        if str(w).strip()
                    )
                ),
            )
            tw.check(members)
        except BadTeamwork as problem:
            raise BadTeamwork(f"{agent_key}: {problem}") from None
        return tw

    def check(self, members: Sequence[str]) -> None:
        """Refuse a policy that can never do what it says.

        Every message names the field, what is wrong, and a line to type. A
        policy that fails silently at 3am is worse than one that fails at
        `pact check`.
        """
        if self.waits_for is Waits.ENOUGH:
            if self.enough_is < 1:
                raise BadTeamwork(
                    "teamwork says `waits-for: enough-of-them` but never says how "
                    "many count as enough. fix: add a line `enough-is: 2`."
                )
            if members and self.enough_is > len(members):
                raise BadTeamwork(
                    f"teamwork says `enough-is: {self.enough_is}` but the team has "
                    f"{len(members)} member(s): {', '.join(members)}. That can never "
                    f"be met. fix: change it to `enough-is: {len(members)}` or fewer, "
                    f"or add another name under `team:`."
                )
        if self.waits_for is Waits.IN_TIME and not self.gives_up_after:
            raise BadTeamwork(
                "teamwork says `waits-for: whoever-answers-in-time` but never says "
                "how long to wait. fix: add a line `gives-up-after: 5s`."
            )
        if self.divides_the_budget is Divides.BY_SHARE:
            # Both of these now fire first from `pact check`, in
            # `crates/pact-loader/src/teamwork.rs` — where the person who typed
            # the line is, in the only tool D13's author runs, with the file, the
            # line and the percentage to type. They stay here because a document
            # can reach the harness without passing through the checker at all:
            # `Teamwork.from_document` is called with whatever `ir.py` loaded,
            # and a test or a runtime that builds a document in memory has had no
            # check run over it. A rule enforced in one of the two places is a
            # rule with a way round it.
            missing = [m for m in members if m not in self.shares]
            if missing:
                raise BadTeamwork(
                    f"teamwork says `divides-the-budget: by-share` but no share is "
                    f"set for {', '.join(missing)}. fix: add a line "
                    f"`{missing[0]}: 50%` under `shares:`."
                )
            total = sum(self.shares.values())
            # Over only. Under 100% is a reserve held back from the team —
            # `Pool.share_of` multiplies, so 90% of the pot is nine tenths of the
            # budget spent and a tenth never spent — and the schema's help for
            # `shares` promises exactly that ("adding up to 100% or less"). The
            # check-time twin says so out loud in its fix, because an author told
            # "100% or less" who lands on 90% has no other way to know they have
            # not made a second mistake nobody mentioned.
            if total > 1.0 + _EPS:
                raise BadTeamwork(
                    f"the shares under teamwork add up to {total * 100:.0f}%, which is "
                    f"more than there is. fix: change them so they add up to 100% or "
                    f"less."
                )
        if self.gives_up_after is not None and self.gives_up_after <= 0:
            raise BadTeamwork(
                "teamwork says `gives-up-after` is zero or negative, so nobody could "
                "ever answer in time. fix: write it like `gives-up-after: 5s`."
            )

    # ---------------------------------------------------------------- semantics

    def met_by(self, answers: Mapping[str, Answer], asked: Sequence[str]) -> bool:
        """Has the join been satisfied by what has come back so far?"""
        good = sum(1 for m in asked if answers[m].state == ANSWERED)
        settled = sum(1 for m in asked if answers[m].state in (ANSWERED, FAILED))
        if self.waits_for is Waits.ANYONE:
            return settled >= 1
        if self.waits_for is Waits.ENOUGH:
            return good >= self.enough_is
        if self.waits_for is Waits.FIRST_GOOD:
            return good >= 1
        # EVERYONE and IN_TIME both want the lot; for IN_TIME the clock is the
        # other way out, handled by the driver.
        return settled >= len(asked)

    def handoff(
        self,
        answers: Mapping[str, Answer],
        asked: Sequence[str],
        *,
        stopped_by: str = "",
        ran_out_of_time: bool = False,
        spent: Callable[[str], float] | None = None,
    ) -> "Handoff":
        """The outcome of a join that has run its course: the one verdict every driver
        of a join reaches (`ask_team` here; a runtime's own join, such as a workflow's
        `each` or `together`, from what came back to it).

        `answers` holds what came back by member (`NOT_ASKED` for a member with no
        answer yet); `stopped_by` names the member whose failure stopped the others
        (`if-someone-fails: stop-the-others`); `ran_out_of_time` says the clock
        (`gives-up-after:`) ended the wait; `spent` is what a member spent, for the
        members that never answered. A member still without an answer was
        overtaken by the clock (`out-of-time`), cut short once the join was met or
        stopped (`not-waited-for`), or, taking turns, never reached (`not-asked`):
        three different facts about a run, and Eve's barrier can state none of them.
        """
        spent = spent or (lambda member: 0.0)
        got = dict(answers)
        for m in asked:
            if got[m].state != NOT_ASKED:
                continue
            if ran_out_of_time:
                got[m] = Answer(m, state=OUT_OF_TIME, spent=spent(m))
            elif self.starts is Starts.ALL_AT_ONCE:
                got[m] = Answer(m, state=CANCELLED, spent=spent(m))
        satisfied = self.met_by(got, asked)
        why = needs_a_person = ""
        # Whoever failed, after the join has run its course. `ask-a-person` does not
        # cut the siblings short the way `stop-the-others` does: the person is about
        # to be asked whether to carry on without one member, and that is a better
        # question when the other answers are already in hand.
        failed = [m for m in asked if got[m].state == FAILED]
        if stopped_by:
            satisfied = False
            why = f"{stopped_by} could not answer, and teamwork says stop-the-others"
        elif failed and self.if_someone_fails is OnFailure.ASK_A_PERSON:
            satisfied = False
            needs_a_person = failed[0]
            why = f"{needs_a_person} could not answer, and teamwork says ask-a-person"
        elif self.waits_for is Waits.IN_TIME:
            # A deadline join is satisfied by whatever arrived, but "nothing
            # arrived" is a failure and must not read like a success.
            satisfied = any(got[m].state == ANSWERED for m in asked)
            if not satisfied:
                why = "nobody answered in time"
        elif not satisfied:
            why = f"{self.waits_for.value} was not met"
        return Handoff(self.waits_for, tuple(got[m] for m in asked), satisfied, why, needs_a_person)

    def unreachable_for(self, asked: Sequence[str]) -> str:
        """Why this join can never be met for *this* batch, or ''.

        Distinct from `check`: `check` is about the authored policy against the
        whole team, this is about the subset the model actually asked. A model
        that asks one specialist under `enough-is: 2` has made a mistake the
        author did not.
        """
        if self.waits_for is Waits.ENOUGH and self.enough_is > len(asked):
            return (
                f"only {len(asked)} of the team was asked, and `enough-of-them` "
                f"needs {self.enough_is}"
            )
        return ""


# ---------------------------------------------------------------- the join itself


async def ask_team(
    members: Sequence[str],
    ask: Asker,
    teamwork: Teamwork | None = None,
    budget: float = 0.0,
    bus: Bus | None = None,
    known: Mapping[str, str] | None = None,
    requests: Mapping[str, str] | None = None,
    pool: "Pool | None" = None,
    failures: tuple[type[BaseException], ...] = (Exception,),
) -> Handoff:
    """Ask `members` for help and wait for them according to `teamwork`.

    `failures` are the exceptions from `ask` that are a MEMBER's failure, which
    is data here (`FAILED`, and `if-someone-fails:` decides). Anything else is
    the run's own — a runtime parking the whole run for a person, a process
    being stopped, a journal that cannot be read — and is re-raised once the
    members still working are stopped, because recording it as one member's
    answer would write a fact about the run into the team's outcome. The
    default keeps every exception a failure, as before.

    `known` carries members whose answers already arrived before a park, so a
    resumed run does not ask them twice — the same exactly-once rule the tool
    path already keeps across an approval boundary.

    `pool` is the parent's budget for the WHOLE request, and it is what makes
    `cost-per-request-under` a ceiling rather than a per-step allowance. Built
    here from `budget` when nobody supplies one — which is right for a caller
    joining a team once — but the harness builds it once per run and hands the
    same one to every step, because a pot rebuilt at full size on each
    delegating step means N steps grant N times the author's written ceiling.
    """
    tw = teamwork or Teamwork()
    bus = bus or Bus()
    known = dict(known or {})
    requests = dict(requests or {})

    asked = tuple(dict.fromkeys(members))
    if not asked:
        return Handoff(tw.waits_for, (), satisfied=True)

    pool = pool if pool is not None else Pool(budget, tw.divides_the_budget, asked, tw.shares)
    answers: dict[str, Answer] = {
        m: (
            Answer(m, text=known[m], ok=True, state=ANSWERED)
            if m in known
            else Answer(m)
        )
        for m in asked
    }

    bus.emit(
        "step.delegate.requested",
        members=list(asked),
        waits_for=tw.waits_for.value,
        starts=tw.starts.value,
        divides=tw.divides_the_budget.value,
    )

    unreachable = tw.unreachable_for(asked)
    if unreachable:
        bus.emit("turn.delegate.failed", reason=unreachable)
        return Handoff(tw.waits_for, tuple(answers[m] for m in asked), False, unreachable)

    todo = [m for m in asked if m not in known]

    async def one(member: str, so_far: tuple[Answer, ...]) -> Answer:
        grant = Grant(member, pool, requests.get(member, ""), so_far)
        bus.emit("step.delegate.started", member=member, allowance=grant.allowance)
        try:
            text = await ask(grant)
        except asyncio.CancelledError:
            raise
        except failures as e:  # a child's failure is data, not a crash
            bus.emit("step.delegate.failed", member=member, reason=str(e))
            return Answer(member, ok=False, error=str(e), state=FAILED, spent=grant.spent)
        bus.emit("step.delegate.completed", member=member, spent=grant.spent)
        return Answer(member, text=text, ok=True, state=ANSWERED, spent=grant.spent)

    stopped_by = ""
    ran_out_of_time = False

    if tw.starts is Starts.ONE_AFTER_ANOTHER:
        stopped_by, ran_out_of_time = await _in_turn(todo, one, tw, answers, asked)
    else:
        stopped_by, ran_out_of_time = await _all_at_once(todo, one, tw, answers, asked, bus)

    handoff = tw.handoff(
        answers, asked, stopped_by=stopped_by, ran_out_of_time=ran_out_of_time, spent=pool.spent_by
    )
    bus.emit(
        "turn.delegate.completed" if handoff.satisfied else "turn.delegate.failed",
        waits_for=tw.waits_for.value,
        answered=[a.member for a in handoff.answers if a.state == ANSWERED],
        reason=handoff.why,
    )
    return handoff


async def _in_turn(
    todo: Sequence[str],
    one: Callable[[str, tuple[Answer, ...]], Awaitable[Answer]],
    tw: Teamwork,
    answers: dict[str, Answer],
    asked: Sequence[str],
) -> tuple[str, bool]:
    """Eve's start order, kept because it is sometimes the right one.

    Turns cost latency and buy one thing: a later member reads what an earlier
    one said (`Grant.so_far`). Eve pays that cost unconditionally and does not
    hand over the earlier answers, so it gets the bill without the benefit.
    """
    loop = asyncio.get_running_loop()
    ends_at = loop.time() + tw.gives_up_after if tw.gives_up_after else None

    for member in todo:
        left = None if ends_at is None else ends_at - loop.time()
        if left is not None and left <= 0:
            return "", True
        so_far = tuple(answers[m] for m in asked if answers[m].state == ANSWERED)
        try:
            answers[member] = (
                await asyncio.wait_for(one(member, so_far), left)
                if left is not None
                else await one(member, so_far)
            )
        except asyncio.TimeoutError:
            answers[member] = Answer(member, state=OUT_OF_TIME)
            return "", True
        if not answers[member].ok and tw.if_someone_fails is OnFailure.STOP_THE_OTHERS:
            return member, False
        if tw.met_by(answers, asked):
            return "", False
    return "", False


async def _all_at_once(
    todo: Sequence[str],
    one: Callable[[str, tuple[Answer, ...]], Awaitable[Answer]],
    tw: Teamwork,
    answers: dict[str, Answer],
    asked: Sequence[str],
    bus: Bus,
) -> tuple[str, bool]:
    """Everyone starts now; the join decides when we stop waiting."""
    loop = asyncio.get_running_loop()
    ends_at = loop.time() + tw.gives_up_after if tw.gives_up_after else None

    tasks = {asyncio.ensure_future(one(m, ())): m for m in todo}
    pending = set(tasks)
    stopped_by = ""
    ran_out_of_time = False

    try:
        while pending:
            left = None if ends_at is None else max(0.0, ends_at - loop.time())
            done, pending = await asyncio.wait(
                pending, timeout=left, return_when=asyncio.FIRST_COMPLETED
            )
            if not done:
                ran_out_of_time = True
                break
            for task in done:
                answers[tasks[task]] = task.result()
            failed = [m for m in todo if answers[m].state == FAILED]
            if failed and tw.if_someone_fails is OnFailure.STOP_THE_OTHERS:
                stopped_by = failed[0]
                break
            if tw.met_by(answers, asked):
                break
    finally:
        # Cancelling is what makes `the-first-good-answer` cheaper than
        # `everyone` rather than merely faster to report.
        #
        # WHO COUNTS is settled above and is exact: the deadline decides which
        # answers are in hand at the moment it passes, and a member whose answer
        # arrived before it is `answered` however long the reaping below takes.
        # WHEN THIS RETURNS is not exact, and the reason is worth stating where
        # someone reading a slow run will look. A member may be inside a call
        # that cannot be interrupted — `summarised-by:` is the one PACT ships,
        # and `transports/_summarise.py` says why it blocks — and Python cannot
        # kill a thread. Waiting here is the alternative to leaving a cancelled
        # child running loose against a budget the parent has already reported
        # on, which would be the worse trade: a late return is visible, a
        # background charge is not.
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        for task in pending:
            bus.emit("step.delegate.cancelled", member=tasks[task])

    return stopped_by, ran_out_of_time


# ------------------------------------------------------- what a member is held to


def granted(member: Any, allowance: float, currency: str = "") -> Any:
    """`member` (an `ir.AgentSpec`) with the share a join granted it as its own
    `cost-per-request-under:`, in both places that line is read.

    The smaller of the two binds: inheriting a budget downward must never RAISE
    one the member set for itself. An unmetered allowance (`inf`, the pot of a
    parent that wrote no money ceiling) changes nothing. This is the one place a
    `Grant` becomes a member's ceiling, so a runtime other than the harness holds
    a member to the same figure the harness does.

    `currency` is the pot's, for a member that wrote no money line of its own:
    the share is a share OF the parent's figure, so the sentence a member that
    reaches it prints names the currency the parent's author wrote, not a bare
    number (`Limits.cost_currency`).
    """
    if not allowance < math.inf:
        return member
    own = member.limits.cost_per_request_under
    figure = allowance if own is None else min(own, allowance)
    unit = member.limits.cost_currency or currency
    return replace(
        member,
        limits=replace(member.limits, cost_per_request_under=figure, cost_currency=unit),
        slo=replace(
            member.slo,
            cost_per_request_under=figure,
            cost_currency=member.slo.cost_currency or currency,
        ),
    )


def request_for(grant: Grant) -> str:
    """What a member is asked: its request, after what earlier members said.

    `one-after-another` earns its latency only if a later member can read what
    an earlier one said. Eve pays the latency and hands over nothing.
    """
    prior = "\n".join(f"{a.member} said: {a.text}" for a in grant.so_far if a.ok)
    return f"{prior}\n\n{grant.request}".strip() if prior else grant.request


def carried_on_without(member: str) -> str:
    """What stands in a failed member's place once a person said to carry on
    without it (`if-someone-fails: ask-a-person`, answered yes)."""
    return f"(no answer: a person said to carry on without {member})"


def asked_too_often(member: str, figure: int) -> str:
    """Why `member` may not be put to work again: its `asks-itself-at-most:`
    is spent. A member's failure, so `if-someone-fails:` decides what follows."""
    return (
        f"'{member}' has already been put to work {figure} time(s) on this request "
        f"— `asks-itself-at-most: {figure}` is spent."
    )


def refused_start(
    starter: str,
    *,
    started: int,
    starts_at_most: int | None,
    nests_left: int | None,
) -> str:
    """Why `starter` may not bring another agent in now, or ''.

    `started` is how many agents this request has brought in so far, counted
    across every level (`starts-at-most:`); `nests_left` is how many levels of
    starting are still allowed below `starter` (`nests-at-most:`, the smaller of
    its own and what its starter had left; `None` when nothing bounds it).
    """
    if nests_left is not None and nests_left < 1:
        return (
            f"'{starter}' may not bring anyone in: it was brought in itself, as deep "
            "as `nests-at-most:` allows."
        )
    if starts_at_most is not None and started >= starts_at_most:
        return (
            f"this request has already brought in {started} agent(s) — "
            f"`starts-at-most: {starts_at_most}` is spent."
        )
    return ""


def beyond_its_starter(starter: str, has: Sequence[str], asked: Sequence[str]) -> str:
    """Why a narrowed agent described with `asked` may not run, or ''.

    A narrowed agent runs with its starter's `uses:` or fewer and can never name
    anything its starter lacks (02P §8.1: permissions only narrow).
    """
    missing = [name for name in dict.fromkeys(asked) if name not in set(has)]
    if not missing:
        return ""
    return (
        f"a narrowed agent may use only what '{starter}' uses, and "
        f"{', '.join(repr(m) for m in missing)} is not among them. fix: describe it "
        f"with some of: {', '.join(has) or '(nothing)'}."
    )


# ------------------------------------------------------------------- reading in


def _listed(raw: Any) -> list[Any]:
    if raw is None:
        return []
    return list(raw) if isinstance(raw, (list, tuple)) else [raw]


def _word(raw: Any, kind: type[Enum], field_name: str, default: Any) -> Any:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return default
    text = str(raw).strip().lower()
    for member in kind:
        if member.value == text:
            return member
    raise BadTeamwork(
        f"`{field_name}: {raw}` is not one of the things teamwork understands. "
        f"fix: use one of: {', '.join(m.value for m in kind)}."
    )


def _whole(raw: Any, field_name: str) -> int:
    if raw is None:
        return 0
    try:
        return int(str(raw).strip())
    except ValueError:
        raise BadTeamwork(
            f"`{field_name}: {raw}` should be a whole number. fix: write it like "
            f"`{field_name}: 2`."
        ) from None


def _percent(raw: Any, member: str) -> float:
    """One share, held to the range a share HAS.

    `check()` only refused a total ABOVE 100%, so `{a: 150%, b: -50%}` summed to
    exactly 1.0 and loaded: measured, `Pool.allowance` then gave one real
    teammate 0.0 and the other 1.5 of a 1.00 USD pot, so the parent's
    `cost-per-request-under` was exceedable by half again. `pact check` refuses
    it, and this module's own `BadTeamwork` docstring says it is the second line
    of defence for a document handed straight to the harness.
    """
    text = str(raw).strip()
    try:
        value = float(text[:-1]) / 100.0 if text.endswith("%") else float(text)
    except ValueError:
        raise BadTeamwork(
            f"the share for {member} is `{raw}`, which is not a percentage. fix: "
            f"write it like `{member}: 40%`."
        ) from None
    if not 0.0 <= value <= 1.0:
        raise BadTeamwork(
            f"the share for {member} is `{raw}`, which is not between none of it "
            f"and all of it. fix: write it like `{member}: 40%`."
        )
    return value


def _seconds(raw: Any, field_name: str) -> float | None:
    """A length of time, or a diagnostic naming the field it came from.

    The reading itself is `limits.seconds`, shared with every other duration in
    the system. The near-copy this replaces stopped at the first suffix it
    recognised, so `waits-for: 1m30s` became one second — a wait ninety times
    shorter than the one written, and nothing said so.
    """
    if raw is None:
        return None
    value = seconds(raw)
    if value is None:
        raise BadTeamwork(
            f"`{field_name}: {raw}` is not a length of time. fix: write it like "
            f"`{field_name}: 5s`."
        )
    return value
