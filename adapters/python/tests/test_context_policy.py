"""The context policy — what to do when the conversation outgrows the model (G3).

This is the largest gap between PACT and the closest prior art. Eve answers the
question once, in code: one ordered list of heuristics with a single private
entry, a recent window of literally 10, reasoning discarded on every pass, and
no way at all to mark anything as must-keep. Every test below is a property an
author gets *because* those four constants became fields.

The tests are named as the guarantee they hold. Where one restates something Eve
does correctly, it says so — the point is not that Eve is wrong everywhere, it
is that what it gets right is unreachable and what it gets wrong is unfixable.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.context_policy import (  # noqa: E402
    CHARS_PER_TOKEN,
    ContextPolicy,
    Message,
    Part,
    PartKind,
    PinKind,
    Pins,
    StillTooLong,
    Tidier,
    estimate,
    from_history,
    parse_amount,
    resolve_pin,
    split_forward,
    to_history,
)
from pact_adapters.resolve import default_model, load_catalogue, window_of  # noqa: E402
from pact_adapters.transports.anthropic_transport import AnthropicTransport  # noqa: E402
from pact_adapters.transports.autogen_transport import AutoGenTransport  # noqa: E402
from pact_adapters.transports.langchain_transport import LangChainTransport  # noqa: E402
from pact_adapters.transports.langgraph_transport import LangGraphTransport  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402
from pact_adapters.transports.openai_agents_transport import OpenAIAgentsTransport  # noqa: E402
from pact_adapters.transports.pydantic_ai_transport import PydanticAITransport  # noqa: E402

EXAMPLE = Path(__file__).resolve().parents[3] / "examples" / "refund-desk"

#: The transports a spec can actually be lowered onto, each bound to a model.
#: `ReferenceTransport` is deliberately absent: it is the script with no
#: framework and no model, so it has no window, and the run that uses it is the
#: OTHER half of this guarantee — held below in its own test rather than
#: parametrised in beside the six that can answer.
TRANSPORTS = {
    "pydantic-ai": PydanticAITransport,
    "langgraph": LangGraphTransport,
    "langchain": LangChainTransport,
    "autogen": AutoGenTransport,
    "openai-agents": OpenAIAgentsTransport,
    "anthropic": AnthropicTransport,
}


# ────────────────────────────────────────────────────────────────── fixtures


def say(role: str, text: str, **kw) -> Message:
    return Message(role=role, parts=(Part(PartKind.TEXT, text),), **kw)


def thought(text: str, thinking: str) -> Message:
    return Message(
        role="assistant",
        parts=(Part(PartKind.TEXT, text), Part(PartKind.THINKING, thinking)),
    )


def called(tool: str) -> Message:
    return Message(role="assistant", parts=(Part(PartKind.TOOL_CALL, "", tool),))


def returned(tool: str, text: str) -> Message:
    return Message(
        role="tool",
        parts=(Part(PartKind.TOOL_RESULT, text, tool),),
        labels=frozenset({f"from:{tool}"}),
    )


def joined(summary, previous):
    """A deterministic summariser. Air-gapped (D17): a test that needed a live
    model would be measuring sampling noise, not the policy."""
    body = " | ".join(m.text()[:20] for m in summary)
    return f"EARLIER: {previous + ' >> ' if previous else ''}{body}"


def policy(**over) -> ContextPolicy:
    doc = {"context-policies": {"p": {"when-full": "80%", **over}}}
    return ContextPolicy.from_document(doc, "p")


# ──────────────────────────────────────────────────── reading what was written


def test_a_policy_written_in_plain_yaml_needs_no_code_to_run() -> None:
    """D14's bar. Every sentence in the worked example resolves to something
    executable without the author writing a line of anything."""
    doc = json.loads((EXAMPLE / "_loaded.json").read_text()) if False else _example_doc()
    p = ContextPolicy.from_document(doc, "long-threads", source=EXAMPLE)
    assert p.errors == (), "\n".join(str(e) for e in p.errors)
    assert [s.what for s in p.steps] == [
        "shorten-long-results", "summarise-older", "drop-parts", "keep-recent-only",
    ]
    assert p.when_full == 0.85
    assert p.if_it_still_does_not_fit == "ask-a-person"


def test_a_pin_that_names_something_the_workspace_has_resolves_to_it() -> None:
    """`anything the payments tool said` is a tool in this tree. Matching by name
    rather than by words is what makes the pin survive rewording of the result."""
    p = ContextPolicy.from_document(_example_doc(), "long-threads", source=EXAMPLE)
    kinds = {pin.phrase: (pin.kind, pin.target) for pin in p.pins.pins}
    assert kinds["anything the payments tool said"] == (PinKind.SOURCE, "payments")
    assert kinds["anything a person approved or declined"] == (PinKind.LABEL, "approval")
    assert kinds["the customer's original request"] == (PinKind.LABEL, "first-request")


def test_a_pin_naming_a_thing_that_is_never_a_message_says_so_rather_than_matching_nothing() -> None:
    """The failure `always-keep:` exists to prevent, arriving through the check
    meant to catch it.

    `from:<name>` is stamped in exactly one place — on a `role: "tool"` message —
    so only a TOOL or a TEAMMATE can ever be the source of anything. A pin naming
    a skill, a connected system or a policy resolved to `SOURCE` anyway, matched
    a label nothing stamps, kept nothing, and suppressed the words fallback that
    would at least have kept something. The worked example's own first pin was
    exactly this, and nobody was warned.
    """
    doc = _example_doc()
    for phrase, names in (
        ("the refund policy", "refund-policy"),
        ("the payments server", "payments-server"),
        # Was `("the customer-data rules", "customer-data")` — the redaction,
        # back when it was a NAMED document in `redactions/` (R61). What must
        # never leave is one unnamed setting of the workspace now, so there is no
        # name to pin at and nothing for this case to be about. The tidying rules
        # are the same shape of mistake on a section that still has names, and
        # they carry the same reason string the redaction did. Not `approvals`,
        # which reads as the LABEL `approval` and resolves before any of this.
        ("the long-threads rules", "long-threads"),
    ):
        pin, problem = resolve_pin(phrase, doc, "long-threads", EXAMPLE)
        if pin.kind is PinKind.SOURCE:
            # A phrase can legitimately reach a real tool by fuzzy match — the
            # server name contains the tool name. That is a working pin.
            assert pin.target in doc["tools"], (phrase, pin.target)
            continue
        assert pin.kind is PinKind.PHRASE, phrase
        assert problem is not None, phrase
        assert "is-not-a-message" in problem.rule, problem.rule
        assert "anything payments said" in problem.fix, problem.fix


def test_a_pin_that_names_nothing_still_works_and_says_so() -> None:
    """The dangerous case: a sentence that quietly matches nothing. It degrades
    to a words match, and the author is told, with the file, the line and a list
    of things they could have typed instead."""
    pin, problem = resolve_pin(
        "the quarterly revenue forecast", _example_doc(), "long-threads", EXAMPLE
    )
    assert pin.kind is PinKind.PHRASE
    assert problem is not None
    assert problem.file == "context-policies/long-threads.yaml"
    assert problem.line == 1, "an unknown phrase is not in the file, so line 1 is honest"
    assert "does not name anything this workspace has" in problem.message
    assert "`anything payments said`" in problem.fix, problem.fix


def test_a_pin_diagnostic_names_the_line_it_was_written_on() -> None:
    """Where, what, why, how — the four parts `pact-diag` requires, from the
    half of the system written in Python as well as the half written in Rust."""
    pin, problem = resolve_pin(
        "the refund policy", {"skills": {}}, "long-threads", EXAMPLE
    )
    assert problem is not None
    assert problem.file == "context-policies/long-threads.yaml"
    written = (EXAMPLE / problem.file).read_text().splitlines()
    assert "the refund policy" in written[problem.line - 1], written[problem.line - 1]
    rendered = str(problem)
    assert f"  --> context-policies/long-threads.yaml:{problem.line}:1" in rendered
    assert "  fix: " in rendered and "  rule: context-policy/" in rendered


def test_an_unreadable_amount_is_refused_with_something_typeable() -> None:
    amount, problem = parse_amount("a bit shorter", "p", None, "keep-recent-only")
    assert amount is None
    assert problem is not None and problem.severity == "error"
    assert "does not say how much to leave" in problem.message
    assert "`down-to: 2000 characters`" in problem.fix
    assert "`down-to: the last 10 messages`" in problem.fix


def test_drop_parts_without_a_kind_of_content_is_refused() -> None:
    """The one way the per-part rule can be written meaninglessly. Eve cannot
    reach this mistake because it cannot reach the feature."""
    p = policy(**{"then": [{"what": "drop-parts", "applies-to": "the boring bits"}]})
    assert len(p.errors) == 1
    assert "is not a kind of content" in p.errors[0].message
    assert "`the model's own thinking`" in p.errors[0].fix


@pytest.mark.parametrize(
    "raw,expect",
    [
        ("2000 characters", ("characters", 2000)),
        ("the last 10 messages", ("messages", 10)),
        ("4000 tokens", ("characters", 4000 * CHARS_PER_TOKEN)),
        ("2k tokens", ("characters", 2000 * CHARS_PER_TOKEN)),
        ("everything since the last approval", ("landmark", "the last approval")),
        ("since the customer's original request", ("landmark", "the customer's original request")),
    ],
)
def test_how_much_to_leave_can_be_a_size_a_count_or_a_landmark(raw, expect) -> None:
    """Eve has one form and it is the number 10. A count is a different amount
    of conversation every run; a landmark is the same one every run."""
    amount, problem = parse_amount(raw, "p", None, "keep-recent-only")
    assert problem is None
    assert getattr(amount, expect[0]) == expect[1]


# ───────────────────────────────────────────────────────── pinning: the fix


def test_a_recorded_approval_survives_tidying_that_drops_everything_else() -> None:
    """The expensive kind of loss, and the reason `always-keep:` exists. There
    is no equivalent anywhere in Eve: a pending-approval record is exactly as
    droppable as small talk."""
    p = policy(
        **{
            "always-keep": ["anything a person approved"],
            "then": [{"what": "keep-recent-only", "down-to": "the last 2 messages"}],
        }
    )
    convo = [
        say("user", "hi " * 200),
        say("assistant", "a person approved a 40 GBP refund", labels=frozenset({"approval"})),
        say("user", "filler " * 200),
        say("assistant", "filler " * 200),
        say("user", "and now?"),
    ]
    out = Tidier(p, budget_tokens=200).apply(convo)
    kept = [m.text() for m in out.messages]
    assert any("a person approved" in t for t in kept), kept
    assert out.pinned == 1


def test_a_pinned_message_is_not_shortened_either() -> None:
    """Pinning outranks every step, not just the dropping ones. A truncated
    approval record is a lost approval record."""
    p = policy(
        **{
            "always-keep": ["anything a person approved"],
            "then": [{"what": "shorten-long-results", "down-to": "50 characters"}],
        }
    )
    receipt = Message(
        role="tool",
        parts=(Part(PartKind.TOOL_RESULT, "APPROVED " + "x" * 500, "payments"),),
        labels=frozenset({"approval", "from:payments"}),
    )
    convo = [called("payments"), receipt, returned("zendesk", "y" * 500), called("zendesk")]
    out = Tidier(p, budget_tokens=10).apply(convo)
    texts = [m.text() for m in out.messages]
    assert any(len(t) > 400 and t.startswith("APPROVED") for t in texts), texts
    assert any("shortened by PACT" in t for t in texts), "the unpinned one was shortened"


def test_pins_that_cannot_all_fit_are_reported_not_silently_dropped() -> None:
    """Structural honesty (T7). If what the author protected is itself over
    budget, saying so is the only correct move — dropping one of them without
    mentioning it is how an approval disappears."""
    p = policy(
        **{
            "always-keep": ["anything a person approved"],
            "then": [{"what": "keep-recent-only", "down-to": "the last 1 messages"}],
        }
    )
    convo = [
        say("assistant", "approved " * 300, labels=frozenset({"approval"})),
        say("assistant", "approved again " * 300, labels=frozenset({"approval"})),
        say("user", "?"),
    ]
    out = Tidier(p, budget_tokens=50).apply(convo)
    assert any("`always-keep` protects is already" in n for n in out.notes), out.notes
    assert len([m for m in out.messages if "approved" in m.text()]) == 2


# ──────────────────────────────────────────────── reasoning: the per-part rule


def test_thinking_is_kept_unless_a_rule_says_to_drop_it() -> None:
    """The headline fix. Eve's `assistantMessageText` keeps text parts and
    discards reasoning on every single compaction, with no setting. Here a
    policy that never mentions thinking never loses any."""
    p = policy(**{"then": [{"what": "shorten-long-results", "down-to": "10 characters"}]})
    convo = [thought("done", "because the receipt was dated 3 March"), returned("z", "x" * 900)]
    out = Tidier(p, budget_tokens=20).apply(convo)
    survived = [pt.text for m in out.messages for pt in m.parts if pt.kind is PartKind.THINKING]
    assert survived == ["because the receipt was dated 3 March"]


def test_thinking_is_dropped_when_a_rule_names_it() -> None:
    p = policy(**{"then": [{"what": "drop-parts", "applies-to": "the model's own thinking"}]})
    convo = [thought("done " * 100, "long reasoning " * 100), say("user", "ok")]
    out = Tidier(p, budget_tokens=60).apply(convo)
    assert PartKind.THINKING not in {pt.kind for m in out.messages for pt in m.parts}
    assert any("done" in m.text() for m in out.messages), "the answer itself must survive"


def test_the_same_rule_can_name_any_kind_of_content_not_just_thinking() -> None:
    """It is a per-*part* rule, not a reasoning switch. Pictures are the case
    that matters for D16: a vision agent's history is mostly images."""
    p = policy(**{"then": [{"what": "drop-parts", "applies-to": "pictures"}]})
    convo = [
        Message("user", (Part(PartKind.TEXT, "see this"), Part(PartKind.IMAGE, "b" * 4000))),
        say("assistant", "seen"),
    ]
    out = Tidier(p, budget_tokens=100).apply(convo)
    assert PartKind.IMAGE not in {pt.kind for m in out.messages for pt in m.parts}
    assert out.messages[0].text() == "see this"


