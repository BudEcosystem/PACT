"""Score a suite and print a verdict — the command a support lead types.

`evals.py` could grade a run and had no way to be *run*: no entry point, no
console script, no `main`. So the author of `examples/refund-desk/evals/suite.yaml`
— six cases, a 70% bar, four rules — had to write Python to find out whether
their agent passes. D14 rules out "experts write code for that" for every
capability in the core, and running the checks you wrote is core: it is also the
mechanism the model-portability figure and the learning gate are computed from,
so the one number nobody could reproduce by hand was the number everything
downstream inherited.

**Why this is a Python entry point and not `pact eval`.** A `pact eval` in the
Rust CLI would keep one command surface, and it would cost two things this
project has decided against. `crates/pact-cli/src/main.rs` opens by saying every
command it has is *deliberately read-only* — *"Neither ever executes author
code. Validation that runs the thing being validated is not validation, it is a
supply-chain hazard (D17, D23)"* — and scoring a suite is exactly running the
thing being validated. And the binary would acquire a Python install as a
prerequisite for a command it advertises, on a distribution whose whole claim is
that the tree needs no build step (D2). The port that runs models is this one,
so the command that runs models lives here and says so. `pact check` still tells
you whether the suite is *well-formed*; this tells you whether it *passes*.

Everything here is decidable offline (D17). The document is loaded by the real
Rust loader rather than re-read in Python, because D2 makes the tree the source
of truth and invariant P-1 forbids an adapter from re-implementing the Expansion
Rule; the model is bound from `models/catalog.yaml`, which is local; and a model
that is not being served here produces UNDECIDED with a line to type, never a
number.

Typed as:

    python -m pact_adapters.evals examples/refund-desk
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from . import egress as _egress
from .diagnostics import Problem
from .evals import (
    Case,
    CaseOutcome,
    Verdict,
    bar_of,
    case_from_a_run,
    check,
    consequential_verdict,
    metrics_of,
    rules_of,
    unenforced_rules,
    verdict,
    what_went_wrong,
)
# The same reading `must-call-before:` is decided by. Imported rather than
# re-written: two functions that answer "did this run call that tool" are two
# functions that can come to disagree, and the one that decides a rule and the
# one that decides whether money moved must be the same one.
from .evals import _calls
from .harness import RunResult, delegate_by_running, run
from .ir import AgentSpec
# The grader the author's `graded-by:` line names, and the one question about
# which weights are on this disk today. Both imported rather than written again
# here: `served_here` is already the only thing in this package that asks a
# runtime what it has, and a second asker is how a suite comes to be told a
# model is present by one function and absent by another.
from .judge import LOCAL_RUNTIME, graded_by, judge_of, local_ask, served_here
# The learning gate. Imported here because this is the only file in the package
# with a command in it, and for a round `learning.py` had no importer in `src/`
# at all — 980 lines holding the held-out split, the blast-radius classifier, the
# monthly spend cap and the drift measurement, reachable from nothing a person
# could type.
from .learning import CAN_BE_APPLIED, Learner, Outcome, Proposal
from .resolve import ModelEntry, load_catalogue, needs_of, price_of, resolve
from .slo import against_the_catalogue

#: Where the repository root is from here, so a checkout that has built the CLI
#: is found without anybody exporting anything.
REPO = Path(__file__).resolve().parents[4]

#: What a mistake in the command itself points at. The renderer wants a file and
#: a line, and a command line has exactly one of each — the same answer
#: `pact-cli`'s own `COMMAND_LINE` gives, so a person who mistypes an option
#: meets one format whichever half of the system caught it.
COMMAND_LINE = "the command line"

#: The default address a locally-served model answers on. `judge.LOCAL_RUNTIME`
#: is the same address for the same reason, and it is named there rather than
#: repeated here — one place to change when a distribution serves elsewhere.
#: `--serving-at` overrides it, because an air-gapped box very often serves its
#: models somewhere else and needing to edit Python for that is the thing this
#: file exists to stop.
DEFAULT_SERVING_AT = LOCAL_RUNTIME

#: Hosts that are still this machine. Used to refuse `--serving-at` pointing off
#: the box when `workspace.yaml` says the model call may not leave it — a
#: workspace with `allow-egress: []` that scores itself against a model over the
#: network has had its one governance line quietly turned off.
ON_THIS_MACHINE = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0", ""})

#: What `population:` means for the sentence a report prints about its own
#: number. The schema's help for that field ends *"Reports say so out loud"*, and
#: for a round no report said anything: `population:` appeared in zero source
#: files across `crates/*/src` and both adapters. A required, `tier: core` field
#: making a claim about reports that no report kept.
POPULATION_SAYS: dict[str, str] = {
    "authored-enumeration": (
        "the situations you wrote down yourself, so that is what this score "
        "describes — not everything a customer might send"
    ),
    "promoted-traces": (
        "real conversations somebody promoted into examples, so this score "
        "describes the traffic you have already seen"
    ),
    "sampled-frame": (
        "a sample drawn from a stated frame, so this score carries whatever "
        "error that sample has"
    ),
}

USAGE = """\
pact_adapters.evals — score a PACT agent against the checks its author wrote

USAGE:
    ./scripts/pact-eval [PATH] [OPTIONS]
    python -m pact_adapters.evals [PATH] [OPTIONS]

Both run the same thing. The first is a wrapper that finds an interpreter with
this adapter's dependencies; the second needs `adapters/python/src` on
PYTHONPATH. PATH is required — a folder scored by accident because it happened
to be the working directory is a number about the wrong agent.

OPTIONS:
    --agent NAME        Which agent to score. Defaults to the one whose
                        `evals:` line names the suite.
    --model NAME        Which model to score it on — a name from
                        `models/catalog.yaml`. Defaults to the agent's own
                        `model:` line, and if it has none, to the cheapest
                        row that meets its `needs:` — admissibility only, on
                        the figures the catalogue publishes.
    --choose-model      Do not take a model on trust: RUN the author's cases
                        against each candidate, in the order their `variants:`
                        are written, and bind the first that passes the bar.
                        If none does, refuse and name the cheapest that would.
                        This is the measured form of the line above, and it
                        costs one model call per case per candidate.
    --serving-at URL    Where that model is being served. Defaults to
                        http://localhost:11434/v1
    --from-trace FILE   Promote a recorded run into an eval case, and
    --called NAME       write it to this agent's own `cases/` folder. FILE is
                        what `RunResult.as_record(asked)` produced. The case
                        arrives with an EMPTY `expect:`, so `pact check`
                        refuses it until a person says what should have
                        happened — the answer the run gave is the wrong one,
                        and writing it into `expect:` would make the bug the
                        specification. What the run actually did is kept
                        beside it under `went-wrong:` so you can see it while
                        writing the right answer.
    --propose FIELD=FILE
                        Put a proposed rewrite through the author's own
                        learning gate instead of scoring the agent as it
                        stands. FILE holds the new wording; the current
                        wording is read off the agent, never typed. The gate
                        locks the held-out split, classifies the blast radius,
                        applies `learning.yaml`'s `enabled:` and
                        `cycle-limits:`, measures drift against the frozen
                        baseline, and compares held-out scores. Nothing here
                        invents a proposal — a person writes it, PACT answers
                        whether it may be applied and whether it helps.
    --help              Show this message (also written -h)

EXIT CODES:
    0  PASS       1  FAIL       2  UNDECIDED       3  nothing could be read

    With `--propose`, 0 means the gate applied the change and 1 means it did
    not. 1 is the ordinary answer for a workspace whose `enabled:` is
    `propose-only`: the gate held the edit for a person, which is it working.
