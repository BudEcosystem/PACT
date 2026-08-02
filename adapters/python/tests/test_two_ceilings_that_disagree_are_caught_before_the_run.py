"""AC-3.6, resolve time — the money cap and the token ceiling, compared on price.

> SLO predicates (TTFT/TPOT/E2E/cost) are enforced at resolve time against
> catalogue estimates *and* at run time against measurements; violation produces
> a typed, actionable failure.

**The run-time half was already met and the register said otherwise.**
`Limits.reached` stops a run on `finishes-within` and `cost-per-request-under`
against what that run actually spent, which is enforcement at run time against
measurements. The row reading *"enforced at neither"* was wrong about this
repository's own code — the same register defect this project has now found in
five places, and the reason a register is computed here rather than maintained.

What was missing is **resolve time**, and this is it. `tokens-at-most` and
`cost-per-request-under` are both ceilings on one request; `models/catalog.yaml`
publishes the exchange rate between them. So before a single call is made it is
decidable which of the two can actually stop a run — and an author who wrote both
and has one believes they have two.

**There is deliberately no latency half.** The criterion asks for TTFT/TPOT
against *catalogue estimates*, and a catalogue latency figure is not a property of
a model: the same weights answer in 200 ms on an H100 and 8 s on a laptop.
Publishing one would be the substitution the catalogue refuses for price, and
would hand out resolve-time verdicts wrong on most machines. `first-reply-within`
and `per-word-under` come back on `RunResult.unmetered` instead, which is the
declared-not-dropped door every other unmeasurable promise leaves by.

Every test here goes through `score()` — the shipped command — and passes nothing
but a path. A check reached only by constructing its own arguments is the defect
this suite exists to catch.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from pact_adapters.scoring import score  # noqa: E402
from pact_adapters.slo import Slo, against_the_catalogue  # noqa: E402

#: A model row this test owns, so the assertions do not move when the real
#: catalogue is repriced. `1.00`/`10.00` per million make the arithmetic
#: legible: 100k tokens is 0.10 all-input and 1.00 all-output.
#:
#: `served-by: ollama, local` is not decoration. Without it the loader refuses
#: the workspace — *"is only served off this machine, and this workspace says
#: `allow-egress: []`"* — which is D17 doing its job, and a test fixture that
#: had to open the box to run would be testing something PACT does not permit.
CATALOGUE = """\
version: 1
default: test-model
models:
  test-model:
    description: A model this test owns.
    family: test
    tier: small
    served-by:
      - { runtime: ollama, endpoint: local }
    capabilities:
      tool-calling: parallel
      modality-in: [text]
      modality-out: [text]
      context-window:
        value: 200000
        provenance:
          source: invented for this test, which is why it lives in a test workspace and never in the shipped catalogue
    cost:
      input-per-mtok: 1.00 USD
      output-per-mtok: 10.00 USD
