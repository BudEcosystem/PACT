"""A spend cap reports the currency it was written in — not the one this code
happened to like.

`Ty::Money` keeps its currency on the Rust side, and `docs/30-FRD.md` FR-1.4.5
states the rule normatively: *"Money MUST retain its currency; currencies MUST
NOT be converted or defaulted."* Then `limits.money()` returned the first
parseable float and dropped every other token on the line, and `Ceiling`'s unit
for a money row was the literal string `"USD"` whatever the file said. So
`cost-per-request-under: 500 JPY` in the worked example loaded cleanly, ran
against a meter priced in USD, and told its author *"(501 of 500 USD)"* — a
currency they had never typed, after a comparison that had already treated 500
JPY and 500 USD as the same money.

Two halves fix that and both are exercised here, in that order:

1. **`pact check` refuses a currency the workspace's price list cannot charge
   in** (`loader/currency-nothing-can-price`), which is what makes the
   comparison sound. Nothing here converts anything.
2. **The run names the currency the author wrote**, which is what makes the
   sentence true.

They have to agree, so the fixture below is a tree `pact check` ACCEPTS: it deals
in JPY, and it says so the way a workspace says so — a row in its own
`models/catalog.yaml`, which is data an author edits and not code (D14). If the
loader ever refused a currency the harness can meter, or vice versa, the first
test in this file fails before any of the run assertions are reached.

Nothing here constructs a `Limits` or a `Ceiling`. Every figure comes off disk:
the cap and its currency from `agents/refund-desk/limits.yaml`, the action taken
at it from that file's `when-it-runs-out: ask-a-person`, the price it is metered
against from the workspace's own catalogue row, and the model from the agent's
own `model:` line. The only things supplied are the transport and the tools.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.limits import Action  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.anthropic_transport import AnthropicTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"

TOOLS = {"zendesk": lambda a: "lamp, broken", "payments": lambda a: "refunded"}

#: The line in the shipped example this whole file is about.
WRITTEN_IN_USD = "cost-per-request-under: 0.05 USD"

#: The same setting in the currency the fixture deals in. Small enough that the
#: first call breaks it: the row below charges 40 JPY per million output tokens,
#: and `_metering.tokens_in` counts four characters to the token, so 50,000
#: characters of answer is about 12,500 tokens and about 0.5 JPY. A cap a run
#: cannot reach would prove the currency is carried and not that it BINDS.
WRITTEN_IN_YEN = "cost-per-request-under: 0.4 JPY"

#: A model this machine serves, priced in the currency this workspace deals in.
#: Locally served because the shipped example says `allow-egress: []` — nothing
#: in it may talk outside the box — and a hosted row would make the fixture a
#: workspace `pact check` refuses for a different reason than the one under test.
A_ROW_PRICED_IN_YEN = """models:
  local-jp:
    family: local-jp
    served-by:
      - { runtime: ollama, endpoint: local }
    cost: { input-per-mtok: 12 JPY, output-per-mtok: 40 JPY }
