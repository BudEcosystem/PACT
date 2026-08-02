"""G9 — what the run knows outlives the messages that established it.

The gap Eve's own documentation revealed and its code hardcodes twice. Its
compaction *"resets read-before-write tracking (so a write afterward re-reads
the file whose read evidence was summarized away) and re-injects the active todo
list"* (`docs/concepts/default-harness.md`), and the same page says *"There is no
per-tool hook to configure"* — so the two cases Eve happened to need are solved
and the third has nowhere to go.

Every test here is named as the guarantee it holds. The one that matters is
`test_an_approval_recorded_before_a_shortening_still_gates_the_call_after_it`:
without this mechanism the check reads nothing and **passes**, which is worse
than failing, because nobody is told.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.context_policy import (  # noqa: E402
    ContextPolicy,
    Message,
    Part,
    PartKind,
    Tidier,
)
from pact_adapters.facts import FACT_LABEL, Fact, Facts  # noqa: E402
from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(PACT_BIN), "show", str(EXAMPLE)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def say(role: str, text: str) -> Message:
    return Message(role=role, parts=(Part(PartKind.TEXT, text),))


def policy(**over) -> ContextPolicy:
    doc = {"context-policies": {"p": {"when-full": "80%", **over}}}
    return ContextPolicy.from_document(doc, "p")


def a_long_conversation(n: int = 60) -> list[Message]:
    return [say("user" if i % 2 == 0 else "assistant", f"turn {i} " + "x" * 200)
            for i in range(n)]


APPROVED = Facts(
    declared={
        "the-refund-was-approved": Fact(
            name="the-refund-was-approved",
            description="a person approved this refund",
            stale_when=("the turn ends",),
        )
    }
)


# ───────────────────────────────────────────────── the guarantee that matters


def test_an_approval_recorded_before_a_shortening_still_gates_the_call_after_it() -> None:
    """The whole point. A person said yes; the messages saying so were
    summarised away; the fact is still there to be read.

    Measured against the same tidier with no facts declared, so the two arms
    differ in exactly one thing."""
    p = policy(**{"then": [{"what": "keep-recent-only", "down-to": "the last 4 messages"}]})
    history = a_long_conversation()

    facts = Facts(declared=dict(APPROVED.declared))
    facts.record("the-refund-was-approved", "yes, by the duty manager")

    without = Tidier(p, budget_tokens=200).apply(history)
    with_facts = Tidier(p, budget_tokens=200, facts=facts).apply(history)

    said_without = " ".join(m.text() for m in without.messages)
    said_with = " ".join(m.text() for m in with_facts.messages)

    assert "duty manager" not in said_without, (
        "the control arm must lose the evidence, or this test proves nothing"
    )
    assert "duty manager" in said_with
    assert with_facts.facts_kept == ["the-refund-was-approved"]


def test_a_fact_that_went_stale_is_reported_rather_than_quietly_missing() -> None:
    """A rule reading a forgotten fact decides on nothing. The run says so."""
    facts = Facts(declared=dict(APPROVED.declared))
    facts.record("the-refund-was-approved", "yes")
    gone = facts.something_happened("the turn ends")

    assert gone == ["the-refund-was-approved"]
    out = Tidier(policy(**{"then": []}), budget_tokens=200, facts=facts).apply(
        a_long_conversation()
    )
    assert out.facts_lost == ["the-refund-was-approved"]
    assert out.facts_kept == []
    (word,) = facts.unenforced()
    assert "decided on nothing" in word and "fix:" in word


def test_an_event_no_fact_named_leaves_every_fact_standing() -> None:
    facts = Facts(declared=dict(APPROVED.declared))
    facts.record("the-refund-was-approved", "yes")
    assert facts.something_happened("the file changes") == []
    assert facts.surviving()[0][1] == "yes"


# ─────────────────────────────────────────────────────── the boundaries of it


def test_a_run_that_declares_no_facts_is_shortened_exactly_as_before() -> None:
    """This may not change a workspace that never asked for it."""
    p = policy(**{"then": [{"what": "keep-recent-only", "down-to": "the last 4 messages"}]})
    history = a_long_conversation()
    plain = Tidier(p, budget_tokens=200).apply(history)
    empty = Tidier(p, budget_tokens=200, facts=Facts()).apply(history)

    assert [m.text() for m in plain.messages] == [m.text() for m in empty.messages]
    assert plain.after == empty.after
    assert empty.facts_kept == [] and empty.facts_lost == []


def test_a_fact_nobody_declared_survivable_is_not_carried() -> None:
    """`record` is silent for an undeclared name. A shortener may not invent
    what should outlive a summary — that is the author's line to write."""
    facts = Facts(declared=dict(APPROVED.declared))
    facts.record("something-nobody-declared", "value")
    assert facts.held == {}
    assert facts.surviving() == []


