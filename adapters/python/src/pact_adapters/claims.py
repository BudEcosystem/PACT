"""Claims that reach past one run: the store behind `same-request-key-across`.

`docs/98-PRIMITIVES-ENGINEERING-PLAN.md` WP-7, the Store primitive's `claim`
operation (`docs/97-PRIMITIVES.md` §2.3): insert-if-absent, with a lease.

`Ledger` (`at_most_once.py`) holds a run's own claims in a dict, which is what
`same-request-key-across: this-run` means. `the-team` and `the-workspace` need a
record every run can see. The schema has always said so — "need a system that
keeps a record outside this run" — and the harness only changed its refusal
sentence. This is that record, as an interface the host supplies and two
implementations that keep it:

* `MemoryClaims` — every run in this process that is handed the same object
  shares its claims. Enough for a host running a team in one process, and for
  tests.
* `SqliteClaims` — a file. Every process that opens the same path shares its
  claims, and a claim survives a restart. `sqlite3` is in the standard library;
  `BEGIN IMMEDIATE` makes taking a claim one atomic step, so two workers racing
  for the same key cannot both get it.

**The lease** is `claim-lasts:`. A claim that has lasted that long is free
again, so a worker that crashed holding a task does not hold it for ever. That
is a queue's visibility timeout (`docs/92-SWARM.md` §6.3 asked for exactly this
rather than an invented semantics). A claim with no lease lasts as long as the
store keeps it.

**What is deliberately not here.** Releasing a claim early is `release`, called
by whoever holds it; nothing releases somebody else's. There is no "who holds
this" query on the run's side: the refusal says the key is taken, and the
holder's name is for the host's own tooling (`holder`).
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


@dataclass(frozen=True)
class Taken:
    """The answer to `take`: whether this caller now holds the key, and if not,
    who does and until when (`None`: no lease)."""

    ok: bool
    holder: str = ""
    until: float | None = None


class ClaimStore(Protocol):
    """Where claims wider than one run are kept. The host supplies one."""

    def take(self, key: str, holder: str, lease: float | None) -> Taken:
        """Claim `key` for `holder` for `lease` seconds (`None`: no expiry).

        Taking a key you already hold succeeds and renews the lease — a worker
        sending its heartbeat. Taking one somebody else holds, unexpired, fails.
        """
        ...

    def release(self, key: str, holder: str) -> bool:
        """Give back a key `holder` holds. False if they did not hold it."""
        ...

    def holder(self, key: str) -> str | None:
        """Who holds `key` now, or None."""
        ...


class MemoryClaims:
    """Claims shared by every run handed this object, in this process."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._held: dict[str, tuple[str, float | None]] = {}
        self._lock = threading.Lock()
        self._clock = clock

    def _live(self, key: str) -> tuple[str, float | None] | None:
        found = self._held.get(key)
        if found is None:
            return None
        holder, until = found
        if until is not None and until <= self._clock():
            del self._held[key]
            return None
        return found

    def take(self, key: str, holder: str, lease: float | None) -> Taken:
        with self._lock:
            found = self._live(key)
            if found is not None and found[0] != holder:
                return Taken(ok=False, holder=found[0], until=found[1])
            until = None if lease is None else self._clock() + lease
            self._held[key] = (holder, until)
            return Taken(ok=True, holder=holder, until=until)

    def release(self, key: str, holder: str) -> bool:
        with self._lock:
            found = self._live(key)
            if found is None or found[0] != holder:
                return False
            del self._held[key]
            return True

    def holder(self, key: str) -> str | None:
        with self._lock:
            found = self._live(key)
            return None if found is None else found[0]


class SqliteClaims:
    """Claims in a file every process opening the same path shares."""

    def __init__(self, path: "str | Path", clock: Callable[[], float] = time.time) -> None:
        self._path = str(path)
        self._clock = clock
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS claims ("
                " key TEXT PRIMARY KEY, holder TEXT NOT NULL, until REAL)"
            )

    def _connect(self) -> sqlite3.Connection:
        # `isolation_level=None` so `BEGIN IMMEDIATE` below is the transaction,
        # taken before the read: the read and the write are one step, and a
        # second writer waits rather than reading what the first is replacing.
        return sqlite3.connect(self._path, timeout=30, isolation_level=None)

    def take(self, key: str, holder: str, lease: float | None) -> Taken:
        now = self._clock()
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM claims WHERE until IS NOT NULL AND until <= ?", (now,))
            row = db.execute("SELECT holder, until FROM claims WHERE key = ?", (key,)).fetchone()
            if row is not None and row[0] != holder:
                db.execute("COMMIT")
                return Taken(ok=False, holder=row[0], until=row[1])
            until = None if lease is None else now + lease
            db.execute(
                "INSERT INTO claims (key, holder, until) VALUES (?, ?, ?)"
                " ON CONFLICT(key) DO UPDATE SET holder = excluded.holder, until = excluded.until",
                (key, holder, until),
            )
            db.execute("COMMIT")
            return Taken(ok=True, holder=holder, until=until)
        except BaseException:
            db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def release(self, key: str, holder: str) -> bool:
        db = self._connect()
        try:
            cur = db.execute("DELETE FROM claims WHERE key = ? AND holder = ?", (key, holder))
            return cur.rowcount > 0
        finally:
            db.close()

    def holder(self, key: str) -> str | None:
        now = self._clock()
        db = self._connect()
        try:
            row = db.execute(
                "SELECT holder FROM claims WHERE key = ? AND (until IS NULL OR until > ?)",
                (key, now),
            ).fetchone()
            return None if row is None else row[0]
        finally:
            db.close()


def scoped(across: str, team: str, tool: str, action: str, value: str) -> str:
    """The store key for one claim: its scope, then `(tool, action, value)`.

    `the-team` is namespaced by the team the run belongs to — the agent at the
    root of the request — so two teams using the same tool do not refuse each
    other. `the-workspace` is one namespace for everything here.
    """
    space = f"team:{team}" if across == "the-team" else "workspace"
    return "\x1f".join((space, tool, action, value))
