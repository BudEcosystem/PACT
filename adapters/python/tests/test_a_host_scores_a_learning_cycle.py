"""A learning cycle a host scores with its own runner, measured from a kept baseline.

Three things the gate needed from outside and could not get:

* **Scoring.** `Learner._score` ran PACT's harness on a transport, synchronously,
  so a host that compiles the same spec to its own framework (budflow, WP9) could
  reuse none of the gate without scoring a different agent from the one it runs.
  `cycle(..., score=)` takes the host's runner; every gate stays in PACT.
* **The baseline.** `Baseline` existed and nothing kept one, so every cycle run
  from the files had `baseline=None`, `_drift` answered 0.0, and `drift.at-most:`
  could never be reached. `Baselines` keeps it in the workspace.
* **`learning.models:`** was typed and read by nobody; `learning_models` /
  `model_for` read it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.evals import Case, CaseOutcome  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.learning import (  # noqa: E402
    Baselines,
    Learner,
    Proposal,
    Scoring,
    learning_models,
    model_for,
)

BAD = "Answer the customer."
GOOD = "Answer the customer. State the outcome as one word at the start, then the figure."
HOLDOUT = [Case("h1", "kettle", {"decision": "approved"}, split="held-out"),
           Case("h2", "lamp", {"decision": "approved"}, split="held-out")]


def learner(**kw) -> Learner:
    spec = AgentSpec(name="Desk", description="d", instructions=BAD)
    return Learner(spec=spec, train=[], holdout=HOLDOUT, rules=[], bar=0.5, tools={}, **kw)


def scorer(seen: list[str]):
    def score(spec: AgentSpec, cases: list[Case]) -> Scoring:
        seen.append(spec.instructions)
        ok = "one word" in spec.instructions
        return Scoring([CaseOutcome(c.key, ok, "" if ok else "vague") for c in cases], spent=0.5, priced=True)

    return score


def test_a_cycle_is_scored_by_the_hosts_runner_and_every_gate_still_decides() -> None:
    seen: list[str] = []
    one = learner()
    outcome = one.cycle(Proposal("instructions", BAD, GOOD), score=scorer(seen))
    assert outcome.applied, outcome.reason
    assert seen == [BAD, GOOD], "the incumbent, then the candidate, each on the held-out split"
    assert (outcome.before_score, outcome.after_score) == (0.0, 1.0)
    assert one.evals_spent == 4 and one.money_spent == 1.0 and one.priced is True


def test_a_cycle_given_nothing_to_score_with_refuses() -> None:
    with pytest.raises(TypeError, match="neither"):
        learner().cycle(Proposal("instructions", BAD, GOOD))


def test_the_baseline_a_person_approved_is_kept_and_the_drift_gate_measures_from_it(
    tmp_path: Path,
) -> None:
    kept = Baselines.at(tmp_path)
    assert kept.of("desk") is None
    first = kept.keep("desk", "Say hello.")
    again = kept.keep("desk", BAD, 0.5)
    assert (first.generation, again.generation) == (0, 1)
    assert Baselines.at(tmp_path).of("desk").instructions == BAD
    assert Baselines.at(tmp_path).of("other") is None

    far = Baselines.at(tmp_path).keep("desk", "Something else entirely, said at length.")
    one = learner(baseline=far, max_cumulative_drift=0.1)
    outcome = one.cycle(Proposal("instructions", BAD, GOOD), score=scorer([]))
    assert not outcome.applied and "drift" in outcome.reason and outcome.drift > 0.1


def test_from_document_reads_the_baseline_the_workspace_kept(tmp_path: Path) -> None:
    Baselines.at(tmp_path).keep("desk", "Kept wording.")
    spec = AgentSpec(name="Desk", description="d", instructions=BAD, key="desk", workspace=str(tmp_path))
    built = Learner.from_document({}, spec, {}, cases=HOLDOUT)
    assert built.baseline is not None and built.baseline.instructions == "Kept wording."


def test_the_learning_models_are_read_in_the_order_written() -> None:
    doc = {"learning": {"models": {"execution": {"role": "llm"},
                                   "reflection": {"role": "reflector", "model": "qwen2.5-14b"}}}}
    assert [(m.name, m.role, m.model) for m in learning_models(doc)] == [
        ("execution", "llm", ""), ("reflection", "reflector", "qwen2.5-14b")]
    assert model_for(doc, "reflector").model == "qwen2.5-14b"
    assert model_for(doc, "judge") is None and learning_models({}) == ()


def test_the_record_is_read_from_where_it_is_written_when_the_derived_area_moves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`$PACT_DERIVED_DIR` moved the writes and not the reads, so a cycle on a read-only tree
    never saw its own baseline, spend or refusals."""
    from pact_adapters.learning import MonthlySpend, Refusals

    monkeypatch.setenv("PACT_DERIVED_DIR", str(tmp_path / "elsewhere"))
    tree = tmp_path / "tree"
    Baselines.at(tree).keep("desk", "Kept wording.")
    MonthlySpend.at(tree).add(1.5, 3)
    Refusals.at(tree).add(Proposal("instructions", BAD, GOOD), "it did not help")
    assert Baselines.at(tree).of("desk").instructions == "Kept wording."
    assert (MonthlySpend.at(tree).money, MonthlySpend.at(tree).runs) == (1.5, 3)
    assert Refusals.at(tree).why(Proposal("instructions", BAD, GOOD)) is not None
    assert not (tree / ".pact").exists()


def test_held_for_a_person_is_its_own_answer_not_a_refusal() -> None:
    from pact_adapters.learning import Permissions

    widening = Proposal("uses", "- zendesk", "- zendesk\n- payments")
    held = learner().cycle(widening, score=scorer([]))
    assert held.held and not held.applied
    proposes = learner(permissions=Permissions(enabled="propose-only"))
    assert proposes.cycle(Proposal("instructions", BAD, GOOD), score=scorer([])).held
    worse = learner().cycle(Proposal("instructions", BAD, BAD + " Be brief."), score=scorer([]))
    assert not worse.held and not worse.applied and "did not improve" in worse.reason
