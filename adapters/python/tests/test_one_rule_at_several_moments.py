"""One rule, several moments — `interceptor.when` as a list.

`when:` held ONE address, so a rule that had to run at two moments had to be
written twice, and the worked example shipped the proof. Measured on the tree as
it stood:

    $ diff examples/refund-desk/interceptors/redact-card-numbers.yaml \\
           examples/refund-desk/interceptors/redact-card-numbers-in-tool-calls.yaml

differed in exactly two settings — `description:` and `when:`
(`step.message.before` against `step.tool.before`). Same `applies-to:`, same
`may:`, the same two sentences copied out word for word. A card number that came
back out of a Zendesk ticket and went into a `payments` argument is a different
MOMENT, not a different rule, and the second file existed only because the field
could not say so.

The tests below are about the AUTHOR'S line reaching the run. Every one of them
that asserts behaviour loads `examples/refund-desk` through the real loader and
passes no chain, no rule and no address of its own — because a test that builds
the object itself proves the object works and says nothing about whether the
second line of `when:` ever gets there. That is the defect this project has
shipped five rounds running.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from consenting import allowing_the_connection  # noqa: E402
from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.interceptors import (  # noqa: E402
    Chain, Interceptor, InterceptorError, Power,
)
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples/refund-desk"
CARD = "4111 1111 1111 1111"


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    """The worked example as the real loader produces it.

    The same door every other worked-example test uses (invariant P-1 — an
    adapter consumes the loaded document and never the tree), so nothing here
    re-implements the Expansion Rule and nothing here can accidentally test a
    document this test wrote.
    """
    binary = REPO / "target/debug/pact"
    if not binary.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(binary), "show", str(EXAMPLE)], capture_output=True, text=True
    )
    if out.returncode != 0:
        pytest.skip(f"the worked example does not currently load:\n{out.stderr}")
    return json.loads(out.stdout)


def _rule(doc: dict[str, Any], name: str) -> dict[str, Any]:
    return dict(doc["interceptors"][name])


def _one(raw: dict[str, Any], agent: str = "a") -> Chain:
    """A chain over one rule, for the REFUSAL tests only.

    Used where the thing under test is a diagnostic and the document has to be
    wrong on purpose — never where the thing under test is behaviour.
    """
    return Chain.from_document(
        {"agents": {agent: {"interceptors": ["x"]}}, "interceptors": {"x": raw}}, agent
    )


def _without_the_floor(doc: dict[str, Any]) -> dict[str, Any]:
    """The loaded document with `redaction.yaml` taken out of it.

    The workspace redaction is bound to EVERY moment that carries values, by
    construction — "must never leave" is not a statement about one point in a
    run. It therefore hides a card number in a tool argument whatever
    `interceptor.when` says, which makes it an alternative explanation for
    anything measured at `step.tool.before`. Removing it is what turns "a card
    number was hidden" into "THIS rule's second moment hid it".

    A copy, never the fixture: the fixture is module-scoped and every other test
    here wants the workspace exactly as its author wrote it.
    """
    out = json.loads(json.dumps(doc))
    out.pop("redaction", None)
    return out


# ───────────────────────────────────────────── the author's two lines, executing


def test_the_worked_example_ships_one_card_number_rule_bound_to_two_moments(
    document: dict,
) -> None:
    """The duplication is gone from the tree, and the cover is not.

    Both halves matter. A tree with one file and one moment would pass a test
    that only counted files while leaving `payments` unprotected — which is the
    trade this change refuses to make.
    """
    declared = document["interceptors"]
    card = [n for n in declared if "card" in n]
    assert card == ["redact-card-numbers"], (
        "one rule about card numbers, not one per moment: " f"{sorted(declared)}"
    )
    assert declared["redact-card-numbers"]["when"] == [
        "step.message.before",
        "step.tool.before",
    ], "both moments have to survive the merge, or the tool call is unprotected"
    assert not (EXAMPLE / "interceptors/redact-card-numbers-in-tool-calls.yaml").exists()


def test_a_rule_that_names_two_moments_runs_at_both_of_them(document: dict) -> None:
    """The line that reads the second entry is `Chain.at`, and this is what it buys.

    Nothing here writes an address: both are the author's, read out of
    `interceptors/redact-card-numbers.yaml` by the loader. `fraud-checker` is
    used deliberately — it names no interceptors at all, so everything below
    arrives through `applies-to: every-agent` and the file's own `when:` list.

    The workspace redaction is taken out of the document first. It binds to every
    moment that carries values by construction, so with it in place a masked card
    number in a tool argument has two possible explanations and this test would
    measure neither.
    """
    covered = Chain.from_document(_without_the_floor(document), "fraud-checker")
    assert [i.name for i in covered.interceptors] == ["redact-card-numbers"]

    typed, _ = covered.run("step.message.before", {"content": f"my card is {CARD}"})
    assert "4111" not in typed["content"], typed
    assert "[card number removed]" in typed["content"]

    handed, _ = covered.run(
        "step.tool.before", {"name": "payments", "args": {"card": CARD}}
    )
    assert "4111" not in json.dumps(handed["args"]), handed
    assert "[card number removed]" in json.dumps(handed["args"])


def test_deleting_the_second_moment_from_the_authors_file_leaves_the_tool_call_open(
    document: dict,
) -> None:
    """The same document with one line taken out, to show the line is load-bearing.

    This is the control for the test above. If `step.tool.before` came from
    anywhere but the author's file — a default, a second builder, the address the
    harness happens to emit — removing it would change nothing and the test above
    would be measuring the harness rather than the document.
    """
    doc = _without_the_floor(document)
    doc["interceptors"]["redact-card-numbers"]["when"] = ["step.message.before"]

    narrowed = Chain.from_document(doc, "fraud-checker")
    handed, _ = narrowed.run(
        "step.tool.before", {"name": "payments", "args": {"card": CARD}}
    )
    assert handed["args"]["card"] == CARD, (
        "with the second moment deleted the card must go through untouched — "
        "otherwise something other than `when:` is deciding this"
    )
    # And the first moment still works, so what changed is the moment and not
    # the rule.
    typed, _ = narrowed.run("step.message.before", {"content": f"card {CARD}"})
    assert "4111" not in typed["content"]


def test_a_card_number_coming_back_from_a_ticket_never_reaches_payments(
    document: dict,
) -> None:
    """The whole run, end to end, with nothing passed in.

    This is the argument the deleted file was written to make, carried into the
    surviving one: `step.message.before` catches what the customer typed and
    cannot catch what comes back the other way — a ticket read out of Zendesk
    carries whatever the customer pasted into it last week, and the model is
    perfectly capable of copying that into the `payments` call it then makes. By
    then `step.message.before` has long since run.

    No chain is handed to `run()`. The agent's chain is built from the document,
    and — with the workspace redaction taken out, for the reason `_without_the_floor`
    gives — the second entry of `when:` is the only thing standing between that
    card number and the payment processor.
    """
    handed_over: list[dict] = []
    desk = AgentSpec.from_document(_without_the_floor(document), "refund-desk")

    def script() -> Script:
        return Script([
            Turn("reading the ticket", (ToolCall("zendesk", {"order": "A-1182"}),)),
            Turn("paying", (ToolCall("payments", {
                "order-number": "A-1182", "card": {"number": CARD},
            }),)),
            Turn("Refunded."),
        ])

    result = allowing_the_connection(
        desk, lambda: ReferenceTransport(script()), "refund order A-1182",
        {"zendesk": lambda a: f"lamp, broken. customer left {CARD} in the ticket",
         "payments": lambda a: handed_over.append(a) or "refunded"},
    )
    assert handed_over, f"payments was never called: {result.output}"
    assert "4111" not in json.dumps(handed_over[0]), handed_over[0]
    assert handed_over[0]["order-number"] == "A-1182", "only the card number is hidden"
    assert handed_over[0]["card"]["number"] == "[card number removed]", (
        "nested arguments too — a card number in `card.number` has left the "
        "building exactly as surely as one at the top"
    )
    # The RECORD of that call, not only the call: a card number the tool never
    # saw but the transcript kept has still left the building.
    #
    # The call, specifically. What the ticket said comes back as a tool RESULT,
    # and no address in `WIRED` is handed one — `step.tool.completed` is a moment
    # a watch may name and not one a rule is offered, so nothing here can mask
    # what a tool returned. That is a real hole and it is not this one; it needs
    # an address that carries a result, which is a row in `WIRED` and a line in
    # `interceptor.when`'s `reaches:` list.
    calls = [c for step in result.trace() for c in step["tools"]]
    assert calls, result.trace()
    assert "4111" not in json.dumps(calls), calls


# ─────────────────────────────────────────── what a list of moments now REFUSES


def test_a_moment_that_is_not_one_is_refused_wherever_in_the_list_it_sits() -> None:
    """Every entry is checked, not just the first one.

    A list checked only at its head is a list that quietly accepts a typo on
    every line after the first — and the line after the first is exactly where a
    rule's second moment lives.
    """
    for when in (["step.banana.before", "step.tool.before"],
                 ["step.tool.before", "step.banana.before"]):
        with pytest.raises(InterceptorError) as e:
            _one({
                "when": when,
                "may": ["hide-values"],
                "rules": ['replace anything that looks like a card number with "x"'],
            })
        assert "'banana' is not something that happens" in str(e.value), e.value


def test_a_rule_no_named_moment_can_carry_out_is_refused_with_the_moments_to_type() -> None:
    """The refusal a list must not lose.

    `stop and say "…"` counts tool calls out of `name` and `so-far`, which only a
    moment that knows which tool is about to run supplies. Bound where nothing
    does, it loads, answers "no" forever, and every refund after the first goes
    through. Writing two moments instead of one must not be a way past that
    check.
    """
    with pytest.raises(InterceptorError) as e:
        _one({
            "when": ["step.message.before", "turn.message.after"],
            "may": ["stop-the-run"],
            "rules": ['if payments is called more than 1 time in one run, '
                      'stop and say "no"'],
        })
    said = str(e.value)
    assert "counts tool calls" in said, said
    # Both moments named, so the author can see which lines are the problem.
    assert "step.message.before" in said and "turn.message.after" in said, said
    assert "step.tool.before" in said, "the fix must be typeable"


def test_a_sentence_one_of_the_named_moments_can_carry_out_is_accepted() -> None:
    """The composition the list exists for, held explicitly.

    Redact at two moments and count tool calls at the one that knows the tool.
    Demanding that EVERY named moment carry EVERY sentence would refuse this and
    send the author straight back to two files, which is what this change
    removes.
    """
    chain = _one({
        "when": ["step.message.before", "step.tool.before"],
        "may": ["hide-values", "stop-the-run"],
        "rules": [
            'replace anything that looks like a card number with "[gone]"',
            'if payments is called more than 1 time in one run, stop and say "twice"',
        ],
    })
    # The redaction reaches both moments.
    typed, _ = chain.run("step.message.before", {"content": f"card {CARD}"})
    assert "[gone]" in typed["content"]
    # And the count reaches the one that knows the tool.
    _, decision = chain.run(
        "step.tool.before",
        {"name": "payments", "args": {}, "so-far": ["payments"]},
    )
    assert decision.stop == "twice", decision
    # While the moment that cannot count simply does not.
    _, quiet = chain.run("step.message.before", {"content": "hello"})
    assert quiet.stop is None


# ────────────────────────────────────────── one moment, written the way it was


def test_a_rule_that_names_one_moment_with_no_dash_still_loads(document: dict) -> None:
    """Nobody has to learn a list to write their first interceptor.

    `interceptors/stop-runaway-refunds.yaml` still says `when: step.tool.before`
    on one line, and the loader still hands that through as a bare string. It is
    the one-element list it means, and it goes on working exactly as written.
    """
    assert _rule(document, "stop-runaway-refunds")["when"] == "step.tool.before"

    desk = Chain.from_document(document, "refund-desk")
    runaway = next(i for i in desk.interceptors if i.name == "stop-runaway-refunds")
    assert runaway.when == ("step.tool.before",)

    _, decision = desk.run(
        "step.tool.before",
        {"name": "payments", "args": {}, "so-far": ["payments"]},
    )
    assert decision.stop and "needs a person" in decision.stop, decision


def test_one_address_written_as_a_plain_string_is_never_read_letter_by_letter() -> None:
    """A string is iterable, which is how this would fail silently.

    `any(addr.matches(w) for w in "step.tool.before")` asks about nineteen single
    characters, matches none of them, and binds the rule to nothing at all — no
    error, no diagnostic, just a rule that never fires. A host building one
    directly (the typed escape §5.5) must not be able to reach that by writing
    the obvious thing.
    """
    direct = Interceptor(
        "host-built", "step.tool.before", frozenset({Power.HIDE_VALUES}),
        lambda p: None,
    )
    assert direct.when == ("step.tool.before",)
    chain = Chain([direct])
    assert [i.name for i in chain.at("step.tool.before")] == ["host-built"]
    assert chain.at("step.message.before") == []
