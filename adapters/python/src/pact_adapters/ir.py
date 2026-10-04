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
from .holes import Hole, holes_in
from .context_policy import ContextPolicy, Summariser, Tidier
from .delegation import Teamwork
from .interceptors import Chain
from .limits import Limits, steps_at_most
from .limits import seconds as _seconds
from .slo import Slo
from .loops import STANDARD, Loop
from .questions import Gate, Rejected, Shape, questions_for
from .suspension import PauseRule
from .watches import Watches
from .yes_no import said_yes

#: Used when the author wrote no `steps-at-most`. A bound is never absent: an
#: unbounded loop is Eve's behaviour, and its consequence is a run that stops
#: only once a token budget is gone.
DEFAULT_STEPS = 8

#: Which keys of the author's `settings:` block `spec/schema.yaml` types
#: `yes-no`. Read once, HERE, where the document becomes a spec — not per
#: transport, and the reason is the reason this whole predicate was collapsed:
#: whether `parallel-tool-calls: enabled` is a tick is a fact about the SCHEMA,
#: identical on every target, and six transports each deciding it privately is
#: `_yes` written six more times.
#:
#: What it cost while the value went through raw. `pact show` renders a `yes-no`
#: as the author's own word (`"enabled"`, `"no"`), and `settings:` was the one
#: group carried into `AgentSpec` verbatim, so the WORD reached the SDKs:
#:
#: * `agents.model_settings.ModelSettings` is a pydantic dataclass typed
#:   `parallel_tool_calls: bool | None`. Measured on openai-agents 0.19.1,
#:   `enabled` and `disabled` raise `ValidationError` — a line `pact check`
#:   printed `OK` for, killing the run. The other eight spellings worked only by
#:   pydantic's own `bool_parsing` coincidence, which is not a decision this
#:   repository made and not one it can rely on.
#: * `pydantic_ai.settings.ModelSettings` is a `TypedDict` and validates
#:   nothing, which is worse. `parallel-tool-calls: no` travelled to
#:   `chat.completions.create(parallel_tool_calls="no")` as the STRING `"no"` —
#:   truthy everywhere it is read, i.e. the opposite of what the author wrote.
#:
#: Pinned against the schema by
#: `tests/test_one_word_for_yes_means_one_thing_to_every_reader.py`, which reads
#: the `settings` group out of `spec/schema.yaml` and fails if a second `yes-no`
#: key is added there without being added here — the same drift guard the
#: vocabulary itself has, because a one-entry table is exactly the kind that
#: goes stale unnoticed.
TICKS_IN_SETTINGS = frozenset({"parallel-tool-calls"})

#: The three lines that say where a tool reaches, in the order the schema writes
#: them — the same order, and the same three names, as `WAYS` in
#: `crates/pact-loader/src/reach.rs`.
#:
#: A table rather than three branches for the reason that file gives: a fourth
#: transport should cost a row here and a row in the schema, never a new shape
#: of reader. It is also what makes "which kinds survive the boundary" a
#: question a test can ask exhaustively instead of naming the three it happens
#: to remember.
WAYS_A_TOOL_REACHES = ("connect", "url", "says")


