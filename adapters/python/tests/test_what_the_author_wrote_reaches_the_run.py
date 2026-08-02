"""Authored lines that loaded, validated, and reached nothing.

Every guarantee here is one that `pact check` already accepted and that no run
carried out. They are grouped in one module because they are one failure wearing
five faces: a document that passes the checker and changes nothing about the run
is worse than a document the checker refuses, because the author has been told
their rule is holding.

The five:

* a **skill** — its whole kind was inert, so the agent whose only declared
  capability is a written policy was sent its own five-line instructions and
  nothing else, and the run reported nothing;
* a **`bind:`** — validated by `pact check` in both halves, executed by neither
  port, so *"whose order"* went on being nobody's;
* the **exactly-once ledger** — right for one step and kept for the whole run,
  so a later call to the same tool was answered from an earlier step's result
  and the transcript recorded a call that never happened;
* **`may-improve-on-its-own:`** — parsed, stored, and used only to fall through,
  which is what happens when the line is absent too;
* the **`variants:`** block — the authoring surface for model portability, read
  by nothing, while the only strategies in the tree were Python lambdas in a
  test file.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from consenting import allowing_the_connection  # noqa: E402
from pact_adapters.harness import ToolCall, _system_for, run  # noqa: E402
from pact_adapters.ir import AgentSpec, SkillSpec, ToolSpec  # noqa: E402
from pact_adapters.learning import (  # noqa: E402
    APPLIES_ITSELF, Permissions, Proposal, Risk, classify,
)
from pact_adapters.resolve import strategies_of  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    """The worked example through the real Rust loader (invariant P-1)."""
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(PACT_BIN), "show", str(EXAMPLE)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


# ───────────────────────────────────────────────────── a written procedure


def test_the_written_procedure_an_agent_uses_reaches_the_model(document: dict) -> None:
    """The one that produced silence.

    `policy-checker`'s only capability is `uses: [refund-policy]` and its own
    instructions say *"quote the exact part of the policy that decides it"*. It
    was sent its five-line `instructions.md` and nothing else: no rule from
    `SKILL.md` reached any model in either port, and `RunResult.unenforced` was
    empty, so the run said nothing was wrong. Two of its own eval cases grade
    rules that exist nowhere but that file.
    """
    spec = AgentSpec.from_document(document, "policy-checker")
    assert spec.skill_names == ("refund-policy",)

    said = _system_for(
        spec.instructions, spec.loop.phase(spec.loop.starts_at), spec.skills
    )
    for rule in ("Refunds are available", "gift card", "Personalised"):
        assert rule in said, f"the policy's own words are missing: {rule!r}"
    assert spec.instructions in said, "the agent's own instructions still come first"


def test_a_stage_that_names_no_procedure_still_reads_every_one_the_agent_has(
    document: dict,
) -> None:
    """The one asymmetry between narrowing tools and narrowing procedures.

    Withholding a tool from a `think` stage is the point — it is what makes it
    think instead of reaching for the first thing it recognises. Withholding the
    written procedure from the same stage would make it think without the rules
    it was told to follow, which is the opposite.
    """
    spec = AgentSpec.from_document(document, "refund-desk")
    thinking = next(
        p for p in spec.loop.steps.values() if p.may_use is None and p.does.value != "use-tools"
    )
    assert thinking.skills_offered(spec.skill_names) == spec.skill_names
    assert thinking.tools_offered(tuple(t.name for t in spec.tools)) == ()


def test_a_stage_narrowed_to_one_procedure_reads_that_one_and_no_tools(
    document: dict,
) -> None:
    """Naming a skill on `may-use:` adds a document to read, never a power.

    The example's checking stage says *"Check the decision you just made against
    the refund policy, rule by rule"* — which it could not do, because the
    policy reached no model. Its `may-use:` now names the skill and `zendesk`
    and not `payments`: it may re-read the ticket and read the policy, and it
    cannot issue a refund while it doubts one.
    """
    spec = AgentSpec.from_document(document, "refund-desk")
    checking = next(
        p for p in spec.loop.steps.values() if p.does.value == "check-its-work"
    )
    assert "refund-policy" in (checking.may_use or ()), (
        "the example's checking stage is supposed to narrow to the policy"
    )
    assert checking.skills_offered(spec.skill_names) == ("refund-policy",)
    offered = checking.tools_offered(tuple(t.name for t in spec.tools))
    assert offered == ("zendesk",), offered
    assert "payments" not in offered, "a stage that doubts a refund cannot issue one"


def test_a_procedure_with_no_procedure_in_it_is_named_on_the_result() -> None:
    """A signpost the author believes is a rulebook.

    The routing lines still reach the model, so this is not a failure to deliver
    — it is the author having written a description and no body. Named rather
    than dropped, which is the door every other unenforced thing uses.
    """
    spec = AgentSpec(
        name="a", description="d", instructions="i",
        skills=(SkillSpec(name="refund-policy", description="The policy."),),
    )
    out = asyncio.run(run(spec, ReferenceTransport(Script([Turn("done")])), "hello"))
    assert any("refund-policy" in u and "no body" in u for u in out.unenforced), out.unenforced


# ─────────────────────────────────────────────────── the surrounding system


def test_an_argument_the_surrounding_system_supplies_reaches_the_tool(
    document: dict,
) -> None:
    """`bind:` — checked at check time in both halves, carried out by neither.

    Measured before this: the payments tool received
    `{order-number, amount, action}` and never `customer-id`, so the identity of
    whoever the run was for never reached the call and nothing said so.
    """
    spec = AgentSpec.from_document(document, "refund-desk")
    seen: list[dict[str, Any]] = []

    def fresh():
        return ReferenceTransport(Script([
            Turn(
                "Looking it up.",
                [ToolCall("payments", {"action": "look-up-order", "order-number": "O-9"})],
            ),
            Turn("Done."),
        ]))

    out = allowing_the_connection(
        spec, fresh, "refund O-9",
        {"payments": lambda a: seen.append(dict(a)) or "ok"},
        run_inputs={"customer-id": "C-9"},
    )
    assert seen and seen[0].get("customer-id") == "C-9", seen
    assert not [u for u in out.unenforced if u.startswith("bind:")], out.unenforced
    # And the model never saw the name: it is not in what the tool was offered.
    payments = next(t for t in spec.tools if t.name == "payments")
    assert "customer-id" not in payments.parameters


def test_a_bind_nothing_supplies_is_named_rather_than_filled_with_nothing(
    document: dict,
) -> None:
    """An empty string in place of a customer id is worse than a run that says
    out loud that the identity never arrived."""
    spec = AgentSpec.from_document(document, "refund-desk")
    out = asyncio.run(run(spec, ReferenceTransport(Script([Turn("hi")])), "hello"))
    said = [u for u in out.unenforced if u.startswith("bind:")]
    assert said, out.unenforced
    assert all("customer-id" in u and "run-inputs.customer-id" in u for u in said), said


# ──────────────────────────────────────────────────── the exactly-once ledger


def test_a_later_step_calling_the_same_tool_really_calls_it_again() -> None:
    """The ledger is the ledger for one STEP.

    Kept for the whole run, a later step's call was answered from the earlier
    step's cached result: measured on the worked example, step 1 asked for ticket
    `T-999` and the trace recorded `results: ['TICKET T-1: broken lamp']` with
    the tool never invoked — another ticket's contents served as the answer, and
    a call claimed in the transcript that never happened.
    """
    asked: list[str] = []
    spec = AgentSpec(
        name="a", description="d", instructions="i", max_steps=4,
        tools=(ToolSpec(name="zendesk", description="Reads a ticket."),),
    )
    script = Script([
        Turn("one", [ToolCall("zendesk", {"ticket-id": "T-1"})]),
        Turn("two", [ToolCall("zendesk", {"ticket-id": "T-999"})]),
        Turn("done"),
    ])
    out = asyncio.run(
        run(
            spec,
            ReferenceTransport(script),
            "hello",
            {"zendesk": lambda a: asked.append(str(a.get("ticket-id"))) or f"TICKET {a['ticket-id']}"},
        )
    )
    assert asked == ["T-1", "T-999"], asked
    assert out.steps[1].tool_results == ("TICKET T-999",), out.steps[1].tool_results


# ─────────────────────────────────────────────────────── what may change itself


def _permissions(**block: Any) -> Permissions:
    return Permissions.from_document({"learning": block})


def test_a_field_the_author_did_not_list_as_safe_needs_a_person() -> None:
    """`may-improve-on-its-own:` NARROWS, and it narrowed nothing.

    `Permissions.of` returned `None` for a field not on the list — which is
    exactly what it returns when there is no list at all — so writing the line
    was indistinguishable from omitting it. Measured with
    `{enabled: yes, auto-apply: yes, may-improve-on-its-own: [], keep-only-if:
    scores-higher-on-evals}` — the two-field spelling of the self-applying
    state, before `auto-apply:` was deleted: an instructions edit came back
    `risk=low needs_a_person=False` and a cycle applied it with no person.
    """
    listed = _permissions(
        enabled=APPLIES_ITSELF, **{"may-improve-on-its-own": ["examples"]}
    )
    safe = classify(Proposal("description", "Answers.", "Answers politely."), listed)
    assert safe.risk == Risk.LOW, safe.reason

    for field in ("instructions", "content", "use-when"):
        held = classify(Proposal(field, "Be brief.", "Be brief and clear."), listed)
        assert held.risk == Risk.HIGH, (field, held.reason)
        assert "may-improve-on-its-own" in held.reason, held.reason


def test_an_empty_list_grants_nothing_rather_than_everything() -> None:
    """The spelling the schema's own help says must not grant everything."""
    none_of_it = _permissions(
        enabled=APPLIES_ITSELF, **{"may-improve-on-its-own": []}
    )
    held = classify(Proposal("instructions", "Be brief.", "Be brief and clear."), none_of_it)
    assert held.risk == Risk.HIGH and held.needs_a_person, held.reason


