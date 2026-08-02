"""Where a proposal comes from (AC-3.5).

> The optimizer improves at least one reference agent's small-model eval score by
> a declared margin over the un-optimised baseline, with a frozen held-out split
> and the split locked before optimisation begins.

`Learner.cycle` gates a proposal — held-out split, blast radius, drift, spend —
and has always taken one **handed in**. Nothing generated one, which is why the
register recorded *"no optimiser"*. This is the missing half, and it is
deliberately the smaller half: the gate is where the value is, and an optimiser
that could route around it would be worse than none.

**It never sees the held-out split.** That is the criterion's own emphasis and
the one property here worth more than the rest put together: an optimiser tuned
on the cases it is scored against reports an improvement that exists only in the
tuning. `improve_on` takes the TRAIN cases and refuses if handed a learner whose
split was never locked.

**It proposes; it does not apply.** What comes back is a `Proposal` for
`Learner.cycle` to accept or refuse, so every gate the learning loop already has
still stands in front of it. In the shipped example that means every proposal is
held for a person, because `enabled: propose-only` — and an optimiser whose
output is reviewed is the only kind D23 permits near decision logic.

**The margin is declared, and it is not met here.** `MARGIN` says what counts as
an improvement; whether a real agent clears it against a small model is a
measurement, and one this repository has not made — see the register.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

from .evals import Case, CaseOutcome, Verdict
from .learning import CAN_BE_APPLIED, Learner, Proposal

#: What counts as an improvement, declared rather than discovered.
#:
#: Five points of the held-out score. Below that and a difference is as likely to
#: be which way the sampling went as anything the edit did — an optimiser that
#: claimed a one-point win would be reporting noise with a straight face. The
#: number is here rather than in a caller's argument for the reason `EPSILON` is:
#: a margin a caller chooses is a margin that grows to fit the result.
MARGIN = 0.05

#: How many failing cases the proposal is written from. More than a handful and
#: the model is asked to fix everything at once, which produces a rewrite rather
#: than an edit — and a rewrite is what `SHRINK_LIMIT` and the drift measurement
#: exist to catch.
FROM_AT_MOST = 3


class CannotOptimise(Exception):
    """The split was not locked, or there is nothing to learn from."""


def what_went_wrong(verdict: Verdict, most: int = FROM_AT_MOST) -> list[CaseOutcome]:
    """The failing cases a proposal should address — at most a handful.

    A handful because a proposal written from every failure at once is a
    rewrite, and the gate refuses rewrites — `ESC-SHRINK` and the drift limit
    both bite. An edit that fixes the three clearest failures is one a person can
    review.
    """
    # By KEY, not by severity. `CaseOutcome` records `passed` and `why` and no
    # score — a case either met what the author expected or did not — so there is
    # no "worst" to sort by, and inventing an ordering would be ranking failures
    # on a number that does not exist. Stable by key instead, so two runs over
    # the same failures write from the same three.
    return sorted((c for c in verdict.results if not c.passed), key=lambda c: c.key)[:most]


def improve_on(
    learner: Learner,
    verdict: Verdict,
    ask: Callable[[str], str],
) -> "Proposal | None":
    """One proposal, written from what the TRAIN cases got wrong.

    `ask` is handed in rather than built here for the same reason `tools` and
    `judge` are on `Learner.from_document`: reaching a model is not something a
    pure read of a document should do, and passing it in is what lets this be
    tested without one.

    Returns `None` when there is nothing to propose — every case passed, or the
    failures carry no reason to write from. `None` is not a failure: an agent
    that is already right should produce no edit, and an optimiser that invented
    one would be changing a working agent to look busy.
    """
    if not learner.holdout:
        raise CannotOptimise(
            "this learner holds nothing out, so there is no frozen split to "
            "measure an improvement against and no way to tell a real one from "
            "tuning on the answers. Fix: mark some cases `split: held-out`."
        )

    held = {c.key for c in learner.holdout}
    failing = [c for c in what_went_wrong(verdict) if c.key not in held]
    if not failing:
        return None

    said = "\n".join(
        f"- asked: {_case_of(learner.train, c.key)}\n  went wrong: {c.why}"
        for c in failing
    )
    written = ask(
        "These are things this agent got wrong. Rewrite its instructions so it "
        "would get them right, changing as little as possible and keeping every "
        "rule it already has.\n\n"
        f"Its instructions now:\n{learner.spec.instructions}\n\n"
        f"What went wrong:\n{said}"
    ).strip()

    if not written or written == learner.spec.instructions.strip():
        return None
    return Proposal(
        field=CAN_BE_APPLIED[0],
        before=learner.spec.instructions,
        after=written,
        rationale=(
            "written from "
            + ", ".join(c.key for c in failing)
            + " — cases in the TRAIN split. The held-out split was locked before "
              "this ran and none of it was read."
        ),
    )


def _case_of(cases: Sequence[Case], key: str) -> str:
    """What the case asked, for the prompt. Empty rather than raising: a failure
    whose case has gone is still a failure worth writing from."""
    return next((c.when for c in cases if c.key == key), "")


def cleared_the_margin(before: float, after: float, margin: float = MARGIN) -> bool:
    """Did this edit improve the held-out score by the declared margin?

    Separate from `Learner.cycle`'s own `after > before` on purpose. The cycle
    asks *"is this better"*, which is the right question for applying an edit.
    AC-3.5 asks *"is this better BY A DECLARED MARGIN"*, which is the right
    question for claiming an optimiser works — and a claim built on the first
    would be a claim about noise.
    """
    return (after - before) >= margin


def measured(held_out: int, before: Verdict, after: Verdict) -> dict[str, Any]:
    """What one optimisation run can honestly say about itself.

    Takes the held-out COUNT rather than the `Learner` it used to, because the
    one place both verdicts exist is `scoring.render_proposal`, which has an
    `Outcome` and no learner. With the old signature that reader computed the
    same three facts itself and this function stayed unreachable — two functions
    answering one question, which is how they come to disagree. The count is the
    only thing the `Learner` was ever consulted for.
    """
    return {
        "margin-declared": MARGIN,
        "before": before.score,
        "after": after.score,
        "improved-by": round(after.score - before.score, 4),
        "cleared-the-margin": cleared_the_margin(before.score, after.score),
        "held-out-cases": held_out,
        "split-locked-before": True,
        # Said out loud, because a margin cleared over three cases is not a
        # result. `Verdict` already refuses a percentage over too few cases; this
        # is the same caution one level up.
        "enough-to-mean-something": held_out >= 5,
    }


USAGE = """\
pact-improve — write one proposal from what an agent got wrong

