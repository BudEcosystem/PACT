"""A reader that nothing calls is not a reader (Phase 1.3).

`test_every_field_has_a_reader.py` asks whether a field name appears in the
source. That is necessary and not sufficient, and this repository has the proof:
`remembers:` **is** mentioned — in `facts.py`, by `Facts.from_document`, which
**nothing calls**. The grep saw a reader and passed while the mechanism was
entirely inert.

Mention is not reachability. This file walks the call graph from the three real
entry points — `harness.run`, `scoring.main`, `scoring.score` — and asks whether
each reader can actually be got to. It is the check that would have caught G9 on
the day it landed, and it is deliberately a *separate* file from the mention
check so that neither can quietly weaken the other.

Names are qualified (`module.function`) rather than bare, because the bare form
collides: `resolve` is `Loop.resolve`, `ContextPolicy.resolve` **and** the
model-selection `resolve.resolve`, and only the last one is unreachable. A check
that cannot tell them apart reports the wrong answer confidently.
"""

from __future__ import annotations

import ast
import sys
from collections import defaultdict
from pathlib import Path

import pytest

BARE = "<a bare call, not an attribute>"
UNKNOWN = "<a receiver this walk cannot name>"

REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "adapters/python/src/pact_adapters"

#: Where a run can actually begin. Everything a document declares must be
#: reachable from one of these, or it is inert however well it is tested.
#:
#: A previous version listed `evals.main`, which **does not exist**. `python -m
#: pact_adapters.evals` imports `scoring.main` under its `__main__` guard, so the
#: name contributed no edges and the walk was one entry point smaller than it
#: read as. Nothing complained, because a missing key in a `defaultdict` is a
#: normal Tuesday — which is the same shape as the defect this file exists for,
#: one level up again. `test_every_entry_point_exists` is the fix.
ENTRIES = {
    "harness.run",
    "scoring.main",
    "scoring.score",
    "scoring.propose",
    # EVERY DOOR'S `main`, and leaving them out was a hole exactly the shape of
    # the thing this file exists to catch. `pyproject.toml` installs each of
    # these as a console script, so a person types them — they are entry points
    # by the same definition `scoring.main` is one.
    #
    # Without them the walk reported `exploding.explode`, `importing.from_a2a_
    # card`, `exporting.to_bud_agent_record`, `optimising.improve_on` and
    # `pipeline.run_pipeline` as reachable from nothing, and said so to nobody:
    # `test_no_new_reader_has_become_unreachable` only looked at functions named
    # `from_document`, `of` and `for_document`, so everything else was outside
    # its reach BY CONSTRUCTION. That is the same shape as the TypeScript port
    # having no producer, and it was found by mutating the callers out of a
    # newly-wired mechanism and watching this file stay green.
    "conformance.main",
    "pipeline.main",
    "exploding.main",
    "importing.main",
    "exporting.main",
    "optimising.main",
}


