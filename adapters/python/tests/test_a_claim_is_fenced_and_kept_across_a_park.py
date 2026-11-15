"""A claim's fencing token, its workspace, and its holder across a park (docs/98 WP-7).

A lease (`claim-lasts:`) frees a key a crashed worker held, but it cannot stop a
call that is still running when the lease ends: a worker that stalled past its
lease and then writes is a second writer nobody refused. Every grant is
therefore numbered, one higher than the key's grant before it, and the number
survives expiry and release, so the system a call writes to can refuse a writer
whose number is lower than one it has seen. A renewal by the same holder keeps
the number.

A `the-workspace` claim is namespaced by the workspace's id when the host names
one, so two workspaces sharing one store do not refuse each other.

A parked run comes back as the same holder (`Suspension.claim_holder`): under a
new name it could neither renew nor release what it claimed before the park.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.at_most_once import Ledger, RequestKeys  # noqa: E402
from pact_adapters.claims import MemoryClaims, SqliteClaims, scoped  # noqa: E402
from pact_adapters.suspension import Suspension  # noqa: E402


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _stores(tmp_path: Path, clock: Clock):
    return [MemoryClaims(clock=clock), SqliteClaims(tmp_path / "claims.db", clock=clock)]


@pytest.mark.parametrize("which", [0, 1])
def test_each_grant_of_a_key_is_numbered_one_higher_and_a_renewal_keeps_its_number(which, tmp_path) -> None:
    clock = Clock()
    store = _stores(tmp_path, clock)[which]
    first = store.take("k", "worker-1", 60)
    assert (first.ok, first.fence) == (True, 1)
    renewed = store.take("k", "worker-1", 60)
    assert (renewed.ok, renewed.fence) == (True, 1)
    refused = store.take("k", "worker-2", 60)
    assert (refused.ok, refused.holder, refused.fence) == (False, "worker-1", 1)
    clock.now += 61
    after_expiry = store.take("k", "worker-2", 60)
    assert (after_expiry.ok, after_expiry.fence) == (True, 2)
    assert store.release("k", "worker-2")
    assert store.holder("k") is None
    after_release = store.take("k", "worker-3", None)
    assert (after_release.ok, after_release.fence) == (True, 3)


@pytest.mark.parametrize("which", [0, 1])
def test_an_expired_holder_cannot_release_the_next_holders_claim(which, tmp_path) -> None:
    clock = Clock()
    store = _stores(tmp_path, clock)[which]
    assert store.take("k", "stalled", 10).ok
    clock.now += 11
    assert not store.release("k", "stalled"), "the lease ended, so nothing is held"
    assert store.take("k", "next", 10).fence == 2
    assert not store.release("k", "stalled")
    assert store.holder("k") == "next"


def test_a_claims_file_written_before_the_token_gains_it(tmp_path) -> None:
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE claims (key TEXT PRIMARY KEY, holder TEXT NOT NULL, until REAL)")
        db.execute("INSERT INTO claims VALUES ('k', 'old-run', NULL)")
    store = SqliteClaims(path)
    assert store.holder("k") == "old-run"
    assert store.take("k", "old-run", None).fence == 0, "the old grant keeps its holder, with no number yet"
    assert store.release("k", "old-run")
    assert store.take("k", "new-run", None).fence == 1


def test_a_workspace_claim_is_namespaced_by_the_workspace_id_when_the_host_names_one() -> None:
    assert scoped("the-workspace", "desk", "pay", "pay", "INV-1") == "workspace\x1fpay\x1fpay\x1fINV-1"
    assert scoped("the-workspace", "desk", "pay", "pay", "INV-1", "park-a") == "workspace:park-a\x1fpay\x1fpay\x1fINV-1"
    assert scoped("the-team", "desk", "pay", "pay", "INV-1", "park-a") == "team:desk\x1fpay\x1fpay\x1fINV-1"


def _keys(scope: str) -> RequestKeys:
    return RequestKeys.from_document(
        {
            "agents": {"w": {"uses": ["payments"]}},
            "tools": {"payments": {"actions": {"pay": {
                "same-request-key": "invoice", "same-request-key-across": scope, "claim-lasts": "10m",
            }}}},
        },
        "w",
    )


CALL = {"action": "pay", "invoice": "INV-7"}


def _ledger(store, holder: str, workspace: str = "", scope: str = "the-workspace") -> Ledger:
    led = Ledger(_keys(scope))
    led.store, led.team, led.holder, led.workspace = store, "desk", holder, workspace
    return led


def test_two_workspaces_sharing_one_store_do_not_refuse_each_other() -> None:
    store = MemoryClaims()
    assert _ledger(store, "a", workspace="park-a").hold("payments", CALL) == ""
    assert _ledger(store, "b", workspace="park-b").hold("payments", CALL) == ""
    said = _ledger(store, "c", workspace="park-a").hold("payments", CALL)
    assert "somewhere in this workspace" in said, said


def test_a_held_call_records_the_fencing_token_it_was_granted() -> None:
    store = MemoryClaims()
    first = _ledger(store, "a", scope="the-team")
    assert first.hold("payments", CALL) == ""
    assert first.fences == {("payments", "pay", "INV-7"): 1}


def test_a_parked_run_comes_back_as_the_holder_of_its_claims() -> None:
    parked = Suspension(reason="needs-approval", claim_holder="w:1f2e")
    back = Suspension.from_json(parked.to_json())
    assert back.claim_holder == "w:1f2e"
    assert parked.escalate(now=2000.0).claim_holder == "w:1f2e"
    old = parked.to_json().replace('"claim-holder": "w:1f2e", ', "")
    assert Suspension.from_json(old).claim_holder == "", "a record from before the field resumes under a new name"