"""

#: `when-it-runs-out:` is required beside any ceiling, and the loader says why:
#: stopping silently, asking a person, and answering as if finished are three
#: different things, so it is never implied.
RUNS_OUT = "  when-it-runs-out: stop-and-say-so\n"


def _workspace(tmp_path: Path, limits: str) -> Path:
    root = tmp_path / "ws"
    (root / "agents" / "desk").mkdir(parents=True)
    (root / "models").mkdir(parents=True)
    (root / "models" / "catalog.yaml").write_text(CATALOGUE)
    (root / "workspace.yaml").write_text("name: ceilings\n")
    # One case, because `score` returns before binding a model when a workspace
    # has none — `if not cases: return scored`. That early return is right for
    # the eval command and is exactly why the same check also runs in
    # `pipeline`'s resolve stage, which needs no suite. See
    # `test_the_resolve_stage_reports_it_without_any_eval_suite`.
    (root / "evals").mkdir()
    (root / "evals" / "suite.yaml").write_text(
        "population: authored-enumeration\n"
        "cases:\n  greets:\n    when: Say hello.\n    expect:\n      greeting: hello\n"
    )
    (root / "agents" / "desk" / "agent.yaml").write_text(
        "name: Desk\n"
        "description: Answers questions.\n"
        "instructions: Answer the question.\n"
        "model: test-model\n"
        "answers-with:\n  greeting: text\n"
        + limits
    )
    return root


def _caveats(root: Path) -> str:
    """Everything the report said about how this run differed from a real one."""
    scored = score(root, serving_at="http://127.0.0.1:9/v1")
    assert scored.problem is None, scored.problem
    return "\n".join(scored.caveats)


def test_a_money_cap_that_makes_the_token_ceiling_unreachable_is_reported(
    tmp_path: Path,
) -> None:
    """100k tokens costs 0.10 at the very cheapest here, and the cap is 0.01.

    So no run can reach its token allowance: the money cap stops it first, every
    time, and `tokens-at-most` governs nothing. That is decidable from a price
    list and two numbers in a file, and today an author discovers it by watching
    runs die one at a time.
    """
    root = _workspace(
        tmp_path,
        "limits:\n  tokens-at-most: 100000\n  cost-per-request-under: 0.01 USD\n"
        + RUNS_OUT,
    )
    said = _caveats(root)
    assert "tokens-at-most: 100000` cannot be reached" in said, said
    # The numbers, so the author can check the claim against their own file
    # rather than take it on trust.
    assert "0.1000" in said and "1.0000" in said, said
    assert "test-model" in said, said
    # AND THE CURRENCY. Mutating this word out of the sentence left the whole
    # suite green, which is how the bug below was found: `resolve._cost` read
    # `raw.split()[0]` and threw `USD` away, so every price this package produced
    # was a bare float that everything downstream read as dollars.
    assert "USD" in said, said
    # And what to do, which is the difference between a diagnostic and a
    # complaint.
    assert "fix:" in said, said


def test_a_money_cap_nothing_can_reach_is_reported_too(tmp_path: Path) -> None:
    """The other direction, and the one an author is likelier to write.

    1000 tokens costs at most 0.01, and the cap is 5.00. The run always stops on
    tokens; the money cap is decoration. A ceiling nothing can reach reads like a
    control and is not one — which is the same complaint `slo.py` makes about a
    `feel:` nothing acted on.
    """
    root = _workspace(
        tmp_path,
        "limits:\n  tokens-at-most: 1000\n  cost-per-request-under: 5.00 USD\n"
        + RUNS_OUT,
    )
    said = _caveats(root)
    assert "cost-per-request-under: 5.0 USD` cannot be reached" in said, said
    assert "never binds" in said, said


def test_two_ceilings_that_can_both_bite_are_not_reported(tmp_path: Path) -> None:
    """The negative half, without which the two above are satisfied by a module
    that reports on every workspace it sees.

    100k tokens costs 0.10 to 1.00 depending on the split, and the cap is 0.50 —
    inside that range. Which ceiling stops a given run depends on how that run
    spent its budget, both are live, and there is nothing to say.
    """
    root = _workspace(
        tmp_path,
        "limits:\n  tokens-at-most: 100000\n  cost-per-request-under: 0.50 USD\n"
        + RUNS_OUT,
    )
    said = _caveats(root)
    assert "cannot be reached" not in said, said


def test_an_author_who_wrote_one_ceiling_is_told_nothing(tmp_path: Path) -> None:
    """No comparison exists between a ceiling and a ceiling that is not there.

    A report that volunteered "you have no cost cap" for every workspace without
    one would be noise, and noise is what makes a report stop being read.
    """
    root = _workspace(tmp_path, "limits:\n  tokens-at-most: 100000\n" + RUNS_OUT)
    assert "cannot be reached" not in _caveats(root)


def test_an_unpriced_model_produces_no_finding_rather_than_one_computed_from_zero(
    tmp_path: Path,
) -> None:
    """The whole of `models/catalog.yaml`'s argument about unsourced prices.

    A row nobody priced makes every request cost 0.00, which would make every
    money cap unreachable and this check would announce that on every agent using
    it. `price_of` returns `None`, and `None` is not zero.
    """
    root = tmp_path / "unpriced"
    (root / "agents" / "desk").mkdir(parents=True)
    (root / "models").mkdir(parents=True)
    (root / "models" / "catalog.yaml").write_text(
        CATALOGUE.replace("test-model", "no-price").split("    cost:")[0]
    )
    (root / "workspace.yaml").write_text("name: unpriced\n")
    (root / "evals").mkdir()
    (root / "evals" / "suite.yaml").write_text(
        "population: authored-enumeration\n"
        "cases:\n  greets:\n    when: Say hello.\n    expect:\n      greeting: hello\n"
    )
    (root / "agents" / "desk" / "agent.yaml").write_text(
        "name: Desk\ndescription: Answers.\ninstructions: Answer.\n"
        "model: no-price\n"
        "answers-with:\n  greeting: text\n"
        "limits:\n  tokens-at-most: 100000\n  cost-per-request-under: 0.01 USD\n"
        + RUNS_OUT
    )
    assert "cannot be reached" not in _caveats(root)


def test_nothing_here_stops_a_run() -> None:
    """The property `slo.py` spent a deletion establishing.

    `Limits.reached` is the one enforcer of these two ceilings. This is a
    resolve-time REPORT, and if it ever gained the power to refuse, one ceiling
    would again mean two things — which is the reason the old `Budget` and its
    `SloBreach` were deleted rather than wired.
    """
    import inspect

    from pact_adapters import slo

    source = inspect.getsource(slo.against_the_catalogue)
    assert "raise" not in source, (
        "`against_the_catalogue` raises. It reports; `Limits` stops runs."
    )
    # And the caller treats it as a caveat — the channel for "this is how the run
    # differed", not for "this run is refused".
    scoring = inspect.getsource(
        __import__("pact_adapters.scoring", fromlist=["x"])
    )
    where = scoring[scoring.index("disagree = against_the_catalogue") :][:600]
    assert "scored.caveats" in where, where
    assert "scored.problem" not in where, where


@pytest.mark.parametrize(
    "cap,tokens,expect",
    [
        (0.01, 100_000, "cost"),   # money bites first
        (5.00, 1_000, "tokens"),   # tokens bite first
        (0.50, 100_000, None),     # both live
        (None, 100_000, None),     # no cap written
        (0.50, None, None),        # no token ceiling written
        (0.50, 0, None),           # a zero ceiling is not a ceiling
    ],
)
def test_the_boundary_between_reporting_and_silence(
    cap: "float | None", tokens: "int | None", expect: "str | None"
) -> None:
    """The library half, over the cases a workspace cannot easily express.

    Kept because the four workspace tests above cannot reach `tokens-at-most: 0`
    or an absent cap in the same run, and the boundary between "say something"
    and "say nothing" is where a check like this goes wrong.
    """
    price = lambda went_in, came_out: (went_in * 1.0 + came_out * 10.0) / 1_000_000
    found = against_the_catalogue(
        Slo(cost_per_request_under=cap, cost_currency="USD"), tokens, "m", price
    )
    assert (found.bites if found is not None else None) == expect


def test_the_resolve_stage_reports_it_without_any_eval_suite(tmp_path: Path) -> None:
    """The door that makes this a RESOLVE-time check rather than an eval-time one.

    `score` returns before binding a model when a workspace has no cases — `if
    not cases: return scored` — which is right for the eval command and wrong as
    the only way to reach this. An author fixing a document has usually not
    written their cases yet, and a resolve-time check reachable only through the
    eval command runs after the thing it was supposed to precede.

    So the same comparison runs in `pipeline`'s stage literally named `resolve`,
    and this workspace has **no `evals/` at all**.
    """
    root = _workspace(
        tmp_path,
        "limits:\n  tokens-at-most: 100000\n  cost-per-request-under: 0.01 USD\n"
        + RUNS_OUT,
    )
    import shutil

    shutil.rmtree(root / "evals")

    from pact_adapters.pipeline import run_pipeline

    ran = run_pipeline(root, serving_at="http://127.0.0.1:9/v1")
    resolve = next(s for s in ran.stages if s.name == "resolve")
    assert resolve.outcome == "ran", resolve.said
    assert "cannot be reached" in resolve.said, resolve.said
    # And it did not turn a report into a refusal: the pipeline still completes.
    assert ran.exit_code == 0, ran.render()


def test_the_loader_refuses_a_cap_nothing_can_price(tmp_path: Path) -> None:
    """The cross-currency case, and where it is actually handled.

    Mutating `USD` out of the finding's sentence left this whole suite green,
    which exposed that `resolve._cost` reads `raw.split()[0]` and **discards the
    currency word** — so `price_of` returns a bare float everything downstream
    reads as dollars, and a cap in JPY would be compared against a price in USD
    as a plain number.

    A third branch was written for it. Then the loader turned out to refuse the
    case already, in better words than mine, before a document ever reaches
    Python — so the branch was deleted instead of kept. A second enforcer of a
    rule already enforced is how one ceiling comes to mean two things, which is
    `slo.py`'s own argument for having deleted `Budget`.

    This test is what makes that deletion safe: if the loader ever stops
    refusing, `against_the_catalogue` silently starts comparing money to
    different money, and this fails.
    """
    import subprocess

    root = _workspace(
        tmp_path,
        "limits:\n  tokens-at-most: 100000\n  cost-per-request-under: 1000 JPY\n"
        + RUNS_OUT,
    )
    binary = Path(__file__).resolve().parents[3] / "target" / "debug" / "pact"
    if not binary.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    said = subprocess.run(
        [str(binary), "check", str(root)], capture_output=True, text=True
    )
    assert said.returncode != 0, said.stdout
    everything = said.stdout + said.stderr
    assert "currency-nothing-can-price" in everything, everything
    # And it says the thing that matters, rather than merely refusing.
    assert "1000 JPY is not 1000 USD" in everything, everything


def test_a_cap_with_no_currency_at_all_is_refused_too(tmp_path: Path) -> None:
    """The other half of the invariant, and the one that closes it.

    `currency-nothing-can-price` stops a cap in money the price list does not
    deal in. This stops a cap in no money at all: `cost-per-request-under: 0.01`
    is refused as *"should be an amount of money, like `0.05 USD`, but it is a
    number"*.

    Together the two make `against_the_catalogue`'s arithmetic same-currency **by
    construction**: every cap that reaches it names a currency, and that currency
    is the one the catalogue prices in. Neither rule alone is enough — the first
    leaves a bare number through, the second leaves JPY through — which is why
    both are pinned here rather than one being taken as covering the case.
    """
    import subprocess

    root = _workspace(
        tmp_path,
        "limits:\n  tokens-at-most: 100000\n  cost-per-request-under: 0.01\n"
        + RUNS_OUT,
    )
    binary = Path(__file__).resolve().parents[3] / "target" / "debug" / "pact"
    if not binary.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    said = subprocess.run(
        [str(binary), "check", str(root)], capture_output=True, text=True
    )
    assert said.returncode != 0, said.stdout
    assert "should be an amount of money" in said.stdout + said.stderr, said.stdout