@dataclass(frozen=True)
class ResourceSpec:
    """One connected system, as `resources/<name>.yaml` publishes it.

    Carried on the tool that reaches it rather than looked up again later, for
    the reason invariant P-1 gives: an adapter is handed the loaded document and
    never the tree, so anything that had to re-walk `resources:` would be doing
    the loader's job without the loader's guarantees — and the middle hop is the
    one `tools/payments.yaml` argues at length is load-bearing (`uses:` names a
    TOOL, `connect:` names a SERVER, and they are deliberately spelled
    differently).

    Never a credential, only where one is kept. The schema refuses
    `bearer-token:` by name, and this keeps that distinction across the
    boundary: `auth_by_reference` is a name the platform team publishes and
    resolving it is theirs, so a bridge can hand it back to the host without
    this process ever holding a secret.
    """

    #: The key in `resources:` — what the tool's `connect:` line named.
    name: str
    #: `resource-kind:`. One choice today (`mcp-server`), carried rather than
    #: assumed: a bridge that built an MCP client for whatever it was handed
    #: would be reading a field that does not say what it thinks it says the
    #: first time a second kind returns.
    kind: str = ""
    #: `endpoint:` — a name the platform team publishes, not an address this
    #: process resolves.
    endpoint: str = ""
    #: `auth.by-reference:` — where the credential is kept.
    auth_by_reference: str = ""
    #: `asks-to-connect:` — the question a person answers before anything goes
    #: over this connection. Already a `Rule` in the gate (`questions_for`), and
    #: carried here as well because the gate answers *"does this call stop?"*
    #: and a bridge has the different question *"may I open this connection at
    #: all?"* about the same line.
    asks_to_connect: str = ""
    #: `tool-snapshot-digest:` — one digest over everything this server published
    #: when somebody reviewed it, prose included. AD-71's injection is a sentence
    #: rewritten under a byte-identical `tools/list`, which is precisely the
    #: change `check_against_authored` cannot see: it holds tool NAMES and
    #: ARGUMENT SCHEMAS and never a description. `""` means the author pinned
    #: nothing, which is a different fact from a pin that failed and is reported
    #: as one — see `mcp_bridge.check_snapshot`.
    tool_snapshot_digest: str = ""
    #: `tool-snapshot-taken-at:` — the day that digest was taken, as `2026-08-06`.
    #: Carried as the author's own text rather than parsed here: what a date
    #: means is `mcp_bridge`'s question and `ir` is the boundary, not a clock.
    tool_snapshot_taken_at: str = ""
    #: `tool-snapshot-max-age:` — how old the pin may be before the connection is
    #: refused, in SECONDS, read through `limits.seconds` so `30d` means here
    #: what it means in every other duration field this port reads. A second
    #: spelling table would be a second opinion about what `1m30s` is, and the
    #: field it would disagree about is a security window.
    #:
    #: `None` means the author wrote no ceiling; `0.0` would mean they wrote one
    #: of zero, and the two must not collapse into each other.
    tool_snapshot_max_age: "float | None" = None
    description: str = ""


