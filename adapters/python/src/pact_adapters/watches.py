"""Watches — the half of the event lattice that only LOOKS.

`interceptors` binds to an address and may CHANGE what happens. This binds to
the same addresses and may not. It is the safer of the two powers by a long way,
and until now it was the one an author could not reach at all: `Bus.on(pattern,
fn)` takes a Python callable, so watching a run was a HOST capability while the
dangerous half — mutation — was already authorable in YAML. That is the wrong
way round twice over, and it is the one D14 ("no capability may require author
code") could not reach.

# Why this is its own kind and not an interceptor with an empty `may:`

Eve's 28 lifecycle events are **all** observe-only — its own source says
*"Handlers are observe-only. They cannot inject model context."* — so watching is
the only half it has, and even that half costs TypeScript. PACT has both halves,
and keeping them two constructs is precisely what lets the safe one be
beginner-tier (`tier: core`, every field) while the dangerous one is not
(`workspace.interceptors` is `tier: expert`).

Fold them into one kind and three things go wrong at once:

  * a person who only wants to know when something happened has to read about
    hiding values, stopping the run and sending it somewhere else first;
  * turning a thing that looks into a thing that changes becomes ONE WORD added
    to a `may:` list, in a document nobody thought needed reviewing;
  * `may: []` would have to mean "allowed to do nothing", which reads as a
    mistake — and every other empty `may:` in the schema IS one, refused by
    `_powers` with *"this rule does not say what it may do, so it may do
    nothing"*.

The same argument decides where a watch lives. An interceptor changes ONE
agent's behaviour, so that agent names it in its own `interceptors:` line. A
watch changes nothing, so it belongs to the WORKSPACE and applies to every run in
it: making somebody name it twice would buy nothing, and it would let an agent
quietly stop being watched by deleting one line.

# What a line can and cannot carry

A watch writes down WHAT happened, WHEN, and where in the run — never the words a
customer typed, the words the model wrote, or the values handed to a tool. That
is not a checked rule, it is `RECORDED`: an allow-list of payload keys, so a
payload field nobody has admitted is simply absent from the record. The direction
matters. The worked example redacts card numbers before they reach the model
(`interceptors/redact-card-numbers.yaml`) and before they reach the `payments`
call (`...-in-tool-calls.yaml`); a watch that wrote payloads out verbatim would
be a way to undo both from a document that needed no approval — the same shape as
WAIT-4's "a timeout can never approve", prevented by there being nowhere to write
it rather than by a check that could be forgotten.

The destination is a plain FILE NAME for the same structural reason. The record
goes under the workspace's own `.pact/watch/`, which is derived (D2: deleting
`.pact/` must be harmless) and which the loader skips because it begins with a
dot — so a watch can never land on top of an author's file, and a workspace that
has been run still passes `pact check`. A name with a `/` in it, or one that
climbs out with `..`, is refused with the name to type instead. Air-gapped by
construction (D17): the only destination is a local file, so no core feature here
wants a hosted collector.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .diagnostics import locate
from .events import Address, Bus, Event

#: Where a watch's record is kept, relative to the workspace root.
#:
#: Under `.pact/` deliberately. The loader skips any name beginning with a dot
#: (`Policy::is_ignored`), so a workspace that has been RUN still loads and still
#: checks clean — write the record to `reports/` instead and the next
#: `pact check` says *"'reports' is not something a workspace can have"*, which
#: is a mistake the author did not make and cannot understand.
UNDER = Path(".pact") / "watch"

#: Where the derived area goes when the workspace itself cannot be written to.
#:
#: Register row C8: `.pact/` is written INTO the workspace, so a read-only
#: checkout — a container image, a signed release, anything mounted `ro` — could
#: not run a watch at all. It did not degrade: `base.mkdir` raised inside a bus
#: handler, so an observability feature took down the run it was only watching.
#:
#: An environment variable and not a document field, deliberately. Where derived
#: output lands is a deployment fact, decided by whoever runs this — the same
#: reason `invocation.url` is left empty when exporting an `AgentRecord`. A
#: workspace that named its own would stop being runnable in two places.
DERIVED_DIR = "PACT_DERIVED_DIR"


def derived_area(root: "str | Path | None") -> "Path | None":
    """Where this workspace's derived records go, or `None` if nowhere can.

    `$PACT_DERIVED_DIR` wins when it is set, so a read-only checkout is run by
    pointing it somewhere writable rather than by copying the tree.
    """
    override = os.environ.get(DERIVED_DIR, "").strip()
    if override:
        return Path(override) / UNDER
    return Path(root) / UNDER if root else None


def can_be_written(area: "Path | None") -> bool:
    """Whether records can actually land there.

    Asked ONCE, when the watches are attached, rather than discovered per line:
    a run that reports its watches unwritten from the start is one somebody can
    act on, and a run that discovers it on the fortieth event has already told
    the author nothing about the first thirty-nine.
    """
    if area is None:
        return False
    try:
        area.mkdir(parents=True, exist_ok=True)
        probe = area / ".writable"
        probe.write_text("")
        probe.unlink()
        return True
    except OSError:
        return False

def write_down(base: "Path", watch: "Watch", record: Mapping[str, Any]) -> bool:
    """Append one record to `watch`'s file under `base`; whether it landed.

    The whole write, on its own, so a runtime with no `Bus` — one that keeps its
    own journal and must write a line only once however often a run is resumed —
    writes exactly the line a subscribed watch writes. Blocking file I/O: a
    runtime on an event loop calls it from a worker thread.

    Opened, appended and closed per line rather than held open for the run. A
    run can be suspended for a person's answer and continue in another process a
    day later (§7.14), and a record that only reaches the disk when a handle is
    closed is a record that is not there when somebody asks what the run did
    before it stopped.
    """
    try:
        base.mkdir(parents=True, exist_ok=True)
        with (base / watch.writes_to).open("a", encoding="utf-8") as f:
            f.write(json.dumps(dict(record), sort_keys=True) + "\n")
        return True
    except OSError:
        # The area was writable when the watches were attached and is not now —
        # a disk filled, a mount went away. Watching must never be the reason a
        # run fails: it changes nothing about what the agent does, and a record
        # is worth less than the work it was recording.
        return False


#: The payload fields a line carries. Names, moments, counts and outcomes.
#:
#: An ALLOW-list, so the next `bus.emit` keyword is absent from every record
#: until somebody adds it here on purpose. A deny-list would have the opposite
#: failure: `bus.emit("session.run.started", input=user_input)` and
#: `bus.emit("step.model.completed", text=text, ...)` both carry words somebody
#: wrote, and forgetting either would put the customer's message and the model's
#: answer in a file that needed no approval to create.
RECORDED: tuple[str, ...] = (
    # which tool, which stage, which teammate, which question
    "name",
    # what kind of stage it was — `think`, `use-a-tool`, `ask-someone`
    "does",
    # how the stage ended — `answered`, `used-a-tool`, `too-many-times`
    "outcome",
    # why a run stopped: one of the closed reasons, or the sentence the AUTHOR
    # wrote in their own `stop and say "..."` rule. Never anything a customer or
    # a model produced.
    "reason",
    # which teammate was asked, and which tools the model asked for. Names only:
    # `tools` is built as `[c.name for c in calls]` at the emit site.
    "member",
    "tools",
)

#: Every address the reference harness actually emits — §7.13's table of thirty.
#:
#: A watch bound anywhere else is REFUSED, naming the moments that exist for the
#: same thing. This is the `WIRED` check `interceptors` already makes, pointed at
#: the other half: an address that is well-formed and never reached is the
#: "loads and does nothing" failure this project keeps shipping, and it is worse
#: here than there, because the author of a watch is told nothing at all rather
#: than merely not protected.
#:
#: Held in step with the harness by
#: `test_every_address_a_watch_may_name_is_one_the_harness_really_emits`, which
#: greps `bus.emit(` out of the source rather than trusting this tuple.
EMITTED: tuple[str, ...] = (
    "session.limit.failed",
    "session.run.started",
    "step.approval.completed",
    "step.approval.requested",
    "step.compaction.completed",
    "step.compaction.started",
    "step.delegate.cancelled",
    "step.delegate.completed",
    "step.delegate.failed",
    "step.delegate.requested",
    "step.delegate.started",
    "step.input.requested",
    "step.message.completed",
    "step.model.completed",
    "step.model.requested",
    "step.run.started",
    "step.stage.completed",
    "step.stage.started",
    "step.tool.cancelled",
    "step.tool.completed",
    "step.tool.started",
    "turn.approval.failed",
    "turn.delegate.completed",
    "turn.delegate.failed",
    "turn.limit.completed",
    "turn.message.completed",
    "turn.run.cancelled",
    "turn.run.completed",
    "turn.run.failed",
    "turn.run.started",
)

#: Buses these watches have already been attached to, marked on the bus itself.
#:
#: A delegate's run is handed the PARENT's bus (`harness.py`: `bus=bus`) and
#: builds its own `AgentSpec` from the same document, so its `watches` are the
#: same workspace-level watches. Without this every line would be written twice
#: for any workspace whose agents ask each other anything — and the record would
#: say two tool calls happened where one did.
_ATTACHED = "_pact_watching"


class WatchError(ValueError):
    """An authoring mistake in a watch document.

    Raised rather than absorbed, for the reason `InterceptorError` gives: the
    only available fallback is to ignore it, and a watch that is ignored leaves
    an author believing a run is being recorded when nothing is recording it.
    Every message names the file, the line, what is wrong, and a line to type.
    """


def _where(source: "Path | None", name: str, phrase: str) -> str:
    """`watch/tool-calls.yaml:25` — the file and line, never a made-up path."""
    file, line = locate(source, "watch", "watch", name, phrase[:60])
    return f"{file}:{line}"


@dataclass(frozen=True)
class Watch:
    """One authored watch: a moment, and a file to write it down in."""

    name: str
    when: str
    writes_to: str
    description: str = ""

    def line(self, event: Event) -> dict[str, Any]:
        """One record of one thing that happened.

        `at` is the position the bus already stamps — session/turn/step indices —
        which is what makes "the third tool call of step 4" answerable without
        the payload. Eve stamps a `{sequence, stepIndex, turnId}` triple on every
        content event and reconstructs the rest from the content it also ships.
        """
        record: dict[str, Any] = {"happened": str(event.address), "at": list(event.at)}
        for key in RECORDED:
            if key in event.payload:
                record[key] = event.payload[key]
        return record


@dataclass
class Watches:
    """The watches a workspace declares, in the order it declares them."""

    watches: tuple[Watch, ...] = ()
    #: Every record made in this process, whether or not it reached a file.
    #: Kept so a host that was handed a document without its tree (invariant
    #: P-1) still has the run's record, and so a test can read one without
    #: opening a file.
    seen: list[dict[str, Any]] = field(default_factory=list)
    #: Watches that had nowhere to write, because nothing said where the
    #: workspace is. Reported on `RunResult.unwatched` for the reason
    #: `unmetered` exists: an author who wrote a watch and got neither a record
    #: nor a word about it has been told something untrue (T7).
    unwritten: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.watches)

    def __len__(self) -> int:
        return len(self.watches)

    def __iter__(self) -> "Iterable[Watch]":
        return iter(self.watches)

    def at(self, address: str) -> list[Watch]:
        addr = Address.parse(address)
        return [w for w in self.watches if addr.matches(w.when)]

    def subscribe(self, bus: Bus, root: "str | Path | None" = None) -> tuple[str, ...]:
        """Attach these watches to `bus`, once. Returns the ones with nowhere to go.

        Once, because a delegate's run is given the parent's bus and would
        otherwise write every line a second time — see `_ATTACHED`.
        """
        already: frozenset[str] = getattr(bus, _ATTACHED, frozenset())
        mine = frozenset(w.name for w in self.watches)
        if mine and mine <= already:
            return self.unwritten
        setattr(bus, _ATTACHED, already | mine)

        if not self.watches:
            # NOTHING TO WRITE, so nothing is probed. The probe below creates the
            # area, and a workspace that declared no `watch:` must not acquire a
            # `.pact/` for having been run — D2 says the derived area is
            # disposable, not that it appears uninvited. Caught by
            # `test_a_workspace_with_no_watch_document_records_nothing_at_all`,
            # which is the test this change first broke.
            self.unwritten = ()
            return self.unwritten
        base = derived_area(root)
        # Asked once, here. A workspace mounted read-only used to attach happily
        # and then raise `PermissionError` out of a bus handler on the first
        # event — an observability feature taking down the run it was watching.
        if not can_be_written(base):
            base = None
        nowhere: list[str] = []
        for watch in self.watches:
            if base is None:
                nowhere.append(watch.name)
            bus.on(watch.when, self._writer(watch, base))
        self.unwritten = tuple(nowhere)
        return self.unwritten

    def _writer(self, watch: "Watch", base: "Path | None"):
        def write(event: Event) -> None:
            record = watch.line(event)
            self.seen.append(record)
            if base is not None and not write_down(base, watch, record):
                if watch.name not in self.unwritten:
                    self.unwritten = self.unwritten + (watch.name,)

        return write

    @staticmethod
    def from_document(
        doc: Mapping[str, Any], source: "str | Path | None" = None
    ) -> "Watches":
        """Every watch this workspace declares.

        Workspace-level and not per-agent: a watch changes nothing, so there is
        no agent whose behaviour it is part of, and nothing for an agent to
        name. The consequence an author feels is that adding one file makes the
        whole system recorded, and no `agent.yaml` has to be touched.

        `source` is the workspace root and is optional for the reason
        `Chain.from_document`'s is: an adapter is handed a loaded document
        (invariant P-1) and may not have the tree beside it. Given one, every
        message below names a real file and a real line.
        """
        root = Path(source) if source is not None else None
        declared = doc.get("watch") or {}
        if not isinstance(declared, Mapping):
            raise WatchError(
                "`watch:` should be one entry per thing you are keeping an eye "
                "on. Fix: put each one in its own file under `watch/`, like "
                "`watch/tool-calls.yaml`."
            )
        return Watches(
            watches=tuple(
                _one(name, entry, root) for name, entry in sorted(declared.items())
            )
        )


def _one(name: str, raw: Any, root: "Path | None") -> Watch:
    where = _where(root, name, "")
    if not isinstance(raw, Mapping):
        raise WatchError(
            f"{where}: this should be a set of settings, not "
            f"{type(raw).__name__}. Fix: write it as `when:` and `writes-to:` "
            f"lines."
        )

    when = str(raw.get("when") or "").strip()
    if not when:
        raise WatchError(
            f"{where}: this does not say what moment to write down. "
            f"Fix: add a line `when: step.tool.completed` — a part of the run, "
            f"a thing that happens, and a moment."
        )
    _check_address(_where(root, name, when), when)

    writes_to = str(raw.get("writes-to") or "").strip()
    if not writes_to:
        raise WatchError(
            f"{where}: this does not say where to write it down. "
            f"Fix: add a line `writes-to: {name}.jsonl` — just a file name."
        )
    _check_destination(_where(root, name, writes_to), writes_to)

    return Watch(
        name=name,
        when=when,
        writes_to=writes_to,
        description=str(raw.get("description") or "").strip(),
    )


def _check_address(where: str, when: str) -> None:
    """Well-formed, and a moment a run actually reaches.

    Two questions, because they have two different fixes. `turn.answer.after` is
    not an address at all and the fix is the vocabulary; `session.tool.completed`
    is a perfectly good address that nothing ever emits, and the fix is the list
    of moments that thing really has.
    """
    try:
        Address.parse(when)
    except ValueError as e:
        raise WatchError(f"{where}: {e}") from None

    address = Address.parse(when)
    if address.subject.startswith("x-"):
        # A thing of the author's own. Whatever emits it is the host's, so this
        # module has no list to hold it against and refusing would be a guess.
        return
    if when in EMITTED:
        return
    same_thing = [a for a in EMITTED if Address.parse(a).subject == address.subject]
    offer = ", ".join(same_thing) if same_thing else ", ".join(EMITTED)
    raise WatchError(
        f"{where}: nothing in a run ever reaches {when!r}, so this would sit "
        f"there and write nothing down. Fix: change `when:` to one of: {offer}."
    )


def _check_destination(where: str, writes_to: str) -> None:
    """Just a file name. Not a path, and never one that climbs out.

    Structural rather than a sanitiser: there is no spelling of a destination
    outside `.pact/watch/`, so a document that needs nobody's approval cannot
    reach anything else on the machine. The same shape as `if-nobody-answers`
    having no word for "approve" (ASK-3) — prevented by there being nowhere to
    write it.
    """
    bad = None
    if "/" in writes_to or "\\" in writes_to:
        bad = "a folder in it"
    elif writes_to.startswith("."):
        bad = "a dot at the front"
    elif writes_to in ("..", "."):
        bad = "no name in it"
    if bad is None:
        return
    plain = writes_to.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1].lstrip(".")
    raise WatchError(
        f"{where}: {writes_to!r} has {bad}, and `writes-to:` is just a file "
        f"name — the record is kept in this workspace's own `.pact` area so it "
        f"can never land on top of something you wrote. "
        f"Fix: write `writes-to: {plain or 'what-happened'}.jsonl`."
    )
