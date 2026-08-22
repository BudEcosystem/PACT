"""What an agent may author for itself, and what a person must read first.

D22 grants an agent the right to author tools for itself — the strongest form of
self-modification this format has. FR-6.2.5 and M7.4 carried it as planned and
unbuilt, for the reason everything else in this phase was unbuilt: there was
nowhere to run a body, and nothing to hold one to.

AD-85 is the decision, and its shape is the interesting part: it does not answer
"may an agent write a tool?" once. It splits the grant by what the tool IS.

# The no-code lane: a composite, and nothing else

Under the `no-code` badge a self-authored tool must be a **composite** — a
declarative composition of actions that are already approved and already pinned.
There is no new behaviour in one, only a new arrangement of behaviour somebody
already signed off. So a support lead can read it line by line, which is exactly
what D13 requires and what a code body can never offer them.

"Already approved" is the whole of what makes that safe. Without it the lane is a
way to reach any action at all by composing it, and the composite becomes the
door round every gate the author wrote.

# The code lane: an engineer, and a sentence

A code-bodied tool requires a distinct `engineer` role, and the approval surface
must state, in those words, *"this tool contains code that has not been read by a
person."* Under D13 the human signing cannot read the body. Saying so is the only
honest thing to put in front of them, and softening it would make the signature
mean something it does not.

# What must never be the acceptance rule

**"Does not raise an exception" is forbidden as an acceptance criterion**, in
AD-85's own words, and the reason is measured rather than theoretical:
SkillWeaver's exception criterion was gamed by silencing every atomic action's
errors. A tool that swallows its own failures passes it perfectly. What keeps a
learned tool is the same eval gate every other learned change goes through — a
held-out score that moved.

# Removal, which is the half nobody builds

§8.5 requires removal to be as expressible as addition. A tool nobody may use any
more is not one you delete and hope: the digest is refused, so a lockfile
carrying it cannot be produced, and `supersedes` carries the edge that makes
rollback possible rather than archaeological.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: The role that has to sign for a body nobody has read.
#:
#: Distinct from whoever approves an ordinary change, deliberately: AD-85's
#: rejected alternative was "a capability manifest plus a model-evaluated QA
#: suite", where the real gate was a model and the human signing could not read
#: what they were signing. A separate role is what makes the difference visible
#: in the approval surface rather than implied by it.
ENGINEER = "engineer"

#: The sentence that goes in front of whoever signs for a code body — in these
#: words, because AD-85 specifies them and because every softer phrasing makes
#: the signature mean something it does not.
NOT_READ_BY_A_PERSON = "this tool contains code that has not been read by a person"

#: Evidence that is not evidence. Matched loosely because the point is the
#: CRITERION rather than a spelling: any claim whose content is "nothing went
#: wrong" is the one AD-85 forbids.
_NOT_EVIDENCE = ("without raising", "did not raise", "no exception", "ran clean", "no errors")


class Refused(Exception):
    """A self-authored tool that may not be reviewed as written."""


@dataclass(frozen=True)
class AuthoredTool:
    """One tool an agent wrote for itself, as it arrives for review."""

    name: str
    description: str
    #: Actions it composes, `<tool>/<action>`. The no-code lane.
    composite: tuple[str, ...] = ()
    #: A carried program it runs instead. The code lane.
    program: str = ""
    #: Why the cycle kept it — read, because AD-85 forbids one answer.
    kept_because: str = ""
    #: sha256 of the body, so it can be pinned and revoked.
    digest: str = ""
    #: The digest this one replaces, so rollback has an edge to walk.
    supersedes: str = ""


@dataclass(frozen=True)
class Review:
    """What has to happen before this tool may be used."""

    roles: frozenset[str] = field(default_factory=frozenset)
    #: The sentence the approval surface must carry, or empty.
    wording: str = ""
    #: Whether a workspace using this tool still earns the `no-code` badge.
    no_code_badge: bool = True


def review_needed(tool: AuthoredTool, approved: "frozenset[str] | set[str]") -> Review:
    """Who must sign for this tool, and what they must be told.

    `approved` is the set of `<tool>/<action>` a person has already approved and
    pinned — the only things a composite may be built from.
    """
    if tool.composite and tool.program:
        raise Refused(
            f"'{tool.name}' both composes actions and carries a program. A tool that does "
            f"both is a code-bodied tool wearing the no-code lane's clothes, and only one "
            f"of the two can be what a reviewer is reading. Fix: write it as a composite "
            f"over approved actions, or as a program, and not as both."
        )

    if not tool.composite and not tool.program:
        raise Refused(
            f"'{tool.name}' neither composes anything nor carries a program, so there is "
            f"nothing here to review or to run. Fix: give it a `composite:` of actions "
            f"somebody has already approved, or a `program:` to run."
        )

    # The acceptance rule, asked of both lanes. A composite is not exempt: a
    # composition kept because nothing went wrong is the same absence of evidence
    # as a body kept that way.
    said = tool.kept_because.strip().lower()
    if said and any(phrase in said for phrase in _NOT_EVIDENCE):
        raise Refused(
            f"'{tool.name}' was kept because it {tool.kept_because.strip()!r}, and not "
            f"raising is not evidence that a tool works — a tool that swallows its own "
            f"failures passes that test perfectly, which is how the one measured attempt "
            f"at this criterion was gamed. Fix: keep it because a held-out eval score "
            f"moved, and say which."
        )

    if tool.composite:
        unapproved = [a for a in tool.composite if a not in approved]
        if unapproved:
            raise Refused(
                f"'{tool.name}' composes {', '.join(unapproved)}, and nobody has approved "
                f"{'them' if len(unapproved) > 1 else 'it'}. A composite is safe because "
                f"everything in it was already signed off; one that reaches an unapproved "
                f"action is a way round every gate the author wrote. Fix: compose only "
                f"actions that are already approved and pinned."
            )
        # Nothing new happens, so nothing new needs an engineer.
        return Review()

    return Review(
        roles=frozenset({ENGINEER}),
        wording=NOT_READ_BY_A_PERSON,
        no_code_badge=False,
    )


def may_bind(tool: AuthoredTool, revoked: "frozenset[str] | set[str]") -> bool:
    """Whether a resolver may bind this tool at all.

    §8.5: removal must be as expressible as addition. A revoked body is refused
    here, so a lockfile carrying it cannot be produced — deleting the file and
    hoping is not removal, because every lockfile already written still names it.
    """
    return not (tool.digest and tool.digest in revoked)
