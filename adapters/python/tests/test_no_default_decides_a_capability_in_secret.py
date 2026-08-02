"""AC-7.2 — a core audit finds no capability-affecting literal.

The criterion has two halves and this file is the second, which is the one that
can be held. The first — *"all defaults resolve from profiles"* — needs a profile
mechanism, and `workspace.profile` has zero readers anywhere; `pact check` now
says so (`loader/profile-selects-nothing`) rather than letting an author believe
`profile: production` changes something.

The half that can be held is this: **every constant that decides what an agent may
do is either author-settable or written down here with the reason it is not.**
Not "there are no constants" — a system with no defaults is unusable by the
non-programmer D14 is about. The property is that no default decides a capability
*in secret*.

Three ways a default earns its place, and every entry says which:

* `AUTHOR_SETS_IT` — a document field overrides it, so the constant is only what
  happens when nobody wrote one;
* `NOT_ABOUT_CAPABILITY` — it decides how something is reported or measured, and
  no agent can do more or less because of it;
* `DELIBERATE_AND_CLOSED` — it is a capability decision made once, on purpose,
  and an author overriding it would be able to weaken something the format exists
  to hold.

A constant in none of the three fails, and the message says which question to
answer. That is the whole mechanism: adding one forces the decision to be written
down, exactly as `DERIVED_FROM_THE_DOCUMENT` does for `run()`'s parameters.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "adapters/python/src/pact_adapters"

#: The constant, and the authored field that overrides it. A reader who wants
#: different behaviour changes their document, not this file.
AUTHOR_SETS_IT: dict[str, str] = {
    "ir.DEFAULT_STEPS": "`limits.steps-at-most:`",
    "slo.FEELS": "`limits.feel:`, and any of the four latency figures written directly",
    "learning.SHRINK_LIMIT": "`learning.max-drift:`, through `Permissions`",
    "context_policy.SUMMARY_RESERVE": "`context-policy:`'s own `keep-under:`",
    "interceptors.HIDING_RUNS_AT": "`runs-at:` on the rule",
    "interceptors.REDACTION_RUNS_AT": "`runs-at:` on the rule",
    "interceptors.EVERYTHING_ELSE_RUNS_AT": "`runs-at:` on the rule",
}

#: Decides reporting or measurement. No agent can do more or less because of it.
NOT_ABOUT_CAPABILITY: dict[str, str] = {
    "conformance.EPSILON": "the tolerance a conformance comparison allows — a "
                           "fact about the report, and it is zero",
    "questions.SHOW_LIMIT": "how much of a value is shown to the person being "
                            "asked. A display bound; the value itself is unchanged",
    "judge.REASON_LIMIT": "how long a grader's stated reason may be",
    "judge.GRADE_TOKENS": "how many tokens one grading call may use",
    "judge.GRADE_TIMEOUT_S": "how long to wait for a grader before giving up",
    "interceptors.NEEDLE": "how much context a redaction diagnostic quotes",
    "resolve.BUILTIN_CATALOGUE": "the path to the shipped price list, not a value",
    "scoring.REPO": "where this checkout is, computed from `__file__`",
    "loops.LIBRARY": "the shipped loop shapes; the numbers in it are each shape's "
                     "own `at-most:`, which an author forks by copying the file",
}

#: Made once, on purpose, and an author overriding it would weaken something.
DELIBERATE_AND_CLOSED: dict[str, str] = {
    "evals.CONSEQUENTIAL_BAR": "money-moving cases are graded at 100%. It is a "
                               "correctness invariant and not a rate (AD-58a) — "
                               "an author who could lower it could accept a suite "
                               "that sometimes refunds the wrong person",
    "context_policy.CHARS_PER_TOKEN": "the estimate used when no transport will "
                                      "count. Author-settable, it would let a "
                                      "workspace claim its conversation fits when "
                                      "it does not",
    "providers.DEFAULT_THRESHOLD": "what a metric counts as a pass when the "
                                   "author's own `metrics:` line sets none",
    "interceptors.NEEDED_BY": "which power each rule form requires. An author "
                              "editing this could give a rule a power its own "
                              "words did not ask for",
    "interceptors.CONTINUES": "which forms let a run carry on rather than stop",
    "optimising.MARGIN": "what counts as an improvement — five points of the "
                         "held-out score. An author who could lower it could claim "
                         "an optimiser works on a difference indistinguishable "
                         "from which way the sampling went",
    "optimising.FROM_AT_MOST": "how many failing cases one proposal is written "
                               "from. Raising it asks the model to fix everything "
                               "at once, which produces a rewrite — and a rewrite "
                               "is what `SHRINK_LIMIT` and the drift limit exist "
                               "to catch",
    "exploding.RESERVED": "the Windows device names a key may not be. Writing to "
                          "`CON.yaml` succeeds and stores nothing, which is the "
                          "worst failure a format whose tree IS the specification "
                          "can have — an author who could shorten this list could "
                          "write a document that vanishes on somebody else's machine",
    "exploding.LONGEST": "how many BYTES a key may be before it cannot become a "
                         "file name. An author who could raise it could write a "
                         "key that does not survive a filesystem the tree has to "
                         "cross, which is what the portable alphabet exists for",
}


def _capability_literals() -> dict[str, ast.AST]:
    """Every module-level constant carrying a NUMBER, by `module.NAME`.

    **Numbers, and that is the definition.** The first version audited every
    upper-case module global and found 141 — most of them vocabulary tables
    naming the format's own words (`ANSWERED`, `FAILED`, `ROLES`, `LABELS`).
    Those decide what something is CALLED. A number decides *how much*, and how
    much is a capability: how many steps, how much of a policy may be rewritten,
    how long a grader waits, what counts as a pass.

    An audit of 141 rows is a bookkeeping exercise nobody reads; an audit of 21
    is one somebody checks. Private names are excluded — a `_`-prefixed constant
    is implementation detail of the module that owns it, and cannot be reached
    from a document.
    """
    found: dict[str, ast.AST] = {}
    for path in sorted(SRC.rglob("*.py")):
        mod = path.stem
        if mod.startswith("_"):
            continue
        tree = ast.parse(path.read_text(errors="ignore"))
        for node in tree.body:
            targets = (
                node.targets if isinstance(node, ast.Assign)
                else [node.target] if isinstance(node, ast.AnnAssign)
                else []
            )
            carries_a_number = any(
                isinstance(n, ast.Constant)
                and isinstance(n.value, (int, float))
                and not isinstance(n.value, bool)
                for n in ast.walk(node)
            )
            for target in targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id.isupper()
                    and not target.id.startswith("_")
                    and carries_a_number
                ):
                    found[f"{mod}.{target.id}"] = node
    return found


def test_the_audit_sees_something() -> None:
    """A walk that found nothing would pass this file vacuously."""
    got = _capability_literals()
    assert len(got) > 15, f"only {sorted(got)} found — the walk is broken"
    assert "ir.DEFAULT_STEPS" in got


def test_every_default_says_which_kind_of_default_it_is() -> None:
    """The check that makes adding one a decision.

    A constant in none of the three lists fails, and the failure asks the
    question rather than telling somebody to add a name to a list — the answer
    decides which list, and getting it wrong is worse than the gap.
    """
    accounted = (
        set(AUTHOR_SETS_IT) | set(NOT_ABOUT_CAPABILITY) | set(DELIBERATE_AND_CLOSED)
    )
    unaccounted = sorted(set(_capability_literals()) - accounted)
    assert not unaccounted, (
        f"{len(unaccounted)} module-level default(s) with nothing said about "
        f"them:\n  " + "\n  ".join(unaccounted) + "\n\n"
        f"For each: can an author override it? Then AUTHOR_SETS_IT, naming the "
        f"field. Does it decide only how something is reported? Then "
        f"NOT_ABOUT_CAPABILITY. Is it a capability decision made once on "
        f"purpose? Then DELIBERATE_AND_CLOSED, saying what an author overriding "
        f"it could weaken. A default in none of the three is one deciding what "
        f"an agent may do in secret, which is what AC-7.2 is about."
    )


def test_nothing_is_accounted_for_that_is_not_a_default() -> None:
    """The other direction. A row for a constant that no longer exists describes
    a decision nobody is making any more — and this repository's characteristic
    failure is a register confidently wrong about its own subject."""
    got = set(_capability_literals())
    for name, register in (
        ("AUTHOR_SETS_IT", AUTHOR_SETS_IT),
        ("NOT_ABOUT_CAPABILITY", NOT_ABOUT_CAPABILITY),
        ("DELIBERATE_AND_CLOSED", DELIBERATE_AND_CLOSED),
    ):
        ghosts = sorted(set(register) - got)
        assert not ghosts, f"{name} names {ghosts}, which no module defines"


def test_no_default_is_filed_two_ways() -> None:
    """`DEFAULT_STEPS` cannot both be author-settable and a closed decision. If it
    is in two lists, whichever a reader consults first decides what they
    believe."""
    pairs = [
        ("AUTHOR_SETS_IT", AUTHOR_SETS_IT, "NOT_ABOUT_CAPABILITY", NOT_ABOUT_CAPABILITY),
        ("AUTHOR_SETS_IT", AUTHOR_SETS_IT, "DELIBERATE_AND_CLOSED", DELIBERATE_AND_CLOSED),
        ("NOT_ABOUT_CAPABILITY", NOT_ABOUT_CAPABILITY,
         "DELIBERATE_AND_CLOSED", DELIBERATE_AND_CLOSED),
    ]
    for a_name, a, b_name, b in pairs:
        both = sorted(set(a) & set(b))
        assert not both, f"{both} are in both {a_name} and {b_name}"


def test_every_author_settable_default_names_a_field() -> None:
    """"An author can override it" is only useful with the line to type. A row
    saying "the author can change it" and not saying where is a row that has not
    been checked."""
    for name, where in AUTHOR_SETS_IT.items():
        assert "`" in where, (
            f"{name} says an author can override it and does not name the field: "
            f"{where!r}"
        )
