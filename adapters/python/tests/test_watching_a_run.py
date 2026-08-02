"""Watching a run is an author's power, not a host's.

`interceptors:` — the half that CHANGES things — has been authorable in YAML for
several rounds. The half that only LOOKS had no authoring surface at all:
`Bus.on(pattern, fn)` takes a Python callable, so watching a run was a HOST
capability. That is the wrong way round twice over — observing is the strictly
safer power, and it is the one D14 ("no capability may require author code")
could not reach.

Every test here goes through the AUTHORED path: the worked example is loaded by
the real Rust loader, `AgentSpec.from_document` resolves it, and `run()` is given
nothing. A test that built a `Watches` object itself would prove the object works
and say nothing about whether `examples/refund-desk/watch/tool-calls.yaml`
reaches the run — which is the exact defect this project has shipped five rounds
running.

The four edits this file was written against have landed: the document moved out
of staging to `examples/refund-desk/watch/tool-calls.yaml`, the `watch` group is
in `spec/schema.yaml`, `AgentSpec.watches` is in `ir.py`, and `run()` calls
`spec.watches.subscribe(bus, spec.workspace)`. Each failure message below still
names the one piece that would be missing if a later change undid it, which is
more use to whoever reads it than a bare assertion would be.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.events import Address, Bus  # noqa: E402
from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402
from pact_adapters.watches import (  # noqa: E402
    EMITTED, RECORDED, UNDER, WatchError, Watches,
)

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"

#: The agent whose runs the workspace's watch records. Named once: nothing in
#: `agents/refund-desk/` points at the watch, and that is the point — see
#: `test_a_watch_needs_no_line_in_any_agent_file_to_take_effect`.
AGENT = "refund-desk"

#: A card number in the customer's own words, and again in what a tool hands
#: back. The worked example's interceptors hide it on the way to the model and on
#: the way into `payments`; a watch that wrote payloads out verbatim would be a
#: way to undo both from a document nobody had to approve.
CARD = "4111 1111 1111 1111"

TOOLS = {
    "zendesk": lambda a: f"lamp, broken, paid with card {CARD}",
    "payments": lambda a: "refunded",
}


# ─────────────────────────────────────────────────────────────────── fixtures


def _loaded(tree: Path) -> dict[str, Any]:
    """`pact show` on a tree — the same door every other adapter test uses.

    Invariant P-1: a Python re-implementation of the Expansion Rule would be a
    second loader and the two would drift.
    """
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(PACT_BIN), "show", str(tree)], capture_output=True, text=True
    )
    assert out.returncode == 0, (
        f"`pact show {tree}` failed. If it says \"'watch' is not something a "
        f"workspace can have\", the `watch` group from this round's "
        f"`needs_wiring` has not been added to spec/schema.yaml yet.\n"
        f"{out.stdout}{out.stderr}"
    )
    return json.loads(out.stdout)


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """A clean copy of the worked example, so a run may write its record.

    Copied rather than used in place because a watch WRITES: running the real
    `examples/refund-desk` would leave a `.pact/` behind in the repository.

    `.pact/` is dropped from the copy on the way, because other tests in this
    suite hand `AgentSpec.from_document` the real example directory and their
    runs leave a record there. Inheriting it would make "the record has one line"
    depend on which tests ran first — and a derived directory being ignorable is
    the whole reason the record lives in one (D2: deleting `.pact/` is harmless).
    """
    copy = tmp_path / "refund-desk"
    shutil.copytree(EXAMPLE, copy, ignore=shutil.ignore_patterns(".pact"))
    return copy


@pytest.fixture()
def desk(workspace: Path) -> AgentSpec:
    doc = _loaded(workspace)
    assert doc.get("watch"), (
        "the worked example declares no watch — expected "
        "examples/refund-desk/watch/tool-calls.yaml to load"
    )
    spec = AgentSpec.from_document(doc, AGENT, workspace)
    assert hasattr(spec, "watches"), (
        "AgentSpec has no `watches` field — apply the ir.py edit from this "
        "round's needs_wiring"
    )
    return spec


def _run(desk: AgentSpec, said: str = "please refund order A-1182"):
    script = Script([
        Turn("checking the ticket", (ToolCall("zendesk", {"id": "A-1182"}),)),
        Turn("approved"),
    ])
    return asyncio.run(run(desk, ReferenceTransport(script), said, TOOLS))


def _record(workspace: Path, name: str = "tool-calls.jsonl") -> list[dict[str, Any]]:
    path = workspace / UNDER / name
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ───────────────────────────────────────────────── the bar the gap itself sets


def test_an_authored_watch_receives_the_moment_it_names_for_a_run_of_the_worked_example(
    workspace: Path, desk: AgentSpec
) -> None:
    """§7.13's gap (1), closed, in the exact terms it names it.

    `examples/refund-desk/watch/tool-calls.yaml` says `when: step.tool.completed`
    and `writes-to: tool-calls.jsonl`. Nothing is passed to `run()` — no bus, no
    observer, no callable — and the record has to be there afterwards. Before
    this, the only way to see a `step.tool.completed` was for a host to write
    `bus.on("step.tool", fn)` in Python.
    """
    result = _run(desk)

    lines = _record(workspace)
    assert lines, (
        "the authored watch wrote nothing. If `AgentSpec.watches` exists but no "
        "record appeared, the `spec.watches.subscribe(bus, spec.workspace)` line "
        "is missing from harness.py — that is the reading line."
    )
    assert [line["happened"] for line in lines] == ["step.tool.completed"]
    assert lines[0]["name"] == "zendesk", lines[0]
    assert result.unwatched == (), result.unwatched


def test_a_workspace_with_no_watch_document_records_nothing_at_all(
    workspace: Path
) -> None:
    """The control for the test above: the author's FILE is what caused it.

    Without this, a record appearing proves only that something writes records.
    A run with no watch has to be byte-identical to one from before the mechanism
    existed — which is the same standard §7.13 sets for the bus itself.
    """
    shutil.rmtree(workspace / "watch")
    doc = _loaded(workspace)
    assert not doc.get("watch")
    _run(AgentSpec.from_document(doc, AGENT, workspace))
    assert not (workspace / ".pact").exists(), "a workspace that asked for nothing got something"


def test_a_watch_needs_no_line_in_any_agent_file_to_take_effect(
    workspace: Path, desk: AgentSpec
) -> None:
    """A watch is the WORKSPACE's, not one agent's — and that is why it is safe.

    An interceptor changes one agent's behaviour, so that agent names it in its
    own `interceptors:` line. A watch changes nothing, so naming it twice would
    buy nothing and would let an agent quietly stop being watched by deleting one
    line. The assertion is that no agent file mentions it and it fires anyway.
    """
    doc = _loaded(workspace)
    for name, agent in (doc.get("agents") or {}).items():
        assert "watch" not in agent, f"agent {name!r} names a watch; it should not have to"
    _run(desk)
    assert _record(workspace), "the workspace's watch did not reach the agent's run"


# ───────────────────────────────────────── what a line may carry, and may not


def test_a_watch_writes_down_that_a_tool_ran_and_never_what_was_handed_to_it(
    workspace: Path, desk: AgentSpec
) -> None:
    """The reason this power needs nobody's approval.

    The worked example hides card numbers before they reach the model and before
    they reach `payments`. A watch that wrote payloads out verbatim would undo
    both from a document that needed no review — so a line carries names, moments
    and outcomes and there is no spelling of "write the values down too".
    """
    _run(desk, f"please refund card {CARD} for order A-1182")

    raw = (workspace / UNDER / "tool-calls.jsonl").read_text()
    assert "step.tool.completed" in raw
    assert "4111" not in raw, f"a watch wrote down a card number:\n{raw}"
    for leaks in ("text", "input", "args", "content"):
        assert leaks not in json.loads(raw.splitlines()[0])


def test_the_fields_a_line_may_carry_are_names_and_moments_and_never_words() -> None:
    """`RECORDED` is an allow-list, so the next `bus.emit` keyword is absent from
    every record until somebody adds it here on purpose. A deny-list would fail
    the other way: `session.run.started` carries `input=` and
    `step.model.completed` carries `text=`, and forgetting either would put the
    customer's message and the model's answer in a file nobody had to approve."""
    for words in ("text", "input", "content", "args", "answered", "did", "notes"):
        assert words not in RECORDED, f"{words!r} carries somebody's words"


# ───────────────────────────────────── mistakes an author makes writing one


def _watch(**fields: Any) -> dict[str, Any]:
    return {"watch": {"slow-tools": fields}}


def test_a_moment_no_run_ever_reaches_is_refused_with_the_moments_that_exist() -> None:
    """`session.tool.completed` is a well-formed address and nothing emits it.

    The address vocabulary alone cannot catch this — every one of the three words
    is legal. Left to load, the author gets a file that validates, a run that
    proceeds, and no record ever, which is the "loads and does nothing" failure
    this project keeps shipping. It is worse here than for an interceptor: there
    the author is merely not protected; here they are told nothing at all.
    """
    with pytest.raises(WatchError) as e:
        Watches.from_document(
            _watch(when="session.tool.completed", **{"writes-to": "x.jsonl"})
        )
    said = str(e.value)
    assert "nothing in a run ever reaches" in said, said
    assert "step.tool.completed" in said, f"the fix must list the moments that exist: {said}"
    assert "step.tool.started" in said and "step.tool.cancelled" in said, said


def test_a_moment_that_is_not_an_address_at_all_is_refused_by_name() -> None:
    """The same three closed lists `interceptor.when` holds — one copy, reached
    from both halves. `turn.answer.after` is the address the schema's own help
    text offered for a round, and it does not exist."""
    with pytest.raises(WatchError) as e:
        Watches.from_document(_watch(when="turn.answer.after", **{"writes-to": "x.jsonl"}))
    assert "'answer' is not something that happens" in str(e.value), str(e.value)


def test_a_destination_that_climbs_out_of_the_workspace_is_refused_with_the_name_to_type() -> None:
    """A watch is a WRITE, and the only structural defence against an arbitrary
    one is that there is no spelling for it. Same shape as `if-nobody-answers`
    having no word for "approve": prevented by there being nowhere to write it,
    not by a check somebody could forget."""
    for bad in ("../../../etc/passwd", "/etc/passwd", "reports/tool-calls.jsonl"):
        with pytest.raises(WatchError) as e:
            Watches.from_document(
                _watch(when="step.tool.completed", **{"writes-to": bad})
            )
        said = str(e.value)
        assert "just a file " in said, said
        assert "Fix: write `writes-to: " in said, f"[{bad}] no name offered: {said}"
        assert ".." not in said.split("Fix:")[1], f"[{bad}] the fix offered a way out: {said}"


def test_a_watch_missing_its_moment_or_its_destination_is_told_which_line_to_add() -> None:
    for fields, expect in [
        ({"writes-to": "x.jsonl"}, "when: step.tool.completed"),
        ({"when": "step.tool.completed"}, "writes-to: slow-tools.jsonl"),
    ]:
        with pytest.raises(WatchError) as e:
            Watches.from_document(_watch(**fields))
        assert expect in str(e.value), str(e.value)


def test_every_refusal_names_a_file_and_a_line_and_something_to_type(
    workspace: Path
) -> None:
    """The project's own rule, with no exceptions: file, line, what is wrong, and
    a fix the author can type. Held against a real tree, so the line comes from
    the file on disk rather than from a path built out of the entry's name."""
    # Loaded FIRST, from the clean tree, and the bad entry put in by hand,
    # because `pact check` refuses this address and `pact show` now runs
    # the same validation — a tree the checker refuses is no longer served as
    # valid interop output. The file on disk still carries the line, which is
    # what `_locate` reads, so the guarantee under test is unchanged: this
    # module is the SECOND line of defence, for a document handed straight to
    # the harness or built in memory by a runtime.
    doc = _loaded(workspace)
    (workspace / "watch" / "slow-tools.yaml").write_text(
        "description: Anything slow.\n\nwhen: session.tool.completed\n\n"
        "writes-to: slow-tools.jsonl\n"
    )
    doc.setdefault("watch", {})["slow-tools"] = {
        "description": "Anything slow.",
        "when": "session.tool.completed",
        "writes-to": "slow-tools.jsonl",
    }
    with pytest.raises(WatchError) as e:
        Watches.from_document(doc, workspace)
    said = str(e.value)
    assert "watch/slow-tools.yaml:3" in said, said
    assert "Fix: " in said, said


