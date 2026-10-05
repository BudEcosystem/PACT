"""The eval runner — config only, no author code (G4, D19, AC-4.2).

Cases come straight out of the PACT document, so the same YAML a support lead
wrote is what runs. Four of the five assertions here are *deterministic*: string
containment, forbidden phrases, tool usage. Decision AC-4.5 requires
deterministic checkers to run before any judge, and a suite that can be decided
without a model must never invoke one — which is also what lets the whole thing
run air-gapped (D17). `check` holds that order structurally: every deterministic
rule is decided first, and the judge is reached only by a case that survived all
of them.

The fifth shape needs a reader, and `judge.py` is it. For a round it needed one
and had none: `Rule.read` returned the `judged:` shape carrying *"judging needs a
model, and this runtime has no judge wired up"*, `_read_rules` put that on
`unenforced`, and the rule never reached `rules` at all. The sentence was
correct and the consequence was that the author's own line decided nothing.

The verdict deliberately distinguishes three outcomes, not two. `UNDECIDED` is
what a suite too small to support its own pass bar must return; collapsing it
into `FAIL` would let a 3-case suite make a 90% claim, which is the statistical
hole the architecture review found in the flagship example. A rule nobody could
grade takes the same three-way care one level down — see `CaseOutcome.unenforced`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from .diagnostics import locate
from .interceptors import said_any
from .harness import RunResult
# The provider layer behind `metrics:`. Imported at module level and not lazily:
# nothing in `providers` imports a model library at import time — DeepEval is
# reached inside a function, behind a `try` — so this costs nothing, and the
# alternative was the state this whole item exists to end, where the module was
# imported by no file in the package at all.
from .providers import MetricSpec, evaluate_metric, share, why_unavailable

if TYPE_CHECKING:  # `judge` reads the catalogue, which imports this module
    from .judge import Judge


#: The five shapes a rule can have, and the only ones. Written here and in
#: `spec/schema.yaml`'s `eval-rule` group, so `pact check` refuses a shape this
#: cannot carry out rather than accepting it and leaving the run to drop it.
#:
#: For a round this list did not exist and `rules_of()` kept `isinstance(r, str)`
#: — so every one of the worked example's five rules was thrown away whole, and
#: an answer breaking the author's own `must-not-contain: ["refund by", "arrive
#: on"]` graded PASS. That empty list was what the model-portability figure and
#: the learning gate were computed against, which is the project's own worst
#: failure ("config that loads and does not reach the run is worse than config
#: that does not load") sitting in the one mechanism that decides whether a
#: money-moving agent is fit to ship.
DETERMINISTIC = ("must-say-one-of", "must-contain", "must-not-contain", "must-call-before")

#: The one shape only a reader can decide. It runs — `judge.Judge` grades it with
#: the model the author named in `graded-by:` — and it is reported rather than
#: dropped whenever nothing could grade it (T7: nothing may vanish).
JUDGED = "judged"


@dataclass(frozen=True)
class Rule:
    """One thing that has to be true of an answer.

    A frozen record rather than a raw mapping so that a shape nobody can carry
    out cannot get as far as `check()` wearing the same clothes as one that can.
    """

    kind: str
    values: tuple[str, ...] = ()
    call: str = ""
    first: str = ""
    because: str = ""
    #: The sentence to put on `RunResult.unenforced` when this runtime cannot
    #: carry the rule out. Empty when it can.
    unenforced: str = ""
    #: Which file the author wrote this in, as they would type it. Stamped by
    #: `_read_rules`, which is the only thing that knows — so a judged rule that
    #: could not be graded names the file it came from rather than a generic one.
    where: str = ""

    @property
    def sentence(self) -> str:
        """The one thing a reader has to decide, for a `judged:` rule.

        Carried in `values` like every other rule's payload, so there is one
        place a rule keeps its words. For a round the sentence was read into a
        local and spent only on the "no judge here" message, which is why the
        rule could not have been run even if a judge had existed.
        """
        return self.values[0] if self.values else ""

    @staticmethod
    def read(entry: Any) -> "Rule | None":
        """One authored entry, or `None` if it is not a rule shape at all."""
        if isinstance(entry, str):
            # A plain sentence is a rule written in prose — D19's second on-ramp,
            # "must cite a source", "never promise a refund". The negative form
            # is decidable without a model (`_forbidden` understands "must
            # never/must not/does not/never"), and AC-4.5 says decide it that way
            # when you can. Everything else goes to the judge, which is what it
            # is for; it used to be carried as unenforced beside an offer to
            # rewrite the sentence as a `must-contain:` — a second construct for
            # the same idea, and one that told an author their plain English was
            # the problem.
            banned = _forbidden(entry)
            if banned:
                return Rule("must-not-contain", tuple(banned), because=entry)
            return Rule(JUDGED, (entry.strip(),))
        if not isinstance(entry, dict):
            return None
        because = str(entry.get("because", "")).strip()
        for kind in DETERMINISTIC:
            if kind not in entry:
                continue
            if kind == "must-call-before":
                spec = entry[kind] or {}
                if not isinstance(spec, dict):
                    return None
                return Rule(
                    kind,
                    call=str(spec.get("call", "")).strip(),
                    first=str(spec.get("first", "")).strip(),
                    because=because,
                )
            raw = entry[kind]
            values = [raw] if isinstance(raw, str) else list(raw or [])
            return Rule(kind, tuple(str(v) for v in values), because=because)
        if JUDGED in entry:
            said = str(entry[JUDGED] or "").strip()
            if not said:
                # The one `judged:` shape that stays unenforceable, and the only
                # thing left on this field. An empty rule cannot be put to a
                # judge and must not be reported as one that passed.
                return Rule(
                    JUDGED,
                    because=because,
                    unenforced=(
                        "`judged:` was left blank, so there was nothing to grade. "
                        "fix: write the sentence a reader would have to decide — "
                        "for example `judged: gives the reason in one sentence a "
                        "customer can understand`."
                    ),
                )
            return Rule(JUDGED, (said,), because=because)
        return None


@dataclass(frozen=True)
class Case:
    key: str
    when: str
    expect: dict[str, Any]
    must_also: tuple[Rule, ...] = ()
    #: Which job this case does — `train`, `held-out`, `quarantine`. Read so the
    #: learning loop's own first named gate ("a frozen held-out split, locked
    #: before the cycle starts") is satisfied by the author's file rather than by
    #: whatever a host hand-builds.
    split: str = ""
    #: Why the expected answer is the right one. Carried for a grader to read.
    because: str = ""
    #: What came with the situation — a photo, an attachment.
    with_: dict[str, Any] = field(default_factory=dict)
    #: The passages the answer was supposed to come from, written down by the
    #: author (A2).
    #:
    #: `providers.evaluate_metric` has taken a `retrieval_context` argument since
    #: it was written and its ONE caller never passed one, so
    #: `deepeval:faithfulness` was accepted by name and could never return a
    #: score. That is the reader-table defect running the other way — a parameter
    #: with no author.
    #:
    #: These are the passages you WROTE, not the ones a run retrieved. Three of
    #: the four retrieval metrics never look at the answer at all, so a gold
    #: context is what makes them mean anything on a machine with no index; what
    #: a run actually fetched is a different fact and belongs on the run.
    from_these_passages: tuple[str, ...] = ()
    #: Entries under `must-also:` this runtime cannot carry out, in the words a
    #: run reports them. Never dropped in silence.
    unenforced: tuple[str, ...] = ()

    @staticmethod
    def from_document(doc: dict[str, Any]) -> list["Case"]:
        cases = ((doc.get("evals") or {}).get("cases")) or {}
        out = []
        for key, c in cases.items():
            if not isinstance(c, dict):
                continue
            expect = c.get("expect")
            rules, unenforced = _read_rules(c.get("must-also"), f"case {key!r}")
            attached = c.get("with")
            out.append(
                Case(
                    key=key,
                    when=str(c.get("when", "")).strip(),
                    expect=expect if isinstance(expect, dict) else {"answer": expect},
                    must_also=rules,
                    split=str(c.get("split", "")).strip(),
                    because=str(c.get("because", "")).strip(),
                    with_=attached if isinstance(attached, dict) else {},
                    from_these_passages=tuple(
                        str(x) for x in (c.get("from-these-passages") or ()) if str(x).strip()
                    ),
                    unenforced=unenforced,
                )
            )
        return out


def _read_rules(written: Any, where: str) -> tuple[tuple[Rule, ...], tuple[str, ...]]:
    """Every entry, as a rule or as a sentence saying why it is not one.

    Nothing is dropped. An entry this runtime cannot read is reported the way
    `RunResult.unenforced` reports every other authored line it cannot apply —
    which is the difference between a gap and a lie.
    """
    rules: list[Rule] = []
    unenforced: list[str] = []
    for entry in written or []:
        rule = Rule.read(entry)
        if rule is None:
            unenforced.append(
                f"{where}: {entry!r} is not a rule PACT knows how to carry out, so it "
                f"was not applied. fix: write one of `must-say-one-of:`, "
                f"`must-contain:`, `must-not-contain:`, `must-call-before:` or `judged:`."
            )
            continue
        if rule.unenforced:
            unenforced.append(f"{where}: {rule.unenforced}")
            continue
        rules.append(replace(rule, where=where))
    return tuple(rules), tuple(unenforced)


@dataclass
class CaseOutcome:
    key: str
    passed: bool
    why: str
    #: Rules that applied to this case and that nothing could decide, each a
    #: sentence naming the file, what was not applied, and a line to type.
    #:
    #: A third state beside passed/failed, and it is here rather than folded into
    #: either for the reason `Verdict` has three outcomes: a `judged:` rule with
    #: no judge is not an answer that satisfied it. Scoring it as a pass is the
    #: silent non-enforcement T7 exists to forbid, and scoring it as a fail
    #: blames the agent for a missing grader.
    unenforced: tuple[str, ...] = ()


#: A suite that stopped because nothing on the other end of `--serving-at`
#: accepted the connection, or accepted it and never answered. The remedy is a
#: runtime: start one, pull the model, or point the command somewhere else.
NOT_SERVING = "not-serving"
#: Something is listening and it answered — with bytes no model runtime would
#: send. An author who pointed `--serving-at` at a web server is here, and
#: telling them to start a runtime sends them to a machine that is already up.
NOT_A_RUNTIME = "not-a-runtime"
#: The model answered and the RUN stopped for a reason that is not the network —
#: a teammate over its budget, a member that halted. Nothing about the machine
#: is wrong, so no sentence here may say there is.
STOPPED = "stopped"


@dataclass(frozen=True)
class Silence:
    """Why a suite produced no score, as facts rather than as a sentence.

    THE FIELD THAT MATTERS IS `answered`. "Answered three of six and then
    stopped" and "never opened a socket" were one state for a round — a verdict
    that was UNDECIDED with no results — so a machine that was serving the model
    perfectly well got reported to its author as one that is not, with "start the
    model runtime" as the remedy. Refusing to publish a SCORE off a shorter suite
    than the author wrote is argued (AC-3.1); refusing to carry the FACT that it
    answered was never argued, and it is what made that sentence reachable.

    `unenforced` is carried for the same reason and it is T7's, not convenience:
    the cases that DID answer may each have met a rule nothing could grade, and
    dropping the whole `Verdict.results` list dropped those reports with it. A
    lossy step that emits nothing is the one thing T7 forbids by name, so the
    channel is kept even though the number is not.
    """

    #: `NOT_SERVING`, `NOT_A_RUNTIME` or `STOPPED` — which remedy is honest.
    kind: str
    #: What actually happened, in as few words as the exception gave us.
    cause: str
    #: Cases that answered before the suite stopped. `0` is "never answered".
    answered: int = 0
    #: Cases the author wrote, so `answered` is readable as a fraction.
    of: int = 0
    #: Rules nothing could decide, off the cases that did answer.
    unenforced: tuple[str, ...] = ()

    def as_sentence(self, model: str) -> str:
        """The note a report prints, which is a different sentence per fact."""
        if self.answered:
            return (
                f"{model} answered {self.answered} of {self.of} cases and then "
                f"stopped, so nothing was measured on it — {self.cause}"
            )
        return f"{model} did not answer, so nothing was measured on it — {self.cause}"


@dataclass
class Verdict:
    outcome: str  # PASS | FAIL | UNDECIDED
    score: float
    bar: float
    results: list[CaseOutcome] = field(default_factory=list)
    note: str = ""
    #: Why there is no score, when there is none. `None` on every verdict
    #: `verdict()` computes — it is set only by a run that stopped, and it is
    #: what tells a reader "unmeasured" apart from "measured at nought".
    silence: "Silence | None" = None

    @property
    def failures(self) -> list[CaseOutcome]:
        return [r for r in self.results if not r.passed]

    @property
    def unenforced(self) -> list[str]:
        """Every rule this suite could not decide, once each, in order met.

        On the object the score is read off, deliberately. `unenforced_rules(doc)`
        answers the same question from the FILES and has never had a caller, so a
        judged rule that nothing graded was reported into a function nobody
        called — which from a reader's side is indistinguishable from a rule that
        passed.

        A stopped suite keeps NO results and still reports here, off
        `Silence.unenforced`. Those sentences are about cases that really ran, and
        a run that threw its score away has no business throwing away the report
        of a rule that was never applied — the score is a claim this module
        refuses to make, and the hole is a fact it is obliged to state (T7).
        """
        out: list[str] = []
        seen: set[str] = set()
        carried = list(self.silence.unenforced) if self.silence is not None else []
        for sentence in [s for r in self.results for s in r.unenforced] + carried:
            if sentence not in seen:
                seen.add(sentence)
                out.append(sentence)
        return out


#: What a run has to carry for a case to be written from it. Named rather than
#: duck-typed, so a caller handing in half a record is told which half.
FROM_A_RUN = ("asked", "output", "trace")


def case_from_a_run(
    record: Mapping[str, Any], key: str, because: str = ""
) -> dict[str, Any]:
    """One recorded run, as the eval case a person would have written (AC-4.4).

    **Every field here is post-interception, and that took two goes to be true.**
    The trace always was: `chain.run` happens before anything is recorded, which
    is what
    `test_one_order_across_kinds.py::test_nothing_that_watches_a_run_ever_sees_what_a_rule_hid`
    holds. The QUESTION was not — `as_record` took it from the caller, and the
    obvious thing to pass is the string as typed, so promoting a run on the
    worked example wrote `4111 1111 1111 1111` into a case file destined for
    version control. `RunResult.asked` is now set by the harness from the message
    after the chain ran, and `as_record` takes no argument, so there is nothing
    left for a caller to get wrong.

    `expect:` is left for a person. A failing run's own answer is the WRONG
    answer — that is why it is being promoted — and writing it into `expect:`
    would enshrine the bug as the specification. What is filled in is everything
    a person cannot reconstruct later: what was asked, what came back, and when.
    """
    missing = [f for f in FROM_A_RUN if f not in record]
    if missing:
        raise ValueError(
            f"a case cannot be written from this run: it has no {', '.join(missing)}. "
            f"Fix: pass what `RunResult.as_record()` produces."
        )
    called = [
        c["name"]
        for step in record["trace"]
        for c in step.get("tools", ())
    ]
    case: dict[str, Any] = {
        "when": record["asked"],
        # Deliberately empty, and deliberately not omitted: an empty `expect:`
        # is refused by `pact check`, so a promoted case cannot be committed
        # until a person has said what the right answer was.
        "expect": {},
        "because": because or (
            "promoted from a run that went wrong. Fill in `expect:` with what "
            "should have happened, and say why here."
        ),
    }
    return case


def what_went_wrong(record: Mapping[str, Any]) -> list[str]:
    """What the run actually did, as COMMENT lines for the promoted file.

    A reviewer needs the wrong answer in front of them to write the right one.
    It is comments and not fields, and that is a correction: the first version
    put a `went-wrong:` block inside the case, which `pact check` refused as an
    unknown field — so the file was rejected for the invented key rather than for
    the empty `expect:` it exists to make somebody fill in. A transient
    annotation for a human is not a reason to grow the schema.
    """
    called = [
        c["name"] for step in record.get("trace", ()) for c in step.get("tools", ())
    ]
    lines = [
        "What the run actually did — this is the WRONG answer, which is why it",
        "is here. Delete these lines once you have written `expect:`.",
        "",
        f"  answered: {record.get('output', '')!r}",
        f"  halted:   {record.get('halted', '')}",
    ]
    if called:
        lines.append(f"  called:   {', '.join(called)}")
    return lines


def rules_of(doc: dict[str, Any]) -> list[Rule]:
    """The suite's own rules, every one of them.

    It used to be `[r for r in ... if isinstance(r, str)]`, and every rule in the
    shipped worked example is a mapping — so this returned `[]` and the whole
    suite graded on `expect:` alone.
    """
    rules, _ = _read_rules((doc.get("evals") or {}).get("rules"), "evals/suite.yaml")
    return list(rules)


def unenforced_rules(doc: dict[str, Any], workspace: Any = None) -> list[str]:
    """Every authored rule this document cannot carry out, in words.

    Reported rather than dropped. The alternative is what shipped: five rules
    written, none applied, and a green suite saying so nowhere.

    Answered from the FILES alone — no model, no network, no run — so it is what
    a checker can say to an author where they are. A `judged:` rule whose
    `graded-by:` is missing, unknown to the catalogue, or only served off a box
    that says nothing may leave it is a mistake in the document, and
    `judge.why_no_judge` writes the sentence. Whether the weights are actually
    running is a fact about the machine and belongs to the run, which reports it
    on `Verdict.unenforced`.
    """
    rules, unenforced = _read_rules(
        (doc.get("evals") or {}).get("rules"), "evals/suite.yaml"
    )
    out = list(unenforced)
    cases = Case.from_document(doc)
    for case in cases:
        out.extend(case.unenforced)
    judged = [r for r in list(rules) + [r for c in cases for r in c.must_also]
              if r.kind == JUDGED]
    if judged:
        from .judge import why_no_judge  # local: `judge` reads the catalogue

        if refused := why_no_judge(doc, workspace):
            out.append(refused)
    # And the same question for `metrics:`. Answerable here for the same reason
    # the judge's is: whether a provider exists is decided by attempting a local
    # import, which touches no network and no model — so an author can be told
    # their score will not be taken BEFORE they run anything, rather than reading
    # it off a report an hour later. `check` asks again while it scores, because
    # a suite scored on a different box is a different answer.
    for spec in metrics_of(doc, workspace):
        if refused := why_unavailable(spec):
            out.append(refused)
    return out


def split(cases: list[Case], which: str) -> list[Case]:
    """The cases doing one job. A case with no `split:` counts as training data.

    `quarantine` is in neither half: it is the set an author has marked as not to
    be learned from and not to be scored against.
    """
    if which == "train":
        return [c for c in cases if c.split in ("", "train")]
    return [c for c in cases if c.split == which]


def bar_of(doc: dict[str, Any], default: float = 0.9) -> float:
    """The pass bar the suite states, or the default.

    The percent branch had no range check while the bare-decimal branch did, so
    `must-pass: -50%` gave `-0.5` and a six-of-six FAILING suite reported PASS
    with exit code 0. `coerce.rs` holds `Ty::Percent` to `0.0..=1.0` and names
    that exact case as fixed — but only in `pact check`, and `scoring._load`
    reads the tree through `pact show`.

    Both spellings and both fields go through `providers.share` now. `metrics:`
    added a second `percent` an adapter reads — `threshold:` — and two readers of
    "a share written `80%` or `0.8`" are two readers that can come to disagree
    about what `80%` means, which is the shape of the bug above one field over.
    """
    return share((doc.get("evals") or {}).get("must-pass"), default)


def metrics_of(
    doc: dict[str, Any], workspace: "str | Path | None" = None
) -> list[MetricSpec]:
    """The ready-made scores the suite says every answer is put through.

    The authored path for D19's fifth on-ramp, and the only reader of
    `evals.metrics:` there is. `workspace` is used for one thing — stamping the
    file and LINE each metric was written on — so a score nothing could take
    names the line to edit rather than a generic filename. Everything works
    without it; the sentences are just less precise.
    """
    source = Path(workspace) if workspace else None
    out: list[MetricSpec] = []
    for raw in (doc.get("evals") or {}).get("metrics") or []:
        spec = MetricSpec.parse(raw)
        file, line = locate(source, "evals", "suite", "suite", spec.uri)
        out.append(replace(spec, where=f"{file}:{line}"))
    return out


#: Wordings that mean the same verdict. Found the hard way: a real 7B model
#: answered *"Yes, a refund is appropriate in this case"* — correct on the
#: substance — and a literal `"approved" in text` check marked it wrong.
#: Grading the wording instead of the decision makes the oracle measure the
#: wrong thing, and every downstream claim inherits that error.
#:
#: This stays a closed, auditable table rather than a judge call: the point of a
#: deterministic checker is that it is decidable offline and cannot itself be
#: the source of a false verdict.
EQUIVALENT: dict[str, tuple[str, ...]] = {
    "approved": ("approved", "approve", "yes, a refund", "refund is appropriate",
                 "issue a refund", "grant the refund", "eligible for a refund"),
    "declined": ("declined", "decline", "denied", "deny", "not eligible",
                 "cannot be refunded", "no refund"),
}


#: Words that turn the phrase after them into its opposite. Kept to the ones
#: English actually uses immediately before a verb or a noun phrase, because a
#: wider list would start refusing sentences that only mention a negation.
_NEGATORS = ("not ", "n't", "cannot", "can not", "never", "no ", "unable to", "refus")

#: How far back to look for one. Long enough for *"I cannot approve a refund"*
#: and *"this order is not eligible for a refund"*; short enough that a negation
#: in the previous clause does not reach across.
_NEGATION_WINDOW = 24


def _stated_at(text: str, phrase: str) -> bool:
    """Is `phrase` in `text` other than inside its own negation?

    The oracle graded a REFUSAL as an APPROVAL. `EQUIVALENT["approved"]` contains
    both `approve` and `eligible for a refund`, and each of those occurs inside
    its own negation — so *"This sale item is not eligible for a refund."* and
    *"I cannot approve a refund for a sale item."* both graded PASS against
    `expect: {decision: approved}`, which are the exact wrong answers the case
    exists to catch. `_states('this order is not eligible for a refund.',
    'approved')` was True AND `_states(..., 'declined')` was True.

    The table stays closed and auditable: the fix is one guard around the `in`
    test, not more phrases. A phrase that only ever appears under a negator
    counts as not stated.
    """
    at = text.find(phrase)
    while at != -1:
        before = text[max(0, at - _NEGATION_WINDOW):at]
        if not any(n in before for n in _NEGATORS):
            return True
        at = text.find(phrase, at + 1)
    return False


def _states(text: str, want: str) -> bool:
    """Does `text` state the verdict `want`, however it is phrased?"""
    needle = want.strip().lower()
    for phrase in EQUIVALENT.get(needle, ()):
        if _stated_at(text, phrase):
            return True
    return _stated_at(text, needle)


def check(
    case: Case,
    result: RunResult,
    rules: list[Rule],
    judge: "Judge | None" = None,
    metrics: "list[MetricSpec] | None" = None,
) -> CaseOutcome:
    """Grade one case. Deterministic first, always, and a judge only if needed.

    AC-4.5 is held here structurally rather than by convention. Two passes: every
    rule decidable by looking at the answer is decided in the first, and the
    first failure returns — so a case a string check already settled never
    reaches the second pass, and a suite that wrote no `judged:` rule finds
    nothing to do in it. That is what makes "a suite decidable without a model
    must never invoke one" a property of the code rather than a promise.

    `judge` is how weights are reached, supplied by whoever runs the suite in the
    same way the transport is for a run — `judge.judge_of(doc)` builds it from
    the author's `graded-by:` line. With none, a `judged:` rule is neither passed
    nor failed: it goes on `CaseOutcome.unenforced` with a line to type.

    `metrics` is the same arrangement for the author's `evals.metrics:` line,
    built by `metrics_of(doc)`. It splits the same way `rules` does and for the
    same reason: a `pact:` score is decided by looking at the answer and is taken
    in the deterministic pass, and a `deepeval:` score reads the answer with a
    model and is taken last, so a suite whose scores are all deterministic never
    reaches a grader. A provider this machine cannot run leaves by the door a
    judgeless `judged:` rule leaves by — `CaseOutcome.unenforced`, with something
    to type — and never as a zero, because scoring a measurement nobody took as a
    failure blames the agent for a package that is not installed.
    """
    text = result.output.lower()

    for key, want in case.expect.items():
        if not isinstance(want, str):
            continue
        needle = want.strip().lower()
        if needle and not _states(text, needle):
            return CaseOutcome(case.key, False, f"expected {key} {want!r}, got {result.output!r}")

    # The case's own extra rules, then the suite's. Case first, because a case
    # rule is about this situation and reads as the more specific failure.
    written = list(case.must_also) + list(rules)
    scores = list(metrics or [])

    for rule in written:
        if rule.kind == JUDGED:
            continue
        broken = _breaks(rule, result, text)
        if broken:
            return CaseOutcome(case.key, False, broken)

    unenforced: list[str] = []
    for spec in scores:
        if not spec.deterministic:
            continue
        missed = _scores_below(spec, case, result, unenforced)
        if missed:
            return CaseOutcome(case.key, False, missed, tuple(unenforced))

    for rule in written:
        if rule.kind != JUDGED:
            continue
        broken = _breaks(rule, result, text, judge, unenforced)
        if broken:
            return CaseOutcome(case.key, False, broken, tuple(unenforced))

    for spec in scores:
        if spec.deterministic:
            continue
        missed = _scores_below(spec, case, result, unenforced, judge)
        if missed:
            return CaseOutcome(case.key, False, missed, tuple(unenforced))

    return CaseOutcome(case.key, True, "", tuple(unenforced))


def first_broken(
    rules: "list[Rule] | tuple[Rule, ...]",
    result: RunResult,
    judge: "Judge | None" = None,
    unenforced: "list[str] | None" = None,
) -> str:
    """Why this answer breaks one of `rules`, or `""` if it breaks none.

    The door an agent's own `checked-by:` goes through (02P O7): the same rule
    shapes as `evals:`, decided the same way — every rule decidable by looking at
    the answer first, a `judged:` one only after all of those passed, and only if
    something can grade it (otherwise it goes on `unenforced` with a line to
    type, exactly as `check` reports it). `result` carries the answer and the
    run's own steps, which `must-call-before:` reads.
    """
    text = result.output.lower()
    for rule in rules:
        if rule.kind != JUDGED and (broken := _breaks(rule, result, text)):
            return broken
    for rule in rules:
        if rule.kind == JUDGED and (broken := _breaks(rule, result, text, judge, unenforced)):
            return broken
    return ""


def _scores_below(
    spec: MetricSpec,
    case: Case,
    result: RunResult,
    unenforced: "list[str] | None",
    judge: "Judge | None" = None,
) -> str:
    """Why this answer misses `spec`'s bar, or `""` if it does not.

    The one line that runs an author's `metrics:` entry. Everything the metric is
    given comes off the case the author wrote — the situation as `input`, the
    answer as what is being scored, and their `expect:` as the expected answer —
    so nothing about the measurement is assembled by a caller.
    """
    taken = evaluate_metric(
        spec,
        result.output,
        _expected_text(case),
        asked=case.when,
        judge=judge.reading() if judge is not None else None,
        # A2. The author's own `from-these-passages:` if they wrote one,
        # otherwise what the run reported retrieving — in that order, because a
        # written-down gold context is a decision and an observed one is a
        # measurement, and a grader asked to check an answer against its sources
        # should be given the sources the author meant.
        retrieval_context=list(case.from_these_passages)
        or list(getattr(result, "retrieved", ()) or ()),
    )
    if taken.unenforced:
        _note(unenforced, taken.unenforced)
        return ""
    if taken.passed:
        return ""
    why = f" — {taken.reason}" if taken.reason else ""
    return (
        f"scored {taken.score:.0%} on `{spec.uri}` where {spec.where} asks for "
        f"{spec.threshold:.0%}{why}"
    )


def _expected_text(case: Case) -> str:
    """The case's own expected answer, as one string, for a metric that reads one.

    `expect:` is a map — `{decision: approved}` — because a case can state more
    than one thing about an answer. A DeepEval score takes a single
    `expected_output`, so the first thing the author wrote in words is what it
    gets, and a case that stated nothing in words gives it nothing rather than a
    made-up sentence.
    """
    for value in case.expect.values():
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _breaks(
    rule: Rule,
    result: RunResult,
    text: str,
    judge: "Judge | None" = None,
    unenforced: "list[str] | None" = None,
) -> str:
    """Why this answer breaks `rule`, or `""` if it does not.

    One function for all five shapes, so a sixth costs an arm here and a line in
    `spec/schema.yaml` rather than a second grader.
    """
    why = f" ({rule.because})" if rule.because else ""
    if rule.kind == "must-say-one-of":
        if not any(_states(text, str(v)) for v in rule.values):
            return f"says none of {list(rule.values)!r}{why}"
        return ""
    if rule.kind == "must-contain":
        missing = [v for v in rule.values if str(v).strip().lower() not in text]
        if missing:
            return f"does not say {missing!r}{why}"
        return ""
    if rule.kind == "must-not-contain":
        # The same function the live-run sentence uses. Grading a recorded case
        # and stopping a turn are different acts — which is why both exist — but
        # they ask one question, and two implementations of one question is how
        # two vocabularies come to disagree.
        said = said_any(rule.values, text)
        if said:
            return f"says {said!r}, which it must not{why}"
        return ""
    if rule.kind == "must-call-before":
        # Read off the run's own steps rather than off its words: the question is
        # what the agent DID, and an answer that describes looking up an order it
        # never looked up is exactly the failure this rule is written for.
        order = _calls(result)
        if rule.call not in order:
            return ""  # the guarded call never happened, so nothing is out of order
        at = order.index(rule.call)
        if rule.first not in order[:at]:
            return f"called {rule.call!r} without calling {rule.first!r} first{why}"
        return ""
    if rule.kind == JUDGED:
        # The fifth arm, and the only one that costs a model call. It is reached
        # last and only for a case every deterministic rule already passed —
        # `check` splits the passes for exactly that reason.
        #
        # These two sentences name the file and the rule and no line, and that is
        # correct rather than a shortfall: neither condition is a mistake in a
        # file. The author's line is right; what is missing is a grader on the
        # machine running the suite. A caret pointing at a correct line would
        # send somebody to edit something that is not wrong. The mistakes that DO
        # live in the document — no `graded-by:`, a typo, a model that only
        # answers off the box — are `judge.why_no_judge`'s, and every one of
        # those names a file and a line.
        where = rule.where or "evals/suite.yaml"
        if judge is None:
            _note(
                unenforced,
                f"{where}: `judged: {rule.sentence}` was not applied — nothing was "
                f"grading this run. fix: name a model this machine serves with "
                f"`graded-by:` under `evals:`, and run the suite where that model "
                f"is served.",
            )
            return ""
        ruling = judge.grade(rule.sentence, result.output, rule.because)
        if not ruling.decided:
            # A grader that answered neither PASS nor FAIL has decided nothing,
            # and guessing either way would make the oracle itself the source of
            # a false verdict — the thing `EQUIVALENT`'s own note refuses to do.
            _note(
                unenforced,
                f"{where}: `judged: {rule.sentence}` was not applied — "
                f"{judge.model} did not answer PASS or FAIL, it said "
                f"{ruling.said.strip()[:120]!r}. fix: point `graded-by:` at a "
                f"larger model this machine serves, or write the rule as "
                f"`must-contain:` if it can be decided by looking at the answer.",
            )
            return ""
        if not ruling.passed:
            return f"a reader would say it does not {rule.sentence!r}: {ruling.reason}{why}"
        return ""
    return ""


def _note(sentences: "list[str] | None", said: str) -> None:
    """Record a rule nothing could decide, if anyone is collecting them.

    `None` is the direct caller — a test asking one rule about one answer — and
    the sentence has nowhere to go there. Every path that scores goes through
    `check`, which always passes a list, so nothing a suite grades can lose one.
    """
    if sentences is not None and said not in sentences:
        sentences.append(said)


def _calls(result: RunResult) -> list[str]:
    """Every tool call the run made, in order, as `<tool>/<action>` when it can.

    The action half is only known when the call named one. A rule written about
    `payments/issue-refund` against a run that called `payments` with no action
    matches on the tool alone, which is the same latitude `Gate` gives an
    approval rule — and it is reported there rather than guessed at.
    """
    out: list[str] = []
    for step in result.trace():
        for call in step.get("tools") or []:
            name = str(call.get("name") or "")
            if not name:
                continue
            out.append(name)
            action = (call.get("args") or {}).get("action")
            if action and "/" not in name:
                out.append(f"{name}/{action}")
    return out


def _forbidden(sentence: str) -> list[str]:
    """Pull the banned phrase out of a plain-language negative rule.

    A closed, boring transformation on purpose: the alternative is asking a model
    what the author meant, which makes the oracle depend on the thing it is
    supposed to be checking.
    """
    s = sentence.lower()
    for marker in ("must never ", "must not ", "does not ", "never "):
        if marker in s:
            tail = s.split(marker, 1)[1].strip()
            return [tail] if tail else []
    return []


#: Assertions that gate a money-moving path must be right EVERY time; they are
#: correctness invariants, not a rate to be averaged (ADR AD-58a). A refund
#: approved outside the window is not offset by six correct ones.
CONSEQUENTIAL_BAR = 1.0


def consequential_verdict(
    results: list[CaseOutcome], consequential: set[str]
) -> Verdict:
    """Grade the money-moving subset. Any failure is fatal, whatever the average."""
    subset = [r for r in results if r.key in consequential]
    if not subset:
        return Verdict("PASS", 1.0, CONSEQUENTIAL_BAR, [], "no consequential assertions")
    score = sum(1 for r in subset if r.passed) / len(subset)
    return Verdict(
        "PASS" if score >= CONSEQUENTIAL_BAR else "FAIL",
        score, CONSEQUENTIAL_BAR, subset,
        "" if score >= CONSEQUENTIAL_BAR
        else "a money-moving assertion failed; an average cannot excuse it",
    )


def verdict(results: list[CaseOutcome], bar: float, min_cases: int = 5) -> Verdict:
    """Score the suite, refusing to decide when it is too small to mean anything.

    `min_cases` is the honest floor: a bar of 90% cannot be distinguished from
    chance on three cases, so a suite that small returns UNDECIDED rather than a
    number that reads as evidence.
    """
    if not results:
        return Verdict("UNDECIDED", 0.0, bar, results, "no cases")
    score = sum(1 for r in results if r.passed) / len(results)
    if len(results) < min_cases:
        return Verdict(
            "UNDECIDED", score, bar, results,
            f"{len(results)} cases is too few to support a {bar:.0%} bar "
            f"(needs at least {min_cases})",
        )
    return Verdict("PASS" if score >= bar else "FAIL", score, bar, results)


if __name__ == "__main__":  # pragma: no cover
    # `python -m pact_adapters.evals <path>` — the whole of D14 for this
    # mechanism. Everything above could grade a run and nothing could RUN one:
    # no entry point, no console script, no `main`, so the author of a suite had
    # to write Python to learn whether their agent passes.
    #
    # The runner lives in `scoring.py` and is IMPORTED here by its absolute name
    # rather than defined here. Two reasons, and the second is not style: this
    # module is the grader and mixing a command into it would put the thing that
    # decides a verdict and the thing that prints one in one file; and `-m`
    # executes this file a second time under the name `__main__`, so a `Case`
    # built here would not be the `Case` that `resolve.py` and `learning.py`
    # imported. Reaching for the package copy keeps one of each.
    import sys as _sys

    from pact_adapters.scoring import main as _main

    raise SystemExit(_main(_sys.argv[1:]))
