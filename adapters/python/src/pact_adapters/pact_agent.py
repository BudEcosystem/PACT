"""A PACT agent wearing a Pydantic AI face, with PACT still driving.

`pydantic_ai_interop.build_agent()` is the other door and it makes the opposite
trade: it hands somebody a real `pydantic_ai.Agent`, and its own docstring names
what stops being enforced on the way over — *"The loop is Pydantic AI's. `loop:`
stages, `interceptors:`, `teamwork:`, `context-policy:`, `remembers:` and
`when-it-runs-out:` are PACT harness behaviour and this agent has none of
them."*

`PactAgent` is the same wish and the opposite trade, and it is the one D12 /
FR-4.1.1 asks for. The OBJECT is a `pydantic_ai.agent.abstract.AbstractAgent`,
so it goes wherever an `Agent` goes; the LOOP is still `harness.run` over
`PydanticAITransport`, so Pydantic AI carries one model call at a time and every
authored stage, ceiling, rule and gate is the one that runs.

Three things follow from that, and they are the whole of this file.

**A surface is where a shim can lie.** This SDK asks eleven abstract members
what the agent is, believes every answer and shows them to people. Every one of
them here is answered from the author's document — the model id through the
catalogue, the answer shape through `_output_type_for`, the tools through
`_takes_as_schema` — because a member answered with this SDK's default instead
is a silent divergence between what `pact check` printed OK for and what a
caller sees.

**Two things cannot be answered at all, and both say so out loud.** `iter()`
hands out a live handle onto `_agent_graph`'s node stream, which PACT's loop
does not have and must not invent; a caller-supplied `usage_limits=` would be a
second enforcer of ceilings `limits.py` already holds, and the second one wins
by raising. Translate or nothing, said in a sentence naming the reason — a
refusal with no reason is the same defect as a silent drop, because the caller's
next move depends entirely on why.

**A run that stopped must not arrive shaped like a run that finished.**
`harness.RunResult.output` is typed `str` and every halt path writes an English
sentence into it — and the `stage-limit` path writes `result.steps[-1].text`,
which on an agent declaring `answers-with:` is a value that PARSES AS THE
DECLARED SHAPE. Measured on `examples/refund-desk`: a run that abandoned the
author's `loop:` handed back `{"decision": "approved", …, "amount": "40 USD"}`,
byte-identical to the same script's answer under `pact:loop/standard`. So a halt
is a TYPE here (`Halted`), the way this SDK already returns
`DeferredToolRequests` for the other thing that is not an answer.

The two dialect crossings live here too (`to_model_messages`, `to_pact_history`)
because they are what makes an `AgentRunResult` carry the conversation the run
actually had. They are asymmetric on purpose: the PACT dialect is the smaller
vocabulary, so only the Pydantic-AI-to-PACT direction can lose, and only that
direction carries a report.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import inspect
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Mapping, Sequence, TypeVar

from pydantic_ai import DeferredToolRequests
from pydantic_ai.agent.abstract import AbstractAgent
from pydantic_ai.exceptions import UserError
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.run import AgentRunResult
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets.external import ExternalToolset
from pydantic_ai.usage import RunUsage

from . import harness
from .exporting import ExportReport
from .harness import CHOSEN_ANSWER_MODE, RunResult, _system_for, slots_of
from .ir import AgentSpec
from .limits import Reached
from .pydantic_ai_interop import (
    _output_type_for,
    _takes_as_schema,
    pydantic_ai_model_id,
)
from .script import Script
from .suspension import (
    ASKED_A_PERSON,
    CONTEXT_TOO_LONG,
    OUT_OF_BUDGET,
    Resumption,
    Suspension,
)
from .transports.pydantic_ai_transport import PydanticAITransport

#: Where a PACT entry's `labels:` and `checkpoint` ride while it is a
#: `ModelMessage`. Both `ModelRequest` and `ModelResponse` carry
#: `metadata: dict[str, Any] | None` and neither has a field for either mark, so
#: this is the only slot in the SDK's dialect that can hold them — and holding
#: them is not decoration: `always-keep: the customer's original request` matches
#: on a label, and `Pins.select` puts every checkpoint in the kept set because a
#: checkpoint is the compressed form of everything already dropped. A crossing
#: that loses them leaves the author's line matching nothing and lets the next
#: tidy summarise a summary.
_MARKS_KEY = "pact"


# ─────────────────────────────────────────── what a run that did not answer is



_R = TypeVar("_R")


def _run_until_complete(coro: "Awaitable[_R]") -> _R:
    """Drive `coro` on the caller's event loop, cleaning up after it if interrupted.

    What `AbstractAgent.run_sync` does to enter an async run from sync code,
    written with `asyncio`'s public API. It used to be imported from
    `pydantic_ai._utils`, a private module this package may not read: a name
    with an underscore is one the SDK is free to move in any release, and a
    host that forbids private upstream imports could not import this module at
    all. On an interrupt (Ctrl-C) the run's own task is cancelled and drained,
    so its `finally` blocks run; no other task on the caller's loop is touched.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    task = asyncio.ensure_future(coro, loop=loop)
    try:
        return loop.run_until_complete(task)
    except BaseException:
        if not task.done():
            task.cancel()
            with contextlib.suppress(BaseException):
                loop.run_until_complete(task)
        raise


@dataclass(frozen=True)
class Halted:
    """A run that stopped, typed so nothing has to read English to find out.

    Deliberately not a `str` and not a `Mapping`. Those are the two shapes a
    caller downstream would go on treating as an answer: a validator, a
    `pydantic_evals` case, a second agent taking this one's output as input, a
    type checker. A distinct type is the only check a downstream consumer can
    actually perform without parsing prose in a language that can change.

    Nothing the harness knew is discarded to make room for the type — that would
    trade one lie for a silence. `words` is the sentence the harness composed,
    which names the setting, both figures and something to type (D13);
    `stopped_by` is the ceiling as a VALUE, because "ran out and answered anyway"
    can only be told from "finished" by reading it, and recovering those figures
    by regex from `Stopped before finishing: … (2 of 2 steps).` is not a caller
    reading a contract.

    A park arrives here too, with `halted == "suspended"`. The record a resume
    needs is not copied onto this object — it is `RunResult.suspension`, reachable
    from `AgentRunResult.pact`, and one copy of it is what keeps the two from
    disagreeing about what a run was waiting for.
    """

    #: `RunResult.halted` verbatim: `step-limit`, `stopped-by-rule`,
    #: `stage-limit`, `suspended`, and whatever the harness adds next. Copied
    #: rather than re-derived so this cannot come to disagree with `.pact`.
    halted: str
    #: Which ceiling ended it, if one did.
    stopped_by: "Reached | None" = None
    #: The words the run wrote. The only thing a person can read.
    words: str = ""


#: The reasons a run parks with NO call pending, which is why they are the ones
#: this SDK has no park-shaped VALUE for.
#:
#: `DeferredToolRequests` IS a pending call — `approvals=[ToolCallPart(…)]` — so
#: `needs-approval`, `needs-permission` and `waiting-for-another-agent` have
#: something to put in it, and every consumer of this SDK already knows how to
#: route one and how to answer it. These three stop the run BETWEEN calls: a
#: `does: ask-someone` stage, a ceiling whose `when-it-runs-out:` is
#: `ask-a-person`, and a conversation the tidier could not fit. Nothing is
#: pending, so there is nothing to hand over in this SDK's own shape.
#:
#: Named from `suspension` rather than spelled out here, so a reason renamed
#: there is renamed once — and so this list cannot come to disagree with the
#: harness about which parks carry `awaiting`.
_PARKS_WITH_NOTHING_PENDING: tuple[str, ...] = (
    ASKED_A_PERSON,
    OUT_OF_BUDGET,
    CONTEXT_TOO_LONG,
)


class PactSuspended(Exception):
    """A run that is still WAITING, raised because waiting is not a value.

    A park is not an ending. The run continues the moment somebody answers, and
    it continues as THIS run: `Suspension` carries the history, the stage it had
    reached, the meter, the permissions already granted and the `same-request-key`
    ledger, precisely so a run cannot be handed a fresh budget or a fresh
    at-most-once record by being interrupted (D23). So the caller of a parked run
    has exactly one correct next move — put `in_words` in front of somebody and
    hand their answer back — and any RETURNED value is a value that can be
    dropped on the floor instead. `result = await agent.run(…)` whose `.output`
    is logged and forgotten ends with a person never asked, the spend already
    made never used, and nothing anywhere reporting it. An exception is the one
    outcome a caller cannot fail to notice, and that is the whole reason this is
    raised rather than returned.

    **Measured on `examples/refund-desk`**, whose `limits.yaml` says
    `when-it-runs-out: ask-a-person`: a run that reaches a ceiling parks under
    `out-of-budget` with `awaiting == ()`, and this door RETURNED it. A caller
    who did not know to type-check `.output` read the run's own mid-run words as
    the desk's decision; one who did was told by a `Halted` that the run had
    STOPPED. It had not — it is waiting, and on both readings the person who can
    end the wait is never shown the question. That is the silence a park must
    never give.

    **Only the parks with nothing pending** (`_PARKS_WITH_NOTHING_PENDING`). An
    approval, a permission and a teammate's work park WITH a call, and they keep
    returning `DeferredToolRequests`: that is this SDK's own word for "a call is
    waiting for a person", it is already the shape `build_agent` parks in, and
    its own resume path leads back into a run rather than away from one.

    Nothing the run knew is lost by raising, which is the rule `Halted` follows
    one type up: `parked` is `RunResult.suspension` itself — the same object,
    never a copy, so the two cannot disagree about what the run is waiting for —
    and `result` is the `AgentRunResult` this door would have returned, carrying
    the conversation, the spend and `.pact`.
    """

    def __init__(self, parked: Suspension, result: "AgentRunResult[Any]") -> None:
        self.parked = parked
        self.result = result
        super().__init__(
            f"this run is waiting, not finished: {parked.reason}. "
            + (f"It is asking:\n\n{parked.in_words}\n\n" if parked.in_words else "")
            + "Nothing has been answered, and no value belongs on `.output` for "
            "a run that has not answered — a returned park is one a caller can "
            "drop, and dropping it leaves the person never asked and the work "
            "already paid for thrown away. fix: show `.parked.in_words` to "
            + (", ".join(parked.who_can_answer) or "whoever can answer")
            + ", then continue THIS run by handing the record back as `resume=` "
            "with their answer as `answer=` — the two arguments `harness.run` "
            "takes. `.parked.answer(**values)` types what they said and refuses "
            "an answer to a wait this run has moved past. What the run had done "
            "up to the park is on `.result`, and its PACT record on "
            "`.result.pact`."
        )


