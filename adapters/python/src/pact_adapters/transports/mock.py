"""The reference transport: the script, with no framework at all.

This is the control arm. If a framework transport disagrees with this, the
framework is the difference — and per invariant F-4 that is a defect to be
tracked, not a fact to be accepted.

**Deliberately no `context_window()`, no `write_summary()`, no `usage()` and no
`summary_usage()`.** Every other transport in this package is bound to a model
id: it looks its window up in `models/catalog.yaml`, it prices what a call
carried against the same file, and it can re-bind to the second model
`context-policy.summarised-by:` names. This one is bound to nothing — it is the
script, with no framework and no model — so it has no window to report, no price
to charge and no second model to call, and inventing any of them would make the
control arm the least honest thing in the set. `harness._window` returns `None`
for it, `harness._summariser` returns `None` for it, `harness._meter_usage` adds
nothing for it, `run()` names `context-policy`, `summarised-by`,
`cost-per-request-under` and `tokens-at-most` on `RunResult.unmetered`, and an
author who wrote a policy or a spend cap is told which parts of it could not run
here rather than being measured against a guess.

That path is not an oversight; it is the other half of the guarantee. This stays
the one transport that is honest-and-inert on purpose, so the `unmetered` route
has something that exercises it — every other real transport now implements the
optional methods its seam can answer, and a mechanism whose failure path nothing
reaches is a mechanism nobody has checked. `test_context_policy.py` holds both
halves for the window and the summariser; `test_termination.py` holds both
halves for the money and token ceilings.
"""

from __future__ import annotations

from typing import Any

from ..harness import ToolCall
from ..script import Script


class ReferenceTransport:
    name = "reference"

    def __init__(self, script: Script) -> None:
        self.script = script

    def lattice(self) -> dict[str, str]:
        return {
            "model_call": "native",
            "tool_calls": "native",
            "text_with_tool_calls": "native",
            "parallel_tool_calls": "native",
            "streaming": "unsupported",
            "durable_resume": "unsupported",
            # Whether a tool's `connect:` line — the one of `ir.WAYS_A_TOOL_
            # REACHES` that names a SYSTEM in `resources:` rather than an
            # address or a wording — becomes a call that leaves this process on
            # this runtime. Spelled for the IR feature and not for a protocol,
            # because `ResourceSpec.kind` is carried rather than assumed and a
            # key named after today's one choice would be a portability
            # instrument that has already picked a wire format.
            #
            # `emulated`, in this lattice's own sense of the word — PACT
            # provides it ABOVE the transport. `pact_adapters/mcp/` is PACT's
            # own client and `mcp.calling.tool_impls_for` turns a `connect:`
            # tool into the `harness.ToolFn` the loop already executes, so the
            # reaching belongs to PACT and not to whatever binds the model.
            # That makes the word the same on every harness-driven target,
            # including this inert one: being bound to no model is a fact about
            # METERING here, and executing a tool was never the transport's job.
            #
            # The two targets that are `unsupported` are unsupported for reasons
            # that are not about the client — `a2a_transport.py` hands the loop
            # to somebody else, and the TypeScript port has no PACT client at
            # all — which is what keeps this column from being decoration.
            "connected_tools": "emulated",
        }

    async def model_call(
        self, system: str, history: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> tuple[str, list[ToolCall]]:
        turn = self.script.next_turn(history)
        return turn.text, list(turn.tool_calls)