def _declarations() -> tuple[
    dict[str, str], dict[str, str], dict[tuple[str, str], str], dict[str, set[str]]
]:
    """First pass: `{class: module}`, `{qualified function: class it returns}`,
    `{(class, field): class}`, `{bare name: {qualified}}`.

    Every one of these comes from an **annotation the source already wrote** —
    `def from_document(...) -> "Learner"`, `slo: Slo = field(...)` — never from a
    name that looks like a type. That distinction is the whole reason this is
    sound: guessing that `X.from_document()` returns an `X` would add edges on a
    hunch, and a wrong extra edge makes dead code look live, which is the one
    direction this file must never fail in.
    """
    owner: dict[str, str] = {}
    returns: dict[str, str] = {}
    fields: dict[tuple[str, str], str] = {}
    where: dict[str, set[str]] = defaultdict(set)

    for path in sorted(SRC.rglob("*.py")):
        mod = path.stem
        tree = ast.parse(path.read_text(errors="ignore"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                owner[node.name] = mod
                # `spec.slo.assess(...)` is only resolvable because `AgentSpec`
                # declares `slo: Slo`. Without this the walk could not see a
                # single `self.something.method()` call, and the package is full
                # of them — it reported `slo.assess` dead while `scoring.score`
                # called it.
                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        named = _annotated(item.annotation)
                        if named:
                            fields[(node.name, item.target.id)] = named
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                where[node.name].add(f"{mod}.{node.name}")
                named = _annotated(node.returns)
                if named:
                    returns[f"{mod}.{node.name}"] = named
    return owner, returns, fields, where


def _annotated(node: ast.AST | None) -> str:
    """The bare class name an annotation names, if it names exactly one.

    `-> "Learner"`, `-> Learner` and `-> "Learner | None"` all give `Learner`;
    `-> tuple[...]`, `-> dict[...]` and anything else give nothing. Narrow on
    purpose — an annotation this cannot read contributes no binding, which loses
    an edge rather than inventing one.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        text = node.value.replace('"', "").replace("'", "").strip()
        parts = [p.strip() for p in text.split("|") if p.strip() and p.strip() != "None"]
        return parts[0] if len(parts) == 1 and parts[0].isidentifier() else ""
    if isinstance(node, ast.Name):
        return node.id
    return ""


def graph() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """`{qualified caller: {qualified callees}}`, plus `{bare name: {qualified}}`.

    **Calls are resolved through their receiver**, which is the whole difficulty.
    A bare-name graph reports `facts.from_document` as reachable the moment
    *any* `from_document` is called anywhere — and six classes define one. The
    first version of this file did exactly that and passed while G9 was inert,
    which is the same failure it exists to catch, one level up.

    So `Chain.from_document(...)` is resolved by finding the module that defines
    `class Chain`, and **a local variable is resolved through the declared return
    type of whatever built it**: `learner = Learner.from_document(...)` makes
    `learner.cycle()` an edge to `learning.cycle`, because `from_document` is
    annotated `-> "Learner"`.

    **And an attribute chain is resolved through declared field types.**
    `spec.slo.assess(...)` is an edge to `slo.assess` because `AgentSpec` declares
    `slo: Slo`; `self.facts.record(...)` is one because the enclosing class
    declares `facts: Facts`. Without this the walk could not see a single
    `self.x.y()` call — and it reported `slo.assess` dead while `scoring.score`
    called it.

    Each of these rules was absent for a round and cost a correct answer.
    A receiver that still cannot be named contributes **no edge**:
    under-approximating is the safe direction, because this check can then miss a
    live caller and wrongly report something dead, which somebody notices, rather
    than miss a dead reader and report it live, which is the failure it exists to
    prevent.
    """
    owner, returns, fields, where = _declarations()
    calls: dict[str, set[str]] = defaultdict(set)

    def type_of(node: ast.AST, local: dict[str, str]) -> str:
        """The class a value is declared to have, or `""`.

        `local` maps a name to a class — including `self`, seeded when walking
        into a method — and `fields` walks one link further down an attribute
        chain. Only declarations are followed; anything else yields `""`.
        """
        if isinstance(node, ast.Name):
            named = local.get(node.id, "")
            return named or (node.id if node.id in owner else "")
        if isinstance(node, ast.Attribute):
            return fields.get((type_of(node.value, local), node.attr), "")
        if isinstance(node, ast.BoolOp):
            # `rules = permissions or Permissions.default()`. Both sides are
            # `Permissions`, so the result is too — and this was the FIFTH thing
            # this walk could not see. It reported `Permissions.of` dead while
            # `classify` called it on the next line, and the register repeated
            # that as fact for several rounds.
            named = {type_of(v, local) for v in node.values}
            named.discard("")
            return next(iter(named)) if len(named) == 1 else ""
        if isinstance(node, ast.IfExp):
            # `x if c else y`, on the same argument.
            named = {type_of(node.body, local), type_of(node.orelse, local)}
            named.discard("")
            return next(iter(named)) if len(named) == 1 else ""
        if isinstance(node, ast.Call):
            recv, attr = callee(node.func, local)
            if recv == BARE:
                return attr if attr in owner else ""
            return returns.get(f"{owner[recv]}.{attr}", "") if recv in owner else ""
        return ""

    def callee(f: ast.AST, local: dict[str, str]) -> tuple[str, str]:
        """`(receiver-or-sentinel, attribute name)` for one call's `func`."""
        if isinstance(f, ast.Name):
            return BARE, f.id
        if isinstance(f, ast.Attribute):
            # `Path(x).resolve()` must NOT fall back to the bare name — that is
            # what made `Path(__file__).resolve()` count as a call to the
            # model-selection `resolve.resolve`.
            named = type_of(f.value, local)
            return (named or UNKNOWN), f.attr
        return UNKNOWN, ""

    def edge(holder: str, recv: str, name: str) -> None:
        if recv == BARE:
            calls[holder].update(where.get(name, set()))
        elif recv in owner:
            calls[holder].add(f"{owner[recv]}.{name}")

    for path in sorted(SRC.rglob("*.py")):
        mod = path.stem
        tree = ast.parse(path.read_text(errors="ignore"))

        def walk(
            node: ast.AST, holder: str, local: dict[str, str], cls: str = ""
        ) -> None:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # A fresh scope — one function's `learner` is not another's —
                    # except for `self`, which is whatever class encloses it, and
                    # for PARAMETERS the author annotated. That last one was
                    # missing and cost a correct answer again: `_finish(...,
                    # facts: "Facts | None")` calls `facts.something_happened()`,
                    # and this walk reported it dead while the harness called it.
                    scope: dict[str, str] = {"self": cls} if cls else {}
                    for arg in (
                        *child.args.posonlyargs, *child.args.args, *child.args.kwonlyargs
                    ):
                        named = _annotated(arg.annotation)
                        if named in owner:
                            scope[arg.arg] = named
                    walk(child, f"{mod}.{child.name}", scope, cls)
                    continue
                if isinstance(child, ast.ClassDef):
                    walk(child, holder, dict(local), child.name)
                    continue
                # Bind a local to a class BEFORE walking, so a variable assigned
                # earlier in the body resolves for the calls that follow it.
                if isinstance(child, (ast.Assign, ast.AnnAssign)):
                    target = (
                        child.targets[0] if isinstance(child, ast.Assign)
                        else child.target
                    )
                    named = (
                        _annotated(child.annotation)
                        if isinstance(child, ast.AnnAssign) else ""
                    )
                    if not named and child.value is not None:
                        # `type_of`, not a second copy of it. This branch used to
                        # inspect `ast.Call` and nothing else, so adding `BoolOp`
                        # to `type_of` changed nothing:
                        # `rules = permissions or Permissions.default()` still
                        # bound no type, and `Permissions.of` still read as dead.
                        # Two places deciding one question is how they come to
                        # disagree — the same finding as `_calls` in `scoring.py`.
                        named = type_of(child.value, local)
                    if isinstance(target, ast.Name) and named in owner:
                        local[target.id] = named
                if isinstance(child, ast.Call):
                    recv, attr = callee(child.func, local)
                    edge(holder, recv, attr)
                walk(child, holder, local, cls)

        walk(tree, f"{mod}.<module>", {}, "")
    return calls, where


def reachable() -> set[str]:
    calls, where = graph()
    seen: set[str] = set()
    stack = [e for e in ENTRIES]
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        for qualified in calls.get(node, ()):
            if qualified not in seen:
                stack.append(qualified)
    return seen


#: Readers known to be unreachable, each with the register row that tracks it.
#: This list may only shrink — `test_the_unreachable_list_only_shrinks` fails
#: when one of these gains a caller, so closing a gap forces the register to be
#: updated in the same change.
UNREACHABLE: dict[str, str] = {
    # A1 is CLOSED. `ir.py` reads `remembers:` into `AgentSpec.facts`,
    # `AgentSpec.tidier` passes them, and the harness records one when a gate
    # clears — held by
    # `test_what_the_author_wrote_reaches_the_run.py::test_a_fact_the_author_marked_survivable_reaches_the_tidier_from_the_document`,
    # mutation-tested on both links. `facts.something_happened` remains
    # unreachable: nothing yet reports a fact going stale.
    #
    # THIS MAP IS NOW EMPTY, and that is the file working rather than a
    # milestone. Its last entry said `Permissions.of` "has no per-field caller",
    # which was **false**: `classify` calls `rules.of(p.field)` one line after
    # building `rules`, and always has. This walk could not see through
    # `rules = permissions or Permissions.default()` — a `BoolOp` — so it read a
    # live caller as dead, and the register repeated that as fact.
    #
    # All five resolver gaps found so far failed the same way: a live caller read
    # as dead. That is the safe direction, chosen on purpose, and it is still
    # wrong every time. Suspect a new entry here of being the sixth before
    # believing it.
    # A2 is CLOSED — `scoring._choose` calls it behind `--choose-model`.
    # A4 is CLOSED — `scoring.score` calls `spec.slo.assess(latencies, "e2e")`,
    # so the author's `finishes-within:` produces a verdict or an honest
    # refusal to give one. It took a third strengthening of the resolver above
    # to SEE that caller, which is worth remembering: for one commit this file
    # would have reported a wired mechanism dead.
}


def test_every_entry_point_exists() -> None:
    """An entry point that is not a real function walks nowhere.

    This file's whole answer depends on `ENTRIES`, and a name in it is checked
    against nothing: `evals.main` sat here for a round and does not exist. The
    walk silently started from three places instead of four, and every
    `UNREACHABLE` assertion passed a little more easily for it.
    """
    _, where = graph()
    defined = {q for quals in where.values() for q in quals}
    missing = sorted(e for e in ENTRIES if e not in defined)
    assert not missing, (
        f"ENTRIES names {missing}, which no module defines — so the walk starts "
        f"from fewer places than it appears to, and every unreachability "
        f"assertion below is weaker than it reads."
    )


def test_the_graph_is_big_enough_to_mean_something() -> None:
    """A walk that reaches almost nothing would pass this file vacuously."""
    got = reachable()
    assert len(got) > 150, f"only {len(got)} functions reachable — the walk is broken"
    assert "harness.run" in got


@pytest.mark.parametrize("reader", sorted(UNREACHABLE))
def test_each_known_unreachable_reader_is_still_unreachable(reader: str) -> None:
    """The register's Class A, asserted rather than described.

    Parametrised so a failure names *which* one was fixed, rather than handing
    back a list.
    """
    assert reader not in reachable(), (
        f"`{reader}` is now reachable from an entry point — {UNREACHABLE[reader]}. "
        f"Remove it from UNREACHABLE and strike the row from "
        f"docs/70-PRODUCTION-GAP-REGISTER.md in this same change."
    )


def test_the_mechanisms_that_do_work_are_reachable() -> None:
    """The control arm. Without it, a walk that reached nothing would make every
    assertion above pass for the wrong reason."""
    got = reachable()
    for wired in (
        "interceptors.from_document",   # the chain, wired in a previous round
        "delegation.from_document",     # teamwork
        "at_most_once.from_document",   # exactly-once keys
        "questions.questions_for",      # approval gates
        # Gaps closed in this session. They belong HERE and not merely absent
        # from UNREACHABLE: a list of what must stay broken cannot notice a fix
        # coming undone. Severing `score()` from `_choose` left `resolve()`
        # unreachable again and the whole suite stayed green, because nothing
        # asserted the positive.
        "facts.from_document",          # A1 — `remembers:` reaches a run
        "resolve.resolve",             # A2 — the measured model choice has a door
        "learning.from_document",       # A3 — the learning gate has a door
        "learning.cycle",               # A3 — and the cycle behind it
        "slo.assess",                   # A4 — the latency promise is assessed
        "facts.something_happened",     # A1 — a fact expires when the turn ends
        "facts.never_raised",           # and a trigger nothing raises is reported
        "learning.of",                  # `classify` asks the author's own lists
    ):
        assert wired in got, (
            f"`{wired}` should be reachable and is not — a capability that "
            f"shipped has become unreachable again"
        )


def test_no_new_reader_has_become_unreachable() -> None:
    """The check that catches the *next* one.

    Every `from_document` in the tree is a document reader by construction. If
    one appears that is neither reachable nor listed, a mechanism has shipped
    inert — which is the defect this whole file exists for.
    """
    _, where = graph()
    got = reachable()
    readers = {
        q
        for name, quals in where.items()
        if name in {"from_document", "of", "for_document"}
        for q in quals
    }
    orphans = sorted(r for r in readers if r not in got and r not in UNREACHABLE)
    assert not orphans, (
        f"document reader(s) nothing can reach: {orphans}\n"
        f"Either wire it to an entry point, delete it, or add it to UNREACHABLE "
        f"with the register row that tracks it."
    )


# ─────────── and the check that missed four modules written to close this


#: Modules that are a DOOR — something a person types — rather than something a
#: run reaches. Each must define `main`, and `test_every_door_is_installed`
#: holds them to being installed as commands.
DOORS = (
    "scoring", "conformance", "pipeline", "exploding", "importing",
    "exporting", "optimising",
)

#: Modules reached only from a door or from another module, and deliberately not
#: from `run`. A name here is a decision, and the reason is the row.
LIBRARIES: dict[str, str] = {
    "evals": "grades a run; reached from `scoring`, never from `run`",
    "learning": "the improvement gate; reached from `scoring --propose`",
    "resolve": "binds a model; reached from `scoring` before a run starts",
    "judge": "the grader named by `graded-by:`; reached from `evals`",
    "providers": "the metric surface; reached from `evals`",
    "diagnostics": "renders a problem; reached from every door",
    "shown": "what a park may show a person; reached from `questions`",
    "egress": "whether binding a role leaves this box; a check, not a run",
    "watches": "attaches to the bus; reached from `run` through `Watches`",
    "script": "a scripted transport's turns; a test and fixture seam",
    "suspension": "a parked run, serialised; reached from `run`",
}


def test_every_module_is_reached_from_somewhere_or_is_a_door() -> None:
    """The check that would have caught four modules written **today**.

    `exploding`, `importing`, `exporting` and `optimising` shipped with no
    `main`, no console script, and no importer in `src/` — built, tested, and
    reachable from nothing a person could type. That is precisely the defect
    this file exists for, reproduced in the work meant to close it.

    It was missed because `test_no_new_reader_has_become_unreachable` looks for
    functions called `from_document`, `of` or `for_document` — a hand-written
    name list, which is the same shape of scope failure corrected three times
    elsewhere in this suite. A module whose public function is called `explode`
    was invisible to it.
    """
    calls, _where = graph()
    reached = {
        name.split(".")[0]
        for callers in calls.values()
        for name in callers
    } | {e.split(".")[0] for e in ENTRIES}

    everything = {
        p.stem for p in SRC.glob("*.py")
        if not p.stem.startswith("_") and p.stem != "__init__"
    }
    orphaned = sorted(
        m for m in everything - reached - set(DOORS) - set(LIBRARIES)
    )
    assert not orphaned, (
        f"{orphaned} are reached by nothing and are on no list.\n"
        f"Either give it a `main` and a console script and add it to DOORS, or "
        f"say in LIBRARIES what reaches it. A module nobody can get to is the "
        f"defect this whole file is about."
    )


@pytest.mark.parametrize("door", sorted(DOORS))
def test_every_door_is_a_command_somebody_can_type(door: str) -> None:
    """A `main` nobody installed is a door with no handle."""
    import tomllib

    source = (SRC / f"{door}.py").read_text()
    assert "def main(" in source, f"`{door}` is a door with no `main`"

    manifest = tomllib.loads(
        (REPO / "adapters/python/pyproject.toml").read_text()
    )
    installed = set(manifest["project"]["scripts"].values())
    assert f"pact_adapters.{door}:main" in installed, (
        f"`{door}.main` exists and no console script points at it, so it is "
        f"reachable only by knowing where the source lives — which is register "
        f"row C6"
    )