# ──────────────────────────────────────────────────── the two message dialects


def to_model_messages(history: "Sequence[Mapping[str, Any]]") -> list[ModelMessage]:
    """PACT's plain history into this SDK's messages. Total — nothing is lost.

    The PACT dialect is the smaller vocabulary, so this direction cannot lose
    and carries no report. What it CAN do is reshape, and the measured example
    of that is `transports/pydantic_ai_transport._to_messages`: it keeps only
    `user` and `tool` entries, drops every assistant turn, and stamps
    `tool_call_id="c0"` on every tool result. With one call per turn that is
    wrong and harmless; with two it is two results claiming to answer one call
    that is not even there, and every provider rejects a `tool_result` with no
    preceding `tool_use`.

    So three things are structural here rather than incidental.

    * **Every assistant turn crosses**, with its text and its calls. A resumed
      conversation is where dropping them bites: the model is shown a tool result
      for a call it cannot see it made.
    * **Ids are minted per call and matched in order.** The PACT dialect pairs on
      the TOOL NAME — `harness.run` writes `tool_calls: [c.name for c in ran]`
      and then one entry per call in the same order — so ORDER is the only thing
      that says which result answers which call, and a constant id transposes
      them silently.
    * **All the results of one turn land in ONE `ModelRequest`.** Split across
      two the conversation reads `assistant → user → user`, which Anthropic
      rejects outright — and again only when the model made more than one call,
      so it survives every single-call test.
    * **A tool entry's marks ride with it, in that same order.** They are real on
      a tool entry and not only on a user turn: `context_policy.to_history`
      writes `_marks(m)` onto every tool entry it emits, `from_history` stamps
      `from:<name>` there and nowhere else, and that label is what a `SOURCE` pin
      — `always-keep: anything the payments tool returned` — matches on. A
      request built with no `metadata=` drops them, and this direction carries no
      report, so the loss would be the silent one.
    """
    out: list[ModelMessage] = []
    #: Calls made by the last model turn and not yet answered, as
    #: `(tool_call_id, tool name)`. A tool result claims the first unanswered
    #: call of its own name, falling back to the oldest unanswered call — which
    #: is what `zip(ran, outputs)` in `harness.run` means by "in the same order".
    unanswered: list[tuple[str, str]] = []
    returning: list[ToolReturnPart] = []
    #: One marks mapping per part in `returning`, positionally, because the
    #: several results of one turn share a single `ModelRequest` and
    #: `_written_marks` reads them back by the index of the PACT entry the part
    #: becomes. An unmarked result holds `{}` rather than being skipped: a gap
    #: would shift every later result onto somebody else's labels.
    returning_marks: list[dict[str, Any]] = []
    minted = 0

    def flush() -> None:
        if returning:
            out.append(
                ModelRequest(
                    parts=list(returning),
                    metadata=(
                        {_MARKS_KEY: list(returning_marks)}
                        if any(returning_marks)
                        else None
                    ),
                )
            )
            returning.clear()
            returning_marks.clear()

    for entry in history:
        role = str(entry.get("role") or "user")
        if role == "tool":
            name = str(entry.get("name") or "")
            answers = _claim(unanswered, name)
            if answers is None:
                # A result whose call was tidied away, or a history assembled by
                # something else. A fresh id keeps it well-formed rather than
                # pairing it with somebody else's call.
                minted += 1
                answers = f"{name or 'tool'}#{minted}"
            returning.append(
                ToolReturnPart(
                    tool_name=name,
                    content=entry.get("content"),
                    tool_call_id=answers,
                )
            )
            returning_marks.append(_mark_of(entry))
            continue

        flush()
        marks = _marks_of(entry)
        if role == "assistant":
            parts: list[Any] = []
            if text := str(entry.get("content") or ""):
                parts.append(TextPart(content=text))
            if thinking := str(entry.get("thinking") or ""):
                parts.append(ThinkingPart(content=thinking))
            unanswered = []
            for call in entry.get("tool_calls") or ():
                minted += 1
                name = str(call)
                slot = f"{name}#{minted}"
                unanswered.append((slot, name))
                parts.append(ToolCallPart(tool_name=name, tool_call_id=slot))
            out.append(ModelResponse(parts=parts, metadata=marks))
            continue

        out.append(
            ModelRequest(
                parts=[UserPromptPart(content=str(entry.get("content") or ""))],
                metadata=marks,
            )
        )
    flush()
    return out


def to_pact_history(
    messages: "Sequence[ModelMessage]",
) -> "tuple[list[dict[str, Any]], ExportReport]":
    """This SDK's messages into PACT's plain history, and what that cost.

    The lossy direction, and the only one with a report. A live Pydantic AI
    conversation carries four things this dialect has no room for at all — a
    `RetryPromptPart`, a thinking block's `signature`, `provider_details`, and
    per-request `usage` — and dropping them is allowed. Dropping them QUIETLY is
    not: that is the silent degradation T7 forbids, and every other crossing in
    this package (`ExportReport`, `ImportReport`) already refuses it.

    `ExportReport` is reused rather than reinvented for the reason its own
    `silent_losses` gives: the report's bucket lists are opinions, and the sweep
    over `seen` is the check on them. Anything this SDK grows that the sweep
    finds and neither bucket names is reported as a bug in this crossing rather
    than lost — which is the only version of "nothing crosses in silence" that
    stays true after somebody else edits the SDK.

    Three parts are read for their content rather than merely named:

    * a `ThinkingPart` becomes the entry's `thinking:` key and NOT part of
      `content:`. Folding it into the text is what makes reasoning into speech —
      `drop-parts: the model's own thinking` stops matching, and the words reach
      the next model call as the agent's own answer.
    * a `RetryPromptPart` becomes nothing. It is a `ModelRequestPart`, so the
      lazy reading — every request part is a user turn — turns "that is not valid
      JSON" into something the customer said, and PACT's harness then re-runs a
      correction another framework's loop already applied.
    * `ModelRequest.instructions` becomes nothing. It carries whatever agent
      produced the conversation, so a history handed in from elsewhere is that
      agent's system prompt arriving beside the author's own `instructions.md` —
      the one input a governed agent's author does not control, coming through
      the door meant for the customer's words.
    """
    report = ExportReport(kind="a PACT conversation", seen=_seen_in(messages))
    for key in report.seen:
        _file(key, report)

    history: list[dict[str, Any]] = []
    for message in messages:
        if isinstance(message, ModelResponse):
            entry: dict[str, Any] = {
                "role": "assistant",
                "content": "\n".join(
                    p.content for p in message.parts if isinstance(p, TextPart)
                ),
            }
            if calls := [
                p.tool_name for p in message.parts if isinstance(p, ToolCallPart)
            ]:
                entry["tool_calls"] = calls
            if thinking := [
                p.content for p in message.parts if isinstance(p, ThinkingPart)
            ]:
                entry["thinking"] = "\n".join(thinking)
            # A turn with no text, no call and no reasoning is not a turn. It
            # would read back through `from_history` as an empty message, which
            # `_repair_pairing` then drops — a message this crossing invented and
            # the tidier deleted, reported as a repair.
            if entry["content"] or len(entry) > 2:
                history.append({**entry, **_written_marks(message, 0)})
            continue

        said = [p for p in message.parts if isinstance(p, UserPromptPart)]
        nth = 0
        for part in said:
            text, unspoken = _as_text(part.content)
            if unspoken:
                report.not_carried[
                    "ModelRequest.parts[UserPromptPart].content — not text"
                ] = unspoken
            history.append(
                {"role": "user", "content": text, **_written_marks(message, nth)}
            )
            nth += 1
        for part in message.parts:
            if isinstance(part, ToolReturnPart):
                text, unspoken = _as_text(part.content)
                if unspoken:
                    report.not_carried[
                        "ModelRequest.parts[ToolReturnPart].content — not text"
                    ] = unspoken
                history.append(
                    {
                        "role": "tool",
                        "name": part.tool_name,
                        "content": text,
                        **_written_marks(message, nth),
                    }
                )
                nth += 1
    return history, report


def _claim(unanswered: list[tuple[str, str]], name: str) -> "str | None":
    """Which call this result answers, by name first and by order second.

    By name because a turn can call two different tools and a provider is free
    to return their results in either order; by order because a turn can call
    ONE tool twice, and then the order is the only thing that distinguishes the
    two — which is the case every constant-id shortcut survives.
    """
    for i, (slot, called) in enumerate(unanswered):
        if called == name:
            del unanswered[i]
            return slot
    return unanswered.pop(0)[0] if unanswered else None


def _mark_of(entry: "Mapping[str, Any]") -> "dict[str, Any]":
    """One PACT entry's marks alone, for a message that carries several entries.

    Split out rather than inlined at the tool branch so the two crossings read
    the same two keys from the same place. A tool entry shares its `ModelRequest`
    with every other result of its turn, so what it needs is the bare mapping to
    put at its own position — where a user turn owns its request and takes the
    one-element list `_marks_of` builds.
    """
    marks: dict[str, Any] = {}
    if isinstance(entry.get("labels"), list):
        marks["labels"] = [str(x) for x in entry["labels"]]
    if entry.get("checkpoint"):
        marks["checkpoint"] = True
    return marks


def _marks_of(entry: "Mapping[str, Any]") -> "dict[str, Any] | None":
    """A PACT entry's `labels:` and `checkpoint`, in the slot the SDK has."""
    marks = _mark_of(entry)
    return {_MARKS_KEY: [marks]} if marks else None


def _written_marks(message: Any, nth: int) -> "dict[str, Any]":
    """The marks this message is carrying for the `nth` PACT entry it becomes.

    A list rather than one mapping because one `ModelRequest` can become several
    PACT entries — every tool result of a turn rides in a single request, and
    each of them is its own entry with its own labels.
    """
    written = (getattr(message, "metadata", None) or {}).get(_MARKS_KEY)
    if not isinstance(written, list) or nth >= len(written):
        return {}
    marks = written[nth]
    return dict(marks) if isinstance(marks, Mapping) else {}


