"""A program nothing here can run is named before the run, not during it (P7).

P6 landed the `program` kind: an agent may carry exact logic — date arithmetic,
a checksum — and reach it through a tool action whose tool `connect:`s to a
locked room. What P6 deliberately did not land is anything that RUNS one.

This is the seam, and it is the same seam the model and the tools already have.
`Transport` and `tool_impls` are both in `SUPPLIED_BY_THE_HOST`: nothing in
`src/` builds one, because building one is what a host does. A program runner is
that shape exactly — `mcp/calling.py` says the same thing in its own first line
about MCP clients, *"Nothing in `src/` calls it, and nothing should"*.

So this port does not bundle a WebAssembly engine. Fetching one would put a
network dependency in the core of a project whose D17 promise is that everything
runs air-gapped, and vendoring one would make the portable artifact carry a
runtime it cannot keep current. What ships instead is the plumbing, the metering,
and — the part that matters — the HONESTY:

    A workspace that declares programs and is run by a host with no runner must
    say so on `unenforced`, before the first call, naming what it could not do.

Without that a run reaches the first call and comes back `error: no tool named
…`, which reads as a typo in the author's own file and is not one. That is the
"silently degraded" failure T7 exists to prevent, on a capability whose whole
selling point is exactness.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

#: A desk whose one tool runs a carried program in a locked room. The shape P6
#: made authorable, as the fixture tree writes it.
CARRIES_A_PROGRAM = {
    "programs": {
        "check-window": {
            "description": "Works out whether a purchase is inside the refund window.",
            "engine": "wasm",
            "determinism": "pure",
            "takes": {"purchased-on": "text"},
            "answers-with": {"verdict": "one of inside, outside"},
            "fuel": {
                "instructions-at-most": "10m",
                "runs-for-at-most": "2s",
                "when-it-runs-out": "stop-and-say-so",
            },
        }
    },
    "resources": {
        "local-sandbox": {
            "resource-kind": "sandbox",
            "description": "The machine-local executor.",
            "engines": ["wasm"],
        }
    },
    "tools": {
        "refund-window": {
            "description": "Answers whether a purchase is inside the window.",
            "connect": "local-sandbox",
            "actions": {
                "check": {
                    "description": "Works out the window.",
                    "program": "check-window",
                    "takes": {"purchased-on": "text"},
                    "reads-only": "yes",
                }
            },
        }
    },
    "agents": {
        "desk": {
            "description": "Decides whether a refund is inside the window.",
            "instructions": "Use the tool for the date arithmetic.",
            "uses": ["refund-window"],
        }
    },
}

#: The same desk with no program anywhere — the inertness control.
PLAIN = {
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
            "description": "Decides refunds.",
            "instructions": "Read the ticket, then decide.",
            "uses": ["zendesk"],
        }
    },
}


def _script() -> Script:
    return Script([Turn("Checking the window.", (ToolCall("refund-window", {"purchased-on": "2026-01-05"}),)), Turn("Inside the window.")])


def _run(doc: dict, key: str, tools: dict | None = None, **kw):
    spec = AgentSpec.from_document(doc, key)
    return asyncio.run(
        run(spec, ReferenceTransport(_script()), "is this refundable?", tools or {}, **kw)
    )


# ────────────────────────────────────────────────────────── the honest absence


def test_a_declared_program_with_nothing_to_run_it_is_named_before_the_run() -> None:
    """The sentence a host with no runner owes the author.

    It names the program and what could not be done with it, because the failure
    an author meets otherwise is `error: no tool named 'refund-window'`, which
    reads as a mistake in their own file.
    """
    result = _run(CARRIES_A_PROGRAM, "desk")
    said = " ".join(result.unenforced)
    assert "check-window" in said, f"name the program: {result.unenforced}"
    assert "program" in said.lower()


def test_a_workspace_with_no_programs_is_told_nothing_about_them() -> None:
    """Additive inertness. A document that declares none must not gain a word."""
    result = _run(PLAIN, "desk", {"zendesk": lambda a: "ticket: lamp, 6 days ago"})
    assert not any("program" in u.lower() for u in result.unenforced), result.unenforced
    assert "program" not in json.dumps(result.trace())


def test_a_run_with_a_runner_says_nothing_about_it() -> None:
    """The other half: supply one and the sentence goes away.

    A report that fires whether or not the thing is missing is a report about
    nothing.

    What is asserted is the SENTENCE, not the program's name. It used to be the
    name, and that stopped meaning what it said once a second, unrelated sentence
    about the same program existed — the boundary line below, which is about a
    door the host holds and not about a missing runner. The name appearing proved
    nothing either way; this wording is the thing that must be gone.
    """
    result = _run(
        CARRIES_A_PROGRAM,
        "desk",
        {"refund-window": lambda a: "inside"},
        run_program=lambda name, args: "inside",
    )
    assert not any("nothing here can run" in u for u in result.unenforced), result.unenforced

    # The positive control the assertion above is worthless without: take the
    # runner away and that exact wording comes back.
    without = _run(CARRIES_A_PROGRAM, "desk")
    assert any("nothing here can run" in u for u in without.unenforced), without.unenforced


# ───────────────────────────────────────────────────────────── the seam itself


def test_the_runner_is_declared_host_supplied() -> None:
    """A new `run()` parameter must be in one of the two registers.

    `DERIVED_FROM_THE_DOCUMENT` or `SUPPLIED_BY_THE_HOST` — the boundary between
    what a document says and what a run is given is declared rather than
    remembered, and the suite fails on a parameter in neither.
    """
    from pact_adapters.harness import DERIVED_FROM_THE_DOCUMENT, SUPPLIED_BY_THE_HOST

    assert "run_program" in SUPPLIED_BY_THE_HOST
    assert "run_program" not in DERIVED_FROM_THE_DOCUMENT


def test_a_program_call_is_a_tool_call_in_the_trace() -> None:
    """It is metered like every other call, and it looks like one.

    A program reached through an action is a tool call: it counts against
    `tool-calls-at-most`, it appears in the trace, and two transports agree about
    it — which is what keeps the portability claim covering it rather than
    acquiring an exception.
    """
    result = _run(
        CARRIES_A_PROGRAM,
        "desk",
        {"refund-window": lambda a: "inside"},
        run_program=lambda name, args: "inside",
    )
    calls = [c for step in result.trace() for c in step["tools"]]
    assert any(c["name"] == "refund-window" for c in calls), result.trace()
    assert result.steps[0].tool_results == ("inside",)


# ─────────────────────────────────── the eighth word of the boundary (P6/audit)


#: The same desk, with the workspace's boundary line written out. `[]` is what
#: both shipped program trees say, and what the schema's own sentence describes:
#: "without it a program runs in a room with the door shut."
def _with_egress(granted: list[str]) -> dict:
    doc = dict(CARRIES_A_PROGRAM)
    doc["allow-egress"] = granted
    return doc


def test_a_program_carries_whether_its_workspace_let_it_talk_outside() -> None:
    """The word has to reach the host, or it is decoration.

    `allow-egress:` gained `programs` as its eighth part, and the commit that
    added it said "a carried program has no network unless that line says so,
    which is the state a reviewer should be able to assume by reading nothing".
    Nothing established that state: no check read the word, no run reported it,
    and `ProgramSpec` — the only thing a host is handed about a program — did not
    carry it. A choice a non-coder can type and nothing can exercise reads as a
    capability, which is worse than an absent one.

    PACT declares the locked room and the host supplies it, exactly as it does
    for a model and for a tool, so PACT cannot itself hold the door shut. What it
    can do, and now does, is hand the host the author's own answer.
    """
    withheld = AgentSpec.from_document(_with_egress([]), "desk")
    assert withheld.programs, "the fixture carries one"
    assert withheld.programs[0].may_reach_outside is False

    granted = AgentSpec.from_document(_with_egress(["programs"]), "desk")
    assert granted.programs[0].may_reach_outside is True


def test_a_workspace_that_withheld_the_grant_is_told_pact_cannot_hold_the_door() -> None:
    """R30's principle, on the newest part of the boundary.

    "`allow-egress: []` is a sentence a person approved, and a check that passes
    under it turns that approval into decoration." PACT cannot open the body and
    cannot watch the room, so the honest report is not silence and not a refusal
    — it is the one sentence saying what this run is trusting the host for.
    """
    result = _run(
        _with_egress([]),
        "desk",
        {"refund-window": lambda a: "inside"},
        run_program=lambda name, args: "inside",
    )
    said = " ".join(result.unenforced)
    assert "allow-egress" in said, result.unenforced
    assert "check-window" in said or "carried program" in said, result.unenforced


def test_a_workspace_that_granted_it_is_told_that_it_did() -> None:
    """The other half, and it used to be silence.

    This test asserted that granting `programs` said nothing, on the argument
    that a report firing either way is a report about nothing. That argument was
    wrong here, and the shape of the wrongness is the tell: it made the SAFER
    arrangement the noisy one, and gave the reviewer nothing at all on the one
    line they most want to see — that a carried body has been allowed out of the
    box. A grant is not the absence of a refusal.

    So there is a line either way, and each says the thing that is true of that
    arrangement: what PACT cannot check when the door is shut, and what has been
    allowed when it is open.
    """
    result = _run(
        _with_egress(["programs"]),
        "desk",
        {"refund-window": lambda a: "inside"},
        run_program=lambda name, args: "inside",
    )
    said = " ".join(result.unenforced)
    assert "allow-egress" in said, result.unenforced
    assert "reach outside" in said, result.unenforced
    assert "does not name" not in said, "that is the other arrangement's sentence"


def test_a_workspace_with_no_runner_is_not_told_twice() -> None:
    """A host with nothing to start a program is already told the bigger thing.

    Adding "and PACT cannot check the door" beside "nothing here can run one at
    all" would be two sentences about one absence, and the second is only
    interesting once something really runs.
    """
    result = _run(_with_egress([]), "desk")
    assert not any("allow-egress" in u for u in result.unenforced), result.unenforced


# ───────────────────────── the doors a run really starts a program through


#: A desk whose loop is routed by a carried program, and whose question is
#: checked by one. Neither has a tool anywhere near it.
NO_TOOL_IN_SIGHT = {
    "programs": {
        "pick-next": {
            "description": "Says which stage to go to next.",
            "engine": "wasm",
            "determinism": "pure",
            "takes": {"said": "text"},
            "answers-with": {"next": "text"},
            "fuel": {"instructions-at-most": "10m", "when-it-runs-out": "stop-and-say-so"},
        },
        "within-the-ceiling": {
            "description": "Says whether an amount is one this desk may give.",
            "engine": "wasm",
            "determinism": "pure",
            "takes": {"amount": "money"},
            "answers-with": {"verdict": "text"},
            "fuel": {"instructions-at-most": "10m", "when-it-runs-out": "stop-and-say-so"},
        },
    },
    "questions": {
        "how-much": {
            "description": "Asks a person how much to give back.",
            "says": "How much should we refund?",
            "answer": {"amount": "money"},
            "asked-of": ["the refunds team"],
            "if-nobody-answers": "stop-and-say-so",
            "checked-by": "within-the-ceiling",
        }
    },
    "loops": {
        "works-it-out": {
            "description": "Answer, and let a program say where to go next.",
            "starts-at": "reply",
            "steps": {
                "reply": {
                    "does": "answer",
                    "then": {
                        "answered": "done",
                        "decided-by": "pick-next",
                        "may-go-to": ["done"],
                    },
                }
            },
        }
    },
    "agents": {
        "desk": {
            "description": "Answers customers.",
            "instructions": "Answer the question.",
            "loop": "works-it-out",
            "limits": {"asks": "how-much", "when-it-runs-out": "stop-and-say-so"},
        }
    },
}


def test_a_program_that_routes_the_loop_is_one_the_run_knows_about() -> None:
    """`ProgramSpec` is the only thing a host is ever handed about a program.

    It was built from two doors — a tool's action, and `uses:` — so a program
    reached by `decided-by:` or `checked-by:` produced no spec at all. A host
    with no runner was never told it could not route the loop, and the
    `allow-egress:` answer that P8 made real never reached the room that would
    run it.
    """
    spec = AgentSpec.from_document(NO_TOOL_IN_SIGHT, "desk")
    named = {p.name for p in spec.programs}
    assert "pick-next" in named, named
    assert "within-the-ceiling" in named, named


def test_a_run_with_no_runner_names_them_before_it_starts() -> None:
    """And says which door each was reached through, so the author knows where
    to look."""
    result = _run(NO_TOOL_IN_SIGHT, "desk")
    said = " ".join(result.unenforced)
    assert "pick-next" in said, result.unenforced
    assert "within-the-ceiling" in said, result.unenforced


def test_the_grant_reaches_a_program_reached_without_a_tool() -> None:
    """The whole of what `allow-egress: programs` delivers is this field."""
    doc = dict(NO_TOOL_IN_SIGHT)
    doc["allow-egress"] = ["programs"]
    spec = AgentSpec.from_document(doc, "desk")
    assert all(p.may_reach_outside for p in spec.programs), spec.programs
