"""The author's `model:` line, from the file to the bound window.

`spec/schema.yaml` has offered `model:` since before the model catalogue was
real, and the loader has always emitted it — `pact discover examples` prints
`"model": null` for every agent that leaves it out. What did not exist was the
last hop: `AgentSpec.from_document` never read the key, so the pin stopped at
the adapter boundary and no host could pass it on even if it wanted to.

That only became a *consequence* once windows became real (G3). A context policy
is measured against what the bound model can hold, and `models/catalog.yaml`
publishes a different window per model — 32,768 for the default, 131,072 for
`llama3.2-1b-instruct`. So an author who pinned a model and got the catalogue
default was having their policy measured against the wrong number, silently,
which is the T7 breach `RunResult.unmetered` exists to prevent everywhere else.

For one round the field was carried and read by nothing but its own test, which
is the same defect one hop further along: `harness.run` built the tidier from
`_window(transport)` and never looked at `spec.model`. These are the three ends
of that seam — the pin reaching the spec, the pin reaching the budget, and the
pin being contradicted by what actually ran.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.events import Bus  # noqa: E402
from pact_adapters.harness import ToolCall, delegate_by_running, run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.limits import Limits  # noqa: E402
from pact_adapters.resolve import default_model, window_of  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402
from pact_adapters.transports.pydantic_ai_transport import (  # noqa: E402
    PydanticAITransport,
)

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"

#: A model in the catalogue whose window is deliberately NOT the default's, so
#: "the pin was carried" and "the pin changed what the run is measured against"
#: are one assertion rather than two hopeful ones.
PINNED = "llama3.2-1b-instruct"


def a_document(**agent) -> dict:
    return {"agents": {"desk": {"name": "Desk", **agent}}}


@pytest.fixture(scope="session")
def document() -> dict:
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run([str(PACT_BIN), "show", str(EXAMPLE)],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_the_model_the_author_pinned_reaches_the_spec() -> None:
    assert AgentSpec.from_document(a_document(model=PINNED), "desk").model == PINNED


def test_an_agent_that_pinned_nothing_says_so_rather_than_naming_the_default() -> None:
    """"Did not choose" and "chose the default" are different facts.

    Writing the catalogue default in here would collapse them, and the collapse
    is not harmless: it is what makes a later change of default invisible to an
    author who never asked to be pinned to anything. R26 — no default nobody
    asked for.
    """
    assert AgentSpec.from_document(a_document(), "desk").model == ""
    # And `null`, which is what the loader emits for an absent line, reads the
    # same way as absent rather than crashing on `.strip()`.
    assert AgentSpec.from_document(a_document(model=None), "desk").model == ""


def test_the_pin_is_what_a_host_hands_the_transport_and_it_changes_the_window() -> None:
    """The seam a host uses: pass `spec.model or None` to the transport.

    An unpinned agent still falls through to the catalogue's `default:` exactly
    as the schema's help text promises.
    """
    script = Script([Turn(text="done")])

    pinned = AgentSpec.from_document(a_document(model=PINNED), "desk")
    bound = PydanticAITransport(script, model=pinned.model or None)
    assert bound.model == PINNED
    assert bound.context_window() == window_of(PINNED)

    unpinned = AgentSpec.from_document(a_document(), "desk")
    fell_through = PydanticAITransport(script, model=unpinned.model or None)
    assert fell_through.model == default_model()

    assert bound.context_window() != fell_through.context_window(), (
        "pick a pin whose window differs from the default's, or this test "
        "passes without measuring anything"
    )


def test_the_window_a_policy_is_measured_against_is_the_model_the_author_pinned(
    document: dict,
) -> None:
    """The reason the field is carried at all, held end to end.

    The worked example's `context-policy: long-threads` fires at 85% of what the
    model can hold. Pinning `llama3.2-1b-instruct` says the model holds 131,072
    tokens; the distribution default holds 32,768. A conversation that fits three
    times over inside the pinned model must therefore not be tidied at all — and
    for a round it was, down from 49,194 tokens to 547, because the harness asked
    the transport and never the author.

    `ReferenceTransport` is used precisely because it cannot say: it is the
    script with no framework and no model, so the author's pin is the only thing
    in the run that knows which model this is. That is the case the fallback
    closes, and it is the case that had no answer at all.
    """
    spec = AgentSpec.from_document(document, "refund-desk", EXAMPLE)
    pinned = replace(spec, model=PINNED)
    assert window_of(PINNED) > window_of(default_model())

    # A ticket that overflows the default's window and fits the pinned one.
    line = "2026-03-01 09:14 status unchanged; nothing new on this order. "
    ticket = line * ((window_of(default_model()) * 4) // len(line) + 1)

    def go(agent: AgentSpec):
        return asyncio.run(
            run(
                agent,
                ReferenceTransport(Script([
                    Turn("Checking.", (ToolCall("zendesk", {"ticket": "T-1"}),)),
                    Turn("Approved: the item arrived damaged within 30 days."),
                ])),
                "my lamp arrived broken, please refund",
                {"zendesk": lambda a: ticket, "payments": lambda a: "refunded"},
            )
        )

    with_pin = go(pinned)
    assert with_pin.tidyings == [], (
        "this conversation fits the model the author pinned, so nothing should "
        "have been thrown away"
    )
    assert "context-policy" not in with_pin.unmetered, with_pin.unmetered

    # And the other half: with no pin, nothing can say what the model holds, so
    # the policy is reported as unenforced rather than measured against a guess.
    without = go(spec)
    assert without.tidyings == []
    assert "context-policy" in without.unmetered, without.unmetered


def test_a_workspace_may_add_a_model_the_distribution_has_never_heard_of(
    document: dict, tmp_path: Path
) -> None:
    """The override layer, reaching a RUN and not only `pact check`.

    An air-gapped machine serving a model PACT has never heard of had no path at
    all: nothing could say what it holds, so a `context-policy:` — core tier, a
    line a non-coder writes — was permanently reported as unenforced, and the
    only fix was editing a file inside the distribution whose own first line
    says the author never writes it. That is "experts edit the product", which is
    the same answer as "experts write code for that" (D14), under a constraint
    (D17) that makes it unavoidable rather than inconvenient.

    A file the checker accepts and the harness never opens would be the same
    defect one hop along, so this drives it through `run()`.
    """
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "catalog.yaml").write_text(
        "version: 1\n"
        "models:\n"
        "  our-own-7b:\n"
        "    tier: small\n"
        "    served-by:\n"
        "      - { runtime: vllm, endpoint: local }\n"
        "    capabilities:\n"
        "      context-window:\n"
        "        value: 16384\n"
        "        provenance:\n"
        "          source: the max-model-len our platform team serves it with\n"
        "          as-of: 2026-07-28\n"
    )
    assert window_of("our-own-7b") is None, "the distribution must not already know it"
    assert window_of("our-own-7b", workspace=tmp_path) == 16384

    spec = replace(
        AgentSpec.from_document(document, "refund-desk", EXAMPLE),
        model="our-own-7b",
        workspace=str(tmp_path),
    )
    line = "2026-03-01 09:14 status unchanged; nothing new on this order. "
    out = asyncio.run(
        run(
            spec,
            ReferenceTransport(Script([
                Turn("Checking.", (ToolCall("zendesk", {"ticket": "T-1"}),)),
                Turn("Approved: the item arrived damaged within 30 days."),
            ])),
            "my lamp arrived broken, please refund",
            {
                "zendesk": lambda a: line * ((16384 * 4) // len(line) + 1),
                "payments": lambda a: "refunded",
            },
        )
    )
    assert "context-policy" not in out.unmetered, out.unmetered
    assert out.tidyings, "the author's policy was measured against their own model"


def test_a_pin_the_run_did_not_honour_is_reported_rather_than_measured_around(
    document: dict,
) -> None:
    """A mis-binding is not a licence to substitute one window for another.

    If the author pinned one model and the transport bound another, the run is
    answering on a model nobody chose. Measuring the context policy against the
    pin would tidy for a window the running model does not have; ignoring the pin
    would hide that the wrong model answered. So the number stays the running
    model's and the disagreement is named, both ids, through the same door a
    spend cap with no price list goes out of.
    """
    spec = replace(
        AgentSpec.from_document(document, "refund-desk", EXAMPLE), model=PINNED
    )
    bus = Bus()
    out = asyncio.run(
        run(
            spec,
            PydanticAITransport(Script([Turn("Approved.")])),  # binds the default
            "my lamp arrived broken, please refund",
            {"zendesk": lambda a: "broken on arrival", "payments": lambda a: "refunded"},
            bus=bus,
        )
    )
    assert "model-pin" in out.unmetered, out.unmetered
    said = [e for e in bus.log if str(e.address) == "session.limit.failed"]
    assert said, "a mis-binding nobody is told about is the silent kind"
    assert said[0].payload["pinned"] == PINNED
    assert said[0].payload["bound"] == default_model()


def test_a_team_members_pin_reaching_the_running_harness_is_honoured_or_reported(
    document: dict,
) -> None:
    """`delegate_by_running` builds a transport from a spec, in this tree, today.

    This test's own predecessor said "nothing in this tree constructs a transport
    from a spec yet", and `harness.delegate_by_running` had been doing exactly
    that — `transport_for(member)` — the whole time. So every delegated member's
    `model:` line was dropped by in-tree code, and the drop was written down as
    an absence.

    Both halves are held here. A factory that reads `member.model` binds what the
    member asked for; a factory that ignores it produces a mismatch that reaches
    the PARENT's bus, because the child's own `RunResult` is discarded and the
    bus is the only thing that survives the hop.
    """
    doc = {
        **document,
        "agents": {
            **document["agents"],
            "policy-checker": {**document["agents"]["policy-checker"], "model": PINNED},
        },
    }

    honoured: list[str] = []

    def reads_the_pin(member: AgentSpec):
        honoured.append(member.model)
        return PydanticAITransport(
            Script([Turn("Rule 2 applies.")]), model=member.model or None
        )

    asyncio.run(
        delegate_by_running(doc, reads_the_pin)(
            _grant("policy-checker", "does rule 2 apply?")
        )
    )
    assert honoured == [PINNED]

    bus = Bus()

    def ignores_the_pin(member: AgentSpec):
        return PydanticAITransport(Script([Turn("Rule 2 applies.")]))

    asyncio.run(
        delegate_by_running(doc, ignores_the_pin, bus=bus)(
            _grant("policy-checker", "does rule 2 apply?")
        )
    )
    failed = [e for e in bus.log if str(e.address) == "session.limit.failed"]
    assert failed, "the member ran on a model nobody asked for and nothing said so"
    assert "model-pin" in failed[0].payload["limits"]
    assert failed[0].payload["pinned"] == PINNED


def _grant(member: str, request: str):
    """One member's slice of a parent's budget, with nothing to divide."""
    from pact_adapters.delegation import Divides, Grant, Pool

    return Grant(
        member=member, pool=Pool(0.0, Divides.EVENLY, (member,)), request=request
    )


def test_a_model_this_workspace_added_itself_is_priced_like_any_other(
    tmp_path: Path,
) -> None:
    """The override layer reaching the MONEY half, not only the window.

    `window_of(..., workspace=)` was threaded into a run one round ago; the price
    lookup beside it was not. So a machine with its own `models/catalog.yaml`
    could size its context policy correctly and still had `usage()` refuse to
    exist, which put `cost-per-request-under` and `tokens-at-most` on
    `RunResult.unmetered` on every run with no no-code way out — for the exact
    D17 author the override layer was built for. `load_catalogue`'s own docstring
    names the shape: *a file the checker accepts but the harness never opens is
    the same defect one hop along.*
    """
    from pact_adapters.resolve import price_of
    from pact_adapters.transports._metering import can_price, priced

    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "catalog.yaml").write_text(
        "version: 1\n"
        "models:\n"
        "  our-own-model:\n"
        "    tier: small\n"
        "    served-by:\n"
        "      - { runtime: vllm, endpoint: local }\n"
        "    capabilities:\n"
        "      context-window:\n"
        "        value: 32768\n"
        "        provenance:\n"
        "          source: the max-model-len our platform team serves it with\n"
        "          as-of: 2026-07-28\n"
        "    cost: { input-per-mtok: 0.20 USD, output-per-mtok: 0.60 USD }\n"
    )
    ws = str(tmp_path)

    assert price_of("our-own-model", 1_000, 1_000) is None, (
        "the distribution must not already price it"
    )
    assert can_price("our-own-model") is False, "and must say so without the workspace"
    assert can_price("our-own-model", ws) is True, "the workspace's own row prices it"
    assert priced("our-own-model", 1_000_000, 1_000_000, ws) == (2_000_000, 0.80)

    # And through a transport, which is the hop that was missing: the row is
    # read by the thing that meters, not only by the thing that checks.
    made = PydanticAITransport(
        Script([Turn("Approved.")]), model="our-own-model", workspace=ws
    )
    assert made.prices_money is True
    assert made.context_window() == 32768
    spec = replace(
        AgentSpec(name="Desk", description="d", instructions="i"),
        limits=Limits(cost_per_request_under=0.05),
        workspace=ws,
        model="our-own-model",
    )
    out = asyncio.run(run(spec, made, "hello", {}))
    assert out.unmetered == (), out.unmetered
    assert out.never_reached == (), "a row priced above zero is a ceiling that can fire"


def test_a_ceiling_measured_against_a_free_model_says_it_can_never_fire(
    document: dict,
) -> None:
    """A meter that works perfectly and always reads zero.

    Different from `unmetered` and so a different field. `models/catalog.yaml`
    publishes five of its thirteen rows at `input-per-mtok: 0 USD` — a SOURCED zero,
    for weights this machine serves — so `can_price` says yes, `usage()` exists,
    `Limits.unmeterable` is empty, and the author is told their `0.05 USD` cap is
    enforced against a meter that reads 0.00 on every call for the life of the
    workspace. The worked example pins no `model:`, so it binds one of them: for
    the only configuration this example can run (`allow-egress: []`), the money
    ceiling meters zero.

    `models/catalog.yaml` names this outcome as the thing to avoid — *"a spend
    cap that can never be reached, under an author who believes they capped their
    spend"* — and it arrives here from the other direction, through a genuinely
    zero price rather than an unsourced one. `limits.yaml` knows about it and
    says so in a comment, which is not a surface anyone runs.
    """
    from pact_adapters.transports.anthropic_transport import AnthropicTransport
    from pact_adapters.transports.autogen_transport import AutoGenTransport

    script = lambda: Script([  # noqa: E731
        Turn("Checking.", (ToolCall("zendesk", {"ticket": "T-1"}),)),
        Turn("Approved: the item arrived damaged within 30 days."),
    ])
    tools = {"zendesk": lambda a: "lamp, broken", "payments": lambda a: "refunded"}
    spec = AgentSpec.from_document(document, "refund-desk", EXAMPLE)

    free = asyncio.run(run(spec, AutoGenTransport(script()), "refund", tools))
    assert free.unmetered == (), "nothing failed to measure — that is the point"
    assert len(free.never_reached) == 1, free.never_reached
    said = free.never_reached[0]
    assert said.startswith("agents/refund-desk/limits.yaml:"), said
    assert "cost-per-request-under" in said and default_model() in said
    assert "tokens-at-most" in said, "the fix has to be typeable"

    # A transport bound to a model that is NOT free says nothing, because there
    # is nothing to say: the ceiling can be reached.
    paid = asyncio.run(run(spec, AnthropicTransport(script()), "refund", tools))
    assert paid.never_reached == (), paid.never_reached
