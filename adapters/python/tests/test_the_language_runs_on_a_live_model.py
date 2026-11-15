"""The PACT language and its reactions, against a real model (docs/99 §7).

Every other test of them drives a scripted model, which is how a loop is
tested and is silent about the one thing a script cannot show: whether a model
that was never told the plan does what the document expects of it. Does it
make the call again after the finance desk has been heard? Does it say what
it is working on, when only it can know? Does a judge reading a customer's
words agree with a person about who is upset?

Opt-in, the way `test_the_phase_1_fields_reach_a_live_model.py` is: set
`PACT_LIVE_BASE_URL` (a server that speaks `/chat/completions`),
`PACT_LIVE_MODEL` (a model on it that calls tools) and `PACT_LIVE_API_KEY`
where the server wants a key. Skipped otherwise, so the offline suite never
reaches a network.

    PACT_LIVE_BASE_URL=https://api.openai.com/v1 PACT_LIVE_MODEL=gpt-4o-mini \\
    PACT_LIVE_API_KEY=... pytest tests/test_the_language_runs_on_a_live_model.py -s

A model that reasons before it answers needs room for both; add
`PACT_LIVE_MAX_TOKENS=4000` for one.

Tools are the test's own functions — nothing here moves money — and every
model in the run is the live one: the agent, the agents it wakes, the judge.
Assertions are about what the HARNESS guarantees whatever the model says (no
refund before the finance desk was heard and a person said yes; once, not
twice) and about what the model was expected to do, each said separately in
the failure so a reader can tell a broken guarantee from a model that did not
cooperate.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters.harness import delegate_by_running, run  # noqa: E402
from pact_adapters.ir import AgentSpec, WorkflowSpec  # noqa: E402
from pact_adapters.reactions import WORKING_ON  # noqa: E402
from pact_adapters.transports.ollama_transport import OllamaTransport  # noqa: E402
from pact_adapters.workflow_runtime import Callers, run_workflow, worded  # noqa: E402
from trees import shown, write  # noqa: E402

BASE_URL = os.environ.get("PACT_LIVE_BASE_URL", "")
MODEL = os.environ.get("PACT_LIVE_MODEL", "")
API_KEY = os.environ.get("PACT_LIVE_API_KEY", "")
#: The most a reply may run to. 400 is plenty for a model that only writes its
#: answer. A model that reasons first spends this on its reasoning too, and at
#: 400 has nothing left to answer with: give it `PACT_LIVE_MAX_TOKENS=4000`.
MAX_TOKENS = int(os.environ.get("PACT_LIVE_MAX_TOKENS", "400"))
REPO = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.skipif(
    not (BASE_URL and MODEL),
    reason="opt-in: set PACT_LIVE_BASE_URL and PACT_LIVE_MODEL to a served model that calls tools",
)


class Live(OllamaTransport):
    """The live model, keeping what it was shown and what it did."""

    #: Every call any live transport in this process made: who, and which
    #: tools it asked for. One list, so the order ACROSS agents can be read.
    log: list[tuple[str, list[str]]] = []

    def __init__(self, who: str = "") -> None:
        super().__init__(MODEL, base_url=BASE_URL, api_key=API_KEY, timeout=120.0, max_tokens=MAX_TOKENS)
        self.who = who
        self.told: list[str] = []
        self.offered: list[str] = []

    async def model_call(self, system, history, tools):  # type: ignore[override]
        self.told.append(system)
        self.offered = [t["name"] for t in tools]
        #: What was offered at each call, in order.
        self.offers = [*getattr(self, "offers", []), self.offered]
        text, calls = await super().model_call(system, history, tools)
        Live.log.append((self.who, [c.name for c in calls]))
        return text, calls


def member(events: list[tuple[str, str]]):
    """A transport for each agent that is woken, noting that it was."""

    def make(spec: AgentSpec) -> Live:
        events.append(("woke", spec.name))
        return Live(spec.name)

    return make


def said(result) -> str:
    return f"halted={result.halted!r} output={result.output!r} unenforced={result.unenforced!r}"


# ── one agent, one file ──────────────────────────────────────────────────────


def test_the_smallest_file_there_is_answers() -> None:
    doc = shown(REPO / "examples/language/hello/hello.pact")
    spec = AgentSpec.from_document(doc, "greeter")
    out = asyncio.run(run(spec, Live("greeter"), "Hello, I'm Sam."))
    print("\n[hello]", out.output)
    assert out.halted == "final", said(out)
    assert out.output.strip(), "the model said nothing"


# ── a limit runs out: answer with what it has ────────────────────────────────


def test_out_of_lookups_it_answers_from_what_it_has_and_makes_nothing_up() -> None:
    """Five lookups asked for, two allowed, `answer-with-what-it-has`.

    The closing request offers no tools. Before it also SAID a limit had been
    reached, this model answered it with `[result of ledger] water: entry
    found` — a tool result it wrote itself, for a lookup never made — five
    runs of five. Told which calls were not made, none of five.
    """
    doc = shown(REPO / "tests/conformance/trees/metered-desk")
    spec = AgentSpec.from_document(doc, "answers")
    looked: list[str] = []

    def ledger(args: dict[str, Any]) -> str:
        looked.append(str(args.get("entry")))
        return f"{args.get('entry')}: entry found"

    live = Live("answers")
    out = asyncio.run(
        run(spec, live, "Look up these five entries in the ledger and tell me which exist: "
            "rent, gas, water, phone, tax.", {"ledger": ledger})
    )
    print("\n[out of lookups]", looked, "->", out.output)
    # What the harness guarantees, whatever the model says.
    assert len(looked) == 2, f"the ceiling is two lookups, and {len(looked)} were made"
    assert out.halted == "tool-call-limit", said(out)
    assert live.offers[-1] == [], "the closing request offered a tool"
    assert "This run has reached its limit, `tool-calls-at-most` (2 of 2 tool calls)" in live.told[-1]
    # What the model was expected to do with being told.
    assert "[result of" not in out.output, f"the model wrote a tool result itself: {out.output!r}"
    never = [e for e in ("rent", "gas", "water", "phone", "tax") if e not in looked]
    made_up = [e for e in never if f"{e}: entry found" in out.output]
    assert not made_up, f"the model reported lookups that were never made: {made_up}"


# ── an answer held to what the agent says it gives ───────────────────────────

REFUNDS = REPO / "tests/conformance/trees/decided-refunds"
ORDER = "Order 7 was a lamp for 45 USD and it arrived broken. Refund it?"


def _orders(args: dict[str, Any]) -> str:
    return "order 7: one lamp, 45 USD, delivered broken, bought 6 days ago"


def test_a_live_model_ends_its_reply_with_what_the_agent_gives() -> None:
    """The shape is put to the model in the author's own words, and the answer
    is held to it. A live model has to actually write the fields."""
    spec = AgentSpec.from_document(shown(REFUNDS), "desk")
    live = Live("desk")
    out = asyncio.run(run(spec, live, ORDER, {"orders": _orders}))
    assert out.halted == "final", said(out)
    assert out.answer.get("decision") in ("approved", "declined"), said(out)
    assert "amount" in out.answer, said(out)


class Forgetful(Live):
    """A live model whose FIRST reply is thrown away and replaced by one that is
    not the answer. What follows is the live model's own doing: it is sent the
    conversation with that reply in it as its own, told why it was not the
    answer, and asked again."""

    async def model_call(self, system, history, tools):  # type: ignore[override]
        first = not self.told
        text, calls = await super().model_call(system, history, tools)
        return ("Sure, I think we should refund them.", []) if first else (text, calls)


def test_a_live_model_told_why_its_answer_did_not_fit_answers_again_and_fits() -> None:
    """The words a model is told when its reply was not the answer
    (`answers_fit.ask_again`) are only any good if a model that reads them
    then writes the fields. Scripted models prove the harness asks again;
    this proves the asking works."""
    spec = AgentSpec.from_document(shown(REFUNDS), "desk")
    live = Forgetful("desk")
    out = asyncio.run(run(spec, live, ORDER, {"orders": _orders}))
    assert out.halted == "final", said(out)
    assert out.steps[0].text == "Sure, I think we should refund them."
    # Told at the request after the reply that did not fit, last in its system text.
    assert "Your last answer did not fit what your answer must contain:" in live.told[1], live.told[1][-500:]
    assert "`decision` is missing" in live.told[1] and "`amount` is missing" in live.told[1]
    assert out.answer.get("decision") in ("approved", "declined"), said(out)
    assert "amount" in out.answer, said(out)


def test_a_live_model_out_of_lookups_still_ends_with_what_the_agent_gives() -> None:
    """The closing answer of a run that reached a limit is held like any other."""
    spec = AgentSpec.from_document(shown(REFUNDS), "closes")
    out = asyncio.run(run(spec, Live("closes"), ORDER, {"orders": _orders}))
    assert out.answer.get("decision") in ("approved", "declined"), said(out)


def _ledger(looked: list[str]):
    def ledger(args: dict[str, Any]) -> str:
        looked.append(str(args.get("entry")))
        return f"{args.get('entry')}: entry found"

    return ledger


FIVE = "Look up these five entries in the ledger and tell me which exist: rent, gas, water, phone, tax."


def test_a_model_shown_its_own_calls_does_not_make_them_again() -> None:
    """Five lookups, three steps allowed. While a turn that called tools was
    sent as `.` and its results as lines of the user's, this model made the
    same five lookups in every step — fifteen — and ran out of steps."""
    doc = shown(REPO / "tests/conformance/trees/metered-desk")
    looked: list[str] = []
    out = asyncio.run(run(AgentSpec.from_document(doc, "paced"), Live("paced"), FIVE, {"ledger": _ledger(looked)}))
    print("\n[its own calls]", looked, "->", out.halted, out.output)
    assert sorted(looked) == sorted(set(looked)), f"the model repeated a lookup: {looked}"
    assert out.halted == "final", said(out)


def test_after_a_yes_it_makes_the_calls_that_were_not_made_and_repeats_none() -> None:
    """Five asked for, two allowed, `ask-a-person`, and the person says yes."""
    doc = shown(REPO / "tests/conformance/trees/metered-desk")
    spec = AgentSpec.from_document(doc, "asks")
    looked: list[str] = []
    out = asyncio.run(run(spec, Live("asks"), FIVE, {"ledger": _ledger(looked)}))
    # What the harness guarantees.
    assert out.halted == "suspended" and len(looked) == 2, said(out)
    parked = out.suspension
    live = Live("asks")
    out = asyncio.run(
        run(spec, live, FIVE, {"ledger": _ledger(looked)}, resume=parked,
            answer=parked.answer(**{a.name: "yes" for a in parked.asks}), now=1.0)
    )
    print("\n[after a yes]", looked, "->", out.halted)
    assert len(looked) <= 4, f"a yes grants two more lookups, and {len(looked) - 2} were made"
    assert "A person was asked and said to keep going." in live.told[0]
    assert all("said to keep going" not in later for later in live.told[1:])
    # What the model was expected to do with being told.
    assert sorted(looked) == sorted(set(looked)), f"the model repeated a lookup: {looked}"
    assert len(looked) == 4, f"the model did not go on with the lookups it was owed: {looked}"


# ── reactions: asked first, a person, once, told after ───────────────────────


def test_the_finance_desk_is_asked_first_a_person_says_yes_and_the_refund_goes_out_once() -> None:
    doc = shown(REPO / "examples/language/finance-first/finance-first.pact")
    spec = AgentSpec.from_document(doc, "support")
    events: list[tuple[str, str]] = []

    def billing(args: dict[str, Any]) -> str:
        events.append(("ran", f"billing/{args.get('action')}"))
        if args.get("action") == "issue-refund":
            return f"refunded {args.get('amount', '40 USD')} for order {args.get('order', 'A1')}"
        return "invoice INV-7: 40 USD, paid"

    def orders(args: dict[str, Any]) -> str:
        events.append(("ran", "orders/look-up"))
        return "order A1: one lamp, 40 USD, delivered on 3 November"

    tools = {"billing": billing, "orders": orders}
    asked = "Please refund order A1. The lamp arrived broken. It cost 40 USD."
    kw: dict[str, Any] = dict(
        ask_member=delegate_by_running(doc, member(events)),
        checking_transport=Live("judge"),
    )
    out = asyncio.run(run(spec, Live("support"), asked, tools, **kw))
    parks = 0
    while out.halted == "suspended" and parks < 4:
        parks += 1
        parked = out.suspension
        events.append(("asked-a-person", ", ".join(a.name for a in parked.asks)))
        # THE GUARANTEE, whatever the model did: at the moment a person is
        # asked, no money has moved.
        assert ("ran", "billing/issue-refund") not in events, events
        yes = parked.answer(**{a.name: "yes" for a in parked.asks})
        out = asyncio.run(
            run(spec, Live("support"), asked, tools, resume=parked, answer=yes, now=float(parks), **kw)
        )
    print("\n[finance-first] events:", events)
    print("[finance-first] reactions:", json.dumps(out.reactions, indent=1)[:1500])
    print("[finance-first] answer:", out.output)

    refunds = [e for e in events if e == ("ran", "billing/issue-refund")]
    woke = [who for kind, who in events if kind == "woke"]
    # What the harness guarantees.
    if refunds:
        first_refund = events.index(("ran", "billing/issue-refund"))
        assert ("woke", "finance-desk") in events[:first_refund], (
            f"money moved before the finance desk was heard: {events}"
        )
        assert any(kind == "asked-a-person" for kind, _ in events[:first_refund]), (
            f"money moved before a person said yes: {events}"
        )
    assert len(refunds) <= 1, f"the refund went out {len(refunds)} times: {events}"
    # What the model was expected to do: go on and make the call again.
    assert out.halted == "final", said(out)
    assert len(refunds) == 1, (
        f"the harness held every guarantee, and the model never completed the refund: {events}"
    )
    assert "finance-desk" in woke, events
    assert "auditor" in woke and events.index(("woke", "auditor")) > events.index(
        ("ran", "billing/issue-refund")
    ), f"the auditor is told AFTER the refund: {events}"
    heard = {h["agent"]: h for r in out.reactions for h in r.get("heard", [])}
    assert heard["finance-desk"]["how"] == "asked-first" and heard["finance-desk"]["said"].strip()
    assert heard["auditor"]["how"] == "told-after" and heard["auditor"]["said"].strip()
    assert out.unenforced == (), out.unenforced


# ── a judgement ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "wrote, upset",
    [
        (
            "This is the THIRD time I am writing. Order A1 still has not arrived and nobody "
            "answers. This is a disgrace and I am furious.",
            True,
        ),
        ("Hello! Could you tell me whether order A1 has been delivered yet? Thank you.", False),
    ],
)
def test_a_live_judge_reads_who_is_upset_and_only_then_is_the_agent_reminded(wrote: str, upset: bool) -> None:
    doc = shown(REPO / "examples/language/finance-first/finance-first.pact")
    spec = AgentSpec.from_document(doc, "support")
    lead = Live("support")
    tools = {
        "orders": lambda args: "order A1: one lamp, 40 USD, out for delivery today",
        "billing": lambda args: "invoice INV-7: 40 USD, paid",
    }
    out = asyncio.run(run(spec, lead, wrote, tools, checking_transport=Live("judge")))
    fired = [r for r in out.reactions if r["reaction"] == "upset-customer"]
    print(f"\n[judge upset={upset}] fired={bool(fired)} answer: {out.output}")
    assert bool(fired) is upset, (out.reactions, wrote)
    assert all(r["certainty"] == "guess" for r in fired)
    reminded = any("The customer is upset." in told for told in lead.told)
    assert reminded is upset
    if upset:
        # Everything the agent said in the run, not its last message alone. The
        # reminder is "Apologise once, plainly, before anything else", and a
        # model that is shown its own earlier turn does exactly that: it
        # apologises in its first words, beside the lookup, and not a second
        # time in the answer. (While its own turn reached it as text it could
        # not recognise, it apologised twice, and this read only the second.)
        spoken = " ".join([*(step.text for step in out.steps), out.output])
        assert re.search(r"sorry|apolog", spoken, re.I), (
            f"the agent was reminded to apologise, and did not: {spoken!r}"
        )


# ── a topic only the agent can notice ────────────────────────────────────────

LEGAL = {
    "legal.pact": """\
