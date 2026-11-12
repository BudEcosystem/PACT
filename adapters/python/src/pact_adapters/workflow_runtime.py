"""The reference workflow runtime: a `WorkflowSpec` run, stage by stage.

`docs/98-PRIMITIVES-ENGINEERING-PLAN.md` WP-9. Until this module, nothing in
PACT executed a workflow: `WorkflowSpec` was read and exported to a
pydantic-graph skeleton whose step bodies raise `NotImplementedError`
(`pydantic_graph_lowering.py`). This is the semantics, the way `harness.py` is
an agent's: a host may keep its own engine, and this is what every engine is
held to.

**What it is built from**, so it is one semantics and not a second one:

* routing by rules is `conditions.choose`, and `until:` and every other
  condition is `conditions.all_hold` — the readers the checker's tables are
  shared with;
* combining is `combine.Combine`, which until now had no engine;
* waiting on branches is the five `waits-for` meanings of `delegation.met_by`'s
  vocabulary;
* a failure plan is `moments.FailurePlan`, as `ir.StageSpec` reads it.

**What it does not do itself.** A workflow calls things — tool actions,
agents, programs, people — and running any of them is the host's: a tool needs
its server, an agent needs a transport, a person needs somebody to ask. So a
run is handed `Callers`, one function per kind, and a workflow called by
another is run here, by this module. That is the seam `harness.run` already
has (`tool_impls`, `transport`), one level up.

**Stages.** `call`, `decide`, `each`, `together`, `repeat`, `ask-someone`,
`answer`. A stage ends in an outcome; `then:` names where that outcome goes;
`done` ends the block it is in, `stop-and-say-so` ends the run. A stage with no
line for its outcome ends its block (inside an `each`, a `repeat` or a
`together`, that is the end of one item, round or branch).
"""

from __future__ import annotations

import asyncio
import inspect
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping

from .combine import Combine
from .conditions import ABSENT, all_hold, choose
from .detectors import DECLARED, declared_in
from .ir import StageSpec, WorkflowSpec

#: `tool(tool, action, inputs) -> answer`.
CallTool = Callable[[str, str, dict[str, Any]], Any]
#: `agent(name, inputs) -> answer` — the host runs it (`harness.run`).
CallAgent = Callable[[str, dict[str, Any]], Any]
#: `program(name, inputs) -> answer` — the host's locked room.
CallProgram = Callable[[str, dict[str, Any]], Any]
#: `person(question, shown) -> answer`, or raise `Parked` to wait.
AskPerson = Callable[[str, dict[str, Any]], Any]

DONE = "done"
STOP = "stop-and-say-so"


class Parked(Exception):
    """A person (or the clock) has not answered yet: the run waits here."""

    def __init__(self, question: str, stage: str) -> None:
        super().__init__(f"waiting on {question!r} at {stage!r}")
        self.question = question
        self.stage = stage


class NobodyAnswered(Exception):
    """The question's time ran out with no answer."""


class Stopped(Exception):
    """The run stopped and said why (`stop-and-say-so`, or a failure with no plan)."""


@dataclass
class Callers:
    """How a run reaches what its stages call. Each is the host's."""

    tool: CallTool | None = None
    agent: CallAgent | None = None
    program: CallProgram | None = None
    person: AskPerson | None = None


@dataclass
class RunRef:
    """A detached run (`waits-for-result: no`), which a later stage may stop."""

    id: str
    task: "asyncio.Task[Any]"

    def stop(self) -> bool:
        return self.task.cancel()


@dataclass
class Written:
    """One write this run made that has a way back (`undone-by:`)."""

    stage: str
    undo: str
    inputs: dict[str, Any]
    answer: Any


