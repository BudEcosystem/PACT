"""A spend cap that only one vendor could ever reach was not a spend cap.

`models/catalog.yaml` has carried a `cost:` block on every row since it landed,
and `resolve.price_of` has been the one place a price is looked up since the
round after that. What neither of them could fix is what was IN the file: the
three Anthropic rows were the only ones publishing both halves of a price, so
`price_of` answered a figure for `anthropic-api` and `None` for every other
hosted row. An author who pinned anything else got `cost-per-request-under` and
`tokens-at-most` straight back onto `RunResult.unmetered` — the honest-and-inert
state the catalogue exists to end, surviving one vendor at a time. Two of the
seven shipped transports, the OpenAI-compatible one and the OpenAI Agents one,
had no priced row to bind at all.

So the mechanism was finished and the DATA was not, and the difference is only
visible from a run. Every test here therefore ends at a refusal — a run that
stopped, on the step that broke the author's own ceiling, on a model no
Anthropic key can reach — rather than at a figure read back out of the file it
was written into. The one test that does read the file back says so in its own
docstring, because "the row exists" and "the row refuses something" are
different claims and only the second one was missing.

Nothing here constructs a `Limits`, a price or a window. The cap is
`examples/refund-desk/agents/refund-desk/limits.yaml`'s `cost-per-request-under:
0.05 USD`, the action taken when it is reached is that file's
`when-it-runs-out: ask-a-person`, and the price the run is measured against is
the catalogue row the author's `model:` line names. The two lines these tests do
edit are edited on the loaded DOCUMENT and named where they are edited — the
same one-line-changed pattern `test_termination.py` and `test_model_portability.py`
already use, for the same reason: the worked example ships air-gapped
(`allow-egress: []`), and an air-gapped workspace binding a hosted model is a
configuration PACT is supposed to refuse.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.resolve import load_catalogue, price_of, window_of  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.autogen_transport import AutoGenTransport  # noqa: E402
from pact_adapters.transports.openai_agents_transport import (  # noqa: E402
    OpenAIAgentsTransport,
)

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"

#: The vendor that could already be metered, named once so the tests below read
#: as claims about "somebody other than this one" rather than as a list.
ALREADY_METERED = "anthropic-api"

#: A hosted row on a vendor no Anthropic key reaches, priced at 0.75 USD per
#: million tokens in and 4.50 out, holding 400,000. It is what the OpenAI Agents
#: transport binds below.
OPENAI_ROW = "gpt-5.4-mini"

#: A second hosted vendor, so "more than one" is a claim about a run and not
#: only about a file. 2.00 USD in, 6.00 out, holding 500,000.
XAI_ROW = "grok-4.5"

#: The row this distribution still publishes as unpriced, on purpose and with a
#: reason written above it: its published price is tiered and `cost:` holds one
#: figure per direction. It is the control arm — same vendor, same transport,
#: same script as `OPENAI_ROW` — so the difference between the two runs is the
#: price and nothing else.
UNPRICED_ROW = "gpt-5.4"

#: An id no catalogue row claims, for the other control: with nothing to look
#: up, both ceilings and the tidying budget go out as unmeasurable.
NOT_IN_THE_CATALOGUE = "a-model-nobody-has-written-down"

TOOLS = {"zendesk": lambda a: "lamp, broken", "payments": lambda a: "refunded"}

#: What an agent says when it will not stop talking. The repeat count is the
#: point: at 4.50 USD per million output tokens — the cheapest OUTPUT price of
#: any hosted row added here — one call of this size bills more than the
#: author's 0.05 USD cap, so the cap has to fire on the first call or not at
#: all. Derived rather than tuned: 0.05 USD / 4.50 USD per Mtok is 11,111
#: tokens, and `_metering.tokens_in` counts four characters to the token.
_SAYS_TOO_MUCH = "the customer wrote back again about the lamp and asked for an update. "
TALKS_PAST_THE_CAP = _SAYS_TOO_MUCH * 800


@pytest.fixture(scope="session")
def document() -> dict:
    """The worked example, loaded by the shipped loader from its own files."""
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run([str(PACT_BIN), "show", str(EXAMPLE)],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def pinned_to(document: dict, model: str) -> AgentSpec:
    """The worked example with the author's `model:` line set, and nothing else.

    Two lines are edited and both are lines an author writes. `model:` is the
    one under test. `allow-egress: [llm]` goes with it because the shipped
    example says `allow-egress: []` — nothing in it may talk outside the box —
    and every row added to the catalogue this round is hosted. Leaving that line
    alone would make the fixture a workspace `pact check` refuses (the CLI's
    `loader/leaves-the-box` rule), which is a different test than this one.
    """
    connected = {
        **document,
        "allow-egress": ["llm"],
        "agents": {
            **document["agents"],
            "refund-desk": {**document["agents"]["refund-desk"], "model": model},
        },
    }
    spec = AgentSpec.from_document(connected, "refund-desk", EXAMPLE)
    assert spec.model == model, "the pin has to reach the spec before it can bind"
    return spec


def hosted_vendors_that_can_be_metered() -> dict[str, list[str]]:
    """Which hosted runtimes have at least one row carrying a price AND a window.

    Both halves of the price, because `Catalogue.price_of` refuses to answer
    without both — an input figure alone would be the input bill wearing the
    whole bill's name. And the window beside it, because the two ceilings this
    round is about are metered off the same row that the context ladder is
    measured against, and a vendor with a price and no window can bound what a
    run spends while still reporting its tidying as unenforced.
    """
    catalogue = load_catalogue()
    by_runtime: dict[str, list[str]] = {}
    for entry in catalogue.entries:
        if entry.served_locally:
            continue  # a machine's own weights cost nothing; that is a sourced 0
        if entry.cost is None or entry.output_cost is None:
            continue
        if entry.context_window is None:
            continue
        for runtime in sorted(entry.runtimes):
            by_runtime.setdefault(runtime, []).append(entry.name)
    return by_runtime


def test_the_money_ceilings_can_be_enforced_against_more_than_one_vendor() -> None:
    """The file itself, held to the claim the rest of this module then runs.

    This is the weakest test here and it is deliberately first: it reads the
    catalogue back and asserts what is in it, which proves a row exists and says
    nothing about whether anything reads the row. The tests below are the ones
    that matter. This one exists so that the day somebody removes the last
    non-Anthropic priced row, the failure names the file rather than arriving as
    four confusing run-time assertions about spend.
    """
    vendors = hosted_vendors_that_can_be_metered()
    assert ALREADY_METERED in vendors, (
        "the vendor that could always be metered has stopped being metered"
    )
    others = {r: rows for r, rows in vendors.items() if r != ALREADY_METERED}
    assert len(others) >= 2, (
        "a price list with one vendor on it is a vendor feature, not a ceiling: "
        f"hosted runtimes carrying both a price and a window are {sorted(vendors)}"
    )

    # And every one of them can actually be priced and sized through the two
    # functions a transport calls, rather than merely looking right in YAML.
    for runtime, rows in sorted(vendors.items()):
        for name in rows:
            assert price_of(name, 1_000_000, 1_000_000) is not None, (runtime, name)
            assert window_of(name), (runtime, name)


def test_a_spend_cap_stops_a_run_bound_to_a_vendor_no_anthropic_key_can_reach(
    document: dict,
) -> None:
    """The refusal, on the transport that had no priced row to bind at all.

    Everything the stop is measured against is authored: the 0.05 USD cap and
    `when-it-runs-out: ask-a-person` come from
    `agents/refund-desk/limits.yaml`, the model comes from the agent's own
    `model:` line, and the price comes from that model's catalogue row. The only
    things this test supplies are the transport and the tools.

    `script.calls == 1` is the half that makes it a ceiling rather than a report:
    the call that broke the cap is the last one made, so nothing was paid for
    after the author's figure was crossed.
    """
    spec = pinned_to(document, OPENAI_ROW)
    script = Script([Turn(TALKS_PAST_THE_CAP)])
    transport = OpenAIAgentsTransport(script, model=spec.model or None)
    assert transport.model == OPENAI_ROW, "the pin is what the transport bound"
    assert transport.prices_money is True, "the catalogue prices this row"

    r = asyncio.run(run(spec, transport, "my lamp arrived broken, please refund", TOOLS))

    assert "cost-per-request-under" not in r.unmetered, r.unmetered
    assert r.stopped_by is not None, "the cap did not fire"
    assert r.stopped_by.ceiling.field == "cost-per-request-under"
    assert r.stopped_by.ceiling.limit == 0.05, "the author's own figure"
    assert r.halted == "suspended", "`when-it-runs-out: ask-a-person` hands it over"
    assert r.spent >= 0.05, f"it stopped before it reached the cap: {r.spent}"
    assert script.calls == 1, f"calls made after the cap broke: {script.calls - 1}"


def test_the_same_run_on_the_row_nobody_can_price_refuses_nothing(
    document: dict,
) -> None:
    """The control, and the reason the test above is about DATA and not code.

    Same document, same transport, same script, same 0.05 USD cap — one line
    different, and it is the model. `gpt-5.4` is the row this distribution still
    publishes as `cost: unknown`, because its published price is tiered at
    272,000 tokens and `cost:` holds one figure per direction; writing the base
    rate would under-bill every long request by half.

    So the run walks straight past the author's cap and says so. That is exactly
    the state EVERY hosted row outside Anthropic was in before this round, which
    is what makes it the right control: the mechanism was never broken, the price
    list was empty.
    """
    spec = pinned_to(document, UNPRICED_ROW)
    script = Script([Turn(TALKS_PAST_THE_CAP)])
    transport = OpenAIAgentsTransport(script, model=spec.model or None)
    assert transport.prices_money is False

    r = asyncio.run(run(spec, transport, "my lamp arrived broken, please refund", TOOLS))

    assert "cost-per-request-under" in r.unmetered, r.unmetered
    assert r.spent == 0.0, "no price, so nothing was billed — and it says so"
    assert r.stopped_by is None, "nothing could stop it: there was no figure"
    assert r.halted == "final", (r.halted, r.spent)
    # The tokens were countable the whole time on both arms. Only the money
    # half of the meter depends on the row carrying a price.
    assert r.used is not None and r.used.tokens > 0, r.used


def test_a_second_vendor_stops_at_the_same_ceiling_on_a_different_framework(
    document: dict,
) -> None:
    """"More than one vendor" as a claim about a run, not about a file.

    A price list that meters one vendor is that vendor's feature. The same
    authored cap, the same authored action, a row on a third vendor — xAI — and
    a different one of the seven adapters underneath it, because a ceiling
    honoured by one framework and not another is a property of whichever adapter
    happened to run (D12).
    """
    spec = pinned_to(document, XAI_ROW)
    script = Script([Turn(TALKS_PAST_THE_CAP)])
    transport = AutoGenTransport(script, model=spec.model or None)
    assert transport.model == XAI_ROW
    assert transport.prices_money is True

    r = asyncio.run(run(spec, transport, "my lamp arrived broken, please refund", TOOLS))

    assert "cost-per-request-under" not in r.unmetered, r.unmetered
    assert r.stopped_by is not None and r.stopped_by.ceiling.field == "cost-per-request-under"
    assert r.stopped_by.ceiling.limit == 0.05
    assert r.halted == "suspended"
    assert r.spent >= 0.05, r.spent
    assert script.calls == 1, f"calls made after the cap broke: {script.calls - 1}"


def test_a_hosted_row_outside_anthropic_can_now_say_what_it_holds(
    document: dict,
) -> None:
    """The other half of the same row: the tidying budget, not the bill.

    `gpt-5.4` published `context-window: unknown` alongside its unknown price,
    so it contributed to neither ceiling nor ladder — an agent bound to it was
    told its `context-policy:` could not be measured. The window was sourceable
    all along; the price still is not. One row, two figures, two different
    answers, which is the whole reason provenance is per figure.

    Held through a run rather than through `window_of`, because a figure the
    checker can read and the harness never asks for is the same defect one hop
    along. The control is the same run pinned to an id nothing has a row for.
    """
    spec = pinned_to(document, UNPRICED_ROW)
    transport = OpenAIAgentsTransport(Script([Turn("Approved.")]), model=spec.model)
    assert transport.context_window() == 1_050_000, (
        "the window comes off the row, through the transport the run uses"
    )

    r = asyncio.run(run(spec, transport, "my lamp arrived broken, please refund", TOOLS))
    assert "context-policy" not in r.unmetered, r.unmetered
    # Nothing was thrown away: this conversation fits a million tokens twice
    # over. "Measured" and "tidied" are different claims and only the first one
    # is being made here.
    assert r.tidyings == []

    nowhere = pinned_to(document, NOT_IN_THE_CATALOGUE)
    blind = OpenAIAgentsTransport(Script([Turn("Approved.")]), model=nowhere.model)
    assert blind.context_window() is None
    out = asyncio.run(
        run(nowhere, blind, "my lamp arrived broken, please refund", TOOLS)
    )
    assert "context-policy" in out.unmetered, out.unmetered
