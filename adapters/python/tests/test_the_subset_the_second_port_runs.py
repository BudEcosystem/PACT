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
        assert spelling in section, (
            f"§7.28 list B has no row for {spelling}.\n"
            f"  fix: add a row `| {spelling} | the mechanism letter | why it is absent here |`"
        )

    # A key this port reports that no row accounts for. `team:` is deliberately
    # excluded: it is the one key on both sides of the bound, and list B's
    # `teamwork:` row says so in words.
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
