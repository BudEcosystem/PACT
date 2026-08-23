"""The two rewrite powers become authorable, because a program can reach them.

`Power` has five members and an author could write three. `change-the-request`
and `change-the-answer` were REMOVED from `interceptor.may` (R24) for a reason
that was exactly right at the time: no sentence in the closed vocabulary
rewrites — every one hides, stops, or sends the run elsewhere — so declaring
either got the rule refused by the next check down. A choice a non-coder can type
and nothing can ever exercise reads as a capability, which is worse than an
absent one. `docs/50-NOT-COPIED.md` §6 recorded them as host-only, with the
condition that would let them back: *"a sentence somebody actually wants"*.

The `program` kind is that sentence's missing half. §6's own worry about a
rewrite was that it "is not reviewable in a way `instructions:` and a stage's
`says:` are" — and a carried program is: it is a file in the folder, fingerprinted
since P3, declared with what it takes and answers with, and refused unless it is
`pure`.

So two forms join the vocabulary:

    replace the answer with what <a program> returns
    replace what the model is told with what <a program> returns

and with a sentence that reaches them, the powers are declarable again. This is a
withdrawal of half of R24, recorded the way §8.3 records R29's: the row is
amended rather than deleted, because a row that quietly disappears is
indistinguishable from one nobody noticed.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from pact_adapters.interceptors import AUTHORABLE, Chain, Power  # noqa: E402

#: A desk whose one rule hands what it was about to say to a carried program and
#: says whatever comes back.
REWRITES = {
    "programs": {
        "house-style": {
            "description": "Puts an answer into the words this desk uses.",
            "engine": "wasm",
            "determinism": "pure",
            "takes": {"content": "text"},
            "answers-with": {"content": "text"},
            "fuel": {"instructions-at-most": "1m", "when-it-runs-out": "stop-and-say-so"},
        }
    },
    "interceptors": {
        "in-house-style": {
            "description": "Says everything the way this desk says it.",
            "when": "turn.message.after",
            "may": ["change-the-answer"],
            "rules": ["replace the answer with what house-style returns"],
        }
    },
    "agents": {
        "desk": {
            "description": "Answers customers.",
            "instructions": "Answer the question.",
            "interceptors": ["in-house-style"],
        }
    },
}


def _shout(name: str, args: dict) -> str:
    assert name == "house-style"
    return args["content"].upper()


# ────────────────────────────────────────────── the power is authorable again


def test_both_rewrite_powers_are_authorable_now() -> None:
    """A power with a sentence that reaches it is a power an author may declare.

    This is the whole of R24's argument, run the other way: the row said a choice
    nothing can exercise is worse than an absent one, so a choice something CAN
    exercise belongs back on the list.
    """
    assert Power.CHANGE_ANSWER in AUTHORABLE
    assert Power.CHANGE_REQUEST in AUTHORABLE


def test_a_rule_rewrites_what_the_agent_was_about_to_say() -> None:
    chain = Chain.from_document(REWRITES, "desk", run_program=_shout)
    seen, decision = chain.run("turn.message.after", {"content": "we will refund that"})
    assert seen["content"] == "WE WILL REFUND THAT"
    assert decision.stop is None


def test_the_program_is_handed_what_was_there_and_nothing_else() -> None:
    """A rewriter sees the content and does not get the run's other business."""
    got: list[dict] = []

    def watching(name: str, args: dict) -> str:
        got.append(dict(args))
        return "fine"

    chain = Chain.from_document(REWRITES, "desk", run_program=watching)
    chain.run("turn.message.after", {"content": "hello", "name": "zendesk"})
    assert got == [{"content": "hello"}]


# ────────────────────────────────────────────────────────── the honest absence


def test_a_rewrite_with_nothing_to_run_it_changes_nothing_and_says_so() -> None:
    """A rule that cannot run must not silently pass the words through.

    It leaves them exactly as they were — a rewriter that half-ran would be worse
    than one that did not — and the chain records that it could not, so the run
    can report it rather than the author believing their words were applied.
    """
    chain = Chain.from_document(REWRITES, "desk")
    seen, decision = chain.run("turn.message.after", {"content": "we will refund that"})
    assert seen["content"] == "we will refund that"
    assert chain.unenforced, "a rule that could not run has to be reportable"
    assert "house-style" in " ".join(chain.unenforced)


def test_a_program_that_raises_leaves_the_words_alone() -> None:
    """A rewriter's failure is not the run's, and never a half-applied answer."""
    def angry(name: str, args: dict) -> str:
        raise RuntimeError("no")

    chain = Chain.from_document(REWRITES, "desk", run_program=angry)
    seen, _ = chain.run("turn.message.after", {"content": "unchanged"})
    assert seen["content"] == "unchanged"
    assert "house-style" in " ".join(chain.unenforced)


# ────────────────────────────────────────────────────────────── still refused


def test_a_rule_that_rewrites_without_declaring_the_power_is_refused() -> None:
    """`may:` is what a reviewer reads to answer "what can this do?"."""
    doc = {**REWRITES, "interceptors": {
        "in-house-style": {**REWRITES["interceptors"]["in-house-style"], "may": ["hide-values"]},
    }}
    with pytest.raises(Exception) as raised:
        Chain.from_document(doc, "desk", run_program=_shout)
    assert "change-the-answer" in str(raised.value)


