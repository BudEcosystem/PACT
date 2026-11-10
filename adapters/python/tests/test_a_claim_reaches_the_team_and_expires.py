"""Claims wider than one run, with a lease (docs/98 WP-7).

`same-request-key-across: the-team` and `the-workspace` used to change only the
refusal sentence: the claim was a dict inside one run, so a second run made the
same call. With a `ClaimStore` handed in by the host, every run sharing it
shares its claims; `claim-lasts:` makes a claim expire, so a worker that
crashed holding a task does not hold it for ever. Without a store, a wider
claim is held for this run only — and the run says so.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.at_most_once import Ledger, RequestKeys  # noqa: E402
from pact_adapters.claims import MemoryClaims, SqliteClaims  # noqa: E402


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _keys(scope: str | None, lease: str | None = None) -> RequestKeys:
    action: dict = {"same-request-key": "item"}
    if scope:
        action["same-request-key-across"] = scope
    if lease:
        action["claim-lasts"] = lease
    return RequestKeys.from_document(
        {
            "agents": {"w": {"uses": ["board"]}},
            "tools": {"board": {"actions": {"take": action}}},
        },
        "w",
    )


def _ledger(store, team: str, holder: str, scope="the-team", lease=None) -> Ledger:
    led = Ledger(_keys(scope, lease))
    led.store, led.team, led.holder = store, team, holder
    return led


CALL = {"action": "take", "item": "Q-7"}


@pytest.mark.parametrize("make", [MemoryClaims, None])
def test_two_runs_of_one_team_cannot_both_take_the_same_item(make, tmp_path) -> None:
    clock = Clock()
    store = make(clock=clock) if make else SqliteClaims(tmp_path / "claims.db", clock=clock)
    first = _ledger(store, "desk", "run-1")
    second = _ledger(store, "desk", "run-2")
    assert first.hold("board", CALL) == ""
    said = second.hold("board", CALL)
    assert "somewhere in this team" in said, said
    assert second.look("board", CALL), "look says the same before anybody asks"


def test_another_team_is_not_refused_by_this_one() -> None:
    store = MemoryClaims()
    assert _ledger(store, "desk", "a").hold("board", CALL) == ""
    assert _ledger(store, "other-desk", "b").hold("board", CALL) == ""


def test_a_workspace_claim_reaches_every_team() -> None:
    store = MemoryClaims()
    assert _ledger(store, "desk", "a", scope="the-workspace").hold("board", CALL) == ""
    said = _ledger(store, "other-desk", "b", scope="the-workspace").hold("board", CALL)
    assert "somewhere in this workspace" in said, said


def test_a_lease_that_runs_out_frees_the_item(tmp_path) -> None:
    clock = Clock()
    for store in (MemoryClaims(clock=clock), SqliteClaims(tmp_path / "c.db", clock=clock)):
        clock.now = 1000.0
        crashed = _ledger(store, "desk", "crashed", lease="5m")
        assert crashed.hold("board", CALL) == ""
        assert _ledger(store, "desk", "next", lease="5m").hold("board", CALL) != ""
        clock.now += 301
        assert _ledger(store, "desk", "next", lease="5m").hold("board", CALL) == "", (
            "five minutes after the worker that took it went quiet, the item is free"
        )


def test_the_holder_renews_its_own_lease(tmp_path) -> None:
    clock = Clock()
    store = SqliteClaims(tmp_path / "c.db", clock=clock)
    assert store.take("k", "me", 60).ok
    clock.now += 50
    assert store.take("k", "me", 60).ok, "a heartbeat is the holder taking it again"
    clock.now += 50
    assert not store.take("k", "you", 60).ok, "renewed, so still held at 100s"
    assert store.holder("k") == "me"
    assert store.release("k", "me")
    assert store.take("k", "you", 60).ok


def test_nobody_releases_a_claim_they_do_not_hold() -> None:
    store = MemoryClaims()
    assert store.take("k", "me", None).ok
    assert not store.release("k", "you")
    assert store.holder("k") == "me"


def test_two_processes_on_one_file_share_claims(tmp_path) -> None:
    one = SqliteClaims(tmp_path / "shared.db")
    two = SqliteClaims(tmp_path / "shared.db")
    assert one.take("k", "a", None).ok
    assert not two.take("k", "b", None).ok
    assert two.holder("k") == "a"


def test_with_no_store_a_wider_claim_is_kept_here_and_says_so() -> None:
    led = Ledger(_keys("the-team"))
    assert led.hold("board", CALL) == ""
    said = " ".join(led.unenforced())
    assert "board/take" in said and "the-team" in said, said
    assert "no claim store" in said, said
    # And it is still held for this run, which is the most it could do.
    assert led.hold("board", CALL) != ""


def test_a_run_scoped_claim_needs_no_store_and_reports_nothing() -> None:
    led = Ledger(_keys(None))
    assert led.hold("board", CALL) == ""
    assert led.unenforced() == ()


def test_the_lease_is_read_off_the_authored_document() -> None:
    keys = _keys("the-team", lease="5m")
    assert keys.leases == {("board", "take"): 300.0}


def test_the_harness_hands_the_store_to_every_run() -> None:
    from pact_adapters.harness import ToolCall, run
    from pact_adapters.ir import AgentSpec
    from pact_adapters.script import Script, Turn
    from pact_adapters.transports.mock import ReferenceTransport

    doc = {
        "agents": {
            "w": {
                "description": "Takes the next item.",
                "instructions": "Take Q-7.",
                "uses": ["board"],
            }
        },
        "tools": {
            "board": {
                "description": "The team's board.",
                "actions": {
                    "take": {
                        "description": "Take an item.",
                        "takes": {"item": "text"},
                        "same-request-key": "item",
                        "same-request-key-across": "the-workspace",
                    }
                },
            }
        },
    }
    spec = AgentSpec.from_document(doc, "w")
    taken: list[str] = []

    def take(args):
        taken.append(args.get("item", ""))
        return "taken"

    store = MemoryClaims()

    def script() -> Script:
        return Script(
            [
                Turn("", (ToolCall("board", {"action": "take", "item": "Q-7"}),)),
                Turn("done"),
            ]
        )

    for _ in range(2):
        asyncio.run(
            run(spec, ReferenceTransport(script()), "go", {"board": take}, claims=store)
        )
    assert taken == ["Q-7"], f"two runs sharing a store took the same item twice: {taken}"
