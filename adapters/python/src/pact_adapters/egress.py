"""What each of the six `allow-egress:` roles actually gates.

`workspace.yaml` offers six choices — `llm`, `stt`, `tts`, `embedder`, `judge`,
`reflector` — and until this module existed **one of them was read and five were
not**. Every check in the repository asked the same question, `"llm" in egress`,
in three places (`resolve.needs_of`, `judge.why_no_judge`, `scoring._pick_model`)
and one more in Rust. A per-role list was one boolean wearing six names, and
`allow-egress: [judge]` behaved in every respect exactly like `allow-egress: []`.

The rule, stated once here so the four call sites cannot drift apart:

* A binding is admitted when `allow-egress:` names **the role that binding
  plays**.
* `llm` is the general grant for *words* leaving this box, so it also admits the
  text roles that are particular kinds of model call — `judge`, `reflector`,
  `embedder`. A workspace that has already decided model calls may leave is not
  asked to decide again.
* `stt` and `tts` are **not** covered by `llm`. This is the one asymmetry, and it
  is the reason those two choices exist: if a grant for words carried speech
  with it, `stt` and `tts` would be exactly the decoration this module removes.
  D16 makes audio a first-class v1 modality, and an author who wrote
  `allow-egress: [llm]` approved a model call — not a recording of a customer
  speaking being posted to it.

Every message built from here quotes `allow-egress:` **as the author wrote it**.
Ledger row R56 records the last time that went wrong: the diagnostic hardcoded
`allow-egress: []`, so a workspace saying `[judge]` was told its own file said
something it does not, and an author who opens the file and sees otherwise stops
believing the checker.

The Rust half of the same rule is `crates/pact-cli/src/egress.rs`, which reaches
the author at `pact check` time. This half reaches whoever runs a suite or asks
for a recommendation, which is where the same mistake arrives second.
"""

from __future__ import annotations

from typing import Any

#: The six roles `allow-egress:` offers, in the order `spec/schema.yaml` lists
#: them. One tuple, so the day a seventh is added there is one place to come to.
ROLES: tuple[str, ...] = ("llm", "stt", "tts", "embedder", "judge", "reflector")

#: The roles that are a kind of model call over words, and so are admitted by the
#: general `llm` grant as well as by their own name.
WORDS: tuple[str, ...] = ("llm", "embedder", "judge", "reflector")

#: Every spelling `spec/schema.yaml`'s own `answer-shape` vocabulary accepts for
#: audio. Taken from that block rather than guessed: `accepts:` and
#: `answers-with:` are written in the author's words, and a check that only knew
#: the word `audio` would miss `a voice message`, which is precisely the spelling
#: the vocabulary was widened to accept.
AUDIO_SPELLINGS: frozenset[str] = frozenset(
    {"audio", "a recording", "a voice message", "list of audio"}
)


def granted(document: dict[str, Any]) -> list[str]:
    """The roles `allow-egress:` names, as written."""
    written = document.get("allow-egress")
    if not isinstance(written, list):
        return []
    return [str(role).strip() for role in written if str(role).strip()]


def listed(document: dict[str, Any]) -> str:
    """The author's own `allow-egress:` line, rendered the way they wrote it."""
    return "[" + ", ".join(granted(document)) + "]"


def admits(document: dict[str, Any], *roles: str) -> bool:
    """Does this workspace let a binding playing any of `roles` talk outside?

    Several roles because some bindings have more than one honest answer: a
    `graded-by:` is admitted by `judge` or by `llm`, and an agent whose
    `needs: audio: yes` says only that it must "hear or speak" is admitted by
    `stt` or by `tts` — demanding both would refuse a transcription agent for a
    reply it never speaks.
    """
    have = granted(document)
    for role in roles:
        if role in have:
            return True
        if role in WORDS and "llm" in have:
            return True
    return False


def _shape_is_audio(written: Any) -> bool:
    return str(written or "").strip().lower() in AUDIO_SPELLINGS


def _yes(written: Any) -> bool:
    if isinstance(written, bool):
        return written
    return str(written or "").strip().lower() in {"yes", "true", "on", "y"}


def carried(agent: dict[str, Any]) -> list[tuple[tuple[str, ...], str]]:
    """The speech this agent's own lines put in the envelope with the words.

    Returns `(roles that would allow it, the line the author wrote)` — so a
    diagnostic can quote the line rather than assert something about the agent
    the author has to go and verify.

    Only `accepts:`/`answers-with:` shapes and `needs: audio:`, because those are
    the three lines in the whole schema that say audio crosses the boundary.
    There is no `vision` role, so pictures cross under `llm` with nothing extra
    asked: this module enforces the list the schema declares and does not invent
    a seventh choice, since a role no author can write in `allow-egress:` would
    be the same defect in reverse.
    """
    out: list[tuple[tuple[str, ...], str]] = []
    for block, role in (("accepts", "stt"), ("answers-with", "tts")):
        rows = agent.get(block)
        if not isinstance(rows, dict):
            continue
        for name, shape in rows.items():
            if _shape_is_audio(shape):
                out.append(((role,), f"{block}: {name}: {shape}"))
                break
    if out:
        return out
    needs = agent.get("needs")
    if isinstance(needs, dict) and _yes(needs.get("audio")):
        out.append((("stt", "tts"), "needs: audio: yes"))
    return out


def missing_for(document: dict[str, Any], agent: dict[str, Any]) -> tuple[str, ...]:
    """The narrowest grant this agent needs and this workspace has not given.

    `()` when it may talk outside the box for everything its own lines say it
    sends. The first group that is missing, not all of them: one mistake gets one
    message, and an author with a line to change is not helped by three.
    """
    if not admits(document, "llm"):
        return ("llm",)
    for roles, _line in carried(agent):
        if not admits(document, *roles):
            return roles
    return ()


def grants(roles: "tuple[str, ...] | list[str]") -> str:
    """How a fix names the grants that would work — narrowest first.

    Never a bare "add `llm`" for a binding `llm` is merely the superset of: the
    advice a checker gives is what an author types, and advice that always says
    "grant everything" is not a per-role gate however carefully it reads one.
    """
    named = [f"`{role}`" for role in roles]
    if not named:
        return "a role"
    return " or ".join(named)
