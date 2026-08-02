"""The judge — the fifth eval rule, running (G7, D19 on-ramp 5, AC-4.5).

`examples/refund-desk/evals/suite.yaml` has written this since it was written:

    - judged: gives the reason in one sentence a customer can understand
      because: a wall of policy text reads as a refusal even when we approve
    graded-by: qwen2.5-14b-instruct

For a round both lines loaded, validated, resolved — and decided nothing.
`Rule.read` returned the `judged:` shape carrying *"judging needs a model, and
this runtime has no judge wired up"*, `_read_rules` put that on `unenforced`, and
the rule never reached `rules` at all. Measured before this file existed:
`rules_of(doc)` came back `['must-say-one-of', 'must-not-contain',
'must-call-before']` and `graded-by:` was read by nobody in the adapter.

Every test here is named as the guarantee it holds. The first one is the bar the
plan sets: the author's own line has to change a **measured score**, not merely
appear in a list.

Everything below runs offline. The grading model is scripted — a judge is a
reader, and a real reader here would measure sampling noise and need weights the
test cannot assume — except for the last test, which is opt-in and talks to the
real locally-served row.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.evals import (  # noqa: E402
    JUDGED,
    Case,
    Rule,
    bar_of,
    check,
    rules_of,
    unenforced_rules,
    verdict,
)
from pact_adapters.harness import RunResult, run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.judge import (  # noqa: E402
    Judge,
    local_ask,
    judge_of,
    read_grade,
    served_here,
    why_no_judge,
)

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"


@pytest.fixture(scope="module")
def doc() -> dict:
    """The worked example as the loader produces it — nothing hand-built.

    The whole point of these tests is that the AUTHOR's two lines reach the
    grader, so the document has to come through `pact show` rather than out of a
    literal in this file.
    """
    if not PACT_BIN.exists():
        out = subprocess.run(
            ["cargo", "run", "--quiet", "-p", "pact-cli", "--", "show", str(EXAMPLE)],
            capture_output=True, text=True, cwd=REPO, timeout=900,
        )
        if out.returncode != 0:
            pytest.skip("pact-cli not built; run ./scripts/test-all.sh")
        return json.loads(out.stdout)
    out = subprocess.run(
        [str(PACT_BIN), "show", str(EXAMPLE)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


# ───────────────────────────────────────────────── a scripted reader and agent


def one_sentence_reader(system: str, user: str) -> str:
    """A stand-in for the grading model, applying the author's actual rule.

    *"Gives the reason in one sentence a customer can understand"* — so this
    counts sentences and nothing else. Deliberately not a lookup table keyed on
    the answer: a table would pass this file's own tests while proving nothing
    about whether a real judge's verdict can reach the score, and the shape of
    what it returns (a word, then a reason) is exactly what the live model is
    asked for in `judge.RUBRIC`.
    """
    answer = user.split("ANSWER:", 1)[-1]
    sentences = [s for s in answer.replace("\n", " ").split(".") if s.strip()]
    if len(sentences) <= 2:
        return "PASS\nthe decision and one reason, which is all a customer needs."
    return f"FAIL\nthe reason runs to {len(sentences) - 1} sentences of policy."


#: What the stand-in agent answers, per situation. Four of the six give the
#: decision and one reason; two bury it in clause references. Written out rather
#: than generated so that "the two arms saw the same answers" is inspectable.
#:
#: The two failing answers were milder at first — six short, plain sentences —
#: and the live 14B judge PASSED one of them, saying *"the answer provides a
#: clear, concise reason for approval that a customer can easily understand."*
#: It was right and the sentence-counting stand-in was wrong, which is exactly
#: what the live cross-check below exists to catch. They are real walls of policy
#: now, so a reader and a counter agree.
ANSWERS: tuple[tuple[str, str], ...] = (
    ("cracked", "DECISION: approved. The lamp was damaged in transit within 30 "
                "days, so we are refunding 40 USD in full."),
    ("45 days", "DECISION: declined. Under clause 4 of the returns policy, "
                "change-of-mind returns are accepted within 30 days of the "
                "delivery date, calculated from the carrier's first delivery "
                "attempt and excluding weekends and public holidays. Clause 5 "
                "provides that this period may be extended only where the goods "
                "are found to be defective, not of satisfactory quality, or not "
                "as described within the meaning of the applicable consumer "
                "legislation. The order in question was delivered 45 days before "
                "this request was raised, and no defect has been reported at any "
                "point in the ticket history. Clause 7 reserves discretionary "
                "extensions to the returns supervisor and they are not available "
                "through this channel. The request accordingly falls outside the "
                "scope of clauses 4 and 5."),
    ("fourth refund", "DECISION: declined. A person is reviewing this request "
                      "before anything is paid out."),
    ("gift card", "DECISION: approved. Under clause 2 of the returns policy, "
                  "goods found to be faulty within the 30-day statutory window "
                  "are eligible for reimbursement of the purchase price in full. "
                  "Clause 6 governs mixed-tender settlements and requires that "
                  "each tender be reimbursed to its originating instrument in the "
                  "proportion in which it was applied at the point of sale. The "
                  "original settlement comprised a card tender and a gift card "
                  "tender, and both are therefore in scope of clause 6. "
                  "Reimbursement will be initiated against each tender separately "
                  "in accordance with the settlement schedule maintained by the "
                  "payments team. No further action is required of the customer "
                  "at this stage."),
    ("dog's name", "DECISION: declined. Personalised items cannot be returned "
                   "unless they are faulty."),
    ("zip", "DECISION: approved. The jacket had a broken zip, and sale items "
            "follow the same rules as everything else."),
)


class Deciding:
    """One answer per situation, with no model and no network.

    The answers are held fixed on purpose: this file measures what the *grader*
    does, and an agent whose wording moved between the two arms would make the
    score difference unattributable.
    """

    name = "deciding"

    def lattice(self) -> dict[str, str]:
        return {}

    async def model_call(self, system, history, tools):
        asked = " ".join(str(m.get("content") or "") for m in history).lower()
        for marker, said in ANSWERS:
            if marker in asked:
                return said, []
        return "DECISION: declined. Nothing here matched a rule we hold.", []


def _agent(doc: dict) -> AgentSpec:
    """The worked example's own agent, exactly as authored.

    Nothing is overridden. Its `loop:` walks `gather -> re-read -> reply` and the
    stand-in answers the same thing at each stage, so the run finishes with the
    authored answer and calls no tools — which satisfies `must-call-before:`
    vacuously and keeps the deterministic half of the suite identical across both
    arms. Stripping `tools` breaks the loop's own `may-use: [zendesk]`, and
    forcing `max_steps=1` parks the run on `steps-at-most` before it can reply;
    both were tried, and both measure the harness rather than the grader.
    """
    return AgentSpec.from_document(doc, "refund-desk")


def _answers(doc: dict) -> list[tuple[Case, RunResult]]:
    """Run every authored case once. The same results grade both arms.

    The approval gate is suppressed exactly as `resolve.evaluate` suppresses it,
    and for the reason stated there: a run that parks for a person cannot be
    scored, so every governed case would come back "did not answer" and the
    grader would be measuring a policy doing its job. The questions stay, so the
    wording an eval asserts on is unchanged.
    """
    import asyncio

    spec = _agent(doc)
    ungated = spec.asking.asking_only()
    out = []
    for case in Case.from_document(doc):
        result = asyncio.run(run(spec, Deciding(), case.when, {}, asking=ungated))
        assert result.halted == "final", (case.key, result.halted)
        out.append((case, result))
    return out


def _without_the_judged_rule(doc: dict) -> dict:
    """The same document with the author's `judged:` line deleted, and nothing else."""
    plain = copy.deepcopy(doc)
    written = (plain.get("evals") or {}).get("rules") or []
    plain["evals"]["rules"] = [
        r for r in written if not (isinstance(r, dict) and JUDGED in r)
    ]
    assert len(plain["evals"]["rules"]) == len(written) - 1, "the example must have one"
    return plain


