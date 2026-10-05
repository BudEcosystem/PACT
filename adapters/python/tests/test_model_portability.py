"""Model portability, end to end.

An agent authored against a frontier model is moved onto a small one. Either it
still meets its contract — proven by the author's own eval suite — or the system
refuses to bind and names the cheapest model that does.

The models here are scripted so the run is deterministic and offline (D17). What
is being tested is the *decision procedure*: does the resolver bind only on
evidence, does it try alternative strategies before giving up, and does it
recommend rather than merely refuse.

**The candidates are the shipped catalogue.** For a round they were three
literals in this file — `frontier-xl`, `mid-8b`, `small-3b`, invented, with
invented prices — so "the cheapest passing model" was ranked against a price
list that existed nowhere but here, and `models/catalog.yaml` was read for
context windows and for nothing else. A recommendation is only worth printing if
it names a model this distribution can actually serve, so the list comes off
disk and so do the prices.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.evals import Case, bar_of  # noqa: E402
from pact_adapters.harness import ToolCall  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.resolve import (  # noqa: E402
    ModelEntry,
    load_catalogue,
    needs_of,
    resolve,
    strategies_of,
)
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"

# --- the three the scripts below know how to answer for ---------------------
#
# Real catalogue ids, with the prices the catalogue publishes: 5.00, 1.00 and 0
# USD per million input tokens. `FRONTIER` is the most expensive row in the file
# and `MID` is a fifth of it, so "the cheapest thing that works" is a claim about
# the shipped price list rather than about numbers this file made up.
FRONTIER = "claude-opus-5"
MID = "claude-haiku-4-5"
SMALL = "llama3.2-1b-instruct"

#: A row the catalogue publishes with `cost: unknown` — the one figure this
#: distribution deliberately refuses to guess.
UNPRICED = "gpt-5.4"

TOOLS = {"zendesk": lambda a: "lamp, 6 days ago, arrived broken, 40 USD, gift card 20 USD"}


@pytest.fixture(scope="session")
def document() -> dict:
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run([str(PACT_BIN), "show", str(EXAMPLE)],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


@pytest.fixture(scope="session")
def spec(document: dict) -> AgentSpec:
    return AgentSpec.from_document(document, "refund-desk")


@pytest.fixture()
def connected(document: dict) -> dict:
    """The same workspace, with the model call allowed off the machine.

    `examples/refund-desk` writes `allow-egress: []` — nothing in it may talk
    outside the box — and the resolver now honours that (Y16), so every row the
    catalogue serves over an API is refused before an eval is run. That is the
    right answer for the shipped example and the wrong fixture for a test about
    *price*, since every locally-served row costs zero. One line changes it, and
    the line is the author's own.
    """
    return {**document, "allow-egress": ["llm"]}


#: The requirements this file's scripts are about — deliberately not the worked
#: example's own, which also demand vision. Tool-calling and a rung, which is
#: what a refund decision needs and what the scripted answers below exercise.
NEEDS = {
    "capabilities": ["tools"],
    "scores": {},
    "context-at-least": "32k",
    "reasoning": "steady",
    "must-stay-on-this-machine": False,
}


# --- the scripted executors ------------------------------------------------
#
# `claude-opus-5` answers correctly one-shot. `claude-haiku-4-5` needs the tool
# consulted first — which is exactly what the "decomposed" strategy provides.
# Everything else gets it wrong under every strategy, which is the honest case
# the design must handle without lying.

CORRECT = {
    "clear-approve": "Approved. The lamp arrived damaged within 30 days, refund 40 USD.",
    "outside-window": "Declined. More than 30 days have passed since the purchase.",
    "fraud-signal": "Declined. A person will review this before any refund is issued.",
    "partial-gift-card": "Approved. Refund 60 USD, with the gift card portion returned to a gift card.",
    "personalised-item": "Declined. It was made to order, so it cannot be returned unless faulty.",
    "sale-item-damaged": "Approved. Sale items follow the same rules and this one was faulty.",
}


def _answer_for(prompt: str) -> str:
    p = prompt.lower()
    if "lamp" in p:
        return CORRECT["clear-approve"]
    if "headphones" in p:
        return CORRECT["outside-window"]
    if "fourth refund" in p:
        return CORRECT["fraud-signal"]
    if "kettle" in p or "gift card" in p:
        return CORRECT["partial-gift-card"]
    if "mug" in p:
        return CORRECT["personalised-item"]
    if "jacket" in p:
        return CORRECT["sale-item-damaged"]
    return "Declined."


def transport_for(model: str, strategy: str):
    """Build the scripted executor for one (model, strategy) pair."""

    def make(prompt: str) -> Script:
        good = Turn(_answer_for(prompt))
        if model == FRONTIER:
            return Script([good])
        if model == MID:
            # Reaches the right answer only when told to consult the tool first.
            if strategy == "decomposed":
                return Script([Turn("Checking.", (ToolCall("zendesk", {}),)), good])
            return Script([Turn("It depends on the circumstances.")])
        return Script([Turn("I am not sure.")])  # every other row, any strategy

    class Bound(ReferenceTransport):
        name = f"{model}/{strategy}"

        def __init__(self) -> None:  # noqa: D107
            super().__init__(Script([Turn("")]))

        async def model_call(self, system, history, tools):
            if self.script.calls == 0:
                prompt = next((m["content"] for m in history if m["role"] == "user"), "")
                self.script = make(prompt)
            return await super().model_call(system, history, tools)

    return Bound()


#: The search, read from the AUTHOR'S OWN `variants:` block.
#:
#: These two were Python lambdas in this file, and they were the only strategies
#: anywhere in the tree — including the `decomposed` one README.md quotes a
#: measured result for. So the headline claim of the whole project, model
#: portability, had "write a lambda" as its authoring surface, which D14 says may
#: never be the answer for a capability in the core. `variants:` is now a closed
#: group in the specification, `AgentSpec` carries it, and `resolve()` builds the
#: search from it when the caller passes nothing.
#:
#: Text and procedure before topology: MASS finds prompt changes dominate, and
#: decomposition hurts below a capability gap of ~0.25 — which is why `authored`
#: is first and why the order here is the order the author wrote.
def strategies(spec: AgentSpec) -> dict:
    return strategies_of(spec)


# --- the tests -------------------------------------------------------------


def test_the_suite_is_large_enough_to_decide(document: dict) -> None:
    """A bar of 70% on three cases is not evidence. The runner must refuse to
    decide below the floor, so the example itself has to clear it."""
    assert len(Case.from_document(document)) >= 5


def test_the_candidates_are_the_models_this_distribution_actually_ships(spec, document) -> None:
    """The list a recommendation is drawn from is the file, not the caller.

    `resolve()` used to require a catalogue argument, and the only caller in the
    tree handed it three invented models. So `models/catalog.yaml` was read for
    context windows and for nothing else, and D11's "the cheapest model that does
    pass" could never name a model anybody could serve.
    """
    shipped = {e.name for e in load_catalogue().entries}
    assert {FRONTIER, MID, SMALL, UNPRICED} <= shipped

    r = resolve(spec, document, FRONTIER, strategies(spec), transport_for, TOOLS, needs=NEEDS)
    assert r.verdict.outcome == "PASS", r.render()


def test_the_frontier_model_passes_on_the_authored_strategy(spec, document) -> None:
    r = resolve(spec, document, FRONTIER, strategies(spec), transport_for, TOOLS, needs=NEEDS)
    assert r.verdict.outcome == "PASS", r.render()
    assert r.strategy == "authored"


def test_a_smaller_model_is_rescued_by_a_different_strategy(spec, document) -> None:
    """The core of T4: the contract is fixed, the strategy is plural. The mid
    model fails as authored and passes decomposed — without touching the
    contract."""
    r = resolve(spec, document, MID, strategies(spec), transport_for, TOOLS, needs=NEEDS)
    assert r.verdict.outcome == "PASS", r.render()
    assert r.strategy == "decomposed", "the authored strategy should not have passed"


def test_a_model_that_cannot_do_it_is_refused_and_an_alternative_named(spec, document) -> None:
    """D11: refusing without advising is a dead end."""
    r = resolve(spec, document, SMALL, strategies(spec), transport_for, TOOLS, needs=NEEDS)
    assert r.verdict.outcome in {"FAIL", "UNDECIDED"}, r.render()
    assert MID in r.recommendation, r.render()
    assert "passes at" in r.recommendation


def test_capability_prefilter_rejects_before_any_eval_is_run(spec, document) -> None:
    """Requirements are a cheap filter, never the proof (FR-2.1.2)."""
    needs = {**NEEDS, "capabilities": ["images"], "reasoning": "deep"}
    r = resolve(spec, document, SMALL, strategies(spec), transport_for, TOOLS, needs=needs)
    assert r.verdict.outcome == "FAIL"
    assert "images" in r.verdict.note or "rung" in r.verdict.note


def test_the_report_always_names_its_baseline(spec, document) -> None:
    """AC-3.1. 98–114% against a hand-authored frontier strategy and 70–94%
    against an optimised one are different claims; a ratio without its baseline
    is not reportable."""
    r = resolve(spec, document, MID, strategies(spec), transport_for, TOOLS, needs=NEEDS)
    assert r.baseline
    assert "measured against:" in r.render()


def test_an_unknown_model_fails_closed(spec, document) -> None:
    r = resolve(spec, document, "gpt-nonexistent", strategies(spec), transport_for, TOOLS,
                needs=NEEDS)
    assert r.verdict.outcome == "FAIL"
    assert "not in the catalogue" in r.verdict.note


def test_the_recommendation_is_the_cheapest_passing_model(spec, document) -> None:
    """Ranking by cost is the point: the useful answer is the cheapest thing
    that works, not merely something that works — and the prices are the ones
    `models/catalog.yaml` publishes, so this is a claim about real money."""
    r = resolve(spec, document, SMALL, strategies(spec), transport_for, TOOLS, needs=NEEDS)
    assert MID in r.recommendation
    assert FRONTIER not in r.recommendation, (
        f"{FRONTIER} is five times the price of {MID}"
    )


def test_a_model_whose_price_nobody_published_is_never_the_cheapest(spec, document) -> None:
    """`cost: unknown` used to read as 0.0, which sorted it FIRST.

    The one row this catalogue deliberately publishes as unsourced therefore
    ranked as the cheapest model on offer, and D11's line printed
    `at 0.0/1k tokens` — a price nobody published, in the sentence the whole
    decision hangs on. `unknown` is not a number; it ranks last and says so.
    """
    catalogue = load_catalogue()
    unpriced = catalogue.get(UNPRICED)
    assert unpriced is not None and unpriced.cost is None
    assert "cannot source" in unpriced.price()

    order = sorted(catalogue.entries, key=lambda e: e.ranks_after({}))
    assert order[-1].name == UNPRICED, [e.name for e in order]


def test_an_air_gapped_workspace_is_never_offered_a_model_it_cannot_reach(
    spec, document
) -> None:
    """D17 and Y16, in the one sentence an author reads after a failure.

    `examples/refund-desk` says `allow-egress: []` — nothing here talks outside
    the box. Every model the catalogue serves over an API is therefore
    unreachable, and recommending one is worse than recommending nothing: it
    sends an author to buy an API key for a machine that has no network. The
    catalogue records `served-by: [{runtime: …, endpoint: local}]` and nothing
    read it until now.
    """
    needs = needs_of(document, "refund-desk")
    assert needs["must-stay-on-this-machine"] is True

    r = resolve(spec, document, SMALL, strategies(spec), transport_for, TOOLS, needs=needs)
    # Nothing is OFFERED. The off-box rows appear only as things that were ruled
    # out, with the reason, which is the opposite of a recommendation.
    assert "RECOMMENDED" not in r.render(), r.render()
    assert "NO ALTERNATIVE" in r.render(), r.render()
    assert "does not let the model call leave the box" in r.recommendation
    # And it does not stop at silence: the refusal names the line to change.
    assert "allow-egress" in r.recommendation, r.render()


def test_the_needs_the_author_wrote_are_the_needs_the_resolver_applies(document) -> None:
    """`needs:` is seven core-tier lines that bound against nothing for a round.

    `satisfies()` expected a shape no loader produced, so every call site passed
    `{}` and the pre-filter was `(True, "")` for every model in the file. The
    worked example's `images: yes` and `context-at-least: 32k` are the two that
    show it: one of them removes every text-only row from the candidate set.
    """
    needs = needs_of(document, "refund-desk")
    assert "images" in needs["capabilities"]
    assert "tools" in needs["capabilities"]
    assert needs["context-at-least"] == "32k"
    assert needs["reasoning"] == "careful"

    catalogue = load_catalogue()
    passing = [e.name for e in catalogue.entries if e.satisfies(needs)[0]]
    assert passing, (
        "no row can serve the shipped example air-gapped with vision — "
        "models/catalog.yaml needs a locally-served vision row"
    )
    for name in passing:
        assert catalogue.get(name).served_locally


def test_a_requirement_the_catalogue_cannot_measure_ranks_last_and_still_binds(
    document,
) -> None:
    """Y12's rule, applied to both figures the catalogue can be silent about.

    "A row with no `reasoning` block is UNKNOWN. At core tier UNKNOWN BINDS and
    ranks last." A beginner predicate that can silently match nothing is worse
    than one that ranks, so an unplaced rung and an unsourced window lose a
    tie-break and never a candidacy.
    """
    catalogue = load_catalogue()
    needs = {"reasoning": "deep", "context-at-least": "500k"}

    unplaced = catalogue.get("qwen2.5-vl-7b-instruct")
    assert unplaced.reasoning == "" and unplaced.context_window is None
    assert unplaced.satisfies(needs) == (True, "")

    # A figure the catalogue DOES record and that falls short is the other half:
    # it filters, and the diagnostic says by how much.
    placed = catalogue.get("llama3.2-1b-instruct")
    ok, why = placed.satisfies({"reasoning": "deep"})
    assert not ok and "rung" in why, why
    ok, why = placed.satisfies({"context-at-least": "500k"})
    assert not ok and "holds 131,072" in why, why

    order = [e.name for e in sorted(catalogue.entries, key=lambda e: e.ranks_after(needs))]
    assert order.index("claude-opus-5") < order.index("qwen2.5-vl-7b-instruct")


def test_a_benchmark_floor_rules_a_model_out_both_when_it_misses_and_when_it_is_silent(
) -> None:
    """`needs: scores:` — the one requirement in that block nothing asserted.

    Deleting the comparison — `if have <= threshold:` for `if False:` — left the
    whole suite green, and coverage reported these five lines as never executed.
    So the expert-tier floor that is supposed to keep a model off a contract it
    cannot meet let every model through, and D11's own headline example
    (`answer_relevancy 0.61 < 0.80 required`) was a sentence nothing could
    produce.

    Both arms, because they are different refusals and only one of them is about
    the model. A row that PUBLISHES a figure and falls short is a measured
    failure and the message quotes both numbers. A row that publishes nothing is
    not a worse model — it is an unmeasured one — and saying so is the same rule
    Y12 applies to an unplaced rung and an unsourced window, in the one place
    where UNKNOWN must NOT bind, because a floor satisfied by silence is not a
    floor.
    """
    # Written as the comparison it is. This line said `{"answer_relevancy": 0.80}`
    # — a bare number, which `_threshold` guessed at as `> 0.80` and
    # `coerce::threshold` has always refused, so no document `pact check` accepted
    # could carry it. Both ports refuse it now (`spec/comparisons.yaml`,
    # `not-comparisons:`), and D11's headline sentence is what is being pinned
    # here, unchanged.
    floor = {"scores": {"answer_relevancy": "> 0.80"}}

    measured = ModelEntry(
        name="qwen3-4b", tier="small", cost=0.0,
        scores={"answer_relevancy": 0.61},
    )
    ok, why = measured.satisfies(floor)
    assert not ok, "0.61 does not clear a 0.8 floor"
    assert "answer_relevancy 0.61 is not > 0.8" in why, why

    # And a figure that DOES clear it binds, so the line refuses on the number
    # rather than on the presence of a `scores:` block.
    passes = ModelEntry(
        name="qwen3-14b", tier="mid", cost=0.0,
        scores={"answer_relevancy": 0.83},
    )
    assert passes.satisfies(floor) == (True, "")
    # Exactly at the floor is not above it — `> 0.80` is what the author typed.
    assert ModelEntry(
        name="qwen3-borderline", tier="mid", cost=0.0,
        scores={"answer_relevancy": 0.80},
    ).satisfies(floor)[0] is False

    silent = load_catalogue().get(FRONTIER)
    assert silent.scores == {}, "this distribution publishes no benchmark figures"
    ok, why = silent.satisfies(floor)
    assert not ok, "silence is not a pass"
    assert "no published answer_relevancy score" in why, why


def test_a_benchmark_floor_the_author_wrote_empties_the_candidate_set(tmp_path) -> None:
    """The same floor, arriving the way an author writes it, refusing something.

    Nothing is constructed here: two lines are added to
    `agents/refund-desk/needs.yaml`, the real loader reads the tree, `needs_of`
    translates the block, and every row in the shipped catalogue is ruled out by
    name. That is what the schema's own help for this field predicts — *"no open
    catalogue carries these, so on an imported catalogue this can only ever empty
    the candidate set"* — and it is the difference between a field that reaches
    an object and a field that refuses something.

    Held against the SHIPPED needs as the other arm, so the emptying is
    demonstrably the two new lines and not the six that were already there.
    """
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    tree = tmp_path / "refund-desk"
    shutil.copytree(EXAMPLE, tree)
    needs_file = tree / "agents" / "refund-desk" / "needs.yaml"
    needs_file.write_text(
        needs_file.read_text() + '\nscores:\n  answer_relevancy: "> 0.8"\n'
    )

    loaded = json.loads(
        subprocess.run([str(PACT_BIN), "show", str(tree)],
                       capture_output=True, text=True, check=True).stdout
    )
    asked = needs_of(loaded, "refund-desk")
    assert asked["scores"] == {"answer_relevancy": "> 0.8"}, asked["scores"]

    # The shipped tree, for the arm this is measured against.
    without = needs_of(json.loads(
        subprocess.run([str(PACT_BIN), "show", str(EXAMPLE)],
                       capture_output=True, text=True, check=True).stdout
    ), "refund-desk")

    catalogue = load_catalogue()
    admitted = [e for e in catalogue.entries if e.satisfies(without)[0]]
    assert admitted, (
        "the shipped needs already admit nothing, so nothing here could be "
        "emptied — models/catalog.yaml needs a locally-served vision row"
    )

    # Every one of them is now refused, and refused for the two lines that were
    # added rather than for the six that were already there. The rows the older
    # requirements had already ruled out are not re-examined: `satisfies` stops
    # at the first thing a model cannot do, which is what makes its sentence one
    # reason and not a list.
    for entry in admitted:
        ok, why = entry.satisfies(asked)
        assert not ok, f"{entry.name} cleared a floor it publishes no figure for"
        assert "no published answer_relevancy score" in why, (entry.name, why)


# ───────── `needs.scores:` — a predicate that could not be satisfied by any data


def test_a_benchmark_figure_the_catalogue_publishes_reaches_the_predicate(
    tmp_path,
) -> None:
    """`needs: scores: {MMLU: 80}` refused every candidate on every threshold.

    `_load_entries` built every `ModelEntry` with `scores={}` — the `benchmarks:`
    key was not read at all — so `satisfies()` answered *"no published MMLU
    score"* however well sourced the catalogue was. Not merely unimplemented: a
    predicate that empties the candidate set whatever the data says is a trap,
    and it is the one Y12 was written about.

    The workspace override layer is where this matters most: an air-gapped box
    with its own measured figures is exactly the case §4.2 made that layer
    normative for.
    """
    from pact_adapters.resolve import load_catalogue

    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "catalog.yaml").write_text(
        """
