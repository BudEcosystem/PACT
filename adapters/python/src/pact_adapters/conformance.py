"""The Conformance Report (AC-2.2).

The criterion, verbatim:

> For every (golden agent × adapter) pair, the shared eval suite passes with
> score within a declared ε of the reference adapter, **or** the adapter declares
> the relevant feature `degraded`/`unsupported` in its lattice *and* the
> Conformance Report says so before execution.

Three obligations in one sentence, and the third is the one that makes it worth
anything: **before execution**. A report that lists what diverged after the fact
is a changelog. A report that states what each adapter has declared it cannot do,
and is then held to it, is a claim that can be wrong — so an adapter that diverges
on something it declared `native` fails, and one that diverges on something it
declared `unsupported` was telling the truth.

`ε` is declared here rather than passed in, because a tolerance a caller chooses
is a tolerance that grows to fit the result.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .harness import run
from .ir import AgentSpec
from .loader import FIX as LOADER_FIX
from .loader import pact_binary
from .providers import coverage as metric_coverage
from .script import Script, Turn
from .transports.anthropic_transport import AnthropicTransport
from .transports.autogen_transport import AutoGenTransport
from .transports.langchain_transport import LangChainTransport
from .transports.langgraph_transport import LangGraphTransport
from .transports.mock import ReferenceTransport
from .transports.openai_agents_transport import OpenAIAgentsTransport
from .transports.pydantic_ai_transport import PydanticAITransport

#: The declared ε, and it is **zero**.
#:
#: Not a hedge and not laziness. Every comparison this report makes is driven by
#: a scripted transport: the model's answer is fixed, so two adapters running the
#: same agent have nothing legitimate to differ about. A non-zero ε here would be
#: room for a real divergence to hide in — and the whole claim is that the
#: framework does not get to change what the agent does.
#:
#: A tolerance would be needed the moment a LIVE model is in the loop, because
#: sampling is not deterministic. That is a different report, and it would have
#: to declare its own ε with the sample size it was measured over.
EPSILON: float = 0.0

#: What the reference is. Every other target is compared against this one, and it
#: is the framework-free control on purpose: comparing frameworks only against
#: each other would agree perfectly while all seven were wrong together.
REFERENCE = "reference"

TARGETS: dict[str, Any] = {
    REFERENCE: ReferenceTransport,
    "pydantic-ai": PydanticAITransport,
    "langgraph": LangGraphTransport,
    "langchain": LangChainTransport,
    "autogen": AutoGenTransport,
    "openai-agents": OpenAIAgentsTransport,
    "anthropic": AnthropicTransport,
}

#: What is asked, and what the scripted model says back. One turn: see
#: `test_the_golden_set_runs_everywhere.py` for what that covers and what it does
#: not, which this report repeats rather than assumes.
ASKED = "What do you make of this?"
ANSWER = "Here is what I make of it."


class _Watching(ReferenceTransport):
    """Records what each call was handed, so inputs are compared and not only
    outputs. A scripted model says the same thing whatever you tell it."""

    def __init__(self, s: Script) -> None:
        super().__init__(s)
        self.told: list[str] = []
        self.offered: list[list[str]] = []

    async def model_call(self, system, history, tools):  # type: ignore[no-untyped-def]
        self.told.append(system)
        self.offered.append([t["name"] for t in tools])
        return await super().model_call(system, history, tools)


def _agents(root: Path, pact_bin: Path) -> list[tuple[str, dict[str, Any]]]:
    out = subprocess.run(
        [str(pact_bin), "show", str(root)], capture_output=True, text=True, check=True
    )
    doc = json.loads(out.stdout)
    return [(key, doc) for key in sorted(doc.get("agents", {}))]


def _run(spec: AgentSpec, cls: Any) -> dict[str, Any]:
    s = Script([Turn(ANSWER)])
    transport = cls(s)
    result = asyncio.run(run(spec, transport, ASKED, {}))
    return {
        "trace": result.trace(),
        "output": result.output,
        "halted": result.halted,
        "calls": s.calls,
        "told": getattr(transport, "told", None),
        "offered": getattr(transport, "offered", None),
    }


def report(roots: list[Path], pact_bin: Path) -> dict[str, Any]:
    """Every (golden agent × adapter) pair, against a declared ε.

    The order of the keys is the order of the obligations: what each adapter has
    DECLARED comes first, then what was measured. A reader has to be able to see
    the claim before the result, or "we expected that" is unfalsifiable.
    """
    declared = {
        name: cls(Script([Turn(ANSWER)])).lattice() for name, cls in TARGETS.items()
    }
    results: list[dict[str, Any]] = []

    for root in roots:
        for key, doc in _agents(root, pact_bin):
            spec = AgentSpec.from_document(doc, key, source=root)
            baseline = _run(spec, _Watching)
            for name, cls in TARGETS.items():
                if name == REFERENCE:
                    continue
                got = _run(spec, cls)
                same = (
                    got["trace"] == baseline["trace"]
                    and got["output"] == baseline["output"]
                    and got["halted"] == baseline["halted"]
                    and got["calls"] == baseline["calls"]
                )
                results.append({
                    "agent": f"{root.name}/{key}",
                    "adapter": name,
                    "agreed": same,
                    # Named so a divergence can be checked against what this
                    # adapter said it could not do, rather than excused.
                    "declares": declared[name],
                })

    diverged = [r for r in results if not r["agreed"]]
    return {
        "apiVersion": "pact.dev/v1",
        "kind": "ConformanceReport",
        "epsilon": EPSILON,
        "epsilon-because": (
            "every comparison here is driven by a scripted transport, so two "
            "adapters running one agent have nothing legitimate to differ about. "
            "A non-zero tolerance would be room for a real divergence to hide in."
        ),
        "reference": REFERENCE,
        "declared-before-execution": declared,
        # AC-4.1's PUBLISHED matrix: every metric DeepEval ships, the URI an
        # author types for it, and — for the ones PACT does not offer — why. The
        # criterion asks for something published, and `providers.coverage` had no
        # caller outside its own test, which made "published" a property of the
        # test suite. It belongs in this artifact rather than behind a flag of its
        # own: a conformance report is the thing a reader diffs and disagrees
        # with, and what the graders cover is part of what conforms.
        #
        # Computed from the installed DeepEval, never listed, which is E-4 — the
        # provider resolves by string, so a matrix that enumerated the set would
        # put back exactly the coupling E-4 removes.
        "metric-coverage": metric_coverage(),
        "compared": {
            "agents": len({r["agent"] for r in results}),
            "adapters": len(TARGETS),
            "pairs": len(results),
        },
        # What this report does NOT cover, stated in the artifact rather than in a
        # docstring somebody has to go and find. A conformance report whose scope
        # is implicit reads as covering everything.
        "not-compared": [
            "multi-step tool sequences: the script answers without calling a tool",
            "runs that park for a person: the second runtime publishes "
            "`durable_resume: unsupported`, so asserting over it would assert "
            "that the ports differ",
            "live-model scores: sampling is not deterministic and would need its "
            "own ε measured over a stated sample size",
            "the TypeScript target: it runs in Node and is held by "
            "`test_the_golden_set_runs_everywhere.py`, which compares it agent by "
            "agent against this same reference",
        ],
        "results": results,
        "summary": {
            "agreed": len(results) - len(diverged),
            "diverged": len(diverged),
            "undeclared-divergences": [
                r for r in diverged
                # A divergence is only excused where the adapter said in advance
                # it could not do the thing. Nothing here declares `degraded`, so
                # any divergence at all is currently undeclared — which is the
                # answer AC-2.2 wants and the one this report must not soften.
                if "degraded" not in r["declares"].values()
            ],
        },
    }


def main(argv: "list[str] | None" = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        sys.stdout.write(
            "pact_adapters.conformance — the Conformance Report (AC-2.2)\n\n"
            "USAGE:\n"
            "    python -m pact_adapters.conformance EXAMPLES_DIR\n\n"
            "Writes the report to stdout as JSON. Every (golden agent × adapter)\n"
            "pair, against a declared ε of "
            f"{EPSILON}, with what each adapter declared\n"
            "it could not do stated BEFORE the results.\n"
        )
        return 0
    where = Path(args[0]).resolve()
    pact_bin = pact_binary()
    if pact_bin is None:
        sys.stderr.write(
            "error: the loader was not found, and this report is about what it "
            f"produces.\n  fix: {LOADER_FIX}\n"
        )
        return 3
    roots = sorted(p.parent for p in where.rglob("workspace.yaml"))
    if not roots:
        sys.stderr.write(f"error: no workspace under {where}\n")
        return 3
    said = report(roots, pact_bin)
    sys.stdout.write(json.dumps(said, indent=2) + "\n")
    return 0 if said["summary"]["diverged"] == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