# ───────────────────────────────────────────────────────────────── the bar


def test_a_judged_rule_the_author_wrote_lowers_the_score_the_suite_reports(doc) -> None:
    """The measurement, and the reason this mechanism is worth having.

    Same six authored cases, the same six answers, the same deterministic rules,
    the same grading model — and the only difference between the two arms is one
    line in `evals/suite.yaml`. With it, two answers that bury the decision in
    policy fail, the score falls below the bar the author typed, and the suite's
    verdict flips from PASS to FAIL.

    A `judged:` rule that loaded and did not run would pass every other test in
    this file's neighbourhood and fail this one, which is the whole point: before
    this, the rule could refuse nothing.
    """
    graded, why = judge_of(doc, ask=one_sentence_reader, workspace=EXAMPLE)
    assert graded is not None, why
    assert graded.model == "qwen2.5-14b-instruct", "the author's `graded-by:` line"

    answered = _answers(doc)
    plain = _without_the_judged_rule(doc)

    with_rule = verdict(
        [check(c, r, rules_of(doc), judge=graded) for c, r in answered], bar_of(doc)
    )
    without_rule = verdict(
        [check(c, r, rules_of(plain), judge=graded) for c, r in answered], bar_of(doc)
    )

    assert without_rule.score > with_rule.score, (without_rule.score, with_rule.score)
    assert (without_rule.outcome, with_rule.outcome) == ("PASS", "FAIL")

    # And why — so an edit that quietly makes the two arms equal fails loudly
    # here rather than passing vacuously.
    assert not without_rule.failures, [f.why for f in without_rule.failures]
    assert {f.key for f in with_rule.failures} == {"outside-window", "partial-gift-card"}
    assert all("sentences of policy" in f.why for f in with_rule.failures)
    assert with_rule.unenforced == [], with_rule.unenforced


