"""What an agent is offered, and what it can be sent — the lines a runtime needs
on the far side of `ir` to honour `available-when:`, `reads-only:`, `accepts:`,
a skill's `references/` and `assets/`, and a resource's credential reference.

Each was loaded, checked and dropped at this boundary: `pact show` emitted them
and `AgentSpec` carried none, so a runtime could only honour them by reading the
document again (P-1). Held end to end through the real loader:

* `available-when:` on a tool, a skill and a resource is carried, and
  `ir.available` decides it from the agent's own reach, by the schema's own
  `satisfied-by:` table — which `AVAILABLE_WHEN` is pinned to row for row;
* `reads-only:` is carried per action through the checker's word list;
* `accepts:` is carried with its shapes, every one readable by `Shape.parse`;
* a skill's `references/` and `assets/` files are carried by name, with where
  they sit;
* `auth.by-reference:` reaches the resource, never a secret.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.ir import AVAILABLE_WHEN, AgentSpec, available  # noqa: E402
from pact_adapters.questions import Shape  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
PACT_BIN = REPO / "target" / "debug" / "pact"

FILES = {
    "workspace.yaml": "name: offered\nallow-egress: []\n",
    "agents/desk/agent.yaml": (
        "description: helps\ninstructions: Help.\nuses: [tickets, handover, house-style]\n"
        "accepts:\n  message: text\n  photos: list of images\n  voice: a voice message\n"
        "  contract: a file\n"
    ),
    "agents/helper/agent.yaml": "description: helps the desk\ninstructions: Help.\n",
    # Reaches one place, by `url:`: no connection, no procedure, nobody to ask.
    "agents/caller/agent.yaml": "description: calls out\ninstructions: Call.\nuses: [lookup]\n",
    # Its one action waits for a person, so a person can be asked.
    "agents/payer/agent.yaml": "description: pays\ninstructions: Pay.\nuses: [refunds]\n",
    "tools/lookup.yaml": (
        "description: Looks a postcode up.\nurl: host/lookup\nmethod: get\nactions:\n"
        "  find:\n    takes:\n      postcode: text\n    reads-only: yes\n"
    ),
    "tools/refunds.yaml": (
        "description: Pays refunds.\nconnect: ticket-server\nactions:\n"
        "  pay:\n    takes:\n      ticket-id: text\n    needs-a-person: yes\n"
    ),
    "agents/lead/agent.yaml": (
        "description: leads\ninstructions: Lead.\nuses: [tickets, handover, house-style]\n"
        "team:\n  helper: helps with anything\n"
    ),
    "tools/tickets.yaml": (
        "description: The ticket system.\nconnect: ticket-server\nactions:\n"
        "  read-ticket:\n    takes:\n      ticket-id: text\n    reads-only: yes\n"
        "  close-ticket:\n    takes:\n      ticket-id: text\n"
    ),
    "tools/handover.yaml": (
        "description: Hands work to a teammate.\navailable-when: this-agent-has-helpers\n"
        "url: host/handover\nmethod: post\nactions:\n  hand-over:\n    takes:\n      task: text\n"
    ),
    "resources/ticket-server.yaml": (
        "resource-kind: mcp-server\nendpoint: host/tickets\nauth:\n  by-reference: host/tickets-credential\n"
        "available-when: a-person-can-be-asked\n"
    ),
    "skills/house-style/SKILL.md": (
        "---\ndescription: How we write.\navailable-when: this-agent-has-connections\n---\n\nShort sentences.\n"
    ),
    "skills/house-style/references/tone.md": "# Tone\n\nPlain words.\n",
    "skills/house-style/assets/logo.png": "not really a png",
}


def _tree(root: Path) -> Path:
    for name, text in FILES.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    return root


def _pact(*args: str) -> subprocess.CompletedProcess[str]:
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    return subprocess.run([str(PACT_BIN), *args], capture_output=True, text=True)


def _specs(tmp_path: Path) -> dict[str, AgentSpec]:
    root = _tree(tmp_path / "w")
    checked = _pact("check", str(root))
    assert checked.returncode == 0, checked.stdout + checked.stderr
    doc = json.loads(_pact("show", str(root)).stdout)
    return {name: AgentSpec.from_document(doc, name) for name in ("desk", "lead", "caller", "payer")}


def test_the_conditions_are_the_schemas_own_table() -> None:
    groups = yaml.safe_load((REPO / "spec" / "schema.yaml").read_text())["groups"]
    for kind in ("tool", "skill", "resource"):
        field = groups[kind]["fields"]["available-when"]
        assert field["satisfied-by"] == dict(AVAILABLE_WHEN), kind
        assert set(field["choices"]) == {"always", *AVAILABLE_WHEN}, kind


def test_available_when_is_carried_and_decided_by_the_agents_own_reach(tmp_path: Path) -> None:
    specs = _specs(tmp_path)
    desk, lead = specs["desk"], specs["lead"]
    tools = {t.name: t for t in desk.tools}
    assert tools["handover"].available_when == "this-agent-has-helpers"
    assert tools["tickets"].reaches.resource.available_when == "a-person-can-be-asked"
    (skill,) = desk.skills
    assert skill.available_when == "this-agent-has-connections"
    # The desk has no teammates; the lead has one.
    assert not available(desk, "this-agent-has-helpers")
    assert available(lead, "this-agent-has-helpers")
    # Both reach a server through a `connect:` line, and both use a skill.
    assert available(desk, "this-agent-has-connections")
    assert available(desk, "this-agent-has-procedures")
    # Nobody can be asked anything by either: no policy, no needs-a-person, no asks.
    assert not available(desk, "a-person-can-be-asked")
    assert available(desk, "always") and available(desk, "")
    with pytest.raises(ValueError, match="not a condition"):
        available(desk, "the-moon-is-full")
    # And the other answer to each of the three, on an agent that gives it: a
    # condition only ever asserted one way is held by nothing ("always yes" and
    # "always no" both passed). `caller` reaches one place, by `url:`, and uses
    # no skill; `payer`'s one action waits for a person.
    caller, payer = specs["caller"], specs["payer"]
    assert not available(caller, "this-agent-has-connections"), "a `url:` is not a connection"
    assert not available(caller, "this-agent-has-procedures")
    assert not available(caller, "a-person-can-be-asked")
    assert available(payer, "a-person-can-be-asked")
    assert available(payer, "this-agent-has-connections") and not available(payer, "this-agent-has-helpers")


def test_reads_only_is_carried_per_action(tmp_path: Path) -> None:
    tools = {t.name: t for t in _specs(tmp_path)["desk"].tools}
    assert tools["tickets"].reads_only == {"read-ticket": True, "close-ticket": False}
    assert tools["handover"].reads_only == {"hand-over": False}


def test_accepts_is_carried_with_shapes_the_vocabulary_reads(tmp_path: Path) -> None:
    desk = _specs(tmp_path)["desk"]
    assert desk.accepts == {
        "message": "text",
        "photos": "list of images",
        "voice": "a voice message",
        "contract": "a file",
    }
    kinds = {k: Shape.parse(v).kind for k, v in desk.accepts.items()}
    assert kinds == {"message": "text", "photos": "images", "voice": "audio", "contract": "file"}
    assert _specs(tmp_path / "again")["lead"].accepts == {}


def test_a_skills_references_and_assets_are_carried_by_name_and_place(tmp_path: Path) -> None:
    (skill,) = _specs(tmp_path)["desk"].skills
    assert skill.references == ("tone.md",)
    assert skill.references_at == "skills/house-style/references"
    assert skill.assets == ("logo.png",)
    assert skill.assets_at == "skills/house-style/assets"


def test_a_resource_carries_where_its_credential_is_kept_and_never_one(tmp_path: Path) -> None:
    tools = {t.name: t for t in _specs(tmp_path)["desk"].tools}
    resource = tools["tickets"].reaches.resource
    assert resource.auth_by_reference == "host/tickets-credential"
    assert tools["handover"].reaches.kind == "url" and tools["handover"].reaches.method == "post"
