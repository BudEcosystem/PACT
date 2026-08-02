"""An approval rule that names ONE ACTION of a tool, enforced.

`examples/refund-desk/policies/approvals.yaml` has three rules. Two name a
threshold on `payments/issue-refund` and were enforced. The third reads

    - when:
        - { tool: zendesk/reply }
      because: nothing goes to a customer without a person seeing it first

and was not. Measured before this round: a run reported `final`, the reply went
out, and `RunResult.unenforced` carried *"the rule about `zendesk/reply` was not
applied … fix: write `zendesk` instead of `zendesk/reply` in that rule"* — advice
that would also have gated the read-only `read-ticket` lookup the author wrote no
rule about, and which `pact check` refuses outright as
`loader/rule-names-no-action`.

The premise was stale rather than wrong-headed. `Rule.decidable` asserted *"every
shipped transport calls a tool by its name and carries no action"*; `ir._takes`
had since begun declaring `action: one of read-ticket, reply` on every
multi-action tool, so the model is shown the action and the call carries it —
which is already how `evals._calls` builds `<tool>/<action>` for
`must-call-before:`. One mechanism read the action off a call while the other
said it could not.

Every test here loads the author's own tree and passes NO gate in: the point is
that the line in their file reaches the run. A test that built the `Gate` itself
would prove the class works and say nothing about whether their rule arrives.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from consenting import allowing_the_connection  # noqa: E402
from pact_adapters.harness import ToolCall  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.questions import questions_for  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.suspension import NEEDS_APPROVAL  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

EXAMPLE = Path(__file__).resolve().parents[3] / "examples" / "refund-desk"


@lru_cache(maxsize=1)
def worked_example() -> dict:
    """The example tree, loaded by the real Rust loader (invariant P-1)."""
    return json.loads(
        subprocess.run(
            ["cargo", "run", "--quiet", "-p", "pact-cli", "--", "show", str(EXAMPLE)],
            cwd=str(EXAMPLE.parents[1]), capture_output=True, text=True, check=True,
        ).stdout
    )


@pytest.fixture(scope="module")
def document() -> dict:
    return worked_example()


class Watching:
    """What each tool was actually called with — the only honest evidence that a
    gate stopped something, because a run can report `suspended` and still have
    let the call through."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def tools(self) -> dict:
        def zendesk(a):
            self.calls.append(("zendesk", dict(a)))
            return "lamp, 6 days ago, broken, 40 USD"

        def payments(a):
            self.calls.append(("payments", dict(a)))
            return f"refunded {a.get('amount')}"

        return {"zendesk": zendesk, "payments": payments}

    @property
    def names(self) -> list[str]:
        return [n for n, _ in self.calls]


def desk(document: dict) -> AgentSpec:
    return AgentSpec.from_document(document, "refund-desk", EXAMPLE)


def one_call(name: str, args: dict):
    """A factory, not a script: a `Script` is a cursor and `ran` resumes."""
    return lambda: Script(
        [Turn("working on it", (ToolCall(name, args),)), Turn("Approved.")]
    )


def ran(spec: AgentSpec, script, seen: "Watching"):
    """The author's document, driven with nothing handed in.

    No `needs_approval=`, no `asking=`. Whatever stops a call here was written in
    `policies/approvals.yaml` by somebody who cannot write code (D14).

    The payments connection's own consent is granted on the way past, because
    `resources/payments-server.yaml` gates it and every `payments` call in this
    file now stops there first. That is the example obeying a different authored
    line, and it is `test_connection_consent.py`'s guarantee rather than this
    file's — so it is answered here and what is under test is what happens next.
    """
    return allowing_the_connection(
        spec, lambda: ReferenceTransport(script()), "refund me", seen.tools()
    )


# ───────────────────────────────────────── the rule the author wrote, enforced


def test_a_rule_naming_one_action_stops_that_action(document: dict) -> None:
    """`zendesk/reply` stops a call that says it is the reply.

    The whole of the author's line: *"nothing goes to a customer without a person
    seeing it first"*. Before this the reply went out and the run said `final`.
    """
    seen = Watching()
    result = ran(
        desk(document),
        one_call("zendesk", {"action": "reply", "ticket-id": "T-1", "message": "Refunded."}),
        seen,
    )

    assert result.halted == "suspended", result.output
    assert result.suspension is not None
    assert result.suspension.reason == NEEDS_APPROVAL
    assert seen.names == [], "the reply reached the customer before anyone saw it"
    assert (
        "nothing goes to a customer without a person seeing it first"
        in result.suspension.in_words
    ), result.suspension.in_words


