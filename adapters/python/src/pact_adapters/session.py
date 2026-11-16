"""A session: one workspace, run two ways (`docs/100` §6).

**Interpreted.** `Session.open(root)` keeps a workspace that can be changed
while runs are going. A change is a *proposal*: new definitions (`propose`),
existing ones replaced (`change`), one taken away (`withdraw`), or a cell a
model wrote during a run (`cell`). Every proposal goes through one door:

    staged copy of the tree → the change applied → `pact check` → admitted or refused

The judge is the same `pact` binary that checks a tree before any run (law 8
of `docs/97-PRIMITIVES.md`: "two phases, one checker"). Nothing here re-reads
a rule of the checker in Python. What this module adds are the facts only a
session can know, each a guard with a name: who is proposing and what THEY
were given (`reach`, `wider`), what a model may define at all (`floor`), how
much checking one proposal may cost (`meter`), and that a name already taken
is never quietly replaced by a model (`collision`).

**Pre-compiled.** `compile_plan(root)` checks a workspace once and seals what
was checked into a `Plan`: the document, and a fingerprint of it. A plan runs
with no checker beside it, and refuses every proposal, because nothing is
there to judge one. The same document runs on the same runtime either way.

**What holds while a session changes:**

* A change takes effect for what STARTS after it. A run already going holds
  the document it started with (`Session.document` is replaced, never edited),
  so an ask in flight finishes under the version it began with.
* Every version has a fingerprint, and a run is told which one it ran
  (`Session.version`).
* The journal is written before the change is: a proposal that was recorded
  and never admitted is, on resume, as if it had never been made.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .loader import pact_binary

#: The blocks a cell may define: things made OF the workspace's own parts.
A_CELL_MAY_DEFINE = ("agent", "flow", "workflow", "shape", "actor")
#: Everything else that starts a block. A model writing one is refused: what
#: the workspace can reach, who may approve and what is hidden are the
#: workspace's to say (`docs/100` §6.3, the floor).
THE_WORKSPACES_OWN = (
    "workspace", "tool", "resource", "policy", "port", "owner", "release", "redaction",
    "evals", "learning", "models", "plugin", "interceptor", "watch", "let", "when",
    "question", "knowledge", "skill", "program", "value", "loop", "context-policy",
    "bundle", "topic", "event", "reaction", "remembers", "detector",
)
#: What a helper a model defines may say about itself. Not its model, its
#: policy or its team: those it has from nobody, so it has none.
A_HELPER_MAY_WRITE = frozenset(
    {"name", "description", "instructions", "accepts", "answers-with", "limits", "uses",
     "checks-at-most", "checked-by"}
)
#: The collection each header word files its block under.
COLLECTION = {"agent": "agents", "flow": "workflows", "workflow": "workflows", "shape": "shapes"}

#: How much one proposal from a model may ask the checker to read.
MOST_BYTES, MOST_LINES, MOST_BLOCKS, DEEPEST = 8_000, 200, 12, 12
#: How many definitions models may add to one session in all.
MOST_FROM_MODELS = 200


@dataclass(frozen=True)
class Admission:
    """What the door said to one proposal."""

    admitted: bool
    #: The session's version once this was decided: new when admitted, the
    #: one it had when refused.
    version: str
    #: Why it was refused: the checker's own sentences, or the guard's.
    said: tuple[str, ...] = ()
    #: Which door refused it: `checker`, or the session guard by name.
    refused_by: str = ""
    #: What it defined, as `collection/name`.
    names: tuple[str, ...] = ()
    #: For a cell, the flow to run.
    main: str = ""
    #: How long the door took, in seconds.
    took: float = 0.0


@dataclass(frozen=True)
class Plan:
    """A workspace checked once and sealed: the pre-compiled way to run."""

    document: Mapping[str, Any]
    version: str
    checker: str = ""

    def save(self, path: "str | Path") -> None:
        Path(path).write_text(
            json.dumps({"version": self.version, "checker": self.checker, "document": self.document},
                       sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def load(path: "str | Path") -> "Plan":
        """Read a plan back, and refuse one that is not what was sealed."""
        held = json.loads(Path(path).read_text(encoding="utf-8"))
        if fingerprint(held["document"]) != held["version"]:
            raise ValueError(
                f"{path} is not the plan that was sealed: its document no longer has the "
                f"fingerprint written beside it. Compile it again from the workspace."
            )
        return Plan(held["document"], held["version"], held.get("checker", ""))

    def propose(self, *_: Any, **__: Any) -> Admission:
        """A sealed plan takes no change: nothing is beside it to check one."""
        return Admission(
            False, self.version, refused_by="sealed",
            said=("This workspace is running pre-compiled: it was checked once and sealed, so "
                  "nothing can be defined or changed while it runs. Open it as a session "
                  "(`Session.open`) to change it while it runs.",),
        )

    change = withdraw = cell = propose


def fingerprint(document: Mapping[str, Any]) -> str:
    """One document's fingerprint: the same for the same document, wherever
    and whenever it was loaded."""
    text = json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _pact(*args: str) -> subprocess.CompletedProcess[str]:
    binary = pact_binary()
    if binary is None:
        raise RuntimeError("there is no `pact` binary here, and a session checks every change with it")
    return subprocess.run([str(binary), *args], capture_output=True, text=True)


def _checked(root: Path) -> tuple[list[str], "dict[str, Any] | None"]:
    """`pact check`'s errors for the tree, in its words, and the document when
    there are none."""
    shown = _pact("show", str(root))
    if shown.returncode == 0:
        return [], json.loads(shown.stdout)
    said = _pact("check", str(root), "--quiet")
    text = (said.stdout + said.stderr).replace(str(root) + "/", "")
    problems = [p.strip() for p in text.split("\n\n") if p.strip().startswith("error")]
    return problems or [text.strip() or "the checker refused it and said nothing"], None


def compile_plan(root: "str | Path") -> Plan:
    """Check a workspace once and seal it. Raises with the checker's words
    when it does not load."""
    problems, document = _checked(Path(root))
    if document is None:
        raise ValueError("this workspace does not load, so there is nothing to seal:\n" + "\n\n".join(problems))
    about = _pact("about")
    return Plan(document, fingerprint(document), (about.stdout or "").splitlines()[0] if about.stdout else "")


def blocks_of(text: str) -> list[tuple[str, str, str]]:
    """The blocks of `.pact` text, as `(header word, name, the block's text)`.
    A line at the left margin that is not a comment starts one."""
    out: list[tuple[str, str, list[str]]] = []
    for line in text.splitlines():
        if line.strip() and not line.startswith((" ", "\t", "#")):
            word, _, rest = line.partition(" ")
            name = rest.strip().split("(")[0].split(" ")[0].strip('"')
            out.append((word, name, [line]))
        elif out:
            out[-1][2].append(line)
    return [(w, n, "\n".join(lines).rstrip() + "\n") for w, n, lines in out]


def _calls(stages: Any) -> Iterable[str]:
    """Every `call:` under a set of stages, however deep."""
    for stage in (stages or {}).values() if isinstance(stages, Mapping) else ():
        if not isinstance(stage, Mapping):
            continue
        if stage.get("call"):
            yield str(stage["call"])
        for rung in stage.get("by") or ():
            if isinstance(rung, Mapping) and rung.get("agent"):
                yield str(rung["agent"])
        yield from _calls(stage.get("steps"))


def reach_of(document: Mapping[str, Any], agent: str) -> frozenset[str]:
    """What `agent` was given: each action of each tool it `uses:`, and each
    teammate. A cell it writes may call these and nothing else."""
    spec = (document.get("agents") or {}).get(agent) or {}
    out: set[str] = set(spec.get("team") or {})
    for used in spec.get("uses") or ():
        tool = (document.get("tools") or {}).get(used)
        if isinstance(tool, Mapping):
            out.update(f"{used}/{action}" for action in tool.get("actions") or {})
    return frozenset(out)


@dataclass
class Session:
    """A workspace that can be changed while it runs. See the module's words."""

    home: Path
    #: The tree as it stands now. Replaced whole on every admitted change.
    tree: Path
    document: Mapping[str, Any]
    version: str
    journal: "Path | None" = None
    #: Every proposal this session decided, in order.
    decided: list[Admission] = field(default_factory=list)
    _n: int = 0
    _from_models: int = 0

    # ── opening ──────────────────────────────────────────────────────────

    @classmethod
    def open(cls, root: "str | Path", *, journal: "str | Path | None" = None) -> "Session":
        """Open `root` as a session. With a `journal` that already has
        entries, every change it admitted is made again, in order, and each
        version it reached is held to the one written down."""
        home = Path(tempfile.mkdtemp(prefix="pact-session-"))
        tree = home / "v0"
        shutil.copytree(root, tree)
        problems, document = _checked(tree)
        if document is None:
            raise ValueError("this workspace does not load, so there is no session to open:\n" + "\n\n".join(problems))
        me = cls(home, tree, document, fingerprint(document), Path(journal) if journal else None)
        if me.journal is not None and me.journal.exists():
            me._resume()
        return me

    def close(self) -> None:
        shutil.rmtree(self.home, ignore_errors=True)

    # ── the four proposals ───────────────────────────────────────────────

    def propose(self, text: str, *, by: str = "an author") -> Admission:
        """New definitions, beside what is there."""
        return self._decide("propose", text, by, lambda tree: self._add(tree, text))

    def change(self, text: str, *, by: str = "an author") -> Admission:
        """Definitions that take the place of the ones of the same name."""

        def apply(tree: Path) -> "str | None":
            for word, name, _ in blocks_of(text):
                if not _remove(tree, word, name):
                    return (f"There is no {word} called '{name}' here to change. To add one, "
                            f"propose it; `change` replaces what is already written.")
            self._add(tree, text)
            return None

        return self._decide("change", text, by, apply)

    def withdraw(self, word: str, name: str, *, by: str = "an author") -> Admission:
        """Take one definition away. Refused, by the checker, while anything
        still names it."""

        def apply(tree: Path) -> "str | None":
            if not _remove(tree, word, name):
                return f"There is no {word} called '{name}' here to take away."
            return None

        return self._decide("withdraw", f"{word} {name}", by, apply)

    def cell(
        self,
        text: str,
        *,
        by: str,
        takes: Mapping[str, str] | None = None,
        gives: Mapping[str, str] | None = None,
        may_call: Iterable[str] = (),
    ) -> Admission:
        """A cell `by` (an agent of this workspace) wrote during a run: the
        statements to carry out, and before them any helpers it defines.

        It is held to what `by` was given. It may call what `by` may call
        (`reach_of`, and `may_call` from the host) and what it defines itself;
        a helper it defines may use no tool `by` does not, and take no more
        steps. It lives until `end(admission)`: a cell's definitions are for
        the call that wrote them."""
        started = time.monotonic()
        refused = self._measured(text) or self._floor(text)
        if refused:
            return self._refused(refused[0], refused[1], started)
        helpers = [(w, n, b) for w, n, b in blocks_of(text) if w in A_CELL_MAY_DEFINE]
        body = _statements(text)
        if not body.strip():
            return self._refused(
                "floor", "A cell has to do something: after any helpers it defines, write the "
                "statements to carry out, ending in `answer with …`.", started)
        taken = {n for w, n, _ in helpers if self._has(w, n)}
        if taken:
            return self._refused(
                "collision", f"{', '.join(sorted(taken))} is already defined here. A cell never "
                f"replaces what the workspace has: give yours another name.", started)
        self._n += 1
        main = f"cell-{self._n}"
        sig = ", ".join(f"{k}: {v}" for k, v in (takes or {}).items())
        out = (" gives " + ", ".join(f"{k}: {v}" for k, v in gives.items())) if gives else ""
        whole = "".join(b + "\n" for _, _, b in helpers) + (
            f"flow {main}({sig}){out}\n  description: A cell {by} wrote during a run.\n"
            + "".join(f"  {line}\n" if line.strip() else "\n" for line in body.splitlines())
        )
        allowed = set(reach_of(self.document, by)) | set(may_call) | {n for _, n, _ in helpers}

        def held(document: Mapping[str, Any]) -> "tuple[str, str] | None":
            return _within(document, self.document, by, main, [n for w, n, _ in helpers], allowed)

        got = self._decide("cell", whole, by, lambda tree: self._add(tree, whole, main), held=held,
                           started=started)
        if got.admitted:
            self._from_models += 1 + len(helpers)
            got = Admission(True, got.version, names=got.names, main=main, took=got.took)
            self.decided[-1] = got
        return got

    def end(self, admission: Admission) -> None:
        """The call a cell was written for has ended: what it defined goes."""
        if not (admission.admitted and admission.main):
            return
        staged = self._stage()
        (staged / f"session-{admission.main}.pact").unlink(missing_ok=True)
        problems, document = _checked(staged)
        if document is not None:
            self._swap(staged, document)
            self._write({"op": "end", "main": admission.main, "state": "admitted", "version": self.version})
        else:  # something admitted since still names it: it stays until that goes
            shutil.rmtree(staged, ignore_errors=True)

    # ── the door ─────────────────────────────────────────────────────────

    def _decide(self, op: str, text: str, by: str, apply: Any, *, held: Any = None,
                started: "float | None" = None) -> Admission:
        started = time.monotonic() if started is None else started
        self._write({"op": op, "by": by, "text": text, "state": "proposed"})
        staged = self._stage()
        said = apply(staged)
        if said:
            shutil.rmtree(staged, ignore_errors=True)
            return self._refused("session", said, started)
        problems, document = _checked(staged)
        if document is None:
            shutil.rmtree(staged, ignore_errors=True)
            return self._refused("checker", problems, started)
        guard = held(document) if held is not None else None
        if guard is not None:
            shutil.rmtree(staged, ignore_errors=True)
            return self._refused(guard[0], guard[1], started)
        before = self.document
        self._swap(staged, document)
        names = tuple(
            f"{c}/{k}" for c in ("agents", "workflows", "shapes")
            for k in (document.get(c) or {}) if k not in (before.get(c) or {})
        )
        self._write({"op": op, "state": "admitted", "version": self.version})
        got = Admission(True, self.version, names=names, took=time.monotonic() - started)
        self.decided.append(got)
        return got

    def _refused(self, by: str, said: "str | list[str]", started: float) -> Admission:
        said = (said,) if isinstance(said, str) else tuple(said)
        self._write({"state": "refused", "refused-by": by})
        got = Admission(False, self.version, said=said, refused_by=by, took=time.monotonic() - started)
        self.decided.append(got)
        return got

    def _stage(self) -> Path:
        staged = self.home / f"staged-{time.monotonic_ns()}"
        shutil.copytree(self.tree, staged)
        return staged

    def _swap(self, staged: Path, document: Mapping[str, Any]) -> None:
        """Make the staged tree the session's: one rename, so the tree is
        wholly the old one or wholly the new."""
        old = self.tree
        self.tree = staged
        self.document, self.version = document, fingerprint(document)
        shutil.rmtree(old, ignore_errors=True)

    def _add(self, tree: Path, text: str, name: str = "") -> None:
        self._n += 0 if name else 1
        (tree / f"session-{name or self._n}.pact").write_text(text, encoding="utf-8")

    def _has(self, word: str, name: str) -> bool:
        if word == "actor":
            return any(k.startswith(f"{name}-") for c in ("agents", "workflows") for k in self.document.get(c) or {})
        return name in (self.document.get(COLLECTION.get(word, "")) or {})

    # ── the guards only a session can keep ───────────────────────────────

    def _measured(self, text: str) -> "tuple[str, str] | None":
        lines = text.splitlines()
        deepest = max((len(l) - len(l.lstrip(" ")) for l in lines if l.strip()), default=0) // 2
        over = (
            f"it is {len(text.encode())} bytes, and the most is {MOST_BYTES}" if len(text.encode()) > MOST_BYTES
            else f"it is {len(lines)} lines, and the most is {MOST_LINES}" if len(lines) > MOST_LINES
            else f"it defines {len(blocks_of(text))} blocks, and the most is {MOST_BLOCKS}" if len(blocks_of(text)) > MOST_BLOCKS
            else f"it is nested {deepest} deep, and the most is {DEEPEST}" if deepest > DEEPEST
            else f"this session has taken {self._from_models} definitions from models, and the most is {MOST_FROM_MODELS}"
            if self._from_models >= MOST_FROM_MODELS else ""
        )
        return ("meter", f"This cell is more than a cell may be: {over}. Write a smaller one.") if over else None

    def _floor(self, text: str) -> "tuple[str, str] | None":
        for word, name, _ in blocks_of(text):
            if word in THE_WORKSPACES_OWN:
                return ("floor", f"A cell cannot define a {word} ('{name}'). What this workspace can "
                        f"reach, who is asked and what is hidden are the workspace's to say. A cell "
                        f"may define: {', '.join(A_CELL_MAY_DEFINE)}.")
        return None

    # ── the journal ──────────────────────────────────────────────────────

    def _write(self, entry: Mapping[str, Any]) -> None:
        if self.journal is None or getattr(self, "_resuming", False):
            return
        with self.journal.open("a", encoding="utf-8") as out:
            out.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
            out.flush()

    def _resume(self) -> None:
        """Make again every change the journal says was admitted. A proposal
        with no verdict after it was never decided: it is not made."""
        entries = []
        for line in self.journal.read_text(encoding="utf-8").splitlines():  # type: ignore[union-attr]
            try:
                entries.append(json.loads(line))
            except ValueError:
                break  # a line cut off mid-write is where the journal ends
        self._resuming = True
        try:
            pending: "Mapping[str, Any] | None" = None
            for entry in entries:
                if entry.get("state") == "proposed":
                    pending = entry
                elif entry.get("state") == "refused":
                    pending = None
                elif entry.get("state") == "admitted" and entry.get("op") == "end":
                    self.end(Admission(True, self.version, main=entry["main"]))
                elif entry.get("state") == "admitted" and pending is not None:
                    op, text, by = pending["op"], pending["text"], pending.get("by", "")
                    if op == "withdraw":
                        word, _, name = text.partition(" ")
                        got = self.withdraw(word, name, by=by)
                    elif op == "change":
                        got = self.change(text, by=by)
                    else:  # a proposal, or a cell as it was written to the tree
                        main = blocks_of(text)[-1][1] if op == "cell" else ""
                        got = self._decide(op, text, by, lambda tree, t=text, m=main: self._add(tree, t, m))
                    if not got.admitted or got.version != entry["version"]:
                        raise ValueError(
                            f"the journal says this change was admitted as {entry['version']}, and "
                            f"made again it is {got.version if got.admitted else 'refused'}: the "
                            f"workspace or the checker is not the one the journal was written with."
                        )
                    pending = None
        finally:
            self._resuming = False


