"""The loop, as an authored document rather than a constant (G1, D12).

Every agent framework has a loop and almost none of them let you see it. Eve is
the honest extreme: `stopWhen: isStepCount(1)` is the **only** stop condition in
171,782 lines, and whether to go round again is one hardcoded boolean. You can
change an Eve agent's tools and its wording; you cannot change the shape of its
thinking, because the shape is not written down anywhere an author can reach.

Here the shape is a document — `loops/careful.yaml` next to the agent, or one of
the shapes PACT ships in `spec/loops/`. It has stages, each stage says what
happens in it and which tools exist there, and the arrows between stages are
outcomes an author can read out loud. Two shapes ship: `pact:loop/standard`
(what you get for free) and `pact:loop/plan-then-do` (think first, act second).

**The rule that keeps this honest:** executing `pact:loop/standard` must produce
exactly the trace the harness produced before loops existed. A mechanism that
changes behaviour when you have not asked for it is not a mechanism, it is a
regression — and a mechanism that changes *nothing* when you do ask is
decoration. Both halves are under test.

# Why three outcomes and not a predicate language

`used-a-tool`, `answered`, `too-many-times`. That is the whole vocabulary, and
it is closed on purpose. A predicate language here would be the fourth place in
this project where an author can write a condition, and D14's bar is a support
lead editing YAML — not a fourth dialect for them to learn. Anything finer
belongs in an interceptor, which already exists and is already reviewable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Mapping


class LoopError(ValueError):
    """An authoring mistake in a loop document.

    Raised rather than absorbed: a loop that names a stage which does not exist
    has no defensible fallback, and picking one would hide the typo (T7). Every
    message names the loop, the stage, what is wrong and a line to type.
    """


class Does(str, Enum):
    """What happens in one stage. Closed — it mirrors `phase.does` in the
    specification, which is where the list is actually maintained."""

    THINK = "think"
    USE_TOOLS = "use-tools"
    CHECK = "check-its-work"
    ASK = "ask-someone"
    ANSWER = "answer"
    #: CodeAct: the model writes the working and the locked room runs it (P8/8).
    RUN_CODE = "run-code"


#: The finish line. Reserved: a stage may not be called this.
DONE = "done"

#: Keys of `then:` that are not outcomes. They say who decides where a stage goes
#: and which stages it may pick between, rather than naming a way the stage
#: ended — so the outcome vocabulary stays the closed three it has always been.
ROUTING_KEYS: frozenset[str] = frozenset({"decided-by", "may-go-to"})

#: Everything a stage can end in. Closed (see the module note).
OUTCOMES = ("used-a-tool", "answered", "too-many-times")

#: The built-in wording for each kind of stage, appended to the agent's own
#: instructions for that stage only. `use-tools` adds nothing at all, which is
#: what makes `pact:loop/standard` byte-identical to having no loop.
#:
#: An author overrides any of these with `says:` on the stage, so the wording is
#: never something only we can change — the exact complaint against Eve's single
#: private `COMPACTION_HEURISTICS` constant applies just as well to a prompt.
SAYS: dict[Does, str] = {
    Does.THINK: "Say what you plan to do, and why. Do not do any of it yet.",
    Does.USE_TOOLS: "",
    Does.CHECK: (
        "Look back at what you just said and check it against your "
        "instructions. If something is wrong, say what is wrong. If it is "
        "right, say so."
    ),
    Does.ANSWER: "Give your final answer now.",
    Does.ASK: "",
    Does.RUN_CODE: (
        "Write the working out as code. It will be run in a locked room with "
        "nothing else in it, and what it prints comes back to you."
    ),
}

#: Stages that offer every tool the agent has when they name none. Every other
#: kind of stage offers nothing unless it names something — that asymmetry is
#: the whole reason a `think` stage thinks instead of reaching for the first
#: tool it recognises.
OFFERS_EVERYTHING = (Does.USE_TOOLS,)


@dataclass(frozen=True)
class Phase:
    """One named stage of thinking."""

    name: str
    does: Does
    then: Mapping[str, str]
    says: str = ""
    may_use: tuple[str, ...] | None = None
    at_most: int | None = None
    #: A carried program that says where to go next, and the stages it may pick
    #: between (P8 wave 7). Empty for every ordinary stage, which is why nothing
    #: about the three-outcome table changes.
    decided_by: str = ""
    may_go_to: tuple[str, ...] = ()
    #: For a `does: ask-someone` stage, the question it puts to a person, by
    #: name. Without it the stage parks carrying wording and nothing else — no
    #: audience, no deadline, no shape for the answer — which from the outside
    #: is a hang. Every other place in PACT that can stop and ask has this line;
    #: this one did not have it for a round, and it was the only one.
    asks: str = ""

    def instruction(self) -> str:
        """The extra wording for this stage, authored or built in."""
        return self.says or SAYS[self.does]

    def tools_offered(self, available: tuple[str, ...]) -> tuple[str, ...]:
        """Which of the agent's tools exist in this stage.

        Narrowing tools per stage is the cheapest accuracy win there is on a
        smaller model, and it is the thing Eve cannot express: its tool set is
        resolved once per run, so a planning step sees the payment tool.
        """
        if self.may_use is None:
            return available if self.does in OFFERS_EVERYTHING else ()
        keep = set(self.may_use)
        return tuple(t for t in available if t in keep)

    def skills_offered(self, available: tuple[str, ...]) -> tuple[str, ...]:
        """Which of the agent's written procedures this stage may read.

        `OFFERS_EVERYTHING` deliberately does NOT apply. Withholding a tool from
        a `think` stage is the point — it is what makes it think instead of
        reaching for the first thing it recognises. Withholding the written
        procedure from the same stage would make it think without the rules it
        was told to follow, which is the opposite. So a stage that names nothing
        reads every procedure the agent has, whatever kind of stage it is, and
        only an explicit `may-use:` narrows it.
        """
        if self.may_use is None:
            return available
        keep = set(self.may_use)
        return tuple(s for s in available if s in keep)


@dataclass(frozen=True)
class Loop:
    """A named shape of thinking, ready to execute."""

    name: str
    starts_at: str
    steps: Mapping[str, Phase]
    description: str = ""

    def phase(self, name: str) -> Phase:
        try:
            return self.steps[name]
        except KeyError:
            raise LoopError(
                f"loop {self.name!r} has no stage called {name!r}. "
                f"Its stages are: {', '.join(sorted(self.steps))}. "
                f"Fix: change the name to one of those, or add a "
                f"`{name}:` stage under `steps:`."
            ) from None

    def route(
        self,
        phase: Phase,
        outcome: str,
        run_program: "Callable[[str, dict[str, Any]], str] | None" = None,
        said: str = "",
    ) -> str:
        """Where a stage goes next, given how it ended.

        `answered` with nowhere to go means finished. That is the one outcome
        with an unarguable terminal reading — an agent that has produced its
        answer and has no further instruction is done, not broken.
        `used-a-tool` with nowhere to go stops the run and says which line to
        add, because silently finishing there would hide a typo in `then:`.

        `too-many-times` never reaches here unrouted. The loop routes past a
        spent stage before entering it (`harness._stage_to_run`), and a stage
        that wrote no `too-many-times:` line goes wherever its `answered:` goes
        — so the stage hands on rather than stopping. That is deliberate and it
        is what `examples/refund-desk/loops/careful.yaml` relies on; the
        schema's help under `then:` says it in the author's own words.
        """
        # A carried program decides, among the stops the author declared (P8
        # wave 7). Asked BEFORE the ordinary table, because a stage that has one
        # wrote it to decide this outcome — and after every ceiling, which is
        # checked by the harness before a stage runs and after every model call.
        # Fuel outranks routing: "the router said continue" must never mean "the
        # money cap did not apply".
        if phase.decided_by and outcome != "too-many-times":
            if run_program is None:
                raise LoopError(
                    f"stage {phase.name!r} of loop {self.name!r} decides where to go with "
                    f"the program {phase.decided_by!r}, and nothing here can run a carried "
                    f"program — so there is nothing to say where this run goes next. Fix: "
                    f"whatever runs your agents has to supply a locked room for programs."
                )
            try:
                chosen = str(run_program(phase.decided_by, {"said": said})).strip()
            except Exception as e:  # noqa: BLE001 — a program's failure is data
                raise LoopError(
                    f"stage {phase.name!r} of loop {self.name!r} asked {phase.decided_by!r} "
                    f"where to go next and it could not run: {e}."
                ) from e
            if chosen not in phase.may_go_to:
                raise LoopError(
                    f"stage {phase.name!r} of loop {self.name!r} asked "
                    f"{phase.decided_by!r} where to go next and it said {chosen!r}, which is "
                    f"not one of the stages it may pick between: "
                    f"{', '.join(phase.may_go_to)}. Fix: have the program answer one of "
                    f"those, or add {chosen!r} to `may-go-to:`."
                )
            return chosen

        target = phase.then.get(outcome)
        if target is not None:
            return target
        if outcome == "answered":
            return DONE
        raise LoopError(
            f"stage {phase.name!r} of loop {self.name!r} ended with "
            f"{outcome!r} and does not say where to go. "
            f"Fix: add a line under that stage's `then:` — "
            f"`{outcome}: {DONE}` to finish there, or the name of another stage."
        )

    def check_against(
        self, tool_names: tuple[str, ...], skill_names: tuple[str, ...] = ()
    ) -> None:
        """Every stage must name something the agent actually has.

        Checked before the first model call rather than when the stage is first
        entered, so a typo in a rarely-taken branch fails at the start of the
        run instead of forty steps in.

        **Skills count.** The agent's own `uses:` line draws from tools AND
        skills, so a stage narrowing what that agent has must be able to draw
        from the same two sets — otherwise the one stage in the worked example
        that exists to read a decision back against the written refund policy
        cannot say "the policy, and only that". Passing no `skill_names` is the
        honest reading of "the caller could not tell us", and it refuses a skill
        exactly as before; it is not a claim that the agent has none.

        `tools_offered` is unaffected on purpose: a skill is a written procedure
        and not something to call, so naming one narrows the stage's TOOLS to
        nothing while leaving the skill in reach. That is what makes
        `may-use: [refund-policy]` mean "read the policy, touch nothing".
        """
        have = set(tool_names) | set(skill_names)
        for phase in self.steps.values():
            for wanted in phase.may_use or ():
                if wanted not in have:
                    raise LoopError(
                        f"stage {phase.name!r} of loop {self.name!r} may use "
                        f"{wanted!r}, which this agent does not have. "
                        f"It has: {', '.join(sorted(have)) or 'no tools or skills'}. "
                        f"Fix: add `{wanted}` to the agent's `uses:` list, or "
                        f"remove it from `may-use:` in that stage."
                    )

    # -------------------------------------------------------------- reading

    @staticmethod
    def from_mapping(name: str, raw: Mapping[str, Any]) -> "Loop":
        """Build a loop from the document shape — `steps`, `starts-at`, `based-on`.

        This is the only path in, and the shipped shapes take it too. A library
        shape that loaded through privileged code would not be a shape an author
        can fork, which is exactly the objection to Eve's compiled manifest.
        """
        if not isinstance(raw, Mapping):
            raise LoopError(
                f"loop {name!r} should be a set of settings, not "
                f"{type(raw).__name__}. Fix: write it as `starts-at:` and "
                f"`steps:` lines."
            )

        base = raw.get("based-on")
        steps_raw: dict[str, Any] = {}
        starts_at = ""
        description = ""
        if isinstance(base, str) and base.strip():
            parent = Loop.from_library(base.strip(), asked_by=name)
            steps_raw = {p.name: _phase_to_mapping(p) for p in parent.steps.values()}
            starts_at = parent.starts_at
            description = parent.description

        # A stage written here replaces the ready-made one of the same name
        # outright. Merging field-by-field would mean an author who deletes
        # `may-use:` from their copy still gets the inherited one, which is the
        # kind of invisible inheritance the Expansion Rule exists to avoid.
        written = raw.get("steps")
        if written is not None and not isinstance(written, Mapping):
            raise LoopError(
                f"loop {name!r} writes its stages as {type(written).__name__} "
                f"and they should be a set of settings — one named stage per "
                f"line. Fix: write `steps:` with a `<name>:` line under it for "
                f"each stage, not a list."
            )
        for key, value in (written or {}).items():
            steps_raw[key] = value

        starts_at = str(raw.get("starts-at") or starts_at or "").strip()
        description = str(raw.get("description") or description or "").strip()

        if not steps_raw:
            raise LoopError(
                f"loop {name!r} has no stages, so there is nothing to run. "
                f"Fix: add a `steps:` section, or point at a ready-made shape "
                f"with `based-on: {STANDARD}`."
            )

        steps = {key: _read_phase(name, key, value) for key, value in steps_raw.items()}

        if DONE in steps:
            raise LoopError(
                f"loop {name!r} has a stage called {DONE!r}, which is the name "
                f"of the finish line. Fix: rename that stage to something else."
            )

        if not starts_at:
            raise LoopError(
                f"loop {name!r} does not say which stage runs first. "
                f"Fix: add a line `starts-at: {sorted(steps)[0]}`."
            )
        if starts_at not in steps:
            raise LoopError(
                f"loop {name!r} starts at {starts_at!r}, but it has no stage "
                f"called that. Its stages are: {', '.join(sorted(steps))}. "
                f"Fix: change `starts-at:` to one of those."
            )

        for phase in steps.values():
            for outcome, target in phase.then.items():
                # The two routing keys are not outcomes and never were: they say
                # WHO decides and WHERE it may go, beside the three ways a stage
                # can end (P8 wave 7).
                if outcome in ROUTING_KEYS:
                    continue
                if outcome not in OUTCOMES:
                    raise LoopError(
                        f"stage {phase.name!r} of loop {name!r} routes on "
                        f"{outcome!r}, which is not something a stage can end "
                        f"in. Fix: use one of: {', '.join(OUTCOMES)}."
                    )
                if target != DONE and target not in steps:
                    raise LoopError(
                        f"stage {phase.name!r} of loop {name!r} sends "
                        f"{outcome!r} to {target!r}, which is not a stage. "
                        f"Its stages are: {', '.join(sorted(steps))}, plus "
                        f"{DONE!r} to finish. Fix: change it to one of those."
                    )

        return Loop(name=name, starts_at=starts_at, steps=steps, description=description)

    @staticmethod
    def from_library(ref: str, asked_by: str = "") -> "Loop":
        """Resolve `pact:loop/<name>` against the shapes PACT ships."""
        key = ref.strip()
        if key not in LIBRARY:
            where = f" (asked for by loop {asked_by!r})" if asked_by else ""
            raise LoopError(
                f"there is no ready-made shape called {key!r}{where}. "
                f"PACT ships: {', '.join(sorted(LIBRARY))}. "
                f"Fix: use one of those, or write your own in `loops/` and "
                f"name it there."
            )
        return Loop.from_mapping(key, LIBRARY[key])

    @staticmethod
    def resolve(doc: Mapping[str, Any], ref: str) -> "Loop":
        """Find the loop an agent named: a shipped shape, or one in this workspace."""
        key = (ref or "").strip()
        if not key:
            return Loop.from_library(STANDARD)
        if key.startswith("pact:loop/"):
            return Loop.from_library(key)
        declared = (doc.get("loops") or {}) if isinstance(doc, Mapping) else {}
        if key in declared:
            return Loop.from_mapping(key, declared[key])
        known = ", ".join(sorted(declared)) or "none"
        raise LoopError(
            f"no loop called {key!r}. This workspace declares: {known}. "
            f"Fix: write `loop: {STANDARD}`, or add a file "
            f"`loops/{key}.yaml` describing the stages."
        )


def _read_phase(loop_name: str, key: str, raw: Any) -> Phase:
    if not isinstance(raw, Mapping):
        raise LoopError(
            f"stage {key!r} of loop {loop_name!r} should be a set of settings. "
            f"Fix: write it as `does: use-tools` and, under it, `then:`."
        )
    does_raw = str(raw.get("does") or "").strip()
    try:
        does = Does(does_raw)
    except ValueError:
        raise LoopError(
            f"stage {key!r} of loop {loop_name!r} says it does {does_raw!r}, "
            f"which is not something a stage can do. "
            f"Fix: use one of: {', '.join(d.value for d in Does)}."
        ) from None

    # Three ordinary YAML slips used to reach Python's own type errors instead
    # of a diagnostic: `then:` as a list of one-item maps, `steps:` as a list,
    # and `at-most: two`. LoopError promises above that every message names the
    # loop, the stage, what is wrong and a line to type — a promise a raw
    # AttributeError does not keep, and one that only bites a host reading the
    # tree natively, which D2 requires to be possible.
    then_raw = raw.get("then")
    if then_raw is not None and not isinstance(then_raw, Mapping):
        raise LoopError(
            f"stage {key!r} of loop {loop_name!r} says where to go next as "
            f"{type(then_raw).__name__}, and it should be one line per outcome. "
            f"Fix: write `then:` with `answered: done` lines under it, one per "
            f"outcome — not a list."
        )
    then = {str(k): str(v) for k, v in (then_raw or {}).items()}

    may_use_raw = raw.get("may-use")
    if isinstance(may_use_raw, str):
        may_use_raw = [may_use_raw]
    may_use = tuple(str(x) for x in may_use_raw) if may_use_raw is not None else None

    at_most_raw = raw.get("at-most")
    at_most: int | None = None
    if at_most_raw is not None:
        try:
            at_most = int(str(at_most_raw).strip())
        except ValueError:
            raise LoopError(
                f"stage {key!r} of loop {loop_name!r} may run at most "
                f"{at_most_raw!r} times, which is not a number. "
                f"Fix: write `at-most: 2`."
            ) from None
    if at_most is not None and at_most < 1:
        raise LoopError(
            f"stage {key!r} of loop {loop_name!r} may run at most "
            f"{at_most} times, which means never. "
            f"Fix: write `at-most: 1` or more, or remove the line."
        )

    return Phase(
        name=key,
        does=does,
        then=then,
        says=str(raw.get("says") or "").strip(),
        may_use=may_use,
        at_most=at_most,
        decided_by=str(then.get("decided-by") or "").strip(),
        may_go_to=tuple(
            str(x).strip() for x in (raw.get("then") or {}).get("may-go-to") or ()
        ),
        asks=str(raw.get("asks") or "").strip(),
    )


def _phase_to_mapping(p: Phase) -> dict[str, Any]:
    """Turn a stage back into document shape, so `based-on` inherits data."""
    out: dict[str, Any] = {"does": p.does.value, "then": dict(p.then)}
    if p.says:
        out["says"] = p.says
    if p.may_use is not None:
        out["may-use"] = list(p.may_use)
    if p.at_most is not None:
        out["at-most"] = p.at_most
    if p.asks:
        out["asks"] = p.asks
    return out


STANDARD = "pact:loop/standard"
PLAN_THEN_DO = "pact:loop/plan-then-do"
#: AC-5.2 asks for six loop patterns. These four are the other four, and the
#: sixth name in the AC — CodeAct — is deliberately absent: it means the agent
#: writes code as its action, which is `runs-as: code`, refused in
#: `docs/50-NOT-COPIED.md` for a stated reason (a spec naming code to run makes
#: `pact check` decide whether that code is safe). Building it here would be
#: reintroducing a refusal through a loop shape.
REACT = "pact:loop/react"
REFLEXION = "pact:loop/reflexion"
TREE_OF_THOUGHT = "pact:loop/tree-of-thought"
ANSWER_MORE_THAN_ONCE = "pact:loop/answer-more-than-once"

#: The shapes PACT ships, mirroring `spec/loops/*.yaml` byte for byte in
#: meaning. They live here as well as there because an adapter reads the loaded
#: document and never the author's tree (invariant P-1) — and
#: `test_loops.py::test_the_two_copies_of_a_shipped_shape_have_not_drifted`
#: reads `spec/loops/*.yaml` through `from_mapping`, the same door an author's
#: own shape goes through, and refuses to let the two drift.
#:
#: (This note used to cite `test_loop_as_data.py`, a file that has never
#: existed, and a mechanism — the real Rust loader — the test does not use.)
LIBRARY: dict[str, dict[str, Any]] = {
    STANDARD: {
        "description": (
            "Work until the job is done: use a tool, look at what came back, "
            "and use another one if it is still needed. Answer when there is "
            "nothing left to check. This is what an agent does when nobody "
            "says otherwise."
        ),
        "starts-at": "work",
        "steps": {
            "work": {
                "does": "use-tools",
                "then": {"used-a-tool": "work", "answered": "done"},
            }
        },
    },
    PLAN_THEN_DO: {
        "description": (
            "Think first, then act. The first stage has no tools at all, so "
            "the agent has to say what it plans to do before it can do "
            "anything."
        ),
        "starts-at": "plan",
        "steps": {
            "plan": {
                "does": "think",
                "says": "Say what you plan to do, in order, and why. Do not do any of it yet.",
                "then": {"used-a-tool": "do", "answered": "do"},
            },
            "do": {
                "does": "use-tools",
                "then": {"used-a-tool": "do", "answered": "done"},
            },
        },
    },
    REACT: {
        "description": (
            "Say what you know, what is missing, and the one thing you will do "
            "next \u2014 then do that one thing, and say it again. The reasoning "
            "is written down at every step instead of happening inside the tool "
            "call."
        ),
        "starts-at": "reason",
        "steps": {
            "reason": {
                "does": "think",
                "says": (
                    "Say what you have found out so far, what you still do not "
                    "know, and the one thing you will do next. One step only "
                    "\u2014 not a plan for the rest of the job."
                ),
                "at-most": 6,
                "then": {
                    "used-a-tool": "act",
                    "answered": "act",
                    "too-many-times": "reply",
                },
            },
            "act": {
                "does": "use-tools",
                "then": {"used-a-tool": "reason", "answered": "reply"},
            },
            "reply": {"does": "answer", "then": {"answered": "done"}},
        },
    },
    REFLEXION: {
        "description": (
            "Do the work, write down what is wrong with what you did, then do "
            "it again with that criticism in front of you. At most two rounds, "
            "then answer."
        ),
        "starts-at": "attempt",
        "steps": {
            "attempt": {
                "does": "use-tools",
                "then": {"used-a-tool": "attempt", "answered": "critique"},
            },
            "critique": {
                "does": "check-its-work",
                "says": (
                    "Say what is wrong with the answer you just gave: what it "
                    "missed, what it assumed without checking, and what you "
                    "would do differently. Do not rewrite the answer here "
                    "\u2014 only say what is wrong with it."
                ),
                "at-most": 2,
                "then": {
                    "used-a-tool": "critique",
                    "answered": "revise",
                    "too-many-times": "reply",
                },
            },
            "revise": {
                "does": "use-tools",
                "says": (
                    "Do the work again with the criticism you just wrote in "
                    "front of you. Fix what you said was wrong rather than "
                    "defending it."
                ),
                "then": {"used-a-tool": "revise", "answered": "critique"},
            },
            "reply": {"does": "answer", "then": {"answered": "done"}},
        },
    },
    TREE_OF_THOUGHT: {
        "description": (
            "Write down three different ways this could be approached, say "
            "what would go wrong with each, then carry out the one that "
            "survives. The branches are written down and pruned in the "
            "transcript, not executed and compared."
        ),
        "starts-at": "propose",
        "steps": {
            "propose": {
                "does": "think",
                "says": (
                    "Write down three different ways this could be approached. "
                    "Number them. Do not choose between them and do not start "
                    "any of them."
                ),
                "then": {"used-a-tool": "judge", "answered": "judge"},
            },
            "judge": {
                "does": "check-its-work",
                "says": (
                    "Take each of the three in turn and say what would go wrong "
                    "with it. Then say which one survives best, and why the "
                    "other two do not."
                ),
                "at-most": 2,
                "then": {
                    "used-a-tool": "judge",
                    "answered": "follow",
                    "too-many-times": "follow",
                },
            },
            "follow": {
                "does": "use-tools",
                "says": (
                    "Carry out the approach you chose. If it fails in the way "
                    "you predicted it might, say so rather than switching to "
                    "another one silently."
                ),
                "then": {"used-a-tool": "follow", "answered": "done"},
            },
        },
    },
    ANSWER_MORE_THAN_ONCE: {
        "description": (
            "Work the whole question through three times, starting again from "
            "the question each time, then say which answer you are standing "
            "behind and whether the attempts disagreed. The attempts share a "
            "conversation, so they are not independent samples."
        ),
        "starts-at": "attempt",
        "steps": {
            "attempt": {
                "does": "think",
                "says": (
                    "Work the whole question through from the beginning and "
                    "give your answer. Start from the question itself, not from "
                    "anything you have already said."
                ),
                "at-most": 3,
                "then": {
                    "used-a-tool": "attempt",
                    "answered": "attempt",
                    "too-many-times": "settle",
                },
            },
            "settle": {
                "does": "answer",
                "says": (
                    "You have worked this through more than once. Say which "
                    "answer you are giving. If the attempts disagreed, say that "
                    "they disagreed and which one you are standing behind "
                    "\u2014 do not present it as though it were settled."
                ),
                "then": {"answered": "done"},
            },
        },
    },
}