@dataclass(frozen=True)
class Reach:
    """Where one tool goes: which of `connect:`, `url:` and `says:` the author
    wrote, and what they wrote on it.

    A named shape rather than a `(kind, value)` pair, and the reason is that the
    pair is not enough on two of the three kinds: `url:` owes a `method:`
    beside it (the schema says so with `needs-also:`) and `connect:` owes the
    resource it named. A tuple would have to grow to four positions nobody can
    remember the order of, and `reach[0]` reads as nothing where `reach.kind`
    reads as what it is.
    """

    #: One of `WAYS_A_TOOL_REACHES`, spelled as the author's own field name so
    #: a diagnostic can quote the line they would open the file and change.
    kind: str
    #: What that line says: a server name, an address, or the wording put to a
    #: model.
    value: str
    #: `method:` — only for a `url:` tool. A `method:` written beside a
    #: `connect:` is governed by nothing (`needs-also:` runs one way, from
    #: `url:`), so carrying it there would tell a reader it means something.
    method: str = ""
    #: The resource a `connect:` names, resolved from the document's
    #: `resources:`. `None` for the other two kinds — and also for a `connect:`
    #: naming a server this workspace has not got, which `names: resources`
    #: refuses at check time. Kept as an absence rather than an empty
    #: `ResourceSpec` because "no endpoint" and "no such server" are different
    #: facts and only one of them is a typo.
    resource: "ResourceSpec | None" = None
    #: The OTHER reach lines written on the same tool, which is always empty for
    #: a document that passed the loader — `reach.rs` makes two of the three an
    #: error, because nothing anywhere decides which of them a call goes to.
    #: Recorded instead of dropped so that a reader handed a document from
    #: somewhere else refuses it rather than silently picking the first, which
    #: is the one behaviour a portable artifact may not have.
    also_written: tuple[str, ...] = ()


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
    #: Per action, the `remembers:` name the answer is kept under — the author's
    #: own `remember-as:` line, keyed the way `binds` is.
    #:
    #: The other direction of the same pair, and it shipped as a checker with no
    #: runtime: `pact check` refused a tool writing where `never-from:` says no
    #: tool may, while no run ever wrote anything at all. A guard biting on a
    #: write that never happens is a guarantee about nothing.
    remembers: dict[str, str] = field(default_factory=dict)
    #: WHERE this tool reaches — the one of `connect:`, `url:` and `says:` the
    #: author wrote, with the server a `connect:` names already resolved.
    #:
    #: Read by nothing for as long as `ToolSpec` has existed. A tool arrived at
    #: the executing side as a name, a sentence and an argument list, and the
    #: three lines that say where a call GOES were dropped at this boundary — so
    #: `connect: payments-server` reached the model as a tool name and reached
    #: nothing else. That is why an MCP bridge could not be written: the half of
    #: the tool that names the server was not on this side of the wall.
    #:
    #: `None` means the document named none of the three, which
    #: `crates/pact-loader/src/reach.rs` refuses as an error at check time. It is
    #: carried as an absence rather than filled in with a guess, because a reader
    #: that assumed `connect:` would send a refund to a server nobody wrote down.
    reaches: "Reach | None" = None


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
class ProgramSpec:
    """One carried program, as the run is told about it (P6/P7).

    Names and shapes only. The BODY is a folder of files the loader recorded by
    name, media type, size and fingerprint, and nothing in this port ever opens
    one — running a body is the host's, the way serving a model and calling a
    tool are, and for the same reason: `pact check` must stay a reading of the
    tree (R5) and this port must stay something an air-gapped machine can run
    without fetching an engine (D17).

    Carried at all so a run can say what it could NOT do. A workspace that
    declares programs, run by a host with no runner, has to be told before the
    first call — otherwise the author meets `error: no tool named ...`, which
    reads as a mistake in their own file and is not one.
    """

    name: str
    description: str = ""
    #: `wasm`, `python` or `typescript`. Which of them a host can start is the
    #: host's business; what this port does with the word is report it.
    engine: str = ""
    #: `pure`, `deterministic` or `nondeterministic` — what a resumed run may
    #: reuse rather than ask again. Declared and delegated (§4).
    determinism: str = ""
    #: The tool actions that reach it, `<tool>/<action>`, so the sentence a run
    #: reports can name where the author wrote it.
    reached_by: tuple[str, ...] = ()
    #: Whether this workspace's `allow-egress:` names `programs`.
    #:
    #: The eighth part of the boundary, and for a round it was decoration: no
    #: check read the word, no run reported it, and this class — the only thing a
    #: host is ever handed about a program — did not carry it. A choice a
    #: non-coder can type and nothing can exercise reads as a capability, which is
    #: worse than an absent one.
    #:
    #: It is a fact carried rather than a rule enforced, and the split is the same
    #: one the room itself makes: PACT declares the locked room and whatever runs
    #: your agents supplies it, so nothing in this port can hold a door shut on a
    #: body it never opens (R5, D17). What it can do is hand the host the author's
    #: own answer, and say on `unenforced` that the answer is being trusted.
    may_reach_outside: bool = False


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
    #: The run-time holes in `instructions:` and `description:` (02P A1) —
    #: `{{run-inputs.<n>}}` and `{{remembers.<n>}}` — each once, in the order
    #: they first appear (instructions first). `pact check` has already refused
    #: any that names something this agent does not declare, so every entry is
    #: one of `run_inputs` or one of `facts.declared`.
    #:
    #: The text itself is carried unfilled in `instructions`/`description`: the
    #: values are only known when a run starts, and `holes.fill` is how a host
    #: puts them in — strictly, so an unfilled hole is an error and never
    #: literal braces in front of a model.
    holes: tuple[Hole, ...] = ()
    #: Which of those keys the author declared of shape `agent` (P4) — the
    #: subset whose VALUE is the name of one of this workspace's agents.
    #:
    #: A separate field rather than a richer `run_inputs`, because `run_inputs`
    #: is what `bind:` checking reads and a `bind:` naming a key does not care
    #: what shape it holds. What the shape decides is a different question with
    #: a different reader: whether a value may be put to work as a DELEGATE
    #: (`harness.run`'s admission pass). Two readers, two fields, and neither
    #: has to know about the other.
    #:
    #: Decided by `questions.Shape.parse`, never by matching the spelling here:
    #: `an agent`, `which agent` and `the name of an agent` all mean `agent` and
    #: the closed vocabulary that says so lives in exactly one place. A second
    #: private list of spellings is the defect `every_shape_the_spellings_accept_can_be_read`
    #: was written against, one module over.
    agent_valued_inputs: tuple[str, ...] = ()
    #: `<tool>/<action>` → the program that shortens what it hands back (P8
    #: wave 5). Keyed by both halves because a tool may offer several actions and
    #: only one of them answer with something worth projecting.
    projections: tuple[tuple[str, str], ...] = ()
    #: The carried programs this agent's own tools reach (P6/P7).
    #:
    #: Narrowed to what THIS agent can get to, the same way `tools` is: a program
    #: another agent's tool reaches is not something this run could have called,
    #: so reporting it here would be a sentence about somebody else's document.
    programs: tuple[ProgramSpec, ...] = ()
    #: Whether this workspace's `allow-egress:` names `programs`, as a fact about
    #: the WORKSPACE rather than about one carried body.
    #:
    #: The same word `ProgramSpec.may_reach_outside` carries, read once and put in
    #: two places on purpose. A host starting one body holds that body's spec and
    #: should not have to go and find the workspace; but a `does: run-code` stage
    #: names no program and so has no body spec at all, and it needs the same
    #: answer — whether the room it is about to use may reach outside decides
    #: whether handing it the model's verbatim words is safe.
    programs_may_reach_outside: bool = False
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
    #: Text somebody OUTSIDE this tree wrote, already fenced by
    #: `mcp_bridge.quarantined` — today an MCP server's own prose (AD-71).
    #:
    #: The one field on this object that `from_document` never fills in, and
    #: deliberately: there is nothing in the workspace to fill it from. A server's
    #: `instructions` string arrives at connect time, on a machine, after the
    #: review — which is the entire reason AD-71 exists. A host that has connected
    #: puts it here; a host that has not gets `()`, which is the state every run
    #: in this repository is in.
    #:
    #: It is on the SPEC rather than passed to `run()` so that it travels with
    #: everything else a transport is handed, and so `_system_for` — the one
    #: place a system message is built — can place it after the authored
    #: procedures and refuse it if it is not fenced. Raw text stored here reaches
    #: a `ValueError` and never a model.
    external_prose: tuple[str, ...] = ()

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
                remembers=_remembers(t),
                # The whole `resources:` map is handed over, not the workspace:
                # the resolution happens HERE, once, so that what crosses the
                # boundary is a server an adapter can reach rather than a name it
                # would have to look up in a document it does not have (P-1).
                reaches=_reaches(t, doc.get("resources")),
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
                must_cite=said_yes(k.get("must-cite")),
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
        description = _text(a.get("description", ""))
        instructions = _text(a.get("instructions", ""))
        return AgentSpec(
            name=_text(a.get("name", agent_key)),
            description=description,
            instructions=instructions,
            holes=tuple(dict.fromkeys(holes_in(instructions) + holes_in(description))),
            tools=tools,
            skills=skills,
            knowledge=knowledge,
            team={k: _text(v) for k, v in sorted((a.get("team") or {}).items())},
            max_steps=steps_at_most(written, DEFAULT_STEPS),
            limits=Limits.from_mapping(written),
            slo=Slo.from_mapping(written),
            settings={
                k: (said_yes(v) if k in TICKS_IN_SETTINGS else v)
                for k, v in (a.get("settings") or {}).items()
            },
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
            programs=_programs_reached_by(doc, a),
            programs_may_reach_outside=_programs_may_reach_outside(doc),
            projections=_projections(doc, a),
            run_inputs=tuple(sorted((a.get("run-inputs") or {}))),
            agent_valued_inputs=_agent_valued(a.get("run-inputs")),
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


def _questions_this_agent_puts(doc: dict[str, Any], agent: dict[str, Any]) -> set[str]:
    """Every question name this agent can reach, by any line that names one.

    Crude on purpose and in one direction only: a name that turns out not to be
    a question is dropped by the caller, and a question missed here costs a
    sentence on `unenforced` rather than a wrong one. Enumerating the six fields
    that can name a question would be a list to keep in step with the schema.
    """
    out: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, str):
            out.add(node.strip())
        elif isinstance(node, Mapping):
            for v in node.values():
                walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v)

    walk(agent)
    for named in _as_list(agent.get("uses")):
        walk((doc.get("tools") or {}).get(named))
    walk((doc.get("policies") or {}).get(str(agent.get("policy") or "")))
    return out