USAGE:
    pact-improve PATH [--serving-at URL]

Scores the agent, asks its own model to rewrite the instructions so the failing
TRAIN cases would pass, and prints the proposal as a diff. **Nothing is applied**:
what comes back goes to `pact-eval PATH --propose instructions=FILE`, which is
where every gate the learning loop has stands in front of it.

The held-out split is never read. An optimiser tuned on the cases it is scored
against reports an improvement that exists only in the tuning.
"""


def main(argv: "list[str] | None" = None) -> int:
    import sys
    from pathlib import Path

    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        sys.stdout.write(USAGE)
        return 0

    serving_at = ""
    if "--serving-at" in args:
        at = args.index("--serving-at")
        serving_at = args[at + 1] if at + 1 < len(args) else ""
        del args[at : at + 2]

    from .scoring import DEFAULT_SERVING_AT, _load_document, _which_agent, score

    root = Path(args[0]).resolve()
    document, trouble = _load_document(root)
    if trouble is not None:
        sys.stderr.write(str(trouble))
        return 3
    agent, trouble = _which_agent(document, "", root)
    if trouble is not None:
        sys.stderr.write(str(trouble))
        return 3

    scored = score(root, serving_at=serving_at or DEFAULT_SERVING_AT)
    if scored.problem is not None:
        sys.stderr.write(str(scored.problem))
        return 3
    if scored.verdict.outcome == "UNDECIDED":
        sys.stderr.write(
            f"error: the suite could not be scored, so there is nothing to "
            f"improve on.\n  {scored.verdict.note}\n"
        )
        return 3

    from .ir import AgentSpec
    from .judge import local_ask
    from .learning import Learner

    spec = AgentSpec.from_document(document, agent, source=root)
    learner = Learner.from_document(document, spec, {})
    try:
        proposal = improve_on(
            learner, scored.verdict,
            lambda prompt: local_ask(
                prompt, at=serving_at or DEFAULT_SERVING_AT, model=scored.model
            ),
        )
    except CannotOptimise as refused:
        sys.stderr.write(f"error: {refused}\n")
        return 1

    if proposal is None:
        sys.stdout.write(
            "Nothing to propose: every case in the train split passed, or the "
            "model returned what the agent already says.\n"
        )
        return 0
    sys.stdout.write(proposal.diff() + "\n\n")
    sys.stdout.write(f"{proposal.rationale}\n\n")
    sys.stdout.write(
        "Nothing has been applied. Put the new wording in a file and run:\n"
        f"  pact-eval {args[0]} --propose instructions=<that file>\n"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