# ──────────────────────────────────────────────────── AC-4.5: order, and never


def test_a_case_a_string_check_already_failed_is_never_put_to_a_model(doc) -> None:
    """AC-4.5's first half, held structurally rather than by convention.

    Deterministic rules decide first, and the first failure returns — so an
    answer that broke `must-not-contain:` costs no grading call at all. The
    property matters twice: a judge is the only thing here that costs money and
    time, and a suite whose failures depend on a model is a suite whose failures
    are not reproducible.
    """
    asked: list[str] = []

    def counting(system: str, user: str) -> str:
        asked.append(user)
        return "PASS\nfine"

    graded, why = judge_of(doc, ask=counting, workspace=EXAMPLE)
    assert graded is not None, why

    # The `expect:` line settles it before any rule is even looked at.
    wrong_answer = RunResult(output="DECISION: declined. Nothing was wrong with it.")
    expected = check(
        Case("wrong", "a customer wants a refund", {"decision": "approved"}),
        wrong_answer, rules_of(doc), judge=graded,
    )
    assert expected.passed is False and "expected decision" in expected.why
    assert asked == [], "an `expect:` miss must not reach the judge either"

    case = Case("bad", "a customer wants a refund", {"decision": "approved"})
    broke_a_string_rule = RunResult(
        output="DECISION: approved. Your refund by Friday, and it will arrive on Monday."
    )
    outcome = check(case, broke_a_string_rule, rules_of(doc), judge=graded)

    assert outcome.passed is False
    assert "refund by" in outcome.why
    assert asked == [], "a deterministic failure must not reach the judge"


