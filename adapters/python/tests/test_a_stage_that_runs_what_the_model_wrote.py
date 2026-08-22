"""CodeAct: a stage where the model writes the code and the room runs it (P8/8).

`docs/30-FRD.md` FR-6.1.5 requires six loop patterns and names CodeAct among
them; AC-5.2 repeats it. It has never been shippable, for a reason that was
correct: there was nowhere to run anything. R16 separately refuses *orchestration
code the model writes while it runs* — Eve's fan-out tool — because it "cannot be
reviewed before it runs, cannot be diffed, cannot be signed, and is not the same
twice", and D22/D23 require structural change to pass a person first.

**This is not that, and the difference is authority.** R16's subject is code that
decides TOPOLOGY: which agents exist, who is asked, what the shape of the run is.
A CodeAct snippet has none of that. It is an ACTION inside one step — the same
standing as a tool call the model asked for — and it:

  * runs in the locked room, under the sandbox's deny-by-default egress and the
    stage's own fuel, so it can reach nothing the author did not grant;
  * has no structural authority whatsoever: it cannot add an agent, edit the
    tree, change a limit, or reach a teammate;
  * lands in the transcript verbatim, so what it did is reviewable AFTER the
    fact exactly as every other model output is — which is the standard the
    model's own prose already meets, not a lower one.

The line R16 draws is `meta-depth = 1` (AD-83): no run-created thing holds
topology-authoring authority. A snippet that computes a number holds none.

It is expert tier and excluded from the `no-code` badge, and it requires a
sandbox at check time — a `does: run-code` stage in a workspace with no locked
room is refused before anything runs, rather than discovered on the first step.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.loops import Does, Loop  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

CODEACT = {
    "resources": {
        "local-sandbox": {
            "resource-kind": "sandbox",
            "description": "The machine-local executor.",
            "engines": ["python"],
        }
    },
    "loops": {
        "works-it-out": {
            "description": "Write the working, run it, then answer.",
            "starts-at": "work",
            "steps": {
                "work": {"does": "run-code", "then": {"answered": "reply"}},
                "reply": {"does": "answer", "then": {"answered": "done"}},
            },
        }
    },
    "agents": {
        "desk": {
            "description": "Works out refund arithmetic.",
            "instructions": "Write the working out as code, then give the answer.",
            "loop": "works-it-out",
            "limits": {"steps-at-most": 4, "when-it-runs-out": "stop-and-say-so"},
        }
    },
}


def _script() -> Script:
    return Script([
        Turn("total = 40.00 + 5.00\nprint(total)"),
        Turn("The refund is 45.00 USD."),
    ])


def _run(**kw):
    return asyncio.run(
        run(AgentSpec.from_document(CODEACT, "desk"), ReferenceTransport(_script()),
            "how much do we refund?", {}, **kw)
    )


# ──────────────────────────────────────────────────────────── the stage exists


def test_run_code_is_a_stage_kind() -> None:
    assert Does.RUN_CODE.value == "run-code"
    loop = Loop.from_mapping("works-it-out", CODEACT["loops"]["works-it-out"])
    assert loop.steps["work"].does is Does.RUN_CODE


def test_what_the_model_wrote_is_run_and_the_answer_comes_back() -> None:
    """The snippet goes to the locked room and its output is the step's result."""
    seen: list[str] = []

    def sandbox(name: str, args: dict) -> str:
        seen.append(args["code"])
        return "45.0"

    result = _run(run_program=sandbox)
    assert seen and "40.00 + 5.00" in seen[0]
    assert result.steps[0].tool_results == ("45.0",)


def test_the_snippet_is_in_the_transcript_verbatim() -> None:
    """Reviewable after the fact, exactly as the model's prose already is.

    R16's objection to model-written code is that it cannot be reviewed, diffed
    or signed. That is true of code which decides TOPOLOGY and unwritten
    anywhere; a snippet that lands in the transcript is as readable as the
    sentence beside it.
    """
    result = _run(run_program=lambda n, a: "45.0")
    assert "40.00 + 5.00" in json.dumps(result.trace())


# ───────────────────────────────────────────────── it holds no other authority


