"""The slice of the PACT document an adapter is allowed to see.

Decision P-1: adapters consume the loaded document only. They never read author
files, never re-implement the Expansion Rule, and never learn a framework's
vocabulary. Everything here is plain data produced by `pact show`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Mapping
from typing import Any

from .at_most_once import RequestKeys
from .facts import Facts
from .context_policy import ContextPolicy, Summariser, Tidier
from .delegation import Teamwork
from .interceptors import Chain
from .limits import Limits, steps_at_most
from .slo import Slo
from .loops import STANDARD, Loop
from .questions import Gate, questions_for
from .suspension import PauseRule
from .watches import Watches

#: Used when the author wrote no `steps-at-most`. A bound is never absent: an
#: unbounded loop is Eve's behaviour, and its consequence is a run that stops
#: only once a token budget is gone.
DEFAULT_STEPS = 8


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    #: Per action, the arguments the SURROUNDING SYSTEM fills in — the author's
    #: own `bind:` lines, keyed by action name (`""` for a tool with no actions).
    #: Deliberately absent from `parameters`: the model must not see them, name
    #: them or change them, which is the whole sentence the field's help makes.
    #:
    #: Both halves were checked at check time and neither was executed: measured
    #: on the worked example, `payments` received `{order-number, amount, action}`
    #: and never `customer-id`, so the identity of whoever the run was for never
    #: reached the call, and `RunResult.unenforced` said nothing.
    binds: dict[str, dict[str, str]] = field(default_factory=dict)


def _document_names(written: Any) -> tuple[str, ...]:
    """The file names under a `documents/` folder, however the loader shaped it.

    `pact show` renders a payload as `{"$payload": …, "files": [{"$file": …}]}`,
    and a folder the walker did not treat as a payload arrives as a plain map. A
    reader that knew only one of those shapes would report a corpus as empty on
    the other, which is the same class of mistake as reading a payload back
    through the keys its JSON rendering invented.
    """
    if isinstance(written, Mapping):
        files = written.get("files")
        if isinstance(files, list):
            return tuple(
                str(f.get("$file")) for f in files if isinstance(f, Mapping) and f.get("$file")
            )
        return tuple(sorted(str(k) for k in written if not str(k).startswith("$")))
    if isinstance(written, list):
        return tuple(str(x) for x in written)
    return ()


@dataclass(frozen=True)
class KnowledgeSpec:
    """One set of documents an agent may look things up in (A7).

    PACT does not retrieve, embed, index or chunk — a runtime that does all four
    already exists. This is what that runtime is TOLD, and what a reviewer can
    read: which documents, how they are found, how many pieces come back, and
    whether an answer has to say where it came from.

    A separate kind from `SkillSpec` for a reason a reviewer cares about, not a
    plumbing one: somebody who has read a skill has read every word the model
    will see. `passages-at-most: 5` means nobody knows at check time which five.
    """

    name: str
    description: str
    #: `must-cite: yes` — an answer with no source is not an answer, and an entry
    #: the run could not consult FAILS THE TURN rather than being answered from
    #: what the model already knew.
    must_cite: bool = False
    passages_at_most: int | None = None
    looked_up_by: str = ""
    split_by: str = ""
    use_when: str = ""
    do_not_use_when: str = ""
    if_unsure: str = ""
    #: The file names the payload walker found, for a runtime that needs to know
    #: what it is indexing without re-walking the tree.
    documents: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillSpec:
    """One written procedure, as the model is shown it.

    Names only, for a round — and the consequence was that no skill reached any
    model at all. `policy-checker`'s single declared capability is
    `uses: [refund-policy]` and its instructions say *"quote the exact part of
    the policy that decides it"*; the only thing it was ever told was its own
    five-line `instructions.md`, and two of its own eval cases grade rules that
    exist nowhere but `SKILL.md`. Nothing was reported either, so the run said
    it had done what the author asked.

    Every routing line the schema marks `surface: S-ROUTE` is carried, because
    they are what the author wrote to say when the procedure applies — dropping
    them would leave the model with the body and no idea when it is the wrong
    document.
    """

    name: str
    description: str = ""
    use_when: str = ""
    do_not_use_when: str = ""
    if_unsure: str = ""
    #: The body of `SKILL.md`. Empty is possible and is not an error — a skill
    #: that is only a description is a signpost — but the harness reports it,
    #: because a procedure with no procedure in it is not what the author read
    #: back from `pact check`.
    content: str = ""

    def in_words(self) -> str:
        """This procedure as the model reads it.

        Header first — the four `S-ROUTE` lines, which are what Eve calls
        progressive disclosure and PACT keeps as ordinary settings — then the
        body. One shape, so two ports can produce the same bytes.
        """
        out = [f"### {self.name}"]
        if self.description:
            out.append(self.description)
        if self.use_when:
            out.append(f"Use this when: {self.use_when}")
        if self.do_not_use_when:
            out.append(f"Do not use this when: {self.do_not_use_when}")
        if self.if_unsure:
            out.append(f"If you are unsure: {self.if_unsure}")
        if self.content:
            out.append(self.content)
        return "\n\n".join(out)


@dataclass(frozen=True)
class AgentSpec:
    """One agent, reduced to what a transport needs to execute it."""

    name: str
    description: str
    instructions: str
    tools: tuple[ToolSpec, ...] = ()
    #: Who helps, and what each is for. The sentence is carried, not just the
    #: name, because it is what the model reads when deciding whom to ask — the
    #: author already wrote it under `team:` and dropping it would make the
    #: harness invent a worse one.
    team: dict[str, str] = field(default_factory=dict)
    #: The step ceiling — `steps-at-most` in the author's file. It is named here
    #: rather than kept inside `limits` because it is also the loop bound the
    #: TypeScript port and all seven transports already speak; two copies of one
    #: ceiling is the `same-setting-twice` mistake the validator exists to catch.
    max_steps: int = DEFAULT_STEPS
    #: Every other way this run is allowed to end, and what to do at each.
    limits: Limits = Limits()
    #: The latency promises, and what `feel:` supplies for the ones nobody wrote.
    #: Carried so a run can REPORT what it does not measure; `Limits` is what
    #: stops a run. See `slo.py` for why there is no second enforcer.
    slo: Slo = field(default_factory=Slo)
    #: How the model itself is asked to behave — `max-tokens:`, `thinking:`,
    #: `temperature:` and the nine others.
    #:
    #: The whole group crossed no boundary for a round: twelve fields, two of
    #: them `tier: core`, and every one of them appeared in zero source files
    #: across `crates/*/src`, `adapters/python/src` and
    #: `adapters/typescript/src`. `max-tokens`' help makes a specific behavioural
    #: claim — *"Left out, PACT uses what the model says it can do — which is what
    #: stops the same tree truncating on one framework and not another"* — and
    #: nothing did that. Carried here as the author's own key names, because the
    #: group's own header says every key works on every provider, which is what
    #: makes one mapping per transport possible.
    settings: dict[str, Any] = field(default_factory=dict)
    #: What the agent hands back when it is done, as the author wrote it —
    #: `decision: one of approved, declined`.
    #:
    #: `tier: core`, in the worked example, emitted by `pact show`, and read by
    #: NOTHING until this field. The consequence was visible in the tests and
    #: nobody read it that way: every scripted answer in the suite hand-writes
    #: `"Decision: approved. Amount: 40 USD."`, because the author's declared
    #: shape never reached a model and a human had to supply the format the
    #: document already specified.
    answers_with: dict[str, str] = field(default_factory=dict)
    #: How that shape is put to the model — `text`, `prompted`,
    #: `native-json-schema` or `tool`.
    #:
    #: Empty means the author left it out, and its own help says what happens
    #: then: *"PACT picks from the shape you declared above, and records what it
    #: picked."* It picks `prompted`, because that is the one mode every one of
    #: the seven transports can honour and the only one that works on a machine
    #: with no network. The other two are reported unenforced rather than
    #: silently downgraded — a run that quietly used prose where the author asked
    #: for a JSON schema is the silent degradation T7 forbids.
    answers_with_mode: str = ""
    #: A better model for the stages that check work — `model-for-checking:`.
    #:
    #: The name only. Which transport serves it is the host's business (P-1: an
    #: adapter may be handed only the document), which is exactly why this field
    #: sat in the schema for a session with zero readers: honouring it needs a
    #: SECOND transport, and nothing asked for one. It is reported unenforced
    #: when the host supplies none, rather than every stage quietly using
    #: `model:` while the author believes the checking is being done better.
    model_for_checking: str = ""
    #: What happens while the run is stopped, per kind of wait.
    pauses: tuple[PauseRule, ...] = ()
    #: The shape of its thinking, read from the author's `loop:` line. Not a
    #: name but the resolved document, because an adapter that had to look the
    #: name up again would need the workspace — which invariant P-1 says it
    #: never sees.
    loop: Loop = field(default_factory=lambda: Loop.from_library(STANDARD))
    #: How to keep a long conversation inside what the model can hold, read from
    #: the author's `context-policy:` line. `None` means no tidying at all —
    #: deliberately, so a workspace that never asked for one is never quietly
    #: given a built-in recipe that throws away its reasoning.
    context_policy: "ContextPolicy | None" = None
    #: The rules that may change what happens as this agent runs, read from the
    #: author's `interceptors:` line and already compiled from their sentences.
    #: Resolved here beside the loop and the context policy for the same reason:
    #: an adapter that had to look the names up again would need the workspace,
    #: which invariant P-1 says it never sees. Empty is the honest default — a
    #: run with no rules is byte-identical to one without the mechanism.
    chain: Chain = field(default_factory=Chain)
    #: What to write down as this workspace runs, read from its `watch/`
    #: documents. The OBSERVE half of the same addresses `chain` binds to, and
    #: resolved here beside it for the same reason: an adapter that had to look
    #: them up again would need the workspace, which invariant P-1 says it never
    #: sees.
    #:
    #: WORKSPACE-level and not per-agent, which is why nothing on the agent names
    #: it. An interceptor changes one agent's behaviour so that agent names it; a
    #: watch changes nothing, so making somebody name it twice would buy nothing
    #: and would let an agent quietly stop being watched by deleting one line.
    watches: Watches = field(default_factory=Watches)
    #: How this agent waits for its team and how it shares out what it may spend
    #: on them, read from the author's `teamwork.yaml`. Resolved here for the
    #: same reason `loop`, `context_policy` and `chain` are, and it was the last
    #: of the five to arrive: for a round `run()` wrote `teamwork or Teamwork()`,
    #: so the worked example's `shares: 60/40` was parsed, validated, and
    #: replaced at the door by an even split nobody wrote — and its
    #: `if-someone-fails: ask-a-person` became `carry-on`, which approved a
    #: refund with no fraud check. Config that loads and does not reach the run
    #: is worse than config that does not load.
    teamwork: Teamwork = field(default_factory=Teamwork)
    #: Which question to put about which thing, and which tool calls stop until
    #: a person answers — read from `policy.ask-a-person`, `limits.asks`, the
    #: context policy and the loop's `does: ask-someone` stages. Resolved here
    #: for the reason invariant P-1 gives: an adapter that had to look the names
    #: up again would need the workspace, which it never sees. Until it was, the
    #: author's approval policy gated nothing without two pieces of host Python.
    asking: Gate = field(default_factory=lambda: Gate({}))
    #: The one model the author pinned, or "" when they left it out and PACT
    #: picks. Carried because a context policy is measured against what the
    #: BOUND model can hold: `models/catalog.yaml` publishes a window per model,
    #: and a policy measured against a different model's window is measured
    #: against the wrong number — silently, which is the T7 breach `unmetered`
    #: exists to prevent. Empty is the honest default and it is not a fallback
    #: value: it means "the author did not choose", which is a different fact
    #: from "the author chose the default".
    model: str = ""
    #: Where this workspace lives on disk, when the adapter was handed a tree as
    #: well as a document. Carried for exactly one thing: a workspace may add
    #: models the distribution has never heard of, in its own
    #: `models/catalog.yaml`, and a run that never opens that file leaves an
    #: air-gapped author's `context-policy:` unmeasurable — which is the case the
    #: override layer exists for. Empty is normal: invariant P-1 says an adapter
    #: may only be given the loaded document, so the tree is an optional extra
    #: and every behaviour has to be correct without it.
    workspace: str = ""
    #: Other ways to run this same agent, from the author's own `variants:`
    #: block, in the order they wrote them. `resolve()` searches these; before
    #: they were read, the only strategies in the tree were two Python lambdas in
    #: a test file — including the `decomposed` one README.md advertises as the
    #: measured result. That is "expert users write code for this" on the
    #: headline differentiator, which D14 rules out for the core.
    variants: tuple[tuple[str, dict[str, Any]], ...] = ()
    #: What the surrounding system says it will supply for every run — the
    #: author's `run-inputs:` keys. Carried so a `bind:` naming one that never
    #: arrives can be named on the result rather than filled with nothing.
    run_inputs: tuple[str, ...] = ()
    #: The agent's own key in `agents:` — the folder name, not the display name.
    #: Carried because a diagnostic about this agent has to name the file the
    #: author would open (`agents/refund-desk/limits.yaml`), and `name:` is
    #: "Refund Desk", which is not a path.
    key: str = ""
    #: Which argument makes two calls to an action "the same call" — the
    #: author's own `same-request-key:` lines. `money.rs` holds the name against
    #: the action's `takes:` at check time and says in its own docstring that
    #: enforcing it is "a separate, runtime question"; carried here so that
    #: question has an answer without a host writing Python for it (D14).
    request_keys: RequestKeys = field(default_factory=RequestKeys)

    #: What this agent knows that its messages do not carry — the `remembers:`
    #: entries marked `survives-shortening:` (G9).
    #:
    #: Here, and not built inside the harness, for the reason `tidier` is here:
    #: which facts outlive a summary is a fact about the DOCUMENT. Building it
    #: in `run()` was the shape that failed — `Tidier` accepted a `facts=`
    #: argument, every test passed one, and nothing on the authored path ever
    #: did, so `survives-shortening:` loaded and did nothing for a round.
    facts: Facts = field(default_factory=Facts)

    #: The written procedures this agent may use — its own `uses:` line filtered
    #: to entries that are `skills:` rather than `tools:`. Carried beside `tools`
    #: because `uses:` draws from both and only one half used to survive the
    #: adapter boundary, so a stage narrowing to a skill (`may-use:` draws from
    #: `[tools, skills, agents]`) was refused at run start for a line `pact
    #: check` had just accepted.
    #:
    #: A skill is a document to READ and not something to call, so it
    #: deliberately does NOT become a `ToolSpec`: offering it in the model's tool
    #: list would hand the model a name no transport can answer. It reaches the
    #: model as text, in the system message, narrowed by the stage's `may-use:`
    #: exactly as tools are.
    skills: tuple[SkillSpec, ...] = ()
    #: The sets of documents this agent may look things up in (A7). Built the
    #: same way `skills` is — off the agent's own `uses:` line — so a corpus
    #: nobody named reaches no run, exactly like a skill nobody named.
    knowledge: tuple[KnowledgeSpec, ...] = ()

    @property
    def skill_names(self) -> tuple[str, ...]:
        """The names alone, for the two places that only need names.

        `Loop.check_against` holds `may-use:` against them, and the conformance
        driver puts them on the wire. Everything else wants the document.
        """
        return tuple(s.name for s in self.skills)

    def tidier(
        self, window: int | None, summarise: "Summariser | None" = None
    ) -> "Tidier | None":
        """The author's `context-policy:` ready to run, or nothing.

        Here rather than in the harness because it is a fact about the spec:
        what the policy says is the document's, and the only two things it needs
        that a document cannot carry are how much the model can hold and who
        writes the summaries. Both come from the runtime.

        `None` on either of two honest grounds — the agent named no policy, or
        nothing will say what the model can hold, so there is no budget to
        measure against. The harness reports the second on `RunResult.unmetered`
        rather than letting it pass as "no policy", because those are different
        situations and only one of them is what the author asked for.
        """
        if self.context_policy is None or not window:
            return None
        # `facts=` is passed HERE rather than by the caller, because a caller who
        # forgets it gets a tidier that silently drops the run's evidence. That
        # is not a hypothetical: it is what shipped.
        return Tidier(
            self.context_policy,
            budget_tokens=window,
            summarise=summarise,
            facts=self.facts,
        )

    @property
    def when_it_runs_out(self) -> str:
        """What the author said to do on reaching a ceiling.

        Read through `limits` rather than stored beside it: the action and the
        ceilings it governs are one decision, and a second copy of it is how a
        run ends up stopping one way while the file says another.
        """
        return self.limits.when_it_runs_out.value

    @staticmethod
    def from_document(
        doc: dict[str, Any], agent_key: str, source: "str | Path | None" = None
    ) -> "AgentSpec":
        """The slice of `doc` one agent needs, ready to run.

        `source` is the workspace root and is optional: an adapter is handed a
        loaded document (invariant P-1) and may not have the tree beside it.
        Given one, a mistake in a context policy or an interceptor names the
        real file and the real line instead of a path built from the entry's
        name — which is wrong for every document written as a folder.
        """
        root = Path(source) if source is not None else None
        agents = doc.get("agents") or {}
        if agent_key not in agents:
            raise KeyError(
                f"no agent named {agent_key!r}; this workspace has: {sorted(agents)}"
            )
        a = agents[agent_key]
        tools = tuple(
            ToolSpec(
                name=n,
                description=_text(t.get("description", "")),
                parameters=_takes(t),
                binds=_binds(t),
            )
            for n, t in sorted((doc.get("tools") or {}).items())
            if n in set(_as_list(a.get("uses")))
        )
        # Sorted, like `tools` above, so two lists in two languages never
        # disagree about order. The whole document is carried, not the name:
        # see `SkillSpec` for what silence cost.
        skills = tuple(
            SkillSpec(
                name=n,
                description=_text(s.get("description", "")),
                use_when=_text(s.get("use-when", "")),
                do_not_use_when=_text(s.get("do-not-use-when", "")),
                if_unsure=_text(s.get("if-unsure", "")),
                content=_text(s.get("content", "")),
            )
            for n, s in sorted((doc.get("skills") or {}).items())
            if n in set(_as_list(a.get("uses"))) and isinstance(s, Mapping)
        )
        knowledge = tuple(
            KnowledgeSpec(
                name=n,
                description=_text(k.get("description", "")),
                must_cite=str(k.get("must-cite", "")).strip().lower() in ("yes", "true", "on", "y"),
                passages_at_most=(
                    int(k["passages-at-most"])
                    if isinstance(k.get("passages-at-most"), int)
                    else None
                ),
                looked_up_by=_text(k.get("looked-up-by", "")),
                split_by=_text(k.get("split-by", "")),
                use_when=_text(k.get("use-when", "")),
                do_not_use_when=_text(k.get("do-not-use-when", "")),
                if_unsure=_text(k.get("if-unsure", "")),
                documents=_document_names(k.get("documents")),
            )
            for n, k in sorted((doc.get("knowledge") or {}).items())
            if n in set(_as_list(a.get("uses"))) and isinstance(k, Mapping)
        )
        written = a.get("limits") or {}
        return AgentSpec(
            name=_text(a.get("name", agent_key)),
            description=_text(a.get("description", "")),
            instructions=_text(a.get("instructions", "")),
            tools=tools,
            skills=skills,
            knowledge=knowledge,
            team={k: _text(v) for k, v in sorted((a.get("team") or {}).items())},
            max_steps=steps_at_most(written, DEFAULT_STEPS),
            limits=Limits.from_mapping(written),
            slo=Slo.from_mapping(written),
            settings={k: v for k, v in (a.get("settings") or {}).items()},
            answers_with={
                str(k): str(v) for k, v in (a.get("answers-with") or {}).items()
            },
            answers_with_mode=str(a.get("answers-with-mode") or "").strip(),
            model_for_checking=str(a.get("model-for-checking") or "").strip(),
            pauses=PauseRule.from_document(doc, agent_key),
            loop=Loop.resolve(doc, _text(a.get("loop", ""))),
            context_policy=ContextPolicy.resolve(
                doc, _text(a.get("context-policy", "")), root
            ),
            chain=Chain.from_document(doc, agent_key, root),
            watches=Watches.from_document(doc, root),
            # A bad `teamwork.yaml` now raises `BadTeamwork` here, at spec-build
            # time — the same shape `Loop.resolve` already has one line up, and
            # the reason `check()` was written to run at load rather than
            # mid-run: an author who wrote `enough-is: 4` for a two-person team
            # should hear about it before a customer is waiting.
            teamwork=Teamwork.from_document(doc, agent_key),
            asking=questions_for(doc, agent_key, root),
            request_keys=RequestKeys.from_document(doc, agent_key),
            facts=Facts.from_document(doc, agent_key),
            # `model:` is in the schema and the loader emits it; until this line
            # existed the adapter boundary dropped it, so no host could pass the
            # author's pin on even if it wanted to. `_text` gives "" for absent,
            # which is the "did not choose" this field documents.
            model=_text(a.get("model", "")),
            run_inputs=tuple(sorted((a.get("run-inputs") or {}))),
            # Declaration order, not sorted: the author's order IS the search
            # order, and `resolve()` returns the first that passes.
            variants=tuple(
                (k, dict(v))
                for k, v in (a.get("variants") or {}).items()
                if isinstance(v, Mapping)
            ),
            workspace=str(root) if root is not None else "",
            key=agent_key,
        )


def _takes(tool: dict[str, Any]) -> dict[str, Any]:
    """One tool's arguments, as the model is shown them.

    Every action's `takes:` block, merged — the model calls the TOOL and names
    the action, so one argument list per tool is what it can act on. Two actions
    naming the same argument mean the same thing by it; that is what makes them
    actions of one tool rather than two tools.

    `parameters` was `{}` by default and never assigned, so every tool in every
    workspace was offered with no arguments at all, and `inspects:`, `bind:` and
    `same-request-key:` all named arguments nothing declared.
    """
    out: dict[str, Any] = {}
    actions = tool.get("actions") or {}
    if isinstance(actions, dict):
        for name, action in sorted(actions.items()):
            if not isinstance(action, dict):
                continue
            takes = action.get("takes") or {}
            if isinstance(takes, dict):
                for arg, shape in takes.items():
                    out.setdefault(str(arg), str(shape))
        if actions:
            # Which action, by name. It is how a call becomes `<tool>/<action>`,
            # which is what an approval rule guards and what `must-call-before:`
            # names — and until `takes:` existed there was nowhere to say so.
            out.setdefault("action", "one of " + ", ".join(sorted(actions)))
    return out


# Two reporters used to live here and both are gone, in opposite directions.
#
# `_consents` said that `asks-to-connect:` "was not applied". It is applied now:
# the consent is a `Rule` in the gate (`questions_for`, `gates=True`) and the run
# parks on it before anything goes over the connection. A report that an authored
# line is unenforced, printed by a runtime that enforces it, is the same untruth
# pointing the other way.
#
# `_money_moving` said that a `spends-money: yes` action no approval rule names
# had nothing routed through the policy. That is a fact about two DOCUMENTS read
# together — a tool file and a policy file — which is `pact check`'s job, not a
# run's, and it now lives in `crates/pact-loader/src/money.rs` where an author
# hears it before a customer is waiting rather than after the run.


def _binds(tool: dict[str, Any]) -> dict[str, dict[str, str]]:
    """One tool's `bind:` lines, per action.

    Kept per ACTION rather than merged the way `takes:` is, because two actions
    binding the same argument to different run-inputs is a real thing to write
    and merging would silently pick one. A tool with no `actions:` block keys
    under `""`, which is what `_bound_args` looks up when a call names no action.
    """
    out: dict[str, dict[str, str]] = {}
    actions = tool.get("actions") or {}
    if not isinstance(actions, dict):
        return out
    for name, action in sorted(actions.items()):
        if not isinstance(action, dict):
            continue
        bind = action.get("bind") or {}
        if isinstance(bind, dict) and bind:
            out[str(name)] = {str(k): str(v) for k, v in bind.items()}
    return out


def _text(v: Any) -> str:
    """One text field, whether it was written as one file or as a folder.

    *"A directory is a field; a field may be a directory"* is the headline rule
    of both READMEs, and `examples/refund-desk/README.md` uses `instructions` as
    its own example — *"Start with one file; split it up when it gets long.
    Nothing else changes."* Two things had to change for that to be true: the
    schema stopped refusing the folder form on a `text` field, and this stopped
    returning `""` for it, which would have been the silent loss T7 forbids.

    The entries arrive in the order the loader put them — ordinals first, then by
    name, which is the order the author numbered them — and are joined with a
    blank line between, because they are separate paragraphs of one document.
    """
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, Mapping) and v and all(isinstance(x, str) for x in v.values()):
        return "\n\n".join(x.strip() for x in v.values() if x.strip())
    return ""


def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        return [x for x in v if isinstance(x, str)]
    return []
