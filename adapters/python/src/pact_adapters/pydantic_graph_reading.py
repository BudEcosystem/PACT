"""A built pydantic-graph `Graph` read as a PACT workflow, without running any step (02P G1-G9).

What `workflow_of` reads is the graph's structure through its public attributes
(`Graph.nodes`, `edges_by_source`, `parent_forks`; each node's own fields), never
a step's body: a step is code, so it becomes a `call` stage whose action, in
`tools/<graph>.yaml`, is a host action still to write (02P G1). In the words of
the lowering `pydantic_graph_lowering.graph_of` writes, so reading what it built
gives the workflow's `structure` again (G1's test):

- a `Step` is a `call` stage named for its id (an inside stage's id is
  `<outer>/<name>`), or the stage its `label` names when that is a `does:` word
  the kernel has no node for (`answer`, `ask-someone`); a `NodeStep` (a v1
  `BaseNode`) and a step that streams are read as `call` stages and named, since
  what they are is code (G8);
- a `Decision` is a `decide` on the rules rung (G3): one label per branch (a
  `Literal`'s value, or a class's name for a branch by type, or `otherwise` for
  `Any`), each rule reading the label the step before it answers with
  (`steps.<step>.kind`, `item.kind` right after a map, `input.kind` at the
  start), the last label taken when no other is; a `matches=` callable is code and is named, its label kept. A decision
  named `<step>:then` right after its step is that step's `then:`, one outcome per
  branch;
- a map `Fork` and the `Join` it leads to are an `each` named for the join (G5),
  a broadcast `Fork` and its join a `together` (G4); the join's reducer says how
  the items' answers become one (G6): `ReduceFirstValue` is `waits-for: anyone`,
  `reduce_null` keeps nothing, the list reducers keep all, and `reduce_sum`,
  `reduce_dict_update` or the author's own are named with the `combines-by:` line
  to write for each field (the fields are the actions', which are still to write);
- a `Decision` one of whose branches goes back to a stage before it is a `repeat`
  of the stages on that cycle (G9), its `at-most:` read from the decision's note
  (`at-most: <n>`); with no note the bound is still to write, since an unbounded
  cycle is refused;
- a path's `label` to the end is `stop-and-say-so` only on an `ask-someone`'s
  `nobody-answered:`, the one outcome that names a route word; any other label is a
  drawing's, named, and the way goes where it leads; a `.transform()` is code on an
  edge, named (G7).
"""

from __future__ import annotations

import inspect
import re
import typing
from collections.abc import Mapping
from typing import Any

import yaml

from .importing import ImportReport
from .openapi import Imported
from .openapi_shapes import kebab
from .pydantic_graph_lowering import STAGE_WORDS

__all__ = ["workflow_of"]

_START, _END = "__start__", "__end__"
#: The one route word a PACT outcome names besides a stage and `done` (`nobody-answered:`).
_STOP = "stop-and-say-so"
_NOTE = re.compile(r"^\s*at-most:\s*(\d+)\s*$")


