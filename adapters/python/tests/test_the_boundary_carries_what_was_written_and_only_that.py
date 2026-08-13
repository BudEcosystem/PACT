"""What `AgentSpec.from_document` carries is what the author wrote — no more, no less.

An independent mutation audit of `src/pact_adapters/ir.py` changed nine things
in that file and the whole adapter suite still passed on every one. This file is
those nine, each pinned by the smallest document that can tell the difference.
They fall into three groups, and none of them is cosmetic:

* **What an agent is given.** Deleting the `uses:` filter on `tools` handed every
  tool in the workspace to every agent in it, and 1835 tests agreed. That is the
  capability boundary itself: `uses:` is the whole of what an author writes to
  say which systems an agent may touch, and a run that ignores it will call a
  payments server nobody let it near. Nothing looked.

* **What order it is given in.** Three separate sorts — the tool list, the
  `action` argument's choices, and the first-wins merge of two actions' `takes:`
  — are load-bearing for the reason `ir.py` states in its own comments: *"so two
  lists in two languages never disagree about order"*. Every one of them could
  be deleted silently, so the ordering guarantee the second port is held to was
  a guarantee nothing held.

* **What the words are when they arrive.** `answers-with-mode:` reached the spec
  as `""` however it was written. `bind:` lines keyed under the empty string
  instead of their action's name — which is what `_bound_args` reads when a call
  names NO action, so every authored bind would have been looked up under a name
  no call has, and the argument the surrounding system fills in would silently
  never be filled. And both halves of `_text` — the `strip()` and the blank line
  between the parts of a field written as a folder — were free to change.

Everything here goes through `AgentSpec.from_document`, which is the authored
path, for the reason `test_where_a_tool_reaches_survives_the_boundary.py` gives:
a test that built the dataclass itself would prove the dataclass works and say
nothing about whether the author's line reaches it.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.ir import AgentSpec  # noqa: E402


def workspace(agent: dict[str, Any], **rest: Any) -> dict[str, Any]:
    """The smallest document with one agent in it, so a failure names one line."""
    base: dict[str, Any] = {"description": "x", "instructions": "y"}
    return {"agents": {"desk": {**base, **agent}}, **rest}


def spec_of(agent: dict[str, Any], **rest: Any) -> AgentSpec:
    return AgentSpec.from_document(workspace(agent, **rest), "desk")


# ───────────────────── what an agent is given ─────────────────────


def test_a_tool_the_agent_did_not_name_does_not_reach_it() -> None:
    """`uses:` is the capability boundary, and it has to be the one that is applied.

    Two tools in the workspace, one named. The unnamed one must not arrive —
    not filtered out later by a transport, not offered and refused, absent.
    An adapter that handed over both would put `payments` in the model's tool
    list for an agent whose author never let it near money, and no other test in
    this suite noticed when that filter was deleted.
    """
    doc = workspace(
        {"uses": ["zendesk"]},
        tools={
            "payments": {"description": "Where refunds are issued.", "connect": "pay-server"},
            "zendesk": {"description": "The ticket desk.", "connect": "zendesk-server"},
        },
    )
    spec = AgentSpec.from_document(doc, "desk")
    assert tuple(t.name for t in spec.tools) == ("zendesk",), (
        "a tool the agent's `uses:` line does not name reached it anyway: "
        f"{sorted(t.name for t in spec.tools)} — `uses:` is the capability "
        "boundary, so a tool nobody named must reach no agent"
    )


def test_an_agent_that_names_no_tools_is_given_none_of_the_workspaces_tools() -> None:
    """The same boundary at zero, which is where "filter deleted" is loudest.

    An agent with no `uses:` line at all and a workspace full of tools: the
    absence of a filter and the absence of a name look identical on an agent
    that names one tool out of one, and this is the case that separates them.
    """
    doc = workspace(
        {},
        tools={
            "payments": {"description": "Where refunds are issued.", "connect": "pay-server"},
            "zendesk": {"description": "The ticket desk.", "connect": "zendesk-server"},
        },
    )
    assert AgentSpec.from_document(doc, "desk").tools == (), (
        "an agent that named no tools was handed the workspace's tools anyway"
    )


# ───────────────────── what order it is given in ─────────────────────


def test_the_tools_arrive_in_name_order_whatever_order_the_document_wrote_them() -> None:
    """`ir.py`'s own reason: *"so two lists in two languages never disagree about order"*.

    `adapters/typescript/src/harness.ts` sorts its skills for the same reason and
    the conformance driver compares the two ports' output. A document whose
    `tools:` block is written in the order the author happened to think of them
    must still cross the boundary in one order, or the two ports differ on a
    document neither of them is wrong about.
    """
    doc = workspace(
        {"uses": ["zendesk", "payments", "audit"]},
        tools={
            "zendesk": {"description": "The ticket desk.", "connect": "zendesk-server"},
            "payments": {"description": "Where refunds are issued.", "connect": "pay-server"},
            "audit": {"description": "The write-down.", "connect": "audit-server"},
        },
    )
    got = tuple(t.name for t in AgentSpec.from_document(doc, "desk").tools)
    assert got == ("audit", "payments", "zendesk"), (
        f"the tools crossed the boundary in {got}, not in name order — the "
        "document's own order reached the model, so the same workspace builds "
        "two different tool lists in the two ports"
    )


def test_the_action_argument_offers_its_choices_in_one_order() -> None:
    """`action` is what makes a call `<tool>/<action>`, and its choices are prose the model reads.

    The sentence is built by joining the action names, so the order is part of
    the system message. Unsorted, it is the order the author's file happened to
    list them in — which makes the prompt, and therefore the run, depend on a
    detail the schema says nothing about.
    """
    doc = workspace(
        {"uses": ["payments"]},
        tools={
            "payments": {
                "description": "Where refunds are issued.",
                "connect": "pay-server",
                "actions": {
                    "refund": {"takes": {"order-number": "text"}},
                    "check": {"takes": {"order-number": "text"}},
                    "authorise": {"takes": {"order-number": "text"}},
                },
            }
        },
    )
    got = AgentSpec.from_document(doc, "desk").tools[0].parameters["action"]
    assert got == "one of authorise, check, refund", (
        f"the action choices reached the model as {got!r} — the author's own "
        "declaration order, which is not an order the two ports agree on"
    )


def test_two_actions_naming_one_argument_settle_it_the_same_way_every_time() -> None:
    """`takes:` is merged across actions, so a clash needs a rule, and the rule has to be fixed.

    `_takes` merges with `setdefault` over `sorted(actions.items())`: the
    earlier action by NAME decides. The rule matters less than its being one
    rule — a merge that took the last writer would give the same document two
    argument lists depending on the order the loader happened to emit, and this
    is exactly the argument list the model is shown.
    """
    doc = workspace(
        {"uses": ["payments"]},
        tools={
            "payments": {
                "description": "Where refunds are issued.",
                "connect": "pay-server",
                "actions": {
                    # Written last, sorts first: if the merge followed the
                    # document rather than the name, `text` would win.
                    "authorise": {"takes": {"amount": "money"}},
                    "refund": {"takes": {"amount": "text"}},
                },
            }
        },
    )
    got = AgentSpec.from_document(doc, "desk").tools[0].parameters["amount"]
    assert got == "money", (
        f"`amount` arrived as {got!r}: the merge is first-by-action-name, so "
        "`authorise` decides — a last-writer merge makes the argument list a "
        "function of the document's order rather than of what it says"
    )


# ───────────────────── what the words are when they arrive ─────────────────────


def test_the_way_the_answer_shape_is_put_to_the_model_reaches_the_spec() -> None:
    """`answers-with-mode:` is what the author wrote to choose between four ways of asking.

    Its own help says the empty case is decided later and RECORDED. That only
    works if the non-empty case survives the boundary; carried as `""` however
    it was written, every author gets `prompted` and the one who asked for a
    native JSON schema is told nothing. No fixture in this suite wrote the line,
    so nothing read it.
    """
    for wrote, want in (
        ("native-json-schema", "native-json-schema"),
        ("tool", "tool"),
        ("  prompted  ", "prompted"),
        ("", ""),
    ):
        got = spec_of({"answers-with-mode": wrote}).answers_with_mode
        assert got == want, f"`answers-with-mode: {wrote!r}` arrived as {got!r}"


def test_each_actions_bind_lines_arrive_under_that_actions_own_name() -> None:
    """`binds` is keyed by action because `_bound_args` looks the call's action up in it.

    Keyed under anything else, every authored `bind:` is filed under a name no
    call carries, so the argument the surrounding system fills in is never
    filled — which is the defect `ToolSpec.binds` documents as already having
    shipped once: *"`payments` received `{order-number, amount, action}` and
    never `customer-id`"*.
    """
    doc = workspace(
        {"uses": ["payments"], "run-inputs": {"customer-id": "text", "agent-id": "text"}},
        tools={
            "payments": {
                "description": "Where refunds are issued.",
                "connect": "pay-server",
                "actions": {
                    "issue-refund": {
                        "takes": {"amount": "money"},
                        "bind": {"customer-id": "run-inputs.customer-id"},
                    },
                    "look-up-order": {
                        "takes": {"order-number": "text"},
                        "bind": {"asked-by": "run-inputs.agent-id"},
                    },
                },
            }
        },
    )
    got = AgentSpec.from_document(doc, "desk").tools[0].binds
    assert got == {
        "issue-refund": {"customer-id": "run-inputs.customer-id"},
        "look-up-order": {"asked-by": "run-inputs.agent-id"},
    }, (
        f"the bind lines arrived as {got!r} — each action's belong under that "
        "action's own name, because that is the key a call is looked up by"
    )


def test_an_action_that_binds_nothing_is_absent_rather_than_present_and_empty() -> None:
    """"No bind lines" and "an empty bind block" must not become the same fact.

    `_bound_args` reads `""` for a call that names no action, so an entry that
    exists and is empty is a different claim from no entry at all. The same
    guard is what stops a `bind:` written as something other than a map from
    being walked as one — a half-finished line becoming an exception deep in a
    run instead of nothing at this boundary.
    """
    doc = workspace(
        {"uses": ["payments"]},
        tools={
            "payments": {
                "description": "Where refunds are issued.",
                "connect": "pay-server",
                "actions": {
                    "issue-refund": {"takes": {"amount": "money"}, "bind": {}},
                    # Not a map: the commonest half-finished `bind:` there is.
                    "look-up-order": {"takes": {"order-number": "text"}, "bind": "customer-id"},
                },
            }
        },
    )
    got = AgentSpec.from_document(doc, "desk").tools[0].binds
    assert got == {}, (
        f"an action with nothing bound arrived as {got!r}, which says there are "
        "bind lines here when there are none"
    )


def test_a_text_field_arrives_without_the_whitespace_around_it() -> None:
    """A block written with a blank line under it is the same document as one without.

    YAML block scalars carry their trailing newline and folder entries carry
    whatever the file ended with, so the untrimmed form is what an author
    normally produces. Two ports comparing system messages byte for byte
    disagree on exactly this, and so does anything that asks whether a field was
    written at all.
    """
    spec = spec_of({"instructions": "\n  Be exact and quote the policy.\n\n", "name": " Desk \n"})
    assert spec.instructions == "Be exact and quote the policy.", repr(spec.instructions)
    assert spec.name == "Desk", repr(spec.name)


def test_a_field_written_as_a_folder_arrives_as_paragraphs_with_a_blank_line_between() -> None:
    """*"A directory is a field; a field may be a directory"* — and the join is part of it.

    `_text`'s own reason: the entries *"are separate paragraphs of one
    document"*. Run together with a single newline they are one paragraph, so
    *"Start with one file; split it up when it gets long. Nothing else
    changes."* — the headline promise of both READMEs — stops being true the
    moment somebody splits the file.
    """
    one_file = "Check the policy first.\n\nThen decide.\n"
    as_folder = {"1-check.md": "Check the policy first.\n", "2-decide.md": "  Then decide.  "}
    assert spec_of({"instructions": one_file}).instructions == (
        spec_of({"instructions": as_folder}).instructions
    ), "splitting one field into a folder changed the document"
    assert spec_of({"instructions": as_folder}).instructions == (
        "Check the policy first.\n\nThen decide."
    ), repr(spec_of({"instructions": as_folder}).instructions)
