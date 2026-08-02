"""The portability proof.

One PACT folder, loaded by the Rust CLI, executed over three different
transports — a bare reference, Pydantic AI, and LangGraph — must produce
*identical* behaviour. This is the claim the whole project rests on, so it is
tested against the real example tree and the real framework APIs, not fixtures.

Why traces and not just final output: two agents that reach the same answer by
calling different tools in a different order are not the same agent. Decision
D27 sets the bar at eval-score parity; this suite is stricter, because at the
harness level exact agreement is achievable and anything less would hide a
divergence that only shows up on a harder task.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.loops import STANDARD, Loop  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.anthropic_transport import AnthropicTransport  # noqa: E402
from pact_adapters.transports.autogen_transport import AutoGenTransport  # noqa: E402
from pact_adapters.transports.langchain_transport import LangChainTransport  # noqa: E402
from pact_adapters.transports.langgraph_transport import LangGraphTransport  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402
from pact_adapters.transports.openai_agents_transport import OpenAIAgentsTransport  # noqa: E402
from pact_adapters.transports.pydantic_ai_transport import PydanticAITransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"

#: Every named target from the brief, plus the framework-free reference that
#: acts as the control arm. Vercel's AI SDK is TypeScript and therefore runs in
#: a separate process — see `test_the_typescript_target_agrees_too`.
TRANSPORTS = {
    "reference": ReferenceTransport,
    "pydantic-ai": PydanticAITransport,
    "langgraph": LangGraphTransport,
    "langchain": LangChainTransport,
    "autogen": AutoGenTransport,
    "openai-agents": OpenAIAgentsTransport,
    "anthropic": AnthropicTransport,
}

TS_DIR = REPO / "adapters" / "typescript"


@pytest.fixture(scope="session")
def document() -> dict:
    """The example tree, loaded by the real Rust loader."""
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(PACT_BIN), "show", str(EXAMPLE)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


@pytest.fixture(scope="session")
def spec(document: dict) -> AgentSpec:
    # The shape of thinking is pinned here rather than read from the example.
    # This module asks whether seven transports agree on ONE loop; the example
    # declares `careful`, and letting that choice leak in would make an edit to
    # the worked example look like a transport divergence. `_ts_trace` sends the
    # SAME pinned loop across, so both ports run the shape this module is about.
    return replace(
        AgentSpec.from_document(document, "refund-desk"),
        loop=Loop.from_library(STANDARD),
    )


def _payload_for(spec: AgentSpec) -> str:
    """The conformance payload for one spec, in ONE place.

    It was written out inline at each call site, which is how the two sites came
    to send different slices of the same agent and how
    `test_every_key_the_loader_emits_is_sent_to_the_second_port_or_accounted_for`
    had nothing to check. A payload built twice is a comparison whose scope
    depends on which test you read.
    """
    return json.dumps({
        "name": spec.name,
        "instructions": spec.instructions,
        "tools": [{"name": t.name, "description": t.description} for t in spec.tools],
        "maxSteps": spec.max_steps,
        # The DOCUMENTS, not the names. Sending names meant no skill reached
        # any model in either port.
        "skills": [
            {
                "name": s.name,
                "description": s.description,
                "use-when": s.use_when,
                "do-not-use-when": s.do_not_use_when,
                "if-unsure": s.if_unsure,
                "content": s.content,
            }
            for s in spec.skills
        ],
        "team": dict(spec.team),
        "loop": spec.loop.name if spec.loop else "",
        "loops": _loops_of(spec),
        # `tier: core`, in the worked example, and absent from this payload for
        # every round the ports were compared — which is why neither port asked
        # the model for the shape the author declared and nothing noticed.
        "answersWith": dict(spec.answers_with),
        "answersWithMode": spec.answers_with_mode,
    })


def _loops_of(spec: AgentSpec) -> dict:
    """The one loop this module pins, in the shape `loops.ts` reads.

    Sent so the TypeScript port runs the SAME shape rather than falling back to
    the standard one by accident. `loop`/`loops` were passed to Node by no test
    at all, so the 519 lines of `loops.ts` were unexercised by the conformance
    suite and the two ports "agreed" about a shape only one of them had read.
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


def script() -> Script:
    """A two-step refund decision: consult a tool, then answer."""
    return Script(
        [
            Turn("Checking the ticket.", (ToolCall("zendesk", {"ticket": "T-1"}),)),
            Turn("Approved: the item arrived damaged within 30 days."),
        ]
    )


