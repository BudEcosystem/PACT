"""Context policy — what to do when the conversation outgrows the model (G3).

Every framework hits this. Almost all of them answer it once, in code, and the
answer becomes unreachable. Eve is the closest prior art and is worth reading
closely, because three of its ideas are right and five of its constants are the
whole gap.

**Kept from Eve, deliberately:**

* *Summarise with a checkpoint, and never truncate the checkpoint.* Everything
  that came before is folded into one marked message that later steps may not
  touch (`harness/compaction.ts:345-363`). Losing it loses the whole earlier
  conversation at once rather than gradually, so it is the one thing worth
  protecting unconditionally.
* *Split the tail forward past leading tool results.* A kept tail that opens on
  a tool result whose call fell into the summarised region is rejected outright
  by every provider (`harness/compaction.ts:464-467`).
* *Escalate rather than jump.* Try the cheapest thing, measure, then try more
  (`harness/compaction.ts:196-246`). One strategy either over-deletes a short
  conversation or under-deletes a long one.

**Fixed here, because each is a constant an author cannot reach:**

* *The list of things to try* is `COMPACTION_HEURISTICS`, a private const with
  exactly one entry, and its own comment says composing a new strategy "means
  adding an entry here" — in the framework's source (`compaction.ts:116-122`).
  Here it is `then:`, in the author's file.
* *Thinking is discarded unconditionally.* `assistantMessageText` keeps only
  text parts, "ignoring tool-call, reasoning, and other non-text parts"
  (`compaction.ts:395-411`), and there is no setting for it. Here dropping is a
  step the author writes and scopes to a kind of content; **write nothing and
  nothing is dropped.**
* *The recent window is the number 10* (`execution/session.ts:6`). Ten messages
  is a different amount of conversation every time. Here `down-to:` takes a
  size, a count, or a landmark, and the landmark form is the one that means the
  same thing twice.
* *Nothing can be pinned.* There is no must-keep list anywhere in Eve, so a
  recorded approval is exactly as droppable as small talk. That is the
  expensive kind of loss, so `always-keep:` exists and outranks every step.
* *Giving up is silent.* Eve's ladder bottoms out at `keep === 0` and returns
  the still-oversized history with no signal (`compaction.ts:241`). That is the
  silent degradation T7 forbids, so `if-it-still-does-not-fit:` is a field and
  the outcome is always on the result.

Everything here runs offline (D17): the size estimate is arithmetic and the
summariser is supplied by the caller, so a policy with no summariser degrades
loudly instead of reaching for a network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

#: `Problem` is imported rather than defined here so that the module that finds
#: a mistake and the module that renders it are the same for every kind. It is
#: re-exported deliberately: `from .context_policy import Problem` was the
#: spelling before this move and there is no reason to make anyone edit it.
from .diagnostics import Problem, locate  # noqa: F401
#: G9. Imported for the type only; the tidier never constructs one, because who
#: knows a fact is the run's business and not the shortener's.
from .facts import Facts  # noqa: F401


# ─────────────────────────────────────────────────────────── content vocabulary


class PartKind(str, Enum):
    """The kinds of content a message can carry.

    PACT owns this vocabulary rather than passing an SDK's through, and that is
    the reason a rule can name `the model's own thinking` at all. In Eve,
    reasoning is a case inside someone else's union, so the only move available
    to the framework is "keep text, discard the rest" — which is exactly what it
    does, every time.
    """

    TEXT = "text"
    THINKING = "thinking"
    TOOL_CALL = "tool-call"
    TOOL_RESULT = "tool-result"
    IMAGE = "image"
    AUDIO = "audio"


#: Plain-language ways an author names a kind of content. Matched longest-first
#: on the whole phrase, so `tool results` never resolves through `tool`.
PART_WORDS: dict[str, PartKind] = {
    "the model's own thinking": PartKind.THINKING,
    "its own thinking": PartKind.THINKING,
    "thinking": PartKind.THINKING,
    "reasoning": PartKind.THINKING,
    "working out": PartKind.THINKING,
    "tool results": PartKind.TOOL_RESULT,
    "tool output": PartKind.TOOL_RESULT,
    "what tools returned": PartKind.TOOL_RESULT,
    "tool calls": PartKind.TOOL_CALL,
    "pictures": PartKind.IMAGE,
    "images": PartKind.IMAGE,
    "photos": PartKind.IMAGE,
    "screenshots": PartKind.IMAGE,
    "audio": PartKind.AUDIO,
    "recordings": PartKind.AUDIO,
}


@dataclass(frozen=True)
class Part:
    kind: PartKind
    text: str = ""
    #: Which tool this call or result belongs to.
    tool: str = ""
    #: Which *call*, when one tool is used twice in a turn. Defaults to the tool
    #: name, which is how the harness itself identifies a result today.
    ref: str = ""

    @property
    def pairs_on(self) -> str:
        return self.ref or self.tool

    def sized(self) -> int:
        return len(self.text) + len(self.tool)


#: Labels the runtime stamps on a message so a pin can name it without code.
#: Closed, and short on purpose: an open label set is an open predicate
#: language, and nobody could review the result.
LABELS = (
    "approval",       # a person approved or declined something
    "first-request",  # the opening ask, the thing the whole run is about
    "answer",         # something handed back to whoever asked
    "attachment",     # a file or picture someone sent in
)


@dataclass(frozen=True)
class Message:
    role: str                             # user | assistant | tool | system
    parts: tuple[Part, ...] = ()
    #: Which of `LABELS` apply, plus `from:<name>` for the tool, skill or
    #: resource the content came out of.
    labels: frozenset[str] = frozenset()
    #: Set by `summarise-older`. A checkpoint is never shortened, never
    #: summarised again, and never dropped — see `Pins.select`.
    checkpoint: bool = False

    def text(self) -> str:
        return "\n".join(p.text for p in self.parts if p.text)

    def sized(self) -> int:
        # The role and the envelope cost tokens on the wire too. Counting them
        # stops a history of many tiny messages from measuring as nearly free,
        # which is the failure mode of a content-only estimate.
        return sum(p.sized() for p in self.parts) + len(self.role) + 8

    def kinds(self) -> frozenset[PartKind]:
        return frozenset(p.kind for p in self.parts)

    def without(self, kind: PartKind) -> "Message":
        return replace(self, parts=tuple(p for p in self.parts if p.kind != kind))

    def is_empty(self) -> bool:
        return not self.parts


def _a_fact_message(text: str, label: str) -> "Message":
    """A re-stated fact, as a checkpoint so no later tidy summarises it back.

    `checkpoint=True` is the existing mechanism for "never shortened, never
    summarised again, never dropped" (`Pins.select`), so a surviving fact
    reuses it rather than introducing a second kind of immovable message.
    """
    return Message(
        role="user",
        parts=(Part(PartKind.TEXT, text),),
        labels=frozenset({label}),
        checkpoint=True,
    )


# ────────────────────────────────────────────────────────────────── estimating

#: Characters per token. Eve uses `JSON.stringify(value).length / 4`
#: (`harness/token-estimate.ts`) and so does this, for the same two reasons: the
#: real count comes back from the model each step, and an estimate that needs a
#: tokenizer download cannot run air-gapped (D17).
CHARS_PER_TOKEN = 4


def estimate(messages: Sequence[Message]) -> int:
    """Rough token count. Replaceable — see `Tidier(measure=...)`."""
    return sum(m.sized() for m in messages) // CHARS_PER_TOKEN


Measure = Callable[[Sequence[Message]], int]

#: Writes the summary. Given the messages being folded away and the previous
#: checkpoint text, returns the new checkpoint. Supplied by the runtime, so this
#: module never opens a socket.
Summariser = Callable[[Sequence[Message], str], str]


# ──────────────────────────────────────────────────────────────── diagnostics
#
# `Problem` and the search behind `_locate` used to live here, and interceptors
# had neither — they synthesised a path from the entry's name and never named a
# line. Both now come from `diagnostics`, so there is one diagnostic shape in
# this adapter rather than two, and the file-name spellings the Expansion Rule
# allows are enumerated in exactly one place.


def _locate(source: Path | None, name: str, needle: str) -> tuple[str, int]:
    """Where a phrase from a context policy was written.

    `context-policy` is the singular the loader accepts as the self file of a
    folder-shaped policy — `context-policies/long-threads/context-policy.yaml`.
    The old list here guessed `policy.yaml`, which `Policy::is_self_file` has
    never accepted, so the folder spelling was searched for under a name it can
    never have.
    """
    return locate(source, "context-policies", "context-policy", name, needle)


# ─────────────────────────────────────────────────────────────────────── pins


class PinKind(str, Enum):
    """How a pin found its messages. Recorded, so `pact` can show an author what
    their sentence actually matched — which is the whole difference between a
    reviewable rule and a wish."""

    LABEL = "label"        # something the runtime marks: an approval, the first ask
    SOURCE = "source"      # content from a named tool, skill or resource
    PHRASE = "phrase"      # the words themselves appear in the message


#: Plain-language ways an author names a label. Same shape as `PART_WORDS`.
LABEL_WORDS: dict[str, str] = {
    "approved or declined": "approval",
    "a person approved": "approval",
    "anyone approved": "approval",
    "approval": "approval",
    "approved": "approval",
    "declined": "approval",
    "signed off": "approval",
    "original request": "first-request",
    "first message": "first-request",
    "what they asked for": "first-request",
    "the answer": "answer",
    "what we told them": "answer",
    "attachment": "attachment",
    "attachments": "attachment",
    "photos they sent": "attachment",
}

_STOP_WORDS = ("the", "a", "an", "any", "anything", "our", "their", "this", "that")


@dataclass(frozen=True)
class Pin:
    """One line of `always-keep:`, resolved.

    Nothing else in PACT can pin content, and nothing in Eve can at all. The
    guarantee is absolute on purpose: a pinned message is not shortened, not
    summarised, not dropped — and if the pins alone overflow the budget, that is
    reported rather than quietly resolved by dropping one of them.
    """

    phrase: str
    kind: PinKind
    target: str

    def matches(self, m: Message) -> bool:
        if self.kind is PinKind.LABEL:
            return self.target in m.labels
        if self.kind is PinKind.SOURCE:
            return f"from:{self.target}" in m.labels
        return self.target in m.text().casefold()


def _typeable(words: dict[str, Any], order: Sequence[Any]) -> list[str]:
    """One phrase an author can actually type, per thing they might mean.

    Derived from the vocabulary rather than written out beside it, because a
    hand-kept list of examples is a list that stops matching the code — and a
    diagnostic offering a fix that no longer works is worse than none.
    """
    first: dict[Any, str] = {}
    for phrase, target in words.items():
        first.setdefault(target, phrase)
    return [first[t] for t in order if t in first]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


#: Sections whose names can really appear as `from:<name>` on a message. A tool
#: result and a teammate's answer are both `{"role": "tool", "name": ...}` in the
#: history (`from_history` stamps the label there and nowhere else), so those two
#: are the whole set.
CAN_BE_A_SOURCE = ("tools", "agents")

#: Named in the workspace and never the source of a message, with the reason
#: printed to whoever wrote the pin. `_known_names` covered all five for a round
#: and turned any of them into a `SOURCE` pin — which matches a label nothing
#: ever stamps, keeps nothing, suppresses the words fallback that WOULD have
#: kept something, and warns about none of it. The worked example's own first
#: pin, `- the refund policy`, was exactly this.
NEVER_A_SOURCE = {
    "skills": (
        "a written procedure, which is part of the instructions rather than "
        "part of the conversation — it is never tidied away, so it needs no pin"
    ),
    "resources": (
        "a connected system, which a tool reaches THROUGH; pin the tool that "
        "connects to it and you pin what came back"
    ),
    "policies": "a set of rules, and rules are not messages",
    "context-policies": "a set of rules, and rules are not messages",
}
# `redactions` is gone from this map, with the section itself (R61). Every entry
# here is a section holding NAMED documents, and what must never leave is now one
# unnamed `redaction:` setting of the workspace written as `redaction.yaml` — so
# there is no name left for a pin to be about. Leaving the key would be dead;
# writing `redaction` instead would be worse, because `_named_in` matches the
# KEYS of the section and this one's keys are `description` and `hide`, so
# `- the description` would resolve to a redaction. A pin naming what used to be
# there now falls to `pin-matches-words-only`, which names the file, the line,
# the fact that nothing in this workspace is called that, and what to type.


def _known_names(doc: dict[str, Any], sections: Sequence[str]) -> dict[str, str]:
    """Every name in the given sections, keyed by a normalised form so
    `anything the payments tool said` finds `payments`."""
    names: dict[str, str] = {}
    for section in sections:
        for key in doc.get(section) or {}:
            names[_norm(key)] = key
    return names


def _named_in(doc: dict[str, Any], stripped: str, sections: Sequence[str]) -> str:
    for norm_name, real in _known_names(doc, sections).items():
        if norm_name and (norm_name in stripped or stripped in norm_name):
            return real
    return ""


def resolve_pin(
    phrase: str, doc: dict[str, Any], name: str, source: Path | None
) -> tuple[Pin, Problem | None]:
    """Turn one plain sentence into a predicate, or say why it could not.

    There are exactly three ways to name a set of messages without writing code,
    and they are tried in this order: by what it *is* (a label PACT stamps), by
    where it *came from* (something named in this workspace), by what it *says*
    (the words). A sentence resolving to neither of the first two still works as
    words — and warns, because a pin that silently matches nothing is precisely
    the failure `always-keep:` exists to prevent.
    """
    lowered = phrase.casefold().strip()

    for words in sorted(LABEL_WORDS, key=len, reverse=True):
        if words in lowered:
            return Pin(phrase, PinKind.LABEL, LABEL_WORDS[words]), None

    stripped = _norm(lowered)
    for word in _STOP_WORDS:
        stripped = re.sub(rf"\b{word}\b", " ", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()

    if real := _named_in(doc, stripped, CAN_BE_A_SOURCE):
        return Pin(phrase, PinKind.SOURCE, real), None

    file, line = _locate(source, name, phrase)
    marks = ", ".join(f"`{w}`" for w in _typeable(LABEL_WORDS, LABELS))
    sources = _known_names(doc, CAN_BE_A_SOURCE)
    mine = (
        ", ".join(f"`anything {k} said`" for k in sorted(sources.values())[:3])
        or "a tool you have"
    )

    # It names something real and that something can never be the source of a
    # message. Said plainly, with the reason, because the author who wrote this
    # line believes it is holding — and the pin falls back to the WORDS, which
    # is the only reading that can keep anything at all.
    for section, why in NEVER_A_SOURCE.items():
        if real := _named_in(doc, stripped, (section,)):
            return (
                Pin(phrase, PinKind.PHRASE, lowered),
                Problem(
                    rule="context-policy/pin-names-something-that-is-not-a-message",
                    file=file,
                    line=line,
                    message=(
                        f"'{phrase}' names '{real}', which is {why}. This line "
                        f"will only keep messages containing those exact words."
                    ),
                    fix=(
                        f"Name something PACT already marks ({marks}), or "
                        f"name where a message came from: {mine}. If the words "
                        f"are what you meant, leave it as it is."
                    ),
                ),
            )

    return (
        Pin(phrase, PinKind.PHRASE, lowered),
        Problem(
            rule="context-policy/pin-matches-words-only",
            file=file,
            line=line,
            message=(
                f"'{phrase}' does not name anything this workspace has, so it will "
                f"only keep messages containing those exact words."
            ),
            fix=(
                f"Name something PACT already marks ({marks}), or name where a "
                f"message came from: {mine}. If the words are what you meant, "
                f"leave it as it is."
            ),
        ),
    )


@dataclass
class Pins:
    pins: tuple[Pin, ...] = ()

    def select(self, messages: Sequence[Message]) -> frozenset[int]:
        """Which messages survive everything.

        A checkpoint is always in the set, whether or not the author wrote any
        pins — it is the compressed form of everything already dropped, so
        tidying it is the one move that cannot be undone.
        """
        return frozenset(
            i
            for i, m in enumerate(messages)
            if m.checkpoint or any(p.matches(m) for p in self.pins)
        )

    def __bool__(self) -> bool:
        return bool(self.pins)


# ───────────────────────────────────────────────────────────── `down-to:` sizes


@dataclass(frozen=True)
class Amount:
    """A parsed `down-to:`. Exactly one of the three forms is set."""

    characters: int | None = None
    messages: int | None = None
    landmark: str | None = None
    raw: str = ""


_SIZE = re.compile(
    r"(?P<n>[\d_]+)\s*(?P<k>k|thousand)?\s*(?P<unit>characters|chars|tokens|words|messages)"
)
_LANDMARK = re.compile(r"(?:everything\s+)?(?:since|after)\s+(?P<what>.+)")


def parse_amount(
    raw: str, name: str, source: Path | None, step: str
) -> tuple[Amount | None, Problem | None]:
    """Read `2000 characters`, `the last 10 messages`, `everything since X`.

    Eve has no equivalent because it has no `down-to:` at all — its window is
    the literal number 10 in `execution/session.ts:6`, which is a different
    amount of conversation on every run.
    """
    text = (raw or "").strip().casefold()
    if not text:
        return None, None

    if (m := _LANDMARK.fullmatch(text)) is not None:
        return Amount(landmark=m.group("what").strip(), raw=raw), None

    if (m := _SIZE.search(text)) is not None:
        n = int(m.group("n").replace("_", "")) * (1000 if m.group("k") else 1)
        unit = m.group("unit")
        if unit == "messages":
            return Amount(messages=n, raw=raw), None
        if unit == "tokens":
            return Amount(characters=n * CHARS_PER_TOKEN, raw=raw), None
        if unit == "words":
            # About five letters and a space. Approximate, and said so, rather
            # than claiming a precision the character estimate does not have.
            return Amount(characters=n * 6, raw=raw), None
        return Amount(characters=n, raw=raw), None

    file, line = _locate(source, name, raw)
    return None, Problem(
        severity="error",
        rule="context-policy/unreadable-amount",
        file=file,
        line=line,
        message=f"'{raw}' does not say how much to leave, so `{step}` cannot run.",
        fix=(
            "Write a size, a count, or a landmark — for example "
            "`down-to: 2000 characters`, `down-to: the last 10 messages`, or "
            "`down-to: everything since the last approval`."
        ),
    )


# ─────────────────────────────────────────────────────────────── the policy


@dataclass(frozen=True)
class Step:
    what: str
    applies_to: str = ""
    amount: Amount | None = None
    #: For `drop-parts`: which kind of content, read out of `applies-to`.
    part: PartKind | None = None


#: What `drop-parts` can be told to remove, in the author's own words. Derived
#: from the vocabulary so the fix a diagnostic offers is always one that works.
DROPPABLE = tuple(_typeable(PART_WORDS, tuple(PartKind)))


@dataclass
class ContextPolicy:
    name: str
    description: str = ""
    when_full: float = 0.9
    pins: Pins = field(default_factory=Pins)
    steps: tuple[Step, ...] = ()
    summarised_by: str = ""
    if_it_still_does_not_fit: str = "use-it-anyway"
    problems: tuple[Problem, ...] = ()

    @property
    def errors(self) -> tuple[Problem, ...]:
        return tuple(p for p in self.problems if p.severity == "error")

    @staticmethod
    def resolve(
        doc: dict[str, Any], named: str, source: Path | None = None
    ) -> "ContextPolicy | None":
        """The policy an agent's `context-policy:` line points at, or nothing.

        Resolved here rather than by the adapter, for the reason `loop:` is:
        an adapter that had to look the name up again would need the whole
        workspace, which invariant P-1 says it never sees.

        Nothing is the honest default. A workspace with no policy does not get a
        silent built-in recipe — it gets no tidying, and a conversation that
        outgrows the model fails at the provider where it is visible.
        """
        if not named:
            return None
        return ContextPolicy.from_document(doc, named, source)

    @staticmethod
    def from_document(
        doc: dict[str, Any], name: str, source: Path | None = None
    ) -> "ContextPolicy":
        """Build from the loaded document.

        There is no author code anywhere on this path (D14): the sentences in
        the file are the whole program.
        """
        policies = doc.get("context-policies") or {}
        if name not in policies:
            raise KeyError(
                f"no context policy named {name!r}; this workspace has: {sorted(policies)}"
            )
        raw = policies[name] or {}
        problems: list[Problem] = []

        pins: list[Pin] = []
        for phrase in raw.get("always-keep") or []:
            if not isinstance(phrase, str):
                continue
            pin, problem = resolve_pin(phrase, doc, name, source)
            pins.append(pin)
            if problem is not None:
                problems.append(problem)

        steps: list[Step] = []
        for entry in raw.get("then") or []:
            if not isinstance(entry, dict):
                continue
            what = str(entry.get("what") or "").strip()
            applies_to = str(entry.get("applies-to") or "").strip()
            amount, problem = parse_amount(
                str(entry.get("down-to") or ""), name, source, what
            )
            if problem is not None:
                problems.append(problem)
            part = _part_of(applies_to)
            if what == "drop-parts" and part is None:
                file, line = _locate(source, name, applies_to or "drop-parts")
                problems.append(
                    Problem(
                        severity="error",
                        rule="context-policy/drop-parts-needs-a-kind",
                        file=file,
                        line=line,
                        message=(
                            f"`drop-parts` does not say what to drop"
                            + (
                                f"; '{applies_to}' is not a kind of content."
                                if applies_to
                                else "."
                            )
                        ),
                        fix=(
                            "Add `applies-to:` naming one of: "
                            + ", ".join(f"`{w}`" for w in DROPPABLE)
                        ),
                    )
                )
            steps.append(Step(what=what, applies_to=applies_to, amount=amount, part=part))

        return ContextPolicy(
            name=name,
            description=str(raw.get("description") or ""),
            when_full=_share(raw.get("when-full"), default=0.9),
            pins=Pins(tuple(pins)),
            steps=tuple(steps),
            summarised_by=str(raw.get("summarised-by") or ""),
            if_it_still_does_not_fit=str(
                raw.get("if-it-still-does-not-fit") or "use-it-anyway"
            ),
            problems=tuple(problems),
        )


def _part_of(phrase: str) -> PartKind | None:
    lowered = phrase.casefold().strip()
    for words in sorted(PART_WORDS, key=len, reverse=True):
        if words in lowered:
            return PART_WORDS[words]
    return None


def _share(raw: Any, default: float) -> float:
    """`85%` or `0.85`. A bare `85` is refused by the schema before it reaches
    here (`coerce.rs`, `percentages_refuse_the_ambiguous_form`), so it is
    refused here too rather than being read as 8500%."""
    if raw is None:
        return default
    text = str(raw).strip()
    if text.endswith("%"):
        try:
            share = float(text[:-1]) / 100
        except ValueError:
            return default
        # The same range the bare-decimal branch below already holds, and for the
        # same reason: `when-full: 150%` and `-50%` were both accepted here while
        # the Rust side refused both.
        return share if 0.0 < share <= 1.0 else default
    try:
        value = float(text)
    except ValueError:
        return default
    return value if 0 < value <= 1 else default


# ──────────────────────────────────────────────────────────────────── the run


class StillTooLong(RuntimeError):
    """Every step ran, it still does not fit, and the policy said not to send it
    anyway. Typed so a caller can tell this apart from a model error."""


@dataclass
class Tidied:
    """What tidying did. Every field is here so nothing has to be inferred.

    Eve returns a bare message array: whether it summarised, whether it gave up,
    and whether the result is actually under the threshold are all unknowable to
    its caller. That is the reporting gap T7 names.
    """

    messages: list[Message]
    fired: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    before: int = 0
    after: int = 0
    budget: int = 0
    fits: bool = True
    pinned: int = 0
    #: Facts re-stated into the tail because the run still knows them (G9).
    facts_kept: list[str] = field(default_factory=list)
    #: Facts that went stale before the run finished. Reported, never silent —
    #: a rule reading a forgotten fact decided on nothing.
    facts_lost: list[str] = field(default_factory=list)
    #: `not-needed` | `fitted` | `used-it-anyway` | `asked-a-person`
    outcome: str = "fitted"
    #: By how much it still did not fit, in words, when the ladder bottomed out
    #: — and empty whenever it did fit. This is the figure `shows:
    #: [how-much-over]` puts in front of a person under `ask-a-person`
    #: (`questions/too-long-to-send.yaml`), and it is a named field rather than
    #: "the last entry of `notes`" because `notes` is a report for the author
    #: and grows an entry whenever something else is worth saying. Reading a
    #: person-facing figure out of a list by position is how it silently becomes
    #: a different sentence. The same string is still appended to `notes`: the
    #: fact belongs in the report too, and it is one value written once, not two
    #: that can drift.
    how_much_over: str = ""


#: Leads the value so it survives a later prefix cap — Eve's reasoning, and it
#: is right (`compaction.ts:249-251`).
SHORTENED = "[shortened by PACT while tidying. Run the tool again for the full result.]"

#: Room left for the summary itself when a tail is sized by fit. Eve reserves
#: `min(2048, max(64, threshold/4))` (`compaction.ts:440-445`); the arithmetic
#: is right and is not a heuristic, so it stays here rather than becoming
#: another field for an author to get wrong.
SUMMARY_RESERVE = 2048


class Tidier:
    """Executes a `ContextPolicy` over a conversation."""

    def __init__(
        self,
        policy: ContextPolicy,
        budget_tokens: int,
        summarise: Summariser | None = None,
        measure: Measure = estimate,
        facts: "Facts | None" = None,
    ) -> None:
        self.policy = policy
        self.budget = budget_tokens
        self.summarise = summarise
        self.measure = measure
        #: What the run knows that the messages no longer carry (G9). Optional
        #: so every existing caller keeps working; absent, this is exactly the
        #: tidier it was before, which is the shape that lost the evidence.
        self.facts = facts

    @property
    def threshold(self) -> int:
        return max(1, int(self.budget * self.policy.when_full))

    def needed(self, messages: Sequence[Message]) -> bool:
        return bool(messages) and self.measure(messages) > self.threshold

    def _ladder(self, messages: Sequence[Message]) -> Tidied:
        """Run the ladder in `then:`, gentlest first, stopping as soon as it fits.

        Steps are **cumulative** — each sees what the one before it left. Eve
        runs its heuristic and its summariser on the same original split, and
        gets the same effect only because two independent constants happen to be
        equal (`TRANSCRIPT_PAYLOAD_LIMIT` is both the result cap and the
        transcript clip, `compaction-prompt.ts:196`). Making it structural means
        the summariser is guaranteed to see what capping left, rather than
        guaranteed by a coincidence that a later edit can break.
        """
        current = list(messages)
        before = self.measure(current)
        result = Tidied(
            messages=current,
            before=before,
            after=before,
            budget=self.budget,
            fits=before <= self.threshold,
        )
        if not self.needed(current):
            result.outcome = "not-needed"
            return result

        pinned = self.policy.pins.select(current)
        result.pinned = len(pinned)
        held = self.measure([current[i] for i in sorted(pinned)])
        if held > self.threshold:
            # Said out loud rather than resolved by quietly dropping a pin. The
            # author asked for these to survive; if that is impossible they need
            # to know, and they need to know which line to change.
            result.notes.append(
                f"what `always-keep` protects is already {held} of {self.threshold} "
                f"allowed — nothing else can be kept"
            )

        for step in self.policy.steps:
            current, note = self._run(step, current)
            result.fired.append(step.what)
            if note:
                result.notes.append(note)
            current = _repair_pairing(current, self.policy.pins, result.notes)
            result.messages = current
            result.after = self.measure(current)
            if result.after <= self.threshold:
                result.fits = True
                result.outcome = "fitted"
                return result

        result.messages = current
        result.after = self.measure(current)
        result.fits = result.after <= self.threshold
        if result.fits:
            result.outcome = "fitted"
            return result
        return self._give_up(result)

    def apply(self, messages: Sequence[Message]) -> Tidied:
        """Shorten, then say again what the run still knows (G9).

        The restating happens AFTER the ladder, never inside it, for the reason
        the ladder is cumulative in the first place: a fact re-stated before
        `drop-parts` runs is a fact `drop-parts` can throw away, and the whole
        point of a surviving fact is that no rung reaches it.

        A run with no declared facts gets the old behaviour exactly — same
        messages, same numbers — so this cannot change a workspace that never
        asked for it.
        """
        result = self._ladder(messages)
        if self.facts is None:
            return result

        lost = list(self.facts.forgotten)
        if lost:
            result.facts_lost = lost

        kept = self.facts.restated(_a_fact_message)
        if not kept:
            return result

        # Counted against the budget rather than added on top of it. A fact that
        # survives by pushing the history over the ceiling has not survived; it
        # has moved the failure one step later, where it is harder to read.
        result.messages = list(result.messages) + kept
        result.after = self.measure(result.messages)
        result.fits = result.after <= self.threshold
        result.facts_kept = [f.name for f, _ in self.facts.surviving()]
        result.notes.append(
            f"{len(kept)} fact(s) the run established were said again after "
            f"shortening: {', '.join(result.facts_kept)}"
        )
        return result

    def _give_up(self, result: Tidied) -> Tidied:
        """Everything ran and it still does not fit.

        Eve's ladder bottoms out and returns the oversized history with no
        signal (`compaction.ts:241`). Here the author chose in advance, and
        whichever they chose is written down.
        """
        told = (
            f"still {result.after - self.threshold} over after "
            f"{', '.join(result.fired) or 'no steps'} — nothing left to tidy that "
            f"`always-keep` allows"
        )
        choice = self.policy.if_it_still_does_not_fit
        if choice == "stop":
            raise StillTooLong(
                f"{self.policy.name}: {told}. `if-it-still-does-not-fit: stop`."
            )
        result.notes.append(told)
        # And on the record under its own name, because under `ask-a-person`
        # this is what a person is shown. `questions/too-long-to-send.yaml`
        # writes `shows: [how-much-over]`, and until this field existed that
        # line reached nobody — the park carried the right audience, the right
        # deadline and the right answer shape, and no words at all.
        result.how_much_over = told
        result.outcome = "asked-a-person" if choice == "ask-a-person" else "used-it-anyway"
        return result

    # ---------------------------------------------------------------- the steps

    def _run(self, step: Step, messages: list[Message]) -> tuple[list[Message], str]:
        if step.what == "shorten-long-results":
            return self._shorten(step, messages)
        if step.what == "drop-parts":
            return self._drop(step, messages)
        if step.what == "summarise-older":
            return self._summarise(step, messages)
        if step.what == "keep-recent-only":
            return self._keep_recent(step, messages)
        return messages, f"`{step.what}` is not a tidying move PACT knows; skipped"

    def _shorten(self, step: Step, messages: list[Message]) -> tuple[list[Message], str]:
        """Cap oversized tool results, keeping every message and its pairing.

        Most of a long conversation is a handful of large tool outputs, so this
        usually suffices with no model call at all. It is the one thing Eve's
        single heuristic does, and it is correct — kept as written.
        """
        cap = step.amount.characters if step.amount and step.amount.characters else 2000
        pinned = self.policy.pins.select(messages)
        out, cut = [], 0
        for i, m in enumerate(messages):
            if i in pinned:
                out.append(m)
                continue
            parts, touched = [], False
            for p in m.parts:
                if p.kind is PartKind.TOOL_RESULT and len(p.text) > cap:
                    parts.append(replace(p, text=f"{SHORTENED}\n\n{p.text[:cap]}"))
                    touched = True
                else:
                    parts.append(p)
            out.append(replace(m, parts=tuple(parts)) if touched else m)
            cut += 1 if touched else 0
        return out, f"shortened {cut} tool result(s) to {cap} characters" if cut else ""

    def _drop(self, step: Step, messages: list[Message]) -> tuple[list[Message], str]:
        """Remove one kind of content. This is the per-part rule.

        In Eve the equivalent is unreachable and unconditional: on every
        compaction `assistantMessageText` keeps text parts and discards
        reasoning (`compaction.ts:395-411`). Here thinking survives unless a
        step names it — and a pinned message keeps even the content this step
        would remove, because `always-keep` outranks every step.
        """
        if step.part is None:
            return messages, "nothing dropped: the step did not name a kind of content"
        pinned = self.policy.pins.select(messages)
        out, dropped = [], 0
        for i, m in enumerate(messages):
            if i in pinned or step.part not in m.kinds():
                out.append(m)
                continue
            trimmed = m.without(step.part)
            dropped += 1
            if not trimmed.is_empty():
                out.append(trimmed)
        return out, f"dropped {step.part.value} from {dropped} message(s)" if dropped else ""

    def _summarise(self, step: Step, messages: list[Message]) -> tuple[list[Message], str]:
        """Fold the older region into a checkpoint at the head.

        The previous checkpoint is carried into the new one, so summarising
        twice does not lose the first half of the conversation. Eve does this
        too and it is the best idea in its file (`compaction.ts:345-363`) — but
        it recognises its own checkpoint by comparing the message text to a
        constant sentence (`compaction.ts:349-356`), so a person who types that
        sentence forges one. Here it is a flag on the message and cannot be
        typed.
        """
        if self.summarise is None:
            # Loud, not silent. A policy that names a summariser and runs
            # without one must say so, or the author will believe it worked.
            named = f" for `{self.policy.summarised_by}`" if self.policy.summarised_by else ""
            return messages, f"could not summarise: no summariser was supplied{named}"

        older, recent = split_forward(messages, self._tail_size(step, messages))
        previous, older = _take_checkpoint(older)
        pinned = self.policy.pins.select(older)
        # A pinned message is not summarised away — it moves to the tail
        # verbatim, ahead of the recent window.
        held = [m for i, m in enumerate(older) if i in pinned]
        folding = [m for i, m in enumerate(older) if i not in pinned]
        if not folding:
            return messages, ""

        # Pictures and voice messages in the folded region survive into the
        # checkpoint. The summarising model is a text model and cannot fold them,
        # so folding them away would be "keep text, discard the rest" — the
        # behaviour `PartKind`'s docstring criticises Eve for, arriving through a
        # step the author wrote as `summarise-older` and never as `drop-parts`.
        # The rule this file works to is that a kind of content survives unless a
        # step names it, and `_drop` is the only step that names one.
        carried = tuple(
            p for m in folding for p in m.parts if p.kind in (PartKind.IMAGE, PartKind.AUDIO)
        )
        head = Message(
            role="assistant",
            parts=(Part(PartKind.TEXT, self.summarise(folding, previous)), *carried),
            checkpoint=True,
        )
        note = f"summarised {len(folding)} older message(s)"
        if carried:
            # Said out loud, because carrying them is a choice with a cost: a
            # checkpoint holding four photos is not small. An author who wants
            # them gone has a line to type, and it is the line that already means
            # that everywhere else in this file.
            kinds = sorted({p.kind.value for p in carried})
            note += (
                f"; kept {len(carried)} {', '.join(kinds)} part(s) the summariser "
                f"cannot read — add a `drop-parts` step naming `pictures` or "
                f"`audio` if they should go"
            )
        return [head, *held, *recent], note

    def _keep_recent(self, step: Step, messages: list[Message]) -> tuple[list[Message], str]:
        """Keep the tail, by size, count, or landmark — and keep every pin.

        The landmark form is why this exists. `the last 10 messages` is Eve's
        only option and is a different amount of conversation every time;
        `since the last approval` means the same thing on every run.
        """
        older, recent = split_forward(messages, self._tail_size(step, messages))
        pinned = self.policy.pins.select(older)
        held = [m for i, m in enumerate(older) if i in pinned]
        dropped = len(older) - len(held)
        return [*held, *recent], f"dropped {dropped} older message(s)" if dropped else ""

    def _tail_size(self, step: Step, messages: list[Message]) -> int:
        """How many messages the tail should be.

        Three forms, and none of them is a constant. With no `down-to:` the tail
        is sized to what actually fits after reserving room for the summary,
        which is what a fixed 10 is trying and failing to approximate.
        """
        amount = step.amount
        if amount is None:
            return self._fitting_tail(messages)
        if amount.messages is not None:
            return min(amount.messages, len(messages))
        if amount.characters is not None:
            return self._fitting_tail(messages, ceiling=amount.characters // CHARS_PER_TOKEN)
        if amount.landmark is not None:
            return _since(messages, amount.landmark)
        return self._fitting_tail(messages)

    def _fitting_tail(self, messages: Sequence[Message], ceiling: int | None = None) -> int:
        """Grow the tail backwards while it still fits."""
        room = (
            ceiling
            if ceiling is not None
            else self.threshold - min(SUMMARY_RESERVE, max(64, self.threshold // 4))
        )
        used, keep = 0, 0
        for m in reversed(messages):
            size = self.measure([m])
            if used + size > room:
                break
            used += size
            keep += 1
        return keep


# ────────────────────────────────────────────────────── structural invariants


def split_forward(messages: Sequence[Message], keep: int) -> tuple[list[Message], list[Message]]:
    """Split into (older, recent), snapping the boundary FORWARD past leading
    tool results.

    A kept tail must never open on a tool result whose call fell into the older
    region: every provider rejects a `tool_result` with no preceding `tool_use`.
    Eve does exactly this (`compaction.ts:464-467`) and it is one of the two
    things in its file worth copying as written.
    """
    if keep <= 0:
        return list(messages), []
    split = max(0, len(messages) - keep)
    while split < len(messages) and messages[split].role == "tool":
        split += 1
    return list(messages[:split]), list(messages[split:])


def _repair_pairing(messages: list[Message], pins: Pins, notes: list[str]) -> list[Message]:
    """Make tool calls and tool results agree, in BOTH directions.

    Eve handles one direction structurally (snap the split forward) and the
    other by blanket-stripping every tool-call part in its text-only tier
    (`compaction.ts:373-393`) — which throws away reasoning as a side effect,
    and is a large part of why reasoning-drop is not configurable there.
    Repairing the pairing directly means dropping a message never forces
    dropping a kind of content, so the two decisions stay separate.

    A pin wins. If a pinned tool result has lost its call, the call cannot be
    resurrected, so the *result* becomes plain text rather than disappearing —
    `always-keep` said keep it.
    """
    have_calls = {p.pairs_on for m in messages for p in m.parts if p.kind is PartKind.TOOL_CALL}
    have_results = {p.pairs_on for m in messages for p in m.parts if p.kind is PartKind.TOOL_RESULT}
    pinned = pins.select(messages)

    out: list[Message] = []
    orphan_results = orphan_calls = 0
    for i, m in enumerate(messages):
        parts: list[Part] = []
        rescued = False
        for p in m.parts:
            if p.kind is PartKind.TOOL_RESULT and p.pairs_on not in have_calls:
                if i in pinned:
                    parts.append(Part(PartKind.TEXT, p.text))
                    rescued = True
                else:
                    orphan_results += 1
                continue
            if p.kind is PartKind.TOOL_CALL and p.pairs_on not in have_results:
                orphan_calls += 1
                continue
            parts.append(p)
        # The ROLE has to change with the part, not only the part.
        #
        # A rescued result stopped being a `TOOL_RESULT` and its message stayed
        # `role: "tool"`, and `to_history` writes every part of a tool-role
        # message as `{"role": "tool", "name": p.tool, ...}` — where a TEXT part's
        # `tool` is `""`. Measured: a pinned `payments` result whose call had been
        # tidied away came out as the FIRST entry of the tidied history as
        # `{'role': 'tool', 'name': '', 'content': 'PAID 40.00 USD'}`, which
        # `anthropic_transport._to_messages` turns into a `tool_result` block with
        # no preceding `tool_use` — the exact orphan this function exists to
        # prevent, produced by the repair itself. Re-reading it with
        # `from_history` also turned the rescued TEXT part straight back into a
        # `TOOL_RESULT` with `pairs_on == ""`, so the repair did not survive one
        # round trip.
        #
        # `user` rather than `assistant`: a tool result is something that arrived,
        # not something the model said, and attributing it to the model would let
        # a pinned page read as the assistant's own words.
        role = "user" if rescued and m.role == "tool" else m.role
        repaired = replace(m, role=role, parts=tuple(parts))
        if not repaired.is_empty():
            out.append(repaired)

    if orphan_results or orphan_calls:
        notes.append(
            f"repaired {orphan_results} tool result(s) with no call and "
            f"{orphan_calls} call(s) with no result"
        )
    return out


def _take_checkpoint(messages: list[Message]) -> tuple[str, list[Message]]:
    """Lift an existing checkpoint out of the head so it is carried into the new
    summary rather than summarised again. Summarising a summary is how a
    conversation loses its beginning."""
    if messages and messages[0].checkpoint:
        return messages[0].text(), messages[1:]
    return "", messages


def _since(messages: Sequence[Message], landmark: str) -> int:
    """How many messages back the landmark is.

    `everything since the last approval` resolves through the same vocabulary a
    pin uses, so an author who learned one sentence form has learned both. A
    landmark matching nothing keeps everything — the safe direction, and the
    step reports that it dropped none.
    """
    lowered = landmark.casefold().strip()
    kind, target = PinKind.PHRASE, lowered
    for words in sorted(LABEL_WORDS, key=len, reverse=True):
        if words in lowered:
            kind, target = PinKind.LABEL, LABEL_WORDS[words]
            break
    probe = Pin(landmark, kind, target)
    for offset, m in enumerate(reversed(messages)):
        if probe.matches(m):
            return offset + 1
    return len(messages)


# ───────────────────────────────────────────────────────── harness interchange


def from_history(history: Iterable[dict[str, Any]]) -> list[Message]:
    """Read the harness's plain history into messages.

    Nothing is invented, and in particular **nothing is inferred from position**.
    A label like `first-request` is stamped once, by the run, at the moment the
    message is created; deriving it here from "the first entry with role user"
    would silently move it onto a later message the moment the original was
    folded into a summary — and `always-keep: the customer's original request`
    would then be pinning the wrong thing while still reporting a match.

    The one label derived here is `from:<tool>`, because a tool result names its
    tool on the entry itself and that is a fact about the message rather than
    about where it sits.
    """
    out: list[Message] = []
    for raw in history:
        role = str(raw.get("role") or "user")
        parts: list[Part] = []
        if role == "tool":
            name = str(raw.get("name") or "")
            parts.append(Part(PartKind.TOOL_RESULT, str(raw.get("content") or ""), name))
        else:
            if text := str(raw.get("content") or ""):
                parts.append(Part(PartKind.TEXT, text))
            if thinking := str(raw.get("thinking") or ""):
                parts.append(Part(PartKind.THINKING, thinking))
            for call in raw.get("tool_calls") or []:
                parts.append(Part(PartKind.TOOL_CALL, "", str(call)))

        stated = raw.get("labels")
        labels = {str(x) for x in stated} if isinstance(stated, list) else set()
        if role == "tool" and raw.get("name"):
            labels.add(f"from:{raw['name']}")

        out.append(
            Message(
                role=role,
                parts=tuple(parts),
                labels=frozenset(labels),
                checkpoint=bool(raw.get("checkpoint")),
            )
        )
    return out


def to_history(messages: Sequence[Message]) -> list[dict[str, Any]]:
    """Back to the harness's shape, losslessly.

    `checkpoint` travels as a flag rather than as a magic sentence. Eve carries
    it as the literal text "Summary of our conversation so far:" and recognises
    it by string equality (`compaction-prompt.ts:5`, `compaction.ts:349-356`),
    which means a person who types that line forges a checkpoint the framework
    will then refuse to touch.
    """
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "tool":
            for p in m.parts:
                out.append(
                    {"role": "tool", "name": p.tool, "content": p.text, **_marks(m)}
                )
            continue
        entry: dict[str, Any] = {
            "role": m.role,
            "content": "\n".join(p.text for p in m.parts if p.kind is PartKind.TEXT),
        }
        if calls := [p.pairs_on for p in m.parts if p.kind is PartKind.TOOL_CALL]:
            entry["tool_calls"] = calls
        if thinking := [p.text for p in m.parts if p.kind is PartKind.THINKING]:
            entry["thinking"] = "\n".join(thinking)
        out.append({**entry, **_marks(m)})
    return out


def _marks(m: Message) -> dict[str, Any]:
    marks: dict[str, Any] = {}
    if m.labels:
        marks["labels"] = sorted(m.labels)
    if m.checkpoint:
        marks["checkpoint"] = True
    return marks
