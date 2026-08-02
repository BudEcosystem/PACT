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
        }

    def usage(self) -> tuple[int, float]:
        """Tokens and money for the last call. Free, and counted honestly."""
        return (len(self.prefix) // 4, 0.0)

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
