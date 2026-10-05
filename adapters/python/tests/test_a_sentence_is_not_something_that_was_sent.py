"""`sent` is a word, not a stem: an edit that says `sentence` is a phrasing (§8.3a, D23).

`HIGH_RISK_PROSE` lists stems with no trailing word boundary on purpose (`approv`
must catch `approved`), and one entry in it is not a stem. `sent`, left open,
matched the first four letters of `sentence`, so the commonest instruction there
is — *"Answer in one short sentence."* — made every edit to those instructions
CLASS-HIGH. Found by a host running a real learning cycle: a change that scored
0 -> 1.0 on the held-out split under `enabled: applies-safe-changes-itself` and
`may-improve-on-its-own: [phrasing]` was held with *"the wording changes a rule,
not a phrasing"*, quoting a line with no rule in it.
"""

from __future__ import annotations

from pact_adapters.learning import Proposal, Risk, classify

ONE_SENTENCE = "Answer in one short sentence."


def wording(after: str, before: str = ONE_SENTENCE) -> str:
    return classify(Proposal("instructions", before, after)).risk


def test_an_edit_that_only_says_sentence_is_a_phrasing() -> None:
    assert wording("Answer in one short sentence, in plain words.") == Risk.LOW
    assert wording("Answer in one short sentence. Name the colour first.") == Risk.LOW
    assert wording("Keep the sentiment friendly.", before="Be friendly.") == Risk.LOW


def test_something_that_is_sent_is_still_a_rule() -> None:
    assert wording("Be brief. The receipt is sent by email.", before="Be brief.") == Risk.HIGH
    assert wording("Be brief. Once sent, tell the customer.", before="Be brief.") == Risk.HIGH


def test_the_stems_beside_it_are_still_open() -> None:
    for after in (
        "Be brief. Refunds are approved.",
        "Be brief. Sending is free.",
        "Be brief. Escalated tickets wait.",
        "Be brief. Payment is on Friday.",
        "Be brief. Requests are declined after 30 days.",
    ):
        assert wording(after, before="Be brief.") == Risk.HIGH, after