def _programs_may_reach_outside(doc: dict[str, Any]) -> bool:
    """Does this workspace's `allow-egress:` name `programs`?

    One reader, two carriers: `ProgramSpec.may_reach_outside` for a host holding
    one body, and `AgentSpec.programs_may_reach_outside` for a `does: run-code`
    stage, which names no body and still has to know whether the room it is about
    to use may reach outside.
    """
    return "programs" in [str(w).strip() for w in _as_list(doc.get("allow-egress"))]


def _programs_reached_by(doc: dict[str, Any], agent: dict[str, Any]) -> tuple[ProgramSpec, ...]:
    """The carried programs this agent's own tools can reach.

    Walked the way a RUN reaches one: the agent's `uses:` names a tool, the
    tool's action names a program. A program no tool of this agent's names is not
    something this run could have called.
    """
    declared = doc.get("programs") or {}
    if not isinstance(declared, Mapping) or not declared:
        return ()
    tools = doc.get("tools") or {}
    reached: dict[str, list[str]] = {}
    # Named straight from `uses:` (P8). Only a `pure` program may be — the
    # checker refuses anything else where the author is — so what arrives here
    # is a calculation that works from what it is given and touches nothing.
    # `uses` is the whole address: there is no tool and no action, which is the
    # point of the short door.
    for used in sorted(_as_list(agent.get("uses"))):
        if used in declared:
            reached.setdefault(used, []).append("uses")
    # WHERE THE RUN GOES NEXT. `decided-by:` names a program with no tool
    # anywhere near it, so this walk never saw one: a host with no runner was
    # never told it could not route the loop, and the `allow-egress:` answer P8
    # made real never reached the room that would run it.
    shape = doc.get("loops") or {}
    named_loop = str(agent.get("loop") or "")
    chosen = shape.get(named_loop) if isinstance(shape, Mapping) else None
    if isinstance(chosen, Mapping):
        steps = chosen.get("steps") or {}
        if isinstance(steps, Mapping):
            for stage_name, stage in sorted(steps.items()):
                if not isinstance(stage, Mapping):
                    continue
                then = stage.get("then") or {}
                router = then.get("decided-by") if isinstance(then, Mapping) else None
                if isinstance(router, str) and router in declared:
                    reached.setdefault(router, []).append(f"{named_loop}/{stage_name}")
    # AND THE ANSWER A PERSON TYPES. `checked-by:` is the same shape one door
    # over: a question this agent puts, and a program that reads the answer
    # before the run goes on with it.
    questions = doc.get("questions") or {}
    if isinstance(questions, Mapping):
        for asked in sorted(_questions_this_agent_puts(doc, agent)):
            q = questions.get(asked)
            if not isinstance(q, Mapping):
                continue
            checker = q.get("checked-by")
            if isinstance(checker, str) and checker in declared:
                reached.setdefault(checker, []).append(f"{asked} (checked-by)")
    for used in sorted(_as_list(agent.get("uses"))):
        tool = tools.get(used) if isinstance(tools, Mapping) else None
        if not isinstance(tool, Mapping):
            continue
        actions = tool.get("actions") or {}
        if not isinstance(actions, Mapping):
            continue
        for action_name, action in sorted(actions.items()):
            if not isinstance(action, Mapping):
                continue
            named = action.get("program")
            if isinstance(named, str) and named in declared:
                reached.setdefault(named, []).append(f"{used}/{action_name}")
    # The workspace's own boundary line, read once and carried on every program.
    # On the program rather than beside it, because a host that is starting one
    # body has the spec for that body in its hand and should not have to go and
    # find the workspace to learn whether the door may be open.
    outward = _programs_may_reach_outside(doc)
    out = []
    for name in sorted(reached):
        block = declared[name]
        block = block if isinstance(block, Mapping) else {}
        out.append(
            ProgramSpec(
                name=name,
                description=_text(block.get("description", "")),
                engine=_text(block.get("engine", "")),
                determinism=_text(block.get("determinism", "")),
                reached_by=tuple(reached[name]),
                may_reach_outside=outward,
            )
        )
    return tuple(out)


