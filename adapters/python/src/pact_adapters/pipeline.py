"""The whole pipeline, as one offline run (AC-7.3).

> The full pipeline (`validate → resolve → build → eval → report`) runs offline
> against a local model, with no network dependency in the core.

Every stage already existed and **nothing composed them**, which is why the
register recorded `resolve` and `build` as *"not stages on any shipped path"*.
They were reachable — `--choose-model` reaches the resolver, `pact show` produces
the built document — but only as separate things a person had to know to run in
order.

Five stages, in the criterion's own order:

* **validate** — `pact check`. Does the tree say something coherent?
* **resolve** — which model, and why. The catalogue is read off the disk.
* **build** — `pact show`, the canonical document with its digest. This is the
  only "build" a PACT tree has, and D2 is why: the file tree is the native form
  and this is derived from it, so the stage costs reading files.
* **eval** — the author's own suite, scored on the resolved model.
* **report** — the verdict, the caveats, and every stage that could not run.

**Offline is a property, not a hope.** Nothing here opens a socket except the
eval stage's calls to a model on this machine, and a model that is not being
served produces `UNDECIDED` with the line to type — never a number and never a
network error. Each stage says which of the three it was: it ran, it was refused
with a reason, or it could not be attempted and why.

**A stage that cannot run does not fail the pipeline.** A workspace on a machine
with no model served should still get `validate`, `resolve` and `build` — those
are the four fifths of this that need nothing but the tree, and a person fixing a
document needs them long before they have weights.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: The stages, in the order AC-7.3 names them.
STAGES = ("validate", "resolve", "build", "eval", "report")

#: What a stage can come to.
RAN = "ran"
REFUSED = "refused"
NOT_ATTEMPTED = "not-attempted"


@dataclass
class Stage:
    """One stage, and which of the three things happened to it."""

    name: str
    outcome: str
    said: str = ""
    #: Whatever the stage produced that a later one needs.
    gave: Any = None

    def line(self) -> str:
        mark = {RAN: "ok", REFUSED: "REFUSED", NOT_ATTEMPTED: "--"}[self.outcome]
        return f"  {mark:>8}  {self.name:<9} {self.said}"


@dataclass
class Pipeline:
    """Every stage, and whether the whole thing got to an answer."""

    workspace: str
    stages: list[Stage] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        # A REFUSAL fails; a stage that could not be attempted does not. A
        # machine with no model served still gets a validated, resolved, built
        # tree, and telling somebody their document is wrong because their laptop
        # has no weights on it would be answering a question they did not ask.
        return 1 if any(s.outcome == REFUSED for s in self.stages) else 0

    def render(self) -> str:
        out = [f"{self.workspace}", ""]
        out += [s.line() for s in self.stages]
        out.append("")
        missed = [s for s in self.stages if s.outcome == NOT_ATTEMPTED]
        if missed:
            out.append(
                f"{len(missed)} stage(s) could not be attempted. That is not a "
                f"failure of the tree — see the reason beside each."
            )
        refused = [s for s in self.stages if s.outcome == REFUSED]
        out.append(
            "The pipeline did not complete." if refused
            else "Every stage that could run, ran."
        )
        return "\n".join(out) + "\n"


def _pact_binary() -> "Path | None":
    here = Path(__file__).resolve().parents[4] / "target" / "debug" / "pact"
    return here if here.exists() else None


def run_pipeline(path: "str | Path", *, serving_at: str = "") -> Pipeline:
    """Every stage over one workspace, offline."""
    from .scoring import DEFAULT_SERVING_AT, score

    root = Path(path).resolve()
    out = Pipeline(workspace=str(root))
    serving_at = serving_at or DEFAULT_SERVING_AT

    pact = _pact_binary()
    if pact is None:
        for name in STAGES:
            out.stages.append(Stage(
                name, NOT_ATTEMPTED,
                "the loader is not built — `cargo build -p pact-cli`",
            ))
        return out

    # ── validate ────────────────────────────────────────────────────────────
    checked = subprocess.run(
        [str(pact), "check", str(root)], capture_output=True, text=True
    )
    if checked.returncode != 0:
        out.stages.append(Stage(
            "validate", REFUSED,
            f"{checked.stdout.strip().splitlines()[-1] if checked.stdout.strip() else 'refused'}",
        ))
        # Nothing downstream can mean anything about a tree the checker refused.
        for name in STAGES[1:]:
            out.stages.append(Stage(name, NOT_ATTEMPTED, "the tree did not validate"))
        return out
    out.stages.append(Stage(
        "validate", RAN, checked.stdout.strip().splitlines()[-1]
    ))

    # ── build ───────────────────────────────────────────────────────────────
    # Out of order deliberately: `resolve` needs the document to know what the
    # agent's `needs:` block says, so the build has to happen first. Reported in
    # the criterion's order below, which is the order a reader thinks in.
    shown = subprocess.run(
        [str(pact), "show", str(root)], capture_output=True, text=True
    )
    document = json.loads(shown.stdout)
    digest = subprocess.run(
        [str(pact), "discover", str(root)], capture_output=True, text=True
    )
    fingerprint = ""
    try:
        found = json.loads(digest.stdout)
        fingerprint = (found[0] if isinstance(found, list) else found).get("digest", "")
    except (ValueError, IndexError, AttributeError):
        fingerprint = ""

    # ── resolve ─────────────────────────────────────────────────────────────
    from .ir import AgentSpec
    from .scoring import _bind, _which_agent

    agent, trouble = _which_agent(document, "", root)
    if trouble is not None:
        out.stages.append(Stage("resolve", REFUSED, str(trouble).splitlines()[0]))
        out.stages.append(Stage("build", RAN, f"digest {fingerprint or 'unknown'}"))
        out.stages.append(Stage("eval", NOT_ATTEMPTED, "no model was resolved"))
        out.stages.append(Stage("report", NOT_ATTEMPTED, "nothing to report on"))
        return out

    spec = AgentSpec.from_document(document, agent, source=root)
    bound, why, trouble = _bind(document, spec, agent, "", serving_at, root)
    if trouble is not None or bound is None:
        out.stages.append(Stage(
            "resolve", REFUSED,
            (str(trouble).splitlines()[0] if trouble is not None else why),
        ))
    else:
        # AC-3.6's resolve-time clause, at the stage named `resolve`. The model is
        # bound and the catalogue is open, so the author's two request ceilings
        # can be compared against a published price before anything runs.
        #
        # Reported HERE as well as in `score` because the two ceilings are
        # readable from the document alone: a workspace with no eval suite gets
        # no `score` at all — `if not cases: return` — and an author fixing a
        # document has usually not written their cases yet. A resolve-time check
        # reachable only through the eval command is a resolve-time check that
        # runs after the thing it was supposed to precede.
        from .resolve import price_of
        from .slo import against_the_catalogue

        disagree = against_the_catalogue(
            spec.slo, spec.limits.tokens_at_most, bound.name,
            lambda went_in, came_out: price_of(
                bound.name, went_in, came_out, workspace=root
            ),
        )
        said = f"{bound.name} — {why}"
        if disagree is not None:
            said += f"\n            {str(disagree).splitlines()[0]}"
        out.stages.append(Stage("resolve", RAN, said, gave=bound))

    out.stages.append(Stage(
        "build", RAN,
        f"{len(document.get('agents', {}))} agent(s), digest {fingerprint or 'unknown'}",
        gave=document,
    ))

    # ── eval ────────────────────────────────────────────────────────────────
    if bound is None:
        out.stages.append(Stage("eval", NOT_ATTEMPTED, "no model was resolved"))
        out.stages.append(Stage("report", NOT_ATTEMPTED, "nothing was scored"))
        return out

    scored = score(root, serving_at=serving_at)
    if scored.problem is not None:
        out.stages.append(Stage("eval", REFUSED, str(scored.problem).splitlines()[0]))
        out.stages.append(Stage("report", NOT_ATTEMPTED, "nothing was scored"))
        return out
    if scored.verdict.outcome == "UNDECIDED":
        # NOT a refusal. A model nobody is serving is a fact about this machine,
        # and the four stages above still ran — telling somebody their document
        # is wrong because their laptop has no weights would answer a question
        # they did not ask.
        out.stages.append(Stage(
            "eval", NOT_ATTEMPTED, scored.verdict.note or "undecided"
        ))
    else:
        out.stages.append(Stage(
            "eval", RAN,
            f"{scored.verdict.outcome} — {scored.verdict.score:.0%} against a "
            f"{scored.verdict.bar:.0%} bar",
            gave=scored,
        ))

    # ── report ──────────────────────────────────────────────────────────────
    from .scoring import render

    out.stages.append(Stage(
        "report", RAN,
        f"{len(scored.caveats)} caveat(s), {len(scored.unenforced)} unenforced rule(s)",
        gave=render(scored),
    ))
    return out


USAGE = """\
pact_adapters.pipeline — validate → resolve → build → eval → report (AC-7.3)

USAGE:
    python -m pact_adapters.pipeline PATH [--serving-at URL]

Runs every stage over one workspace, offline. Nothing here opens a socket except
the eval stage's calls to a model on this machine; a model that is not served
makes that stage `--` with the line to type, never a network error.

A REFUSED stage fails the run. A stage that could not be ATTEMPTED does not: a
machine with no model served still gets a validated, resolved, built tree, which
is what somebody fixing a document needs long before they have weights.

EXIT CODES:
    0  every stage that could run, ran       1  a stage was refused
"""


def main(argv: "list[str] | None" = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        sys.stdout.write(USAGE)
        return 0
    serving_at = ""
    if "--serving-at" in args:
        at = args.index("--serving-at")
        serving_at = args[at + 1] if at + 1 < len(args) else ""
        del args[at : at + 2]
    if not args:
        sys.stderr.write("error: no folder was given\n  fix: name one\n")
        return 1
    said = run_pipeline(args[0], serving_at=serving_at)
    sys.stdout.write(said.render())
    return said.exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