def test_a_suite_with_no_judged_rule_asks_the_judge_nothing(doc) -> None:
    """AC-4.5's second half: *a suite decidable without a model must never
    invoke one.* This is what keeps the whole runner air-gapped by default (D17)
    — a workspace that wrote only string rules never opens a socket, whatever
    grader happens to be available."""
    asked: list[str] = []

    def counting(system: str, user: str) -> str:
        asked.append(user)
        return "PASS\nfine"

    graded, _ = judge_of(doc, ask=counting, workspace=EXAMPLE)
    plain = _without_the_judged_rule(doc)
    for case, result in _answers(doc):
        check(case, result, rules_of(plain), judge=graded)
    assert asked == []


# ──────────────────────────────────────── what `graded-by:` now refuses to bind


def test_a_judge_that_only_answers_off_this_box_is_refused_where_the_author_is(doc) -> None:
    """D17, over the third model binding — and the one that sees the most.

    `examples/refund-desk/workspace.yaml` says `allow-egress: []`: nothing in
    this workspace may talk to anything outside the box. A `graded-by:` naming a
    hosted row is therefore refused before anything is graded, with the file, the
    line, and a locally-served id to type — the same refusal `pact check` already
    makes over `model:` and `summarised-by:`, arriving in the runner too so an
    air-gapped author cannot discover it at suite time.
    """
    hosted = copy.deepcopy(doc)
    hosted["evals"]["graded-by"] = "claude-opus-5"

    graded, why = judge_of(hosted, workspace=EXAMPLE)
    assert graded is None, "a hosted judge must not bind under `allow-egress: []`"
    assert "evals/suite.yaml:" in why, why
    assert "claude-opus-5" in why and "outside the box" in why
    assert "fix: write `graded-by: qwen2.5-7b-instruct`" in why, why
    assert "add `llm` to `allow-egress:`" in why


def test_which_model_grades_is_whichever_one_the_author_typed(doc) -> None:
    """The line, not a constant — which is the thing this project keeps shipping
    the other way round.

    A judge hardcoded to the right id would satisfy every score measurement in
    this file, because the right id is what the worked example writes. Changing
    the author's line and watching the binding follow is what tells the two
    apart, and it is why the refusal tests either side of this one exist.
    """
    graded, why = judge_of(doc, ask=one_sentence_reader, workspace=EXAMPLE)
    assert graded is not None, why
    assert graded.model == "qwen2.5-14b-instruct"

    moved = copy.deepcopy(doc)
    moved["evals"]["graded-by"] = "qwen2.5-7b-instruct"
    other, why = judge_of(moved, ask=one_sentence_reader, workspace=EXAMPLE)
    assert other is not None, why
    assert other.model == "qwen2.5-7b-instruct"


def test_a_judge_the_catalogue_has_never_heard_of_names_one_it_has(doc) -> None:
    """A typo in `graded-by:` is a mistake in a file, so it reads like one.

    Before `graded-by:` was resolved anywhere in the adapter it could name
    anything at all — the field was `map of text` at one point and the shipped
    example named a model in no catalogue and no `served-by:` row.
    """
    typo = copy.deepcopy(doc)
    typo["evals"]["graded-by"] = "qwen2.5-14b-instrct"
    graded, why = judge_of(typo, ask=one_sentence_reader, workspace=EXAMPLE)
    assert graded is None
    assert "has no row for" in why and "qwen2.5-14b-instrct" in why
    assert "fix: write `graded-by: " in why


def test_a_judged_rule_with_no_graded_by_line_is_reported_from_the_files_alone(doc) -> None:
    """Said where the author is, with no model, no network and no run.

    `unenforced_rules` answers from the document, which is what lets a checker
    tell somebody their rule will not be applied *before* they run anything.
    """
    orphan = copy.deepcopy(doc)
    orphan["evals"].pop("graded-by")
    said = unenforced_rules(orphan, EXAMPLE)
    assert len(said) == 1, said
    assert "`graded-by:` is not set" in said[0]
    assert "fix: add `graded-by: qwen2.5-14b-instruct`" in said[0]
    # And the document as shipped has nothing to report.
    assert unenforced_rules(doc, EXAMPLE) == []


