"""An agent somewhere else, reached over A2A (`resource-kind: a2a-agent`, N1).

`resources/booker.yaml` says `resource-kind: a2a-agent`, where it is
(`endpoint:`), where its credential is kept (`auth.by-reference:`), which
question a person answers before it is first asked anything
(`asks-to-connect:`), and what its card said when somebody read it
(`tool-snapshot-digest:`). A tool reaches it with `connect: booker`, and that
tool's `actions:` are the skills of the card the model may ask, each by the
skill's id. `pact check` refuses a tool that asks it for no skill, and an
action that promises values from it (`crates/pact-loader/src/remote.rs`).

This module is the half that can only be decided once the card has arrived, and
it is the MCP bridge's half over again, for a different publication:

* **The card is what the agent publishes about itself**, so it is pinned the way
  an MCP server's tool list and prose are (AD-71): `card_digest` is the digest
  `tool-snapshot-digest:` holds, and `check_card` reports drift, a stale review
  (`mcp_bridge.check_pin`, the one reader of those three lines) and a skill
  this tree asks for that the card does not list.
* **A reply is words a stranger wrote**, so it reaches a model only fenced
  (`reply`, which is `mcp_bridge.quarantined`): after everything a person
  wrote, labelled non-authoritative, every line quoted. Nothing a run decides
  reads it.

Nothing here opens a connection, resolves a reference or holds a secret: the
runtime fetches the card and sends the messages, with the address and the
credential its host resolved, after the consent `questions.questions_for`
built from `asks-to-connect:` was answered.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from .ir import ResourceSpec
from .mcp_bridge import check_pin, quarantined

__all__ = ["A2A_AGENT", "card_digest", "check_card", "reply"]

#: The `resource-kind:` of an agent reached over A2A.
A2A_AGENT = "a2a-agent"

#: The card lines a digest leaves out: a signature is made anew at every signing
#: (with a randomized algorithm, a different one each time) over the rest of the
#: card, so it carries nothing the rest does not, and pinning it would report a
#: card that never changed as drifted on every fetch.
_UNPINNED = ("signatures",)


def card_digest(card: Mapping[str, Any]) -> str:
    """One digest over everything a card says, as served (its JSON), signatures aside.

    Canonical JSON with sorted keys, so two fetches of one card digest alike on
    any machine whatever order the server wrote its keys in.
    """
    whole = {str(k): v for k, v in card.items() if k not in _UNPINNED}
    canonical = json.dumps(whole, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def skills_of(card: Mapping[str, Any]) -> tuple[str, ...]:
    """The ids of the skills a card lists, in its order."""
    skills = card.get("skills") or ()
    return tuple(str(s.get("id")) for s in skills if isinstance(s, Mapping) and s.get("id"))


def check_card(
    resource: ResourceSpec,
    card: Mapping[str, Any],
    skills: Iterable[str],
    *,
    now: float | None = None,
) -> tuple[str, ...]:
    """Everything wrong with a card that just arrived, as sentences; empty when it holds.

    `skills` are the skill ids this tree asks for (the actions of the tools
    that `connect:` to `resource`). Each one the card does not list is a
    finding: a call to it would reach an agent that never offered it. Then,
    when the resource pins a digest, the pin (`mcp_bridge.check_pin`: drift, and
    a review older than `tool-snapshot-max-age:`). `now` is epoch seconds.
    """
    server = resource.name
    listed = skills_of(card)
    found = [
        f"`{server}`'s card lists no skill `{skill}` (it lists: {', '.join(listed) or 'none'}), "
        f"and a tool connecting to it asks for that skill. fix: name the action after a skill id "
        f"the card lists, or ask whoever runs `{server}` whether the skill was renamed."
        for skill in dict.fromkeys(skills)
        if skill not in listed
    ]
    if resource.tool_snapshot_digest:
        found += check_pin(resource, card_digest(card), now=now)
    return tuple(found)


def reply(server: str, text: str) -> str:
    """A remote agent's reply in the only shape it may reach a model in (AD-71).

    Always labelled as words nobody reviewed: a pinned digest covers the card,
    which somebody read, never a reply, which is new at every call.
    """
    return quarantined(server, text, what="sent as its reply")
