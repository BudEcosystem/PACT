"""A PACT workflow as the structure of a pydantic-graph `Graph` (02P G1-G9; 03 §B.2).

What `graph_of` builds is the kernel 03 §B.2 names, and nothing a step does: each
stage that runs something is a `Step` whose body is a host action still to write
(it raises when run), `decide` is a `Decision` with one `Literal` branch per label,
`each` is a `.map()` into its own stages and a `Join` named for it, `together` a
broadcast into its branches and a `Join`, `repeat` its own stages ended by a
`Decision` named for it whose `again` branch goes back (a cycle; its `at-most:` is
the decision's note, `at-most: <n>`), and a stage with more than one way on (an
`ask-someone`'s, a `repeat`'s, any `then:` with more than `answered:`) a
`Decision` named `<stage>:then` with one branch per outcome. A step whose `does:`
the kernel has no node for (`answer`, `ask-someone`) carries that word as its
`label` (pydantic-graph's own name for a step in a drawing); a route to a word
that is not a stage (`stop-and-say-so`) is labelled on the path to the end. An
inside stage's node id is `<outer>/<name>`, so two blocks may use one name.

`structure` is what such a graph holds of a workflow, and so what reading it back
(`pydantic_graph_reading.workflow_of`) must give again: the names, what each stage
does, where each goes, and the stages inside (G1's test: export, then import, is
the identity). Everything else a stage says (what it calls, binds, checks, the
question it asks, the rules a `decide` reads) is the body of a host action, named
once per stage by the export report.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from .exporting import ExportReport

__all__ = ["AGAIN", "STAGE_WORDS", "graph_of", "structure"]

#: The `does:` words a step carries as its label: the kernel has no node of their own.
STAGE_WORDS = ("answer", "ask-someone")
#: A repeat's decision: the branch that runs another round.
AGAIN = "again"
#: What `structure` keeps of a stage; the rest is the body of a host action.
_STRUCTURE = ("does", "then", "chooses-between", "starts-at", "steps", "at-most")


def structure(block: Mapping[str, Any]) -> dict[str, Any]:
    """The part of a workflow (or of one `steps:` block's stage) a graph holds: `starts-at`
    and, per stage, `does`, `then` (less `answered: done`, the same as no `then`),
    `chooses-between`, and an `each`'s, `together`'s or `repeat`'s own stages (a repeat's
    `at-most:` with them)."""
    out: dict[str, Any] = {}
    if block.get("starts-at"):
        out["starts-at"] = str(block["starts-at"])
    out["steps"] = {name: _stage(stage) for name, stage in (block.get("steps") or {}).items()}
    return out


def _stage(stage: Mapping[str, Any]) -> dict[str, Any]:
    kept: dict[str, Any] = {"does": stage["does"]}
    then = {k: v for k, v in (stage.get("then") or {}).items() if not (k == "answered" and v == "done")}
    if then:
        kept["then"] = then
    if stage.get("chooses-between"):
        kept["chooses-between"] = dict(stage["chooses-between"])
    if stage["does"] in ("each", "together", "repeat"):
        kept.update(structure(stage))
        if stage["does"] == "together":
            kept.pop("starts-at", None)
        if stage["does"] == "repeat":
            kept["at-most"] = stage.get("at-most")
    return kept


def graph_of(document: Mapping[str, Any], workflow: str) -> tuple[Any, ExportReport]:
    """Workflow `workflow` of a loaded document (`pact show`) as a built `Graph`, and the
    report naming each stage's body (a host action the graph's step does not hold)."""
    from pydantic_graph import GraphBuilder

    block = dict((document.get("workflows") or {}).get(workflow) or {})
    if not block:
        raise ValueError(f"the document has no workflow called {workflow!r}")
    report = ExportReport(kind="a pydantic-graph Graph", seen=tuple(sorted(block)))
    g = GraphBuilder(name=workflow, input_type=dict, output_type=Any, auto_instrument=False)
    lowering = _Lowering(g, report)
    enter = lowering.block(block, "", g.end_node)
    first = enter(str(block.get("starts-at") or ""))(g.edge_from(g.start_node))  # lowers what it reaches
    g.add(*lowering.edges, first)
    for key in block:
        if key in ("starts-at", "steps"):
            report.carried[key] = "the graph's nodes and edges, one per stage and route"
        else:
            report.not_carried[key] = (
                "said of the workflow, not of its structure: a built graph has nodes and edges and "
                "nothing else, so the host that runs it holds this"
            )
    return g.build(), report


class _Lowering:
    """One workflow's blocks lowered into one builder; `edges` collects every path."""

    def __init__(self, g: Any, report: ExportReport) -> None:
        self.g, self.report, self.edges = g, report, []
        self.forks: set[str] = set()

    def block(self, block: Mapping[str, Any], prefix: str, exit_: Any) -> Any:
        """The stages of one `steps:` block, each lowered once; returns `enter`: for a stage's
        name, how a path reaches it (a function of a path builder that completes the path).
        `exit_` is where a route to `done` goes: the end, the enclosing fan's join, or the
        enclosing repeat's decision."""
        from pydantic_graph import Decision

        steps: Mapping[str, Any] = block.get("steps") or {}
        nodes: dict[str, Any] = {}
        for name, stage in steps.items():
            nid, does = f"{prefix}{name}", stage["does"]
            if does in ("decide", "repeat"):
                note = f"at-most: {stage.get('at-most')}" if does == "repeat" else None
                nodes[name] = Decision(id=nid, branches=[], note=note)
            elif does in ("each", "together"):
                nodes[name] = self._join(stage, nid)
            else:
                nodes[name] = self.g.step(_body(nid), node_id=nid, label=None if does == "call" else does)
            self._name_the_body(nid, stage)
        inside: dict[str, Any] = {}  # each fan's and repeat's own block, lowered once

        def enter(name: str) -> Any:
            """How a path reaches stage `name` of this block (a route word ends the block)."""
            if name in ("", "done"):
                return lambda path: path.to(exit_)
            if name not in steps:  # `stop-and-say-so` and the like: the end, saying the word
                return lambda path: path.label(name).to(self.g.end_node)
            stage, nid = steps[name], f"{prefix}{name}"
            if stage["does"] not in ("each", "together", "repeat"):
                return lambda path: path.to(nodes[name])
            if name not in inside:
                inside[name] = self.block(stage, f"{nid}/", nodes[name])
                if stage["does"] == "repeat":
                    first = inside[name](str(stage.get("starts-at") or ""))
                    nodes[name].branches.append(first(self.g.match(_literal(AGAIN))))
            into = inside[name]
            if stage["does"] == "each":
                start = into(str(stage.get("starts-at") or ""))
                return lambda path: start(path.map(fork_id=self._fork(f"{nid}:items")))
            if stage["does"] == "together":
                own = stage.get("steps") or {}
                reached = {t for s in own.values() for t in (s.get("then") or {}).values()}
                firsts = [into(n) for n in own if n not in reached]
                return lambda path: path.broadcast(
                    lambda b: [first(b) for first in firsts], fork_id=self._fork(f"{nid}:branches")
                )
            return into(str(stage.get("starts-at") or ""))

        for name, stage in steps.items():
            self._routes(name, stage, nodes[name], enter, prefix)
        return enter

    def _routes(self, name: str, stage: Mapping[str, Any], node: Any, enter: Any, prefix: str) -> None:
        g, does = self.g, stage["does"]
        if does == "decide":
            for label, target in (stage.get("chooses-between") or {}).items():
                node.branches.append(enter(str(target))(g.match(_literal(label))))
            return
        if does == "repeat":
            then = dict(stage.get("then") or {})
            for outcome in ("answered", "too-many-times"):
                if outcome in then or outcome == "answered":
                    node.branches.append(enter(str(then.get(outcome) or ""))(g.match(_literal(outcome))))
            return
        then = dict(stage.get("then") or {})
        heard = then.pop("heard", None) or {}
        ways = {**then, **{f"heard/{port}": target for port, target in heard.items()}}
        if does == "answer":
            self.edges.append(g.edge_from(node).to(g.end_node))
        elif does == "ask-someone" or set(ways) - {"answered"}:
            from pydantic_graph import Decision

            then_node = Decision(id=f"{prefix}{name}:then", branches=[], note=None)
            for outcome, target in ways.items():
                then_node.branches.append(enter(str(target))(g.match(_literal(outcome))))
            self.edges.append(g.edge_from(node).to(then_node))
        else:
            self.edges.append(enter(str(ways.get("answered") or ""))(g.edge_from(node)))

    def _join(self, stage: Mapping[str, Any], nid: str) -> Any:
        """A fan's join: the first value when `waits-for: anyone`, else every item kept (PACT's
        own default); a `combines-by:` line is the formula after it, said in the report."""
        from pydantic_graph import ReduceFirstValue, reduce_list_append

        anyone = (stage.get("teamwork") or {}).get("waits-for") == "anyone"
        if anyone:
            return self.g.join(ReduceFirstValue(), initial=None, node_id=nid)
        return self.g.join(reduce_list_append, initial_factory=list, node_id=nid)

    def _fork(self, wanted: str) -> str:
        if wanted in self.forks:
            raise ValueError(
                f"`{wanted.split(':')[0]}` is reached from more than one place, and a pydantic-graph map "
                "has one way in. Fix: route every stage that reaches it to one stage before it"
            )
        self.forks.add(wanted)
        return wanted

    def _name_the_body(self, nid: str, stage: Mapping[str, Any]) -> None:
        body = sorted(k for k in stage if k not in _STRUCTURE)
        if body:
            self.report.not_carried[f"steps.{nid}"] = (
                f"{', '.join(f'`{k}:`' for k in body)}: what the stage does, which a graph's step "
                "runs as code and does not hold. Its body is a host action to write"
            )


def _literal(label: str) -> Any:
    from pydantic_graph import TypeExpression

    return TypeExpression[Literal[label]]  # type: ignore[valid-type]


def _body(nid: str) -> Any:
    """A step's body: the host action this stage runs, not written yet."""

    async def step(ctx: Any) -> Any:
        raise NotImplementedError(f"stage {nid!r}: write the host action this step runs")

    step.__name__ = nid
    return step
