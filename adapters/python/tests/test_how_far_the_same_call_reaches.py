"""`same-request-key-across:` — a scope on the line above it (A5, B13).

`same-request-key:` already names the argument that makes two calls one call.
What it never said is how far "the same call" reaches, and the refusal was
hardcoded to *"already ran in this run"* whatever the author wrote.

On a workspace scope that sentence is false in the direction that matters. The
call was made by ANOTHER run, and telling somebody it was this one sends them
looking through the wrong transcript for a payment that is not in it.

**B13.** This field is also the whole of what a contended `claim` on a shared
board can say: a key plus a scope wider than one run IS mutual exclusion. What a
claim additionally needs — releasing it, seeing who holds it, expiring it — is a
lease, and `Ledger` has no release and no introspection, so that stays deferred
with a fixture rather than invented here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.at_most_once import Ledger, RequestKeys  # noqa: E402

REPO = Path(__file__).resolve().parents[3]


def ledger_for(scope: str | None) -> Ledger:
    action: dict = {"same-request-key": "order-number"}
    if scope:
        action["same-request-key-across"] = scope
    return Ledger(
        RequestKeys.from_document(
            {
                "agents": {"a": {"uses": ["payments"]}},
                "tools": {"payments": {"actions": {"issue-refund": action}}},
            },
            "a",
        )
    )


def refused_twice(scope: str | None) -> str:
    led = ledger_for(scope)
    call = {"action": "issue-refund", "order-number": "O-9"}
    assert led.hold("payments", call) == "", "the first call goes through"
    return led.hold("payments", call)


@pytest.mark.parametrize(
    "scope,phrase",
    [
        (None, "in this run"),
        ("this-run", "in this run"),
        ("the-team", "somewhere in this team"),
        ("the-workspace", "somewhere in this workspace"),
    ],
)
def test_the_refusal_says_which_scope_it_is_speaking_about(scope, phrase) -> None:
    said = refused_twice(scope)
    assert phrase in said, said
    assert "withheld rather than done a second time" in said


def test_a_wider_scope_never_claims_the_call_was_made_by_this_run() -> None:
    """The precise defect. A person reading `already ran in this run` for a call
    another run made goes looking in the wrong place, and concludes the record
    is wrong rather than that the guarantee worked."""
    said = refused_twice("the-workspace")
    assert "in this run" not in said, said


def test_the_scope_is_read_off_the_authored_document() -> None:
    keys = RequestKeys.from_document(
        {
            "agents": {"a": {"uses": ["payments"]}},
            "tools": {
                "payments": {
                    "actions": {
                        "issue-refund": {
                            "same-request-key": "order-number",
                            "same-request-key-across": "the-team",
                        }
                    }
                }
            },
        },
        "a",
    )
    assert keys.scopes[("payments", "issue-refund")] == "the-team"


def test_the_scope_needs_the_key_it_scopes() -> None:
    """A scope with nothing to scope is a line that means nothing —
    `needs-also:` says so at check time."""
    schema = yaml.safe_load((REPO / "spec/schema.yaml").read_text())["groups"]
    field = schema["action"]["fields"]["same-request-key-across"]
    assert field["needs-also"] == ["same-request-key"]
    assert field["choices"] == ["this-run", "the-team", "the-workspace"]


def test_the_scope_does_not_claim_a_companion_a_field_cannot_hold() -> None:
    """`needed-when:` holds one field of a document against another field of the
    SAME group. `durability:` is a field of the WORKSPACE and this is a field of
    an ACTION, so a `needed-when:` here can never fire in either direction —
    measured, and the reason this attribute is deliberately absent."""
    schema = yaml.safe_load((REPO / "spec/schema.yaml").read_text())["groups"]
    field = schema["action"]["fields"]["same-request-key-across"]
    assert "needed-when" not in field, (
        "an attribute that cannot fire is R24's defect wearing schema meta"
    )
    assert "durability" in schema["workspace"]["fields"], (
        "the workspace is where the store is declared"
    )


# ───────────────────────────────── A3: a gate that compares something else

from pact_adapters.questions import _atom_holds, _atom_stops  # noqa: E402


def test_a_gate_can_stop_on_a_value_that_is_not_a_number() -> None:
    """`more-than:` compares a magnitude, and a customer tier has none — so an
    approval gate could ask about money and about nothing else. `arg:` even
    carried `needs-also: [more-than]`, which refused the correct rule outright."""
    atom = {"tool": "crm/write", "arg": "tier", "is": "enterprise"}
    assert _atom_stops(atom, {"action": "write", "tier": "enterprise"}, as_action="write")
    assert not _atom_stops(atom, {"action": "write", "tier": "small"}, as_action="write")


def test_the_comparison_is_folded_because_a_model_wrote_the_value() -> None:
    atom = {"tool": "crm/write", "arg": "tier", "is": "enterprise"}
    assert _atom_stops(atom, {"action": "write", "tier": "Enterprise"}, as_action="write")


def test_several_values_are_one_rule_and_not_three_files() -> None:
    atom = {"tool": "crm/write", "arg": "tier", "is-one-of": ["enterprise", "government"]}
    for tier in ("enterprise", "government"):
        assert _atom_stops(atom, {"action": "write", "tier": tier}, as_action="write"), tier
    assert not _atom_stops(atom, {"action": "write", "tier": "small"}, as_action="write")


def test_a_call_carrying_none_of_the_value_is_not_the_call_the_rule_is_about() -> None:
    """The same reading `more-than:` takes when its argument is absent."""
    atom = {"tool": "crm/write", "arg": "tier", "is": "enterprise"}
    assert not _atom_stops(atom, {"action": "write"}, as_action="write")


def test_both_halves_of_the_gate_read_equality_the_same_way() -> None:
    """`_atom_holds` chooses the wording a person reads and `_atom_stops`
    decides whether the call is withheld. Two readings of one rule is how a
    person gets asked about a call that was never stopped."""
    atom = {"tool": "crm/write", "arg": "tier", "is": "enterprise"}
    for args, want in [
        ({"action": "write", "tier": "enterprise"}, True),
        ({"action": "write", "tier": "small"}, False),
    ]:
        assert _atom_holds(atom, args) is want, args
        assert _atom_stops(atom, args, as_action="write") is want, args
