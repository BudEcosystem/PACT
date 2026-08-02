"""The termination vocabulary (G2): three actions, and why there is no fourth.

`when-it-runs-out` offers `stop-and-say-so`, `ask-a-person` and
`answer-with-what-it-has`. A fourth — `park`: stop now, carry on later, tell
nobody — was considered and refused. This file is that refusal held under test,
because a decision that is only written in prose stops being a decision the
first time somebody finds the enum convenient.

Three things have to hold for the refusal to be honest:

* **The vocabulary is one vocabulary.** It is written in three places — the
  specification, the Python harness, and the TypeScript port — and they have to
  say the same three words. Adding `park` to only one of them is worse than not
  adding it: the Python reader falls back to `stop-and-say-so` for a word it
  does not know, so a run an author asked to park would silently stop instead.
  That is exactly the silent degradation T7 forbids, and the drift guards below
  are what turn it into a failed test rather than a surprise in production.
* **`ask-a-person` already parks.** Not "can be made to park" — reaching a
  ceiling with `ask-a-person` writes the whole run down and another process
  picks it up. `park` would be that mechanism with the person deleted, which is
  the repo's own `same-setting-twice` mistake in a new place.
* **Deleting the person deletes the un-parker.** A suspension is cleared by a
  yes and by nothing else; `TIMEOUT_ACTIONS` deliberately has no `approve`,
  because a timeout that grants is not a gate. So a park nobody was told about
  has no exit at all, and a run that never finishes is a governance failure
  rather than a governance option.

Eve is the counter-example throughout. Its session-token continuation is one of
five bespoke park kinds, each with its own state key and its own guard, and it
parks indefinitely: a run waiting on an approver who left the company waits
forever. Four of those five collapse into one `Suspension` here, and the whole
argument below is that a fourth *action* would start the pile over again.
"""

from __future__ import annotations

import asyncio
import re
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec, ToolSpec  # noqa: E402
from pact_adapters.limits import Action, Limits  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.suspension import (  # noqa: E402
    OUT_OF_BUDGET,
    TIMEOUT_ACTIONS,
    Suspension,
    WrongAnswer,
    clears,
)
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
SCHEMA = REPO / "spec" / "schema.yaml"
TS_LIMITS = REPO / "adapters" / "typescript" / "src" / "limits.ts"
NOT_COPIED = REPO / "docs" / "50-NOT-COPIED.md"

SPEC = AgentSpec(
    name="Refund Desk",
    description="Decides refunds",
    instructions="Decide, then issue the refund.",
    tools=(ToolSpec("zendesk", "read the ticket"),),
)
TOOLS = {"zendesk": lambda a: "lamp, broken"}


def never_finishes() -> Script:
    """A model that keeps calling a tool and never answers — the shape a ceiling
    exists for, and the one Eve cannot bound at all."""
    return Script([Turn("still working", (ToolCall("zendesk", {}),))])


# ─────────────────────────────────────────────────────── reading the three files


def _choices_for(field: str) -> tuple[str, ...]:
    """The words the specification offers for one `one-of` field.

    Read out of `spec/schema.yaml` as text rather than through a YAML library,
    so the guard holds on a machine with nothing installed (D17) and so it is
    reading the file an author actually edits rather than something derived
    from it.
    """
    lines = SCHEMA.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.strip() != f"{field}:":
            continue
        indent = len(line) - len(line.lstrip())
        for below in lines[i + 1:]:
            if below.strip() and (len(below) - len(below.lstrip())) <= indent:
                break  # the next field started; this one declared no choices
            if below.strip().startswith("choices:"):
                inner = below.split("[", 1)[1].split("]", 1)[0]
                return tuple(w.strip() for w in inner.split(",") if w.strip())
    raise AssertionError(
        f"`{field}:` no longer declares `choices: [...]` in spec/schema.yaml, so "
        "nothing here can see what the specification offers an author."
    )


