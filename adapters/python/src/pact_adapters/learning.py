"""The learning loop (T6, D9, D22, D23).

An agent improves itself by proposing an **edit to a spec file**. Never weights,
never hidden state, never an opaque adapter — because an agent that learns must
still be one you can read, review, sign, fork and port. That is thesis T6, and
it is what keeps self-improvement compatible with portability at all.

Three gates, each from a specific finding rather than from caution:

* **A frozen held-out split, locked before the cycle starts.** Otherwise the
  optimiser tunes the thing it is scored on.
* **A blast-radius classifier** (D23). Wording auto-applies; anything touching
  tools, permissions or decision logic needs a person. Classification is
  conservative and explains itself.
* **Cumulative drift against a frozen baseline**, not just per-diff review.
  Gradual blueprint erosion is invisible one diff at a time — 17 of 25 MLAS
  attack-surface cells have no per-diff defence.

And the reason the gate matters more than the edit: model-authored skills
measure 8–11 points *below* no-skill, and ungated libraries score below the
baseline outright. Learning without a gate is worse than no learning.
"""

from __future__ import annotations

import difflib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Mapping

from .evals import Case, CaseOutcome, Verdict, check, verdict
from .harness import run
from .ir import AgentSpec
from .limits import _nothing_can_reach, money


class Risk:
    LOW = "low"        # auto-applies; reverted automatically if evals worsen
    HIGH = "high"      # always needs a person
    UNKNOWN = "unknown"  # treated as HIGH — absence of evidence is not safety


#: Fields whose change alters what the agent can *do*, not how it says things.
#: Deliberately over-broad: a false HIGH costs a review, a false LOW costs an
#: incident.
HIGH_RISK_FIELDS = (
    "uses", "tools", "team", "model", "policy", "needs-approval-before",
    "limits", "needs", "evals", "learning", "answers-with", "run-inputs",
)

#: What each of `may-improve-on-its-own:`'s four choices names, as a field of a
#: spec document. The schema's words are written for whoever reads the file; the
#: classifier works on field names, and one mapping in one place is what keeps
#: the two from meaning different things.
SAFE_TO_CHANGE: dict[str, tuple[str, ...]] = {
    "phrasing": ("instructions",),
    "examples": ("description",),
    "skill-notes": ("content",),
    "when-skills-are-used": ("use-when", "do-not-use-when", "if-unsure"),
}

#: Phrases that change decision logic even inside prose. Instructions are the
#: one field where a "wording" edit can silently become a permission edit.
#:
#: **No trailing `\b`.** Every truncated stem here was dead: closing the
#: alternation with a word boundary meant `approv` had to be followed by a
#: non-word character, which never happens in English. Measured against the live
#: regex before the fix: `Refunds are available for 300 days.` did not match,
#: `Refunds are approved.` did not match, `Escalate to a manager.` did not match,
#: and the only string that ever matched `escalat` was the bare fragment. So
#: `classify(Proposal('instructions', '... 30 days.', '... 300 days.'))` returned
#: `risk=low, needs_a_person=False` — and §8.3a makes exactly that 30→300 case
#: normative at CLASS-3 or above.
#:
#: The leading `\b` stays: it is what stops `pay` matching inside `company`.
HIGH_RISK_PROSE = re.compile(
    r"\b(never|always|must not|do not|approv|declin|refund|delet|send|sent|pay|paid|"
    r"issu|escalat|without asking|automatically)",
    re.IGNORECASE,
)

#: The fields a cycle can actually put into effect.
#:
#: `_with` rewrites the spec it scores, so this is the intersection of two
#: things: what `AgentSpec` carries, and what a run reads. `instructions` is the
#: whole of that set, and the shortfall against `SAFE_TO_CHANGE` is not an
#: oversight to be tidied away — of `description`, `content`, `use-when`,
#: `do-not-use-when` and `if-unsure`, only `description` is an `AgentSpec` field
#: at all, and `_system_for` puts `instructions` into the system text and
#: `description` nowhere.
#:
#: So a `description` proposal used to build a candidate that WAS the incumbent,
#: score both at full price, and return *"held-out score did not improve"* — a
#: true sentence about a comparison with no candidate in it. Naming the set is
#: what lets `cycle` refuse before spending, and `_with` raise instead of
#: silently agreeing.
CAN_BE_APPLIED: tuple[str, ...] = (
    "instructions",
    # A written procedure's body and its four routing lines (P5). `_with`
    # rewrites the spec that gets SCORED, so the condition for a field being
    # applicable is that a run READS it — and every one of these reaches the
    # model through `SkillSpec.in_words()`, which is spliced into the system
    # message. A candidate carrying a different one is genuinely a different
    # agent to grade, which is the whole test.
    #
    # They were granted and unreachable. `may-improve-on-its-own:` is `tier:
    # core` and offers four words; three of them named these fields, and an
    # author who wrote `[skill-notes]` granted something no cycle could put into
    # effect. Every proposal came back with a sentence about a limitation of this
    # process rather than about their document — a governance surface that loads
    # and does nothing, in the one file whose subject is what may change with
    # nobody watching.
    "content",
    "use-when",
    "do-not-use-when",
    "if-unsure",
)

#: Fields a cycle genuinely cannot apply, and why — one entry, one reason.
#:
#: The condition is not "this process happens not to rewrite it": it is that
#: NOTHING IN A RUN READS IT, so a candidate carrying a different value is the
#: incumbent wearing a different file and both scoring runs would grade the same
#: agent. That is a fact about the field, and it is the sentence a reviewer needs
#: — the older message named which fields this process rewrites, which tells them
#: nothing about their own document.
#:
#: A word under `may-improve-on-its-own:` must name a field that is either
#: applicable or excused here, and a test holds that: a third state cannot appear
#: by omission.
READ_BY_NO_RUN: dict[str, str] = {
    "description": (
        "one line for a colleague reading the file — it reaches the A2A card and "
        "no model, so rewriting it would score the same agent twice"
    ),
}

#: The three answers `learning.enabled:` has, in the schema's own spelling.
#:
#: Written down here because this module has to be able to say what the author
#: SHOULD have typed. There used to be a second setting beside it — `auto-apply:
#: yes-no` — and between them they spelled six combinations for these three
#: states, two of which contradicted each other: `enabled: propose-only` with
#: `auto-apply: yes` loaded cleanly and `may_apply_without_a_person()` threw the
#: `yes` away, while `enabled: yes` with no `auto-apply:` line at all defaulted
#: to no and so meant nothing.
OFF = "off"
PROPOSE_ONLY = "propose-only"
#: The one answer that lets an improvement take effect with nobody reading it.
APPLIES_ITSELF = "applies-safe-changes-itself"
ENABLED_CHOICES = (OFF, PROPOSE_ONLY, APPLIES_ITSELF)

#: A line that is one item of a list, numbered or not. §8.3's `ESC-SHRINK`.
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s)")

#: An anchor a policy clause is referred to by — `{#refund-window}`. Removing one
#: breaks every reference to it, silently.
_ANCHOR = re.compile(r"\{#[\w-]+\}")

#: How much of the text may disappear before a removal is a rewrite. §8.3's
#: `ESC-SHRINK` third trigger.
SHRINK_LIMIT = 0.4

