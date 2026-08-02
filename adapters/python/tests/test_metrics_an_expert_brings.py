"""Ready-made scores an expert brings — D19's fifth on-ramp, running (D6, FR-3.1.3).

`examples/refund-desk/evals/suite.yaml` now writes this:

    metrics:
      - uri: pact:at_most_words
        threshold: 80%
        with: { words: 60 }

For a round there was no door to write it through. Measured before this file
existed: `grep -n metrics spec/schema.yaml` returned nothing, so
`metrics: [{uri: deepeval:faithfulness, threshold: 0.8}]` under `evals:` was
answered *"'metrics' is not something evals can have"*; and `grep -rn
'import.*providers' adapters/python/src` returned nothing, so
`pact_adapters/providers.py` — whose own docstring says a metric is named by URI
in YAML — was imported by no file in the package. A provider layer serving a
field that did not exist, and a field nobody could write.

Every test here is named as the guarantee it holds. The first is the bar: the
author's own line has to change a **measured score**, not merely appear in a
list. The second is the one that catches the failure this project keeps shipping
— it hands the scorer nothing but the loaded document and the answers, and the
score still changes, because a test that builds the metric itself proves the
metric works and says nothing about whether the author's line reaches it.

Everything below runs offline and reaches no network. The one test about a
missing provider makes that a property rather than an intention: it removes the
provider and asserts a sentence with a line to type comes back, with nothing
attempted over a socket.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters import providers  # noqa: E402
from pact_adapters.evals import (  # noqa: E402
    Case,
    bar_of,
    check,
    metrics_of,
    rules_of,
    unenforced_rules,
    verdict,
)
from pact_adapters.harness import RunResult, run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.judge import judge_of  # noqa: E402
from pact_adapters.providers import (  # noqa: E402
    MetricSpec,
    available_deepeval_metrics,
    evaluate_metric,
    share,
    why_unavailable,
)

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"


@pytest.fixture(scope="module")
def doc() -> dict:
    """The worked example as the loader produces it — nothing hand-built.

    The whole point of these tests is that the AUTHOR's `metrics:` line reaches
    the scorer, so the document comes through `pact show` rather than out of a
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


# ───────────────────────────────────────────────────────────── a scripted agent


#: What the stand-in agent answers, per situation. Four of the six give the
#: decision and one reason and come in well under the author's 60-word target;
#: two bury it in clause references and run past 100 words. Written out rather
#: than generated so that "the two arms saw the same answers" is inspectable,
#: and held fixed because this file measures what the SCORE does — an agent whose
#: wording moved between arms would make the difference unattributable.
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
                "through this channel."),
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
                  "payments team."),
    ("dog's name", "DECISION: declined. Personalised items cannot be returned "
                   "unless they are faulty."),
    ("zip", "DECISION: approved. The jacket had a broken zip, and sale items "
            "follow the same rules as everything else."),
)


class Deciding:
    """One answer per situation, with no model and no network."""

    name = "deciding"

    def lattice(self) -> dict[str, str]:
        return {}

    async def model_call(self, system, history, tools):
        asked = " ".join(str(m.get("content") or "") for m in history).lower()
        for marker, said in ANSWERS:
            if marker in asked:
                return said, []
        return "DECISION: declined. Nothing here matched a rule we hold.", []


def _answers(doc: dict) -> list[tuple[Case, RunResult]]:
    """Run every authored case once. The same results grade every arm.

    The approval gate is suppressed exactly as `resolve.evaluate` suppresses it,
    and for the reason stated there: a run that parks for a person cannot be
    scored, so every governed case would come back "did not answer" and the score
    would be measuring a policy doing its job.
    """
    import asyncio

    spec = AgentSpec.from_document(doc, "refund-desk")
    ungated = spec.asking.asking_only()
    out = []
    for case in Case.from_document(doc):
        result = asyncio.run(run(spec, Deciding(), case.when, {}, asking=ungated))
        assert result.halted == "final", (case.key, result.halted)
        out.append((case, result))
    return out