def _as_text(content: Any) -> tuple[str, str]:
    """One part's content as the string PACT's dialect holds, and what was not.

    The PACT dialect is text. A multimodal prompt and a structured tool return
    are both real and neither has a home here, so what does not cross comes back
    as a sentence for the caller rather than as a `str()` of an object.
    """
    if isinstance(content, str):
        return content, ""
    if isinstance(content, (list, tuple)):
        spoken = [c for c in content if isinstance(c, str)]
        if len(spoken) == len(content):
            return "\n".join(spoken), ""
        return "\n".join(spoken), (
            "the part carried images, audio or files beside its text, and a PACT "
            "history entry is `content:` — one string. Only the text crossed. "
            "fix: nothing to type; the conversation has to be handed over in a "
            "dialect that carries them"
        )
    try:
        return json.dumps(content), ""
    except (TypeError, ValueError):
        return str(content), (
            "the content was an object this could not write as JSON, so the "
            "entry carries `str()` of it. fix: hand tool results back as text "
            "or as something JSON can hold"
        )


# ────────────────────────────── the sweep, and the two buckets it is checked on


def _seen_in(messages: "Sequence[ModelMessage]") -> tuple[str, ...]:
    """Every field of this conversation that is carrying something.

    Mechanical, from `dataclasses.fields`, because the point of the report is to
    survive somebody else editing the SDK. A field is *carrying something* when
    it differs from what this SDK would have put there by itself — which is what
    makes `ModelResponse.usage` on a message with no usage silent and the same
    field on a message with 11 input tokens loud, without either being written
    down anywhere.
    """
    seen: list[str] = []
    for message in messages:
        kind = type(message).__name__
        for field in dataclasses.fields(message):
            if field.name == "parts":
                continue
            value = getattr(message, field.name, None)
            if not _carrying(field, value):
                continue
            if field.name == "metadata" and isinstance(value, Mapping):
                seen += [f"{kind}.metadata[{key}]" for key in value]
                continue
            seen.append(f"{kind}.{field.name}")
        for part in getattr(message, "parts", ()) or ():
            if not dataclasses.is_dataclass(part):
                continue
            named = type(part).__name__
            for field in dataclasses.fields(part):
                if _carrying(field, getattr(part, field.name, None)):
                    seen.append(f"{kind}.parts[{named}].{field.name}")
    return tuple(dict.fromkeys(seen))


def _carrying(field: Any, value: Any) -> bool:
    """Whether this field holds anything but what the SDK would have defaulted.

    The factory branch is what keeps the sweep honest in both directions: a
    `ToolCallPart.tool_call_id` is generated per instance so it never equals a
    fresh one and is always reported, while a `ModelResponse.usage` nobody filled
    in equals a fresh `RequestUsage()` and is not.
    """
    if value is None or value == "":
        return False
    if field.default is not dataclasses.MISSING:
        return bool(value != field.default)
    if field.default_factory is not dataclasses.MISSING:
        try:
            return bool(value != field.default_factory())
        except Exception:
            return True
    return True


def _file(key: str, report: ExportReport) -> None:
    """Put one swept field in a bucket, or leave it for `silent_losses`.

    No fallback bucket, deliberately. A field neither table names is a field
    nobody decided about, and `ExportReport.silent_losses` reports it as a bug in
    this crossing — which is the whole difference between a report and a list
    somebody has to remember to extend.
    """
    lookup = _lookup(key)
    if lookup in _CARRIED:
        report.carried[key] = _CARRIED[lookup]
    elif lookup in _NO_ROOM_FOR:
        report.not_carried[key] = _NO_ROOM_FOR[lookup]


def _lookup(key: str) -> str:
    """A swept field's key, reduced to the thing the tables are written about.

    `ModelRequest.parts[TextPart].content` and
    `ModelResponse.parts[TextPart].content` are one decision about `TextPart`,
    and writing it twice is how the two come to disagree.
    """
    if ".parts[" in key:
        return key.split(".parts[", 1)[1].replace("].", ".", 1)
    if ".metadata[" in key and key.endswith("]"):
        inside = key.split(".metadata[", 1)[1][:-1]
        return "metadata.pact" if inside == _MARKS_KEY else "metadata.elsewhere"
    return key


#: Why a foreign field of a live conversation has no home in a PACT history.
#:
#: A reason and not a label, because *which kind of thing it is* decides whether
#: losing it matters, and a reader deciding whether to hand this history to a
#: governed agent needs the consequence rather than the name.
_NO_ROOM_FOR: dict[str, str] = {
    "ModelRequest.instructions": (
        "whatever agent produced this conversation put its own system prompt "
        "here. Pasting it into a PACT history would reach the model beside the "
        "author's `instructions.md` — the one input a governed agent's author "
        "does not control, arriving through the door meant for the customer's "
        "words. fix: nothing to type; instructions are the agent's, not the "
        "conversation's"
    ),
    "ModelRequest.timestamp": (
        "a PACT history entry is what was said, not when. Nothing in the format "
        "reads a per-message time and inventing a key for one would make two "
        "runtimes disagree about a field neither uses"
    ),
    "ModelRequest.run_id": (
        "which run produced the turn. PACT's own record of a run is "
        "`RunResult`, and a history entry that also claimed a run id would be a "
        "second answer to the same question"
    ),
    "ModelRequest.conversation_id": (
        "no field for it: PACT's harness is handed one conversation and the "
        "caller owns the identity of it"
    ),
    "ModelRequest.state": (
        "this SDK's marker for a message still being built. A PACT history is "
        "what has already been said"
    ),
    "ModelRequest.kind": "the SDK's own discriminator; `role:` is PACT's",
    "ModelResponse.usage": (
        "what this one request cost. `tokens-at-most` counts it, so a "
        "conversation imported without it starts the author's ceiling from zero "
        "on a conversation that has already spent. fix: nothing to type — the "
        "spend that reaches a ceiling is this run's own, on `RunResult.used`"
    ),
    "ModelResponse.model_name": (
        "which model said it. PACT binds a catalogue ROW for the whole run "
        "(`model:`), so a per-message model would be a second, quieter answer to "
        "`which model is this agent running on`"
    ),
    "ModelResponse.provider_name": (
        "who served it. Same reason as `model_name`: the binding is the run's, "
        "and `RunResult.unmetered` is where a run says what it could not "
        "attribute"
    ),
    "ModelResponse.provider_url": "the endpoint that served it — deployment, "
                                  "which PACT deliberately does not own",
    "ModelResponse.provider_details": (
        "the only record of WHY the provider stopped — a truncation, a refusal, "
        "a filter. A conversation resumed without it looks like one that ended "
        "because the model had finished"
    ),
    "ModelResponse.provider_response_id": (
        "the provider's own handle on the call, for their support to trace. "
        "Nothing in a PACT history is addressed to a provider"
    ),
    "ModelResponse.finish_reason": (
        "this SDK's normalised stop reason. PACT's word for how a run ended is "
        "`RunResult.halted`, and it is about the RUN rather than about one call"
    ),
    "ModelResponse.timestamp": "as `ModelRequest.timestamp`",
    "ModelResponse.run_id": "as `ModelRequest.run_id`",
    "ModelResponse.conversation_id": "as `ModelRequest.conversation_id`",
    "ModelResponse.state": "as `ModelRequest.state`",
    "ModelResponse.kind": "as `ModelRequest.kind`",
    "metadata.elsewhere": (
        "metadata written by whatever produced this conversation. A PACT entry "
        "has `labels:` and `checkpoint` and nothing else, and carrying somebody "
        "else's keys through would put values into a history a context policy "
        "then matches on"
    ),
    "SystemPromptPart.content": (
        "a system prompt that arrived inside a conversation. PACT's system text "
        "is built per stage from the author's `instructions.md`, their skills "
        "and their `answers-with:` — the same reason `ModelRequest.instructions` "
        "does not cross"
    ),
    "SystemPromptPart.timestamp": "as `ModelRequest.timestamp`",
    "SystemPromptPart.dynamic_ref": (
        "the handle this SDK re-evaluates a dynamic system prompt by. There is "
        "nothing on the far side to re-evaluate it"
    ),
    "UserPromptPart.timestamp": "as `ModelRequest.timestamp`",
    "TextPart.id": "this SDK's handle for streaming a part in fragments; a PACT "
                   "history holds finished turns",
    "TextPart.provider_name": "as `ModelResponse.provider_name`",
    "TextPart.provider_details": "as `ModelResponse.provider_details`",
    "ThinkingPart.signature": (
        "the token a provider requires before it will accept a thinking block "
        "back. The reasoning TEXT crosses as `thinking:`, so an author's "
        "`drop-parts: the model's own thinking` still finds it — but a block "
        "that crosses without its signature cannot be re-sent even though its "
        "words survived"
    ),
    "ThinkingPart.id": "as `TextPart.id`",
    "ThinkingPart.provider_name": "as `ModelResponse.provider_name`",
    "ThinkingPart.provider_details": "as `ModelResponse.provider_details`",
    "ToolCallPart.args": (
        "what the call carried. `tool_calls:` holds NAMES — `from_history` gives "
        "each entry a `pairs_on` of `str(entry)` — so writing the arguments "
        "there would give the call a `pairs_on` matching no tool result "
        "anywhere, and the next `_repair_pairing` would delete every call in the "
        "conversation. A model resuming this will not see what it asked for"
    ),
    "ToolCallPart.tool_call_id": (
        "the provider's handle on the call. PACT pairs on the TOOL NAME, so this "
        "is minted afresh on the way back rather than carried — a history that "
        "kept it would pair on a string no PACT tool result ever holds"
    ),
    "ToolCallPart.tool_kind": (
        "whether this SDK considers the tool a function, a builtin or an "
        "external one. PACT's tools are the author's `tools/<name>.yaml`, and "
        "which runtime executes one is not a fact about the conversation"
    ),
    "ToolCallPart.id": "as `TextPart.id`",
    "ToolCallPart.provider_name": "as `ModelResponse.provider_name`",
    "ToolCallPart.provider_details": "as `ModelResponse.provider_details`",
    "ToolReturnPart.tool_call_id": "as `ToolCallPart.tool_call_id`",
    "ToolReturnPart.tool_kind": "as `ToolCallPart.tool_kind`",
    "ToolReturnPart.metadata": (
        "a payload this SDK carries beside a tool result for its own tools to "
        "read. A PACT tool result is `content:`, and the author's rules read that"
    ),
    "ToolReturnPart.timestamp": "as `ModelRequest.timestamp`",
    "ToolReturnPart.outcome": (
        "whether this SDK considers the call to have failed. PACT records a "
        "failure as what the tool returned, which is what the author's "
        "interceptors and their `if-someone-fails:` line read"
    ),
    "RetryPromptPart.content": (
        "another framework's loop leaving a mark on the transcript. PACT owns "
        "the loop (D12), and reading a retry as a user turn makes the agent "
        "answer the correction instead of the question while `steps-at-most` "
        "counts a turn nobody took"
    ),
    "RetryPromptPart.tool_name": "as `RetryPromptPart.content` — the retry does "
                                 "not cross, so neither does what it was about",
    "RetryPromptPart.tool_call_id": "as `RetryPromptPart.content`",
    "RetryPromptPart.timestamp": "as `ModelRequest.timestamp`",
}