def test_no_list_at_all_keeps_the_built_in_lists() -> None:
    """A workspace that said nothing is not a workspace that said `[]`."""
    silent = _permissions(enabled=APPLIES_ITSELF)
    wording = classify(Proposal("instructions", "Be brief.", "Be brief and clear."), silent)
    assert wording.risk == Risk.LOW, wording.reason
    assert classify(Proposal("tools", "a", "b"), silent).risk == Risk.HIGH


def test_a_spend_cap_on_self_improvement_this_process_cannot_measure_is_named() -> None:
    """`cycle-limits.per-month` is a `tier: core`, S-GOV ceiling on a
    self-modifying system, and it reached no code and no report at all. Nothing
    here sees a month; naming it is what stops a reviewer reading an unenforced
    cap as an enforced one."""
    p = _permissions(
        enabled="propose-only",
        **{"cycle-limits": {"per-cycle": 4, "per-month": "20 USD", "evals": 2000}},
    )
    assert p.per_cycle == 4 and p.evals_at_most == 2000 and p.per_month == "20 USD"


# ────────────────────────────────────────────────── other ways to run it


def test_the_search_for_a_model_that_works_comes_from_the_authors_own_file(
    document: dict,
) -> None:
    """Model portability is the headline claim, and its authoring surface was a
    Python lambda in a test file — including the `decomposed` strategy README.md
    quotes a measured result for. D14 rules that out for any capability in the
    core, and `variants:` is the line that was supposed to say it.
    """
    spec = AgentSpec.from_document(document, "refund-desk")
    assert [name for name, _ in spec.variants] == ["decomposed"]

    ways = strategies_of(spec)
    assert list(ways) == ["authored", "decomposed"], (
        "the agent as authored is always tried first — MASS finds prompt changes "
        "dominate topology changes"
    )
    assert ways["authored"](spec) is spec

    other = ways["decomposed"](spec)
    assert other.max_steps == 6, "`steps-at-most:` is the author's number"
    assert other.instructions.startswith(spec.instructions), (
        "`says:` adds a line, it does not replace the instructions"
    )
    assert "look the order up" in other.instructions


