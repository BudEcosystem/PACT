"""`allow-egress:` offers six model roles. Five of them were read by nothing.

Measured before this file existed: every egress check in the repository asked
the same question — `"llm" in allow-egress:` — in `resolve.needs_of`,
`judge.why_no_judge` and `scoring._pick_model`, and once more in Rust. So a
per-role list was one boolean wearing six names. `allow-egress: [judge]`
behaved in every respect exactly like `allow-egress: []`, and `stt`, `tts`,
`embedder` and `reflector` were four words a workspace could write that changed
nothing at all.

What is held here is the property a single boolean cannot have: **the same
workspace admits one binding and refuses another, because of which role each one
plays.** Every document comes through `pact show` over the worked example, so
what is under test is the author's own line reaching the check — not a
dictionary this file built. A test that constructs the object proves the object
works and says nothing about whether the author's line gets there.

The Rust half of the same rule is
`crates/pact-cli/tests/one_grant_names_one_role.rs`, which holds it at
`pact check` time. This half holds it where the same mistake arrives second: in
whoever runs a suite or asks for a model recommendation.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.judge import judge_of, why_no_judge  # noqa: E402
from pact_adapters.resolve import load_catalogue, needs_of  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"

#: The command a support lead actually runs. The scoring surface is where the
#: same mistake arrives second, and it writes its own message rather than
#: reusing one — so the role it names needs holding down separately.
LAUNCHER = REPO / "scripts" / "pact-eval"

#: A row `models/catalog.yaml` serves over somebody's API and nowhere else.
HOSTED = "claude-opus-5"

#: The one catalogue row the worked example's own `needs.yaml` admits — it has
#: to be able to read the photos the cases attach. Passed explicitly so the
#: refusal under test is the egress one and not the needs one, which `_pick_model`
#: reaches first.
SEES_IMAGES = "qwen2.5-vl-7b-instruct"


def _shown(root: Path) -> dict:
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(PACT_BIN), "show", str(root)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


@pytest.fixture(scope="module")
def doc() -> dict:
    """The worked example as the loader produces it — nothing hand-built."""
    return _shown(EXAMPLE)


@pytest.fixture()
def authored(tmp_path: Path):
    """Edit the worked example's own files and load the result.

    The point of the indirection: the only thing these tests are allowed to
    change is a line an author types. Everything after that has to be the real
    loader reading the real tree, or the test proves the object works and not
    that the line reaches it.
    """

    def apply(name: str, edits: list[tuple[str, str, str]]) -> dict:
        return _shown(_edited(tmp_path, name, edits))

    return apply


def _edited(tmp_path: Path, name: str, edits: list[tuple[str, str, str]]) -> Path:
    """A copy of the worked example with `edits` applied, on disk.

    The tree itself, not the loaded document, because the scoring surface is a
    command a person runs over a folder — handing it a dictionary would test the
    object again instead of the line.
    """
    root = tmp_path / name
    shutil.copytree(EXAMPLE, root)
    for rel, before, after in edits:
        path = root / rel
        text = path.read_text()
        assert before in text, f"fixture drifted: {before!r} not in {rel}"
        path.write_text(text.replace(before, after))
    return root


# ─────────────────────────────────── the grant names the role, not everything


def test_a_grant_for_the_grader_admits_the_grader(doc) -> None:
    """AD-56 is why `judge` is a role of its own: the grader reads every eval
    case, which is strictly more than the reflector ever sees. A team that wants
    a hosted grader and nothing else hosted has one line to write — and until
    the roles were read, writing it did nothing whatsoever, because
    `why_no_judge` asked only about `llm`."""
    hosted = copy.deepcopy(doc)
    hosted["evals"]["graded-by"] = HOSTED
    hosted["allow-egress"] = ["judge"]

    assert why_no_judge(hosted, EXAMPLE) == "", (
        "`judge` is the role that names grading and it must admit the grader"
    )


def test_a_grant_for_the_words_admits_the_grader(doc) -> None:
    """And the general grant covers it, because grading is a model call over
    words. A workspace that has already decided model calls may leave is not
    asked to decide about its grader a second time — `egress.WORDS` is the rule
    that says so, and this is the one check in the Python port that reaches it.

    Mutation: delete `"judge"` from `egress.WORDS`. Red here and in the parity
    check below; every other check in the adapter suite stays green (measured:
    `3 failed, 1382 passed`, the third being the pre-existing README count
    drift). It did NOT bite before `why_no_judge` stopped passing `"llm"` beside
    `"judge"`: with that call site as it was, `WORDS = ()` — the whole table
    emptied — left every behavioural check green and only the parity check red
    (measured: `2 failed, 1383 passed`). That is the fact this test was written
    from, and the reason the fix was to the call site and not to this file.
    """
    hosted = copy.deepcopy(doc)
    hosted["evals"]["graded-by"] = HOSTED
    hosted["allow-egress"] = ["llm"]

    assert why_no_judge(hosted, EXAMPLE) == "", (
        "`llm` is the grant for words leaving the box and grading is a model "
        "call over words, so it must admit the grader without `judge` beside it"
    )


def test_both_ports_carry_the_same_words_under_a_grant_for_words() -> None:
    """The list is written twice, so something has to read both copies.

    `crates/pact-cli/src/egress.rs` holds the same rule at `pact check` time and
    keeps its own `WORDS`, because neither port can derive this one from the
    schema: `spec/schema.yaml` says which roles exist and no line in it says
    which of them a grant for words carries. Two written lists are tolerable
    only while a check fails when they disagree — the alternative is `ROLES`
    again, a copy of the specification with no gate depending on it.

    This is also what holds `embedder` and `reflector` down on the Python side:
    no caller in this port plays either role yet, and Rust reaches both through
    a learning model's `role:` line.

    Mutation: drop `"reflector"` from `egress.WORDS`. Red here, and green
    everywhere else in the adapter suite.
    """
    from pact_adapters import egress  # noqa: PLC0415

    source = (REPO / "crates" / "pact-cli" / "src" / "egress.rs").read_text()
    written = re.search(r'const WORDS: &\[&str\] = &\[(.*?)\];', source, re.S)
    assert written, (
        "`crates/pact-cli/src/egress.rs` no longer declares `const WORDS` — the "
        "Rust half of this rule moved, and this check is now reading nothing"
    )
    rust = tuple(re.findall(r'"([^"]+)"', written.group(1)))

    assert rust == egress.WORDS, (
        f"the two ports disagree about which roles a grant for words carries:\n"
        f"  crates/pact-cli/src/egress.rs: {rust}\n"
        f"  adapters/python/.../egress.py: {egress.WORDS}\n"
        f"one workspace would be admitted by `pact check` and refused by the "
        f"suite, or the other way round"
    )


def test_a_grant_for_the_improver_does_not_admit_the_grader(doc) -> None:
    """And it stops at the role it names. `reflector` is a decision about the
    model that proposes rewrites; the grader sees the eval cases, which is a
    different decision and a different line."""
    hosted = copy.deepcopy(doc)
    hosted["evals"]["graded-by"] = HOSTED
    hosted["allow-egress"] = ["reflector"]

    graded, why = judge_of(hosted, workspace=EXAMPLE)
    assert graded is None, "a grant for the improver must not bind a hosted grader"
    assert "outside the box" in why, why
    assert "add `judge` to `allow-egress:`" in why, (
        "ask for the role this binding needs, not the superset:\n" + why
    )


def test_the_refusal_quotes_the_egress_line_the_author_wrote(doc) -> None:
    """Ledger row R56, in the second language.

    The message hardcoded `allow-egress: []`, so a workspace saying otherwise
    was told its own file says something it does not — and an author who opens
    the file and sees different stops believing the checker."""
    hosted = copy.deepcopy(doc)
    hosted["evals"]["graded-by"] = HOSTED
    hosted["allow-egress"] = ["reflector", "embedder"]

    _, why = judge_of(hosted, workspace=EXAMPLE)
    assert "`allow-egress: [reflector, embedder]`" in why, (
        "quote the workspace's own line, as written:\n" + why
    )


# ──────────────────────────── a grant for the words is not a grant for a voice


def test_an_agent_that_takes_a_voice_message_is_kept_on_this_machine_by_a_grant_for_words(
    authored,
) -> None:
    """The refusal this round adds, from the author's own two lines.

    `allow-egress: [llm]` is a decision about a model call. It is not a decision
    to post a recording of a customer speaking to somebody else's API, and until
    now the two were the same line: every hosted row in the catalogue was
    offered to this agent. D16 makes audio a first-class v1 modality, and if a
    grant for words carried speech with it, `stt` and `tts` would be exactly the
    decoration this file exists to remove.

    Nothing is constructed here. Two lines change in the tree — one in
    `workspace.yaml`, one in `agent.yaml` — and the recommendation surface has
    to refuse every model this box does not serve.
    """
    document = authored(
        "voice",
        [
            ("workspace.yaml", "allow-egress: []", "allow-egress: [llm]"),
            (
                "agents/refund-desk/agent.yaml",
                "  photos: list of images",
                "  photos: list of images\n  recording: a voice message",
            ),
        ],
    )
    needs = needs_of(document, "refund-desk")
    assert needs["must-stay-on-this-machine"] is True, (
        "a grant for the words let the recording out with them"
    )
    assert needs["egress-missing"] == ("stt",), needs["egress-missing"]

    # And the refusal REFUSES. Every row this box does not serve is ruled out
    # before an eval is run — the recommendation surface has nothing off-box
    # left to offer. `satisfies` gives the first reason a row fails, which for
    # some rows is the reasoning rung this agent's `needs:` asks for, so what is
    # asserted is the outcome; the sibling test below is what proves the missing
    # `stt` is the thing causing it.
    catalogue = load_catalogue(workspace=EXAMPLE)
    hosted = [e for e in catalogue.entries if not e.served_locally]
    assert hosted, "fixture drifted: the catalogue serves every row locally"
    for entry in hosted:
        ok, _why = entry.satisfies(needs)
        assert not ok, f"{entry.name} was offered to an agent that sends a recording"


def test_the_same_agent_is_offered_a_hosted_model_once_the_recording_is_allowed_out(
    authored,
) -> None:
    """The escape hatch is one word, which is the whole point of a per-role list:
    the team decides about the recording separately from the words.

    This is also what proves the missing `stt` was what refused the rows in the
    test above rather than something else the agent's `needs:` block asks for —
    one word changes in `workspace.yaml`, and a hosted model becomes bindable
    again.
    """
    document = authored(
        "voice-allowed",
        [
            ("workspace.yaml", "allow-egress: []", "allow-egress: [llm, stt]"),
            (
                "agents/refund-desk/agent.yaml",
                "  photos: list of images",
                "  photos: list of images\n  recording: a voice message",
            ),
        ],
    )
    needs = needs_of(document, "refund-desk")
    assert needs["must-stay-on-this-machine"] is False
    assert needs["egress-missing"] == ()

    catalogue = load_catalogue(workspace=EXAMPLE)
    passing = [e for e in catalogue.entries if not e.served_locally and e.satisfies(needs)[0]]
    assert passing, (
        "one word was added to `allow-egress:` and nothing off-box became "
        "bindable, so the word was not what refused them"
    )


def test_the_command_a_support_lead_runs_names_the_role_that_is_missing_and_not_llm(
    tmp_path,
) -> None:
    """The scoring surface writes its own refusal, and it hardcoded `llm` twice.

    That was true only while `llm` was the one role anything read. An agent that
    `accepts:` a voice message, in a workspace that granted `llm` and not `stt`,
    was told its file "does not name `llm`" — while the file plainly does. That
    is ledger row R56 happening a second time in a second language: a message
    that quotes a line the author did not write is a message they stop
    believing.

    Two lines change in the tree and nothing is constructed. What is asserted is
    that the message names `stt` — the grant that is actually absent — and
    quotes `[llm]`, the grant that is actually there.
    """
    root = _edited(
        tmp_path,
        "voice-scored",
        [
            ("workspace.yaml", "allow-egress: []", "allow-egress: [llm]"),
            (
                "agents/refund-desk/agent.yaml",
                "  photos: list of images",
                "  photos: list of images\n  recording: a voice message",
            ),
        ],
    )
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    done = subprocess.run(
        [
            str(LAUNCHER), str(root),
            "--model", SEES_IMAGES,
            "--serving-at", "http://models.example.com/v1",
        ],
        capture_output=True, text=True, cwd=REPO, timeout=300,
    )
    report = done.stdout + done.stderr

    assert "scoring/egress-refused" in report, report
    assert "nothing there names `stt`" in report, (
        "name the grant that is missing, not the one that happens to be first:\n" + report
    )
    assert "`allow-egress: [llm]`" in report, (
        "quote the workspace's own line, as written — R56:\n" + report
    )
    assert "add `- stt` under `allow-egress:`" in report, (
        "the fix must be the line the author types:\n" + report
    )


def test_a_workspace_that_says_nothing_may_leave_still_keeps_everything_in(doc) -> None:
    """The floor. `examples/refund-desk` writes `allow-egress: []` and pins no
    model anywhere. Six roles are only worth having if the empty list still means
    what it said."""
    needs = needs_of(doc, "refund-desk")
    assert needs["must-stay-on-this-machine"] is True
    assert needs["egress-missing"] == ("llm",)