def workflow_of(graph: Any, *, name: str = "", connect: str = "") -> Imported:
    """`graph` (a built `pydantic_graph.Graph`) as `workflows/<name>.yaml`, its steps' host
    actions as `tools/<name>.yaml`, and the report. `name` is the workflow's (kebab case),
    else the graph's own, else `graph`; `connect` the MCP server the host serves the steps'
    actions from (the tool file then says `connect:`, and `resources/<connect>.yaml` is
    written beside it)."""
    called = kebab(name or str(graph.name or "")) or "graph"
    report = ImportReport(kind=f"a pydantic-graph Graph ({graph.name or called})")
    read = _Reading(graph, called, report)
    workflow = read.block(None)
    for key, why in (
        ("state_type", "the Python type the steps share. Stages hand values on by `bind:` instead"),
        ("deps_type", "what the host hands every step: the host's, not the workflow's"),
    ):
        if getattr(graph, key) is not type(None):
            report.seen += (key,)
            report.not_portable[key] = why
    if graph.auto_instrument:
        report.seen += ("auto_instrument",)
        report.not_portable["auto_instrument"] = "whether a run is traced: the host decides that"
    for key, line in (("input_type", "accepts"), ("output_type", "answers-with")):
        if getattr(graph, key) is not type(None):
            report.seen += (key,)
            report.mapped[key] = f"`{line}:`, still to write: the graph's is a Python type"
    report.seen += ("name",)
    report.mapped["name"] = f"`workflows/{called}.yaml`"
    report.still_to_write = (
        f"in workflows/{called}.yaml, what it is for (`description:`), what it `accepts:` and what "
        "it `answers-with:`",
        f"each action in tools/{called}.yaml: what its step does, what it `takes:` and answers "
        "with" + ("" if connect else ", and how the host reaches it (`connect:` or `url:`)"),
        *read.owed,
    )
    said = {"description": f"The pydantic-graph graph {graph.name or called}, read as its structure."}
    files = {f"workflows/{called}.yaml": _text({**said, **workflow})}
    if read.actions:
        tool = {"description": f"The host actions the steps of the graph {called} ran.", "actions": read.actions}
        if connect:
            tool = {"description": tool["description"], "connect": connect, "actions": read.actions}
            files[f"resources/{connect}.yaml"] = _text(
                {"resource-kind": "mcp-server", "description": f"Where the host serves the steps of {called}."}
            )
        files[f"tools/{called}.yaml"] = _text(tool)
    return Imported(api="", files=files, shapes={}, report=report)