"""

#: What an agent says when it will not stop talking, sized against the row above.
TALKS_PAST_THE_CAP = "the customer wrote back about the lamp again. " * 1200


def _show(root: Path) -> dict:
    out = subprocess.run(
        [str(PACT_BIN), "show", str(root)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


def _dealing_in_yen(into: Path, *edits: tuple[str, str, str]) -> Path:
    """The worked example, dealing in JPY, with its lines changed on DISK.

    On disk and not on the loaded document, because the claim being tested is
    that the AUTHOR's line reaches the sentence a person reads. A document edited
    in Python proves the object works and says nothing about whether the file
    does.

    `edits` are further (file, from, to) triples, so a test that needs one more
    authored line — a different `when-it-runs-out:`, one more name under
    `shows:` — writes it in the tree rather than in Python.
    """
    root = into / "refund-desk"
    shutil.copytree(EXAMPLE, root)

    limits = root / "agents" / "refund-desk" / "limits.yaml"
    text = limits.read_text()
    assert WRITTEN_IN_USD in text, "the shipped example has moved; this fixture is stale"
    limits.write_text(text.replace(WRITTEN_IN_USD, WRITTEN_IN_YEN))

    agent = root / "agents" / "refund-desk" / "agent.yaml"
    agent.write_text(agent.read_text().rstrip() + "\nmodel: local-jp\n")

    (root / "models").mkdir(exist_ok=True)
    (root / "models" / "catalog.yaml").write_text(A_ROW_PRICED_IN_YEN)

    for name, was, now in edits:
        f = root / name
        before = f.read_text()
        assert was in before, f"fixture drifted: {was!r} not in {name}"
        f.write_text(before.replace(was, now))
    return root


@pytest.fixture(scope="module")
def in_yen(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    return _dealing_in_yen(tmp_path_factory.mktemp("yen"))


def _parked_on_the_cap(root: Path):
    """One run of the tree at `root`, stopped by its own spend cap."""
    spec = AgentSpec.from_document(_show(root), "refund-desk", root)
    assert spec.model == "local-jp", "the pin has to reach the spec before it can bind"
    transport = AnthropicTransport(Script([Turn(TALKS_PAST_THE_CAP)]),
                                   model=spec.model, workspace=str(root))
    assert transport.prices_money is True, "the workspace's own row has to be priced"
    return asyncio.run(run(spec, transport, "my lamp arrived broken, please refund", TOOLS))


def test_a_workspace_that_prices_a_model_in_yen_is_allowed_to_write_yen(in_yen: Path) -> None:
    """The two halves have to agree about which currencies are writable.

    If `pact check` refused this tree there would be no legal way to write a
    ceiling in JPY at all, and every assertion below would be about a workspace
    nobody can ship. If it accepted a currency the harness cannot meter, the
    refusal would be in the wrong place. So this runs first, and it runs the
    command D13's reader actually runs.
    """
    out = subprocess.run(
        [str(PACT_BIN), "check", str(in_yen)], capture_output=True, text=True
    )
    assert out.returncode == 0, out.stdout + out.stderr


def test_the_shipped_example_still_reports_the_currency_its_own_file_writes(
) -> None:
    """`cost-per-request-under: 0.05 USD`, read off disk, reported as USD.

    USD was also the hardcoded answer, so on its own this test proves nothing —
    it is here as the control for the one below, which changes that single line
    and nothing else. Together they are the claim: the currency comes from the
    file.
    """
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    spec = AgentSpec.from_document(_show(EXAMPLE), "refund-desk", EXAMPLE)
    assert spec.limits.cost_currency == "USD"
    row = next(c for c in spec.limits.ceilings() if c.reads == "money")
    assert row.unit == "USD"


def test_the_currency_reported_is_the_one_the_author_wrote_and_not_a_default(
    in_yen: Path,
) -> None:
    """One line different from the test above, and the report follows it.

    Read off the ceiling the loaded document produced, with nothing passed: the
    file says JPY, so the row says JPY. Before this, `Ceiling`'s unit for a money
    row was the literal `"USD"` and this assertion was unreachable — there was no
    tree, anywhere, that could make it say anything else.
    """
    spec = AgentSpec.from_document(_show(in_yen), "refund-desk", in_yen)
    assert spec.limits.cost_currency == "JPY"
    row = next(c for c in spec.limits.ceilings() if c.reads == "money")
    assert row.unit == "JPY", "the unit is the author's currency, not this code's favourite"
    assert row.limit == 0.4, "and the amount is still the amount"


def test_the_cap_in_yen_stops_a_run_and_the_sentence_names_yen(in_yen: Path) -> None:
    """The half that matters: the currency has to REFUSE something.

    A field that reaches an object and constrains nothing is the defect this
    project keeps shipping, so the assertion is on a run that stopped. The cap
    is the author's, the action at it (`ask-a-person`) is the author's, the price
    it is measured against is the author's own catalogue row — and the sentence
    that comes back names the currency they wrote in.
    """
    r = _parked_on_the_cap(in_yen)

    assert "cost-per-request-under" not in r.unmetered, r.unmetered
    assert r.stopped_by is not None, "the cap did not fire"
    assert r.stopped_by.ceiling.field == "cost-per-request-under"
    assert r.stopped_by.ceiling.limit == 0.4, "the author's own figure"
    assert r.stopped_by.ceiling.unit == "JPY"
    assert r.stopped_by.action is Action.ASK, "`when-it-runs-out:` is the author's too"
    assert "0.4 JPY" in r.stopped_by.what, r.stopped_by.what
    assert "USD" not in r.stopped_by.what, (
        "a currency nobody wrote, in the sentence that reports their own ceiling: "
        + r.stopped_by.what
    )
    assert "JPY" in r.stopped_by.sentence()


def test_the_person_asked_whether_to_keep_going_is_shown_the_currency_too(
    tmp_path: Path,
) -> None:
    """The last hop, and the one that made this worth fixing.

    `which-limit` is one of the names an author may write under a question's
    `shows:` (`spec/schema.yaml` lists it beside `spent-so-far` and
    `steps-taken`), and it renders this ceiling's own sentence. So the currency
    does not stop at a field on a result object in a test — it reaches the screen
    of the person being asked whether to spend more, which is the only place in
    this system where a human decides about money.

    The line is added to the fixture's own `questions/keep-going.yaml` rather
    than to the shipped one: what is under test is that an author who writes it
    is told the truth, not which values the worked example happens to ask for.

    NOT asserted here, and a separate defect: `spent-so-far` beside it still
    renders `f"{...:.2f} USD"` unconditionally (`shown.spent`), because the
    figure it prints is the BILL — priced by `models/catalog.yaml` — and
    `resolve.price_of` drops the currency off a `cost:` row the same way
    `limits.money()` used to drop it off a ceiling. Fixing that is a chain
    through `resolve` and the meter, not a line here.
    """
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    root = _dealing_in_yen(
        tmp_path,
        ("questions/keep-going.yaml", "  - steps-taken", "  - steps-taken\n  - which-limit"),
    )
    r = _parked_on_the_cap(root)

    assert r.halted == "suspended", "`when-it-runs-out: ask-a-person` hands it over"
    assert r.suspension is not None
    shown = r.suspension.in_words
    assert "which-limit" in shown, "the author's `shows:` line reached the screen:\n" + shown
    assert "0.4 JPY" in shown, "and it named the currency they wrote:\n" + shown


def test_a_run_stopped_by_the_cap_says_which_currency_in_its_own_answer(
    tmp_path: Path,
) -> None:
    """The route that needs no question at all.

    With `when-it-runs-out: stop-and-say-so` the run's OUTPUT is the ceiling's
    sentence (`harness.py`: `result.output = reached.sentence()`), so this is
    what every caller of `run()` reads back — a person, a report, another agent.
    It is the widest audience the currency has, and it was telling all of them
    USD.
    """
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    root = _dealing_in_yen(
        tmp_path,
        (
            "agents/refund-desk/limits.yaml",
            "when-it-runs-out: ask-a-person",
            "when-it-runs-out: stop-and-say-so",
        ),
    )
    r = _parked_on_the_cap(root)

    assert r.halted == "cost-limit", r.halted
    assert "0.4 JPY" in r.output, r.output
    assert "USD" not in r.output, (
        "a currency nobody wrote, in the answer the run hands back: " + r.output
    )
