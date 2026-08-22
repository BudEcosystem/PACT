"""The event lattice and interceptors.

Interceptors are the capability Eve structurally lacks: all 28 of its lifecycle
events are observe-only, so there is no point at which a value can be redacted
before it reaches the model, and no way to stop a tool call on a condition the
approval rules cannot express.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from consenting import allowing_the_connection  # noqa: E402
from pact_adapters.events import Address, Bus, Phase, Scope  # noqa: E402
from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.interceptors import (  # noqa: E402
    REDACTION, REDIRECTS_AT, Chain, Decision, Interceptor, InterceptorError, Power,
    Refused, guard,
)
from pact_adapters.ir import AgentSpec, ToolSpec  # noqa: E402
from pact_adapters.loops import Loop  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

SPEC = AgentSpec(
    name="Refund Desk", description="d", instructions="Decide refunds.",
    tools=(ToolSpec("zendesk", "read the ticket"), ToolSpec("payments", "issue a refund")),
)
TOOLS = {"zendesk": lambda a: "lamp, broken", "payments": lambda a: "refunded"}


# ------------------------------------------------------------------ addresses


def test_an_address_is_scope_subject_phase() -> None:
    a = Address.parse("step.tool.before")
    assert (a.scope, a.subject, a.phase) == (Scope.STEP, "tool", Phase.BEFORE)
    assert str(a) == "step.tool.before"


def test_a_prefix_subscribes_to_every_phase() -> None:
    """The thing Eve's flat union cannot do: care about tools without
    enumerating every phase of them."""
    a = Address.parse("step.tool.completed")
    assert a.matches("step.tool")
    assert a.matches("step")
    assert a.matches("*")
    assert not a.matches("turn.tool")
    assert not a.matches("step.message")


def test_a_malformed_address_says_what_is_wrong() -> None:
    for bad, expect in [
        ("nonsense", "a part, a thing, and a moment"),
        ("nowhere.tool.before", "is not a part of a run"),
        ("step.tool.someday", "is not a moment"),
        ("step.nonsense.before", "is not something that happens"),
    ]:
        with pytest.raises(ValueError) as e:
            Address.parse(bad)
        assert expect in str(e.value), f"{bad!r} said: {e.value}"


def test_an_author_can_add_a_subject_without_editing_the_core() -> None:
    """A new subject costs an `x-` prefix, not a schema bump. Eve's equivalent
    is editing the union, the channel subset, the hook map and the manifest."""
    a = Address.parse("step.x-retrieval.completed")
    assert a.subject == "x-retrieval"


def test_the_bus_delivers_in_order_and_records_everything() -> None:
    b, seen = Bus(), []
    b.on("step.tool", lambda e: seen.append(str(e.address)))
    b.emit("step.tool.before", name="a")
    b.emit("turn.message.completed")
    b.emit("step.tool.completed", name="a")
    assert seen == ["step.tool.before", "step.tool.completed"]
    assert len(b.log) == 3


# --------------------------------------------------------------- interceptors


def test_powers_are_declared_and_enforced_after_the_fact() -> None:
    """Checked after running, because a declaration that is never verified is
    documentation rather than a control."""
    over = Interceptor(
        "bad", "step.tool.before", frozenset({Power.HIDE_VALUES}),
        lambda p: Decision(stop="nope"),
    )
    with pytest.raises(Refused, match="may only hide-values"):
        over.apply({})


def test_a_redactor_is_built_from_config_not_code() -> None:
    """The sentence in the author's file IS the rule.

    This test used to pass a dict of Python regexes written in its own source,
    which proved the builder worked and proved nothing about the mechanism the
    worked example depends on: nothing read `rules:` at all, so
    `interceptors/redact-card-numbers.yaml` loaded, validated, and let every
    card number through to the model.
    """
    c = Chain.from_document(
        {
            "agents": {"a": {"interceptors": ["cards"]}},
            "interceptors": {
                "cards": {
                    "when": "step.message.before",
                    "may": ["hide-values"],
                    "rules": [
                        'replace anything that looks like a card number with '
                        '"[card number removed]"'
                    ],
                }
            },
        },
        "a",
    )
    out, _ = c.run("step.message.before", {"content": "card 4111 1111 1111 1111 here"})
    assert "4111" not in out["content"]
    assert "[card number removed]" in out["content"]


def test_a_sentence_nobody_can_carry_out_is_refused_with_the_ones_that_work() -> None:
    """A rule that loads and does nothing is worse than one that fails: the
    author believes they are protected. So the vocabulary is closed and a
    sentence outside it is named, with the forms that exist printed under it."""
    with pytest.raises(InterceptorError) as e:
        Chain.from_document(
            {
                "agents": {"a": {"interceptors": ["x"]}},
                "interceptors": {
                    "x": {
                        "when": "step.message.before",
                        "may": ["hide-values"],
                        "rules": ["be careful about card numbers"],
                    }
                },
            },
            "a",
        )
    said = str(e.value)
    assert "interceptors/x.yaml:1, rule 1" in said, said
    assert "replace anything that looks like a <thing>" in said, said


def test_a_rule_that_does_more_than_the_interceptor_declared_is_refused_at_load() -> None:
    """`may:` is a review surface, so it is checked where a reviewer is — when
    the file is read — and not only after a body has already run."""
    with pytest.raises(InterceptorError, match="stop-the-run"):
        Chain.from_document(
            {
                "agents": {"a": {"interceptors": ["x"]}},
                "interceptors": {
                    "x": {
                        "when": "step.tool.before",
                        "may": ["hide-values"],
                        "rules": [
                            'if payments is called more than 1 time in one run, '
                            'stop and say "no"'
                        ],
                    }
                },
            },
            "a",
        )


def test_naming_a_rule_this_workspace_does_not_have_says_which_ones_it_does() -> None:
    with pytest.raises(InterceptorError) as e:
        Chain.from_document(
            {"agents": {"a": {"interceptors": ["redact-card-numberz"]}},
             "interceptors": {"redact-card-numbers": {}}},
            "a",
        )
    assert "redact-card-numbers" in str(e.value)
    assert "interceptors/redact-card-numberz.yaml" in str(e.value), "the fix must be typeable"


def test_a_halted_chain_does_not_keep_modifying() -> None:
    """A run that has been stopped must not then be quietly changed by a later
    rule — the audit trail would show a change to something that never happened."""
    ran_after = []
    c = Chain()
    c.add(guard("stop", "step.tool.before", lambda p: "not allowed"))
    c.add(guard("later", "step.tool.before", lambda p: ran_after.append(p) or None))
    out, d = c.run("step.tool.before", {"name": "secret-tool", "args": {}})
    assert d.stop == "not allowed"
    assert ran_after == [], "the later rule must not have run"


# --------------------------------------------------------- wired into the loop


def test_the_run_emits_a_full_event_trace() -> None:
    bus = Bus()
    s = Script([Turn("checking", (ToolCall("zendesk", {}),)), Turn("Approved.")])
    asyncio.run(run(SPEC, ReferenceTransport(s), "refund?", TOOLS, bus=bus))
    addresses = [str(e.address) for e in bus.log]
    for expected in [
        "session.run.started", "turn.run.started", "step.model.requested",
        "step.tool.started", "step.tool.completed", "turn.message.completed",
        "turn.run.completed",
    ]:
        assert expected in addresses, f"{expected} missing from {addresses}"


def test_an_interceptor_redacts_before_the_model_sees_anything() -> None:
    """The point of the whole mechanism. Eve cannot do this at any point."""
    seen_by_model = []

    class Watching(ReferenceTransport):
        async def model_call(self, system, history, tools):
            seen_by_model.append(history[0]["content"])
            return await super().model_call(system, history, tools)

    chain = Chain.from_document(
        {
            "agents": {"a": {"interceptors": ["cards"]}},
            "interceptors": {
                "cards": {
                    "when": "step.message.before",
                    "may": ["hide-values"],
                    "rules": [
                        'replace anything that looks like a card number with "[removed]"'
                    ],
                }
            },
        },
        "a",
    )
    asyncio.run(
        run(SPEC, Watching(Script([Turn("ok")])), "my card is 4111111111111111",
            TOOLS, chain=chain)
    )
    assert "4111111111111111" not in seen_by_model[0]
    assert "[removed]" in seen_by_model[0]


def test_an_interceptor_can_stop_a_tool_call() -> None:
    """PreToolUse interception — no equivalent exists in Eve."""
    called = []
    chain = Chain()
    chain.add(guard("no-payments", "step.tool.before",
                    lambda p: "refunds need a person" if p["name"] == "payments" else None))
    s = Script([Turn("paying", (ToolCall("payments", {}),))])
    r = asyncio.run(
        run(SPEC, ReferenceTransport(s), "refund?",
            {"payments": lambda a: called.append("ran") or "done"}, chain=chain)
    )
    assert r.halted == "stopped-by-rule"
    assert r.output == "refunds need a person"
    assert called == [], "the tool must not have executed"


def test_a_run_with_no_interceptors_is_unchanged() -> None:
    """The mechanism must cost nothing when unused."""
    s = Script([Turn("checking", (ToolCall("zendesk", {}),)), Turn("Approved.")])
    plain = asyncio.run(run(SPEC, ReferenceTransport(s), "refund?", TOOLS))
    s2 = Script([Turn("checking", (ToolCall("zendesk", {}),)), Turn("Approved.")])
    withbus = asyncio.run(run(SPEC, ReferenceTransport(s2), "refund?", TOOLS,
                              bus=Bus(), chain=Chain()))
    assert plain.trace() == withbus.trace()
    assert plain.halted == withbus.halted == "final"


# ────────────────────────────────────────────── the worked example, end to end


@pytest.fixture(scope="session")
def document() -> dict:
    """The worked example as the loader produces it — no author files read."""
    import json
    import subprocess

    repo = Path(__file__).resolve().parents[3]
    if not (repo / "target/debug/pact").exists():
        pytest.skip("build the CLI first")
    out = subprocess.run(
        [str(repo / "target/debug/pact"), "show", str(repo / "examples/refund-desk")],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def test_the_worked_examples_card_rule_actually_reaches_the_model_call(document: dict) -> None:
    """The one that would have caught the round this mechanism did nothing.

    `examples/refund-desk/interceptors/redact-card-numbers.yaml` says it stops
    card numbers reaching the model. For a round it did not: nothing read
    `interceptors:`, `run()` defaulted to an empty chain, and the file was inert
    while three landed documents said otherwise. So the assertion is not "the
    chain contains a rule" — it is what the transport was handed.
    """
    from pact_adapters.ir import AgentSpec

    seen_by_model: list[str] = []

    class Watching(ReferenceTransport):
        async def model_call(self, system, history, tools):
            seen_by_model.append(history[0]["content"])
            return await super().model_call(system, history, tools)

    desk = AgentSpec.from_document(document, "refund-desk")
    asyncio.run(
        run(
            desk,
            Watching(Script([Turn("Looking at it.")])),
            "please refund card 4111 1111 1111 1111 for order A-1182",
            TOOLS,
        )
    )
    assert seen_by_model, "the model was never called"
    assert "4111" not in seen_by_model[0], seen_by_model[0]
    assert "[card number removed]" in seen_by_model[0]
    assert "A-1182" in seen_by_model[0], "only the card number is hidden"


def test_the_worked_examples_second_refund_is_stopped_by_the_rule_that_says_so(
    document: dict,
) -> None:
    """`stop-runaway-refunds.yaml`, executing. The approval policy asks about
    the AMOUNT and so cannot see this: two ordinary-sized refunds in one
    conversation are two calls each of which is fine on its own."""
    from pact_adapters.ir import AgentSpec

    ran: list[str] = []
    desk = AgentSpec.from_document(document, "refund-desk")

    def script() -> Script:
        return Script([
            Turn("first", (ToolCall("payments", {"amount": "10.00 USD"}),)),
            Turn("second", (ToolCall("payments", {"amount": "10.00 USD"}),)),
        ])

    result = allowing_the_connection(
        desk, lambda: ReferenceTransport(script()), "refund it twice",
        {"payments": lambda a: ran.append("paid") or "refunded",
         "zendesk": lambda a: "lamp, broken"},
    )
    assert result.halted == "stopped-by-rule"
    assert "second refund" in result.output.lower(), result.output
    assert ran == ["paid"], "exactly one refund was issued"


# ────────────────────────── hiding a value inside a tool call (§7.10 gap 2)
#
# For a round a redaction reached a `message` payload's `content` and nothing
# else, and a rule bound at `step.tool.before` was REFUSED with the address to
# use instead. The refusal was honest and it still left the leak: the worked
# example exists to stop a card number leaving, and a card number typed into a
# `payments` argument is the likeliest way one does.


def _masking_tool_args(*rules: str, may: list[str] | None = None) -> dict:
    """The document an author writes for this: a document, not a callable."""
    return {
        "agents": {"a": {"interceptors": ["cards-in-calls"]}},
        "interceptors": {
            "cards-in-calls": {
                "when": "step.tool.before",
                "may": may if may is not None else ["hide-values"],
                "rules": list(rules) or [
                    'replace anything that looks like a card number with '
                    '"[card number removed]"'
                ],
            }
        },
    }


def test_a_card_number_inside_a_tool_calls_arguments_is_masked_before_the_tool_runs() -> None:
    """The fixture §7.10 named as the one that would force this.

    The assertion is what the TOOL was handed, not what the chain returned:
    `payments` is where the card number would actually have gone.
    """
    handed_over: list[dict] = []
    chain = Chain.from_document(_masking_tool_args(), "a")
    script = Script([
        Turn("paying", (ToolCall("payments", {
            "order": "A-1182",
            "amount": "10.00 USD",
            "card": {"number": "4111 1111 1111 1111"},
        }),)),
        Turn("Refunded."),
    ])
    asyncio.run(run(
        SPEC, ReferenceTransport(script), "refund it",
        {"zendesk": lambda a: "lamp, broken",
         "payments": lambda a: handed_over.append(a) or "refunded"},
        chain=chain,
    ))
    assert handed_over, "payments was never called"
    got = handed_over[0]
    assert "4111" not in json.dumps(got), got
    assert got["card"]["number"] == "[card number removed]"
    assert got["order"] == "A-1182", "only the card number is hidden"
    assert got["amount"] == "10.00 USD", "only the card number is hidden"


def test_a_card_number_nested_inside_another_argument_is_masked_too() -> None:
    """One sentence about card numbers has to mean all of them.

    An author who wrote `replace anything that looks like a card number` and got
    the top level only has been told something untrue by their own file — which
    is the same failure as a rule that loads and does nothing, one level down.
    """
    c = Chain.from_document(_masking_tool_args(), "a")
    out, _ = c.run("step.tool.before", {
        "name": "payments",
        "args": {"payer": {"cards": ["4111 1111 1111 1111", "keep me"]}},
    })
    assert out["args"]["payer"]["cards"] == ["[card number removed]", "keep me"]


def test_a_card_number_that_arrived_as_a_number_is_masked_and_an_amount_is_not() -> None:
    """`{"card": 4111111111111111}` is a string that skipped its quotes.

    Leaving it would make the rule false in a shape card numbers really arrive
    in. The type changes only where the value matched, so an amount that is a
    number is still a number afterwards.
    """
    c = Chain.from_document(_masking_tool_args(), "a")
    out, _ = c.run("step.tool.before", {
        "name": "payments",
        "args": {"card": 4111111111111111, "amount": 10.0, "retry": False},
    })
    assert out["args"]["card"] == "[card number removed]"
    assert out["args"]["amount"] == 10.0 and isinstance(out["args"]["amount"], float)
    assert out["args"]["retry"] is False


def test_a_rule_that_masks_inside_a_tool_call_must_have_declared_hide_values() -> None:
    """One sentence, one power.

    This used to accept any of the three change-powers, which is how `may:` came
    to mean "it changes something" rather than "it does this". A reviewer reading
    `may: [change-the-request]` over a masking rule learned less than the rules
    below it did.
    """
    with pytest.raises(InterceptorError) as e:
        Chain.from_document(_masking_tool_args(may=["stop-the-run"]), "a")
    said = str(e.value)
    assert "interceptors/cards-in-calls.yaml:1, rule 1" in said, said
    assert "- hide-values" in said, f"the fix must be typeable: {said}"


def test_a_power_the_rules_do_not_use_is_refused_naming_what_they_need() -> None:
    """WHAT THIS USED TO TEST, and why it changed.

    It held that `change-the-request` and `change-the-answer` were host-only,
    because "no sentence in the closed vocabulary rewrites". That was true when
    it was written and is false since two rewriting sentences landed (P8 wave 6,
    `50-NOT-COPIED.md` §8.5): a carried program is something a sentence can name,
    and §6's own condition for letting the powers back was "a sentence somebody
    actually wants".

    The premise went stale rather than being wrong — R29's shape — so the test
    moves to the property that survives, which is the one R24 really states:
    `may:` and the rules have to AGREE. Declaring a rewrite power beside rules
    that only mask is still refused, and the refusal now names what those rules
    actually need, which is the more useful half.
    """
    for declared in ("change-the-request", "change-the-answer"):
        with pytest.raises(InterceptorError) as e:
            Chain.from_document(_masking_tool_args(may=[declared]), "a")
        said = str(e.value)
        assert "hide" in said.lower(), said
        assert "hide-values" in said, "and the line to type: " + said


def test_the_three_change_powers_are_told_apart_rather_than_counted_as_one() -> None:
    """The gap §7.10 published: a `changed` needed ANY of the three and which
    one was never asked. `change-the-request` is a change power and it no longer
    covers a hiding — the decision says which, and the check reads it."""
    masking = Interceptor(
        "m", "step.tool.before", frozenset({Power.CHANGE_REQUEST}),
        lambda p: Decision(changed=dict(p), by=Power.HIDE_VALUES),
    )
    with pytest.raises(Refused, match="tried to hide values"):
        masking.apply({"name": "payments", "args": {}})


def test_a_change_that_will_not_say_which_power_it_used_is_refused() -> None:
    """Nothing can hold an unlabelled change to `may:`, and waving it through
    against the union of the three is the one-bit enforcement this replaces."""
    anonymous = Interceptor(
        "a", "step.tool.before", frozenset({Power.HIDE_VALUES}),
        lambda p: Decision(changed=dict(p)),
    )
    with pytest.raises(Refused, match="which power"):
        anonymous.apply({"name": "payments", "args": {}})


def test_a_redaction_bound_where_nothing_carries_values_is_still_refused_at_load() -> None:
    """Two addresses now carry values, not all of them. `step.delegate.before`
    carries a list of who is being asked, so a redaction there would load and do
    nothing — and the refusal names both addresses that work."""
    with pytest.raises(InterceptorError) as e:
        Chain.from_document(
            {
                "agents": {"a": {"interceptors": ["x"]}},
                "interceptors": {
                    "x": {
                        "when": "step.delegate.before",
                        "may": ["hide-values"],
                        "rules": [
                            'replace anything that looks like a card number '
                            'with "[removed]"'
                        ],
                    }
                },
            },
            "a",
        )
    said = str(e.value)
    assert "step.message.before" in said and "step.tool.before" in said, said


def test_a_run_with_no_interceptors_is_byte_identical_to_one_that_never_had_the_mechanism() -> None:
    """§7.10's INT invariant, now measured over a tool call that carries
    arguments — the trace field this work reaches into. Byte-identical means
    byte-identical, so the comparison is over the serialised form rather than
    over two objects that compare equal for a reason of their own."""

    def script() -> Script:
        return Script([
            Turn("paying", (ToolCall("payments", {
                "order": "A-1182", "card": {"number": "4111 1111 1111 1111"},
            }),)),
            Turn("Refunded."),
        ])

    never = asyncio.run(run(SPEC, ReferenceTransport(script()), "refund it", TOOLS))
    wired = asyncio.run(run(SPEC, ReferenceTransport(script()), "refund it", TOOLS,
                            bus=Bus(), chain=Chain()))
    assert json.dumps(never.trace()) == json.dumps(wired.trace())
    assert never.halted == wired.halted == "final"
    assert never.output == wired.output


def test_a_masked_tool_call_is_recorded_masked_in_the_runs_own_trace() -> None:
    """The trace IS the transcript, so masking has to reach the record.

    A card number the tool never saw but the run's own record kept has still
    left the building, which is the one thing
    `interceptors/redact-card-numbers.yaml` exists to stop. The harness hands
    `checked["args"]` to the tool and then appends the ORIGINAL call, so today
    the two disagree about what happened.
    """
    chain = Chain.from_document(_masking_tool_args(), "a")
    script = Script([
        Turn("paying", (ToolCall("payments", {"card": "4111 1111 1111 1111"}),)),
        Turn("Refunded."),
    ])
    result = asyncio.run(run(
        SPEC, ReferenceTransport(script), "refund it", TOOLS, chain=chain,
    ))
    assert "4111" not in json.dumps(result.trace()), result.trace()


def test_the_worked_example_masks_a_card_number_inside_a_payments_call(document: dict) -> None:
    """The worked example's own claim, measured where it matters.

    `step.message.before` catches what the customer typed. It cannot catch a
    card number that came back out of a ticket and went into the `payments` call
    the model then made — by then it has long since run. That is the SECOND
    moment on `redact-card-numbers.yaml`'s `when:` list, and it was a second file
    until `when:` could hold two.
    """
    handed_over: list[dict] = []
    desk = AgentSpec.from_document(document, "refund-desk")

    def script() -> Script:
        return Script([
            Turn("paying", (ToolCall("payments", {
                "order-number": "A-1182", "card": "4111 1111 1111 1111",
            }),)),
            Turn("Refunded."),
        ])

    allowing_the_connection(
        desk, lambda: ReferenceTransport(script()), "refund order A-1182",
        {"zendesk": lambda a: "lamp, broken",
         "payments": lambda a: handed_over.append(a) or "refunded"},
    )
    assert handed_over, "payments was never called"
    assert "4111" not in json.dumps(handed_over[0]), handed_over[0]
    assert handed_over[0]["order-number"] == "A-1182", "only the card number is hidden"


# ────────────────────────────── send-elsewhere: G5's third outcome, executing

# `send-elsewhere` was declarable, refused when undeclared, and short-circuited
# the chain — and no address acted on it, so an interceptor declaring it changed
# nothing. §7.10 published that as gap (1) rather than leaving it to be
# discovered. These are the fixtures that close it: a sentence an author can
# type, an address that carries it out, and a refusal everywhere it would not be.

#: Two stages, mirroring `examples/refund-desk/loops/careful.yaml` in shape:
#: ordinary work, and a stage whose whole job is to look again — which is where
#: a rule sends a run that is about to do something for the second time. Written
#: here rather than read from the example so these tests hold the mechanism
#: rather than one workspace's copy of it.
CHECKING_LOOP = Loop.from_mapping(
    "checking",
    {
        "starts-at": "gather",
        "steps": {
            "gather": {
                "does": "use-tools",
                "then": {"used-a-tool": "gather", "answered": "done"},
            },
            "re-read": {
                "does": "check-its-work",
                "may-use": ["zendesk"],
                "then": {"used-a-tool": "re-read", "answered": "done"},
            },
        },
    },
)

SECOND_REFUND_GOES_BACK = (
    "if payments is called more than 1 time in one run, "
    "go to the re-read stage instead"
)


def _one_rule(sentence: str, may: list[str], when: str = "step.tool.before") -> Chain:
    """One interceptor, built through the door an author's file goes through.

    `Chain.from_document` deliberately, never a hand-built `Interceptor`: a test
    that constructs the body itself proves the builder works and proves nothing
    about the sentence somebody actually types, which is exactly the gap that let
    `redact-card-numbers.yaml` load, validate and do nothing for a round.
    """
    return Chain.from_document(
        {
            "agents": {"a": {"interceptors": ["x"]}},
            "interceptors": {"x": {"when": when, "may": may, "rules": [sentence]}},
        },
        "a",
    )


def test_a_rule_may_send_the_run_to_another_stage_instead_of_doing_the_call() -> None:
    """The sentence exists, so a redirect can be ASKED for without code."""
    chain = _one_rule(SECOND_REFUND_GOES_BACK, ["send-elsewhere"])
    _, decision = chain.run(
        "step.tool.before",
        {"name": "payments", "args": {}, "so-far": ["zendesk", "payments"]},
    )
    assert decision.redirect == "re-read"
    assert decision.stop is None, "a redirect is not a stop wearing a different name"


def test_the_same_rule_leaves_the_first_call_alone() -> None:
    """One condition, counted from the run's own record — `more than 1 time`
    means the second one, not every one."""
    chain = _one_rule(SECOND_REFUND_GOES_BACK, ["send-elsewhere"])
    _, decision = chain.run(
        "step.tool.before", {"name": "payments", "args": {}, "so-far": ["zendesk"]}
    )
    assert decision.is_noop


def test_a_redirect_rule_that_did_not_declare_send_elsewhere_is_refused_at_load() -> None:
    """`may:` is a review surface, so it is checked where a reviewer is — when
    the file is read — and the refusal carries the line to type."""
    with pytest.raises(InterceptorError) as e:
        _one_rule(SECOND_REFUND_GOES_BACK, ["stop-the-run"])
    said = str(e.value)
    assert "interceptors/x.yaml:1, rule 1" in said, said
    assert "- send-elsewhere" in said, "the fix must be typeable"


def test_a_redirect_bound_where_nothing_carries_one_out_is_refused_with_the_address() -> None:
    """The check that stops this power going back to being decoration.

    A redirect is acted on at `step.tool.before` and nowhere else, so a rule
    bound at an address that would never carry it out is refused when the file is
    read — rather than loading, validating, and doing nothing, which is what
    `send-elsewhere` amounted to at every address for a round.
    """
    with pytest.raises(InterceptorError) as e:
        _one_rule(SECOND_REFUND_GOES_BACK, ["send-elsewhere"], when="turn.message.after")
    said = str(e.value)
    assert "would do nothing" in said, said
    assert "step.tool.before" in said, "the fix must be typeable"


#: Every address the reference harness hands to `Chain.run`, plus four it never
#: does. The four are the point: a rule bound at one of them used to load
#: cleanly, so the three enumerations below would pass vacuously without them.
WIRED_AND_NOT = [
    "step.message.before", "step.tool.before", "step.delegate.before",
    "step.message.after", "turn.message.after",
    "step.tool.completed", "step.tool.after", "turn.message.before",
    "session.message.before", "action.tool.before",
]


def _accepted_at(sentence: str, may: list[str]) -> list[str]:
    """Which of those addresses this sentence is allowed to be bound at."""
    out = []
    for when in WIRED_AND_NOT:
        try:
            _one_rule(sentence, may, when=when)
        except InterceptorError:
            continue
        out.append(when)
    return out


def test_a_redirect_is_accepted_only_where_the_harness_carries_one_out() -> None:
    """The enumeration that keeps this power from going inert again.

    §7.10 lists five addresses the reference harness binds. Exactly one of them
    can send a run somewhere else — before a tool runs — and every other address,
    bound or not, refuses the rule rather than accepting a promise it cannot
    keep. An address added to `WIRED` without `somewhere_else` fails here.
    """
    assert _accepted_at(SECOND_REFUND_GOES_BACK, ["send-elsewhere"]) == list(
        REDIRECTS_AT
    ) == ["step.tool.before"]


def test_a_redaction_is_accepted_only_where_the_run_is_holding_values() -> None:
    """The same enumeration for `hide-values`, which did not have one.

    Its check read the address's SUBJECT — `if subject not in REDACTS` — and
    `REDACTS` was keyed on `message` and `tool`, so four addresses the harness
    never emits passed it: `step.tool.after`, `turn.message.before`,
    `session.message.before`, `action.tool.before`. A card-number rule bound at
    any of them loaded, validated, and masked nothing — the identical failure
    `REDIRECTS_AT` exists to stop for redirects, left standing in the power the
    worked example actually depends on.

    FIVE addresses honour a hiding. `step.tool.completed` was on the list above
    for a round, and it was the one entry that named a real moment: the run
    reaches it, a watch could already bind there, and the chain was simply never
    handed it — so a card number the agent typed was masked and the same card
    number a tool RETURNED was not, while `redaction.yaml`'s own promise is
    "what must never leave this workspace". It is a moment now, not a mistake.
    """
    masks = 'replace anything that looks like a card number with "[gone]"'
    assert _accepted_at(masks, ["hide-values"]) == [
        "step.message.before", "step.tool.before",
        "step.message.after", "turn.message.after", "step.tool.completed",
    ]


def test_a_counting_rule_is_accepted_only_where_the_run_knows_which_tool_it_is() -> None:
    """And the same for the two sentences that count calls, which had no check.

    `stop and say "…"` reads `name` and `so-far` out of the payload, and only
    `step.tool.before` carries them. Bound anywhere else it loaded, saw neither
    field, and answered "no" forever — while its twin, which shares the counter
    and differs only in the ending, was checked. `stop-runaway-refunds.yaml` was
    correct by luck of its `when:` line.
    """
    stops = 'if payments is called more than 1 time in one run, stop and say "no"'
    assert _accepted_at(stops, ["stop-the-run"]) == ["step.tool.before"]
    said = ""
    try:
        _one_rule(stops, ["stop-the-run"], when="turn.message.after")
    except InterceptorError as e:
        said = str(e)
    assert "counts tool calls" in said, said
    assert "step.tool.before" in said, "the fix must be typeable"


def test_a_bank_account_written_the_way_people_write_it_is_masked_too() -> None:
    """The second sentence of `redact-card-numbers.yaml`, measured.

    It used to be largely decorative. The IBAN alternative required the part
    after the country code to be a whole number of four-character groups, which
    no real IBAN written without spaces is, and the UK alternative required the
    account number to follow the sort code with exactly one space and no words
    between — which is not how anybody types it. The test that shipped with the
    rule only asserted `"4111" not in ...`, so the bank half of the file's own
    claim went unmeasured and was mostly false.

    The last probe is the overlap case: sixteen of an IBAN's characters are
    digits, so the card sentence and the bank sentence both match there, and
    which one won used to depend on which the author wrote first — leaving
    `GB29 NWBK` standing beside the replacement. Longest match wins now.
    """
    masks = _one_rule(
        'replace anything that looks like a card number with "[removed]"',
        ["hide-values"],
    )
    both = Chain.from_document(
        {
            "agents": {"a": {"interceptors": ["x"]}},
            "interceptors": {"x": {
                "when": "step.tool.before",
                "may": ["hide-values"],
                "rules": [
                    'replace anything that looks like a card number with "[removed]"',
                    "do the same for anything that looks like a bank account",
                ],
            }},
        },
        "a",
    )
    for probe in (
        "IBAN GB33BUKB20201555555555",
        "sort code 12-34-56 account 12345678",
        "DE89 3704 0044 0532 0130 00",
        "my iban is GB29 NWBK 6016 1331 9268 19",
    ):
        out, _ = both.run("step.tool.before", {"name": "payments", "args": {"note": probe}})
        left = out["args"]["note"]
        assert not re.search(r"[A-Z]{2}\d{2}|\d{4}", left), f"{probe!r} left {left!r}"
    # And the card rule on its own still leaves a bank account alone, so the
    # second sentence is doing the work rather than the first over-reaching.
    alone, _ = masks.run(
        "step.tool.before", {"name": "payments", "args": {"note": "sort code 12-34-56"}}
    )
    assert alone["args"]["note"] == "sort code 12-34-56"


def test_a_diagnostic_names_the_file_the_rule_is_really_in_and_the_line(tmp_path) -> None:
    """Every diagnostic names a file, a line, what is wrong, and a fix.

    These named `interceptors/<name>.yaml` — a path SYNTHESISED from the entry's
    name — and no line at all. In the folder-of-folders spelling the loader
    accepts, and which `digest_equality_for_the_new_kinds.rs` exists to
    guarantee, that path does not exist on disk: the author was sent to a file
    they could not open.
    """
    folder = tmp_path / "interceptors" / "stop-runaway-refunds"
    folder.mkdir(parents=True)
    (folder / "interceptor.yaml").write_text(
        "description: Stops a runaway.\n"
        "when: step.tool.before\n"
        "may:\n"
        "  - stop-the-run\n"
        "rules:\n"
        "  - escalate to a manager if the customer seems angry\n"
    )
    with pytest.raises(InterceptorError) as e:
        Chain.from_document(
            {
                "agents": {"a": {"interceptors": ["stop-runaway-refunds"]}},
                "interceptors": {"stop-runaway-refunds": {
                    "when": "step.tool.before",
                    "may": ["stop-the-run"],
                    "rules": ["escalate to a manager if the customer seems angry"],
                }},
            },
            "a",
            tmp_path,
        )
    said = str(e.value)
    assert "interceptors/stop-runaway-refunds/interceptor.yaml:6" in said, said
    assert "is not a rule PACT knows how to carry out" in said, said
    assert "replace anything that looks like a <thing>" in said, "the fix must be typeable"


def test_a_redirect_from_an_interceptor_without_the_power_is_refused_mid_run() -> None:
    """The after-the-fact check, reached through the harness.

    Load-time and after-the-fact answer different questions and both are kept: a
    host that builds an `Interceptor` in its own process (§5.5's typed escape)
    never passes through the sentence compiler, so this is the only check it
    meets — and the harness must not swallow it.
    """
    chain = Chain()
    chain.add(
        Interceptor(
            "sneaky", "step.tool.before", frozenset({Power.STOP}),
            lambda p: Decision(redirect="re-read"),
        )
    )
    script = Script([Turn("paying", (ToolCall("payments", {}),))])
    with pytest.raises(Refused) as e:
        asyncio.run(
            run(SPEC, ReferenceTransport(script), "refund?", TOOLS,
                chain=chain, loop=CHECKING_LOOP)
        )
    assert "sneaky" in str(e.value), str(e.value)
    assert "stop-the-run" in str(e.value), "it must say what it may do instead"


def test_a_redirect_rule_that_never_fires_leaves_the_run_byte_identical() -> None:
    """The mechanism must cost nothing when it is not asked for — the same bar
    `pact:loop/standard` is held to."""
    def script() -> Script:
        return Script([
            Turn("paying", (ToolCall("payments", {}),)),
            Turn("Refunded."),
        ])

    plain = asyncio.run(
        run(SPEC, ReferenceTransport(script()), "refund?", TOOLS, loop=CHECKING_LOOP)
    )
    ruled = asyncio.run(
        run(SPEC, ReferenceTransport(script()), "refund?", TOOLS, loop=CHECKING_LOOP,
            chain=_one_rule(SECOND_REFUND_GOES_BACK, ["send-elsewhere"]))
    )
    assert plain.trace() == ruled.trace()
    assert plain.phases == ruled.phases == ["gather", "gather"]
    assert plain.halted == ruled.halted == "final"


def test_a_redirect_changes_which_stage_runs_next() -> None:
    """G5's third outcome, executing — the one thing that made `send-elsewhere`
    a promise rather than a power.

    A second refund does not end the run here; it sends it back to the stage
    that reads the decision against the policy, which cannot reach `payments` at
    all. That is a thing `stop-the-run` cannot express: stopping is the only
    ending it has.
    """
    paid: list[str] = []
    bus = Bus()
    script = Script([
        Turn("first", (ToolCall("payments", {}),)),
        Turn("second", (ToolCall("payments", {}),)),
        Turn("Checked it against the policy."),
    ])
    r = asyncio.run(
        run(SPEC, ReferenceTransport(script), "refund it twice",
            {"payments": lambda a: paid.append("paid") or "refunded",
             "zendesk": lambda a: "lamp, broken"},
            chain=_one_rule(SECOND_REFUND_GOES_BACK, ["send-elsewhere"]),
            loop=CHECKING_LOOP, bus=bus)
    )
    assert r.phases == ["gather", "gather", "re-read"], r.phases
    assert paid == ["paid"], "the second refund never happened"
    assert r.halted == "final"
    assert r.output == "Checked it against the policy."


def test_a_redirected_call_is_recorded_as_asked_for_and_not_done() -> None:
    """T7: an action the model really took is never silently dropped.

    The redirected call was DECIDED, the way a call refused by `may-use:` is, so
    it stays in the step carrying the reason — and the model reads that reason on
    its next turn instead of finding that what it asked for simply never
    happened.
    """
    bus = Bus()
    script = Script([
        Turn("first", (ToolCall("payments", {}),)),
        Turn("second", (ToolCall("payments", {}),)),
        Turn("Checked it against the policy."),
    ])
    r = asyncio.run(
        run(SPEC, ReferenceTransport(script), "refund it twice", TOOLS,
            chain=_one_rule(SECOND_REFUND_GOES_BACK, ["send-elsewhere"]),
            loop=CHECKING_LOOP, bus=bus)
    )
    second = r.steps[1]
    assert [c.name for c in second.tool_calls] == ["payments"]
    assert "not done" in second.tool_results[0], second.tool_results[0]
    assert "re-read" in second.tool_results[0], second.tool_results[0]

    # A redirect is never a silent departure: the ledger carries both the call
    # that did not happen and the stage the run went to instead.
    cancelled = [e for e in bus.seen("step.tool.cancelled")]
    assert cancelled and "re-read" in cancelled[0].payload["reason"], cancelled
    stages = [e for e in bus.seen("step.stage.completed")]
    assert any(e.payload.get("outcome") == "sent-elsewhere" for e in stages), stages
    assert any(e.payload.get("to") == "re-read" for e in stages), stages


def test_a_redirect_to_a_stage_the_loop_has_not_got_fails_before_the_first_model_call() -> None:
    """A typo'd destination costs nothing, because it is caught before the run.

    An interceptor document does not know which loop will be in force — the same
    reason §7.12's REF-3 gives for `may-use:` — so `pact check` has nothing to
    resolve the name against. The AGENT does: it names both its `loop:` and its
    `interceptors:`, so the harness holds every destination against the loop
    beside `Loop.check_against`, whose own docstring sets the standard — *"a typo
    in a rarely-taken branch fails at the start of the run instead of forty steps
    in"*. A redirect destination IS that rarely-taken branch.

    For a round it was exempt, and the cost is what this test used to assert:
    two steps, a model call, and a real refund issued before one wrong character
    surfaced. Now nothing runs at all.
    """
    ran: list[str] = []
    r = asyncio.run(
        run(SPEC, ReferenceTransport(Script([
                Turn("first", (ToolCall("payments", {}),)),
                Turn("second", (ToolCall("payments", {}),)),
            ])),
            "refund it twice",
            {"payments": lambda a: ran.append("paid") or "refunded",
             "zendesk": lambda a: "lamp, broken"},
            chain=_one_rule(
                "if payments is called more than 1 time in one run, "
                "go to the reread stage instead",
                ["send-elsewhere"],
            ),
            loop=CHECKING_LOOP)
    )
    assert r.halted == "loop-error"
    # The loop's own diagnostic, not a second one written for interceptors —
    # a second message would be the one telling an author which stages exist
    # while the loop file changed underneath it.
    assert "no stage called 'reread'" in r.output, r.output
    assert "gather, re-read" in r.output, "the stages that exist must be listed"
    assert "`reread:` stage under `steps:`" in r.output, "the fix must be typeable"
    assert r.steps == [], "nothing ran: the check is before the first model call"
    assert ran == [], "no refund was issued to discover a typo"


def test_a_rule_that_says_it_covers_everything_reaches_an_agent_that_never_names_it() -> None:
    """Redaction was opt-in per agent while watching — which can do nothing — was
    workspace-wide, so the worked example's card-number rules covered ONE of its
    three agents. `fraud-checker` reads Zendesk tickets, the very source
    `redact-card-numbers.yaml` names as carrying "whatever the customer pasted
    into it last week", with no redaction at all. The polarity was backwards
    from the argument the schema itself makes for keeping `watch:`
    workspace-scoped: the agent that forgets to list a rule is the one that
    leaks.
    """
    import json as _json
    import subprocess as _sub
    import sys as _sys
    from pathlib import Path as _Path

    repo = _Path(__file__).resolve().parents[3]
    binary = repo / "target/debug/pact"
    if not binary.exists():
        import pytest as _pytest

        _pytest.skip("build the CLI first")
    doc = _json.loads(
        _sub.run([str(binary), "show", str(repo / "examples/refund-desk")],
                 capture_output=True, text=True, check=True).stdout
    )
    _sys.path.insert(0, str(repo / "adapters/python/src"))
    from pact_adapters.interceptors import Chain

    # `fraud-checker` names no interceptors at all.
    assert not (doc["agents"]["fraud-checker"].get("interceptors") or [])
    covered = Chain.from_document(doc, "fraud-checker")
    assert [i.name for i in covered.interceptors] == [
        "redact-card-numbers",
        REDACTION,
    ], "an agent that names nothing must still be covered by the workspace rules"

    # And a card number really is masked on the way to the model, on the agent
    # that never asked for it.
    changed, _ = covered.run("step.message.before", {"content": "card 4111 1111 1111 1111"})
    assert "4111" not in changed["content"], changed
    assert "[card number removed]" in changed["content"]

    # The agent that DOES name a rule keeps it, and the workspace rules run
    # FIRST — the chain threads each change into the next, so a redaction that
    # runs after a guard has read the value has redacted nothing.
    desk = Chain.from_document(doc, "refund-desk")
    assert [i.name for i in desk.interceptors] == [
        "redact-card-numbers",
        REDACTION,
        "stop-runaway-refunds",
    ], "its own rule is added after the workspace ones, never instead of them"
