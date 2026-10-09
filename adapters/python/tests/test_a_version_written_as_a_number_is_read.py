"""A stage's `version:` written as a number is read as the version it names.

`version:` is text (02W §2.3: `latest`, a version number, or a binding to a
date), and YAML reads `version: 2` as the number 2. The reader took only text,
so a call pinned to version 2 arrived as a call with no version at all, and a
runtime ran `latest`: the pin the author wrote, gone in silence.

Over `tests/trees/a-workflow-that-calls-and-answers/`, with a flow beside it
that calls `order-status` at a version.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters.ir import WorkflowSpec  # noqa: E402
from trees import REPO, shown  # noqa: E402

TREE = REPO / "tests/trees/a-workflow-that-calls-and-answers"
PINNED = """description: Asks a pinned version of the order look-up.
accepts:
  order-number: text
answers-with:
  status: text
starts-at: ask
steps:
  ask:
    does: call
    call: order-status
    version: {version}
    bind:
      order-number: input.order-number
    then:
      answered: reply
  reply:
    does: answer
    bind:
      status: steps.ask.status
"""


@pytest.mark.parametrize(("written", "read"), [("2", "2"), ('"2"', "2"), ("latest", "latest")])
def test_a_version_is_read_as_written(tmp_path: Path, written: str, read: str) -> None:
    root = tmp_path / "tree"
    shutil.copytree(TREE, root)
    (root / "workflows/pinned.yaml").write_text(PINNED.format(version=written))
    spec = WorkflowSpec.from_workflow(shown(root), "pinned")
    (ask,) = [s for s in spec.steps if s.name == "ask"]
    assert ask.version == read
