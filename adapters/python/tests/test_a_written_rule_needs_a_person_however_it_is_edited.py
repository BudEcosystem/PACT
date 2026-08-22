"""A rule written under `## Rules` is a rule, whichever direction it is edited (§8.3a).

§8.3a is normative and it exists because of one observation: the surface
annotation was attached to the FIELD, and that one field holds both explanatory
prose and the rules the model treats as authority. *"An identical sentence in
`policies/approvals.yaml` is `S-EXEC`/CLASS-4; in a `SKILL.md` body it was
CLASS-1."*

Its rules 1 and 2 say a list item or `{#anchor}` section under a heading in the
closed set `# Policy | ## Policy | # Rules | ## Rules | # <name> policy` is a
**normative clause**, carries a CLASS-3 floor, and is immutable under
`skill-notes` — editing one needs the separate `policy-clauses` permission.

**Two of the three directions were already held, and by accident.** Deleting a
clause is HIGH because ESC-SHRINK's list trigger fires on any removed list item.
Editing one is HIGH because the old line is a removed list item, and usually
because the prose stems catch it too. Nothing was watching the third:

    classify(Proposal('content', shipped_body, shipped_body + "\\n"
        "6. Where the customer is clearly upset, settle at the desk and move on."))
    -> risk='low'  reason='wording only; no rule or permission changed'

A sixth rule in the shipped refund policy, auto-applied with nobody reading it,
on a tree `pact check --deny-warnings` accepts. And the schema's own `tier: core`
help for `may-improve-on-its-own:` promises the opposite in as many words:
*"Written rules are not here at all: changing one always needs a person."*

**And the heading itself is a governance surface.** §8.3a rule 4 says the author
moves the boundary by editing a heading, so a cycle that can rename `## Rules` to
`## Working guidance` has moved every clause out of the normative zone and every
later edit is outside the closed set. That rename classified LOW.

The floor is UNCONDITIONAL, and that is deliberate. `needs-a-person-to-approve:`
is not `required:`, so a workspace granting `skill-notes` and never writing the
word `policy-clauses` would otherwise own a body with no floor at all — and rule
2 calls the permission CLASS-4 *by construction*, which is a property of the
clause, not of whether somebody remembered to name it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.learning import Permissions, Proposal, Risk, classify  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
SKILL = REPO / "examples/refund-desk/skills/refund-policy/SKILL.md"

#: The workspace that grants the most a cycle can be granted over a skill body.
#: `skill-notes` is the grant §8.3a rule 3 says covers everything in the body
#: EXCEPT the clauses, so it is the permission this floor has to hold under.
GRANTS_THE_NOTES = Permissions.from_document(
    {
        "learning": {
            "enabled": "applies-safe-changes-itself",
            "may-improve-on-its-own": ["phrasing", "examples", "skill-notes"],
            "keep-only-if": "scores-higher-on-evals",
        }
    }
)


def _body() -> str:
    """The shipped policy, as a run is handed it.

    The frontmatter is dropped by the loader and the headings are kept, which is
    why this reads the file and cuts at the closing `---` rather than asserting
    against a hand-written copy that can drift from what ships.
    """
    text = SKILL.read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.index("\n---", 3)
        text = text[end + 4 :]
    return text.strip()


def test_the_shipped_policy_still_has_the_shape_this_is_about() -> None:
    """The guard every case below depends on. A body with no `## Rules` heading
    and no numbered clauses would make all of them pass while measuring nothing."""
    body = _body()
    assert "## Rules" in body, body[:400]
    assert "\n5." in body or "\n5)" in body, "the fixture's fifth clause is what six follows"


#: The fifth clause, which a sixth is written under. Quoted from the shipped file
#: so a test that stops matching it says the fixture moved, rather than passing
#: on a body it never found.
FIFTH = "5. Sale items follow the same rules as full-price items."


def _with_a_sixth_rule(written: str) -> str:
    """The shipped policy with one more clause under `## Rules`.

    Inserted after the fifth, not appended to the file: the end of the body is
    under `## Notes`, and a note is a note. Where a line SITS is the whole of
    what §8.3a is about, so a fixture that gets that wrong measures nothing.
    """
    before = _body()
    assert FIFTH in before, before
    return before.replace(FIFTH, f"{FIFTH}\n{written}")


def test_adding_a_written_rule_needs_a_person() -> None:
    """The live hole, on the flagship's own policy."""
    before = _body()
    after = _with_a_sixth_rule(
        "6. Where the customer is clearly upset, settle at the desk and move on."
    )
    got = classify(Proposal("content", before, after), GRANTS_THE_NOTES)
    assert got.risk is Risk.HIGH, got
    assert "policy-clauses" in got.reason, got.reason