# ─────────────────────────────────────────────── the mechanism's own hygiene


def test_every_address_a_watch_may_name_is_one_the_harness_really_emits() -> None:
    """`EMITTED` is a list in one module about behaviour in another, so it is
    held against the source rather than trusted. §7.13 publishes the same thirty
    as a table; a row that drifts turns "nothing ever reaches this" into a
    refusal of something that does happen."""
    import re

    found: set[str] = set()
    for path in (REPO / "adapters/python/src/pact_adapters").rglob("*.py"):
        for m in re.finditer(r'bus\.emit\(\s*"([^"]+)"', path.read_text()):
            found.add(m.group(1))
    assert found == set(EMITTED), (
        f"emitted but not listed: {sorted(found - set(EMITTED))}; "
        f"listed but never emitted: {sorted(set(EMITTED) - found)}"
    )
    for address in EMITTED:
        Address.parse(address)


def test_a_thing_of_the_authors_own_is_allowed_because_the_host_emits_it() -> None:
    """`x-` subjects are the author's, emitted by whatever the host wired up, so
    this module has no list to hold them against and refusing would be a guess.
    The `x-` escape exists in the address vocabulary; a check that ignored it
    would close it."""
    watches = Watches.from_document(
        _watch(when="step.x-retrieval.completed", **{"writes-to": "retrieval.jsonl"})
    )
    assert len(watches) == 1