"""


# ────────────────────────────────────────────────────────────────── the report


@dataclass
class Scored:
    """Everything one scoring run has to say, before it is words.

    A record rather than printing as it goes, so the exit code, the test and the
    text are all reading the same facts. Every field here appears in `render`:
    a fact collected and not printed is the failure this file was written to
    close, one level up.
    """

    #: Where and what was scored.
    workspace: str = ""
    agent: str = ""
    agent_name: str = ""
    suite: str = "evals/suite.yaml"
    #: How many examples the author wrote. Carried separately from
    #: `verdict.results`, which is empty on every run that never got as far as
    #: scoring — and "0 examples" would read as an empty suite rather than as a
    #: suite nothing could be run against.
    cases: int = 0
    #: The author's own bar, from `must-pass:`.
    bar: float = 0.0
    #: What `population:` says this score is a score OF.
    population: str = ""
    #: Which model, and the sentence saying how it came to be that one.
    model: str = ""
    model_because: str = ""
    #: The suite verdict, never flattened: PASS, FAIL or UNDECIDED.
    verdict: Verdict = field(default_factory=lambda: Verdict("UNDECIDED", 0.0, 0.0, []))
    #: What the author's `finishes-within:` promise measured out at, or the
    #: refusal to claim one. Never a bare number: `Slo.assess` answers
    #: `UNGOVERNED` when nothing was promised and `UNDECIDED (n samples, need
    #: 20 for p95)` when a suite is too small to support a percentile, which is
    #: the honest answer for every suite this size and the reason the figure is
    #: worth printing at all.
    latency: str = "UNGOVERNED"
    #: The money-moving subset, graded at 100% because it is a correctness
    #: invariant and not a rate (AD-58a).
    money: Verdict = field(default_factory=lambda: Verdict("PASS", 1.0, 1.0, []))
    #: Rules the author wrote that nothing here could carry out, in their words.
    unenforced: tuple[str, ...] = ()
    #: Everything else this run could not do — approvals suppressed, tools with
    #: nothing behind them, ceilings nobody could measure.
    caveats: tuple[str, ...] = ()
    #: The command that reproduces this, exactly.
    reproduce: str = ""
    #: A mistake that stopped the whole thing, in the four-part form.
    problem: "Problem | None" = None

    @property
    def exit_code(self) -> int:
        """0 pass, 1 fail, 2 undecided, 3 nothing could be read.

        A money-moving failure is a failure of the whole thing, whatever the
        average says. AD-58a is explicit that those assertions are correctness
        invariants and not a rate — so a report that printed `VERDICT: PASS` and
        exited 0 while a refund had been issued without the order being looked up
        would be the exact hiding-inside-a-good-average the rule exists to
        prevent, one layer up from where it was fixed.
        """
        if self.problem is not None:
            return 3
        if self.money.outcome == "FAIL":
            return 1
        return {"PASS": 0, "FAIL": 1}.get(self.verdict.outcome, 2)


def render(scored: Scored) -> str:
    """The report, in words a person who cannot write code can act on."""
    if scored.problem is not None:
        return str(scored.problem)

    out: list[str] = []
    out.append(f"{scored.agent_name or scored.agent} — {scored.workspace}")
    out.append("")
    out.append(
        f"  checks   {scored.suite} — {scored.cases} examples, "
        f"{scored.bar:.0%} of them must come out right"
    )
    if scored.population:
        out.append(f"  which are {scored.population}")
    out.append(f"  model    {scored.model or 'none'} — {scored.model_because}")

    if scored.verdict.results:
        out.append("")
        for result in scored.verdict.results:
            mark = "PASS" if result.passed else "FAIL"
            out.append(f"  {mark}  {result.key}")

    out.append("")
    out.append(_verdict_line(scored))
    # Every failure, with the reason `CaseOutcome.why` already carries. Not the
    # first five: a report that truncates the failures is a report that hides the
    # one the author needed.
    for failed in scored.verdict.failures:
        out.append(f"    - {failed.key}: {failed.why}")

    out.append("")
    out.append(_money_line(scored))
    out.append(_latency_line(scored))

    if scored.unenforced:
        out.append("")
        out.append(
            f"NOT CHECKED — {len(scored.unenforced)} rule(s) you wrote that this run "
            f"could not apply. A green score above does not cover these:"
        )
        for line in scored.unenforced:
            out.append(f"    - {line}")

    if scored.caveats:
        out.append("")
        out.append(
            f"HOW THIS RUN DIFFERED FROM A REAL ONE — {len(scored.caveats)} thing(s):"
        )
        for line in scored.caveats:
            out.append(f"    - {line}")

    out.append("")
    out.append(f"Run this again with:  {scored.reproduce}")
    return "\n".join(out) + "\n"


def _verdict_line(scored: Scored) -> str:
    v = scored.verdict
    if v.outcome == "UNDECIDED":
        # Never flattened into FAIL. A suite too small to support its own bar,
        # or a model nothing could reach, has produced no evidence — and
        # reporting "no evidence" as "failed" is the statistical hole `verdict()`
        # was written to close, wearing a different hat.
        return f"VERDICT: UNDECIDED — {v.note or 'nothing was scored'}"
    right = sum(1 for r in v.results if r.passed)
    head = (
        f"VERDICT: {v.outcome} — {right} of {len(v.results)} came out right "
        f"({v.score:.0%}); {scored.suite} asks for {v.bar:.0%}."
    )
    if v.note:
        head += f" {v.note}"
    if v.outcome == "PASS" and scored.money.outcome == "FAIL":
        # Said here and not only on the MONEY line below, because this is the one
        # place a reader in a hurry looks. A suite over its bar with a wrong
        # refund inside it has not passed.
        head += (
            "\n  NOT SHIPPABLE, though: an example that moved money came out "
            "wrong, and an average cannot excuse that. See MONEY below."
        )
    if v.outcome == "FAIL":
        head += "\n  What went wrong:"
    return head


def _latency_line(scored: Scored) -> str:
    """The author's latency promise, and what this run can honestly say about it.

    `UNGOVERNED` prints nothing at all — a reader who wrote no `finishes-within:`
    does not need a line telling them so, and `Slo` already keeps `feel:`'s
    defaults out of `unmetered` for exactly that reason.
    """
    if scored.latency == "UNGOVERNED":
        return ""
    if scored.latency.startswith("UNDECIDED"):
        # Not a failure and not a pass. Said in the same shape as an eval bar
        # over too few cases, because it is the same mistake: a percentile over a
        # handful of runs reads like evidence and is not.
        return f"  speed    no claim — {scored.latency[len('UNDECIDED '):].strip('()')}"
    return f"  speed    {scored.latency}"


def _money_line(scored: Scored) -> str:
    m = scored.money
    if not m.results:
        return (
            "MONEY: nothing to check — no example reached an action marked "
            "`spends-money: yes`."
        )
    right = sum(1 for r in m.results if r.passed)
    line = (
        f"MONEY: {m.outcome} — {right} of {len(m.results)} example(s) that moved "
        f"money came out right, and every one has to."
    )
    if m.outcome != "PASS":
        line += f"\n  {m.note}"
        for failed in m.failures:
            line += f"\n    - {failed.key}: {failed.why}"
    return line


# ─────────────────────────────────────────────────────────────────── the score


def score(
    path: "str | Path",
    *,
    agent: str = "",
    model: str = "",
    serving_at: str = DEFAULT_SERVING_AT,
    choose: bool = False,
) -> Scored:
    """Load the tree, run every case, grade it, and say what happened.

    Nothing is passed in that an author could have written down. The suite, the
    bar, the rules, the population, which agent, which model and what it needs
    all come out of their files; the two options that are not in any file —
    where the model is being served, and which of several agents to score — are
    the two this takes.
    """
    root = Path(path).resolve()
    scored = Scored(workspace=_shown(root))

    document, trouble = _load_document(root)
    if trouble is not None:
        scored.problem = trouble
        return scored

    key, trouble = _which_agent(document, agent, root)
    if trouble is not None:
        scored.problem = trouble
        return scored

    scored.agent = key
    spec = AgentSpec.from_document(document, key, source=root)
    scored.agent_name = spec.name
    # The file this agent's own `evals:` line points at, so a workspace that
    # named its checks something else is told the truth about which file the bar
    # came from. The leading `/` is how the Expansion Rule spells "from the top
    # of the workspace"; it is not part of the path anybody types.
    named = str(((document.get("agents") or {}).get(key) or {}).get("evals") or "")
    scored.suite = named.lstrip("/") or scored.suite
    scored.bar = bar_of(document)
    scored.population = POPULATION_SAYS.get(
        str((document.get("evals") or {}).get("population") or "").strip(), ""
    )
    # Every rule the FILES already say nothing can carry out — a `judged:` line
    # with no `graded-by:`, a grader in no catalogue, a rule shape this runtime
    # does not know. Collected before anything runs, so a suite that never gets
    # as far as a model still tells the author which of their rules were never
    # going to be applied.
    scored.unenforced = tuple(unenforced_rules(document, root))
    scored.reproduce = _reproduce(root, key, model, serving_at)

    # Collected from here down rather than only from the run, so a suite that
    # never reaches a model still carries what it would not have covered.
    caveats: list[str] = []
    if not named:
        # An agent scored against checks its own file does not name. A workspace
        # has one `evals:` block, so this is a real thing to do — and it is a
        # different claim from "this agent passes its checks", which is what a
        # reader will take the number for unless it is said.
        caveats.append(
            f"`{key}` does not name any checks of its own, so it was scored "
            f"against this workspace's {scored.suite}. fix: add `evals: "
            f"/{scored.suite}` to agents/{key}/agent.yaml if that is what you "
            f"meant, or score a different agent with `--agent <name>`."
        )
    scored.caveats = tuple(caveats)

    cases = Case.from_document(document)
    rules = rules_of(document)
    scored.cases = len(cases)
    scored.verdict = Verdict("UNDECIDED", 0.0, scored.bar, [])

    if not cases:
        scored.verdict = Verdict(
            "UNDECIDED", 0.0, scored.bar, [],
            f"{scored.suite} has no `cases:`, so there is nothing to score. "
            f"fix: add a case — `cases:` with `when:` and `expect:` under it.",
        )
        return scored

    if choose:
        # The measured selection (D11), which had no door until this line.
        # `resolve()` filters on `needs:`, then RUNS the author's cases against
        # each candidate strategy in declaration order and binds the first that
        # passes. For a round it worked and the only caller was a test, so
        # "PACT picks the model" was a capability of the test suite.
        chosen, trouble = _choose(document, spec, key, serving_at, root)
        if trouble is not None:
            scored.problem = trouble
            return scored
        model = chosen

    bound, why, trouble = _bind(document, spec, key, model, serving_at, root)
    scored.model = bound.name if bound is not None else (model or "")
    scored.model_because = why
    if trouble is not None:
        scored.problem = trouble
        return scored
    if bound is None:
        # The reason belongs on the verdict, which is the line a reader acts on.
        # Printing the same sentence twice makes a report look like two findings
        # and is how the one that matters stops being read.
        scored.model_because = "refused — see the verdict below"
        scored.verdict = Verdict("UNDECIDED", 0.0, scored.bar, [], why)
        return scored

    # RESOLVE TIME (AC-3.6). The model is known and the catalogue is open, so the
    # two request ceilings the author wrote can be compared against a published
    # price before a single call is made. Nothing is stopped: `Limits` does the
    # stopping at run time, and `slo.py` records why there is no second enforcer.
    # What this catches is one of the two ceilings being dead — an author who
    # wrote both believes they have both.
    disagree = against_the_catalogue(
        spec.slo, spec.limits.tokens_at_most, bound.name,
        lambda went_in, came_out: price_of(
            bound.name, went_in, came_out, workspace=root
        ),
    )
    if disagree is not None:
        scored.caveats = scored.caveats + (str(disagree),)

    tag, unreachable = _served(bound, serving_at)
    if unreachable:
        # UNDECIDED, not FAIL. Nobody answered, so nothing was measured, and
        # calling that a failure would put a model's name against six results it
        # never produced.
        scored.verdict = Verdict("UNDECIDED", 0.0, scored.bar, [], unreachable)
        return scored

    grader, no_grader = _grader(document, root, serving_at)
    if no_grader:
        _collect(caveats, [no_grader])

    transport_for = _transport_for(tag, serving_at, root)
    results, money_movers, ran, latencies = _run_every_case(
        spec, cases, rules, transport_for, document, grader, root
    )
    # The author's own `finishes-within:` against what actually happened. This
    # module's header has said all along that `Slo.assess` *"refuses rather than
    # reporting a number that reads like evidence"* — and nothing called it, so a
    # suite of six cases silently made no latency claim either way. `e2e` only:
    # the same header explains that time-to-first-token is not the time to the
    # first step, and nothing here measures it.
    scored.latency = spec.slo.assess(latencies, "e2e")
    _collect(caveats, ran)
    scored.caveats = tuple(caveats)
    if len(results) < len(cases):
        # The model answered the probe and then stopped answering. Partial
        # results are not a score of this suite: the cases that did not run are
        # not failures, they are unknowns, and averaging over what happened to
        # finish is how a suite comes to report a number about a subset.
        scored.verdict = Verdict(
            "UNDECIDED", 0.0, scored.bar, [],
            f"{bound.name} stopped answering after {len(results)} of "
            f"{len(cases)} examples, so this suite has no score. "
            f"fix: check the model is still being served at {serving_at}, "
            f"then run the command again.",
        )
        return scored
    scored.verdict = verdict(results, scored.bar)
    scored.money = consequential_verdict(results, money_movers)
    # The rules the RUN could not decide, on top of the ones the files already
    # said nothing could. Two different questions with one answer for the reader:
    # `unenforced_rules` asks what is undecidable from the document, and
    # `Verdict.unenforced` asks what nothing decided this time. An author must
    # never read a green score without also reading both.
    scored.unenforced = tuple(
        list(scored.unenforced)
        + [s for s in scored.verdict.unenforced if s not in scored.unenforced]
    )
    return scored


def _served(entry: "ModelEntry", serving_at: str) -> tuple[str, str]:
    """What the runtime at `serving_at` calls these weights, or why it cannot.

    Asked once, before any case, so a box with nothing served says so in one
    sentence instead of six identical stack traces — a raw exception reaching
    somebody who cannot write code is the one thing the diagnostic bar forbids
    outright.

    The catalogue says which runtimes *can* serve a row; only the runtime knows
    what is on this disk today, and `judge.served_here` is already the one thing
    in this package that asks it. Every spelling the row answers to is tried,
    which is what `also-known-as:` is for — `qwen2.5-vl-7b-instruct` is what a
    person types and `qwen2.5vl:7b` is what the runtime answers to.
    """
    running = served_here(serving_at)
    names = [entry.name, *sorted(entry.aliases)]
    for name in names:
        if name in running:
            return name, ""
    # Prefer a spelling that looks like a runtime tag, so the line to type is one
    # that actually works.
    tag = next((n for n in names if ":" in n), entry.name)
    if not running:
        return "", (
            f"nothing is serving models at {serving_at}, so no example was run. "
            f"fix: start the runtime that serves `{tag}` on this machine, or point "
            f"the command at the one you have with `--serving-at <address>`."
        )
    return "", (
        f"the runtime at {serving_at} has {len(running)} model(s) and `{tag}` is "
        f"not one of them, so no example was run. fix: fetch it — `ollama pull "
        f"{tag}` — or score on one it already has with `--model <name>`; it has "
        f"{', '.join(sorted(running)[:4])}."
    )


def _grader(document: dict[str, Any], root: Path, serving_at: str):
    """The judge the author's `graded-by:` line names, at THIS address.

    `judge_of` binds the default runtime when it is handed no route, and a suite
    scored on `--serving-at X` whose judge quietly ran somewhere else would put
    two models under one number. So the route is built here, against the address
    this command was pointed at, and `judge_of` is only asked once there is one
    — its document-level refusals are already on the report through
    `unenforced_rules`.
    """
    named = graded_by(document)
    if not named:
        return None, ""
    route = local_ask(named, str(root), base_url=serving_at)
    if route is None:
        return None, (
            f"`graded-by: {named}` names the model that decides your `judged:` "
            f"rules, and the runtime at {serving_at} is not serving it — so those "
            f"rules were read and not applied. fix: fetch it into that runtime, or "
            f"point `--serving-at` at one that has it."
        )
    return judge_of(document, route, workspace=root)


def _run_every_case(
    spec: AgentSpec,
    cases: list[Case],
    rules: list[Any],
    transport_for,
    document: dict[str, Any],
    grader=None,
    root: "Path | None" = None,
) -> tuple[list[CaseOutcome], set[str], tuple[str, ...], list[float]]:
    """Every case, run and graded, plus which of them moved money.

    `document` is what makes the author's own `metrics:` line reach the grading:
    the scores are read off it here rather than passed in, so scoring a folder
    applies every measure its suite names with nothing typed at the command line.
    """
    scores = metrics_of(document, root)
    # The approval gate is SUPPRESSED, and it is said out loud on the report
    # rather than left to a default nobody reads. A run that parks for a person
    # cannot be scored — every governed case would come back "did not answer"
    # and the model would be blamed for a policy doing its job. `asking_only`
    # exists for exactly this caller and says so in its own docstring; the
    # questions stay, so wording an eval asserts on is unchanged.
    ungated = spec.asking.asking_only()
    money_actions = _money_moving_actions(document, spec)
    results: list[CaseOutcome] = []
    movers: set[str] = set()
    #: How long each case took, end to end. Measured HERE rather than read off
    #: `RunResult`, because `Meter.seconds(now)` needs the clock reading the run
    #: finished at and nothing carries it out — and because `e2e` means exactly
    #: what this brackets: the whole answer, tool calls and delegation included.
    #: `Slo.assess` is what turns these into a verdict or a refusal to give one.
    latencies: list[float] = []
    caveats: list[str] = []
    if spec.asking.rules:
        caveats.append(
            "approvals did not stop anything. A run that waits for a person "
            "cannot be scored, so every rule in your `policy:` was read and none "
            "of them held a call up. fix: nothing to type — this is what scoring "
            "means; the same rules do stop a real run."
        )

    # THE TEAM RUNS. Without this, `run` gets no `ask_member`, every delegation
    # parks the run instead of asking, and each case comes back "did not answer"
    # — so scoring an agent with a `team:` measured a suspension and blamed the
    # model for it. `delegate_by_running` is a hundred lines with its own budget
    # charge-back and `Grant.spend`, and its only callers were tests.
    #
    # It is built HERE and not in `run`, and that is P-1 rather than an
    # oversight: `run` is handed an `AgentSpec` and one transport, so it has
    # neither the document a member is defined in nor a way to make a transport
    # for that member. This caller has both.
    ask_member = (
        delegate_by_running(document, lambda _member: transport_for())
        if spec.team else None
    )

    for case in cases:
        try:
            began = time.monotonic()
            result = asyncio.run(
                run(
                    spec, transport_for(), case.when, {},
                    asking=ungated, ask_member=ask_member,
                )
            )
            latencies.append(time.monotonic() - began)
        except Exception:
            # The model answered the probe and then stopped. Reported as fewer
            # results than cases, which `score` turns into UNDECIDED — never as
            # a failed case, because a case nobody could run is not a case the
            # agent got wrong.
            break
        results.append(check(case, result, rules, grader, scores))
        if set(_calls(result)) & money_actions:
            movers.add(case.key)
        _collect(caveats, _uncalled_tools(result))
        _collect(caveats, result.unenforced)
        if result.unmetered:
            _collect(caveats, [
                f"these ceilings were not measured on this run, so they stopped "
                f"nothing: {', '.join(result.unmetered)}. fix: nothing to type — "
                f"what can be measured depends on what the model reports back."
            ])
    return results, movers, tuple(caveats), latencies


def _collect(into: list[str], lines) -> None:
    """Add each line once. Six cases produce six copies of the same sentence."""
    for line in lines:
        if line not in into:
            into.append(line)


def _uncalled_tools(result: RunResult) -> tuple[str, ...]:
    """Tools this run reached with nothing behind them, in the author's terms.

    Scoring connects nothing: an MCP server is a runtime resource and inventing
    a reply for one would fabricate the evidence the score is built on. What the
    agent *did* is still recorded, so `must-call-before:` is decided exactly as
    it would be live — but what a tool would have ANSWERED is not part of this
    number, and an author reading a green score has to be told which of their
    tools never spoke.
    """
    named: list[str] = []
    for step in result.trace():
        for answer, call in zip(step.get("results") or [], step.get("tools") or []):
            if "no tool named" in str(answer):
                name = str(call.get("name") or "")
                line = (
                    f"`{name}` was called and nothing was connected to it, so what it "
                    f"would have answered is not part of this score. Whether the "
                    f"agent called it, and in what order, is. "
                    f"fix: nothing to type — connecting `{name}` is the job of "
                    f"whatever runs your agents."
                )
                if line not in named:
                    named.append(line)
    return tuple(named)


def _money_moving_actions(document: dict[str, Any], spec: AgentSpec) -> set[str]:
    """Every `<tool>/<action>` this agent can reach that moves money.

    Read from the author's own `spends-money: yes` rather than from a list here,
    which is what makes AD-58a's money-moving subset a fact about their files.
    Both spellings go in, because a call that named no action is recorded under
    the tool alone — the same latitude `must-call-before:` already allows.
    """
    out: set[str] = set()
    tools = document.get("tools") or {}
    for name in {t.name for t in spec.tools}:
        tool = tools.get(name)
        if not isinstance(tool, dict):
            continue
        for action, written in (tool.get("actions") or {}).items():
            if not isinstance(written, dict):
                continue
            if str(written.get("spends-money") or "").strip().lower() in ("yes", "true", "on"):
                out.add(f"{name}/{action}")
    return out


# ─────────────────────────────────────────────────────────────── what to score


def _load_document(root: Path) -> tuple[dict[str, Any], "Problem | None"]:
    """The tree, loaded by the real Rust loader.

    Not re-read in Python. D2 makes the folder the source of truth and the
    loader normative, and invariant P-1 says an adapter consumes the loaded
    document only — a second reader of the tree is a second Expansion Rule, and
    the two would disagree the first time somebody wrote a setting as a folder.
    """
    binary = _pact_binary()
    if binary is None:
        return {}, Problem(
            severity="error", rule="scoring/no-loader", file=COMMAND_LINE, line=1,
            message=(
                "the `pact` command is not on this machine, and it is what reads "
                "your folder"
            ),
            fix="run `cargo build -p pact-cli` in the PACT checkout, then try again",
        )
    if not root.exists():
        return {}, Problem(
            severity="error", rule="scoring/no-such-folder", file=COMMAND_LINE, line=1,
            message=f"there is no folder at {root}",
            fix="check the path, or run the command from inside your agent's folder",
        )
    done = subprocess.run(
        [str(binary), "show", str(root)], capture_output=True, text=True
    )
    if done.returncode != 0:
        return {}, Problem(
            severity="error", rule="scoring/will-not-load", file="workspace.yaml", line=1,
            message=(
                "this folder does not load, so there is nothing to score yet. "
                + (done.stderr.strip().splitlines() or ["`pact show` refused it"])[0]
            ),
            fix=f"run `pact check {root}` — it lists every problem at once, with a "
                f"line to type for each",
        )
    try:
        document = json.loads(done.stdout)
    except ValueError:
        return {}, Problem(
            severity="error", rule="scoring/will-not-load", file="workspace.yaml", line=1,
            message="the loader did not return a readable document for this folder",
            fix=f"run `pact check {root}` and fix what it names",
        )
    return document if isinstance(document, dict) else {}, None


def _pact_binary() -> "Path | None":
    """Where `pact` is: a built checkout first, then whatever is on PATH."""
    for candidate in (REPO / "target/debug/pact", REPO / "target/release/pact"):
        if candidate.exists():
            return candidate
    found = shutil.which("pact")
    return Path(found) if found else None


def _which_agent(
    document: dict[str, Any], asked: str, root: Path
) -> tuple[str, "Problem | None"]:
    """The agent to score: the one asked for, or the one that owns the suite.

    `agents/<name>/agent.yaml`'s `evals:` line points at the checks that agent is
    held to, and until this read it nothing in either adapter did — the Rust side
    checks the file it names exists and no runtime ever asked whose suite it was.
    So a workspace with three agents had no no-code way to say which one the
    score is about.
    """
    agents = document.get("agents") or {}
    if asked:
        if asked in agents:
            return asked, None
        return "", Problem(
            severity="error", rule="scoring/no-such-agent", file=COMMAND_LINE, line=1,
            message=f"`--agent {asked}` names an agent this folder does not have",
            fix=f"use one of: {', '.join(sorted(agents)) or '(this folder has none)'}",
        )
    owners = [key for key, a in sorted(agents.items()) if (a or {}).get("evals")]
    if len(owners) == 1:
        return owners[0], None
    if not owners and len(agents) == 1:
        return next(iter(agents)), None
    if not owners:
        return "", Problem(
            severity="error", rule="scoring/nobody-owns-the-checks",
            file="agents/<name>/agent.yaml", line=1,
            message=(
                "no agent in this folder says which checks it is held to, so there "
                "is nothing to score"
            ),
            fix="add `evals: /evals/suite.yaml` to the agent you want scored, or "
                "run the command again with `--agent <name>`",
        )
    return "", Problem(
        severity="error", rule="scoring/several-suites",
        file="agents/<name>/agent.yaml", line=1,
        message=f"{len(owners)} agents here name checks, so it is not clear which to score",
        fix=f"run the command again with `--agent <name>`, one of: {', '.join(owners)}",
    )


# ──────────────────────────────────────────────────────────────── which model


def _choose(
    document: dict[str, Any],
    spec: AgentSpec,
    key: str,
    serving_at: str,
    root: Path,
) -> tuple[str, "Problem | None"]:
    """Run the author's cases against each candidate and return the one that passes.

    Distinct from `_bind`, which decides ADMISSIBILITY from what the catalogue
    publishes. This decides whether the model can actually do the job, by doing
    it — which is the only honest answer for behaviour that is probabilistic, and
    the whole of T4.

    Refusal is the useful outcome: when nothing passes, `resolve()` names the
    cheapest row that would, and that sentence is returned rather than a number.
    """
    catalogue = load_catalogue(workspace=root)
    entries = list(catalogue.entries)
    if not entries:
        return "", Problem(
            severity="error", rule="scoring/no-catalogue", file=COMMAND_LINE, line=1,
            message="there is no model catalogue to choose from",
            fix="add `models/catalog.yaml` to this workspace, or name a model "
                "with `--model`",
        )
    asked = spec.model or entries[0].name
    report = resolve(
        spec,
        document,
        asked,
        # The same two seams the scoring path already uses, so a chosen model
        # is measured exactly as a named one is — one transport per case, and the
        # author's own `graded-by:` judge.
        transport_for=lambda name: _transport_for(name, serving_at, root)(),
        catalogue=entries,
        agent_key=key,
        judge=judge_of(document, workspace=root)[0],
    )
    if report.verdict.outcome == "PASS":
        return report.model, None
    return "", Problem(
        severity="error", rule="scoring/no-model-passes", file=COMMAND_LINE, line=1,
        message=report.render(),
        fix=report.recommendation
        or "lower `must-pass:`, add a `variants:` strategy, or serve a stronger model",
    )


def _bind(
    document: dict[str, Any],
    spec: AgentSpec,
    key: str,
    asked: str,
    serving_at: str,
    root: Path,
) -> tuple["ModelEntry | None", str, "Problem | None"]:
    """Which model this suite is scored on, and the sentence explaining why.

    A score is a claim about ONE model — that is the whole of T4 and of D11 — so
    the report never prints a number without printing which model produced it and
    how that model came to be chosen.

    The author's `needs:` block decides admissibility, not preference. A model
    that cannot see the photos the cases attach would produce a number about a
    different agent, so it is refused here with the reason `satisfies` gives and
    the cheapest row that does qualify is named — which is D11's obligation to
    recommend rather than merely gate.
    """
    catalogue = load_catalogue(workspace=root)
    needs = needs_of(document, key)
    written = _needs_file(root, key)

    wanted, because = asked, "you asked for it with `--model`"
    if not wanted and spec.model:
        wanted, because = spec.model, f"`model:` in agents/{key}/agent.yaml pins it"
    if not wanted:
        picked = _cheapest_that_qualifies(catalogue.entries, needs)
        if picked is None:
            return None, (
                f"no model in `models/catalog.yaml` meets what {written} asks for, "
                f"so there is nothing to score this on. fix: relax one line in "
                f"that file, or add a row for a model this machine serves to your "
                f"own `models/catalog.yaml`."
            ), None
        # The catalogue's own `default:` wins where it qualifies, because that is
        # the promise the schema makes on `model:` — "Leave this out and PACT
        # picks". Where it does not qualify, picking it anyway would be picking a
        # model the author's own `needs:` refuses.
        fallback = catalogue.get(catalogue.default)
        if fallback is not None and fallback.satisfies(needs)[0]:
            picked = fallback
        wanted = picked.name
        because = (
            f"nothing pins a model, so PACT picked the cheapest one that meets "
            f"{written}"
        )

    entry = catalogue.get(wanted)
    if entry is None:
        return None, "", Problem(
            severity="error", rule="scoring/no-such-model",
            file="models/catalog.yaml", line=1,
            message=f"`{wanted}` is not a model this machine has a row for",
            fix="use one of: "
                + ", ".join(sorted(e.name for e in catalogue.entries)),
        )

    ok, why = entry.satisfies(needs)
    if not ok:
        better = _cheapest_that_qualifies(catalogue.entries, needs, exclude=entry.name)
        advice = (
            f" `{better.name}` does meet it — score on that with "
            f"`--model {better.name}`."
            if better is not None
            else " Nothing in the catalogue meets it."
        )
        return None, (
            f"`{entry.name}` {why}, and {written} says it has to. Scoring on it "
            f"would produce a number about a different agent.{advice}"
        ), None

    off_box = _off_this_machine(serving_at)
    if needs.get("must-stay-on-this-machine") and off_box:
        # Name the role that is actually missing, and quote the line as written.
        # This message hardcoded `llm` in both halves, which was true only while
        # `llm` was the one role anything read: an agent that `accepts:` a voice
        # message under `allow-egress: [llm]` is refused for `stt`, and telling
        # that author their file "does not list `llm`" when it plainly does is
        # ledger row R56 happening a second time in a second language.
        wants = needs.get("egress-missing") or ("llm",)
        return None, "", Problem(
            severity="error", rule="scoring/egress-refused",
            file="workspace.yaml", line=1,
            message=(
                f"`--serving-at {serving_at}` sends every case to {off_box}, and "
                f"this workspace says `allow-egress: {_egress.listed(document)}` "
                f"— nothing there names {_egress.grants(wants)}"
            ),
            fix="serve the model on this machine and point `--serving-at` at it, "
                f"or add `- {wants[0]}` under `allow-egress:` — which is a change "
                "a person has to approve",
        )
    return entry, because, None


def _needs_file(root: Path, key: str) -> str:
    """The file this agent's `needs:` block was written in, as the author sees it.

    Two spellings, because both are the Expansion Rule's: a `needs.yaml` beside
    `agent.yaml`, or a `needs:` block inside it. A diagnostic that names the
    first when the tree has the second sends somebody to a file that is not
    there, which is the one failure `diagnostics.py` exists to stop.
    """
    if (root / "agents" / key / "needs.yaml").exists():
        return f"agents/{key}/needs.yaml"
    return f"the `needs:` block in agents/{key}/agent.yaml"


def _cheapest_that_qualifies(
    entries, needs: dict[str, Any], exclude: str = ""
) -> "ModelEntry | None":
    """The first model D11 would offer: cheapest that meets the author's needs."""
    ranked = sorted(
        (e for e in entries if e.name != exclude and e.satisfies(needs)[0]),
        key=lambda e: e.ranks_after(needs),
    )
    return ranked[0] if ranked else None