# ─────────────────────────────────── G9: what the run knows outlives the messages


def test_a_fact_the_author_marked_survivable_reaches_the_tidier_from_the_document(
    document: dict,
) -> None:
    """`remembers:` with `survives-shortening:` reaches a run with nothing passed.

    This is the test that did not exist when G9 shipped. The mechanism was built,
    mutation-tested and green — and `ir.py` never read `remembers:`, `harness.py`
    never mentioned `Facts`, and every test constructed one in Python. So the
    tidier accepted facts, restated them correctly, and was never given any.

    It asserts the *chain*, not the behaviour: document → `AgentSpec.facts` →
    `AgentSpec.tidier`. Deleting any link fails it.
    """
    spec = AgentSpec.from_document(document, "refund-desk")
    assert "payments-was-approved" in spec.facts.declared, (
        "the worked example declares a fact that survives shortening; "
        "`Facts.from_document` should have read it"
    )

    tidier = spec.tidier(4000, None)
    assert tidier is not None, "the example has a context policy, so there is a tidier"
    assert tidier.facts is spec.facts, (
        "the tidier must carry the spec's facts. When it did not, a shortening "
        "silently destroyed the evidence a `policy:` reads — and the check that "
        "read it afterwards passed on nothing, which is worse than failing."
    )


def test_the_fact_is_only_read_because_the_author_asked_for_it(document: dict) -> None:
    """The control arm. `remembers:` entries that say nothing about shortening are
    ordinary session memory and none of this mechanism's business — so a
    workspace that never asked for it cannot be changed by it."""
    spec = AgentSpec.from_document(document, "refund-desk")
    agent = (document.get("agents") or {})["refund-desk"]
    written = set((agent.get("remembers") or {}).keys())

    assert "what-the-customer-told-us" in written, "the example should still have one"
    assert "what-the-customer-told-us" not in spec.facts.declared, (
        "an entry with no `survives-shortening:` must not be picked up"
    )
    assert len(spec.facts.declared) < len(written)


