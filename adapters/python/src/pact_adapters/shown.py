"""What a parked run puts in front of the person.

A suspension carries two halves. The **contract** — what has to come back, and
in what shape (`suspension.Expect`) — worked at every one of the five places a
run can park. The **words** did not. `Question.for_person` renders them, and
until this module existed exactly one caller in the harness ever called it, so
four parks handed a person an answer contract and an empty string:

    where                                       reason              in_words
    a tool call the policy stops                needs-approval      the words
    a `does: ask-someone` stage                 x-asked-a-person    "" unless it named a question
    a conversation nobody can shrink            context-too-long    ""
    a teammate that could not answer            needs-approval      ""
    a ceiling reached before an answer          out-of-budget       ""

That made `shows: [spent-so-far, steps-taken]` in `questions/keep-going.yaml`
and `shows: [how-much-over]` in `questions/too-long-to-send.yaml` lines an
author wrote that reached nobody. It is one level past the usual version of that
defect: those four parks resolved their audience, their deadline, their timeout
action and their answer shape correctly out of the author's document. Only the
rendering was missing, which is the hardest kind to notice, because everything
you can assert about the park is right.

**There is deliberately no renderer in here.** `Question.for_person` is the one
rendering there is (ASK-4, and Y18/AD-46 before it): the author's sentence
first, then every value as quoted, control-stripped, length-capped data in its
own labelled region, never folded into that sentence. A second renderer is how
one of the two comes to concatenate, and the last hop into the only human
control in the system is the wrong place to keep two of anything.

What this module owns is the other half of the call — **which values a park has
to offer** — because that is the only thing that actually differs between them.
A tool approval offers the arguments the model chose, and always did; that is
why it was the one that worked. The other four had nothing to offer because
nobody had written down what they have. So each one below is a small closed
vocabulary of names an author types in `shows:`, and adding a value to a park is
one entry in one of these functions rather than a second way to render.

Two rules hold across all of them:

* **A figure nothing could count says so.** A run whose transport never reported
  usage has `money == 0.0` on its meter, and printing `0.00 USD` to somebody
  about to decide whether to keep spending reads as "this has cost nothing".
  `Limits.unmeterable` draws exactly this line for ceilings and for the same
  reason; here it arrives in front of a person who is about to act on it.
* **A park never shows nothing.** Where the author named no question the park
  still renders the built-in wording for its reason through the same
  `Question`, because a run stopped with nothing to show is, from the outside,
  indistinguishable from a run that has hung.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from .questions import Question

if TYPE_CHECKING:  # pragma: no cover - import cycle avoided at runtime
    from .context_policy import Tidied
    from .suspension import Expect


# ────────────────────────────────────────────────────────────── the one call


def words_for(
    question: "Question | None",
    about: str,
    values: Mapping[str, Any] | None = None,
    *,
    otherwise: str = "",
    contract: "Sequence[Expect]" = (),
    waits_for: str = "",
    asked_of: "Sequence[str] | None" = None,
) -> str:
    """What the person reads at one park.

    `question` is the author's, bound to whatever this park is about; `values`
    are the ones it may show, from the functions below. `otherwise` is the
    built-in wording for this reason, used when the author named no question —
    a park with no question is still a park somebody has to read.

    `contract` is what the wait actually asks for (`Suspension.asks`), and it
    governs the answer line **whether or not the author wrote a question**. That
    is the whole reason it is passed rather than derived here: a wait keyed on
    `payments` and `payments.because` that printed *"answer with: approved (yes
    or no), because (some text)"* is a screen whose instructions the wait itself
    refuses — measured on the worked example, where `w.answer(approved="yes",
    because="ok")` came back *"this wait did not ask for 'approved'"*. Two
    derivations of one contract is how the two come to disagree; there is one,
    and this substitutes it.

    `waits_for` and `asked_of` are the WAIT's deadline and audience, and they
    override the question's own for the same reason. A question is shown at a
    park whose rule may have come from a different line — `how-much-to-refund`
    is put at a wait `is-this-ok` governs, and a `waiting-for-another-agent`
    park has no rule at all — so printing the question's `answer-within: 4h`
    above a wait that expires in thirty minutes tells the person something the
    run will not honour. `None` means "the question's own", which is right where
    the two are the same line.
    """
    shown = _under_the_contract(question, contract, waits_for, asked_of)
    if shown is not None:
        return shown.about_call(about, dict(values or {})).for_person()
    if not otherwise:
        return ""
    if not contract:
        # Nothing is being asked for, so there is no answer line to render and
        # `for_person` would print an empty one. The wording is the built-in
        # sentence — authored here, never model or customer text — so returning
        # it whole cannot forge a labelled region.
        return otherwise
    built = Question(
        name=about,
        asks=otherwise,
        answer={e.name: e.shape for e in contract},
        asked_of=tuple(asked_of or ()),
        answer_within=waits_for,
    )
    return built.about_call(about, dict(values or {})).for_person()


def _under_the_contract(
    question: "Question | None",
    contract: "Sequence[Expect]",
    waits_for: str,
    asked_of: "Sequence[str] | None",
) -> "Question | None":
    """The author's question, saying what the wait will actually accept.

    Three substitutions, each of them a line the person would otherwise be told
    that the run does not honour: the answer names, the deadline and the
    audience. Nothing else is touched — the wording, the `because:` and the
    values shown are the author's and stay theirs.
    """
    if question is None:
        return None
    changes: dict[str, Any] = {}
    if contract:
        changes["answer"] = {e.name: e.shape for e in contract}
    if asked_of is not None:
        changes["asked_of"] = tuple(asked_of)
    if waits_for or asked_of is not None:
        changes["answer_within"] = waits_for
    return replace(question, **changes) if changes else question


# ──────────────────────────────────────────────── what each park has to offer


def spent(
    used: Mapping[str, float], *, counted: bool, which_limit: str = ""
) -> dict[str, str]:
    """The figures a run offers when a ceiling stopped it — `out-of-budget`.

    `counted` is whether the transport said what its calls cost. Steps, tool
    calls and the clock are the harness's own count and are always real; tokens
    and money are only knowable if the transport reports them, which is the same
    line `Limits.unmeterable` draws. A run that could not count them says so
    rather than showing a zero.

    `which_limit` is the ceiling that was reached, in the words the run report
    uses for it, so the person deciding whether to keep going and the person
    reading the run afterwards are not shown two accounts of one stop.
    """
    nobody_counted = "nothing here could count it"
    figures = {
        "steps-taken": _whole(used.get("steps")),
        "tool-calls-made": _whole(used.get("tool_calls")),
        "time-spent": _how_long(used.get("seconds")),
        "tokens-used": _whole(used.get("tokens")) if counted else nobody_counted,
        "spent-so-far": (
            f"{float(used.get('money') or 0.0):.2f} USD" if counted else nobody_counted
        ),
    }
    if which_limit:
        figures["which-limit"] = which_limit
    return figures


def tidying(tidied: "Tidied") -> dict[str, str]:
    """The figures a conversation offers when nobody can shrink it —
    `context-too-long`.

    `how-much-over` is the sentence the tidier already wrote when its ladder
    bottomed out — *"still 1102 over after shorten-long-results,
    summarise-older, drop-parts, keep-recent-only — nothing left to tidy that
    `always-keep` allows"*. It is read off the record rather than recomputed:
    the threshold is `when-full` × what the bound model holds, the record does
    not carry that, and a second calculation here would be a second answer to
    one question with nothing keeping the two equal.
    """
    return {
        "how-much-over": tidied.how_much_over,
        "what-was-tried": ", ".join(tidied.fired) or "nothing — there was nothing to try",
        "how-long-it-is": (
            f"{tidied.after} against about {tidied.budget} this model can hold"
        ),
    }


def teammate(who: str, said: str, answered: Sequence[str] = ()) -> dict[str, str]:
    """The figures a failed delegate offers — `needs-approval`, from `teamwork`.

    `why-they-could-not` is the teammate's own words, and a teammate may be a
    remote agent reading customer text. That is the Y18 case exactly, and it is
    safe here for the reason Y18 was closed rather than by anybody remembering:
    every value on this dict reaches the person through `for_person`, quoted,
    with control characters stripped, in its own labelled region.
    """
    return {
        "who-could-not-answer": who,
        "why-they-could-not": said,
        "who-did-answer": ", ".join(answered) or "nobody else",
    }


def a_stage(name: str, says: str) -> dict[str, str]:
    """The figures a `does: ask-someone` stage offers — `x-asked-a-person`.

    A stage has no pending action to pull values from, which is why this park
    rendered an author's question with no values under it even when it named
    one. What it has instead is its own `says:` line, and a person reading
    "answer within 10m" is better served knowing which stage of the agent's
    thinking is waiting on them.
    """
    return {"the-stage": name, "what-the-stage-said": says}


# ────────────────────────────────────────────────────────────────── numbers


def _whole(v: Any) -> str:
    """A count, without the `.0` a meter carries it as."""
    try:
        return str(int(float(v or 0.0)))
    except (TypeError, ValueError):
        return "0"


def _how_long(v: Any) -> str:
    """A measured duration, short enough to read at a glance.

    "1 seconds" is the kind of thing that tells a reader nobody looked at this
    screen, and this screen is the one place a person is asked to act.
    """
    try:
        f = float(v or 0.0)
    except (TypeError, ValueError):
        f = 0.0
    figure = str(int(f)) if f.is_integer() else f"{f:.4g}"
    return f"{figure} second" if figure == "1" else f"{figure} seconds"