#: Where each field of a live conversation lands in the PACT dialect.
_CARRIED: dict[str, str] = {
    "UserPromptPart.content": "`{'role': 'user', 'content': …}`",
    "TextPart.content": "`content:` on an assistant entry",
    "ThinkingPart.content": (
        "the entry's `thinking:` key, which is what `PartKind.THINKING` reads "
        "and what `drop-parts: the model's own thinking` matches on"
    ),
    "ToolCallPart.tool_name": "one entry of `tool_calls:`, which is the pairing key",
    "ToolReturnPart.tool_name": "`name:` on the tool entry, which is what it pairs on",
    "ToolReturnPart.content": "`content:` on the tool entry",
    "metadata.pact": "`labels:` and `checkpoint` on the entry it came from",
}


# ─────────────────────────────────────────────────────────── the agent itself


class PactAgent(AbstractAgent[dict, Any]):
    """One PACT document as an object this SDK can hold, running PACT's loop.

    `run` lowers to `harness.run(spec, PydanticAITransport(...), …)`, so the
    stages of the author's `loop:`, their interceptor chain, their gate, their
    ceilings and their `when-it-runs-out:` are the ones that execute — and
    `run_sync` and `run_stream_events` follow it, because both are concrete on
    `AbstractAgent` and route through `self.run`. Writing a second loop in either
    would be two implementations of one thing, and the async one is the one no
    test would otherwise open — so the `run_sync` below forwards and decides
    nothing; it exists because that method's signature is a closed list of this
    SDK's own arguments, with nowhere to name a park being resumed.

    Subclassing rather than duck-typing, because everything typed against
    `AbstractAgent` — `to_cli`, a router holding a mix of agents, a host's own
    annotations — refuses an object that merely has the same method names.

    **"Running PACT's loop" is a claim, and it is measured.** This is HARNESS
    lowering, not native lowering, so nothing here needs the Conformance Report's
    permission to exist — but a facade is exactly the shape of thing that becomes
    a second runtime by accident, one dropped keyword at a time, and a scripted
    model answers identically either way.
    `tests/test_the_facade_scores_what_the_reference_scores.py` drives the same
    scripted eval through `harness.run` over `ReferenceTransport` — the
    framework-free control arm — and through this class, and holds the four
    fields `conformance.report()` compares (`trace()`, `output`, `halted`, and
    how many times the script was asked) to `conformance.EPSILON`, which is zero.
    This class is deliberately absent from `conformance.TARGETS`: every row there
    is a `Transport`, constructed from a `Script` and asked for a `lattice()`,
    and this is a CALLER of the harness rather than a seam under it.
    """

    def __init__(
        self,
        spec: AgentSpec,
        *,
        transport: Any = None,
        script: "Script | None" = None,
        tool_impls: "Mapping[str, Any] | None" = None,
        event_stream_handler: Any = None,
    ) -> None:
        self._spec = spec
        # A transport a caller built wins over a script, because the caller who
        # built one has already decided which model this talks to. A script alone
        # is the shape the harness's own tests use, and it is enough to run:
        # `PydanticAITransport.__init__` takes a `Script` positionally and always
        # drives through it — there is no unscripted mode of that transport.
        #
        # The WORKSPACE goes with it, because a row a workspace added to its own
        # `models/catalog.yaml` prices and sizes nothing otherwise, and a spend
        # cap over an unpriced model is a cap reported as unmetered.
        if transport is None and script is not None:
            transport = PydanticAITransport(
                script, model=spec.model or None, workspace=spec.workspace
            )
        self._transport = transport
        self._tool_impls = dict(tool_impls or {})
        self._event_stream_handler = event_stream_handler
        # The author's own words, held rather than recomputed, because
        # `AbstractAgent._infer_name` assigns through the name setter when a run
        # starts on an agent with no name — and an agent whose author wrote none
        # is better named after the caller's variable than after nothing.
        self._name = spec.name or spec.key or None
        self._description = spec.description or None
        self._toolsets: tuple[Any, ...] = _toolsets_of(spec)

    @classmethod
    def for_spec(
        cls,
        spec: AgentSpec,
        *,
        transport: Any = None,
        script: "Script | None" = None,
        tool_impls: "Mapping[str, Any] | None" = None,
        event_stream_handler: Any = None,
    ) -> "PactAgent":
        """One PACT agent, as an object this SDK can hold.

        **Nothing but the spec is required to HOLD one**, which is the rule
        `build_agent` follows and for the reason its `defer_model_check=True`
        comment gives: a caller inspecting what a PACT document became — which
        tools, which answer shape, which model id — needs no endpoint and no
        credentials, and asking for a transport here would make every one of
        those inspections a deployment question. Running one needs a `transport=`
        or a `script=`, and `run` says so.

        `tool_impls` and not `tools`, because `harness.run` already calls this map
        `tool_impls` and it is the same map handed to the same place. Two
        spellings for one thing is the `same-setting-twice` mistake arriving in a
        signature.

        Named `for_spec` and not `of`, `from_document` or `for_document`: those
        three names mean *a reader of an authored document* in this package, and
        `test_a_reader_is_reachable_from_a_run` requires every one of them to be
        reachable from an entry point. This reads no document — it is handed one
        somebody else loaded (P-1).
        """
        return cls(
            spec,
            transport=transport,
            script=script,
            tool_impls=tool_impls,
            event_stream_handler=event_stream_handler,
        )

    # ─────────────────────────────────────────── what the eleven members answer

    @property
    def model(self) -> Any:
        """The bound catalogue row, in this SDK's own id scheme.

        The two schemes are not the same thing — PACT binds a catalogue ROW (a
        name with a window, a price and a provenance beside it) and this SDK
        binds `provider:name` — and the row already holds both halves in
        `served-by:` and `also-known-as:`, so this is a lookup and never a guess.
        Measured before it was one: a `model:` copied across produced a document
        whose every run died on `UserError: Unknown model: qwen2.5-7b-instruct`.

        A row with no Pydantic AI id answers `None` rather than a name
        `infer_model` will reject. `Agent(None)` is legal and defers the choice to
        `run(model=…)`, so `None` is a caller who still has options where a bad
        id is a dead run — and a reader of this property has no way to tell a bad
        id from a working one.
        """
        if not self._spec.model:
            return None
        said, _ = pydantic_ai_model_id(self._spec.model, self._spec.workspace)
        return said or None

    @property
    def name(self) -> "str | None":
        """What the author wrote under `name:`, never the folder.

        Left unanswered this SDK names the agent after the caller's local
        variable: `_infer_name` walks the calling frame and takes whatever the
        object was assigned to, so an agent whose author wrote `name: Refund
        Desk` turns up in somebody's traces as `a`. `ir.AgentSpec.key` exists
        because a folder name and an agent's name are not the same string — one
        is what a diagnostic has to name, the other is what a person reads.
        """
        return self._name

    @name.setter
    def name(self, value: "str | None") -> None:
        self._name = value

    @property
    def description(self) -> "str | None":
        return self._description

    @description.setter
    def description(self, value: Any) -> None:
        self._description = value

    @property
    def deps_type(self) -> type:
        """`dict` — the author's `run-inputs:`, which is what a caller supplies.

        `harness.run` takes `run_inputs` as a `Mapping[str, Any]` keyed by the
        author's own names, so `dict` is what goes in `deps=`. Both other answers
        are wrong in opposite directions. `object` — this SDK's default, and what
        `build_agent` leaves behind — tells a caller nothing, so nobody passes
        anything: measured on the worked example, the payments tool received
        `{order-number, amount, action}` and never `customer-id`, so *whose
        order* went on being something nobody supplied. A class synthesised from
        the run-input names is what `_AGENT_NOT_PORTABLE['deps_type']` refuses
        from the other side — `run-inputs:` names what is supplied and the shape
        of each, and *does not name a class, because a class is not portable to
        another language*.
        """
        return dict

    @property
    def output_type(self) -> Any:
        """The author's answer shape — and, on an agent that can run, the halt.

        The shape comes from `_output_type_for` rather than from a second mode
        table here, because that function carries the line a re-implementation
        gets wrong without noticing: **unset is `prompted`, not `auto`**. `auto`
        is resolved per model from `ModelProfile.default_structured_output_mode`,
        so an agent built that way answers one shape under PACT's harness and
        another here, from the same file, for a reason that has nothing to do
        with the agent.

        A bound agent adds two members, and the union is spelled the way this SDK
        already spells `output_type=[str, DeferredToolRequests]`: a run can hand
        back a `Halted`, and a run parked on a call somebody has to approve hands
        back `DeferredToolRequests`. Declaring only the answer shape while `run()`
        can return either is the same lie as putting a sentence in a
        mapping-shaped slot, pointing the other way.

        **An unbound agent declares the answer alone, and that is the honest
        answer rather than a convenience.** `for_spec(spec)` with no transport is
        the inspection door — what did this document become — and what it says
        must be what the DOCUMENT says, byte-for-byte with `build_agent(spec)
        .output_json_schema()`, or the two Pydantic AI doors disagree about one
        file. Such an agent cannot run at all (`run` refuses it by name), so
        there is no run whose outcome the declaration could be understating.
        """
        declared = _output_type_for(self._spec)
        if self._transport is None:
            return declared
        return [declared, DeferredToolRequests, Halted]

    @property
    def event_stream_handler(self) -> Any:
        """The caller's own handler, and `None` when nobody passed one.

        Identity and not a wrapper: a handler is a callable the caller owns, and
        wrapping it would mean the object they can compare against is not the
        object that runs.

        **Held, and not called by this class.** PACT's transport seam is
        `model_call(system, history, tools) -> (text, calls)` — one whole model
        call — so there is no partial-response stream to hand anybody, which is
        exactly what `PydanticAITransport.lattice()` already declares as
        `streaming: emulated`. A caller who reaches this through
        `run_stream_events` still gets the final `AgentRunResultEvent`, because
        that method wraps `self.run`. Synthesising per-token events here would
        mean inventing boundaries PACT does not have, which is the same thing
        `iter()` refuses to do one method down.

        **Held is not the same as hidden.** A run with a handler in force — this
        one or `run(event_stream_handler=…)` — says so on
        `RunResult.unenforced` (`_unhonoured`), because a handler that is held
        and never called is otherwise indistinguishable from a run nothing
        happened in, and the caller finds out by watching a blank screen.
        """
        return self._event_stream_handler

    @property
    def toolsets(self) -> "Sequence[Any]":
        """The author's tools, readable without starting a run.

        "Statically" is the load-bearing word, and it is why this is an
        `ExternalToolset` of `ToolDefinition`s rather than anything resolved per
        run: `_toolsets_to_pact` — which is what `from_pydantic_ai_agent` uses to
        read a live agent back into a PACT document — reports a toolset it cannot
        read rather than carrying four of nine tools. A `PactAgent` whose tools
        were only knowable inside a run would import back as a document with no
        `uses:` at all: the author's tools, gone, through the one class whose
        entire claim is that the document survives being held.

        External and not a `FunctionToolset`, because these tools are not this
        SDK's to call. `tool_impls` is the host's map and `harness.run` is what
        invokes it, so binding Python functions here would advertise an execution
        path that does not exist.
        """
        return self._toolsets

    async def system_prompt_parts(self, **how: Any) -> "list[SystemPromptPart]":
        """The system text PACT's first stage is given.

        Overridden because the inherited one returns `[]` with a `# pragma: no
        cover` beside it, so an agent that does not override it silently claims
        to have no system prompt at all — and this method is what a UI adapter or
        a history reconstruction reads.

        `_system_for` rather than anything assembled here: it is what the harness
        calls on every step, so the instructions, the stage's own line, the
        skills that stage may read and the author's `answers-with:` arrive in one
        order and not two.

        **The opening stage, and that is the one thing this cannot express.**
        PACT's system text differs per stage — that is what `loop:` IS — and this
        method's signature has nowhere to name one. A caller reading it is
        reading what the run starts with.
        """
        loop = self._spec.loop
        phase = loop.phase(loop.starts_at)
        readable = set(phase.skills_offered(self._spec.skill_names))
        mode = self._spec.answers_with_mode or CHOSEN_ANSWER_MODE
        said = _system_for(
            self._spec.instructions,
            phase,
            tuple(s for s in self._spec.skills if s.name in readable),
            answers_with=(
                self._spec.answers_with if mode == CHOSEN_ANSWER_MODE else {}
            ),
        )
        return [SystemPromptPart(content=said)] if said else []

    # ────────────────────────────────── the two that refuse, with the reason

    def iter(self, *args: Any, **how: Any) -> Any:
        """Refused, because there is no graph here to iterate.

        `iter()` hands back an `AgentRun`: a live handle onto `_agent_graph`'s
        node stream, with `next()`, `.result`, `.usage()` and the node vocabulary
        (`is_model_request_node` and the rest). A `PactAgent` runs PACT's harness
        — named stages, an interceptor chain, a gate, the author's ceilings — and
        has no node stream of that shape to hand back. Emulating one would mean
        inventing node boundaries PACT does not have, which is the opaque
        wrapping *translate or nothing* forbids.

        The message matters more than the exception. A bare `NotImplementedError`
        has an EMPTY `str()`, and a caller who meets one learns only that the
        method exists and does nothing — where the two real next moves are
        opposite. `run_stream` and `run_stream_sync` used to bottom out here and
        no longer do: a caller who typed one of those words was answered with a
        sentence about a THIRD method they had never called, so each now refuses
        under its own name — see `run_stream` below.
        """
        raise UserError(
            "`iter()` is not something a PACT agent can offer. It hands back an "
            "`AgentRun` over `_agent_graph`'s node stream, and this agent's loop "
            "is `harness.run` — the author's `loop:` stages, their interceptor "
            "chain, their gate and their ceilings — which has no node stream of "
            "that shape. Emulating one would mean inventing boundaries the "
            "document does not describe.\n\n"
            "fix: use `run()`/`run_sync()`, which is the same loop with the same "
            "guarantees and returns this SDK's own `AgentRunResult`; or, if you "
            "need the node stream itself, `pydantic_ai_interop.build_agent()` "
            "gives you a real `Agent` — and its docstring names what stops being "
            "enforced when you take it."
        )

    def override(self, **how: Any) -> Any:
        """Refused, for the same reason and with a different list.

        Everything `override` can replace — the model, the tools, the
        instructions, the retries — is a line in the author's tree, and this
        class exists to run what that tree says. Overriding one here would make
        `pact check` a statement about a document nobody ran.
        """
        raise UserError(
            "`override()` is not something a PACT agent can offer: the model, "
            "the tools, the instructions and the retries it replaces are all "
            "lines in the author's document, and this class runs that document. "
            "fix: change the document — or, for a test, build the spec you want "
            "with `dataclasses.replace(spec, …)` and hand it to "
            "`PactAgent.for_spec`."
        )

    # ───────────────────────────────────────────────────────────────── the run

    async def run(
        self,
        user_prompt: Any = None,
        *,
        deps: Any = None,
        message_history: Any = None,
        event_stream_handler: Any = None,
        run_id: "str | None" = None,
        conversation_id: "str | None" = None,
        infer_name: bool = True,
        resume: "Suspension | None" = None,
        answer: "Resumption | None" = None,
        **not_ours: Any,
    ) -> "AgentRunResult[Any]":
        """One PACT run, entered through this SDK's door.

        The override is on `run`, and `run_sync` below adds nothing to it but the
        two arguments this SDK's own signature has no room for.
        `run_stream_events` awaits this method, so that door is this loop by
        construction — where a second implementation of the loop would drift.

        Everything this SDK's `run()` can be handed that PACT cannot honour is
        REFUSED by name rather than accepted and dropped. That includes arguments
        added to the SDK after this was written: an unknown non-`None` keyword is
        refused too, because a silently ignored argument is a caller who believes
        something is happening. `deps=` that is not a mapping is refused here for
        the same reason and not filtered by shape on the way to `run_inputs=`,
        where it used to become `None` in silence and leave every `bind:` line
        filling from nothing.

        Two things cannot be refused and are REPORTED instead, on
        `RunResult.unenforced` and by `_unhonoured`: a prompt's non-text parts
        (refusing them fails an ordinary question because a screenshot rode along
        with it) and `event_stream_handler=` (`run_stream_events` passes one
        itself, so refusing it would break the inherited method this class gets
        for free). Reported and not dropped, which is the same rule one door
        along: the caller's next move depends on knowing.

        **`resume=` and `answer=` are the way back in, and without them a park is
        a dead end.** `harness.run` takes both; this method took neither, so a
        run that stopped for a person could be shown to somebody and never
        continued — and `when-it-runs-out: ask-a-person`, which is the worked
        example's own line, collapsed through this class into `stop-and-say-so`:
        the ceiling was reached, the question was carried on
        `RunResult.suspension`, and nothing a caller could type put the answer
        back. That is the author's choice discarded rather than degraded, which
        is the T7 failure every other refusal in this file exists to prevent —
        and it is what `PactSuspended` tells the caller to type.

        **Passed straight through, and nothing about a park is decided here.**
        The exactly-once guarantee across the wait is `harness.run`'s: it seeds
        `already` from `Suspension.completed` so a tool that ran before the park
        does not run again, and its `Ledger` from `Suspension.spent_keys` so a
        `same-request-key:` spent before the park cannot be spent after it —
        measured on the other side of that line, a refund issued once could be
        issued again by the run being interrupted. Re-deriving either of them
        here would be a second at-most-once record beside the one that survives
        the process dying, which is the `same-setting-twice` mistake at the point
        it costs money. `Suspension.accepts` is likewise the harness's guard: an
        answer written for a wait this run has moved past is refused there by
        name, and a check here would be a second one to disagree with it.
        """
        for named in sorted(not_ours):
            if not_ours[named] is not None:
                raise UserError(
                    _NOT_OURS_TO_TAKE.get(named)
                    or (
                        f"`{named}=` is not something a PACT run can take. This "
                        f"agent's run is `harness.run` over the author's "
                        f"document, and nothing in that document describes "
                        f"`{named}`. Ignoring it would be worse than refusing "
                        f"it: you would be told it was honoured. fix: if this "
                        f"argument has an authored counterpart, write it in the "
                        f"tree; if it does not, `pydantic_ai_interop"
                        f".build_agent()` is the door where this SDK owns the "
                        f"loop and takes its own arguments."
                    )
                )
        if deps is not None and not isinstance(deps, Mapping):
            raise UserError(
                f"`deps=` on a PACT run is the author's `run-inputs:` — a "
                f"mapping from the names they declared to the values the "
                f"surrounding system supplies — which is why `deps_type` "
                f"answers `dict` and `harness.run` takes `run_inputs: "
                f"Mapping[str, Any]`. This run was handed a "
                f"`{type(deps).__name__}`, which has no name-to-value shape to "
                f"read from. Dropping it is the worse half of the same problem: "
                f"every `bind:` line the author wrote would fill from nothing "
                f"and the tool would be called without the argument, which is "
                f"the exact failure `run_inputs` was added for — measured on "
                f"the worked example, the payments tool received "
                f"`{{order-number, amount, action}}` and never `customer-id`, "
                f"so *whose order* went on being something nobody supplied. "
                f"fix: pass a mapping keyed by the names in `run-inputs:`; a "
                f"dependency OBJECT this SDK's own tools read belongs to "
                f"`pydantic_ai_interop.build_agent()`, where the SDK owns the "
                f"loop and its tools take a `RunContext`."
            )
        if message_history:
            crossed, lost = to_pact_history(message_history)
            raise UserError(
                f"`message_history=` is not something a PACT run can take. Those "
                f"{len(crossed)} turn(s) cross into PACT's dialect cleanly enough "
                f"— `to_pact_history()` is exported here and reports what does "
                f"not"
                + (
                    f" (this history would lose {', '.join(sorted(lost.not_carried))})"
                    if lost.not_carried
                    else ""
                )
                + " — but `harness.run` has nowhere to put them: it continues a "
                "conversation through a `Suspension`, the park record that "
                "carries the history, the meter, the permissions already granted "
                "and the stage it had reached. Accepting a bare message list "
                "would put turns in front of the model that the author's "
                "`context-policy:` never measured and their ceilings never "
                "counted. fix: to continue a parked run, hand the `Suspension` on "
                "`RunResult.suspension` back as `run(resume=…, answer=…)`; to "
                "read one dialect in the other, `to_model_messages()` and "
                "`to_pact_history()`."
            )
        if self._transport is None:
            raise UserError(
                "this `PactAgent` was built from a spec alone, which is enough to "
                "READ the agent — its model id, its tools, its answer shape — and "
                "not enough to run one. fix: "
                "`PactAgent.for_spec(spec, transport=…)` with a "
                "`pact_adapters.transports` transport, or `script=` to drive "
                "`PydanticAITransport` off a `Script`."
            )

        asked, unspoken = _asked(user_prompt)
        ran = await harness.run(
            self._spec,
            self._transport,
            asked,
            tool_impls=self._tool_impls,
            # The author's `run-inputs:` keys, filled by the surrounding system.
            # `deps` is this SDK's name for exactly that, which is why
            # `deps_type` says `dict`. Passed whole rather than filtered by
            # shape: anything that is not a mapping was refused by name above,
            # where `deps if isinstance(deps, Mapping) else None` used to drop it
            # in silence.
            run_inputs=deps,
            # The park record and the answer to it, by the names `harness.run`
            # already gives them. Two spellings for one thing is the
            # `same-setting-twice` mistake arriving in a signature, which is the
            # reason `tool_impls` is not called `tools` either.
            resume=resume,
            answer=answer,
        )
        ran.unenforced += _unhonoured(
            unspoken, event_stream_handler or self._event_stream_handler
        )
        result = self._as_result(ran, run_id=run_id, conversation_id=conversation_id)
        # A park with nothing pending leaves through the one door a caller cannot
        # ignore. Built first and carried on the exception, so raising costs
        # nothing the run knew — see `PactSuspended` for why these three reasons
        # and not the three that park with a call.
        if ran.suspension is not None and (
            ran.suspension.reason in _PARKS_WITH_NOTHING_PENDING
        ):
            raise PactSuspended(ran.suspension, result)
        return result

    def run_sync(
        self,
        user_prompt: Any = None,
        *,
        resume: "Suspension | None" = None,
        answer: "Resumption | None" = None,
        **how: Any,
    ) -> "AgentRunResult[Any]":
        """`run`, from code that is not async — including the way back into a park.

        This class deliberately does not write a second loop, and this is not
        one: with nothing parked it IS the inherited method, and with a park in
        hand it awaits the same `self.run` the inherited method would have
        awaited. The override exists for one reason only —
        `AbstractAgent.run_sync` is a CLOSED signature of this SDK's own
        arguments, and `resume=`/`answer=` are not on it, so handing a
        `Suspension` to the inherited method is a `TypeError` and the door back
        into a parked run would be async-only. A `when-it-runs-out: ask-a-person`
        ceiling parks a synchronous caller exactly as readily as an async one,
        and a resume nobody can reach is the same dead end as no resume at all.

        `_run_until_complete` and not `asyncio.run`, for what the inherited
        `run_sync` does at this exact step: it drives the coroutine on the
        CALLER's event loop, and on a `KeyboardInterrupt` it cancels and drains
        its own task rather than leaving the run's `finally` blocks un-run.
        """
        if resume is None and answer is None:
            return super().run_sync(user_prompt, **how)
        return _run_until_complete(
            self.run(user_prompt, resume=resume, answer=answer, **how)
        )

    # ─────────────────────────────────────── the three doors that say `stream`

    def run_stream(self, *args: Any, **how: Any) -> Any:
        """Refused by name: there is no partial response here to stream.

        `run_stream` hands back a live `StreamedRunResult`, and every read on one
        — `stream_text(delta=True)`, `stream_output()`, `stream_response()` — is
        a look at a model response that has not finished arriving. PACT's
        transport seam is `model_call(system, history, tools) -> (text, calls)`:
        one whole model call, handed back whole. There is no half of one to read.

        **The alternative is worse than the refusal, which is why this IS a
        refusal.** `StreamedRunResult` has a second constructor taking a finished
        `AgentRunResult` (`result.py:445-458`), so this method could hand back the
        completed run wearing a stream's clothes. On an agent with `answers-with:`
        — the worked example — `stream_text()` on that object raises `UserError:
        stream_text() can only be used with text responses`, which names nothing
        about this document and offers no way forward; on a text agent it yields
        the entire answer once and calls it a delta. Both are
        accept-and-silently-degrade, found out by watching a blank screen.

        **Raised at the CALL and not inside `__aenter__`.** An
        `@asynccontextmanager` that fails on entry is still an object a caller can
        build, store and hand somewhere else, and the traceback then names
        whoever entered it rather than whoever asked to stream.

        This does not contradict `PydanticAITransport.lattice()`'s `streaming:
        emulated` — it is what that word buys. `emulated` means the harness above
        the transport provides the feature, and what this harness has to provide
        is a run that finished: one terminal event, which is `run_stream_events`
        below. There is no granularity between that and a token, so the two doors
        demanding a finer one refuse and name the door that is the emulation.
        """
        raise _no_partial_response(
            "run_stream",
            "fix: `run_stream_events()` gives this run as a single terminal "
            "`AgentRunResultEvent` — the whole result, once, with nothing before "
            "it — and `run()` gives that same result directly. For a real token "
            "stream, `pydantic_ai_interop.build_agent()` hands you a "
            "`pydantic_ai.Agent` whose loop is this SDK's, and its docstring "
            "names what stops being enforced when you take it.",
        )

    def run_stream_sync(self, *args: Any, **how: Any) -> Any:
        """Refused by name, for the reason `run_stream` gives and with its own fix.

        This is `run_stream` wrapped in `StreamedRunResultSync`, so the reason is
        the same one and saying it twice would be two things to keep true. What
        differs is the line to type: a caller here is not in async code, so
        `run_stream_events()` — an async context manager — is not the move, and
        `run_sync()` is.

        Refused under its OWN name rather than left to bottom out in
        `run_stream`. It used to reach `iter()` two methods further down and
        answer a caller who typed `run_stream_sync` with a sentence about
        `iter()`: a method they had never called, on a class they were holding
        through this SDK's own abstract base.
        """
        raise _no_partial_response(
            "run_stream_sync",
            "fix: `run_sync()` returns the whole result from synchronous code, "
            "which is the same loop with the same guarantees; from async code "
            "`run_stream_events()` gives that result as a single terminal "
            "`AgentRunResultEvent`. For a real token stream, "
            "`pydantic_ai_interop.build_agent()` hands you a `pydantic_ai.Agent` "
            "whose loop is this SDK's, and its docstring names what stops being "
            "enforced when you take it.",
        )

    def run_stream_events(self, *args: Any, **how: Any) -> Any:
        """The finished run as ONE terminal `AgentRunResultEvent`, nothing before.

        Kept rather than refused, and forwarded rather than re-implemented: the
        inherited method wraps `self.run` and feeds events through an
        `event_stream_handler` this class holds and never calls, so a consumer
        receives exactly one — `AgentRunResultEvent(result)`, carrying the same
        `AgentRunResult` `run()` returns, `.pact` and all. That single event IS
        `PydanticAITransport.lattice()`'s `streaming: emulated`: the harness above
        the transport provides the feature at the one granularity it has, a run
        that finished.

        **Overridden for the docstring, because the docstring was the lie.**
        Inherited, this method advertises `PartStartEvent`, `PartDeltaEvent` and
        `PartEndEvent` in a worked example, and a caller reading `help()` on a
        `PactAgent` believed it. A surface is where a shim can lie, and a
        docstring shown by this SDK's own tooling is a surface.

        **One event and never zero**, which is the failure this shape exists to
        avoid: a door that yielded nothing would be indistinguishable from a run
        that never happened, and the run DID happen — every stage, every ceiling,
        every gate. The run says the other half out loud on `RunResult.unenforced`
        (`_unhonoured`), because a handler held and never called is otherwise
        silent.

        `infer_name` is handled here rather than left to the inherited method:
        that method names an unnamed agent from the CALLER's frame, and
        forwarding adds one — so an agent whose author wrote no `name:` would come
        back called `self`.
        """
        if how.pop("infer_name", True) and self.name is None:
            self._infer_name(inspect.currentframe())
        return super().run_stream_events(*args, infer_name=False, **how)

    def _as_result(
        self,
        ran: RunResult,
        *,
        run_id: "str | None" = None,
        conversation_id: "str | None" = None,
    ) -> "AgentRunResult[Any]":
        """The PACT run as this SDK's own result type.

        `AgentRunResult(output=…)` alone is a run that never said anything and
        never spent anything: `_state` defaults to an empty `GraphAgentState`, so
        `all_messages()` is `[]` and `usage` is a `RunUsage()` of zeros. A caller
        following this SDK's documented way of continuing a conversation hands
        the next turn nothing, and a caller totalling spend across a chain of runs
        measures nothing and stops nothing — which is the T7 failure
        `RunResult.unmetered` exists to prevent one level down.

        `.pact` is set because `AgentRunResult` has five fields and not one of
        them can hold a trace, a stage path, a meter, or the sentences naming
        rules nobody could decide. A facade that returned only what the SDK
        defines would have thrown away every honesty channel the harness has.
        """
        result: "AgentRunResult[Any]" = AgentRunResult(output=self._answer_of(ran))
        state = result._state
        state.message_history.extend(to_model_messages(_history_of(ran)))
        state.usage = RunUsage(
            requests=len(ran.steps),
            tool_calls=int(ran.used.tool_calls) if ran.used else 0,
            # PACT's meter carries ONE token figure, because that is what every
            # transport here can honestly say; this SDK carries a prompt half and
            # a completion half and sums them for `total_tokens`. The total is the
            # only figure both sides agree on, so it goes where the total comes
            # out right and the split is not claimed. A caller who needs the split
            # reads it off the transport that made the calls.
            input_tokens=int(ran.used.tokens) if ran.used else 0,
        )
        if run_id:
            state.run_id = run_id
        if conversation_id:
            state.conversation_id = conversation_id
        result.pact = ran
        return result

    def _answer_of(self, ran: RunResult) -> Any:
        """What goes on `.output`, which is the one place this can quietly lie.

        Three outcomes and three shapes. A run that reached `done` hands back the
        author's declared shape. A run parked on a call somebody has to approve
        hands back `DeferredToolRequests`, which is this SDK's own word for it and
        the shape `build_agent` already parks in. Everything else — a ceiling, a
        rule, a stage that gave up, a park with no call pending — is a `Halted`.

        The `Halted` a park with nothing pending produces is never RETURNED to a
        caller: `run` raises `PactSuspended` for those three reasons, and this is
        the `.output` of the result that rides on it. Built here anyway, so the
        record on the exception says the same thing every other outcome does
        rather than being a second, quieter description of the same park.
        """
        if ran.halted == "final":
            return self._declared(ran.output)
        parked = ran.suspension
        # `_pending` and not `awaiting`, because `awaiting` is the WHOLE batch of
        # the parked step and the calls the gate cleared have already run. A park
        # whose every call ran is a park with nothing to approve, and
        # `DeferredToolRequests(approvals=[])` is a caller sent to answer a
        # question nobody is asking.
        if parked is not None and _pending(parked):
            return _waiting_on(parked)
        return Halted(
            halted=ran.halted,
            stopped_by=ran.stopped_by,
            # At a park `RunResult.output` is the model's LAST TEXT, because no
            # park path writes a sentence into it: `harness._ran_out` returns
            # inside the `ask-a-person` branch, before the
            # `result.output = reached.sentence()` its other two actions reach,
            # and the gate parks return with the step's own words still there. So
            # a run that stopped to ask whoever owns the budget handed the caller
            # the model's mid-run chatter as the reason it stopped, while the
            # sentence naming the ceiling, the figures and who to ask sat unread
            # on `Suspension.in_words` — the field the harness composes and
            # carries ACROSS the process boundary precisely so the words a person
            # reads cannot be rebuilt into something else later (D23).
            words=(parked.in_words if parked is not None else "") or ran.output,
        )

    def _declared(self, said: str) -> Any:
        """The answer in the shape the author declared, when they declared one.

        `answers-with:` makes `_output_type_for` a `StructuredDict`, so handing a
        caller the JSON TEXT leaves them to parse it — and where they parse it and
        how they report a failure is exactly the divergence between two runtimes
        that PACT exists to remove.

        Read and not VALIDATED, deliberately. The author's shape is put to the
        model by the harness (`shape_to_ask_for`) and a second check here would be
        the `same-setting-twice` mistake: two places deciding whether one answer
        keeps one contract. Text that is not the declared shape comes back as the
        text the run wrote, because inventing a parse failure at the door would
        turn a bad answer into no answer.
        """
        declared = _output_type_for(self._spec)
        # `str` is what `_output_type_for` returns for `answers-with-mode: text`
        # and for an agent with no declared shape at all. Reading JSON out of
        # either would contradict the type this same object publishes.
        if isinstance(declared, type):
            return said
        try:
            read = json.loads(said)
        except (TypeError, ValueError):
            return said
        return read if isinstance(read, Mapping) else said

    # ────────────────────────────────────────────────────── the context manager

    async def __aenter__(self) -> "PactAgent":
        """Nothing to enter.

        `Agent.__aenter__` starts the toolsets that need a connection — an MCP
        server, a sandbox. PACT's tools are the host's `tool_impls` and its
        transports are constructed ready, so there is no lifecycle here to hold
        open. Answering rather than inheriting, because the base is abstract and a
        subclass without it cannot be instantiated at all.
        """
        return self

    async def __aexit__(self, *args: Any) -> "bool | None":
        return None