def _off_this_machine(serving_at: str) -> str:
    """The host `serving_at` points at, or `""` when it is still this machine."""
    host = (urlparse(serving_at).hostname or "").strip().lower()
    return "" if host in ON_THIS_MACHINE else host


def _transport_for(served_as: str, serving_at: str, root: Path):
    """A fresh transport per case, bound to `served_as` on the local runtime.

    Fresh per case for the reason `resolve.evaluate` builds one per case: a
    transport carries what the LAST call used, and six cases sharing one would
    price the sixth against the fifth.

    `workspace=` is passed so a row this machine added to its own
    `models/catalog.yaml` is priced and sized — the case that layer exists for is
    exactly an air-gapped box serving a model the distribution has never heard
    of, and it is where a suite is most likely to be scored.
    """
    from .transports.ollama_transport import OllamaTransport

    def build():
        return OllamaTransport(
            served_as, base_url=serving_at, workspace=str(root), timeout=600.0
        )

    return build


# ─────────────────────────────────────────────────────────────── the command


def _reproduce(root: Path, agent: str, model: str, serving_at: str) -> str:
    """The exact line that runs this again.

    Printed because the complaint this whole file answers is a number nobody can
    reproduce by hand, and a report that does not say how it was produced is a
    number of that kind however it was computed.

    `PACT_EVAL_COMMAND` is set by `scripts/pact-eval`, which is the spelling a
    reader who got here through that wrapper can actually retype — the module
    form needs the adapter's `src/` on `PYTHONPATH`, and printing a line that
    only works for whoever already knew that would be the same failure one step
    along.
    """
    typed = os.environ.get("PACT_EVAL_COMMAND") or "python -m pact_adapters.evals"
    line = f"{typed} {_shown(root)} --agent {agent}"
    if model:
        line += f" --model {model}"
    if serving_at != DEFAULT_SERVING_AT:
        line += f" --serving-at {serving_at}"
    return line