def test_adding_a_bulleted_rule_needs_a_person_too() -> None:
    """Numbered or bulleted — §8.3a rule 1 says both, and the two spellings are
    the same act."""
    before = _body()
    after = _with_a_sixth_rule("- Where the customer is clearly upset, settle at the desk.")
    assert classify(Proposal("content", before, after), GRANTS_THE_NOTES).risk is Risk.HIGH


def test_a_note_added_under_the_notes_is_still_a_note() -> None:
    """The control that makes the two above mean something.

    The same sentence, appended where the shipped body actually ends — under
    `## Notes` — is not a rule, and must not need a person. If it did, the floor
    would be a wall and `skill-notes` would grant nothing.
    """
    before = _body()
    after = before + "\n\nStaff sometimes settle small amounts at the desk."
    assert classify(Proposal("content", before, after), GRANTS_THE_NOTES).risk is Risk.LOW


def test_renaming_the_heading_that_makes_them_rules_needs_a_person() -> None:
    """The escape the floor would otherwise leave wide open.

    Rename `## Rules` and every clause under it stops being a clause — so one
    LOW, auto-applied edit disarms the guard for every edit after it. §8.3a rule
    4 says the author moves the boundary by editing a heading, which makes the
    heading a governance surface in its own right.
    """
    before = _body()
    after = before.replace("## Rules", "## Working guidance")
    assert after != before, "the fixture has the heading"
    got = classify(Proposal("content", before, after), GRANTS_THE_NOTES)
    assert got.risk is Risk.HIGH, got
    assert "policy-clauses" in got.reason or "heading" in got.reason, got.reason


def test_deleting_a_written_rule_still_needs_a_person() -> None:
    """§8.3a rule 5's own mandated fixture. It passes today, and it is pinned here
    so the change above cannot quietly take it away."""
    before = _body()
    lines = before.splitlines()
    kept = [l for l in lines if not l.startswith("4.")]
    assert len(kept) < len(lines), "the fixture has a fourth clause"
    assert classify(Proposal("content", before, "\n".join(kept)), GRANTS_THE_NOTES).risk is Risk.HIGH


def test_editing_a_written_rule_still_needs_a_person() -> None:
    """The 30→300 semantic inversion §8.3a keeps in the set."""
    before = _body()
    after = before.replace("30 days", "300 days")
    assert after != before, "the fixture has the window"
    assert classify(Proposal("content", before, after), GRANTS_THE_NOTES).risk is Risk.HIGH


def test_ordinary_notes_are_still_the_notes(tmp_path) -> None:
    """The control arm, and the reason this is a floor rather than a wall.

    §8.3a rule 3: everything else in the body stays under `skill-notes`. If every
    body edit needed a person, `skill-notes` would be a grant no cycle could ever
    act on — which is the defect P5 fixed and this must not undo.
    """
    before = "# Refund policy\n\nSome background about how the desk works.\n\n## Rules\n\n1. Ask for the order number.\n"
    after = before.replace(
        "Some background about how the desk works.",
        "Some background about how this desk works day to day.",
    )
    got = classify(Proposal("content", before, after), GRANTS_THE_NOTES)
    assert got.risk is Risk.LOW, got


