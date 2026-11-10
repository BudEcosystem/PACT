"""Law 8 (docs/98 WP-15): what a run proposes is held to the checker the
author's own tree is held to, before it takes effect."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters.checking import check_instructions  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.learning import Learner, Proposal  # noqa: E402
from trees import shown  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
DESK = REPO / "examples" / "refund-desk"
PHASES = REPO / "examples" / "kernel" / "phases"

BROKEN = "Answer the customer, who is {{run-inputs.nobody-declared-this}}."


def test_a_sound_change_to_a_tree_that_carries_files_passes() -> None:
    doc = shown(DESK)
    assert check_instructions(doc, "refund-desk", "Decide the refund. Be brief.", source=DESK) == []


def test_a_change_that_breaks_a_rule_is_refused_in_the_checkers_own_words() -> None:
    doc = shown(DESK)
    refused = check_instructions(doc, "refund-desk", BROKEN, source=DESK)
    assert refused and any("nobody-declared-this" in r for r in refused), refused


def test_a_document_with_no_files_is_checked_through_the_document_itself() -> None:
    doc = shown(PHASES)
    assert check_instructions(doc, "builder", "Carry out the plan, in order.") == []
    assert check_instructions(doc, "builder", BROKEN), "no source tree needed to refuse it"


def test_a_learning_cycle_refuses_a_proposal_the_checker_refuses_before_scoring_it() -> None:
    doc = shown(DESK)
    spec = AgentSpec.from_document(doc, "refund-desk", source=DESK)
    learner = Learner.from_document(doc, spec, tools={})
    scored: list[str] = []

    def transport_for(s):  # a scoring run would reach here; it must not
        scored.append(s.instructions)
        raise AssertionError("scored a proposal the checker refuses")

    out = learner.cycle(Proposal("instructions", spec.instructions, BROKEN), transport_for)
    assert not out.applied
    assert "does not pass `pact check`" in out.reason, out.reason
    assert scored == []