def _shown(root: Path) -> str:
    try:
        return str(root.relative_to(Path.cwd()))
    except ValueError:
        return str(root)


# ──────────────────────────────────────────── proposing one improvement (T6)


@dataclass
class Proposed:
    """What one learning cycle has to say, before it is words.

    A record for the same reason `Scored` is one: the exit code, the test and
    the text then read the same facts.
    """

    workspace: str = ""
    agent: str = ""
    field: str = ""
    #: Where the new wording was read from, so the report names it.
    source: str = ""
    outcome: "Outcome | None" = None
    problem: "Problem | None" = None

    @property
    def exit_code(self) -> int:
        if self.problem is not None or self.outcome is None:
            return 3
        # 1 means the gate did not apply it, which for a workspace whose
        # `enabled:` is `propose-only` is the CORRECT and expected answer — not a
        # malfunction. The report says which of the gates held; the exit code
        # only says whether the file changed.
        return 0 if self.outcome.applied else 1


def _proposal(
    spec: AgentSpec, raw: str, root: Path
) -> tuple["Proposal | None", "Problem | None"]:
    """`FIELD=FILE` into a proposal against what the agent says today.

    The `before` side is never typed: it is read off the loaded spec, so a
    proposal cannot claim the agent currently says something it does not — which
    is what the drift measurement and the whole `unified_diff` are computed from.
    """
    name, sep, where = raw.partition("=")
    if not sep or not where.strip():
        return None, Problem(
            severity="error", rule="scoring/propose-wants-a-field-and-a-file",
            file=COMMAND_LINE, line=1,
            message=f"`--propose {raw}` does not say which field and which file",
            fix="write it as `--propose FIELD=FILE`, as in "
                "`--propose instructions=better-instructions.md`",
        )
    if name not in CAN_BE_APPLIED:
        return None, Problem(
            severity="error", rule="scoring/propose-cannot-apply-that-field",
            file=COMMAND_LINE, line=1,
            message=f"a learning cycle cannot put a change to `{name}` into "
                    f"effect: nothing in a run reads it, so both scoring runs "
                    f"would grade the same agent",
            fix=f"the fields a cycle applies are: {', '.join(CAN_BE_APPLIED)}",
        )
    candidate = Path(where.strip())
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        after = candidate.read_text()
    except OSError as trouble:
        return None, Problem(
            severity="error", rule="scoring/propose-file-cannot-be-read",
            file=str(candidate), line=1,
            message=f"the proposed {name} could not be read: {trouble.strerror or trouble}",
            fix=f"write the new {name} into that file, or point `--propose` at "
                f"one that exists",
        )
    before = getattr(spec, name, "")
    if after.strip() == str(before).strip():
        return None, Problem(
            severity="error", rule="scoring/propose-changes-nothing",
            file=str(candidate), line=1,
            message=f"the proposed {name} is what the agent already says",
            fix="edit that file so it differs, or drop `--propose` and score "
                "the agent as it stands",
        )
    return Proposal(
        field=name, before=str(before), after=after,
        rationale=f"proposed at the command line from {_shown(candidate)}",
    ), None


