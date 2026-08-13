"""Phase 1.2 — every key `pact show` emits is consumed, or delegated on purpose.

The `pact show` → `AgentSpec.from_document` boundary had **no completeness
check**. A field could be emitted by the Rust loader, sit in the JSON, and be
dropped by `ir.py` with nothing anywhere comparing the two — which is how
`remembers:`, `run-inputs:`, `ports:` and `variants:` each came to be authored,
validated, emitted and read by nobody.

`test_every_field_has_a_reader.py` greps the source for a field NAME, and
`test_a_reader_is_reachable_from_a_run.py` walks the call graph to a reader. Both
start from the schema. This one starts from **what the loader actually emitted for
a real workspace**, which is the only view that knows what an author's tree
produces rather than what the format permits.

The two directions:

* a key in the JSON that `from_document` does not consume must be **named** below
  with what does consume it instead, or with why nothing should;
* a name below that the loader no longer emits must be **deleted**, because a
  register that can be wrong about its own subject is what this whole round is
  about.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import fields as dataclass_fields
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.ir import AgentSpec  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"
IR = REPO / "adapters/python/src/pact_adapters/ir.py"

#: Agent-level keys `AgentSpec.from_document` does not read, and who reads them.
#:
#: Every entry is a DECISION with a named consumer. "Nothing reads it" is not an
#: allowed reason — that is the defect, and it belongs in `KNOWN_GAPS` in
#: `test_every_field_has_a_reader.py` where the only-shrinks rule applies.
CONSUMED_ELSEWHERE: dict[str, str] = {
    "needs": "`resolve.needs_of` — model admissibility, at resolve time, not "
             "run time. An adapter that filtered the catalogue would need the "
             "workspace, which invariant P-1 says it never sees",
    "variants": "`resolve.strategies_of` — the portability strategies, read by "
                "the resolver for the same reason as `needs:`",
    "evals": "`evals.Case.from_document` and `evals.bar_of` — the suite grades "
             "a run; it is not something a run carries",
    "accepts": "`egress.py` — the input shapes decide whether binding an `stt` "
               "role leaves the workspace, which is a check and not a run",
}

#: Workspace-level keys. `AgentSpec` is ONE AGENT, so most of these are read by
#: something else per-mechanism, keyed by the name the agent's own line gives.
WORKSPACE_KEYS: dict[str, str] = {
    "agents": "the map this spec is built from",
    "name": "`AgentSpec.workspace_name`",
    "description": "the workspace's own line; an agent carries its own",
    "workspace-id": "`facts.py` — the identity evidence is kept under",
    "owner": "governance metadata; no run reads it, and none should",
    "allow-egress": "`egress.py` — whether binding a role leaves this machine",
    "loops": "`Loop.from_document`, keyed by the agent's `loop:`",
    "policies": "`Gate.of` via `questions.py`, keyed by the agent's `policy:`",
    "questions": "`questions.questions_for` — the wording for each park",
    "context-policies": "`ContextPolicy.from_document`, keyed by `context-policy:`",
    "interceptors": "`interceptors.from_document`, keyed by the agent's list",
    "tools": "`ToolSpec` — the definitions the agent's `uses:` names",
    "skills": "`SkillSpec` — the written procedures `uses:` names",
    "resources": "`ToolSpec.reaches` and `egress.py` — where a tool connects",
    "redaction": "`interceptors.py` — the workspace floor under an agent's rules",
    "watch": "`events.py` / `Watches` — what a run records",
    "learning": "`learning.Permissions.from_document` — the improvement gate",
    "evals": "`evals.py` — the suite",
    "ports": "DELEGATED to the host: a port is a way IN to a run (a schedule, an "
             "inbound call), so nothing inside a run reads one. `pact waits` "
             "publishes the schedule for whatever drives it",
}


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(PACT_BIN), "show", str(EXAMPLE)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


class _Watched(dict):
    """A mapping that records which of its keys anybody looked up.

    **Recorded rather than parsed.** The first version of this file walked the AST
    of `AgentSpec.from_document` for string literals, and reported `remembers`,
    `interceptors`, `policy` and `teamwork` as unread — because each is read by a
    HELPER it calls (`Facts.from_document`, `interceptors.from_document`, …) and
    the literal lives there. A parse that stops at one function answers a question
    nobody asked.

    Watching the real load answers the right one — *did the thing that turns a
    document into a run look this key up* — and it follows every helper for free.
    """

    def __init__(self, inner: dict, seen: set[str]) -> None:
        super().__init__(inner)
        self._seen = seen

    def __getitem__(self, key: Any) -> Any:
        self._seen.add(str(key))
        return super().__getitem__(key)

    def get(self, key: Any, default: Any = None) -> Any:
        self._seen.add(str(key))
        return super().get(key, default)

    def __contains__(self, key: Any) -> bool:
        self._seen.add(str(key))
        return super().__contains__(key)


def _keys_a_load_reads(document: dict, agent: str) -> set[str]:
    """Which of the agent's own keys a real `from_document` touches."""
    seen: set[str] = set()
    doc = json.loads(json.dumps(document))          # a copy, so nothing is shared
    doc["agents"][agent] = _Watched(doc["agents"][agent], seen)
    AgentSpec.from_document(doc, agent, source=EXAMPLE)
    return seen