# ───────────────────────────────── A2: the measured model choice has a door


def test_the_command_offers_a_way_to_choose_a_model_and_not_only_to_name_one() -> None:
    """`resolve()` — filter on `needs:`, run the cases, refuse and recommend —
    worked for several rounds with no caller but a test. So "PACT picks the
    model" was a capability of the test suite, and the README showed a report no
    shipped command produced.

    Asserted at the seam rather than by running models: the flag exists, the
    parser accepts it, and `_choose` is what calls `resolve`. Whether the
    resolution is *correct* is `test_model_portability.py`'s job and is already
    held there.
    """
    from pact_adapters import scoring

    assert "--choose-model" in scoring.FLAGS
    assert "--choose-model" in scoring.USAGE, "an option nobody is told about is not one"

    path, options, trouble = scoring._parse(["somewhere", "--choose-model"])
    assert trouble is None, trouble
    assert path == "somewhere", "the flag must not swallow the folder"
    assert options.get("--choose-model") == "yes"

    src = Path(scoring.__file__).read_text()
    assert "def _choose(" in src and "resolve(" in src.split("def _choose(")[1], (
        "`_choose` is the door; if it stops calling `resolve` the capability is "
        "unreachable again and only the reachability test would notice"
    )


def test_the_flag_refuses_a_value_rather_than_eating_the_folder() -> None:
    """`--choose-model` takes nothing. Were it in OPTIONS instead of FLAGS it
    would consume the next token, which for this command is the path — scoring
    a folder nobody asked for and reporting a number about the wrong agent."""
    from pact_adapters import scoring

    path, options, trouble = scoring._parse(["--choose-model", "examples/refund-desk"])
    assert trouble is None, trouble
    assert path == "examples/refund-desk"


# ───────────────────────────── A3: the learning gate has a door and a holdout


def test_the_learning_gate_has_a_door_a_person_can_reach() -> None:
    """980 lines — held-out split, blast-radius classifier, monthly spend cap,
    drift against a frozen baseline — and **no importer in `src/`** at all.

    Every gate in it was a capability of the test suite. `--propose FIELD=FILE`
    is the door; asserted at the seam, because whether the gate DECIDES correctly
    is what the tests below and `test_the_learning_loop_holds_the_line.py` are
    for.
    """
    from pact_adapters import scoring

    assert "--propose" in scoring.OPTIONS
    assert "--propose" in scoring.USAGE, "an option nobody is told about is not one"

    src = Path(scoring.__file__).read_text()
    door = src.split("def propose(")[1]
    assert "Learner.from_document(" in door and ".cycle(" in door, (
        "`propose` is the only importer of the learning module; if it stops "
        "calling the cycle, every gate in `learning.py` is unreachable again"
    )


def test_a_proposal_the_cycle_cannot_apply_is_refused_before_it_spends_anything(
    document: dict,
) -> None:
    """`_with` rewrote `instructions` and silently returned the incumbent for
    anything else, so a `description` proposal scored two IDENTICAL specs at full
    price and reported *"held-out score did not improve"* — a true sentence about
    a comparison with no candidate in it.

    Refused now with the reason, and refused *before* any transport is built:
    the callable handed in raises if it is ever called.

    The description is **replaced with a bland one** first. The example's own
    reads *"Decides whether a customer's refund request should be approved"*,
    which trips `HIGH_RISK_PROSE` on `refund` and `approv` and takes the
    blast-radius branch — a correct answer to a different question, and it would
    have made this test green while the branch it names went unexercised.
    """
    from dataclasses import replace as _replace

    from pact_adapters.learning import CAN_BE_APPLIED, Learner

    spec = _replace(
        AgentSpec.from_document(document, "refund-desk", source=EXAMPLE),
        description="Handles customer messages about orders.",
    )
    learner = Learner.from_document(document, spec, {})

    def never(_spec: Any) -> Any:
        raise AssertionError("a refused proposal must not reach a model")

    outcome = learner.cycle(
        Proposal("description", spec.description, "Handles customer questions."), never
    )
    assert not outcome.applied
    assert "a change to `description` cannot be put into effect" in outcome.reason
    assert "rewrites instructions" in outcome.reason, "it must say what it CAN apply"
    assert outcome.verdict_before is None, "nothing may have been scored"
    assert "description" not in CAN_BE_APPLIED
    assert outcome.classification.risk != "high", (
        "`description` is `examples:` in the author's own "
        "`may-improve-on-its-own:`, so this must be the mechanical refusal and "
        "not the blast-radius one — otherwise it is testing the other branch"
    )


