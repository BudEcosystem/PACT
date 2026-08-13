"""A `connect:` tool, as something `harness.run` can actually execute (M5 W3).

`mcp_bridge` answers *"may this connection be opened, and does the server
publish what was reviewed?"* and hands a host a toolset for somebody else's
stack. This answers the one question left after that: **what does the harness
call when the model asks for `payments`?**

The shape is `harness.ToolFn` — `Callable[[dict], str]` — because that is the
seam the harness already has, and giving it a second one would be the run path
gaining an MCP client. It must not: invariant P-1 keeps an adapter to the loaded
document, and AD-43 says PACT neither launches nor sandboxes a runtime-owned
server. So a HOST builds the clients, calls this, and passes the result to
`harness.run(tool_impls=…)`. Nothing in `src/` calls it, and nothing should.

## The three decisions this file makes, and why each is here rather than there

**A tool whose server has no client is ABSENT from the result, not present with
an apology.** The harness reads `call.name in tool_impls` to decide whether a
call CAN run, and that decision governs the at-most-once ledger: `hold` claims a
`same-request-key:` before the tool is reached, deliberately, because a call that
ran and then timed out may still have moved money. A stub that accepted the call
and returned *"no client for this server"* would spend that key for a call that
provably did nothing — and the model's next turn would read that the refund
"already ran in this run" when nothing was sent anywhere. Absence is the honest
state and the harness already has words for it.

**The ACTION becomes the tool name on the wire.** A PACT tool with an `actions:`
block is offered to the model as ONE tool with an `action:` argument
(`ir._takes`), and an MCP server publishes one tool per operation — which is the
shape `mcp_bridge.check_against_authored` already documents, keyed by *"the name
the server publishes"*. So `payments` + `action: issue-refund` is `tools/call`
for `issue-refund`, and `action` is not sent as an argument because it is PACT's
way of naming which call this is, not one of the author's `takes:` lines.

**An action the author did not declare never reaches the wire.**
`examples/refund-desk/tools/payments.yaml` writes it in as many words above its
`actions:` block — *"The only actions this agent may call. Anything else on the
server is refused."* Until this file, nothing on the executing side enforced it:
the model was shown `one of look-up-order, issue-refund` and a model that asked
for `delete-account` would have had it posted to the payments server. The
declared set is read from the argument list the model was SHOWN, so it is the
author's own line and not a second copy of it.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from ..harness import ToolFn
from ..ir import AgentSpec, ToolSpec
from ..questions import ACTION, Shape
from .client import Called, Client

__all__ = ["tool_impls_for"]


def tool_impls_for(
    spec: AgentSpec,
    clients: Mapping[str, Client],
    *,
    answer_input: "Callable[[str, Mapping[str, Any]], Any] | None" = None,
    input_rounds: int = 1,
) -> dict[str, ToolFn]:
    """The agent's `connect:` tools, as implementations `harness.run` can call.

    `clients` is keyed by SERVER — the `resources:` key, which is what a
    `connect:` line names, what `mcp_bridge` groups connections by, and the name
    a person's `asks-to-connect:` consent is granted under. Keyed by server and
    not by tool because a connection is a property of the server: two tools
    reaching `zendesk-server` are one client and one yes.

    Only tools whose server is in `clients` appear in the result. A host that
    resolved three of four endpoints, or was refused consent for one, passes
    three clients and the fourth tool is simply not implemented here — which is
    the state `harness.run` already has words for and the state the at-most-once
    ledger needs (see this module's docstring).

    `answer_input` is the MRTR half. A server on `2026-07-28` cannot send a
    request of its own; it answers `input_required` and waits to be asked again
    with the answers. PACT's own way of reaching a person is to PARK the run, so
    the default here is `None` — the call comes back as a sentence saying what
    the server wants, and the host decides. A host that CAN answer in-line (it
    has the person, or the answer is a machine fact) passes a callable and gets
    at most `input_rounds` retries. Bounded on purpose: an unbounded loop is a
    server able to keep a run alive forever, which is a ceiling nobody wrote.
    """
    made: dict[str, ToolFn] = {}
    for tool in spec.tools:
        reach = tool.reaches
        if reach is None or reach.kind != "connect" or not reach.value:
            # `url:` and `says:` are the other two ways a tool reaches
            # (`ir.WAYS_A_TOOL_REACHES`) and neither is an MCP server; a tool
            # with no reach line at all is refused by
            # `crates/pact-loader/src/reach.rs` at check time. Skipped rather
            # than guessed at, because a reader that assumed `connect:` would
            # post a refund to a server nobody wrote down.
            continue
        client = clients.get(reach.value)
        if client is None:
            continue
        made[tool.name] = _implementation(tool, reach.value, client, answer_input, input_rounds)
    return made


def _implementation(
    tool: ToolSpec,
    server: str,
    client: Client,
    answer_input: "Callable[[str, Mapping[str, Any]], Any] | None",
    input_rounds: int,
) -> ToolFn:
    """One tool's `ToolFn`, closed over the client its `connect:` line names."""
    declared = _declared_actions(tool)

    def call_it(args: dict[str, Any]) -> str:
        name, sending, refusal = _what_to_send(tool, server, args, declared)
        if refusal:
            # "not done", which is the word the harness already uses for a call
            # that was DECIDED rather than attempted — a rule that stopped it, a
            # rule that sent the run elsewhere. The model reads why on its next
            # turn instead of finding that the thing it asked for never happened
            # and nothing says so (T7).
            return refusal

        called = client.call(name, sending)
        for _ in range(max(0, input_rounds)):
            if called.complete or answer_input is None:
                break
            answers = _gathered(called, answer_input)
            if not answers:
                break
            # A NEW request, carrying the server's own `requestState` back
            # untouched. Not a resumption: there is no session, which is why
            # this survives the process ending between the two.
            called = client.call(
                name, sending, answers=answers, request_state=called.request_state
            )

        if not called.complete:
            return _still_waiting(called, name, server)
        if called.is_error:
            # The server's own `isError`, not an exception. MCP puts a tool's
            # own failure in the result *"otherwise the LLM would not be able to
            # see that an error occurred and self-correct"*, and `harness._call_
            # tool` says the same thing about a tool that raises: a failure is
            # data. The word is `error:` because that is the vocabulary the
            # harness already hands a model for a call that did not work.
            return f"error: {name!r} failed at {server!r}: {called.text}"
        return called.text

    return call_it


def _what_to_send(
    tool: ToolSpec,
    server: str,
    args: Mapping[str, Any],
    declared: "tuple[str, ...] | None",
) -> "tuple[str, dict[str, Any], str]":
    """`(the tool name the server publishes, its arguments, or why not)`.

    The arguments go over unchanged, and that is a contract rather than
    laziness: `mcp_bridge.check_against_authored` holds the author's `takes:`
    names against the server's published `inputSchema` properties and reports
    every difference in both directions, so the two ARE the same names or a host
    was told before the run. A renaming layer here would be a second opinion
    about what an argument is called, and the first thing it would do is hide the
    drift the check exists to find.

    The `bind:` arguments are already in `args`: `harness.run` merges them before
    the tool is reached, which is the whole point of the field — measured on the
    worked example, `payments` received `{order-number, amount, action}` and
    never `customer-id`, so the identity of whoever the run was for never
    reached the call.
    """
    sending = {str(k): v for k, v in args.items() if k != ACTION}
    if declared is None:
        # No `actions:` block: the tool IS the operation, and its own name is
        # what the server publishes.
        return (tool.name, sending, "")

    action = str(args.get(ACTION) or "").strip()
    if not action:
        # The harness reaches here whenever a model omits the argument it was
        # shown. Guessing — "there is only one action, it must be that one" —
        # would post a refund because nobody said not to.
        return (
            "",
            {},
            f"not done: `{tool.name}` does not say which action it is. Nothing "
            f"was sent to `{server}`. Ask again with `{ACTION}` set to one of: "
            f"{', '.join(declared)}.",
        )
    if action.lower() not in {a.lower() for a in declared}:
        return (
            "",
            {},
            f"not done: `{action}` is not an action `{tool.name}` declares, so "
            f"nothing was sent to `{server}`. The author wrote: "
            f"{', '.join(declared)}.",
        )
    return (action, sending, "")


def _declared_actions(tool: ToolSpec) -> "tuple[str, ...] | None":
    """The actions the author wrote, or `None` for a tool that has none.

    Read off `parameters[ACTION]`, which is the line `ir._takes` builds — `one
    of look-up-order, issue-refund` — and therefore the exact set the MODEL was
    shown. A second walk of the document would be a second copy that can
    disagree with what the model saw, and the disagreement would show up as a
    call refused for naming an action the model had been offered.

    `None` and not `()` because the two mean opposite things: a tool with no
    `actions:` block accepts every call to it under its own name, and a tool
    with an unreadable action line is not one that declares nothing.
    """
    written = tool.parameters.get(ACTION)
    if not written:
        return None
    try:
        shape = Shape.parse(written)
    except Exception:  # noqa: BLE001 — a shape PACT cannot parse is not a refusal
        # An author who wrote `action: text` in a `takes:` block owns that key
        # (`_takes` uses `setdefault`), and this cannot know what is allowed.
        # Refusing every call on a line it cannot read would be the instrument
        # reporting its own limit as the author's mistake.
        return None
    return shape.choices if shape.kind == "one-of" and shape.choices else None


def _gathered(
    called: Called, answer_input: "Callable[[str, Mapping[str, Any]], Any]"
) -> dict[str, Any]:
    """The host's answers to what the server asked for, under the server's keys.

    Every key or none. The MRTR retry says *"for each key in the response's
    `inputRequests` field, the same key must appear here"*, so a partial set is
    a request the server will refuse or, worse, answer with the missing half
    guessed. A host that cannot answer one of them has not answered.
    """
    if not called.needs:
        return {}
    answers: dict[str, Any] = {}
    for key, asked in called.needs.items():
        try:
            said = answer_input(str(key), asked if isinstance(asked, Mapping) else {})
        except Exception:  # noqa: BLE001 — a host that cannot answer has answered
            return {}
        if said is None:
            return {}
        answers[str(key)] = said
    return answers


def _still_waiting(called: Called, name: str, server: str) -> str:
    """What the model is told when the server wants more and nobody answered.

    Named, so the sentence says which input the server is missing rather than
    that something went wrong. `input_required` is not a failure — the call has
    not happened yet — and reporting it as one would send the model looking for a
    fault that is not there.
    """
    wanted = ", ".join(f"`{k}`" for k in sorted(called.needs)) or "something it did not name"
    return (
        f"not done: `{server}` will not run `{name}` until it is given more — it "
        f"asked for {wanted}. Nothing has happened at the server yet, and this "
        f"run has no way to answer that here."
    )
