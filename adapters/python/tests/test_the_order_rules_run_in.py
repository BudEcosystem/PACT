"""The order interceptors run in, and the line that decides it.

`Chain.from_document` built the workspace-wide rules with
`sorted(declared.items())` — the FILENAMES — three lines under its own comment
saying *"Order matters: the chain threads each change into the next, and a
redaction that runs after a guard has read the value has redacted nothing"*.
Measured before this module existed: adding `aaa-hide.yaml` gave the chain
`['aaa-hide', 'redact-card-numbers-in-tool-calls', 'stop-runaway-refunds']` and
renaming the same file `zzz-hide.yaml` gave
`['redact-card-numbers-in-tool-calls', 'zzz-hide', 'stop-runaway-refunds']`. A
safety property decided by a rename, with no field an author could write to say
otherwise — the "significant ordering game" D18 forbids by name.

`runs-at:` is that field. What is measured here is not that the number sorts,
which would be a test of `list.sort`, but the three things that make it worth
having:

* the DEFAULT is the safe order, so a support lead who writes nothing still gets
  hiding before reading (D13);
* the number OVERRIDES the alphabet, in a chain where the alphabet is wrong;
* and the order the field exists to protect is REFUSED when it cannot be
  honoured, with the harm measured rather than asserted — a guard in front of a
  redaction leaves the card number in the run's own record.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.interceptors import (  # noqa: E402
    ENDS_THE_CHAIN, EVERYTHING_ELSE_RUNS_AT, HIDING_RUNS_AT, Chain, Decision,
    Interceptor, InterceptorError, Power,
)
from pact_adapters.ir import AgentSpec, ToolSpec  # noqa: E402
from pact_adapters.loops import Loop  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"

SPEC = AgentSpec(
    name="Refund Desk", description="d", instructions="Decide refunds.",
    tools=(ToolSpec("zendesk", "read the ticket"), ToolSpec("payments", "issue a refund")),
)
TOOLS = {"zendesk": lambda a: "lamp, broken", "payments": lambda a: "refunded"}

MASKS = 'replace anything that looks like a card number with "[card number removed]"'
COUNTS = 'if payments is called more than 1 time in one run, stop and say "no"'

#: Two stages, so a redirect has somewhere to go. Mirrors
#: `examples/refund-desk/loops/careful.yaml` in shape.
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


def _document(**rules: dict) -> dict:
    """A workspace whose only agent is covered by every rule named.

    Through the document rather than by building `Interceptor` objects: a test
    that constructs the object proves the object works and says nothing about
    whether the author's line reaches it, which is the exact gap that let
    `redact-card-numbers.yaml` load, validate and do nothing for a round.
    """
    return {
        "agents": {"a": {"interceptors": sorted(rules)}},
        "interceptors": dict(rules),
    }


def _hides(**extra) -> dict:
    return {"when": "step.tool.before", "may": ["hide-values"], "rules": [MASKS], **extra}


def _stops(**extra) -> dict:
    return {"when": "step.tool.before", "may": ["stop-the-run"], "rules": [COUNTS], **extra}


# ────────────────────────────────────────────── the order, and where it comes from


def test_two_rules_at_one_moment_run_in_the_order_they_state_and_not_in_the_order_of_their_names() -> None:
    """The measurement that produced this field, inverted.

    Both rules cover every agent and both hide values, so before `runs-at:` the
    only thing separating them was `sorted(declared.items())`: `aaa-hide` first,
    always, and renaming a file moved it. Here `aaa-hide` says it runs at 90, so
    it runs SECOND — the alphabet's answer is available and wrong, and the
    author's line is what the chain uses.
    """
    doc = {
        "agents": {"a": {}},
        "interceptors": {
            "aaa-hide": {
                "applies-to": "every-agent", "when": "step.tool.before",
                "may": ["hide-values"], "runs-at": 90,
                "rules": ['replace anything that looks like a bank account with "[b]"'],
            },
            "zzz-hide": {
                "applies-to": "every-agent", "when": "step.tool.before",
                "may": ["hide-values"], "rules": [MASKS],
            },
        },
    }
    assert [i.name for i in Chain.from_document(doc, "a").interceptors] == [
        "zzz-hide", "aaa-hide"
    ], "the number decides, not the filename"

    # And with the numbers the other way round it is the other way round, so the
    # first assertion is not the alphabet agreeing with the author by accident.
    doc["interceptors"]["aaa-hide"].pop("runs-at")
    doc["interceptors"]["zzz-hide"]["runs-at"] = 90
    assert [i.name for i in Chain.from_document(doc, "a").interceptors] == [
        "aaa-hide", "zzz-hide"
    ]


def test_a_rule_that_hides_a_value_runs_before_one_that_reads_it_with_nobody_writing_a_number() -> None:
    """The default has to be the safe order, or the field is a trap.

    D13's author is a support lead. Asking them to work out that a redaction has
    to precede a guard, and to keep working it out every time they add a rule, is
    the failure mode D28 names first. So the two bands come from what a rule DOES:
    a rule that hides values runs at 10, everything else at 50, and the sentence
    the help text makes is true of a workspace nobody has numbered.
    """
    chain = Chain.from_document(_document(hide=_hides(), stop=_stops()), "a")
    assert [(i.name, i.order) for i in chain.interceptors] == [
        ("hide", HIDING_RUNS_AT), ("stop", EVERYTHING_ELSE_RUNS_AT)
    ]
    # `stop` sorts after `hide` alphabetically too, so the names are reversed to
    # show the bands are what did it.
    swapped = Chain.from_document(_document(a_stop=_stops(), z_hide=_hides()), "a")
    assert [i.name for i in swapped.interceptors] == ["z_hide", "a_stop"]


def test_the_worked_examples_own_rules_are_ordered_by_what_they_do(document: dict) -> None:
    """The real tree, through the real loader, with nothing passed in.

    Written as the GUARANTEE rather than as an inventory: the worked example
    gains and loses rules between rounds, and a test that lists its chain
    measures the example rather than the mechanism. What must hold of any
    workspace is that everything which hides values has run before anything that
    can end the chain — because after a stop or a redirect there is no chain
    left to hide anything.

    The example's own two rules are then named, and neither of them writes a
    number: `redact-card-numbers` is in front of `stop-runaway-refunds` because
    of what the two DO, not because `r` sorts before `s`.
    """
    chain = Chain.from_document(document, "refund-desk")
    ordered = chain.interceptors
    hiding = [n for n, i in enumerate(ordered) if Power.HIDE_VALUES in i.may]
    ending = [n for n, i in enumerate(ordered) if i.may & ENDS_THE_CHAIN]
    assert hiding and ending, f"both halves must exist: {[i.name for i in ordered]}"
    assert max(hiding) < min(ending), [(i.name, i.order) for i in ordered]

    by_name = {i.name: i for i in ordered}
    card, guard = by_name["redact-card-numbers"], by_name["stop-runaway-refunds"]
    assert (card.order, guard.order) == (HIDING_RUNS_AT, EVERYTHING_ELSE_RUNS_AT)
    assert card.runs_at is None and guard.runs_at is None, (
        "neither states a number — this is the default doing the work"
    )


# ───────────────────────────────────────── what the order is worth, measured


def _sends_to_re_read(name: str, runs_at: int) -> Interceptor:
    """A rule that redirects, built through the typed escape (§5.5) on purpose.

    `Chain.from_document` REFUSES the order this test is about, which is the
    whole point of it — so the unsafe chain is assembled the one way that can
    still assemble it, a host building an `Interceptor` in its own process.
    """
    return Interceptor(
        name=name,
        when=("step.tool.before",),
        may=frozenset({Power.REDIRECT}),
        body=lambda payload: Decision(redirect="re-read"),
        goes_to=frozenset({"re-read"}),
        runs_at=runs_at,
    )


def _paid_with_a_card_number() -> Script:
    return Script([
        Turn("paying", (ToolCall("payments", {"card": "4111 1111 1111 1111"}),)),
        Turn("looking again", (ToolCall("zendesk", {}),)),
        Turn("Refunded."),
    ])


def _trace_of(chain: Chain) -> str:
    result = asyncio.run(run(
        SPEC, ReferenceTransport(_paid_with_a_card_number()), "refund it", TOOLS,
        chain=chain, loop=CHECKING_LOOP,
    ))
    return json.dumps(result.trace())


def test_a_rule_that_ends_the_run_before_a_redaction_leaves_the_card_number_in_the_record() -> None:
    """What the ordering actually buys, measured rather than asserted.

    `Chain.run` returns at the first stop or redirect, so a rule that ends the
    chain does not delay the rules behind it — it deletes them. On the redirect
    path the harness writes what the chain left into the run's own record, under
    its own comment: *"a value that must not survive in the record must not
    survive on the path where the tool never even ran."* So the two orders differ
    in whether a card number is in the transcript, and that is why `runs-at:` is
    a safety field rather than a preference.
    """
    hiding = _document(hide=_hides())

    jumped = Chain.from_document(hiding, "a")
    jumped.add(_sends_to_re_read("jumps-the-queue", runs_at=1))
    assert "4111" in _trace_of(jumped), (
        "this is the leak the refusal below exists to stop — if it is gone, the "
        "refusal is guarding nothing and should be deleted, not kept"
    )

    behind = Chain.from_document(hiding, "a")
    behind.add(_sends_to_re_read("waits-its-turn", runs_at=90))
    left = _trace_of(behind)
    assert "4111" not in left, left
    assert "[card number removed]" in left


# ───────────────────────────────────────────────────────────── what it refuses


def test_a_rule_that_can_end_the_run_may_not_be_put_in_front_of_one_that_hides_values() -> None:
    """Stated, and unsound — refused when the file is read.

    Refused rather than quietly reordered: reordering would be this module
    deciding which of two rules the author meant to come first, and the two
    orders differ in what ends up written down.
    """
    with pytest.raises(InterceptorError) as e:
        Chain.from_document(_document(hide=_hides(), stop=_stops(**{"runs-at": 5})), "a")
    said = str(e.value)
    assert "interceptors/stop.yaml:1" in said, said
    assert "can end the run at `step.tool.before`" in said, said
    assert "would be handed on and written down" in said, said
    assert "`runs-at: 5` in interceptors/hide.yaml" in said, "the fix must be typeable"
    assert "`runs-at: 15` in interceptors/stop.yaml" in said, said


def test_two_rules_that_would_delete_each_others_work_must_say_which_goes_first() -> None:
    """Equal numbers are refused, and that is the point rather than strictness.

    Equal means the order comes from whichever file was read first, which for two
    workspace-wide rules is their filenames — the thing this field exists to take
    the decision away from. The author is told both numbers to write.
    """
    with pytest.raises(InterceptorError) as e:
        Chain.from_document(
            _document(hide=_hides(**{"runs-at": 20}), stop=_stops(**{"runs-at": 20})), "a"
        )
    said = str(e.value)
    assert "nothing says which of them goes first" in said, said
    assert "both run at 20" in said, said
    assert "`runs-at: 20` in interceptors/hide.yaml" in said, said
    assert "`runs-at: 30` in interceptors/stop.yaml" in said, said


def test_rules_that_never_meet_are_left_alone_however_they_are_numbered() -> None:
    """The check is about one moment, not about the whole workspace.

    A guard before a tool call and a redaction on the way back out never see the
    same payload, so ordering them is nobody's business but the author's — and a
    refusal that fired here would be teaching a rule that is not true.
    """
    doc = _document(
        stop=_stops(**{"runs-at": 5}),
        hide={"when": "turn.message.after", "may": ["hide-values"],
              "rules": [MASKS], "runs-at": 90},
    )
    assert [i.name for i in Chain.from_document(doc, "a").interceptors] == ["stop", "hide"]


def test_a_number_below_one_is_refused_with_the_line_to_type() -> None:
    """`at-least: 1` in the schema, and again here, because an adapter is handed
    a document (invariant P-1) that may never have met the checker."""
    with pytest.raises(InterceptorError) as e:
        Chain.from_document(_document(hide=_hides(**{"runs-at": 0})), "a")
    said = str(e.value)
    assert "the earliest a rule can run is 1" in said, said
    assert "runs-at: 1" in said, "the fix must be typeable"
    assert "10, 20, 30" in said, "and it must say why to leave gaps"


def test_a_runs_at_that_is_not_a_whole_number_is_refused_rather_than_read_as_one() -> None:
    """`runs-at: yes` is the one that matters: Python reads `True` as 1, so it
    would silently become "the very first rule at this moment" — which is not a
    reading of "yes" that anybody intended."""
    for bad in ("first", 1.5, True, [10]):
        with pytest.raises(InterceptorError) as e:
            Chain.from_document(_document(hide=_hides(**{"runs-at": bad})), "a")
        assert "is a whole number" in str(e.value), f"{bad!r}: {e.value}"
        assert "`runs-at: 10`" in str(e.value), "the fix must be typeable"


# ─────────────────────────────────────── from a file on disk, through the loader


@pytest.fixture(scope="module")
def document() -> dict:
    """The worked example as the loader produces it — no author files read."""
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(PACT_BIN), "show", str(EXAMPLE)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


def test_a_runs_at_line_written_in_a_file_survives_the_loader_and_decides_the_chain(
    tmp_path: Path,
) -> None:
    """The whole point, end to end: a line typed into a file, and nothing else.

    A copy of the worked example gains one more workspace-wide redaction whose
    name sorts FIRST, and a `runs-at:` line saying it runs after the card rule.
    Alphabetically it would be first; by its own line it is second. Nothing is
    passed to `Chain.from_document` but the loaded document.

    This is the test that fails while `interceptor.runs-at` is missing from
    `spec/schema.yaml` — the loader refuses the field, so the author's line never
    reaches the chain at all. That refusal is the honest signal: the Python half
    of this mechanism is inert until the schema half lands.
    """
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    workspace = tmp_path / "refund-desk"
    shutil.copytree(EXAMPLE, workspace)
    (workspace / "interceptors" / "aaa-hide-emails.yaml").write_text(
        "description: Stops an email address reaching the model.\n"
        "applies-to: every-agent\n"
        "when: step.message.before\n"
        "runs-at: 20\n"
        "may:\n"
        "  - hide-values\n"
        "rules:\n"
        '  - replace anything that looks like an email address with "[removed]"\n'
    )
    shown = subprocess.run(
        [str(PACT_BIN), "show", str(workspace)], capture_output=True, text=True
    )
    if shown.returncode != 0:
        pytest.fail(
            "the loader refused `runs-at:`, so the author's line reaches nothing. "
            "Add the `runs-at:` field block to `interceptor.fields` in "
            "spec/schema.yaml — it is in this task's report under "
            "'needs_wiring'.\n" + shown.stderr
        )
    doc = json.loads(shown.stdout)
    assert doc["interceptors"]["aaa-hide-emails"]["runs-at"] == 20, (
        "the number the author typed must survive the loader"
    )
    chain = Chain.from_document(doc, "refund-desk", workspace)
    ran = [i.name for i in chain.interceptors]
    # The GUARANTEE, not the inventory — the same standard
    # `test_the_worked_examples_own_rules_are_ordered_by_what_they_do` sets above
    # and for the reason it gives. This assertion was a list of three names, and
    # the workspace redaction floor arriving in the chain made it four; a test
    # that spells the example's contents out fails on the next rule anybody adds
    # and says nothing about whether the author's number did any work.
    assert sorted(ran)[0] == "aaa-hide-emails", (
        f"this measures nothing unless the alphabet's answer is available and "
        f"wrong: {ran}"
    )
    assert ran[0] != "aaa-hide-emails", (
        f"first alphabetically is what the filename used to buy — the `runs-at: "
        f"20` line is what has to move it: {ran}"
    )
    assert ran.index("redact-card-numbers") < ran.index("aaa-hide-emails") \
        < ran.index("stop-runaway-refunds"), ran