def _without_the_metric(doc: dict) -> dict:
    """The same document with the author's `metrics:` line deleted, and nothing else."""
    plain = copy.deepcopy(doc)
    assert plain["evals"].pop("metrics", None), "the worked example must write one"
    return plain


# ─────────────────────────────────────────────────────────────────────── the bar


def test_a_metric_the_author_wrote_lowers_the_score_the_suite_reports(doc) -> None:
    """The measurement, and the reason this mechanism is worth having.

    Same six authored cases, the same six answers, the same rules — and the only
    difference between the two arms is three lines in `evals/suite.yaml`. With
    them, the two answers that run to a wall of clause references score under the
    author's own 80% bar on a 60-word target, and the suite's verdict flips from
    PASS to FAIL.

    A `metrics:` entry that loaded and did not run would pass every other test in
    this file's neighbourhood and fail this one, which is the whole point: before
    this, the line could refuse nothing.
    """
    answered = _answers(doc)
    plain = _without_the_metric(doc)

    with_score = verdict(
        [check(c, r, rules_of(doc), metrics=metrics_of(doc, EXAMPLE)) for c, r in answered],
        bar_of(doc),
    )
    without_score = verdict(
        [check(c, r, rules_of(plain), metrics=metrics_of(plain, EXAMPLE)) for c, r in answered],
        bar_of(doc),
    )

    assert without_score.score > with_score.score, (without_score.score, with_score.score)
    assert (without_score.outcome, with_score.outcome) == ("PASS", "FAIL")

    # And why — so an edit that quietly makes the two arms equal fails loudly
    # here rather than passing vacuously.
    assert not without_score.failures, [f.why for f in without_score.failures]
    assert {f.key for f in with_score.failures} == {"outside-window", "partial-gift-card"}
    for failed in with_score.failures:
        assert "pact:at_most_words" in failed.why
        assert "60 is the most" in failed.why
        assert "evals/suite.yaml:" in failed.why, "a failure names the line it came from"


def test_the_authored_metric_reaches_the_scorer_with_nothing_passed_in(doc) -> None:
    """The one this project keeps getting wrong, held as a property.

    Four rounds running, an authoring field was added, resolved from the
    document, and read by nobody — because the tests built the object in Python
    instead of letting the author's line reach it. So nothing about scores is
    passed in here. `scoring._run_every_case` is handed the loaded document and
    the workspace root and reads `evals.metrics:` off them itself, which is the
    same call `score()` makes when somebody types `./scripts/pact-eval`.

    Delete the `scores = metrics_of(document, root)` line in `scoring.py` and
    this test fails while every other test in the file still passes. That is the
    difference between a field that reaches an object and a field that decides
    something.
    """
    from pact_adapters.scoring import _run_every_case

    spec = AgentSpec.from_document(doc, "refund-desk")
    cases = Case.from_document(doc)
    results, _movers, _caveats, _latencies = _run_every_case(
        spec, cases, rules_of(doc), lambda: Deciding(), doc, None, EXAMPLE
    )

    assert len(results) == len(cases)
    refused = [r for r in results if not r.passed]
    assert {r.key for r in refused} == {"outside-window", "partial-gift-card"}
    assert all("pact:at_most_words" in r.why for r in refused), [r.why for r in refused]


def test_the_bar_a_score_is_held_to_is_whichever_one_the_author_typed(doc) -> None:
    """The line, not a constant — which is the thing this project keeps shipping
    the other way round.

    A threshold hardcoded to 80% would satisfy the measurement above, because 80%
    is what the worked example writes. Moving the author's number and watching
    the verdict follow is what tells the two apart. At 40% the long answers clear
    the bar; at 95% even the short ones do not.
    """
    answered = _answers(doc)

    lenient = copy.deepcopy(doc)
    lenient["evals"]["metrics"][0]["threshold"] = "40%"
    generous = verdict(
        [check(c, r, [], metrics=metrics_of(lenient, EXAMPLE)) for c, r in answered],
        bar_of(doc),
    )
    assert not generous.failures, [f.why for f in generous.failures]

    strict = copy.deepcopy(doc)
    strict["evals"]["metrics"][0]["threshold"] = "95%"
    strict["evals"]["metrics"][0]["with"] = {"words": 10}
    harsh = verdict(
        [check(c, r, [], metrics=metrics_of(strict, EXAMPLE)) for c, r in answered],
        bar_of(doc),
    )
    assert len(harsh.failures) == len(answered), [f.why for f in harsh.failures]