models:
  measured-locally:
    tier: mid
    cost: { input-per-mtok: 0 USD, output-per-mtok: 0 USD }
    served-by:
      - runtime: ollama
        endpoint: local
    benchmarks:
      MMLU:
        value: 84.1
        provenance:
          source: run on this machine against the published split
          as-of: 2026-07-29
      SWE-Verified: 41.5
      GPQA:
        value: unknown
        provenance: { source: not measured here }
"""
    )
    rows = {e.name: e for e in load_catalogue(workspace=tmp_path).entries}
    entry = rows["measured-locally"]

    # Both shapes read: the two-line provenance form and the bare number, for the
    # stated reason a hand-written override layer must not have to learn the
    # longer one first.
    assert entry.scores == {"MMLU": 84.1, "SWE-Verified": 41.5}, entry.scores
    # `unknown` is DROPPED, not kept as zero. Zero satisfies no threshold and
    # reads as a measurement; absent is the truth.
    assert "GPQA" not in entry.scores

    # The thresholds are WRITTEN AS COMPARISONS. These four lines said
    # `{"MMLU": 80}` — a bare number, which `_threshold` read as `> 80` and
    # `coerce::threshold` has always refused ("a bare number states no
    # comparison"), so `pact check` would not have loaded a document saying it.
    # Both ports refuse it now; see `spec/comparisons.yaml` under
    # `not-comparisons:`. Nothing this test is ABOUT changed — it is about a
    # catalogue's own published figures reaching the predicate.
    ok, why = entry.satisfies({"scores": {"MMLU": "> 80"}})
    assert ok, why
    # And the AC's own example, both metrics at once.
    assert entry.satisfies({"scores": {"MMLU": "> 80", "SWE-Verified": "> 40"}})[0]
    # A threshold it does not clear is refused with the figures, not with silence.
    ok, why = entry.satisfies({"scores": {"MMLU": "> 90"}})
    assert not ok and "84.1" in why and "90" in why, why
    # And a metric nobody published is still refused — honestly, and by name.
    ok, why = entry.satisfies({"scores": {"GPQA": "> 50"}})
    assert not ok and "no published GPQA score" in why, why


def test_the_shipped_catalogue_publishes_no_figures_and_says_so() -> None:
    """The other half, so the test above cannot be read as a claim about this
    distribution. `models/catalog.yaml`'s own header says *"no benchmark figures
    have been imported into this distribution"* — so `needs.scores:` refuses here,
    and that refusal is correct rather than a bug."""
    from pact_adapters.resolve import load_catalogue

    for entry in load_catalogue().entries:
        assert entry.scores == {}, (
            f"{entry.name} publishes {entry.scores}, so the catalogue header's "
            f"claim that none were imported is no longer true"
        )


# ───────── AC-3.2: the predicate the format already had and the adapter did not


def test_the_criterions_own_example_is_expressible_and_holds(tmp_path) -> None:
    """AC-3.2 asks for a predicate evaluating `MMLU > 80 && SWE-Verified > 40`.

    The conjunction is the map — every entry has to hold — and the comparison is
    `> 80`, which the LOADER has parsed all along: `needs.scores` is
    `type: map of threshold` and `coerce.rs` reads `>`, `>=`, `<`, `<=`, `=` and a
    trailing `%`. `satisfies` then did `have <= threshold` with a float on the
    left and the string `"> 80"` on the right, which is a `TypeError` — **the
    format's own documented syntax crashed the resolver**, rather than refusing
    or working.
    """
    from pact_adapters.resolve import load_catalogue

    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "catalog.yaml").write_text(
        """
