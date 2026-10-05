"""A summary a runtime awaits rather than blocks for (`Tidier.apply_async`).

`summarise-older` is the one rung of a context policy that needs a model call,
and `Summariser` is synchronous: a runtime whose model calls are coroutines (a
host on an event loop, such as budflow-core on Pydantic AI) could only finish
one by blocking a thread. `apply_async` takes an awaitable summariser and keeps
the ladder the one `apply` runs, so there is no second copy of it to drift; and
`summary_request` is the one text every runtime shows the summarising model.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.context_policy import (  # noqa: E402
    SUMMARISE,
    ContextPolicy,
    Message,
    Part,
    PartKind,
    Tidier,
    summary_request,
)
from pact_adapters.transports import _summarise  # noqa: E402


def say(role: str, text: str) -> Message:
    return Message(role=role, parts=(Part(PartKind.TEXT, text),))


def policy(**over) -> ContextPolicy:
    doc = {"context-policies": {"p": {"when-full": "80%", **over}}}
    return ContextPolicy.from_document(doc, "p")


def joined(folding, previous) -> str:
    body = " | ".join(m.text()[:20] for m in folding)
    return f"EARLIER: {previous + ' >> ' if previous else ''}{body}"


def test_an_awaited_summary_tidies_exactly_as_a_called_one_and_is_asked_for_once() -> None:
    p = policy(
        **{
            "then": [
                {"what": "summarise-older"},
                {"what": "keep-recent-only", "down-to": "the last 1 messages"},
            ]
        }
    )
    convo = [say("user", f"message {i} " * 60) for i in range(8)]
    asked: list[tuple[int, str]] = []

    async def awaited(folding, previous) -> str:
        asked.append((len(folding), previous))
        await asyncio.sleep(0)
        return joined(folding, previous)

    tidier = Tidier(p, budget_tokens=120)
    out = asyncio.run(tidier.apply_async(convo, awaited))
    same = Tidier(p, budget_tokens=120, summarise=joined).apply(convo)
    assert [m.text() for m in out.messages] == [m.text() for m in same.messages]
    assert out.outcome == same.outcome and out.fired == same.fired
    assert len(asked) == 1, f"one fold, one summary: {asked}"


def test_a_conversation_that_fits_is_never_summarised() -> None:
    p = policy(**{"then": [{"what": "summarise-older"}]})

    async def never(folding, previous) -> str:
        raise AssertionError("nothing needed summarising")

    out = asyncio.run(Tidier(p, budget_tokens=10_000).apply_async([say("user", "hi")], never))
    assert out.outcome == "not-needed"


def test_the_summariser_is_shown_the_previous_summary_then_the_folded_messages() -> None:
    folded = [say("user", "my lamp broke"), Message(role="user", parts=(Part(PartKind.IMAGE, ""),))]
    assert summary_request(folded, "") == "user: my lamp broke\nuser: [a picture that was sent in]"
    assert summary_request(folded[:1], "they bought a lamp").startswith(
        "Summary so far:\nthey bought a lamp\n\nuser: my lamp broke"
    )
    assert _summarise.SUMMARISE is SUMMARISE  # one wording for every runtime


def test_the_question_a_conversation_too_long_to_send_puts_is_found_by_its_reason() -> None:
    """`context-policies.<p>.asks` beside `if-it-still-does-not-fit: ask-a-person`,
    read the way `PauseRule.from_document` reads it (and no other way)."""
    from pact_adapters.suspension import CONTEXT_TOO_LONG, OUT_OF_BUDGET, question_for

    doc = {
        "agents": {"desk": {"context-policy": "long"}},
        "context-policies": {"long": {"if-it-still-does-not-fit": "ask-a-person", "asks": "too-long"}},
    }
    assert question_for(doc, "desk", CONTEXT_TOO_LONG) == "too-long"
    assert question_for(doc, "desk", OUT_OF_BUDGET) is None
