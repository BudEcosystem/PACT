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


def test_whoever_decides_is_shown_what_they_are_deciding_about() -> None:
    """Found by the first live run (`test_the_language_runs_on_a_live_model`):
    a `decide` stage has no `bind:`, and the runtime handed the deciding agent
    `{}` and the deciding person `{}`. A scripted sorter answers whatever it
    is given; a real one, asked to sort a message it was not shown, said
    `not-sure` to every message."""
    desks = Desks(sorter_says="not-sure")
    shown_to_a_person: list[tuple[str, dict[str, Any]]] = []

    def person(question: str, shown: dict[str, Any]) -> dict[str, Any]:
        shown_to_a_person.append((question, dict(shown)))
        return {"desk": "tech"}

    doc = shown(REPO / TREE)
    spec = WorkflowSpec.from_workflow(doc, "route")
    out = asyncio.run(
        run_workflow(
            spec, {"message": "The app crashes.", "channel": "chat"},
            Callers(agent=desks, person=person), document=doc,
        )
    )
    assert out.halted == "final", out.said
    # The sorter `takes message: text`, so it is given the message — and not
    # the channel, which it never said it reads.
    assert desks.asked[0] == ("sorter", {"message": "The app crashes."})
    # The sorter was not sure, so a person decides — shown what the question's
    # own `shows: [input.message]` says to show.
    assert shown_to_a_person == [("which-desk", {"input.message": "The app crashes."})]
    assert stages(out) == ["where", "fix", "reply-fix"], out.trace


def test_inside_a_loop_the_decision_is_about_the_item() -> None:
    """`rung.agent`, as the schema says it: the current item's fields over the
    workflow's input, as many as the agent `accepts:` and nothing else, and
    the stage's `says:` at the start of its `message`."""
    from trees import write

    import tempfile

    files = {
        "w.pact": """\
workspace "Sorting"
  description: Every message in an inbox is put on a shelf.

shape letter
  id: text
  message: text
  secret: text

agent sorter
  description: Says which shelf a message belongs on.
  takes message: text
  gives shelf: one of bills, other
  instructions: Say which shelf.

workflow sort-all
  description: Sort every letter.
  takes letters: list of letter, message: text
  every = for each item in input.letters
    identified-by: [id]
    limits:
      items-at-most: 5
      when-it-runs-out: stop-and-say-so
    where = decide
      says: Pick the shelf for this letter.
      by:
        - { agent: sorter }
      if bills: done
      if other: done
  answer
"""
    }
    seen: list[tuple[str, dict[str, Any]]] = []

    def agent(name: str, inputs: dict[str, Any]) -> dict[str, Any]:
        seen.append((name, dict(inputs)))
        return {"shelf": "bills"}

    with tempfile.TemporaryDirectory() as tmp:
        doc = shown(write(Path(tmp) / "sorting", files))
    spec = WorkflowSpec.from_workflow(doc, "sort-all")
    letters = [
        {"id": "a", "message": "Your invoice is attached.", "secret": "never for the sorter"},
        {"id": "b", "message": "Hello from the seaside.", "secret": "nor this"},
    ]
    out = asyncio.run(
        run_workflow(spec, {"letters": letters, "message": "the workflow's own"}, Callers(agent=agent), document=doc)
    )
    assert out.halted == "final", out.said
    # Each letter's own `message` — the item's, over the workflow's — after the
    # stage's `says:`; and neither `secret` nor `id` nor `letters`, which the
    # sorter never said it reads.
    assert sorted(given["message"] for _, given in seen) == [
        "Pick the shelf for this letter.\n\nHello from the seaside.",
        "Pick the shelf for this letter.\n\nYour invoice is attached.",
    ]
    assert all(set(given) == {"message"} for _, given in seen), seen
    assert out.unenforced == []


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