def propose(
    path: "str | Path",
    *,
    change: str,
    agent: str = "",
    model: str = "",
    serving_at: str = DEFAULT_SERVING_AT,
) -> Proposed:
    """Put one proposed edit through the author's own learning gate.

    The gate is the point, not the edit. `Learner.cycle` locks the held-out
    split, classifies the blast radius, checks the author's `enabled:` and
    `cycle-limits:`, measures cumulative drift against the frozen baseline, and
    only then compares held-out scores — and the module carrying all of that had
    **no importer in `src/`**, so every one of those gates was a capability of
    the test suite.

    The proposal comes from a person because nothing here generates one: there
    is no optimiser (AC-3.5), and inventing one silently would be the opposite
    of what D23 asks for. What PACT owns is the answer to *"may this be
    applied, and does it actually help"*.
    """
    root = Path(path).resolve()
    out = Proposed(workspace=_shown(root))

    document, trouble = _load_document(root)
    if trouble is not None:
        out.problem = trouble
        return out

    key, trouble = _which_agent(document, agent, root)
    if trouble is not None:
        out.problem = trouble
        return out
    out.agent = key
    spec = AgentSpec.from_document(document, key, source=root)

    proposal, trouble = _proposal(spec, change, root)
    if trouble is not None:
        out.problem = trouble
        return out
    assert proposal is not None
    out.field, out.source = proposal.field, proposal.rationale

    bound, why, trouble = _bind(document, spec, key, model, serving_at, root)
    if trouble is not None:
        out.problem = trouble
        return out
    if bound is None:
        # `why` is the whole answer and this line used to discard it, printing
        # "name one with `--model`" to somebody who had just named one with
        # `--model`. `_bind` has already worked out which `needs:` row refused it
        # and which catalogue row would satisfy it; re-summarising that as
        # "no model qualifies" is exactly the D11 failure of gating without
        # recommending.
        out.problem = Problem(
            severity="error", rule="scoring/no-model-to-measure-with",
            file=COMMAND_LINE, line=1,
            message=f"an improvement cannot be measured, because the suite "
                    f"cannot be scored: {why}",
            fix="satisfy the `needs:` line above, or name a model that already "
                "does with `--model`",
        )
        return out

    tag, unreachable = _served(bound, serving_at)
    if unreachable:
        out.problem = Problem(
            severity="error", rule="scoring/model-not-served",
            file=COMMAND_LINE, line=1, message=unreachable,
            fix=f"serve `{bound.name}` at {serving_at}, or point `--serving-at` "
                f"at the machine that does",
        )
        return out

    grader, _no_grader = _grader(document, root, serving_at)
    learner = Learner.from_document(
        document, spec, {},
        # The author's own grader, so a proposal is judged by the measure their
        # suite names rather than by string equality.
        judge=grader,
    )
    # `Learner._score` asks for a transport PER SPEC, not per name: it scores the
    # incumbent and the candidate, and they are two specs on one model. Fresh
    # each time for the reason `_transport_for` gives.
    build = _transport_for(tag, serving_at, root)
    out.outcome = learner.cycle(proposal, lambda _spec: build())
    return out