# ──────────────────────────────────────────────────────────────────── helpers


#: Arguments this SDK's `run()` takes that a PACT run cannot honour, and what
#: each would break. Refused rather than ignored: an argument silently dropped is
#: a caller who believes a ceiling holds, a shape is enforced or a model is bound,
#: and none of it is happening.
#:
#: Anything NOT named here is refused too, with the generic sentence in `run` —
#: this table exists to say the interesting ones properly, not to be the list
#: that decides.
_NOT_OURS_TO_TAKE: dict[str, str] = {
    "usage_limits": (
        "`usage_limits=` would be a SECOND enforcer of ceilings this agent's "
        "`limits.yaml` already holds. `UsageLimits` has exactly one behaviour — "
        "it raises `UsageLimitExceeded` — and every PACT ceiling carries the "
        "author's own `when-it-runs-out:`, which is `stop-and-say-so`, "
        "`answer-with-what-it-has` or `ask-a-person`. A run that reached the "
        "ceiling under a caller-supplied `UsageLimits` would die with a traceback "
        "at precisely the point the document says to park and ask somebody: the "
        "author's line is not degraded, it is discarded, and nothing records that "
        "it was. fix: write the ceiling in `limits.yaml`, where "
        "`when-it-runs-out:` decides what happens at the edge. "
        "`pydantic_ai_interop.usage_limits_for()` builds a `UsageLimits` for the "
        "OTHER door — the host that called `build_agent()` and drives "
        "`Agent.run` itself, where this SDK owns the loop and nothing else is "
        "enforcing anything."
    ),
    "output_type": (
        "`output_type=` would decide the answer shape a second time. The author "
        "wrote `answers-with:` and `answers-with-mode:`, and `_output_type_for` "
        "is the single place those four words become this SDK's four marker "
        "classes — a per-run override means one document answering in two shapes. "
        "fix: write the shape in the agent's own file."
    ),
    "model": (
        "`model=` would run the document on a model nobody wrote down. PACT binds "
        "a catalogue ROW through `model:` and `needs:`, so the model is a fact "
        "the tree states and `RunResult` reports against. fix: write `model:` in "
        "the agent, or add the row to `models/catalog.yaml`; to serve it "
        "somewhere else, hand `for_spec` a transport already bound to it."
    ),
    "toolsets": (
        "`toolsets=` would give the run tools the author did not write. Which "
        "tools exist is `uses:`, which of them a STAGE may reach is that stage's "
        "own line, and the gate in `policies/` is written about those names. fix: "
        "write the tool in `tools/<name>.yaml` and hand its implementation in as "
        "`tool_impls`."
    ),
    "instructions": (
        "`instructions=` would put words in front of the model beside the "
        "author's `instructions.md`, per run and outside the document. That is "
        "the one input a governed agent's author does not control. fix: write "
        "them in the tree — or in a `skills/` document, which is what `may-use:` "
        "narrows per stage."
    ),
    "model_settings": (
        "`model_settings=` would override the author's `settings:` block, which "
        "the transport already translates key by key and reports what it could "
        "not take. fix: write the setting in `settings:`."
    ),
    "retries": (
        "`retries=` is this SDK's loop retrying its own model call, and PACT owns "
        "the loop (D12). What a PACT run does when something fails is the "
        "author's `interceptors:`, their `if-someone-fails:` and their ceilings. "
        "fix: write the rule."
    ),
    "deferred_tool_results": (
        "`deferred_tool_results=` answers a `DeferredToolRequests` this SDK "
        "produced. A PACT run that parked produced a `Suspension` instead, and it "
        "carries the correlation key that makes a stale answer unable to land. "
        "fix: `run(resume=<the `Suspension` on `RunResult.suspension`>, "
        "answer=parked.answer(…))`, which is the same park answered through the "
        "record that carries the key."
    ),
    "usage": (
        "`usage=` would seed the meter with spend from somewhere else. PACT's "
        "meter is carried across a park by the `Suspension` itself, precisely so "
        "a run cannot get a fresh budget by being interrupted. fix: "
        "`run(resume=…)`, which restores that meter rather than seeding a new one."
    ),
    "capabilities": (
        "`capabilities=` are this SDK's wrappers around its own graph — "
        "durability, approval, instrumentation — and they wrap a loop this agent "
        "does not run. fix: the PACT counterparts are `policies/` for approval "
        "and `watch:` for the record; for the SDK's own, "
        "`pydantic_ai_interop.build_agent()`."
    ),
    "spec": (
        "`spec=` applies a Pydantic AI `AgentSpec` on top of this run. The "
        "specification here is the author's tree, and a second one applied at run "
        "time would mean `pact check` passed on a document that is not what ran. "
        "fix: `pydantic_ai_interop.from_pydantic_ai_spec()` turns one into a PACT "
        "document you can check."
    ),
    "metadata": (
        "`metadata=` is carried by this SDK on the run and its messages. PACT's "
        "record of a run is `RunResult` and its record of a conversation is the "
        "history, neither of which has a slot a caller can write into. fix: hold "
        "it beside the result — `AgentRunResult.pact` is the PACT run, and it is "
        "yours to key by."
    ),
}


