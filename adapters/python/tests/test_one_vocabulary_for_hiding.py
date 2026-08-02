"""One set of words for one act — `redaction.hide` and `interceptor.rules`.

There were two closed vocabularies for hiding a value and each was missing what
the other had. Measured on the shipped tree, mirrored:

  * `redaction.yaml` writes `anything that looks like a card number`. The same
    line under an interceptor's `rules:` was refused — *"not a rule PACT knows
    how to carry out"*.
  * `interceptors/redact-card-numbers.yaml` writes `replace anything that looks
    like a card number with "[card number removed]"`. The same line under
    `hide:` was refused the same way.

Three lines apart in one worked example, describing one act. That is D13's
one-thing-one-name broken where it costs most: an author who learned to write a
redaction had learned nothing about writing an interceptor, and what they were
writing about both times was a card number in somebody's transcript.

# The bigger half: `redaction.hide` was read by nobody

The merge turned up the defect this project keeps shipping. `redaction.hide` was
in the schema, was `required:`, was resolved out of the tree by the loader and
printed by `pact show` — and appeared in no source file in either language. The
worked example's own third line says an email address must never leave this
workspace, and nothing hid an email address anywhere, on any agent, in any run.

So the tests below come in two kinds and the second kind is the point:

  * refusals, which may build a small document on purpose, because the thing
    under test is a diagnostic;
  * behaviour, which loads `examples/refund-desk` through the real loader and
    passes NO chain, NO rule and NO address — because a test that builds the
    object itself proves the object works and says nothing about whether the
    author's line ever reaches it.

Each behaviour test has a control beside it that takes the author's line back out
and shows the value leaking, so "it was hidden" cannot be explained by anything
else in the tree.
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
from pact_adapters.harness import ToolCall  # noqa: E402
from pact_adapters.interceptors import (  # noqa: E402
    ON_ITS_OWN,
    REDACTION,
    Chain,
    InterceptorError,
    Power,
)
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples/refund-desk"

#: An address the worked example's own `redaction.yaml` says must never leave,
#: and which — before that file was read by anything — left through the model
#: call, through a tool argument and through the reply.
EMAIL = "jo.taylor@example.com"
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


def _without_the_authors_line(doc: dict[str, Any]) -> dict[str, Any]:
    """The same document with `redaction.yaml` taken out of it.

    The control for every behaviour test here. Delete the line
    `Chain.from_document` reads and the run is what it was before this landed —
    which is what turns "the email address was hidden" into "the AUTHOR'S line
    hid it".

    A copy, never the fixture: the fixture is module-scoped and every other test
    wants the workspace exactly as its author wrote it.
    """
    out = json.loads(json.dumps(doc))
    out.pop("redaction", None)
    return out


def _a_redaction(*hide: str) -> Chain:
    """A chain over a redaction alone, for the REFUSAL tests only.

    Used where the thing under test is a diagnostic and the file has to be wrong
    on purpose — never where the thing under test is behaviour.
    """
    return Chain.from_document(
        {"agents": {"a": {}}, "redaction": {"hide": list(hide)}}, "a"
    )


def _an_interceptor(*rules: str, may: list[str] | None = None) -> Chain:
    return Chain.from_document(
        {
            "agents": {"a": {"interceptors": ["x"]}},
            "interceptors": {
                "x": {
                    "when": ["step.message.before", "step.tool.before"],
                    "may": may or ["hide-values"],
                    "rules": list(rules),
                }
            },
        },
        "a",
    )


# ────────────────────────────────── one vocabulary, measured in both directions


def test_the_sentence_a_redaction_writes_is_also_a_sentence_an_interceptor_takes() -> None:
    """`anything that looks like a card number`, under `rules:`.

    It is the line all three of the shipped `redaction.yaml`'s entries are
    written in, and under an interceptor it was refused by name as free prose.
    """
    chain = _an_interceptor("anything that looks like a card number")
    out, _ = chain.run("step.message.before", {"content": f"card {CARD}"})
    assert "4111" not in out["content"], out
    assert "[removed]" in out["content"], (
        "a sentence that names no replacement still has to hide something"
    )


def test_the_sentences_an_interceptor_writes_are_also_sentences_a_redaction_takes() -> None:
    """`replace … with "…"` and `do the same for …`, under `hide:`.

    Both are the shipped interceptor's own lines, and under `hide:` each was
    refused. The first is what a redaction needs to choose the words left behind;
    the second is what it needs to name a second thing without repeating them.
    """
    chain = _a_redaction(
        'replace anything that looks like a card number with "[gone]"',
        "do the same for anything that looks like an email address",
    )
    out, _ = chain.run("step.message.before", {"content": f"{CARD} / {EMAIL}"})
    assert out["content"] == "[gone] / [gone]", out


def test_a_bare_sentence_says_what_the_one_after_it_does_the_same_as() -> None:
    """`do the same for …` written under a sentence that named no replacement.

    The bare sentence IS `replace … with "[removed]"` with the words left out, so
    the rule after it has something to be the same as. Refusing here would be the
    tool telling an author that the line plainly hiding something above says
    nothing about what to replace anything with.
    """
    chain = _a_redaction(
        "anything that looks like a card number",
        "do the same for anything that looks like an email address",
    )
    out, _ = chain.run("step.message.before", {"content": f"{CARD} / {EMAIL}"})
    assert out["content"] == "[removed] / [removed]", out


def test_do_the_same_with_nothing_above_it_is_still_refused_in_both_files() -> None:
    """The one refusal the bare sentence must not have swallowed.

    `do the same for …` first in the list has nothing to be the same as, in
    either kind of file, and the fix is a sentence that stands on its own.

    The words changed with `continues: yes` in `spec/schema.yaml`, which made
    `pact check` refuse the same line — before that only this half did, so the
    author's own tool passed a file the run rejects. The two messages are one
    sentence now, so the guarantee below is that BOTH halves refuse it and that
    what they offer is typeable, not that this half phrases it its own way.
    """
    for build in (
        lambda: _a_redaction("do the same for anything that looks like a card number"),
        lambda: _an_interceptor("do the same for anything that looks like a card number"),
    ):
        with pytest.raises(InterceptorError) as e:
            build()
        said = str(e.value)
        assert "no rule before it says what to do" in said, said
        assert "anything that looks like a <thing>" in said, (
            f"the fix must be typeable: {said}"
        )
        assert "stop and say" not in said, (
            f"a sentence it can carry on from hides values; the counting ones do "
            f"not, and offering them here would be a fix in shape only: {said}"
        )


def test_each_sentence_that_refusal_offers_stands_on_its_own_and_hides_something() -> None:
    """Follow the fix, and the file you were told to write works.

    The whole standard for a diagnostic here — name the file, the line, what is
    wrong, and a fix that can be TYPED — with the last word measured rather than
    asserted. Each line the refusal offers is written on its own, with the hole
    filled in with the author's own subject, and has to both load and hide.

    It did not, for a round, on the sibling refusal: `do the same for anything
    that looks like a shoe size` was told to write `replace anything that looks
    like a shoe size with "[removed]"`, which the next check refused by name.
    """
    offered = [
        f.replace("<thing>", "card number").replace('"<text>"', '"[gone]"')
        for f in ON_ITS_OWN
    ]
    assert offered, "the refusal must have something to offer"
    for sentence in offered:
        chain = _a_redaction(sentence)
        out, _ = chain.run("step.message.before", {"content": f"card {CARD}"})
        assert "4111" not in out["content"], (
            f"{sentence!r} was offered as the repair and hides nothing: {out}"
        )


def test_a_thing_nothing_can_recognise_is_refused_the_same_way_in_both_files() -> None:
    """One list of recognisable things, so the two kinds cannot drift apart.

    The author must not be able to tell which half of the system refused them,
    and until the hole vocabulary was shared that depended on two hand-kept
    copies agreeing.
    """
    for build in (
        lambda: _a_redaction("anything that looks like a passport number"),
        lambda: _an_interceptor('replace anything that looks like a passport number with "x"'),
    ):
        with pytest.raises(InterceptorError) as e:
            build()
        said = str(e.value)
        assert "nothing here knows what 'passport number' looks like" in said, said
        assert "card number" in said and "phone number" in said, (
            f"the fix must list what can be recognised: {said}"
        )


# ─────────────────── what the shared list must NOT hand a file that cannot use it


def test_a_redaction_that_tries_to_stop_the_run_is_refused_where_it_is_written() -> None:
    """The hazard the merge creates, and the reason the powers are stated.

    One list holds five sentences and a redaction can carry out three. The other
    two have to be refused when the file is read — a counting sentence that loads
    in `redaction.yaml` and counts nothing is the "loads and does nothing"
    failure the vocabulary exists to end, arriving through the fix for another
    one.
    """
    with pytest.raises(InterceptorError) as e:
        _a_redaction(
            "anything that looks like a card number",
            'if payments is called more than 1 time in one run, stop and say "no"',
        )
    said = str(e.value)
    assert "a redaction may only hide values" in said, said
    # And the fix has to be typeable IN THAT FILE. A redaction has no `may:`, so
    # "add a line under `may:`" is advice nobody can follow.
    assert "under `may:`" not in said, f"untypeable fix offered: {said}"
    assert "anything that looks like a <thing>" in said, said
    assert "stop and say" not in said.split("Fix:")[1], (
        f"a refusal must not offer back the sentence it just refused: {said}"
    )


def test_an_interceptor_missing_a_power_is_still_told_which_line_to_add() -> None:
    """The other half of the same check, unchanged.

    An interceptor DOES choose what it may do, so the fix there is still the line
    to type under `may:` — the two refusals differ because the two files differ,
    not because one of them was left behind.
    """
    with pytest.raises(InterceptorError) as e:
        _an_interceptor(
            'if payments is called more than 1 time in one run, stop and say "no"',
            may=["hide-values"],
        )
    said = str(e.value)
    assert "does not say it may" in said, said
    assert "- stop-the-run" in said, f"the fix must be typeable: {said}"


# ─────────────────────────── the authored path: `redaction.yaml`, nothing passed


def test_the_workspace_redaction_covers_an_agent_that_names_no_rule_at_all(
    document: dict,
) -> None:
    """`fraud-checker` names no interceptors, and is covered anyway.

    Nothing here writes a sentence or an address: both come from
    `examples/refund-desk/redaction.yaml`, through the loader, through
    `Chain.from_document`. What may not leave is a fact about the workspace, so
    an agent cannot be outside it by writing nothing.
    """
    assert not (document["agents"]["fraud-checker"].get("interceptors") or [])
    covered = Chain.from_document(document, "fraud-checker", EXAMPLE)
    assert REDACTION in [i.name for i in covered.interceptors], (
        f"the workspace redaction must be in every agent's chain: "
        f"{[i.name for i in covered.interceptors]}"
    )
    floor = next(i for i in covered.interceptors if i.name == REDACTION)
    assert floor.may == frozenset({Power.HIDE_VALUES}), (
        "a redaction hides and does nothing else"
    )
    assert set(floor.when) == {
        "step.message.before",
        "step.message.after",
        "turn.message.after",
        "step.tool.before",
        # What came BACK, which this set was missing for a round. "Must never
        # leave this workspace" was one-directional: a card number the agent
        # typed into a `payments` argument was masked and the same card number
        # `payments` handed back was not — and a tool result goes into the
        # history and is read to the model on the next turn, so it leaves by the
        # same door as anything else.
        "step.tool.completed",
    }, f"'must never leave' is not a statement about one moment: {floor.when}"


def test_the_line_that_says_an_email_address_must_never_leave_removes_one(
    document: dict,
) -> None:
    """The author's third line, executing — and its control.

    `redaction.yaml` line 24 is `anything that looks like an email address`. No
    interceptor in the worked example mentions email addresses, so before this
    file was read by anything that line hid nothing at all, at any moment, on any
    agent.
    """
    covered = Chain.from_document(document, "fraud-checker", EXAMPLE)
    typed, _ = covered.run("step.message.before", {"content": f"write to {EMAIL}"})
    assert EMAIL not in typed["content"], typed
    assert "[removed]" in typed["content"]

    # The control. Take that file out of the document and the address goes
    # straight through — which is what the tree did for every round before this.
    without = Chain.from_document(_without_the_authors_line(document), "fraud-checker", EXAMPLE)
    leaked, _ = without.run("step.message.before", {"content": f"write to {EMAIL}"})
    assert leaked["content"] == f"write to {EMAIL}", (
        "with `redaction.yaml` out of the document the address must go through "
        "untouched — otherwise something other than the author's line is hiding it"
    )


def test_the_reply_the_customer_reads_is_covered_by_the_workspace_redaction(
    document: dict,
) -> None:
    """`turn.message.after` — a moment no interceptor in the example binds to.

    The shipped card-number rule names `step.message.before` and
    `step.tool.before`. Nothing named the reply, so a card number the model wrote
    into its answer went out unmasked. A redaction is bound to every moment that
    carries values, so it covers this one without anybody having to notice it was
    missing.
    """
    covered = Chain.from_document(document, "fraud-checker", EXAMPLE)
    said, _ = covered.run("turn.message.after", {"content": f"your card {CARD}, {EMAIL}"})
    assert "4111" not in said["content"], said
    assert EMAIL not in said["content"], said

    without = Chain.from_document(_without_the_authors_line(document), "fraud-checker", EXAMPLE)
    leaked, _ = without.run("turn.message.after", {"content": f"your card {CARD}"})
    assert CARD in leaked["content"], (
        "the reply was covered by nothing before `redaction.yaml` was read"
    )


def test_an_email_address_out_of_a_ticket_never_reaches_the_payments_tool(
    document: dict,
) -> None:
    """The whole run, end to end, with nothing passed in.

    No chain, no rule and no address is handed to `run()`. The agent's chain is
    built from the loaded document, and `redaction.yaml` is the only thing in
    the workspace that says anything about an email address — no interceptor
    mentions one.

    The last turn puts the address in the REPLY as well, which is a moment no
    interceptor in this workspace binds to: the shipped card rule names
    `step.message.before` and `step.tool.before`. So the reply is covered because
    the floor is bound to every moment that carries values, not because anybody
    remembered to name that one.
    """
    handed_over: list[dict] = []
    desk = AgentSpec.from_document(document, "refund-desk")

    def script() -> Script:
        return Script([
            Turn("reading the ticket", (ToolCall("zendesk", {"order": "A-1182"}),)),
            Turn("paying", (ToolCall("payments", {
                "order-number": "A-1182", "contact": {"email": EMAIL},
            }),)),
            Turn(f"Refunded. We have written to {EMAIL}."),
        ])

    result = allowing_the_connection(
        desk, lambda: ReferenceTransport(script()), "refund order A-1182",
        {"zendesk": lambda a: f"lamp, broken. reply to {EMAIL}",
         "payments": lambda a: handed_over.append(a) or "refunded"},
    )
    assert handed_over, f"payments was never called: {result.output}"
    assert EMAIL not in json.dumps(handed_over[0]), handed_over[0]
    assert handed_over[0]["order-number"] == "A-1182", "only the address is hidden"
    assert handed_over[0]["contact"]["email"] == "[removed]", (
        "nested arguments too — an address in `contact.email` has left the "
        "building exactly as surely as one at the top"
    )
    # The RECORD of that call, not only the call: an address the tool never saw
    # but the transcript kept has still left the building.
    calls = [c for step in result.trace() for c in step["tools"]]
    assert calls, result.trace()
    assert EMAIL not in json.dumps(calls), calls
    # And the reply the customer reads, through the harness rather than through a
    # `chain.run(...)` this test wrote — `turn.message.after` is a real moment of
    # a real run and the floor is the only thing bound to it here.
    assert EMAIL not in result.output, result.output
    assert "[removed]" in result.output, result.output


def test_the_same_run_leaks_that_address_with_the_authors_file_taken_out(
    document: dict,
) -> None:
    """The control for the run above, and the only honest way to read it.

    Same script, same tools, same everything but one file. If the address is
    still hidden here then something other than `redaction.yaml` is hiding it and
    the test above is measuring the wrong thing.
    """
    handed_over: list[dict] = []
    desk = AgentSpec.from_document(_without_the_authors_line(document), "refund-desk")

    def script() -> Script:
        return Script([
            Turn("paying", (ToolCall("payments", {
                "order-number": "A-1182", "contact": {"email": EMAIL},
            }),)),
            Turn(f"Refunded. We have written to {EMAIL}."),
        ])

    result = allowing_the_connection(
        desk, lambda: ReferenceTransport(script()), "refund order A-1182",
        {"zendesk": lambda a: "lamp, broken",
         "payments": lambda a: handed_over.append(a) or "refunded"},
    )
    assert handed_over, "payments was never called"
    assert handed_over[0]["contact"]["email"] == EMAIL, (
        "without `redaction.yaml` the address must reach the tool — that is the "
        "behaviour every round before this one shipped"
    )
    assert EMAIL in result.output, (
        "and it must reach the customer's reply too, or something other than the "
        "author's line is hiding it in the test above"
    )


def test_the_workspace_floor_runs_after_the_rules_an_author_wrote(
    document: dict,
) -> None:
    """A floor is a backstop, not an override.

    The example says `replace anything that looks like a card number with
    "[card number removed]"` in an interceptor, and `anything that looks like a
    card number` in `redaction.yaml`. Run the floor first and the author's chosen
    words never appear anywhere — a rule they wrote, can read, and can point at
    becomes one that loads and does nothing. Run it last and both are true.
    """
    covered = Chain.from_document(document, "fraud-checker", EXAMPLE)
    names = [i.name for i in covered.interceptors]
    assert names.index(REDACTION) > names.index("redact-card-numbers"), names

    out, _ = covered.run("step.message.before", {"content": f"card {CARD}, {EMAIL}"})
    assert "[card number removed]" in out["content"], (
        f"the author's own words must survive the floor: {out}"
    )
    assert EMAIL not in out["content"], f"and the floor must still catch the rest: {out}"


def test_a_workspace_with_no_redaction_file_runs_exactly_as_it_did_before(
    document: dict,
) -> None:
    """The honest default: no floor, not an invented one.

    A workspace that never wrote a `redaction.yaml` must not be quietly given a
    set of rules nobody typed — the same argument `context_policy` makes for
    leaving a workspace with no policy untidied.
    """
    without = Chain.from_document(_without_the_authors_line(document), "refund-desk", EXAMPLE)
    assert REDACTION not in [i.name for i in without.interceptors], (
        f"nothing may be added on the author's behalf: "
        f"{[i.name for i in without.interceptors]}"
    )


def test_a_redaction_that_is_written_and_hides_nothing_adds_no_rule(document: dict) -> None:
    """An empty `hide:` is not a floor of nothing, it is no floor.

    `pact check` refuses an empty one (the field is `required:`), so this is
    about a document handed straight to an adapter — invariant P-1 says one may
    arrive without ever having been through the tree.
    """
    doc = _without_the_authors_line(document)
    doc["redaction"] = {"description": "nothing yet"}
    assert REDACTION not in [
        i.name for i in Chain.from_document(doc, "refund-desk", EXAMPLE).interceptors
    ]


def test_the_file_the_author_is_sent_to_is_the_one_they_wrote_in() -> None:
    """A redaction lives in `redaction.yaml`, not under `interceptors/`.

    Every diagnostic in this module names a file and a line, and for a round the
    interceptor half of it named a path built out of an entry's name — a file
    that does not exist when the rule was written as a folder. The redaction half
    must not repeat that: `redaction.yaml` sits at the top of the workspace, the
    way `learning.yaml` does.
    """
    with pytest.raises(InterceptorError) as e:
        Chain.from_document(
            {"agents": {"a": {}}, "redaction": {"hide": ["be careful with cards"]}},
            "a",
            EXAMPLE,
        )
    said = str(e.value)
    assert said.startswith("redaction.yaml:"), said
    assert "interceptors/" not in said, f"the author is sent to a file that exists: {said}"
