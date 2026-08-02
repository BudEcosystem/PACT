"""G13 — one order for everything reactive, not one per kind.

Eve fixes the order in which its reactive machinery runs — channel handler,
metadata projection, hooks, then dynamic resolvers — and states plainly that
*"The order is structural, not incidental"*
(`docs/concepts/sessions-runs-and-streaming.md`).

PACT gained `runs-at:` for interceptors and said nothing about where a `watch`
sits, so the answer is whatever the call order in `harness.run` happens to be.
**It happens to be right** — `bus.emit` runs after `chain.run`, so a watcher
already records `[card number removed]` rather than the digits.

That property is held by `test_nothing_that_watches_a_run_ever_sees_what_a_rule_hid`
below, which was mutation-tested: moving the emit above the chain — the edit
that looks like an improvement, "log it before anything changes it" — turns it
red.

**A previous version of this file also declared `WATCHING_RUNS_AT = 100` and
asserted `100 > 50 > 20 > 10`.** That assertion compared four integer literals,
could not fail, and `Bus` never sorted by band, so the constant enforced
nothing while reading as though it did. Both are deleted: the behavioural test
is the guarantee, and a second fake one beside it is worse than none.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.events import Bus  # noqa: E402
from pact_adapters.harness import run  # noqa: E402
from pact_adapters.interceptors import (  # noqa: E402
    EVERYTHING_ELSE_RUNS_AT,
    HIDING_RUNS_AT,
    REDACTION_RUNS_AT,
    Power,
    order_for,
)
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
CARD = "refund card 4111 1111 1111 1111"


def document() -> dict:
    out = subprocess.run(
        [str(REPO / "target/debug/pact"), "show", str(EXAMPLE)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


# ───────────────────────────────────────────────── the property that matters


def test_nothing_that_watches_a_run_ever_sees_what_a_rule_hid() -> None:
    """The safety property, held rather than assumed.

    A watcher subscribed to everything must not find the digits anywhere on the
    bus — not at the address the redaction rule names, and not at any other."""
    spec = AgentSpec.from_document(document(), "refund-desk")
    bus = Bus()
    seen: list[str] = []
    bus.on("", lambda e: seen.append(json.dumps(e.payload)))

    asyncio.run(run(spec, ReferenceTransport(Script([Turn("ok")])), CARD, {}, bus=bus))

    assert seen, "the bus must have carried something, or this proves nothing"
    leaked = [s for s in seen if "4111" in s]
    assert not leaked, f"a watcher saw a card number: {leaked[:1]}"
    assert any("card number removed" in s for s in seen), (
        "and it must have seen the redacted form, or the redaction never ran "
        "and this test is passing for the wrong reason"
    )



def test_a_rule_that_hides_runs_before_one_that_only_reads() -> None:
    """The default that keeps a support lead from reasoning about order at all:
    writing no `runs-at:` still gets hiding-before-reading."""
    assert order_for(frozenset({Power.HIDE_VALUES})) < order_for(frozenset({Power.STOP}))


def test_the_workspace_floor_runs_after_the_authors_own_words_but_before_a_guard() -> None:
    """A floor is a backstop, not an override — run it first and an author's
    chosen wording never appears. Run it after a guard and it is no floor at
    all, because the chain returns at the first stop."""
    assert HIDING_RUNS_AT < REDACTION_RUNS_AT < EVERYTHING_ELSE_RUNS_AT


# ──────────────────────────────────────────────── and the mutation that bites



def test_there_is_room_between_the_bands_to_place_something_new() -> None:
    """Gaps rather than 1,2,3,4: a rule can be put between two others without
    renumbering everything around it, which is the renaming hazard `runs-at:`
    was introduced to remove."""
    bands = sorted([HIDING_RUNS_AT, REDACTION_RUNS_AT, EVERYTHING_ELSE_RUNS_AT])
    for lower, upper in zip(bands, bands[1:]):
        assert upper - lower >= 10, f"no room between {lower} and {upper}"