def _typescript_action_union() -> tuple[str, ...]:
    text = TS_LIMITS.read_text(encoding="utf-8")
    union = re.search(r"export type Action =(.*?);", text, re.S)
    assert union is not None, (
        "adapters/typescript/src/limits.ts no longer declares `export type Action`, "
        "so the two runtimes can no longer be checked against each other."
    )
    return tuple(re.findall(r'"([^"]+)"', union.group(1)))


def _limits_comment_block() -> str:
    """The prose above `limits:` in the schema — where the reasoning for this
    family of fields lives, and the only comment an author reading `limits:`
    will actually pass through."""
    text = SCHEMA.read_text(encoding="utf-8")
    start = text.index("# ── LIMITS")
    return text[start:text.index("\n  limits:\n", start)]


# ────────────────────────────────────────────────── the vocabulary is one thing


def test_the_specification_offers_exactly_three_ways_for_a_run_to_end_at_a_ceiling() -> None:
    """The count itself is the guarantee. Each of the three is a different
    governance decision — say nothing, ask, or answer anyway — and a fourth has
    to earn its place against the three, not be added because an enum has room.
    """
    assert _choices_for("when-it-runs-out") == (
        "stop-and-say-so",
        "ask-a-person",
        "answer-with-what-it-has",
    )


def test_the_harness_can_do_every_action_the_specification_offers_and_no_others() -> None:
    """Both directions, and neither is optional.

    A word in the schema the harness does not know is read by `limits.action()`
    as `stop-and-say-so`, so an author who wrote `park` would get a stop and no
    message about it. A word in the harness the schema does not offer is a
    behaviour nobody can reach and nobody can find — the dead code that
    accumulates in Eve as `COMPACTION_HEURISTICS`-style private constants.
    """
    assert set(_choices_for("when-it-runs-out")) == {a.value for a in Action}


def test_both_runtimes_offer_the_same_three_actions_so_park_cannot_be_added_to_one() -> None:
    """Cross-runtime agreement about the vocabulary, not just about a trace.

    Two ports that step identically and then end a run on different rules have
    agreed about nothing that matters. This is the cheapest form of that check:
    a fourth action costs an edit in Python, in TypeScript and in the schema, so
    it cannot be slipped into one of them.
    """
    assert set(_typescript_action_union()) == {a.value for a in Action}


# ───────────────────────────────────────── ask-a-person is already what park is


def test_asking_a_person_at_a_ceiling_already_parks_the_run_in_a_form_that_outlives_the_process() -> None:
    """The whole case against a fourth action, driven end to end.

    Everything `park` promises — stop here, keep the work, pick it up in another
    process later — `ask-a-person` already does, and the only string that
    crosses the boundary below is the durable record itself. Eve's equivalent is
    a session-limit continuation keyed by session, separate from its four other
    park kinds, each of which needs its own state key and its own guard deciding
    whether the answer that just arrived belongs to this run.
    """
    spec = replace(SPEC, max_steps=2, limits=Limits(when_it_runs_out=Action.ASK))
    parked = asyncio.run(run(spec, ReferenceTransport(never_finishes()), "hello", TOOLS))
    assert parked.halted == "suspended"
    assert parked.suspension is not None
    assert parked.suspension.reason == OUT_OF_BUDGET
    assert len(parked.steps) == 2

    # The process dies here. Only this string survives it.
    carried = Suspension.from_json(parked.suspension.to_json())
    assert carried.correlation_key == parked.suspension.correlation_key
    assert carried.used["steps"] == 2, "and it remembers what it had already spent"

    resumed = asyncio.run(
        run(spec, ReferenceTransport(never_finishes()), "hello", TOOLS,
            resume=carried, answer=carried.answer(decision="yes"))
    )
    assert len(resumed.steps) == 4, "it carried on from the record, not from the start"