# ──────────────────────────────────────── the parts of Eve worth keeping


def test_the_tail_never_opens_on_a_tool_result_whose_call_was_dropped() -> None:
    """Kept from Eve verbatim (`compaction.ts:464-467`): every provider rejects
    a tool_result with no preceding tool_use, so the split snaps forward."""
    convo = [say("user", "go"), called("zendesk"), returned("zendesk", "ticket"), say("user", "?")]
    older, recent = split_forward(convo, keep=2)
    assert recent[0].role != "tool", [m.role for m in recent]
    assert [m.role for m in recent] == ["user"]
    assert [m.role for m in older] == ["user", "assistant", "tool"]


def test_a_tool_call_left_without_its_result_is_repaired_too() -> None:
    """Both directions. Eve fixes the orphaned *result* structurally and the
    orphaned *call* by blanket-stripping every tool-call part — which is why
    dropping reasoning is welded to dropping tool calls there and separate
    here."""
    p = policy(**{"then": [{"what": "drop-parts", "applies-to": "tool results"}]})
    convo = [say("user", "go " * 200), called("zendesk"), returned("zendesk", "t" * 900)]
    out = Tidier(p, budget_tokens=60).apply(convo)
    kinds = {pt.kind for m in out.messages for pt in m.parts}
    assert PartKind.TOOL_RESULT not in kinds
    assert PartKind.TOOL_CALL not in kinds, "a call with no result is not sendable"
    assert any("repaired" in n for n in out.notes), out.notes


def test_a_tool_result_left_without_its_call_is_repaired_the_same_way() -> None:
    """The other direction the test above claims and did not exercise.

    `_repair_pairing`'s docstring says BOTH, and only one arm ran: dropping
    `tool results` orphans the CALL, so the whole test lived on the
    `p.kind is PartKind.TOOL_CALL and p.pairs_on not in have_results` branch and
    its mirror could be deleted with the suite still green. Swapping one word of
    the author's own `applies-to:` line is what puts the other branch under
    load — the orphan now points the other way, and it is the direction every
    provider rejects outright rather than merely dislikes.

    Written as the author writes it, so this is also a check that the two
    spellings of `applies-to:` are two spellings of one step and not two steps.
    """
    p = policy(**{"then": [{"what": "drop-parts", "applies-to": "tool calls"}]})
    convo = [say("user", "go " * 200), called("zendesk"), returned("zendesk", "t" * 900)]
    out = Tidier(p, budget_tokens=60).apply(convo)
    kinds = {pt.kind for m in out.messages for pt in m.parts}
    assert PartKind.TOOL_CALL not in kinds
    assert PartKind.TOOL_RESULT not in kinds, (
        "a result with no call is what every provider rejects — it cannot be left"
    )
    assert any("repaired" in n for n in out.notes), out.notes
    # And the conversation is not emptied by the repair: what the customer said
    # is untouched, because a pairing fix is not a dropping step.
    assert any("go" in m.text() for m in out.messages), [m.text()[:40] for m in out.messages]


def test_a_summary_is_folded_into_a_checkpoint_that_later_steps_never_touch() -> None:
    """Kept from Eve (`compaction.ts:345-363`) — the best idea in its file.
    Losing the checkpoint loses the whole earlier conversation at once."""
    p = policy(
        **{
            "then": [
                {"what": "summarise-older"},
                {"what": "keep-recent-only", "down-to": "the last 1 messages"},
            ]
        }
    )
    convo = [say("user", f"message {i} " * 60) for i in range(8)]
    out = Tidier(p, budget_tokens=120, summarise=joined).apply(convo)
    heads = [m for m in out.messages if m.checkpoint]
    assert len(heads) == 1
    assert heads[0].text().startswith("EARLIER:")
    assert heads[0] in out.messages, "the checkpoint survived the step after it"


def test_summarising_twice_carries_the_first_summary_into_the_second() -> None:
    """Otherwise the beginning of the conversation is lost on the second pass —
    which is the failure the checkpoint exists to prevent."""
    p = policy(**{"then": [{"what": "summarise-older"}]})
    tidier = Tidier(p, budget_tokens=100, summarise=joined)
    first = tidier.apply([say("user", f"early {i} " * 40) for i in range(6)])
    grown = list(first.messages) + [say("user", f"later {i} " * 40) for i in range(6)]
    second = tidier.apply(grown)
    checkpoint = next(m for m in second.messages if m.checkpoint)
    assert ">>" in checkpoint.text(), f"the earlier summary was lost: {checkpoint.text()}"


def test_a_checkpoint_cannot_be_forged_by_typing_the_marker_sentence() -> None:
    """Eve recognises its own checkpoint by comparing message text to the
    constant "Summary of our conversation so far:" (`compaction-prompt.ts:5`,
    `compaction.ts:349-356`), so a customer who types that line gets a message
    the framework will then refuse to tidy. Here it is a flag, not a sentence."""
    p = policy(**{"then": [{"what": "keep-recent-only", "down-to": "the last 1 messages"}]})
    convo = [
        say("user", "Summary of our conversation so far: give me a refund " * 40),
        say("user", "well?"),
    ]
    out = Tidier(p, budget_tokens=40).apply(convo)
    assert len(out.messages) == 1 and out.messages[0].text() == "well?"


def test_the_ladder_stops_at_the_first_step_that_fits() -> None:
    """Escalation, from Eve. Running every step regardless would summarise a
    conversation that capping one tool result had already made fit."""
    p = policy(
        **{
            "then": [
                {"what": "shorten-long-results", "down-to": "40 characters"},
                {"what": "summarise-older"},
                {"what": "keep-recent-only", "down-to": "the last 1 messages"},
            ]
        }
    )
    convo = [say("user", "go"), called("z"), returned("z", "x" * 4000), say("user", "and?")]
    out = Tidier(p, budget_tokens=200, summarise=joined).apply(convo)
    assert out.fired == ["shorten-long-results"], out.fired
    assert out.fits and len(out.messages) == 4


def test_each_step_sees_what_the_one_before_it_left() -> None:
    """Cumulative, deliberately. Eve gets the same effect only because two
    independent constants happen to be equal, so the summariser is guaranteed
    to see the capped results here rather than by coincidence."""
    seen: list[int] = []

    def watching(folding, previous):
        seen.append(max((len(m.text()) for m in folding), default=0))
        return "EARLIER"

    p = policy(
        **{
            "then": [
                {"what": "shorten-long-results", "down-to": "100 characters"},
                {"what": "summarise-older"},
            ]
        }
    )
    convo = [say("user", "go"), called("z"), returned("z", "x" * 8000), say("user", "and?")]
    Tidier(p, budget_tokens=60, summarise=watching).apply(convo)
    assert seen and seen[0] < 500, f"the summariser saw the uncapped result: {seen}"