class _Reading:
    def __init__(self, graph: Any, called: str, report: ImportReport) -> None:
        self.graph, self.called, self.report = graph, called, report
        self.nodes: Mapping[str, Any] = graph.nodes
        self.actions: dict[str, Any] = {}
        self.owed: list[str] = []
        report.seen += tuple(f"nodes.{n}" for n in self.nodes)
        report.mapped[f"nodes.{_START}"] = "`starts-at:`"
        report.mapped[f"nodes.{_END}"] = "`done`, the end of the run"
        #: `nid -> [(word, destination, the path's label)]`: a branch's label is its word.
        self.out = {nid: self._ways(nid) for nid in self.nodes}
        self.into: dict[str, list[str]] = {nid: [] for nid in self.nodes}
        for source, ways in self.out.items():
            for _, target, _ in ways:
                self.into[target].append(source)
        # A fan: a fork and the join it leads to (`parent_forks`); the stage is named for the join.
        forks = {nid for nid, node in self.nodes.items() if type(node).__name__ == "Fork"}
        self.inside: dict[str, set[str]] = {}
        self.fan_of_fork: dict[str, str] = {}
        for join, (fork, inside) in self._fans(forks).items():
            self.fan_of_fork[fork], self.inside[join] = join, inside
        for fork in sorted(forks):
            if fork in self.fan_of_fork:
                report.mapped[f"nodes.{fork}"] = f"the way into {self._name(self.fan_of_fork[fork])}"
            else:
                self._lost(f"nodes.{fork}", "a fork whose ways never join: write an `each` (or a `together`) "
                           "around the stages after it")
        self.repeats = self._repeats()
        self.action_of = self._actions()

    def _fans(self, forks: set[str]) -> dict[str, tuple[str, set[str]]]:
        """Each join and the nearest fork every way to it passes through, with the nodes between
        (`ParentForkFinder`, which `build` runs to find the farthest; the nearest is the fan)."""
        from pydantic_graph.parent_forks import ParentForkFinder

        finder = ParentForkFinder(
            nodes=set(self.nodes),
            start_ids={_START},
            fork_ids=forks,
            edges={n: [t for _, t, _ in ways] for n, ways in self.out.items()},
        )
        out: dict[str, tuple[str, set[str]]] = {}
        for join in (n for n, node in self.nodes.items() if type(node).__name__ == "Join"):
            found = finder.find_parent_fork(join, prefer_closest=True)
            if found is not None and found.fork_id in forks and found.fork_id not in {f for f, _ in out.values()}:
                out[join] = (str(found.fork_id), {str(n) for n in found.intermediate_nodes})
        return out

    # ── edges ───────────────────────────────────────────────────────────────────────────

    def _ways(self, nid: str) -> list[tuple[str, str, str]]:
        node = self.nodes[nid]
        if type(node).__name__ == "Decision":
            ways: list[tuple[str, str, str]] = []
            for branch in node.branches:
                label = word = self._branch(branch)
                n = 1
                while word in {w for w, _, _ in ways}:  # one word per route, never one lost
                    n += 1
                    word = f"{label}-{n}"
                if word != label:
                    self._lost(
                        f"nodes.{nid}.branches.{word}",
                        f"a second branch by `{label}`, which only its `matches=` or its order told apart: "
                        f"its route is the label `{word}`. Write what chooses it as the rule's `when:`",
                    )
                if branch.matches is not None:
                    self._lost(
                        f"nodes.{nid}.branches.{word}.matches",
                        "a `matches=` function decides this branch, and code does not cross: write its "
                        "condition as the rule's `when:`",
                    )
                ways.append((word, *self._end_of(nid, branch.path)))
            return ways
        return [(said, target, said) for target, said in (self._end_of(nid, p) for p in
                self.graph.edges_by_source.get(nid, ()))]

    def _end_of(self, nid: str, path: Any) -> tuple[str, str]:
        """Where a path goes, and the word its `label` says ("" for none)."""
        word, target = "", _END
        for item in path.items:
            kind = type(item).__name__
            if kind == "LabelMarker":
                word = str(item.label)
            elif kind == "TransformMarker":
                self._lost(f"edges.{nid}.transform", "code on an edge (`.transform()`): write it as a `call` stage")
            elif kind == "DestinationMarker":
                target = str(item.destination_id)
        return target, word

    @staticmethod
    def _branch(branch: Any) -> str:
        """A decision branch's label: a `Literal`'s value, a class's name, `otherwise` for `Any`."""
        source = branch.source
        if getattr(typing.get_origin(source), "__name__", "") == "TypeExpression":
            source = typing.get_args(source)[0]
        if typing.get_origin(source) is typing.Literal:
            return "-or-".join(_label(str(v)) for v in typing.get_args(source))
        if source in (Any, object):
            return "otherwise"
        return _label(getattr(source, "__name__", str(source)))

    # ── stages ──────────────────────────────────────────────────────────────────────────

    def block(self, fan: str | None, nodes: set[str] | None = None, first: str = "") -> dict[str, Any]:
        """The stages of one block: the top (`fan` None), a fan's inside, or a repeat's round
        (`fan` is then the join, or the repeat's decision, which a route to `done` reaches)."""
        if nodes is None:
            nodes = set(self.nodes) - {_START, _END} - {n for inside in self.inside.values() for n in inside}
            first = self._stage_of(self.out[_START][0][1], nodes, None) if self.out.get(_START) else ""
        deeper = {n for j, inside in self.inside.items() if j in nodes for n in inside}
        deeper |= {n for d, cycle in self.repeats.items() if d in nodes for n in cycle}
        own = [n for n in self.nodes if n in nodes - deeper and not self._is_then(n)]
        steps: dict[str, Any] = {}
        for nid in (n for n in own if type(self.nodes[n]).__name__ != "Fork"):
            if self._name(nid) in steps:  # two ids one stage name: never one of them lost
                raise ValueError(f"two nodes of the graph are both the stage {self._name(nid)!r}; give one another id")
            steps[self._name(nid)] = self._stage(nid, nodes, fan)
        return {**({"starts-at": first} if first else {}), "steps": steps}

    def _stage(self, nid: str, nodes: set[str], fan: str | None) -> dict[str, Any]:
        node, kind = self.nodes[nid], type(self.nodes[nid]).__name__
        if kind == "Join" and nid in self.inside:
            return self._fan(nid, nodes, fan)
        if kind == "Decision":
            return self._repeat(nid, nodes, fan) if nid in self.repeats else self._decide(nid, nodes, fan)
        does = str(node.label) if getattr(node, "label", None) in STAGE_WORDS else "call"
        name = self._name(nid)
        self.report.mapped[f"nodes.{nid}"] = f"a `{does}` stage" + (
            f", whose action `{self.called}/{self._action(nid)}` is a host action to write" if does == "call" else ""
        )
        stage: dict[str, Any] = {"does": does}
        if does == "call":
            stage["call"] = f"{self.called}/{self._action(nid)}"
            self.actions.setdefault(self._action(nid), {"description": f"What the step {nid} of the graph does."})
        elif does == "ask-someone":
            stage["asks"] = name
            self.owed.append(f"`questions/{name}.yaml`, the question the stage {name} asks")
        if kind == "Join":
            self._lost(f"nodes.{nid}.join", "a join no fork leads to: it waits for whatever reaches it. Write "
                       "the stages before it as an `each` or a `together`")
        elif kind == "NodeStep":
            self._lost(f"nodes.{nid}.node", "a v1 `BaseNode`: its `run` is code that also picks what comes next")
        elif _streams(getattr(node, "call", None)):
            self._lost(f"nodes.{nid}.stream", "a step that streams its output; streams are not a workflow's (G8)")
        if does != "answer" and (then := self._then(nid, nodes, fan)):
            stage["then"] = then
        return stage

    def _then(self, nid: str, nodes: set[str], fan: str | None) -> dict[str, Any]:
        ways = self.out[nid]
        if len(ways) == 1 and self._is_then(ways[0][1]):
            gate = ways[0][1]
            self.report.mapped[f"nodes.{gate}"] = f"the `then:` of {self._name(nid)}, one outcome per branch"
            then: dict[str, Any] = {}
            for word, target, said in self.out[gate]:
                where = self._route(gate, word, target, nodes, fan, said)
                if word.startswith("heard/"):
                    then.setdefault("heard", {})[word.split("/", 1)[1]] = where
                else:
                    then[word] = where
            return then
        if len(ways) > 1:  # a built graph puts a fork between a step and its several ways
            self._lost(f"nodes.{nid}.ways", "a step with several ways out and no decision between them")
        where = self._route(nid, "answered", ways[0][1], nodes, fan, ways[0][2]) if ways else "done"
        return {} if where == "done" else {"answered": where}

    def _decide(self, nid: str, nodes: set[str], fan: str | None) -> dict[str, Any]:
        value, step = self._value_before(nid)
        choices = {word: self._route(nid, word, target, nodes, fan, said) for word, target, said in self.out[nid]}
        last = list(choices)[-1]  # the branches cover every label the step answers with
        rules = [
            {"choose": w} if w in ("otherwise", last) or value is None else {"when": [{"value": value, "is": w}], "choose": w}
            for w in choices
        ]
        if value is None:
            self.owed.append(f"the rules of {self._name(nid)}: what each label is chosen by")
        elif value.startswith("steps."):
            action = self.actions.setdefault(self._action(step), {"description": ""})
            action["answers-with"] = {"kind": "one of " + ", ".join(c for c in choices if c != "otherwise")}
        self.report.mapped[f"nodes.{nid}"] = "a `decide` stage on the rules rung, one label per branch"
        return {"does": "decide", "chooses-between": choices, "by": [{"rules": rules}]}

    def _fan(self, nid: str, nodes: set[str], fan: str | None) -> dict[str, Any]:
        fork = next(f for f, j in self.fan_of_fork.items() if j == nid)
        is_map = bool(self.nodes[fork].is_map)
        does = "each" if is_map else "together"
        inside = self.inside[nid]
        stage: dict[str, Any] = {"does": does}
        if is_map:
            stage["over"] = "input.items"
            self.owed.append(
                f"on {self._name(nid)}: the list it goes through (`over:`), what tells its items apart "
                "(`identified-by:`) and its ceiling (`limits: {items-at-most: <n>, when-it-runs-out: ...}`)"
            )
            first = self._stage_of(self.out[fork][0][1], inside, nid)
            stage.update(self.block(nid, inside, first))
        else:
            stage["steps"] = self.block(nid, inside)["steps"]
        reducer = self.nodes[nid].reducer
        called = getattr(reducer, "__name__", type(reducer).__name__)
        kept = {
            "ReduceFirstValue": "`teamwork: {waits-for: anyone}`: the first answer, the others stopped",
            "reduce_list_append": "every answer kept, as a fan does when `combines-by:` says nothing",
            "reduce_list_extend": "every answer kept, as a fan does when `combines-by:` says nothing",
            "reduce_null": "nothing kept of the answers",
        }
        self.report.mapped[f"nodes.{nid}"] = f"an `{does}` stage" + (f"; its join: {kept[called]}" if called in kept else "")
        if called == "ReduceFirstValue":
            stage["teamwork"] = {"waits-for": "anyone"}
        elif called not in kept:
            line = {"reduce_sum": "add-up", "reduce_dict_update": "merge"}.get(called)
            self.report.seen += (f"nodes.{nid}.reducer",)
            if line:
                self.report.mapped[f"nodes.{nid}.reducer"] = f"`combines-by:` with `<field>: {line}` for each field"
                self.owed.append(f"`combines-by:` on {self._name(nid)}: `<field>: {line}` for each field")
            else:
                self._lost(f"nodes.{nid}.reducer", f"`{called}`, a reducer of the author's: write it as a "
                           "`call` of a program after the fan, which keeps every answer")
        if then := self._then(nid, nodes, fan):
            stage["then"] = then
        return stage

    def _repeat(self, nid: str, nodes: set[str], fan: str | None) -> dict[str, Any]:
        cycle = self.repeats[nid]
        back = next(t for _, t, _ in self.out[nid] if t in cycle)
        stage: dict[str, Any] = {"does": "repeat"}
        if found := _NOTE.match(str(self.nodes[nid].note or "")):
            stage["at-most"] = int(found.group(1))
        else:
            self.owed.append(f"`at-most:` on {self._name(nid)}: a cycle with no bound is refused")
        stage.update(self.block(nid, cycle, self._stage_of(back, cycle, nid)))
        then = {w: self._route(nid, w, t, nodes, fan, said) for w, t, said in self.out[nid] if t not in cycle}
        if set(then) - {"answered", "too-many-times"}:
            ways = list(then.values())
            then = {"answered": ways[0], **({"too-many-times": ways[1]} if len(ways) > 1 else {})}
        if then := {k: v for k, v in then.items() if not (k == "answered" and v == "done")}:
            stage["then"] = then
        self.report.mapped[f"nodes.{nid}"] = "a `repeat` of the stages on its cycle"
        return stage

    # ── routes and names ────────────────────────────────────────────────────────────────

    def _route(self, nid: str, outcome: str, target: str, nodes: set[str], fan: str | None, said: str) -> str:
        """Where the way out of `nid` its `outcome` takes reaches, from a block of `nodes`: a
        stage's name or `done`. The path's label is the route word it names only where PACT has
        one (`nobody-answered: stop-and-say-so`); anywhere else it is a drawing's label, named."""
        if target == _END and said == _STOP and outcome == "nobody-answered":
            return _STOP
        where = "done" if target == _END else self._stage_of(target, nodes, fan)
        if said and said not in ("done", "answered", outcome):
            self._lost(
                f"edges.{nid}.{outcome}.label",
                f"the label `{said}`: PACT names a route word only in an `ask-someone`'s `nobody-answered: "
                f"{_STOP}`, so this way is `{where}`. Say what the label meant in the stage's `description:`",
            )
        return where

    def _stage_of(self, target: str, nodes: set[str], fan: str | None) -> str:
        if target == fan:
            return "done"
        if target in self.fan_of_fork:
            return self._name(self.fan_of_fork[target])
        if type(self.nodes[target]).__name__ == "Fork":  # a fork that never joins: its first way
            return self._stage_of(self.out[target][0][1], nodes, fan)
        for decision, cycle in self.repeats.items():  # into a repeat from outside it
            if target in cycle and not nodes <= cycle:
                return self._name(decision)
        return self._name(target)

    def _value_before(self, nid: str) -> tuple[str | None, str]:
        """What a decision's rules read: the label of what reaches it, when one thing does, and
        the step that answers with it ("" when none does)."""
        sources = self.into[nid]
        if len(sources) != 1:
            return None, ""
        (source,) = sources
        kind = type(self.nodes[source]).__name__
        if source == _START:
            return "input.kind", ""
        if kind == "Fork":
            return ("item.kind", "") if self.nodes[source].is_map else self._value_before(source)
        if kind == "Decision":
            return self._value_before(source)
        if kind == "Join" or getattr(self.nodes[source], "label", None) in STAGE_WORDS:
            return None, ""  # what a fan or a person hands on is no one label
        return f"steps.{self._name(source)}.kind", source

    def _repeats(self) -> dict[str, set[str]]:
        """Each decision with a branch back to a node before it, and the nodes on that cycle."""
        found: dict[str, set[str]] = {}
        stack: list[str] = []
        seen: set[str] = set()

        def reaches(start: str, goal: str) -> bool:
            todo, met = [start], set()
            while todo:
                n = todo.pop()
                if n == goal:
                    return True
                if n not in met:
                    met.add(n)
                    todo += [t for _, t, _ in self.out.get(n, ())]
            return False

        def walk(n: str) -> None:
            seen.add(n)
            stack.append(n)
            for _, t, _ in self.out.get(n, ()):
                if t in stack and type(self.nodes[n]).__name__ == "Decision":
                    found[n] = {m for m in stack[stack.index(t):] if m != n} | {
                        m for m in self.nodes if m != n and reaches(t, m) and reaches(m, n)
                    }
                elif t in stack:
                    self._lost(f"nodes.{n}.cycle", "a cycle with no decision on it, which never ends")
                elif t not in seen:
                    walk(t)
            stack.pop()

        walk(_START)
        return found

    def _is_then(self, nid: str) -> bool:
        return nid.endswith(":then") and nid[: -len(":then")] in self.nodes

    def _action(self, nid: str) -> str:
        """The host action step `nid` calls (`_actions`)."""
        return self.action_of[nid]

    def _actions(self) -> dict[str, str]:
        """Each step's host action: its stage's name, unless a step nearer the top already has
        it (inside ids are `<outer>/<name>`, so two blocks may share one), when it is the step's
        whole id (`fan-check`): two steps are never merged into one action."""
        out: dict[str, str] = {}
        steps = [
            n for n, node in self.nodes.items()
            if n not in (_START, _END, *self.inside) and type(node).__name__ not in ("Decision", "Fork")
            and getattr(node, "label", None) not in STAGE_WORDS
        ]
        for step in sorted(steps, key=lambda n: n.count("/")):  # stable: the graph's order within a depth
            base = self._name(step) if self._name(step) not in out.values() else kebab(step.replace("/", "-"))
            name, n = base, 1
            while name in out.values():
                n += 1
                name = f"{base}-{n}"
            out[step] = name
        return out

    @staticmethod
    def _name(nid: str) -> str:
        return kebab(nid.rsplit("/", 1)[-1])

    def _lost(self, key: str, why: str) -> None:
        self.report.seen += (key,)
        self.report.not_portable[key] = why


def _streams(call: Any) -> bool:
    """Whether a step's function streams: an async generator, or `GraphBuilder.stream`'s wrapper of
    one (`PG/graph_builder.py:1367`, whose own qualified name says so)."""
    return inspect.isasyncgenfunction(call) or str(getattr(call, "__qualname__", "")).startswith("GraphBuilder.stream.")


def _label(text: str) -> str:
    return text if re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*(/[a-z0-9]+(-[a-z0-9]+)*)?", text) else kebab(text) or "otherwise"


def _text(body: Mapping[str, Any]) -> str:
    return yaml.safe_dump(dict(body), sort_keys=False, allow_unicode=True, width=100)
