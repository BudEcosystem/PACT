"""Granting the worked example's connection consent, once, for tests about
something else.

`examples/refund-desk/resources/payments-server.yaml` says a person is asked
before this desk uses the payments connection. Since that line became a wait
rather than a note, **every** run of the worked example that reaches `payments`
parks once before anything goes over it — which is the example doing exactly what
it says, and is not what the tests importing this are about.

So the consent is given here, in the answer the author's own question asks for,
and the run carries on to the thing under test. One helper rather than a copy per
file: it is the same answer to the same question, and five copies of it would
drift the day the question's fields change.

`fresh_transport` is a factory and not a transport, because a `Script` is a
cursor: the run below is resumed, so each leg needs its own.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import run  # noqa: E402
from pact_adapters.suspension import NEEDS_PERMISSION  # noqa: E402

#: The connection the worked example gates, and the name its consent is answered
#: under — the SERVER, because consent is granted for the connection and not for
#: one call over it. Written out rather than derived, so a test tree that renames
#: the server has to say so here too.
CONNECTION = "payments-server"


def allowing_the_connection(spec, fresh_transport, prompt, tools, **kw):
    """Run, giving the connection consent if the run stops for it.

    A run that never reaches `payments`, or that was handed a gate of its own,
    comes straight back — this is a pass-through in every case but the one it
    exists for.
    """
    result = asyncio.run(run(spec, fresh_transport(), prompt, tools, **kw))
    parked = result.suspension
    if parked is None or parked.reason != NEEDS_PERMISSION:
        return result
    allowed = parked.answer(
        **{
            CONNECTION: "yes",
            f"{CONNECTION}.because": "allowed, so this test can reach the rest",
        }
    )
    return asyncio.run(
        run(spec, fresh_transport(), prompt, tools, resume=parked, answer=allowed, **kw)
    )