def test_the_length_a_score_measures_against_comes_from_the_authors_own_with_line(doc) -> None:
    """`with:` is passed through unchanged and is never filled in for us.

    FR-3.1.5 forbids silently normalising a provider's settings, because a score
    whose defaults were quietly evened out is a score that no longer means what
    its documentation says. The smallest version of that rule is a ceiling nobody
    wrote: `with:` missing is an unenforced measurement with a line to type, not
    a number this file picked.
    """
    moved = copy.deepcopy(doc)
    moved["evals"]["metrics"][0]["with"] = {"words": 200}
    answered = _answers(doc)
    roomy = verdict(
        [check(c, r, [], metrics=metrics_of(moved, EXAMPLE)) for c, r in answered],
        bar_of(doc),
    )
    assert not roomy.failures, [f.why for f in roomy.failures]

    silent = copy.deepcopy(doc)
    silent["evals"]["metrics"][0].pop("with")
    outcomes = [check(c, r, [], metrics=metrics_of(silent, EXAMPLE)) for c, r in answered]
    assert all(o.passed for o in outcomes), "a ceiling nobody wrote must not fail anybody"
    said = verdict(outcomes, bar_of(doc)).unenforced
    assert len(said) == 1, said
    assert "needs to be told the length" in said[0]
    assert "fix: write `with: { words: 60 }`" in said[0]


# ──────────────────────────────── a provider this machine does not have (D17)


def test_a_provider_nothing_here_supplies_lands_on_unenforced_with_a_line_to_type(doc) -> None:
    """T7 over the fifth on-ramp: nothing may vanish.

    `ragas:` is a real provider family and one this build deliberately does not
    ship — the legacy wrappers hard-import `ragas` and HuggingFace `datasets` and
    need a LangChain embeddings object, so they belong behind a provider of their
    own. An author who writes one gets the same three-part answer a judgeless
    `judged:` rule gets: the file and line, what was not measured, and something
    to type. Never a silent skip, and never a zero — scoring an absent provider
    as a failure would blame the agent for a package nobody installed.
    """
    brought = copy.deepcopy(doc)
    brought["evals"]["metrics"] = [
        {"uri": "ragas:answer_correctness", "threshold": 0.8}
    ]
    answered = _answers(doc)
    scored = verdict(
        [check(c, r, [], metrics=metrics_of(brought, EXAMPLE)) for c, r in answered],
        bar_of(doc),
    )

    assert not scored.failures, "an absent provider must not fail anybody"
    assert scored.outcome == "PASS"
    assert len(scored.unenforced) == 1, scored.unenforced
    said = scored.unenforced[0]
    assert said.startswith("evals/suite.yaml:"), said
    assert "nothing on this machine provides `ragas:` scores" in said
    assert "fix: this build provides" in said and "`deepeval:`" in said

    # And the same sentence is available from the FILES alone, so a checker can
    # say it where the author is rather than an hour into a run.
    assert unenforced_rules(brought, EXAMPLE) == [said]


