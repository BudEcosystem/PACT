"""A runtime that keeps memory and at-most-once outside one process reads PACT's
own terms for both, instead of re-reading the document or re-writing a sentence.

Two gaps, both found by a runtime (budflow) that keeps its record in a store:

* `remembers:` said how long each entry lasts, when it goes, what it starts as,
  what shape it has and which sources may never write it, and `Fact` carried
  none of the five, so a runtime read them off the document a second time.
* `Ledger.hold` decided "the same call" and wrote the refusal, but only against
  a dict in this process. A record that must outlive the process (a journal) or
  be shared by every run of a workspace (`same-request-key-across:`) needs the
  key and the sentence without the dict: `RequestKeys.claim`.

And one more: `AgentSpec.facts` is one object per agent, so a runtime that
records into it shares one run's memory with every other. `Facts.fresh` is a
run's own copy, and `AgentSpec.tidier(facts=)` restates that copy.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.at_most_once import Claim, Ledger, RequestKeys  # noqa: E402
from pact_adapters.facts import Facts  # noqa: E402

REMEMBERS = {
    "agents": {
        "a": {
            "remembers": {
                "size": {
                    "description": "the shoe size",
                    "lasts": "one-turn",
                    "forget-after": "30d",
                    "starts-as": "unknown",
                    "shaped-like": {"size": "number"},
                    "never-from": ["tool output", "retrieval"],
                },
                "approved": {
                    "description": "that a person approved it",
                    "lasts": "one-conversation",
                    "survives-shortening": "yes",
                    "stops-being-true-when": ["the turn ends"],
                },
            }
        }
    }
}


def test_a_fact_carries_every_term_its_entry_wrote() -> None:
    size = Facts.from_document(REMEMBERS, "a").declared["size"]
    assert size.lasts == "one-turn"
    assert size.forget_after == "30d"
    assert size.starts_as == "unknown"
    assert size.shaped_like == {"size": "number"}
    assert size.never_from == ("tool output", "retrieval")
    approved = Facts.from_document(REMEMBERS, "a").declared["approved"]
    assert (approved.lasts, approved.forget_after, approved.shaped_like, approved.never_from) == (
        "one-conversation",
        None,
        None,
        (),
    )


def test_a_fresh_copy_holds_nothing_and_shares_nothing() -> None:
    spec_facts = Facts.from_document(REMEMBERS, "a")
    one, two = spec_facts.fresh(), spec_facts.fresh()
    one.record("approved", "cleared")
    assert one.value("approved") == "cleared"
    assert two.held == {} and spec_facts.held == {}
    assert two.declared is spec_facts.declared


def test_forgetting_on_request_is_not_going_stale() -> None:
    facts = Facts.from_document(REMEMBERS, "a").fresh()
    facts.record("approved", "cleared")
    facts.forget("approved")
    assert facts.value("approved") is None and facts.forgotten == []
    facts.record("approved", "cleared")
    assert facts.something_happened("the turn ends") == ["approved"]


REFUNDS = {
    "agents": {"a": {"uses": ["payments"]}},
    "tools": {
        "payments": {
            "actions": {
                "issue-refund": {
                    "same-request-key": "order-number",
                    "same-request-key-across": "the-workspace",
                },
                "look-up": {},
            }
        }
    },
}


def test_a_claim_is_the_key_and_the_sentences_and_spends_nothing() -> None:
    keys = RequestKeys.from_document(REFUNDS, "a")
    call = {"action": "issue-refund", "order-number": " O-9 "}
    claim = keys.claim("payments", call)
    assert claim == Claim("payments", "issue-refund", "order-number", "O-9", "the-workspace")
    assert claim.key == ("payments", "issue-refund", "O-9")
    assert keys.claim("payments", call) == claim, "pure: claiming twice spends nothing"
    assert keys.claim("payments", {"action": "look-up", "order-number": "O-9"}) is None


def test_the_ledger_says_what_the_claim_says() -> None:
    keys = RequestKeys.from_document(REFUNDS, "a")
    call = {"action": "issue-refund", "order-number": "O-9"}
    ledger = Ledger(keys)
    assert ledger.hold("payments", call) == ""
    refused = ledger.hold("payments", call)
    assert refused == keys.claim("payments", call).refusal()  # type: ignore[union-attr]
    assert "somewhere in this workspace" in refused


def test_a_call_without_its_key_cannot_be_claimed_and_says_so() -> None:
    keys = RequestKeys.from_document(REFUNDS, "a")
    claim = keys.claim("payments", {"action": "issue-refund"})
    assert claim is not None and claim.value is None
    ledger = Ledger(keys)
    assert ledger.hold("payments", {"action": "issue-refund"}) == ""
    assert ledger.unenforced() == (claim.cannot_tell(),)