def test_a_snippet_reaches_no_tool_and_no_teammate() -> None:
    """The whole safety argument in one assertion.

    A CodeAct stage offers the model NOTHING but the room — no tools, no
    teammates — so a snippet cannot call a gated action, spend money, or ask an
    agent. It computes and answers.
    """
    offered: list[list[str]] = []

    class Watching(ReferenceTransport):
        async def model_call(self, system, history, tools):
            offered.append([t["name"] for t in tools])
            return await super().model_call(system, history, tools)

    asyncio.run(
        run(AgentSpec.from_document(CODEACT, "desk"), Watching(_script()),
            "how much?", {}, run_program=lambda n, a: "45.0")
    )
    assert offered[0] == [], f"a run-code stage offers nothing else: {offered[0]}"


# ────────────────────────────────────────────────────────── the honest absence


def test_a_run_code_stage_with_no_room_says_so() -> None:
    """Refused rather than quietly turning into a `think` stage."""
    result = _run()
    said = " ".join(result.unenforced) + str(result.output)
    assert "run-code" in said or "locked room" in said


# ────────────────────────────────── what a snippet says, and what the room says


#: The same desk with the workspace's one redaction file beside it. `hide:` is
#: the workspace-wide spelling of the same act an interceptor's `rules:` writes,
#: and its own promise is *"what must never leave this workspace"*.
def _guarded() -> dict:
    doc = {k: dict(v) if isinstance(v, dict) else v for k, v in CODEACT.items()}
    doc["redaction"] = {
        "description": "Never let a card number out.",
        "hide": ["anything that looks like a card number"],
    }
    return doc


def _run_guarded(script: Script, **kw):
    return asyncio.run(
        run(AgentSpec.from_document(_guarded(), "desk"), ReferenceTransport(script),
            "how much do we refund?", {}, **kw)
    )


def test_what_the_room_printed_meets_the_rules_like_any_other_result() -> None:
    """A locked room's output is a tool result, and it leaves by the same door.

    The tool path already makes this argument in its own comment: what a tool
    handed back "goes into `history` and is read back to the model on the next
    turn, so an unmasked one leaves by the same door as anything else". A
    snippet's output is the same thing — it is metered as a tool call and it is
    appended to `history` — and it was the one result in this harness that no
    rule ever saw.
    """
    result = _run_guarded(
        Script([Turn("print(look_up())"), Turn("Done.")]),
        run_program=lambda name, args: "the card on file is 4111111111111111",
    )
    said = json.dumps(result.trace()) + " ".join(s.text for s in result.steps)
    assert "4111111111111111" not in said, said


def test_what_the_model_wrote_meets_the_rules_too() -> None:
    """The snippet itself is words the model produced, and they go into
    `history` unchanged. A card number typed into a comment is the same leak by a
    shorter route."""
    result = _run_guarded(
        Script([Turn("# refund the card 4111111111111111\nprint(45)"), Turn("Done.")]),
        run_program=lambda name, args: "45",
    )
    said = json.dumps(result.trace()) + " ".join(s.text for s in result.steps)
    assert "4111111111111111" not in said, said


def test_a_rule_can_stop_a_run_on_what_the_model_wrote() -> None:
    """A snippet is words the model produced, so the rule that stops on words
    stops on it.

    `stop and say "..."` is offered at `step.message.after` and
    `turn.message.after` and at no other moment — so it reaches what the model
    WROTE and deliberately not what the room printed. That boundary is the
    schema's, held where an author can read it: nothing in the closed vocabulary
    ends a run on a tool result, and a rule that claimed to would be refused when
    the file was read.
    """
    doc = _guarded()
    doc["interceptors"] = {
        "no-secrets": {
            "description": "Stops the run if the working mentions a password.",
            "when": "step.message.after",
            "may": ["stop-the-run"],
            "rules": ['if the answer mentions "password", stop and say "not done here"'],
        }
    }
    doc["agents"]["desk"] = {**doc["agents"]["desk"], "interceptors": ["no-secrets"]}
    result = asyncio.run(
        run(AgentSpec.from_document(doc, "desk"),
            ReferenceTransport(Script([Turn("print(password)"), Turn("Done.")])),
            "how much do we refund?", {},
            run_program=lambda name, args: "45")
    )
    assert result.halted == "stopped-by-rule", result.halted
    assert "not done here" in (result.output or ""), result.output


