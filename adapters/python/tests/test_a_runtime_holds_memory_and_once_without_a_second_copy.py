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
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters.at_most_once import Claim, Ledger, RequestKeys  # noqa: E402
from pact_adapters.facts import Facts  # noqa: E402
from trees import pact, shown, write  # noqa: E402

REMEMBERS = {
    "agents": {
        "a": {
            "remembers": {
                "size": {
                    "description": "the shoe size",
                    "lasts": "one-turn",
                    "kept-for": "30d",
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
    assert size.kept_for == "30d"
    assert size.starts_as == "unknown"
    assert size.shaped_like == {"size": "number"}
    assert size.never_from == ("tool output", "retrieval")
    approved = Facts.from_document(REMEMBERS, "a").declared["approved"]
    assert (approved.lasts, approved.kept_for, approved.shaped_like, approved.never_from) == (
        "one-conversation",
        None,
        None,
        (),
    )


def test_the_old_name_forget_after_is_read_as_kept_for_for_one_release() -> None:
    """`forget-after:` was renamed `kept-for:` (02W §1.3). `pact check` warns on
    the old name (`loader/forget-after-is-now-kept-for`) and a run still keeps
    the value for the time it says, so a tree written before the rename keeps
    what it promised."""
    old = {"agents": {"a": {"remembers": {"size": {"description": "d", "lasts": "forever", "forget-after": "1d"}}}}}
    assert Facts.from_document(old, "a").declared["size"].kept_for == "1d"


def test_a_source_written_without_a_dash_is_one_source_and_not_its_letters(tmp_path: Path) -> None:
    """`never-from: tool output` is the spelling the schema's own help uses, and
    `pact check` accepts it. Read by iterating, it became `('t', 'o', 'o', 'l',
    ...)`: a guard that names no source a value can come from, so it refused
    nothing. The same for `stops-being-true-when:` one field along."""
    root = write(tmp_path / "w", {
        "workspace.yaml": "name: memory\nallow-egress: []\n",
        "agents/pal.yaml": (
            "description: remembers\ninstructions: Help.\nremembers:\n  note:\n"
            "    description: a note\n    lasts: one-conversation\n"
            "    never-from: tool output\n    survives-shortening: yes\n"
            "    stops-being-true-when: the turn ends\n"
        ),
    })
    checked = pact("check", str(root), "--deny-warnings")
    assert checked.returncode == 0, checked.stdout + checked.stderr
    note = Facts.from_document(shown(root), "pal").declared["note"]
    assert note.never_from == ("tool output",)
    assert note.stale_when == ("the turn ends",)


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


def test_a_repeats_memory_carries_where_each_round_adds_to_it() -> None:
    """02W §2.11: a repeat's `remembers:` says what each round adds and how, and
    a workflow's or the workspace's may keep one value per input field."""
    facts = Facts.of(
        {
            "drafts": {
                "description": "every draft so far",
                "lasts": "one-run",
                "comes-from": "steps.draft.text",
                "combines-by": "keep-all",
            },
            "seen": {"description": "who was seen", "lasts": "forever", "kept-per": "specialty"},
        }
    ).declared
    drafts, seen = facts["drafts"], facts["seen"]
    assert (drafts.lasts, drafts.comes_from, drafts.combines_by) == ("one-run", "steps.draft.text", "keep-all")
    assert (seen.kept_per, seen.comes_from, seen.combines_by) == ("specialty", "", "")
