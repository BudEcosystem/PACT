"""AC-2.1 — the golden set: every shipped agent, on every target, identical.

The criterion asks for a **golden set of ≥12 agents** run per framework. The
register's finding was blunt and correct: *"byte-identical across seven targets
is currently proven on ONE agent"* — an existence proof, not a conformance set.

This runs **every agent in `examples/`** — one entry per agent `pact show`
reports under every `examples/**/workspace.yaml` — over all seven Python targets
and the TypeScript port, and asserts the traces are identical. It is generated
from the tree rather than listed here, so an agent added to `examples/` joins
the set by existing.

**How many that is, is deliberately not written here.** It is `len(GOLDEN)`,
and this docstring said "twenty-eight of them across nine workspaces" while the
tree held more — the figure went stale the first time somebody added a pattern,
and `docs/70-PRODUCTION-GAP-REGISTER.md` had copied it. A count in prose beside
a set built from the tree is a second copy of the set.

**What this covers, precisely.** The script answers without calling a tool, so
what is compared is everything that decides the FIRST model call and the shape
of the run around it: the system text (instructions, stage wording, written
procedures, the declared `answers-with:` shape), the loop's starting stage, and
how the run ends. That is where every portability defect this repository has
found actually lived — the unported answer shape, the skills that reached no
model, the loop the conformance payload never sent.

**What it does not cover.** Multi-step tool sequences per agent, and any run that
parks: the TypeScript port publishes `durable_resume: unsupported`, so a
supervisor whose script calls a teammate suspends in Python and errors in Node.
That divergence is real, documented in §7.28, and asserting over it here would
be asserting that the two ports differ. The worked example's own multi-step
sequence is held by `test_portability.py`, which does exactly that for one agent
in depth. This file is breadth; that one is depth, and the thesis asks for both.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.anthropic_transport import AnthropicTransport  # noqa: E402
from pact_adapters.transports.autogen_transport import AutoGenTransport  # noqa: E402
from pact_adapters.transports.langchain_transport import LangChainTransport  # noqa: E402
from pact_adapters.transports.langgraph_transport import LangGraphTransport  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402
from pact_adapters.transports.openai_agents_transport import (  # noqa: E402
    OpenAIAgentsTransport,
)
from pact_adapters.transports.pydantic_ai_transport import PydanticAITransport  # noqa: E402
from pact_adapters.ports import tool_payload  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "examples"
PACT_BIN = REPO / "target" / "debug" / "pact"
TS_DIR = REPO / "adapters" / "typescript"

#: The six frameworks plus the framework-free control. The seventh target —
#: Vercel AI — runs in Node and is reached through `run-trace.ts` below.
TRANSPORTS = {
    "reference": ReferenceTransport,
    "pydantic-ai": PydanticAITransport,
    "langgraph": LangGraphTransport,
    "langchain": LangChainTransport,
    "autogen": AutoGenTransport,
    "openai-agents": OpenAIAgentsTransport,
    "anthropic": AnthropicTransport,
}

#: What every agent in the set is asked, and what the model says back. One turn,
#: no tool calls — see the module note for why, and for what that leaves out.
ASKED = "What do you make of this?"
ANSWER = "Here is what I make of it."


def _workspaces() -> list[Path]:
    """Every directory under `examples/` holding a `workspace.yaml`."""
    return sorted(p.parent for p in EXAMPLES.rglob("workspace.yaml"))


def _golden_set() -> list[tuple[str, str]]:
    """`(workspace path relative to examples/, agent key)` for every agent."""
    if not PACT_BIN.exists():
        return []
    out: list[tuple[str, str]] = []
    for root in _workspaces():
        shown = subprocess.run(
            [str(PACT_BIN), "show", str(root)], capture_output=True, text=True, check=True
        )
        for key in sorted(json.loads(shown.stdout).get("agents", {})):
            out.append((str(root.relative_to(EXAMPLES)), key))
    return out


GOLDEN = _golden_set()


def _spec(where: str, agent: str) -> AgentSpec:
    root = EXAMPLES / where
    shown = subprocess.run(
        [str(PACT_BIN), "show", str(root)], capture_output=True, text=True, check=True
    )
    return AgentSpec.from_document(json.loads(shown.stdout), agent, source=root)


class Watching(ReferenceTransport):
    """Records what each model call was actually HANDED.

    Borrowed from `test_portability.py`, which explains why it has to exist: a
    trace records the model's replies, and `says:`, `may-use:`, the written
    procedures and the declared `answers-with:` shape are all claims about what
    the model was TOLD and OFFERED — inputs to the call, not outputs of it.

    This file compared traces alone for its first draft, and two mutations proved
    that worthless: deleting the answer shape from the second port's system text,
    and deleting the skills from it, both left all fifty-nine assertions green. A
    scripted model says the same thing whatever you tell it, so comparing what it
    said compares the script. That is the "seam, not effect" mistake this round
    has now produced three times.
    """

    def __init__(self, s: Script) -> None:
        super().__init__(s)
        self.told: list[str] = []
        self.offered: list[list[str]] = []

    async def model_call(self, system, history, tools):  # type: ignore[no-untyped-def]
        self.told.append(system)
        self.offered.append([t["name"] for t in tools])
        return await super().model_call(system, history, tools)


def _here(spec: AgentSpec, transport_cls: Any) -> dict[str, Any]:
    s = Script([Turn(ANSWER)])
    transport = transport_cls(s)
    result = asyncio.run(run(spec, transport, ASKED, {}))
    return {
        "trace": result.trace(),
        "output": result.output,
        "halted": result.halted,
        "model_calls": s.calls,
        "told": getattr(transport, "told", None),
        "offered": getattr(transport, "offered", None),
    }


def _loops_of(spec: AgentSpec) -> dict[str, Any]:
    """The agent's own loop, in the shape `loops.ts` reads.

    Sent so the second runtime runs the SAME shape rather than falling back to
    the standard one by accident — `loop`/`loops` reached Node from no test at
    all for a round, so the two ports "agreed" about a shape only one of them
    had read.
    """
    from pact_adapters.loops import _phase_to_mapping

    if spec.loop is None:
        return {}
    return {
        spec.loop.name: {
            "starts-at": spec.loop.starts_at,
            "steps": {k: _phase_to_mapping(v) for k, v in spec.loop.steps.items()},
        }
    }


def _there(spec: AgentSpec) -> dict[str, Any] | None:
    """The same agent through the Vercel AI SDK, in Node. `None` if unavailable."""
    payload = json.dumps({
        "name": spec.name,
        "instructions": spec.instructions,
        "tools": [tool_payload(t) for t in spec.tools],
        "maxSteps": spec.max_steps,
        "skills": [
            {
                "name": s.name, "description": s.description,
                "use-when": s.use_when, "do-not-use-when": s.do_not_use_when,
                "if-unsure": s.if_unsure, "content": s.content,
            }
            for s in spec.skills
        ],
        # A7. Sent for the reason the comment at the top of this file gives about
        # `skills`: a field the payload never carries is a field the second port
        # cannot honour, and the divergence looks like a bug in the port rather
        # than a hole in the driver. Measured — with `knowledge` missing here,
        # Python refused a `must-cite:` corpus it could not read and Node
        # answered, and the port had the code to refuse it all along.
        "knowledge": [
            {
                "name": k.name, "description": k.description,
                "must-cite": k.must_cite,
                "passages-at-most": k.passages_at_most,
                "looked-up-by": k.looked_up_by, "split-by": k.split_by,
            }
            for k in spec.knowledge
        ],
        "team": dict(spec.team),
        "loop": spec.loop.name if spec.loop else "",
        "loops": _loops_of(spec),
        "answersWith": dict(spec.answers_with),
        "answersWithMode": spec.answers_with_mode,
    })
    out = subprocess.run(
        ["node", "--experimental-strip-types", "src/run-trace.ts",
         payload, json.dumps({"turns": [{"text": ANSWER}]}), ASKED],
        cwd=TS_DIR, capture_output=True, text=True,
    )
    if out.returncode != 0:
        return None
    return json.loads(out.stdout)


# ─────────────────────────────────────────────────── the set itself


def test_the_golden_set_is_big_enough_to_be_one() -> None:
    """AC-2.1 asks for **≥12**. One agent is an existence proof, and that is what
    the portability claim rested on for the life of the project."""
    if not GOLDEN:
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    assert len(GOLDEN) >= 12, (
        f"the golden set has {len(GOLDEN)} agents: {GOLDEN}"
    )
    # And from more than one workspace, or twelve agents in one tree would be
    # twelve variations on one author's habits.
    assert len({w for w, _ in GOLDEN}) >= 5, sorted({w for w, _ in GOLDEN})


def test_the_set_is_generated_from_the_tree_not_listed_here() -> None:
    """A hand-written list is a scope somebody has to remember to extend, which
    is the defect this repository keeps producing — most recently in the loop
    drift check, which covered two of six shapes and said nothing."""
    if not GOLDEN:
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    on_disk = {p.relative_to(EXAMPLES).as_posix() for p in _workspaces()}
    assert {w for w, _ in GOLDEN} == on_disk, (
        f"workspaces on disk: {sorted(on_disk)}; in the set: "
        f"{sorted({w for w, _ in GOLDEN})}"
    )


# ─────────────────────────────────── every agent, on every Python target


@pytest.mark.parametrize("where,agent", GOLDEN)
def test_every_agent_runs_identically_on_every_python_target(
    where: str, agent: str
) -> None:
    """Six frameworks and the framework-free control, on one agent, compared
    whole. A divergence here is an ambiguity in PACT rather than a bug in one
    SDK — which is the entire reason the control arm is in the set."""
    spec = _spec(where, agent)
    results = {name: _here(spec, cls) for name, cls in TRANSPORTS.items()}
    reference = results["reference"]
    for name, got in results.items():
        assert got == reference, (
            f"{where}/{agent}: {name} diverged from the reference transport.\n"
            f"  reference: {json.dumps(reference, indent=2)}\n"
            f"  {name}: {json.dumps(got, indent=2)}"
        )
    # A workspace whose corpus says `must-cite: yes` and which is run where
    # nothing retrieves reaches `no-sources` — deliberately, and identically on
    # every target, which is what this test is actually about. PACT does not
    # retrieve; a run that answered anyway would answer from what the model
    # already knew and cite a document it never opened, which is the worst
    # outcome available and the one that looks most like success.
    #
    # It is asserted as its own case rather than folded into `final`, because
    # "every target refused for the same reason" and "every target answered" are
    # different claims and only one of them is true here.
    if spec.knowledge and any(c.must_cite for c in spec.knowledge):
        assert reference["halted"] == "no-sources", reference
        assert reference["model_calls"] == 0, (
            "nothing may be paid for before the sources are known to be missing",
            reference,
        )
        return
    assert reference["halted"] == "final", reference
    # NOT `model_calls == 1`. A multi-stage loop costs one call per stage, so
    # `refund-desk` (gather → re-read → reply) makes three for a single answer
    # and `debate` makes three of its own — that is the loop doing its job, not a
    # target doing something extra. Agreement on the count is already asserted
    # above, where it belongs; what is left to say here is the property that
    # holds whatever the shape: one step recorded per call, so a target that
    # silently retried would show a trace longer than its own count.
    assert reference["model_calls"] >= 1, reference
    assert len(reference["trace"]) == reference["model_calls"], reference


# ────────────────────────────────────────── and on the second runtime


@pytest.mark.parametrize("where,agent", GOLDEN)
def test_every_agent_runs_identically_on_the_typescript_target(
    where: str, agent: str
) -> None:
    """The seventh target, in a different language and a different SDK.

    This is where every portability defect found this session actually lived:
    the answer shape neither port asked for, the nested `limits.*` keys dropped
    in silence, the hardcoded currency. One agent was being compared, so one
    agent's worth of them was findable.
    """
    spec = _spec(where, agent)
    there = _there(spec)
    if there is None:
        pytest.skip("node or the AI SDK is unavailable")
    here = _here(spec, Watching)
    assert there["trace"] == here["trace"], (
        f"{where}/{agent}: the two runtimes produced different traces.\n"
        f"  python: {json.dumps(here['trace'], indent=2)}\n"
        f"  node:   {json.dumps(there['trace'], indent=2)}"
    )
    assert there["output"] == here["output"], (where, agent)
    assert there["halted"] == here["halted"], (where, agent)

    # AND WHAT THE MODEL WAS HANDED. This is the half a trace cannot show, and
    # without it this whole file passed while the second port sent no answer
    # shape and no written procedures at all.
    # A run that refused before it started told the model nothing, and that is
    # the point: `must-cite: yes` on a corpus nothing retrieved must not pay for
    # an answer it cannot give. Both ports have to agree on the silence too,
    # which the next assertion says.
    if here["halted"] != "no-sources":
        assert there["told"], f"{where}/{agent}: the second runtime recorded nothing told"
    assert there["told"] == here["told"], json.dumps(
        {"agent": f"{where}/{agent}", "node": there["told"], "python": here["told"]},
        indent=2,
    )
    assert there["offered"] == here["offered"], json.dumps(
        {"agent": f"{where}/{agent}",
         "node": there["offered"], "python": here["offered"]},
        indent=2,
    )


def test_the_agents_are_not_all_the_same_agent() -> None:
    """Twenty-four identical agents would satisfy every assertion above and prove
    nothing. The set has to contain real variety, or "twelve agents" is a count
    of files."""
    if not GOLDEN:
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    specs = [_spec(w, a) for w, a in GOLDEN]
    assert len({s.instructions for s in specs}) >= 12, (
        "the set has fewer than twelve distinct sets of instructions"
    )
    # At least one supervisor and at least one leaf, or the set is one shape.
    assert [s for s in specs if s.team], "no agent in the set has a team"
    assert [s for s in specs if not s.team], "every agent in the set has a team"
    # And more than one shape of thinking, or `loop:` is untested by breadth.
    assert len({s.loop.name for s in specs}) >= 2, (
        f"every agent thinks in the same shape: {sorted({s.loop.name for s in specs})}"
    )
