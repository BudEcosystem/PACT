"""`turns:` as Pydantic AI messages (docs/96 §D): the one lowering every host on Pydantic AI uses.

An agent's `turns:` (a worked example placed before every live conversation), a variant's (the
few-shot a smaller model needs) and an eval case's (the conversation so far) are one `turn` group,
and `pact check` has already held them to their rules (`turns.rs`): `system` and `developer` only
before anyone speaks, every `calls:` answered by the very next `tool` turn, a call to an action
the agent may use. This module lowers them, by §D's table:

| PACT | Pydantic AI |
|---|---|
| `system`, `developer` | `SystemPromptPart` (both: the provider places them) |
| `user` | `UserPromptPart`, with what `attaches:` names after the words |
| `agent` | `ModelResponse([TextPart])` |
| `agent` with `calls:` | `ModelResponse([ToolCallPart])`, `with:` as its arguments |
| `tool` | `ToolReturnPart`, `answer:` as its content, under the call's own id |

Consecutive parts of one side share one message, as a provider sends them. What `says:` is filled
with, how an attachment becomes content, and what a `<tool>/<action>` is called where the model
sees it are the host's (`fill`, `attached`, `tool_name`): an agent's turns may carry holes, a case's
never do, and each host names its tools its own way.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelRequestPart,
    ModelResponse,
    ModelResponsePart,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

__all__ = ["messages_of"]

#: The speakers whose words are standing instructions rather than a turn of the conversation.
STANDING = ("system", "developer")


def _same(text: str) -> str:
    return text


def messages_of(
    turns: Iterable[Mapping[str, Any]],
    *,
    fill: Callable[[str], str] | None = None,
    attached: Callable[[str], Any] | None = None,
    tool_name: Callable[[str], str] | None = None,
    call_ids: str = "turn",
) -> list[ModelMessage]:
    """The turns as Pydantic AI messages, oldest first. `fill` fills a turn's words (an agent's,
    with its holes; a case's are used as written); `attached(name)` is one `UserContent` for an
    `attaches:` entry; `tool_name("<tool>/<action>")` is the name the model calls it by. Each call
    is given the id `<call_ids>-<n>`, and the `tool` turn after it answers under the same id."""
    fill, tool_name = fill or _same, tool_name or _same
    out: list[ModelMessage] = []
    request: list[ModelRequestPart] = []
    response: list[ModelResponsePart] = []
    pending: tuple[str, str] | None = None  # the call the next `tool` turn answers: (name, id)
    n = 0

    def close_request() -> None:
        if request:
            out.append(ModelRequest(parts=list(request)))
            request.clear()

    def close_response() -> None:
        if response:
            out.append(ModelResponse(parts=list(response)))
            response.clear()

    for turn in turns:
        speaker = str(turn.get("from") or "").strip()
        says = turn.get("says")
        if speaker in STANDING:
            close_response()
            request.append(SystemPromptPart(fill(str(says or ""))))
        elif speaker == "user":
            close_response()
            content: list[Any] = [fill(str(says))] if says else []
            for name in turn.get("attaches") or ():
                if attached is not None and (one := attached(str(name))) is not None:
                    content.append(one)
            request.append(UserPromptPart(content if len(content) != 1 or not isinstance(content[0], str) else content[0]))
        elif speaker == "agent":
            close_request()
            if says:
                response.append(TextPart(fill(str(says))))
            if turn.get("calls"):
                n += 1
                name, call_id = tool_name(str(turn["calls"]).strip()), f"{call_ids}-{n}"
                response.append(ToolCallPart(name, dict(turn.get("with") or {}), tool_call_id=call_id))
                pending = (name, call_id)
        elif speaker == "tool":
            close_response()
            name, call_id = pending if pending is not None else ("tool", f"{call_ids}-{n}")
            request.append(ToolReturnPart(name, turn.get("answer"), tool_call_id=call_id))
            pending = None
    close_request()
    close_response()
    return out