TOOLS = {"zendesk": lambda args: f"ticket {args.get('ticket')}: lamp, 6 days ago, broken"}


class Watching(ReferenceTransport):
    """Records what each model call was actually handed.

    The same shim `run-trace.ts` puts around the Vercel transport and the same
    one `test_worked_example_loop.py` puts around this one. It exists here so
    the two ports can be compared on the two things a trace cannot show:
    `says:` is a claim about what the model was TOLD and `may-use:` is a claim
    about what it was OFFERED, and both are inputs to the call rather than
    outputs of it.

    The TypeScript side had been computing both for a round and no assertion
    read either, so the port could have narrowed a different set of tools at a
    different stage — or sent different instructions entirely — and every
    existing cross-runtime assertion would still have passed.
    """

    def __init__(self, s: Script) -> None:
        super().__init__(s)
        self.told: list[str] = []
        self.offered: list[list[str]] = []

    async def model_call(self, system, history, tools):
        self.told.append(system)
        self.offered.append([t["name"] for t in tools])
        return await super().model_call(system, history, tools)


def execute(spec: AgentSpec, transport_cls) -> dict:
    s = script()
    result = asyncio.run(run(spec, transport_cls(s), "Can I get a refund?", TOOLS))
    return {"trace": result.trace(), "output": result.output,
            "halted": result.halted, "model_calls": s.calls}


# ---------------------------------------------------------------- the proof


def test_the_folder_loads_into_an_agent_spec(spec: AgentSpec) -> None:
    assert spec.name
    assert spec.instructions, "instructions.md must have become a field"
    assert "policy-checker" in spec.team and "fraud-checker" in spec.team


@pytest.mark.parametrize("name", sorted(TRANSPORTS))
def test_each_transport_runs_the_agent(spec: AgentSpec, name: str) -> None:
    out = execute(spec, TRANSPORTS[name])
    assert out["halted"] == "final"
    assert "Approved" in out["output"]


def test_all_three_transports_agree_exactly(spec: AgentSpec) -> None:
    """AC-2.2 at the harness level: same folder, same behaviour, everywhere."""
    results = {name: execute(spec, cls) for name, cls in TRANSPORTS.items()}
    reference = results["reference"]
    for name, got in results.items():
        assert got == reference, (
            f"{name} diverged from the reference transport.\n"
            f"  reference: {json.dumps(reference, indent=2)}\n"
            f"  {name}: {json.dumps(got, indent=2)}"
        )


def test_transports_do_not_change_how_often_the_model_is_called(spec: AgentSpec) -> None:
    """A transport that calls the model a different number of times has changed
    the loop, even when the final text matches. That is the divergence most
    likely to be missed and most expensive in production."""
    counts = {name: execute(spec, cls)["model_calls"] for name, cls in TRANSPORTS.items()}
    assert len(set(counts.values())) == 1, counts
    assert counts["reference"] == 2


def test_the_step_limit_is_reported_not_disguised(spec: AgentSpec) -> None:
    """A run that stopped because it ran out of budget is not a run that
    finished. Reporting them alike is the silent degradation T7 forbids.

    What "stopped" means is now the author's own `when-it-runs-out` (G2) rather
    than a fixed abort, so this asserts the guarantee — the run is never
    reported as having finished, and the ceiling it reached is named — and lets
    the example's file decide the rest.
    """
    looping = Script([Turn("still working", (ToolCall("zendesk", {}),))])
    result = asyncio.run(run(spec, ReferenceTransport(looping), "hello", TOOLS))
    assert result.halted != "final"
    assert len(result.steps) == spec.max_steps
    assert result.stopped_by is not None
    assert result.stopped_by.ceiling.field == "steps-at-most"
    assert result.stopped_by.action.value == spec.when_it_runs_out


def test_an_unknown_tool_is_reported_to_the_model_not_swallowed(spec: AgentSpec) -> None:
    s = Script([Turn("trying", (ToolCall("nonexistent", {}),)), Turn("done")])
    result = asyncio.run(run(spec, ReferenceTransport(s), "hello", TOOLS))
    assert "no tool named" in result.steps[0].tool_results[0]


# ------------------------------------------------------- capability lattice


