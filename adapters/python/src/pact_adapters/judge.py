"""The judge — the one eval rule only a reader can decide (D19 on-ramp 5).

Four of the five rule shapes are decidable by looking at the answer: does it say
one of these words, does it avoid those, was that action called first. The fifth
is not. *"Gives the reason in one sentence a customer can understand"* is the
kind of thing a support lead actually writes down, and no amount of string
matching decides it.

For a round PACT read that rule and did not run it. `evals.Rule.read` returned it
carrying the sentence *"judging needs a model, and this runtime has no judge
wired up"*, `_read_rules` put it on `unenforced`, and it never reached `rules`.
The author's `judged:` line and their `graded-by:` line both loaded, validated,
and decided nothing — which is the project's own worst failure ("config that
loads and does not reach the run is worse than config that does not load") in the
one mechanism that says whether a money-moving agent is fit to ship. D19 names
"expert upload — metrics and rubrics with the full capability surface DeepEval
provides" as an on-ramp reachable strictly through config, and a rule that is
read and not run does not satisfy it.

**What this now refuses.** An answer a reader would say fails the author's
sentence fails its case, so the suite score drops and the verdict at the author's
own bar flips. That is the whole point: before this, `judged:` could refuse
nothing.

**Air-gapped, or nothing (D17).** The judge is a model call, and the only model
call it will make is to a model this box already serves. `graded-by:` is resolved
against `models/catalog.yaml` exactly as `context-policy.summarised-by:` is; a
row that is only reachable over the network is refused where the author is, in a
workspace whose `allow-egress:` does not admit it, with a locally-served id to
type instead. Nothing here falls back to a hosted judge, and nothing here guesses
a verdict when no judge could run — an ungraded rule goes to `unenforced` with a
sentence, which is the same door `unmetered` and `unwatched` leave by (T7).

**Three outcomes, not two**, for the reason `evals.Verdict` has three: a grading
model that answers neither PASS nor FAIL has not decided anything, and scoring
that as a pass would make the oracle quietly stop being one. `Ruling.decided` is
what separates "the judge said no" from "nothing judged".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from . import egress as _egress
from .diagnostics import locate

#: One grading call: `(system, user) -> what the grading model said`.
#:
#: A callable rather than a transport, because a judge is not a run: there is no
#: loop, no tools, no history. It is the same seam `context-policy.summarised-by:`
#: uses one level down — the model *id* comes from the author's file and the way
#: to reach weights comes from whoever is running the suite — so a scripted
#: grader in a test and Ollama on a laptop plug into the same hole.
Ask = Callable[[str, str], str]

#: Where a locally-served model answers, by default. The same address
#: `OllamaTransport` uses, and it never leaves the box.
LOCAL_RUNTIME = "http://localhost:11434/v1"

#: What the grading model is told to do.
#:
#: Two lines and a fixed first word, because a grade that has to be inferred from
#: prose is a grade that can be inferred wrongly, and a wrong grade is worse than
#: no grade — see `Ruling.decided`. Deliberately narrow: it judges the ONE
#: sentence it was handed and is told so, otherwise a 14B model volunteers an
#: opinion on the whole answer and the author's rule stops being what was
#: measured.
RUBRIC = (
    "You are grading one answer against one rule, and nothing else.\n"
    "Reply in exactly two lines.\n"
    "Line 1: the single word PASS if the answer satisfies the rule, or FAIL if "
    "it does not. That word alone.\n"
    "Line 2: one short sentence saying why.\n"
    "Judge only the rule you are given. Do not judge anything else about the "
    "answer, and do not rewrite it."
)

#: How long a reason is allowed to be when it lands in a failure message. A
#: grading model asked for one sentence sometimes writes six, and a case failure
#: nobody can read at a glance is a failure nobody acts on.
REASON_LIMIT = 300

#: How many tokens a grade may take. `RUBRIC` asks for a word and a sentence, so
#: this is honest for the task rather than a saving: measured on the shipped row,
#: a grade is 15 completion tokens and an uncapped model writes 300 where 20
#: would answer. `experiments/real_model_portability.py` caps for the same reason.
GRADE_TOKENS = 96

#: How long to wait for one grade. Generous, because the machine this has to work
#: on is the air-gapped one: a 14B model on a loaded box took four minutes for
#: those 15 tokens here, and the shipped default of 180s turned a judge that
#: works into a `ReadTimeout`. A judge that gives up early does not degrade
#: gracefully — it reports a rule as ungraded when the answer was coming.
GRADE_TIMEOUT_S = 900.0


@dataclass(frozen=True)
class Ruling:
    """What the judge said about one sentence and one answer.

    `decided` first, because it is the field that keeps this honest. A judge that
    could not be understood has not passed the answer and has not failed it, and
    collapsing that into either would make the oracle report something nobody
    measured.
    """

    decided: bool
    passed: bool = False
    reason: str = ""
    #: Exactly what the grading model said, kept so a suite that disagrees with
    #: its judge can be argued about rather than guessed at.
    said: str = ""


class Judge:
    """Grades one `judged:` sentence against one answer, with one model call.

    Holds no state between calls on purpose: two cases graded in either order
    must get the same verdicts, which is the property a scorer needs and the
    property a conversation would take away.
    """

    def __init__(self, model: str, ask: Ask) -> None:
        #: The id from the author's `graded-by:` line, resolved against the
        #: catalogue before this was built. Carried so a report can say which
        #: model produced a verdict — a score whose grader is anonymous cannot be
        #: reproduced.
        self.model = model
        self._ask = ask

    def grade(
        self,
        sentence: str,
        answer: str,
        because: str = "",
        *,
        passages: "tuple[str, ...] | list[str]" = (),
        right_because: str = "",
    ) -> Ruling:
        """Does `answer` satisfy `sentence`?

        `because` is the author's own `because:` line and is shown to the judge.
        It is the difference between grading the words of a rule and grading what
        the rule is for, and it costs nothing — the author already wrote it for
        whoever reads the failure.

        `passages` are the case's `from-these-passages:` and `right_because` its
        `because:` — why the expected answer is the right one, which the schema
        names as "what a grader reads". Both are shown only when written, so a
        suite that wrote neither asks exactly what it asked before.
        """
        if not sentence.strip():
            return Ruling(decided=False, reason="there was no rule to grade")
        asked = f"RULE: {sentence.strip()}\n"
        if because.strip():
            asked += f"WHY THE RULE EXISTS: {because.strip()}\n"
        if right_because.strip():
            asked += f"WHY THE EXPECTED ANSWER IS RIGHT: {right_because.strip()}\n"
        written = [p.strip() for p in passages if str(p).strip()]
        if written:
            asked += "THE PASSAGES THE ANSWER SHOULD COME FROM:\n" + "\n".join(
                f"- {p}" for p in written
            ) + "\n"
        asked += f"\nANSWER:\n{answer}"
        said = str(self._ask(RUBRIC, asked) or "")
        return read_grade(said)

    def reading(self):
        """This same grader, in the shape a `deepeval:` metric asks for.

        One grader for both halves of the suite, deliberately. A `judged:` rule
        and a `metrics:` entry are both "somebody reads the answer and says how
        it did", so they must be read by the SAME model — the one the author put
        in `graded-by:`, resolved through the same catalogue row and refused by
        the same `allow-egress:` walk. `providers.py` used to ship a `LocalJudge`
        that defaulted to `qwen2.5:7b-instruct` on localhost, which would have
        graded an author's metrics with a model they never wrote down.

        Built here rather than in `providers` so that `_ask` stays private to
        this file: the route to weights is this module's business, and a second
        thing constructing one is a second place a hosted fallback could appear.
        """
        from .providers import AskModel

        return AskModel(self.model, self._ask)


#: Decoration a model wraps a one-word answer in, stripped before comparing.
_DRESSING = " \t.:*_-–—#>`"

#: A line that IS the verdict and nothing else. Any case and any inflection is
#: safe here, because a line reading only `passed` cannot mean anything else.
_ALONE = re.compile(r"^(pass(?:es|ed)?|fail(?:s|ed)?)$", re.IGNORECASE)

#: The verdict embedded in a line — `**PASS**`, `Verdict: FAIL`. UPPERCASE and
#: exact, deliberately. A reason reading *"the 30-day window has passed"* or
#: *"this does not pass the rule"* would be mined for the wrong verdict by
#: anything looser, and a judge that silently inverts is worse than no judge:
#: `Ruling.decided` exists so the answer to an unreadable reply is "nobody
#: decided this", never a guess.
_EMBEDDED = re.compile(r"\b(PASS|FAIL)\b")


def read_grade(said: str) -> Ruling:
    """Turn what the grading model wrote into a ruling, or admit it could not.

    Tolerant about decoration and strict about substance, in that order: a line
    that is only the word wins first, then an uppercase token anywhere. Models
    bold the verdict, bullet it, or put a label in front of it, and refusing all
    of those would report a working judge as broken. What is NOT tolerated is a
    reply with no verdict in it: that lands on `unenforced` with something to
    type, because a rule nobody decided must never be scored as one that passed.
    """
    lines = [line.strip() for line in said.splitlines() if line.strip()]
    for finder in (_ALONE, _EMBEDDED):
        for at, line in enumerate(lines):
            bare = line.strip(_DRESSING)
            found = finder.search(bare if finder is _ALONE else line)
            if found is None:
                continue
            # Everything BEFORE the token is a label (`Verdict:`, `**`) and
            # everything after it is the reason. Taking the tail rather than
            # both sides is what keeps `Verdict: FAIL` from reporting its own
            # label as the reason the answer failed.
            tail = (bare if finder is _ALONE else line)[found.end():]
            reason = tail.strip(_DRESSING)
            if not reason and at + 1 < len(lines):
                reason = lines[at + 1].strip(_DRESSING)
            passed = found.group(1).lower().startswith("pass")
            return Ruling(
                True,
                passed,
                (reason or ("the answer satisfies the rule" if passed
                            else "the answer does not satisfy the rule"))[:REASON_LIMIT],
                said,
            )
    return Ruling(decided=False, reason="", said=said)


# ──────────────────────────────────────────────────── the author's `graded-by:`


def graded_by(doc: dict[str, Any]) -> str:
    """The model id the suite says grades it, as the author typed it."""
    return str(((doc.get("evals") or {}).get("graded-by") or "")).strip()


def why_no_judge(
    doc: dict[str, Any], workspace: "str | Path | None" = None
) -> str:
    """Why this document cannot have a judge, or `""` when it can.

    Everything decidable from the FILES lives here — the line is missing, the id
    is in no catalogue, the row only answers off this machine — so the same
    sentences are available to `pact`-style reporting without a model, a network
    or a run. Whether weights are actually reachable is the separate question
    `judge_of` asks afterwards, because it is a fact about the box and not about
    the document.

    The egress role checked is `llm`, which is what `pact check`'s own
    `egress_is_allowed` walk and `resolve.needs_of` both check. One role for
    every model binding, so an author who added it for `model:` does not discover
    a second spelling when they add a judge.
    """
    source = Path(workspace) if workspace else None
    file, line = locate(source, "evals", "suite", "suite", "graded-by")
    named = graded_by(doc)
    if not named:
        return (
            f"{file}:{line} — a `judged:` rule was written and `graded-by:` is not "
            f"set, so nothing decided it. fix: add `graded-by: qwen2.5-14b-instruct` "
            f"under `evals:` — a model from `models/catalog.yaml` that is not the "
            f"one doing the work."
        )

    from . import resolve as _resolve  # local: `resolve` imports `evals` imports this

    catalogue = _resolve.load_catalogue(workspace=workspace)
    entry = catalogue.get(named)
    local = sorted(e.name for e in catalogue.entries if e.served_locally)
    offer = catalogue.default if catalogue.default in local else (
        local[0] if local else "a model this machine serves"
    )
    if entry is None:
        return (
            f"{file}:{line} — `graded-by: {named}` names a model "
            f"`models/catalog.yaml` has no row for, so the `judged:` rules were "
            f"not applied. fix: write `graded-by: {offer}`, or add a row for "
            f"{named} to `models/catalog.yaml`."
        )

    # `judge`, and only `judge`: the role this binding plays. AD-56 is why it is
    # a role of its own — the grader reads every eval case, which is strictly
    # more than the reflector ever sees, so a team that wants a hosted grader and
    # nothing else hosted has one line to write. Until `egress.py` existed only
    # `llm` was read here, so `allow-egress: [judge]` behaved exactly like
    # `allow-egress: []` and the only fix this message could offer was to grant
    # every model role at once.
    #
    # `allow-egress: [llm]` admits a grader as well, but that is `egress.WORDS`'s
    # rule to apply and not this line's to restate. Passing `"llm"` here beside
    # `"judge"` made the rule redundant at every call site in the port —
    # MEASURED: emptying `WORDS` altogether changed no answer anywhere and the
    # suite stayed green, so a word could have left that table the way `tools`
    # never entered it.
    if not entry.served_locally and not _egress.admits(doc, "judge"):
        # The same refusal `pact check` makes over `model:` and `summarised-by:`,
        # made here for the third binding — and the one that sees the most, since
        # the judge reads every eval case. Refusing rather than calling out is the
        # whole of D17: an air-gapped box must not discover its judge needs an API
        # when the suite runs.
        return (
            f"{file}:{line} — `graded-by: {named}` is only served off this "
            f"machine, and this workspace says "
            f"`allow-egress: {_egress.listed(doc)}` — nothing there lets the "
            f"model that grades the checks talk to anything outside the box, so "
            f"the `judged:` rules were not applied. fix: write "
            f"`graded-by: {offer}`, which runs here; or add `judge` to "
            f"`allow-egress:` in workspace.yaml, which is the least of the six "
            f"roles that covers grading. To let every model call out instead, "
            f"add `llm` to `allow-egress:`. Either is a change a person has to "
            f"approve."
        )
    return ""


def judge_of(
    doc: dict[str, Any],
    ask: "Ask | None" = None,
    workspace: "str | Path | None" = None,
) -> "tuple[Judge | None, str]":
    """The judge the author's `graded-by:` line names, or nothing and why not.

    This is the whole authored path: the id comes off `evals.graded-by`, the row
    comes off `models/catalog.yaml`, and the workspace's own `allow-egress:`
    decides whether that row may be used. Nothing is defaulted — a document that
    named no judge gets no judge, and says so.

    `ask` is the way to reach weights, supplied by whoever runs the suite exactly
    as the transport is for a run. Passing none asks for the local route, and the
    local route exists only if this box really serves the named model; when it
    does not, that is a sentence with something to type rather than a call that
    goes looking for a network.
    """
    refused = why_no_judge(doc, workspace)
    if refused:
        return None, refused
    named = graded_by(doc)
    if ask is not None:
        return Judge(named, ask), ""

    here = str(workspace or "")
    route = local_ask(named, here)
    if route is None:
        source = Path(workspace) if workspace else None
        file, line = locate(source, "evals", "suite", "suite", "graded-by")
        # Catalogue ids rather than runtime tags, because `graded-by:` takes a
        # catalogue id — offering `qwen2.5:14b-instruct` here would be a fix that
        # does not work, which is worse than none.
        ready = ", ".join(runnable_judges(here)) or "nothing this catalogue knows"
        return None, (
            f"{file}:{line} — `graded-by: {named}` is a model this machine is not "
            f"serving right now, so the `judged:` rules were not applied. Ready "
            f"here: {ready}. fix: start it — `ollama pull "
            f"{_ollama_tag(named, here)}` — or write `graded-by:` with one of the "
            f"models above."
        )
    return Judge(named, route), ""


def runnable_judges(workspace: str = "") -> list[str]:
    """Every catalogue id this machine is really serving, as `graded-by:` takes it.

    The catalogue says which rows COULD be served locally and the runtime says
    which weights are actually on this disk; a judge needs both to be true, so
    this is the intersection and not either half. It is what a diagnostic offers,
    and it is why the offer is a line that works.
    """
    from . import resolve as _resolve

    catalogue = _resolve.load_catalogue(workspace=workspace or None)
    running = served_here()
    return sorted(
        entry.name
        for entry in catalogue.entries
        if entry.served_locally and ({entry.name, *entry.aliases} & running)
    )


# ────────────────────────────────────────────────────────────── the local route


def local_ask(
    model: str, workspace: str = "", base_url: str = LOCAL_RUNTIME
) -> "Ask | None":
    """One grading call against a model served ON THIS MACHINE, or nothing.

    Built on `OllamaTransport` rather than beside it: a judge asking a model a
    question is one model call, and the transport that already knows how to make
    one — including reading the counts back off the wire — is the one to make it.
    Nothing new is opened here that a run does not already open.

    `None` when this box is not serving the model. That is the honest air-gapped
    answer and it is why there is no hosted fallback anywhere in this file: the
    alternative is a suite that quietly starts costing money and needing a
    network the moment a local model is missing.
    """
    tag = _ollama_tag(model, workspace, base_url)
    if not tag or tag not in served_here(base_url):
        return None

    def ask(system: str, user: str) -> str:
        # A fresh transport per call, because `Judge` holds no state between
        # calls and a shared one would carry the last call's token counts into
        # the next case's report.
        from .transports._summarise import finish_now
        from .transports.ollama_transport import OllamaTransport

        transport = OllamaTransport(
            tag,
            base_url=base_url,
            temperature=0.0,
            max_tokens=GRADE_TOKENS,
            timeout=GRADE_TIMEOUT_S,
            workspace=workspace,
        )
        said, _calls_no_grader_should_make = finish_now(
            transport.model_call(system, [{"role": "user", "content": user}], [])
        )
        return said

    return ask


@lru_cache(maxsize=4)
def served_here(base_url: str = LOCAL_RUNTIME) -> frozenset[str]:
    """Every model tag the local runtime actually has pulled.

    Asked rather than assumed. The catalogue says which runtimes *can* serve a
    row; only the runtime knows which weights are on this disk today, and the
    difference is exactly the failure an air-gapped author hits — a perfectly
    valid `graded-by:` line against a model nobody downloaded.

    Empty whenever nothing answers, which covers "no runtime installed", "not
    started" and "no network at all" with one honest answer instead of three
    tracebacks. Cached, so a six-case suite asks once.
    """
    try:
        import httpx

        root = base_url.rstrip("/")
        root = root[: -len("/v1")] if root.endswith("/v1") else root
        answered = httpx.get(f"{root}/api/tags", timeout=2.0)
        answered.raise_for_status()
        rows = answered.json().get("models") or []
        return frozenset(str(r.get("name") or "") for r in rows if r.get("name"))
    except Exception:  # noqa: BLE001 — every failure means the same thing here
        return frozenset()


def _ollama_tag(
    model: str, workspace: str = "", base_url: str = LOCAL_RUNTIME
) -> str:
    """What the local runtime calls these weights.

    The catalogue's `also-known-as:` list is what makes this possible without a
    per-runtime table in code: `qwen2.5-14b-instruct` is the id an author writes
    and `qwen2.5:14b-instruct` is what Ollama answers to, and the row carries
    both. The first spelling the runtime recognises wins; with nothing serving,
    the catalogue id comes back so the diagnostic above can still name something
    to pull.
    """
    from . import resolve as _resolve

    entry = _resolve.load_catalogue(workspace=workspace or None).get(model)
    names = [model, *sorted(entry.aliases)] if entry is not None else [model]
    running = served_here(base_url)
    for name in names:
        if name in running:
            return name
    # Prefer a spelling that looks like a runtime tag over the catalogue id, so
    # `ollama pull ...` in the diagnostic is a line that actually works.
    return next((n for n in names if ":" in n), model)