def _statements(text: str) -> str:
    """What is left of a cell's text once the blocks it defines are taken out:
    the statements to carry out."""
    kept: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.strip() and not line.startswith((" ", "\t")):
            inside = line.split(" ")[0] in A_CELL_MAY_DEFINE or line.startswith("#")
        if not inside:
            kept.append(line)
    return "\n".join(kept).strip("\n")


def _remove(tree: Path, word: str, name: str) -> bool:
    """Take `<word> <name>` out of a tree, wherever it is written: a block of
    a `.pact` file, or its own file or folder."""
    found = False
    for path in sorted(p for p in tree.glob("*.pact") if p.is_file()):
        blocks = blocks_of(path.read_text(encoding="utf-8"))
        kept = [b for w, n, b in blocks if not (n == name and COLLECTION.get(w, w) == COLLECTION.get(word, word))]
        if len(kept) != len(blocks):
            found = True
            if kept:
                path.write_text("\n".join(kept), encoding="utf-8")
            else:
                path.unlink()
    folder = tree / COLLECTION.get(word, word + "s")
    for where in (folder / name, folder / f"{name}.yaml", folder / f"{name}.yml", folder / f"{name}.md"):
        if where.is_dir():
            shutil.rmtree(where)
            found = True
        elif where.exists():
            where.unlink()
            found = True
    return found


