"""Eval metric providers — the pluggable layer behind config-only evals (D6).

A metric is named by URI in YAML (`deepeval:faithfulness`) and executed by
whichever provider owns that scheme. The author never imports anything, never
subclasses anything, and never writes a callable. That is decision D14 applied
to evaluation: if expressing a check requires code, the format has failed.

**For a round this file was reachable from nowhere.** Measured: `grep -rn
'import.*providers' adapters/python/src` returned zero lines, and `grep -n
metrics spec/schema.yaml` returned zero lines — so the module that says a metric
is named by URI in YAML was serving a YAML field that did not exist. Writing
`metrics: [{uri: deepeval:faithfulness, threshold: 0.8}]` under `evals:` got
*"'metrics' is not something evals can have"* from the loader. D19's fifth
on-ramp — *"expert upload: metrics and rubrics with the full capability surface
DeepEval provides"* — had a provider layer, a docstring describing the URI, and
no door. The door is `evals.metrics:` in `spec/schema.yaml`; `evals.metrics_of`
reads it and `evals.check` runs what it returns.

Two provider families ship:

* `pact:` — deterministic scores PACT owns. These run FIRST and, where a suite
  is fully decidable, no model is ever invoked (AC-4.5). This is also what makes
  the suite runnable air-gapped (D17).
* `deepeval:` — the full DeepEval metric surface, constructed from config. Every
  metric that release exports is reachable this way. The legacy RAGAS wrappers
  are excluded deliberately: they hard-import `ragas` and HuggingFace `datasets`
  and need a LangChain embeddings object, so they belong behind a `ragas:`
  provider rather than being smuggled in through this one.

**Why `pact:contains` exists beside `must-contain:`.** They say the same thing,
and one construct for one idea is the rule this codebase holds — so the tie is
broken by who is writing. `rules:` is what a support lead types in their own
words and is where the schema's help sends a first-time author; `metrics:` is
what an EXISTING suite arrives carrying, and an expert converting one should not
have to translate half of it by hand into a different vocabulary. The new member
of the family, `at_most_words`, is the one no rule shape can express at all: a
rule is a yes or a no, and this is a *score* — how far inside a length an answer
came, graded against a bar the author sets, so `threshold: 80%` tolerates a
quarter over and refuses double.

**Air-gapped, or nothing (D17).** Nothing here builds its own judge. A
`deepeval:` metric is graded by the model the author named in `graded-by:` and by
no other — the same id, the same catalogue row, the same `allow-egress:` walk the
`judged:` rules go through. A `LocalJudge` class used to sit here defaulting to
`qwen2.5:7b-instruct` at `localhost:11434`, which would have let a metric be
graded by a model nobody wrote down and nobody's egress rule had admitted. A
provider this machine cannot run is a REPORTED ABSENCE with something to type,
never a call that goes looking for a network.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable

# Import of `deepeval.telemetry` starts Sentry + PostHog and probes the network
# unless this is set. It must be set BEFORE deepeval is imported anywhere, or
# the air-gap guarantee is broken by an import side effect.
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
os.environ.setdefault("ERROR_REPORTING", "NO")

#: The bar a metric is held to when the author wrote no `threshold:`. Half
#: marks, which is DeepEval's own default — a metric scored against a different
#: bar than its documentation states is a metric that no longer means what its
#: documentation says (FR-3.1.5).
DEFAULT_THRESHOLD = 0.5


def share(raw: Any, default: float) -> float:
    """A share of the whole, written `80%` or `0.8`, or `default`.

    One reader for both spellings and one range for both, which is not a style
    preference: the percent branch had no range check while the bare-decimal
    branch did, so `must-pass: -50%` gave `-0.5` and a six-of-six FAILING suite
    reported PASS with exit code 0. `evals.bar_of` reads `must-pass:` through
    this and `MetricSpec.parse` reads `threshold:` through it, so the two cannot
    come to disagree about what `80%` means.
    """
    if isinstance(raw, bool):
        return default
    if isinstance(raw, str) and raw.strip().endswith("%"):
        try:
            value = float(raw.strip().rstrip("%")) / 100.0
        except ValueError:
            return default
        return value if 0.0 <= value <= 1.0 else default
    if isinstance(raw, (int, float)) and 0.0 <= float(raw) <= 1.0:
        return float(raw)
    return default


@dataclass(frozen=True)
class MetricSpec:
    """One metric, exactly as it appears in YAML."""

    uri: str
    threshold: float = DEFAULT_THRESHOLD
    with_: dict[str, Any] = field(default_factory=dict)
    #: Which file the author wrote this in, and which line. Stamped by
    #: `evals.metrics_of`, which is the only thing that knows where the tree is —
    #: so a metric nothing could run names the line it came from rather than a
    #: generic one. Same reason `Rule.where` exists.
    where: str = "evals/suite.yaml:1"

    @staticmethod
    def parse(raw: Any, where: str = "evals/suite.yaml:1") -> "MetricSpec":
        if isinstance(raw, str):
            return MetricSpec(uri=raw.strip(), where=where)
        if not isinstance(raw, dict):
            return MetricSpec(uri="", where=where)
        return MetricSpec(
            uri=str(raw.get("uri", "")).strip(),
            threshold=share(raw.get("threshold"), DEFAULT_THRESHOLD),
            with_=dict(raw.get("with") or {}),
            where=where,
        )

    @property
    def scheme(self) -> str:
        return self.uri.split(":", 1)[0].strip() if ":" in self.uri else ""

    @property
    def metric(self) -> str:
        return self.uri.split(":", 1)[1].strip() if ":" in self.uri else self.uri

    @property
    def deterministic(self) -> bool:
        """Can this be decided without a model?

        Read by `evals.check` to hold AC-4.5 structurally: every metric that
        answers yes is measured in the deterministic pass, and a suite whose
        metrics all answer yes never reaches a grader at all.
        """
        return self.scheme == PACT


@dataclass
class MetricResult:
    """What one metric said about one answer.

    Three outcomes, not two, for the reason `evals.Verdict` and `judge.Ruling`
    both have three: a metric nothing could run has not passed the answer and has
    not failed it, and collapsing that into either would either let a suite
    report a green score on a measure nobody took, or blame the agent for a
    provider that is not installed. `unenforced` is what separates them.
    """

    uri: str
    score: float = 0.0
    passed: bool = False
    reason: str = ""
    deterministic: bool = True
    #: The sentence to put on `CaseOutcome.unenforced` when nothing could take
    #: this measurement. Empty when something did.
    unenforced: str = ""

    def __post_init__(self) -> None:
        # Why nothing measured it IS the reason, so a caller reading `reason`
        # never sees a blank where an explanation exists. One sentence written
        # once and readable from both fields, rather than two that can drift.
        if self.unenforced and not self.reason:
            self.reason = self.unenforced


# --------------------------------------------------------------- pact: family

PACT = "pact"
DEEPEVAL = "deepeval"
#: A grader the author CARRIES (P8 wave 3).
#:
#: The gap it closes is exactness. A refund amount, a checksum, a date window
#: each have a right answer, and grading one meant either a `judged:` rule put to
#: a model — which costs money, needs a judge binding and cannot be decided
#: offline — or a `must-contain:` string match that grades the wording rather
#: than the number.
#:
#: It belongs in the DETERMINISTIC-FIRST band beside `pact:`, so a suite that can
#: be fully decided still never invokes a model (AC-4.5), and it is air-gapped by
#: construction: the body is in the folder. Like every other program, what RUNS
#: it is the host's — this module declares the seam and reports honestly when
#: nothing supplies one.
PROGRAM = "program"

#: Every scheme this build answers to. Named once so the diagnostic for a scheme
#: nobody provides offers the real list rather than a hand-kept copy of it.
PROVIDERS: tuple[str, ...] = (PACT, DEEPEVAL, PROGRAM)


def _wanted(expected: str, with_: dict[str, Any]) -> str:
    """The words a containment check is looking for.

    `with: {text: ...}` when the metric names them itself, and the case's own
    `expect:` when it does not — so one entry under `metrics:` can hold for every
    case without the author repeating the answer they already wrote down.
    """
    written = with_.get("text")
    return str(written) if written is not None else expected


def _contains(actual: str, expected: str, with_: dict[str, Any]) -> Any:
    want = _wanted(expected, with_)
    if not want.strip():
        return MetricResult(
            f"{PACT}:contains",
            unenforced=(
                f"`{PACT}:contains` was not told what to look for. fix: write "
                f"`with: {{ text: refunded }}` under it, or state the answer on "
                f"each case with `expect:`."
            ),
        )
    hit = want.strip().lower() in actual.lower()
    return (1.0 if hit else 0.0), "" if hit else f"missing {want!r}"


def _absent(actual: str, expected: str, with_: dict[str, Any]) -> Any:
    want = _wanted(expected, with_)
    if not want.strip():
        return MetricResult(
            f"{PACT}:absent",
            unenforced=(
                f"`{PACT}:absent` was not told what to look for. fix: write "
                f"`with: {{ text: business days }}` under it."
            ),
        )
    hit = want.strip().lower() not in actual.lower()
    return (1.0 if hit else 0.0), "" if hit else f"must not contain {want!r}"


def _at_most_words(actual: str, expected: str, with_: dict[str, Any]) -> Any:
    """How far inside a word count an answer came, as a score between 0 and 1.

    A score rather than a yes/no, which is the whole reason this is a metric and
    not a rule: `threshold: 80%` on a 60-word ceiling tolerates an answer a
    quarter over and refuses one at double, and no rule shape can say that. An
    answer inside the ceiling scores 1.

    The ceiling comes from `with:` and is never guessed at. FR-3.1.5 forbids
    silently normalising a provider's settings, and a length ceiling nobody wrote
    is the same mistake one size smaller.
    """
    written = with_.get("words")
    try:
        ceiling = int(written)
    except (TypeError, ValueError):
        return MetricResult(
            f"{PACT}:at_most_words",
            unenforced=(
                f"`{PACT}:at_most_words` needs to be told the length, and "
                f"`with:` says {written!r}. fix: write `with: {{ words: 60 }}` "
                f"under it — the most words an answer may run to."
            ),
        )
    if ceiling < 1:
        return MetricResult(
            f"{PACT}:at_most_words",
            unenforced=(
                f"`{PACT}:at_most_words` was given `words: {ceiling}`, and an "
                f"answer cannot be shorter than one word. fix: write "
                f"`with: {{ words: 60 }}`, or a number above zero."
            ),
        )
    used = len(actual.split())
    if used <= ceiling:
        return 1.0, ""
    return ceiling / used, f"{used} words where {ceiling} is the most"


#: The deterministic family, by name. Adding one is a function here and a line in
#: an author's file — nothing enumerates them anywhere else, which is what keeps
#: `metrics:` from needing a schema change per metric (invariant E-4).
PACT_METRICS: dict[str, Callable[[str, str, dict[str, Any]], Any]] = {
    "contains": _contains,
    "absent": _absent,
    "at_most_words": _at_most_words,
}


# ------------------------------------------------------------ deepeval: family


def _normalise(name: str) -> str:
    """`pii_leakage`, `PIILeakage` and `piileakage` are one name.

    DeepEval's class names carry acronyms — `PIILeakageMetric`, `DAGMetric`,
    `MCPUseMetric` — and a per-character snake_case of those gives
    `p_i_i_leakage`, which nobody would type and which the old resolver was the
    only spelling that worked. Matching on letters and digits alone means the
    author writes the metric the way DeepEval's own documentation names it.
    """
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _readable(stem: str) -> str:
    """`PIILeakage` -> `pii_leakage`, `AnswerRelevancy` -> `answer_relevancy`.

    What a diagnostic offers, so the fix it names is a line that works.
    """
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", stem)
    return spaced.lower()


def _deepeval_classes() -> "dict[str, Any] | None":
    """Every DeepEval metric reachable from config, by normalised name.

    `None` — never an exception — when DeepEval is not on this machine. That is
    the honest air-gapped answer: a provider that is not installed is an absence
    to report, and a caller that got a traceback instead would turn a missing
    optional dependency into a crash in the middle of somebody's suite.

    Resolution is by string so adding a metric is a YAML edit. Nothing here
    enumerates the metric set, which is what keeps the provider from needing a
    change every time DeepEval ships one (invariant E-4).
    """
    try:
        import deepeval.metrics as m
    except Exception:  # noqa: BLE001 — every failure means "not available here"
        return None

    out: dict[str, Any] = {}
    for attr in getattr(m, "__all__", []) or dir(m):
        if not (attr.endswith("Metric") or attr == "GEval"):
            continue
        if attr.startswith("Ragas"):
            continue  # excluded by design — see module docstring
        if attr.startswith("Base"):
            continue  # abstract bases, not metrics an author can name
        cls = getattr(m, attr, None)
        if cls is None:
            continue
        stem = attr[: -len("Metric")] if attr.endswith("Metric") else attr
        out[_normalise(stem)] = cls
    return out


def available_deepeval_metrics() -> list[str]:
    """Every DeepEval metric reachable from config, as URIs an author can type.

    Empty when DeepEval is not installed, which is a different fact from "there
    are none" and is why `why_unavailable` asks `_deepeval_classes()` for `None`
    rather than for emptiness.
    """
    classes = _deepeval_classes()
    if classes is None:
        return []
    return sorted(
        f"{DEEPEVAL}:{_readable(cls.__name__[: -len('Metric')] if cls.__name__.endswith('Metric') else cls.__name__)}"
        for cls in classes.values()
    )


def coverage() -> dict[str, Any]:
    """The published coverage matrix (AC-4.1).

    Every metric DeepEval ships, the URI an author types for it, and — for the
    ones PACT does not offer — WHY. The criterion asks for a *published* matrix,
    and the difference between this and `available_deepeval_metrics()` is exactly
    that: one answers "what can I write", the other is an artifact somebody can
    read, diff and disagree with.

    **Computed from the installed DeepEval, never listed here.** A hand-written
    matrix is a second copy of somebody else's release notes, and it is wrong the
    first time they ship a metric. That is invariant E-4 — the provider resolves
    by string so adding a metric is a YAML edit — and a matrix that enumerated
    the set would put back exactly the coupling E-4 removes.

    Two exclusions, both deliberate and both stated: `Base*` are abstract classes
    an author cannot name, and `Ragas*` are excluded by design (see the module
    docstring). Nothing else is filtered — if a metric DeepEval ships is missing
    from `reachable`, that is a defect and this matrix is where it shows.
    """
    try:
        import deepeval  # noqa: F401
        import deepeval.metrics as m
    except Exception:  # noqa: BLE001
        return {
            "apiVersion": "pact.dev/v1",
            "kind": "MetricCoverage",
            "provider": DEEPEVAL,
            "installed": False,
            "why": (
                "DeepEval is not on this machine. That is an absence to report, "
                "not an empty matrix: `deepeval:` metrics an author writes are "
                "refused with the line to type, and nothing here guesses at what "
                "a version somebody else has would offer."
            ),
            "ships": [], "reachable": [], "not-offered": {},
        }

    ships = sorted(
        a for a in (getattr(m, "__all__", None) or dir(m))
        if a.endswith("Metric") or a == "GEval"
    )
    classes = _deepeval_classes() or {}
    reachable = available_deepeval_metrics()
    offered = {cls.__name__ for cls in classes.values()}

    not_offered: dict[str, str] = {}
    for name in ships:
        if name in offered:
            continue
        if name.startswith("Base"):
            not_offered[name] = (
                "an abstract base class, not a metric an author can name"
            )
        elif name.startswith("Ragas"):
            not_offered[name] = (
                "excluded by design — it brings its own model plumbing, which "
                "would take the grading decision away from the author's own "
                "`graded-by:` line"
            )
        else:
            not_offered[name] = (
                "SHIPPED BY DEEPEVAL AND NOT REACHABLE FROM CONFIG — this is a "
                "defect, not a decision"
            )

    return {
        "apiVersion": "pact.dev/v1",
        "kind": "MetricCoverage",
        "provider": DEEPEVAL,
        "installed": True,
        "version": getattr(__import__("deepeval"), "__version__", "unknown"),
        "counted": {
            "ships": len(ships),
            "reachable": len(reachable),
            "not-offered": len(not_offered),
        },
        "ships": ships,
        "reachable": reachable,
        "not-offered": not_offered,
    }


# ----------------------------------------------------- what nothing can measure


def why_unavailable(spec: MetricSpec, can_run_programs: bool = False) -> str:
    """Why this machine cannot take this measurement, or `""` when it can.

    Everything decidable WITHOUT running anything — no model, no network, no run
    — lives here, so the same sentences are available to a report before a suite
    starts and to `evals.check` while it scores. It is the split `judge.why_no_judge`
    already makes one construct over, for the same reason: a mistake in a file
    should reach the author where they are.

    Whether the provider is installed is asked by attempting the import, which
    touches no network. An absence answers with a line to type — including the
    line that needs nothing installed at all — because D17 means an air-gapped
    box must never discover at suite time that a score it wrote down needs a
    package it cannot fetch.
    """
    if not spec.uri:
        return (
            f"{spec.where} — a metric was written with no `uri:`, so there was "
            f"nothing to measure. fix: write `uri: {PACT}:at_most_words` under "
            f"it — or `{DEEPEVAL}:` followed by the name of any score DeepEval "
            f"provides, such as `uri: {DEEPEVAL}:faithfulness`."
        )
    if not spec.scheme:
        return (
            f"{spec.where} — `uri: {spec.uri}` does not say who provides that "
            f"score, so nothing measured it. fix: put the provider in front of "
            f"it with a colon — `uri: {DEEPEVAL}:{spec.uri}` for a DeepEval "
            f"score, or `uri: {PACT}:at_most_words` for one that needs nothing "
            f"installed."
        )
    if spec.scheme not in PROVIDERS:
        return (
            f"{spec.where} — nothing on this machine provides `{spec.scheme}:` "
            f"scores, so `{spec.uri}` was not measured. fix: this build provides "
            f"`{'`, `'.join(p + ':' for p in PROVIDERS)}` — write one of those in "
            f"front of the colon, for example "
            f"`uri: {DEEPEVAL}:{spec.metric or 'faithfulness'}`."
        )

    if spec.scheme == PROGRAM:
        if not spec.metric:
            return (
                f"{spec.where} — `{spec.uri}` names no program, so nothing says which "
                f"grader to run. fix: write the program's name after the colon, as "
                f"`uri: program:<name>`, naming one of the entries in `programs`."
            )
        if not can_run_programs:
            return (
                f"{spec.where} — `{spec.metric}` is a grader this workspace carries, and "
                f"nothing here can run a carried program, so `{spec.uri}` was not "
                f"measured. fix: whatever runs your agents has to supply a locked room "
                f"for programs; until it does, this score is reported rather than taken."
            )
        return ""

    if spec.scheme == PACT:
        if spec.metric in PACT_METRICS:
            return ""
        # The fix names a DeepEval score only when DeepEval really has one under
        # that name. Offering `deepeval:<whatever they typed>` unconditionally
        # would hand somebody a line that does not work, which is worse than
        # offering nothing — the whole reason a fix has to be typeable.
        known = _deepeval_classes() or {}
        instead = (
            f", or name the DeepEval score of that name instead — "
            f"`uri: {DEEPEVAL}:{spec.metric}`"
            if _normalise(spec.metric) in known
            else ""
        )
        return (
            f"{spec.where} — `{spec.uri}` is not a score PACT takes on its own, "
            f"so it was not measured. fix: write one of "
            f"`{'`, `'.join(PACT + ':' + n for n in sorted(PACT_METRICS))}`"
            f"{instead}. If you meant a check on the words of an answer, that is "
            f"a rule rather than a score — write `must-contain:` or "
            f"`must-not-contain:` under `rules:`."
        )

    classes = _deepeval_classes()
    if classes is None:
        return (
            f"{spec.where} — `{spec.uri}` needs DeepEval and it is not installed "
            f"on this machine, so that score was not measured. Nothing here "
            f"reached for the network to find it. fix: install it where your "
            f"agents run — `uv pip install deepeval` — or write a score that "
            f"needs nothing installed, `uri: {PACT}:at_most_words` with "
            f"`with: {{ words: 60 }}`."
        )
    if _normalise(spec.metric) not in classes:
        near = _closest(spec.metric, classes)
        return (
            f"{spec.where} — DeepEval has no score called `{spec.metric}`, so "
            f"`{spec.uri}` was not measured. fix: write "
            f"`uri: {near}`{_or_list(classes)}."
        )
    return ""


def _closest(wanted: str, classes: dict[str, Any]) -> str:
    """The URI a typo most likely meant. Never empty — a fix has to name one."""
    import difflib

    names = available_deepeval_metrics()
    hit = difflib.get_close_matches(f"{DEEPEVAL}:{wanted}", names, n=1, cutoff=0.5)
    return hit[0] if hit else (names[0] if names else f"{PACT}:at_most_words")


def _or_list(classes: dict[str, Any]) -> str:
    n = len(classes)
    return f", or one of the other {n - 1} scores this DeepEval provides" if n > 1 else ""


# ------------------------------------------------------------------ the measure


class _Asking:
    """The half of a DeepEval judge that is ours: turn a prompt into an answer.

    Kept apart from the base class so the same code works whether or not
    DeepEval is installed — `AskModel` below mixes this with DeepEval's own
    abstract class when there is one, and with nothing when there is not.
    """

    def __init__(self, name: str, ask: Callable[[str, str], str]) -> None:
        self.model_name = name
        self.name = name
        self._ask = ask
        self.model = self

    def load_model(self):  # DeepEval protocol
        return self

    def get_model_name(self) -> str:
        return self.model_name

    def generate(self, prompt: str, schema: Any = None, **_: Any) -> Any:
        said = str(self._ask("", prompt) or "")
        if schema is None:
            return said
        import json as _json

        body = said[said.find("{") : said.rfind("}") + 1] or "{}"
        try:
            return schema(**_json.loads(body))
        except Exception:  # noqa: BLE001 — an unreadable reply is an empty one
            return schema()

    async def a_generate(self, prompt: str, schema: Any = None, **k: Any) -> Any:
        return self.generate(prompt, schema, **k)


def _ask_model_class() -> type:
    """`_Asking`, made into something DeepEval will accept as a judge.

    **This is a D17 load-bearing detail, found by running it.** The class used to
    duck-type DeepEval's protocol and say so in a comment — and DeepEval 4.x
    does not duck-type. `metrics/utils.initialize_model` ends with
    `isinstance(model, DeepEvalBaseLLM)` and raises `TypeError` for anything
    else, which the construction below used to catch and answer by building the
    metric WITHOUT a judge — at which point DeepEval reached for `GPTModel` and
    demanded `OPENAI_API_KEY`. Measured on this machine: `deepeval:faithfulness`
    with a perfectly good locally-served grader raised *"OpenAI API key is not
    configured"*. An air-gapped box would have discovered at suite time that its
    metrics wanted a hosted model, which is the exact failure D17 exists to
    prevent, reached through a `except TypeError` written to be helpful.

    Subclassing rather than duck-typing keeps the dependency one-directional all
    the same: this file knows about DeepEval, DeepEval never learns about PACT.
    """
    try:
        from deepeval.models import DeepEvalBaseLLM
    except Exception:  # noqa: BLE001 — no DeepEval, so nothing to satisfy
        return type("AskModel", (_Asking,), {})
    return type("AskModel", (_Asking, DeepEvalBaseLLM), {})


def AskModel(name: str, ask: Callable[[str, str], str]) -> Any:  # noqa: N802
    """A DeepEval judge backed by whatever `graded-by:` already resolved to.

    The route in is `judge.Ask` — `(system, user) -> what the model said` — which
    is the same seam `judge.Judge` and `context-policy.summarised-by:` use, so a
    scripted grader in a test and Ollama on an air-gapped laptop plug into the
    same hole. There is deliberately no default: a metric with no judge is
    reported unenforced rather than quietly graded by a model the author never
    named and no `allow-egress:` line ever admitted.

    A function rather than a class because what it has to BE depends on whether
    DeepEval is installed, and that is a fact about the machine — not something
    to decide when this module is imported.
    """
    return _ask_model_class()(name, ask)


def _takes_a_judge(cls: Any) -> bool:
    """Does this score read the answer with a model?

    Asked of the class's own signature, so a score that takes no judge is
    constructed without one and a score that does is never constructed without
    one. `**kwargs` counts as yes: DeepEval's own metrics that forward their
    arguments all pass `model` on, and handing the judge to something that
    ignores it is harmless, while withholding it is how a hosted default gets
    reached for.
    """
    import inspect

    try:
        params = inspect.signature(cls).parameters
    except (TypeError, ValueError):
        return True
    if "model" in params:
        return True
    return any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())


def evaluate_metric(
    spec: MetricSpec,
    actual: str,
    expected: str = "",
    *,
    asked: str = "",
    judge: Any = None,
    retrieval_context: "list[str] | None" = None,
    run_program: "Callable[[str, dict[str, Any]], str] | None" = None,
) -> MetricResult:
    """Take one measurement. Deterministic providers never touch a model.

    `judge` is an `AskModel` or `None`, built by the caller from the author's own
    `graded-by:` line. `None` for a `deepeval:` score is an unenforced result
    with something to type, not a default judge — see the module docstring.
    """
    refused = why_unavailable(spec, can_run_programs=run_program is not None)
    if refused:
        return MetricResult(spec.uri, unenforced=refused,
                            deterministic=spec.deterministic)

    if spec.scheme == PROGRAM:
        # A grader the author carries. It is handed what was answered and what
        # was expected, and says how right the answer was — a number, because a
        # metric is a number against a bar and that is what separates one from a
        # `rules:` entry.
        #
        # A runner that raises is THIS SCORE's failure and not the suite's: the
        # same reading `_call_tool` gives a tool that could not run, because one
        # grader that could not answer must not take the other scores down with
        # it.
        assert run_program is not None  # `why_unavailable` refused otherwise
        try:
            said = run_program(spec.metric, {
                "actual": actual,
                "expected": expected,
                "asked": asked,
                **spec.with_,
            })
        except Exception as e:  # noqa: BLE001 — a grader's failure is data
            return MetricResult(
                spec.uri, 0.0, False,
                f"`{spec.metric}` could not run: {e}",
                deterministic=spec.deterministic,
            )
        try:
            score = float(str(said).strip())
        except ValueError:
            return MetricResult(
                spec.uri, 0.0, False,
                f"`{spec.metric}` answered {said!r}, and a score is a number between "
                f"0 and 1.",
                deterministic=spec.deterministic,
            )
        return MetricResult(
            spec.uri, score, score >= spec.threshold,
            f"`{spec.metric}` scored {score}",
            deterministic=spec.deterministic,
        )

    if spec.scheme == PACT:
        answered = PACT_METRICS[spec.metric](actual, expected, spec.with_)
        if isinstance(answered, MetricResult):
            return answered
        score, why = answered
        return MetricResult(spec.uri, score, score >= spec.threshold, why)

    # DeepEval defaults its judge to GPT and demands OPENAI_API_KEY at
    # CONSTRUCTION time. Under D17 that is a hard failure, not a warning — so a
    # metric with no judge never gets as far as being built.
    if judge is None:
        return MetricResult(
            spec.uri, deterministic=False,
            unenforced=(
                f"{spec.where} — `{spec.uri}` is scored by reading the answer, "
                f"and nothing was grading this run, so it was not measured. fix: "
                f"name a model this machine serves with `graded-by:` under "
                f"`evals:`, and run the suite where that model is served."
            ),
        )

    classes = _deepeval_classes() or {}
    cls = classes[_normalise(spec.metric)]
    # Whether this score takes a judge is ASKED, not discovered by catching an
    # error. The version that caught `TypeError` and retried without the judge is
    # how a locally-served grader turned into a demand for `OPENAI_API_KEY` — see
    # `_ask_model_class`. `tool_correctness` and its kind genuinely take no
    # model, and their signature says so.
    settings: dict[str, Any] = {"threshold": spec.threshold, **spec.with_}
    if _takes_a_judge(cls):
        settings["model"] = judge
    try:
        metric = cls(**settings)
    except Exception as e:  # noqa: BLE001
        return MetricResult(
            spec.uri, deterministic=False,
            unenforced=(
                f"{spec.where} — `{spec.uri}` does not take the settings written "
                f"under `with:` ({type(e).__name__}: {e}), so it was not "
                f"measured. fix: check the settings against DeepEval's own page "
                f"for that score and write them under `with:` exactly as it "
                f"names them."
            ),
        )

    from deepeval.test_case import LLMTestCase

    case = LLMTestCase(
        input=asked,
        actual_output=actual,
        expected_output=expected or None,
        retrieval_context=retrieval_context,
    )
    try:
        metric.measure(case)
    except Exception as e:  # noqa: BLE001
        # A score that could not be taken is an absence, NOT a zero. Scoring it
        # as a failure would blame the agent for a case that does not carry what
        # the metric needs — `faithfulness` with nothing retrieved, say — which
        # is the same wrong-way-round T7 forbids for a rule nobody could grade.
        return MetricResult(
            spec.uri, deterministic=False,
            unenforced=(
                f"{spec.where} — `{spec.uri}` could not be measured on this "
                f"answer: {type(e).__name__}: {e}. fix: check the cases give "
                f"that score what it reads — DeepEval's page for it names what "
                f"it needs — or remove the line if it does not fit this suite."
            ),
        )
    score = float(getattr(metric, "score", 0.0) or 0.0)
    return MetricResult(
        spec.uri, score, score >= spec.threshold,
        str(getattr(metric, "reason", "") or ""), deterministic=False,
    )