models:
  measured-locally:
    tier: mid
    cost: { input-per-mtok: 0 USD, output-per-mtok: 0 USD }
    served-by:
      - runtime: ollama
        endpoint: local
    benchmarks:
      MMLU: 84.1
      SWE-Verified: 41.5
      hallucination-rate: 2.3
"""
    )
    entry = {e.name: e for e in load_catalogue(workspace=tmp_path).entries}["measured-locally"]

    ok, why = entry.satisfies({"scores": {"MMLU": "> 80", "SWE-Verified": "> 40"}})
    assert ok, why
    # Conjunction: one entry failing fails the whole predicate, and the refusal
    # names WHICH.
    ok, why = entry.satisfies({"scores": {"MMLU": "> 80", "SWE-Verified": "> 45"}})
    assert not ok and "SWE-Verified" in why and "41.5" in why, why


def test_every_comparison_the_loader_parses_is_one_the_resolver_decides() -> None:
    """The two halves have to agree, or a model is bound on a rule `pact check`
    read differently from the thing that binds it.

    `_HOLDS` mirrors `Op::holds` in `crates/pact-schema/src/coerce.rs`.
    """
    from pact_adapters.resolve import _HOLDS, ModelEntry, _threshold

    entry = ModelEntry(
        name="m", tier="mid", cost=0.0, output_cost=0.0,
        capabilities=frozenset(), scores={"m": 50.0}, context_window=1,
    )
    for written, holds in (
        ("> 40", True), ("> 60", False),
        (">= 50", True), (">= 51", False),
        ("< 60", True), ("< 40", False),
        ("<= 50", True), ("<= 49", False),
        ("= 50", True), ("== 50", True), ("= 51", False),
    ):
        got, why = entry.satisfies({"scores": {"m": written}})
        assert got is holds, f"`m: {written}` against 50 gave {got}: {why}"

    # `%` scales, the way the loader's own parser does.
    assert _threshold("> 80%") == (">", 0.8)
    # A bare number is NOT a comparison, and this line used to say the opposite:
    # `assert _threshold(40) == (">", 40.0)`, under a comment calling it "what
    # every author who wrote one meant". `coerce::threshold` has always refused it
    # — *"a bare number states no comparison"* — so the two ports disagreed, and
    # unreachably, because `pact check` refuses `MMLU: 40` at the author's line
    # first. Both refuse it now; the reasoning and the rows are in
    # `spec/comparisons.yaml` under `not-comparisons:`, and the guess was not
    # obviously right anyway — on a latency or a hallucination rate the assumed
    # `>` is the wrong direction.
    assert _threshold(40) is None
    assert _threshold("40") is None
    assert set(_HOLDS) == {">", ">=", "<", "<=", "="}


def test_a_threshold_nobody_can_read_is_refused_rather_than_crashing() -> None:
    """The failure that shipped was a `TypeError`. A refusal with the line to
    type is the version an author can act on."""
    from pact_adapters.resolve import ModelEntry

    entry = ModelEntry(
        name="m", tier="mid", cost=0.0, output_cost=0.0,
        capabilities=frozenset(), scores={"m": 50.0}, context_window=1,
    )
    ok, why = entry.satisfies({"scores": {"m": "quite high"}})
    assert not ok
    assert "not a threshold this can read" in why, why
    assert "> 80" in why, "it must show the shape to write"


def test_a_variant_holds_its_steps_and_narrows_every_kind_it_can_name() -> None:
    """`variant.steps-at-most:` is a WRITTEN ceiling (a runtime that holds only
    what the author wrote, `steps_written`, must hold it), and `variant.may-use:`
    narrows every kind the schema lets it name — tools, procedures, knowledge and
    the programs the agent's own `uses:` reaches — not only the first two."""
    doc = {
        "agents": {"a": {
            "uses": ["t1", "t2", "manual", "notes", "calc"],
            "variants": {"small": {"steps-at-most": 4, "may-use": ["t1", "notes"]}},
        }},
        "tools": {"t1": {"description": "one"}, "t2": {"description": "two"}},
        "skills": {"manual": {"description": "how"}},
        "knowledge": {"notes": {"description": "notes"}},
        "programs": {"calc": {"description": "adds", "engine": "python", "determinism": "pure"}},
    }
    spec = AgentSpec.from_document(doc, "a")
    small = strategies_of(spec)["small"](spec)
    assert (small.max_steps, small.steps_written) == (4, True)
    assert [t.name for t in small.tools] == ["t1"]
    assert small.skills == ()
    assert [k.name for k in small.knowledge] == ["notes"]
    assert [p.name for p in small.programs if "uses" in p.reached_by] == []
