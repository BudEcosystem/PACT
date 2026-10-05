"""What a tool IS, at the boundary between the reference port and the second one.

The payload the conformance driver sends carries a tool as two strings — a name
and a sentence. `ToolSpec` has six fields, so four were dropped at the wall, and
each dropping cost something different:

* **`parameters`** — the second port offers every tool with `parameters: {}`, so
  the model is told a tool exists and never what it takes. That is word for word
  the defect `_takes`' own docstring records and fixes on the reference side:
  *"every tool in every workspace was offered with no arguments at all, and
  `inspects:`, `bind:` and `same-request-key:` all named arguments nothing
  declared."* Fixed there, live here, and reported nowhere.
* **`binds`** — the author's `bind:` lines, whose whole promise is that the model
  cannot see, name or change the argument. A port that never receives them
  cannot fill one, so *"whose order"* goes back to being something the model
  decides.
* **`remembers`** — `remember-as:`, which this port has no store for.
* **`reaches`** — where the call GOES, which this port has no client for.

The last two this port genuinely cannot do, and that is fine: it is a smaller
port, and being smaller is allowed. What is not allowed is being smaller in
silence. `notDoneHere`'s own docstring calls that the T7 breach it exists to
prevent — and it prevented it at the AGENT level, where `interceptors:`,
`policy:` and `team:` are named, while four fields one level down went past it.

A field the payload never sends is a field the second port cannot honour AND
cannot report, and the divergence then reads as a bug in the port rather than a
hole in the wall.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import fields as dataclass_fields
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.ir import AgentSpec, ToolSpec  # noqa: E402
from pact_adapters.ports import WIRE_NAME, tool_payload  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
TS_DIR = REPO / "adapters" / "typescript"

#: A desk whose one tool binds an argument and keeps what it answered — the two
#: lines this boundary was losing.
BINDS_AND_REMEMBERS = {
    "tools": {
        "orders": {
            "description": "Looks orders up.",
            "url": "https://orders.example.com",
            "method": "get",
            "actions": {
                "look-up": {
                    "description": "Finds an order.",
                    "takes": {"order-number": "text", "account": "text"},
                    "bind": {"account": "run-inputs.customer-id"},
                    "remember-as": "last-order-seen",
                    "reads-only": "yes",
                }
            },
        }
    },
    "agents": {
        "desk": {
            "description": "Answers questions about an order.",
            "instructions": "Look the order up and answer.",
            "uses": ["orders"],
            "run-inputs": {"customer-id": "text"},
            "remembers": {
                "last-order-seen": {
                    "description": "The last order this conversation looked at.",
                    "lasts": "one-conversation",
                    "forget-after": "1d",
                }
            },
        }
    },
}


# ─────────────────────────────────── the wall itself, held against the shape


#: Fields of `ToolSpec` the payload deliberately does not send, each with the
#: reason. Empty on purpose today — it is here so that a field added later is a
#: DECISION rather than a drop, exactly as `SUPPLIED_BY_THE_HOST` is for `run()`.
NOT_SENT: dict[str, str] = {}


def _a_tool_with_everything() -> ToolSpec:
    """One tool with every field filled, so nothing looks excused by being empty."""
    from pact_adapters.ir import Reach

    return ToolSpec(
        name="orders",
        description="Looks orders up.",
        parameters={"order-number": "text"},
        binds={"look-up": {"account": "run-inputs.customer-id"}},
        remembers={"look-up": "last-order-seen"},
        answers_with={"look-up": {"status": "one of open, shipped"}},
        programs={"look-up": "shorten-order"},
        reaches=Reach(kind="url", value="https://orders.example.com", method="get"),
        available_when="this-agent-has-helpers",
        reads_only={"look-up": True},
    )


def test_every_field_a_tool_has_crosses_the_wall_or_is_excused() -> None:
    """The instrument the agent level has and the tool level did not.

    `test_the_loader_to_adapter_boundary_is_total` asks this of `AgentSpec`, one
    level out. Nothing asked it of `ToolSpec`, so four of its six fields were
    dropped by a projection hand-written in five test files — and a copy in five
    places is a rule in none of them.
    """
    # A tool carrying EVERY line, so a key the projection only writes when it has
    # something to say is still counted. A bare one would let three of them look
    # excused when they are simply empty.
    sent = set(tool_payload(_a_tool_with_everything()))
    declared = {f.name for f in dataclass_fields(ToolSpec)}
    # Through the declared correspondence, because the wire deliberately uses the
    # AUTHOR's words — `bind`, `remember-as` — rather than this port's field
    # names. A guard that guessed the mapping would be the same guess that let
    # four fields fall off the wall.
    missing = sorted(
        f for f in declared if WIRE_NAME.get(f, f) not in sent and f not in NOT_SENT
    )
    unmapped = sorted(f for f in declared if f not in WIRE_NAME and f not in NOT_SENT)
    assert not unmapped, (
        f"{unmapped} are on `ToolSpec` and `WIRE_NAME` has never heard of them.\n"
        "  fix: say which key on the wire carries each, or excuse them in `NOT_SENT`."
    )
    assert not missing, (
        f"{missing} are on `ToolSpec` and are not sent to the second port.\n"
        "  fix: add them to `tool_payload`, and to the second port's own tool "
        "shape so it can honour or report them — or put them in `NOT_SENT` with "
        "the reason no port could use them."
    )


def test_the_projection_is_one_function_and_not_five_copies() -> None:
    """The defect under the defect.

    Every caller of the driver wrote its own `[{"name": ..., "description": ...}]`
    line, so widening the wall meant finding five of them. One function, and the
    next field added to `ToolSpec` reaches every driver by existing.
    """
    corpus = "\n".join(
        p.read_text(encoding="utf-8")
        for p in (REPO / "adapters/python/tests").glob("test_*.py")
        if p.name != Path(__file__).name
    )
    assert '"description": t.description}' not in corpus, (
        "a hand-written tool projection is still in the suite — it will go stale "
        "the next time `ToolSpec` grows. Use `ports.tool_payload`."
    )


# ──────────────────────────────────── and what the second port does with it


def _through_the_second_port(spec: AgentSpec) -> dict:
    payload = json.dumps({
        "name": spec.name,
        "instructions": spec.instructions,
        "tools": [tool_payload(t) for t in spec.tools],
        "maxSteps": spec.max_steps,
    })
    out = subprocess.run(
        ["node", "--experimental-strip-types", "src/run-trace.ts",
         payload, json.dumps({"turns": [{"text": "done"}]}), "where is my order?",
         json.dumps({"orders": "order O-1: a lamp"})],
        cwd=TS_DIR, capture_output=True, text=True,
    )
    if out.returncode != 0:
        pytest.skip(f"node/AI SDK unavailable: {out.stderr[-300:]}")
    return json.loads(out.stdout)


def test_the_second_port_is_told_what_the_tool_takes() -> None:
    """The capability half. A model that is not told the arguments cannot fill
    them, and this port told it nothing at all."""
    spec = AgentSpec.from_document(BINDS_AND_REMEMBERS, "desk")
    got = _through_the_second_port(spec)
    offered = json.dumps(got.get("offered-shapes") or got.get("offered") or got)
    assert "order-number" in offered, (
        f"the tool's own `takes:` has to reach the model: {offered[:400]}"
    )


def test_the_second_port_says_what_it_cannot_do_with_a_bound_argument() -> None:
    """The honesty half. `bind:` promises the model cannot see, name or change
    an argument — a promise this port cannot keep, so it has to say so."""
    spec = AgentSpec.from_document(BINDS_AND_REMEMBERS, "desk")
    got = _through_the_second_port(spec)
    said = " ".join(got.get("unenforced") or [])
    assert "bind" in said, f"a bound argument is unhonoured and unnamed: {said}"
    assert "orders" in said, said


def test_the_second_port_says_what_it_cannot_remember() -> None:
    """`remember-as:` has no store on this runtime, which is allowed. Silence is
    not."""
    spec = AgentSpec.from_document(BINDS_AND_REMEMBERS, "desk")
    got = _through_the_second_port(spec)
    said = " ".join(got.get("unenforced") or [])
    assert "remember-as" in said, f"a declared memory is unhonoured and unnamed: {said}"


def test_a_tool_with_none_of_this_is_reported_about_none_of_it() -> None:
    """Additive inertness at the wall. The overwhelming majority of tools carry
    no `bind:` and no `remember-as:`, and must gain no sentence."""
    plain = {
        "tools": {
            "zendesk": {
                "description": "Reads a ticket.",
                "url": "https://tickets.example.com",
                "method": "get",
                "actions": {"read": {"description": "reads", "takes": {"id": "text"}}},
            }
        },
        "agents": {
            "desk": {
                "description": "Answers.",
                "instructions": "Read the ticket.",
                "uses": ["zendesk"],
            }
        },
    }
    got = _through_the_second_port(AgentSpec.from_document(plain, "desk"))
    said = " ".join(got.get("unenforced") or [])
    assert "bind" not in said, said
    assert "remember-as" not in said, said


def test_both_ports_say_the_same_thing_about_an_unchecked_return_type() -> None:
    """02P A4. Neither port's tools return typed values, so both name every
    action's `answers-with:` as unchecked — in the same words, because a reader
    comparing two runs should not find two opinions about one line."""
    import asyncio

    from pact_adapters.harness import run
    from pact_adapters.script import Script, Turn
    from pact_adapters.transports.mock import ReferenceTransport

    doc = json.loads(json.dumps(BINDS_AND_REMEMBERS))
    doc["tools"]["orders"]["actions"]["look-up"]["answers-with"] = {
        "status": "one of open, shipped"
    }
    spec = AgentSpec.from_document(doc, "desk")
    second = [s for s in _through_the_second_port(spec).get("unenforced") or []
              if s.startswith("answers-with:")]
    reference = asyncio.run(run(
        spec, ReferenceTransport(Script([Turn("done")])), "go", {},
        run_inputs={"customer-id": "c-1"},
    ))
    first = [s for s in reference.unenforced if s.startswith("answers-with:")]
    assert first and first == second, (first, second)