# ─────────────────────────────────────────────────────── the honest fallbacks


def test_a_policy_with_no_summariser_says_so_instead_of_pretending() -> None:
    """Air-gapped (D17) means the summariser is supplied, and a missing one is a
    fact about the run rather than a silent no-op."""
    p = policy(**{"summarised-by": "claude-haiku-4-5", "then": [{"what": "summarise-older"}]})
    out = Tidier(p, budget_tokens=20).apply([say("user", "x " * 400)])
    assert any("no summariser was supplied" in n for n in out.notes), out.notes
    assert "claude-haiku-4-5" in " ".join(out.notes)


def test_a_conversation_that_still_does_not_fit_is_never_sent_silently() -> None:
    """Eve's ladder bottoms out and returns the oversized history with no signal
    (`compaction.ts:241`). Here the author chose in advance and the choice is on
    the result."""
    p = policy(**{"always-keep": ["anything a person approved"], "then": []})
    convo = [say("assistant", "approved " * 500, labels=frozenset({"approval"}))]
    out = Tidier(p, budget_tokens=50).apply(convo)
    assert out.outcome == "used-it-anyway"
    assert out.fits is False
    assert any("still" in n and "over" in n for n in out.notes), out.notes


def test_stop_means_stop_and_is_a_typed_refusal() -> None:
    p = policy(**{"if-it-still-does-not-fit": "stop", "then": []})
    with pytest.raises(StillTooLong, match="if-it-still-does-not-fit: stop"):
        Tidier(p, budget_tokens=10).apply([say("user", "x " * 500)])


def test_tidying_a_conversation_that_already_fits_changes_nothing() -> None:
    """The mechanism must cost nothing when it is not needed."""
    p = policy(**{"then": [{"what": "keep-recent-only", "down-to": "the last 1 messages"}]})
    convo = [say("user", "short"), say("assistant", "also short")]
    out = Tidier(p, budget_tokens=10_000).apply(convo)
    assert out.outcome == "not-needed" and out.messages == convo and out.fired == []


# ─────────────────────────────────────────────────────────── the landmark form


def test_a_landmark_keeps_the_same_amount_of_conversation_every_time() -> None:
    """The reason `down-to:` is not a number. Two runs whose messages are
    different lengths keep the same *part* of the conversation."""
    p = policy(
        **{"then": [{"what": "keep-recent-only", "down-to": "everything since the last approval"}]}
    )
    for filler in (20, 400):
        convo = [
            say("user", "hello " * filler),
            say("assistant", "approved", labels=frozenset({"approval"})),
            say("user", "thanks " * filler),
            say("user", "one more thing"),
        ]
        out = Tidier(p, budget_tokens=100).apply(convo)
        assert [m.text()[:8] for m in out.messages] == ["approved", "thanks t", "one more"], filler


def test_a_landmark_that_matches_nothing_keeps_everything() -> None:
    """The safe direction, and it is reported rather than assumed."""
    p = policy(**{"then": [{"what": "keep-recent-only", "down-to": "since the last approval"}]})
    convo = [say("user", f"m{i} " * 50) for i in range(5)]
    out = Tidier(p, budget_tokens=50).apply(convo)
    assert len(out.messages) == 5
    assert out.outcome == "used-it-anyway"


def test_a_window_can_be_measured_in_tokens_rather_than_messages() -> None:
    p = policy(**{"then": [{"what": "keep-recent-only", "down-to": "60 tokens"}]})
    convo = [say("user", f"m{i} " * 40) for i in range(10)]
    out = Tidier(p, budget_tokens=400).apply(convo)
    assert 0 < estimate(out.messages) <= 70, estimate(out.messages)
    assert len(out.messages) < 10


# ──────────────────────────────────────────────────────────── the round trip


def test_the_harness_history_survives_a_round_trip_through_tidying() -> None:
    history = [
        {"role": "user", "content": "refund please"},
        {"role": "assistant", "content": "checking", "tool_calls": ["zendesk"]},
        {"role": "tool", "name": "zendesk", "content": "lamp, broken"},
    ]
    back = to_history(from_history(history))
    assert [h["role"] for h in back] == ["user", "assistant", "tool"]
    assert back[1]["tool_calls"] == ["zendesk"]
    assert back[2]["name"] == "zendesk" and back[2]["content"] == "lamp, broken"


def test_a_pinned_tool_result_whose_call_was_tidied_away_survives_a_round_trip_as_text(
) -> None:
    """The repair has to survive being written back out and read in again.

    `_repair_pairing` rescues a pinned tool result whose call has gone by turning
    the PART into text — `always-keep` said keep it, and the call cannot be
    resurrected. Its own fifteen-line comment records what happened when the
    MESSAGE stayed `role: "tool"` alongside: `to_history` writes every part of a
    tool-role message as `{"role": "tool", "name": p.tool, ...}` and a TEXT
    part's `tool` is `""`, so the rescued receipt came out as
    `{'role': 'tool', 'name': '', 'content': 'PAID 40.00 USD'}` — which
    `from_history` reads straight back as a `TOOL_RESULT` pairing on nothing, and
    which the Anthropic transport turns into a `tool_result` block with no
    preceding `tool_use`. The exact orphan the function exists to prevent,
    manufactured by the repair itself, one hop later.

    That comment says it was measured and fixed, and deleting the fix
    (`role = m.role`) left the suite green — so what it records was held by
    nothing. Asserted through the round trip rather than on the object, because
    the object was always right: it is the trip out and back that was not.

    `user` rather than `assistant` is part of the guarantee. A tool result is
    something that arrived; attributing it to the model would let a pinned page
    of somebody else's text read as the assistant's own words.
    """
    p = policy(
        **{
            "always-keep": ["anything a person approved"],
            "then": [{"what": "drop-parts", "applies-to": "tool calls"}],
        }
    )
    receipt = Message(
        role="tool",
        parts=(Part(PartKind.TOOL_RESULT, "PAID 40.00 USD", "payments"),),
        labels=frozenset({"approval", "from:payments"}),
    )
    convo = [say("user", "refund " * 300), called("payments"), receipt]

    out = Tidier(p, budget_tokens=40).apply(convo)
    rescued = [m for m in out.messages if "PAID 40.00 USD" in m.text()]
    assert len(rescued) == 1, [m.text()[:30] for m in out.messages]
    assert rescued[0].role == "user", rescued[0].role
    assert rescued[0].kinds() == frozenset({PartKind.TEXT}), rescued[0].parts

    # Out to the harness's shape and back — the trip the run really makes,
    # because a parked run is resumed from a written history (D23).
    again = from_history(to_history(out.messages))
    survivor = [m for m in again if "PAID 40.00 USD" in m.text()]
    assert len(survivor) == 1, [m.text()[:30] for m in again]
    assert survivor[0].role == "user", (
        "the rescued receipt came back as a tool message, so the next thing to "
        "read this history sees a tool result with no call again"
    )
    assert PartKind.TOOL_RESULT not in survivor[0].kinds(), survivor[0].parts

    # And what the transports are actually handed carries no nameless tool entry,
    # which is the shape that becomes an orphaned `tool_result` block.
    written = to_history(out.messages)
    assert not [h for h in written if h.get("role") == "tool" and not h.get("name")], written


def test_a_mark_is_never_inferred_from_where_a_message_sits() -> None:
    """`the customer's original request` has to keep meaning the same message.
    A reader that decided `first-request` meant "the earliest user message I can
    see" would move the pin onto a later one the moment the real one was folded
    into a summary — and would still report a match."""
    marked = [
        {"role": "user", "content": "the original ask", "labels": ["first-request"]},
        {"role": "user", "content": "and another thing"},
    ]
    read = from_history(marked)
    assert read[0].labels == frozenset({"first-request"})
    assert read[1].labels == frozenset(), "the mark was invented for a later message"
    assert from_history(to_history(read))[1].labels == frozenset()


def test_the_run_marks_the_opening_request_so_a_pin_can_find_it() -> None:
    """The other half: the mark has to be put on by somebody. It is the run,
    once, at the point that knows."""
    from pact_adapters.harness import run
    from pact_adapters.ir import AgentSpec
    from pact_adapters.script import Script, Turn
    from pact_adapters.transports.mock import ReferenceTransport

    seen: list[dict] = []

    class Watching(ReferenceTransport):
        async def model_call(self, system, history, tools):
            seen.append(history[0])
            return await super().model_call(system, history, tools)

    spec = AgentSpec(name="a", description="d", instructions="i")
    asyncio.run(run(spec, Watching(Script([Turn("hi")])), "refund please"))
    assert seen[0]["labels"] == ["first-request"]
    assert Pins((_first_request_pin(),)).select(from_history(seen)) == frozenset({0})


def _first_request_pin():
    pin, problem = resolve_pin("the customer's original request", {}, "p", None)
    assert problem is None
    return pin


# ──────────────────────────────────────────────────── wired into the real loop


def test_the_model_is_shown_the_tidied_conversation_not_the_original() -> None:
    """Executes rather than decorates. This is the property that separates a
    context policy from a comment about one."""
    from pact_adapters.harness import ToolCall, run
    from pact_adapters.ir import AgentSpec, ToolSpec
    from pact_adapters.script import Script, Turn
    from pact_adapters.transports.mock import ReferenceTransport

    shown: list[int] = []

    class Watching(ReferenceTransport):
        async def model_call(self, system, history, tools):
            shown.append(len(json.dumps(history)))
            return await super().model_call(system, history, tools)

    spec = AgentSpec(
        name="Refund Desk", description="d", instructions="Decide refunds.",
        tools=(ToolSpec("zendesk", "read the ticket"),),
    )
    script = Script([Turn("checking", (ToolCall("zendesk", {}),)), Turn("done")])
    p = policy(**{"then": [{"what": "shorten-long-results", "down-to": "100 characters"}]})
    tidier = Tidier(p, budget_tokens=200, summarise=joined)

    out = asyncio.run(
        run(spec, Watching(script), "refund?", {"zendesk": lambda a: "x" * 9000}, tidy=tidier)
    )
    assert out.halted == "final"
    assert len(shown) == 2, shown
    assert shown[1] < 2000, f"the second call still carried the full result: {shown[1]}"
    assert out.tidyings and out.tidyings[0].fired == ["shorten-long-results"]


