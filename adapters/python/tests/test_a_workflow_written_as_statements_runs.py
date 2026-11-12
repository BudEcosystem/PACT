"""A workflow written as statements RUNS (docs/99 §4.6).

`examples/language/help-centre` is four `.pact` files. Its two workflows are
written the way a program is — a name for each step, one line after another, a
`decide` with an `if` for each label, a `for each` — and nothing in this file
knows that: it loads the folder through `pact show`, as every other test of the
workflow runtime does, and runs what came out.

What is held is what the statements promise. The order written is the order
run. A step's name is a variable the next step reads. One workflow calls the
other, once for each item. A figure with a name (`let`) is the figure. A desk
made from a pattern (`based on … with …`) is that pattern, filled in.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters.ir import AgentSpec, WorkflowSpec  # noqa: E402
from pact_adapters.workflow_runtime import Callers, run_workflow  # noqa: E402
from trees import shown  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
TREE = "examples/language/help-centre"


class Desks:
    """The host's side: each agent answers with its own name, so a test can
    see which one a message reached."""

    def __init__(self, sorter_says: str = "tech") -> None:
        self.asked: list[tuple[str, dict[str, Any]]] = []
        self.sorter_says = sorter_says

    def __call__(self, name: str, inputs: dict[str, Any]) -> dict[str, Any]:
        self.asked.append((name, dict(inputs)))
        if name == "sorter":
            return {"desk": self.sorter_says}
        return {"reply": f"{name}: {inputs['message']}"}


def go(name: str, inputs: dict[str, Any], desks: Desks):
    doc = shown(REPO / TREE)
    spec = WorkflowSpec.from_workflow(doc, name)
    callers = Callers(agent=desks, person=lambda question, shown: {"desk": "out-of-scope"})
    return asyncio.run(run_workflow(spec, inputs, callers, document=doc)), doc


def stages(out) -> list[str]:
    return [t.split("/")[0] for t in out.trace]


def test_the_order_written_is_the_order_run_and_a_name_is_read_by_the_next_step() -> None:
    desks = Desks()
    out, _ = go("route", {"message": "My invoice is wrong.", "channel": "invoices-mailbox"}, desks)
    assert out.halted == "final", out.said
    # `where = decide` → the rule for the invoices mailbox picks `billing` →
    # the two statements beneath `if billing`, in the order they are written.
    assert stages(out) == ["where", "bill", "reply-bill"], out.trace
    # `bill = call billing-desk with message: input.message`
    assert desks.asked == [("billing-desk", {"message": "My invoice is wrong."})]
    # `reply-bill = answer with reply: bill.reply` — `bill` read by name.
    assert out.answer == {"reply": "billing-desk: My invoice is wrong."}


def test_the_decision_falls_to_the_next_one_who_can_make_it() -> None:
    # No rule covers the chat channel, so the sorter is asked, and says tech.
    desks = Desks(sorter_says="tech")
    out, _ = go("route", {"message": "The app crashes.", "channel": "chat"}, desks)
    assert out.halted == "final", out.said
    assert stages(out) == ["where", "fix", "reply-fix"], out.trace
    assert [name for name, _ in desks.asked] == ["sorter", "tech-desk"]
    assert out.answer == {"reply": "tech-desk: The app crashes."}


def test_a_label_with_one_step_beneath_it_ends_there() -> None:
    desks = Desks(sorter_says="out-of-scope")
    out, _ = go("route", {"message": "What is the weather?", "channel": "chat"}, desks)
    assert out.halted == "final", out.said
    assert stages(out) == ["where", "decline"], out.trace
    assert [name for name, _ in desks.asked] == ["sorter"], "no desk was asked"


def test_one_workflow_calls_another_once_for_each_item() -> None:
    desks = Desks(sorter_says="tech")
    inbox = [
        {"id": "m1", "text": "My invoice is wrong.", "channel": "invoices-mailbox"},
        {"id": "m2", "text": "The app crashes.", "channel": "chat"},
        # The same message again: `identified-by: [id]` makes it one item.
        {"id": "m1", "text": "My invoice is wrong.", "channel": "invoices-mailbox"},
    ]
    out, _ = go("clear-inbox", {"messages": inbox}, desks)
    assert out.halted == "final", out.said
    # `one = call route with message: item.text, channel: item.channel`,
    # inside `for each item in input.messages`: `route` ran twice, and each
    # run reached the desk its own message belongs to.
    reached = [name for name, _ in desks.asked if name != "sorter"]
    assert sorted(reached) == ["billing-desk", "tech-desk"], desks.asked
    # `done-all = answer with replies: every.reply` — every item's answer.
    assert sorted(out.answer["replies"]) == [
        "billing-desk: My invoice is wrong.",
        "tech-desk: The app crashes.",
    ]


def test_a_figure_with_a_name_is_the_figure_wherever_it_is_used() -> None:
    doc = shown(REPO / TREE)
    # `let large-refund = 200 USD`, used in the policy's sentence as
    # `{use: large-refund}`.
    rule = doc["policies"]["approvals"]["ask-a-person"][0]
    assert rule["when"] == [
        {"tool": "billing/issue-refund", "arg": "amount", "more-than": "200 USD"}
    ]
    # `let messages-at-most = 50`, used as a setting beneath `for each`.
    every = doc["workflows"]["clear-inbox"]["steps"]["every"]
    assert every["limits"]["items-at-most"] == 50
    assert "values" not in doc, "a figure put in place leaves nothing behind"


def test_a_desk_made_from_a_pattern_is_the_pattern_filled_in() -> None:
    doc = shown(REPO / TREE)
    # `based on desk with domain: billing, cap: 0.10 USD`
    billing = AgentSpec.from_document(doc, "billing-desk")
    tech = AgentSpec.from_document(doc, "tech-desk")
    assert "questions about billing" in billing.instructions
    assert "questions about technical problems" in tech.instructions
    assert doc["agents"]["billing-desk"]["limits"]["cost-per-request-under"] == "0.10 USD"
    assert doc["agents"]["tech-desk"]["limits"]["cost-per-request-under"] == "0.05 USD"
    # What the desk added to the pattern is its own: a tool, a policy, and the
    # reaction written inside its block.
    assert doc["agents"]["billing-desk"]["uses"] == ["billing"]
    assert [r.name for r in billing.reactions.reactions] == [
        "wrap-up",
        "finance-desk listens for finance",
    ]
    assert "desk" not in {a for a, v in doc["agents"].items() if not v.get("base")}