def _within(
    document: Mapping[str, Any], before: Mapping[str, Any], by: str, main: str,
    helpers: list[str], allowed: set[str],
) -> "tuple[str, str] | None":
    """Whether what a cell defined is within what its writer was given."""
    mine = [k for k in (document.get("workflows") or {}) if k == main or k in helpers
            or any(k.startswith(f"{h}-") for h in helpers)]
    for flow in mine:
        for target in _calls((document["workflows"][flow]).get("steps")):
            if target not in allowed and target not in mine and not any(
                target.startswith(f"{h}-") for h in helpers
            ):
                return ("reach", f"This cell calls '{target}', which {by} was not given. It may call: "
                        f"{', '.join(sorted(allowed)) or 'nothing'}.")
    writer = (before.get("agents") or {}).get(by) or {}
    for key, helper in (document.get("agents") or {}).items():
        if key in (before.get("agents") or {}):
            continue
        extra = set(helper) - A_HELPER_MAY_WRITE
        if extra:
            return ("wider", f"The helper '{key}' writes {', '.join(sorted(extra))}. A helper a run "
                    f"defines may say what it is told, what it takes and gives, and no more than "
                    f"its writer may do; it has no {sorted(extra)[0]} of its own.")
        more = set(helper.get("uses") or ()) - set(writer.get("uses") or ())
        if more:
            return ("wider", f"The helper '{key}' uses {', '.join(sorted(more))}, which {by} does not. "
                    f"A helper is never given more than whoever defined it has.")
        for limit, most in (writer.get("limits") or {}).items():
            if isinstance(most, (int, float)) and not isinstance(most, bool):
                asks = (helper.get("limits") or {}).get(limit)
                if asks is None or (isinstance(asks, (int, float)) and asks > most):
                    return ("wider", f"The helper '{key}' may run past `{limit}: {most}`, which is "
                            f"what {by} has. Write that limit on the helper, at {most} or less.")
        if "{{" in str(helper.get("instructions") or ""):
            return ("wider", f"The helper '{key}' has a template mark in what it is told. Words a "
                    f"run writes are words: write them out.")
    return None