def test_the_authors_held_out_split_reaches_the_learning_gate(document: dict) -> None:
    """`split: held-out` in a case file → `Case.split` → `Learner.holdout`.

    The whole authored path, and it was inert twice over: the suite declared no
    split at all, and nothing built a `Learner` from a document. With no holdout
    both scoring runs grade zero cases, and the cycle's answer was *"held-out
    score did not improve (0% → 0%)"* — which reads as a measured tie.
    """
    from pact_adapters.learning import Learner

    spec = AgentSpec.from_document(document, "refund-desk", source=EXAMPLE)
    learner = Learner.from_document(document, spec, {})

    assert learner.holdout, (
        "the worked example must hold something out, or the one gate that "
        "decides whether an improvement IS one is inert on the only tree here"
    )
    assert learner.train, "and it must still have cases to learn from"
    held = {c.key for c in learner.holdout}
    assert held.isdisjoint({c.key for c in learner.train}), (
        "a case cannot be both, or the gate scores what the proposal was "
        "written from"
    )


def test_a_suite_that_holds_nothing_out_is_told_so_rather_than_scored(
    document: dict,
) -> None:
    """The refusal that replaced `0% → 0%`. Built by emptying the holdout, so
    this asserts the branch and not the example's own splits."""
    from dataclasses import replace as _replace

    from pact_adapters.learning import Learner

    spec = AgentSpec.from_document(document, "refund-desk", source=EXAMPLE)
    learner = _replace(Learner.from_document(document, spec, {}), holdout=[])

    def never(_spec: Any) -> Any:
        raise AssertionError("a suite with no holdout must not spend a model call")

    outcome = learner.cycle(
        Proposal("instructions", spec.instructions, spec.instructions + "\n\nBe brief."),
        never,
    )
    assert not outcome.applied
    assert "nothing is held out" in outcome.reason
    assert "split: held-out" in outcome.reason, "it must say what to type"


def test_the_authors_propose_only_line_holds_a_wording_change_for_a_person(
    document: dict, tmp_path: Path,
) -> None:
    """`enabled: propose-only` and `keep-only-if: a-person-approves-it`, read off
    the example's own `learning.yaml` and reaching a real cycle.

    A `ReferenceTransport` rather than a served model, so the gate is what is
    under test and not whether this machine has weights. The assertion is that
    nothing was applied and that the reason names the author's own setting —
    `Learner.cycle` once rewrote an agent's instructions with `applied=True` in a
    workspace whose file said every improvement comes to review.

    **The workspace is a COPY**, and that is not tidiness. A cycle records what
    it spent in `<workspace>/.pact/learning/spend.jsonl`, so pointing this at the
    shipped tree wrote a real ledger into `examples/refund-desk/` — which
    `test_a_months_spend_on_improving_is_held.py` then `copytree`s into its own
    fixture. Twenty-eight recorded runs at `money: 0.0` diluted `per_run` to
    zero, the monthly forecast could never cross `20 USD`, and five passing tests
    of the spend ceiling went red. A test that writes into the tree other tests
    read is a shared mutable fixture wearing a constant's clothes.
    """
    import shutil

    from pact_adapters.learning import Learner
    from pact_adapters.script import Script, Turn
    from pact_adapters.transports.mock import ReferenceTransport

    root = tmp_path / "refund-desk"
    shutil.copytree(EXAMPLE, root)
    spec = AgentSpec.from_document(document, "refund-desk", source=root)
    learner = Learner.from_document(document, spec, {})

    outcome = learner.cycle(
        Proposal("instructions", spec.instructions, spec.instructions + "\n\nBe brief."),
        lambda _spec: ReferenceTransport(
            Script([Turn("approved — 40 USD, the item arrived damaged")] * 40)
        ),
    )
    assert not outcome.applied, "propose-only must not apply anything"
    assert "held for review" in outcome.reason, outcome.reason
    assert spec.instructions == learner.spec.instructions, (
        "and the spec it holds must be unchanged"
    )
    assert outcome.verdict_before is not None, (
        "it must have been MEASURED and then held, not refused before scoring — "
        "otherwise this passes for the wrong reason"
    )


# ───────────────────── A4: the latency promise is assessed, or refused honestly