#: The headings that make what sits under them a written RULE (§8.3a rule 1).
#:
#: `# Policy`, `## Policy`, `# Rules`, `## Rules` and `# <name> policy`, at any
#: depth: an author who nests their rules one level further down has not stopped
#: writing rules. Matched on the whole heading line, so `## Rules of thumb` is
#: not one — the closed set is closed, and widening it by substring would make
#: `## Notes` normative the day somebody wrote `## Notes on policy`.
_NORMATIVE_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(?:policy|rules|[\w'’\- ]*\s+policy)\s*$", re.I)

#: The permission §8.3a rule 2 says a written rule is edited under, and the word
#: every refusal below names.
#:
#: NOT a field name, and deliberately not in `SAFE_TO_CHANGE`. `Permissions.of`
#: tests `field in self.high` first, so mapping this word onto `content` would
#: make `of('content')` return HIGH for the flagship — every body edit would need
#: a person, `skill-notes` would become a grant no cycle could act on, and §8.3a
#: rule 3 ("everything else in the body stays S-GEN under `skill-notes`") would
#: be broken in the course of enforcing rule 2. It names a surface INSIDE a
#: document, which is the whole point of §8.3a, so only the clause check consults
#: it.
POLICY_CLAUSES = "policy-clauses"


#: A fenced code block, either spelling markdown offers.
#:
#: Fences matter because a `#` is a COMMENT in half the languages an author is
#: likely to paste, and a hyphen starts a list in YAML. Without this, the same
#: sample broke the floor in both directions at once: `# Rules` inside a fence
#: read as a heading, so a real rule written after the sample fell outside the
#: normative region and got no floor — and a line added to the sample itself read
#: as a written rule, so fixing a typo in an example needed a person.
_FENCE = re.compile(r"^\s{0,3}(?:```|~~~)")


def _prose_lines(body: str) -> list[str]:
    """`body` with every fenced code block taken out.

    Everything below reads this rather than `splitlines()`, so a fence is invisible
    to the heading walk and to the clause walk alike — which is the only way the
    two stay consistent about where a sample begins and ends.
    """
    out: list[str] = []
    fenced = False
    for line in body.splitlines():
        if _FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            out.append(line)
    return out


def _under_a_normative_heading(body: str) -> list[str]:
    """Every line of `body` that sits under one of the closed headings.

    "Under" means the nearest heading ABOVE it is one of them, so `## Notes`
    following `## Rules` ends the rules — which is how an author already reads
    their own file, and is the boundary §8.3a rule 4 says they move by editing a
    heading.
    """
    out: list[str] = []
    inside = False
    for line in _prose_lines(body):
        if line.lstrip().startswith("#"):
            inside = bool(_NORMATIVE_HEADING.match(line))
            continue
        if inside:
            out.append(line)
    return out


def _written_rules(body: str) -> set[str]:
    """The normative clauses in `body` — list items and anchored sections.

    §8.3a rule 1's definition, with prose deliberately left out: a paragraph of
    explanation under `## Rules` is explanation. What the model treats as
    authority is the numbered or bulleted line, and the section other clauses
    refer to by `{#anchor}`.
    """
    return {
        line.strip()
        for line in _under_a_normative_heading(body)
        if line.strip() and (_LIST_ITEM.match(line) or _ANCHOR.search(line))
    }


def _headings_that_make_rules(body: str) -> list[str]:
    """The closed-set heading lines themselves, as written."""
    return [
        line.strip()
        for line in _prose_lines(body)
        if line.lstrip().startswith("#") and _NORMATIVE_HEADING.match(line)
    ]


def a_written_rule_changed(before: str, after: str) -> "Classification | None":
    """§8.3a rules 1 and 2: the CLASS-3 floor under a written rule.

    An identical sentence in `policies/approvals.yaml` is `S-EXEC` and CLASS-4;
    in a `SKILL.md` body it was CLASS-1, because the surface was attached to the
    FIELD and that one field holds both explanation and authority.

    Two of the three directions were already answered, and by accident. Removing
    a clause is HIGH because ESC-SHRINK's list trigger fires on a removed list
    item; editing one is HIGH because the old line is a removed list item.
    Nothing watched the third, and ADDING a rule is the direction that matters
    most: measured on the flagship's own policy, a sixth numbered clause under
    `## Rules` classified LOW and applied itself with nobody reading it — while
    `may-improve-on-its-own:`'s own `tier: core` help promises "written rules are
    not here at all: changing one always needs a person".

    The HEADING is a governance surface too, and rule 4 says so in as many words:
    the author moves the boundary by editing one. A cycle that could rename
    `## Rules` to `## Working guidance` would move every clause out of the zone
    in one LOW edit and leave every later edit outside the closed set.

    Unconditional, and never keyed to the author having written the word
    `policy-clauses`: `needs-a-person-to-approve:` carries no `required:`, so a
    workspace that grants `skill-notes` and omits it would otherwise own a body
    with no floor. Rule 2 calls the permission CLASS-4 BY CONSTRUCTION, which is
    a property of the clause and not of anybody's memory.
    """
    # THE HEADING FIRST, because it explains everything below it. Renaming one
    # takes every clause under it out of the zone, so the clause-set difference
    # fires as well — and telling an author who reworded a title that five
    # written rules were removed sends them looking for a deletion they did not
    # make. The reason a person reads has to name the edit they actually did.
    if _headings_that_make_rules(before) != _headings_that_make_rules(after):
        return Classification(
            Risk.HIGH,
            f"the heading that makes those lines rules changed, which moves every one of "
            f"them in or out of the rules — that boundary is `{POLICY_CLAUSES}`, not "
            f"`skill-notes`",
        )
    was, now = _written_rules(before), _written_rules(after)
    added = sorted(now - was)
    if added:
        return Classification(
            Risk.HIGH,
            f"a written rule was added under a `Rules`/`Policy` heading, and a rule is "
            f"changed under `{POLICY_CLAUSES}` rather than `skill-notes` — {added[0][:70]!r}",
        )
    gone = sorted(was - now)
    if gone:
        return Classification(
            Risk.HIGH,
            f"a written rule was taken out from under a `Rules`/`Policy` heading, and a "
            f"rule is changed under `{POLICY_CLAUSES}` — {gone[0][:70]!r}",
        )
    return None


@dataclass
class Proposal:
    """One proposed edit, as a diff against a spec file."""

    field: str
    before: str
    after: str
    rationale: str = ""

    def diff(self, path: str = "agent") -> str:
        return "\n".join(
            difflib.unified_diff(
                self.before.splitlines(), self.after.splitlines(),
                fromfile=f"a/{path}.{self.field}", tofile=f"b/{path}.{self.field}",
                lineterm="",
            )
        )


@dataclass
class Classification:
    risk: str
    reason: str

    @property
    def needs_a_person(self) -> bool:
        return self.risk != Risk.LOW


def classify(p: Proposal, permissions: "Permissions | None" = None) -> Classification:
    """Blast radius of one edit. Conservative, and it always says why.

    `permissions` comes from the author's own `learning.yaml`. Without it the
    built-in lists apply, which is the right default for a workspace that wrote
    no such file — but it must not be the only answer, because "edit
    `HIGH_RISK_FIELDS` in learning.py" is the same answer as "experts write code
    for that", on the one mechanism D14 names by name.
    """
    rules = permissions or Permissions.default()
    # THE FLOOR UNDER A WRITTEN RULE, asked before anything else (§8.3a rules
    # 1-2). Before the author's own permissions, because it is a floor: a grant
    # cannot lower it, which is what "CLASS-4 by construction" means. `content`
    # alone, because it is the only field holding a document with headings in it.
    if p.field == "content":
        floor = a_written_rule_changed(p.before, p.after)
        if floor is not None:
            return floor
    verdict = rules.of(p.field)
    if verdict is not None:
        return verdict
    if p.field not in ("instructions", "description", "content"):
        return Classification(Risk.UNKNOWN, f"'{p.field}' is not a field with a known blast radius")

    lines = p.diff().splitlines()
    added = [l[1:].strip() for l in lines if l.startswith("+") and not l.startswith("+++")]
    # REMOVALS COUNT. `classify` collected only added lines, so a diff that only
    # deletes has nothing to test and fell through to LOW — and `Learner.cycle`
    # auto-applied it with no person. Measured: deleting the bullet
    # "Personalised items cannot be returned unless faulty." from a four-rule
    # refund policy returned `risk=low, reason='wording only; no rule or
    # permission changed'`. §8.3a records exactly that as found and fixed, and
    # the fix ("ESC-SHRINK's list trigger becomes removal of any list item") had
    # never been written.
    removed = [l[1:].strip() for l in lines if l.startswith("-") and not l.startswith("---")]

    for line in added + removed:
        if HIGH_RISK_PROSE.search(line):
            return Classification(
                Risk.HIGH,
                f"the wording changes a rule, not a phrasing: {line[:70]!r}",
            )
    # ESC-SHRINK. Three triggers, each naming itself in the reason, because a
    # refusal a person cannot explain is a refusal they will route around.
    for line in removed:
        if _LIST_ITEM.match(line):
            return Classification(
                Risk.HIGH,
                f"ESC-SHRINK: a written rule was removed from a list — {line[:70]!r}",
            )
        if _ANCHOR.search(line):
            return Classification(
                Risk.HIGH,
                f"ESC-SHRINK: an anchor other text refers to was removed — {line[:70]!r}",
            )
    before, after = len(p.before.split()), len(p.after.split())
    if before and after < before * (1.0 - SHRINK_LIMIT):
        return Classification(
            Risk.HIGH,
            f"ESC-SHRINK: {before - after} of {before} words removed, which is a rewrite "
            f"rather than a rephrasing",
        )
    return Classification(Risk.LOW, "wording only; no rule or permission changed")


@dataclass(frozen=True)
class Permissions:
    """What `learning.yaml` says may change itself, and what needs a person.

    The whole document reached no implementation for a round: `HIGH_RISK_FIELDS`
    and `max_cumulative_drift` were literals, `classify()` never saw the
    document, and `may-improve-on-its-own`, `needs-a-person-to-approve`,
    `keep-only-if`, `auto-apply`, `enabled` and `drift` appeared in no source
    file. So D14's own sentence — *"the learning loop enabled, entirely in
    YAML"* — was false, and D23's *"normative change-classification function"*
    was a hardcoded Python tuple.
    """

    #: `learning.enabled`, and now the WHOLE of that decision — one of
    #: [`ENABLED_CHOICES`]. `off` refuses to run a cycle at all. Empty means NO
    #: `learning.yaml` was read — a caller driving `Learner` by hand has taken
    #: the decision itself, and inventing a gate it never asked for would be a
    #: governance decision made on its behalf. A workspace that has a
    #: `learning:` block always sets this, because the schema requires it.
    #:
    #: `auto_apply: bool` used to sit beside it, read from `auto-apply:`. Two
    #: fields for one decision is two chances to disagree, and the disagreement
    #: was silent in both directions — see [`ENABLED_CHOICES`].
    enabled: str = ""
    #: `keep-only-if`. `a-person-approves-it` means nothing auto-applies.
    keep_only_if: str = ""
    low: tuple[str, ...] = ()
    high: tuple[str, ...] = ()
    max_drift: float = 0.5
    #: `cycle-limits.per-cycle` — how many improvements one round may APPLY.
    #: `None` means the author wrote none. The whole `cycle-limits:` group was
    #: two `tier: core`, `S-GOV` ceilings on a self-modifying system that
    #: appeared in no source file anywhere, and unlike every other unenforced
    #: ceiling in this project it was not even named on the honest-reporting
    #: door.
    per_cycle: int | None = None
    #: `cycle-limits.evals` — how many scoring runs one round may spend.
    evals_at_most: int | None = None
    #: `cycle-limits.per-month`, exactly as the author wrote it — `20 USD`.
    #:
    #: Kept as the author's own text because two readers want it: the comparison
    #: wants the amount, and every sentence a person reads wants the line they
    #: typed. It used to be recorded and never held, on the argument that
    #: *"nothing here sees a month"* — see [`MonthlySpend`] for why that argument
    #: was wrong in one place.
    per_month: str = ""
    #: Whether a `may-improve-on-its-own:` line was WRITTEN, as opposed to a
    #: caller building `Permissions` by hand. The distinction is the whole of the
    #: fix: `of()` returned `None` for a field not on the list, which is exactly
    #: what it returns when there is no list at all, so writing the line changed
    #: nothing. Measured with `may-improve-on-its-own: []` beside the
    #: self-applying answer (`auto-apply: yes` then; `enabled:
    #: applies-safe-changes-itself` now), an instructions edit came back
    #: `risk=low needs_a_person=False` and `Learner.cycle` applied it with no
    #: person — the empty list granting everything, which is the outcome the
    #: field's own help says it exists to prevent.
    stated: bool = False

    @staticmethod
    def default() -> "Permissions":
        """What applies when the author wrote no `learning.yaml` at all.

        The hardcoded lists survive HERE and only here — as the answer for a
        workspace that said nothing, which is the one case where a built-in
        conservative default is the honest thing rather than a policy nobody
        wrote.
        """
        return Permissions(high=HIGH_RISK_FIELDS)

    @staticmethod
    def from_document(doc: Mapping[str, Any]) -> "Permissions":
        block = doc.get("learning")
        if not isinstance(block, Mapping) or not block:
            # No `learning.yaml` at all. Nothing here says anything about
            # self-improvement, so the built-in blast-radius lists apply and the
            # document-level gates do not exist to be read.
            return Permissions.default()
        drift = block.get("drift") or {}
        at_most = drift.get("at-most") if isinstance(drift, Mapping) else None
        cycles = block.get("cycle-limits") or {}
        if not isinstance(cycles, Mapping):
            cycles = {}
        return Permissions(
            enabled=str(block.get("enabled", PROPOSE_ONLY)).strip(),
            keep_only_if=str(block.get("keep-only-if", "")).strip(),
            low=tuple(_as_list(block.get("may-improve-on-its-own"))),
            # Anything the author named as needing a person, PLUS the built-in
            # list. A workspace may widen what needs review and may not narrow
            # it: `needs-a-person-to-approve: []` must not make `tools:`
            # auto-appliable.
            high=tuple(dict.fromkeys(_as_list(block.get("needs-a-person-to-approve")) + list(HIGH_RISK_FIELDS))),
            max_drift=_share(at_most, 0.5),
            stated="may-improve-on-its-own" in block,
            per_cycle=_whole(cycles.get("per-cycle")),
            evals_at_most=_whole(cycles.get("evals")),
            per_month=str(cycles.get("per-month") or "").strip(),
        )

    def of(self, field: str) -> Classification | None:
        """This field's class from the author's own lists, or `None` for prose."""
        if field in self.high:
            return Classification(
                Risk.HIGH,
                f"'{field}' is on `needs-a-person-to-approve:`, so a person decides",
            )
        if field in self._allowed():
            return None  # named as safe: fall through to the prose check
        if self.stated:
            # A list was written, and this field is not on it. That is the whole
            # point of writing one: `may-improve-on-its-own:` NARROWS. Falling
            # through here — which is what happened for a round — made writing
            # the line indistinguishable from omitting it.
            return Classification(
                Risk.HIGH,
                f"'{field}' is not on `may-improve-on-its-own:`, so a person decides",
            )
        if field in HIGH_RISK_FIELDS:
            return Classification(
                Risk.HIGH, f"'{field}' changes what the agent can do, not how it words things"
            )
        return None

    def _allowed(self) -> frozenset[str]:
        """The FIELDS the author's four choices name.

        The schema's vocabulary is written for whoever reads the file
        (`phrasing`, `examples`, `skill-notes`, `when-skills-are-used`); the
        classifier works on field names. One mapping, here, so the two cannot
        drift — and a value not in the mapping is kept as itself, so a caller
        constructing `Permissions` in memory with a raw field name still works.
        """
        out: set[str] = set()
        for word in self.low:
            out.update(SAFE_TO_CHANGE.get(word, (word,)))
        return frozenset(out)

    def may_apply_without_a_person(self) -> str:
        """Why nothing may take effect without a person, or `""` when something may.

        `enabled:` is the whole of this decision now, and exactly one of its
        three answers opens the door. It used to take two lines that could
        disagree — see [`ENABLED_CHOICES`] — and both lines were read by nobody
        for a round: the shipped `learning.yaml` said `enabled: propose-only`,
        `auto-apply: no` and `keep-only-if: a-person-approves-it`, and
        `Learner.cycle` applied an instructions edit with `applied=True` and no
        person involved.
        """
        if not self.enabled:
            return ""  # no document said; the caller decided
        if self.enabled == OFF:
            return "`enabled: off` — the learning loop is switched off"
        if self.enabled == PROPOSE_ONLY:
            return "`enabled: propose-only` — improvements are proposed and a person applies them"
        if self.enabled != APPLIES_ITSELF:
            # Fail CLOSED on a word this file does not have. `pact check` refuses
            # it where the author is, and this is the twin refusal one language
            # over — deliberately, the way every other paired check in PACT is,
            # so the author cannot tell which half stopped them. It matters most
            # for the spelling that was legal last version: `enabled: yes` used
            # to be a choice, it now means nothing, and a stale file falling
            # through to `return ""` would hand a self-rewriting agent the one
            # permission its own file no longer grants.
            return (
                f"`enabled: {self.enabled}` is not something learning can be — "
                f"write one of: {', '.join(ENABLED_CHOICES)}"
            )
        if self.keep_only_if == "a-person-approves-it":
            return "`keep-only-if: a-person-approves-it` — a score is not an approval"
        return ""

    def per_month_cap(self) -> "tuple[float, str] | None":
        """The monthly spend ceiling as an amount and the currency it is in.

        `limits.money` and not a second parser, for the reason that module gives:
        it is the one reader of a money value in this package, it takes all three
        spellings the schema's own help offers (`20 USD`, `USD 20`, `$20`), and
        it keeps the currency instead of assuming one. A second copy here is how
        `500 JPY` came to be compared against a meter priced in USD.

        **The currency is not converted and must not be.** `pact check` already
        refuses a money figure written in a currency this workspace's price list
        cannot charge in — `loader/currency-nothing-can-price`, which names
        `learning.cycle-limits.per-month` by name — so by the time a cycle runs,
        the cap and the meter are in the same money. This half only carries the
        word, so the sentence a person reads names the currency they wrote.

        **A figure no spend can ever cross is not returned at all.** That is
        [`Permissions.per_month_holds_nothing`], and it is the decision
        `Limits.__post_init__` already makes one module over for
        `cost-per-request-under`: a cap nothing can be compared against is not a
        loose cap, it is no cap, and carrying it as one is how a cycle comes to
        report a ceiling it never held. Measured before this, three real cycles
        against a real workspace ledger with `per-month: NaN USD`:

            cycle 1: month_total=8.0   unmeasured=()
            cycle 2: month_total=16.0  unmeasured=()
            cycle 3: month_total=24.0  unmeasured=()

        against the same three under the author's own `20 USD`, where the third
        is refused at `16.00 USD`. Twenty-four dollars of self-improvement under
        a ceiling every outcome stayed silent about. The enforcement site
        compares `would_reach > amount` and every comparison against a NaN is
        false, so the refusal below it never ran; `_unmeasured` enumerated three
        reasons the ceiling can fail to bite and this was a fourth.
        """
        cap = money(self.per_month) if self.per_month else None
        if cap is not None and _nothing_can_reach(cap[0]):
            return None
        return cap

    def per_month_holds_nothing(self) -> bool:
        """Did the author write a monthly ceiling no spend can ever cross?

        `limits._nothing_can_reach` and not a second test, for the reason that
        function gives itself: `nan` and `inf` are the two figures no spend can
        be at or above, and `-inf` is deliberately NOT one of them because a run
        reaches it immediately — a wrong ceiling, not an absent one. The
        comparison here is `>` and the one there is `>=`, and the answer is the
        same on both: `would_reach > nan` and `would_reach > inf` are false at
        every spend there is, `would_reach > -inf` is true at every spend.

        `True` only when something WAS written. A workspace with no
        `cycle-limits.per-month` line has no ceiling it failed to hold, and
        saying so would put a sentence on every cycle that never asked for one.
        """
        cap = money(self.per_month) if self.per_month else None
        return cap is not None and _nothing_can_reach(cap[0])


def _as_list(v: Any) -> list[str]:
    if isinstance(v, str):
        return [v]
    return [str(x) for x in (v or [])]


def _whole(v: Any) -> int | None:
    """A whole number the author wrote, or nothing. Out of range is refused by
    the schema (`at-least: 1`) where the author is."""
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _share(v: Any, default: float) -> float:
    """`50%` or `0.5`. Out of range is refused where the author is, by the schema."""
    if isinstance(v, str) and v.strip().endswith("%"):
        try:
            return float(v.strip().rstrip("%")) / 100.0
        except ValueError:
            return default
    if isinstance(v, (int, float)) and 0.0 <= float(v) <= 1.0:
        return float(v)
    return default


#: Where a month's running total is kept, relative to the workspace root.
#:
#: Under `.pact/` for the reason `watches.UNDER` gives: the loader skips any name
#: beginning with a dot (`Policy::is_ignored`), so a workspace that has improved
#: itself still loads and still passes `pact check`. D2 says deleting `.pact/`
#: must be harmless, and it is — the total goes back to zero and the month starts
#: again, which is the honest reading of a workspace whose record somebody threw
#: away.
UNDER = Path(".pact") / "learning"


def _append(root: Path, name: str, row: dict) -> None:
    """One line onto a ledger, or nothing if this workspace cannot be written to.

    Register row C8: a read-only checkout — a container image, a signed release,
    anything mounted `ro` — could not keep either of these records, and found out
    by raising. A learning cycle that fails because it could not write down that
    it happened has turned a bookkeeping problem into a run failure.

    `$PACT_DERIVED_DIR` redirects the whole derived area, which is how a
    read-only tree is run: point it somewhere writable rather than copying the
    tree. Shared with `watches.derived_area` so the two halves of `.pact/` cannot
    end up in different places.
    """
    from .watches import DERIVED_DIR

    override = os.environ.get(DERIVED_DIR, "").strip()
    area = (Path(override) if override else Path(root)) / UNDER
    try:
        area.mkdir(parents=True, exist_ok=True)
        with (area / name).open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")
    except OSError:
        # Reported by `Learner._unmeasured`, which already says a month cannot be
        # kept when there is nowhere to keep it — this is the same fact arriving
        # from a different direction.
        return

#: The file the running total is appended to. One line per cycle.
LEDGER = "spend.jsonl"

#: Where refused proposals are remembered, beside the spend ledger and for the
#: same reason: a `Learner` is one cycle, and what has to survive a cycle has to
#: survive the process.
REFUSALS = "refused.jsonl"


@dataclass
class Refusals:
    """What this workspace has already refused, and why (AC-5.5).

    **`Learner.rejected` was a list nothing read.** Its own comment beside the
    append said the purpose — *"a rejected candidate that is simply forgotten
    will be proposed again next cycle"* — and forgetting was exactly what
    happened twice over: nothing consulted the list, and a `Learner` is built
    fresh per cycle, so it did not outlive the process that made it.

    A repeat proposal is refused HERE, before the evals run, which is the whole
    value: the expensive part of finding out that an edit does not help is
    finding out, and doing it twice is paying twice for one answer. The reason
    the first refusal gave is handed back, so a reviewer sees why rather than
    just that.

    Keyed on the field and the exact text proposed. Not on the diff: two authors
    writing the same replacement from different starting points are proposing the
    same thing, and the second one should be told what the first one was told.
    """

    root: Path | None = None
    #: `{key: (why, when)}` for everything refused in this workspace.
    seen: dict[str, tuple[str, str]] = field(default_factory=dict)

    @staticmethod
    def at(root: "str | Path | None") -> "Refusals":
        r = Refusals(root=Path(root) if root else None)
        r.reread()
        return r

    @property
    def kept(self) -> bool:
        """Whether there is anywhere to remember a refusal at all.

        `False` is an ordinary state, not a failure — invariant P-1 says an
        adapter may be handed the document without the tree, and then there is
        nowhere to keep anything. A cycle in that state simply cannot recognise a
        repeat, which `Learner._unmeasured` says out loud.
        """
        return self.root is not None

    @staticmethod
    def key(proposal: "Proposal") -> str:
        """One proposed edit, as the thing that gets recognised again."""
        return f"{proposal.field}\n{proposal.after.strip()}"

    def why(self, proposal: "Proposal") -> "tuple[str, str] | None":
        """`(reason, when)` if this exact edit has been refused before."""
        return self.seen.get(self.key(proposal))

    def reread(self) -> None:
        self.seen = {}
        if self.root is None:
            return
        path = self.root / UNDER / REFUSALS
        if not path.exists():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                # A half-written line from a cycle somebody killed. Skipped for
                # the reason `MonthlySpend.reread` gives: erring towards letting
                # a cycle run beats refusing to start because the record is
                # scuffed. The cost here is one repeated proposal, not money.
                continue
            if not isinstance(row, Mapping) or "key" not in row:
                continue
            self.seen[str(row["key"])] = (
                str(row.get("why") or ""), str(row.get("when") or "")
            )

    def add(self, proposal: "Proposal", why: str, today: "date | None" = None) -> None:
        """Write down that this edit was refused, and what for.

        Append-only, like the spend ledger — a refusal that can be edited away is
        not a record. The newest line wins on read, so a proposal refused for one
        reason and later for another is remembered by the later one.
        """
        if self.root is None:
            return
        when = (today or date.today()).isoformat()
        row = {"key": self.key(proposal), "why": why, "when": when}
        # In memory first, so a workspace that cannot be written to still refuses
        # a repeat WITHIN one process. Losing the record across processes is a
        # cost; losing it inside one would mean scoring the same proposal twice
        # in a single cycle.
        self.seen[self.key(proposal)] = (why, when)
        _append(self.root, REFUSALS, row)


@dataclass
class MonthlySpend:
    """What improving this system has cost so far this calendar month.

    A `Learner` is ONE cycle — that is what makes `cycle-limits.per-cycle`
    countable on it at all — so a month is by definition bigger than one, and for
    a round that was the whole argument for `per-month` being *"recorded and NOT
    held"*. The argument was wrong in exactly one place: the running total does
    not have to live in the PROCESS, it has to live in the WORKSPACE, which is
    where `watch:` already keeps a record of what a run did and for the same
    reason.

    Three properties, none of them free:

    * **It survives the cycle.** One append-only file under the workspace's own
      `.pact/` area, so next Friday's cycle can see what last Friday's cost.
    * **It carries no words.** A month, an amount and a count of scoring runs.
      The failing conversations a cycle learns from are the customer's own words
      (§8.8 requirement 3) and none of them come near this file — the same
      allow-list argument `watches.RECORDED` makes, settled here by there being
      nothing else to write.
    * **It is air-gapped (D17).** A local file. No service, no collector, and
      nothing that stops working on a machine with no network.
    """

    #: The workspace root, or `None` when the caller was handed the document
    #: without the tree. Invariant P-1 says that is always allowed, so `None` is
    #: an ordinary state and not a failure — it means there is nowhere to keep a
    #: month, which `Learner._unmeasured` says out loud rather than enforcing the
    #: ceiling against a total that starts at zero in every process.
    root: "Path | None" = None
    #: What day it is. A function so a test can walk a month forward without
    #: waiting for one — the same seam `harness.run` takes as `clock`.
    today: Callable[[], date] = date.today
    #: Money spent on scoring THIS month, in the currency the price list charges
    #: in. Zero is a real answer: it is what a workspace on its first cycle of
    #: the month has spent, and also what a locally-served model costs.
    money: float = 0.0
    #: Scoring runs made this month. Kept beside the money because the two
    #: together are what let a cycle forecast its own cost before spending it.
    runs: int = 0

    @staticmethod
    def at(root: "str | Path | None") -> "MonthlySpend":
        """The running total this workspace has, read off disk."""
        m = MonthlySpend(root=Path(root) if root else None)
        m.reread()
        return m

    @property
    def kept(self) -> bool:
        """Whether there is anywhere to keep a month's total at all."""
        return self.root is not None

    @property
    def per_run(self) -> float:
        """What one scoring run has cost on average this month.

        Zero when nothing has been scored yet, and that is the honest forecast
        for the first cycle of a month: refusing on no evidence would refuse the
        one cycle that produces the evidence, and the cap would then bite hardest
        on the workspace that had spent nothing.
        """
        return self.money / self.runs if self.runs else 0.0

    def key(self) -> str:
        """`2026-07` — which month a row belongs to."""
        return self.today().strftime("%Y-%m")

    def in_words(self) -> str:
        """`July 2026` — the month as a person says it."""
        return self.today().strftime("%B %Y")

    def next_in_words(self) -> str:
        """`August` — when the ceiling lifts, so a refusal can say when."""
        d = self.today()
        return date(d.year + (d.month == 12), d.month % 12 + 1, 1).strftime("%B")

    def reread(self) -> None:
        """Add up this month's rows again from the file."""
        self.money, self.runs = 0.0, 0
        if self.root is None:
            return
        path = self.root / UNDER / LEDGER
        if not path.exists():
            return
        this = self.key()
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                # A half-written line from a cycle somebody killed. Skipped
                # rather than raised: the ceiling reads LOW by whatever that line
                # held, which errs towards letting a cycle run, and a self-
                # improvement loop that refuses to start because its own record
                # is scuffed is a worse failure than one that spends a little
                # over. `pact check` never reads this file, so there is nobody
                # else to tell.
                continue
            if not isinstance(row, Mapping) or row.get("month") != this:
                continue
            self.money += float(row.get("money") or 0.0)
            self.runs += int(row.get("runs") or 0)

    def add(self, spent: float, runs: int) -> None:
        """Write down what one cycle cost, and count it against this month.

        Opened, appended and closed per line rather than held open, for the
        reason `Watches._writer` gives: a cycle can be stopped part-way, and a
        record that only reaches the disk when a handle closes is not there when
        somebody asks what was spent before it stopped.
        """
        self.money += float(spent)
        self.runs += int(runs)
        if self.root is None:
            return
        _append(
            self.root,
            LEDGER,
            {"month": self.key(), "money": float(spent), "runs": int(runs)},
        )


@dataclass
class Baseline:
    """The frozen reference a cycle is measured against.

    Held separately from the current spec so *cumulative* drift is measurable.
    Comparing only against the previous version is how a series of individually
    reasonable edits walks an agent somewhere nobody approved.
    """

    instructions: str
    score: float
    generation: int = 0


@dataclass
class Outcome:
    applied: bool
    reason: str
    classification: Classification
    before_score: float = 0.0
    after_score: float = 0.0
    drift: float = 0.0
    verdict_before: Verdict | None = None
    verdict_after: Verdict | None = None
    #: How many cases were held out — the frozen split both scoring runs were
    #: measured on.
    #:
    #: Carried rather than counted off `verdict_after.results`, which is what the
    #: report did. The two agree on this path because `cycle` scores against
    #: `self.holdout` and `_score` returns one result per case, and nothing held
    #: them together — so AC-3.5's own *"is this enough to mean anything"* gate
    #: was reading a stand-in for the split rather than the split. A scoring run
    #: that graded more than was held out would have reported a three-case split
    #: as big enough to claim on, which is the one arrangement where the claim is
    #: certainly wrong.
    #:
    #: **Set in exactly one place** — [`Learner.cycle`] stamps it onto every
    #: answer `_decide` returns. The default below is the value that under-claims
    #: rather than over-claims, and it is still not a value a cycle should ever
    #: produce: `_decide` refuses before scoring when nothing is held out, so an
    #: `Outcome` carrying two verdicts and a zero here has lost the count on the
    #: way out. `scoring._margin_line` says so rather than printing it.
    held_out: int = 0
    #: Ceilings the author wrote that nothing in this process can measure, in
    #: their own words. Every other unenforced ceiling in PACT is named on
    #: `RunResult.unmetered`; `cycle-limits.per-month` had no such door, so a
    #: reviewer reading a cycle could not tell an enforced spend cap on
    #: self-improvement from an assumed one.
    unmeasured: tuple[str, ...] = ()

    @property
    def ungraded(self) -> list[str]:
        """Every written rule neither scoring run could apply, once each.

        A cycle promotes a variant on a NUMBER, and a `judged:` rule nobody
        graded is silently absent from that number — so the decision reads as
        "the suite improved" when what improved is the part of the suite anything
        could measure. Read off the verdicts rather than recomputed, so it cannot
        disagree with the score it qualifies, and surfaced here because `Outcome`
        is what a caller looks at.
        """
        out: list[str] = []
        for scored in (self.verdict_before, self.verdict_after):
            for sentence in scored.unenforced if scored is not None else []:
                if sentence not in out:
                    out.append(sentence)
        return out


@dataclass
class Learner:
    """Runs one improvement cycle under the three gates."""

    spec: AgentSpec
    train: list[Case]
    holdout: list[Case]          # frozen BEFORE the cycle; never optimised against
    rules: list[str]
    bar: float
    tools: dict[str, Callable[[dict], str]]
    #: Who grades the suite's `judged:` rules, or nothing.
    #:
    #: Same shape as `tools` — supplied by whoever runs the cycle, built from the
    #: author's `graded-by:` line by `judge.judge_of(doc)`. `None` is honest and
    #: is the ordinary case on a box with no second model; what it must never be
    #: is silent, which is why `Outcome` now carries what went ungraded. Without
    #: this field `_score` called `check(...)` with no judge at all, so every
    #: `judged:` rule landed on `Verdict.unenforced`, nothing printed it, and a
    #: cycle could promote a variant on a suite whose written rule nobody had
    #: applied.
    judge: Any = None
    #: The suite's own `metrics:` line, read off the document by
    #: [`Learner.from_document`]. Beside `rules` because it is the same kind of
    #: thing: part of what the author wrote down as "working". A cycle that
    #: promoted a variant against the rules and not the scores would be gating
    #: self-modification on a smaller suite than the one in the folder.
    metrics: Any = None
    baseline: Baseline | None = None
    #: Proposals refused in THIS process. In-memory and per-cycle; what has to
    #: survive a cycle is `refusals` below, because a `Learner` is one cycle.
    rejected: list[Proposal] = field(default_factory=list)
    #: What this workspace has already refused, across cycles (AC-5.5).
    refusals: "Refusals" = field(default_factory=Refusals)
    #: What `learning.yaml` says. Built from the document by
    #: [`Learner.from_document`]; the built-in defaults apply when nobody wrote
    #: one.
    permissions: Permissions = field(default_factory=Permissions.default)

    #: How far from the frozen baseline before a person re-baselines.
    #:
    #: `None` means "whatever `learning.yaml` says", which is the ordinary case.
    #: It was a hardcoded `0.5` while `learning.drift:` was `map of anything`
    #: read by nobody, so the one number governing how far a self-improving agent
    #: may walk lived in Python and not in the file the reviewer reads.
    max_cumulative_drift: float | None = None

    #: How many proposals this learner has APPLIED since it was built. One
    #: `Learner` is one cycle, which is what makes `cycle-limits.per-cycle`
    #: countable here at all.
    applied_this_cycle: int = 0
    #: How many scoring runs it has spent, against `cycle-limits.evals`.
    evals_spent: int = 0
    #: What those scoring runs cost, as far as anything could price them.
    #: Against `cycle-limits.per-month`, via [`MonthlySpend`] — the running total
    #: this cycle adds to and is refused by.
    money_spent: float = 0.0
    #: This month's running total, kept in the workspace. Built from
    #: `spec.workspace` by [`Learner.from_document`]; the default here keeps
    #: nothing, which is the honest answer for a caller driving `Learner` by hand
    #: and is what `_unmeasured` reports rather than enforcing a month against a
    #: total that starts at zero every process.
    month: MonthlySpend = field(default_factory=MonthlySpend)
    #: Whether every transport this cycle scored through could put a price on its
    #: calls. `None` until something has been scored, which is a third state and
    #: not a false: an early refusal has priced nothing and knows nothing, and
    #: saying "nobody could price this" there would be a guess.
    #:
    #: Asked of the transport in the same two steps `harness.run` asks it in
    #: (`harness.py`: `reports_usage` then `prices_money`), because a spend
    #: ceiling held against a transport that reports no money is a ceiling that
    #: silently never fires — which is the whole reason `RunResult.unmetered`
    #: exists one layer down.
    priced: "bool | None" = None

    @property
    def drift_limit(self) -> float:
        return (
            self.max_cumulative_drift
            if self.max_cumulative_drift is not None
            else self.permissions.max_drift
        )

    @staticmethod
    def from_document(
        doc: Mapping[str, Any],
        spec: AgentSpec,
        tools: dict[str, Callable[[dict], str]],
        cases: list[Case] | None = None,
        bar: float | None = None,
        judge: Any = None,
    ) -> "Learner":
        """Build a learner from the author's own files.

        The split comes from the cases' own `split:` lines — the loop's first
        named gate is *"a frozen held-out split, locked before the cycle
        starts"*, and it was satisfied by whatever a host hand-assembled because
        `Case` had nowhere for `split:` to land.

        `judge` is handed in rather than built here, the same way `tools` is:
        reaching a grader means reaching a model, and this is a pure read of the
        document. `judge.judge_of(doc)` is what builds one from `graded-by:`.
        """
        from .evals import Case as _Case, bar_of, metrics_of, rules_of, split as _split

        all_cases = cases if cases is not None else _Case.from_document(doc)
        held = _split(all_cases, "held-out")
        return Learner(
            spec=spec,
            # With no `split:` written anywhere every case trains and nothing is
            # held out, which is the honest reading of a suite that never said.
            train=_split(all_cases, "train"),
            holdout=held,
            rules=rules_of(doc),
            metrics=metrics_of(doc, spec.workspace),
            bar=bar if bar is not None else bar_of(doc),
            tools=tools,
            judge=judge,
            permissions=Permissions.from_document(doc),
            # The month's running total comes from the workspace the spec was
            # loaded out of. Empty is normal — invariant P-1 says an adapter may
            # be handed only the document — and it means the month cannot be
            # kept, which `_unmeasured` says in words rather than pretending.
            month=MonthlySpend.at(spec.workspace),
            # Read from the same workspace area the month's spend is kept in.
            # Empty is normal — invariant P-1 says an adapter may be handed only
            # the document — and it means a repeat cannot be recognised, which
            # `_unmeasured` says rather than pretending.
            refusals=Refusals.at(spec.workspace),
        )

    def _unmeasured(self) -> tuple[str, ...]:
        """Ceilings the author wrote that this cycle could not hold.

        `cycle-limits.per-month` used to be here unconditionally, with the
        sentence *"nothing here counts a month's spend"*. That is no longer true:
        [`MonthlySpend`] keeps the running total in the workspace's own
        `.pact/learning/` area and [`Learner.cycle`] refuses a cycle that would
        cross the cap. So the field is now empty in the ordinary case, which is
        what makes it worth reading — a door that is always open tells a reviewer
        nothing.

        FOUR things can still stop the ceiling biting. They are four different
        facts with four different fixes, so each gets its own sentence rather
        than one that covers all of them — the distinction `RunResult.unmetered`
        and `RunResult.never_reached` already make one layer down, where
        *"nobody could count it"* and *"the count is right and the answer is
        always zero"* would send an author looking in two different places.

        **The first of the four is the only one that is a mistake in the file**,
        and it is the one this docstring claimed did not exist. The other three
        are facts about the WORLD — no workspace folder, no price list, a price
        list that honestly charges nothing — and in every one of them the line
        the author wrote is a good line that this cycle cannot hold, so the cycle
        runs and is told so. A figure that is not a figure is not that: nothing
        about the environment would make `per-month: NaN USD` hold, so it is also
        the one of the four that REFUSES the cycle ([`Learner._decide`]) rather
        than reporting past it. It stays on this channel as well, because a
        reviewer reading `Outcome.unmeasured` for "which ceilings held" must not
        get an empty tuple for the one ceiling that held nothing at all.

        Measured before it existed, three real cycles against a real ledger with
        `per-month: NaN USD` built in code: `month_total` 8.0, 16.0, 24.0, and
        `unmeasured=()` on every one of them.
        """
        wrote = self.permissions.per_month
        if not wrote:
            return ()
        if self.permissions.per_month_holds_nothing():
            return (
                f"cycle-limits.per-month: {wrote} — no amount of money can ever be "
                f"above this, so it is not a ceiling improving can run out against "
                f"and nothing was held against it. Fix: write the most improving "
                f"may cost in a month as an amount — `cycle-limits: "
                f"{{ per-month: 20 USD }}` — or remove the line.",
            )
        if not self.month.kept:
            return (
                f"cycle-limits.per-month: {wrote} — this cycle was handed the "
                f"agent's settings without the folder they came from, so there is "
                f"nowhere to keep what improving has cost so far this month and the "
                f"ceiling is recorded rather than held. Fix: run the cycle against "
                f"the workspace folder, so the total can be kept in its own "
                f"`.pact/learning/` area beside it.",
            )
        if self.priced is False:
            return (
                f"cycle-limits.per-month: {wrote} — nothing could put a price on the "
                f"model calls this cycle made, so the month's total does not move "
                f"and this ceiling can never be reached. Fix: add a `cost:` block "
                f"for the model that does the work to `models/catalog.yaml`.",
            )
        if self.priced and self.month.runs and self.month.money == 0.0:
            # The `never_reached` fact, one layer up. Nothing failed to measure:
            # the count is right and the price is a sourced zero, which is what
            # five of the nine rows in `models/catalog.yaml` publish because this
            # machine serves them. Telling the author "nobody could measure it"
            # would send them looking for a transport rather than for the ceiling
            # that still works.
            return (
                f"cycle-limits.per-month: {wrote} — every model call counted this "
                f"month was priced at nothing, so the total is 0.00 and this "
                f"ceiling can never be reached. Nothing failed: the model doing "
                f"the work is served on this machine and costs nothing per word. "
                f"Fix: set `cycle-limits.evals:` beside it, which is the ceiling "
                f"that still bites when there is no bill.",
            )
        return ()

    def _score(self, spec: AgentSpec, cases: list[Case], transport_for) -> Verdict:
        import asyncio

        results: list[CaseOutcome] = []
        self.evals_spent += len(cases)
        # Suppressed for the same declared reason as `resolve.evaluate`: a run
        # that parks for a person cannot be scored, and a learning cycle that
        # scored a policy park as a bad answer would optimise the policy away.
        ungated = spec.asking.asking_only()
        for case in cases:
            transport = transport_for(spec)
            # Whether anything can put a price on what this call carries, asked
            # in the same two steps and the same order `harness.run` asks it in:
            # a token count is knowable whenever a call is made, a price only if
            # the catalogue publishes one. Read BEFORE the run, off the transport
            # the run is about to use, so a cycle whose money reads 0.00 can tell
            # "the model is free" from "nobody could count it" — the distinction
            # `Limits.unmeterable` and `Limits.priced_at_nothing` already make,
            # and the one that decides whether `per-month` is a held ceiling or
            # a number in a file.
            # `False`, not `counts`, and it is the same default `harness.run`
            # uses — the two have to agree or one cycle's `per-month` means
            # something different from the run inside it. Reading the money
            # answer off the token answer is the B6 defect; the reason it is a
            # defect and not a convenience is argued in full at that line.
            counts = callable(getattr(transport, "usage", None))
            prices = bool(getattr(transport, "prices_money", False))
            self.priced = prices if self.priced is None else (self.priced and prices)
            result = asyncio.run(
                run(spec, transport, case.when, self.tools, asking=ungated)
            )
            # What the scoring cost, on the meter `cycle-limits.per-month` reads.
            # `RunResult.spent` is the run's own meter rather than a second sum,
            # for the reason that property gives: a second copy is how a figure
            # comes to disagree with itself.
            self.money_spent += result.spent
            results.append(
                check(case, result, self.rules, judge=self.judge, metrics=self.metrics)
            )
        return verdict(results, self.bar, min_cases=1)

    def cycle(self, proposal: Proposal, transport_for) -> Outcome:
        """Evaluate one proposal. Returns what happened and why.

        Two lines, and the second one is the whole reason this wrapper exists.

        `_decide` has twelve exits, and the held-out count belongs on every one
        of them — it is what [`Outcome.held_out`] carries, and what AC-3.5's
        *"is this enough to mean anything"* gate is answered from. Written at
        each exit it was written twelve times, and twelve copies of one fact
        agree only until somebody adds a thirteenth exit or edits one of the
        twelve. That is not hypothetical: three of them were measured missing
        while every test of the count passed, because the tests all came out of
        the same branch and the field's default quietly reported a real
        three-case split as *"over 0 held-out case(s)"* — a false number that
        reads as caution rather than as a bug.

        So it is stamped here, once, onto whatever answer came back. There is
        one line to get wrong instead of twelve, and no exit can be added that
        forgets it.
        """
        from dataclasses import replace

        return replace(
            self._decide(proposal, transport_for), held_out=len(self.holdout)
        )

    def _decide(self, proposal: Proposal, transport_for) -> Outcome:
        """Which answer this proposal gets, and why. See [`cycle`].

        Private because the count `cycle` stamps is part of the answer: an
        `Outcome` from here has not been told how big the split was, and a
        reader who took one would be reading the field's default rather than
        the author's frozen split.
        """
        cls = classify(proposal, self.permissions)

        # Whether this process can put such a change into effect at all, asked
        # before anything else because it is the one answer that does not depend
        # on the author's settings: turning `enabled:` on would not make a
        # `description` edit reach a model. Free, and it saves two full scoring
        # runs whose result was decided before they started.
        if proposal.field not in CAN_BE_APPLIED:
            self.rejected.append(proposal)
            # A high-risk field is HELD, and that sentence must not be masked by
            # a mechanical limitation of this process. `uses:`, `tools:` and
            # `policy:` are exactly what the classifier exists for, and the first
            # version of this check answered a proposed `uses:` change with
            # "nothing in a run reads it" — which is both the wrong answer for a
            # reviewer and, for `uses:`, simply false: it is the skills the agent
            # may read. What is true is narrower, and is said below.
            if cls.needs_a_person:
                return Outcome(
                    False, f"held for review: {cls.reason}", cls,
                    unmeasured=self._unmeasured(),
                )
            if proposal.field in READ_BY_NO_RUN:
                # The reason that is TRUE about this field, rather than a
                # sentence about which fields this process happens to rewrite —
                # a reviewer reading the second one learns nothing about their
                # own document.
                return Outcome(
                    False,
                    f"a change to `{proposal.field}` cannot be put into effect here: "
                    f"{READ_BY_NO_RUN[proposal.field]} — so no run reads it, and both "
                    f"scoring runs would grade the same agent. A cycle rewrites "
                    f"{', '.join(CAN_BE_APPLIED)}.",
                    cls, unmeasured=self._unmeasured(),
                )
            return Outcome(
                False,
                f"a cycle rewrites {', '.join(CAN_BE_APPLIED)} and nothing else, "
                f"so a change to `{proposal.field}` cannot be put into effect "
                f"here — both scoring runs would grade the same agent.",
                cls, unmeasured=self._unmeasured(),
            )

        # Whether this exact edit has been refused before. FIRST among the paid
        # gates, because the expensive part of learning that a proposal does not
        # help is finding out, and finding out twice is paying twice for one
        # answer. The reason the first refusal gave is handed back, so a reviewer
        # sees why rather than merely that.
        #
        # `Learner.rejected` was supposed to be this and was a list nothing read —
        # its own comment said *"a rejected candidate that is simply forgotten
        # will be proposed again next cycle"*, and forgetting happened twice
        # over: nothing consulted the list, and a `Learner` does not outlive the
        # cycle that made it.
        seen_before = self.refusals.why(proposal)
        if seen_before is not None:
            why, when = seen_before
            self.rejected.append(proposal)
            return Outcome(
                False,
                f"this exact change was refused on {when} and nothing has been "
                f"spent on it again. It was refused because: {why}",
                cls, unmeasured=self._unmeasured(),
            )

        # What the author's own `learning.yaml` says about applying anything at
        # all, checked BEFORE the evals are run: `enabled: off` means no cycle,
        # and running one to reject it afterwards would spend the money the line
        # exists to save.
        if self.permissions.enabled == OFF:
            self.rejected.append(proposal)
            return Outcome(
                False, "the learning loop is switched off (`enabled: off`)", cls,
                unmeasured=self._unmeasured(),
            )

        # The module's own first named gate — *"a frozen held-out split, locked
        # before the cycle starts"* — asked rather than assumed.
        #
        # With no `split:` written anywhere, `from_document` holds nothing out,
        # which is the honest reading of a suite that never said. But then both
        # scoring runs grade zero cases, and the answer below was `held-out score
        # did not improve (0% → 0%)`: a true sentence whose plain reading is "we
        # measured, and it was a tie". Nothing was measured. The shipped example
        # took exactly this path, so the one gate that decides whether an
        # improvement IS one was inert on the only tree in the repository.
        if not self.holdout:
            self.rejected.append(proposal)
            return Outcome(
                False,
                "nothing is held out, so whether this proposal improves the agent "
                "cannot be measured — both scoring runs would grade zero cases. "
                "Fix: mark some of your `cases:` with `split: held-out`, and keep "
                "them out of the ones the proposal was written from.",
                cls, unmeasured=self._unmeasured(),
            )

        # And the two ceilings on how much improving one round may do. Before the
        # evals for the same reason `enabled: off` is: refusing afterwards would
        # spend exactly the budget the line exists to cap.
        if (
            self.permissions.per_cycle is not None
            and self.applied_this_cycle >= self.permissions.per_cycle
        ):
            self.rejected.append(proposal)
            return Outcome(
                False,
                f"`cycle-limits.per-cycle: {self.permissions.per_cycle}` — this round "
                f"has already applied that many improvements",
                cls, unmeasured=self._unmeasured(),
            )
        runs_this_proposal = 2 * max(len(self.holdout), 1)
        if (
            self.permissions.evals_at_most is not None
            and self.evals_spent + runs_this_proposal > self.permissions.evals_at_most
        ):
            self.rejected.append(proposal)
            return Outcome(
                False,
                f"`cycle-limits.evals: {self.permissions.evals_at_most}` — scoring this "
                f"proposal would spend more eval runs than this round is allowed",
                cls, unmeasured=self._unmeasured(),
            )

        # And the third ceiling, which is the one that spans cycles: what
        # improving itself may COST in a month.
        #
        # It was recorded and never held, because a `Learner` is one cycle and
        # *"nothing here sees a month"* — so a workspace could write
        # `per-month: 20 USD` on a `tier: core`, `S-GOV` line and spend without
        # bound, which is the exact shape D22/D23 exist to prevent. What sees a
        # month is the WORKSPACE, and [`MonthlySpend`] is what keeps the total
        # there.
        #
        # Forecast rather than after-the-fact, the same way the `evals:` ceiling
        # above is: refusing once the money is gone would be reporting the
        # overspend, not capping it. The forecast is what a scoring run has
        # actually cost this month multiplied by the runs this proposal needs —
        # the workspace's own measured price, not an estimate this file invented
        # — and it is zero on the first cycle of a month, so nothing is ever
        # refused on no evidence.
        #
        # BEFORE the forecast, the ceiling itself. `per-month: NaN USD` is not a
        # loose ceiling, it is no ceiling: `would_reach > nan` is false at every
        # spend there is, so the refusal below never runs, and — measured — three
        # cycles spent 8.00, 16.00 and 24.00 USD with `unmeasured=()` on every
        # one, under an author who believes they capped what improving may cost.
        #
        # REFUSED and not merely reported, which is the opposite of the choice
        # `Limits.__post_init__` makes for `cost-per-request-under` one module
        # over, and the difference is where the decision sits. There, the object
        # is a frozen `Limits` built on the delegation path — `harness._delegating`
        # calls `replace()` on a member whose own cap is `NaN USD` and hands it
        # the join policy's real share — so raising would kill a run that is about
        # to become correct, and the honest answer is to drop the row and name the
        # field. HERE the decision point is a method call with no money spent yet
        # and refusal is the module's ordinary vocabulary: two ceilings above this
        # one already return `Outcome(False, ...)`. FR-8.1.1 says a lossy step is
        # fail-closed by default, and here fail-closed costs nothing structural,
        # so it is taken.
        #
        # Not conditional on `self.month.kept`. A missing workspace folder is a
        # fact about the world and is reported past (see `_unmeasured`); a figure
        # that is not a figure is a mistake in the file, and no folder would make
        # it hold.
        if self.permissions.per_month_holds_nothing():
            self.rejected.append(proposal)
            return Outcome(
                False,
                f"`cycle-limits.per-month: {self.permissions.per_month}` — no amount "
                f"of money can ever be above this, so nothing improving spends could "
                f"ever reach it and this cycle is not run. Write the most improving "
                f"may cost in a month as an amount — `cycle-limits: "
                f"{{ per-month: 20 USD }}` — or remove the line.",
                cls, unmeasured=self._unmeasured(),
            )

        cap = self.permissions.per_month_cap()
        if cap is not None and self.month.kept:
            amount, currency = cap
            would_reach = self.month.money + self.month.per_run * runs_this_proposal
            if would_reach > amount:
                self.rejected.append(proposal)
                unit = f" {currency}" if currency else ""
                return Outcome(
                    False,
                    f"`cycle-limits.per-month: {self.permissions.per_month}` — "
                    f"improving this system has already cost "
                    f"{self.month.money:.2f}{unit} in {self.month.in_words()}, and "
                    f"scoring this proposal would take it to "
                    f"{would_reach:.2f}{unit}. Nothing more is spent on improving "
                    f"until {self.month.next_in_words()}.",
                    cls, unmeasured=self._unmeasured(),
                )

        after = self._with(proposal)
        spent_before, runs_before = self.money_spent, self.evals_spent
        before_v = self._score(self.spec, self.holdout, transport_for)
        after_v = self._score(after, self.holdout, transport_for)
        # What this cycle cost, onto the month's running total — here, before any
        # of the answers below, because every one of them returns and a cycle
        # refused for drift has still spent what it spent. Written to the
        # workspace, so next Friday's cycle can see it.
        self.month.add(self.money_spent - spent_before, self.evals_spent - runs_before)

        drift = self._drift(after)

        if cls.needs_a_person:
            self.rejected.append(proposal)
            return Outcome(
                False, f"held for review: {cls.reason}", cls,
                before_v.score, after_v.score, drift, before_v, after_v,
                unmeasured=self._unmeasured(),
            )

        # And the author's own answer to "may anything take effect without a
        # person", whatever the class. `learning.yaml`'s `enabled:
        # propose-only` and `keep-only-if: a-person-approves-it` were read by
        # nobody, so `Learner.cycle` rewrote an agent's instructions with
        # `applied=True` in a workspace whose own file said every improvement
        # comes to review. It was three lines then and is two now: `auto-apply:`
        # was the third, and it was the one that could contradict the other two.
        blocked = self.permissions.may_apply_without_a_person()
        if blocked:
            self.rejected.append(proposal)
            return Outcome(
                False, f"held for review: {blocked}", cls,
                before_v.score, after_v.score, drift, before_v, after_v,
                # The one exit that did not carry the honest-reporting door. It
                # is also the one the worked example takes on every cycle
                # (`enabled: propose-only`), so the ceiling a reviewer most wants
                # told about was silent on the answer they actually get.
                unmeasured=self._unmeasured(),
            )

        if drift > self.drift_limit:
            # NOT remembered: drift is a property of how far the agent has moved
            # since the baseline, not of this edit. Re-baseline and the same
            # proposal is a different question.
            return self._refuse(
                proposal,
                f"cumulative drift {drift:.0%} from the frozen baseline exceeds "
                f"{self.drift_limit:.0%}; a person must re-baseline",
                cls, before_v.score, after_v.score, drift, before_v, after_v,
                remember=False,
            )

        if after_v.score <= before_v.score:
            # THE refusal AC-5.5 is about. Remembered, so next Friday's cycle
            # recognises the same edit and does not pay to learn the same thing.
            return self._refuse(
                proposal,
                f"held-out score did not improve ({before_v.score:.0%} → {after_v.score:.0%})",
                cls, before_v.score, after_v.score, drift, before_v, after_v,
            )

        self.spec = after
        self.applied_this_cycle += 1
        return Outcome(
            True, f"held-out score improved {before_v.score:.0%} → {after_v.score:.0%}",
            cls, before_v.score, after_v.score, drift, before_v, after_v,
            unmeasured=self._unmeasured(),
        )

    def _refuse(
        self,
        proposal: Proposal,
        why: str,
        cls: Classification,
        *rest: Any,
        remember: bool = True,
    ) -> Outcome:
        """Refuse a proposal, and remember it so the next cycle need not re-learn.

        Every refusal goes through here rather than each path appending to
        `rejected` and building its own `Outcome`. Eleven paths did it by hand,
        and the eleven agreed only because nobody had added a twelfth — which is
        the shape of every defect in this repository's register.

        `remember=False` for the two refusals that are about the WORKSPACE rather
        than the proposal: `enabled: off` and a spent ceiling would refuse
        anything at all, and writing that down would mean a proposal turned away
        by a switch could never be tried again once the switch was flipped.
        """
        self.rejected.append(proposal)
        if remember:
            self.refusals.add(proposal, why)
        return Outcome(False, why, cls, *rest, unmeasured=self._unmeasured())

    #: A skill's fields, by the name an author writes, to the attribute that
    #: holds it. One mapping, so the author's spelling and the dataclass cannot
    #: come to mean different things.
    _SKILL_FIELDS = {
        "content": "content",
        "use-when": "use_when",
        "do-not-use-when": "do_not_use_when",
        "if-unsure": "if_unsure",
    }

    def _with(self, p: Proposal) -> AgentSpec:
        """The candidate this proposal describes — the spec that gets scored.

        An error rather than `return self.spec` on anything it cannot build,
        because `return self.spec` is what the silent version did, and a
        candidate that is secretly the incumbent scores exactly like one.
        """
        from dataclasses import replace

        if p.field == "instructions":
            return replace(self.spec, instructions=p.after)

        if p.field in self._SKILL_FIELDS:
            attr = self._SKILL_FIELDS[p.field]
            if not self.spec.skills:
                raise ValueError(
                    f"a change to `{p.field}` is a change to a written procedure, and "
                    f"'{self.spec.name}' has no written procedure to change — a permission "
                    f"is not a promise that the document has one."
                )
            # The procedure the edit is FOR: the one whose current text is what
            # the proposal says it replaces. A cycle proposes against what it
            # read, so a `before` matching nothing is a proposal about a document
            # that has already moved — and applying it to whichever procedure
            # happened to be first would silently rewrite the wrong one.
            matched = [
                i
                for i, sk in enumerate(self.spec.skills)
                if getattr(sk, attr, "") == p.before
            ]
            if not matched:
                raise ValueError(
                    f"no written procedure on '{self.spec.name}' has the `{p.field}` this "
                    f"proposal replaces, so there is nothing here to change — the document "
                    f"has moved since the proposal was made."
                )
            at = matched[0]
            skills = list(self.spec.skills)
            skills[at] = replace(skills[at], **{attr: p.after})
            return replace(self.spec, skills=tuple(skills))

        if p.field in READ_BY_NO_RUN:
            raise ValueError(
                f"a change to `{p.field}` cannot be put into effect here: "
                f"{READ_BY_NO_RUN[p.field]} — so no run reads it, and both scoring "
                f"runs would grade the same agent."
            )

        raise ValueError(
            f"a cycle cannot apply a change to `{p.field}` — "
            f"it applies {', '.join(CAN_BE_APPLIED)}"
        )

    def _drift(self, candidate: AgentSpec) -> float:
        """How far the candidate has moved from the frozen baseline, cumulatively."""
        if self.baseline is None:
            return 0.0
        ratio = difflib.SequenceMatcher(
            None, self.baseline.instructions, candidate.instructions
        ).ratio()
        return 1.0 - ratio
