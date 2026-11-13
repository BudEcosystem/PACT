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
import json
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
    """How a run reaches what its stages call. Each is the host's.

    `agent` RUNS an agent, and an agent a stage calls is an agent's run like
    any other: under its own `limits:`, its own approvals and the reactions
    that cover it (docs/99 §5). This runtime does not run agents — the host
    does, with `harness.run` or its own loop — so none of that is carried out
    here, and a host that answers for an agent without running it has skipped
    it. The shared workflow cases answer for each agent on purpose, on trees
    no reaction covers, so that what they compare is the workflow.
    """

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
    #: Why a `decide` went the way it did, where a written rule chose and gave
    #: its reason (`because:`), by stage: the run's "why this path". It is not
    #: part of the stage's record, which a binding reads.
    because: dict[str, str] = field(default_factory=dict)


#: Who answered a question, where the host says: a person's answer may carry
#: it under this name beside the fields the question asks for. It is taken
#: out of the answer and kept as `steps.<stage>.answered-by`. The name is one
#: no question's `answer:` can have a field called (`pact check` refuses an
#: answer field named like something every stage has), so it hides nothing.
ANSWERED_BY = "answered-by"


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
    #: What every stage has besides its answer (`steps.<stage>.outcome`, and a
    #: repeat's `.rounds` and `.ended`), by stage. Kept apart from the answer:
    #: a body hands its last stage's answer on, and these are not part of it.
    words: dict[str, dict[str, Any]] = field(default_factory=dict)

    def read(self, binding: str) -> Any:
        binding = str(binding).strip()
        head, _, rest = binding.partition(".")
        if head == "input":
            root: Any = self.input
        elif head == "steps":
            stage, _, rest = rest.partition(".")
            if stage not in self.steps:
                return ABSENT
            if rest in self.words.get(stage, {}):
                return self.words[stage][rest]
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
            words=dict(self.words),
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
        #: A repeat's `.rounds` and `.ended`, and who answered an `ask`, from the
        #: moment the stage finishes until `block` files them under its name.
        self.stage_words: dict[int, dict[str, Any]] = {}
        #: Whether an `answer` stage of the workflow's own `steps:` ran. What
        #: the last stage came to is what a body hands back to the stage that
        #: holds it; it is not what the workflow hands back.
        self.answered = False
        #: The model catalogue, read the first time a `decide` asks what kind
        #: of model an agent runs on.
        self._catalogue: Any = None

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
                if not where:
                    self.answered = True
                return answer
            scope.steps[stage.name] = answer
            self.result.steps[stage.name] = answer
            # The word the stage ended in — the one its `then:` is read by. A
            # `decide` ends in a label, which is `.label`; its outcome is the
            # plain one.
            said = {"outcome": "answered" if stage.does == "decide" else outcome}
            said.update(self.stage_words.pop(id(stage), {}))
            scope.words[stage.name] = said
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
        """Try the rungs in order and hand back the label that stands at the
        end, with who chose it (`steps.<stage>.label`, `.decided-by`,
        `.answered-by`).

        **A rung that decides makes its label the standing one**, and while a
        label stands a rung is not asked — unless it writes `if-it-disagrees:
        go-on`, which makes it a second opinion. The same label, and it
        stands. Another one, or a second opinion that passes the decision on
        itself, and nothing stands: the rungs after it are tried as if nobody
        had decided. With nothing standing, a `go-on` rung decides as any
        other does.

        **An agent rung passes the decision on** when it answers none of the
        labels (`not-sure`), and — where the rung writes `if-unsure-below:` —
        when its `score` is under that share or it gave none: an answer
        nobody measured is not known to be sure. A score exactly at the
        threshold decides. It passes on to the next RUNG; an agent's `model:`
        fallbacks are for a call that failed, never for an answer.

        This read neither line. A classifier one-tenth sure decided, and a
        second opinion was never asked: the first rung with a label ended it.
        Bud Agent Flow, which had built both, is how that was found.
        """
        labels = tuple(stage.chooses_between)
        standing: dict[str, Any] | None = None
        for rung in stage.by:
            if rung.rules:
                if standing is not None:
                    continue
                # No rule held, or one could not be read: the decision passes on.
                chosen = choose(rung.rules, scope.read)
                if chosen.label:
                    standing = {"label": chosen.label, "decided-by": "rules"}
                    if chosen.because:
                        # The run's "why this path", in the rule's own words.
                        self.result.because[stage.name] = chosen.because
                continue
            if rung.agent:
                second = rung.goes_on_if_it_disagrees
                if standing is not None and not second:
                    continue
                given = self.given_to(rung.agent, scope, stage.says, stage.bind)
                answer = _as_answer(await self.invoke(rung.agent, given))
                label = _one_of(answer, labels)
                if label and rung.if_unsure_below is not None:
                    score = _score(answer)
                    if score is None or score < rung.if_unsure_below:
                        label = ""
                if standing is not None:
                    if label != standing["label"]:
                        standing = None
                        self.result.because.pop(stage.name, None)
                    continue
                if label:
                    standing = {"label": label, "decided-by": "agent", "answered-by": rung.agent}
                continue
            if rung.asks:
                if standing is not None:
                    continue
                answer = await self.person(rung.asks, self.shown_for(rung.asks, scope), stage.name)
                who = answer.pop(ANSWERED_BY, None)
                label = _one_of(answer, labels)
                if label:
                    # Who answered is the host's to say (`ANSWERED_BY`).
                    standing = {"label": label, "decided-by": "person"}
                    if who:
                        standing[ANSWERED_BY] = who
        if standing is not None:
            return standing["label"], standing
        raise Stopped(f"{stage.name!r} ran out of ways to decide between {', '.join(labels)}")

    def given_to(
        self,
        agent: str,
        scope: _Scope,
        says: str = "",
        bind: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """What an agent that decides is handed (`rung.agent`, in the schema's
        own words): the stage's `bind:` over the current item's fields over
        the workflow's input, as many as it `accepts:` and nothing it does
        not, and — for an agent that reads instructions — the stage's `says:`
        at the start of its `message`.

        **The stage's `bind:`, over both.** The input and the item are all a
        deciding agent could be given, so one that had to judge what an
        EARLIER STAGE found — which team takes a defect a triage stage has
        just classified — was handed nothing, in this runtime and in Bud
        Agent Flow's, and a scripted agent answered regardless. A `decide`
        may now write `bind:` as a `call` does: `kind: steps.triage.kind`. A
        bound name is the binding's to fill and nothing else's: it wins over
        the same name in the item or the input, and where the binding reads
        nothing the agent is given nothing under that name. Written rules
        read their own bindings and a person is shown the question's
        `shows:`, so `bind:` is the agents' alone.

        A `decide` stage has no `bind:` — `pact check` refuses one
        (`loader/a-line-this-stage-never-reads`) — so there was no line that
        said what the agent is given, and for a round it was given `{}`. Every
        scripted agent answered regardless. The first real one was asked to
        sort a message it had not been shown, and said `not-sure` to all of
        them.

        **The item, where there is one.** Inside a `for each`, the decision is
        about the item; the workflow's input is what every item shares.

        **An item that is one value is the `message`.** A list of texts has no
        fields; each text is what the decision is about.

        **Nothing it does not accept.** What an agent reads is what `pact
        check` reasons about when it looks for a leak, and an agent handed
        every other field of the workflow as text has read things its own
        file never said it reads. An agent that writes no `accepts:` takes a
        `message` and nothing else.
        """
        declared = ((self.document.get("agents") or {}).get(agent) or {}).get("accepts") or {}
        accepted = set(declared) or {"message"}
        subject = dict(scope.input) if isinstance(scope.input, Mapping) else {}
        bound = {str(k).strip(): scope.read(v) for k, v in (bind or {}).items()}
        # `bind: {note: item}` says where a one-value item goes, so there is
        # nothing left to report about it.
        placed = any(str(v).strip() == "item" for v in (bind or {}).values())
        if isinstance(scope.item, Mapping):
            subject.update(scope.item)
        elif scope.item is not ABSENT:
            # An item that is ONE VALUE — `for each item in input.messages`, a
            # list of texts — has no fields to lay over anything: it is the
            # thing to decide about, so it is the agent's `message`. Found by
            # Bud Agent Flow, whose commonest decision is "sort each of these
            # texts" and whose sorter was handed the `says:` and nothing else.
            if "message" in accepted:
                item = scope.item
                subject["message"] = item if isinstance(item, str) else json.dumps(
                    item, ensure_ascii=False, sort_keys=True, default=str
                )
            elif not placed:
                self.result.unenforced.append(
                    f"a stage that '{agent}' decides, for each item of a list of single "
                    f"values — '{agent}' accepts no `message`, so the item it was to decide "
                    f"about could not be given to it"
                )
        # A name the stage binds is the binding's to fill, and nothing else's:
        # where the binding reads nothing the agent is given nothing under
        # that name, rather than whatever the input happens to call the same.
        for name, value in bound.items():
            subject.pop(name, None)
            if value is not ABSENT:
                subject[name] = value
        given = {k: v for k, v in subject.items() if k in accepted}
        said = (says or "").strip()
        # A trained classifier follows no instruction: it scores the text it
        # is given, and "Pick the shelf for this note." in front of the note
        # is text nobody calibrated it on. So an agent ALL of whose models
        # are `kind: decision` is given its fields as they are — the same
        # test `pact check` uses to let it go without `instructions:` — and
        # nothing is reported, because nothing was owed: on a ladder with a
        # classifier and then a language model, the `says:` is written for
        # the second.
        if said and self.decides_alone(agent):
            said = ""
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

    def decides_alone(self, agent: str) -> bool:
        """Whether every model `agent` names is a trained classifier — a
        catalogue row with `kind: decision`, the distribution's rows and the
        workspace's own both read (`deciding.rs`, `decides_alone`)."""
        written = ((self.document.get("agents") or {}).get(agent) or {}).get("model")
        models = [written] if isinstance(written, str) else list(written or ())
        if not models:
            return False
        if self._catalogue is None:
            from .resolve import load_catalogue

            self._catalogue = load_catalogue(document=self.document)
        rows = (self._catalogue.get(str(m).strip()) for m in models)
        return all(row is not None and row.kind == "decision" for row in rows)

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
            # What the question's own `shows:` lists, as a `decide` asking the
            # same question shows it. A stage that waits showed the person
            # nothing: it passed its `bind:`, which a waiting stage cannot
            # write, so "May this fix be closed?" arrived with no fix.
            shown = {**self.shown_for(stage.asks, scope), **self.inputs(stage, scope)}
            answer = await self.person(stage.asks, shown, stage.name)
        except NobodyAnswered:
            return "nobody-answered", {}
        who = answer.pop(ANSWERED_BY, None)
        if who:
            # A LIST on a wait, always, in the order they answered: a question
            # can need several answers (`answered-by: everyone`), and the
            # shape of `steps.<stage>.answered-by` must not depend on how many
            # people happened to answer. One name is a list of one. (On a
            # `decide` it is one name: a decision is one person's.)
            names = [str(w) for w in who] if isinstance(who, (list, tuple)) else [str(who)]
            self.stage_words[id(stage)] = {ANSWERED_BY: names}
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
        rules = {
            name: Combine.parse(fact.combines_by) if fact.combines_by else Combine.parse("keep-all")
            for name, fact in stage.remembers.declared.items()
        }
        # What a round reads before anything has been remembered: `starts-as:`
        # where the author wrote one; otherwise what the rule makes of nothing
        # — an empty list, for a rule that keeps several (`keep-all`, `top 3
        # …`) — and for a rule that keeps one thing, nothing at all, so a
        # `bind:` that reads it is left out. It was `null` for every rule: a
        # proposer handed `frontier: null` where "no ideas yet" is `[]`.
        kept: dict[str, Any] = {}
        for name, fact in stage.remembers.declared.items():
            if fact.starts_as is not None:
                kept[name] = fact.starts_as
            elif isinstance(empty := rules[name].result(rules[name].start()), list):
                kept[name] = empty
        partials: dict[str, Any] = {}
        rounds = stage.at_most if stage.at_most is not None else (10**9 if self.spec_unbounded() else 1)
        answer: dict[str, Any] = {}
        went = 0
        for _ in range(rounds):
            went += 1
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
                    self.stage_words[id(stage)] = {"rounds": went, "ended": "passed"}
                    return "answered", {**answer, **kept}
        # `.ended` says whether what the repeat was waiting for came to hold. A
        # repeat with no `until:` was waiting for nothing: it has `.rounds`
        # and no `.ended`.
        self.stage_words[id(stage)] = {"rounds": went, **({"ended": "ran-out"} if stage.until else {})}
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
    # A workflow hands back what an `answer` stage bound, and one that
    # reached none hands back nothing: an empty record. It handed back the
    # last stage's own record — a `decide`'s label, a called agent's whole
    # answer — which is nothing the workflow said it gives.
    result.answer = (answer or {}) if run.answered else {}
    # What a run hands back is held to what the workflow says it gives. It was
    # handed back as it came: a workflow that `gives ideas: list of idea`
    # returned records with none of an idea's parts, and said it had finished.
    wrong = _does_not_fit(spec, result.answer)
    if wrong:
        result.halted = "stopped"
        result.said = f"the answer does not fit `answers-with:` — {wrong}"
        # And it is not handed back. A value that fails the workflow's own
        # contract, returned beside the word `stopped`, is a value a caller can
        # still read fields off — fields the workflow said it does not give.
        # Why it stopped is in `said`; what the stages answered is in `steps`.
        result.answer = {}
        return result
    result.halted = "final"
    return result


def _does_not_fit(spec: WorkflowSpec, answer: Mapping[str, Any]) -> str:
    """Why `answer` is not what `spec.answers_with` says — `""` when it is.

    Each field is read by the shape it is written as (`questions.Shape`, the
    one reader of these lines): a field left out is refused unless its shape
    says `, optional`. What the answer carries beyond them is left alone."""
    from .questions import Rejected, Shape

    problems: list[str] = []
    for name, written in spec.answers_with.items():
        try:
            Shape.parse(written, spec.shapes).read(answer.get(name))
        except Rejected as no:
            problems.append(f"{name}: {no}")
    return "; ".join(problems)


def worded(document: Mapping[str, Any] | None, agent: str, given: Mapping[str, Any]) -> str:
    """What a model is shown of the inputs an agent was given, as one text.

    A workflow hands an agent a set of fields (`bind:` on a `call`,
    `given_to` on a `decide`), and something has to turn that into what a
    model reads. PACT said nothing about how, and each runtime chose: this
    repository's own live test sent the `message` and dropped every other
    field; Bud Agent Flow put the agent's `description:` in front when there
    was no `message`, and its classifiers' scores moved with it. What is
    fixed (`accepts:`, in the schema's own words):

    * **Everything given, and nothing else.** The `message`, where there is
      one, as the words; every other field by its name and value. No field is
      left out and nothing is added — not the agent's description, which is
      written for whoever chooses the agent and is not a request put to it.
    * **No `message`, no words in front.** The fields are the whole input;
      what to do with them is what `instructions:` are for.
    * **In the order `accepts:` writes them**, so the same agent is shown the
      same thing from one run to the next.

    How the fields are laid out is each runtime's own. This is the layout
    this one uses: the message, a blank line, then `name: value` lines, a
    value that is not text written as JSON.
    """
    declared = (((document or {}).get("agents") or {}).get(agent) or {}).get("accepts") or {}
    order = [k for k in declared if k in given] + [k for k in given if k not in declared]
    words = str(given.get("message") or "").strip()
    lines = []
    for name in order:
        if name == "message":
            continue
        value = given[name]
        said = value if isinstance(value, str) else json.dumps(
            value, ensure_ascii=False, sort_keys=True, default=str
        )
        lines.append(f"{name}: {said}")
    return "\n\n".join(part for part in (words, "\n".join(lines)) if part)


def _as_answer(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {"answer": value}


def _score(answer: Mapping[str, Any]) -> float | None:
    """How sure a decision model said it was of the label it picked: the
    `score` beside the label, a share of one. `None` when it gave none, or
    one that is no such share."""
    raw = answer.get("score")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return float(raw) if 0.0 <= float(raw) <= 1.0 else None


def _one_of(answer: Mapping[str, Any], labels: tuple[str, ...]) -> str:
    for v in answer.values():
        if isinstance(v, str) and v.strip() in labels:
            return v.strip()
    return ""
