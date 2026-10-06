"""The Resolver — model portability, decided by evals (thesis T4, decision D11).

The question "can this agent run on a smaller model?" is not a translation
question. It is a search: the contract stays fixed, and a *different strategy*
is sought for a weaker executor. The developer's eval suite is the oracle, and
nothing binds without a verdict from it.

Two behaviours here are non-negotiable and both come from evidence:

* **Fail, then recommend** (D11). Refusing to bind is only half an answer. The
  resolver searches the catalogue and names the cheapest model that *does* pass,
  so a failure arrives as a decision rather than a dead end.
* **Never report a bare ratio** (AC-3.1). Measured against a *hand-authored*
  frontier strategy an optimised small model reaches 98–114%; against an
  *optimised* frontier strategy, 70–94%. Those are different claims, and a
  report that prints one without naming its baseline is misleading, so
  `PortabilityReport` cannot be constructed without one.

The catalogue itself is **read from a file, once** (`models/catalog.yaml`, D8).
It used to be three literals inside one test, which is why `ModelEntry` had no
context window at all and every shipped transport reported that it could not say
what its model could hold. A fact about a model that lives in a test fixture is a
fact the product does not have.

For one round the file existed and only `window_of` read it: `resolve()` still
took its candidate list from the caller, and the only caller in the tree handed
it three invented models. So `tier`, `cost`, `reasoning` and `capabilities` were
parsed off disk into `ModelEntry` and no shipped path read them, which meant
D11's "the cheapest model that does pass" could never name a model this
distribution can actually serve. The list is now the catalogue by default, the
requirements are read from the author's own `needs:` block by default, and the
three literals are gone.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping

import yaml

from . import egress as _egress
from .diagnostics import Problem
from .evals import (
    NOT_A_RUNTIME,
    NOT_SERVING,
    STOPPED,
    Case,
    CaseOutcome,
    Silence,
    Verdict,
    bar_of,
    check,
    metrics_of,
    rules_of,
    verdict,
)
from .harness import delegate_by_running, run
from .holes import holes_in
from .ir import AgentSpec
from .loader import REPO, shipped
from .yes_no import said_yes

#: Where the distribution keeps its catalogue: `<repo>/models/catalog.yaml` in a
#: checkout, and inside the package in a wheel (`loader.shipped`), which sits in
#: no checkout and used to resolve no shipped model at all.
#: §4.2 names the location normatively and names the address it is served under
#: (`pact:catalog/builtin`); resolving it from the package rather than from the
#: caller's working directory is what makes "the author never authors it" true
#: for a process started anywhere.
BUILTIN_CATALOGUE = shipped("models", "catalog.yaml")

#: What a row writes when the figure exists but nobody in this distribution can
#: attribute it (§4.2). Read as "no window", exactly as an absent transport
#: method is, so it travels to `RunResult.unmetered` rather than into a guess.
UNKNOWN = "unknown"

#: The four rungs of `needs.reasoning:`, weakest first. Decision Y12 gave this
#: ladder a defined order, a catalogue home and a **non-filtering UNKNOWN**,
#: because `reasoning: careful` was the first line of the first predicate file an
#: author writes and it bound against nothing.
LADDER: tuple[str, ...] = ("simple", "steady", "careful", "deep")

#: The three answers `needs.tool-calling:` takes — `spec/schema.yaml`'s own
#: `choices: [no, yes, parallel]`, and nothing else. NOT a `yes-no`: `parallel`
#: is a third answer rather than a stronger tick, which is why this field does
#: not go through `yes_no.said_yes` and needs a list of its own.
#:
#: `needs_of` reads it as *everything but `no` needs a model that can call
#: tools*, which is true of all three and is the whole of what the field decides
#: there. A FOURTH choice added to the schema fails the test that holds this set
#: against it, which is the point: somebody then has to say whether the new word
#: means tools, rather than having it silently mean them.
TOOL_CALLING: frozenset[str] = frozenset({"no", "yes", "parallel"})


def _rung(value: str) -> "int | None":
    """Where on the ladder a word sits, or `None` for one nobody measured."""
    try:
        return LADDER.index(str(value or "").strip())
    except ValueError:
        return None


def _tokens(written: Any) -> "int | None":
    """`32k`, `131072`, `1M` — how an author writes a size, as a number.

    Written out rather than left to a regular expression because the three
    spellings are the ones `needs.context-at-least:` documents ("e.g. 32k") and
    an author who typed a fourth deserves the requirement to be *ignored* rather
    than silently read as zero, which would pass every model.
    """
    if isinstance(written, bool):
        return None
    if isinstance(written, int):
        return written if written > 0 else None
    text = str(written or "").strip().lower().replace(",", "").replace("_", "")
    if not text:
        return None
    scale = 1
    if text.endswith("k"):
        scale, text = 1_000, text[:-1]
    elif text.endswith("m"):
        scale, text = 1_000_000, text[:-1]
    try:
        size = int(round(float(text) * scale))
    except ValueError:
        return None
    return size if size > 0 else None


@dataclass(frozen=True)
class ModelEntry:
    """A catalogue row. `cost` is per-1k-tokens; `tier` gates variant selection."""

    name: str
    tier: str            # frontier | mid | small
    #: Per 1k input tokens, or `None` when the catalogue says `unknown`.
    #: `None` is NOT zero. It used to be: a row published as unsourced sorted
    #: first as the cheapest model and D11's recommendation line then printed
    #: `at 0.0/1k tokens`, a price nobody published, which contradicts the
    #: catalogue's own rule that a figure nobody can source is written `unknown`
    #: and never guessed. An unpriced row now ranks LAST and says so.
    cost: "float | None"
    #: Per 1k OUTPUT tokens, read the same way and `None` for the same reason.
    #: A second figure rather than a second record, because a bill is
    #: `in × in-price + out × out-price` and every row in this catalogue already
    #: publishes both halves — pricing a call off `cost` alone would undercount
    #: every answer by the factor between them, which on the shipped Anthropic
    #: rows is five. `cost` stays the INPUT figure alone because it is what D11
    #: ranks on and what `price()` prints, and moving that would change a
    #: recommendation while nobody was looking.
    output_cost: "float | None" = None
    capabilities: frozenset[str] = frozenset()
    scores: dict[str, float] = None  # type: ignore[assignment]
    #: How much this model can hold, in tokens. `None` means the catalogue says
    #: `unknown` — not "small", and not "ask again later". It is here rather than
    #: on a second record beside it because a window is a fact about a model, and
    #: two places to learn one fact is how a runtime comes to tidy against a
    #: different number than the one the resolver ranked on.
    context_window: int | None = None
    #: Every other id this row answers to — what each runtime calls the same
    #: weights (`qwen2.5:7b-instruct` on Ollama). Looking the row up under all of
    #: them beats carrying one row per runtime.
    aliases: frozenset[str] = frozenset()
    #: The rung on `LADDER`, or `""` for a row nobody has placed. Empty binds
    #: and ranks last (Y12) — it never removes a candidate, because a beginner
    #: predicate that can silently match nothing is worse than one that ranks.
    reasoning: str = ""
    #: Whether some runtime serves these weights ON THIS MACHINE — a `served-by:`
    #: entry with `endpoint: local`. Y16: egress is a property of the binding, so
    #: a workspace whose `allow-egress:` does not list `llm` may only bind a row
    #: that is true here. Read from the catalogue rather than inferred from how
    #: the runtime is spelled.
    served_locally: bool = False
    #: Which runtimes serve these weights (`ollama`, `vllm`, `anthropic-api`).
    #: A transport that knows which runtime it *is* can then bind a model that
    #: runtime can actually serve, instead of the distribution-wide default —
    #: which for one round meant the Anthropic transport reported that its model
    #: held 32,768 tokens because it had bound a Qwen id it cannot serve.
    runtimes: frozenset[str] = frozenset()

    def satisfies(self, needs: dict[str, Any]) -> tuple[bool, str]:
        """Cheap pre-filter. Never a substitute for an eval verdict (FR-2.1.2).

        `needs` is the flat shape `needs_of` produces from the author's own
        `needs:` block. For a round this method existed and every caller passed
        `{}`, so it always returned `(True, "")` — `images: yes`,
        `context-at-least: 32k` and the rest were core-tier lines a non-coder
        writes that bound against nothing at all (D13/D14).

        Two rules, and the difference between them is the whole of Y12:
        a figure the catalogue RECORDS and that falls short **filters**; a figure
        the catalogue says is `unknown` **binds and ranks last**.
        """
        for cap in needs.get("capabilities", ()):
            if cap not in self.capabilities:
                # "cannot handle images", not "cannot images". `cap` is the
                # author's own key — `images`, `tool-calling` — so the verb has
                # to be supplied here, and this is a core-tier sentence a
                # non-coder reads when their agent is refused a model.
                return False, f"cannot handle {cap}"
        for metric, threshold in (needs.get("scores") or {}).items():
            have = (self.scores or {}).get(metric)
            if have is None:
                return False, f"no published {metric} score"
            wanted = _threshold(threshold)
            if wanted is None:
                return False, (
                    f"`scores.{metric}: {threshold}` is not a threshold this can "
                    f"read — write it as `> 80`, `>= 80`, `< 5` or `<= 5`"
                )
            op, value = wanted
            if not _HOLDS[op](have, value):
                return False, f"{metric} {have} is not {op} {value:g}"
        wanted = _tokens(needs.get("context-at-least"))
        if wanted is not None and self.context_window is not None:
            if self.context_window < wanted:
                return False, (
                    f"holds {self.context_window:,} tokens and this needs at "
                    f"least {wanted:,}"
                )
        floor = _rung(needs.get("reasoning", ""))
        mine = _rung(self.reasoning)
        if floor is not None and mine is not None and mine < floor:
            return False, (
                f"thinks at the {self.reasoning!r} rung and this needs at least "
                f"{LADDER[floor]!r}"
            )
        if needs.get("must-stay-on-this-machine") and not self.served_locally:
            return False, (
                "is only reachable over the network, and this workspace does "
                "not let the model call leave the box"
            )
        return True, ""

    def ranks_after(self, needs: dict[str, Any]) -> tuple:
        """Sort key for "cheapest that passes". Lower is offered first.

        Everything the catalogue could not source sinks rather than disappears
        (Y12), and price is the tie-break D11 names. The model's own name is the
        last term so that two rows priced the same are offered in the same order
        on every machine — a recommendation that depends on dict order is not a
        recommendation anyone can reproduce.
        """
        floor = _rung(needs.get("reasoning", ""))
        unplaced = 1 if (floor is not None and _rung(self.reasoning) is None) else 0
        unsized = 1 if (
            _tokens(needs.get("context-at-least")) is not None
            and self.context_window is None
        ) else 0
        return (unplaced + unsized, self.cost is None, self.cost or 0.0, self.name)

    def price(self) -> str:
        """The per-1k figure as a recommendation should print it."""
        if self.cost is None:
            return "at a price this distribution cannot source"
        return f"at {self.cost}/1k tokens"


# ────────────────────────────────────────────────────────────── the catalogue


@dataclass(frozen=True)
class Catalogue:
    """`models/catalog.yaml`, read. Distribution-supplied, never authored (§4.2).

    `problems` is carried rather than raised for the same reason every other
    document in this package carries its mistakes: a catalogue with one bad row
    should still bind the other nine, and the author — here, whoever ships the
    distribution — gets a file, a line and something to type instead of a
    traceback.
    """

    entries: tuple[ModelEntry, ...] = ()
    default: str = ""
    problems: tuple[Problem, ...] = ()
    _by_id: dict[str, ModelEntry] = field(default_factory=dict, repr=False)

    @property
    def errors(self) -> tuple[Problem, ...]:
        return tuple(p for p in self.problems if p.severity == "error")

    def get(self, model: str) -> "ModelEntry | None":
        """The row for `model`, under its catalogue id or any runtime alias."""
        return self._by_id.get(str(model or "").strip())

    def window_of(self, model: str) -> int | None:
        entry = self.get(model)
        return entry.context_window if entry is not None else None

    def price_of(
        self, model: str, input_tokens: int, output_tokens: int
    ) -> "float | None":
        """What one call on `model` cost in USD, or `None` if nobody published a price.

        BOTH halves have to be sourced. A row that priced its input and wrote
        `unknown` for its output could still produce a number here, and that
        number would be the input bill wearing the whole bill's name — an
        undercount that reads exactly like a cheap model. `None` is the same
        answer an absent transport method is, and it travels to
        `RunResult.unmetered` where the author can read it.

        `None` is NOT zero, for the reason `ModelEntry.cost` gives one field up:
        the one row this catalogue deliberately publishes as unpriced would
        otherwise meter every ceiling at 0.0 USD, and a spend cap that can never
        be reached is the silent non-enforcement T7 exists to name.
        """
        entry = self.get(model)
        if entry is None or entry.cost is None or entry.output_cost is None:
            return None
        went_in = max(0, int(input_tokens))
        came_out = max(0, int(output_tokens))
        return (went_in * entry.cost + came_out * entry.output_cost) / 1000.0


def load_catalogue(
    path: "str | Path | None" = None, workspace: "str | Path | None" = None
) -> Catalogue:
    """Read the catalogue. Offline, always — D17 forbids a network path here.

    Cached on the resolved path so a run that asks seven transports what their
    model holds opens the file once.

    `workspace` is the OVERRIDE LAYER architecture §4.2 makes normative: "A
    workspace-local `models/catalog.yaml` is an optional *override layer* in the
    RES-2 vertical chain, with the same per-figure provenance requirement —
    never a prerequisite." It is what an author on an air-gapped box serving a
    model this distribution has never heard of writes, and without it their
    `context-policy:` was permanently on `unmetered` with no no-code way out,
    which is a D14/D17 failure. The workspace wins row by row; a row it does not
    mention keeps the distribution's, and `default:` is overridden only if the
    workspace states one.
    """
    builtin = _load(Path(path) if path is not None else BUILTIN_CATALOGUE)
    if workspace is None:
        return builtin
    local = Path(workspace)
    if local.is_dir():
        local = local / "models" / "catalog.yaml"
    if not local.exists():
        return builtin
    return _layer(builtin, _load(local))


def _layer(under: Catalogue, over: Catalogue) -> Catalogue:
    """The workspace's rows on top of the distribution's, row by row.

    Per row and not per file, because the whole point of the layer is a machine
    that serves one extra model — replacing the whole catalogue to add a row is
    how an author ends up hand-maintaining eight figures they never wanted to
    know. Provenance survives because a row is carried whole: this never merges
    two sources into one figure, which is the LangChain anti-pattern §4.2's
    fifth finding names.
    """
    rows = {e.name: e for e in under.entries}
    rows.update({e.name: e for e in over.entries})
    entries = tuple(sorted(rows.values(), key=lambda e: e.name))
    by_id: dict[str, ModelEntry] = {}
    for entry in over.entries:
        for key in (entry.name, *entry.aliases):
            by_id.setdefault(key, entry)
    for entry in entries:
        for key in (entry.name, *entry.aliases):
            by_id.setdefault(key, entry)
    return Catalogue(
        entries,
        over.default or under.default,
        under.problems + over.problems,
        by_id,
    )


def window_of(
    model: str,
    path: "str | Path | None" = None,
    workspace: "str | Path | None" = None,
) -> int | None:
    """How much `model` can hold, or `None` if this distribution cannot say.

    The single source of a window. A transport calls this and answers with what
    it gets; nothing invents a number on the way past, because a policy measured
    against an invented budget is the silent degradation T7 exists to forbid.

    `workspace` brings the override layer into a RUN rather than leaving it to
    `pact check`. A machine serving its own model is exactly the case that had
    no answer, and a file the checker accepts but the harness never opens is the
    same defect one hop along.
    """
    return load_catalogue(path, workspace).window_of(model)


def price_of(
    model: str,
    input_tokens: int,
    output_tokens: int,
    path: "str | Path | None" = None,
    workspace: "str | Path | None" = None,
) -> "float | None":
    """What one call on `model` cost, or `None` if this distribution cannot say.

    The single source of a price, and it sits here beside `window_of` for the
    same reason that one does: a transport asks and answers with what it gets,
    and nothing invents a figure on the way past. Seven transports each doing
    their own arithmetic over `input-per-mtok` is seven places a currency, a
    scale factor or an `unknown` can be read differently, and a spend cap
    measured against a price the catalogue did not publish is the T7 breach
    `RunResult.unmetered` exists to prevent.

    Until this existed the money and token ceilings were the two `Limits` rows
    that no shipped transport could measure: `harness._meter_usage` probed for
    `usage()`, found nothing on all seven, and `Limits.unmeterable` put
    `cost-per-request-under` and `tokens-at-most` on `RunResult.unmetered` on
    every real run. That is exactly the state `context_window()` was in before
    `models/catalog.yaml` landed, and it is closed the same way — from the
    catalogue, not hardcoded per transport.
    """
    return load_catalogue(path, workspace).price_of(model, input_tokens, output_tokens)


def default_model(path: "str | Path | None" = None) -> str:
    """What PACT binds when the author pinned no `model:`.

    The promise `spec/schema.yaml` already makes on that field — "Leave this out
    and PACT picks" — answered from data rather than from a constant in code, so
    changing the pick is a YAML edit.
    """
    return load_catalogue(path).default


@lru_cache(maxsize=8)
def _load(path: Path) -> Catalogue:
    shown = _shown(path)
    try:
        text = path.read_text()
    except OSError:
        return Catalogue(
            problems=(
                Problem(
                    severity="error",
                    rule="catalog/missing",
                    file=shown,
                    line=1,
                    message=(
                        "there is no model catalogue at this path, so nothing "
                        "knows how much any model can hold"
                    ),
                    fix=(
                        "restore the catalogue that ships with PACT at "
                        "`models/catalog.yaml`"
                    ),
                ),
            )
        )

    lines = text.splitlines()
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as broken:
        # Carried, not raised — the promise this class makes about itself. A
        # traceback out of here would land on whoever is running an agent, who
        # did not write this file and cannot read a parser stack.
        mark = getattr(broken, "problem_mark", None)
        return Catalogue(
            problems=(
                Problem(
                    severity="error", rule="catalog/unreadable-file", file=shown,
                    line=(mark.line + 1) if mark is not None else 1,
                    message="this line of the model catalogue is not valid YAML",
                    fix=(
                        "check the indentation on this line — every setting under "
                        "a model sits two spaces further in than the model's name"
                    ),
                ),
            )
        )
    if not isinstance(raw, dict):
        return Catalogue(
            problems=(
                Problem(
                    severity="error", rule="catalog/unreadable-file", file=shown,
                    line=1,
                    message="the model catalogue is not a set of settings",
                    fix="start the file with `version: 1` and a `models:` block",
                ),
            )
        )

    problems: list[Problem] = []
    entries: list[ModelEntry] = []
    by_id: dict[str, ModelEntry] = {}

    written = raw.get("models")
    if not isinstance(written, dict):
        written = {}
    for name, row in sorted(written.items()):
        name = str(name)
        if not isinstance(row, dict):
            problems.append(
                _problem(shown, lines, name, "catalog/unreadable-row",
                         f"the row for {name} is not a set of settings",
                         f"write `{name}:` with `capabilities:` indented under it")
            )
            continue
        caps = row.get("capabilities")
        if not isinstance(caps, dict):
            caps = {}
        window, trouble = _window(shown, lines, name, caps.get("context-window"))
        if trouble is not None:
            problems.append(trouble)
        entry = ModelEntry(
            name=name,
            tier=str(row.get("tier") or "mid"),
            cost=_cost(row.get("cost")),
            output_cost=_cost(row.get("cost"), "output-per-mtok"),
            capabilities=_capabilities(caps),
            scores=_benchmarks(row.get("benchmarks")),
            context_window=window,
            aliases=frozenset(
                str(a) for a in (row.get("also-known-as") or []) if isinstance(a, str)
            ),
            reasoning=_reasoning(row.get("reasoning")),
            served_locally=_served_locally(row.get("served-by")),
            runtimes=_runtimes(row.get("served-by")),
        )
        entries.append(entry)
        for key in (name, *entry.aliases):
            by_id.setdefault(key, entry)

    default = str(raw.get("default") or "")
    if default and default not in by_id:
        problems.append(
            _problem(shown, lines, "default:", "catalog/unknown-default",
                     f"`default: {default}` names a model this catalogue has no row for",
                     f"use one of: {', '.join(sorted(e.name for e in entries)) or '(none)'}")
        )
    return Catalogue(tuple(entries), default, tuple(problems), by_id)


def _window(
    file: str, lines: list[str], name: str, written: Any
) -> tuple[int | None, "Problem | None"]:
    """Read one row's `context-window`, which is a value with its own provenance.

    One shape, not two. §4.2's fifth finding requires per-figure `source` and
    `as-of` on the resolved entry — LangChain's hand-written override layer that
    records nothing is named there as the anti-pattern — so a bare integer is
    refused rather than quietly accepted, and the diagnostic says what to type.
    """
    if not isinstance(written, dict):
        return None, _problem(
            file, lines, name, "catalog/window-without-provenance",
            f"{name} does not say how much it can hold, or says so without a source",
            "write `context-window:` with `value:` and `provenance:` under it, "
            "as every other row in this file does",
        )
    value = written.get("value")
    if value == UNKNOWN:
        return None, None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None, _problem(
            file, lines, name, "catalog/unreadable-window",
            f"{name} gives {value!r} as how much it can hold, which is not a "
            f"number of tokens",
            f"write `value: 32768`, or `value: {UNKNOWN}` if nobody can source it",
        )
    return value, None


def _cost(written: Any, key: str = "input-per-mtok") -> "float | None":
    """Per-1k tokens, from the per-million figure §4.2 records.

    `key` picks which half of the row's `cost:` block is being read. One reader
    for both, rather than one per direction: `unknown`, a missing block and a
    trailing currency word have to mean the same thing on the output figure as
    on the input one, and two readers is how they come to differ.

    `unknown` and a missing block both read as `None`, and a `None` ranks LAST.

    They used to read as `0.0`, which ranked the row FIRST — so the one row this
    catalogue deliberately publishes as unsourced sorted as the cheapest model on
    offer and D11's recommendation line printed `at 0.0/1k tokens`, a price
    nobody published. That contradicts this file's own rule in the one sentence
    D11 makes load-bearing: a figure nobody can source is written `unknown`, and
    `unknown` is not a number. The reasoning behind the old direction — "a human
    has to look at it, so put it at the top" — described a review queue, not a
    recommendation, and the recommendation is what an author reads.
    """
    if not isinstance(written, dict):
        return None
    raw = written.get(key)
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw) / 1000.0
    if isinstance(raw, str):
        head = raw.split()[0] if raw.split() else ""
        try:
            return float(head) / 1000.0
        except ValueError:
            return None
    return None


def _reasoning(written: Any) -> str:
    """The rung this row was placed on, or `""` for one nobody placed.

    Same `value:`/`provenance:` shape as the window, and read the same way: a
    word not on `LADDER` — including the literal `unknown` — comes back empty,
    which BINDS and ranks last rather than filtering (Y12). A bare string is
    accepted too, so a workspace override layer written by hand does not have to
    learn the two-line shape before it can say something true.
    """
    if isinstance(written, dict):
        written = written.get("value")
    value = str(written or "").strip()
    return value if _rung(value) is not None else ""


#: How close two published figures have to be before `= 80` calls them equal.
#:
#: A billionth, and the same billionth `SCORE_TOLERANCE` in
#: `crates/pact-schema/src/coerce.rs` allows, because the two decide the same
#: author's line. The figure is written down in `spec/comparisons.yaml` and both
#: ports are held to it there — the comment on `_HOLDS` below claimed a mirror
#: for a release while this side allowed `1e-12` and the checker allowed
#: `f64::EPSILON` (~2.2e-16), four orders of magnitude apart. A catalogue
#: publishing `80.0000000001` cleared `= 80` for the checker and not for this
#: file; one publishing `79.999999999999` cleared it here and not there.
#:
#: Why a billionth and not either of those: a score that has been written down
#: as text, read back, and divided by a hundred lands a few steps from where it
#: started, and around 80 a step is about 1.4e-14 — so `f64::EPSILON`, which is
#: the step at 1.0, cannot reach even one of them and means bit-for-bit equality.
#: A billionth leaves room for several hundred steps, and is still ten million
#: times finer than the two decimal places a benchmark is published to, so
#: `79.99` stays a different score from 80 and is refused.
SCORE_TOLERANCE = 1e-9

#: What each comparison means. Mirrors `Op::holds` in
#: `crates/pact-schema/src/coerce.rs` — the loader parses these and this decides
#: them, and a difference between the two is a model bound on a rule the checker
#: read differently. Held to that claim, from both sides, by
#: `spec/comparisons.yaml` and the two tests named
#: `a_comparison_means_the_same_thing_in_both_ports`.
_HOLDS: dict[str, Any] = {
    ">": lambda have, want: have > want,
    ">=": lambda have, want: have >= want,
    "<": lambda have, want: have < want,
    "<=": lambda have, want: have <= want,
    "=": lambda have, want: abs(have - want) < SCORE_TOLERANCE,
}

#: Longest first, so `>=` is not read as `>` followed by a stray `=`.
_COMPARISONS = (">=", "<=", "==", ">", "<", "=")


def _threshold(written: Any) -> "tuple[str, float] | None":
    """One `needs.scores:` entry as `(comparison, number)`.

    **The loader has always parsed these and this file never did.** `needs.scores`
    is `type: map of threshold`, and `coerce.rs` reads `> 80`, `>= 80`, `< 5`,
    `<= 5`, `= 80` and a trailing `%` — so `MMLU: "> 80"` loads cleanly and
    `pact show` emits the string `"> 80"`. `satisfies` then did `have <= threshold`
    with a float on the left and that string on the right, which is a `TypeError`,
    not a refusal: **the format's own documented syntax crashed the resolver.**

    AC-3.2 asks for a predicate evaluating `MMLU > 80 && SWE-Verified > 40`. The
    conjunction is the map — every entry has to hold — and the comparison is
    this. What PACT deliberately does not have is the `&&` as a string an author
    types: an expression language is a language, and the one thing a non-coder
    must never have to learn is a syntax with precedence in it. Two lines that
    both have to be true is the same predicate without the parser.

    **A bare number is not a comparison and is refused here, as it is there.**
    This file used to read `MMLU: 80` as `> 80` "which is what every author who
    wrote one meant", and `coerce.rs::threshold` has always answered `None` to it
    — *"a bare number states no comparison"* — so `pact check` prints:

        error: 'scores' should be a comparison, like `> 80`, but it is a
               whole number.
          fix: Write it like `> 80` or `>= 0.8`.

    The two were never reachable at once: a document with `MMLU: 80` in it does
    not become a document this port is handed, so the generous arm here was
    unreachable rather than wrong, and it stayed that way only because nothing
    said so. It is gone rather than documented as deliberate, because the guess it
    made is not obviously right — `< 5` is a real thing to want on a latency or a
    hallucination-rate metric, and on those the silent `>` is the WRONG direction,
    binding models the author meant to exclude. The checker refuses and shows the
    two shapes; that is the better answer and there is now only one of them.

    `satisfies` turns the `None` into the same sentence in this port's words, so
    a document that somehow arrived without going through the checker refuses its
    models with a line to type instead of binding them on a guess.
    """
    if not isinstance(written, str):
        return None
    said = written.strip()
    for op in _COMPARISONS:
        if said.startswith(op):
            rest = said[len(op):].strip()
            scale = 1.0
            if rest.endswith("%"):
                rest, scale = rest[:-1].strip(), 0.01
            try:
                figure = float(rest) * scale
            except ValueError:
                return None
            # `inf`, `nan` and `Infinity` all parse to a float here and to
            # nothing at all in `coerce::threshold`, which refuses a non-finite
            # result unless the author's text carried a digit
            # (`pact_schema::has_a_digit`). The distinction is the same one money
            # and sizes already draw: `> 1e999` is a real figure that ran off the
            # end of the number line and is carried up so the ceiling can name
            # it; `> inf` is a WORD spelled where a figure goes and is not a
            # threshold. Without this line `> inf` bound every model in the
            # catalogue here and was `schema/wrong-type` one crate over.
            if figure != figure or figure in (float("inf"), float("-inf")):
                if not any(c.isdigit() and c.isascii() for c in rest):
                    return None
            return ("=" if op == "==" else op), figure
    return None


def _benchmarks(written: Any) -> dict[str, float]:
    """Published benchmark figures for one row, by metric name.

    This came back `{}` unconditionally — the argument was not even read — so
    `satisfies()` answered *"no published {metric} score"* for every candidate on
    every threshold, and `needs.scores:` could not be satisfied by any catalogue
    however well sourced. Not merely unimplemented: a predicate that empties the
    candidate set whatever the data says is a trap, and it is the one Y12 was
    written about.

    The `value:`/`provenance:` shape `reasoning:` and `context-window` use, and a
    bare number accepted for the same stated reason: *"a workspace override layer
    written by hand does not have to learn the two-line shape before it can say
    something true"* — and a hand-written layer is exactly the air-gapped case
    this file exists for.

    A figure written `unknown`, or one that is not a number, is DROPPED rather
    than kept as zero. Zero would satisfy no threshold and read as a measurement;
    absent is the truth, and `satisfies()` says *"no published X score"* about it.
    """
    if not isinstance(written, dict):
        return {}
    out: dict[str, float] = {}
    for metric, figure in written.items():
        if isinstance(figure, dict):
            figure = figure.get("value")
        try:
            out[str(metric)] = float(figure)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue          # `unknown`, or prose — see the docstring
    return out


def _served_locally(written: Any) -> bool:
    """Whether any runtime serves these weights on this machine.

    `endpoint: local` on a `served-by:` entry, and nothing else. Y16 states the
    rule over exactly this field — "the resolver refuses to bind any role whose
    catalogue row has a non-local `served-by.endpoint` unless listed" — and
    reading the fact rather than pattern-matching the runtime's name is the
    difference between this and Eve's `model.provider.includes("anthropic")`.
    """
    if not isinstance(written, list):
        return False
    return any(
        isinstance(entry, dict) and str(entry.get("endpoint") or "").strip() == "local"
        for entry in written
    )


#: How the catalogue's own capability vocabulary lands in the flat set
#: `ModelEntry.satisfies` checks a `needs:` block against. Written out rather
#: than inferred, because a mapping nobody can read is a mapping that quietly
#: fails a requirement the author typed.
def _capabilities(caps: dict[str, Any]) -> frozenset[str]:
    out: set[str] = set()
    calling = str(caps.get("tool-calling") or "").strip()
    if calling and calling != "none":
        out.add("tools")
    if calling == "parallel":
        out.add("parallel-tools")
    modality_in = caps.get("modality-in") or []
    if isinstance(modality_in, list):
        if "image" in modality_in:
            out.add("images")
        if "audio" in modality_in:
            out.add("audio_in")
    modality_out = caps.get("modality-out") or []
    if isinstance(modality_out, list) and "audio" in modality_out:
        out.add("audio_out")
    # `needs_of` has emitted this token since the field existed, and nothing here
    # could ever emit it: `model-can` had no field for computer use, so
    # `needs: computer-use: yes` was 0 of 13 rows in the shipped catalogue and
    # 0 of any catalogue anybody could write. D16 names it as a v1 modality, and
    # D17's escape hatch — a workspace adding its own row — could not reach it
    # either, because there was no line to write it on.
    if said_yes(caps.get("computer-use")):
        out.add("computer-use")
    return frozenset(out)


def needs_of(document: dict[str, Any], agent_key: str) -> dict[str, Any]:
    """The author's `needs:` block, in the shape `ModelEntry.satisfies` reads.

    The missing half of the translation. `_capabilities` above turns a catalogue
    row's own vocabulary into a flat set; this turns the *schema's* `needs:`
    block — `reasoning`, `tool-calling`, `images`, `audio`, `computer-use`,
    `context-at-least`, `because`, `scores` — into the same one. Without it
    nothing anywhere produced the shape `satisfies` expects, every call site
    passed `{}`, and the pre-filter was `satisfies({}) -> (True, "")` on every
    model in the catalogue: seven core-tier lines a non-coder writes, bound to
    nothing (D13/D14).

    `because:` is not translated, deliberately. It is the sentence printed under
    a rejection, not a requirement — see `spec/schema.yaml`.

    `allow-egress:` is read from the workspace rather than the agent, because
    egress is a property of the BINDING and not of one model role (Y16). A
    workspace that has not listed the role this agent's model plays has said the
    call may not leave the box, and a recommendation that ignores it hands an
    air-gapped author a hosted model.

    *Which* of the six roles has to be listed depends on what this agent's own
    lines send. `llm` is the grant for the words; an agent that `accepts:` a
    voice message needs `stt` beside it, because a grant for words that also
    carried speech would make `stt` and `tts` two choices nothing reads — which
    is what they were. See `egress.py` for the rule and why the asymmetry is
    deliberate.
    """
    agent = ((document.get("agents") or {}).get(agent_key) or {})
    block = agent.get("needs") or {}
    if not isinstance(block, dict):
        block = {}

    caps: list[str] = []
    # `needs.tool-calling:` is NOT a `yes-no`, which is why it does not go
    # through `said_yes` two lines down. `spec/schema.yaml` types it
    # `one-of: [no, yes, parallel]`, because `parallel` is a third answer and not
    # a stronger tick.
    #
    # It held a fourth word, `true`, for as long as this file held its own `_yes`
    # beside it — and `pact check` refuses `tool-calling: true` at the author's
    # own line (*"'tool-calling' should be one of: no, yes, parallel"*), so it
    # was a spelling no document reaching here could ever carry. Removed for the
    # reason `yes_no.py` gives for removing `facts._yes`'s `1`: a reader more
    # generous than the checker is a second, unwritten specification, and the
    # next person to read this line has no way to tell which of the two is the
    # rule. `TOOL_CALLING` is held to the schema's own `choices:` by
    # `tests/test_one_word_for_yes_means_one_thing_to_every_reader.py`.
    calling = str(block.get("tool-calling") or "").strip()
    if calling in TOOL_CALLING - {"no"}:
        caps.append("tools")
    if calling == "parallel":
        caps.append("parallel-tools")
    if said_yes(block.get("images")):
        caps.append("images")
    if said_yes(block.get("audio")):
        caps.extend(("audio_in", "audio_out"))
    if said_yes(block.get("computer-use")):
        caps.append("computer-use")

    missing = _egress.missing_for(document, agent)

    return {
        "capabilities": caps,
        "scores": block.get("scores") or {},
        "context-at-least": block.get("context-at-least"),
        "reasoning": block.get("reasoning") or "",
        "must-stay-on-this-machine": bool(missing),
        # Which grant is absent, so a refusal can ask for that one rather than
        # for `llm` every time. Advice that always says "grant everything" is
        # not a per-role gate however carefully it reads one.
        "egress-missing": missing,
    }


def _runtimes(written: Any) -> frozenset[str]:
    """Which runtimes a row says serve it."""
    if not isinstance(written, list):
        return frozenset()
    return frozenset(
        str(entry.get("runtime") or "").strip()
        for entry in written
        if isinstance(entry, dict) and str(entry.get("runtime") or "").strip()
    )


def default_for(runtime: str, path: "str | Path | None" = None) -> str:
    """What to bind on `runtime` when the author pinned no `model:`.

    `default_model()` answers the same question for the distribution as a whole,
    and for a transport that knows which runtime it is, that answer is wrong: an
    Anthropic transport bound the distribution default and then reported that
    its model held 32,768 tokens, because the default row is Qwen weights served
    by Ollama and vLLM. Nothing checked that the runtime could serve the id, so
    a context policy on that transport was measured against a window belonging
    to a model it cannot run — "measured against the wrong number, silently".

    The catalogue's own `default:` wins where the runtime serves it; otherwise
    the cheapest row that runtime does serve, unpriced rows last, name as the
    tie-break so the pick is the same on every machine. `""` when this runtime
    serves nothing here — honest, and it lands on `unmetered` like every other
    thing this distribution cannot say.
    """
    catalogue = load_catalogue(path)
    wanted = str(runtime or "").strip()
    if not wanted:
        return catalogue.default
    fallback = catalogue.get(catalogue.default)
    if fallback is not None and wanted in fallback.runtimes:
        return catalogue.default
    servable = [e for e in catalogue.entries if wanted in e.runtimes]
    if not servable:
        return ""
    return min(servable, key=lambda e: (e.cost is None, e.cost or 0.0, e.name)).name


def _problem(
    file: str, lines: list[str], needle: str, rule: str, message: str, fix: str
) -> Problem:
    return Problem(
        severity="error", rule=rule, file=file,
        line=_line_of(lines, needle), message=message, fix=fix,
    )


def _line_of(lines: list[str], needle: str) -> int:
    for i, line in enumerate(lines, start=1):
        if needle in line:
            return i
    return 1


def _shown(path: Path) -> str:
    """The path as whoever ships the distribution would type it."""
    for home in (Path(__file__).resolve().parent, REPO):  # a wheel's copy, then a checkout's
        if path.is_relative_to(home):
            return str(path.relative_to(home))
    return str(path)


@dataclass
class PortabilityReport:
    agent: str
    model: str
    baseline: str          # REQUIRED — see module docstring
    verdict: Verdict
    strategy: str
    recommendation: str = ""
    #: The search's answer as FACTS, where `recommendation` is the same answer as
    #: words. `--choose-model` binds off this: a flag whose help says it binds the
    #: model that passes could only ever bind the one the agent already named,
    #: because the name of the row that passed existed nowhere but inside a
    #: sentence. Always set where `recommendation` is; `.model` is `""` when
    #: nothing passed, which is the same thing `recommendation` opens with.
    instead: "Alternative | None" = None

    def render(self) -> str:
        head = (
            f"PORTABILITY: {self.verdict.outcome} for {self.model}"
            f"  (agent {self.agent}, strategy {self.strategy})"
        )
        lines = [head, f"  measured against: {self.baseline}"]
        if not self.verdict.results:
            # NOTHING RAN, so there is no score, and `score 0% vs bar 70%` is not
            # a neutral way of saying that — it is a measurement claim. Printed
            # beside "did not answer, so nothing was measured on it" it reads as
            # a model that answered and got every case wrong, which is the exact
            # misreading `evaluate` refuses to encode when it returns no results
            # instead of a figure off a shorter suite than the author wrote.
            #
            # NO RESULTS, whatever the outcome, and not UNDECIDED-with-no-results.
            # The other empty verdict is the one `resolve` builds when the
            # catalogue row does not meet the author's `needs:` — FAIL, refused
            # before an eval was run — and it printed `score 0% vs bar 70%` beside
            # "thinks at the 'steady' rung and this needs at least 'careful'",
            # which is the same false number with a different word above it.
            lines.append(f"  score: not measured (bar {self.verdict.bar:.0%})")
        else:
            lines.append(
                f"  score {self.verdict.score:.0%} vs bar {self.verdict.bar:.0%}"
            )
        if self.verdict.note:
            lines.append(f"  {self.verdict.note}")
        for f in self.verdict.failures[:5]:
            lines.append(f"  - {f.key}: {f.why}")
        # A portability figure computed while one of the author's rules went
        # ungraded is a figure with a hole in it, and the hole has to be printed
        # beside the number rather than left on an object nobody prints. This is
        # the same obligation `PortabilityReport` already meets by refusing to
        # exist without a `baseline`: a score whose provenance is unstated is
        # misleading even when it is arithmetically right.
        for said in self.verdict.unenforced[:3]:
            lines.append(f"  NOT APPLIED: {said}")
        if self.recommendation:
            # Two different sentences, so two different labels. A search that
            # found nothing is not a recommendation, and printing it under
            # `RECOMMENDED:` would make "nothing qualifies" read as advice.
            label = "NO ALTERNATIVE" if self.recommendation.startswith("nothing") else "RECOMMENDED"
            lines.append(f"{label}: {self.recommendation}")
        return "\n".join(lines)


# A strategy is a way of running the agent: it may change instructions, step
# budget, or decomposition. It is *not* a change to the contract.
Strategy = Callable[[AgentSpec], AgentSpec]


def strategies_of(spec: AgentSpec) -> dict[str, Strategy]:
    """Every way to run this agent, from the author's own `variants:` block.

    The authored agent first, always, then the variants in the order they were
    written — MASS shows prompt changes dominate topology changes, so trying the
    author's own wording before anything that restructures the work is not
    politeness, it is the ordering that measures best.

    This function exists because `resolve()` used to REQUIRE the caller to hand
    it `dict[str, Callable[[AgentSpec], AgentSpec]]`, and the only such callables
    anywhere in the tree were two Python lambdas in `test_model_portability.py`.
    One of them is the `decomposed` strategy README.md quotes as a measured
    result. Model portability is the headline claim, and its authoring surface
    was a lambda — which is exactly what D14 says may never be the answer for a
    capability in the core.
    """
    out: dict[str, Strategy] = {"authored": lambda s: s}
    for name, written in spec.variants:
        out[name] = _variant(written)
    return out


def _variant(written: Mapping[str, Any]) -> Strategy:
    """One variant's fields, as a transformation of the spec.

    `instructions:` replaces; `says:` appends. Both exist because they are
    different edits: replacing is how you write a whole other approach, and
    appending is how you add the one sentence — *"Always look the order up before
    deciding"* — that makes a smaller model reliable without rewriting anything.
    """

    def apply(s: AgentSpec) -> AgentSpec:
        changes: dict[str, Any] = {}
        if instructions := str(written.get("instructions") or "").strip():
            changes["instructions"] = instructions
        if extra := str(written.get("says") or "").strip():
            base = changes.get("instructions", s.instructions)
            changes["instructions"] = f"{base}\n\n{extra}" if base else extra
        if (steps := written.get("steps-at-most")) is not None:
            try:
                # Written, so a runtime that holds only the ceilings an author
                # wrote (`steps_written`) holds this one too.
                changes["max_steps"] = int(steps)
                changes["steps_written"] = True
            except (TypeError, ValueError):
                pass
        named = written.get("may-use")
        if isinstance(named, str):
            # `may-use: lookup` is the same line as a list of one. Read only as
            # a list, the lone form narrowed nothing and a read-only variant
            # kept the tool that writes.
            named = [named]
        if named is not None:
            # Everything `variant.may-use:` names: tools, procedures, knowledge
            # and the programs the agent's own `uses:` reaches. A kind it can
            # name and this left alone would be a narrowing with a hole in it.
            keep = {str(x) for x in named}
            changes["tools"] = tuple(t for t in s.tools if t.name in keep)
            changes["skills"] = tuple(k for k in s.skills if k.name in keep)
            changes["knowledge"] = tuple(k for k in s.knowledge if k.name in keep)
            changes["programs"] = tuple(
                p for p in s.programs if p.name in keep or "uses" not in p.reached_by
            )
        if "instructions" in changes:
            # The words changed, so what a run must fill changed with them. Left
            # as the authored agent's, a hole only the variant writes was one no
            # host was told to supply and nothing filled.
            changes["holes"] = tuple(
                dict.fromkeys(holes_in(changes["instructions"]) + holes_in(s.description))
            )
        return replace(s, **changes) if changes else s

    return apply

TransportFactory = Callable[[str, str], Any]  # (model_name, strategy_name) -> Transport


def _why_it_stopped(stopped: Exception) -> "tuple[str, str] | None":
    """Which of the three no-score states this is, and the cause in words.

    `None` means it is NOT one of them, and that is the important return: an
    `AttributeError` in our own program, or a `TypeError` from a factory with the
    wrong arity, is a defect in PACT. Filing it as "the model did not answer" and
    then telling the author to start a model runtime is a right field name with a
    wrong diagnosis and a remedy that cannot help — the shape C9 already names as
    a defect in this repository (`docs/70-PRODUCTION-GAP-REGISTER.md`). Those
    propagate.

    `httpx` is imported here rather than at the top because this module is the
    decision procedure and does not otherwise need a network library; a
    distribution that scores with a scripted transport must still be able to
    import it.
    """
    said = " ".join(str(stopped).split())
    try:
        import httpx
    except ImportError:  # pragma: no cover — httpx ships with the adapter
        httpx = None  # type: ignore[assignment]

    if httpx is not None:
        if isinstance(stopped, httpx.HTTPStatusError):
            code = stopped.response.status_code
            if code == 404:
                return NOT_SERVING, (
                    "something is listening there and answered 404 — it is not "
                    "serving a model by that name"
                )
            return NOT_A_RUNTIME, (
                f"something is listening there and answered HTTP {code} rather "
                f"than a completion"
            )
        if isinstance(stopped, httpx.ConnectTimeout):
            return NOT_SERVING, "nothing accepted the connection before it timed out"
        if isinstance(stopped, httpx.TimeoutException):
            # The socket was ACCEPTED. Nothing about this machine needs starting,
            # so it must not be filed under "not serving" whatever the remedy
            # sentence for that group happens to say.
            return STOPPED, (
                "the connection was accepted and no answer arrived before the "
                "request timed out"
            )
        if isinstance(stopped, httpx.TransportError):
            return NOT_SERVING, said or "nothing accepted the connection"
    if isinstance(stopped, json.JSONDecodeError):
        return NOT_A_RUNTIME, (
            "something is listening there and what it sent back was not JSON, so "
            "it is not a model runtime"
        )
    if isinstance(stopped, RuntimeError):
        # The product raising on purpose: `harness.delegate_by_running` raises
        # this when a member goes over the budget its grant allowed it, and when
        # a member halts without finishing. Both are facts about the RUN, and
        # neither is anything to do with whether a machine is serving a model.
        return STOPPED, said or stopped.__class__.__name__
    return None


def evaluate(
    spec: AgentSpec,
    cases: list[Case],
    rules: list[str],
    bar: float,
    transport_for: TransportFactory,
    model: str,
    strategy_name: str,
    tools: dict[str, Callable[[dict], str]],
    *,
    document: dict[str, Any],
    min_cases: int = 5,
    judge: Any = None,
    metrics: Any = None,
) -> Verdict:
    """Score one model on one strategy against the author's own suite.

    `document` is REQUIRED and keyword-only, because the one thing it is for is
    the thing that is silently wrong when it is missing: an agent with a `team:`
    is only runnable here if `run` is given an `ask_member`, and building one
    needs the document its members are defined in. Without it every delegation
    parks instead of asking, every governed case comes back "did not answer", and
    the model under test is blamed for a suspension — the identical defect
    `scoring._run_every_case` records at its own `ask_member` line. A default of
    `None` would have made that a mistake a caller can make by omission, which is
    how this module's transport factory came to default to `None` (D3).

    `judge` is the grader for the suite's `judged:` rules, built from the
    document by `judge.judge_of`. It is threaded rather than built here for the
    same reason the transport is: this function must stay deterministic — the
    portability figure is a claim about a decision procedure — and a live grading
    model inside the search would make the same suite score differently twice.
    With none, a `judged:` rule lands on `Verdict.unenforced` rather than being
    dropped, so a portability number never quietly rests on a rule nobody ran.

    `metrics` is the author's `evals.metrics:` line, threaded for exactly the
    same reason and read off the document by `resolve()`. A portability figure
    computed with the suite's scores left out would be a claim about a smaller
    suite than the author wrote — the same hole one construct over.
    """
    results: list[CaseOutcome] = []
    # The approval gate is SUPPRESSED here, and it has to be said out loud rather
    # than left to a default argument. A run that parks for a person cannot be
    # scored — every governed case would come back "did not answer" and the model
    # under test would be blamed for a policy doing its job. The questions stay,
    # so wording an eval asserts on is unchanged; only the stopping goes.
    #
    # The rule that makes this safe is that it is the ONLY suppression: a real
    # run parks, a delegated member parks under its own policy, and this one line
    # is where a reader looks to find out why the numbers differ.
    ungated = spec.asking.asking_only()
    # THE TEAM RUNS, for the reason `scoring._run_every_case` gives at its own
    # `ask_member` line and with the same construction. Without this, `run` gets
    # no `ask_member`, `harness.run` leaves `delegates` empty, and every call to a
    # teammate parks the run as WAITING_FOR_ANOTHER_AGENT — so scoring an agent
    # with a `team:` measured a suspension and blamed the model for it. The
    # worked example this door is run against has a `team:` of two, and the
    # measured result of omitting this was six cases out of six failing with
    # `expected decision 'approved', got ''`.
    #
    # The member runs on THE MODEL UNDER TEST, which is what makes the figure a
    # portability figure: "can this model do this agent's job" includes the work
    # its specialists do. `delegate_by_running` gives the member its share of the
    # budget and charges back what it spent.
    ask_member = (
        delegate_by_running(document, lambda _member: transport_for(model, strategy_name))
        if spec.team
        else None
    )
    #: Why the suite stopped early, when it did. `None` means it did not.
    silence: "Silence | None" = None
    for case in cases:
        # DELIBERATELY OUTSIDE the `try` below, and belt-and-braces rather than
        # load-bearing since the `except` narrowed: building the transport is this
        # function's contract with whoever called it, and a factory that takes the
        # wrong arguments is a mistake in the program — not a model that did not
        # answer. Moving this line inside the `try` is a mutation
        # `test_a_factory_with_the_wrong_arity_is_a_defect_and_not_a_model_that_did_not_answer`
        # covers, because `_why_it_stopped` returns `None` for a `TypeError` and
        # the raise goes on out.
        transport = transport_for(model, strategy_name)
        try:
            result = asyncio.run(
                run(spec, transport, case.when, tools, asking=ungated,
                    ask_member=ask_member)
            )
        except Exception as stopped:
            reading = _why_it_stopped(stopped)
            if reading is None:
                # NOT one of the three no-score states, so it is a defect, and a
                # defect reported as "this machine is not serving them. Start the
                # model runtime" sends the author to fix a machine that is fine.
                # `except Exception` here filed a missing attribute in our own
                # program, and `harness`'s own deliberate `RuntimeError`s, under
                # that sentence with the cause dropped.
                raise
            kind, cause = reading
            # WHAT ANSWERED IS KEPT, even though the score is not. "Answered three
            # of six and then stopped" and "never opened a socket" were the same
            # state downstream, so a machine that was serving perfectly well was
            # reported to its author as one that is not.
            silence = Silence(
                kind=kind,
                cause=cause,
                answered=len(results),
                of=len(cases),
                unenforced=tuple(
                    dict.fromkeys(s for r in results for s in r.unenforced)
                ),
            )
            break
        results.append(check(case, result, rules, judge=judge, metrics=metrics))
    if silence is not None:
        # UNDECIDED with no RESULTS kept, where `_run_every_case` keeps what it
        # got. The divergence is this module's whole argument: a portability
        # figure is a claim about the author's suite, and one computed off the
        # four cases that answered before the runtime went away is a claim about
        # a smaller suite than they wrote (AC-3.1). A row that went quiet gets a
        # reason here rather than a number.
        #
        # WHAT IS NOT DISCARDED is on the `Silence`: how many cases answered, why
        # it stopped, and every rule those cases met that nothing could grade.
        # Dropping the score is argued; dropping a "a rule of yours was never
        # applied" report is the silent degradation T7 forbids by name, and
        # `Verdict.unenforced` reads it back so `render` still prints it.
        return Verdict("UNDECIDED", 0.0, bar, [], silence.as_sentence(model), silence)
    return verdict(results, bar, min_cases=min_cases)


def _went_quiet(v: Verdict) -> bool:
    """Whether this row never answered at all, as against answering badly.

    Structural, and now off the `Silence` itself rather than off "UNDECIDED with
    no results": that shape could not tell a row that answered three of six cases
    apart from one that never opened a socket, and the sentence built on it told
    the author of the first that this machine is not serving the model.
    """
    return v.silence is not None and v.silence.answered == 0


def resolve(
    spec: AgentSpec,
    document: dict[str, Any],
    requested: str,
    strategies: "dict[str, Strategy] | None" = None,
    # `| None` and NOT a `# type: ignore[assignment]`. The annotation was
    # `TransportFactory` with a `None` default — a declared shape the value could
    # not have — and the mismatch was silenced by a directive addressed to a type
    # checker this tree does not run (`grep -n "mypy\|pyright" pyproject.toml
    # scripts/test-all.sh` -> no output). AD-41: delete the unenforceable control
    # rather than annotate around it. What the parameter can actually hold is
    # written here, and what it must be by the time anything uses it is enforced
    # in the body.
    transport_for: "TransportFactory | None" = None,
    tools: "dict[str, Callable[[dict], str]] | None" = None,
    catalogue: "list[ModelEntry] | None" = None,
    needs: dict[str, Any] | None = None,
    agent_key: str = "",
    baseline: str = "the hand-authored frontier strategy",
    judge: Any = None,
) -> PortabilityReport:
    """Bind `requested` if it can meet the contract; otherwise refuse and advise.

    Order matters: the authored strategy is tried first, then alternatives in
    declaration order. Text and procedure before decomposition — MASS shows
    prompt changes dominate topology changes, and decomposition actively hurts
    below a capability gap of ~0.25.

    `catalogue` and `needs` both default to the real thing. Passing neither is
    the normal call, and it is what makes D11's recommendation a statement about
    models this distribution can serve rather than about whatever list the caller
    happened to build. Both stay overridable so a test can hold the search fixed,
    but a *default* of "whatever you were handed" is how the price list ended up
    being three invented rows for a round.
    """
    # `transport_for` KEEPS its `None` default, and the reason is not the one an
    # earlier round of this comment gave. That round said a required parameter
    # would "break all nine existing call sites, every one of which passes it
    # positionally". Measured instead of recalled — by parsing the three files
    # that call this function and counting `ast.Call` nodes named `resolve`,
    # because a grep for the string also matches `Path.resolve()` and prose:
    # there are SEVENTEEN call sites, not nine — fifteen positional, one that
    # omits the argument on purpose (the guard's own test), and the one
    # PRODUCTION caller, `scoring.py:1005`, which passes `transport_for=` BY
    # KEYWORD. Making the parameter keyword-only would therefore break zero
    # shipped callers and cost fifteen mechanical edits in two test files. Seven
    # of the seventeen arrived with this very change — all of them in the door
    # test file, which `git status --porcelain` still reports as untracked — so
    # "existing" was wrong as well as "nine".
    #
    # THAT COUNT WAS ITSELF WRONG FOR A ROUND, in the same direction and for the
    # same reason. It read FOURTEEN, measured before the two tests this change
    # added had been written, and the three call sites they brought were never
    # re-counted. A number in a comment is a measurement with no test behind it;
    # re-take it rather than trusting it.
    #
    # The decision was reopened on that measurement and the default was kept
    # DELIBERATELY, for one reason: a required parameter buys Python's stock
    # `TypeError: resolve() missing 1 required keyword-only argument` and loses
    # the authored sentence below, which is the sentence that says WHY a factory
    # is needed. D13 — a refusal is a sentence, not a stack — applies to the
    # library door as much as to the CLI. What actually closes the defect class
    # is the check itself, and the check now covers the whole class rather than
    # one member of it.
    #
    # WHAT IS CHECKED, AND THAT IT IS CHECKED HERE RATHER THAN NARRATED. An
    # earlier round of this comment claimed the factory's ARITY "CANNOT" be seen
    # at runtime and handed the job to a test file. That was false: three lines
    # of `inspect` decide it, and they reject the exact original A1 defect (a
    # one-argument lambda handed to the two-argument protocol) while admitting
    # `scoring._choose`'s two-argument closure, a `*args` forwarder, a callable
    # object and a `functools.partial`. Under AD-41 and T7 a declared control
    # nothing enforces is worse than an absent one, so the annotation
    # `TransportFactory = Callable[[str, str], Any]` — which no type checker in
    # this tree reads, there being no `[tool.mypy]` in `pyproject.toml` and no
    # checker in `scripts/test-all.sh` — is backed by an executable check rather
    # than by a comment explaining that it is not.
    #
    # Six wrong shapes were measured against the old one-word guard and five of
    # them reached `TypeError` four frames down with a message naming neither
    # `resolve` nor `transport_for`: a zero-, one- and three-argument lambda, a
    # transport INSTANCE, a bare string, and `False` — falsy, not callable, not
    # `None`, and admitted. All six now stop here with the sentence below.
    what = "nothing" if transport_for is None else repr(transport_for)
    needed = (
        "resolve() needs a transport_for(model_name, strategy_name) factory: "
        "it decides portability by RUNNING the author's cases, and there is "
        "nothing honest to return without something to run them on"
    )
    if not callable(transport_for):
        raise TypeError(f"{needed} — got {what}, which is not callable")
    try:
        shape: "inspect.Signature | None" = inspect.signature(transport_for)
    except (TypeError, ValueError):
        # A C builtin whose arity is not introspectable. ADMITTED rather than
        # refused: refusing on "I could not look" would turn a guard into a
        # closed door for callers that are fine, which is the failure mode a
        # gate that fires on the wrong evidence has.
        shape = None
    if shape is not None:
        try:
            shape.bind("model_name", "strategy_name")
        except TypeError as wrong_arity:
            raise TypeError(
                f"{needed} — got {what}, which cannot be called with two "
                f"positional arguments: {wrong_arity}"
            ) from wrong_arity
    # The author's own `variants:` unless the caller overrode them. `is None`,
    # not `or`: an author who wrote no variants gets `{"authored": ...}` and one
    # who deliberately passed `{}` gets nothing, and those are different facts.
    if strategies is None:
        strategies = strategies_of(spec)
    tools = {} if tools is None else tools
    cases = Case.from_document(document)
    rules = rules_of(document)
    # The suite's own ready-made scores, off the same document the rules come
    # from. Read here rather than taken as a parameter for the reason `rules` is:
    # a portability number is a claim about the author's whole suite.
    scores = metrics_of(document, spec.workspace)
    bar = bar_of(document)
    if catalogue is None:
        catalogue = list(load_catalogue().entries)
    if needs is None:
        needs = needs_of(document, agent_key or spec.name)

    by_name = {m.name: m for m in catalogue}
    entry = by_name.get(requested)
    if entry is None:
        return PortabilityReport(
            spec.name, requested, baseline,
            Verdict("FAIL", 0.0, bar, [], f"{requested!r} is not in the catalogue"),
            "authored",
        )

    ok, why = entry.satisfies(needs)
    if not ok:
        report = PortabilityReport(
            spec.name, requested, baseline,
            Verdict("FAIL", 0.0, bar, [], f"{requested} {why}"), "authored",
        )
        report.instead = _cheapest_passing(
            spec, document, catalogue, strategies, transport_for, tools, needs, bar,
            exclude=requested, judge=judge,
        )
        report.recommendation = report.instead.sentence
        return report

    last: Verdict | None = None
    for strategy_name, transform in strategies.items():
        candidate = transform(spec)
        v = evaluate(candidate, cases, rules, bar, transport_for, requested,
                     strategy_name, tools, document=document, judge=judge,
                     metrics=scores)
        last = v
        if v.outcome == "PASS":
            return PortabilityReport(spec.name, requested, baseline, v, strategy_name)

    # `last is None` MEANS THE LOOP ABOVE DID NOT RUN, which happens on exactly
    # one input: `strategies={}`, which `resolve`'s docstring declares supported.
    # It used to fall into `last or Verdict("FAIL", ...)` labelled `exhausted` —
    # a FAIL verdict and the word "exhausted" over a search that built no
    # transport and ran no case. `render` was already honest about the figure
    # ("score: not measured"), so the head line read `PORTABILITY: FAIL for
    # qwen2.5-vl-7b-instruct (strategy exhausted)` with nothing exhausted and
    # nothing failed. UNDECIDED is the outcome this module already uses for "no
    # score could be taken", and the note says which of the reasons it is.
    if last is None:
        report = PortabilityReport(
            spec.name, requested, baseline,
            Verdict("UNDECIDED", 0.0, bar, [],
                    f"no strategy was supplied, so {requested} was never run"),
            "none supplied",
        )
    else:
        report = PortabilityReport(spec.name, requested, baseline, last, "exhausted")
    report.instead = _cheapest_passing(
        spec, document, catalogue, strategies, transport_for, tools, needs, bar,
        exclude=requested, judge=judge,
    )
    report.recommendation = report.instead.sentence
    return report


@dataclass(frozen=True)
class Alternative:
    """What the search found instead: the NAME and the sentence, not one or the
    other.

    The sentence alone was the whole return for a round, and `--choose-model`
    could therefore refuse with an error over a model it had just watched pass —
    the search did the work, printed prose about it, and threw the answer away.
    A caller that has to bind something needs the name; a caller that has to
    print something needs the sentence; parsing the first back out of the second
    is how a report becomes an API nobody declared.
    """

    #: The row that passed, or `""` when nothing did.
    model: str = ""
    #: What to print, whether or not anything passed.
    sentence: str = ""
    #: The strategy it passed under, and at what score — the two facts an author
    #: needs to reproduce it.
    strategy: str = ""
    score: float = 0.0


def _why_no_score(rows: "dict[str, Silence]") -> str:
    """The rows that produced no score, grouped by WHAT TO DO about them.

    One clause per remedy rather than one per row, and never a remedy the
    evidence does not support. "This machine is not serving them. Start the model
    runtime" was printed for every non-result there was — for a socket that
    connected and answered `<html>nginx</html>`, for a teammate that went over
    the budget its author set, and for a defect in our own program. A support
    lead who cannot write code (D13) then goes and starts a runtime that is
    already running.
    """
    said: list[str] = []

    def grouped(kind: str) -> "dict[str, list[str]]":
        """The rows of one kind that never answered, by the cause they share.

        BY CAUSE and not merely by kind, because the cause is the half a reader
        acts on: a row nothing accepted a connection for and a row whose runtime
        timed out reach the same remedy by different roads, and printing the
        first row's cause over both is how a report starts describing a run that
        did not happen.
        """
        out: dict[str, list[str]] = {}
        for name, s in rows.items():
            if s.kind == kind and not s.answered:
                out.setdefault(s.cause, []).append(name)
        return out

    for cause, names in grouped(NOT_SERVING).items():
        said.append(
            f"this machine is not serving {', '.join(names)} — {cause}. Start the "
            f"model runtime, or run it again with `--serving-at` pointing at the "
            f"machine that does"
        )
    for cause, names in grouped(NOT_A_RUNTIME).items():
        said.append(
            f"{', '.join(names)}: {cause}. Point `--serving-at` at a machine "
            f"that is serving models"
        )
    for name, s in rows.items():
        if not s.answered and s.kind in (NOT_SERVING, NOT_A_RUNTIME):
            continue
        if s.answered:
            said.append(
                f"{name} answered {s.answered} of {s.of} cases and then stopped "
                f"— {s.cause}"
            )
        else:
            said.append(f"{name} never answered — {s.cause}")
    return "; ".join(said)


def _cheapest_passing(
    spec, document, catalogue, strategies, transport_for, tools, needs, bar, exclude,
    judge=None,
) -> Alternative:
    """D11: a refusal that does not name an alternative is a dead end.

    And a refusal that names nothing *because nothing qualifies* has to say that
    out loud too, with the line the author would have to change. Returning an
    empty string there was the dead end D11 exists to close, wearing the shape of
    a successful search.
    """
    cases = Case.from_document(document)
    rules = rules_of(document)
    scores = metrics_of(document, spec.workspace)
    ruled_out: list[str] = []
    tried: list[str] = []
    #: Rows that qualified and produced no score, with the reason each one did
    #: not — a different fact from a row that answered badly, and a different
    #: thing for the author to go and do.
    no_score: dict[str, Silence] = {}
    off_box = False
    for entry in sorted(catalogue, key=lambda m: m.ranks_after(needs)):
        if entry.name == exclude:
            continue
        ok, why = entry.satisfies(needs)
        if not ok:
            ruled_out.append(f"{entry.name} {why}")
            off_box = off_box or "leave the box" in why
            continue
        tried.append(entry.name)
        # SEEDED `False`, AND THE THIRD POPULATION IS COUNTED SEPARATELY BELOW.
        # This flag was seeded `not strategies` for a round, so that a caller who
        # passed `strategies={}` — an input `resolve`'s own docstring declares
        # supported — did not have every qualifying row filed as having gone
        # silent. That is a true fact about the rows and it was recorded in the
        # wrong place: marking them SCORED put them in `measured` below, and the
        # author was then told "N model(s) met the requirements and none reached
        # the bar" about a search that ran zero cases and built zero transports.
        # Measured on `examples/refund-desk` with a factory that raises if it is
        # called: 0 factory calls, 0 results, and "5 model(s) met the
        # requirements and none reached the bar".
        #
        # A row nobody tried is neither scored nor silent. It is UNRUN, and the
        # `if not strategies` branch below is where unrun rows get said out loud.
        scored_it = False
        why_not: "Silence | None" = None
        for strategy_name, transform in strategies.items():
            v = evaluate(transform(spec), cases, rules, bar, transport_for,
                         entry.name, strategy_name, tools, document=document,
                         judge=judge, metrics=scores)
            if v.outcome == "PASS":
                return Alternative(
                    entry.name,
                    f"{entry.name} — passes at {v.score:.0%} using the "
                    f"{strategy_name!r} strategy, {entry.price()}",
                    strategy_name,
                    v.score,
                )
            if v.silence is None:
                scored_it = True
            else:
                why_not = v.silence
        if not scored_it and why_not is not None:
            no_score[entry.name] = why_not

    # Nothing passed, and there are two different reasons for that. Both get a
    # sentence, because "no recommendation" printed as an empty string is the
    # dead end D11 exists to close wearing the shape of a finished search.
    reasons = "; ".join(ruled_out[:3])
    fix = (
        " Either add `llm` to `allow-egress:` in `workspace.yaml`, or add a row "
        "to `models/catalog.yaml` for a model this machine serves."
        if off_box
        else ""
    )
    if not tried:
        head = "nothing in the catalogue meets what this agent needs"
        return Alternative(sentence=f"{head} — {reasons}.{fix}")

    # NOTHING WAS RUN, because the caller supplied no strategy to run. Its own
    # sentence, before either of the two below, because it is a third fact and
    # not a shading of either: these rows did not fail to reach the bar (no bar
    # was approached) and they did not go quiet (no socket was opened). The
    # remedy is not to edit the suite and not to start a runtime — it is to pass
    # a strategy — so printing it as either of those sends the author somewhere
    # that cannot help, the shape D13 and C9 both name.
    if not strategies:
        head = (
            f"nothing was measured: {len(tried)} model(s) met the requirements "
            f"and no strategy was supplied, so not one of them was run"
        )
        if ruled_out:
            head += f". The rest were ruled out before any eval ran — {reasons}"
        return Alternative(sentence=f"{head}.{fix}")

    # THE POPULATIONS ARE COUNTED SEPARATELY, and the mixed case is the ordinary
    # one rather than a corner: a box serving one local model has that row answer
    # and every other qualifying row go quiet. Rolling the quiet rows into "met
    # the requirements and none reached the bar" states a measurement that was
    # never taken, and sends the author to edit their suite over models their
    # machine is not serving.
    measured = [name for name in tried if name not in no_score]
    silent = all(s.answered == 0 for s in no_score.values())
    if not measured:
        # NOT "none reached the bar". No bar was reached or missed, because
        # nothing was measured at all. And "none of them answered" only when that
        # is what happened: a row that answered four cases and stopped on the
        # fifth ANSWERED, and reporting it as a row that did not is how a machine
        # that is serving a model was reported as one that is not.
        opened = (
            "none of them answered" if silent else "no score could be taken off any"
        )
        head = (
            f"nothing could be measured: {len(tried)} model(s) met the "
            f"requirements and {opened} — {_why_no_score(no_score)}"
        )
        if ruled_out:
            head += f". The rest were ruled out before any eval ran — {reasons}"
        return Alternative(sentence=f"{head}.{fix}")
    head = (
        f"nothing in the catalogue passed: {len(measured)} model(s) met the "
        f"requirements and none reached the bar"
    )
    if ruled_out:
        head += f", and the rest were ruled out before any eval ran — {reasons}"
    if no_score:
        # A SEPARATE SENTENCE, and it names them. These rows are not part of the
        # count above and never were measured against the bar; what the author
        # has to do about them is start a runtime, not change their suite.
        head += (
            f". {len(no_score)} more met the requirements and "
            f"{'never answered' if silent else 'produced no score'} — "
            f"{_why_no_score(no_score)}"
        )
    return Alternative(sentence=f"{head}.{fix}")
