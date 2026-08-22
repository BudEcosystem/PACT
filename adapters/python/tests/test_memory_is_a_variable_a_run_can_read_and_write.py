"""What `bind: remembers.<n>` reads, and what `remember-as:` writes (P8 wave 2).

The wave landed the checker and nothing else. `pact check` refused a tool that
wrote where the author said no tool may, `pact check` refused a bind naming a
fact that does not exist — and on a run, `bind: remembers.verified-account` filled
NOTHING and `remember-as: last-order-seen` wrote nothing. Measured on the shipped
fixture: the tool received `{}` where the account should have been, and the
sentence reporting the miss named `run-inputs.remembers.verified-account`, a
namespace that does not exist.

That is the field whose own help says *"this is how 'whose order' stops being
something the model decides"*, so what shipped was a promise about identity that
the run did not keep, and a `never-from:` guard biting on a write that never
happened.

Three things had to be true for the pair to be a variable, and each was missing:

* **The store had to hold more than pinned facts.** `Facts.from_document` kept
  only entries writing `survives-shortening: yes`, because it was built for one
  job — evidence a summary must not destroy. Every other declared `remembers:`
  entry "is none of this module's business", so the fixture's own two facts were
  not in it. Now every declared entry is held and the flag decides only what a
  shortening RE-STATES, which is what the flag was always about.

* **Something had to seed it.** `lasts: one-conversation` outlives a single
  `run()`, and where a conversation's memory is kept is the host's (§4). So it
  arrives as `remembered=`, beside `run_inputs=` in `SUPPLIED_BY_THE_HOST`.

* **The write had to happen after the rules.** A tool result goes into `history`
  and is read back to the model next turn, so it passes the interceptor chain
  first. A fact written before that would be the one copy of the result that
  never met a redaction rule, and `context-policy` re-states facts into later
  prompts — so the masked value would be un-masked by the memory.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
TREE = REPO / "tests/trees/a-desk-that-remembers"


def _tree() -> dict:
    """The shipped fixture, as the loader hands it over.

    Read through `pact show` so this test measures the document a run really
    gets, rather than a hand-written copy of it that can drift.
    """
    import subprocess

    out = subprocess.run(
        [str(REPO / "target/debug/pact"), "show", str(TREE)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout)


def _script() -> Script:
    return Script(
        [
            Turn("Looking it up.", (ToolCall("orders", {"action": "look-up", "order-number": "O-1"}),)),
            Turn("It shipped on Tuesday."),
        ]
    )


def _run(doc: dict, seen: list, **kw):
    spec = AgentSpec.from_document(doc, "desk")
    tools = {"orders": lambda a: (seen.append(dict(a)), "order O-1: a lamp, shipped")[1]}
    return spec, asyncio.run(
        run(spec, ReferenceTransport(_script()), "where is my order?", tools, **kw)
    )


def test_a_bind_from_memory_fills_the_argument_the_model_never_sees() -> None:
    """The whole promise of the field, on the shipped fixture."""
    seen: list = []
    _, result = _run(_tree(), seen, remembered={"verified-account": "ACC-77"})
    assert seen, "the tool was called"
    assert seen[0].get("account") == "ACC-77", seen
    assert not any("verified-account" in u for u in result.unenforced), result.unenforced


def test_the_model_is_never_offered_the_bound_argument() -> None:
    """It is bound precisely so it is not chosen. A fact the model can name is a
    fact the model can change."""
    spec, _ = _run(_tree(), [], remembered={"verified-account": "ACC-77"})
    orders = next(t for t in spec.tools if t.name == "orders")
    assert "account" not in json.dumps(orders.parameters), orders.parameters


def test_nothing_remembered_is_reported_in_the_authors_own_namespace() -> None:
    """The miss is still reported — and now it names a namespace that exists.

    It used to say `run-inputs.remembers.verified-account`, gluing the one
    namespace onto the other, which is the same defect the checker's own
    diagnostic goes out of its way to avoid.
    """
    seen: list = []
    _, result = _run(_tree(), seen)
    said = " ".join(result.unenforced)
    assert "remembers.verified-account" in said, result.unenforced
    assert "run-inputs.remembers" not in said, result.unenforced
    assert "account" not in seen[0], "an empty identity is worse than none at all"


def test_what_a_tool_answered_is_written_where_the_author_said_to_put_it() -> None:
    """`remember-as:` — the other direction, and the half nothing ran at all."""
    spec, _ = _run(_tree(), [], remembered={"verified-account": "ACC-77"})
    assert spec.facts.held.get("last-order-seen") == "order O-1: a lamp, shipped", spec.facts.held


def test_a_remembered_result_passes_the_rules_before_it_is_kept() -> None:
    """The write is after the interceptor chain, and that is the point.

    A tool result read back to the model next turn goes through the chain; a fact
    written before it would be the one copy nothing masked — and `context-policy`
    re-states facts into later prompts, so the memory would put back exactly what
    the redaction took out.
    """
    doc = _tree()
    doc["redaction"] = {
        "description": "Never let a card number out.",
        "hide": ["anything that looks like a card number"],
    }
    seen: list = []
    spec = AgentSpec.from_document(doc, "desk")
    tools = {"orders": lambda a: "paid with 4111111111111111"}
    asyncio.run(run(spec, ReferenceTransport(_script()), "where is my order?", tools,
                    remembered={"verified-account": "ACC-77"}))
    kept = spec.facts.held.get("last-order-seen", "")
    assert "4111111111111111" not in kept, kept
    assert kept, "and it is still remembered, masked"


def test_a_document_that_remembers_nothing_gains_nothing() -> None:
    """Additive inertness, §1.3. A tree with no `remembers:` and no `bind:` must
    be byte-identical to what it was."""
    plain = {
        "tools": {
            "zendesk": {
                "description": "Reads a ticket.",
                "url": "https://tickets.example.com",
                "method": "get",
                "actions": {"read": {"description": "reads", "takes": {"id": "text"}}},
            }
        },
        "agents": {
            "desk": {
                "description": "Decides refunds.",
                "instructions": "Read the ticket, then decide.",
                "uses": ["zendesk"],
            }
        },
    }
    spec = AgentSpec.from_document(plain, "desk")
    before = json.dumps(
        asyncio.run(
            run(spec, ReferenceTransport(Script([Turn("done")])), "hello",
                {"zendesk": lambda a: "a ticket"})
        ).trace()
    )
    after = json.dumps(
        asyncio.run(
            run(AgentSpec.from_document(plain, "desk"),
                ReferenceTransport(Script([Turn("done")])), "hello",
                {"zendesk": lambda a: "a ticket"}, remembered={"anything": "at all"})
        ).trace()
    )
    assert before == after, "a document that declares no memory is not changed by one"
    assert "remember" not in before, before


def test_the_seed_is_declared_host_supplied() -> None:
    """A new `run()` parameter is in one of the two registers or the suite fails.

    Where a conversation's memory is kept is the host's, the same way the model
    and the tools are — `lasts: one-conversation` outlives a single `run()`, so
    nothing in this port could have built it.
    """
    from pact_adapters.harness import DERIVED_FROM_THE_DOCUMENT, SUPPLIED_BY_THE_HOST

    assert "remembered" in SUPPLIED_BY_THE_HOST
    assert "remembered" not in DERIVED_FROM_THE_DOCUMENT