def test_a_restated_fact_is_a_checkpoint_so_a_later_shortening_cannot_eat_it() -> None:
    """Reuses the existing never-dropped mechanism rather than adding a second."""
    facts = Facts(declared=dict(APPROVED.declared))
    facts.record("the-refund-was-approved", "yes")
    out = Tidier(policy(**{"then": []}), budget_tokens=200, facts=facts).apply(
        a_long_conversation()
    )
    (restated,) = [m for m in out.messages if FACT_LABEL in m.labels]
    assert restated.checkpoint is True


def test_a_restated_fact_reads_as_evidence_and_not_as_an_instruction() -> None:
    """A re-stated fact is something that happened, not something to do.
    Evidence phrased as a command is how a summary becomes an injection
    surface — the hazard `patterns/multi-tenant-memory.md` warns about in
    Eve's own docs, where the mitigation is authoring advice and nothing more."""
    said = APPROVED.declared["the-refund-was-approved"].said("yes")
    assert said.startswith("[recorded earlier]")
    for imperative in ("you must", "always ", "never ", "do not"):
        assert imperative not in said.lower()


def test_the_restated_fact_is_counted_against_the_budget_not_added_on_top() -> None:
    """A fact that survives by breaking the ceiling has not survived; it has
    moved the failure somewhere harder to read.

    Held by comparing the two arms: the arm carrying a fact must MEASURE larger,
    which is only true if the re-stated message went through `measure` after
    being appended rather than being bolted on afterwards.
    """
    p = policy(**{"then": []})
    history = a_long_conversation()

    facts = Facts(declared=dict(APPROVED.declared))
    facts.record("the-refund-was-approved", "yes " + "y" * 400)

    without = Tidier(p, budget_tokens=200).apply(history)
    with_fact = Tidier(p, budget_tokens=200, facts=facts).apply(history)

    assert with_fact.after > without.after, "the fact must cost what it costs"
    # `after` is the measure of what actually ends up in `messages`, so the
    # number a caller reads and the history a model receives cannot disagree.
    from pact_adapters.context_policy import estimate

    assert with_fact.after == estimate(with_fact.messages)
    # and `fits` is the verdict recomputed AFTER the fact was added, not the
    # one the ladder reached before it existed.
    assert with_fact.fits is (with_fact.after <= Tidier(p, budget_tokens=200).threshold)


# ────────── the other half of `stops-being-true-when:` — what nothing raises


def test_a_stale_trigger_nothing_can_raise_is_reported(document: dict) -> None:
    """`stops-being-true-when:` is `list of text`, and the schema's own help
    offers *"`the file changes` or `the turn ends`"*.

    Nothing in PACT watches a file. An author who writes that has a fact which
    never goes stale and believes otherwise — the T7 breach the rest of this
    codebase reports rather than swallows. Reported and not refused at check
    time, because the open vocabulary is deliberate (a closed predicate language
    would mean *"an author who has to invent an expression will write
    nothing"*) and a host that watches files may raise it.
    """
    from dataclasses import replace as _replace

    from pact_adapters.facts import Fact, Facts

    spec = AgentSpec.from_document(document, "refund-desk", source=EXAMPLE)
    watched = Facts(declared={
        "the-file-was-signed": Fact(
            name="the-file-was-signed", description="that it was signed",
            stale_when=("the file changes",),
        ),
    })
    out = asyncio.run(run(
        _replace(spec, facts=watched),
        ReferenceTransport(Script([Turn("done")] * 8)), "hello",
    ))
    said = [u for u in out.unenforced if "stops-being-true-when" in u]
    assert said, f"nothing reported the unraisable trigger: {out.unenforced}"
    assert "the file changes" in said[0]
    assert "the turn ends" in said[0], "it must name what it CAN raise"


def test_the_example_writes_only_triggers_a_run_can_raise(document: dict) -> None:
    """The shipped tree must not be an example of the thing above."""
    spec = AgentSpec.from_document(document, "refund-desk", source=EXAMPLE)
    assert spec.facts.declared, "the example declares facts; this test needs them"
    assert spec.facts.never_raised() == [], spec.facts.never_raised()


def test_a_fact_expires_when_the_turn_ends_and_the_run_says_which(
    document: dict,
) -> None:
    """`Facts.something_happened` had no caller at all, so a fact declared with
    `stops-being-true-when: the turn ends` never expired.

    Reported on the result rather than silently: a reviewer needs to know what a
    NEXT turn cannot rely on.
    """
    spec = AgentSpec.from_document(document, "refund-desk", source=EXAMPLE)
    spec.facts.record("payments-was-approved", "cleared earlier")
    assert "payments-was-approved" in spec.facts.held

    out = asyncio.run(
        run(spec, ReferenceTransport(Script([Turn("done")] * 8)), "hello")
    )
    assert "payments-was-approved" in out.facts_expired, out.facts_expired
    assert "payments-was-approved" not in spec.facts.held


