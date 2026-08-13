"""The eighth framework, in fifty lines and outside the core (AC-2.5).

There is no framework here — the point is not what it binds but where it lives.
This file is in no package the core installs, is imported by nothing under
`adapters/python/src`, and appears in no registry. If a transport needed to be
registered somewhere to work, this could not run at all, and that is exactly the
property the criterion is about.

`Transport` in `harness.py` is a `Protocol`, so conformance is structural: an
object with `model_call` IS a transport. Nothing is inherited and nothing is
declared. The six optional methods below are optional in the strict sense — a
transport that omits them says nothing and the run reports what it could not
therefore enforce, rather than failing to load.
"""

from __future__ import annotations

from typing import Any


class EchoTransport:
    """Answers with the last thing it was asked, and says what it costs.

    Enough of a model to drive a loop, little enough to read in one sitting. An
    author writing a real eighth adapter replaces `model_call` and keeps the
    shape.
    """

    #: Which runtime this is, in the catalogue's `served-by:` vocabulary. A name
    #: the core has never seen, which is the point.
    runtime = "echo"

    def __init__(self, prefix: str = "you said: ") -> None:
        self.prefix = prefix
        self.calls = 0

    def lattice(self) -> dict[str, str]:
        """What this can do, in the four words the lattice uses.

        Declared rather than assumed. An adapter that published nothing would be
        one a Conformance Report could not account for, which is AC-2.2's `or`
        clause read from the other side.
        """
        return {
            "model_call": "native",
            "tool_calls": "unsupported",
            "text_with_tool_calls": "unsupported",
            "parallel_tool_calls": "unsupported",
            "streaming": "unsupported",
            "durable_resume": "unsupported",
            # An out-of-tree adapter is not obliged to track the core's key set
            # — E-1 says adding one costs zero core changes, and no test here
            # compares this dict against a core transport's. It is written all
            # the same, because P-2's *"an adapter that omits a feature cannot
            # be compared"* is the reason the key set matters, and an exemplar
            # that quietly omitted the newest one would teach the omission.
            #
            # `emulated` rather than `unsupported`, and an eighth adapter's
            # author does not have to do anything to earn it: a `connect:` tool
            # reaches its server through PACT's own client and the `tool_impls`
            # seam `harness.run` already has, above whatever this binds. Only a
            # transport that takes the LOOP away — `a2a_transport.py` — is
            # `unsupported` there.
            "connected_tools": "emulated",
        }

    #: Whether ANYTHING can put a price on what a call here carried. Nothing
    #: can: this is a scripted echo bound to no model, so no row in
    #: `models/catalog.yaml` describes it and none ever will.
    #:
    #: Separate from `usage()` on purpose, and the reason is the same one the
    #: `lattice()` comment gives about the newest key — an exemplar that quietly
    #: omitted this would teach the omission. `harness.run` reads two facts in
    #: two steps: does `usage()` exist (tokens), and can anything price it
    #: (money). It defaults the second to `False`, so an undeclared transport is
    #: told nothing on its behalf and the author's money ceilings arrive on
    #: `RunResult.unmetered` — which is the honest report here. This file said
    #: nothing for a round and returned `0.0` below, and a run over it reported
    #: `cost-per-request-under: 0.05 USD` as ENFORCED against a meter that read
    #: 0.00 for the life of the workspace. That is B6, in the one file a third
    #: party is told to copy.
    prices_money = False

    def usage(self) -> tuple[int, float | None]:
        """Tokens for the last call, and no price — because there is none.

        `None`, never `0.0`. `transports/_metering.py` states the rule in the
        imperative: *"An unpriced row yields `None`, never zero … Metering a
        ceiling at 0.0 USD is a spend cap that can never be reached, under an
        author who believes they capped their spend."* `harness._meter_usage`
        adds the token count and leaves the money meter alone when the second
        half is `None`, so a cap over this transport moves nothing and says so,
        rather than sitting at 0.00 and looking held.
        """
        return (len(self.prefix) // 4, None)

    async def model_call(
        self,
        system: str,
        history: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> tuple[str, list[Any]]:
        self.calls += 1
        asked = next(
            (m["content"] for m in reversed(history) if m.get("role") == "user"),
            "",
        )
        return f"{self.prefix}{asked}", []