def test_the_same_watch_reaching_a_delegates_run_writes_each_line_once(
    workspace: Path, desk: AgentSpec
) -> None:
    """A delegate's run is handed the PARENT's bus and builds its own `AgentSpec`
    from the same document, so its watches are the same workspace-level watches.
    Attached twice, the record would say two tool calls happened where one did —
    and a record that overcounts is worse than none, because it is believed."""
    bus = Bus()
    desk.watches.subscribe(bus, workspace)
    desk.watches.subscribe(bus, workspace)
    bus.emit("step.tool.completed", at=(0,), name="zendesk")
    assert len(_record(workspace)) == 1


def test_a_watch_with_nowhere_to_write_is_named_on_the_result_rather_than_dropped(
    workspace: Path
) -> None:
    """An adapter may be handed a loaded document without its tree (P-1), and
    then a watch has no workspace to write into. Reported through the same door
    `unmetered` uses and for the same reason: an author who wrote a watch and got
    neither a record nor a word about it has been told something untrue (T7)."""
    spec = AgentSpec.from_document(_loaded(workspace), AGENT)  # no tree
    result = _run(spec)
    assert result.unwatched == ("tool-calls",), result.unwatched
    assert not (workspace / ".pact").exists()


def test_a_workspace_that_has_been_watched_still_passes_pact_check(
    workspace: Path, desk: AgentSpec
) -> None:
    """The record goes under `.pact/`, which the loader skips because it begins
    with a dot. Written to `reports/` instead, the next `pact check` would say
    "'reports' is not something a workspace can have" — a mistake the author did
    not make and could not act on."""
    _run(desk)
    assert (workspace / UNDER / "tool-calls.jsonl").exists()
    out = subprocess.run(
        [str(PACT_BIN), "check", str(workspace)], capture_output=True, text=True
    )
    assert out.returncode == 0, out.stdout + out.stderr