def test_a_parked_run_does_not_expire_the_approval_it_is_parked_on(
    document: dict,
) -> None:
    """The distinction that makes the turn-end trigger safe.

    A suspended run is WAITING, not finished. Expiring its facts would forget the
    approval it is parked on — which is the whole of G9: `payments-was-approved`
    has to survive the wait for the person who granted it.
    """
    spec = AgentSpec.from_document(document, "refund-desk", source=EXAMPLE)
    spec.facts.record("payments-was-approved", "cleared earlier")

    out = asyncio.run(run(
        spec, ReferenceTransport(Script([
            Turn("Refunding.", (ToolCall("payments", {"action": "issue-refund"}),)),
            Turn("done"),
        ])),
        "refund it", {}, needs_approval=frozenset({"payments"}),
    ))
    assert out.halted == "suspended", out.halted
    assert out.facts_expired == (), (
        f"a parked run expired {out.facts_expired} — the turn has not ended, and "
        f"forgetting the approval it is parked on is the failure G9 exists to stop"
    )
    assert "payments-was-approved" in spec.facts.held


def test_a_turn_that_ends_by_answering_expires_its_facts(document: dict) -> None:
    """The ending the worked example actually takes, driven three ways.

    **This does not cover three code paths, and an earlier version of it said it
    did.** Traced: `pact:loop/standard`, the example's `careful` loop and a
    one-step ceiling all leave through the same `result.halted = "final"` — the
    third suspends rather than ending at all. Two mutations that removed expiry
    from the OTHER two endings left this green, which is how the claim was found
    to be false. `test_every_ending_routes_through_one_place` below is the check
    that actually covers them, structurally, because no fixture here reaches
    them.
    """
    from dataclasses import replace as _replace

    from pact_adapters.loops import STANDARD, Loop

    endings: dict[str, AgentSpec] = {
        # `pact:loop/standard`: one stage, `answered: done` — the loop reaches
        # `done` and `_finish` runs.
        "reached done": _replace(
            AgentSpec.from_document(document, "refund-desk", source=EXAMPLE),
            loop=Loop.from_library(STANDARD),
        ),
        # The example's own `careful` loop, whose last stage answers.
        "a stage answered": AgentSpec.from_document(
            document, "refund-desk", source=EXAMPLE
        ),
        # A step ceiling, so the run stops having taken every stage it could.
        "ran out of steps": _replace(
            AgentSpec.from_document(document, "refund-desk", source=EXAMPLE),
            max_steps=1,
        ),
    }
    for how, spec in endings.items():
        spec.facts.record("payments-was-approved", "cleared earlier")
        out = asyncio.run(
            run(spec, ReferenceTransport(Script([Turn("done")] * 8)), "hello")
        )
        if out.halted == "suspended":
            continue          # a park is not an ending; held above
        assert out.facts_expired == ("payments-was-approved",), (
            f"a turn that ended by {how!r} (halted={out.halted!r}) expired "
            f"{out.facts_expired} — every ending has to expire the same facts, "
            f"or which one is forgotten depends on how the run happened to stop"
        )


def test_every_ending_routes_through_one_place() -> None:
    """Three lines in `harness.run` end a turn, and the first wiring caught one.

    A fact that expires or survives depending on which way the run happened to
    finish is not a property anybody could reason about from the document — and
    it is the same multi-exit shape that made `run` need a declared boundary in
    the first place.

    Structural, and deliberately so: no fixture in this repository reaches two of
    the three, so a behavioural test would assert nothing about them. What this
    catches is the fourth ending somebody adds later.
    """
    src = (
        REPO / "adapters/python/src/pact_adapters/harness.py"
    ).read_text().splitlines()
    endings = [i for i, line in enumerate(src) if 'halted = "final"' in line]
    assert len(endings) >= 3, f"only {len(endings)} endings found — did `run` change?"
    for at in endings:
        # BOTH directions. `_finish` expires before it sets `halted`, because the
        # answer has to be composed first — a forward-only window called that
        # unguarded, which is a false positive found by running this.
        window = "\n".join(src[max(0, at - 8) : at + 8])
        assert "_turn_ended" in window or "_finish" in window, (
            f"harness.py:{at + 1} ends a turn and nothing around it expires the "
            f"author's facts:\n{window}\n"
            f"Every ending has to go through `_turn_ended`, or which facts are "
            f"forgotten depends on how the run happened to stop."
        )