def test_a_deepeval_that_is_not_installed_is_a_reported_absence_and_never_a_network_call(
    doc, monkeypatch
) -> None:
    """D17, over the provider layer itself.

    The air-gapped case is not "DeepEval is slow", it is "DeepEval is not on this
    machine and never will be". The honest answer is a sentence with two lines to
    type — one that installs it, and one that needs nothing installed at all —
    and NOT a reach for a package index. `_deepeval_classes` answers `None` on
    every import failure for exactly this, so a missing optional dependency is an
    absence to report rather than a crash in the middle of somebody's suite.
    """
    import socket as _socket

    brought = copy.deepcopy(doc)
    brought["evals"]["metrics"] = [
        {"uri": "deepeval:faithfulness", "threshold": 0.8}
    ]
    # The answers are produced BEFORE the socket is taken away, because asyncio
    # opens a pipe to itself to make an event loop at all. What must not touch a
    # socket is the SCORING, which is what is measured below.
    answered = _answers(doc)

    monkeypatch.setattr(providers, "_deepeval_classes", lambda: None)
    # Not a promise, a property: any attempt to open a connection while a
    # provider is missing fails this test outright.
    monkeypatch.setattr(
        _socket, "socket",
        lambda *a, **k: pytest.fail("nothing here may open a socket"),
    )
    scored = verdict(
        [check(c, r, [], metrics=metrics_of(brought, EXAMPLE)) for c, r in answered],
        bar_of(doc),
    )

    assert not scored.failures
    assert len(scored.unenforced) == 1, scored.unenforced
    said = scored.unenforced[0]
    assert "needs DeepEval and it is not installed on this machine" in said
    assert "Nothing here reached for the network" in said
    assert "uv pip install deepeval" in said
    assert "pact:at_most_words" in said, "and a line that needs nothing installed"
    assert available_deepeval_metrics() == [], "absent is not the same as empty"


def test_a_deepeval_score_with_nothing_grading_the_run_is_reported_not_guessed(doc) -> None:
    """The fifth on-ramp meeting the same door the fourth leaves by.

    A `deepeval:` score reads the answer with a model, so it needs the grader the
    author named in `graded-by:` — and with none it is neither passed nor failed.
    The wording is deliberately the wording a judgeless `judged:` rule gets,
    because it is the same missing thing and an author should not have to learn
    two vocabularies for it.
    """
    brought = copy.deepcopy(doc)
    brought["evals"]["metrics"] = [{"uri": "deepeval:answer_relevancy"}]
    answered = _answers(doc)
    scored = verdict(
        [check(c, r, [], judge=None, metrics=metrics_of(brought, EXAMPLE))
         for c, r in answered],
        bar_of(doc),
    )
    assert not scored.failures
    assert len(scored.unenforced) == 1, scored.unenforced
    said = scored.unenforced[0]
    assert "nothing was grading this run" in said
    assert "fix: name a model this machine serves with `graded-by:`" in said


def test_a_deepeval_score_is_read_by_the_model_the_author_named_and_by_no_other(doc) -> None:
    """One grader for both halves of the suite (D17, AD-56).

    `providers.py` used to ship a `LocalJudge` defaulting to `qwen2.5:7b-instruct`
    at `localhost:11434` — so a metric would have been graded by a model nobody
    wrote down and no `allow-egress:` line had admitted, while the `judged:` rule
    one line above it was refused for exactly that. It is gone. The only route to
    weights is `graded-by:`, resolved through `models/catalog.yaml` and refused by
    the same egress walk.
    """
    asked: list[str] = []

    def scripted(system: str, user: str) -> str:
        asked.append(user)
        return '{"score": 1.0, "reason": "fine"}'

    graded, why = judge_of(doc, ask=scripted, workspace=EXAMPLE)
    assert graded is not None, why
    reader = graded.reading()
    assert reader.get_model_name() == "qwen2.5-14b-instruct", "the author's line"
    assert reader.generate("say something") == '{"score": 1.0, "reason": "fine"}'
    assert asked, "the grader the author named is the one that was asked"

    assert not hasattr(providers, "LocalJudge"), (
        "a second way to reach weights is a second place a hosted fallback appears"
    )


