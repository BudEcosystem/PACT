"""Every public function in `src/` is named by something in `src/`.

The cheap half of the reachability question, and the half that actually caught
things. `test_a_reader_is_reachable_from_a_run.py` answers the hard question —
*is this reachable from an entry point* — by walking a call graph, and that walk
is **imprecise in the safe direction**: it cannot see through a module alias
(`_egress.grants`), a default argument (`measure: Measure = estimate`), a dict
of handlers (`READERS[kind](artifact)`) or duck-typed dispatch. Twenty-two live
functions currently read as dead there, and a list of twenty-two declared
exceptions saying *"the tool is imprecise here"* would rot on contact.

This asks a question the source answers exactly: **does any file in `src/` so
much as mention this name?** No graph, no types, no inference — a name that
appears nowhere but its own `def` is called by nothing, and no amount of
imprecision changes that.

It is worth its own file because it found three:

* `harness.delegate_by_running` — scoring ran every eval case with no
  `ask_member`, so a team agent's delegations parked and each case scored as
  "did not answer".
* `optimising.measured` — AC-3.5's *"by a declared margin"*, computed and shown
  to nobody.
* `providers.coverage` — AC-4.1's *published* matrix, published nowhere.

Each had a full test file of its own and passed every assertion in it. Being
tested is not being reached, and that is the defect this repository is written
against.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "pact_adapters"

#: Public functions deliberately called by nothing here, each with the reason.
#:
#: A name in this map is a DECISION. It may only be added with a sentence saying
#: why the source is right not to call it, and `test_no_declared_exception_has
#: _gained_a_caller` deletes it again when one appears — a list of what must stay
#: uncalled cannot notice a fix.
HOST_API: dict[str, str] = {
    "interceptors.guard": (
        "the typed escape hatch §5.5 requires every mechanism to have. A host "
        "embedding the harness expresses a condition the sentence vocabulary "
        "does not yet carry, in its own process — and its own docstring says "
        "**not an authoring path**. Nothing in `src/` calls it because nothing "
        "in `src/` is a host; `Chain.from_document` is what an author reaches, "
        "and it takes no code. A public function with no internal caller is "
        "normally dead, and this is the one shape where it is the point"
    ),
}


def _names_in(tree: ast.Module) -> set[str]:
    """Every identifier this file mentions in a way that could reach a function.

    Deliberately over-broad. A bare `ast.Name` counts, because a function handed
    somewhere without being called — a default argument, a dict of handlers, a
    callback — is used. So does an aliased import: `from .providers import
    coverage as metric_coverage` is what wires the metric matrix into the
    conformance report, and a checker that missed it would have reported a
    freshly-wired mechanism as dead. It did, on its first run.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                found.add(alias.name)
    return found


def _public_functions() -> dict[str, str]:
    """`{bare name: qualified}` for every module-level public `def` in `src/`.

    Module-level only. A method's name is shared across classes and reached
    through a receiver this cannot type, so asking the same question of methods
    would answer it wrongly — which is the failure this file exists to avoid
    repeating.
    """
    found: dict[str, str] = {}
    for path in sorted(SRC.rglob("*.py")):
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    found[node.name] = f"{path.stem}.{node.name}"
    return found


def _mentioned() -> set[str]:
    seen: set[str] = set()
    for path in sorted(SRC.rglob("*.py")):
        seen |= _names_in(ast.parse(path.read_text()))
    return seen


def test_no_public_function_is_named_by_nothing() -> None:
    """The check itself.

    A function nothing names is either dead — delete it — or a mechanism that
    shipped inert, which is worse, because it looks finished and its tests pass.
    """
    functions = _public_functions()
    named = _mentioned()
    orphans = sorted(
        q for name, q in functions.items()
        if name not in named and q not in HOST_API
    )
    assert not orphans, (
        "public function(s) nothing in `src/` names:\n  "
        + "\n  ".join(orphans)
        + "\n\nEach is either dead — delete it — or a mechanism that shipped "
        "inert. Wire it to something an author can type, or add it to HOST_API "
        "with the reason the source is right not to call it."
    )


def test_the_check_is_looking_at_something() -> None:
    """A walk over an empty tree passes everything above.

    The first version of this file resolved `SRC` one directory too high and
    found no functions at all, which is a green suite asserting nothing — the
    exact failure mode it was written to catch, one level up.
    """
    functions = _public_functions()
    assert len(functions) > 80, f"only found {len(functions)} public functions"
    assert "run_pipeline" in functions, sorted(functions)[:20]
    assert len(_mentioned()) > 400, len(_mentioned())


@pytest.mark.parametrize("name", sorted(HOST_API))
def test_no_declared_exception_has_gained_a_caller(name: str) -> None:
    """The other direction, without which HOST_API only ever grows.

    A list of what must stay uncalled cannot notice a fix. If something starts
    calling `guard`, the row is now describing a state that ended, and a register
    that can be wrong about its own subject is what this repository has most of.
    """
    bare = name.split(".")[-1]
    assert bare in {n for n in _public_functions()}, (
        f"HOST_API names `{name}`, which is not a public function in `src/` — "
        f"delete the row"
    )
    assert bare not in _mentioned(), (
        f"`{name}` is excused as a host-only entry point and something in "
        f"`src/` now names it. Delete the HOST_API row: it is reached."
    )


def test_every_declared_exception_says_why() -> None:
    """A row whose reason is a shrug is a row nobody can check."""
    thin = sorted(k for k, why in HOST_API.items() if len(why.split()) < 15)
    assert not thin, f"{thin} are excused without a reason anybody can weigh"