#: A ticket-system dump big enough to fill a small model's whole window on its
#: own. The size is the point rather than the content: most of a long agent
#: conversation is one or two large tool results, which is why
#: `shorten-long-results` is the first rung of the worked example's ladder.
LONG_TICKET = "2026-03-01 09:14 status unchanged; nothing new on this order. " * 145

#: What the stand-in model below can read at once — the whole raw ticket and the
#: line that fetched it, and nothing more. Derived from the ticket rather than
#: written as a number, so the two stay in the relationship the test is about:
#: the customer's own message is exactly what falls out of the window when
#: nothing tidies the conversation first.
WINDOW = len(LONG_TICKET) + 200

#: What the stand-in says when the request is no longer readable. It states
#: neither verdict on purpose, so `evals.check` scores it as the miss it is
#: rather than as a decline that would be right on half the cases by accident.
NOTHING_TO_GO_ON = (
    "I cannot see the customer's message in what I was given, "
    "so there is nothing here to go on."
)

#: The whole decision rule. Deliberately tiny: this test is not about how well
#: the stand-in decides, it is about whether it can still read the thing it
#: decides from. A judge or a live model here would measure sampling noise and
#: would need a network (D17).
FAULTY = ("cracked", "broken", "damaged", "faulty")


def _decides_from(request: str) -> str:
    """Answer one case the way the worked example's own suite expects it.

    It has to satisfy the SUITE, not only the `expect:` line — every rule under
    `evals.rules:` and every `must-also:` on the case reaches the grader now, and
    for a round none of them did: `rules_of()` kept only plain strings and all
    five of the example's rules are mappings, so this fixture was graded against
    an empty list while its own docstring claimed the deterministic grader.
    Writing the answers so they really pass is what makes the FAIL→PASS flip
    below mean what it says.
    """
    said = request.casefold()
    money = ", ".join(re.findall(r"\d+(?:\.\d+)?\s*(?:USD|GBP|EUR)", request))
    if any(word in said for word in FAULTY):
        extra = " Split back across both payment methods, gift card included." if "gift card" in said else ""
        return (
            "DECISION: approved. The item arrived faulty."
            + (f" Refund {money}." if money else "")
            + extra
        )
    if "personalised" in said or "printed with" in said or "dog's name" in said:
        return (
            "DECISION: declined. This was a personalised item made to order, and "
            "personalised items cannot be returned unless faulty."
        )
    if "fourth refund" in said or "different from all their previous" in said:
        return (
            "DECISION: declined. A person will review this request before anything "
            "is paid, because several details do not line up."
        )
    return "DECISION: declined. Nothing was wrong with it, and the 30 days have passed."


def _readable(history: list[dict], window: int) -> list[dict]:
    """The newest messages that fit in `window`, oldest dropped first.

    What actually happens when a model is handed more than it can hold: it does
    not fail cleanly, the front of the conversation stops being read. The
    opening ask is the oldest thing there, so it is the first thing to go —
    which is why `always-keep: the customer's original request` is a line in the
    worked example rather than a nicety.
    """
    room, kept = window, []
    for message in reversed(history):
        cost = len(json.dumps(message))
        if cost > room:
            break
        room -= cost
        kept.append(message)
    return list(reversed(kept))


#: What the stand-in model below says it can hold, in tokens. Under the
#: character window it truncates at, deliberately: a policy is measured against
#: what the model reports, and it has to bite before the provider silently drops
#: the front of the conversation. `Tidier` counts four characters to the token
#: (`CHARS_PER_TOKEN`), so 1200 tokens is about 4,800 characters against a
#: readable window of about 9,100.
BUDGET_TOKENS = 1200


def test_attaching_a_context_policy_changes_the_score_the_eval_suite_reports() -> None:
    """The bar AC-5.3 sets for loops, met for G3 and met through the scorer.

    Stated separately from the history-size measurement above because the two
    prove different things. That one shows the policy *ran* — the second model
    call carried fewer bytes than the first. This one shows the policy changed
    **what the system is judged to have done**: same authored cases, same
    deterministic grader, same model stand-in, and the only difference between
    the two arms is whether `context-policies/long-threads.yaml` was attached.
    A policy that ran and left the verdict alone would pass the first test and
    fail this one, and it is this one that says the mechanism is worth having.

    **The two arms differ by the author's line and nothing else.** For a round
    this test built the `Tidier` itself and passed it as `tidy=`, which measured
    the class and said nothing about the mechanism: `spec.context_policy` was
    resolved from the document and read by nobody, so `context-policy:
    long-threads` in the worked example tidied nothing unless a host wrote
    Python. The arms below are two `AgentSpec`s that differ in one field — the
    one the author types — and neither run is handed a tidier.

    Everything here is decidable offline (AC-4.5, D17): no judge, no live model.
    What the stand-in answers is a function of what it was handed, and what it
    was handed is the only thing the policy changes.
    """
    from pact_adapters.evals import Case, bar_of, check, rules_of, verdict
    from pact_adapters.harness import ToolCall, run
    from pact_adapters.ir import AgentSpec, ToolSpec

    doc = _example_doc()
    cases = Case.from_document(doc)
    written = ContextPolicy.from_document(doc, "long-threads", source=EXAMPLE)
    assert written.errors == (), "\n".join(str(e) for e in written.errors)

    def agent(policy: "ContextPolicy | None") -> AgentSpec:
        return AgentSpec(
            name="Refund Desk", description="d", instructions="Decide refunds.",
            tools=(ToolSpec("zendesk", "read the ticket"),),
            context_policy=policy,
        )

    class SmallWindow:
        """A model with a fixed context window, standing in deterministically."""

        name = "small-window"

        def __init__(self) -> None:
            #: One entry per model call: could it still see the opening ask?
            self.could_read_the_request: list[bool] = []

        def lattice(self) -> dict[str, str]:
            return {}

        def context_window(self) -> int:
            """What it can hold. Optional on the protocol and answered here,
            because a policy has to be measured against something and the only
            honest source is the thing doing the holding."""
            return BUDGET_TOKENS

        async def model_call(self, system, history, tools):
            visible = _readable(history, WINDOW)
            asked = next(
                (m for m in visible if "first-request" in (m.get("labels") or [])), None
            )
            self.could_read_the_request.append(asked is not None)
            if asked is None:
                return NOTHING_TO_GO_ON, []
            if not any(m.get("role") == "tool" for m in visible):
                return "Looking up the ticket.", [ToolCall("zendesk", {})]
            return _decides_from(str(asked.get("content") or "")), []

    # The suite's own rules have to REACH the grader. For a round `rules_of()`
    # returned `[]` here — every rule in the shipped example is a mapping and it
    # kept only plain strings — so this test's docstring claimed "the same
    # deterministic grader" while grading against nothing, and an answer breaking
    # the author's own `must-not-contain: ["refund by", "arrive on"]` passed.
    suite = rules_of(doc)
    assert suite, "the authored suite rules must reach the grader"
    assert {r.kind for r in suite} >= {"must-say-one-of", "must-not-contain", "must-call-before"}

    def scored(spec):
        """Run the worked example's own cases and grade them, config only."""
        graded, could_read, tidied = [], [], []
        for case in cases:
            model = SmallWindow()
            out = asyncio.run(
                run(spec, model, case.when, {"zendesk": lambda a: LONG_TICKET},
                    summarise=joined)
            )
            assert out.halted == "final", (case.key, out.halted)
            could_read.append(model.could_read_the_request)
            tidied.append([step for t in out.tidyings for step in t.fired])
            graded.append(check(case, out, rules_of(doc)))
        return verdict(graded, bar_of(doc)), could_read, tidied

    without, read_without, tidied_without = scored(agent(None))
    with_policy, read_with, tidied_with = scored(agent(written))

    # The measurement. One number is lower than the other, and the verdict the
    # suite reports at the bar the author typed flips with it.
    assert without.score < with_policy.score, (without.score, with_policy.score)
    assert (without.outcome, with_policy.outcome) == ("FAIL", "PASS")

    # And why — so an edit that quietly makes the two arms equal fails loudly
    # here instead of passing vacuously. Untidied, the opening ask stopped being
    # readable the moment the ticket arrived; tidied, it never did, and the
    # ladder's first rung alone was enough to put it back in view.
    assert all(seen == [True, False] for seen in read_without), read_without
    assert all(seen == [True, True] for seen in read_with), read_with
    assert all(fired == [] for fired in tidied_without), tidied_without
    assert all(fired == [written.steps[0].what] for fired in tidied_with), tidied_with


class _SmallModel:
    """A stand-in that answers once, calls `zendesk` first, and says what it holds.

    Written out rather than reusing `ReferenceTransport` because the thing under
    test is the OPTIONAL half of the transport protocol: `context_window()` is
    what a context policy is measured against, and a transport that does not
    have one is the other half of the same test.
    """

    name = "small-model"

    def __init__(self, window: int | None) -> None:
        self._window = window
        if window is not None:
            self.context_window = lambda: window  # type: ignore[method-assign]

    def lattice(self) -> dict[str, str]:
        return {}

    async def model_call(self, system, history, tools):
        from pact_adapters.harness import ToolCall

        if not any(m.get("role") == "tool" for m in history):
            return "Looking up the ticket.", [ToolCall("zendesk", {})]
        return "DECISION: approved. The item arrived faulty.", []


def _worked_example_run(window: int | None):
    """The shipped worked example, run from its own files, handed no tidier."""
    from pact_adapters.harness import run
    from pact_adapters.ir import AgentSpec

    doc = _example_doc()
    spec = AgentSpec.from_document(doc, "refund-desk", EXAMPLE)
    assert spec.context_policy is not None
    assert spec.context_policy.name == "long-threads"
    out = asyncio.run(
        run(spec, _SmallModel(window), "my lamp arrived broken, please refund",
            {"zendesk": lambda a: LONG_TICKET}, summarise=joined)
    )
    return spec, out