def test_a_deepeval_score_is_never_answered_by_a_hosted_model_the_author_did_not_name(
    doc, monkeypatch
) -> None:
    """The hole this item found by running the thing rather than reading it.

    `AskModel` used to duck-type DeepEval's model protocol and say so in a
    comment. DeepEval 4.x does not duck-type: `initialize_model` ends with
    `isinstance(model, DeepEvalBaseLLM)` and raises for anything else — and the
    construction here caught that and retried WITHOUT the judge, at which point
    DeepEval reached for GPT and demanded `OPENAI_API_KEY`. Measured on this
    machine before the fix: `deepeval:faithfulness`, with a perfectly good
    locally-served grader named in `graded-by:`, raised *"OpenAI API key is not
    configured"*. An air-gapped box would have found that out at suite time.

    So the guarantee is stated as a property: with no key in the environment and
    a hosted model that fails on sight, the author's own grader still takes the
    measurement.
    """
    pytest.importorskip("deepeval")
    import deepeval.metrics.utils as _utils

    class NoHostedJudge:
        """Stands where DeepEval's OpenAI model stands. Building one fails."""

        def __init__(self, *a, **k):
            pytest.fail("a hosted judge must never be built")

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(_utils, "GPTModel", NoHostedJudge)

    asked: list[str] = []

    def scripted(system: str, user: str) -> str:
        asked.append(user)
        return '{"statements": [], "verdicts": [], "score": 1.0, "reason": "fine"}'

    graded, why = judge_of(doc, ask=scripted, workspace=EXAMPLE)
    assert graded is not None, why

    taken = evaluate_metric(
        MetricSpec(uri="deepeval:answer_relevancy", threshold=0.7,
                   where="evals/suite.yaml:34"),
        "DECISION: approved. The lamp arrived cracked within 30 days.",
        asked="my lamp arrived cracked",
        judge=graded.reading(),
    )
    assert not taken.unenforced, taken.unenforced
    assert taken.deterministic is False, "a score that reads is not a deterministic one"
    assert asked, "the grader the author named is what answered"


def test_whether_a_score_reads_the_answer_is_asked_and_never_discovered_by_failure() -> None:
    """The mechanism behind the guarantee above.

    A score that takes no model must be built without one, and a score that takes
    a model must never be built without one. The version that decided this by
    catching `TypeError` and retrying answered BOTH questions the same way —
    drop the judge — and dropping the judge is what let a hosted default in. It
    is a question about the class's own signature, so it is asked of the
    signature.
    """
    pytest.importorskip("deepeval")
    from deepeval.metrics import AnswerRelevancyMetric

    assert providers._takes_a_judge(AnswerRelevancyMetric) is True

    class ComparesTwoLists:
        def __init__(self, threshold: float = 0.5) -> None:
            self.threshold = threshold

    class ForwardsWhateverItIsGiven:
        def __init__(self, threshold: float = 0.5, **rest) -> None:
            self.threshold = threshold

    assert providers._takes_a_judge(ComparesTwoLists) is False
    # `**kwargs` counts as yes: withholding the judge is the failure that costs
    # money, and handing it to something that ignores it costs nothing.
    assert providers._takes_a_judge(ForwardsWhateverItIsGiven) is True


# ─────────────────────────────────────────────── AC-4.5: order, and never


def test_a_suite_whose_scores_are_all_deterministic_asks_the_judge_nothing(doc) -> None:
    """AC-4.5's second half, extended to the fifth on-ramp.

    `pact:at_most_words` counts words. A suite whose scores are all of that kind
    must never open a socket, whatever grader happens to be available — which is
    what keeps the whole runner air-gapped by default. `MetricSpec.deterministic`
    is what makes this structural rather than a convention: `check` runs those
    scores in the pass before the judge is ever consulted.
    """
    asked: list[str] = []

    def counting(system: str, user: str) -> str:
        asked.append(user)
        return "PASS\nfine"

    graded, _ = judge_of(doc, ask=counting, workspace=EXAMPLE)
    quiet = copy.deepcopy(doc)
    quiet["evals"]["rules"] = [
        r for r in quiet["evals"]["rules"] if not (isinstance(r, dict) and "judged" in r)
    ]
    for case, result in _answers(doc):
        check(case, result, rules_of(quiet), judge=graded,
              metrics=metrics_of(quiet, EXAMPLE))
    assert asked == []
    assert all(m.deterministic for m in metrics_of(doc, EXAMPLE))


