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

**The fencing token.** Every grant of a key to a holder that does not already
hold it is numbered one higher than the key's grant before it; a renewal keeps
the number. A lease bounds how long a claim lasts but cannot stop a call that is
already running when it ends, so a worker that stalled past its lease and then
writes would be a second writer nobody refused. The number is what the system it
writes to refuses it with: a write carrying a token lower than one it has seen
is stale. `Taken.fence` is the number, and an expired or released key keeps its
count so the next grant is higher still.

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
    who does and until when (`None`: no lease); and the fencing token of the
    grant that holds it."""

    ok: bool
    holder: str = ""
    until: float | None = None
    fence: int = 0


class ClaimStore(Protocol):
    """Where claims wider than one run are kept. The host supplies one."""

    def take(self, key: str, holder: str, lease: float | None) -> Taken:
        """Claim `key` for `holder` for `lease` seconds (`None`: no expiry).

        Taking a key you already hold succeeds and renews the lease — a worker
        sending its heartbeat — keeping its fencing token. Taking one somebody
        else holds, unexpired, fails. Any other take is a new grant, numbered
        one higher than the key's grant before it.
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
        # Kept when a claim expires or is released, so a later grant's token is
        # higher than every token the key was granted with before.
        self._fences: dict[str, int] = {}
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
            fence = self._fences.get(key, 0)
            if found is not None and found[0] != holder:
                return Taken(ok=False, holder=found[0], until=found[1], fence=fence)
            if found is None:
                fence += 1
                self._fences[key] = fence
            until = None if lease is None else self._clock() + lease
            self._held[key] = (holder, until)
            return Taken(ok=True, holder=holder, until=until, fence=fence)

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
                " key TEXT PRIMARY KEY, holder TEXT NOT NULL, until REAL,"
                " fence INTEGER NOT NULL DEFAULT 0)"
            )
            # A file written before the fencing token gains the column; its
            # rows count as never granted, so their next grant is token 1.
            columns = {row[1] for row in db.execute("PRAGMA table_info(claims)")}
            if "fence" not in columns:
                db.execute("ALTER TABLE claims ADD COLUMN fence INTEGER NOT NULL DEFAULT 0")

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
            # An expired or released row is free but kept, so its fencing count
            # survives; a released row's holder is empty.
            row = db.execute("SELECT holder, until, fence FROM claims WHERE key = ?", (key,)).fetchone()
            live = row is not None and row[0] != "" and (row[1] is None or row[1] > now)
            if live and row[0] != holder:
                db.execute("COMMIT")
                return Taken(ok=False, holder=row[0], until=row[1], fence=row[2])
            fence = row[2] if live else (0 if row is None else row[2]) + 1
            until = None if lease is None else now + lease
            db.execute(
                "INSERT INTO claims (key, holder, until, fence) VALUES (?, ?, ?, ?)"
                " ON CONFLICT(key) DO UPDATE SET holder = excluded.holder,"
                " until = excluded.until, fence = excluded.fence",
                (key, holder, until, fence),
            )
            db.execute("COMMIT")
            return Taken(ok=True, holder=holder, until=until, fence=fence)
        except BaseException:
            db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def release(self, key: str, holder: str) -> bool:
        now = self._clock()
        db = self._connect()
        try:
            cur = db.execute(
                "UPDATE claims SET holder = '', until = NULL WHERE key = ? AND holder = ?"
                " AND (until IS NULL OR until > ?)",
                (key, holder, now),
            )
            return cur.rowcount > 0
        finally:
            db.close()

    def holder(self, key: str) -> str | None:
        now = self._clock()
        db = self._connect()
        try:
            row = db.execute(
                "SELECT holder FROM claims WHERE key = ? AND holder != ''"
                " AND (until IS NULL OR until > ?)",
                (key, now),
            ).fetchone()
            return None if row is None else row[0]
        finally:
            db.close()


def scoped(
    across: str, team: str, tool: str, action: str, value: str, workspace: str = ""
) -> str:
    """The store key for one claim: its scope, then `(tool, action, value)`.

    `the-team` is namespaced by the team the run belongs to — the agent at the
    root of the request — so two teams using the same tool do not refuse each
    other. `the-workspace` is namespaced by the workspace's id when the host
    names one, so two workspaces sharing one store do not refuse each other
    either; without one it is one namespace for everything the store holds.
    """
    if across == "the-team":
        space = f"team:{team}"
    else:
        space = f"workspace:{workspace}" if workspace else "workspace"
    return "\x1f".join((space, tool, action, value))