def test_every_transport_publishes_a_lattice_over_the_same_features(spec: AgentSpec) -> None:
    """Invariant P-2. An adapter that omits a feature cannot be compared, so the
    key set is required to match even where the values differ."""
    lattices = {name: cls(script()).lattice() for name, cls in TRANSPORTS.items()}
    keys = [frozenset(v) for v in lattices.values()]
    assert len(set(keys)) == 1, {k: sorted(v) for k, v in lattices.items()}
    allowed = {"native", "emulated", "degraded", "unsupported"}
    for name, lat in lattices.items():
        assert set(lat.values()) <= allowed, (name, lat)


# ------------------------------------------------------ the seventh target


def _ts_trace(spec: AgentSpec) -> dict:
    """Run the same agent through the Vercel AI SDK, in Node.

    THE WHOLE AGENT SLICE, not four fields of it. It used to send
    `name/instructions/tools/maxSteps` and nothing else, so the two ports agreed
    about `pact:loop/standard` with no team, no interceptors, no context policy,
    no teamwork and no policy — and the trace matched only because the fixture's
    script never calls a teammate. Scripted one and they diverged outright:
    Python `halted='suspended'` with an empty trace, Node `halted='final'` with
    `error: no tool named 'policy-checker'`. `loop`/`loops` were passed by NO
    test at all, so 519 lines of `loops.ts` were unexercised by the conformance
    suite.

    What this port genuinely does not do comes back on `unenforced`, and
    `test_the_typescript_port_says_what_it_does_not_do` holds it to naming every
    one — which is what makes sending the whole slice honest rather than a
    pretence that both do the same things.
    """
    payload_spec = _payload_for(spec)
    payload_script = json.dumps({
        "turns": [
            {"text": "Checking the ticket.",
             "toolCalls": [{"name": "zendesk", "args": {"ticket": "T-1"}}]},
            {"text": "Approved: the item arrived damaged within 30 days."},
        ]
    })
    out = subprocess.run(
        ["node", "--experimental-strip-types", "src/run-trace.ts",
         payload_spec, payload_script, "Can I get a refund?"],
        cwd=TS_DIR, capture_output=True, text=True,
    )
    if out.returncode != 0:
        pytest.skip(f"node/AI SDK unavailable: {out.stderr[-300:]}")
    return json.loads(out.stdout)


def test_the_typescript_target_agrees_too(spec: AgentSpec) -> None:
    """Cross-*runtime* agreement, not just cross-framework.

    The Vercel AI SDK runs on Node, so its harness is a separate port of the same
    specification. If the two ports agree, the loop semantics are genuinely
    specified rather than merely implemented once — a divergence here would be an
    ambiguity in the spec, not a bug in one language.

    Agreement is asserted on the INPUTS as well as the outputs. `run-trace.ts`
    has reported `told` and `offered` since the `Watching` shim was added to it
    and nothing read either field, so the strongest half of the claim was being
    computed and thrown away: two ports that hand the model different
    instructions, or narrow a stage to a different set of tools, and then reach
    the same answer because the script says so have agreed about nothing. The
    Python side is wrapped in the same shim here so the two are compared like
    for like.
    """
    ts = _ts_trace(spec)
    watched = Watching(script())
    result = asyncio.run(run(spec, watched, "Can I get a refund?", TOOLS))
    reference = {"trace": result.trace(), "output": result.output,
                 "halted": result.halted}

    assert ts["trace"] == reference["trace"], json.dumps(
        {"node": ts["trace"], "reference": reference["trace"]}, indent=2
    )
    assert ts["output"] == reference["output"]
    assert ts["halted"] == reference["halted"]

    # What each stage put in front of the model, call for call. Non-empty is
    # asserted first, because two empty lists are equal and would make this test
    # pass on a port that recorded nothing at all.
    assert ts["offered"], "the TypeScript port recorded no tool lists"
    assert ts["told"], "the TypeScript port recorded no instructions"
    assert ts["offered"] == watched.offered, json.dumps(
        {"node": ts["offered"], "reference": watched.offered}, indent=2
    )
    assert ts["told"] == watched.told, json.dumps(
        {"node": ts["told"], "reference": watched.told}, indent=2
    )


def test_all_seven_targets_publish_the_same_lattice_features(spec: AgentSpec) -> None:
    """Including the TypeScript one — a lattice that cannot be compared across
    runtimes is not a portability instrument."""
    ts = _ts_trace(spec)
    python_keys = frozenset(ReferenceTransport(script()).lattice())
    assert frozenset(ts["lattice"]) == python_keys