def test_a_case_a_string_rule_already_failed_is_never_measured_by_a_model(doc) -> None:
    """AC-4.5's first half. A deterministic rule decides first and returns, so an
    answer that broke `must-not-contain:` costs no model call — including the one
    a `deepeval:` score would have made."""
    taken: list[str] = []
    real = providers.evaluate_metric

    def counting(spec, actual, expected="", **k):
        taken.append(spec.uri)
        return real(spec, actual, expected, **k)

    brought = copy.deepcopy(doc)
    brought["evals"]["metrics"] = [{"uri": "deepeval:answer_relevancy"}]
    import pact_adapters.evals as evals_module

    original = evals_module.evaluate_metric
    evals_module.evaluate_metric = counting
    try:
        broke = RunResult(
            output="DECISION: approved. Your refund by Friday, and it will arrive on Monday."
        )
        outcome = check(
            Case("bad", "a customer wants a refund", {"decision": "approved"}),
            broke, rules_of(brought), judge=None,
            metrics=metrics_of(brought, EXAMPLE),
        )
    finally:
        evals_module.evaluate_metric = original

    assert outcome.passed is False and "refund by" in outcome.why
    assert taken == [], "a deterministic failure must not reach a score that reads"


# ──────────────────────────────────── the full DeepEval surface, from config


def test_every_score_deepeval_exports_is_reachable_by_typing_its_name() -> None:
    """FR-3.1.4, held as a property rather than as a number.

    The requirement was written against one release ("51 of 56"), and a test that
    pins a count goes red on an upgrade that ADDS metrics — which is the opposite
    of what it is protecting. What has to stay true is that nothing here
    enumerates the set: every metric that release exports, other than the legacy
    RAGAS wrappers, is reachable by writing its name in YAML.
    """
    if providers._deepeval_classes() is None:
        pytest.skip("DeepEval is not installed here; the absence path covers that")

    names = available_deepeval_metrics()
    assert len(names) >= 40, f"only {len(names)} scores reachable: {names}"
    assert "deepeval:faithfulness" in names
    assert "deepeval:answer_relevancy" in names
    assert not [n for n in names if "ragas" in n], "the RAGAS wrappers are excluded by design"
    for uri in names:
        assert why_unavailable(MetricSpec(uri=uri)) == "", uri


@pytest.mark.parametrize(
    "typed",
    ["deepeval:pii_leakage", "deepeval:PIILeakage", "deepeval:piileakage",
     "deepeval:g_eval", "deepeval:geval", "deepeval:GEval"],
)
def test_a_score_whose_name_is_an_acronym_is_written_the_way_its_docs_name_it(
    typed: str,
) -> None:
    """`PIILeakageMetric` snake-cased one character at a time is `p_i_i_leakage`,
    which nobody would type and which was the only spelling the old resolver
    accepted. Matching on letters and digits alone means the author writes what
    DeepEval's own page calls it."""
    if providers._deepeval_classes() is None:
        pytest.skip("DeepEval is not installed here")
    assert why_unavailable(MetricSpec(uri=typed)) == "", typed


# ─────────────────────────────────── mistakes in the file, said where they are


def test_a_score_with_no_provider_in_front_of_it_is_refused_rather_than_guessed(doc) -> None:
    """Guessing which provider was meant is how a suite comes to measure
    something nobody asked for. The colon is required and its absence names both
    spellings that would work."""
    said = why_unavailable(MetricSpec(uri="faithfulness", where="evals/suite.yaml:34"))
    assert "does not say who provides that score" in said
    assert "fix: put the provider in front of it with a colon" in said
    assert "`uri: deepeval:faithfulness`" in said