def test_a_judged_rule_nothing_graded_is_reported_and_never_counted_as_passed(doc) -> None:
    """T7, in the one place it decides whether an agent ships.

    With no judge the rule is neither passed nor failed. It lands on the outcome
    — and so on the `Verdict` the score is read off — as a sentence naming the
    file, what was not applied, and something to type. Scoring it as a pass would
    let a suite report 100% on a rule nobody ran, which is exactly the state this
    module was in for a round.
    """
    answered = _answers(doc)
    ungraded = verdict(
        [check(c, r, rules_of(doc), judge=None) for c, r in answered], bar_of(doc)
    )
    assert ungraded.outcome == "PASS", "the string rules still decide what they can"
    assert len(ungraded.unenforced) == 1, ungraded.unenforced
    said = ungraded.unenforced[0]
    assert said.startswith("evals/suite.yaml:")
    assert "gives the reason in one sentence a customer can understand" in said
    assert "fix: name a model this machine serves" in said


def test_a_portability_report_says_when_its_number_rests_on_an_ungraded_rule(doc) -> None:
    """The number and the hole in it, printed together.

    `resolve()` is where evals decide whether a model may be bound at all, so a
    suite whose `judged:` rule nothing graded is a portability figure with a
    missing term. It used to be impossible to notice: the rule was dropped before
    `rules_of` returned, so the report was complete on its face and short one
    rule underneath. Passing a judge in removes the line; passing none prints it.
    """
    from pact_adapters.evals import Verdict
    from pact_adapters.resolve import PortabilityReport

    answered = _answers(doc)
    ungraded = verdict(
        [check(c, r, rules_of(doc), judge=None) for c, r in answered], bar_of(doc)
    )
    report = PortabilityReport(
        "refund-desk", "qwen2.5-7b-instruct", "the hand-authored frontier strategy",
        ungraded, "authored",
    )
    assert "NOT APPLIED:" in report.render(), report.render()
    assert "gives the reason in one sentence" in report.render()

    graded, _ = judge_of(doc, ask=one_sentence_reader, workspace=EXAMPLE)
    with_judge = verdict(
        [check(c, r, rules_of(doc), judge=graded) for c, r in answered], bar_of(doc)
    )
    quiet = PortabilityReport(
        "refund-desk", "qwen2.5-7b-instruct", "the hand-authored frontier strategy",
        with_judge, "authored",
    )
    assert "NOT APPLIED:" not in quiet.render(), quiet.render()
    assert isinstance(with_judge, Verdict)


def test_a_grader_that_answers_neither_pass_nor_fail_has_decided_nothing(doc) -> None:
    """Three outcomes, one level down from `Verdict`'s three.

    A grading model too small to follow the rubric is a fact about the grader,
    not about the answer. Guessing PASS would silently stop enforcing the rule;
    guessing FAIL would blame the agent for the judge. It is reported, with the
    model named and its actual words quoted, so the fix is obvious.
    """
    graded, _ = judge_of(doc, ask=lambda s, u: "Well, it depends.", workspace=EXAMPLE)
    case = Case("one", "a customer wants a refund", {"decision": "approved"})
    good = RunResult(output="DECISION: approved. It arrived damaged within 30 days.")

    outcome = check(case, good, rules_of(doc), judge=graded)
    assert outcome.passed is True
    assert len(outcome.unenforced) == 1
    assert "did not answer PASS or FAIL" in outcome.unenforced[0]
    assert "qwen2.5-14b-instruct" in outcome.unenforced[0]
    assert "'Well, it depends.'" in outcome.unenforced[0]


# ────────────────────────────────── plain language, which is on-ramp 2 of five


