"""`chosen-by:`, read once for every runtime (96 §C).

An interface is a contract; which implementation does its work is decided for
each run. Nothing in this package read `chosen-by:`, so an agent that looked
things up in an interface was handed the interface itself — a set with no
documents — and every host worked the rule out again for itself. Found by Bud
Agent Flow, whose compiled agent looked things up in nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters.interfaces import chosen  # noqa: E402
from trees import shown  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
#: `email` is chosen by the run input `mailbox`; `shop-policies` (documents) and
#: `refund-policy` (a written procedure) are the host's to choose.
TREE = REPO / "tests" / "trees" / "a-desk-that-listens-reads-and-chooses"


def by_name(*args, **kwargs):
    return {c.interface: c for c in chosen(shown(TREE), "front-desk", *args, **kwargs)}


def test_every_interface_the_agent_uses_is_found_with_everything_that_implements_it() -> None:
    found = by_name()
    assert set(found) == {"email", "shop-policies", "refund-policy"}
    assert (found["email"].kind, found["email"].implementations) == ("tools", ("gmail", "outlook"))
    assert (found["shop-policies"].kind, found["shop-policies"].implementations) == ("knowledge", ("acme-policies",))
    assert (found["refund-policy"].kind, found["refund-policy"].implementations) == ("skills", ("acme-refund-policy",))
    assert found["email"].chosen_by == "run-inputs.mailbox"
    assert found["shop-policies"].chosen_by == "the-host", "what leaving `chosen-by:` out means"


def test_a_run_input_picks_and_the_host_picks_what_is_the_hosts() -> None:
    found = by_name({"mailbox": "outlook"}, {"shop-policies": "acme-policies", "refund-policy": "acme-refund-policy"})
    assert {n: c.picked for n, c in found.items()} == {
        "email": "outlook", "shop-policies": "acme-policies", "refund-policy": "acme-refund-policy",
    }
    assert all(c.why_not == "" for c in found.values())


def test_nothing_chosen_is_said_in_a_sentence_and_never_filled_in() -> None:
    found = by_name()
    assert all(c.picked == "" for c in found.values()), "one implementation is not a choice"
    assert "the run input `mailbox` was not given" in found["email"].why_not
    assert "`gmail` or `outlook`" in found["email"].why_not
    assert "the host picked nothing" in found["shop-policies"].why_not
    assert found["shop-policies"].why_not.startswith("knowledge: shop-policies is an interface")


def test_only_something_that_implements_it_can_be_picked_whoever_picks() -> None:
    found = by_name({"mailbox": "carrier-pigeon"}, {"shop-policies": "email"})
    assert found["email"].picked == "" and "'carrier-pigeon', which does not say `implements: email`" in found["email"].why_not
    assert found["shop-policies"].picked == "" and "the host picked 'email'" in found["shop-policies"].why_not


def test_a_host_may_bind_what_a_run_did_not_say() -> None:
    assert by_name({}, {"email": "gmail"})["email"].picked == "gmail"
    # The run's own word comes first.
    assert by_name({"mailbox": "outlook"}, {"email": "gmail"})["email"].picked == "outlook"


def test_an_agent_that_uses_no_interface_has_nothing_to_choose() -> None:
    doc = shown(REPO / "examples" / "kernel" / "finance-first")
    assert chosen(doc, "support") == ()
