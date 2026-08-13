"""AC-7.2 — a core audit finds no capability-affecting literal.

The criterion has two halves and this file is the second, which is the one that
can be held. The first — *"all defaults resolve from profiles"* — needs a profile
mechanism, and `workspace.profile` has zero readers anywhere; `pact check` now
says so (`loader/profile-selects-nothing`) rather than letting an author believe
`profile: production` changes something.

**And that half should not be built** — `docs/remediation/C8-profiles.md`. The two
halves pull against each other, and this file is why: everything in
`DELIBERATE_AND_CLOSED` below is a default whose row says what an author
overriding it could weaken, and *"all defaults resolve from profiles"* asks for
the mechanism that lets them. The decision is to delete the field and amend the
criterion to what this file holds. Nothing about this file changes either way;
the lists below are the evidence for the decision, not a consequence of it.

**What this file does NOT cover, said here rather than left to be found.** `SRC`
below is `adapters/python/src/pact_adapters`, and that is the entire walk. AC-7.2
says *"a core audit"*, and this repository's word for the core is the Rust crates
(`docs/20-ARCHITECTURE-DRAFT.md:1766`). No Rust-side audit exists, so constants
like `crates/pact-doc/src/yaml.rs`'s `MAX_TEXT` (a 5 MB knowledge file is refused)
and `crates/pact-schema/src/coerce.rs`'s `SCORE_TOLERANCE` — the twin of a
constant filed below — are unfiled and nothing forces them to be filed. That is
**D-4** in the decision document's §7 and it is the gap between what this file
holds and what the criterion asks for.

The half that can be held here is this: **every constant in this package that
decides what an agent may do is either author-settable or written down here with
the reason it is not.**
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

**A fourth list and a second walk, added because a default hid from the first
one.** `_capability_literals` finds module-level upper-case names carrying a
NUMBER, and `harness.run`'s `getattr(transport, "prices_money", reports_usage)`
is none of the three: it is inside a function, it is lower case, and its value is
a boolean, which that walk excludes by name. It decided whether an author's spend
cap was reported as enforced — a transport with a `usage()` that could never be
priced was taken to price its calls, so a spend cap over a remote agent metered
0.00 for the life of the workspace (B6). That is precisely "a default deciding a
capability in secret", and the file claiming the property could not see it.
`OPTIONAL_ON_THE_TRANSPORT` and `_transport_fallbacks()` close it: every value the
harness invents on a transport's behalf is filed with what it grants, and a
fallback of `None` — this package's word for *"it did not say"*, which is
reported rather than assumed — needs no row.
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
    "resolve.SCORE_TOLERANCE": "how close a published score has to be before "
                               "`scores: {MMLU: \"= 80\"}` calls it equal. It is "
                               "not a display figure: it decides which models are "
                               "BOUND, and an author who could widen it could have "
                               "`= 80` met by a model publishing 79.99. It is also "
                               "not this port's to choose — `spec/comparisons.yaml` "
                               "states it and the Rust checker reads the same "
                               "figure, because two ports deciding one author's "
                               "line differently is the defect it was added to fix",
}

#: A fourth kind, and the reason it exists is a default this file could not see.
#:
#: `harness.run` asks the transport what it can do — `getattr(transport, "X",
#: <fallback>)` — and the FALLBACK is a decision about what happens when nobody
#: answered. `prices_money` was `getattr(transport, "prices_money",
#: reports_usage)`: a transport that had a `usage()` and had never said whether
#: anything could PRICE it was taken to price its calls, so a spend cap over a
#: remote agent was reported as enforced and metered 0.00 for the life of the
#: workspace (B6, row C5 of `docs/70-PRODUCTION-GAP-REGISTER.md`). That is a
#: capability decision made by a default, in secret, which is the one thing this
#: file exists to make impossible — and the walk below structurally could not
#: reach it, three times over: `_capability_literals` inspects `tree.body` only
#: (this is inside a function), requires `target.id.isupper()` (this is a local),
#: and excludes booleans outright.
#:
#: Nothing in `src/` constructs a transport, so the population these fallbacks
#: land on is every host-written transport there is. Filing them is the same
#: obligation `DELIBERATE_AND_CLOSED` carries, on the same grounds — and each row
#: says what the fallback GRANTS, because a fallback that grants nothing cannot
#: lie about a ceiling.
OPTIONAL_ON_THE_TRANSPORT: dict[str, str] = {
    "prices_money": "whether anything can put a PRICE on what a call carried. "
                    "`False`: a transport that never said it could price is not "
                    "taken to have, so the author's money ceilings arrive on "
                    "`RunResult.unmetered` — *'could not promise to measure'*, "
                    "which is exactly what is true when nobody promised. It was "
                    "`reports_usage`, and that is B6",
    "unenforced": "sentences the transport wants on the report. `tuple`, so a "
                  "transport that says nothing adds nothing. Grants no capability "
                  "in either direction",
    "model": "which model this transport actually bound, for the catalogue "
             "lookups (`_window`, `_never_reached`) and the `model-pin` report. "
             "`\"\"` means it will not say, and every reader treats that as "
             "'nothing here knows' rather than as a name",
    "name": "what to call this transport in a diagnostic. A display string",
}


def _capability_literals() -> dict[str, ast.AST]:
    """Every module-level constant carrying a NUMBER, by `module.NAME`.

    **Numbers, and that is the definition.** The first version audited every
    upper-case module global and found 141 — most of them vocabulary tables
    naming the format's own words (`ANSWERED`, `FAILED`, `AUDIO_SPELLINGS`,
    `LABELS`).
    Those decide what something is CALLED. A number decides *how much*, and how
    much is a capability: how many steps, how much of a policy may be rewritten,
    how long a grader waits, what counts as a pass.

    An audit of 141 rows is a bookkeeping exercise nobody reads; an audit of what
    this walk leaves is one somebody checks. **How many that is, is deliberately
    not written down anywhere** — not here and not in
    `docs/70-PRODUCTION-GAP-REGISTER.md`, which used to say 21 and was wrong by
    five a session later, because closing a defect anywhere in the package adds
    or removes a constant and no rule made the prose move with it. The count is
    `len(_capability_literals())` and has no second home. Private names are
    excluded — a `_`-prefixed constant is implementation detail of the module
    that owns it, and cannot be reached from a document.
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


