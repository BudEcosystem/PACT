"""AC-2.4 / AC-6.4 — importing with zero silent drops.

> Framework-native fixtures import with an `ImportReport`; every unmapped
> construct appears in the report — measured coverage: **zero silent drops**
> across the fixture set.

`ImportReport.silent_drops` is **computed from the source**, not maintained: a key
in none of the three buckets is a drop by definition, so a construct nobody
thought about lands there without anybody having to remember. Every test here
asserts it is empty, and one deliberately breaks an importer to prove the
measurement can fail.

**Why these two artifacts.** Every framework in this repository defines its agents
in code, and importing code means either executing it — which D17 and D23 forbid
outright — or parsing it, which is a different project. Two things are declarative
and real: an **A2A Agent Card**, which PACT itself exports so the round trip is
checkable; and an **Anthropic Messages request**, which is where a framework's
intent stops being computed and gets written down. The other five targets are
recorded as blocked in the register with what each would need.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.importing import (  # noqa: E402
    ImportReport,
    from_a2a_card,
    from_anthropic_request,
)

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"


@pytest.fixture(scope="module")
def card() -> dict:
    """The card PACT itself exports, so the round trip is a real one."""
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(PACT_BIN), "card", "refund-desk", str(EXAMPLE)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


# ────────────────────────────── the property the criterion is about


def test_importing_the_card_pact_exports_drops_nothing_silently(card: dict) -> None:
    """The round trip, which is the only import whose source PACT controls.

    Every key in the card is mapped, unmapped or not-portable. A key in none of
    the three is a silent drop, and `silent_drops` finds it whether or not
    anybody expected it.
    """
    _agent, report = from_a2a_card(card)
    assert report.silent_drops == (), (
        f"the card carries {report.silent_drops} and the report accounts for "
        f"none of it:\n{report.in_words()}"
    )
    assert set(report.seen) == set(card), "the report must have seen the whole card"


def test_the_card_round_trip_recovers_what_a_card_can_carry(card: dict) -> None:
    """What DID survive, asserted — or "zero silent drops" would be satisfied by
    an importer that mapped nothing and reported everything as unmapped."""
    agent, report = from_a2a_card(card)
    assert agent["name"] == "Refund Desk"
    assert "refund" in agent["description"].lower()
    assert set(agent["uses"]) == {"zendesk", "payments", "refund-policy"}
    # Handoffs become teammates, not tools. A card tags them and an importer that
    # ignored the tag would produce an agent that thinks its colleagues are APIs.
    assert set(agent["team"]) == {"policy-checker", "fraud-checker"}
    assert "policy-checker" not in agent["uses"]
    assert len(report.mapped) >= 3, report.mapped


def test_the_report_says_a_card_is_a_facade(card: dict) -> None:
    """A card carries no instructions, no ceilings, no loop and no policy.

    Producing that stub is fine. Producing it and letting somebody believe they
    had imported an agent is not, so the shortfall is in the report as work to
    do rather than absent.
    """
    _agent, report = from_a2a_card(card)
    owed = " ".join(report.still_to_write)
    for missing in ("instructions:", "limits:", "loop:", "policy:"):
        assert missing in owed, f"the report does not say `{missing}` is still owed"


def test_a_deployment_fact_is_not_imported_as_an_agent_fact(card: dict) -> None:
    """`url` is where one deployment answers. Importing it would make the tree
    claim something a runtime decides — which is exactly what makes the same tree
    runnable in two places."""
    agent, report = from_a2a_card(card)
    assert "url" in report.not_portable
    assert "url" not in agent and "protocolVersion" not in agent
    assert "deployed" in report.not_portable["url"]


# ───────────────────────── the framework-native one


def test_a_real_request_body_imports_with_everything_accounted_for() -> None:
    """A Messages API request — where a framework's intent stops being computed
    and gets written down."""
    request = {
        "model": "claude-sonnet-5",
        "system": "You triage support tickets.",
        "max_tokens": 2048,
        "temperature": 0.2,
        "stop_sequences": ["END"],
        "tool_choice": {"type": "any"},
        "tools": [
            {"name": "zendesk", "description": "read the ticket", "input_schema": {}},
        ],
        "messages": [{"role": "user", "content": "hello"}],
        "stream": True,
        "metadata": {"user_id": "u-1"},
        "a_key_nobody_has_heard_of": 7,
    }
    agent, report = from_anthropic_request(request)

    assert report.silent_drops == (), report.in_words()
    assert agent["instructions"] == "You triage support tickets."
    assert agent["model"] == "claude-sonnet-5"
    assert agent["uses"] == ["zendesk"]
    assert agent["settings"]["max-tokens"] == 2048
    assert agent["settings"]["temperature"] == 0.2
    # `any` on the wire is `required` in the author's words — the same mapping
    # `anthropic_transport._translated` uses in the other direction.
    assert agent["settings"]["tool-choice"] == "required"

    # A transcript is not an agent.
    assert "messages" in report.not_portable
    assert "conversation" in report.not_portable["messages"]
    assert "messages" not in agent
    # And a key nobody has heard of is REPORTED, not dropped.
    assert "a_key_nobody_has_heard_of" in report.unmapped


def test_a_system_prompt_written_as_blocks_is_read_as_one() -> None:
    """The API takes `system` as a string or as a list of text blocks. An
    importer that read only the string form would silently produce an agent with
    no instructions from a request that plainly had some."""
    agent, report = from_anthropic_request({
        "system": [
            {"type": "text", "text": "You triage tickets."},
            {"type": "text", "text": "Be brief."},
        ],
        "max_tokens": 10,
    })
    assert "You triage tickets." in agent["instructions"]
    assert "Be brief." in agent["instructions"]
    assert report.silent_drops == ()


# ──────────────────────────── and the measurement itself can fail


def test_the_drop_measurement_is_not_decorative() -> None:
    """The mutation, written into the suite rather than run by hand.

    `silent_drops` is computed from `seen`, so an importer that forgets a key it
    was handed is caught. If this can be made to pass with a key genuinely
    unaccounted for, every assertion above is worthless.
    """
    report = ImportReport(kind="a made-up thing", seen=("a", "b", "c"))
    report.mapped["a"] = "somewhere"
    report.not_portable["b"] = "a reason"
    assert report.silent_drops == ("c",), report.silent_drops
    assert "BUG IN THIS IMPORTER" in report.in_words()

    report.unmapped["c"] = "now accounted for"
    assert report.silent_drops == ()
    assert "BUG IN THIS IMPORTER" not in report.in_words()


def test_an_importer_that_forgets_a_key_is_caught(card: dict) -> None:
    """The same property through a real importer: hand it a card with a key it
    has never seen and the report must place it somewhere."""
    strange = dict(card)
    strange["somethingNobodyPlannedFor"] = {"nested": True}
    _agent, report = from_a2a_card(strange)
    assert report.silent_drops == (), report.in_words()
    assert "somethingNobodyPlannedFor" in report.unmapped
