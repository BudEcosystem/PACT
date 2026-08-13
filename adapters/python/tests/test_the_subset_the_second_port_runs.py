"""§7.28's list B, held against what the second port actually reports.

`README.md` says one folder produces *"byte-identical traces, tool sequences and
model-call counts"* over all seven targets. The seventh is the TypeScript port
and it honours a strict subset: eight keys — `interceptors`, `contextPolicy`,
`policy`, `teamwork`, `settings`, `slo`, `model`, `watches` — are declared on
`AgentSpec` for one purpose only, so `notDoneHere` can name them on
`RunResult.unenforced`. §7.28 of `docs/20-ARCHITECTURE-DRAFT.md` writes that
subset down; this file is the half of it that runs.

Why here and not in the Rust test beside it. The Rust half
(`crates/pact-cli/tests/the_subset_the_second_port_runs.rs`) holds README against
§7.28 against `AGENT_SPEC_FIELDS` — all three of them documents. It deliberately
does NOT grep `harness.ts` for `spec.<field>` inside `notDoneHere`, because that
check false-passes: measured, replacing `if (spec.model)` with `if (false)` left
`spec.model` in the neighbouring message and the grep went green while the report
was gone. The only honest way to hold "this port still says so" is to run it and
read `unenforced`.

List B has a ninth row on this channel that is NOT one of those keys: a loop
stage's `asks:`. It is written INSIDE `loops:`, which list A covers, so
`notDoneHere` never sees it — the block reaches this port raw and the stages only
exist once `run()` has resolved a loop. For a round the consequence was that the
line was parsed into `Phase.asks`, read by nothing, and reported by nothing, and
§7.28 ended with a paragraph *stating* that rather than closing it. A stated hole
is still a governance line dropped in silence. `run()` now appends the row after
`resolve`, and `test_a_stage_that_asks_a_person_names_the_question_it_cannot_put`
below is the half that runs.

List B has a further row that is not on this channel at all: the documents under
`knowledge/`, which land on `RunResult.unretrieved` — the fifth channel, for the
reason `never_reached` is not `unmetered`. Its positive half is held by
`test_a_corpus_the_second_port_never_looked_in_is_not_silent.py`, which runs both
ports over one corpus and compares the sentence. Held HERE is the negative half,
and it is the half this file is shaped for: the spec below now declares a corpus,
so if that sentence ever moves onto `unenforced` it arrives as a line no row of
list B accounts for and `test_the_architecture_lists_exactly_the_keys_the_run_says_it_ignores`
fails. One fact in two channels is what that test is for.

`test_portability.py::test_the_typescript_port_says_what_it_does_not_do` already
does this for three of the eight, which is how the other five stayed unheld: TS-8
records that a document carrying `first-reply-within`, `per-word-under`,
`settings:` and `model:` gave Python four named lines and Node nothing at all,
because a key no field declares vanishes in `JSON.parse`. Three of eight is the
same shape of hole one layer up.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TS_DIR = REPO / "adapters" / "typescript"
ARCH = REPO / "docs" / "20-ARCHITECTURE-DRAFT.md"

#: One authored key per row: how §7.28 spells it, what this test writes for it,
#: and what the `unenforced` line about it must begin with.
#:
#: The last column is not derivable from the first. `settings:` and `slo:` report
#: the key INSIDE them — `settings.max-tokens`, `first-reply-within` — because
#: that is the line the author would open, and `notDoneHere`'s own contract is
#: *"each entry names the author's own field"*. A row whose report began with the
#: group name would send a reader to a block instead of a line.
KEYS = (
    # (field on AgentSpec, how §7.28 spells it, the value sent, the report's start)
    ("interceptors", "`interceptors:`", ["redact-card-numbers"], "interceptors:"),
    ("contextPolicy", "`context-policy:`", "long-threads", "context-policy:"),
    ("policy", "`policy:`", "approvals", "policy:"),
    ("teamwork", "`teamwork:`", {"waits-for": "all"}, "teamwork:"),
    ("settings", "`settings.*`", {"max-tokens": 400}, "settings.max-tokens:"),
    ("slo", "`slo.*`", {"first-reply-within": "2s"}, "first-reply-within:"),
    ("model", "`model:`", "claude-haiku-4-5", "model:"),
    ("watches", "`watch/`", ["everything"], "watch:"),
)

#: A teammate, which is the one key on BOTH sides of the bound: the name is
#: offered to the model (list A — it is part of the byte-identical tool list) and
#: running one is not (list B's `teamwork:` row). Both halves are asserted, in
#: `test_a_teammate_is_offered_here_and_still_not_runnable_here`.
TEAM = {"policy-checker": "checks a decision against the written policy"}

#: A set of documents, declared and never looked in — list B's tenth row, and the
#: one reported on a channel of its own. Carried on the spec below so that the
#: stray check has something to catch: a sentence about this corpus turning up on
#: `unenforced` would be one fact filed in two channels across the two ports, and
#: would send the author to a document with nothing wrong in it.
#:
#: No `must-cite:`, deliberately. With it the turn is refused before a model call
#: — which is list A, not list B — and every other assertion in this file about
#: what the model was offered would be asserting about a run that never happened.
CORPUS = [{"name": "staff-handbook", "description": "the handbook everyone asks about"}]

#: How §7.28 list B spells that row. The folder and not the colon: `knowledge:`
#: is the declaration, whose `must-cite:` half both ports carry out identically
#: and which list A therefore names.
DOCUMENTS = "`knowledge/`"

#: How §7.28 list B spells the row that is not a top-level key. A `does:
#: ask-someone` stage names WHICH question a person is put, and that is a
#: governance line: it decides what somebody is shown and what answer is taken
#: back. Both ports stop the run in that stage; only Python puts the question.
STAGE_QUESTION = "`asks:`"

#: A loop whose first stage stops to ask a person, and names the question.
#: `approve-refund` is an entry under `questions/` — which is §7.28 list C, a
#: category this port refuses outright — so there is nothing here for the port to
#: look the name up in even if it had somewhere to put the answer.
ASKING_LOOP = {
    "loop": "review",
    "loops": {
        "review": {
            "starts-at": "check",
            "steps": {
                "check": {
                    "does": "ask-someone",
                    "asks": "approve-refund",
                    "then": {"answered": "done"},
                },
            },
        },
    },
}

#: The same question on a stage the run never enters: the loop answers at its
#: first stage and stops. Carried so the report is held to being about the
#: DOCUMENT rather than about the path — `interceptors:` is named whether or not
#: one would have fired, and a line that appeared only when the stage happened to
#: be reached would tell an author their file was fine on every run that took the
#: other branch.
UNREACHED_ASKING_LOOP = {
    "loop": "review",
    "loops": {
        "review": {
            "starts-at": "reply",
            "steps": {
                "reply": {"does": "answer", "then": {"answered": "done"}},
                "check": {
                    "does": "ask-someone",
                    "asks": "approve-refund",
                    "then": {"answered": "done"},
                },
            },
        },
    },
}


def _run(spec: dict) -> dict:
    """The second port, on the same script, over one payload."""
    out = subprocess.run(
        [
            "node",
            "--experimental-strip-types",
            "src/run-trace.ts",
            json.dumps(spec),
            json.dumps({"turns": [{"text": "done"}]}),
            "hello",
        ],
        cwd=TS_DIR,
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        pytest.skip(f"node/AI SDK unavailable: {out.stderr[-300:]}")
    return json.loads(out.stdout)


def _everything_written() -> dict:
    spec = {
        "name": "Refund Desk",
        "instructions": "Decide, then issue the refund.",
        "tools": [],
        "maxSteps": 2,
        "team": dict(TEAM),
        "knowledge": [dict(c) for c in CORPUS],
    }
    for field, _, written, _ in KEYS:
        spec[field] = written
    return spec


def _list_b() -> str:
    """The `**B — …**` part of §7.28, from its marker to the next bold line."""
    doc = ARCH.read_text(encoding="utf-8")
    at = doc.find('### 7.28 What "byte-identical across all seven targets" covers')
    assert at >= 0, (
        f"{ARCH} has no §7.28.\n"
        "  fix: add the subsection — README.md links to it, so without it the front page's "
        "scope note points at nothing."
    )
    section = doc[at:]
    end = section[1:].find("\n### ")
    section = section[: end + 1] if end >= 0 else section
    open_at = section.find("**B — ")
    assert open_at >= 0, "§7.28 has lost its list B, which is the list this file holds"
    rest = section[open_at:]
    stop = rest[1:].find("\n**")
    return rest[: stop + 1] if stop >= 0 else rest


def _named_by_a_row(part: str, written: str) -> bool:
    """Whether one of list B's TABLE ROWS names the key — not merely the letters.

    The same bar `named_by_a_row` holds in
    `crates/pact-cli/tests/the_subset_the_second_port_runs.rs`, and this file needs
    it for the same measured reason. With a plain ``written in part`` here, deleting
    the whole ``| `asks:` … |`` row from §7.28 left this file green: the paragraph
    above the table says *"a loop stage's `asks:`"* and the substring found it
    there. The Rust half caught it, so the gate as a whole still bit — but a check
    that cannot fail is not a second artifact, and the four-artifact rule is a rule
    about four artifacts that each hold.

    A sentence about a row is not a row. The row carries the mechanism letter and
    the reason the port is smaller, which are the two cells a reader sent to the
    list has come for. A row is a line beginning `|`, which is how every list in
    §7.28 is written.
    """
    return any(
        written in line for line in part.splitlines() if line.lstrip().startswith("|")
    )


# --------------------------------------------------------------- the guarantee


def test_every_key_the_architecture_calls_unenforced_is_named_by_the_run_that_ignores_it() -> None:
    """A governance line this port does not carry out is named, one at a time.

    This is the drift that would matter most and that nobody would notice: a key
    gets ported, its `notDoneHere` branch goes away because the run really does
    it now, and §7.28 goes on telling readers it does not. Or the reverse — a
    branch is dropped in a refactor and a `policy:` the author wrote is neither
    applied nor mentioned, which is the T7 breach `unenforced` exists to prevent.
    """
    said = _run(_everything_written())["unenforced"]
    assert said, "a port that carries out none of these has to say so"

    missing = []
    for field, spelling, _, starts in KEYS:
        if not any(line.startswith(starts) for line in said):
            missing.append(
                f"nothing on `unenforced` begins with {starts!r}, so {spelling} "
                f"(`spec.{field}`) is read and silently ignored"
            )
    assert not missing, (
        "adapters/typescript/src/harness.ts ran a spec carrying every key §7.28 list B names, "
        "and did not name them all:\n  "
        + "\n  ".join(missing)
        + "\n  fix: if the key is now carried out on this runtime, move its row from §7.28 "
        "list B to list A and widen the sentence in README.md beside the byte-identical "
        "claim. If it is not, restore its branch in `notDoneHere` — a runtime that silently "
        "drops a governance line is worse than one that refuses the document.\n"
        f"  what it did say:\n    " + "\n    ".join(said)
    )


def test_the_architecture_lists_exactly_the_keys_the_run_says_it_ignores() -> None:
    """The other direction: §7.28 list B must not fall behind `notDoneHere`.

    Held on the report rather than on the source, so a ninth key added to
    `notDoneHere` and left out of the architecture fails here rather than being
    discovered by a reader who trusted the list.
    """
    section = _list_b()
    for _, spelling, _, _ in KEYS:
        assert _named_by_a_row(section, spelling), (
            f"§7.28 list B has no row for {spelling}.\n"
            f"  fix: add a row `| {spelling} | the mechanism letter | why it is absent here |`"
        )
    # And the tenth row, whose report goes to a different channel and therefore
    # to a different person. Named here because list B is one list however many
    # channels carry it; asserted as a REPORT by
    # `test_a_corpus_the_second_port_never_looked_in_is_not_silent.py`.
    # And the row that is not a top-level key at all. Named in list B and NOT in
    # list A, which the Rust half asserts on both sides; here it is enough that
    # the list a reader is sent to names it in a ROW — see `_named_by_a_row` for
    # the measurement that made every check in this test a row check, and for why
    # the substring version of this one could not fail.
    assert _named_by_a_row(section, STAGE_QUESTION), (
        f"§7.28 list B has no row for {STAGE_QUESTION}.\n"
        "  fix: add a row — a `does: ask-someone` stage names which question a person is "
        "put, this port has no durable suspension to put one into, and a governance line "
        "that is read and asked of nobody is the T7 breach the whole section exists to "
        "bound. A sentence about the key in the prose above the table is not a row: the "
        "row is what carries the mechanism letter and the reason."
    )
    assert _named_by_a_row(section, DOCUMENTS), (
        f"§7.28 list B has no row for {DOCUMENTS}.\n"
        "  fix: add a row — this port looks nothing up in a declared corpus, and a run "
        "that answers out of the model's own memory and says nothing is the T7 breach "
        "the whole section exists to bound."
    )

    # A key this port reports that no row accounts for. `team:` is deliberately
    # excluded: it is the one key on both sides of the bound, and list B's
    # `teamwork:` row says so in words.
    #
    # The spec carries a corpus, so this is also where the fifth channel stays a
    # fifth: the sentence about a set of documents nobody looked in belongs on
    # `unretrieved`, and arriving here instead would be one fact in two channels
    # across the two ports and a ticket sent to an author with nothing to edit.
    said = _run(_everything_written())["unenforced"]
    accounted = tuple(starts for _, _, _, starts in KEYS) + ("team:",)
    stray = [line for line in said if not line.startswith(accounted)]
    assert not stray, (
        "this port reports a line §7.28 list B does not account for:\n  "
        + "\n  ".join(stray)
        + "\n  fix: add a row to §7.28 list B naming the author's own key, the mechanism it "
        "belongs to, and why it is absent on this runtime."
    )


def test_a_teammate_is_offered_here_and_still_not_runnable_here() -> None:
    """The row a reader is most likely to get wrong, asserted on both halves.

    `team:` is in list A — the names ARE in the tool list this port shows the
    model, which is TS-5 — and `teamwork:` is in list B, because nothing here can
    run one. So the same document is byte-identical about what the model was
    offered and honest about what would happen if it asked. Naming only one half
    would make the bound wrong in whichever direction the reader guessed.
    """
    out = _run(_everything_written())

    offered = out["offered"]
    assert offered, "the port made no model call, so nothing was offered"
    assert "policy-checker" in offered[0], (
        "the teammate was not offered to the model, so §7.28 list A's `team:` row is false.\n"
        f"  fix: the tool list for the first step was {offered[0]}; `harness.ts` must append "
        "one definition per `team:` member, as `harness.py` does — a model that is never told "
        "a teammate exists can never ask for one (TS-5)."
    )

    said = out["unenforced"]
    assert any(line.startswith("team:") for line in said), (
        "the teammate is offered and nothing says it cannot be run, so an author reads "
        "`pact check`, sees OK, and believes delegation works here.\n"
        "  fix: restore the `team:` branch in `notDoneHere`, or move `teamwork:` out of "
        "§7.28 list B because this port now delegates."
    )


def test_a_stage_that_asks_a_person_names_the_question_it_cannot_put() -> None:
    """The row `notDoneHere` cannot see, held by running the port.

    `asks:` says WHICH question a person is put — with a shape for the answer, an
    audience and a deadline, all of them in `questions/`. Both ports stop the run
    in that stage, at the same point of the same path, with `halted: "suspended"`;
    only Python then puts the question. So an author who wrote one and read this
    port's report was told the run had suspended and nothing about the question
    going nowhere.

    Measured before the fix, through this same driver:

        halted: "suspended", phases: ["check"], unenforced: []

    which is a governance line parsed (`loops.ts` fills `Phase.asks`), dropped and
    unmentioned — the T7 breach `unenforced` exists to prevent, in the port's own
    reporting mechanism. §7.28 named the hole in a closing paragraph for a round
    rather than closing it, which is why this test exists rather than a note.
    """
    spec = {
        "name": "Refund Desk",
        "instructions": "Decide, then issue the refund.",
        "tools": [],
        "maxSteps": 2,
        **ASKING_LOOP,
    }
    out = _run(spec)

    assert out["halted"] == "suspended", (
        f"the stage did not stop the run, so this test is asserting about the wrong "
        f"path: {out['halted']!r}, phases {out['phases']}"
    )
    said = out["unenforced"]
    named = [line for line in said if "approve-refund" in line]
    assert named, (
        "the run stopped in a stage that asks a person and said nothing about the "
        "question it was supposed to put.\n"
        f"  it stopped at {out['phases']} and reported {said}\n"
        "  fix: in `harness.ts`, after `resolve(spec.loops, spec.loop)`, append one line "
        "to `unenforced` for each `does: ask-someone` stage that names an `asks:` — the "
        "resolved loop is in scope there, which is the reason `notDoneHere` cannot do it. "
        "A question read and asked of nobody is worse than a document this port refused."
    )
    line = named[0]
    assert line.startswith("asks:"), (
        "the report does not begin with the author's own key, so a reader cannot tell "
        f"which line of their file to open: {line!r}"
    )
    assert "check" in line, (
        f"the report names no stage, so an author with two asking stages cannot tell "
        f"which one this is about: {line!r}"
    )

    # About the DOCUMENT, not about the path taken. A loop that answers at its
    # first stage never enters the asking one, and the line still has to appear —
    # otherwise the report is a property of this particular run and an author
    # reads "nothing unenforced" on every run that took the other branch.
    elsewhere = _run({
        "name": "Refund Desk",
        "instructions": "Decide, then issue the refund.",
        "tools": [],
        "maxSteps": 2,
        **UNREACHED_ASKING_LOOP,
    })
    assert "check" not in elsewhere["phases"], (
        f"the asking stage was entered after all, so this half asserts nothing: "
        f"{elsewhere['phases']}"
    )
    assert any("approve-refund" in line for line in elsewhere["unenforced"]), (
        "a stage that asks a person is reported only when the run happens to reach it, "
        "so the same document says two different things about itself.\n"
        f"  phases {elsewhere['phases']}, unenforced {elsewhere['unenforced']}\n"
        "  fix: report every asking stage the loop declares, as `interceptors:` is "
        "reported whether or not one would have fired."
    )

    # And the report says it in the CONDITIONAL, because on this second run the
    # stage was never entered. "the run stops in that stage" is a sentence about
    # something that did not happen, told to an author who would then go looking
    # for a stop that is not in `phases`.
    unreached = [ln for ln in elsewhere["unenforced"] if "approve-refund" in ln][0]
    assert "a run that reaches that stage stops there" in unreached, (
        "the line is reported for every declared stage and written as if this run had "
        "taken it, so on the branch that never entered the stage the report states "
        "something the run did not do.\n"
        f"  phases {elsewhere['phases']}, line {unreached!r}\n"
        "  fix: write the consequence in the conditional — a report that overstates is "
        "the same defect as one that omits."
    )

    # And the shape that most needs the line: a stage that stops to ask a person
    # and names NO question. `spec/schema.yaml` refuses that document, so no tree
    # `pact check` accepted can produce one — but `run()` is a library entry point
    # and a hand-built payload reached it and suspended with `unenforced: []`. A
    # port's own report may not depend on a validator it never runs.
    nameless = _run({
        "name": "Refund Desk",
        "instructions": "Decide, then issue the refund.",
        "tools": [],
        "maxSteps": 2,
        "loop": "review",
        "loops": {"review": {"starts-at": "check", "steps": {
            "check": {"does": "ask-someone", "then": {"answered": "done"}},
        }}},
    })
    assert nameless["halted"] == "suspended", (
        f"the nameless stage did not stop the run: {nameless['halted']!r}"
    )
    assert any(ln.startswith("asks:") for ln in nameless["unenforced"]), (
        "a stage stops the run to ask a person, names no question, and the report says "
        "nothing — which is the silence this whole channel exists to prevent, in the "
        "one case where the author has most to fix.\n"
        f"  it reported {nameless['unenforced']}\n"
        "  fix: in `harness.ts`, report the stage whether or not it carries an `asks:` — "
        "`pact check` refuses the document, and this port does not run `pact check`."
    )

    # And no other line, because the spec carries no other unenforced key. The
    # bound has to stay a bound: a report that fires on every run stops being read.
    stray = [line for line in said if not line.startswith("asks:")]
    assert not stray, f"a spec carrying only a loop was told about something else: {stray}"


def test_a_document_carrying_none_of_them_is_told_nothing() -> None:
    """A report that fires on every run stops being read.

    The bound has to be a bound and not a banner: a spec with no governance keys
    at all comes back with an empty `unenforced`, which is what makes the eight
    lines above mean something when they do appear.
    """
    quiet = _run(
        {"name": "Refund Desk", "instructions": "Decide.", "tools": [], "maxSteps": 2}
    )
    assert quiet["unenforced"] == [], (
        "a spec carrying no unenforced key was told about one anyway: "
        f"{quiet['unenforced']}"
    )