def test_a_sentence_naming_a_program_the_tree_does_not_have_is_refused() -> None:
    doc = {**REWRITES, "interceptors": {
        "in-house-style": {
            **REWRITES["interceptors"]["in-house-style"],
            "rules": ["replace the answer with what no-such-program returns"],
        },
    }}
    with pytest.raises(Exception) as raised:
        Chain.from_document(doc, "desk", run_program=_shout)
    assert "no-such-program" in str(raised.value)


#: A document that BOTH hides and rewrites. The commonest real shape — a desk
#: that speaks in its own words and must never print a card number — and the one
#: the first version of this feature broke.
HIDES_AND_REWRITES = {
    "programs": REWRITES["programs"],
    "interceptors": {
        "in-house-style": {
            "description": "Says everything the way this desk says it, and hides card numbers.",
            "when": "turn.message.after",
            "may": ["change-the-answer", "hide-values"],
            "rules": [
                "anything that looks like a card number",
                "replace the answer with what house-style returns",
            ],
        }
    },
    "agents": {
        "desk": {
            "description": "Answers customers.",
            "instructions": "Answer the question.",
            "interceptors": ["in-house-style"],
        }
    },
}


def test_a_rewrite_does_not_delete_the_hiding_rules_beside_it() -> None:
    """The attack §8.5 says a rewrite cannot mount, which it could.

    `body` returned as soon as a rewriter had run, so every hiding rule in the
    same document was skipped: measured, a card number survived a chain whose own
    first rule was written to remove it. A rewriting rule silently disabling the
    redaction beside it is worse than the rewrite being refused outright, because
    the author reads two rules and gets one.

    The order is rewrite THEN hide, and it is that way round on purpose: the
    hiders must see the words that will actually be said, including any a
    rewriter introduced.
    """
    chain = Chain.from_document(HIDES_AND_REWRITES, "desk", run_program=_shout)
    seen, _ = chain.run("turn.message.after", {"content": "card 4111111111111111 here"})
    assert "4111111111111111" not in seen["content"], seen
    # And the rewrite still happened: the words the rewriter produced are its
    # own. The whole line is NOT uppercase, and that is the correct result --
    # `[removed]` is put there by the hider, which runs after, and the hider
    # writes it in its own words rather than the rewriter's.
    assert "CARD" in seen["content"] and "HERE" in seen["content"], seen
    assert "[removed]" in seen["content"], seen


def test_a_rewriter_that_introduces_a_card_number_is_still_masked() -> None:
    """The reason the order is rewrite-then-hide rather than the reverse."""
    chain = Chain.from_document(
        HIDES_AND_REWRITES, "desk",
        run_program=lambda n, a: "your card 4111111111111111 was refunded",
    )
    seen, _ = chain.run("turn.message.after", {"content": "done"})
    assert "4111111111111111" not in seen["content"], seen


# ────────────────────────────── the same rule, through the door a host uses


def _through_run(doc: dict, said: str, **kw):
    """The shipped entry point, not the `Chain` API.

    Every test above builds a `Chain` by hand and hands it a runner. That is the
    right way to test a chain and the wrong way to believe a claim about a RUN:
    `AgentSpec.from_document` builds the chain with no runner, and `run()` passed
    its runner to loops, projections and code stages and never to the chain. So a
    rewriting rule never rewrote anything on a real run, and the honest sentence
    the chain recorded about it never reached `RunResult.unenforced` either.
    """
    import asyncio
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from pact_adapters.harness import run
    from pact_adapters.ir import AgentSpec
    from pact_adapters.script import Script, Turn
    from pact_adapters.transports.mock import ReferenceTransport

    spec = AgentSpec.from_document(doc, "desk")
    return spec, asyncio.run(
        run(spec, ReferenceTransport(Script([Turn(said)])), "can I have a refund?", {}, **kw)
    )


def test_a_rewriting_rule_rewrites_on_a_real_run() -> None:
    """The claim §8.5's withdrawal rests on, through the door a host really uses."""
    _, result = _through_run(
        REWRITES, "we will refund that", run_program=lambda n, a: a["content"].upper()
    )
    assert result.output == "WE WILL REFUND THAT", result.output


def test_a_run_with_nothing_to_run_the_rewriter_says_so() -> None:
    """And where there is no runner, the run says what it could not do.

    The chain recorded the sentence all along and nothing collected it, so the
    only way to see it was to hold the `Chain` object — which a host does not.
    """
    _, result = _through_run(REWRITES, "we will refund that")
    assert result.output == "we will refund that"
    said = " ".join(result.unenforced)
    assert "house-style" in said, result.unenforced
    assert "left exactly as they were" in said, result.unenforced


def test_a_workspace_with_no_rewriting_rule_gains_nothing() -> None:
    """Additive inertness for the wiring itself."""
    plain = {
        "agents": {
            "desk": {"description": "Answers customers.", "instructions": "Answer the question."}
        }
    }
    _, result = _through_run(plain, "hello", run_program=lambda n, a: "SHOUTED")
    assert result.output == "hello"
    assert not result.unenforced, result.unenforced
