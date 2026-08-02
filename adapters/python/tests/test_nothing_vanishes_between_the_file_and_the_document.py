"""AC-7.1 — a fuzzer proving no semantic element vanishes without a report.

The criterion, and the defect class this whole repository keeps producing: an
author writes a line, it loads, it validates, and **nothing downstream ever sees
it**. `remembers:`, `answers-with:`, `run-inputs:`, `variants:` — four of them,
each found by hand, each after shipping.

Found by hand is the problem. This asserts the property instead, over mutations
of the real worked example:

* **Property A — what is written arrives.** Every key an author writes appears in
  what `pact show` emits. A loader that parses a field and drops it is the
  `answers-with:` defect at its source.
* **Property B — what is not understood is refused, never dropped.** Insert a
  key the schema does not know and it must either be REFUSED by name or arrive
  in the document. A tree that loads cleanly carrying a key nobody read is how
  an author comes to believe a rule is holding.

**Which of these has a demonstrated mutation, and which does not.** Property A
fires: making `Node::to_json` skip `because:` — one silent drop of a key the
example really writes — turns it red by name. Property B does not have one, and
the reason is worth stating rather than leaving as a gap: the shape it guards
against is *accepted AND dropped*, and no single edit to this loader produces it,
because `show` runs the same validation `check` does. Disabling the unknown-field
refusal makes both accept the key and both emit it, which is Property B passing
honestly. B is guarding a door that is currently shut by construction — it earns
its place by being the only one that can see a key the tree does not contain, and
by failing the day some derivation step starts stripping fields.
* **Property C — a value change reaches the document.** Change what a key says
  and the new value must appear. A field read into a variable nothing forwards
  looks identical to one that works, right up to the run.

**Seeded, not random.** A fuzzer whose failures cannot be reproduced is a
flake generator: `SEED` is fixed, every case prints the mutation that produced
it, and re-running gives the same set. Raising `ROUNDS` explores more without
changing what the existing cases do.

**The re-dump guard.** Mutations are applied by loading YAML, editing the tree
and writing it back, which loses comments and normalises scalars — `yes` becomes
`true`. So each file's UNMUTATED re-dump is checked first, and a file whose
round-trip the loader would refuse for reasons of its own is skipped rather than
counted as a finding. Without that, this file would report the YAML library's
opinions as PACT defects.
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"

#: Fixed. See the module note — a fuzzer nobody can reproduce is noise.
SEED = 20260730
#: How many mutations each property explores. Raising this finds more without
#: changing what the cases below already cover.
ROUNDS = 30

#: Keys whose NAME is data rather than schema — a map keyed by things the author
#: invented, where an unrecognised key is the author naming a new one rather than
#: misspelling an old one. Renaming one of these is not expected to be refused.
AUTHOR_NAMED: frozenset[str] = frozenset({
    "agents", "tools", "skills", "loops", "policies", "questions", "resources",
    "context-policies", "interceptors", "ports", "team", "shares", "remembers",
    "cases", "models", "settings", "answers-with", "accepts", "run-inputs",
    "steps", "then", "metrics", "answer", "execution", "reflection",
})


def _check(root: Path) -> tuple[bool, str]:
    out = subprocess.run(
        [str(PACT_BIN), "check", str(root)], capture_output=True, text=True
    )
    return out.returncode == 0, out.stdout + out.stderr


def _show(root: Path) -> dict[str, Any]:
    out = subprocess.run(
        [str(PACT_BIN), "show", str(root)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


def _every_key(node: Any, out: set[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            out.add(str(k))
            _every_key(v, out)
    elif isinstance(node, list):
        for v in node:
            _every_key(v, out)


def _paths(node: Any, here: tuple = ()) -> list[tuple]:
    """Every `(key, ...)` path to a mapping key in a parsed document."""
    found: list[tuple] = []
    if isinstance(node, dict):
        for k, v in node.items():
            found.append(here + (k,))
            found.extend(_paths(v, here + (k,)))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            found.extend(_paths(v, here + (i,)))
    return found


def _at(node: Any, path: tuple) -> Any:
    for step in path:
        node = node[step]
    return node


def _yaml_files() -> list[Path]:
    return sorted(
        p for p in EXAMPLE.rglob("*.yaml") if ".pact" not in p.relative_to(EXAMPLE).parts
    )


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """The shipped example, copied, with its derived area left behind."""
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    root = tmp_path / "refund-desk"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns(".pact"))
    return root


def _redump_survives(root: Path, rel: Path) -> bool:
    """Is this file's own YAML round-trip something the loader still accepts?

    See the module note. `yes` becomes `true` on the way through, so a file that
    fails here fails for the YAML library's reasons and not PACT's.
    """
    p = root / rel
    keep = p.read_text()
    p.write_text(yaml.safe_dump(yaml.safe_load(keep), sort_keys=False))
    ok, _ = _check(root)
    p.write_text(keep)
    return ok


# ─────────────────────────────── A: what is written arrives


def test_every_key_the_author_wrote_appears_in_the_document(tree: Path) -> None:
    """No mutation needed for this one — it is the property at rest.

    145 keys across 43 files, and every one has to survive to what a runtime
    receives. A key that parses and does not arrive is `answers-with:`, which was
    `tier: core`, in this very example, and read by nothing for a session.
    """
    authored: set[str] = set()
    for f in _yaml_files():
        _every_key(yaml.safe_load(f.read_text()), authored)
    emitted: set[str] = set()
    _every_key(_show(tree), emitted)

    lost = sorted(k for k in authored if k not in emitted)
    assert not lost, (
        f"{len(lost)} key(s) written in the tree and absent from `pact show`: "
        f"{lost}\nA key that loads and does not arrive is a line the author "
        f"believes is holding."
    )
    assert len(authored) > 100, f"only {len(authored)} keys — did the walk work?"


# ─────────────────────── B: what is not understood is refused, not dropped


def test_a_key_the_schema_does_not_know_is_always_refused(tree: Path) -> None:
    """The fuzzer proper.

    A key no schema knows is INSERTED beside an existing one, at a random place
    in a random file. Two outcomes are acceptable and a third is the defect:
    `pact check` refuses it by name (correct), or it survives into `pact show`
    where a reader can see it (nothing was lost). **Accepted and gone** is what
    must never happen.

    Today the first outcome is what happens every time, because `show` runs the
    same validation `check` does — so a refused tree produces no document at all.
    An earlier note here claimed the key was "accepted by check and dropped by
    show"; that was a misreading of an empty stdout from a command that had
    exited 1.

    *Inserted, not renamed.* The first version renamed an existing key, and
    almost every rename produced *"a workspace must have a 'name'"* — a refusal
    for a different reason, which passed through the `else` branch below without
    ever reaching the question this test is about. Measured: disabling the
    loader's whole unknown-field refusal left it green. An insertion cannot
    remove a required field, so it always lands where it means to.
    """
    rng = random.Random(SEED)
    files = [f for f in _yaml_files() if _redump_survives(tree, f.relative_to(EXAMPLE))]
    assert files, "no file survives its own YAML round-trip — the guard is wrong"

    checked = 0
    for n in range(ROUNDS):
        src = rng.choice(files)
        rel = src.relative_to(EXAMPLE)
        doc = yaml.safe_load((tree / rel).read_text())
        # Any mapping in the file, including the top one. A key added under an
        # author-named map is the author naming a new thing rather than
        # misspelling a known one, so those are left alone.
        spots = [()] + [
            p for p in _paths(doc)
            if isinstance(_at(doc, p), dict)
            and not (isinstance(p[-1], str) and p[-1] in AUTHOR_NAMED)
        ]
        if not spots:
            continue
        where = rng.choice(spots)
        added = f"zz-fuzz-{n}"
        keep = (tree / rel).read_text()
        try:
            target = _at(doc, where) if where else doc
            if not isinstance(target, dict):
                continue
            target[added] = "a value no schema asked for"
            (tree / rel).write_text(yaml.safe_dump(doc, sort_keys=False))

            ok, said = _check(tree)
            checked += 1
            if ok:
                emitted: set[str] = set()
                _every_key(_show(tree), emitted)
                assert added in emitted, (
                    f"`{added}` was inserted at {where or '<top>'} in {rel}, "
                    f"accepted by `pact check`, and does not appear in "
                    f"`pact show`.\nIt vanished between the file and the "
                    f"document with nothing said — which is the defect AC-7.1 "
                    f"is about.\nseed={SEED} round={n}"
                )
            else:
                assert added in said, (
                    f"the tree was refused and the message does not name "
                    f"`{added}`, so an author cannot act on it:\n{said}\n"
                    f"seed={SEED} round={n}"
                )
        finally:
            (tree / rel).write_text(keep)

    assert checked >= 10, f"only {checked} mutations landed — too few to mean anything"


# ─────────────────────────── C: a changed value reaches the document


def test_a_value_the_author_changes_reaches_the_document(tree: Path) -> None:
    """A field read into a variable that nothing forwards looks exactly like one
    that works. This changes what a key SAYS and asserts the new words arrive."""
    rng = random.Random(SEED + 1)
    files = [f for f in _yaml_files() if _redump_survives(tree, f.relative_to(EXAMPLE))]

    checked = 0
    for _ in range(ROUNDS):
        src = rng.choice(files)
        rel = src.relative_to(EXAMPLE)
        doc = yaml.safe_load((tree / rel).read_text())
        # Only prose values: changing a number or an enum produces a refusal,
        # which is a different property and is covered above.
        candidates = [
            p for p in _paths(doc)
            if isinstance(_at(doc, p), str) and len(_at(doc, p)) > 12
            and isinstance(p[-1], str) and p[-1] not in ("based-on", "loop", "policy")
        ]
        if not candidates:
            continue
        path = rng.choice(candidates)
        keep = (tree / rel).read_text()
        try:
            marker = f"zzmarker{checked}"
            parent = _at(doc, path[:-1]) if len(path) > 1 else doc
            parent[path[-1]] = f"{_at(doc, path)} {marker}"
            (tree / rel).write_text(yaml.safe_dump(doc, sort_keys=False))

            ok, said = _check(tree)
            if not ok:
                continue          # a value this field will not take; not a loss
            checked += 1
            assert marker in json.dumps(_show(tree)), (
                f"the value of `{'.'.join(str(s) for s in path)}` in {rel} was "
                f"changed and the change does not appear in `pact show`.\n"
                f"The key arrives and its value does not, which is worse than "
                f"losing both — the document looks complete.\n"
                f"seed={SEED + 1} path={path}"
            )
        finally:
            (tree / rel).write_text(keep)

    assert checked >= 5, f"only {checked} value mutations landed — too few"