def _margin_line(outcome: "Any") -> str:
    """Whether the edit cleared the declared margin, in one sentence.

    Separate from `Learner.cycle`'s own `after > before`, which is the right
    question for APPLYING an edit. AC-3.5 asks whether an optimiser improves a
    score *by a declared margin*, which is the right question for CLAIMING one
    works — and a claim built on `after > before` is a claim about noise.
    """
    from .optimising import measured

    after = outcome.verdict_after
    said = measured(
        len(getattr(after, "results", ())) if after is not None else 0,
        outcome.verdict_before,
        after,
    )
    line = (
        f"  margin      {said['improved-by']:+.1%} against a declared "
        f"{said['margin-declared']:.0%} — "
        f"{'cleared' if said['cleared-the-margin'] else 'NOT cleared'}"
    )
    if not said["enough-to-mean-something"]:
        # Said out loud for the reason `Verdict` refuses a percentage over too
        # few cases: a margin cleared over three cases is not a result.
        line += (
            f"\n              (over {said['held-out-cases']} held-out case(s), "
            f"so this is not a measurement)"
        )
    return line


def render_proposal(p: Proposed) -> str:
    """The cycle as words, in the order a reviewer needs them."""
    if p.problem is not None:
        return str(p.problem)
    outcome = p.outcome
    assert outcome is not None
    # `optimising.measured` says what one improvement run can honestly claim —
    # the declared margin, whether it was cleared, and whether the held-out split
    # is big enough for the answer to mean anything. It had no caller outside its
    # own test, which made AC-3.5's *"by a declared margin"* a property of the
    # test suite. This is the one place both verdicts exist.

    lines = [
        f"{'APPLIED' if outcome.applied else 'NOT APPLIED'}  "
        f"{p.agent} · {p.field}",
        f"  workspace   {p.workspace}",
        f"  proposed    {p.source}",
        f"  blast radius {outcome.classification.risk}"
        + (f" — {outcome.classification.reason}" if outcome.classification.reason else ""),
        f"  why         {outcome.reason}",
    ]
    if outcome.verdict_before is not None and outcome.verdict_after is not None:
        lines.append(
            f"  held-out    {outcome.before_score:.0%} → {outcome.after_score:.0%}"
            f"   (drift {outcome.drift:.0%})"
        )
        # `optimising.measured`'s question, asked where both verdicts exist. It
        # had no caller outside its own test, which made AC-3.5's *"by a declared
        # margin"* a property of the test suite rather than of any report.
        lines.append(_margin_line(outcome))
    else:
        # Said out loud rather than printed as `0% → 0%`, which reads as a
        # measured tie and is the one thing it is not.
        lines.append("  held-out    not measured — refused before anything was run")
    for sentence in outcome.ungraded:
        lines.append(f"  ungraded    {sentence}")
    for sentence in outcome.unmeasured:
        lines.append(f"  unmeasured  {sentence}")
    return "\n".join(lines) + "\n"