def test_a_plain_language_rule_that_is_not_a_prohibition_goes_to_the_judge(doc) -> None:
    """D19's second on-ramp — *"must cite a source"* — reaching the grader.

    A negative sentence stays deterministic, because AC-4.5 says decide without a
    model wherever you can. A positive one used to be carried as unenforced
    alongside an offer to rewrite it as `must-contain:`, which was a second
    construct for the same idea and told a support lead their plain English was
    the problem. There is one construct now and it runs.
    """
    prohibition = Rule.read("must never promise a delivery date")
    assert prohibition is not None
    assert prohibition.kind == "must-not-contain"
    assert prohibition.values == ("promise a delivery date",)

    positive = Rule.read("cites the policy the decision came from")
    assert positive is not None
    assert positive.kind == JUDGED
    assert positive.sentence == "cites the policy the decision came from"
    assert positive.unenforced == "", "there is a judge for this now"

    graded = Judge("qwen2.5-14b-instruct", lambda s, u: "FAIL\nno policy is named")
    case = Case("one", "a customer wants a refund", {})
    outcome = check(case, RunResult(output="DECISION: declined."), [positive],
                    judge=graded)
    assert outcome.passed is False
    assert "no policy is named" in outcome.why


def test_a_judged_rule_left_blank_is_the_one_shape_that_still_cannot_run() -> None:
    """An empty rule has nothing to put to a judge, so it says so and names the
    line to write. Kept on `Rule.unenforced` because it is a mistake in the
    document rather than a missing capability."""
    blank = Rule.read({"judged": "   ", "because": "we want short answers"})
    assert blank is not None
    assert blank.kind == JUDGED
    assert "was left blank" in blank.unenforced
    assert "fix: write the sentence" in blank.unenforced


# ─────────────────────────────────────────────── reading what a model wrote back


@pytest.mark.parametrize(
    "said, decided, passed",
    [
        ("PASS\nreads clearly", True, True),
        ("FAIL\ntoo long", True, False),
        ("**PASS** — one sentence and a reason", True, True),
        ("Verdict: FAIL\nit quotes four paragraphs of policy", True, False),
        ("- pass", True, True),
        ("I would rather not say", False, False),
        ("", False, False),
        # The two that must NOT be mined for a verdict. Both are ordinary English
        # about a refund, and a looser reader turns each into its opposite.
        ("The 30-day window has passed, so this is out of scope.", False, False),
        ("This does not pass the rule as written.", False, False),
    ],
)
def test_a_verdict_is_read_through_decoration_but_never_invented(
    said: str, decided: bool, passed: bool
) -> None:
    """Tolerant about how a model dresses its answer, strict about whether there
    is one. Refusing `**PASS**` would report a working judge as broken; reading
    *"the 30-day window has passed"* as PASS would make the judge silently invert
    its own verdict, which is worse than having none."""
    ruling = read_grade(said)
    assert (ruling.decided, ruling.passed) == (decided, passed)
    if decided:
        assert ruling.reason, "a verdict without a reason is not reviewable"


def test_the_judge_is_shown_the_authors_own_because_line() -> None:
    """`because:` already exists for whoever reads the failure; the judge reads
    it too. It is the difference between grading the words of a rule and grading
    what the rule is for, and it costs nothing to send."""
    seen: list[str] = []
    graded = Judge("m", lambda s, u: (seen.append(u), "PASS\nfine")[1])
    graded.grade("gives one reason", "DECISION: approved.", "a wall of text reads as a refusal")
    assert "RULE: gives one reason" in seen[0]
    assert "WHY THE RULE EXISTS: a wall of text reads as a refusal" in seen[0]
    assert "ANSWER:\nDECISION: approved." in seen[0]


# ──────────────────────────────────────────────────────────── the live judge