def _toolsets_of(spec: AgentSpec) -> tuple[Any, ...]:
    """The author's `tools/` as one statically-readable toolset.

    `_takes_as_schema` and not a schema built here, for the reason the mode table
    is not rebuilt either: it is the schema the model is shown, and two builders
    of it is two things the model is shown.
    """
    if not spec.tools:
        return ()
    return (
        ExternalToolset(
            [
                ToolDefinition(
                    name=tool.name,
                    description=tool.description,
                    parameters_json_schema=_takes_as_schema(tool.parameters),
                )
                for tool in spec.tools
            ],
            id="pact",
        ),
    )


def _asked(user_prompt: Any) -> tuple[str, str]:
    """The question, as the one string `harness.run` takes, and what stayed behind.

    A `Sequence[UserContent]` is this SDK's multimodal prompt and PACT's harness
    takes text. The text of it is used rather than refused, because refusing
    would make an image attached to an otherwise ordinary question fail the whole
    run — but only the text reaches the model.

    **Both halves, because this used to return one.** `_as_text` composes the
    sentence naming what did not cross and the second half of its pair was
    discarded here (`said, _ = _as_text(...)`), so a prompt whose picture WAS the
    question ran, answered from the words alone, and nothing anywhere said the
    model had never seen the thing being asked about. `run` puts the sentence on
    `RunResult.unenforced`, which is the crossing that has somewhere to say it.
    """
    if user_prompt is None:
        return "", ""
    if isinstance(user_prompt, str):
        return user_prompt, ""
    return _as_text(user_prompt)