def promote(path: "str | Path", *, record: str, called: str) -> "Problem | None":
    """Turn one recorded run into an eval case file (AC-4.4).

    The criterion asks for *one command*, and the reason it is one command is
    the moment it happens in: something went wrong in production, somebody is
    looking at it now, and the alternative is retyping the situation into a case
    file from memory tomorrow. Every minute between the two loses detail.

    **Redaction survives because of where the record comes from, not because of
    anything here.** `RunResult.as_record` carries the trace, which is what the
    run produced after its interceptor chain ran — so a card number an author's
    rule hid is already `[card number removed]` before this function sees it.
    Promoting from a raw request would reintroduce it into a file that gets
    committed, which is the one way this feature could make a workspace less
    safe than not having it.
    """
    root = Path(path).resolve()
    try:
        run_record = json.loads(Path(record).read_text())
    except (OSError, ValueError) as trouble:
        return Problem(
            severity="error", rule="scoring/trace-cannot-be-read",
            file=str(record), line=1,
            message=f"the recorded run could not be read: {trouble}",
            fix="point `--from-trace` at a file written by "
                "`RunResult.as_record(asked)`, as JSON",
        )

    document, trouble = _load_document(root)
    if trouble is not None:
        return trouble
    key, trouble = _which_agent(document, "", root)
    if trouble is not None:
        return trouble

    try:
        case = case_from_a_run(run_record, called)
    except ValueError as incomplete:
        return Problem(
            severity="error", rule="scoring/trace-is-not-a-run",
            file=str(record), line=1, message=str(incomplete),
            fix="record the run with `RunResult.as_record(asked)`, which fills "
                "in every field this needs",
        )

    suite = _suite_of(document, key, root)
    where = suite.parent / "cases" / f"{called}.yaml"
    if where.exists():
        return Problem(
            severity="error", rule="scoring/case-already-exists",
            file=_shown(where), line=1,
            message=f"there is already a case called `{called}`",
            fix="choose another name — overwriting one would lose whatever a "
                "person had already written in it",
        )
    where.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "Promoted from a run that went wrong.",
        "",
        "`expect:` is EMPTY, so `pact check` refuses this file until you fill it",
        "in. That is deliberate: the answer this run gave is the wrong one — that",
        "is why it is here — and writing it into `expect:` would make the bug the",
        "specification.",
        "",
        "Everything below `when:` has been through this workspace's own",
        "interceptors, so a value one of your rules hides is already hidden here.",
        "",
        *what_went_wrong(run_record),
    ]
    where.write_text(
        "".join(f"# {line}\n".replace("# \n", "#\n") for line in header)
        + yaml.safe_dump(case, sort_keys=False, allow_unicode=True)
    )
    sys.stdout.write(
        f"Wrote {_shown(where)}.\n"
        f"It will not pass `pact check` until you fill in `expect:` — which is "
        f"the point.\n"
    )
    return None


