"""Scripted answers that are what the agent says it gives.

An agent's answer is held to its `answers-with:` (`pact_adapters.answers_fit`).
A test that scripts a model for the worked example — the Refund Desk gives a
`decision`, a `reason` and an `amount` — and is not ABOUT the answer has to
script one that fits, or what it measures is the harness asking again.
"""

from __future__ import annotations

import re
from typing import Mapping

from pact_adapters.questions import Shape

#: The three lines the Refund Desk's answer ends with, for a refund it grants.
REFUND = "- decision: approved\n- reason: as explained above\n- amount: 45 USD"


def fits(said: str = "", decision: str = "", amount: str = "") -> str:
    """`said`, ended the way the Refund Desk is asked to end its reply.

    The three fields say what `said` says, so a test that grades the words is
    grading the same answer: `declined` when the words decline, the amount the
    words name (none for a decline). The reason names no rule, so it cannot
    satisfy a check the words were meant to."""
    decision = decision or ("declined" if "declin" in said.lower() else "approved")
    named = re.search(r"\d+(?:\.\d+)? USD", said)
    amount = amount or (named.group(0) if named else "0 USD" if decision == "declined" else "45 USD")
    lines = f"- decision: {decision}\n- reason: as explained above\n- amount: {amount}"
    return f"{said}\n{lines}" if said else lines


#: What the worked example's two checkers end their replies with.
FRAUD = "- concern: none\n- why: nothing suspicious"
POLICY = "- allowed: yes\n- clause: rule 2, faulty on arrival"


def fraud_says(said: str = "") -> str:
    return f"{said}\n{FRAUD}" if said else FRAUD


def policy_says(said: str = "") -> str:
    return f"{said}\n{POLICY}" if said else POLICY


def fits_whoever_asks(said: str = "") -> str:
    """`said`, ended with what each of the worked example's three agents gives.

    For a stand-in that is handed to the desk AND to whichever checker the
    desk consults, and cannot tell which is asking. A field an agent does not
    declare is not a reason to ask again and is dropped, so the one reply is
    an answer for all three."""
    return f"{fits(said)}\n{POLICY}\n{FRAUD}"


def one_that_fits(
    shape: Mapping[str, str],
    shapes: Mapping[str, Mapping[str, str]] | None = None,
    said: str = "",
) -> str:
    """A reply that fits `shape`: `said`, and then each field the shape
    requires on a line of its own, with the example its shape reader gives
    (`Shape.example`), the way the model is asked to end its reply.

    For a stand-in that answers for ANY agent (the golden set runs every agent
    in `examples/`). An optional field is left out, which fits. With no shape
    it is `said`."""
    lines = []
    for name, written in shape.items():
        if str(written).rstrip().endswith(", optional"):
            continue
        lines.append(f"- {name}: {Shape.parse(written, dict(shapes or {})).example()}")
    return "\n".join(part for part in (said, "\n".join(lines)) if part)
