"""`learning.enabled:` is the whole decision, and the author's line is what decides.

There used to be two settings for one decision — `enabled: one-of [off,
propose-only, yes]` and `auto-apply: yes-no` beside it. Six spellings for three
real states, and they could disagree in silence. Measured on the shipped worked
example before the fix:

    enabled: propose-only
    auto-apply: yes
    → OK — examples/refund-desk loaded cleanly (492 settings).   exit 0

`Permissions.may_apply_without_a_person()` reads `enabled:` first and returns on
`propose-only`, so the author's `yes` was discarded and nothing said so. The
reverse was worse: `enabled: yes` with no `auto-apply:` line defaulted to `no`,
so the strongest word on the one setting that decides whether a system rewrites
itself with nobody watching meant nothing at all.

**Everything here goes through the real Rust loader on a real tree on disk.**
That is the point. A `Permissions` built in Python proves that `Permissions`
works and says nothing about whether the author's line reaches it — and this
module's own subject is a pair of settings that reached the reader and were
thrown away.

The Rust half — the diagnostics that refuse the deleted spelling and demand the
list of what may change — is `crates/pact-cli/tests/one_line_says_whether_it_
changes_itself.rs`. The deletion itself is `docs/50-NOT-COPIED.md` §5 R59.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.evals import Case  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.learning import (  # noqa: E402
    APPLIES_ITSELF, Learner, Proposal,
)
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"

# Free of every word the blast-radius classifier watches for, so what is being
# tested is the governance line and not the classifier: an instruction
# mentioning refunds, approvals or declines is decision logic and is HIGH by
# design, whatever `enabled:` says.
BAD = "Answer the customer."
GOOD = "Answer the customer. State the outcome as one word at the start, then the figure."

SPEC = AgentSpec(name="Refund Desk", description="Decides refunds", instructions=BAD)
HOLDOUT = [
    Case("h1", "kettle faulty after 10 days", {"decision": "approved"}),
    Case("h2", "headphones, changed mind, 45 days", {"decision": "declined"}),
]


def transport_for(spec: AgentSpec):
    """A model that only answers gradeably once the instructions say how to."""
    if "one word at the start" in spec.instructions:
        return ReferenceTransport(Script([Turn("Decision: approved. Amount: 40 USD.")]))
    return ReferenceTransport(Script([Turn("It depends on the circumstances.")]))


def _workspace(tmp_path: Path, **edits: str) -> dict:
    """The worked example on disk with `learning.yaml` rewritten, loaded for real.

    `pact show` is the same door every adapter reads through, so what comes back
    is what a runtime would see. The tree is CHECKED first: a document `pact
    check` refuses must never be the thing a test asserts behaviour about, or
    the test is describing a workspace nobody could ship.
    """
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    root = tmp_path / "refund-desk"
    shutil.copytree(EXAMPLE, root)
    p = root / "learning.yaml"
    text = p.read_text()
    for old, new in edits.items():
        old = old.replace("_", "-")
        assert old in text, f"fixture drifted: {old!r} is not in learning.yaml"
        text = text.replace(old, new)
    p.write_text(text)

    checked = subprocess.run(
        [str(PACT_BIN), "check", str(root)], capture_output=True, text=True
    )
    assert checked.returncode == 0, (
        "the tree these assertions are about has to be one `pact check` accepts:\n"
        + checked.stdout
    )
    shown = subprocess.run(
        [str(PACT_BIN), "show", str(root)], capture_output=True, text=True, check=True
    )
    return json.loads(shown.stdout)


def _cycle(doc: dict):
    learner = Learner.from_document(doc, SPEC, tools={}, cases=HOLDOUT, bar=0.5)
    learner.holdout = HOLDOUT
    return learner, learner.cycle(Proposal("instructions", BAD, GOOD), transport_for)


def test_the_shipped_file_carries_the_whole_decision_on_one_line() -> None:
    """The worked example, untouched, through the loader.

    Two assertions and both matter: the deleted setting is gone from the
    document a runtime is handed, and the one that survived still refuses.
    """
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    shown = subprocess.run(
        [str(PACT_BIN), "show", str(EXAMPLE)], capture_output=True, text=True, check=True
    )
    block = json.loads(shown.stdout)["learning"]

    assert "auto-apply" not in block, (
        "`auto-apply:` is back in the worked example — the one document a "
        "support lead copies from"
    )
    assert block["enabled"] == "propose-only"

    _, out = _cycle(json.loads(shown.stdout))
    assert not out.applied, out.reason
    assert "propose-only" in out.reason, out.reason


def test_the_third_choice_is_what_lets_a_wording_change_go_live(tmp_path: Path) -> None:
    """The authored path, and the behaviour that changed.

    One word on one line in `learning.yaml` — plus the accept test beside it,
    see the sibling below — and a safe wording edit that a person had to approve
    now takes effect on its own. Nothing is constructed here: the tree is copied,
    the line is edited, `pact check` accepts it and `pact show` loads it.

    Before this item there was no single line that could do it. `enabled: yes`
    alone left `auto_apply` at its `no` default and the cycle refused; it took
    `auto-apply: yes` as well, and writing THAT beside `enabled: propose-only`
    was accepted and ignored.
    """
    doc = _workspace(
        tmp_path,
        **{
            "enabled: propose-only": f"enabled: {APPLIES_ITSELF}",
            "keep-only-if: a-person-approves-it": "keep-only-if: scores-higher-on-evals",
        },
    )
    assert doc["learning"]["enabled"] == APPLIES_ITSELF

    learner, out = _cycle(doc)
    assert out.applied, out.reason
    assert learner.spec.instructions == GOOD, (
        "the author wrote the answer that applies safe changes itself, and "
        "nothing applied"
    )


def test_the_same_tree_with_only_that_word_changed_back_refuses(tmp_path: Path) -> None:
    """The control for the test above, and the mutation guard.

    Identical tree, identical proposal, identical transport — one word different
    on one line. If `may_apply_without_a_person()` stops reading `enabled:`,
    this test and the one above cannot both hold.
    """
    doc = _workspace(
        tmp_path,
        **{"keep-only-if: a-person-approves-it": "keep-only-if: scores-higher-on-evals"},
    )
    learner, out = _cycle(doc)
    assert not out.applied, out.reason
    assert "propose-only" in out.reason, out.reason
    assert learner.spec.instructions == BAD


def test_the_accept_test_beside_it_can_still_make_the_third_choice_inert(
    tmp_path: Path,
) -> None:
    """The sibling on the same decision, named rather than hidden.

    `keep-only-if: a-person-approves-it` and `enabled: applies-safe-changes-
    itself` are the same disagreement one setting over: the first says a person
    decides, the second says nothing waits for one. The adapter resolves it the
    safe way and SAYS WHICH LINE DID IT — that much is held here. What no test
    can claim is that `pact check` refuses the pair; it does not, and R59's
    argument applies to it exactly as it applied to `auto-apply:`.
    """
    doc = _workspace(tmp_path, **{"enabled: propose-only": f"enabled: {APPLIES_ITSELF}"})
    assert doc["learning"]["keep-only-if"] == "a-person-approves-it"

    learner, out = _cycle(doc)
    assert not out.applied, out.reason
    assert "keep-only-if" in out.reason, (
        "a refusal the author cannot trace to a line they wrote is a refusal "
        "they will route around: " + out.reason
    )
    assert learner.spec.instructions == BAD


def test_a_word_the_specification_no_longer_has_refuses_rather_than_opening_the_door() -> None:
    """`enabled: yes` was legal last version. Failing closed is the only safe read.

    `pact check` refuses it where the author is — that is the Rust half. This is
    the twin refusal one language over, deliberately, the way every other paired
    check in PACT is: a stale file reaching a runtime that never ran `check`
    must not be handed the one permission its own file no longer grants. The
    branch it exercises is the `!= APPLIES_ITSELF` line; without it the function
    falls through to `return ""`, which is *yes, apply it*.
    """
    from pact_adapters.learning import Permissions

    stale = Permissions.from_document({"learning": {"enabled": "yes"}})
    blocked = stale.may_apply_without_a_person()
    assert blocked, "a word this file does not have must never mean `go ahead`"
    for choice in ("off", "propose-only", APPLIES_ITSELF):
        assert choice in blocked, (choice, blocked)


def test_a_caller_that_read_no_learning_file_still_decides_for_itself() -> None:
    """The one case where saying nothing is not the same as saying `off`.

    A host driving `Learner` by hand has taken the decision itself, and
    inventing a gate it never asked for would be a governance decision made on
    its behalf. The fail-closed branch above must not swallow this.
    """
    from pact_adapters.learning import Permissions

    assert Permissions.default().may_apply_without_a_person() == ""
    assert Permissions.from_document({}).may_apply_without_a_person() == ""