def _suite_of(document: dict[str, Any], key: str, root: Path) -> Path:
    """Where this agent's own `evals:` line points."""
    named = str((document.get("agents", {}).get(key) or {}).get("evals") or "")
    return root / (named.lstrip("/") or "evals/suite.yaml")


#: Every option this command takes, spelled the way it has to be typed. One
#: list, so the refusal a reader sees and the set the parser enforces cannot say
#: different things — the rule `pact-cli`'s own `OPTIONS` is held to.
OPTIONS: tuple[str, ...] = (
    "--agent", "--model", "--serving-at", "--propose", "--from-trace", "--called",
)
#: Options that are a flag rather than a name=value pair.
FLAGS: tuple[str, ...] = ("--choose-model",)


def main(argv: "list[str] | None" = None) -> int:
    """Parse, score, print, and return the exit code.

    Hand-rolled rather than `argparse`, for one reason: `argparse` answers a
    mistyped option with *"error: unrecognized arguments"* and a usage dump,
    which names no file, no line and nothing to type. Every diagnostic in this
    project has four parts and a person who cannot write code has to be able to
    act on it — the command line is not exempt, and `pact-cli` is not exempt
    from it either.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if any(a in ("--help", "-h", "help") for a in args):
        sys.stdout.write(USAGE)
        return 0

    path, options, trouble = _parse(args)
    if trouble is not None:
        sys.stderr.write(str(trouble))
        return 3

    if "--from-trace" in options:
        # A different job again: this writes a FILE rather than printing a
        # verdict, so it neither scores nor proposes.
        called = options.get("--called", "").strip()
        if not called:
            sys.stderr.write(str(Problem(
                severity="error", rule="scoring/promoted-case-needs-a-name",
                file=COMMAND_LINE, line=1,
                message="`--from-trace` writes a case file and nothing said what "
                        "to call it",
                fix="add `--called SOMETHING` — it becomes the file name and the "
                    "name the report uses when the case fails",
            )))
            return 3
        trouble = promote(path, record=options["--from-trace"], called=called)
        if trouble is not None:
            sys.stderr.write(str(trouble))
            return 3
        return 0

    if "--propose" in options:
        # A different question from scoring, so a different report and a
        # different exit code. `--choose-model` would be asking which model to
        # measure an improvement on while the improvement is what is being
        # measured, so the two are refused together rather than silently
        # combined.
        if "--choose-model" in options:
            sys.stderr.write(str(Problem(
                severity="error", rule="scoring/propose-and-choose-model",
                file=COMMAND_LINE, line=1,
                message="`--propose` and `--choose-model` ask two different "
                        "questions and cannot be answered in one run",
                fix="score the agent with `--choose-model` first to fix the "
                    "model, then run `--propose` against that model with "
                    "`--model NAME`",
            )))
            return 3
        proposed = propose(
            path,
            change=options["--propose"],
            agent=options.get("--agent", ""),
            model=options.get("--model", ""),
            serving_at=options.get("--serving-at", DEFAULT_SERVING_AT),
        )
        stream = sys.stderr if proposed.problem is not None else sys.stdout
        stream.write(render_proposal(proposed))
        return proposed.exit_code

    scored = score(
        path,
        agent=options.get("--agent", ""),
        model=options.get("--model", ""),
        serving_at=options.get("--serving-at", DEFAULT_SERVING_AT),
        choose="--choose-model" in options,
    )
    stream = sys.stderr if scored.problem is not None else sys.stdout
    stream.write(render(scored))
    return scored.exit_code


def _parse(args: list[str]) -> tuple[str, dict[str, str], "Problem | None"]:
    """One path and the three options, or a mistake said in four parts."""
    path = ""
    options: dict[str, str] = {}
    rest = list(args)
    while rest:
        token = rest.pop(0)
        if not token.startswith("-"):
            if path:
                return "", {}, Problem(
                    severity="error", rule="scoring/two-paths", file=COMMAND_LINE, line=1,
                    message=f"two folders were given — {path!r} and {token!r} — and this "
                            f"scores one at a time",
                    fix=f"run it twice: once with {path}, once with {token}",
                )
            path = token
            continue
        name, _, inline = token.partition("=")
        # A flag carries no value. Kept a separate list rather than a sentinel
        # value, so `--choose-model x` is refused rather than silently eating the
        # next token — which for this flag would be the folder.
        if name in FLAGS:
            options[name] = "yes"
            continue
        if name not in OPTIONS:
            return "", {}, Problem(
                severity="error", rule="scoring/unknown-option", file=COMMAND_LINE, line=1,
                message=f"`{name}` is not something this command takes",
                fix=f"the options are: {', '.join(OPTIONS + FLAGS)}, --help",
            )
        if not inline:
            if not rest:
                return "", {}, Problem(
                    severity="error", rule="scoring/option-needs-a-value",
                    file=COMMAND_LINE, line=1,
                    message=f"`{name}` was given with nothing after it",
                    fix=f"write the value after it, as in `{name} something`",
                )
            inline = rest.pop(0)
        options[name] = inline
    # NOT `path or "."`. The Rust CLI documents and designed against exactly this
    # — *"Typing just `pact` is the first thing a new author does, and it used to
    # mean `check .` … measured at four minutes and still going, descending into
    # `research/repos`, so the first command anybody types looked like a hang"* —
    # and this line reintroduced it. Measured: `./scripts/pact-eval` from the
    # repository root was killed at 120s and again at 25s with 0 bytes written,
    # blocked in `subprocess.run([pact, 'show', '.'])`.
    if not path:
        return "", options, Problem(
            severity="error", rule="scoring/no-folder-given", file=COMMAND_LINE, line=1,
            message="no folder was given, so there is nothing to score",
            fix="run it as `./scripts/pact-eval <folder>` — for example "
                "`./scripts/pact-eval examples/refund-desk`",
        )
    return path, options, None