@dataclass
class WorkflowResult:
    """How a workflow run ended, and what it handed back."""

    #: `final` (an `answer` stage, or the end), `stopped` (stop-and-say-so, or a
    #: failure nothing planned for), `parked` (a person has not answered).
    halted: str = "final"
    answer: dict[str, Any] = field(default_factory=dict)
    #: Every stage's answer, by name, as `steps.<name>` reads it.
    steps: dict[str, Any] = field(default_factory=dict)
    #: Why it stopped, in words, when it did.
    said: str = ""
    #: The stage a parked run waits at, and its question.
    parked_at: str = ""
    question: str = ""
    #: The order stages ran in, nested ones as `outer/inner`.
    trace: list[str] = field(default_factory=list)
    #: Writes with a way back, newest last.
    written: list[Written] = field(default_factory=list)
    #: Detached runs still going.
    detached: dict[str, RunRef] = field(default_factory=dict)
    #: What was written and could not be carried out, in sentences — never
    #: left out and never guessed at.
    unenforced: list[str] = field(default_factory=list)


async def _maybe(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


@dataclass
class _Scope:
    """What a binding reads: the run's input, every stage's answer so far, the
    item of an `each`, the round's memory, the document's values."""

    input: Mapping[str, Any]
    steps: dict[str, Any]
    item: Any = ABSENT
    remembers: dict[str, Any] = field(default_factory=dict)
    values: Mapping[str, Any] = field(default_factory=dict)

    def read(self, binding: str) -> Any:
        binding = str(binding).strip()
        head, _, rest = binding.partition(".")
        if head == "input":
            root: Any = self.input
        elif head == "steps":
            stage, _, rest = rest.partition(".")
            if stage not in self.steps:
                return ABSENT
            root = self.steps[stage]
        elif head == "item":
            root = self.item
        elif head == "remembers":
            root = self.remembers
        elif head == "values":
            root = self.values
        else:
            return binding  # written as a literal
        if not rest:
            return root
        for part in rest.split("."):
            if isinstance(root, Mapping) and part in root:
                root = root[part]
            elif isinstance(root, RunRef) and part == "run":
                return root
            else:
                return ABSENT
        return root

    def child(self, **changes: Any) -> "_Scope":
        """A copy to run one item, branch or round in: it reads what this scope
        knows, and what it writes stays in the copy (`forks:`, docs/98 WP-10)."""
        return _Scope(
            input=self.input,
            steps=dict(self.steps),
            item=changes.get("item", self.item),
            remembers=dict(changes.get("remembers", self.remembers)),
            values=self.values,
        )


class _Run:
    def __init__(
        self,
        spec: WorkflowSpec,
        callers: Callers,
        document: Mapping[str, Any] | None,
        result: WorkflowResult,
    ) -> None:
        self.spec = spec
        self.callers = callers
        self.document = document or {}
        self.result = result
        self.agents = set((self.document.get("agents") or {}).keys())
        self.programs = set((self.document.get("programs") or {}).keys())
        self.workflows = set((self.document.get("workflows") or {}).keys())

    # ───────────────────────────────────────────────────────────── blocks

    async def block(
        self, steps: tuple[StageSpec, ...], start: str, scope: _Scope, where: str
    ) -> dict[str, Any] | None:
        """Run one block of stages from `start` until it ends, and return what it
        hands back: an `answer` stage's answer, or else the last stage's — what
        one item of an `each`, one branch of a `together` or one round of a
        `repeat` came to. `None` when no stage ran."""
        by_name = {s.name: s for s in steps}
        at = start or (steps[0].name if steps else "")
        ran = 0
        last: dict[str, Any] | None = None
        while at and at != DONE:
            if at == STOP:
                raise Stopped(f"the run reached `stop-and-say-so` in {where or 'the workflow'}")
            stage = by_name.get(at)
            if stage is None:
                raise Stopped(f"{where or 'the workflow'} has no stage {at!r}")
            ran += 1
            if ran > 10_000:  # the checker refuses circles outside a repeat (WF-8)
                raise Stopped(f"{where} went round more than 10000 stages")
            self.result.trace.append(f"{where}/{stage.name}".lstrip("/"))
            outcome, answer = await self.stage(stage, scope, where)
            if stage.does == "answer":
                return answer
            scope.steps[stage.name] = answer
            self.result.steps[stage.name] = answer
            last = _as_answer(answer)
            nxt = stage.then.get(outcome)
            if nxt is None and outcome == "too-many-times":
                nxt = stage.then.get("answered")
            if isinstance(nxt, Mapping):  # `heard:` — port to stage
                nxt = next(iter(nxt.values()), None)
            if stage.does == "decide":
                nxt = stage.chooses_between.get(outcome)
            at = str(nxt).strip() if nxt is not None else ""
        return last

    # ───────────────────────────────────────────────────────────── stages

    async def stage(self, stage: StageSpec, scope: _Scope, where: str) -> tuple[str, Any]:
        does = stage.does
        if does == "call":
            return await self.call(stage, scope, where)
        if does == "decide":
            return await self.decide(stage, scope)
        if does == "each":
            return "answered", await self.each(stage, scope, where)
        if does == "together":
            return "answered", await self.together(stage, scope, where)
        if does == "repeat":
            return await self.repeat(stage, scope, where)
        if does == "ask-someone":
            return await self.ask(stage, scope)
        if does == "answer":
            return "answered", self.inputs(stage, scope)
        if does == "stop":
            return "answered", self.stop(stage, scope)
        raise Stopped(f"{stage.name!r} does {does!r}, which a workflow does not run")

    def stop(self, stage: StageSpec, scope: _Scope) -> dict[str, Any]:
        """`does: stop`: cancel a run a `call` started without waiting for it."""
        ref = scope.read(stage.stops)
        if not isinstance(ref, RunRef):
            raise Stopped(f"{stage.name!r} stops {stage.stops!r}, which is not a run this one started")
        stopped = ref.stop()
        self.result.detached.pop(ref.id, None)
        return {"stopped": stopped}

    def inputs(self, stage: StageSpec, scope: _Scope) -> dict[str, Any]:
        """A stage's `bind:`, read. A binding that reads nothing is left out
        rather than sent as a marker, so the callee sees what it was given."""
        read = {k: scope.read(v) for k, v in stage.bind.items()}
        return {k: v for k, v in read.items() if v is not ABSENT}

    async def target(self, stage: StageSpec, scope: _Scope) -> str:
        """What a `call:` names: as written, or — written as a binding — what the
        binding holds, which must be on `may-call:`."""
        written = stage.call.strip()
        if written.split(".", 1)[0] in ("steps", "item", "input", "remembers"):
            picked = (scope.read(written))
            name = str(picked).strip() if picked is not ABSENT else ""
            if name not in stage.may_call:
                raise Stopped(
                    f"{stage.name!r} was to call {name or 'nothing'!r}, which `may-call:` "
                    f"does not list ({', '.join(stage.may_call)})"
                )
            return name
        return written

    async def invoke(self, name: str, inputs: dict[str, Any]) -> Any:
        if "/" in name:
            tool, action = name.split("/", 1)
            if self.callers.tool is None:
                raise Stopped(f"nothing here can call the tool {name!r} (no `Callers.tool`)")
            return await _maybe(self.callers.tool(tool, action, inputs))
        if name in self.workflows:
            inner = WorkflowSpec.from_workflow(self.document, name)
            out = await run_workflow(inner, inputs, self.callers, document=self.document)
            if out.halted != "final":
                raise Stopped(f"the workflow {name!r} {out.halted}: {out.said}")
            return out.answer
        if name in self.programs:
            if self.callers.program is None:
                raise Stopped(f"nothing here can run the program {name!r} (no `Callers.program`)")
            return await _maybe(self.callers.program(name, inputs))
        if name in self.agents or self.callers.agent is not None:
            if self.callers.agent is None:
                raise Stopped(f"nothing here can run the agent {name!r} (no `Callers.agent`)")
            return await _maybe(self.callers.agent(name, inputs))
        raise Stopped(f"{name!r} is not a tool action, agent, program or workflow here")

    async def call(self, stage: StageSpec, scope: _Scope, where: str) -> tuple[str, Any]:
        name = await self.target(stage, scope)
        inputs = self.inputs(stage, scope)
        if not stage.waits_for_result:
            ref = RunRef(id=uuid.uuid4().hex, task=asyncio.ensure_future(self.invoke(name, inputs)))
            self.result.detached[ref.id] = ref
            return "answered", {"run": ref}
        attempts = max(1, stage.at_most or 1)
        failure: BaseException | None = None
        for _ in range(attempts):
            try:
                answer = await self.invoke(name, inputs)
            except (Stopped, Parked):
                raise
            except Exception as err:  # a call that failed is data for the plan
                failure = err
                continue
            undo = stage.undone_by or self._action_undo(name)
            if undo:
                self.result.written.append(Written(stage.name, undo, inputs, answer))
            return "answered", _as_answer(answer)
        return await self.failed(stage, scope, name, inputs, failure, where)

    def _action_undo(self, name: str) -> str:
        if "/" not in name:
            return ""
        tool, action = name.split("/", 1)
        body = (((self.document.get("tools") or {}).get(tool) or {}).get("actions") or {}).get(action)
        return str((body or {}).get("undone-by") or "")

    async def failed(
        self,
        stage: StageSpec,
        scope: _Scope,
        name: str,
        inputs: dict[str, Any],
        failure: BaseException | None,
        where: str,
    ) -> tuple[str, Any]:
        plan = stage.if_it_fails
        why = f"{stage.name!r} failed calling {name!r}: {failure}"
        if plan is None or plan.after_that == "stop-and-say-so":
            raise Stopped(why)
        if plan.after_that == "use-a-backup":
            try:
                return "answered", _as_answer(await self.invoke(plan.backup, inputs))
            except (Stopped, Parked):
                raise
            except Exception as err:
                raise Stopped(f"{why}; the backup {plan.backup!r} failed too: {err}") from None
        if plan.after_that == "carry-on":
            return "answered", {k: (scope.read(v)) for k, v in plan.carry_on_with.items()}
        if plan.after_that == "ask-a-person":
            answer = await self.person(plan.asks, {"failed": str(failure)}, stage.name)
            return "answered", answer
        if plan.after_that == "undo":
            await self.undo(plan.undo)
            raise Stopped(f"{why}; what {plan.undo or 'the run'!r} did was undone, newest first")
        raise Stopped(f"{why}; `{plan.after_that}` needs the host (a new version, a person)")

    async def undo(self, stage_name: str = "") -> list[str]:
        """Take back what was written, newest first: everything, or one stage's."""
        undone: list[str] = []
        for w in reversed(self.result.written):
            if stage_name and w.stage != stage_name:
                continue
            await self.invoke(w.undo, dict(w.inputs))
            undone.append(w.stage)
        self.result.written = [
            w for w in self.result.written if stage_name and w.stage != stage_name
        ]
        return undone

    async def decide(self, stage: StageSpec, scope: _Scope) -> tuple[str, Any]:
        labels = tuple(stage.chooses_between)
        for rung in stage.by:
            if rung.rules:
                # No rule held, or one could not be read: the decision passes on.
                chosen = choose(rung.rules, scope.read)
                if chosen.label:
                    return chosen.label, {"label": chosen.label, "because": chosen.because}
                continue
            if rung.agent:
                given = self.given_to(rung.agent, scope, stage.says)
                answer = _as_answer(await self.invoke(rung.agent, given))
                label = _one_of(answer, labels)
                if label:
                    return label, {"label": label, "by": rung.agent}
                continue
            if rung.asks:
                answer = await self.person(rung.asks, self.shown_for(rung.asks, scope), stage.name)
                label = _one_of(answer, labels)
                if label:
                    return label, {"label": label, "by": "a person"}
        raise Stopped(f"{stage.name!r} ran out of ways to decide between {', '.join(labels)}")

    def given_to(self, agent: str, scope: _Scope, says: str = "") -> dict[str, Any]:
        """What an agent that decides is handed (`rung.agent`, in the schema's
        own words): the current item's fields over the workflow's input, as
        many as it `accepts:` and nothing it does not, and the stage's `says:`
        at the start of its `message`.

        A `decide` stage has no `bind:` — `pact check` refuses one
        (`loader/a-line-this-stage-never-reads`) — so there was no line that
        said what the agent is given, and for a round it was given `{}`. Every
        scripted agent answered regardless. The first real one was asked to
        sort a message it had not been shown, and said `not-sure` to all of
        them.

        **The item, where there is one.** Inside a `for each`, the decision is
        about the item; the workflow's input is what every item shares.

        **Nothing it does not accept.** What an agent reads is what `pact
        check` reasons about when it looks for a leak, and an agent handed
        every other field of the workflow as text has read things its own
        file never said it reads. An agent that writes no `accepts:` takes a
        `message` and nothing else.
        """
        declared = ((self.document.get("agents") or {}).get(agent) or {}).get("accepts") or {}
        accepted = set(declared) or {"message"}
        subject = dict(scope.input) if isinstance(scope.input, Mapping) else {}
        if isinstance(scope.item, Mapping):
            subject.update(scope.item)
        given = {k: v for k, v in subject.items() if k in accepted}
        said = (says or "").strip()
        if said:
            if "message" in accepted:
                rest = str(given.get("message") or "").strip()
                given["message"] = f"{said}\n\n{rest}" if rest else said
            else:
                self.result.unenforced.append(
                    f"says: on a stage that '{agent}' decides — '{agent}' accepts no "
                    f"`message`, so the stage's own instruction could not be given to it"
                )
        return given

    def shown_for(self, question: str, scope: _Scope) -> dict[str, Any]:
        """What a person who decides is shown: the question's own `shows:`
        lines, read — `shows: [input.message]`. It was `{}`, so the person was
        asked which desk should take a message nobody showed them."""
        mine = (self.document.get("workflows") or {}).get(self.spec.name) or {}
        asked = (mine.get("questions") or {}).get(question) or (
            (self.document.get("questions") or {}).get(question) or {}
        )
        shown: dict[str, Any] = {}
        for binding in asked.get("shows") or ():
            value = scope.read(str(binding))
            if value is not ABSENT:
                shown[str(binding)] = value
        return shown

    async def person(self, question: str, shown: dict[str, Any], at: str) -> dict[str, Any]:
        if self.callers.person is None:
            raise Parked(question, at)
        return _as_answer(await _maybe(self.callers.person(question, shown)))

    async def ask(self, stage: StageSpec, scope: _Scope) -> tuple[str, Any]:
        try:
            answer = await self.person(stage.asks, self.inputs(stage, scope), stage.name)
        except NobodyAnswered:
            return "nobody-answered", {}
        no = [k for k, v in answer.items() if isinstance(v, bool) and v is False]
        return ("declined" if no else "answered"), answer

    async def each(self, stage: StageSpec, scope: _Scope, where: str) -> dict[str, Any]:
        items = (scope.read(stage.over))
        items = list(items) if isinstance(items, (list, tuple)) else []
        ceiling = stage.items_at_most
        if ceiling is not None and len(items) > ceiling:
            raise Stopped(
                f"{stage.name!r} was given {len(items)} items and may take {ceiling} "
                f"(`items-at-most:`)"
            )
        if stage.identified_by:
            seen: set[tuple[Any, ...]] = set()
            unique = []
            for it in items:
                key = tuple((it.get(f)) if isinstance(it, Mapping) else it for f in stage.identified_by)
                if key not in seen:
                    seen.add(key)
                    unique.append(it)
            items = unique
        inner_where = f"{where}/{stage.name}".lstrip("/")
        at_once = stage.region_limits.at_once_at_most if stage.region_limits else None
        gate = asyncio.Semaphore(at_once) if at_once else None

        async def one(it: Any) -> dict[str, Any]:
            async def go() -> dict[str, Any]:
                child = scope.child(item=it)
                return await self.block(stage.steps, stage.starts_at, child, inner_where) or {}

            if gate is None:
                return await go()
            async with gate:
                return await go()

        if not stage.keeps_taking:
            answers = await self.branches(stage, [one(it) for it in items])
            return self.combined(stage, answers)
        return self.combined(stage, await self.taking(stage, scope, items, one, ceiling))

    async def taking(
        self,
        stage: StageSpec,
        scope: _Scope,
        items: list[Any],
        one: Callable[[Any], Awaitable[dict[str, Any]]],
        ceiling: int | None,
    ) -> list[Any]:
        """`keeps-taking: yes`: an `each` over a list that grows while it runs.

        Each time an item finishes the `over:` list is read again, and anything
        new is started. It ends once the list has stopped growing and nothing it
        started is still running — the join over a growing set (docs/97 §2.5).
        `items-at-most:` still bounds it, counted over everything it took."""
        def key(it: Any) -> Any:
            if stage.identified_by and isinstance(it, Mapping):
                return tuple(str(it.get(f)) for f in stage.identified_by)
            return repr(it)

        taken = {key(it) for it in items}
        running = {asyncio.ensure_future(one(it)) for it in items}
        answers: list[Any] = []
        while running:
            done, running = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                answers.append(t.result())
            now = scope.read(stage.over)
            for it in now if isinstance(now, (list, tuple)) else ():
                if key(it) in taken:
                    continue
                if ceiling is not None and len(taken) >= ceiling:
                    raise Stopped(
                        f"{stage.name!r} has taken {ceiling} items, all its `items-at-most:` allows"
                    )
                taken.add(key(it))
                running.add(asyncio.ensure_future(one(it)))
        return answers

    async def together(self, stage: StageSpec, scope: _Scope, where: str) -> dict[str, Any]:
        inner_where = f"{where}/{stage.name}".lstrip("/")

        async def branch(s: StageSpec) -> dict[str, Any]:
            child = scope.child()
            out = await self.block((s,), s.name, child, inner_where)
            return out if out is not None else _as_answer(child.steps.get(s.name, {}))

        answers = await self.branches(stage, [branch(s) for s in stage.steps])
        return self.combined(stage, answers)

    async def branches(self, stage: StageSpec, work: list[Awaitable[dict[str, Any]]]) -> list[Any]:
        """Run branches side by side and join them by `teamwork.waits-for`."""
        waits = str(stage.teamwork.get("waits-for") or "everyone").strip()
        enough = int(stage.teamwork.get("enough-is") or 0)
        on_failure = str(stage.teamwork.get("if-someone-fails") or "stop-the-others").strip()
        tasks = [asyncio.ensure_future(w) for w in work]
        got: list[Any] = [ABSENT] * len(tasks)
        good = 0
        pending = set(tasks)
        try:
            while pending:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for t in done:
                    i = tasks.index(t)
                    if t.cancelled():
                        continue
                    err = t.exception()
                    if err is not None:
                        if isinstance(err, (Stopped, Parked)) and on_failure != "carry-on":
                            raise err
                        got[i] = {"failed": str(err)}
                        if on_failure == "stop-the-others":
                            raise Stopped(f"a branch of {stage.name!r} failed: {err}")
                        continue
                    got[i] = t.result()
                    good += 1
                if waits in ("anyone", "the-first-good-answer") and good >= 1:
                    break
                if waits == "enough-of-them" and enough and good >= enough:
                    break
        finally:
            for t in pending:
                t.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        return [g for g in got if g is not ABSENT]

    def combined(self, stage: StageSpec, answers: list[Any]) -> dict[str, Any]:
        """Each field of the answers made one by its `combines-by:` rule; a field
        no rule names keeps every answer's value, in order."""
        fields: list[str] = []
        for a in answers:
            for k in a if isinstance(a, Mapping) else ():
                if k not in fields:
                    fields.append(k)
        out: dict[str, Any] = {}
        for f in fields:
            values = [a[f] for a in answers if isinstance(a, Mapping) and f in a]
            rule = stage.combines_by.get(f)
            if not rule:
                out[f] = values
                continue
            combined = Combine.parse(rule).combined(values)
            out[f] = combined["answer"] if isinstance(combined, dict) and "share" in combined else combined
        out["items"] = answers
        return out

    async def repeat(self, stage: StageSpec, scope: _Scope, where: str) -> tuple[str, Any]:
        inner_where = f"{where}/{stage.name}".lstrip("/")
        kept: dict[str, Any] = {
            name: fact.starts_as for name, fact in stage.remembers.declared.items()
        }
        partials: dict[str, Any] = {}
        rules = {
            name: Combine.parse(fact.combines_by) if fact.combines_by else Combine.parse("keep-all")
            for name, fact in stage.remembers.declared.items()
        }
        rounds = stage.at_most if stage.at_most is not None else (10**9 if self.spec_unbounded() else 1)
        answer: dict[str, Any] = {}
        for _ in range(rounds):
            child = scope.child(remembers={**scope.remembers, **kept})
            out = await self.block(stage.steps, stage.starts_at, child, inner_where)
            answer = out or {}
            for name, fact in stage.remembers.declared.items():
                if not fact.comes_from:
                    continue
                value = (child.read(fact.comes_from))
                if value is ABSENT:
                    continue
                rule = rules[name]
                items = value if isinstance(value, list) and rule.rule == "keep-all" else [value]
                part = partials.get(name, rule.start())
                for it in items:
                    part = rule.add(part, it)
                partials[name] = part
                kept[name] = rule.result(part)
            if stage.until:
                after = scope.child(remembers={**scope.remembers, **kept})
                after.steps.update(child.steps)
                if all_hold(stage.until, after.read) is True:
                    return "answered", {**answer, **kept}
        return "too-many-times" if stage.until else "answered", {**answer, **kept}

    def spec_unbounded(self) -> bool:
        return self.spec.unbounded


async def run_workflow(
    spec: WorkflowSpec,
    inputs: Mapping[str, Any],
    callers: Callers,
    *,
    document: Mapping[str, Any] | None = None,
    remembered: Mapping[str, Any] | None = None,
) -> WorkflowResult:
    """Run `spec` with `inputs`, reaching what it calls through `callers`.

    `remembered` is what the workspace and the workflow already remember, by
    name — the host's store, as `harness.run`'s `remembered=` is. A stage reads
    it as `remembers.<name>`; a `repeat` adds its own round's memory on top."""
    result = WorkflowResult()
    values = {name: v.value for name, v in spec.values.items()}
    scope = _Scope(
        input=dict(inputs), steps={}, remembers=dict(remembered or {}), values=values
    )
    run = _Run(spec, callers, document, result)
    # The workspace's own `detectors:`, for `looks-like:` (docs/98 WP-12).
    held = DECLARED.set(declared_in(document or {}))
    try:
        answer = await run.block(spec.steps, spec.starts_at, scope, "")
    except Parked as parked:
        result.halted = "parked"
        result.parked_at = parked.stage
        result.question = parked.question
        result.said = str(parked)
        return result
    except Stopped as stopped:
        result.halted = "stopped"
        result.said = str(stopped)
        return result
    finally:
        DECLARED.reset(held)
    result.halted = "final"
    result.answer = answer or {}
    return result


def _as_answer(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {"answer": value}


def _one_of(answer: Mapping[str, Any], labels: tuple[str, ...]) -> str:
    for v in answer.values():
        if isinstance(v, str) and v.strip() in labels:
            return v.strip()
    return ""