def test_the_recording_sees_something_or_this_file_proves_nothing(
    document: dict,
) -> None:
    seen = _keys_a_load_reads(document, "refund-desk")
    assert len(seen) > 10, f"the load touched only {sorted(seen)}"
    for certain in ("instructions", "uses", "team", "limits", "remembers"):
        assert certain in seen, (
            f"`{certain}` is read on the authored path and the recording missed "
            f"it — the watcher is not in place"
        )


def test_every_agent_key_the_loader_emits_is_consumed_or_named(document: dict) -> None:
    """The check that would have caught `remembers:` the day the loader emitted it.

    Not "does the schema define a reader" but "does the thing that turns a
    document into a run actually look this key up". Four mechanisms shipped
    authored, validated, emitted and inert because nothing asked.
    """
    consumed: set[str] = set()
    emitted: set[str] = set()
    for name, agent in document["agents"].items():
        consumed |= _keys_a_load_reads(document, name)
        emitted |= set(agent)

    unaccounted = sorted(emitted - consumed - set(CONSUMED_ELSEWHERE))
    assert not unaccounted, (
        f"`pact show` emits {unaccounted} on an agent, and `AgentSpec.from_document` "
        f"does not read them.\n"
        f"Either read them, or add each to CONSUMED_ELSEWHERE with the function "
        f"that does. 'Nothing reads it' is not an allowed entry — that is the "
        f"defect, and it belongs in KNOWN_GAPS in "
        f"test_every_field_has_a_reader.py where the only-shrinks rule applies."
    )


def test_every_workspace_key_the_loader_emits_is_accounted_for(document: dict) -> None:
    """The same question one level up. `ports:` — ten fields, zero adapter readers —
    is the one that needed an explicit answer rather than an absence."""
    unaccounted = sorted(set(document) - set(WORKSPACE_KEYS))
    assert not unaccounted, (
        f"`pact show` emits {unaccounted} at the top level and nothing here says "
        f"who reads them. Add each to WORKSPACE_KEYS with its consumer."
    )


def test_nothing_is_excused_that_the_loader_no_longer_emits(document: dict) -> None:
    """Both registers, held to their own subject.

    A row for a key that no longer exists describes a boundary that has moved,
    and this repository's characteristic failure is a document that is confidently
    wrong about the code.
    """
    agent_keys: set[str] = set()
    for agent in document["agents"].values():
        agent_keys |= set(agent)

    ghost_agents = sorted(set(CONSUMED_ELSEWHERE) - agent_keys)
    assert not ghost_agents, f"excused but not emitted on any agent: {ghost_agents}"

    ghost_workspace = sorted(set(WORKSPACE_KEYS) - set(document) - {"name", "description"})
    assert not ghost_workspace, f"excused but not emitted at the top: {ghost_workspace}"


def test_every_spec_field_that_holds_authored_state_is_filled_from_the_document(
    document: dict,
) -> None:
    """The other side of the same boundary: a field on `AgentSpec` that no load
    ever fills.

    `facts` was exactly this — a field with a default, never assigned in
    `from_document`, so the mechanism behind it was inert while `AgentSpec` looked
    complete. Checked against the real worked example, whose agent uses every
    mechanism the example ships.
    """
    spec = AgentSpec.from_document(document, "refund-desk", source=EXAMPLE)
    #: Fields no document fills, each because the host or the run supplies it.
    from_the_host = {
        "workspace",        # where the tree was loaded from
        "skills",           # built from `uses:` against the workspace's `skills:`
        "tools",            # same, against `tools:`
        "request_keys",     # derived from the tools' `same-request-key:`
        "chain",            # built from the workspace's `interceptors:`
        "asking",           # built from the workspace's `policies:`
        "model_for_checking",   # authored, and empty in this example
        "answers_with_mode",    # authored, and empty in this example
        "settings",         # authored, and this example writes none
        "pauses",           # authored, and this example writes none
        # Authored, and this example writes none — deliberately. The D14 core is
        # at its bound of 26 files and `knowledge/` is counted by neither that
        # ceiling nor the showcase one, so putting a corpus here would be growth
        # in a directory nobody counts, which is the defect both of those
        # comments exist to prevent. The construct is demonstrated whole in
        # `examples/answers-from-documents/`, which is checked by the gate.
        "knowledge",
        # Authored and deliberately absent: the example pins no `model:`, which is
        # how it binds a locally-served row rather than naming one. `_bind` decides.
        "model",
        # NOT authored at all, and no document can fill it: this is what an MCP
        # server said about its own tools, which arrives over a live connection
        # on the host's machine AFTER `pact check` has finished. That is the
        # whole of AD-71 — the text is not in the tree a reviewer read, so it is
        # quarantined rather than trusted, and a run that has connected to
        # nothing carries `()`. Every run in this repository is in that state,
        # which is why the worked example leaves it empty and always will.
        "external_prose",
    }
    empty: list[str] = []
    for f in dataclass_fields(spec):
        if f.name in from_the_host:
            continue
        value = getattr(spec, f.name)
        if value in (None, "", (), {}, [], 0):
            empty.append(f.name)
    assert not empty, (
        f"{empty} are empty after loading the worked example, which uses every "
        f"mechanism it ships. Either the document does not reach them — which is "
        f"the `facts` defect again — or they belong in `from_the_host` with the "
        f"reason no document fills them."
    )