def test_a_workspace_with_no_rules_is_unchanged_by_any_of_this() -> None:
    """Additive inertness. The control every assertion above depends on."""
    plain = _run(run_program=lambda name, args: "45.0")
    assert plain.steps[0].tool_results == ("45.0",)
    assert "40.00 + 5.00" in plain.steps[0].text


# ─────────────────────────── what is recorded, and what is actually run


def test_the_room_runs_what_the_model_wrote_not_what_the_transcript_shows() -> None:
    """Masking decides what is WRITTEN DOWN, never what runs.

    Routing the snippet through the chain closed a real leak — a card number
    typed into a comment reached `history` unmasked — and opened a worse one by
    handing the room the masked text. The card pattern is `(?:\\d[ -]*?){12,}\\d`
    and deliberately over-matches, which is right for prose and destructive for
    code: measured, `order_id = 9780306406157` became `order_id = [removed]` and
    the room raised `NameError`. Under the SHIPPED redaction file it is worse
    still, because the bank-account pattern contains `\\b\\d{8}\\b` — so any
    eight-digit literal, an order id or a date-as-int, was destroyed.

    And it does not always fail loudly: `print(len("9780306406157"))` becomes
    `print(len("[removed]"))`, the step result is `9`, and the model answers from
    it. A control quietly doing something other than what it says is the shape T7
    forbids.

    This file already draws the distinction two hundred lines away, about a tool's
    arguments: *"Rewriting `call` decides what is WRITTEN DOWN, never what runs."*
    """
    got: list[str] = []
    result = _run_guarded(
        Script([Turn('order_id = 9780306406157\nprint(order_id)'), Turn("Done.")]),
        run_program=lambda name, args: got.append(args["code"]) or "9780306406157",
    )
    assert got and got[0] == "order_id = 9780306406157\nprint(order_id)", got

    # And nothing unmasked was recorded: the transcript shows the masked form,
    # and the room's OUTPUT is masked too, so the model reads `[removed]`.
    said = json.dumps(result.trace()) + " ".join(s.text for s in result.steps)
    assert "9780306406157" not in said, said


def test_a_snippet_the_rules_changed_is_said_out_loud() -> None:
    """The transcript and the room saw different text, so somebody is told.

    Whichever way round it is, a reader of the trace is looking at something
    other than what ran, and silence about that is the thing this whole file
    exists to prevent.
    """
    result = _run_guarded(
        Script([Turn('order_id = 9780306406157\nprint(order_id)'), Turn("Done.")]),
        run_program=lambda name, args: "9780306406157",
    )
    said = " ".join(result.unenforced)
    assert "writes code to be run" in said, result.unenforced
    assert "hiding rule changed it" in said, result.unenforced
    assert "do not match" in said, result.unenforced


def test_where_the_room_may_reach_outside_the_masked_snippet_is_what_runs() -> None:
    """The one case where the caution goes the other way.

    Handing the room the verbatim text is sound only while the room is inside the
    boundary. `allow-egress: programs` says it is not — the author has granted a
    carried body the outside world — and a verbatim snippet is then a real way
    out. There the masked text is what runs, and the cost is said out loud rather
    than paid in silence.
    """
    doc = _guarded()
    doc["allow-egress"] = ["programs"]
    got: list[str] = []
    result = asyncio.run(
        run(AgentSpec.from_document(doc, "desk"),
            ReferenceTransport(Script([Turn('x = 9780306406157\nprint(x)'), Turn("Done.")])),
            "how much do we refund?", {},
            run_program=lambda name, args: got.append(args["code"]) or "0")
    )
    assert got and "9780306406157" not in got[0], got
    said = " ".join(result.unenforced)
    assert "allow-egress" in said or "outside" in said, result.unenforced


def test_a_workspace_with_no_hiding_rules_hands_the_room_exactly_what_was_written() -> None:
    """The control. Nothing to mask, nothing to say, nothing changed."""
    got: list[str] = []
    result = _run(run_program=lambda name, args: got.append(args["code"]) or "45.0")
    assert got and got[0] == "total = 40.00 + 5.00\nprint(total)", got
    assert not any("hiding rule changed it" in u for u in result.unenforced), result.unenforced