def test_a_park_with_nobody_to_tell_has_no_way_of_ever_starting_again() -> None:
    """What `park` would be, built by hand: the same suspension with the person
    taken out — nothing asked for, no deadline.

    A wait is cleared by a yes and by nothing else, and `TIMEOUT_ACTIONS` has no
    `approve` on purpose, because a timeout that grants is not a gate but a
    delay. So removing the person removes every exit: the run is stopped, is
    durable, and is finished with — which is the outcome a governance setting
    exists to prevent, not one it should offer. Eve parks indefinitely by
    default and this is what that costs.
    """
    silent = Suspension(reason=OUT_OF_BUDGET, asks=(), correlation_key="whatever")

    assert not silent.expired(now=10_000_000.0), "no deadline, so nothing ever ends it"
    assert "approve" not in TIMEOUT_ACTIONS, "and no timeout may grant the go-ahead"
    assert not clears(OUT_OF_BUDGET, ""), "and silence is not a go-ahead either"

    # Nothing anyone types is even admissible: a wait that asked for nothing has
    # no question for an answer to belong to.
    for said in ("yes", "approve", "carry on"):
        with pytest.raises(WrongAnswer):
            silent.answer(decision=said)
    assert silent.answer().values == {}, "so the only valid answer says nothing"

    # And through the real loop: it comes back parked, on the same record.
    spec = replace(SPEC, max_steps=2, limits=Limits(when_it_runs_out=Action.ASK))
    again = asyncio.run(
        run(spec, ReferenceTransport(never_finishes()), "hello", TOOLS,
            resume=silent, answer=silent.answer())
    )
    assert again.halted == "suspended", "still parked, with nothing left that could move it"
    assert again.suspension is silent, "and not even a new wait somebody could answer"


def test_the_three_actions_end_a_run_three_different_observable_ways() -> None:
    """The bar a fourth action would have to clear: a *different* ending.

    Each of these is distinguishable from the outside without knowing which
    ceiling was hit. `park` would produce `halted == "suspended"` with an
    `out-of-budget` suspension — byte for byte what `ask-a-person` produces —
    so it would be a second spelling rather than a fourth behaviour.
    """
    endings = {}
    for act in Action:
        script = never_finishes()
        spec = replace(SPEC, max_steps=2, limits=Limits(when_it_runs_out=act))
        r = asyncio.run(run(spec, ReferenceTransport(script), "hello", TOOLS))
        endings[act.value] = (
            r.halted,
            r.suspension.reason if r.suspension else None,
            # How many times the model was asked. Counted because it is the one
            # difference `halted` cannot show: two of these three end at the
            # same ceiling and report it by the same name.
            script.calls,
        )

    assert endings["stop-and-say-so"] == ("step-limit", None, 2)
    assert endings["ask-a-person"] == ("suspended", OUT_OF_BUDGET, 2)
    assert endings["answer-with-what-it-has"] == ("step-limit", None, 3), (
        "the third call is the closing one, made with no tools offered so the "
        "model has to answer from what it already has rather than start more work"
    )
    assert len(set(endings.values())) == len(Action), (
        "each action must be tellable apart from the others, or it is not an action"
    )


# ────────────────────────────────────────────── the refusal is written down too


def test_refusing_a_fourth_termination_action_is_written_down_where_a_reader_looks() -> None:
    """A decision recorded nowhere is re-litigated by the next person to read
    the enum, which is how a closed vocabulary of three becomes an open one of
    nine. Both places are load-bearing: the schema comment is what an author
    editing `when-it-runs-out` sees, and `50-NOT-COPIED.md` is what somebody
    asking "why is this not here?" reads.

    Both are asserted by the words that carry the argument rather than by whole
    sentences: a paragraph anybody may reword should not be a test anybody may
    break, but a paragraph that stops naming `park` has stopped being the
    refusal.
    """
    block = _limits_comment_block().lower()
    assert "park" in block, (
        "the `limits:` comment in spec/schema.yaml does not say that `park` was "
        "considered and refused, so the next reader has only three choices and "
        "no reason for them."
    )
    assert "fourth" in block, "and it must say plainly that there is no fourth action"

    assert NOT_COPIED.exists(), (
        "docs/50-NOT-COPIED.md is missing. A specification that does not say what "
        "it refuses accumulates everything."
    )
    written = NOT_COPIED.read_text(encoding="utf-8").lower()
    assert "park" in written, "the refused `park` action must be listed there"
    assert "ask-a-person" in written, "named against the thing that already does it"