def _no_partial_response(door: str, fix: str) -> UserError:
    """The refusal both partial-response doors give, written once.

    One reason and two fixes, rather than two of each. The REASON is identical —
    the seam is one whole model call — and two copies of it are two things to
    keep true of one fact. What differs per door is the line to type, and that is
    the half a caller acts on: `test_every_argument_a_pact_run_cannot_honour_is_
    refused_in_its_own_words` is this same rule one door along, where a generic
    sentence naming only the argument passed the test and told nobody anything.

    Named in the refusal rather than left implicit: the door the caller typed,
    what the seam actually is, what the finished-run-in-stream's-clothing
    alternative would do to them, and `streaming: emulated` — because that word
    lives in another file (`transports/pydantic_ai_transport.py`) and the two can
    only be kept from drifting apart by each naming the other.
    """
    return UserError(
        f"`{door}()` is not something a PACT agent can offer. It hands back a "
        f"live `StreamedRunResult`, and every read on one — `stream_text()`, "
        f"`stream_output()`, `stream_response()` — is a look at a model response "
        f"that has not finished arriving. PACT's transport seam is "
        f"`model_call(system, history, tools) -> (text, calls)`: one whole model "
        f"call, handed back whole, so there is no half of one to read. Returning "
        f"the FINISHED run through this door instead would be worse than "
        f"refusing it: on an agent with `answers-with:` this SDK's own "
        f"`stream_text()` then raises `stream_text() can only be used with text "
        f"responses`, and on a text agent it yields the whole answer once and "
        f"calls it a delta — accepted, silently degraded, found out by watching "
        f"a blank screen. `PydanticAITransport.lattice()` declares `streaming: "
        f"emulated` and this is what that word buys: the emulation exists at "
        f"exactly one granularity, the finished run as a single terminal event."
        f"\n\n{fix}"
    )