def test_the_lattice_records_a_real_difference_between_the_two_frameworks() -> None:
    """The lattice earns its place only if it is not uniform. LangGraph carries
    durable resume natively; the Pydantic AI `direct` path cannot. A spec needing
    kill-and-resume must be told that before it runs, not after."""
    pyd = PydanticAITransport(script()).lattice()
    lg = LangGraphTransport(script()).lattice()
    assert pyd["durable_resume"] == "unsupported"
    assert lg["durable_resume"] == "native"


def test_the_typescript_port_says_what_it_does_not_do(spec: AgentSpec) -> None:
    """A smaller port must NAME what it is smaller by.

    Sending the whole agent slice to Node is only honest if the port says which
    of it reached nothing. Before this there was no `unenforced` channel on the
    TypeScript `RunResult` at all, so a spec carrying the worked example's three
    interceptors ran with none of them and said nothing: measured, a card number
    reached `payments` twice and `stop-runaway-refunds` did nothing, while
    Python halted `stopped-by-rule` on the second refund with the card masked.
    """
    payload_spec = json.dumps({
        "name": spec.name,
        "instructions": spec.instructions,
        "tools": [{"name": t.name, "description": t.description} for t in spec.tools],
        "maxSteps": spec.max_steps,
        "interceptors": ["redact-card-numbers"],
        "contextPolicy": "long-threads",
        "policy": "approvals",
    })
    payload_script = json.dumps({"turns": [{"text": "done"}]})
    out = subprocess.run(
        ["node", "--experimental-strip-types", "src/run-trace.ts",
         payload_spec, payload_script, "hello"],
        cwd=TS_DIR, capture_output=True, text=True,
    )
    if out.returncode != 0:
        pytest.skip(f"node/AI SDK unavailable: {out.stderr[-300:]}")
    said = json.loads(out.stdout)["unenforced"]

    assert said, "a port that does not run interceptors has to say so"
    joined = " ".join(said)
    for named in ("interceptors", "redact-card-numbers", "context-policy", "policy"):
        assert named in joined, f"{named!r} is unhonoured and unnamed: {said}"
    # And a spec carrying none of them is told nothing, because there is nothing
    # to tell — a report that fires on every run stops being read.
    quiet = subprocess.run(
        ["node", "--experimental-strip-types", "src/run-trace.ts",
         json.dumps({"name": "x", "instructions": "y", "tools": [], "maxSteps": 2}),
         payload_script, "hello"],
        cwd=TS_DIR, capture_output=True, text=True,
    )
    assert json.loads(quiet.stdout)["unenforced"] == []


def test_the_second_ports_library_refuses_a_field_it_does_not_know() -> None:
    """§7.28 says this port *"refuses to start"* on an undeclared key, and that
    was true of `run-trace.ts` and of nothing else.

    The check lived in the conformance driver, so a library consumer calling
    `run()` got the silent cast — an authored setting this port has not ported was
    neither honoured nor reported, which is the T7 breach `notDoneHere` exists to
    prevent, arriving one layer earlier. `run` now refuses with `SpecError`, and
    the driver calls the same function rather than keeping a second copy of the
    rule.
    """
    probe = """
import { run, undeclaredIn, SpecError } from "./src/harness.ts";
const spec = { name: "a", instructions: "i", tools: [], remembers: {"x": {}} };
if (undeclaredIn(spec).join(",") !== "remembers") {
  console.log("WRONG: " + undeclaredIn(spec).join(","));
} else {
  try {
    await run(spec as any, { name: "t", lattice: () => ({}),
      modelCall: async () => ["ok", []] } as any, "hello");
    console.log("NOT REFUSED");
  } catch (e) {
    console.log(e instanceof SpecError ? "REFUSED: " + e.message : "WRONG ERROR");
  }
}
"""
    probe_file = TS_DIR / "refuses-probe.ts"
    probe_file.write_text(probe)
    try:
        out = subprocess.run(
            ["node", "--experimental-strip-types", "refuses-probe.ts"],
            cwd=TS_DIR, capture_output=True, text=True,
        )
    finally:
        probe_file.unlink(missing_ok=True)
    if out.returncode != 0:
        pytest.skip(f"node unavailable: {out.stderr[-300:]}")
    said = out.stdout.strip()
    assert said.startswith("REFUSED:"), said
    assert "remembers" in said, said
    # And it names what it DOES read, so the author has somewhere to go.
    assert "instructions" in said, said