def test_the_authors_latency_promise_is_assessed_rather_than_ignored(
    document: dict,
) -> None:
    """`finishes-within: 30s` is in the shipped example and `Slo.assess` — which
    exists precisely to refuse a percentile a small suite cannot support — had no
    caller at all. So a scored suite made no latency claim in either direction,
    and `slo.py`'s own header described a mechanism nothing invoked.

    Asserted on `assess` directly with the real `Slo`, plus the seam that reaches
    it, because producing twenty real latency samples means twenty model calls.
    """
    from pact_adapters import scoring

    spec = AgentSpec.from_document(document, "refund-desk", source=EXAMPLE)
    assert spec.slo.finishes_within_s == 30.0, "the example's own promise"

    # Too few samples: a refusal, not a number.
    said = spec.slo.assess([0.4] * 6, "e2e")
    assert said.startswith("UNDECIDED") and "need 20" in said, said

    # Enough samples, comfortably inside: a verdict.
    assert spec.slo.assess([0.4] * 20, "e2e").startswith("PASS")
    # Enough samples, over the promise: the other verdict.
    assert spec.slo.assess([45.0] * 20, "e2e").startswith("FAIL")

    src = Path(scoring.__file__).read_text()
    assert "spec.slo.assess(latencies" in src, (
        "`score` is the only caller; without it `Slo.assess` is unreachable and "
        "the example's `finishes-within:` is decoration again"
    )


def test_a_suite_too_small_to_support_a_percentile_says_so_instead_of_a_number(
) -> None:
    """The rendered line. `UNDECIDED (6 samples, need 20 for p95)` becomes
    *"no claim"* rather than a figure — the same treatment an eval bar over too
    few cases already gets, because it is the same mistake."""
    from pact_adapters.scoring import Scored, _latency_line

    assert _latency_line(Scored(latency="UNGOVERNED")) == "", (
        "an author who promised nothing must not be told about it"
    )
    said = _latency_line(Scored(latency="UNDECIDED (6 samples, need 20 for p95)"))
    assert "no claim" in said and "need 20 for p95" in said, said
    assert "PASS" not in said and "FAIL" not in said
    assert "p95=0.40s" in _latency_line(Scored(latency="PASS (p95=0.40s vs 30.00s)"))


# ───────────── A5: the declared answer shape, and the better checking model


def test_the_shape_the_author_declared_reaches_the_model(document: dict) -> None:
    """`answers-with:` is `tier: core`, sits in the worked example, is emitted by
    `pact show` — and was read by nothing in either port.

    The consequence was in plain sight and read as normal: every scripted answer
    in the eval suite hand-writes `"Decision: approved. Amount: 40 USD."`, because
    the shape the document already specified never reached a model and a person
    had to supply the format twice.
    """
    from pact_adapters.harness import CHOSEN_ANSWER_MODE, _system_for

    spec = AgentSpec.from_document(document, "refund-desk", source=EXAMPLE)
    assert spec.answers_with == {
        "decision": "one of approved, declined",
        "reason": "text",
        "amount": "money",
    }, spec.answers_with
    assert spec.answers_with_mode == "", "the example leaves the mode out"

    said = _system_for(
        spec.instructions,
        spec.loop.phase(spec.loop.starts_at),
        spec.skills,
        answers_with=spec.answers_with,
    )
    assert "What your answer must contain" in said
    for name, says in spec.answers_with.items():
        assert f"- {name}: {says}" in said, f"{name} is missing from the system text"
    # The author's own words, not a rewrite. `one of approved, declined` is
    # already the clearest statement of that constraint.
    assert "one of approved, declined" in said
    assert CHOSEN_ANSWER_MODE == "prompted", (
        "the mode PACT picks has to be the one every target can honour"
    )


def test_a_mode_no_transport_can_deliver_is_reported_not_silently_downgraded(
    document: dict,
) -> None:
    """`native-json-schema` constrains the answer at the provider, and nothing
    here does that. Serving prose and calling it done is the silent degradation
    T7 forbids, so it lands on `unenforced` with the line to type instead."""
    from dataclasses import replace as _replace

    spec = _replace(
        AgentSpec.from_document(document, "refund-desk", source=EXAMPLE),
        answers_with_mode="native-json-schema",
    )
    out = asyncio.run(run(spec, ReferenceTransport(Script([Turn("ok")] * 8)), "hello"))
    said = [u for u in out.unenforced if u.startswith("answers-with-mode:")]
    assert said, f"nothing reported the unhonoured mode: {out.unenforced}"
    assert "prompted" in said[0], "and it must name the mode that does work"


def test_a_better_model_for_checking_is_used_for_the_checking_stages(
    document: dict,
) -> None:
    """`model-for-checking:` validated, held itself against `loop:`, and had zero
    readers in any runtime — so "think with a cheaper model, check with a better
    one" was a sentence in the schema and nothing else.

    Two transports, and the assertion is that the checking stage's system text
    arrived at the second one and the doing stages did not.
    """
    from dataclasses import replace as _replace

    from pact_adapters.loops import Does

    spec = _replace(
        AgentSpec.from_document(document, "refund-desk", source=EXAMPLE),
        model_for_checking="a-better-model",
    )
    assert any(p.does is Does.CHECK for p in spec.loop.steps.values()), (
        "this test needs the example's checking stage"
    )

    doing = ReferenceTransport(Script([Turn("ok")] * 8))
    checking = ReferenceTransport(Script([Turn("looks right")] * 8))
    asked: dict[str, int] = {"doing": 0, "checking": 0}
    for name, t in (("doing", doing), ("checking", checking)):
        original = t.model_call

        def counted(*a: Any, _n: str = name, _f: Any = original, **k: Any) -> Any:
            asked[_n] += 1
            return _f(*a, **k)

        t.model_call = counted  # type: ignore[method-assign]

    asyncio.run(
        run(spec, doing, "refund O-9", checking_transport=checking)
    )
    assert asked["checking"] > 0, (
        "the checking stage never reached the second model, so "
        "`model-for-checking:` is decoration again"
    )
    assert asked["doing"] > 0, "and the doing stages must still use the first"


