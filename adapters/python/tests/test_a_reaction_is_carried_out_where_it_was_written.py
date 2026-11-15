"""Topics, events and reactions at run time (docs/99 §5).

The harness owns the loop, so "when this happens, do that" is a line of its own
code at each of six moments. What is held here:

- a tagged tool raises its topic exactly, and an agent that listens
  `asked-first` is asked BEFORE the call — the call is held, its answer comes
  back in the call's place, and the same call made again goes through;
- a held call is not put to a person in the same step, so nobody approves a
  call that then does not happen;
- what a run has already reacted to survives a park;
- a guess — a judgement, or the agent saying so itself — advises and never
  stops;
- a reaction being carried out does not fire again beneath itself;
- and what a runtime cannot do, it says.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import ToolCall, delegate_by_running, run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.reactions import MOMENTS, WORKING_ON, Reactions, judged_yes  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.suspension import Suspension  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]


def pact() -> str:
    built = [p for p in (ROOT / "target" / k / "pact" for k in ("debug", "release")) if p.exists()]
    return str(max(built, key=lambda p: p.stat().st_mtime))


#: The same workspace, written two ways (docs/99 §4): a folder of YAML, and one
#: PACT-language file.
AS_A_FOLDER = "kernel/finance-first"
AS_ONE_FILE = "language/finance-first/finance-first.pact"


def shipped(written: str = AS_A_FOLDER) -> dict[str, Any]:
    out = subprocess.run(
        [pact(), "show", str(ROOT / "examples" / written)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


class Listening(ReferenceTransport):
    """A scripted model that keeps the system text it was shown."""

    def __init__(self, script: Script) -> None:
        super().__init__(script)
        self.told: list[str] = []

    async def model_call(self, system, history, tools):  # type: ignore[override]
        self.told.append(system)
        self.offered = [t["name"] for t in tools]
        #: What was offered at each call, in order.
        self.offers = [*getattr(self, "offers", []), self.offered]
        return await super().model_call(system, history, tools)


def says(text: str):
    """A transport factory for members: every member answers `text`, and the
    order they were woken in is kept on `.woken`."""
    woken: list[tuple[str, str]] = []

    class Member(ReferenceTransport):
        def __init__(self, spec: AgentSpec) -> None:
            super().__init__(Script([Turn(text)]))
            self.who = spec.name

        async def model_call(self, system, history, tools):  # type: ignore[override]
            woken.append((self.who, str(history[0]["content"])))
            return await super().model_call(system, history, tools)

    def make(spec: AgentSpec) -> ReferenceTransport:
        return Member(spec)

    make.woken = woken  # type: ignore[attr-defined]
    return make


REFUND = ToolCall("billing", {"action": "issue-refund", "order": "A1", "amount": "40 USD"})
NO = lambda: ReferenceTransport(Script([Turn("no")]))  # noqa: E731


def tools(ran: list[dict[str, Any]]):
    def billing(args: dict[str, Any]) -> str:
        ran.append(dict(args))
        return "refunded 40 USD"

    return {"billing": billing, "orders": lambda args: "order A1: delivered"}


# ── the shipped example ──────────────────────────────────────────────────────


def test_the_moments_a_reaction_reaches_are_the_ones_the_schema_lists() -> None:
    schema = yaml.safe_load((ROOT / "spec" / "schema.yaml").read_text())["groups"]
    for group in ("event", "reaction"):
        assert tuple(schema[group]["fields"]["at"]["reaches"]) == MOMENTS, group


def test_a_subscription_is_a_reaction_written_from_the_other_side() -> None:
    doc = shipped()
    support = Reactions.from_document(doc, "support")
    by_name = {r.name: r for r in support.reactions}
    asked = by_name["finance-desk listens for finance"]
    assert asked.signal.kind == "topic" and [t.verb for t in asked.then] == ["consult"]
    assert not asked.every_time
    told = by_name["auditor listens for refund-issued"]
    assert told.signal.at == "step.tool.completed" and [t.verb for t in told.then] == ["tell"]
    assert told.every_time, "a record that hears only the first refund is wrong"
    # Nobody is woken by their own work.
    finance = Reactions.from_document(doc, "finance-desk")
    assert "finance-desk listens for finance" not in {r.name for r in finance.reactions}


def test_the_file_and_the_folder_are_one_document() -> None:
    assert shipped(AS_ONE_FILE) == shipped(AS_A_FOLDER)


@pytest.mark.parametrize("written", [AS_A_FOLDER, AS_ONE_FILE])
def test_the_finance_desk_is_asked_before_the_refund_and_the_auditor_told_after(written: str) -> None:
    """The whole path, from either way of writing it: `.pact` or YAML → `pact
    show` → `AgentSpec` → the harness."""
    doc = shipped(written)
    spec = AgentSpec.from_document(doc, "support")
    lead = Script([Turn("", (REFUND,)), Turn("", (REFUND,)), Turn("Refunded.")])
    members = says("A refund needs the order number and the reason.")
    ran: list[dict[str, Any]] = []

    first = asyncio.run(
        run(spec, ReferenceTransport(lead), "Please refund order A1.", tools(ran),
            ask_member=delegate_by_running(doc, members), checking_transport=NO())
    )
    # Step 0: the call was held, and what the finance desk said came back in
    # its place. Step 1: the same call again — and only NOW is a person asked.
    assert first.halted == "suspended", (first.halted, first.output)
    assert ran == [], "money moved before the finance desk or a person was heard"
    held = first.steps[0].tool_results[0]
    assert held.startswith("not done yet — finance-desk was asked first"), held
    assert "A refund needs the order number" in held
    assert [who for who, _ in members.woken] == ["finance-desk"]
    assert "about to call `billing` (issue-refund)" in members.woken[0][1]
    assert len(first.steps) == 1, "the person was asked about the call that was held"

    parked = Suspension.from_json(first.suspension.to_json())
    assert parked.reactions["fired"] == ["finance-desk listens for finance"]
    yes = parked.answer(**{a.name: "yes" for a in parked.asks})
    after = asyncio.run(
        run(spec, ReferenceTransport(lead), "Please refund order A1.", tools(ran),
            ask_member=delegate_by_running(doc, members), checking_transport=NO(),
            resume=parked, answer=yes, now=1.0)
    )
    assert after.halted == "final" and after.output == "Refunded."
    assert len(ran) == 1, "the refund went out once"
    assert [who for who, _ in members.woken] == ["finance-desk", "auditor"]
    assert "It answered:\n\nrefunded 40 USD" in members.woken[1][1]
    assert [(r["reaction"], r["did"]) for r in after.reactions] == [
        ("finance-desk listens for finance", ["asked finance-desk"]),
        ("auditor listens for refund-issued", ["told auditor"]),
    ]
    # `tell:`'s help says what the agent told answers "is written down with the
    # run". The model never sees it, so the run's own record is the only place
    # it can be — and it survives the park, with the finance desk's answer.
    assert [r["heard"] for r in after.reactions] == [
        [{"agent": "finance-desk", "how": "asked-first",
          "said": "A refund needs the order number and the reason."}],
        [{"agent": "auditor", "how": "told-after",
          "said": "A refund needs the order number and the reason."}],
    ]
    assert after.unenforced == ()


def test_the_agent_says_its_own_topic_and_gets_the_answer_back() -> None:
    doc = shipped()
    spec = AgentSpec.from_document(doc, "support")
    lead = Script([
        Turn("", (ToolCall(WORKING_ON, {"topic": "finance"}),)),
        Turn("VAT is not refunded on shipping."),
    ])
    members = says("VAT on shipping is not refundable.")
    listening = Listening(lead)
    out = asyncio.run(
        run(spec, listening, "Is the VAT on shipping refunded?", tools([]),
            ask_member=delegate_by_running(doc, members), checking_transport=NO())
    )
    # Offered until it has been used for the one topic there is, and not after.
    assert WORKING_ON in listening.offers[0] and WORKING_ON not in listening.offers[1]
    assert out.halted == "final", (out.halted, out.output)
    said = out.steps[0].tool_results[0]
    assert said.startswith("noted: finance"), said
    assert "finance-desk was asked first about this, and said: VAT on shipping" in said
    assert out.reactions[0]["certainty"] == "guess"
    # A subject that is not one of them is an error the model can read.
    wrong = asyncio.run(
        run(spec, ReferenceTransport(Script([
            Turn("", (ToolCall(WORKING_ON, {"topic": "the weather"}),)), Turn("ok")])),
            "hello", tools([]), ask_member=delegate_by_running(doc, members),
            checking_transport=NO())
    )
    assert wrong.steps[0].tool_results[0].startswith("error: 'the weather' is not one of")


def test_the_tool_an_agent_says_its_topic_with_is_written_as_every_tool_is() -> None:
    """Found by the first live run. The definition was a JSON schema; every
    transport builds its own from `{argument: shape in words}`, so a provider
    was sent a tool with three arguments called `type`, `properties` and
    `required`."""
    from pact_adapters.transports.anthropic_transport import AnthropicTransport
    from pact_adapters.transports.ollama_transport import OllamaTransport

    spec = AgentSpec.from_document(shipped(), "support")
    said_so = spec.reactions.tool()
    assert said_so["parameters"] == {"topic": "one of finance"}
    assert all(isinstance(shape, str) for shape in said_so["parameters"].values())
    # The name comes first and the description after it in brackets.
    assert "`finance` (Money moving" in said_so["description"]
    # And what a provider is sent: one argument, `topic`, a closed list.
    sent = OllamaTransport("m").payload_for("", [], [said_so])["tools"][0]["function"]
    assert sent["parameters"]["properties"] == {
        "topic": {"type": "string", "enum": ["finance"], "description": "one of finance"}
    }
    sent = AnthropicTransport(Script([])).request_for("", [], [said_so])["tools"][0]
    assert set(sent["input_schema"]["properties"]) == {"topic"}


def test_once_every_topic_has_been_said_the_tool_is_no_longer_offered() -> None:
    """Found by the first live run: told `noted: legal`, a model said it again
    — four times, until its steps ran out. A tool with nothing left to say can
    only be called again, so it is not offered."""
    spec = AgentSpec.from_document(shipped(), "support")
    says_it = ToolCall(WORKING_ON, {"topic": "finance"})
    lead = Script([Turn("", (says_it,)), Turn("", (says_it,)), Turn("Done.")])
    seen: list[list[str]] = []

    class Watching(ReferenceTransport):
        async def model_call(self, system, history, tools):  # type: ignore[override]
            seen.append([t["name"] for t in tools])
            return await super().model_call(system, history, tools)

    out = asyncio.run(run(spec, Watching(lead), "A question about a refund.", tools([]), checking_transport=NO()))
    assert WORKING_ON in seen[0], seen
    assert all(WORKING_ON not in offered for offered in seen[1:]), seen
    # Saying it a second time, with the tool gone, is a call to nothing — and
    # is told so, as any call to a tool that is not offered is.
    assert out.steps[0].tool_results[0].startswith("noted: finance"), out.steps[0].tool_results
    assert out.reactor.state()["said"] == ["finance"]


def test_saying_the_topic_first_does_not_spend_the_guard_on_the_call() -> None:
    """A guess does not spend what is exact. `finance` is `noticed-by: [tags,
    the-agent]`: the agent may say it, and the billing tool is tagged with it.
    An agent that said it on its first step had the finance desk asked about
    nothing in particular — and the tagged call that came later was then not
    held at all, because once-a-run had been spent on the guess."""
    doc = shipped()
    spec = AgentSpec.from_document(doc, "support")
    lead = Script([
        Turn("", (ToolCall(WORKING_ON, {"topic": "finance"}),)),
        Turn("", (REFUND,)),
        Turn("", (REFUND,)),
        Turn("Refunded."),
    ])
    members = says("A refund needs the order number and the reason.")
    ran: list[dict[str, Any]] = []
    first = asyncio.run(
        run(spec, ReferenceTransport(lead), "Please refund order A1.", tools(ran),
            ask_member=delegate_by_running(doc, members), checking_transport=NO())
    )
    # Step 0: said, and the finance desk asked — a guess. Step 1: the refund
    # call is STILL held and the desk asked again, about this call. Step 2: the
    # same call, and only now is a person asked.
    assert first.halted == "suspended", (first.halted, first.output)
    assert ran == [], "money moved without the call itself being held"
    assert first.steps[0].tool_results[0].startswith("noted: finance")
    assert first.steps[1].tool_results[0].startswith("not done yet — finance-desk was asked first")
    assert [who for who, _ in members.woken] == ["finance-desk", "finance-desk"]
    assert "about to call `billing` (issue-refund)" in members.woken[1][1]
    assert [r["certainty"] for r in first.reactor.log] == ["guess", "exact"]
    # And a second guess after either is not due: said once, asked once for it.
    state = first.reactor.state()
    assert state["fired"] == state["sure"] == ["finance-desk listens for finance"]


def test_an_agent_a_reaction_woke_is_not_asked_what_the_work_has_turned_to() -> None:
    """Found by a live run, once a woken agent's own lines reached the run that
    woke it: the auditor, told a refund had gone out, said `finance`, and the
    finance desk was to be consulted by an agent with nobody it can ask."""
    doc = shipped()
    spec = AgentSpec.from_document(doc, "support")
    lead = Script([Turn("", (REFUND,)), Turn("", (REFUND,)), Turn("Refunded.")])
    offered: dict[str, list[str]] = {}

    def member(inner: AgentSpec) -> ReferenceTransport:
        class Member(ReferenceTransport):
            async def model_call(self, system, history, tools):  # type: ignore[override]
                offered[inner.name] = [t["name"] for t in tools]
                return await super().model_call(system, history, tools)

        return Member(Script([Turn("Noted.")]))

    ran: list[dict[str, Any]] = []
    kw: dict[str, Any] = dict(ask_member=delegate_by_running(doc, member), checking_transport=NO())
    first = asyncio.run(run(spec, ReferenceTransport(lead), "Please refund order A1.", tools(ran), **kw))
    parked = first.suspension
    yes = parked.answer(**{a.name: "yes" for a in parked.asks})
    after = asyncio.run(
        run(spec, ReferenceTransport(lead), "Please refund order A1.", tools(ran), resume=parked, answer=yes, now=1.0, **kw)
    )
    assert set(offered) == {"finance-desk", "auditor"}
    # The auditor is covered by the finance desk's `listens-for` like any other
    # agent, and on its own run it WOULD be offered the tool; woken, it is not.
    assert AgentSpec.from_document(doc, "auditor").reactions.tool() is not None
    assert all(WORKING_ON not in names for names in offered.values()), offered
    assert after.unenforced == ()


def test_a_judge_that_says_yes_adds_the_reminder_and_one_that_says_no_adds_nothing() -> None:
    doc = shipped()
    spec = AgentSpec.from_document(doc, "support")
    for verdict, reminded in (("Yes.", True), ("no", False)):
        listening = Listening(Script([Turn("I am sorry about that.")]))
        judge = Listening(Script([Turn(verdict)]))
        out = asyncio.run(
            run(spec, listening, "This is the third time. Useless!", tools([]),
                checking_transport=judge)
        )
        assert ("Apologise once" in listening.told[0]) is reminded, verdict
        assert bool(out.reactions) is reminded
        if reminded:
            assert out.reactions[0] == {
                "reaction": "upset-customer", "at": 0, "did": ["reminded"], "certainty": "guess",
            }


def test_a_count_holds_from_the_one_after_the_figure() -> None:
    doc = shipped()
    spec = AgentSpec.from_document(doc, "support")
    look = ToolCall("orders", {"action": "look-up", "order": "A1"})
    listening = Listening(Script([Turn("", (look,))] * 8 + [Turn("Done.")]))
    out = asyncio.run(run(spec, listening, "where is it", tools([]), checking_transport=NO()))
    assert out.halted == "final"
    reminded = ["You have taken more than six steps" in told for told in listening.told]
    # Steps 0-5 are the first six; the seventh (index 6) is the first reminded.
    assert reminded[:6] == [False] * 6 and all(reminded[6:]), reminded
    assert [r["at"] for r in out.reactions] == [6], "once a run"


# ── what a document built in code is held to ─────────────────────────────────


def desk(**reactions: Any) -> dict[str, Any]:
    return {
        "name": "T",
        "tools": {
            "pay": {
                "description": "Pays.",
                "actions": {
                    "send": {"description": "Send.", "takes": {"amount": "money", "to": "text"}},
                    "look": {"description": "Look.", "reads-only": "yes"},
                },
            }
        },
        "reactions": reactions,
        "agents": {
            "desk": {
                "description": "Pays people.",
                "instructions": "Pay.",
                "uses": ["pay"],
                "reactions": sorted(reactions),
            },
            "checker": {"description": "Checks.", "instructions": "Check."},
        },
    }


def send(to: str) -> ToolCall:
    return ToolCall("pay", {"action": "send", "amount": "5 USD", "to": to})


def test_with_nobody_to_run_another_agent_the_call_goes_through_and_the_run_says_so() -> None:
    doc = desk(first={
        "description": "Payments are checked.",
        "at": "step.tool.before",
        "when-this": [{"tool": "pay/send"}],
        "then": [{"consult": "checker"}],
    })
    ran: list[Any] = []
    out = asyncio.run(
        run(AgentSpec.from_document(doc, "desk"),
            ReferenceTransport(Script([Turn("", (send("ann"),)), Turn("Paid.")])),
            "pay ann", {"pay": lambda a: ran.append(a) or "sent"})
    )
    assert out.halted == "final" and len(ran) == 1
    assert out.unenforced == (
        "the reaction 'first' consults 'checker', and this run has nobody to run another "
        "agent — 'checker' was not asked",
    )


def test_every_time_holds_each_different_call_once() -> None:
    doc = desk(first={
        "description": "Payments are checked.",
        "at": "step.tool.before",
        "when-this": [{"tool": "pay/send"}],
        "fires": "every-time",
        "then": [{"consult": "checker"}],
    })
    members = says("Fine.")
    ran: list[Any] = []
    script = Script([
        Turn("", (send("ann"),)), Turn("", (send("ann"),)),
        Turn("", (send("bob"),)), Turn("", (send("bob"),)),
        Turn("", (ToolCall("pay", {"action": "look"}),)),
        Turn("Paid both."),
    ])
    out = asyncio.run(
        run(AgentSpec.from_document(doc, "desk"), ReferenceTransport(script), "pay both",
            {"pay": lambda a: ran.append(a.get("to")) or "sent"},
            ask_member=delegate_by_running(doc, members))
    )
    assert out.halted == "final", (out.halted, out.output)
    assert ran == ["ann", "bob", None], "each payment once, and the look-up untouched"
    assert [who for who, _ in members.woken] == ["checker", "checker"]


def test_an_exact_moment_can_stop_the_run_and_a_guess_cannot() -> None:
    twice = desk(second={
        "description": "One payment a request.",
        "at": "step.tool.before",
        "when-this": [{"tool": "pay/send"}],
        "more-than": 1,
        "then": [{"stop": "A second payment in one request needs a person."}],
    })
    ran: list[Any] = []
    out = asyncio.run(
        run(AgentSpec.from_document(twice, "desk"),
            ReferenceTransport(Script([Turn("", (send("ann"),)), Turn("", (send("bob"),)), Turn("x")])),
            "pay both", {"pay": lambda a: ran.append(a["to"]) or "sent"})
    )
    assert out.halted == "stopped-by-rule"
    assert out.output == "A second payment in one request needs a person."
    assert ran == ["ann"]

    # `pact check` refuses this tree (`loader/a-guess-cannot-stop`); a document
    # built in code gets the same answer at run time.
    guessed = desk(rude={
        "description": "The customer is rude.",
        "judged": "yes",
        "at": "turn.run.started",
        "then": [{"stop": "Goodbye."}],
    })
    out = asyncio.run(
        run(AgentSpec.from_document(guessed, "desk"),
            ReferenceTransport(Script([Turn("Hello.")])), "you fools", {},
            checking_transport=ReferenceTransport(Script([Turn("yes")])))
    )
    assert out.halted == "final" and out.output == "Hello."
    assert "would have stopped the run on a guess" in out.unenforced[0]


def test_a_reaction_being_carried_out_does_not_fire_again_beneath_itself() -> None:
    # Two agents that each ask to be consulted about the other's payments: the
    # shape that would never end. `a` pays -> `b` is asked; `b` pays inside
    # that -> `a` is asked; `a` pays inside THAT -> `b listens…` is already
    # being carried out, so it does not fire, and the payment goes through.
    agent = lambda: {  # noqa: E731
        "description": "Pays.", "instructions": "Pay.", "uses": ["pay"],
        "limits": {"asks-itself-at-most": 3, "when-it-runs-out": "stop-and-say-so"},
        "listens-for": [{"topic": "money", "how": "asked-first"}],
    }
    doc = {
        "name": "T",
        "topics": {"money": {"description": "Money."}},
        "tools": {"pay": {"description": "Pays.", "topics": ["money"],
                          "actions": {"send": {"description": "Send."}}}},
        "agents": {"a": agent(), "b": agent()},
    }
    paid: list[str] = []
    depth: list[str] = []

    def member(spec: AgentSpec) -> ReferenceTransport:
        depth.append(spec.name)
        return ReferenceTransport(Script([
            Turn("", (send(spec.name),)), Turn("", (send(spec.name),)), Turn(f"{spec.name} paid."),
        ]))

    out = asyncio.run(
        run(AgentSpec.from_document(doc, "a"),
            ReferenceTransport(Script([Turn("", (send("root"),)), Turn("", (send("root"),)), Turn("Done.")])),
            "pay", {"pay": lambda a: paid.append(a["to"]) or "sent"},
            ask_member=delegate_by_running(doc, member, {"pay": lambda a: paid.append(a["to"]) or "sent"}))
    )
    assert out.halted == "final", (out.halted, out.output, out.unenforced)
    assert depth == ["b", "a"], "two reactions were written, so the consulting is two deep"
    # Innermost first. `a`, two deep, was held by nothing — so both sends in
    # its script went out; `b` and the root were each held once, and paid once.
    assert paid == ["a", "a", "b", "root"], paid


def test_a_judges_first_word_decides() -> None:
    assert judged_yes("Yes — clearly.") is True
    assert judged_yes("**No**") is False
    assert judged_yes("It depends.") is None
    assert judged_yes("") is None


# ── the second port ──────────────────────────────────────────────────────────

TS_DIR = ROOT / "adapters" / "typescript"


def _node(spec: dict[str, Any], turns: list[dict[str, Any]]) -> dict[str, Any]:
    out = subprocess.run(
        ["node", "--experimental-strip-types", "src/run-trace.ts",
         json.dumps(spec), json.dumps({"turns": turns}), "hello"],
        cwd=TS_DIR, capture_output=True, text=True,
    )
    if out.returncode != 0:
        pytest.skip(f"node/AI SDK unavailable: {out.stderr[-300:]}")
    return json.loads(out.stdout)


def test_the_second_port_names_every_reaction_it_does_not_carry_out() -> None:
    spec = AgentSpec.from_document(shipped(), "support")
    said_so = spec.reactions.tool()
    payload = {
        "name": "support", "instructions": "Help.", "tools": [], "maxSteps": 4,
        "reactions": {
            "names": [r.name for r in spec.reactions.reactions],
            "workingOn": {
                "description": said_so["description"],
                "topics": [t.name for t in spec.reactions.said_by_the_agent()],
            },
        },
    }
    out = _node(payload, [
        # A subject that is not one of them first: once the one topic there
        # is has been said, the tool is no longer offered on either port.
        {"text": "", "toolCalls": [{"name": WORKING_ON, "args": {"topic": "the weather"}}]},
        {"text": "", "toolCalls": [{"name": WORKING_ON, "args": {"topic": "finance"}}]},
        {"text": "", "toolCalls": [{"name": WORKING_ON, "args": {"topic": "finance"}}]},
        {"text": "done"},
    ])
    lines = [s for s in out["unenforced"] if s.startswith("reactions: ")]
    assert len(lines) == len(spec.reactions.reactions) == 4, out["unenforced"]
    for reaction in spec.reactions.reactions:
        assert any(s.startswith(f"reactions: {reaction.name} — read and not carried out") for s in lines)
    # The tool is offered and answered in the words Python uses, so a model
    # sees the same thing on both; nobody is asked on this port.
    assert out["trace"][0]["results"] == [
        "error: 'the weather' is not one of the subjects to say: finance"
    ], out["trace"]
    assert out["trace"][1]["results"] == ["noted: finance"], out["trace"]
    # Said, so it is gone: saying it again is a call to a tool not offered.
    assert "working-on" in out["trace"][2]["results"][0], out["trace"]
    assert not out["trace"][2]["results"][0].startswith("noted"), out["trace"]
    # An agent no reaction covers is told nothing about them.
    quiet = _node({"name": "x", "instructions": "y", "tools": [], "maxSteps": 2}, [{"text": "done"}])
    assert not [s for s in quiet["unenforced"] if s.startswith("reactions")]


# ── the other two ways a topic is noticed ────────────────────────────────────


def test_a_tagged_set_of_documents_raises_its_topic_when_it_was_looked_in() -> None:
    doc = {
        "name": "T",
        "topics": {"hr": {"description": "People matters."}},
        "knowledge": {"handbook": {"description": "The handbook.", "topics": ["hr"]}},
        "reactions": {"hr-first": {
            "description": "People matters are worded carefully.",
            "topic": "hr",
            "applies-to": "every-agent",
            "then": [{"remind": "This is a people matter. Quote the handbook exactly."}],
        }},
        "agents": {"desk": {"description": "Answers.", "instructions": "Answer.", "uses": ["handbook"]}},
    }
    spec = AgentSpec.from_document(doc, "desk")
    for looked_in, reminded in ((["leave is 25 days"], True), (None, False)):
        listening = Listening(Script([Turn("25 days.")]))
        out = asyncio.run(
            run(spec, listening, "how much leave?", {},
                retrieved_by={"handbook": looked_in} if looked_in else None)
        )
        assert ("This is a people matter." in listening.told[0]) is reminded, looked_in
        assert [r["certainty"] for r in out.reactions] == (["exact"] if reminded else [])


def test_a_judge_notices_a_topic_only_where_the_topic_says_a_judge_does() -> None:
    def doc(noticed_by: list[str]) -> dict[str, Any]:
        return {
            "name": "T",
            "topics": {"legal": {"description": "A request for legal advice.", "noticed-by": noticed_by}},
            "reactions": {"no-advice": {
                "description": "Legal questions get the standard line.",
                "topic": "legal",
                "applies-to": "every-agent",
                "then": [{"remind": "Do not give legal advice. Say a solicitor should be asked."}],
            }},
            "agents": {"desk": {"description": "Answers.", "instructions": "Answer."}},
        }

    def went(noticed_by: list[str], verdict: str) -> tuple[Listening, Listening, Any]:
        listening = Listening(Script([Turn("You could sue."), Turn("Ask a solicitor.")]))
        judge = Listening(Script([Turn(verdict)]))
        spec = AgentSpec.from_document(doc(noticed_by), "desk")
        out = asyncio.run(run(spec, listening, "can I sue them?", {}, checking_transport=judge))
        return listening, judge, out

    # Read by a judge, at the start of the turn: the customer's words.
    listening, judge, out = went(["a-judge"], "yes")
    assert judge.told, "the judge was asked"
    assert "Do not give legal advice." in listening.told[0]
    assert out.reactions[0]["certainty"] == "guess"
    assert out.reactor.judged == 1, "asked once, and not again once the topic was noticed"
    # A judge that says no adds nothing — and is asked again after the step.
    listening, judge, out = went(["a-judge"], "no")
    assert "Do not give legal advice." not in listening.told[0]
    assert out.reactor.judged == 2
    # A topic only tags notice is never put to a judge at all.
    listening, judge, out = went(["tags"], "yes")
    assert judge.told == [] and out.reactor.judged == 0


# ── what a reaction costs is counted once, on the run that caused it ─────────


class Priced(ReferenceTransport):
    """A scripted model that says what its LAST call cost, as a real one does:
    a judgement costs a tenth of what a step of work does."""

    def __init__(self, script: Script) -> None:
        super().__init__(script)
        self.last = 0.0

    async def model_call(self, system, history, tools):  # type: ignore[override]
        from pact_adapters.reactions import JUDGE_SYSTEM

        self.last = 0.001 if system == JUDGE_SYSTEM else 0.010
        return await super().model_call(system, history, tools)

    def usage(self) -> tuple[int, float]:
        return (10, self.last)


def test_a_judgement_on_the_working_model_is_metered_once_and_the_step_is_not_lost() -> None:
    # One transport does the work AND the judging, which is what a run is
    # handed when nobody serves a second model. Two judgements (the customer's
    # words, then the agent's step) and one step of work.
    doc = desk(
        rude={"description": "The customer is rude.", "judged": "yes",
              "at": "turn.run.started", "then": [{"remind": "Stay polite."}]},
        unsure={"description": "The agent is unsure.", "judged": "yes",
                "then": [{"remind": "Say what you do not know."}]},
    )
    transport = Priced(Script([Turn("no")]))
    out = asyncio.run(run(AgentSpec.from_document(doc, "desk"), transport, "hello", {}))
    assert out.halted == "final" and out.reactor.judged == 2
    assert round(out.spent, 6) == round(0.010 + 2 * 0.001, 6), out.spent


def test_what_a_consulted_agent_spends_is_charged_to_the_run_that_woke_it() -> None:
    doc = desk(first={
        "description": "Payments are checked.",
        "at": "step.tool.before",
        "when-this": [{"tool": "pay/send"}],
        "then": [{"consult": "checker"}],
    })
    doc["agents"]["desk"]["limits"] = {
        "cost-per-request-under": "0.05 USD", "when-it-runs-out": "stop-and-say-so",
    }
    script = lambda: Script([Turn("", (send("ann"),)), Turn("", (send("ann"),)), Turn("Paid.")])  # noqa: E731
    alone = asyncio.run(
        run(AgentSpec.from_document(doc, "desk"), Priced(script()), "pay ann",
            {"pay": lambda a: "sent"})
    )
    woken = asyncio.run(
        run(AgentSpec.from_document(doc, "desk"), Priced(script()), "pay ann",
            {"pay": lambda a: "sent"},
            ask_member=delegate_by_running(doc, lambda spec: Priced(Script([Turn("Fine.")]))))
    )
    assert alone.halted == woken.halted == "final"
    # The checker made one call of its own, and it is on the desk's bill.
    assert round(woken.spent - alone.spent, 6) == 0.010, (alone.spent, woken.spent)