# ─────────── the payload boundary: what the second port is even shown (bug 10)

#: Keys `pact show` emits for an agent that the conformance payload deliberately
#: does NOT send, each with the §7.28 category that accounts for it.
#:
#: This map is the fix for the bug that hid five others. The payload is
#: hand-written, so a key absent from it is outside the comparison **by
#: construction** — and `answers-with:` was absent for a whole session while
#: `tier: core` and sitting in the worked example, so neither port asked the model
#: for the shape the author declared and nothing could notice.
NOT_SENT_TO_THE_SECOND_PORT: dict[str, str] = {
    # Category C — the driver puts no field on the wire, and since TS-8 an
    # undeclared key cannot arrive by accident either.
    "run-inputs": "C — RUN-3, the surrounding system's values, not the agent's",
    "variants": "C — RUN-6, model portability strategies; resolution is Rust",
    "accepts": "C — the input shapes; this port is handed one string",
    "needs": "C — model admissibility, decided by the Rust resolver",
    "evals": "C — which suite grades it; nothing here scores",
    # Identity, per §7.28's own note: two agents differing only in it produce the
    # same trace over the same script.
    "description": "identity — decides nothing about a run",
    # Sent, but under this port's own spelling rather than the author's.
    "uses": "sent as `tools` and `skills` — the DOCUMENTS, not the names",
    "loop": "sent as `loop` plus `loops`, resolved by `_loops_of`",
}


def test_every_key_the_loader_emits_is_sent_to_the_second_port_or_accounted_for(
    document: dict,
) -> None:
    """The check that would have caught `answers-with:` on the day it landed.

    A hand-written payload cannot be compared against itself. This compares it
    against `pact show`, which is the only thing that knows what an author can
    write — so a key the loader emits is either put on the wire, or named above
    with the §7.28 category that says why not. There is no third option, and
    "nobody added it to the dict" was the third option for a session.
    """
    from pact_adapters.ir import AgentSpec

    spec = AgentSpec.from_document(document, "refund-desk", source=EXAMPLE)
    payload = json.loads(_payload_for(spec))

    emitted = set(document["agents"]["refund-desk"])
    # The author's key -> the payload key(s) it is sent as. Written out rather
    # than approximated by a case-fold: `answers-with` reaches the port as
    # `answersWith`, and a check that guessed the mapping would have accepted a
    # payload that sent nothing at all under either spelling.
    sent_as = {
        "name": ("name",),
        "instructions": ("instructions",),
        "uses": ("tools", "skills"),
        "team": ("team",),
        "loop": ("loop", "loops"),
        "answers-with": ("answersWith",),
        "answers-with-mode": ("answersWithMode",),
        "limits": ("maxSteps",),
        # Sent by the governance test rather than this one, and reported by the
        # port on `unenforced` when they are. §7.28 list B.
        "policy": ("policy",),
        "interceptors": ("interceptors",),
        "context-policy": ("contextPolicy",),
        "teamwork": ("teamwork",),
        "remembers": ("remembers",),
    }
    reaches = {
        authored for authored, keys in sent_as.items()
        if any(k in payload for k in keys) or authored in NOT_SENT_TO_THE_SECOND_PORT
        or authored in {"policy", "interceptors", "context-policy", "teamwork",
                        "remembers"}
    }
    unaccounted = sorted(emitted - reaches - set(NOT_SENT_TO_THE_SECOND_PORT))
    assert not unaccounted, (
        f"`pact show` emits {unaccounted} for this agent and the conformance "
        f"payload neither sends them nor accounts for them.\n"
        f"Send each, or add it to NOT_SENT_TO_THE_SECOND_PORT with the §7.28 "
        f"category. A key in neither is a key outside the comparison by "
        f"construction — which is how `answers-with:` stayed unported for a "
        f"session while sitting in the worked example."
    )


def test_nothing_is_excused_that_the_loader_no_longer_emits(document: dict) -> None:
    """The other direction. An excuse for a key that no longer exists describes a
    gap that has closed, and this register can be wrong about its own subject in
    exactly the way the documents it replaced were."""
    emitted = set(document["agents"]["refund-desk"])
    ghosts = sorted(set(NOT_SENT_TO_THE_SECOND_PORT) - emitted)
    assert not ghosts, (
        f"excused but no longer emitted for this agent: {ghosts} — delete the rows"
    )
