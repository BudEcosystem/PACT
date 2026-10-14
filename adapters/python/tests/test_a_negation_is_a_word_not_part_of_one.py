"""A grader's negation guard reads whole words.

`evals._stated_at` counts an expected value as not stated when a negator stands
within a few characters before it, so *"not eligible for a refund"* never
grades as an approval. The negators were matched as plain substrings, so the
`no ` at the end of *Merino* negated whatever followed it: a reply that closed
a sentence on *"... the Merino tee"* and then wrote `"hand-off": "stay"` graded
FAIL against `expect: {hand-off: stay}`, though it said exactly that (budFlow
corpus #76, recorded on DeepSeek flash). A negator now begins at a word's
start; `n't` still ends one.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.evals import Case, check  # noqa: E402
from pact_adapters.harness import RunResult  # noqa: E402


def _grades(output: str, expect: dict[str, str]) -> bool:
    return check(Case("c1", "a ticket", expect), RunResult(output=output), []).passed


def test_a_word_that_ends_in_a_negator_does_not_negate_what_follows() -> None:
    reply = 'Sizing runs small on the Merino tee {"hand-off": "stay"}'
    assert _grades(reply, {"hand-off": "stay"})
    for word in ("casino", "piano", "volcano"):
        assert _grades(f"the {word} stay", {"hand-off": "stay"}), word


def test_a_negator_that_is_a_word_still_negates() -> None:
    assert not _grades("This sale item is not eligible for a refund.", {"decision": "approved"})
    assert not _grades("I cannot approve a refund for a sale item.", {"decision": "approved"})
    assert not _grades("No stay is possible here", {"hand-off": "stay"})
    assert not _grades("We don't stay", {"hand-off": "stay"})
    assert not _grades("It was refused: stay", {"hand-off": "stay"})


def test_a_negator_in_the_field_before_does_not_negate_the_next_field() -> None:
    """A negator ending one field is that field's: *"... we can't"* then `path: simple` on the
    next line, or in the next field of one line of JSON, still states `simple` (budFlow's
    *Route to a specialist* example, recorded on DeepSeek flash)."""
    assert _grades("reply: Sorry, that is one we can't\npath: simple", {"path": "simple"})
    assert _grades('{"reply": "Sorry, that is one we can\'t", "path": "simple"}', {"path": "simple"})
    assert not _grades('{"decision": "not approved"}', {"decision": "approved"})
    assert not _grades('{"reply": "I cannot approve a refund"}', {"decision": "approved"})


def test_a_quote_or_a_line_break_alone_ends_no_field() -> None:
    """Only a closed string followed by `,` `:` `}` or `]`, or a line starting `<key>:`, ends a
    field: a negator before a quoted or line-wrapped value still negates it. Cutting at every
    quote and line break graded these refusals as approvals."""
    approved = {"decision": "approved"}
    assert not _grades('This refund is not "approved".', approved)
    assert not _grades('I cannot mark it "approved"', approved)
    assert not _grades('Sorry, we cannot "approve" this refund.', approved)
    assert not _grades("The refund is not\napproved", approved)
    assert _grades('{"reply": "Sorry, that is one we can\'t",\n"path": "simple"}', {"path": "simple"})
