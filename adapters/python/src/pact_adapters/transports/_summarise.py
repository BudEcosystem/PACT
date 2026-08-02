"""One summarising model call, finished synchronously, on any transport.

This is the shared half of `context-policy.summarised-by:` — the rung of the
author's ladder that needs a model. `AnthropicTransport.write_summary` states
the rule the five framework transports follow here: *a second transport rather
than a second code path — same class, same script, another model id — because
"summarise with a different model" is one model call and the harness already
knows how to make one. Nothing about the work model changes; `self.model` is
untouched.*

**Why this module exists at all: the method must stay synchronous.**
`ollama_transport.py` gives the reason where the first one was written — tidying
decides mid-history what to fold, so a summariser the tidier had to await would
make every context strategy async, four rungs rewritten for the one that needs a
model. The two transports that already had `write_summary` could honour that
unaided: the Anthropic SDK builds its `Message` synchronously, and Ollama's is
one blocking request. The five framework seams are async only —
`direct.model_request`, `Pregel.ainvoke`, `ChatCompletionClient.create`,
`Model.get_response`, `BaseChatModel._agenerate` — and the summariser is called
from *inside* the harness's own running loop, so `asyncio.run` refuses and
Pydantic AI's own `model_request_sync` raises `This event loop is already
running`.

So the coroutine is finished on a private loop in a worker thread. The calling
thread blocks, exactly as Ollama's `httpx.post` does and for the same declared
reason; the framework's real seam is used rather than reaching around it into
the script; and neither the running loop nor the work model is disturbed. One
construct for all five, rather than a sync shortcut per framework — two of the
five have no sync seam to shortcut to, so a per-framework answer would have been
two mechanisms doing one job.

Nothing here leaves the box: which model answers is the second transport's
business, and the distribution's default is locally served (D17).
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Coroutine, TypeVar

T = TypeVar("T")

#: What the summarising model is told to do. Wording lifted from
#: `ollama_transport.py`, which is the one transport here that puts it on a wire
#: to real weights, so all of them ask for the same thing rather than each
#: inventing a prompt. The scripted seams ignore it — they answer from history —
#: but a transport pointed at a live provider would not, and a summarising call
#: that carries no instruction is a continuation of the conversation rather than
#: a summary of it.
SUMMARISE = (
    "Summarise the conversation below. Keep decisions, figures and anything a "
    "person approved. Be brief."
)


def summarise_with(transport: Any, text: str) -> str:
    """One model call on `transport`; its text is the summary.

    `transport` is the SECOND instance — the caller has already built it, bound
    to the id the author wrote in `summarised-by:`. Called through the transport's
    own declared seam, `model_call`, so the summary travels the same path the
    work does and a framework that would mangle it mangles it visibly.

    No tools are offered: a summariser is asked for prose. If the model answers
    with tool calls anyway they are discarded here, because a call issued during
    a summarising request belongs to no step and there is no loop to run it in.
    """
    said, _calls_that_belong_to_no_step = finish_now(
        transport.model_call(SUMMARISE, [{"role": "user", "content": text}], [])
    )
    return said


def finish_now(work: Coroutine[Any, Any, T]) -> T:
    """Run one coroutine to completion from synchronous code, loop or no loop.

    Public rather than private because it now has a second caller with the same
    problem: `judge.local_ask` grades a `judged:` rule with one model call from
    inside `evals.check`, which is synchronous for the same reason tidying is —
    every caller of the scorer would otherwise have to become async so that one
    rule of five could run. A second copy of the loop-or-no-loop dance is exactly
    the overlapping construct this file exists to avoid.

    Two callers, two situations. A test calling `write_summary()` directly has no
    running loop, and `asyncio.run` is then the whole answer. The harness has
    one — `Tidier.apply` is called from inside `run()` — and reentering it is not
    possible, so the work goes to a thread with a loop of its own and this one
    waits for it. Waiting is the point rather than a compromise: the tidier's
    next decision depends on the summary it just got back.

    **What blocking costs, and who pays it.** The calling thread stops until the
    summary comes back. For a round that thread was the event loop's, because
    `run()` called `_tidy` inline — so one delegate tidying froze every sibling
    and every `gives-up-after:` in the run. Measured end-to-end on authored lines
    only: a 500ms deadline fired at 1.07s, and a member whose answer HAD arrived
    was recorded `out-of-time` and thrown away. The harness now runs the whole of
    tidying through `asyncio.to_thread`, so this branch is reached on a worker
    thread that has no loop of its own to stop, the `asyncio.run` above is taken,
    and the siblings' clocks keep running.

    What remains, and it is a property of threads rather than of this design: a
    child inside a summarising call cannot be cancelled promptly, so a deadline
    that expires mid-summary is reported correctly but returned late. Said again
    at the reaping in `delegation._all_at_once`, which is the other place a
    reader meets it.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(work)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, work).result()
