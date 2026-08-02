"""AC-5.1 — eight orchestration patterns, each a different coordination rule.

The criterion asks for **≥8 orchestration patterns**. `examples/patterns/` is
where they live, one small workspace each, and this file holds three things
about them that a directory of YAML cannot hold about itself:

1. every one **loads** through the real Rust loader;
2. every one is **distinct** — a different `teamwork:` rule, not a different
   name for the same coordination;
3. every one **runs** to an answer over a scripted transport.

(3) is the one that matters. A pattern that loads is a document; a pattern that
runs is a shape. The register recorded these as *"0 files each"*, and a
directory of eight files that nothing executes would be the same finding with a
larger denominator.

**Three of the criterion's named patterns are absent, and deliberately.**
`blackboard` needs a store agents read and write between turns; `market` and
`auction` need bidding and a settlement rule. PACT has neither primitive, and
`teamwork:` is a *waiting* vocabulary — who is asked, how long for, what happens
when one fails. Inventing shared mutable state between agents to satisfy a
criterion would be the largest design change in the system made for the smallest
reason. What is here instead is documented in `docs/70-PRODUCTION-GAP-REGISTER.md`
against AC-5.1, with what each of the three would require.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
PATTERNS = REPO / "examples" / "patterns"
PACT_BIN = REPO / "target" / "debug" / "pact"

#: Each pattern, and the agent that does the coordinating. Written out rather
#: than guessed from the directory, because "which agent is the supervisor" is
#: the one fact about a pattern that its file layout does not carry.
LEADS: dict[str, str] = {
    "quorum": "referee",
    "race": "referee",
    "pipeline": "editor",
    "swarm": "dispatcher",
    "weighted": "assessor",
    "escalation": "approver",
    "debate": "judge",
    "first-answer": "router",
}


def shown(name: str) -> dict[str, Any]:
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(PACT_BIN), "show", str(PATTERNS / name)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def test_the_directory_and_this_file_describe_the_same_patterns() -> None:
    """A ninth pattern added to `examples/patterns/` and not to `LEADS` would be
    one nothing here runs — which is how a directory comes to look like coverage.
    """
    on_disk = {p.name for p in PATTERNS.iterdir() if p.is_dir()}
    assert on_disk == set(LEADS), (
        f"examples/patterns/ has {sorted(on_disk)}; this file knows {sorted(LEADS)}"
    )


def test_the_thesis_asks_for_eight_and_there_are_eight() -> None:
    assert len(LEADS) >= 8, sorted(LEADS)


@pytest.mark.parametrize("name", sorted(LEADS))
def test_every_pattern_loads_through_the_real_loader(name: str) -> None:
    """`pact check` accepting it is the floor. A pattern the checker refuses is
    not an example of anything."""
    out = subprocess.run(
        [str(PACT_BIN), "check", str(PATTERNS / name)], capture_output=True, text=True
    )
    assert out.returncode == 0, out.stdout + out.stderr
    assert "loaded cleanly" in out.stdout, out.stdout


@pytest.mark.parametrize("name", sorted(LEADS))
def test_every_pattern_names_a_team_and_a_rule_for_waiting_on_it(name: str) -> None:
    """A pattern whose lead has no teammates is not orchestrating anything, and
    one with no `teamwork:` block is using the default — which is a ninth copy of
    `waits-for: everyone` rather than a pattern."""
    spec = AgentSpec.from_document(shown(name), LEADS[name], source=PATTERNS / name)
    assert spec.team, f"{name}'s lead has no `team:`"
    assert spec.teamwork is not None, f"{name} declares no `teamwork:`"


def test_no_two_patterns_wait_the_same_way() -> None:
    """The check that stops this being eight names for one behaviour.

    Compared on the WAITING RULE — how much of the team has to come back, in what
    order, and what happens when one fails — because that is what an orchestration
    pattern *is*. Two patterns with the same triple differ only in their prose.
    """
    rules: dict[str, tuple] = {}
    for name, lead in LEADS.items():
        spec = AgentSpec.from_document(shown(name), lead, source=PATTERNS / name)
        t = spec.teamwork
        rules[name] = (
            t.waits_for, t.enough_is, t.gives_up_after,
            t.starts, t.divides_the_budget, t.if_someone_fails,
        )
    clashes = [
        (a, b) for a in rules for b in rules if a < b and rules[a] == rules[b]
    ]
    assert not clashes, (
        "these patterns coordinate identically and differ only in their prose:\n"
        + "\n".join(f"  {a} == {b}: {rules[a]}" for a, b in clashes)
    )


def test_the_two_that_look_alike_are_the_one_line_apart_they_claim_to_be() -> None:
    """`swarm` and `first-answer` are the pair a reader will confuse, and both
    files say so in words. This is that claim, held.

    `anyone` takes the first reply of ANY kind, so a teammate that fails fastest
    wins. `the-first-good-answer` waits past the failures. It is one line, and it
    is the difference between a resilience pattern and a race a failure can win.
    """
    swarm = AgentSpec.from_document(shown("swarm"), "dispatcher", source=PATTERNS / "swarm")
    first = AgentSpec.from_document(
        shown("first-answer"), "router", source=PATTERNS / "first-answer"
    )
    assert swarm.teamwork.waits_for == "the-first-good-answer", swarm.teamwork
    assert first.teamwork.waits_for == "anyone", first.teamwork
    # And everything else about how they wait is the same, which is what makes
    # the one line the whole difference.
    assert swarm.teamwork.starts == first.teamwork.starts
    assert swarm.teamwork.divides_the_budget == first.teamwork.divides_the_budget


@pytest.mark.parametrize("name", sorted(LEADS))
def test_every_pattern_runs_to_an_answer(name: str) -> None:
    """The one that makes these shapes rather than documents.

    A scripted transport that always answers, and no tool implementations — so
    what is under test is whether the pattern's own stages and waiting rules
    reach an answer, not whether a model is good at anything. The teammates are
    unimplemented, which is the honest default: a run that needs one suspends,
    and that is a real outcome rather than a crash.
    """
    root = PATTERNS / name
    spec = AgentSpec.from_document(shown(name), LEADS[name], source=root)
    out = asyncio.run(
        run(spec, ReferenceTransport(Script([Turn("here is the answer")] * 40)), "go")
    )
    assert out.halted in ("final", "suspended"), (
        f"{name} ended as {out.halted!r} — it stopped on a ceiling rather than "
        f"reaching an answer or a wait somebody can clear"
    )
    # `phases`, not `steps`. A pattern that parks before its first model call
    # has taken zero steps and has still entered a stage, and asserting `steps`
    # found exactly that: `debate` opened with `does: ask-someone`, which parks
    # for a PERSON — teammates are offered to the model as tools, so asking one
    # is `use-tools`. The stage was right and the verb was wrong, and the run
    # suspended before the debate began.
    assert out.phases, f"{name} entered no stage at all"


def test_the_pattern_that_needs_a_person_says_who_and_by_when() -> None:
    """`escalation` is the only shape here that parks, and a park with no
    audience and no deadline is a hang wearing a governance label.

    Read off the loader's own wait list — the one §9.4 G14 obliges a runtime to
    walk — rather than off the file, so this asserts what a runtime receives.
    """
    out = subprocess.run(
        [str(PACT_BIN), "waits", str(PATTERNS / "escalation")],
        capture_output=True, text=True, check=True,
    )
    waits = json.loads(out.stdout)["waits"]
    assert waits, "escalation must produce a wait, or its whole point is missing"
    theirs = next((w for w in waits if w["question"] == "what-is-it-worth"), None)
    assert theirs is not None, [w["question"] for w in waits]
    assert theirs["asked-of"], f"nobody is named to answer it: {theirs}"
    assert theirs["answer-within"], f"no deadline: {theirs}"
    assert theirs["if-nobody-answers"] == "stop-and-say-so", (
        "a deadline that approves a claim nobody valued is the expensive mistake "
        f"this shape exists to prevent: {theirs}"
    )
    assert theirs["wakes"], "a scheduler must be able to time it"
