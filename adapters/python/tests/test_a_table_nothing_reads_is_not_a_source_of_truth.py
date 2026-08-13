"""Every public table in `src/` is read by something.

`test_nothing_public_is_named_by_nothing.py` asks this question of module-level
**functions** — it walks `ast.FunctionDef` and nothing else, and its own
docstring is careful to say why methods are out of scope. Module-level
CONSTANTS were never in scope at all, and that is the whole reason this file
exists: `egress.ROLES` sat in `src/` for a round as a six-word tuple naming the
model roles `allow-egress:` accepts, was read by no module and no test, and went
stale — the word `tools` had been added to the schema's own `choices:` and the
tuple did not move. Every check in the suite stayed green, because nothing was
looking. A vocabulary table nothing opens is a second copy of the specification
with no gate depending on it, which is the shape that rots quietly.

The measurement, taken before the deletion — there is no such line to grep for
now, and it is transcribed here rather than cited so nobody goes looking:

```text
$ grep -rn '\\bROLES\\b' adapters/python          # while it still existed
adapters/python/src/pact_adapters/egress.py:ROLES: tuple[str, ...] = (...)
```

One hit: its own definition. Nothing else in the port, nothing in the suite.

The Rust half of that same rule keeps no copy: `crates/pact-cli/src/egress.rs`
reads the roles off `pact_schema::Group` (`fn plays`). So the fix was to delete
the tuple rather than add the missing word, and this file is what stops the next
one being written.

It found a second on its first run: `harness.ANSWER_MODES`, the four spellings
of `answers-with-mode:`, also a copy of a `choices:` list in `spec/schema.yaml`
and also read by nothing. Its two neighbours — `CHOSEN_ANSWER_MODE` and
`MODES_NOTHING_HERE_DELIVERS` — decide what a run actually does and are read by
`run()`; the table of all four decided nothing. Its TypeScript twin
(`adapters/typescript/src/harness.ts`) was deleted in the same round and by
hand: this walk reads Python only, so the second port is unguarded and the note
left in its place says so.

**What counts as read is `src/` only**, the same rule the sibling file uses, and
for the same reason it states: being tested is not being reached. A test that
pins a table's contents can keep a dead table alive forever, so the three
registers whose one honest consumer *is* an auditing test are named in
`AUDITED` below with the sentence saying why — a decision somebody wrote down,
not a silence.

Mutation: put `ROLES = ("llm", "stt", "tts", "embedder", "judge", "reflector")`
back into `egress.py`. Without this file the entire suite stays green — that is
the measured fact this file was written from — and with it,
`test_no_public_table_is_read_by_nothing` names `egress.ROLES` and says what to
do about it.

Second mutation, and the one that matters more, because the first only exercises
the easy path — a dead table whose NAME is unique. Append
`LABELS = ("dead", "table")` to `slo.py`: nothing anywhere reads it, but
`context_policy.py` loads a `LABELS` of its own. The first version of this file
collected bare names into one flat set and passed — `6 passed`, measured — so a
dead table was invisible whenever any unrelated module happened to spell a live
one the same way, and six constant names in this package are already duplicated
across modules. `_read` now resolves every read to the module that wrote the
table, and the mutation is reported as `slo.LABELS`.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "pact_adapters"

#: A CONSTANT, and this is the definition: module level, and spelt the way this
#: codebase spells a thing that does not change. A lower-case module global is
#: mutable state or a configured object, which is a different question with a
#: different answer, and `_`-prefixed names are the owning module's own business.
CONSTANT = re.compile(r"^[A-Z][A-Z0-9_]*$")

#: Tables whose one reader is a test that audits them, each with the reason the
#: source is right not to read it.
#:
#: A row here is a DECISION and may only be added with a sentence. The bar is
#: that the test which reads it FAILS THE BUILD when the table is wrong — an
#: assertion that merely restates the table's contents is not a consumer, it is
#: the table written twice. `test_no_audited_table_has_gained_a_reader` deletes
#: the row again when the source starts reading it, because a list of what must
#: stay unread cannot notice a fix.
AUDITED: dict[str, str] = {
    "harness.DERIVED_FROM_THE_DOCUMENT": (
        "half of the register that makes `run()`'s parameter list total. Its "
        "consumer is `test_the_boundary_between_a_document_and_a_run_is_"
        "declared`, which fails when a parameter appears in neither this map "
        "nor `SUPPLIED_BY_THE_HOST` — so a mechanism cannot ship with no "
        "authored source without somebody writing that down. The register is "
        "the claim; the run itself has no use for it"
    ),
    "harness.SUPPLIED_BY_THE_HOST": (
        "the other half of the same register: the parameters no document "
        "describes, because they are facts about the process rather than about "
        "the agent. Same consumer, same failure, same reason the run does not "
        "read it — a name here says nothing happens, and nothing happening "
        "needs no code"
    ),
    "interceptors.REDIRECTS_AT": (
        "derived from `WIRED`, so it cannot drift from it. The run does not "
        "consult it — `_carries(when, 'somewhere_else')` asks `WIRED` "
        "directly — and its reader is the §7.10 enumeration in "
        "`test_events_and_interceptors`, which pins the answer to exactly one "
        "address and goes red when a moment is marked `somewhere_else` "
        "without anybody deciding it may send a run elsewhere"
    ),
}


def _modules() -> dict[str, ast.Module]:
    """`{dotted module name: its parsed tree}` for every file in `src/`.

    Dotted and relative to the package, so `transports/a2a_transport.py` is
    `transports.a2a_transport` and cannot be confused with a top-level module of
    the same stem.
    """
    found: dict[str, ast.Module] = {}
    for path in sorted(SRC.rglob("*.py")):
        name = ".".join(path.relative_to(SRC).with_suffix("").parts)
        found[name] = ast.parse(path.read_text())
    return found


def _package_of(module: str, level: int) -> list[str]:
    """The package `from .` means, written from inside `module`.

    `from . import x` in `transports/a2a_transport.py` is `transports.x`; the
    same line in `harness.py` is `x`. Getting this wrong is how a per-module
    check quietly becomes the bare-name one it replaced.
    """
    parts = module.split(".")[:-1]
    drop = level - 1
    return parts[: len(parts) - drop] if drop else parts


def _tables(trees: dict[str, ast.Module] | None = None) -> set[str]:
    """`{module.NAME}` for every module-level public constant in `src/`."""
    found: set[str] = set()
    for module, tree in (trees or _modules()).items():
        for node in tree.body:
            named: list[str] = []
            if isinstance(node, ast.Assign):
                named = [t.id for t in node.targets if isinstance(t, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                named = [node.target.id]
            found.update(f"{module}.{name}" for name in named if CONSTANT.match(name))
    return found


def _read(trees: dict[str, ast.Module] | None = None) -> set[str]:
    """Every constant `src/` READS, by `module.NAME` — as opposed to writes.

    **Qualified, and that is the whole of what this walk has to get right.** The
    first version of this file collected bare names into one flat set, and a
    dead table was invisible whenever any unrelated module happened to load a
    name spelt the same. Six constant names are already duplicated across this
    package — `USAGE` in six modules, `SAYS`, `UNDER`, `LIBRARY`,
    `NEEDS_PERMISSION`, `NEEDS_APPROVAL` in two each — so the hole was live and
    not hypothetical, and it was demonstrated with a table nothing anywhere
    reads (see the second mutation in the module docstring).

    What counts as reading `egress.WORDS`, in the three shapes this package
    writes:

    * a bare load inside `egress.py` itself — `if role in WORDS`;
    * `from .egress import WORDS` anywhere, which is a use by itself: the name
      is on somebody else's line and moving it breaks their import;
    * `_egress.WORDS`, where `_egress` is a module this file imported. The
      attribute is resolved through that import rather than by its spelling, so
      `entry.WORDS` on some unrelated object is not mistaken for it.

    Deliberately over-broad in one direction only, the same as the sibling file:
    a table merely handed somewhere is a table used. The one thing that never
    counts is the assignment that creates it — `ast.Store` — which is the entire
    difference between a table with a reader and a table with none.
    """
    trees = trees or _modules()
    known = set(trees)
    seen: set[str] = set()

    for module, tree in trees.items():
        # Local alias → the module it names, and local alias → a constant
        # imported by name. Both are needed before the walk, because a bare
        # `WORDS` means a different table depending on which one it came from.
        as_module: dict[str, str] = {}
        as_constant: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                where = _package_of(module, node.level or 0) if node.level else []
                prefix = ".".join([*where, *(node.module.split(".") if node.module else [])])
                for alias in node.names:
                    target = f"{prefix}.{alias.name}" if prefix else alias.name
                    if target in known:
                        as_module[alias.asname or alias.name] = target
                    elif prefix in known and CONSTANT.match(alias.name):
                        as_constant[alias.asname or alias.name] = target
                        seen.add(target)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    inside = alias.name.removeprefix("pact_adapters.")
                    if inside in known:
                        as_module[alias.asname or alias.name] = inside

        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if not CONSTANT.match(node.id):
                    continue
                seen.add(as_constant.get(node.id, f"{module}.{node.id}"))
            elif isinstance(node, ast.Attribute) and CONSTANT.match(node.attr):
                if isinstance(node.value, ast.Name) and node.value.id in as_module:
                    seen.add(f"{as_module[node.value.id]}.{node.attr}")
    return seen


def test_no_public_table_is_read_by_nothing() -> None:
    """The check itself.

    A table nothing opens is either dead — delete it — or a rule that shipped
    inert. Both are worse than they look, because a list of the format's own
    words reads as documentation and a reader believes it.
    """
    trees = _modules()
    read = _read(trees)
    orphans = sorted(
        name for name in _tables(trees) if name not in read and name not in AUDITED
    )
    assert not orphans, (
        "public table(s) nothing in `src/` reads:\n  "
        + "\n  ".join(orphans)
        + "\n\nEach is either dead — delete it, and let whichever file already "
        "decides the thing keep deciding it — or a rule that shipped inert, in "
        "which case wire it to the check it was written for. If its one honest "
        "reader is a test that audits it, add it to AUDITED with the sentence "
        "saying why the source is right not to read it."
    )


def test_the_check_is_looking_at_something() -> None:
    """A walk that finds no tables passes everything above.

    The sibling file records resolving `SRC` one directory too high and finding
    nothing at all — a green suite asserting nothing, which is the failure this
    whole class of test exists to catch, one level up.
    """
    tables = _tables()
    assert len(tables) > 100, f"only found {len(tables)} public tables"
    assert "egress.WORDS" in tables, sorted(tables)[:20]
    read = _read()
    assert len(read) > 100, len(read)
    # And the qualifying resolves, rather than every read landing in the module
    # that wrote it. `egress.AUDIO_SPELLINGS` is only ever reached from inside
    # `egress.py`; `judge.LOCAL_RUNTIME` is reached from `evals.py` through an
    # `_judge.` attribute, which is the shape that needs an import resolved.
    assert {"egress.AUDIO_SPELLINGS", "judge.LOCAL_RUNTIME"} <= read, sorted(read)[:20]


@pytest.mark.parametrize("name", sorted(AUDITED))
def test_no_audited_table_has_gained_a_reader(name: str) -> None:
    """The other direction, without which `AUDITED` only ever grows."""
    assert name in _tables(), (
        f"AUDITED names `{name}`, which is not a public module-level constant "
        f"in `src/` — delete the row"
    )
    assert name not in _read(), (
        f"`{name}` is excused as a register only a test reads, and something in "
        f"`src/` now reads it. Delete the AUDITED row: it is reached."
    )


def test_every_audited_table_says_why() -> None:
    """A row whose reason is a shrug is a row nobody can weigh."""
    thin = sorted(k for k, why in AUDITED.items() if len(why.split()) < 15)
    assert not thin, f"{thin} are excused without a reason anybody can check"
