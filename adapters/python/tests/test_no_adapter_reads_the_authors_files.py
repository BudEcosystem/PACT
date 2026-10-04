"""AC-2.3 / invariant P-1 — the run path never touches the author's tree.

> No adapter reads author files; adapter tests pass with only `canonical.json`
> present.

This is the invariant everything else in PACT leans on. A runtime is handed a
**document** — what `pact show` emits — and nothing else. If any part of the run
path reached back into the folder, then:

* the Expansion Rule would have two implementations, one in Rust and one
  accidentally in Python, and they would drift;
* a host that legitimately has only the document — a registry, a message queue,
  another machine — could not run the agent at all;
* and every portability claim in this repository would be about a tree rather
  than about a specification.

**Fourteen modules make up the run path and none of them opens a file.** That is
measured here rather than assumed, because it is the sort of thing one
`Path(...).read_text()` quietly ends.

The commands are a different matter and are named below. `scoring`, `pipeline`
and `conformance` are things a person types at a tree; reading one is their whole
job. The line P-1 draws is not "no Python touches a disk" — it is that the code
which turns a document into a run does not.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "pact_adapters"

#: The run path: everything between a document and an answer.
#:
#: Not derived from imports, on purpose. "Which modules run an agent" is a claim
#: about the design, and a list computed from the import graph would follow the
#: code wherever it went — including somewhere it should not have gone.
THE_RUN_PATH = (
    "harness", "ir", "evals", "interceptors", "context_policy", "loops",
    "delegation", "questions", "at_most_once", "facts", "limits", "slo",
    "suspension", "script", "events", "shown", "egress",
    # Moved here from COMMANDS by `test_nothing_is_excused_that_no_longer_touches
    # _a_disk`, which caught two excuses of mine being simply wrong: `judge` asks
    # a served runtime over HTTP and `providers` imports DeepEval, and NEITHER
    # opens a file. I had assumed rather than measured. On this list their
    # cleanliness is asserted instead of merely excused, which is the stronger
    # place for them to be.
    "judge", "providers",
)

#: Modules that DO touch a disk, each with the reason it is not a P-1 breach.
#: A module here is one somebody types, not one a run reaches.
COMMANDS: dict[str, str] = {
    "scoring": "the eval command. Reads the tree because a person pointed it at "
               "one, and hands the DOCUMENT to the harness",
    "conformance": "the Conformance Report, over every workspace under a path",
    "exploding": "writes a tree from a document — the inverse of loading, and "
                 "the only module here whose job is to CREATE author files",
    # Both moved here from THE_RUN_PATH the moment they gained a `main`, and this
    # check is what noticed. Their LIBRARY halves — `from_a2a_card`,
    # `to_bud_agent_record` — still touch nothing; it is the door that reads a
    # file, because a door is a thing a person points at something.
    "importing": "reads the artifact named on the command line",
    "learning": "keeps the spend and refusal ledgers in `.pact/`, which is the "
                "DERIVED area (D2) and never the author's files",
    "watches": "writes a `watch:` record to `.pact/`, same area, same reason",
    "resolve": "reads `models/catalog.yaml` — the price list, which is a fact "
               "about the machine rather than about the agent, and is why "
               "`load_catalogue` takes a workspace and `AgentSpec` does not",
    "diagnostics": "reads a source line to show it under a caret. Rendering an "
                   "error about a file is not reading the specification from it",
    "transports": "the package of framework bindings; each talks to a model",
}

#: What counts as touching a disk.
REACHES_A_DISK = {
    "open", "read_text", "read_bytes", "write_text", "write_bytes",
    "rglob", "glob", "iterdir", "listdir", "mkdir", "exists", "unlink",
}


def _filesystem_calls(module: str) -> list[str]:
    """Every call in this module that reaches a disk, as `line: name`."""
    path = SRC / f"{module}.py"
    if not path.exists():
        return []
    tree = ast.parse(path.read_text())
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = (
            node.func.attr if isinstance(node.func, ast.Attribute)
            else node.func.id if isinstance(node.func, ast.Name)
            else ""
        )
        if name in REACHES_A_DISK:
            found.append(f"{path.name}:{node.lineno}: {name}(…)")
    return found


def test_the_run_path_is_named_and_real() -> None:
    """A list naming modules that do not exist would pass everything below."""
    missing = [m for m in THE_RUN_PATH if not (SRC / f"{m}.py").exists()]
    assert not missing, f"THE_RUN_PATH names {missing}, which do not exist"
    assert len(THE_RUN_PATH) >= 14, THE_RUN_PATH


@pytest.mark.parametrize("module", sorted(THE_RUN_PATH))
def test_no_module_on_the_run_path_opens_a_file(module: str) -> None:
    """Invariant P-1, measured.

    One `Path(...).read_text()` in any of these and a runtime holding only the
    document could no longer run the agent — which is the difference between a
    specification and a folder.
    """
    reaching = _filesystem_calls(module)
    assert not reaching, (
        f"`{module}` is on the run path and touches a disk:\n  "
        + "\n  ".join(reaching)
        + f"\n\nA runtime is handed a DOCUMENT and nothing else. If it needs the "
        f"tree, either the document is missing something — add it to the loader "
        f"— or `{module}` belongs in COMMANDS with the reason."
    )


def test_every_module_that_touches_a_disk_says_why() -> None:
    """The other direction. A module that reads files and is on neither list is
    one nobody has decided about."""
    on_a_list = set(THE_RUN_PATH) | set(COMMANDS)
    everything = {
        p.stem for p in SRC.glob("*.py")
        if not p.stem.startswith("_") and p.stem != "__init__"
    }
    undecided = sorted(
        m for m in everything - on_a_list if _filesystem_calls(m)
    )
    assert not undecided, (
        f"{undecided} touch a disk and are on neither list.\n"
        f"Either they are on the run path — in which case this is a P-1 breach — "
        f"or they are a command, and COMMANDS wants the reason."
    )


def test_nothing_is_excused_that_no_longer_touches_a_disk() -> None:
    """A register that can be wrong about its own subject is what this repository
    has most of. A module in COMMANDS that stopped reading files should leave,
    because the row is now describing something that is not happening."""
    stale = sorted(
        m for m in COMMANDS
        if (SRC / f"{m}.py").exists() and not _filesystem_calls(m)
    )
    assert not stale, (
        f"{stale} are excused for reading files and no longer do — delete the rows"
    )


def test_the_two_lists_do_not_overlap() -> None:
    """A module cannot both be on the run path and be a command that reads trees.
    If it is in both, whichever a reader consults first decides what they
    believe."""
    both = sorted(set(THE_RUN_PATH) & set(COMMANDS))
    assert not both, f"{both} are on the run path AND excused as commands"


def test_a_spec_built_from_a_document_alone_runs(tmp_path: Path) -> None:
    """The behavioural half: no `source=`, no tree, no filesystem anywhere near
    it — and the agent still runs.

    Every other test in this suite hands `AgentSpec.from_document` a `source=`
    for the workspace-shaped things that need one. This one deliberately does
    not, because a host with only the document is the case P-1 exists for.
    """
    import asyncio
    import json

    sys.path.insert(0, str(SRC.parent))
    from pact_adapters.harness import run
    from pact_adapters.ir import AgentSpec
    from pact_adapters.script import Script, Turn
    from pact_adapters.transports.mock import ReferenceTransport

    # A document, as JSON, as it would arrive over a queue. Not read from a tree.
    document = json.loads(json.dumps({
        "name": "somewhere-else",
        "agents": {
            "desk": {
                "name": "Desk",
                "description": "Answers questions.",
                "instructions": "Answer the question.",
                "answers-with": {"decision": "one of yes, no"},
            }
        },
    }))
    spec = AgentSpec.from_document(document, "desk")
    out = asyncio.run(
        run(spec, ReferenceTransport(Script([Turn("yes")])), "is this ok?")
    )
    assert out.halted == "final", out.halted
    assert out.output == "yes"
    # And the authored answer shape reached the model without a tree in sight.
    assert spec.answers_with == {"decision": "one of yes, no"}