def test_a_typo_in_a_score_name_offers_the_name_it_meant() -> None:
    """A typo in `uri:` is a mistake in a file, so it reads like one — and the
    fix is a line that works rather than a list to search."""
    if providers._deepeval_classes() is None:
        pytest.skip("DeepEval is not installed here")
    said = why_unavailable(
        MetricSpec(uri="deepeval:fathfulness", where="evals/suite.yaml:34")
    )
    assert "DeepEval has no score called `fathfulness`" in said
    assert "fix: write `uri: deepeval:faithfulness`" in said


def test_a_setting_the_score_does_not_take_is_named_rather_than_ignored(doc) -> None:
    """`with:` is passed through unchanged, so a key the score has never heard of
    is a mistake in the file. It is reported with the words the provider itself
    used — quietly dropping it would leave an author certain they had configured
    something they had not."""
    if providers._deepeval_classes() is None:
        pytest.skip("DeepEval is not installed here")
    graded, why = judge_of(doc, ask=lambda s, u: "{}", workspace=EXAMPLE)
    assert graded is not None, why
    taken = evaluate_metric(
        MetricSpec(uri="deepeval:answer_relevancy", with_={"bananas": 3},
                   where="evals/suite.yaml:34"),
        "DECISION: approved.", judge=graded.reading(),
    )
    assert taken.unenforced, taken
    assert "does not take the settings written under `with:`" in taken.unenforced
    assert "fix: check the settings against DeepEval's own page" in taken.unenforced
    assert taken.passed is False and taken.score == 0.0


def test_a_score_nothing_could_take_is_counted_as_neither_a_pass_nor_a_failure() -> None:
    """Three outcomes, one construct down from `Verdict`'s three.

    A measurement nobody took has not passed the answer and has not failed it.
    Guessing pass would let a suite report green on a measure nobody applied;
    guessing fail would blame the agent for a provider that is not installed.
    """
    absent = evaluate_metric(
        MetricSpec(uri="ragas:faithfulness", where="evals/suite.yaml:34"), "anything"
    )
    assert absent.unenforced
    assert absent.passed is False and absent.score == 0.0

    outcome = check(
        Case("one", "a customer wants a refund", {}),
        RunResult(output="DECISION: approved."), [],
        metrics=[MetricSpec(uri="ragas:faithfulness", where="evals/suite.yaml:34")],
    )
    assert outcome.passed is True, "an absent provider must not fail the case"
    assert len(outcome.unenforced) == 1


# ──────────────────────────────────────────── one reader for one kind of number


@pytest.mark.parametrize(
    "written, want",
    [("80%", 0.8), (0.8, 0.8), ("0.8", 0.5), ("100%", 1.0), ("0%", 0.0),
     ("-50%", 0.5), ("150%", 0.5), (-0.5, 0.5), (None, 0.5), (True, 0.5)],
)
def test_a_share_written_either_way_means_the_same_thing_and_holds_one_range(
    written, want
) -> None:
    """`threshold:` is the second `percent` an adapter reads, after `must-pass:`.

    They go through one function, which is not tidiness: the percent branch of
    the old `bar_of` had no range check while the bare-decimal branch did, so
    `must-pass: -50%` gave `-0.5` and a six-of-six FAILING suite reported PASS
    with exit code 0. Two readers of the same kind of number are two readers that
    can come to disagree about what `80%` means.
    """
    assert share(written, 0.5) == want


def test_the_threshold_a_metric_defaults_to_is_the_one_deepeval_documents() -> None:
    """Half marks, and named once. A score held to a different bar than its own
    documentation states is a score that no longer means what it says
    (FR-3.1.5)."""
    assert providers.DEFAULT_THRESHOLD == 0.5
    assert MetricSpec.parse({"uri": "deepeval:bias"}).threshold == 0.5
    assert MetricSpec.parse("deepeval:bias").threshold == 0.5
    assert MetricSpec.parse({"uri": "deepeval:bias", "threshold": "70%"}).threshold == 0.7