@pytest.mark.skipif(
    not os.environ.get("PACT_LIVE_JUDGE"),
    reason="opt-in: set PACT_LIVE_JUDGE=1 with the `graded-by:` row served locally",
)
def test_the_locally_served_row_the_example_names_really_grades_its_own_rule(doc) -> None:
    """The air-gapped path, end to end, against real weights.

    Nothing is injected: `judge_of(doc)` reads `graded-by: qwen2.5-14b-instruct`,
    resolves the row through `models/catalog.yaml`, finds the tag the local
    runtime answers to via `also-known-as:`, and grades with it. No network
    leaves the box, which is what makes this the shipped path rather than a
    demonstration (D17).

    Held to the direction of the verdict rather than to its wording: a one-line
    answer must pass the author's rule and six sentences of policy must not.
    """
    graded, why = judge_of(doc, workspace=EXAMPLE)
    if graded is None:
        pytest.skip(f"not serving it here: {why}")
    rule = next(r for r in rules_of(doc) if r.kind == JUDGED)

    short = graded.grade(rule.sentence, ANSWERS[0][1], rule.because)
    wall = graded.grade(rule.sentence, ANSWERS[3][1], rule.because)

    assert short.decided and wall.decided, (short.said, wall.said)
    assert short.passed is True, short.said
    assert wall.passed is False, wall.said


@pytest.mark.skipif(
    not os.environ.get("PACT_LIVE_JUDGE"),
    reason="opt-in: set PACT_LIVE_JUDGE=1 with the `graded-by:` row served locally",
)
def test_the_live_judge_changes_the_measured_score_exactly_as_the_scripted_one_does(doc) -> None:
    """The same measurement as the first test in this file, with real weights.

    It exists so that the scripted reader above is checkable rather than merely
    convenient: if the two ever disagree, the stand-in has stopped standing in
    for anything.
    """
    graded, why = judge_of(doc, workspace=EXAMPLE)
    if graded is None:
        pytest.skip(f"not serving it here: {why}")
    answered = _answers(doc)
    plain = _without_the_judged_rule(doc)
    with_rule = verdict(
        [check(c, r, rules_of(doc), judge=graded) for c, r in answered], bar_of(doc)
    )
    without_rule = verdict(
        [check(c, r, rules_of(plain), judge=graded) for c, r in answered], bar_of(doc)
    )
    assert without_rule.outcome == "PASS", [f.why for f in without_rule.failures]
    assert with_rule.score < without_rule.score, (
        with_rule.score, [f.why for f in with_rule.failures], with_rule.unenforced
    )


def test_nothing_here_reaches_for_a_runtime_that_is_not_answering() -> None:
    """The air-gap, stated as a property rather than as an intention.

    `served_here` asks a local address and comes back empty on any failure —
    nothing installed, nothing started, no network at all — and `local_ask`
    returns nothing rather than a route. There is no hosted fallback anywhere in
    this path, which is what D17 means: a missing local model produces a sentence
    with something to type, never a call that goes looking for the internet.
    """
    nowhere = "http://127.0.0.1:1/v1"
    assert served_here(nowhere) == frozenset()
    assert local_ask("qwen2.5-14b-instruct", base_url=nowhere) is None


def test_a_judge_needs_weights_this_machine_actually_has(doc) -> None:
    """The last refusal, and it is about the box rather than the document.

    A `graded-by:` row can be perfectly valid, locally served according to the
    catalogue, and simply not pulled — which is the ordinary state of a fresh
    air-gapped install, and the one case a document check can never catch. The
    document is fine, so `why_no_judge` says nothing; `judge_of` is the one that
    has to name what to run, and it names the tag the runtime answers to rather
    than the catalogue id, because `ollama pull qwen2.5-vl-7b-instruct` is not a
    line that works.
    """
    absent = copy.deepcopy(doc)
    absent["evals"]["graded-by"] = "qwen2.5-vl-7b-instruct"
    assert why_no_judge(absent, EXAMPLE) == "", "a locally-served row is a fine choice"

    graded, why = judge_of(absent, workspace=EXAMPLE)
    if graded is not None:
        pytest.skip("this machine is serving that row too, so there is nothing to refuse")
    assert "is not serving right now" in why, why
    assert "fix: start it — `ollama pull qwen2.5vl:7b`" in why, why