def _unhonoured(unspoken: str, watching: Any) -> tuple[str, ...]:
    """What this run was handed, did not carry out, and must not go quiet about.

    Two things reach `run()` that PACT can neither honour nor refuse, and each
    would otherwise be accepted and dropped — which this module's own docstring
    forbids in one line: *"a refusal with no reason is the same defect as a
    silent drop, because the caller's next move depends entirely on why"*. A
    silent drop with no refusal is that defect with the sentence missing too.

    **The prompt's non-text parts.** Refusing them would fail an otherwise
    ordinary question because a screenshot rode along with it, which is a worse
    trade than answering the words. But the picture reached nothing, and a run
    that answered a question it never fully saw is byte-identical to one that
    did — the same shape as the `stage-limit` answer that parses as the declared
    output, one door along.

    **A handler that was never called.** `AbstractAgent.run_stream_events` passes
    `event_stream_handler=` into `self.run` itself, so refusing the argument
    would break the inherited method this class says it gets for free. What
    cannot be done is stream: PACT's transport seam is `model_call(system,
    history, tools) -> (text, calls)` — one whole model call — which is what
    `PydanticAITransport.lattice()` already declares as `streaming: emulated`,
    and synthesising per-token events would invent boundaries the document does
    not describe, which is what `iter()` refuses two methods up.

    `unenforced` rather than a sixth honesty channel. The field's own line says
    *a rule the author wrote that this run could not decide*, and an argument the
    caller handed in is that fact one door out: something asked for, not done,
    with a line to type. A channel invented for it would have to be invented in
    the second port too
    (`test_a_channel_count_in_a_document_is_the_count_the_run_has` counts them,
    and three shipped documents say how many there are) for two sentences no
    harness in either port can produce.
    """
    said: list[str] = []
    if unspoken:
        said.append(
            "`user_prompt=` reached `harness.run` as the one string it takes, "
            f"and the rest of the prompt reached nothing: {unspoken} — for a "
            "run that means putting what the model must see into the words, or "
            "handing the file to a tool the author wrote (`tools/<name>.yaml`), "
            "whose result comes back as text the next step reads."
        )
    if watching is not None:
        said.append(
            "`event_stream_handler=` was held for this run and never called, so "
            "nothing was streamed to it. PACT's transport seam is one whole "
            "model call — `model_call(system, history, tools) -> (text, calls)` "
            "— so there is no partial response to hand anybody, which is what "
            "`PydanticAITransport.lattice()` already declares as `streaming: "
            "emulated`; synthesising per-token events would invent boundaries "
            "the document does not describe. The run itself is unaffected and "
            "the finished run still arrives whole — as the `AgentRunResult` this "
            "call returns, and through `run_stream_events()` as one terminal "
            "`AgentRunResultEvent` with no event before it, which is the whole "
            "of what `emulated` buys here. fix: "
            "for what this run did, `AgentRunResult.pact.trace()`; for events "
            "as they happen, `pydantic_ai_interop.build_agent()` gives a real "
            "`Agent` whose loop is this SDK's — and its docstring names what "
            "stops being enforced when you take it."
        )
    return tuple(said)


def _history_of(ran: RunResult) -> list[dict[str, Any]]:
    """The conversation this run had, in PACT's own dialect.

    Written the way `harness.run` writes it and in that order — the opening ask
    with its `first-request` label, then per step the model's turn carrying the
    names of the calls it made, then one entry per result — because that is the
    dialect `context_policy.from_history` reads and `Pins` matches on. The harness
    does not hand its history back on `RunResult`, so this rebuilds it from what
    it does hand back: `asked` and `steps`.

    `RunResult.asked` and never the string the caller typed. It is the question
    AFTER the author's interceptor chain ran on it, so a workspace with a
    redaction rule has already had it rewritten — and `as_record` takes no
    argument for exactly this reason, after a card number reached a committed
    eval case file.
    """
    history: list[dict[str, Any]] = []
    if ran.asked:
        history.append(
            {"role": "user", "content": ran.asked, "labels": ["first-request"]}
        )
    for step in ran.steps:
        entry: dict[str, Any] = {"role": "assistant", "content": step.text}
        if step.tool_calls:
            entry["tool_calls"] = [call.name for call in step.tool_calls]
        history.append(entry)
        for call, said in zip(step.tool_calls, step.tool_results):
            history.append({"role": "tool", "name": call.name, "content": said})
    return history


def _pending(parked: Suspension) -> "list[tuple[str, Any]]":
    """The parked calls that have NOT happened, each under PACT's own slot.

    Two facts about a `Suspension` that reading `awaiting` alone gets wrong, both
    of them the harness's own (`harness._park_state` and its callers).

    **`awaiting` is the whole batch, not the waiting part of it.** Every park
    site passes `awaiting=tuple(calls)` because that is what a resume re-drives
    (`harness.run` sets `pending = resume.awaiting` and replays the step from
    it). The harness deliberately carries out everything the gate cleared BEFORE
    it parks — *"a person who approves two of three actions gets those two"* —
    and records each under `already[<its slot>]`, which `_park_state` copies onto
    `completed`. Publishing all of `awaiting` as `approvals` therefore asks
    somebody to authorise the refund that has already gone out, and a host whose
    approval UI is driven by this list shows a decision that cannot be made.

    **The slot is the harness's, and its first call keeps the BARE name.**
    ``harness.slots_of`` mints `c.name` for a step's first call to a tool and
    `<name>#<n>` only from the second on, and that slot is the key an answer is
    filed and read under. Numbering from one instead gives the FIRST call
    `payments#1`, which is the harness's name for the SECOND — so an approval of
    the 40 USD refund arrives as the answer to the 300 USD one beside it.
    """
    # By SLOT, the key `completed` has: a call the gate cleared ran before the
    # park even when another call to its tool is still waiting.
    return [
        (slot, call)
        for slot, call in zip(slots_of(parked.awaiting), parked.awaiting)
        if slot not in parked.completed
    ]


def _waiting_on(parked: Suspension) -> DeferredToolRequests:
    """A park with a call pending, in this SDK's own shape for one.

    `approvals` and not `calls`: PACT parked because something outside the run
    has to happen — a person approving a payment, a permission being granted —
    which is what `approvals` means here. `calls` means "you execute this", and
    the harness will execute it itself when the wait clears.

    **Every key is PACT's own.** The slot comes from `_pending`, which is
    ``harness.slots_of`` — the bare tool name for a step's first call to it,
    `<tool>#<n>` from the second on — and never a provider's `tool_call_id`,
    because a provider id is minted by whichever model happened to serve the step
    and a resume has to survive the process dying. Minting them here instead is
    how the two came to disagree: an id in the harness's namespace that names a
    different call in it is worse than a foreign id, because it looks answerable.
    The correlation key beside it is `Suspension.correlation_key`, derived from
    what the run was waiting for, so two transports running the same tree park
    under the same key and a stale answer cannot land.

    **And only what is still waiting**, for the reason `_pending` gives: the
    calls the gate cleared ran before the park, so listing them here is an
    approval asked for something that already happened.
    """
    calls = [
        ToolCallPart(tool_name=call.name, args=dict(call.args), tool_call_id=slot)
        for slot, call in _pending(parked)
    ]
    return DeferredToolRequests(
        approvals=calls,
        metadata={
            part.tool_call_id: {
                "correlation-key": parked.correlation_key,
                "reason": parked.reason,
            }
            for part in calls
        },
    )
