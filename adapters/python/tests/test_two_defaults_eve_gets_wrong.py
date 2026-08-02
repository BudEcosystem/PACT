"""Two things Eve does that PACT must keep not doing (Phase H).

Neither is a gap in PACT. Both are places where the obvious "reach parity with
Eve" move would import a defect, so each is pinned by a test — the point of
writing them down is that a future round reading `50-NOT-COPIED.md` should find
the divergence already held by something that fails, not by a paragraph.

**1. Approval fails open in Eve.** `docs/tools/human-in-the-loop.md`: *"By
default, omitted `approval` behaves like `never()`, so tool calls may execute
without human approval."* A tool is unguarded unless the author remembers to
guard it, and the thing an author forgets is by definition the thing they did
not think about.

**2. A thrown hook kills the run in Eve.** `docs/guides/hooks.md`: *"A thrown
handler propagates through the emit composer and surfaces as `turn.failed`. If a
hook subscribed to a failure-cascade event also throws, it escalates to
`session.failed`."* An audit logger can end the session it was only meant to
observe. PACT's answer is structural rather than defensive: a `watch` is
declarative, so there is no author code in it to throw.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

REPO = Path(__file__).resolve().parents[3]
SCHEMA = yaml.safe_load((REPO / "spec" / "schema.yaml").read_text())["groups"]


# ─────────────────────────────────────────── 1. approval may not fail open


def test_a_policy_says_who_it_applies_to_and_the_answer_can_be_every_agent() -> None:
    """The field that stops an approval rule covering one agent by accident.

    Eve has no equivalent: approval is a property of a tool, so an agent that
    reaches the same tool by another route is simply not covered, and nothing
    says so."""
    applies = SCHEMA["policy"]["fields"]["applies-to"]
    assert "every-agent" in applies["choices"]
    # The property that matters is CLASS-4 — a change here needs a person —
    # not one particular spelling of it. §9118 lists S-CAP, S-EXEC, S-GOV and
    # S-META as the governed surfaces, and `applies-to` sits with
    # `interceptor.may`, `port.who-can-reach-it` and `state.never-from`, which
    # is the right company for "who does this gate cover".
    assert applies["surface"] in {"S-CAP", "S-EXEC", "S-GOV", "S-META"}, (
        "narrowing who an approval gate covers must never be auto-appliable"
    )


def test_the_worked_examples_gate_covers_every_agent_and_not_just_the_one() -> None:
    """The example is the thing people copy, so it is the thing that has to be
    right. It covered one of three agents for a round — `fraud-checker` reached
    `zendesk/reply`, the very action the policy names, ungated."""
    p = yaml.safe_load((REPO / "examples/refund-desk/policies/approvals.yaml").read_text())
    assert p.get("applies-to") == "every-agent", (
        "an approval policy scoped to one agent leaves the others reaching the "
        "same tools with no gate at all"
    )


def test_the_schema_never_offers_a_choice_that_means_ask_nobody() -> None:
    """Eve's `never()` is a documented default. Here it must not even be a
    spelling, because a default that means "no gate" is the one an author picks
    by not typing anything."""
    for rule in SCHEMA["policy"]["fields"].values():
        for choice in rule.get("choices") or []:
            assert choice not in {"never", "none", "no-approval"}, (
                f"`{choice}` is Eve's fail-open default wearing PACT's clothes"
            )


# ─────────────────────────────────── 2. watching may not be able to kill a run


def test_a_watch_is_declarative_so_there_is_no_author_code_in_it_to_throw() -> None:
    """The structural answer to Eve's thrown-hook cascade.

    PACT's protection is not a try/except around author code; it is that a
    `watch` has nowhere to put author code. This test fails the moment somebody
    adds an escape hatch, which is the round where the cascade becomes possible
    again."""
    watch = SCHEMA["watch"]["fields"]
    for name, field in watch.items():
        assert field.get("type") not in {"code", "module", "callable"}, (
            f"`watch.{name}` can carry executable author code, so a watch can now "
            f"throw — which is exactly how an audit logger ends a session in Eve"
        )
    assert "runs" not in watch and "execute" not in watch and "handler" not in watch


def test_watching_cannot_name_a_script_the_way_a_skill_can() -> None:
    """A skill legitimately carries `scripts/` — files it points at, carried
    verbatim. A watch must not, because a watch fires inside the run."""
    watch = SCHEMA["watch"]["fields"]
    assert "scripts" not in watch and "assets" not in watch


def test_the_powers_a_rule_may_take_are_a_closed_list_with_no_general_escape() -> None:
    """`interceptor.may` is the one place PACT lets a rule change what happens.
    It is closed, and every member is a named effect rather than a way in."""
    may = SCHEMA["interceptor"]["fields"]["may"]
    assert may["type"] == "list of one-of"
    for choice in may["choices"]:
        assert choice in {"hide-values", "stop-the-run", "send-elsewhere"}, (
            f"`{choice}` is a new power; if it can run author code the cascade is back"
        )


@pytest.mark.parametrize("kind", ["watch", "interceptor"])
def test_neither_reactive_kind_can_be_given_a_module_to_import(kind: str) -> None:
    """R5 and R42 refuse a spec that names code to run. Held here per kind
    rather than once, so adding a third reactive kind does not inherit the
    exemption by being new."""
    for name, field in SCHEMA[kind]["fields"].items():
        help_text = str(field.get("help", "")).lower()
        assert ".py" not in help_text and ".ts" not in help_text, (
            f"`{kind}.{name}` tells the author to name a file of code: {help_text[:90]}"
        )