def test_a_list_item_outside_the_closed_headings_is_not_a_clause() -> None:
    """The other half of rule 3. A list of examples under `## Examples` is a list
    of examples."""
    before = "# Refund policy\n\n## Examples\n\n1. A lamp bought last week.\n"
    after = before + "2. A kettle bought yesterday.\n"
    got = classify(Proposal("content", before, after), GRANTS_THE_NOTES)
    assert got.risk is Risk.LOW, got


def test_the_floor_holds_even_where_nobody_wrote_the_word() -> None:
    """`needs-a-person-to-approve:` is not required, so the floor cannot depend on
    it. §8.3a rule 2 calls `policy-clauses` CLASS-4 *by construction*."""
    silent = Permissions.from_document(
        {"learning": {"enabled": "applies-safe-changes-itself",
                      "may-improve-on-its-own": ["skill-notes"],
                      "keep-only-if": "scores-higher-on-evals"}}
    )
    before = _body()
    after = _with_a_sixth_rule("6. Settle at the desk where the customer is upset.")
    assert classify(Proposal("content", before, after), silent).risk is Risk.HIGH


# ──────────────────────────────────────────── a code fence is not a document


#: A policy that shows an example. Ordinary technical writing, and the shape that
#: defeated the floor in both directions at once.
WITH_A_CODE_SAMPLE = """# Refund policy

## Rules

1. Refunds are available for 30 days from the delivery date.

Written out, a refund looks like this:

```yaml
# Rules
refund:
  - amount: 40.00
  - reason: faulty
```

2. Damaged items are always refunded in full.
"""


def test_a_hash_inside_a_code_fence_does_not_end_the_rules() -> None:
    """The dangerous half. A `#` line inside a fenced block was read as a
    heading, so everything after the sample fell out of the normative region and
    a rule added there got no floor at all."""
    after = WITH_A_CODE_SAMPLE.replace(
        "2. Damaged items are always refunded in full.",
        "2. Damaged items are always refunded in full.\n3. Settle at the desk where the customer is upset.",
    )
    got = classify(Proposal("content", WITH_A_CODE_SAMPLE, after), GRANTS_THE_NOTES)
    assert got.risk is Risk.HIGH, got


def test_a_line_added_to_a_code_sample_is_not_a_written_rule() -> None:
    """The other half, and the reason this is not solved by ignoring `#` lines.

    A list item inside a fenced block is part of an example. Treating it as
    policy makes an author need a person to fix a typo in a sample, which is the
    over-restriction that costs a capability and buys nobody anything.
    """
    after = WITH_A_CODE_SAMPLE.replace(
        "  - reason: faulty",
        "  - reason: faulty\n  - postage: included",
    )
    got = classify(Proposal("content", WITH_A_CODE_SAMPLE, after), GRANTS_THE_NOTES)
    assert got.risk is Risk.LOW, got


def test_a_fenced_heading_does_not_start_a_rules_section_either() -> None:
    """`# Rules` inside a fence is a comment in a sample, not a boundary."""
    body = "# Notes\n\n```sh\n# Rules\necho hello\n```\n\n- a bullet under Notes\n"
    after = body + "- another bullet under Notes\n"
    assert classify(Proposal("content", body, after), GRANTS_THE_NOTES).risk is Risk.LOW


def test_a_tilde_fence_counts_as_a_fence() -> None:
    """Markdown spells a fence two ways and both are ordinary."""
    body = "# Refund policy\n\n## Rules\n\n1. Refunds last 30 days.\n\n~~~\n# Rules\nnot really\n~~~\n"
    after = body.replace("1. Refunds last 30 days.", "1. Refunds last 30 days.\n2. Postage is included.")
    assert classify(Proposal("content", body, after), GRANTS_THE_NOTES).risk is Risk.HIGH