def test_the_same_rule_lets_the_tools_other_actions_through(document: dict) -> None:
    """`read-ticket` is not `reply`, and the author wrote no rule about it.

    This is the direction the old code could not take without stopping the
    lookup as well, which is why it stopped neither. A gate that fires on every
    `zendesk` call is the safe direction and the wrong reading — it is how a
    governance setting turns into a nuisance somebody switches off.
    """
    seen = Watching()
    result = ran(desk(document), one_call("zendesk", {"action": "read-ticket", "ticket-id": "T-1"}), seen)

    assert result.halted == "final", result.halted
    assert seen.names == ["zendesk"], "the read-only lookup must simply run"


def test_the_read_only_lookup_is_not_reported_as_something_nobody_could_decide(
    document: dict,
) -> None:
    """A call that says which action it is NOT leaves nothing to report.

    The rule was applied to it — the answer was "this is not that call" — so
    saying it went unenforced would be the same untruth pointing the other way.
    """
    gate = questions_for(document, "refund-desk", EXAMPLE)
    assert gate.undecided_on("zendesk", {"action": "read-ticket", "ticket-id": "T-1"}) == ()
    assert gate.undecided_on("zendesk", {"action": "reply", "message": "hi"}) == ()


def test_the_worked_examples_own_run_no_longer_reports_the_reply_rule_as_unapplied(
    document: dict,
) -> None:
    """The sentence this round exists to remove, gone from a run that obeys the rule.

    `zendesk/reply` was on `unenforced` for EVERY run of this example, including
    runs that never touched `zendesk` at all, because it was decided once at load
    from the rule rather than per call.
    """
    seen = Watching()
    reply = ran(
        desk(document),
        one_call("zendesk", {"action": "reply", "ticket-id": "T-1", "message": "Refunded."}),
        seen,
    )
    lookup = ran(desk(document), one_call("zendesk", {"action": "read-ticket", "ticket-id": "T-1"}), Watching())

    # Only the APPROVAL sentence. `unenforced` carries other kinds now — an
    # unfilled `bind:` names the same `zendesk/reply` — and a substring test that
    # cannot tell them apart would fail on a line that has nothing to do with
    # this rule.
    def about_the_rule(said: tuple[str, ...]) -> list[str]:
        return [u for u in said if "zendesk/reply" in u and not u.startswith("bind:")]

    assert not about_the_rule(reply.unenforced), reply.unenforced
    assert not about_the_rule(lookup.unenforced), lookup.unenforced
    # And the load-time channel that used to carry it says nothing at all now.
    assert questions_for(document, "refund-desk", EXAMPLE).unenforced == ()


# ─────────────────────────────────── what is left: a call that names no action


def test_a_call_that_names_no_action_is_reported_with_a_line_to_type(
    document: dict,
) -> None:
    """Neither silently gated nor silently let through — said, with a fix.

    NEEDS THE WIRING in `harness.run` described in this round's `needs_wiring`:
    the sentence is a fact about a CALL now, so it is collected per call through
    `Gate.undecided_on` rather than read once from `Gate.unenforced` before the
    run starts. Until that edit lands this assertion fails and the one below it,
    which reads the gate directly, passes.
    """
    seen = Watching()
    result = ran(desk(document), one_call("zendesk", {"ticket-id": "T-1"}), seen)

    assert result.halted == "final", "not gated on a guess"
    assert seen.names == ["zendesk"]
    said = "\n".join(result.unenforced)
    assert "zendesk/reply" in said, said


def test_the_sentence_about_it_names_the_file_the_line_and_a_line_to_type(
    document: dict,
) -> None:
    """Where, what, why, and something the author can type — the project's bar.

    The two fixes it used to offer are gone with the premise. *"Write `zendesk`
    instead of `zendesk/reply`"* would gate the read-only lookup, and
    `pact-loader::approvals` refuses that spelling as
    `loader/rule-names-no-action` — a fix that cannot be typed. *"Move `reply`
    into a tool file of its own"* was surgery on a tool to fix a policy, and the
    new file would declare `reply` under its own `actions:`, so a call naming no
    action would be exactly as silent as before.
    """
    gate = questions_for(document, "refund-desk", EXAMPLE)
    said = "\n".join(gate.undecided_on("zendesk", {"ticket-id": "T-1"}))

    assert said, "a rule that could not be applied must not go quiet"
    assert said.startswith("policies/approvals.yaml:36"), said
    assert "did not say which of its actions it was" in said
    assert "fix: write a rule for `zendesk/read-ticket` as well" in said
    # The advice that is gone.
    assert "instead of `zendesk/reply`" not in said, said
    assert "tool file of its own" not in said, said
    # No jargon: a support lead reads this (D13).
    for word in ("atom", "predicate", "decidable", "vocabulary", "None", "args"):
        assert word not in said, f"{word!r} is not a word a support lead reads: {said}"


