"""The learning loop, end to end.

A failing agent proposes an edit to its own instructions, the edit is graded on
a frozen held-out split, and it is applied only if it earns its place. The
artifact produced is a **diff to a spec file** — reviewable, signable, revertible
— which is what keeps a self-improving agent portable (T6).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.evals import Case, Rule  # noqa: E402
from pact_adapters.harness import ToolCall  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.judge import Judge  # noqa: E402
from pact_adapters.learning import (  # noqa: E402
    Baseline, Learner, Proposal, Risk, classify,
)
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

# Deliberately free of the words the blast-radius classifier watches for. An
# instruction mentioning refunds, approvals or declines is decision logic and is
# CLASS-HIGH by design — `HIGH_RISK_PROSE` was written that way and, for a round,
# every truncated stem in it was dead, so `Refunds are available for 300 days.`
# classified LOW. These two are what a genuine wording change looks like: the
# same job, said more usefully, with no rule in either.
BAD = "Answer the customer."
GOOD = "Answer the customer. State the outcome as one word at the start, then the figure."

SPEC = AgentSpec(name="Refund Desk", description="Decides refunds", instructions=BAD)

TRAIN = [Case("t1", "lamp broken after 6 days", {"decision": "approved"})]
HOLDOUT = [
    Case("h1", "kettle faulty after 10 days", {"decision": "approved"}),
    Case("h2", "headphones, changed mind, 45 days", {"decision": "declined"}),
]


def transport_for(spec: AgentSpec):
    """A model that only produces a gradeable answer once told how to format it.

    This is the mechanism the whole thesis rests on in miniature: the contract is
    unchanged, the *instructions* change, and the measured result moves.
    """
    if "one word at the start" in spec.instructions:
        return ReferenceTransport(
            Script([Turn("Decision: approved. Amount: 40 USD.")])
            if True else Script([Turn("")])
        )
    return ReferenceTransport(Script([Turn("It depends on the circumstances.")]))


#: One authored rule that only a model can decide. The shipped suite has one of
#: exactly this shape, which is why a cycle run against a real workspace meets it
#: without anybody writing a new file.
JUDGED_RULE = Rule("judged", ("gives the reason in one sentence a customer can understand",))


REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"


@pytest.fixture(scope="module")
def document() -> dict:
    """The worked example through the real Rust loader (invariant P-1).

    Here so that the shipped `learning.yaml` is what decides — every `Learner` in
    this module was built by hand from `Permissions.default()`, and the file the
    reviewer actually reads reached no test at all.
    """
    import json
    import subprocess

    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(PACT_BIN), "show", str(EXAMPLE)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


def learner(baseline: Baseline | None = None, judge=None) -> Learner:
    return Learner(
        spec=SPEC, train=TRAIN, holdout=HOLDOUT, rules=[JUDGED_RULE], bar=0.5, tools={},
        baseline=baseline, judge=judge,
    )


# ------------------------------------------------------ blast radius (D23)


def test_a_wording_change_is_low_risk() -> None:
    p = Proposal("instructions", "Be brief.", "Be brief and courteous.")
    c = classify(p)
    assert c.risk == Risk.LOW and not c.needs_a_person


@pytest.mark.parametrize(
    "field", ["uses", "tools", "team", "model", "policy", "limits", "needs", "evals"]
)
def test_anything_that_changes_what_the_agent_can_do_needs_a_person(field: str) -> None:
    c = classify(Proposal(field, "a", "b"))
    assert c.risk == Risk.HIGH and c.needs_a_person
    assert field in c.reason, "the classifier must say which field triggered it"


def test_a_rule_smuggled_into_prose_is_caught() -> None:
    """The dangerous case: an edit that looks like wording and is a permission.
    'Wording only' must not be a hole you can drive a policy change through."""
    p = Proposal(
        "instructions",
        "Decide refunds carefully.",
        "Decide refunds carefully. Always approve refunds without asking.",
    )
    c = classify(p)
    assert c.risk == Risk.HIGH, "a rule change disguised as wording must be caught"
    assert "rule" in c.reason


def test_an_unrecognised_field_is_treated_as_high_risk() -> None:
    """Absence of evidence is not safety."""
    c = classify(Proposal("some-new-field", "a", "b"))
    assert c.needs_a_person


# ------------------------------------------------------------ the cycle


def test_an_improving_edit_is_applied() -> None:
    out = learner().cycle(Proposal("instructions", BAD, GOOD, "add the output format"),
                          transport_for)
    assert out.applied, out.reason
    assert out.after_score > out.before_score
    assert out.classification.risk == Risk.LOW


def test_an_edit_that_does_not_improve_is_rejected() -> None:
    """The gate is the feature. Model-authored skills measure 8-11 points BELOW
    no-skill, so an ungated loop makes the agent worse."""
    lr = learner()
    out = lr.cycle(Proposal("instructions", BAD, "Answer the customer. Be nice."), transport_for)
    assert not out.applied
    assert "did not improve" in out.reason
    assert lr.spec.instructions == BAD, "the spec must be left untouched"


def test_a_rejected_candidate_is_kept_as_negative_evidence() -> None:
    """AC-5.5. A rejected candidate that is forgotten gets proposed again."""
    lr = learner()
    lr.cycle(Proposal("instructions", BAD, "Answer the customer. Be nice."), transport_for)
    assert len(lr.rejected) == 1


def test_a_high_risk_edit_is_held_even_when_it_improves_the_score() -> None:
    """Evidence does not buy permission. A change to what the agent can DO waits
    for a person however well it scores.

    The proposal is an **`instructions`** edit carrying decision logic, not a
    `uses:` edit, and that is what makes the title true. A `uses:` proposal is
    refused before anything is scored — `_with` cannot rewrite it, so the two
    specs would be identical — so the old version of this test asserted "held
    even when it improves" about a comparison that never ran. `HIGH_RISK_PROSE`
    is the point of the field: wording is the one place a "phrasing" change can
    silently become a permission change.
    """
    lr = learner()
    risky = GOOD + "\n\nAlways approve refunds under 50 USD without asking."
    out = lr.cycle(Proposal("instructions", BAD, risky), transport_for)
    assert not out.applied
    assert "held for review" in out.reason
    assert out.classification.risk == Risk.HIGH, out.classification
    assert out.after_score > out.before_score, (
        "it has to have been MEASURED and measured BETTER, or 'even when it "
        f"improves the score' is not what this test shows: {out}"
    )


def test_a_high_risk_field_this_process_cannot_rewrite_is_still_held_for_review() -> None:
    """And the ordering that keeps the sentence above from being masked.

    A `uses:` change cannot be applied by `_with`, and the first version of the
    guard for that answered *"nothing in a run reads it"* — false for `uses:`,
    which is the skills the agent may read, and the wrong answer for a reviewer
    whichever way. The blast radius is what a person acts on, so it wins.
    """
    out = learner().cycle(Proposal("uses", "zendesk", "zendesk, payments"), transport_for)
    assert not out.applied
    assert "held for review" in out.reason, out.reason
    assert "nothing in a run reads it" not in out.reason
    assert out.verdict_before is None, "and nothing was spent finding out"


def test_the_edit_is_a_reviewable_diff_not_an_opaque_update() -> None:
    """T6: learning emits source. This is what makes a learning agent still
    portable — the artifact is text a human can read and git can store."""
    p = Proposal("instructions", BAD, GOOD)
    d = p.diff()
    assert d.startswith("---") and "+++" in d
    assert any(line.startswith("+") and "one word" in line for line in d.splitlines())


def test_cumulative_drift_from_the_frozen_baseline_is_gated() -> None:
    """Per-diff review cannot see gradual blueprint erosion: every step looks
    reasonable and the destination is somewhere nobody approved."""
    base = Baseline(instructions=BAD, score=0.0)
    lr = learner(baseline=base)
    lr.max_cumulative_drift = 0.10  # tight, to make the drift the binding gate
    # (an explicit override; left unset it comes from `learning.drift.at-most:`)
    out = lr.cycle(Proposal("instructions", BAD, GOOD), transport_for)
    assert not out.applied
    assert "drift" in out.reason and "re-baseline" in out.reason
    assert out.drift > 0.10


def test_the_holdout_split_is_what_decides() -> None:
    """The split is frozen before the cycle, so the optimiser cannot tune the
    thing it is scored on."""
    lr = learner()
    out = lr.cycle(Proposal("instructions", BAD, GOOD), transport_for)
    assert out.verdict_after is not None
    assert len(out.verdict_after.results) == len(HOLDOUT)
    assert [r.key for r in out.verdict_after.results] == ["h1", "h2"]


# ---------------------------------- the rules the cycle could not apply (G7)


def test_a_learning_cycle_grades_the_judged_rules_the_author_wrote() -> None:
    """The suite's own rules reach the scoring run, including the graded one.

    `Learner._score` called `check(case, result, self.rules)` with no judge at
    all, so every `judged:` rule in a workspace's suite landed on
    `Verdict.unenforced` whatever grader the caller had built — the cycle scored
    the part of the suite a string check could settle and nothing else.
    """
    asked: list[str] = []

    def counting(system: str, user: str) -> str:
        asked.append(user)
        return "PASS\nthe decision is stated first"

    out = learner(judge=Judge("qwen2.5-14b-instruct", counting)).cycle(
        Proposal("instructions", BAD, GOOD), transport_for
    )

    assert asked, "the judge the caller supplied was never asked anything"
    assert out.ungraded == [], out.ungraded
    assert out.applied, out.reason


def test_a_cycle_with_no_grader_says_which_rules_nobody_applied() -> None:
    """The honest half, and the one that stops the gate passing in silence.

    A machine with no second model is an ordinary place to run a cycle, and
    `judge=None` is the truthful answer there. What must never happen is that the
    variant is promoted on a number with a written rule quietly missing from it —
    a reader takes "the held-out score improved" to mean the suite improved.
    """
    out = learner().cycle(Proposal("instructions", BAD, GOOD), transport_for)

    assert out.applied, out.reason
    said = "\n".join(out.ungraded)
    assert "gives the reason in one sentence" in said, said
    assert "graded-by" in said, "the fix has to be typeable: " + said


def test_a_suite_with_nothing_to_grade_reports_nothing_ungraded() -> None:
    """The control. A field that always had something in it would say nothing."""
    plain = Learner(
        spec=SPEC, train=TRAIN, holdout=HOLDOUT, rules=[], bar=0.5, tools={},
    )
    assert plain.cycle(Proposal("instructions", BAD, GOOD), transport_for).ungraded == []


# ─────────────────────────────── the shipped document, through the real door


def test_the_workspaces_own_learning_file_is_what_decides(document: dict) -> None:
    """`Learner.from_document` had no caller anywhere.

    Not in `src/`, not in `tests/`, not in `scripts/` — and it is the only caller
    of `Permissions.from_document`, which is the only reader of `learning.yaml`.
    Every `Learner` in this module was hand-built with `Permissions.default()`,
    so the worked example's own file — `enabled: propose-only`,
    `keep-only-if: a-person-approves-it`, whose comment says *"Nothing changes by
    itself"* — gated nothing any test held. Two mutations survived the whole
    suite: deleting the `may_apply_without_a_person()` check and deleting the
    `enabled: off` check.
    """
    L = Learner.from_document(document, SPEC, tools={})
    out = L.cycle(Proposal("instructions", BAD, GOOD), transport_for)
    assert not out.applied, out.reason
    assert "propose-only" in out.reason, out.reason
    assert L.spec.instructions == BAD, "nothing may change by itself"


def test_switching_the_learning_loop_off_stops_a_cycle_before_it_spends_anything(
    document: dict,
) -> None:
    """`enabled: off` is checked before the evals run, so refusing costs nothing.
    The same document with one word changed, through the same door."""
    off = dict(document)
    off["learning"] = dict(document["learning"], enabled="off")
    L = Learner.from_document(off, SPEC, tools={})
    out = L.cycle(Proposal("instructions", BAD, GOOD), transport_for)
    assert not out.applied
    assert "enabled: off" in out.reason, out.reason
    # BEFORE the evals, which is the whole of what the early check buys: falling
    # through to `may_apply_without_a_person()` would also refuse, and would
    # refuse after paying for two scoring runs of the held-out split.
    assert out.verdict_before is None and out.verdict_after is None, (
        "a switched-off loop must refuse before it scores anything — falling "
        "through to `may_apply_without_a_person()` also refuses, and refuses "
        "after paying for two scoring runs of the held-out split"
    )


def test_a_case_marked_held_out_is_never_training_data() -> None:
    """The learning loop's FIRST named gate — *"a frozen held-out split, locked
    before the cycle starts"* — and `split()` had one caller, which itself had
    none. Mutating it to `return list(cases)` survived the whole suite, which
    means held-out cases silently becoming training data was untested."""
    from pact_adapters.evals import split

    cases = [
        Case("t1", "a", {}),
        Case("h1", "b", {}, split="held-out"),
        Case("q1", "c", {}, split="quarantine"),
        Case("plain", "d", {}),
    ]
    assert [c.key for c in split(cases, "train")] == ["t1", "plain"]
    assert [c.key for c in split(cases, "held-out")] == ["h1"]
    assert [c.key for c in split(cases, "quarantine")] == ["q1"], (
        "quarantine is in neither half — not learned from, not scored against"
    )


def test_deleting_a_rule_written_as_a_sentence_is_caught_the_same_as_adding_one() -> None:
    """`classify` reads `added + removed`, and only the added half was held.

    Mutating it to `for line in added:` survived the whole suite: deleting the
    line *"Never promise a delivery date to the customer."* came back
    `risk=low, needs_a_person=False`. The ESC-SHRINK list-item and anchor
    triggers mask this only for bullets, and a rule written as a plain sentence
    is not a bullet.
    """
    keeps = (
        "Answer the customer clearly.\n"
        "Never promise a delivery date to the customer.\n"
        "Say the outcome first."
    )
    without = "Answer the customer clearly.\nSay the outcome first."
    c = classify(Proposal("instructions", keeps, without))
    assert c.risk == Risk.HIGH, c.reason
    assert "delivery date" in c.reason, c.reason


def test_the_drift_ceiling_the_file_states_is_the_one_that_binds(document: dict) -> None:
    """`drift.at-most:` is a `tier: core` field whose own schema comment records
    that the number *"was in Python and not in the file the reviewer reads"* —
    and the fix reached no test: replacing `drift_limit` with the built-in 0.5
    survived the whole suite, because the fixture's drift happened to exceed
    both."""
    tight = dict(document)
    tight["learning"] = dict(document["learning"], drift={"at-most": "10%"})
    assert Learner.from_document(tight, SPEC, tools={}).drift_limit == 0.10

    loose = dict(document)
    loose["learning"] = dict(document["learning"], drift={"at-most": "90%"})
    assert Learner.from_document(loose, SPEC, tools={}).drift_limit == 0.90