def _projections(doc: dict[str, Any], agent: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """`<tool>/<action>` → the program that shortens what it answers with.

    Walked over this agent's OWN `uses:`, like everything else here: a projection
    on a tool this agent cannot reach is not something its runs could apply.
    """
    tools = doc.get("tools") or {}
    if not isinstance(tools, Mapping):
        return ()
    out: list[tuple[str, str]] = []
    for used in sorted(_as_list(agent.get("uses"))):
        tool = tools.get(used)
        if not isinstance(tool, Mapping):
            continue
        actions = tool.get("actions") or {}
        if not isinstance(actions, Mapping):
            continue
        for action_name, action in sorted(actions.items()):
            if not isinstance(action, Mapping):
                continue
            named = action.get("projects-with")
            if isinstance(named, str) and named.strip():
                out.append((f"{used}/{action_name}", named.strip()))
    return tuple(out)


def _agent_valued(declared: Any) -> tuple[str, ...]:
    """The `run-inputs:` keys the author declared of shape `agent` (P4).

    Sorted, like `run_inputs` itself: what a document says must not depend on
    the order a loader happened to emit a map in, and this tuple decides which
    delegation edges a run admits.

    A spelling this vocabulary does not know is SKIPPED rather than raised on.
    Deciding it here would move the diagnostic for a mistyped shape out of the
    checker — where the document is in scope and the message can name the file —
    and into spec-building, which every adapter does on the way to every run.
    The unreadable line then fails where it is read, with the words the reader
    already has, and the only thing lost here is a delegation nobody could have
    intended.
    """
    if not isinstance(declared, Mapping):
        return ()
    named: list[str] = []
    for key, written in sorted(declared.items()):
        try:
            shape = Shape.parse(written)
        except Rejected:
            continue
        if shape.kind == "agent":
            named.append(str(key))
    return tuple(named)


def _takes(tool: dict[str, Any]) -> dict[str, Any]:
    """One tool's arguments, as the model is shown them.

    Every action's `takes:` block, merged — the model calls the TOOL and names
    the action, so one argument list per tool is what it can act on. Two actions
    naming the same argument mean the same thing by it; that is what makes them
    actions of one tool rather than two tools.

    `parameters` was `{}` by default and never assigned, so every tool in every
    workspace was offered with no arguments at all, and `inspects:`, `bind:` and
    `same-request-key:` all named arguments nothing declared.

    A BOUND argument is left out, because `bind:`'s own help says the model
    "cannot see them, name them, or change them" and the model sees exactly this
    dict. It was in here, so on the shipped fixture the model was offered
    `account` — the argument whose whole purpose is that the model does not
    choose it — and could have written any value, which the author's own bind
    then quietly overwrote. Offered-and-overwritten is the worst of the three
    possible behaviours: the model spends a decision on a value that is thrown
    away, and a reader of the trace cannot tell which one the tool got.

    Left out only when EVERY action taking that argument binds it. One action
    binding `account` and another taking it from the model is a real thing to
    write, and the argument is still the second action's to fill.
    """
    out: dict[str, Any] = {}
    actions = tool.get("actions") or {}
    if isinstance(actions, dict):
        asked: dict[str, int] = {}
        bound: dict[str, int] = {}
        for name, action in sorted(actions.items()):
            if not isinstance(action, dict):
                continue
            takes = action.get("takes") or {}
            binds = action.get("bind") or {}
            if isinstance(takes, dict):
                for arg, shape in takes.items():
                    out.setdefault(str(arg), str(shape))
                    asked[str(arg)] = asked.get(str(arg), 0) + 1
                    if isinstance(binds, dict) and str(arg) in binds:
                        bound[str(arg)] = bound.get(str(arg), 0) + 1
        for arg, times in asked.items():
            if bound.get(arg, 0) == times:
                out.pop(arg, None)
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


def _remembers(tool: dict[str, Any]) -> dict[str, str]:
    """One tool's `remember-as:` lines, per action.

    Keyed the way `_binds` is, and for the same reason: two actions of one tool
    keeping their answers under different names is an ordinary thing to write.
    """
    out: dict[str, str] = {}
    actions = tool.get("actions") or {}
    if not isinstance(actions, dict):
        return out
    for name, action in sorted(actions.items()):
        if not isinstance(action, dict):
            continue
        named = action.get("remember-as")
        if isinstance(named, str) and named.strip():
            out[str(name)] = named.strip()
    return out


def _reaches(tool: Any, resources: Any) -> "Reach | None":
    """Where one tool goes, read off the tool's own three candidate lines.

    `crates/pact-loader/src/reach.rs` guarantees that exactly one of them is
    written — a tool with none and a tool with two are both errors, and it
    reproduces on the shipped example what each cost before it existed. This
    still counts rather than trusting the count, because the guarantee belongs
    to the loader and this function's argument is a document, which is not the
    same thing: a host may hand `AgentSpec.from_document` a document it built
    itself, and "the checker would have caught it" is not a property of the
    object in front of you.

    So both wrong shapes survive as facts a reader can act on. None written is
    `None`, which a bridge refuses; more than one keeps the first in schema
    order AND names the rest on `also_written`, so refusing is possible without
    the reader re-deriving what was in the file.
    """
    if not isinstance(tool, Mapping):
        return None
    written: list[tuple[str, str]] = []
    for way in WAYS_A_TOOL_REACHES:
        said = tool.get(way)
        # `connect:` with nothing after it is the commonest half-finished line
        # there is, and `reach.rs` refuses it for that reason. Reading it as an
        # answer here would put an empty server name on the far side of the
        # boundary, where the failure is a call to nowhere rather than a message.
        if isinstance(said, str) and said.strip():
            written.append((way, said.strip()))
    if not written:
        return None
    kind, value = written[0]
    entry = resources.get(value) if kind == "connect" and isinstance(resources, Mapping) else None
    return Reach(
        kind=kind,
        value=value,
        method=_text(tool.get("method", "")) if kind == "url" else "",
        resource=_resource(value, entry) if isinstance(entry, Mapping) else None,
        also_written=tuple(way for way, _ in written[1:]),
    )


def _resource(name: str, entry: Mapping[str, Any]) -> "ResourceSpec":
    """One entry of `resources:`, as the tool that connects to it needs it.

    Read here rather than wherever a bridge happens to want it, because
    `endpoint:` and `auth.by-reference:` are references a HOST resolves and the
    only thing this side may do with them is carry them intact. A reader that
    went back to the document for them would be a second copy of this walk, and
    two walks over `resources:` is how `connections_needing_permission` came to
    take the first entry with an `asks-to-connect:` line and hand it to an agent
    that could not reach that server.
    """
    auth = entry.get("auth")
    return ResourceSpec(
        name=name,
        kind=_text(entry.get("resource-kind", "")),
        endpoint=_text(entry.get("endpoint", "")),
        # `auth:` is a `group:credential-reference` with one required key. The
        # value never travels — a spec file may not contain a credential, ever —
        # so what crosses is the NAME the platform team publishes for where it
        # is kept.
        auth_by_reference=(
            _text(auth.get("by-reference", "")) if isinstance(auth, Mapping) else ""
        ),
        asks_to_connect=_text(entry.get("asks-to-connect", "")),
        # AD-71. Read here beside the other four for the reason this function
        # exists at all: a bridge that went back to the document for them would
        # be a second walk over `resources:`, and the pin has to arrive on the
        # same object as the endpoint it is a pin ON. Absence is carried as
        # absence — `""` and `None` — because "no pin" and "a pin that no longer
        # matches" are different facts and only one of them is an attack.
        tool_snapshot_digest=_text(entry.get("tool-snapshot-digest", "")),
        tool_snapshot_taken_at=_text(entry.get("tool-snapshot-taken-at", "")),
        # Through `limits.seconds`, not a table here: `30d` is the same length of
        # time in this field as in `runs-for-at-most`, and two readers of one
        # grammar drift the moment nobody is looking.
        tool_snapshot_max_age=_seconds(entry.get("tool-snapshot-max-age")),
        description=_text(entry.get("description", "")),
    )


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
