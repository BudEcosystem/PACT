"""An agent is read with the workspace's own `remembers:` beside its own.

`workspace.remembers:` is "named memory any agent or workflow here may read as
`remembers.<name>`, written only by the stock actions `bud/remember` and
`bud/forget`". A workflow was read with it (`WorkflowSpec.workspace_remembers`);
an agent was read with its own entries alone, so a runtime handed `AgentSpec`
had no way to know what the workspace remembers. It is kept apart from
`facts`, because the agent's own `remember` writes only those.

The tree is `tests/trees/an-agent-that-reads-the-workspace-memory/`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters.ir import AgentSpec  # noqa: E402
from trees import REPO, shown  # noqa: E402

TREE = REPO / "tests/trees/an-agent-that-reads-the-workspace-memory"


def test_an_agent_is_read_with_the_workspace_memory_kept_apart_from_its_own() -> None:
    spec = AgentSpec.from_document(shown(TREE), "desk", TREE)
    assert set(spec.facts.declared) == {"last-order-seen"}
    assert set(spec.workspace_remembers.declared) == {"house-style"}
    style = spec.workspace_remembers.declared["house-style"]
    assert (style.lasts, style.starts_as) == ("forever", "plain and brief")