def test_the_context_policy_line_in_the_worked_example_tidies_without_any_host_code() -> None:
    """G3's last mile: the author's line, and nothing else, causes tidying.

    Every other test in this file builds a `Tidier` in Python. That proves the
    class and it proved nothing about the mechanism, because for a round the
    harness read `spec.context_policy` nowhere at all: `run()` tidied only when
    a CALLER constructed a tidier and passed `tidy=`. So the shipped
    `context-policy: long-threads` in `agents/refund-desk/agent.yaml` loaded,
    validated, and did nothing — the same "loads and does nothing" failure this
    round closed for interceptors, left standing in the mechanism the plan calls
    the biggest gap. D14 rules out "experts write code for that" for every
    capability in the core, and this is the test that says nobody has to.

    Nothing below is constructed by the test but the model stand-in and the
    tool. The agent, its loop, its ceilings, its rules and its policy all come
    off disk through `pact show`.
    """
    spec, out = _worked_example_run(BUDGET_TOKENS)

    assert out.tidyings, "the author's `context-policy:` line tidied nothing"
    fired = [step for t in out.tidyings for step in t.fired]
    assert fired[0] == spec.context_policy.steps[0].what == "shorten-long-results"
    assert "context-policy" not in out.unmetered, out.unmetered
    # And it really shrank the conversation rather than merely reporting a pass
    # over it — the ladder stops at the first rung that fits, so `after` is the
    # measurement that says the rung did something.
    assert all(t.after < t.before for t in out.tidyings), out.tidyings


def test_a_transport_that_will_not_say_what_it_holds_reports_the_policy_it_could_not_apply() -> None:
    """The honest half, and the reason there is no guessed default.

    A context policy is measured against what the model can hold. A transport
    that does not answer leaves nothing to measure against, and inventing a
    number would be the silent degradation T7 forbids — an author who wrote
    `context-policy: long-threads` and got neither tidying nor a word about it
    has been told something untrue. So it goes out the same door a spend cap
    with no price list goes out: named on `unmetered`, and announced.
    """
    from pact_adapters.events import Bus

    doc = _example_doc()
    from pact_adapters.harness import run
    from pact_adapters.ir import AgentSpec

    bus = Bus()
    spec = AgentSpec.from_document(doc, "refund-desk", EXAMPLE)
    out = asyncio.run(
        run(spec, _SmallModel(None), "my lamp arrived broken, please refund",
            {"zendesk": lambda a: LONG_TICKET}, summarise=joined, bus=bus)
    )
    assert out.tidyings == [], "nothing can be measured, so nothing is claimed"
    assert "context-policy" in out.unmetered, out.unmetered
    said = [e for e in bus.seen("session.limit.failed")]
    assert said and "context-policy" in said[0].payload["limits"], said


def test_a_run_with_a_policy_it_never_triggers_is_identical_to_one_without() -> None:
    """The cost-nothing-when-unused property, held at the loop level."""
    from pact_adapters.harness import ToolCall, run
    from pact_adapters.ir import AgentSpec, ToolSpec
    from pact_adapters.script import Script, Turn
    from pact_adapters.transports.mock import ReferenceTransport

    spec = AgentSpec(name="a", description="d", instructions="i", tools=(ToolSpec("z", "d"),))
    tools = {"z": lambda a: "small"}

    def once(tidy):
        s = Script([Turn("checking", (ToolCall("z", {}),)), Turn("done")])
        return asyncio.run(run(spec, ReferenceTransport(s), "hi", tools, tidy=tidy))

    plain = once(None)
    with_policy = once(Tidier(policy(**{"then": []}), budget_tokens=100_000))
    assert plain.trace() == with_policy.trace()
    assert with_policy.tidyings == []


def test_a_conversation_nobody_can_shrink_parks_for_a_person() -> None:
    """`if-it-still-does-not-fit: ask-a-person`, executing. Adding this sixth
    reason to park cost one row in `suspension.REASONS` and one entry in its
    clearance table — the claim that module makes about itself, used."""
    from pact_adapters.harness import run
    from pact_adapters.ir import AgentSpec
    from pact_adapters.script import Script, Turn
    from pact_adapters.suspension import CONTEXT_TOO_LONG
    from pact_adapters.transports.mock import ReferenceTransport

    spec = AgentSpec(name="a", description="d", instructions="i")
    p = policy(**{"if-it-still-does-not-fit": "ask-a-person", "then": []})
    out = asyncio.run(
        run(spec, ReferenceTransport(Script([Turn("hi")])), "x " * 4000,
            tidy=Tidier(p, budget_tokens=50))
    )
    assert out.halted == "suspended"
    assert out.suspension is not None and out.suspension.reason == CONTEXT_TOO_LONG
    assert out.tidyings[-1].outcome == "asked-a-person"


def test_the_person_saying_carry_on_lets_that_step_through_and_only_that_step() -> None:
    """A standing permission nobody remembers granting is not a gate. The next
    overflow is a different step, so a different question."""
    from pact_adapters.harness import run
    from pact_adapters.ir import AgentSpec
    from pact_adapters.script import Script, Turn
    from pact_adapters.suspension import Resumption
    from pact_adapters.transports.mock import ReferenceTransport

    spec = AgentSpec(name="a", description="d", instructions="i")
    p = policy(**{"if-it-still-does-not-fit": "ask-a-person", "then": []})
    tidier = Tidier(p, budget_tokens=50)
    parked = asyncio.run(
        run(spec, ReferenceTransport(Script([Turn("hi")])), "x " * 4000, tidy=tidier)
    )
    assert parked.suspension is not None

    # Answered under the name the wait actually asks about — the thing, not a
    # generic `decision`. That is what keeps two waits open in one step from
    # answering for each other, so the field name is part of the guarantee and
    # is read off the suspension rather than assumed.
    (asked,) = parked.suspension.asks
    assert asked.name == "conversation"
    said = Resumption(
        correlation_key=parked.suspension.correlation_key, values={asked.name: "carry-on"}
    )
    out = asyncio.run(
        run(spec, ReferenceTransport(Script([Turn("hi")])), "", tidy=tidier,
            resume=parked.suspension, answer=said)
    )
    assert out.halted == "final" and out.output == "hi"


# ─────────────────────────────────────────────────────────────────── helpers


