"""Phase 1.1 — the root cause, made impossible rather than fixed again.

`harness.run` takes sixteen optional objects. For each one, "use what the author
wrote when the host passes nothing" was a separate hand-written line inside
`run`. **There were seven such lines for sixteen parameters.**

That is the cause, and it is not a bug in any of the sixteen: authored
configuration and host overrides shared one channel, so derivation was optional,
per-parameter, and invisible when omitted. Six mechanisms shipped built, tested
and read by nothing on the authored path. `remembers:` was the sixth, and it
landed in the very change whose stated purpose was to close this class.

Three checks here, and the third is the one that matters:

1. every parameter is **declared** — derived from the document, or host-only;
2. every declared derivation is **present** in `run`;
3. a run given nothing but a spec and a transport **behaves** as the document
   says, for each derived parameter — which is the only check that a derivation
   is real rather than spelled correctly.

`test_what_the_author_wrote_reaches_the_run.py` holds (3) per mechanism in
depth. This file holds the boundary itself: that no seventeenth parameter can be
added without somebody deciding, in writing, where it comes from.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.events import Bus  # noqa: E402
from pact_adapters.harness import (  # noqa: E402
    DERIVED_FROM_THE_DOCUMENT,
    SUPPLIED_BY_THE_HOST,
    run,
)
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    """The worked example through the real Rust loader (invariant P-1)."""
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(PACT_BIN), "show", str(EXAMPLE)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


def _parameters() -> set[str]:
    """Every parameter of `run` but `spec`, which is the document itself."""
    return set(inspect.signature(run).parameters) - {"spec"}


# ────────────────────────────────────────── 1. the boundary is total


def test_every_parameter_is_declared_one_way_or_the_other() -> None:
    """The check that makes the next mechanism impossible to forget.

    A seventeenth parameter appears in neither map until somebody puts it in one,
    and this fails until they do. That is the whole mechanism: the decision
    "where does this come from" stops being implicit in whether a line got
    written.
    """
    declared = set(DERIVED_FROM_THE_DOCUMENT) | set(SUPPLIED_BY_THE_HOST)
    undeclared = sorted(_parameters() - declared)
    assert not undeclared, (
        f"`run` takes {undeclared} and nothing says where they come from.\n"
        f"Add each to DERIVED_FROM_THE_DOCUMENT with the expression that derives "
        f"it, or to SUPPLIED_BY_THE_HOST to record that no document describes it. "
        f"A parameter in neither is how six mechanisms shipped inert."
    )


def test_nothing_is_declared_that_is_not_a_parameter() -> None:
    """The other direction. A stale entry describes a channel that no longer
    exists, and a register that can be wrong about its own subject is the thing
    this project has most of."""
    declared = set(DERIVED_FROM_THE_DOCUMENT) | set(SUPPLIED_BY_THE_HOST)
    ghosts = sorted(declared - _parameters())
    assert not ghosts, f"declared but not parameters of `run`: {ghosts}"


def test_no_parameter_is_declared_both_ways() -> None:
    """`chain` cannot both come from the document and be host-only. If it is in
    both, whichever map a reader consults first decides what they believe."""
    both = sorted(set(DERIVED_FROM_THE_DOCUMENT) & SUPPLIED_BY_THE_HOST)
    assert not both, f"declared as both authored and host-only: {both}"


# ─────────────────────────── 2. every declared derivation is actually written


def test_every_declared_derivation_appears_in_the_function() -> None:
    """A register that says `chain` comes from `spec.chain` while `run` reads
    `chain or Chain()` is worse than no register — and that exact line shipped:
    the two governance documents in the worked example loaded, validated, and
    were replaced by a policy nobody wrote."""
    body = inspect.getsource(run)
    missing = [
        f"{name} ← {source}"
        for name, source in DERIVED_FROM_THE_DOCUMENT.items()
        if source not in body
    ]
    assert not missing, (
        f"declared derivations that do not appear in `run`: {missing}"
    )


def test_no_derived_parameter_falls_back_with_or() -> None:
    """`x = x or spec.x` and `x = spec.x if x is None else x` are not the same
    check, and the difference has cost this repository two mechanisms.

    An empty `Chain()`, an empty `Teamwork()` and a `Gate` with no rules are all
    falsy. Under `or`, a host that passes one — or a document that produces one —
    is silently replaced by the default, which is how
    `examples/refund-desk/interceptors/` came to load, validate and do nothing
    while the card numbers it says it hides reached the model.
    """
    body = inspect.getsource(run)
    offenders = [
        name for name in DERIVED_FROM_THE_DOCUMENT
        if f"{name} = {name} or " in body
    ]
    assert not offenders, (
        f"{offenders} fall back with `or`, so a legitimately empty authored "
        f"object is discarded. Use `is None`."
    )


# ────────────────────── 3. and the run behaves as the document says, with
#                          nothing passed but a transport


def test_a_run_handed_only_a_transport_uses_every_authored_mechanism(
    document: dict,
) -> None:
    """The end-to-end form of the same claim, on the real worked example.

    Nothing is injected. If any of the seven derivations regressed to `None`,
    something below stops being true — which is what makes this the check the
    six inert mechanisms would each have failed.
    """
    spec = AgentSpec.from_document(document, "refund-desk", source=EXAMPLE)
    card = "please refund card 4111 1111 1111 1111"
    seen: list[str] = []
    bus = Bus()
    bus.on("", lambda e: seen.append(json.dumps(e.payload)))
    out = asyncio.run(
        run(spec, ReferenceTransport(Script([Turn("ok")] * 8)), card, bus=bus)
    )

    # `chain` — the author's redaction rule ran on the way in. Read off the bus
    # because that is where the run's own view of its messages is observable,
    # and it is the seam `test_one_order_across_kinds.py` already proves.
    assert seen, "the bus carried nothing, so this proves nothing"
    assert not [line for line in seen if "4111" in line], (
        "the card number survived, so `chain` did not come from the document"
    )
    assert any("card number removed" in line for line in seen), (
        "and the redacted form must be there, or the rule never ran at all"
    )
    # `loop` — the example's own stages, not a one-step default.
    assert out.phases, "no stage was recorded, so `loop` was not derived"
    assert set(out.phases) <= set(spec.loop.steps), out.phases
    # `asking` — the author's `policy:` reached the run and reports what it
    # could not apply, rather than an empty gate that reports nothing.
    assert spec.asking.rules, "the example ships a policy; this test needs it"
    # `team_budget` — `cost-per-request-under: 0.05 USD` became the pot.
    assert spec.limits.cost_per_request_under == 0.05


def test_the_same_run_with_an_override_prefers_the_override(document: dict) -> None:
    """The other half of the contract, so this file cannot be satisfied by making
    derivation unconditional. A host must still be able to override — that is
    what the channel is FOR — and the bug was never that overriding worked."""
    from pact_adapters.interceptors import Chain

    spec = AgentSpec.from_document(document, "refund-desk", source=EXAMPLE)
    card = "please refund card 4111 1111 1111 1111"
    seen: list[str] = []
    bus = Bus()
    bus.on("", lambda e: seen.append(json.dumps(e.payload)))
    asyncio.run(
        run(
            spec, ReferenceTransport(Script([Turn("ok")] * 8)), card,
            bus=bus, chain=Chain(),
        )
    )
    assert [line for line in seen if "4111" in line], (
        "an explicitly empty `chain` must win — otherwise derivation has stopped "
        "being an override and become a hard-coding"
    )