def _transport_fallbacks() -> dict[str, list[str]]:
    """Every `getattr(transport, "X", <something other than None>)` in `SRC`.

    The companion walk, and it exists because `_capability_literals` cannot see
    this shape at all — it is not module level, not upper case, and the value
    that mattered was a boolean, which that walk excludes by name. The default
    it missed decided whether an author's spend cap was reported as enforced.

    `None` is excluded on purpose and it is the whole discrimination: a fallback
    of `None` is *"the transport did not say"*, and every reader of one in this
    package turns that into a sentence on `RunResult.unmetered` rather than into
    a permission. Anything ELSE is a value the harness invents on the transport's
    behalf, and inventing one is what has to be argued.

    Scoped to the parameter named `transport`, which is the seam `harness.run`
    and `Learner.cycle` probe. Said here rather than left to be found: a fallback
    read off a differently-named local is outside this walk.
    """
    found: dict[str, list[str]] = {}
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(errors="ignore"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id != "getattr" or len(node.args) != 3:
                continue
            who, what, fallback = node.args
            if not (isinstance(who, ast.Name) and who.id == "transport"):
                continue
            if not (isinstance(what, ast.Constant) and isinstance(what.value, str)):
                continue
            if isinstance(fallback, ast.Constant) and fallback.value is None:
                continue
            where = f"{path.relative_to(SRC)}:{node.lineno}"
            found.setdefault(what.value, []).append(where)
    return found


def test_the_companion_walk_sees_something() -> None:
    """The same vacuity guard the constant walk has, for the same reason: this
    check was added because a default hid from the other one, and a walk that
    matched nothing would hide it just as well."""
    got = _transport_fallbacks()
    assert "prices_money" in got, f"the walk is broken: {sorted(got)}"
    assert len(got) >= 3, sorted(got)


def test_every_capability_the_harness_invents_for_a_transport_is_filed() -> None:
    """A fallback the harness supplies on a transport's behalf is a decision.

    `getattr(transport, "prices_money", reports_usage)` answered the MONEY
    question with the TOKEN answer for a round, and told an author their spend
    cap was enforced against a meter that read 0.00 for the life of the
    workspace. It is a default deciding a capability in secret — the property
    this file is named for — and it was invisible to the walk above.
    """
    filed = set(OPTIONAL_ON_THE_TRANSPORT)
    got = _transport_fallbacks()
    unaccounted = sorted(set(got) - filed)
    assert not unaccounted, (
        "the harness invents a value on a transport's behalf for "
        + ", ".join(f"{k} ({', '.join(got[k])})" for k in unaccounted)
        + " and nothing says what that grants. Add a row to "
        "`OPTIONAL_ON_THE_TRANSPORT` naming the fallback and what a transport "
        "that never declared it is therefore taken to be able to do — or make "
        "the fallback `None`, which is this package's word for \"it did not "
        "say\" and is reported rather than assumed."
    )
    ghosts = sorted(filed - set(got))
    assert not ghosts, (
        f"OPTIONAL_ON_THE_TRANSPORT names {ghosts}, which nothing in `SRC` reads "
        "off a transport any more — a register confidently wrong about its own "
        "subject is this repository's characteristic failure"
    )


def test_every_author_settable_default_names_a_field() -> None:
    """"An author can override it" is only useful with the line to type. A row
    saying "the author can change it" and not saying where is a row that has not
    been checked."""
    for name, where in AUTHOR_SETS_IT.items():
        assert "`" in where, (
            f"{name} says an author can override it and does not name the field: "
            f"{where!r}"
        )