def _example_doc() -> dict:
    """The worked example as the loader produces it.

    Read through `pact show` when the binary is available, and reconstructed
    from the same YAML otherwise, so the test is about the policy rather than
    about whether Rust has been built.
    """
    import subprocess

    try:
        out = subprocess.run(
            ["cargo", "run", "--quiet", "-p", "pact-cli", "--", "show", str(EXAMPLE)],
            capture_output=True, text=True, cwd=EXAMPLE.parents[1], timeout=600,
        )
        if out.returncode == 0:
            return json.loads(out.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    pytest.skip("pact-cli not built; run ./scripts/test-all.sh")


# ────────────────────────────── the window, from the catalogue, on real targets
#
# Everything above this line proves the policy WORKS. What it could not prove is
# that the policy ever RUNS outside this file, and for a round it did not:
# `harness._window` probed an optional `context_window()` that no shipped
# transport implemented, so on every real target the window was `None`, the
# policy went out as unenforced on `RunResult.unmetered`, and the only place a
# window was ever supplied was a stand-in written a few hundred lines up. A
# mechanism exercised by its own test fixture is decoration.
#
# What closed it is data, not code: `models/catalog.yaml` carries a window per
# model with a source and an `as-of` date beside it (arch §4.2), each transport
# looks up the id it is bound to, and `resolve.window_of` is the only place a
# window comes from. The tests below are named for the guarantee that buys.

#: The line a ticket system repeats. Content is irrelevant; size is the point.
_TICKET_LINE = "2026-03-01 09:14 status unchanged; nothing new on this order. "

#: What the distribution binds when the author pins no `model:` — read here
#: rather than written down, so this file cannot drift from the catalogue. If the
#: default moves to a model with a different window, everything below re-sizes.
CATALOGUE_MODEL = default_model()
CATALOGUE_WINDOW = window_of(CATALOGUE_MODEL)

def fills(window: int) -> str:
    """A ticket that fills `window` on its own, derived rather than guessed at.

    `long-threads` triggers at 85% (`when-full:`), so filling 100% of it leaves
    no room for the arithmetic to be marginal — and the first rung of the
    ladder, `shorten-long-results`, is the one that answers a conversation
    shaped like this.

    Sized per transport rather than once, because the transports no longer all
    bind the same model: `anthropic_transport.py` names its runtime and binds a
    row that runtime can actually serve, whose window is 200,000 rather than the
    distribution default's 32,768. A fixed ticket sized for the smaller window
    silently stopped triggering the policy on that arm — which is the same
    "measured against the wrong number" defect one layer up, arriving in a test.
    """
    return _TICKET_LINE * ((window * CHARS_PER_TOKEN) // len(_TICKET_LINE) + 1)


#: A ticket that fills the default model's whole window on its own.
TICKET_THAT_FILLS_THE_WINDOW = fills(CATALOGUE_WINDOW)

#: An id no catalogue row claims. Used instead of pinning the one row that says
#: `unknown` today, so this test still holds the guarantee on the day somebody
#: sources that model's window.
NOT_IN_THE_CATALOGUE = "a-model-nobody-has-written-down"


def a_refund_worth_checking() -> "Script":  # noqa: F821
    """One turn per stage of the worked example's own `careful` loop.

    Look the ticket up, finish looking things up, read the decision back against
    the policy, reply. Scripted rather than sampled for the reason every other
    run in this package is: the claim is about what the model was HANDED, and a
    live model would measure sampling noise instead — and would need a network
    (D17).
    """
    from pact_adapters.harness import ToolCall
    from pact_adapters.script import Script, Turn

    return Script([
        Turn("Checking the ticket.", (ToolCall("zendesk", {"ticket": "T-1"}),)),
        Turn("The ticket says the lamp arrived broken 6 days ago."),
        Turn("Rule 2 applies: faulty on arrival, and 6 days is inside the window."),
        Turn("Approved: the item arrived damaged within 30 days."),
    ])


#: The sentence an agent repeats when it is thinking out loud at length. Content
#: is irrelevant; that it is the AGENT's prose and not a tool's output is the
#: whole point — see below.
_RAMBLE = "The customer wrote back again with the same question about the lamp. "


def a_refund_with_more_prose_than_shortening_can_fix(window: int) -> "Script":  # noqa: F821
    """The same four stages, with one that talks far past what the model holds.

    `a_refund_worth_checking` overflows through a huge TOOL RESULT, and the first
    rung of the shipped ladder — `shorten-long-results` — answers that on its
    own, so the ladder stops there and `summarise-older` is never reached. That
    is why the summariser could be missing on five of seven transports for a
    round without a single test noticing.

    Here the bulk is the agent's own prose. `shorten-long-results` may only touch
    tool results and `always-keep` does not pin it, so the second rung is the one
    that has to do the work, and whether it can is now visible in whether the run
    finishes at all.

    Sized from the transport's own window for the reason `fills` gives: the
    transports no longer all bind the same model.
    """
    from pact_adapters.harness import ToolCall
    from pact_adapters.script import Script, Turn

    said = _RAMBLE * ((window * CHARS_PER_TOKEN) // len(_RAMBLE) + 1)
    return Script([
        Turn("Checking the ticket.", (ToolCall("zendesk", {"ticket": "T-1"}),)),
        Turn("The ticket says the lamp arrived broken 6 days ago. " + said),
        Turn("Rule 2 applies: faulty on arrival, and 6 days is inside the window."),
        Turn("Approved: the item arrived damaged within 30 days."),
    ])


def without_a_summariser(transport_cls: type) -> type:
    """The same transport with `write_summary` taken away, and nothing else.

    Not a stand-in: this is exactly what these five classes WERE one round ago,
    so it is the state the fix moved them out of. `harness._summariser` probes
    the method with `getattr` and asks whether it is callable, so setting it to
    nothing makes the probe miss without disturbing the constructor, the window,
    the script or the loop. Every difference the paired arms show is therefore
    attributable to that one method.
    """
    return type(
        f"{transport_cls.__name__}WithoutASummariser",
        (transport_cls,),
        {"write_summary": None},
    )


def _worked_example_on(
    transport,
    ticket: str | None = None,
    summarise=joined,
    spend_cap: bool = True,
    doc: dict | None = None,
):
    """The shipped example, run from its own files, handed no tidier and no window.

    Nothing here is constructed by the test but the transport and the tools. The
    agent, its loop, its ceilings, its rules and its `context-policy:` line all
    come off disk through `pact show`; the budget the policy is measured against
    comes off disk through `models/catalog.yaml`.

    `ticket` defaults to one sized for the distribution default. A transport
    bound to a bigger window has to be handed a bigger ticket or the policy
    never fires and the test passes over the top of it.

    `spend_cap` drops `limits.cost-per-request-under` and nothing else, and it
    exists because two shipped ceilings genuinely collide on one arm — only from
    the round the money one stopped being inert. `limits.yaml` writes
    `cost-per-request-under: 0.05 USD`; the Anthropic transport binds
    `claude-haiku-4-5`, whose catalogue row publishes 5.00 USD per million output
    tokens; and a conversation that OVERFLOWS that model's 200,000-token window
    is by arithmetic at least 0.85 USD of the agent's own words. So a test that
    has to overflow the window cannot also stay inside the author's cap: the cost
    ceiling fires first — correctly, and at the right step — and the context
    ladder under test never gets to run. Dropped only where the conversation has
    to be that big, so every other run here is still measured against every
    ceiling the author wrote. `test_termination.py` is where the cap itself is
    held.
    """
    from dataclasses import replace

    from pact_adapters.harness import run
    from pact_adapters.ir import AgentSpec

    # `doc` is the example with ONE line edited, for a test about that line. It
    # defaults to the shipped tree, so every other caller here is still measured
    # against the files as they ship.
    spec = AgentSpec.from_document(doc or _example_doc(), "refund-desk", EXAMPLE)
    if not spend_cap:
        spec = replace(spec, limits=replace(spec.limits, cost_per_request_under=None))
    out = asyncio.run(
        run(
            spec,
            transport,
            "my lamp arrived broken, please refund",
            {
                "zendesk": lambda a: ticket or TICKET_THAT_FILLS_THE_WINDOW,
                "payments": lambda a: "refunded",
            },
            summarise=summarise,
        )
    )
    return spec, out


def test_the_catalogue_this_distribution_ships_reads_without_a_mistake_in_it() -> None:
    """The file every window comes from, held under test like any other document.

    It is distribution-supplied and the author never opens it (§4.2), which is
    exactly why nobody would notice a bad row until a run somewhere quietly
    reported a policy as unenforced. Every problem it can have names a file, a
    line and something to type — the project's own rule, applied to the project's
    own data.
    """
    catalogue = load_catalogue()
    assert catalogue.errors == (), "\n".join(str(p) for p in catalogue.errors)
    assert catalogue.entries, "a catalogue with no models in it holds no windows"
    assert catalogue.get(CATALOGUE_MODEL) is not None, (
        f"`default: {CATALOGUE_MODEL}` names a model with no row"
    )
    assert CATALOGUE_WINDOW and CATALOGUE_WINDOW > 0


@pytest.mark.parametrize("name", sorted(TRANSPORTS))
def test_every_shipped_transport_says_what_its_model_holds_with_nothing_passed_in(
    name: str,
) -> None:
    """G3's last mile on the targets people actually run.

    `test_the_context_policy_line_in_the_worked_example_tidies_without_any_host_code`
    proved the author's line is enough — but it proved it against a stand-in
    written in this file that answers `context_window()` because the test told it
    to. That is the shape of the gap this closes: on all seven shipped
    transports the method did not exist, so the honest-but-inert branch fired
    every time and `context-policy` went out on `unmetered` on every real run.

    Nothing is passed in here. The transport is constructed with a script and
    nothing else, the window arrives from `models/catalog.yaml` by way of the id
    the transport is bound to, and the assertion is that the number the policy
    was measured against is the number the catalogue publishes — not merely that
    some number turned up.

    It used to assert that all six bound the SAME id, which cemented a real
    defect: `anthropic_transport.py` bound the distribution default — Qwen
    weights the catalogue records as served by Ollama and vLLM only — and then
    answered that its model held 32,768 tokens. The stronger property, and the
    one that would have caught it, is that whatever a transport bound is a model
    its own runtime can actually serve.
    """
    transport = TRANSPORTS[name](a_refund_worth_checking())
    entry = load_catalogue().get(transport.model)
    assert entry is not None, (
        f"{name} bound {transport.model!r}, which has no row in models/catalog.yaml"
    )
    assert transport.context_window() == entry.context_window
    if transport.runtime:
        assert transport.runtime in entry.runtimes, (
            f"{name} says it is the {transport.runtime!r} runtime and bound "
            f"{transport.model!r}, which the catalogue says is served by "
            f"{sorted(entry.runtimes)}"
        )
    else:
        assert transport.model == CATALOGUE_MODEL, (
            "a transport that names no runtime is provider-agnostic, so it takes "
            "the distribution default"
        )


def test_the_live_local_transport_takes_its_window_from_the_tag_ollama_answers_to() -> None:
    """The seventh target, and the one where the id is genuinely two ids.

    `OllamaTransport` is the only transport here bound to real weights, and it is
    bound by the tag the runtime uses — `qwen2.5:7b-instruct`, not the catalogue's
    `qwen2.5-7b-instruct`. §4.2 says the catalogue is keyed on
    `(model, provider, runtime)` for exactly this reason, so the row answers to
    both and there is one row rather than one per runtime.

    No model is served and no request is made: constructing a transport and
    asking what its model holds is a catalogue lookup, which is the whole point
    of the figure living in a file (D17 — this must hold air-gapped).
    """
    from pact_adapters.transports.ollama_transport import OllamaTransport

    live = OllamaTransport("qwen2.5:7b-instruct")
    assert live.context_window() == CATALOGUE_WINDOW
    assert load_catalogue().get("qwen2.5:7b-instruct") is load_catalogue().get(
        CATALOGUE_MODEL
    ), "the runtime tag and the catalogue id must reach the same row, not two"


@pytest.mark.parametrize("name", sorted(TRANSPORTS))
def test_the_worked_examples_policy_line_tidies_on_every_shipped_transport(
    name: str,
) -> None:
    """The author's line, a real transport, and nothing else — and it bites.

    This is the measurement the mechanism is worth having for. Same shipped
    agent, same shipped `context-policies/long-threads.yaml`, same ladder; the
    only thing this test supplies is a script and a tool. The conversation
    outgrows what the catalogue says the bound model can hold, the first rung
    fires, and `context-policy` is NOT on `unmetered` — because something finally
    said what the model holds.

    The ticket is sized from THAT transport's own window rather than from the
    distribution default's, because the six no longer all bind the same model.
    """
    transport = TRANSPORTS[name](a_refund_worth_checking())
    spec, out = _worked_example_on(transport, fills(transport.context_window()))

    assert out.halted == "final", (name, out.halted)
    assert "context-policy" not in out.unmetered, out.unmetered
    assert out.tidyings, "the author's `context-policy:` line tidied nothing"
    fired = [step for t in out.tidyings for step in t.fired]
    assert fired[0] == spec.context_policy.steps[0].what == "shorten-long-results"
    # And it really shrank the conversation rather than reporting a pass over it.
    assert all(t.after < t.before for t in out.tidyings), out.tidyings


@pytest.mark.parametrize("name", sorted(TRANSPORTS))
def test_the_summariser_the_author_named_is_built_from_their_line_and_nothing_else(
    name: str,
) -> None:
    """`summarised-by:` executes with no host code — the other half of G3.

    Three rungs of the shipped ladder need no model and always ran. The fourth,
    `summarise-older`, needs one, and for a round the ONLY way to supply it was
    for a host to write Python and pass `summarise=` into `run()`. So the worked
    example's ladder fell through `summarise-older` — with the note "could not
    summarise: no summariser was supplied" — to `keep-recent-only` and then to
    `if-it-still-does-not-fit: ask-a-person`, on a conversation a summariser
    would have handled. D14 rules that out for every capability in the core.

    Nothing is passed in here. The model that writes the summary is the one the
    author wrote in `context-policies/long-threads.yaml`, and it is a DIFFERENT
    model from the one doing the work, which is the whole reason the field
    exists.

    Held across every shipped transport rather than one. For a round it was one,
    and the mechanism was two transports wide: `write_summary` existed on the
    Anthropic and Ollama transports and on none of the other five, so
    `summarised-by:` was a lattice difference — a rung that fires on some targets
    and reports itself unmetered on the rest — rather than a mechanism. That is
    the same shape `context_window()` was in one round earlier.
    """
    from pact_adapters.harness import _summariser
    from pact_adapters.ir import AgentSpec

    spec = AgentSpec.from_document(_example_doc(), "refund-desk", EXAMPLE)
    named = spec.context_policy.summarised_by
    assert named, "the worked example must name a summarising model"

    transport = TRANSPORTS[name](a_refund_worth_checking())
    working = transport.model
    assert named != working, (
        "a model summarising its own history compounds its own mistakes — the "
        "worked example is supposed to demonstrate the separation"
    )

    summarise = _summariser(transport, spec)
    assert summarise is not None, f"{name}: the author's line produced no summariser"

    tidier = spec.tidier(400, summarise)
    out = tidier.apply([say("user", "x " * 900), say("assistant", "y " * 900),
                        say("user", "and now?")])
    assert "summarise-older" in out.fired, out.fired
    assert not any("no summariser" in n for n in out.notes), out.notes
    checkpoint = next((m for m in out.messages if m.checkpoint), None)
    assert checkpoint is not None, "no checkpoint was written"
    assert checkpoint.text(), (
        "the checkpoint is empty, so a summariser was found and then said nothing"
    )
    # The invariant every one of these methods is written to preserve: a second
    # transport, not a second binding. Summarising with another model must not
    # move the model the work is being done on.
    assert transport.model == working, (
        f"{name} re-bound itself to summarise; `self.model` must be untouched"
    )


@pytest.mark.parametrize("name", sorted(TRANSPORTS))
def test_summarising_is_what_lets_the_shipped_ladder_finish_and_not_park(
    name: str,
) -> None:
    """The author's line, through `run()`, with nothing handed in — and it bites.

    The end-to-end version of the test above, and the one that would have caught
    the gap. Two runs of the SAME shipped example, on the SAME transport, over
    the SAME conversation; the only difference is whether `write_summary` is
    reachable, which is the only difference this round closed.

    * As shipped, `summarise-older` folds the older region into a checkpoint,
      the conversation gets shorter, and the run reaches a decision.
    * With the method taken away, the rung writes "could not summarise", the
      ladder falls through `drop-parts` and `keep-recent-only`, and
      `if-it-still-does-not-fit: ask-a-person` parks the run — a refund a person
      now has to look at, on a conversation a summariser would have handled.

    Nothing is constructed here but the transport and the tools, and one ceiling
    is taken off — `_worked_example_on`'s `spend_cap` argument says why in full.
    In one line: a conversation big enough to overflow a 200,000-token window
    costs more than the author's 0.05 USD cap on any model anybody charges for,
    so on the Anthropic arm the money ceiling now fires first and the ladder
    under test never runs. The policy, its ladder, its pins, the model that
    writes the summary and the budget it is all measured against still come off
    disk.
    """
    made = TRANSPORTS[name]
    window = made(a_refund_worth_checking()).context_window()

    _, shipped = _worked_example_on(
        made(a_refund_with_more_prose_than_shortening_can_fix(window)),
        fills(window),
        summarise=None,
        spend_cap=False,
    )
    assert "summarised-by" not in shipped.unmetered, shipped.unmetered
    folded = [t for t in shipped.tidyings if "summarise-older" in t.fired]
    assert folded, f"{name}: the summarising rung never ran"
    assert not any("no summariser" in n for t in folded for n in t.notes), folded
    assert all(t.after < t.before for t in folded), [
        (t.before, t.after) for t in folded
    ]
    assert any(m.checkpoint for t in folded for m in t.messages), "no checkpoint"
    assert shipped.halted == "final", shipped.halted

    _, blind = _worked_example_on(
        without_a_summariser(made)(
            a_refund_with_more_prose_than_shortening_can_fix(window)
        ),
        fills(window),
        summarise=None,
        spend_cap=False,
    )
    assert "summarised-by" in blind.unmetered, blind.unmetered
    assert any("no summariser" in n for t in blind.tidyings for n in t.notes), (
        "the rung has to say it could not run; silence here is the T7 breach"
    )
    assert blind.halted == "suspended", (
        f"{name}: without a summariser this conversation must reach "
        f"`if-it-still-does-not-fit: ask-a-person`, not finish anyway"
    )


def test_a_transport_that_cannot_re_bind_reports_the_summariser_rather_than_dropping_it() -> None:
    """The honest half, the same shape as `context-policy` and `usage`.

    `ReferenceTransport` is the script with no framework and no model, so it
    cannot make a call with a second model. A rung of the author's ladder
    therefore cannot run, and the run says which one rather than quietly firing
    three of four.

    Both halves of that guarantee are here, because either alone is satisfiable
    by a mistake: a run that never reports `summarised-by` has stopped being
    honest, and a run that always reports it has a mechanism that never fires.
    The control arm stays deliberately inert — `transports/mock.py` says why —
    so the reporting path keeps something that exercises it.
    """
    _, out = _worked_example_on(
        ReferenceTransport(a_refund_worth_checking()), summarise=None
    )
    assert "summarised-by" in out.unmetered, out.unmetered
    assert not hasattr(ReferenceTransport, "write_summary"), (
        "the control arm is the one transport left honest-and-inert on purpose"
    )

    for name, made in sorted(TRANSPORTS.items()):
        transport = made(a_refund_worth_checking())
        _, ran = _worked_example_on(transport, fills(transport.context_window()),
                                    summarise=None)
        assert "summarised-by" not in ran.unmetered, (name, ran.unmetered)


def test_the_control_arm_is_bound_to_no_model_and_says_so_instead_of_guessing() -> None:
    """The honest half, now held against the real transport rather than a stub.

    `ReferenceTransport` is the script with no framework and no model. It has no
    window to report, so it reports none, and the run names `context-policy` on
    `unmetered` and announces it. Inventing a plausible number here would make
    the control arm the least honest thing in the set — and would be the silent
    degradation T7 exists to forbid: an author who wrote
    `context-policy: long-threads` and got neither tidying nor a word about it
    has been told something untrue.
    """
    reference = ReferenceTransport(a_refund_worth_checking())
    assert not hasattr(reference, "context_window")

    _, out = _worked_example_on(reference)
    assert out.tidyings == [], "nothing can be measured, so nothing is claimed"
    assert "context-policy" in out.unmetered, out.unmetered


def test_a_transport_bound_to_a_model_the_catalogue_does_not_list_reports_it() -> None:
    """A window nobody published is `None`, never a plausible-looking number.

    The same door as the control arm above, reached a different way: the
    transport is real and does implement `context_window()`, but the model it is
    pinned to has no row. The fix an author needs is a line in
    `models/catalog.yaml`, and telling them the policy went unenforced is what
    sends them to look.
    """
    pinned = AnthropicTransport(a_refund_worth_checking(), model=NOT_IN_THE_CATALOGUE)
    assert pinned.context_window() is None

    _, out = _worked_example_on(pinned)
    assert out.tidyings == []
    assert "context-policy" in out.unmetered, out.unmetered


def test_a_row_that_cannot_source_its_window_says_unknown_rather_than_dropping_it(
    tmp_path: Path,
) -> None:
    """`unknown` is a state the catalogue can be in, and it is not the same as absent.

    §4.2: "Where a field cannot be discovered it is recorded as `unknown`", and
    an unprovenanced figure may not satisfy a predicate. So the ROW still exists
    — the model is real, it is served, it can be bound — while the WINDOW reads
    as nothing. Collapsing the two would lose the difference between "we have not
    heard of this model" and "we have, and nobody can source what it holds",
    which are different things to tell an author.
    """
    written = tmp_path / "catalog.yaml"
    written.write_text(
        "version: 1\n"
        "default: sourced\n"
        "models:\n"
        "  sourced:\n"
        "    tier: small\n"
        "    capabilities:\n"
        "      context-window:\n"
        "        value: 8192\n"
        "        provenance: { source: a published model card, as-of: 2026-07-28 }\n"
        "  unsourced:\n"
        "    tier: small\n"
        "    capabilities:\n"
        "      context-window:\n"
        "        value: unknown\n"
        "        provenance: { source: nobody publishes one, as-of: 2026-07-28 }\n"
    )
    catalogue = load_catalogue(written)

    assert catalogue.errors == (), "\n".join(str(p) for p in catalogue.errors)
    assert catalogue.window_of("sourced") == 8192
    assert catalogue.get("unsourced") is not None, "the model is listed"
    assert catalogue.window_of("unsourced") is None, "its window is not"
    assert catalogue.get("never-heard-of-it") is None


def test_a_window_written_without_a_source_is_refused_by_name(tmp_path: Path) -> None:
    """One shape for a window, and the diagnostic says which one.

    §4.2's fifth finding is the reason: per-figure `source` and `as-of` on the
    RESOLVED entry, with LangChain's shipped precedent named as the anti-pattern
    — an upstream feed that records provenance, a hand-written override layer
    that records none, and a merged result no consumer can attribute. A bare
    `context-window: 131072` is exactly that hand edit, so it is refused rather
    than quietly accepted, and the fix is a line the person who wrote it can
    type.
    """
    written = tmp_path / "catalog.yaml"
    written.write_text(
        "version: 1\n"
        "models:\n"
        "  bare:\n"
        "    tier: small\n"
        "    capabilities:\n"
        "      context-window: 131072\n"
    )
    (problem,) = load_catalogue(written).errors

    assert problem.rule == "catalog/window-without-provenance"
    assert problem.file.endswith("catalog.yaml")
    assert written.read_text().splitlines()[problem.line - 1].strip().startswith("bare")
    assert "without a source" in problem.message
    assert "`value:` and `provenance:`" in problem.fix
    assert load_catalogue(written).window_of("bare") is None


def test_a_catalogue_nobody_can_parse_is_reported_rather_than_thrown(
    tmp_path: Path,
) -> None:
    """A parser stack is not a diagnostic, and it lands on the wrong person.

    Whoever is running an agent did not write this file — §4.2 says the author
    never authors it — so a `yaml.YAMLError` escaping here would hand a traceback
    to somebody with no way to act on it. It is carried like every other mistake
    in this package, with the line the parser objected to.
    """
    written = tmp_path / "catalog.yaml"
    written.write_text("version: 1\nmodels:\n  a:\n   tier: small\n     bad: indent\n")

    (problem,) = load_catalogue(written).errors
    assert problem.rule == "catalog/unreadable-file"
    assert problem.line == 5, problem
    assert "not valid YAML" in problem.message
    assert "indentation" in problem.fix


# ─────────────────────── what summarising must not quietly take away or hide


def test_a_picture_is_not_thrown_away_by_a_step_that_only_said_summarise() -> None:
    """The rule this whole file works to, applied to the one rung that folds.

    `PartKind`'s own docstring says what Eve does — "keep text, discard the
    rest, which is exactly what it does, every time" — and the schema says the
    opposite is PACT's rule: a kind of content survives unless a step names it,
    and `drop-parts` is the only step that names one. Measured before this held:
    the shipped policy run over a history whose first message was a customer's
    damage photo produced `fired: ['shorten-long-results', 'summarise-older']`
    and no IMAGE part anywhere in the result. The author wrote no
    `drop-parts: pictures`. D16 puts vision in v1, so this is not a corner.
    """
    policy = ContextPolicy.resolve(_example_doc(), "long-threads", EXAMPLE)
    with_a_photo = [
        Message(
            "user",
            (Part(PartKind.TEXT, "here is the damage"), Part(PartKind.IMAGE, "")),
            labels=frozenset({"attachment"}),
        ),
        *[Message("assistant", (Part(PartKind.TEXT, "looking into it. " * 200),))
          for _ in range(8)],
        Message("user", (Part(PartKind.TEXT, "any news?"),)),
    ]
    tidier = Tidier(policy, budget_tokens=400, summarise=lambda folding, previous: (
        f"{previous} " + " ".join(m.text()[:20] for m in folding)
    ).strip())

    tidied = tidier.apply(with_a_photo)

    assert "summarise-older" in tidied.fired
    kinds = {p.kind for m in tidied.messages for p in m.parts}
    assert PartKind.IMAGE in kinds, (
        f"a picture was thrown away by a step that only said summarise: {tidied.fired}"
    )
    assert any("drop-parts" in n for n in tidied.notes), (
        f"keeping it has a cost and has to be reported: {tidied.notes}"
    )


def test_the_summariser_is_told_a_picture_existed_rather_than_shown_nothing() -> None:
    """What the folding model reads. It cannot see an image, so the checkpoint
    must at least SAY one arrived — a summary that silently omits the photo the
    whole ticket is about is worse than one that names it."""
    from pact_adapters.harness import _readable

    said = _readable(
        Message("user", (Part(PartKind.TEXT, "here is the damage"), Part(PartKind.IMAGE, "")))
    )
    assert "a picture" in said, said
    assert _readable(Message("user", (Part(PartKind.AUDIO, ""),))).count("voice message") == 1


def test_what_the_summarising_model_costs_is_counted_or_named_never_neither() -> None:
    """`summarised-by:` is a second model call and somebody pays for it.

    `write_summary` builds a SECOND transport internally, so `_meter_usage` —
    which reads `usage()` off the one transport handed to `run()` — never sees
    that call. On a long thread that is one extra call per tidy, charged to
    nothing, under an author who wrote `cost-per-request-under`. Same door as
    every other ceiling nobody can measure, because reporting neither the spend
    nor the fact that it could not be counted is the T7 breach that door exists
    to close.
    """
    made = TRANSPORTS["pydantic-ai"]
    window = made(a_refund_worth_checking()).context_window()

    # The control arm is a transport with `summary_usage` out of REACH, which is
    # what every shipped transport was one round ago and what three of the seven
    # still were the round after — the metering that closed "two ceilings that
    # have never metered a real call" landed on four of them. Now that all seven
    # answer, the arm has to be built rather than found, which is the point: the
    # failure route stays exercised and no shipped transport is on it.
    blind = type(
        "PydanticAIThatCannotPriceItsSummariser",
        (made,),
        {"summary_usage": None},
    )
    _, unable = _worked_example_on(
        blind(a_refund_with_more_prose_than_shortening_can_fix(window)),
        fills(window),
        summarise=None,
    )
    assert any("summarise-older" in t.fired for t in unable.tidyings), "the rung must run"
    assert "summarised-by-cost" in unable.unmetered, unable.unmetered

    class Priced(made):  # type: ignore[misc, valid-type]
        """A transport that can say what its summarising call cost."""

        def summary_usage(self) -> tuple[int, float]:
            return (500, 0.004)

    priced = Priced(a_refund_with_more_prose_than_shortening_can_fix(window))
    _, counted = _worked_example_on(priced, fills(window), summarise=None)
    assert "summarised-by-cost" not in counted.unmetered, counted.unmetered
    assert counted.spent >= 0.004, (
        f"the summariser's bill has to reach the meter the ceiling reads: {counted.spent}"
    )


def test_a_summarising_model_nobody_can_price_is_named_and_never_billed_at_zero() -> None:
    """The last hop of "an unpriced row yields `None`, never zero".

    `what_the_summariser_cost` returned `(0, 0.0)` when the second transport
    could not price its own call, and `harness._summariser` handed that straight
    to `charge(0, 0.0)` — so a `summarised-by:` model the catalogue publishes as
    `cost: unknown` was billed as nothing at all against the author's spend cap,
    with nothing anywhere saying so. Reachable from the shipped distribution with
    one line: `models/catalog.yaml` ships `gpt-5.4` unpriced.

    The difference from the arm above is where the silence was. There the
    transport has no `summary_usage` at all and the run says so at the top; here
    it has one, answers honestly, and the run has to notice mid-flight — which is
    the case `_metering`'s own docstring used to record as an unfixable residual
    ("`harness.run` probes `summary_usage` ONCE, before any summarising model is
    known"). It is fixable: the probe stays where it is and the CHARGE reports.
    """
    from pact_adapters.resolve import price_of

    assert price_of("gpt-5.4", 1_000, 1_000) is None, (
        "point this test at a row the catalogue still cannot price"
    )
    unpriced = json.loads(json.dumps(_example_doc()))
    unpriced["context-policies"]["long-threads"]["summarised-by"] = "gpt-5.4"

    made = TRANSPORTS["pydantic-ai"]
    window = made(a_refund_worth_checking()).context_window()
    _, out = _worked_example_on(
        made(a_refund_with_more_prose_than_shortening_can_fix(window)),
        fills(window),
        summarise=None,
        doc=unpriced,
    )
    assert any("summarise-older" in t.fired for t in out.tidyings), "the rung must run"
    assert "summarised-by-cost" in out.unmetered, out.unmetered
    assert out.spent == 0.0, (
        f"an unpriceable summariser must reach no meter at all, not a zero: {out.spent}"
    )


def test_a_delegate_that_summarises_does_not_stop_its_siblings_clock() -> None:
    """A blocking summariser must cost one member's time, never the run's.

    `transports/_summarise.py` finishes the coroutine on a worker thread and
    BLOCKS the caller, for reasons it argues at length. For a round the caller
    was the event loop's own thread, because `run()` called `_tidy` inline — so
    one delegate tidying froze every sibling: measured end-to-end on authored
    lines only, a 500ms `gives-up-after:` fired at 1.07s and a member whose
    answer HAD arrived was recorded `out-of-time` and thrown away. A deadline a
    sibling's summary can overrun is a deadline the author cannot rely on, and
    recording a member that answered as having missed one is the silent
    mis-statement T7 forbids.

    Held as a clock reading rather than as a deadline outcome, because the
    outcome depends on which callback the loop happens to reach first once it is
    released. What has to be true is simpler and is the whole guarantee: while
    one member is inside an uninterruptible summarising call, the other member's
    seconds keep passing.

    Authored lines only: `context-policy: long-threads` on the child — the same
    policy the desk itself uses — and a team of two on the parent.
    """
    import time

    from pact_adapters.delegation import ANSWERED
    from pact_adapters.harness import ToolCall, delegate_by_running, run
    from pact_adapters.ir import AgentSpec
    from pact_adapters.script import Script, Turn

    BLOCKS_FOR = 0.6

    doc = json.loads(json.dumps(_example_doc()))
    doc["agents"]["policy-checker"]["context-policy"] = "long-threads"
    doc["agents"]["policy-checker"]["uses"] = ["zendesk"]

    made = TRANSPORTS["pydantic-ai"]
    window = made(a_refund_worth_checking()).context_window()
    summarised_at: list[float] = []
    answered_at: list[float] = []

    class Blocking(made):  # type: ignore[misc, valid-type]
        """A summarising call that really does stop the thread it is on."""

        def write_summary(self, text: str, model: str) -> str:
            summarised_at.append(time.monotonic())
            time.sleep(BLOCKS_FOR)
            return "the customer's lamp arrived broken"

    class Unhurried(ReferenceTransport):
        async def model_call(self, system, history, tools):
            await asyncio.sleep(0.05)
            answered_at.append(time.monotonic())
            return await super().model_call(system, history, tools)

    # The child has to still be running when the summary is written, so its
    # rambling turn makes another call rather than ending the run. Shortening
    # cannot touch the agent's own prose, so `summarise-older` is the rung that
    # has to answer it — which is the whole reason this script is not the one
    # every other test here uses.
    said = _RAMBLE * ((window * CHARS_PER_TOKEN) // len(_RAMBLE) + 1)
    rambles = Script([
        Turn("Checking the ticket.", (ToolCall("zendesk", {"ticket": "T-1"}),)),
        Turn("The lamp arrived broken 6 days ago. " + said,
             (ToolCall("zendesk", {"ticket": "T-2"}),)),
        Turn("Rule 2 applies, and 6 days is inside the window."),
    ])

    def transport_for(member: AgentSpec):
        if member.name == "Policy Checker":
            return Blocking(rambles)
        return Unhurried(Script([Turn("nothing suspicious")]))

    asking_both = Script([
        Turn("Consulting the team.",
             (ToolCall("policy-checker", {"question": "is this covered?"}),
              ToolCall("fraud-checker", {"question": "does this look real?"}))),
        Turn("Approved."),
    ])

    desk = AgentSpec.from_document(doc, "refund-desk", EXAMPLE)
    out = asyncio.run(
        run(desk, ReferenceTransport(asking_both), "my lamp arrived broken",
            {"zendesk": lambda a: fills(window), "payments": lambda a: "refunded"},
            ask_member=delegate_by_running(
                doc, transport_for, {"zendesk": lambda a: fills(window)}))
    )

    handoff = out.handoffs[0]
    states = {a.member: a.state for a in handoff.answers}
    assert states == {"policy-checker": ANSWERED, "fraud-checker": ANSWERED}, states
    assert summarised_at, "the summarising rung never ran, so nothing was blocked"
    assert answered_at, "the sibling never reached its model call"
    waited = answered_at[0] - summarised_at[0]
    assert waited < BLOCKS_FOR, (
        f"the sibling was frozen for {waited:.2f}s by another member's summary, "
        f"which blocks for {BLOCKS_FOR}s"
    )
