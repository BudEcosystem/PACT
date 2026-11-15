"""The voice plan: what an agent's `voice:` lines come to, decided (96 §A6).

PACT's harness carries no audio stream — a phone line, a browser microphone
and a meeting bot are each a host's transport, and each speaks its own wire
protocol. What every one of them needs, and what is PACT's to decide, is the
same short list: which models listen, think and speak; whether the person may
talk over the agent; how long a pause ends a turn; and whether the sound itself
is kept. That is `VoicePlan`, made here from the document and the catalogue,
and handed to the host whole.

`pipeline: pact-picks` (or no `pipeline:` at all) is decided HERE, from the
catalogue, and the plan says why — the T7 rule that a choice PACT makes is a
choice PACT records:

* `talking: both-at-once` needs one model that listens while it speaks
  (`sessions: [duplex]`, audio in and out), so that is the only pipeline it
  can be.
* Otherwise, an agent whose own model hears and speaks uses it alone — one
  model answers sooner than three in a row.
* Otherwise, a transcriber, the agent's model and a speaker, served on this
  machine where the catalogue has one, so a caller's voice stays here when it
  can.

A plan that cannot be made — `both-at-once` with no duplex model anywhere —
says so in `why` with `pipeline` empty, rather than quietly taking turns.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .limits import seconds
from .resolve import Catalogue, ModelEntry, load_catalogue

__all__ = ["VoicePlan", "plan_for"]

#: `voice.pipeline:`, word by word.
PIPELINES = ("pact-picks", "transcribe-think-speak", "one-speech-model")
#: `voice.talking:`, word by word: whether the session must be duplex.
TALKING = {"takes-turns": False, "both-at-once": True}
#: `voice.keeps-the-audio:`, word by word: how long the sound outlives the call.
KEEPS = ("no", "for-this-run", "with-the-run-record")


@dataclass(frozen=True)
class VoicePlan:
    """What the host's voice transport is asked to do for one agent."""

    #: `transcribe-think-speak` or `one-speech-model`; `""` when none can be made.
    pipeline: str
    #: The model that turns speech into words, on `transcribe-think-speak`.
    hears_with: str = ""
    #: The model that answers — the agent's own, or the one speech model.
    thinks_with: str = ""
    #: The model that speaks the answer, on `transcribe-think-speak`.
    speaks_with: str = ""
    speaks_as: str = ""
    languages: tuple[str, ...] = ()
    #: Whether the person may talk while the agent is speaking.
    duplex: bool = False
    #: `turn-ends-after:` in seconds, or `None` for the transport's own.
    turn_ends_after: "float | None" = None
    may_be_interrupted: bool = True
    keeps_the_audio: str = "no"
    #: How the pipeline was decided, in one sentence, for the run's report.
    why: str = ""


def _hears_and_speaks(row: "ModelEntry | None") -> bool:
    return row is not None and {"audio_in", "audio_out"} <= set(row.capabilities)


def _duplex(row: "ModelEntry | None", raw: Mapping[str, Any]) -> bool:
    # The row carries its `sessions:` (`ModelEntry.sessions`); `raw` is read too
    # for a caller that still hands rows beside an entry built without them.
    said = ((raw.get("capabilities") or {}).get("sessions") or []) if raw else []
    sessions = set(row.sessions if row is not None else ()) | {str(s) for s in said}
    return _hears_and_speaks(row) and "duplex" in sessions


def plan_for(
    document: Mapping[str, Any],
    agent_key: str,
    catalogue: "Catalogue | None" = None,
    rows: "Mapping[str, Mapping[str, Any]] | None" = None,
) -> "VoicePlan | None":
    """The voice plan for one agent, or `None` when it writes no `voice:`.

    Which sessions a model can hold is read off its entry (`ModelEntry.sessions`).
    `rows`, the raw catalogue rows by id, is still read beside it, for a caller
    that built its entries by hand without them.
    """
    agent = ((document.get("agents") or {}).get(agent_key)) or {}
    voice = agent.get("voice")
    if not isinstance(voice, Mapping):
        return None
    catalogue = catalogue or load_catalogue()
    by_name = {e.name: e for e in catalogue.entries}
    raw = dict(rows or ((document.get("models") or {}).get("models") or {}))
    said = str(voice.get("pipeline") or "pact-picks").strip()
    # A word `pact check` would have refused is read as no choice at all, and
    # the plan says PACT picked — never a pipeline nobody wrote.
    if said not in PIPELINES:
        said = "pact-picks"
    duplex = TALKING.get(str(voice.get("talking") or "takes-turns").strip(), False)
    models = agent.get("model")
    own = (models[0] if isinstance(models, list) and models else models) or catalogue.default
    own = str(own or "")

    def first(kind: str) -> str:
        candidates = [e for e in catalogue.entries if e.kind == kind]
        local = [e for e in candidates if e.served_locally]
        return (local or candidates)[0].name if (local or candidates) else ""

    def one_model() -> str:
        if _duplex(by_name.get(own), raw.get(own, {})) or (
            not duplex and _hears_and_speaks(by_name.get(own))
        ):
            return own
        for e in catalogue.entries:
            if e.kind == "language" and (
                _duplex(e, raw.get(e.name, {})) if duplex else _hears_and_speaks(e)
            ):
                return e.name
        return ""

    common = dict(
        speaks_as=str(voice.get("speaks-as") or ""),
        languages=tuple(str(x) for x in (voice.get("languages") or [])),
        duplex=duplex,
        turn_ends_after=seconds(voice.get("turn-ends-after")) if voice.get("turn-ends-after") else None,
        may_be_interrupted=str(voice.get("may-be-interrupted", "yes")).strip() not in ("no", "False", "false"),
        keeps_the_audio=next(
            (k for k in KEEPS if k == str(voice.get("keeps-the-audio") or "no").strip()), "no"
        ),
    )
    if said == "one-speech-model" or (said == "pact-picks" and (duplex or _hears_and_speaks(by_name.get(own)))):
        speaker = one_model()
        if not speaker:
            return VoicePlan(
                pipeline="",
                why=(
                    "no model in the catalogue both hears and speaks"
                    + (" while it listens" if duplex else "")
                    + ", so this agent cannot be talked to yet; add one, or write "
                    "`talking: takes-turns` with `pipeline: transcribe-think-speak`"
                ),
                **common,
            )
        return VoicePlan(
            pipeline="one-speech-model",
            thinks_with=speaker,
            why=(
                f"`{speaker}` hears and speaks itself"
                + (", and can listen while it speaks" if duplex else "")
                + ("" if said == "one-speech-model" else "; PACT picked it")
            ),
            **common,
        )
    hears = str(voice.get("hears-with") or "") or first("transcription")
    speaks = str(voice.get("speaks-with") or "") or first("speech")
    return VoicePlan(
        pipeline="transcribe-think-speak",
        hears_with=hears,
        thinks_with=own,
        speaks_with=speaks,
        why=(
            f"`{hears}` turns speech into words, `{own}` answers, and `{speaks}` speaks it"
            + ("" if said == "transcribe-think-speak" else "; PACT picked them")
        ),
        **common,
    )