def test_the_fix_the_sentence_offers_actually_stops_the_call(document: dict) -> None:
    """Type what it says and the silent call is stopped. Otherwise it is advice.

    Once every action of a tool has a rule there is no longer a call to that tool
    the author wrote no rule about, so a call that names none of them is stopped
    — whichever action it turns out to be, they wrote a rule about it. That is
    also the only spelling `pact check` accepts for "ask about every call to this
    tool": a bare `tool: zendesk` is refused as `loader/rule-names-no-action`.
    """
    covered = copy.deepcopy(document)
    covered["policies"]["approvals"]["ask-a-person"].append({
        "when": [{"tool": "zendesk/read-ticket"}],
        "because": "we look at every ticket this desk opens",
        "question": "is-this-ok",
    })
    seen = Watching()
    result = ran(AgentSpec.from_document(covered, "refund-desk", EXAMPLE),
                 one_call("zendesk", {"ticket-id": "T-1"}), seen)

    assert result.halted == "suspended", result.halted
    assert seen.names == [], "nothing may run while the answer is outstanding"
    assert questions_for(covered, "refund-desk", EXAMPLE).undecided_on(
        "zendesk", {"ticket-id": "T-1"}
    ) == (), "the rule was applied, so there is nothing left to report"


def test_covering_every_action_does_not_defeat_a_threshold(document: dict) -> None:
    """The 40 USD refund still runs when both `payments` actions have a rule.

    "Every action is ruled on" is asked action by action against THIS call, not
    tool-wide. A tool-wide reading would have turned a rule about looking orders
    up into a gate on every small refund — the over-gating this round is here to
    remove, reappearing one door along.
    """
    covered = copy.deepcopy(document)
    covered["policies"]["approvals"]["ask-a-person"].append({
        "when": [{"tool": "payments/look-up-order"}],
        "because": "we log every order we open",
        "question": "is-this-ok",
    })
    spec = AgentSpec.from_document(covered, "refund-desk", EXAMPLE)

    small = Watching()
    assert ran(spec, one_call("payments", {"amount": "40.00 USD"}), small).halted == "final"
    assert small.names == ["payments"]

    large = Watching()
    assert ran(spec, one_call("payments", {"amount": "300.00 USD"}), large).halted == "suspended"
    assert large.names == []


# ──────────────────────────────── the gate the action half must not have broken


def test_a_refund_over_the_limit_still_waits_when_the_call_names_no_action(
    document: dict,
) -> None:
    """The action half narrows; it must never take a threshold off.

    `payments/issue-refund` names an action AND carries `more-than: 200 USD`. A
    first cut of this change refused every atom whose action the call did not
    state, which read plausibly and quietly removed the 300 USD gate from every
    call the model wrote without an `action:` — the one gate in the example that
    was working.
    """
    seen = Watching()
    result = ran(desk(document), one_call("payments", {"amount": "300.00 USD"}), seen)

    assert result.halted == "suspended", result.output
    assert result.suspension.reason == NEEDS_APPROVAL
    assert seen.names == [], "the money moved before anyone was asked"


def test_a_refund_under_the_limit_still_runs_when_the_call_names_its_action(
    document: dict,
) -> None:
    """And the threshold still means 200 when the call does say what it is."""
    seen = Watching()
    result = ran(
        desk(document),
        one_call("payments", {"action": "issue-refund", "amount": "40.00 USD"}),
        seen,
    )

    assert result.halted == "final"
    assert seen.names == ["payments"]


def test_a_lookup_carrying_an_amount_is_not_the_refund_the_threshold_is_about(
    document: dict,
) -> None:
    """`action: look-up-order` is not `issue-refund`, whatever else it carries.

    Before the action half was read, the arguments were the only evidence — so a
    lookup that happened to be handed an amount matched a rule written about
    issuing money.
    """
    seen = Watching()
    result = ran(
        desk(document),
        one_call("payments", {"action": "look-up-order", "order-number": "A-1182",
                              "amount": "300.00 USD"}),
        seen,
    )

    assert result.halted == "final", result.halted
    assert seen.names == ["payments"]