workspace "Live"
  description: A desk that knows when a question is a legal one.

topic legal
  description: Contracts, liability, or what the law requires of the company.
  noticed-by: [the-agent]

agent helper
  description: Answers staff questions.
  uses notes
  at most 6 steps
  when it runs out: stop and say so

  when the work touches legal
    called a-legal-question
    remind it: This is a legal matter. Say plainly that you are not a lawyer, and that the legal team must confirm before anyone acts.

  instructions
    Answer the question a member of staff asks, briefly.

resource office
  resource-kind: mcp-server
  endpoint: host/office
  description: Where the office systems are reached.

tool notes
  description: The company's internal notes.
  connect: office
  actions:
    search:
      description: Search the internal notes for a phrase.
      reads-only: yes
      takes:
        phrase: text
"""
}


def test_a_model_says_what_it_is_working_on_and_the_reaction_fires(tmp_path: Path) -> None:
    doc = shown(write(tmp_path / "legal", LEGAL))
    spec = AgentSpec.from_document(doc, "helper")
    lead = Live("helper")
    tools = {"notes": lambda args: "No notes mention this."}
    out = asyncio.run(
        run(
            spec, lead,
            "Can we be sued if we end the contract with our supplier three months early?",
            tools,
        )
    )
    said_so = [who_calls for who_calls in Live.log if who_calls[0] == "helper" and WORKING_ON in who_calls[1]]
    print(f"\n[working-on] offered={lead.offered} called={bool(said_so)} reactions={out.reactions}")
    print("[working-on] answer:", out.output)
    assert WORKING_ON in lead.offers[0], "the tool was not offered"
    assert WORKING_ON not in lead.offers[-1], "said, and still offered: it would be said again"
    # What the model was expected to do, and what nothing but a live run shows.
    assert said_so, f"the model never said what it was working on: {Live.log}"
    fired = [r for r in out.reactions if r["reaction"] == "a-legal-question"]
    assert fired and fired[0]["certainty"] == "guess", out.reactions
    assert out.halted == "final", said(out)
    assert re.search(r"not a lawyer|legal team", out.output, re.I), out.output


# ── workflows written as statements, with real agents ────────────────────────


def _answer_of(text: str) -> dict[str, Any]:
    """What an agent answered, as the fields it was asked for."""
    found = re.search(r"\{.*\}", text, re.S)
    if found:
        try:
            parsed = json.loads(found.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {"reply": text.strip()}


def live_agents(doc: dict[str, Any], ran: list[str]):
    async def agent(name: str, inputs: dict[str, Any]) -> dict[str, Any]:
        spec = AgentSpec.from_document(doc, name)
        ran.append(name)
        out = await run(
            # Everything it was given and nothing else (`worded`). This sent
            # the `message` and dropped every other field, so an agent that
            # accepted more was never shown it.
            spec, Live(name), worded(doc, name, inputs),
            {"billing": lambda args: "invoice INV-7: 40 USD, paid on 1 November"},
        )
        answer = _answer_of(out.output)
        if name == "sorter" and "desk" not in answer:
            # One word was asked for; a model that wrote a sentence still said it.
            word = re.search(r"billing|tech|out-of-scope|not-sure", out.output)
            answer = {"desk": word.group(0) if word else "not-sure"}
        print(f"  [{name}] {out.output[:160]!r} -> {answer}")
        return answer

    return agent


@pytest.mark.parametrize(
    "message, channel, expect_stages, expect_agents",
    [
        # A written rule decides: nobody is asked where it goes.
        ("My invoice shows the wrong amount.", "invoices-mailbox", ["where", "bill", "reply-bill"], ["billing-desk"]),
        # No rule covers chat, so the sorter — a real model — decides.
        ("The app crashes every time I open the settings page.", "chat", ["where", "fix", "reply-fix"], ["sorter", "tech-desk"]),
        ("What is the weather like in Lisbon tomorrow?", "chat", ["where", "decline"], ["sorter"]),
    ],
)
def test_a_workflow_written_as_statements_routes_with_real_agents(
    message: str, channel: str, expect_stages: list[str], expect_agents: list[str]
) -> None:
    doc = shown(REPO / "examples/language/help-centre")
    spec = WorkflowSpec.from_workflow(doc, "route")
    ran: list[str] = []
    print(f"\n[route] {channel}: {message}")
    callers = Callers(
        agent=live_agents(doc, ran),
        person=lambda question, shown: {"desk": "out-of-scope"},
    )
    out = asyncio.run(
        run_workflow(spec, {"message": message, "channel": channel}, callers, document=doc)
    )
    stages = [t.split("/")[0] for t in out.trace]
    print(f"[route] stages={stages} agents={ran} answer={out.answer}")
    assert out.halted == "final", out.said
    assert stages == expect_stages, (stages, out.trace)
    assert ran == expect_agents
    if "decline" not in expect_stages:
        reply = str(out.answer.get("reply", ""))
        assert reply.strip(), out.answer
        # FOUND LIVE AND NOT FIXED (docs/99 §7): asked to "end your reply with
        # … `- reply: text`", `gpt-4o-mini` ends its reply with the line
        # `- reply: text`. A closed list (`desk: one of …`) it fills in
        # correctly. That instruction is the harness's for every agent that
        # `gives` anything and is not the language's to change; a clearer
        # wording was tried here and did not hold. Printed, not asserted, so
        # this file's result is about routing — and the line is not lost.
        if "reply: text" in reply:
            print("  [known] the desk copied `- reply: text` instead of filling it in")


def test_one_workflow_calls_another_for_each_message_with_real_agents() -> None:
    doc = shown(REPO / "examples/language/help-centre")
    spec = WorkflowSpec.from_workflow(doc, "clear-inbox")
    ran: list[str] = []
    inbox = [
        {"id": "m1", "text": "My invoice shows the wrong amount.", "channel": "invoices-mailbox"},
        {"id": "m2", "text": "The app crashes when I open settings.", "channel": "chat"},
    ]
    print("\n[clear-inbox]")
    callers = Callers(agent=live_agents(doc, ran), person=lambda q, s: {"desk": "out-of-scope"})
    out = asyncio.run(run_workflow(spec, {"messages": inbox}, callers, document=doc))
    print(f"[clear-inbox] agents={ran} answer={out.answer}")
    assert out.halted == "final", out.said
    assert sorted(a for a in ran if a != "sorter") == ["billing-desk", "tech-desk"], ran
    replies = out.answer["replies"]
    assert len(replies) == 2 and all(str(r).strip() for r in replies), replies
