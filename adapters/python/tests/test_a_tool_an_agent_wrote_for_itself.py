"""What an agent may author for itself, and what a person must read first (P9).

D22 grants an agent the right to author tools for itself — the strongest form of
self-modification in the format. FR-6.2.5 and M7.4 have carried it as planned and
unbuilt since, for the reason everything else in this plan was unbuilt: there was
nowhere to run a body and nothing to hold it to.

AD-85 is the decision, and it splits the grant in two rather than answering it
once:

  * **Under the `no-code` badge a self-authored tool must be a `composite`** — a
    declarative composition of actions that are already approved and already
    pinned. There is no new behaviour in it, only a new arrangement of behaviour
    somebody already signed off, so a support lead can read it line by line and
    the badge survives.

  * **A code-bodied tool requires a distinct `engineer` role**, and the approval
    surface must say, in those words, *"this tool contains code that has not been
    read by a person."* Under D13 the human signing cannot read the body; saying
    so is the only honest thing to put in front of them.

And the acceptance rule that is the whole reason this is careful: **"does not
raise an exception" is forbidden as an acceptance criterion.** SkillWeaver's
exception criterion was gamed by silencing every atomic action's errors — a tool
that swallows its own failures passes it perfectly. What keeps a learned tool is
the eval gate every other learned change goes through.

Revocation is the other half nobody remembers to build: §8.5 requires removal to
be as expressible as addition, so a revoked digest cannot bind.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from pact_adapters.authoring import (  # noqa: E402
    ENGINEER,
    NOT_READ_BY_A_PERSON,
    AuthoredTool,
    Refused,
    may_bind,
    review_needed,
)


def _composite(**kw) -> AuthoredTool:
    kw.setdefault("composite", ("payments/issue-refund", "zendesk/reply"))
    return AuthoredTool(
        name="refund-and-tell",
        description="Issues the refund and replies, in one step.",
        **kw,
    )


def _code_bodied(**kw) -> AuthoredTool:
    return AuthoredTool(
        name="work-out-the-split",
        description="Works out how a refund splits across payment methods.",
        program="split-a-refund",
        **kw,
    )


#: Actions a person has already approved and pinned — what a composite may be
#: built from, and nothing else.
APPROVED = {"payments/issue-refund", "zendesk/reply", "zendesk/read-ticket"}


# ─────────────────────────────────────────── the no-code lane: composites only


def test_a_composite_over_approved_actions_needs_no_engineer() -> None:
    """The whole point of the lane: a support lead can read it.

    Nothing new happens — the actions were already approved and already pinned —
    so what needs reviewing is the arrangement, which is two lines.
    """
    needed = review_needed(_composite(), approved=APPROVED)
    assert ENGINEER not in needed.roles
    assert NOT_READ_BY_A_PERSON not in needed.wording


def test_a_composite_naming_an_action_nobody_approved_is_refused() -> None:
    """"Already approved" is the whole of what makes a composite safe.

    Without it the lane is a way to reach any action at all by composing it.
    """
    with pytest.raises(Refused) as raised:
        review_needed(
            _composite(composite=("payments/issue-refund", "payments/wire-transfer")),
            approved=APPROVED,
        )
    said = str(raised.value)
    assert "payments/wire-transfer" in said
    assert "approved" in said


def test_a_composite_is_still_refused_when_it_carries_a_body() -> None:
    """One or the other. A tool that composes AND carries code is a code-bodied
    tool wearing the badge's clothes."""
    with pytest.raises(Refused):
        review_needed(
            AuthoredTool(
                name="both", description="x",
                composite=("zendesk/reply",), program="something",
            ),
            approved=APPROVED,
        )


# ──────────────────────────────────────── the code lane: an engineer, and words


def test_a_code_bodied_tool_needs_the_engineer_role() -> None:
    needed = review_needed(_code_bodied(), approved=APPROVED)
    assert ENGINEER in needed.roles


def test_the_approval_surface_says_the_body_was_not_read() -> None:
    """In those words. Under D13 the person signing cannot read the body, and
    the only honest thing to put in front of them is that sentence."""
    needed = review_needed(_code_bodied(), approved=APPROVED)
    assert needed.wording == NOT_READ_BY_A_PERSON
    assert "has not been read by a person" in NOT_READ_BY_A_PERSON


def test_a_code_bodied_tool_does_not_earn_the_no_code_badge() -> None:
    assert review_needed(_code_bodied(), approved=APPROVED).no_code_badge is False
    assert review_needed(_composite(), approved=APPROVED).no_code_badge is True


# ────────────────────────────────── the acceptance rule, and why it is not that


def test_not_raising_is_not_an_acceptance_criterion() -> None:
    """AD-85 forbids it in as many words, and the reason is measured.

    SkillWeaver's exception criterion was gamed by silencing every atomic
    action's errors: a tool that swallows its own failures passes it perfectly.
    So a learned tool that offers "it ran without erroring" as its evidence is
    refused, and told what would count.
    """
    with pytest.raises(Refused) as raised:
        review_needed(_code_bodied(kept_because="it ran without raising"), approved=APPROVED)
    said = str(raised.value)
    assert "eval" in said.lower() or "held-out" in said.lower()


def test_a_tool_kept_because_the_evals_improved_is_accepted() -> None:
    """The positive control — the refusal above is about the CRITERION, not
    about learned tools."""
    needed = review_needed(
        _code_bodied(kept_because="held-out score rose from 61% to 88%"),
        approved=APPROVED,
    )
    assert ENGINEER in needed.roles


# ──────────────────────────────────────────────────────────────── revocation


def test_a_revoked_body_cannot_bind() -> None:
    """§8.5: removal must be as expressible as addition.

    A tool nobody may use any more is not a tool you delete and hope — the
    digest is refused, so a lockfile carrying it cannot be produced.
    """
    tool = _code_bodied(digest="a" * 64)
    assert may_bind(tool, revoked=frozenset())
    assert not may_bind(tool, revoked=frozenset({"a" * 64}))


def test_a_superseded_tool_names_what_replaced_it() -> None:
    """Rollback needs the edge, not just the absence."""
    tool = _code_bodied(digest="b" * 64, supersedes="c" * 64)
    assert tool.supersedes == "c" * 64