def test_asking_for_a_better_checking_model_nobody_serves_is_reported(
    document: dict,
) -> None:
    """The other half. A host that supplies no second transport must not leave
    the author believing their checking is being done better."""
    from dataclasses import replace as _replace

    spec = _replace(
        AgentSpec.from_document(document, "refund-desk", source=EXAMPLE),
        model_for_checking="a-better-model",
    )
    out = asyncio.run(run(spec, ReferenceTransport(Script([Turn("ok")] * 8)), "hello"))
    said = [u for u in out.unenforced if u.startswith("model-for-checking:")]
    assert said, f"nothing reported the missing second model: {out.unenforced}"
    assert "a-better-model" in said[0]


# ─────────────── A5b: the three settings that reached no transport at all


def test_the_settings_the_register_called_unreachable_reach_the_wire() -> None:
    """`settings.tool-choice`, `settings.presence-penalty` and
    `settings.frequency-penalty` were *"writable and reach no transport"*.

    The reason is the one a reader would least guess: the only transport that
    implemented `apply_settings` was the Anthropic one, and that provider has no
    penalties at all — so it was never that nothing mapped them, it was that the
    one thing mapping anything could not have. The locally-served transport, which
    is the one an air-gapped install runs, implemented none of it.
    """
    from pact_adapters.transports.ollama_transport import _WIRE, OllamaTransport

    for authored in ("tool-choice", "presence-penalty", "frequency-penalty"):
        assert authored in _WIRE, f"{authored} still reaches nothing"

    t = OllamaTransport("qwen2.5-7b-instruct", base_url="http://localhost:1/v1")
    left = t.apply_settings({
        "temperature": 0.2, "presence-penalty": 0.5, "frequency-penalty": 0.1,
        "tool-choice": "required", "thinking": "high",
    })
    # `thinking:` is NOT silently accepted. This endpoint has no such parameter,
    # and saying so is what puts it on `RunResult.unmetered`.
    assert left == ("thinking",), left

    # And the REQUEST, not just the mapping table. The first version of this test
    # asserted only the two things above, and severing the settings from the
    # payload left it green — a seam checked instead of an effect, which is the
    # same defect this file exists for, one layer down.
    payload = t.payload_for("be brief", [{"role": "user", "content": "hello"}], [])
    assert payload["presence_penalty"] == 0.5, payload
    assert payload["frequency_penalty"] == 0.1, payload
    assert payload["tool_choice"] == "required", payload
    # An authored value beats the constructor's default, because a file is more
    # specific than a host's fallback.
    assert payload["temperature"] == 0.2, payload
    assert "thinking" not in payload, "a key this endpoint cannot take must not be sent"


def test_one_authored_word_becomes_each_providers_own_shape() -> None:
    """"Translate or nothing." `tool-choice: required` is one word an author
    writes once, and the two providers spell it differently — Anthropic says
    `any`, the OpenAI-compatible endpoint says `required`. One mapping table per
    transport is what the `settings` group's header promises and what makes the
    group closeable at all.

    The case that matters is a tool NAME. Passed through as a bare string the
    OpenAI-compatible endpoint accepts it and it means nothing — a setting in a
    shape the provider ignores is worse than one reported unhonoured, because
    nothing says it did not happen.
    """
    from pact_adapters.transports.anthropic_transport import (
        _translated as anthropic_shape,
    )
    from pact_adapters.transports.ollama_transport import _translated as openai_shape

    assert openai_shape("tool-choice", "required") == "required"
    assert openai_shape("tool-choice", "auto") == "auto"
    assert openai_shape("tool-choice", "payments") == {
        "type": "function", "function": {"name": "payments"},
    }
    assert anthropic_shape("tool-choice", "required") == {"type": "any"}
    assert anthropic_shape("tool-choice", "auto") == {"type": "auto"}
    assert anthropic_shape("tool-choice", "payments") == {
        "type": "tool", "name": "payments",
    }
    # And nothing else is touched, in either.
    assert openai_shape("temperature", 0.2) == 0.2
    assert anthropic_shape("temperature", 0.2) == 0.2


