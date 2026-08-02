"""`action.inspects:` deciding what a gate does, not just what a help line says.

`inspects:`' own help: *"the arguments an approval rule is allowed to look at —
an amount, a quantity. These are exactly the ones the model DOES choose, which is
the point of asking a person about them."* The architecture is stricter still:
an `inspected` argument is *"the only role a `policy.ask-a-person` predicate may
read"*.

Nothing read the line. Measured before this round, on the shipped tree:

    inspects: [amount]          questions_for(doc, 'refund-desk')
    inspects: [order-number]    ... -> the identical Question for the same call

so the word *allowed* governed nothing, and `pact check` said so in a **warning**
that exited 0 and claimed a consequence — *"nothing is compared and nobody is
asked"* — which no code anywhere could produce.

Both halves bite now, and they agree with each other. `pact check` refuses the
tree (`crates/pact-cli/tests/a_gate_that_reads_what_it_may_not.rs`), and here the
gate refuses the call: a condition PACT may not evaluate STOPS, the same
direction a malformed `more-than:` already stopped in, because turning a mistake
into a disabled gate is the one way this area must never fail.

Every test below loads a TREE — the worked example, or a copy of it with one line
of one YAML file changed — through the real Rust loader, and passes no gate in.
A test that built the `Rule` itself would prove the predicate works and say
nothing about whether the author's `inspects:` line arrives, which is exactly the
shape of defect this file exists about.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.questions import questions_for  # noqa: E402
from pact_adapters.suspension import NEEDS_APPROVAL  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"

#: A refund UNDER the author's 200 USD figure. It runs on the shipped tree, and
#: that is what makes it the honest probe: anything that stops it is stopping a
#: call the author wrote no rule about.
UNDER_THE_LIMIT = {"action": "issue-refund", "order-number": "A-1182", "amount": "40.00 USD"}

#: And one over it, which the author's rule really is about.
OVER_THE_LIMIT = {"action": "issue-refund", "order-number": "A-1182", "amount": "300.00 USD"}


def loaded(root: Path) -> dict:
    """One tree, through the real Rust loader (invariant P-1)."""
    return json.loads(
        subprocess.run(
            ["cargo", "run", "--quiet", "-p", "pact-cli", "--", "show", str(root)],
            cwd=str(REPO), capture_output=True, text=True, check=True,
        ).stdout
    )


@lru_cache(maxsize=1)
def worked_example() -> dict:
    return loaded(EXAMPLE)


def a_tree_with_one_line_changed(tmp_path: Path, file: str, was: str, now: str) -> Path:
    """The worked example on disk with a single line of one YAML file rewritten.

    Nothing else moves — not the policy, not the question, not the agent. So a
    difference in what the gate does afterwards is attributable to that line and
    to nothing this test did.
    """
    root = tmp_path / "tree"
    shutil.copytree(EXAMPLE, root)
    path = root / file
    text = path.read_text()
    assert was in text, f"fixture drifted: {file} no longer contains {was!r}"
    path.write_text(text.replace(was, now, 1))
    return root


def with_one_line_changed(tmp_path: Path, file: str, was: str, now: str) -> dict:
    """The same, loaded — for edits that leave a tree `pact check` accepts."""
    return loaded(a_tree_with_one_line_changed(tmp_path, file, was, now))


def as_a_host_that_skipped_the_check(was: str, now: str) -> dict:
    """The shipped document with the same one-line edit applied after loading.

    It has to be done this way round and it is worth saying why. The two halves
    of this round AGREE: a rule looking outside `inspects:` is an error, so
    `pact check` exits non-zero and `pact show` refuses to emit the document at
    all — *"a tree that only `check` refuses is a tree every adapter accepts"* is
    the comment on `show`, and it means no adapter in this repository can be
    handed such a tree off disk.

    What is left to prove is the fail-safe underneath that: D2 makes the
    folder-and-file tree natively executable, so a runtime that reads it itself,
    or a host that assembles a document some other way, can still reach the gate
    without ever running `check`. This is that host. The edit is the identical
    one the disk test makes — a value under `tools.payments.actions.issue-refund.inspects`
    — and `questions_for` still resolves everything from the document, so what is
    measured is still the author's line arriving and not an object built here.
    """
    doc = json.loads(json.dumps(worked_example()))
    action = doc["tools"]["payments"]["actions"]["issue-refund"]
    assert action["inspects"] == [was], f"fixture drifted: {action['inspects']}"
    action["inspects"] = [now]
    return doc


def stops(doc: dict, args: dict) -> bool:
    """Does the author's own policy stop this `payments` call?

    Through `only_for(NEEDS_APPROVAL)` so the connection consent — which stops
    every call to `payments` and is a different authored line's guarantee — is
    not what is being measured.
    """
    return questions_for(doc, "refund-desk").only_for(NEEDS_APPROVAL)._stops(
        "payments", args
    )


# ────────────────────────────────────── the shipped tree, unchanged


def test_the_worked_examples_own_rule_reads_an_argument_its_tool_file_offers() -> None:
    """The floor, and the thing every test below is a departure from.

    `tools/payments.yaml` writes `inspects: [amount]` and
    `policies/approvals.yaml` looks at `amount`, so the author's 200 USD figure
    governs: 40 USD runs, 300 USD waits. If enforcing `inspects:` had made the
    shipped example stop everything, this is where it would say so.
    """
    doc = worked_example()
    assert stops(doc, UNDER_THE_LIMIT) is False
    assert stops(doc, OVER_THE_LIMIT) is True


# ─────────────────────────── the author's line, changed, changing the outcome


def test_taking_amount_off_the_inspects_line_stops_the_refund_it_used_to_let_through(
    tmp_path: Path,
) -> None:
    """The whole item, in one assertion.

    One line of `tools/payments.yaml` changes — `inspects: [amount]` becomes
    `inspects: [order-number]` — and a 40 USD refund that ran now waits for a
    person. The rule is looking at a figure the action does not offer it, so
    there is no comparison it may legitimately make, and a gate PACT cannot
    evaluate stops rather than goes quiet.

    Before this round the same edit changed nothing at all: same gate, same
    question, same run. `questions._atom_stops` is where it now bites, through
    `_reads_something_it_may_not`; delete that call and this test fails.
    """
    doc = as_a_host_that_skipped_the_check("amount", "order-number")
    assert stops(doc, UNDER_THE_LIMIT) is True, (
        "the author's `inspects:` line reached nothing — a gate reading an argument "
        "the action does not offer must not quietly go on comparing"
    )

    # And the author is told, at the same edit, by the command they run. The two
    # halves have to agree or one of them is a trap: it is safe for every call to
    # wait, and it is not what they wrote.
    root = a_tree_with_one_line_changed(
        tmp_path, "tools/payments.yaml", "inspects: [amount]", "inspects: [order-number]"
    )
    out = subprocess.run(
        ["cargo", "run", "--quiet", "-p", "pact-cli", "--", "check", str(root)],
        cwd=str(REPO), capture_output=True, text=True,
    )
    assert out.returncode != 0, out.stdout
    assert "loader/argument-not-offered-for-inspection" in out.stdout, out.stdout


def test_the_same_edit_leaves_the_refund_that_was_already_over_the_figure_waiting() -> None:
    """And it fails safe, not open.

    The direction matters more than the mechanism. A refusal that let the 300 USD
    refund through would be this round shipping the very fail-open its own
    diagnostic used to describe.
    """
    assert stops(as_a_host_that_skipped_the_check("amount", "order-number"), OVER_THE_LIMIT) is True


def test_an_action_that_offers_nothing_for_inspection_restricts_no_rule_at_all(
    tmp_path: Path,
) -> None:
    """An absent line is not an empty list.

    Most tool files have never written `inspects:`. Reading their silence as "no
    argument may be looked at" would turn every gate in every such workspace into
    a gate that stops everything — a governance change nobody authored, which is
    the same class of harm as the one being fixed.
    """
    doc = with_one_line_changed(
        tmp_path, "tools/payments.yaml", "\n    inspects: [amount]", ""
    )
    assert stops(doc, UNDER_THE_LIMIT) is False
    assert stops(doc, OVER_THE_LIMIT) is True


def test_widening_the_inspects_line_is_a_way_to_say_yes_and_not_only_a_way_to_say_no(
    tmp_path: Path,
) -> None:
    """The author's other move: offer the argument instead of changing the rule.

    Both fixes the diagnostic prints have to work, or one of them is advice that
    does not lead anywhere. This is the one that keeps the rule as written.
    """
    doc = with_one_line_changed(
        tmp_path,
        "tools/payments.yaml",
        "inspects: [amount]",
        "inspects: [amount, order-number]",
    )
    assert stops(doc, UNDER_THE_LIMIT) is False
    assert stops(doc, OVER_THE_LIMIT) is True


def test_the_permission_is_per_action_and_not_per_tool() -> None:
    """`look-up-order` is on the same tool and offers nothing for inspection.

    A permission read per TOOL would have `look-up-order`'s silence overrule
    `issue-refund`'s line, or the other way about — and `payments` is exactly the
    tool where that matters, because one of its actions moves money and the other
    reads. The rule names `payments/issue-refund`, so that action's line is the
    one that governs it, keyed the way the rule itself spells it.
    """
    from pact_adapters.questions import _inspects_of

    offered = _inspects_of(worked_example())
    assert offered == {"payments/issue-refund": frozenset({"amount"})}, offered
    assert "payments/look-up-order" not in offered, (
        "an action that never wrote the line must not acquire an empty one"
    )


# ───────────────────────────────────────── what the author is told, in words


def test_pact_check_refuses_the_tree_the_gate_would_have_to_stop_everything_for(
    tmp_path: Path,
) -> None:
    """The two halves have to agree, or one of them is a trap.

    The runtime stopping every call is safe and is not what the author wrote, so
    they have to hear about it before a customer is waiting rather than by
    watching every refund park. `pact check` is the one command D13's reader
    runs, and it exits non-zero on exactly the tree the test above measures.
    """
    root = tmp_path / "tree"
    shutil.copytree(EXAMPLE, root)
    policy = root / "policies/approvals.yaml"
    policy.write_text(
        policy.read_text().replace(
            "arg: amount, more-than: 200 USD", "arg: order-number, more-than: 200 USD", 1
        )
    )
    out = subprocess.run(
        ["cargo", "run", "--quiet", "-p", "pact-cli", "--", "check", str(root)],
        cwd=str(REPO), capture_output=True, text=True,
    )
    assert out.returncode != 0, out.stdout
    assert "loader/argument-not-offered-for-inspection" in out.stdout, out.stdout
    assert "inspects:" in out.stdout, "the fix has to be typeable: " + out.stdout


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