# ────────────── AC-4.4: a failing run becomes an eval case, in one command


def test_a_promoted_case_carries_what_the_rules_allowed_not_what_was_typed(
    document: dict, tmp_path: Path,
) -> None:
    """The security half of AC-4.4, and the bug the first version shipped.

    `as_record` took `asked: str` from the caller, and the obvious thing to pass
    is the question as typed — so promoting a run on THIS example, whose author
    wrote `redact-card-numbers`, put `4111 1111 1111 1111` into a YAML file
    destined for version control. Measured, not reasoned about: the digits were
    in the file.

    `RunResult.asked` is now set by the harness from the message after the
    interceptor chain ran, and `as_record()` takes no argument — so there is no
    parameter left for a caller to get wrong. That is the only version of this
    property that stays true.
    """
    from pact_adapters.evals import case_from_a_run

    spec = AgentSpec.from_document(document, "refund-desk", source=EXAMPLE)
    card = "refund card 4111 1111 1111 1111 please"
    out = asyncio.run(
        run(spec, ReferenceTransport(Script([Turn("Approved.")] * 8)), card)
    )

    assert "4111" not in out.asked, out.asked
    assert "card number removed" in out.asked, out.asked
    record = out.as_record()
    assert "4111" not in json.dumps(record), record

    case = case_from_a_run(record, "a-card-number-leaked")
    assert "4111" not in json.dumps(case), case
    assert case["when"] == out.asked


def test_a_promoted_case_leaves_the_right_answer_for_a_person(document: dict) -> None:
    """`expect:` is empty on purpose. The answer the run gave is the WRONG one —
    that is why it is being promoted — and writing it into `expect:` would make
    the bug the specification."""
    from pact_adapters.evals import case_from_a_run, what_went_wrong

    spec = AgentSpec.from_document(document, "refund-desk", source=EXAMPLE)
    out = asyncio.run(
        run(spec, ReferenceTransport(Script([Turn("Approved.")] * 8)), "a question")
    )
    case = case_from_a_run(out.as_record(), "went-wrong")
    assert case["expect"] == {}, case
    assert case["because"], "a promoted case must say why it is there"

    # And what actually happened is COMMENT text, not a field. The first version
    # put a `went-wrong:` block in the case body, which `pact check` refused as
    # an unknown field — so the file was rejected for the invented key rather
    # than for the empty `expect:` it exists to make somebody fill in.
    said = "\n".join(what_went_wrong(out.as_record()))
    assert "Approved." in said
    assert "went-wrong" not in case


def test_the_promotion_has_a_door_and_it_names_the_case() -> None:
    """One command, which is the whole of AC-4.4: something went wrong, somebody
    is looking at it now, and the alternative is retyping the situation from
    memory tomorrow."""
    from pact_adapters import scoring

    assert "--from-trace" in scoring.OPTIONS
    assert "--called" in scoring.OPTIONS
    assert "--from-trace" in scoring.USAGE, "an option nobody is told about is not one"

    src = Path(scoring.__file__).read_text()
    door = src.split("def promote(")[1]
    assert "case_from_a_run(" in door, (
        "`promote` is the only caller; without it the promotion is unreachable"
    )


def test_a_case_that_asserts_nothing_is_refused(document: dict, tmp_path: Path) -> None:
    """The rule that makes the empty `expect:` mean something.

    `expect:` is `type: anything` in the schema, so `expect: {}` loaded cleanly —
    and a suite carrying a promoted case reported one more case than it could
    grade. `must-also:` counts as an assertion: a case whose whole point is *"it
    must call `look-up-order` before `issue-refund`"* is complete without an
    `expect:`.
    """
    import shutil

    root = tmp_path / "refund-desk"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns(".pact"))
    (root / "evals" / "cases" / "asserts-nothing.yaml").write_text(
        "when: something happened\nexpect: {}\n"
    )
    out = subprocess.run(
        [str(PACT_BIN), "check", str(root)], capture_output=True, text=True
    )
    assert out.returncode != 0, out.stdout
    assert "evals/case-asserts-nothing" in out.stdout, out.stdout
    assert "asserts-nothing" in out.stdout, out.stdout

    # A rule instead of an expectation is enough.
    (root / "evals" / "cases" / "asserts-nothing.yaml").write_text(
        "when: something happened\n"
        "expect: {}\n"
        "must-also:\n"
        "  - must-contain: [\"declined\"]\n"
        "    because: the customer needs a clear answer\n"
    )
    out = subprocess.run(
        [str(PACT_BIN), "check", str(root)], capture_output=True, text=True
    )
    assert out.returncode == 0, out.stdout + out.stderr
